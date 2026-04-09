import streamlit as st
import google.generativeai as genai
import feedparser
from youtubesearchpython import VideosSearch
from streamlit_mic_recorder import speech_to_text
import urllib.request
import json
import re  # 👈 숨겨진 이미지를 찾기 위한 라이브러리 추가

# ==========================================
# 1. 초기 설정 및 API 키 불러오기
# ==========================================
st.set_page_config(page_title="보스턴 스몰톡 준비", page_icon="🇺🇸", layout="wide")

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
except KeyError:
    st.error("오류: Streamlit Secrets에 'GEMINI_API_KEY'가 설정되지 않았습니다.")
    st.stop()

# ==========================================
# 2. AI 모델 분리 (요약용 vs 채팅용)
# ==========================================
analyzer_model = genai.GenerativeModel('gemini-3-flash-preview')

persona = """
You are a friendly American colleague working at LG Energy Solution Vertech in Westborough, MA. 
The user is a Korean expat engineer with about 4 years of experience who recently joined your team. 
Your job is to make small talk based on the daily news, sports, or weather topics the user brings up.
Always reply in English. Keep your sentences natural, conversational, and easy to understand.
If the user makes a grammatical error or uses an awkward expression in English, politely provide a correction at the end of your response like this: 
"*Tip: Instead of [User's phrase], you can say [Natural phrase].*"
"""
chat_model = genai.GenerativeModel('gemini-3-flash-preview', system_instruction=persona)

# ==========================================
# 3. 세션 상태 (Session State) 초기화
# ==========================================
if "messages" not in st.session_state:
    st.session_state.messages = []
if "selected_article" not in st.session_state:
    st.session_state.selected_article = None
if "chat_session" not in st.session_state:
    st.session_state.chat_session = chat_model.start_chat(history=[]) 
if "show_chat" not in st.session_state:
    st.session_state.show_chat = False

# ==========================================
# 4. 보조 함수 (뉴스 수집, 분류, 이미지 추출)
# ==========================================
@st.cache_data(ttl=3600)
def get_news():
    feeds = {
        "🌎 미국 주요 뉴스": ["http://rss.cnn.com/rss/cnn_topstories.rss"],
        "🏅 미국 주요 스포츠": ["https://www.espn.com/espn/rss/news"],
        "📰 보스턴 지역 뉴스": ["https://www.wcvb.com/topstories-rss"],
        "🏆 보스턴 스포츠": [
            "https://www.espn.com/espn/rss/nba/news",
            "https://www.espn.com/espn/rss/mlb/news",
            "https://www.espn.com/espn/rss/nfl/news"
        ],
        "🍿 엔터/가십거리": ["http://rss.cnn.com/rss/cnn_showbiz.rss"]
    }
    
    results = {}
    for category, urls in feeds.items():
        combined_entries = []
        for url in urls:
            parsed = feedparser.parse(url)
            combined_entries.extend(parsed.entries[:10]) 
        results[category] = combined_entries[:9]
    return results

def get_category_prefix(title, summary, category_name, article_link=""):
    if "스포츠" in category_name:
        link_lower = article_link.lower()
        text_lower = (title + " " + summary).lower()
        
        if 'nba' in link_lower or 'basketball' in text_lower: return "🏀 [NBA]"
        if 'mlb' in link_lower or 'baseball' in text_lower: return "⚾ [MLB]"
        if 'nfl' in link_lower or 'football' in text_lower: return "🏈 [NFL]"
        if 'nhl' in link_lower or 'hockey' in text_lower: return "🏒 [NHL]"
        if 'golf' in link_lower or 'masters' in text_lower or 'pga' in text_lower: return "⛳ [골프]"
        if 'soccer' in link_lower or 'fc' in text_lower or 'premier league' in text_lower: return "⚽ [축구]"
        return "🏅 [스포츠 종합]"
    
    text = (title + " " + summary).lower()
    if any(word in text for word in ['market', 'economy', 'stock', 'fed', 'inflation', 'bank', 'business', 'price', 'rates', 'ceo', 'revenue', 'invest']):
        return "📈 [경제]"
    elif any(word in text for word in ['tech', 'apple', 'google', 'alphabet', 'microsoft', 'ai', 'software', 'space', 'nasa', 'science', 'nvidia', 'tsmc', 'chip']):
        return "💻 [IT/과학]"
    elif any(word in text for word in ['president', 'election', 'senate', 'house', 'court', 'law', 'biden', 'trump', 'government', 'policy', 'vote', 'congress']):
        return "🏛️ [정치]"
    elif any(word in text for word in ['movie', 'music', 'star', 'hollywood', 'celebrity', 'actor', 'award', 'netflix', 'singer', 'album', 'tour']):
        return "🍿 [엔터]"
    elif any(word in text for word in ['police', 'crime', 'crash', 'shoot', 'killed', 'investigation', 'fire', 'emergency']):
        return "🚨 [사건사고]"
    else:
        return "📰 [일반]"

def get_image_url(entry):
    """더 다양한 태그를 스캔하고 파라미터를 제거하여 액박을 방지합니다."""
    fallback_img = "https://images.unsplash.com/photo-1495020689067-958852a7765e?auto=format&fit=crop&w=400&q=80"
    
    img_candidates = []

    # 1. media_content 태그 확인
    if 'media_content' in entry:
        for content in entry.media_content:
            if 'url' in content:
                img_candidates.append(content['url'])
                
    # 2. media_thumbnail 태그 확인
    if 'media_thumbnail' in entry:
        for thumb in entry.media_thumbnail:
            if 'url' in thumb:
                img_candidates.append(thumb['url'])

    # 3. links 항목에서 이미지 타입 확인 (엔터 탭 해결책)
    if 'links' in entry:
        for link in entry.links:
            if 'image' in link.get('type', ''):
                img_candidates.append(link.get('href', ''))

    # 후보군 검사
    for url in img_candidates:
        if not url: continue
        
        # 주소 뒤의 쿼리 파라미터(?...) 제거하여 순수 확장자 추출
        clean_url = url.split('?')[0].lower()
        
        if any(ext in clean_url for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
            # 상대 경로 방지: http로 시작하는지 확인
            if url.startswith('http'):
                return url
                
    return fallback_img

@st.cache_data(ttl=1800)
def get_weather():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=42.3601&longitude=-71.0589&current=temperature_2m&daily=temperature_2m_max,temperature_2m_min&timezone=America%2FNew_York"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception:
        return None

def get_youtube_link(query):
    try:
        videosSearch = VideosSearch(query, limit=1)
        res = videosSearch.result()
        if res and res.get('result'):
            return res['result'][0]['link']
    except Exception:
        return None
    return None

# ==========================================
# 5. 상단 UI: 뉴스 및 날씨 목록 (카드형)
# ==========================================
st.title("🇺🇸 보스턴 출근길 스몰톡 도우미")
st.markdown("오늘의 지역 가십거리와 날씨를 파악하고 동료들과 자연스럽게 대화해 보세요!")

col_refresh, _ = st.columns([1, 5])
with col_refresh:
    if st.button("🔄 최신 기사 새로고침", use_container_width=True):
        get_news.clear()
        st.rerun()

news_data = get_news()
tab_names = list(news_data.keys()) + ["🌤️ 보스턴 날씨"]
tabs = st.tabs(tab_names)

# --- 뉴스 영역 ---
for idx, (category, entries) in enumerate(news_data.items()):
    with tabs[idx]:
        cols = st.columns(3)
        for i, entry in enumerate(entries):
            with cols[i % 3]:
                with st.container(border=True):
                    title = entry.get('title', '제목 없음')
                    link = entry.get('link', '#')
                    # 요약본 데이터 정제
                    summary_raw = str(entry.get('summary', ''))
                    
                    # 👈 업그레이드된 이미지 추출 함수 적용
                    img_url = get_image_url(entry)
                    
                    st.image(img_url, use_container_width=True)
                    
                    prefix = get_category_prefix(title, summary_raw, category, link)
                    display_title = f"{prefix} {title}"
                    
                    short_title = display_title if len(display_title) < 60 else display_title[:57] + "..."
                    st.markdown(f"**{short_title}**")
                    
                    btn_key = f"btn_news_{idx}_{i}_{title[:10]}"
                    if st.button("분석 💬", key=btn_key, use_container_width=True):
                        with st.spinner("기사 분석 및 배경 지식을 검색하는 중입니다..."):
                            yt_link = get_youtube_link(title)
                            
                            prompt = f"""
                            다음 뉴스 기사 제목과 내용을 바탕으로 지정된 양식에 맞춰 엄격하게 작성해 줘. (인사말이나 다른 사담은 절대 추가하지 마시오)
                            
                            기사 제목: {title}
                            기사 내용: {summary_raw}
                            
                            [작성 양식]
                            ### 📝 영문 요약본
                            (기사 내용을 유추하여 2~3문장 영어 요약)
                            
                            ### 🇰🇷 국문 요약본
                            (위 영문 요약의 한국어 번역)
                            
                            ### 💡 뉴스 배경 지식 (영문)
                            (이 뉴스를 제대로 이해하기 위해 필요한 사전 지식을 2~3문장 영어로 설명. 등장하는 인물, 스포츠 팀의 연고지, 기업의 특징, 사건의 역사적 배경 등)
                            
                            ### 💡 뉴스 배경 지식 (국문)
                            (위 영문 배경 지식의 자연스러운 한국어 번역)
                            
                            ### 🗣️ 스몰톡 서두 추천 문구
                            (동료에게 말을 걸 때 쓸 수 있는 자연스러운 영어 아이스브레이커 2개와 뜻)
                            
                            ### 💬 스몰톡 추천 표현
                            (대화를 이어갈 때 쓸만한 유용한 영어 문장 3개와 뜻)
                            """
                            response = analyzer_model.generate_content(prompt)
                            st.session_state.selected_article = {
                                "title": display_title, "link": link, "yt_link": yt_link, "ai_analysis": response.text
                            }
                            
                            st.session_state.messages = []
                            st.session_state.chat_session = chat_model.start_chat(history=[
                                {"role": "user", "parts": [f"Let's talk about this news topic: {title}"]},
                                {"role": "model", "parts": [f"Sure! I saw that headline. What do you think about it?"]}
                            ])
                            st.session_state.show_chat = False
                        st.rerun()

# --- 날씨 영역 ---
with tabs[-1]:
    st.subheader("📍 미국 매사추세츠주 보스턴 (Boston, MA)")
    weather_data = get_weather()
    
    if weather_data:
        current_temp = weather_data.get('current', {}).get('temperature_2m', 'N/A')
        max_temp = weather_data.get('daily', {}).get('temperature_2m_max', ['N/A'])[0]
        min_temp = weather_data.get('daily', {}).get('temperature_2m_min', ['N/A'])[0]

        with st.container(border=True):
            col1, col2 = st.columns([4, 1])
            with col1:
                st.markdown(f"#### 🌡️ **현재 기온:** {current_temp}°C &nbsp;&nbsp;|&nbsp;&nbsp; 🔼 **최고:** {max_temp}°C &nbsp;&nbsp;|&nbsp;&nbsp; 🔽 **최저:** {min_temp}°C")
                
            with col2:
                if st.button("분석 💬", key="btn_weather_analysis", use_container_width=True):
                    with st.spinner("날씨 기반 스몰톡 표현을 준비 중입니다..."):
                        prompt = f"""
                        현재 보스턴의 날씨 데이터(현재 {current_temp}도, 최고 {max_temp}도, 최저 {min_temp}도)를 바탕으로 지정된 양식에 맞춰 엄격하게 작성해 줘. (인사말이나 다른 사담은 절대 추가하지 마시오)

                        [작성 양식]
                        ### 🌤️ 날씨 상황
                        (현재 보스턴 날씨의 체감이나 특징을 1~2문장으로 요약)
                        
                        ### 🗣️ 스몰톡 서두 추천 문구
                        (동료에게 날씨로 말을 걸 때 쓸 수 있는 자연스러운 영어 아이스브레이커 2개와 한국어 뜻)
                        
                        ### 💬 대화 이어가기
                        (이어서 주말 계획이나 점심 메뉴 등으로 화제를 부드럽게 전환하는 유용한 영어 문장 2개와 한국어 뜻)
                        """
                        response = analyzer_model.generate_content(prompt)
                        
                        st.session_state.selected_article = {
                            "title": f"🌤️ 오늘의 보스턴 날씨 (현재 {current_temp}°C)",
                            "link": "https://weather.com/weather/today/l/42.36,-71.06",
                            "yt_link": None,
                            "ai_analysis": response.text
                        }
                        
                        st.session_state.messages = []
                        st.session_state.chat_session = chat_model.start_chat(history=[
                            {"role": "user", "parts": [f"Let's talk about the weather in Boston today. It's around {current_temp} degrees Celsius."]},
                            {"role": "model", "parts": ["Yeah, the weather today is interesting! How are you finding the Boston weather so far?"]}
                        ])
                        st.session_state.show_chat = False
                    st.rerun()
    else:
        st.error("날씨 정보를 불러올 수 없습니다.")

st.divider()

# ==========================================
# 6. 하단 UI: 분석 결과 및 챗봇 영역
# ==========================================
if st.session_state.selected_article:
    article = st.session_state.selected_article
    
    st.subheader(f"📌 {article['title']}")
    st.markdown(article['ai_analysis'])
    
    st.markdown("### 🔗 관련 링크")
    st.markdown(f"👉 [원문 정보 바로가기]({article['link']})")
    if article['yt_link']:
        st.markdown(f"📺 [유튜브 관련 영상 보기]({article['yt_link']})")
    
    st.write("") 
    
    if not st.session_state.show_chat:
        if st.button("💬 동료와 이 주제로 영어 토론하기", use_container_width=True):
            st.session_state.show_chat = True
            st.rerun()

    if st.session_state.show_chat:
        st.divider()
        st.subheader("🗣️ 동료와의 대화 (영어)")
        
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])

        st.markdown("🎙️ **음성으로 말하기**")
        spoken_text = speech_to_text(language='en-US', use_container_width=True, just_once=True, key='STT')

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