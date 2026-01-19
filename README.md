# 📢 광운대 통합 공지 알림 서비스 (Kwangwoon Notification System)

> **"생성형 AI를 활용하여 다중 채널 공지사항을 자동 분석하고 맞춤형 알림을 제공하는 광운대 통합 정보 큐레이션 시스템"**

교내 26개 이상의 학과 웹사이트와 인스타그램 SNS에 파편화된 공지사항을 실시간으로 수집하고, **Gemini AI**를 통해 핵심 내용을 요약 및 분류하여 **디스코드**로 맞춤형 알림을 전달하는 서비스입니다.



## 🛠 Tech Stack
* **Language**: Python 3.x
* **Database**: Firebase Cloud Firestore
* **AI/ML**: Google Gemini 2.0 Flash API
* **Crawling**: Selenium, BeautifulSoup4, Instaloader
* **Interface**: Discord.py (Discord Bot)

## ✨ Key Features
1. **다중 채널 자동 수집**: 학과 홈페이지(Web)와 인스타그램(SNS) 게시물을 주기적으로 탐색하여 신규 등록 및 기존 내용 수정 사항을 실시간 감지합니다.
2. **AI 기반 스마트 정제**: AI가 공지 본문과 이미지(포스터) 맥락을 동시에 분석하여 핵심 내용을 요약하고 마감 기한(Deadline)을 자동 추출합니다.
3. **6대 핵심 카테고리 분류**: '학사/행정, 장학/복지, 취업/대외, 글로벌, 행사/시설, 기타'의 체계로 공지를 자동 분류하여 정보의 가독성을 높였습니다.
4. **개인화된 구독 및 타겟팅 알림**: 사용자가 설정한 관심 학과와 주제에 부합하는 공지만 선별하여 디스코드 DM으로 개별 발송합니다.



## 👥 Team: 그것이 알고싶다
역할 분담을 통해 데이터 수집부터 서비스 제공까지의 전 과정을 파이프라인으로 구축하였습니다.

* **홍진표**: 광운대 학과 홈페이지 및 인스타그램 공지사항 크롤링 엔진 구현
* **윤찬송**: Gemini API 연동을 통한 데이터 전처리, 요약 및 6종 카테고리 자동 분류 로직 구현
* **차승환**: 디스코드 봇 인터페이스 설계 및 사용자별 맞춤 구독/실시간 알림 시스템 구현

## 🚀 Quick Start
1. **환경 변수 설정**: `.env` 파일에 API 키와 Firebase 경로를 설정합니다.
   ```env
   GEMINI_API_KEY_1=your_key
   DISCORD_TOKEN=your_token
   FIREBASE_KEY_PATH=your_json_path
   DISCORD_CHANNEL_ID=your_channel_id
   ```

2. **의존성 라이브러리 설치**: 아래 명령어를 터미널에 복사하여 붙여넣으면 모든 필수 라이브러리가 한 번에 설치됩니다.
   ```bash
   pip install requests beautifulsoup4 selenium webdriver-manager instaloader google-genai python-dotenv firebase-admin discord.py
   ```


3. **시스템 실행**: 라이브러리 설치와 환경 변수 설정이 완료되면 메인 스크립트를 실행하여 파이프라인을 시작합니다.
   ```bash
   python main.py
   ```
4. **디스코드 접속 및 구독 설정**: 시스템이 실행 중인 상태에서 아래 링크를 통해 알림 구독을 완료합니다.  
   https://discord.gg/TTDygDpg
