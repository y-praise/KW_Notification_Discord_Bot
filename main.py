import os
import time
from multiprocessing import Process
from dotenv import load_dotenv
from kwapp import crawl_all_kw_sites
from instagram_crawling import crawl_multiple_instagram_accounts
from processor import load_metadata, process_raw_to_refined
from discord_bot import run_discord_bot

# 환경 변수 로드
load_dotenv(".env")

# 수집 프로세스 함수
def run_crawling_loop():
    while True:
        try:
            print("\n--- 학교 홈페이지 통합 수집 시작 ---")
            crawl_all_kw_sites()
            
            print("\n--- 인스타그램 수집 시작 ---")
            crawl_multiple_instagram_accounts()
            
        except Exception as e:
            print(f"[Crawler] 에러 발생: {e}")
            time.sleep(60)

# 분석 프로세스 함수
def run_processor_loop():
    # 시작 전 DB에서 최신 카테고리/학과 목록 한 번 동기화
    load_metadata() 
    
    while True:
        try:
            print("\n--- Gemini 분석 및 데이터 정제 시작 ---")
            process_raw_to_refined()
            print(f"[{time.strftime('%H:%M:%S')}] 분석 루틴 완료. 5분 대기...")
            time.sleep(300)
        except Exception as e:
            print(f"[Processor] 에러 발생: {e}")
            time.sleep(60)

# 디스코드 봇 프로세스 함수
def run_bot_process():
    token = os.getenv('DISCORD_TOKEN')
    channel_id = os.getenv('DISCORD_CHANNEL_ID')

    if not token or not channel_id:
        print("[DiscordBot] 에러: .env 파일에 디스코드 설정이 없습니다.")
        return

    print("[DiscordBot] 실시간 알림 서비스 시작...")
    try:
        run_discord_bot(token, channel_id)
    except Exception as e:
        print(f"[DiscordBot] 종료됨: {e}")

if __name__ == "__main__":
    print("========================================")
    print("광운대 통합 알림 시스템 시작")
    print("========================================")

    # 1. 수집 프로세스 (학교 홈페이지 + 인스타)
    p_crawler = Process(target=run_crawling_loop, name="Crawler")
    
    # 2. 분석 프로세스 (Gemini AI)
    p_processor = Process(target=run_processor_loop, name="Processor")
    
    # 3. 알림 프로세스 (Discord Bot)
    p_bot = Process(target=run_bot_process, name="DiscordBot")

    # 모든 프로세스 시작
    p_crawler.start()
    p_processor.start()
    p_bot.start()

    # 프로세스들이 종료되지 않도록 유지
    try:
        p_crawler.join()
        p_processor.join()
        p_bot.join()
    except KeyboardInterrupt:
        print("\n시스템을 종료합니다...")
        p_crawler.terminate()
        p_processor.terminate()
        p_bot.terminate()