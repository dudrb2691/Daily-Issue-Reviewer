import streamlit as st
import google.generativeai as genai
import feedparser
from youtubesearchpython import VideosSearch
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

# 챗봇 페르소나 (LG Energy Solution Vertech 동료)
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
if "selected_article" not in st.session_state:
    st.session_state.selected_article = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = model.start_chat(history=[])
if "show_chat" not in st.session_state:
    st.session_state.show_chat = False

# ==========================================
# 3. 보조 함수 (뉴스 수집 및 유튜브 검색)
# ==========================================
@st.cache_data(ttl=3600)
def get_news():
    # 더 안정적인 RSS 피드 주소로 교체했습니다.
    feeds = {
        "🌎 미국 주요 뉴스": ["http://rss.cnn.com/rss/cnn_topstories.rss"],
        "🏅 미국 주요 스포츠": ["https://www.espn.com/espn/rss/news"],
        "📰 보스턴 지역 뉴스": ["https://www.wcvb.com/topstories-rss"],
        "🏆 보스턴 스포츠": [
            "https://www.espn.com/espn/rss/nba/news",
            "https://www.espn.com/espn/rss/mlb/news"
        ]
    }
    
    results = {}
    for category, urls in feeds.items():
        combined_entries = []
        for url in urls:
            parsed = feedparser.parse(url)
            combined_entries.extend(parsed.entries[:5])
        results[category] = combined_entries[:8]
    return results

def get_youtube_link(query):
    # 제목으로 유튜브를 검색해 첫 번째 실제 영상 링크를 반환합니다.
    try:
        videosSearch = VideosSearch(query, limit=1)
        res = videosSearch.result()
        if res and res.get('result'):
            return res['result'][0]['link']
    except Exception:
        return None
    return None

# ==========================================
# 4. 상단 UI: 뉴스 목록
# ==========================================
st.title("🇺🇸 보스턴 출근길 스몰톡 도우미")
st.markdown("오늘의 지역 가십거리를 파악하고 동료들과 자연스럽게 대화해 보세요!")

news_data = get_news()
tabs = st.tabs(list(news_data.keys()))

for idx, (category, entries) in enumerate(news_data.items()):
    with tabs[idx]:
        for entry in entries:
            title = entry.get('title', '제목 없음')
            link = entry.get('link', '#')
            summary_raw = entry.get('summary', '')
            
            # 목록에서는 깔끔하게 제목과 버튼만 보여줍니다.
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"**{title}**")
            with col2:
                btn_key = f"btn_{idx}_{title[:15]}_{len(title)}"
                if st.button("분석", key=btn_key):
                    # 분석 버튼 클릭 시, 해당 기사 정보를 세션에 저장하고 AI 분석을 시작합니다.
                    with st.spinner("기사 분석 및 유튜브 영상을 찾는 중입니다..."):
                        yt_link = get_youtube_link(title)
                        
                        prompt = f"""
                        당신은 보스턴에 파견된 한국인 주재원의 스몰톡을 돕는 AI입니다.
                        다음 뉴스 기사 제목과 내용을 바탕으로 지정된 양식에 맞춰 작성해 줘.
                        
                        기사 제목: {title}
                        기사 내용: {summary_raw}
                        
                        [작성 양식]
                        ### 📝 영문 요약본
                        (기사 내용을 유추하여 2~3문장 영어 요약)
                        
                        ### 🇰🇷 국문 요약본
                        (위 영문 요약의 한국어 번역)
                        
                        ### 🗣️ 스몰톡 서두 추천 문구
                        (동료에게 말을 걸 때 쓸 수 있는 자연스러운 영어 아이스브레이커 2개와 뜻)
                        
                        ### 💬 스몰톡 추천 표현
                        (대화를 이어갈 때 쓸만한 유용한 영어 문장 3개와 뜻)
                        """
                        
                        response = model.generate_content(prompt)
                        
                        # 분석 결과와 링크 정보를 세션에 통합 저장
                        st.session_state.selected_article = {
                            "title": title,
                            "link": link,
                            "yt_link": yt_link,
                            "ai_analysis": response.text
                        }
                        
                        # 채팅 초기화 및 숨김
                        st.session_state.messages = []
                        st.session_state.chat_session = model.start_chat(history=[
                            {"role": "user", "parts": [f"Let's talk about this news topic: {title}"]},
                            {"role": "model", "parts": [f"Sure! I saw that headline about '{title}' too. What do you think about it?"]}
                        ])
                        st.session_state.show_chat = False
                    st.rerun()

st.divider()

# ==========================================
# 5. 하단 UI: 분석 결과 및 챗봇 영역
# ==========================================
if st.session_state.selected_article:
    article = st.session_state.selected_article
    
    # 요청하신 순서대로 레이아웃 배치
    st.subheader(f"📌 {article['title']}")
    
    # 1~4. AI 분석 내용 (영문 요약 -> 국문 요약 -> 서두 문구 -> 추천 표현)
    st.markdown(article['ai_analysis'])
    
    # 5~6. 원문 및 유튜브 링크
    st.markdown("### 🔗 관련 링크")
    st.markdown(f"👉 [원문 기사 바로가기]({article['link']})")
    if article['yt_link']:
        st.markdown(f"📺 [유튜브 관련 영상 보기]({article['yt_link']})")
    
    st.write("") # 간격 띄우기
    
    # 7. 챗봇 활성화 버튼
    if not st.session_state.show_chat:
        if st.button("💬 Gemini와 이 주제로 영어 토론하기", use_container_width=True):
            st.session_state.show_chat = True
            st.rerun()

    # 챗봇 UI (버튼을 눌렀을 때만 표시됨)
    if st.session_state.show_chat:
        st.divider()
        st.subheader("🗣️ 영어 토론")
        
        # 이전 채팅 내역 표시
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        # 음성 입력 (마이크)
        st.markdown("🎙️ **음성으로 말하기**")
        spoken_text = speech_to_text(language='en-US', use_container_width=True, just_once=True, key='STT')

        # 텍스트 입력
        typed_text = st.chat_input("Type your message here...")

        user_input = spoken_text if spoken_text else typed_text

        if user_input:
            st.session_state.messages.append({"role": "user", "content": user_input})
            with st.chat_message("user"):
                st.markdown(user_input)
                
            with st.chat_message("assistant"):
                with st.spinner("동료가 대답을 생각하고 있습니다..."):
                    response = st.session_state.chat_session.send_message(user_input)
                    st.markdown(response.text)
                    
            st.session_state.messages.append({"role": "assistant", "content": response.text})
            st.rerun()

else:
    st.info("👆 위 목록에서 '분석' 버튼을 누르면 요약본과 스몰톡 추천 문구가 표시됩니다.")