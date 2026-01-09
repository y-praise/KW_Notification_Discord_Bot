import os
from dotenv import load_dotenv
from discord_bot import run_discord_bot

# .env 파일 로드
load_dotenv()

def main():
    token = os.getenv('DISCORD_TOKEN')
    channel_id = os.getenv('DISCORD_CHANNEL_ID')

    if not token or not channel_id:
        print("❌ 에러: .env 파일에 토큰 설정이 없습니다.")
        return

    print("🚀 프로그램을 시작합니다...")
    run_discord_bot(token, channel_id)

if __name__ == "__main__":
    main()