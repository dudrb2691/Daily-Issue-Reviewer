# ==========================================
# 필요 라이브러리 (requirements.txt)
# ==========================================
# streamlit
# google-generativeai
# feedparser
# streamlit-mic-recorder
# ==========================================

import streamlit as st
import google.generativeai as genai
import feedparser
import urllib.parse
from streamlit_mic_recorder import speech_to_text

# ==========================================
# 1. 초기 설정 및 API 키 불러오기
# ==========================================
st.set_page_config(page_title="보스턴 스몰톡 준비", page_icon="🇺🇸", layout="centered")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("오류: Streamlit Secrets에 'GEMINI_API_KEY'가 설정되지 않았습니다.")
    st.stop()

# 챗봇의 기본 성격을 지정합니다.
persona = """
You are a friendly American colleague working at LG Energy Solution Vertech in Westborough, MA. 
The user is a Korean expat engineer with about 4 years of experience who recently joined your team. 
Your job is to make small talk based on the daily news or sports topics the user brings up.
Always reply in English. Keep your sentences natural, conversational, and easy to understand.
If the user makes a grammatical error or uses an awkward expression in English, politely provide a correction at the end of your response like this: 
"*Tip: Instead of [User's phrase], you can say [Natural phrase].*"
"""

model = genai.GenerativeModel(
    'gemini-1.5-flash',
    system_instruction=persona
)

# ==========================================
# 2. 세션 상태 (Session State) 초기화
# ==========================================
# 앱을 새로고침해도 대화 내용과 선택한 주제가 날아가지 않도록 저장하는 공간입니다.
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_topic" not in st.session_state:
    st.session_state.current_topic = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])
if "smalltalk_result" not in st.session_state:
    st.session_state.smalltalk_result = None

# ==========================================
# 3. 뉴스 데이터 수집 함수 (RSS)
# ==========================================
@st.cache_data(ttl=3600) # 1시간 동안 데이터를 캐싱하여 속도를 높입니다.
def get_news():
    feeds = {
        "🌎 미국 주요 뉴스 (AP)": "https://rss.app/feeds/v1.1/tDkrWPiLqMBECgR3.xml",
        "📰 보스턴 지역 뉴스 (CBS Boston)": "https://www.cbsnews.com/latest/rss/boston",
        "🏀 보스턴 셀틱스 (ESPN NBA)": "https://www.espn.com/espn/rss/nba/news",
        "⚾ 보스턴 레드삭스 (ESPN MLB)": "https://www.espn.com/espn/rss/mlb/news"
    }
    
    results = {}
    for category, url in feeds.items():
        parsed = feedparser.parse(url)
        # 각 피드에서 최신 기사 5개만 가져옵니다.
        results[category] = parsed.entries[:5]
    return results

# ==========================================
# 4. 메인 화면 UI 구성
# ==========================================
st.title("🇺🇸 보스턴 출근길 스몰톡 도우미")
st.markdown("오늘의 지역 가십거리를 파악하고 동료들과 자연스럽게 대화해 보세요!")

news_data = get_news()

# 뉴스 목록을 탭으로 나누어 깔끔하게 보여줍니다.
tabs = st.tabs(list(news_data.keys()))

for idx, (category, entries) in enumerate(news_data.items()):
    with tabs[idx]:
        for entry in entries:
            title = entry.get('title', '제목 없음')
            summary = entry.get('summary', '')
            published = entry.get('published', '')
            link = entry.get('link', '#')
            # 유튜브 검색 링크 생성
            yt_query = urllib.parse.quote(f"{title}")
            yt_link = f"https://www.youtube.com/results?search_query={yt_query}"
            
            with st.expander(f"**{title}**"):
                # 기사 요약 또는 발행일 표시
                if summary:
                    st.caption(summary[:200])
                if published:
                    st.caption(f"🕐 {published}")
                
                st.markdown(f"[🔗 원문 기사 보기]({link}) &nbsp; | &nbsp; [▶️ 유튜브 검색하기]({yt_link})")
                
                # 스몰톡 준비 버튼
                if st.button("💬 이 주제로 스몰톡 준비", key=f"btn_{idx}_{title[:30]}", use_container_width=True):
                    st.session_state.current_topic = title
                    
                    with st.spinner("Gemini가 핵심 요약과 아이스브레이킹 표현을 준비 중입니다..."):
                        prompt = f"""
                        다음 뉴스 기사 제목을 바탕으로 두 가지를 작성해 줘.
                        기사 제목: {title}
                        
                        1. 이 뉴스의 배경이나 핵심 내용 2~3줄 요약 (한국어)
                        2. 이 주제로 미국 동료에게 출근해서 자연스럽게 말을 걸 수 있는 영어 서두(Icebreaker) 표현 3가지와 한국어 뜻
                        """
                        response = model.generate_content(prompt)
                        st.session_state.smalltalk_result = response.text
                        
                    # 새로운 주제를 선택하면 채팅 내역을 초기화하고, 토픽 컨텍스트를 채팅에 주입합니다.
                    st.session_state.messages = []
                    st.session_state.chat_session = model.start_chat(history=[
                        {"role": "user", "parts": [f"Let's talk about this news topic: {title}"]},
                        {"role": "model", "parts": [f"Sure! I saw that headline about '{title}' too. What do you think about it?"]}
                    ])
                    st.rerun()

st.divider()

# ==========================================
# 5. 실시간 영어 토론 챗봇 (마이크 & 텍스트)
# ==========================================
if st.session_state.current_topic:
    st.subheader(f"🗣️ 토론 중인 주제: {st.session_state.current_topic}")
    
    # 저장된 스몰톡 준비 결과를 항상 표시합니다.
    if st.session_state.smalltalk_result:
        st.info(st.session_state.smalltalk_result)
    
    # 이전 채팅 내역을 화면에 표시합니다.
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 마이크 음성 입력 (채팅 입력 위에 배치)
    st.markdown("🎙️ **음성으로 말하기** (마이크 버튼을 눌러 영어로 말해보세요)")
    spoken_text = speech_to_text(language='en-US', use_container_width=True, just_once=True, key='STT')

    # 키보드 텍스트 입력 (페이지 하단 고정)
    typed_text = st.chat_input("Type your message here...")

    # 음성이나 텍스트 중 하나라도 입력이 들어오면 실행됩니다.
    user_input = spoken_text if spoken_text else typed_text

    if user_input:
        # 1. 사용자 메시지 저장
        st.session_state.messages.append({"role": "user", "content": user_input})
            
        # 2. Gemini 모델에 메시지 전송 및 답변 받기
        with st.spinner("동료가 대답을 생각하고 있습니다..."):
            response = st.session_state.chat_session.send_message(user_input)
                
        # 3. AI 답변 저장
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        
        # 화면 새로고침으로 채팅 내역 표시
        st.rerun()

else:
    st.info("👆 위에서 뉴스를 선택하고 '스몰톡 준비' 버튼을 누르면 영어 대화를 시작할 수 있습니다.")