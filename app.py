import streamlit as st
import google.generativeai as genai

# 1. 서버 금고(Secrets)에서 API 키를 몰래 꺼내옵니다. (코드에는 키가 노출되지 않음!)
api_key = st.secrets["GEMINI_API_KEY"]

# 2. 꺼내온 키로 Gemini 환경 세팅을 합니다.
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-pro')

# 3. 화면 UI 구성
st.title("🇺🇸 보스턴 스몰톡 준비 도우미")
st.write("오늘의 가십거리를 파악하고 영어로 대화를 연습해 보세요.")

# 테스트용 임시 뉴스 기사
sample_news = "The Boston Celtics secured a thrilling overtime victory against the Lakers last night..."
st.info(f"오늘의 뉴스: {sample_news}")

# 4. 버튼을 누르면 AI가 요약 및 서두를 추천합니다.
if st.button("이 뉴스로 스몰톡 준비하기"):
    with st.spinner("Gemini가 추천 표현을 작성 중입니다..."):
        prompt = f"다음 뉴스를 바탕으로 미국 현지 동료와 자연스럽게 스몰톡을 시작할 수 있는 영어 문장 3개와 한글 뜻을 작성해줘: {sample_news}"
        response = model.generate_content(prompt)
        
        st.success("추천 표현이 완성되었습니다!")
        st.write(response.text)