import time
import json
import firebase_admin
from firebase_admin import credentials, firestore
from google.genai import Client
import PIL.Image
import io
import requests
import re
import itertools
import os
from dotenv import load_dotenv
import itertools

load_dotenv()

# 사용할 API 키 리스트
API_KEYS = [
    os.getenv("GEMINI_API_KEY_1"),
    os.getenv("GEMINI_API_KEY_2"),
    os.getenv("GEMINI_API_KEY_3"),
]
# 키를 순환하며 제공하는 이터레이터 생성
key_rotation = itertools.cycle(API_KEYS)

# Firebase에 연결
firebase_path = os.getenv("FIREBASE_KEY_PATH")
cred = credentials.Certificate(firebase_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# 메타데이터
cached_depts = []
cached_colleges = []
cached_types = []


# DB에서 메타데이터 로드 함수
def load_metadata():
    global cached_depts, cached_colleges, cached_types
    try:
        doc = db.collection('metadata').document('categories').get()

        if doc.exists:
            data = doc.to_dict()
            cached_depts = data.get('departments', [])
            cached_colleges = data.get('colleges', [])
            cached_types = data.get('notice_types', [])

    except Exception as e:
        print(f"[분석] 동기화 실패: {e}")


# 텍스트 정리 함수
def clean_text(text):
    if not text: return ""

    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^\w\s가-힣.,\[\]():-]', '', text)

    return text.strip()[:600] # 최대 글자 수 제한(600자)


# Gemini 분석 수행 함수
def perform_gemini_analysis(batch_data):
    # API 키 순환에서 현재 키 가져오기
    current_key = next(key_rotation)
    client = Client(api_key=current_key)
    
    # 메타 데이터를 문자열로 변환
    dept_str = ", ".join(cached_depts) if cached_depts else "전체"
    college_str = ", ".join(cached_colleges) if cached_colleges else "전체"
    type_str = ", ".join(cached_types) if cached_types else "기타"

    # 배치 프롬프트 구성
    notices_context = ""
    contents = []
    
    for i, data in enumerate(batch_data):
        # 공지 본문 정리
        cleaned_text = clean_text(data.get('full_text', ''))
        notices_context += f"--- [공지 {i+1} 본문] ---\n{cleaned_text}\n\n"
        notices_context += f"[공지 출처]: {data.get('source', '알 수 없음')}\n"
        notices_context += f"[공지 링크]: {data.get('link', '')}\n\n"
        
        # 이미지 첨부
        image_urls = data.get('image_url', [])
        if isinstance(image_urls, str): image_urls = [image_urls]
        for url in image_urls:
            try:
                img_res = requests.get(url, timeout=5)
                if img_res.status_code == 200:
                    img = PIL.Image.open(io.BytesIO(img_res.content))
                    contents.append(f"[공지 {i+1} 관련 이미지]")
                    contents.append(img)
            except: pass

    prompt = f"""
    지금부터 대학 공지사항을 분석할 겁니다.
    아래 {len(batch_data)}개의 공지사항을 분석하여 각 항목별로 JSON 배열을 반환하세요.
    [주의사항]:
    1. 대상 학과나 단과대가 특정되지 않았다면 '전체'를 포함할 것.
    2. 반드시 제공된 목록에 있는 이름만 사용할 것.
    3. '공지 타입'은 반드시 1개여야 함.
    4. '학과명 혹은 단과대명'은 '공지 출처'를 참고하여 판단할 것.
    
    [공지 타입 분류 가이드] - 반드시 아래 6개 중 하나 이상을 선택하세요.
    - 학사/행정: 수강신청, 졸업, 성적, 휴/복학, 입학, 학위수여식 등 학교 운영 관련 의무 사항.
    - 장학/복지: 교내외 장학금, 학자금 대출, 학생회 복지 혜택(제휴), 기숙사비 지원 등 금전적 혜택.
    - 취업/대외: 채용 공고, 인턴십, 창업 지원, 외부 공모전, 자격증 취득 지원 등 커리어 관련.
    - 글로벌: 교환학생, 해외 연수, 토익/어학 강좌, 외국인 유학생 전용 공지.
    - 행사/시설: 축제, 강연회, 동아리 활동, 봉사활동, 학교 시설 이용 및 대관 안내.
    - 기타: 위 5개 항목에 명확히 해당하지 않는 일반 안내 사항 (학생회 부원 모집, 숏폼 챌린지, 학교 홍보 등).
    
    [학과 목록]: {dept_str}
    [단과대 목록]: {college_str}
    [공지 타입]: {type_str}

    {notices_context}

    [응답 형식]
    [
      {{
        "title": "공지 1 제목",
        "summary": ["요약1", "요약2", "요약3"],
        "category": ["학과명 혹은 단과대명", "공지 타입"],
        "deadline": "YYYY-MM-DD 또는 None"
      }},
      ... (총 {len(batch_data)}개 작성)
    ]
    """
    
    # 프롬프트를 콘텐츠 맨 앞에 삽입
    contents.insert(0, prompt)

    # Gemini API 호출
    try:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=contents)
        clean_json = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(clean_json)
    except Exception as e:
        print(f"[분석] Gemini 분석 에러: {e}")
        return None


# 메인 처리 함수
def process_raw_to_refined():

    # 보류 중(pending)인 공지사항을 가져와 리스트에 담음
    docs = list(db.collection('raw_notices').where('status', '==', 'pending').limit(15).stream())
    
    # 3개씩 묶어서 처리
    for i in range(0, len(docs), 3):
        batch_docs = docs[i:i+3]
        batch_data = [d.to_dict() for d in batch_docs]
        success_count = 0
        
        results = perform_gemini_analysis(batch_data)
        
        if results and len(results) == len(batch_docs):
            for doc, analysis in zip(batch_docs, results):
                raw_id = doc.id
                raw_data = doc.to_dict()
                db.collection('refined_notices').document(raw_id).set({
                    'title': analysis.get('title'),
                    'category': analysis.get('category'),
                    'summary': analysis.get('summary'),
                    'deadline': analysis.get('deadline'),
                    'link': raw_data.get('link'),
                    'source': raw_data.get('source'),
                    'processed_at': firestore.SERVER_TIMESTAMP,
                    'is_sent': False
                })
                doc.reference.update({'status': 'completed'})
                success_count += 1
        else:
            for d in batch_docs: d.reference.update({'status': 'error'})

        print(f"[분석] {success_count}/{len(batch_docs)}개의 공지사항 처리 완료.")
        time.sleep(10)

"""
# 실행 부분 (테스트용)
if __name__ == "__main__":
    load_metadata()
    while True:
        process_raw_to_refined()
        print("대기 중 (60초)...")
        time.sleep(60)
"""