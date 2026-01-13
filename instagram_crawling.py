import instaloader
import time
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore
import os
from dotenv import load_dotenv

load_dotenv()

# Firebase에 연결
firebase_path = os.getenv("FIREBASE_CRED_PATH")
if not firebase_admin._apps:
    cred = credentials.Certificate(firebase_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()


# Instagram ID와 학과/단과대명을 Firebase에서 로드하는 함수
def get_instagram_mapping():
    try:
        doc_ref = db.collection("metadata").document("categories")
        doc = doc_ref.get()
        if doc.exists:
            raw_list = doc.to_dict().get("instagram_id", [])
            mapping = {}
            for item in raw_list:
                mapping.update(item) # 각 맵 요소를 하나로 합침
            return mapping
        else:
            print("Firebase에서 매핑 데이터를 찾을 수 없습니다.")
            return {}
    except Exception as e:
        print(f"매핑 데이터 로드 실패: {e}")
        return {}


# 메인 크롤링 함수
def crawl_multiple_instagram_accounts():
    # Firebase에서 학과/단과대 별 계정 리스트 및 이름 매핑 로드
    ACCOUNT_MAP = get_instagram_mapping()
    account_list = list(ACCOUNT_MAP.keys())
    
    if not account_list:
        print("조회할 계정이 없습니다. 프로그램을 종료합니다.")
        return

    L = instaloader.Instaloader()
    
    # 브라우저 헤더 설정 (차단 방지용)
    L.context._session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
    })

    # 각 계정별 크롤링 시작
    for target_id in account_list:
        try:
            # 계정 이름 매핑
            account_display_name = ACCOUNT_MAP.get(target_id, target_id)
            print(f"\n{'='*20} [{account_display_name}] 접속 중 {'='*20}")
            
            # 프로필 로드
            profile = instaloader.Profile.from_username(L.context, target_id)
            
            # 게시물 크롤링
            posts = profile.get_posts()
            valid_post_count = 0
            seen_texts = set()

            for post in posts:
                # 텍스트 유무 및 중복 체크
                if not post.caption or post.caption.strip() == "":
                    continue
                current_caption = post.caption.strip()

                # 중복 본문 스킵
                if current_caption in seen_texts:
                    continue

                seen_texts.add(current_caption)
                valid_post_count += 1
                
                # 문서 ID 생성 및 중복 확인
                doc_id = f"{account_display_name}__{post.shortcode}(instagram)"
                doc_ref = db.collection("raw_notices").document(doc_id)
                
                if doc_ref.get().exists:
                    print(f"[-] ({valid_post_count}/4) 중복 스킵: {post.shortcode}")
                else:
                    # 이미지 추출 (단일/다중 이미지 대응)
                    image_urls = []
                    if post.typename == 'GraphSidecar':     # 다중 이미지 게시물
                        for node in post.get_sidecar_nodes():
                            if not node.is_video:
                                image_urls.append(node.display_url)
                    else:                                   # 단일 이미지 게시물
                        image_urls.append(post.url)

                    # 본문 첫 줄을 제목으로 추출
                    title = current_caption.split('\n')[0][:50]

                    # 데이터 저장
                    doc_data = {
                        "crawled_time": datetime.now().strftime("%Y.%m.%d %H:%M:%S"),
                        "full_text": current_caption,
                        "image_url": image_urls,
                        "link": f"https://www.instagram.com/p/{post.shortcode}/",
                        "source": account_display_name,
                        "status": "completed",
                        "title": title
                    }

                    doc_ref.set(doc_data)
                    print(f"({valid_post_count}/4) '{account_display_name}' 저장 완료")

                # 유효 게시물 4개를 채우면 다음 계정으로
                if valid_post_count >= 4:
                    break

            # 계정 간 차단 방지를 위한 대기
            time.sleep(12)

        except Exception as e:
            print(f"\n[{target_id}] 처리 중 에러: {e}")
            time.sleep(20)


# 실행 부분 (테스트용)
"""
if __name__ == "__main__":
    crawl_multiple_instagram_accounts()
"""