import discord
from discord.ext import tasks, commands
from discord.ui import Select, View
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore
import asyncio

# --- [1. Firebase 접속 설정] ---
cred = credentials.Certificate("firebase_key.json") 
if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)
db = firestore.client()

# --- [2. 색상 및 DB 로드 함수] ---
def get_color(category):
    if '장학' in category or '등록' in category: return 0xFFD700 
    elif '학사' in category or '입학' in category: return 0x1E90FF 
    elif '취업' in category or '외부' in category: return 0x00FF00
    elif '행사' in category or '봉사' in category: return 0xFFA500
    else: return 0x95A5A6 

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
                "장학": "💰", "등록": "🧾", "취업": "👔", "병무": "🪖",
                "행사": "🎉", "봉사": "🤝", "학사": "🎓", "입학": "💌",
                "학생": "🙋", "시설": "🛠️", "국제교류": "✈️", "국제학생": "🌏",
                "외부": "🏢", "일반": "📌", "기타": "📂"
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

#  [봇 실행 함수] 
def run_discord_bot(token_key, channel_id_key):
    CHANNEL_ID = int(channel_id_key)
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True 
    
    bot = commands.Bot(command_prefix='!', intents=intents)

    @bot.command()
    async def 구독설정(ctx):
        user_id = str(ctx.author.id)
        doc = db.collection('subscriptions').document(user_id).get()
        current_subs = []
        if doc.exists:
            current_subs = doc.to_dict().get('keywords', [])
        await ctx.send(
            "👇 **메뉴를 클릭해 구독을 설정하세요!** (이미 구독 중인 항목은 체크되어 있습니다)", 
            view=SubscribeView(user_subs=current_subs)
        )

    @bot.command()
    async def 내구독(ctx):
        user_id = str(ctx.author.id)
        doc = db.collection('subscriptions').document(user_id).get()
        if doc.exists:
            keywords = doc.to_dict().get('keywords', [])
            if keywords:
                await ctx.send(f"📋 **{ctx.author.name}**님의 구독 리스트:\n{', '.join(keywords)}")
            else:
                await ctx.send("구독 중인 키워드가 없습니다.")
        else:
            await ctx.send("아직 구독 설정이 없습니다.")

    @bot.command()
    async def 구독초기화(ctx):
        user_id = str(ctx.author.id)
        db.collection('subscriptions').document(user_id).delete()
        await ctx.send("🗑️ 모든 구독 설정을 초기화했습니다.")

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
                    except: pass

            doc.reference.update({'is_sent': True})

    @bot.event
    async def on_ready():
        print(f'🔥 {bot.user} 봇이 준비되었습니다!')
        check_firestore.start()

    # 봇 실행
    bot.run(token_key)