import requests
from bs4 import BeautifulSoup
from datetime import datetime
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import hashlib
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

if not firebase_admin._apps:
    cred = credentials.Certificate("fkey.json") 
    firebase_admin.initialize_app(cred)
db = firestore.client() # 데이터베이스 접속 객체


def get_kw_notices():
    BASE_URL = "https://www.kw.ac.kr"
    NOTICE_LIST_URL = "https://www.kw.ac.kr/ko/life/notice.jsp" 


    # 헤더 설정 (브라우저인 척 속이기)
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 공지사항 리스트 파싱
    articles = soup.select(".board-list-box ul li") 
    
    results = []
    
    for article in articles[:2]:  #크롤링할 갯수
        # 제목 및 링크 추출 로직 (사이트 구조에 맞춰 수정 필요)
        a_tag = article.select_one("div.board-text > a")
        
        # a_tag가 없는 항목(혹시 모를 빈 줄 등)은 건너뛰기
        if not a_tag:
            continue

        if a_tag.select_one(".ico-new"):
            a_tag.select_one(".ico-new").decompose() # 태그 삭제

        if a_tag.select_one(".ico-new"):
            a_tag.select_one(".ico-new").decompose()    # Attachment삭제 

        for junk in a_tag.select(".ico-file"): # 파일 아이콘 클래스 삭제
            junk.decompose()
            
        # 클래스 이름이 달라서 안 지워질 경우를 대비한 강력한 삭제 
        for span in a_tag.select("span"):
            if "Attachment" in span.text:
                span.decompose()

        raw_title = a_tag.text

        title = " ".join(raw_title.split())

        relative_link = a_tag['href'] # 상대경로 -> 절대경로 변환
        if "http" not in relative_link:
            link = BASE_URL + relative_link
        else:
            link = relative_link
        
        # [상세 페이지 접속 - 이미지 확인]
        sub_res = requests.get(link, headers=headers)
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        content_box = sub_soup.select_one(".board-view-box") # 광운대 본문 영역 클래스
        
        if content_box:
            trash_tags = [ #본문에서 삭제할 태그들
                ".title",      # 제목 영역
                ".subject",         # 제목 영역 (다른 게시판 스타일일 경우)
                ".info",       # 작성일, 조회수 등 정보창
                ".info",            # 정보창 (다른 스타일)
                ".attachment",       # 첨부파일 목록 (Attachment...)
                ".ico-new",         # New 아이콘 텍스트
                "dt", "dd"          # 기타 정의 목록 태그
            ]
        
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", "").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
        else:
            content = "not found"

        
        img_tags = sub_soup.select("img[src*='webeditor']") # 본문 내 이미지 태그 찾기
        img_urls = []
        for img in img_tags:
            src = img.get('src')
            if not src.startswith("http"):
                src = BASE_URL + src
            img_urls.append(src)
            
        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        #크롤링시간

        data = {
            "crawled_at": crawled_time, #크롤링한시간
            "full_text": content, #본문내용
            "image_url": img_urls,  #이미지 url
            "link": link,   #링크
            "source": "광운대학교",
            "status": "pending",
            "title": title  #제목
        }
        results.append(data)
        print(f"title : {title}")  #제목 모음들
        
    return results  #광운대 공지사항 크롤링

def get_kwai_notices():
    BASE_URL = "https://aicon.kw.ac.kr/main/main.php"
    NOTICE_LIST_URL = "https://aicon.kw.ac.kr/administration/notice.php" 


    headers = {'User-Agent': 'Mozilla/5.0'}
    
    results = []
    page = 1 # 1페이지부터 시작
    target_count = 5 # 수집하고 싶은 '일반' 게시글 수
    
    print(f"최신 글 {target_count}개를 찾을 때까지 페이지를 탐색합니다...")

    # 목표 개수를 채울 때까지 계속 반복 (단, 최대 5페이지까지만 제한)
    while len(results) < target_count and page <= 5:
        print(f"📡 [Page {page}] 탐색 중...")
        
        # 페이지 번호가 포함된 URL 접속

        url = f"{NOTICE_LIST_URL}?page={page}"
        
        try:
            res = requests.get(url, headers=headers)
            res.encoding = 'utf-8'
            soup = BeautifulSoup(res.text, 'html.parser')
            
            # 행(tr) 가져오기
            articles = soup.select(".board-list tr")
            if not articles: articles = soup.select("tbody tr")
            
            if not articles:
                print("게시글 목록을 찾을 수 없습니다. 크롤링 종료.")
                break

            # 헤더(첫 줄) 제외하고 반복
            for article in articles[1:]:
                # 목표 개수 다 채웠으면 즉시 중단
                if len(results) >= target_count:
                    break

                # 첫 번째 칸(td)에 번호나 '공지' 텍스트가 들어있음
                no_td = article.select_one("td")
                if not no_td: continue
                
                no_text = no_td.get_text(strip=True)
                
                # "공지"라고 적혀있으면 건너뛰기 (이미지 아이콘인 경우도 있음)
                if "공지" in no_text or article.select_one("img[src*='ico_nt']"):
                    continue
                
                # --- [제목 추출] ---
                title_td = article.select_one(".subject")
                if not title_td: title_td = article.select_one(".title")
                if not title_td: title_td = article.select_one("td.left")
                
                if not title_td:
                    tds = article.select("td")
                    if len(tds) > 2: title_td = tds[1]

                if not title_td: continue
                a_tag = title_td.select_one("a")
                if not a_tag: continue

                # 청소
                for junk in a_tag.select("img, span"): junk.decompose()

                raw_title = a_tag.get_text(separator=" ", strip=True)
                if "New" in raw_title: raw_title = raw_title.replace("New", "")
                title = " ".join(raw_title.split())

                # --- [링크 생성] ---
                ADMIN_URL = "https://aicon.kw.ac.kr/administration"
                relative_link = a_tag['href']
                if "http" not in relative_link:
                    if relative_link.startswith("/"):
                        link = f"https://aicon.kw.ac.kr{relative_link}"
                    else:
                        clean_link = relative_link.replace("./", "")
                        link = f"{ADMIN_URL}/{clean_link}"
                else:
                    link = relative_link
                
                # --- [상세 페이지 접속] ---
                sub_res = requests.get(link, headers=headers)
                sub_res.encoding = 'utf-8' 
                sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

                content_box = None
                candidates = [".view_td", ".board_view_con", ".view_content", ".board-view"]
                
                for candidate in candidates:
                    content_box = sub_soup.select_one(candidate)
                    if content_box: break

                if not content_box:
                     divs = sub_soup.select("div")
                     valid_divs = [d for d in divs if len(d.text) > 50]
                     if valid_divs:
                        content_box = max(valid_divs, key=lambda x: len(x.text))

                img_urls = []
                content = "본문 내용을 찾을 수 없습니다."

                if content_box:
                    trash_tags = [".table_view_list", ".view_file", ".file_area", "dt", "dd", ".view_title_box"]
                    for selector in trash_tags:
                        for trash in content_box.select(selector):
                            trash.decompose()
                    
                    content = content_box.get_text(separator="\n", strip=True)
                    content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
                    content = content.replace("\u200b", "").replace("\xa0", " ")
                    
                    if len(content) > 3000:
                        content = content[:3000] + "...(내용 잘림)"

                    img_tags = content_box.select("img")
                    for img in img_tags:
                        src = img.get('src')
                        if not src: continue
                        if src.startswith("data:"): continue
                        if "icon" in src or "logo" in src or "common" in src: continue
                        
                        if not src.startswith("http"):
                            if src.startswith("../"):
                                 src = src.replace("../", "")
                                 src = f"https://aicon.kw.ac.kr/{src}"
                            elif src.startswith("/"):
                                 src = f"https://aicon.kw.ac.kr{src}"
                            else:
                                 src = f"{ADMIN_URL}/{src}"
                        img_urls.append(src)

                crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                data = {
                    "crawled_at": crawled_time, #크롤링한시간
                    "full_text": content, #본문내용
                    "image_url": img_urls,  #이미지 url
                    "link": link,   #링크
                    "source": "인공지능융합대학",
                    "status": "pending",
                    "title": title  #제목
                }
                results.append(data)
                print(f"수집 성공 ({len(results)}/{target_count}): {title}")
        
        except Exception as e:
            print(f"Page {page} 크롤링 중 에러 발생: {e}")
        
        # 다음 페이지로 이동
        page += 1
        
    return results  #인융대 공지사항 크롤링

def get_kwei_notices():   # 전자정보공과대학 공지사항 크롤링
    BASE_URL = "https://ei.kw.ac.kr/community"
    NOTICE_LIST_URL = "https://ei.kw.ac.kr/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 찾기 (제목이 있는 표 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        articles = soup.select(".board_table tr") # board-table이 아니라 board_table(언더바)
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] 공지글 패스
        if "notice_tr" in article.get("class", []):
            continue
            
        no_td = article.select_one("td")
        if not no_td: continue
        no_text = no_td.get_text(strip=True)
        if not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue
        a_tag = title_td.select_one("a")
        if not a_tag: continue

        for junk in a_tag.select("img, span"): junk.decompose()
        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://ei.kw.ac.kr{clean_link}"
            else:
                link = f"{BASE_URL}/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 정확한 본문 찾기]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [핵심] 전자정보대 본문은 무조건 .view_con 클래스 안에 있음
        content_box = sub_soup.select_one(".view_con")
        
        # 만약 .view_con을 못 찾으면 2순위 후보 탐색
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. 본문 내부의 불필요한 태그 삭제 (HWP 데이터 등)
            for junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                junk.decompose()

            # 2. 잡다한 메타 정보 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출] content_box 안에서만 검색
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://ei.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://ei.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/{src}"
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전자정보공과대학",
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwbiz_notices():   # 경영대학 공지사항 크롤링
    BASE_URL = "https://biz.kw.ac.kr"
    NOTICE_LIST_URL = "https://biz.kw.ac.kr/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 표 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        articles = soup.select(".board-list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] 공지글 패스
        no_td = article.select_one("td")
        if not no_td: continue
        no_text = no_td.get_text(strip=True)
        if "notice_tr" in article.get("class", []) or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue
        a_tag = title_td.select_one("a")
        if not a_tag: continue

        for junk in a_tag.select("img, span"): junk.decompose()
        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://biz.kw.ac.kr{clean_link}"
            else:
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 정확한 본문 찾기]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [핵심 수정] 1. 본문 박스 (.view_con) 찾기 (제공해주신 HTML 기준)
        content_box = sub_soup.select_one(".view_con")
        
        # 없으면 예비 후보군 시도
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # [핵심 수정] 2. HWP 에디터 데이터 덩어리 제거 (hwpEditorBoardContent)
            # 이게 있으면 텍스트가 지저분해집니다.
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 3. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [핵심 수정] 4. 이미지 추출 (content_box 안에서만)
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://biz.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://biz.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}" # /community/data/...
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "경영대학", 
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwingenium_notices():   # 인제니움학부대학 공지사항 크롤링
    BASE_URL = "https://ingenium.kw.ac.kr"
    NOTICE_LIST_URL = "https://ingenium.kw.ac.kr/inform/notice.php" 

    # 헤더 설정
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 공지사항 리스트 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 인제니움대는 .list_wrap table 또는 tbody 사용
        articles = soup.select(".list_wrap table tbody tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        no_td = article.select_one("td")
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글(notice 클래스) 확인 및 번호 확인
        # 인제니움대는 공지글에 'notice' 클래스가 붙거나 번호 칸에 '공지'라고 적혀있음
        if "notice" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://ingenium.kw.ac.kr{clean_link}"
            else:
                # 인제니움대 공지사항은 inform 폴더 안에 있음
                link = f"{BASE_URL}/inform/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        # 인제니움대학은 .view_con 클래스를 사용합니다.
        content_box = sub_soup.select_one(".view_con")
        
        # 없으면 예비 후보군 시도
        if not content_box:
            content_box = sub_soup.select_one(".board_view")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://ingenium.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://ingenium.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/inform/{src}" # /inform/data/...
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "인제니움학부대학", 
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwee_notices():   # 전자공학과 공지사항 크롤링
    BASE_URL = "https://ee.kw.ac.kr"
    NOTICE_LIST_URL = "https://ee.kw.ac.kr/HTML/department/undergrad_info.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 전자공학과는 .board_list 클래스를 사용
        articles = soup.select(".board_list tbody tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        # 전자공학과는 번호 칸 클래스가 .num 인 경우가 많음
        no_td = article.select_one(".num")
        if not no_td: no_td = article.select_one("td") # 없으면 첫번째 칸
        
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        
        # "공지" 텍스트가 있거나, 숫자가 아니면 패스
        if "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1] # 보통 2번째 칸이 제목

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        for junk in a_tag.select("img, span"): junk.decompose()
        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://ee.kw.ac.kr{clean_link}"
            else:
                # 전자공학과 공지사항은 보통 같은 폴더 내에 있음
                # /HTML/department/view.php...
                link = f"https://ee.kw.ac.kr/HTML/department/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        content_box = sub_soup.select_one(".view_con")
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://ee.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://ee.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전자공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwelcomm_notices():   # 전자통신공학과 공지사항 크롤링
    BASE_URL = "https://elcomm.kw.ac.kr"
    NOTICE_LIST_URL = "https://elcomm.kw.ac.kr/department/office_notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        # 전자통신공학과는 tbody가 없는 경우가 많음
        articles = table.select("tr") 
    else:
        # .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        # 번호 칸(.num)에 '공지' 텍스트나 아이콘이 있으면 패스
        no_td = article.select_one(".num")
        if not no_td: no_td = article.select_one("td") # 없으면 첫번째 칸
        
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_icon 클래스 등)
        if "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://elcomm.kw.ac.kr{clean_link}"
            else:
                # 전자통신공학과 공지사항은 department 폴더 안에 있음
                link = f"{BASE_URL}/department/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        # 전자통신공학과는 .view_con 클래스를 주로 사용
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://elcomm.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://elcomm.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전자통신공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwelecradiowave_notices():   # 전자융합공학과 공지사항 크롤링
    BASE_URL = "https://radiowave.kw.ac.kr"
    NOTICE_LIST_URL = "https://radiowave.kw.ac.kr/community/s_notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 전자융합공학과는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        # 번호 칸(.num)에 '공지' 텍스트나 아이콘이 있으면 패스
        no_td = article.select_one(".num")
        if not no_td: no_td = article.select_one("td") 
        
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_icon 클래스 등)
        if "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://radiowave.kw.ac.kr{clean_link}"
            else:
                # 전자융합공학과 공지사항은 community 폴더 안에 있음
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        # 전자융합공학과는 .view_con 클래스를 주로 사용
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://radiowave.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://radiowave.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전자융합공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwelectric_notices():   # 전기공학과 공지사항 크롤링
    BASE_URL = "https://electric.kw.ac.kr"
    NOTICE_LIST_URL = "https://electric.kw.ac.kr/community/s_notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 전기공학과는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        # 번호 칸(.num)에 '공지' 텍스트나 아이콘이 있으면 패스
        no_td = article.select_one(".num")
        if not no_td: no_td = article.select_one("td") 
        
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인
        if "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://electric.kw.ac.kr{clean_link}"
            else:
                # 전기공학과 공지사항은 community 폴더 안에 있음
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        # 전기공학과는 .view_con 클래스를 주로 사용
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://electric.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://electric.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전기공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwem_notices():   # 전자재료공학과 공지사항 크롤링
    BASE_URL = "https://snme.kw.ac.kr"
    NOTICE_LIST_URL = "https://snme.kw.ac.kr/college/college_notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' 
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 소융대는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        no_td = article.select_one("td")
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_tr 클래스, "공지" 텍스트, 숫자가 아닌 경우)
        if "notice_tr" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://snme.kw.ac.kr{clean_link}"
            else:
                # 소융대 공지사항은 college 폴더 안에 있음
                link = f"{BASE_URL}/college/{clean_link}"
        else:
            link = relative_link
        
        # [상세 페이지 접속]
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        # 소융대는 .view_con 클래스를 주로 사용
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://snme.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://snme.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/college/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "전자재료공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwsemicon_notices():   # 반도체시스템공학부 공지사항 크롤링
    BASE_URL = "https://semicon.kw.ac.kr"
    NOTICE_LIST_URL = "https://semicon.kw.ac.kr/HTML/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 반도체학부는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        no_td = article.select_one("td")
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_tr, "공지" 텍스트, 숫자 여부)
        if "notice_tr" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://semicon.kw.ac.kr{clean_link}"
            else:
                # 반도체학부 공지사항은 /HTML/community/ 폴더 안에 있음
                link = f"{BASE_URL}/HTML/community/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 본문 파싱]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [본문 영역 찾기]
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://semicon.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://semicon.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/HTML/community/{src}" # 경로 주의!
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "반도체시스템공학부", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwarchi_notices():   # 건축공학과 공지사항 크롤링
    BASE_URL = "https://archi.kw.ac.kr"
    NOTICE_LIST_URL = "https://archi.kw.ac.kr/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 건축공학과는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        no_td = article.select_one("td")
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_tr 클래스, "공지" 텍스트, 숫자 여부)
        if "notice_tr" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://archi.kw.ac.kr{clean_link}"
            else:
                # 건축공학과 공지사항은 community 폴더 안에 있음
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 본문 파싱]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [1단계] 메뉴바, 헤더, 푸터 등 방해꾼들 미리 제거 (Pre-cleaning)
        global_trash = [
            "header", "footer", "nav", 
            "#header", "#footer", ".header", ".footer",
            ".gnb", ".lnb", ".snb", 
            ".top_menu", ".login_wrap", 
            ".btn_list", ".paging_wrap", 
            ".view_go", ".prev_next" # 이전글/다음글 목록 제거
        ]
        for selector in global_trash:
            for tag in sub_soup.select(selector):
                tag.decompose()

        # [2단계] 본문 영역 찾기
        # 건축공학과는 .view_con 클래스를 주로 사용
        content_box = sub_soup.select_one(".view_con")
        
        if not content_box:
            content_box = sub_soup.select_one(".board_view_con")
        if not content_box:
            content_box = sub_soup.select_one(".view_content")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # 1. HWP 에디터 데이터 제거 (필수)
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 2. 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://archi.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://archi.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}" 
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "건축공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwchemng_notices():   # 화학공학과 공지사항 크롤링
    BASE_URL = "https://chemng.kw.ac.kr"
    NOTICE_LIST_URL = "https://chemng.kw.ac.kr/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8'
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] 공지글 패스
        no_td = article.select_one("td")
        if not no_td: continue
        no_text = no_td.get_text(strip=True)
        if "notice_tr" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue
        a_tag = title_td.select_one("a")
        if not a_tag: continue

        for junk in a_tag.select("img, span"): junk.decompose()
        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://chemng.kw.ac.kr{clean_link}"
            else:
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 강력 본문 탐색]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [1단계] 메뉴바, 헤더, 푸터 등 방해꾼들 삭제 (가장 중요!)
        global_trash = [
            "header", "footer", "nav", 
            "#header", "#footer", ".header", ".footer",
            ".gnb", ".lnb", ".snb", ".top_menu", 
            ".btn_list", ".paging_wrap", ".view_go", ".prev_next"
        ]
        for selector in global_trash:
            for tag in sub_soup.select(selector):
                tag.decompose()

        # [2단계] 본문 영역 찾기 (우선순위: 클래스 -> ID -> 최후의 수단)
        content_box = None
        
        # 화학공학과에서 쓸만한 클래스/ID 후보군
        candidates = [".view_con", "#view_con", ".board_view", ".view_content", ".view_td", "td.view_content"]
        
        for candidate in candidates:
            content_box = sub_soup.select_one(candidate)
            if content_box: break

        # [3단계] **자동 탐색 모드** (클래스로 못 찾았을 때 발동)
        if not content_box:
             # 페이지에 남은 모든 div와 td를 긁어모읍니다. (메뉴바는 이미 지웠으니 안전)
             all_blocks = sub_soup.select("div, td")
             
             # 글자 수가 50자 이상인 덩어리만 추립니다.
             valid_blocks = [b for b in all_blocks if len(b.get_text(strip=True)) > 50]
             
             if valid_blocks:
                # 그 중에서 글자 수가 가장 많은 덩어리를 본문으로 찍습니다.
                content_box = max(valid_blocks, key=lambda x: len(x.get_text(strip=True)))
                # print("  ⚠️ 경고: 본문 클래스를 못 찾아 '자동 탐색'으로 가장 긴 글을 가져왔습니다.")

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # HWP 에디터 데이터 제거
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # 이미지 추출
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://chemng.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://chemng.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}"
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "화학공학과", 
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwenv_notices():   # 환경공학과 공지사항 크롤링
    BASE_URL = "https://env.kw.ac.kr"
    NOTICE_LIST_URL = "https://env.kw.ac.kr/community/notice.php" 

    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(NOTICE_LIST_URL, headers=headers)
    res.encoding = 'utf-8' # 한글 깨짐 방지
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 1. 목록 파싱 (제목이 있는 테이블 찾기)
    header = soup.find(lambda tag: tag.name in ['th', 'td'] and "제목" in tag.text)
    
    if header:
        table = header.find_parent("table")
        articles = table.select("tr")
    else:
        # 환경공학과는 .board_list 클래스를 주로 사용
        articles = soup.select(".board_list tr")
        if not articles: articles = soup.select("tbody tr")

    print(f"🔍 찾아낸 게시글 수: {len(articles)}")
    
    results = []
    target_count = 5 
    
    # 헤더 제외하고 반복
    for article in articles[1:]: 
        if len(results) >= target_count:
            break

        # [필터링] '공지' 글 건너뛰기
        no_td = article.select_one("td")
        if not no_td: continue
        
        no_text = no_td.get_text(strip=True)
        # 공지글 확인 (notice_tr, 공지 텍스트, 숫자 여부)
        if "notice_tr" in article.get("class", []) or "공지" in no_text or not no_text.replace(",", "").isdigit():
            continue

        # [제목 추출]
        title_td = article.select_one(".subject")
        if not title_td: title_td = article.select_one(".title")
        if not title_td: title_td = article.select_one("td.left")
        
        # 최후의 수단: 두 번째 칸
        if not title_td:
            tds = article.select("td")
            if len(tds) > 2: title_td = tds[1]

        if not title_td: continue

        a_tag = title_td.select_one("a")
        if not a_tag: continue

        # [청소]
        for junk in a_tag.select("img, span"): 
            junk.decompose()

        raw_title = a_tag.get_text(separator=" ", strip=True)
        if "New" in raw_title: raw_title = raw_title.replace("New", "")
        title = " ".join(raw_title.split())

        # [링크 생성]
        relative_link = a_tag['href']
        if "http" not in relative_link:
            clean_link = relative_link.replace("./", "")
            if clean_link.startswith("/"):
                link = f"https://env.kw.ac.kr{clean_link}"
            else:
                # 환경공학과 공지사항은 community 폴더 안에 있음
                link = f"{BASE_URL}/community/{clean_link}"
        else:
            link = relative_link
        
        # ---------------------------------------------------------------
        # [상세 페이지 접속 & 강력 본문 탐색]
        # ---------------------------------------------------------------
        sub_res = requests.get(link, headers=headers)
        sub_res.encoding = 'utf-8'
        sub_soup = BeautifulSoup(sub_res.text, 'html.parser')

        # [1단계] 메뉴바, 헤더, 푸터 등 방해꾼들 삭제
        global_trash = [
            "header", "footer", "nav", 
            "#header", "#footer", ".header", ".footer",
            ".gnb", ".lnb", ".snb", ".top_menu", 
            ".btn_list", ".paging_wrap", ".view_go", ".prev_next"
        ]
        for selector in global_trash:
            for tag in sub_soup.select(selector):
                tag.decompose()

        # [2단계] 본문 영역 찾기
        content_box = None
        # 환경공학과에서 쓸만한 클래스 후보군
        candidates = [".view_con", "#view_con", ".board_view", ".view_content", ".view_td", "td.view_content"]
        
        for candidate in candidates:
            content_box = sub_soup.select_one(candidate)
            if content_box: break

        # [3단계] 자동 탐색 모드 (클래스로 못 찾았을 때 발동)
        if not content_box:
             all_blocks = sub_soup.select("div, td")
             valid_blocks = [b for b in all_blocks if len(b.get_text(strip=True)) > 50]
             
             if valid_blocks:
                content_box = max(valid_blocks, key=lambda x: len(x.get_text(strip=True)))

        img_urls = []
        content = "본문 내용을 찾을 수 없습니다."

        if content_box:
            # HWP 에디터 데이터 제거
            for hwp_junk in content_box.select("#hwpEditorBoardContent, .hwp_editor_board_content"):
                hwp_junk.decompose()

            # 잡다한 태그 삭제
            trash_tags = [".view-file", ".file", "dt", "dd", ".view-info", "ul.view-info", ".view_title_box"]
            for selector in trash_tags:
                for trash in content_box.select(selector):
                    trash.decompose()
            
            content = content_box.get_text(separator="\n", strip=True)
            content = content.replace("\n", " ").replace("\r", "").replace("\t", "")
            content = content.replace("\u200b", "").replace("\xa0", " ")
            
            if len(content) > 3000:
                content = content[:3000] + "...(내용 잘림)"

            # [이미지 추출]
            img_tags = content_box.select("img")
            for img in img_tags:
                src = img.get('src')
                if not src: continue
                if src.startswith("data:"): continue
                if "icon" in src or "logo" in src or "common" in src: continue
                
                if not src.startswith("http"):
                    if src.startswith("../"):
                         src = src.replace("../", "")
                         src = f"https://env.kw.ac.kr/{src}"
                    elif src.startswith("/"):
                         src = f"https://env.kw.ac.kr{src}"
                    else:
                         src = f"{BASE_URL}/community/{src}" # /community/data/...
                img_urls.append(src)

        crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 요청하신 데이터 포맷 (data)
        data = {
            "crawled_at": crawled_time,
            "full_text": content,
            "image_url": img_urls,
            "link": link,
            "source": "환경공학과", # 출처 변경
            "status": "pending",
            "title": title
        }
        results.append(data)
        print(f"[{data['source']}] 수집 성공: {title}")
        
    return results

def get_kwuarchi_notices():   # 건축학과 공지사항 크롤링
    BASE_URL = "https://www.kwuarchitecture.com"
    NOTICE_LIST_URL = "https://www.kwuarchitecture.com/blank-1" 

    chrome_options = Options()
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    
    results = []
    
    try:
        print(f"📡 [건축학과] 페이지 접속 중: {NOTICE_LIST_URL}")
        driver.get(NOTICE_LIST_URL)
        
        # 1. 로딩 대기
        print("⏳ 페이지 로딩 및 스크롤 중...")
        time.sleep(5)
        
        # 스크롤을 내려서 게시글 로딩 유도
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(3)

        # 2. 링크 수집
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        links = soup.select("a")
        
        notice_links = []
        seen_links = set()

        print(f"🧐 페이지 내 발견된 총 링크 수: {len(links)}개")

        for a in links:
            href = a.get('href', '')
            if not href: continue
            
            # [핵심 수정] URL 패턴을 '/single-post/'로 변경!
            if "/single-post/" in href:
                # 중복 제거
                if href not in seen_links:
                    seen_links.add(href)
                    notice_links.append(href)

        print(f"🔍 공지사항으로 식별된 링크 수: {len(notice_links)}")
        
        target_count = 5 
        
        # 3. 상세 페이지 순회
        for link in notice_links[:target_count]:
            print(f"  👉 접속 시도: {link}")
            driver.get(link)
            
            # 본문 로딩 대기
            time.sleep(5) 
            
            sub_soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # [제목 추출]
            title_tag = sub_soup.select_one("h1")
            # 제목이 h1이 아닐 경우 span 등에서 스타일로 찾기
            if not title_tag:
                title_tags = sub_soup.select("span")
                # 글자 크기가 큰 span을 제목으로 추정
                for t in title_tags:
                    style = t.get('style', '')
                    if 'font-size' in style and ('2' in style or '3' in style or '4' in style): # 대충 큰 폰트
                        title_tag = t
                        break
            
            title = title_tag.get_text(strip=True) if title_tag else "제목 없음"

            # [본문 추출] Wix 특유의 구조 대응
            content_box = sub_soup.select_one("article")
            if not content_box:
                content_box = sub_soup.select_one("main")
            if not content_box:
                # Wix 텍스트 박스 클래스
                content_box = sub_soup.select_one("div[data-testid='richTextElement']")

            img_urls = []
            content = "본문 내용을 찾을 수 없습니다."

            if content_box:
                for trash in content_box.select("style, script, button"):
                    trash.decompose()
                
                content = content_box.get_text(separator="\n", strip=True)
                if len(content) > 3000:
                    content = content[:3000] + "..."

                # 이미지 추출
                img_tags = content_box.select("img")
                for img in img_tags:
                    src = img.get('src')
                    if not src: continue
                    # Wix 이미지 CDN 주소 처리
                    if src.startswith("wix:image"): continue 
                    if not src.startswith("http"): continue
                    img_urls.append(src)

            crawled_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            data = {
                "crawled_at": crawled_time,
                "full_text": content,
                "image_url": img_urls,
                "link": link,
                "source": "건축학과", 
                "status": "pending",
                "title": title
            }
            results.append(data)
            print(f"  ✅ 수집 성공: {title}")

    except Exception as e:
        print(f"⚠️ 크롤링 중 오류 발생: {e}")
        
    finally:
        driver.quit()
        
    return results



def save_to_firebase(data_list):     #파이어베이스 저장 함수
    print(f"데이터베이스 저장을 시작합니다... ({len(data_list)}개)")
    
    # 'kw_notices'라는 이름의 컬렉션(폴더)에 저장
    collection_ref = db.collection('test_notices') 
    
    for data in data_list:
        raw_id = data['source']
        safe_id = raw_id.replace("/", "_").replace("\\", "_").replace(".", "_")
        # / 있으면 에러나는거 방지
       
        link_hash = hashlib.md5(data['link'].encode()).hexdigest()[:6]
        doc_id = f"{safe_id}__{link_hash}"
        #해시값으로 중복제목 방지
        
        # doc_id 문서가 있으면 업데이트(덮어쓰기), 없으면 새로 생성
        collection_ref.document(doc_id).set(data)
        print(f"  - 저장 완료: {doc_id}")
        
    print("모든 데이터 저장 완료!")

crawled_data = get_kwuarchi_notices()     

if crawled_data:
    save_to_firebase(crawled_data)
else:
    print("수집된 데이터가 없습니다.")

