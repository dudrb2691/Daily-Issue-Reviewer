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
if "messages" not in st.session_state:
    st.session_state.messages = []
if "current_topic" not in st.session_state:
    st.session_state.current_topic = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])
if "smalltalk_result" not in st.session_state:
    st.session_state.smalltalk_result = None

# ==========================================
# 3. 뉴스 데이터 수집 함수 (RSS) - 구조 개선
# ==========================================
@st.cache_data(ttl=3600)
def get_news():
    # 여러 개의 피드를 하나의 탭으로 묶을 수 있도록 리스트([]) 형태로 변경했습니다.
    feeds = {
        "🌎 미국 주요 뉴스": ["https://rss.app/feeds/v1.1/tDkrWPiLqMBECgR3.xml"],
        "🏅 미국 주요 스포츠": ["https://www.espn.com/espn/rss/news"], # 새롭게 추가된 ESPN 전체 스포츠 종합
        "📰 보스턴 지역 뉴스": ["https://www.cbsnews.com/latest/rss/boston"],
        "🏆 보스턴 스포츠": [
            "https://www.espn.com/espn/rss/nba/news", # 셀틱스 관련
            "https://www.espn.com/espn/rss/mlb/news"  # 레드삭스 관련
        ]
    }
    
    results = {}
    for category, urls in feeds.items():
        combined_entries = []
        for url in urls:
            parsed = feedparser.parse(url)
            # 각 링크별로 5개씩 가져와서 하나의 리스트에 합칩니다.
            combined_entries.extend(parsed.entries[:5])
            
        # 탭당 너무 많은 기사가 나오지 않도록 최대 10개로 제한합니다.
        results[category] = combined_entries[:10]
        
    return results

# ==========================================
# 4. 메인 화면 UI 구성
# ==========================================
st.title("🇺🇸 보스턴 출근길 스몰톡 도우미")
st.markdown("오늘의 지역 가십거리를 파악하고 동료들과 자연스럽게 대화해 보세요!")

news_data = get_news()

tabs = st.tabs(list(news_data.keys()))

for idx, (category, entries) in enumerate(news_data.items()):
    with tabs[idx]:
        for entry in entries:
            title = entry.get('title', '제목 없음')
            summary = entry.get('summary', '')
            published = entry.get('published', '')
            link = entry.get('link', '#')
            yt_query = urllib.parse.quote(f"{title}")
            yt_link = f"https://www.youtube.com/results?search_query={yt_query}"
            
            with st.expander(f"**{title}**"):
                if summary:
                    st.caption(summary[:200])
                if published:
                    st.caption(f"🕐 {published}")
                
                st.markdown(f"[🔗 원문 기사 보기]({link}) &nbsp; | &nbsp; [▶️ 유튜브 검색하기]({yt_link})")
                
                # 버튼 key에 특수문자나 겹치는 이름이 들어가지 않도록 약간의 해시(길이 등)를 추가
                btn_key = f"btn_{idx}_{title[:20]}_{len(title)}"
                
                if st.button("💬 이 주제로 스몰톡 준비", key=btn_key, use_container_width=True):
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
    
    if st.session_state.smalltalk_result:
        st.info(st.session_state.smalltalk_result)
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    st.markdown("🎙️ **음성으로 말하기** (마이크 버튼을 눌러 영어로 말해보세요)")
    spoken_text = speech_to_text(language='en-US', use_container_width=True, just_once=True, key='STT')

    typed_text = st.chat_input("Type your message here...")

    user_input = spoken_text if spoken_text else typed_text

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
            
        with st.spinner("동료가 대답을 생각하고 있습니다..."):
            response = st.session_state.chat_session.send_message(user_input)
                
        st.session_state.messages.append({"role": "assistant", "content": response.text})
        st.rerun()

else:
    st.info("👆 위에서 뉴스를 선택하고 '스몰톡 준비' 버튼을 누르면 영어 대화를 시작할 수 있습니다.")