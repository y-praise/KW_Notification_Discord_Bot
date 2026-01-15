import discord
from discord.ext import tasks, commands
from discord.ui import Select, View
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import asyncio
import os
from dotenv import load_dotenv

# --- [1. Firebase 접속 설정] ---
load_dotenv()
firebase_path = os.getenv("FIREBASE_KEY_PATH")
cred = credentials.Certificate(firebase_path)
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- [2. 색상 및 DB 로드 함수] ---
def get_color(category):
    if '학사' in category or '행정' in category: 
        return 0x3498DB 
    elif '장학' in category or '복지' in category: 
        return 0xFFD700 
    elif '취업' in category or '대외' in category: 
        return 0x2ECC71
    elif '글로벌' in category: 
        return 0x9B59B6 
    elif '행사' in category or '시설' in category: 
        return 0xE67E22
    else: 
        return 0x95A5A6

def get_metadata_from_db():
    try:
        doc = db.collection('metadata').document('categories').get()
        if doc.exists:
            data = doc.to_dict()
            return {
                'departments': data.get('departments', []), 
                'notice_types': data.get('notice_types', []),
                'colleges': data.get('colleges', [])  
            }
        return {'departments': [], 'notice_types': [], 'colleges': []}
    except Exception as e:
        print(f"❌ Metadata 읽기 실패: {e}")
        return {'departments': [], 'notice_types': [], 'colleges': []}

# --- [3. UI 관련 함수 및 클래스] ---
async def update_subscription(interaction, selected_values, all_possible_values_in_menu):
    user_id = str(interaction.user.id)
    user_name = interaction.user.name
    doc_ref = db.collection('subscriptions').document(user_id)
    
    doc = doc_ref.get()
    current_keywords = []
    if doc.exists:
        current_keywords = doc.to_dict().get('keywords', [])

    filtered_keywords = [k for k in current_keywords if k not in all_possible_values_in_menu]
    updated_keywords = list(set(filtered_keywords + selected_values))
    
    doc_ref.set({'user_name': user_name, 'keywords': updated_keywords}, merge=True)
    
    if len(selected_values) > 0:
        msg = f"✅ **반영 완료!**\n현재 선택: {', '.join(selected_values)}\n\n(📃 총 구독 리스트: {', '.join(updated_keywords)})"
    else:
        msg = f"🗑️ **선택 해제 완료!**\n이 메뉴의 모든 구독이 취소되었습니다.\n\n(📃 총 구독 리스트: {', '.join(updated_keywords)})"

    await interaction.response.send_message(msg, ephemeral=True)


class DynamicSelect(Select):
    def __init__(self, placeholder, options_data, custom_id_suffix, user_subs):
        self.all_managed_keywords = options_data 
        
        discord_options = []
        for item in options_data:
            label = item
            
            notice_emoji_map = {
                "장학": "💰", "복지": "🎁",     
                "취업": "👔", "대외": "✨",      
                "행사": "🎉", "시설": "🏢",    
                "학사": "🎓", "행정": "📜",      
                "글로벌": "🌏", "광운": "🏫",                  
                "기타": "📂"                     
            }
            college_emoji_map = {
                "전자정보": "⚡", "인공지능": "🤖", "공과": "🏗️", 
                "자연과학": "🧪", "인문사회": "📚", "정책법학": "⚖️", 
                "경영": "💼", "인제니움": "💡"
            }
            dept_emoji_map = {
                "소프트": "💻", "정보융합": "🌐", "컴퓨터": "🖥️", "로봇": "🤖",
                "전자공학": "⚡", "전자통신": "📡", "전자융합": "🎛️", 
                "전기": "💡", "전자재료": "💎", "반도체": "💾",
                "건축공학": "🏗️", "건축": "🏛️", "화학공학": "⚗️", "환경": "🌿",
                "수학": "📐", "바이오": "🧬", "화학": "🧪", "스포츠": "⚽",
                "국어": "📜", "영어": "🅰️", "미디어": "🎥", "심리": "🧠",
                "동북아": "🌏", "행정": "📋", "법학": "⚖️",
                "국제학": "✈️", "경영": "💼", "통상": "🚢", "자율": "🧩",
                "전체": "📢"
            }

            emoji = "🏫" 
            found = False
            for key, icon in notice_emoji_map.items():
                if key in label:
                    emoji = icon
                    found = True
                    break
            if not found:
                for key, icon in college_emoji_map.items():
                    if key in label:
                        emoji = icon
                        found = True
                        break
            if not found:
                for key, icon in dept_emoji_map.items():
                    if key in label:
                        emoji = icon
                        break

            is_default = (item in user_subs)
            discord_options.append(
                discord.SelectOption(label=label, emoji=emoji, default=is_default)
            )

        super().__init__(
            placeholder=placeholder,
            min_values=0, 
            max_values=len(discord_options), 
            options=discord_options, 
            custom_id=f"dynamic_{custom_id_suffix}"
        )

    async def callback(self, interaction: discord.Interaction):
        await update_subscription(interaction, self.values, self.all_managed_keywords)


class SubscribeView(View):
    def __init__(self, user_subs):
        super().__init__()
        data = get_metadata_from_db()
        dept_list = data['departments']
        notice_list = data['notice_types']
        college_list = data['colleges']

        if notice_list:
            self.add_item(DynamicSelect("🔔 주제별 공지 선택 (선택 해제 시 취소됨)", notice_list, "types", user_subs))
        if college_list:
            self.add_item(DynamicSelect("🏫 단과대학(학부) 선택", college_list, "colleges", user_subs))

        eng_sw_group = []        
        humanity_biz_group = []  
        nature_sports_group = [] 

        for d in dept_list:
            if d == "전체": continue 
            if any(key in d for key in ["소프트", "정보", "컴퓨터", "로봇", "전자", "전기", "반도체", "건축", "화학공학", "환경"]):
                eng_sw_group.append(d)
            elif any(key in d for key in ["국어", "영어", "미디어", "심리", "동북아", "행정", "법학", "국제", "경영", "통상", "자율"]):
                humanity_biz_group.append(d)
            else:
                nature_sports_group.append(d)

        if eng_sw_group:
            self.add_item(DynamicSelect("💻 공학 & SW & 건축 계열", eng_sw_group, "eng_sw", user_subs))
        if humanity_biz_group:
            self.add_item(DynamicSelect("📚 인문 & 사회 & 경영 계열", humanity_biz_group, "humanity", user_subs))
        if nature_sports_group:
            self.add_item(DynamicSelect("🧬 자연과학 & 체육 & 기타", nature_sports_group, "nature", user_subs))

# [새로 추가] 설정창을 여는 버튼 (공용으로 떠 있는 것)
class SubscriptionLauncher(View):
    def __init__(self):
        super().__init__(timeout=None) # 버튼이 영원히 작동하도록 설정

    @discord.ui.button(label="🔔 구독 설정 열기 (클릭)", style=discord.ButtonStyle.primary, custom_id="open_settings_btn")
    async def open_settings(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = str(interaction.user.id)
        
        # 1. DB에서 내 정보 가져오기
        doc = db.collection('subscriptions').document(user_id).get()
        current_subs = []
        if doc.exists:
            current_subs = doc.to_dict().get('keywords', [])
        
        # 2. 내 정보가 체크된 메뉴판 만들기
        # (여기서 만드는 뷰는 ephemeral이므로 timeout이 있어도 상관없음)
        view = SubscribeView(user_subs=current_subs)
        
        # 3. 나만 보이는 메시지로 전송 (ephemeral=True)
        await interaction.response.send_message(
            content="👇 **아래 메뉴에서 구독 정보를 수정하세요!** (변경 시 즉시 자동 저장됩니다)", 
            view=view, 
            ephemeral=True # <--- 핵심! 나한테만 보임
        )




#  [봇 실행 함수] 
def run_discord_bot(token_key, channel_id_key):
    CHANNEL_ID = int(channel_id_key)
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True 
    
    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.command()
    async def 설치(ctx):
        embed = discord.Embed(title="📢 공지 알림 구독 센터", description="버튼을 눌러 나만의 알림 설정을 시작하세요!", color=0x00CED1)
        embed.add_field(name="❓ 어떻게 쓰나요?", value="아래 **'구독 설정 열기'** 버튼을 누르면,\n나만 볼 수 있는 설정 메뉴가 나타납니다.", inline=False)
        embed.add_field(name="💾 내 정보 불러오기", value="버튼을 누르면 **내가 기존에 구독했던 항목이 체크된 상태**로 뜹니다.", inline=False)
        embed.set_footer(text="Team 그것이 알고싶다", icon_url="https://i.imgur.com/RJ8Zgm0.png")
        
        # 메뉴판(SubscribeView) 대신 버튼(SubscriptionLauncher)을 보냄
        await ctx.send(embed=embed, view=SubscriptionLauncher())

    # 루프 함수: Firestore에서 새 공지 확인
    @tasks.loop(seconds=30) 
    async def check_firestore():
        await bot.wait_until_ready()

        meta_data = get_metadata_from_db()
        dept_list = meta_data['departments']

        try:
            public_channel = await bot.fetch_channel(CHANNEL_ID)
        except: return

        docs = db.collection('refined_notices').where(field_path='is_sent', op_string='==', value=False).stream()
        
        for doc in docs:
            data = doc.to_dict()
            title = data.get('title', '제목 없음')
            link = data.get('link', '')
            deadline = data.get('deadline', '기한 없음')
            source = data.get('source', '') 
            processed_at = str(data.get('processed_at', '')).split('.')[0]
            raw_category = data.get('category', '공지')
            category = raw_category[0] if isinstance(raw_category, list) and raw_category else raw_category
            
            summary = ""
            raw_summary = data.get('summary', [])
            if isinstance(raw_summary, list):
                for item in raw_summary: summary += f"• {item}\n" 
            else: summary = raw_summary

            notice_dept = None
            for dept_name in dept_list:
                if dept_name in source:
                    notice_dept = dept_name
                    break
            
            try:
                embed = discord.Embed(title=title, description="", color=get_color(category))
                embed.set_author(name=f"📢 {category} 공지")
                if deadline: embed.add_field(name="📅 마감일", value=deadline, inline=True)
                if source: embed.add_field(name="🏢 출처", value=source, inline=True)
                if processed_at: embed.add_field(name="🕒 수집일", value=processed_at, inline=False)
                embed.add_field(name="🔗 바로가기", value=f"[공지사항 원문 이동]({link})", inline=False)
                if summary: embed.add_field(name="📝 요약 내용", value=summary, inline=False)
                embed.set_footer(text="Team 그것이 알고싶다", icon_url="https://i.imgur.com/RJ8Zgm0.png")
                
                await public_channel.send(embed=embed)
            except: pass

            subscribers = db.collection('subscriptions').where('keywords', 'array_contains', category).stream()
            
            for sub in subscribers:
                sub_data = sub.to_dict()
                user_id = sub.id 
                user_keywords = sub_data.get('keywords', [])

                should_send = False
                matched_reason = ""

                if notice_dept:
                    # 학과 공지인 경우: 
                    # 이미 위에서 '카테고리' 구독자는 걸러서 가져왔으니, '학과'도 구독했는지 확인만 하면 됨
                    if notice_dept in user_keywords:
                        should_send = True
                        matched_reason = f"{notice_dept} + {category}"
                else:
                    # 일반 공지인 경우:
                    # 위에서 이미 '카테고리' 구독자만 가져왔으므로 무조건 보냄
                    should_send = True
                    matched_reason = f"{category}"

                if should_send:
                    try:
                        user = await bot.fetch_user(int(user_id))
                        dm_embed = embed.copy()
                        dm_embed.set_author(name=f"🔔 맞춤 알림 ({matched_reason})")
                        await user.send(embed=dm_embed)
                        # 메시지 하나 보낼 때마다 0.1초씩 버퍼걸기
                        await asyncio.sleep(0.1)
                    except: pass

            doc.reference.update({'is_sent': True})

    @bot.event
    async def on_ready():
        print(f'🔥 {bot.user} 봇이 준비되었습니다!')
        
        bot.add_view(SubscriptionLauncher())
        
        check_firestore.start()
    # 봇 실행
    bot.run(token_key)