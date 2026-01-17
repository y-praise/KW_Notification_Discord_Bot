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

# 크롤링 프로세스 함수
def run_crawling_loop():
    print("[크롤링] 크롤링 프로세스 시작...")
    while True:
        try:
            crawl_all_kw_sites()
            crawl_multiple_instagram_accounts()
            
        except Exception as e:
            print(f"[크롤링] 에러 발생: {e}")
            time.sleep(60)


# 분석 프로세스 함수
def run_processor_loop():
    # 시작 전 DB에서 최신 카테고리/학과 목록 한 번 동기화
    load_metadata() 
    
    print("[분석] 분석 프로세스 시작...")
    while True:
        try:
            process_raw_to_refined()
        except Exception as e:
            print(f"[분석] 에러 발생: {e}")
            time.sleep(60)


# 디스코드 봇 프로세스 함수
def run_bot_process():
    token = os.getenv('DISCORD_TOKEN')
    channel_id = os.getenv('DISCORD_CHANNEL_ID')

    if not token or not channel_id:
        print("[디스코드 봇] 에러: .env 파일에 디스코드 설정이 없습니다.")
        return

    print("[디스코드 봇] 디스코드 봇 프로세스 시작...")
    try:
        run_discord_bot(token, channel_id)
    except Exception as e:
        print(f"[디스코드 봇] 종료됨: {e}")


if __name__ == "__main__":
    print("========================================")
    print("광운대 통합 알림 시스템 시작")
    print("========================================")

    # 프로세스 생성
    p_crawler = Process(target=run_crawling_loop, name="Crawler")
    p_processor = Process(target=run_processor_loop, name="Processor")
    p_bot = Process(target=run_bot_process, name="DiscordBot")

    # 모든 프로세스 시작
    p_crawler.start()
    p_processor.start()
    p_bot.start()

    # 프로세스 종료 대기
    try:
        p_crawler.join()
        p_processor.join()
        p_bot.join()
    except KeyboardInterrupt:
        p_crawler.terminate()
        p_processor.terminate()
        p_bot.terminate()