import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from PIL import Image  # 이미지 크기 확인용
import io

# ==========================================
# 설정 부분
PARENT_FOLDER_ID = "12WeFmWCJ1RJE-kAzZdzeetp6Hqc32IcX"
# ==========================================

# 1. 페이지 기본 설정 (탭 이름, 아이콘)
st.set_page_config(
    page_title="GWU Turfgrass Lab",
    page_icon="🌿",
    layout="centered"
)

# 2. 예쁜 헤더 (HTML 사용)
st.markdown("""
    <h1 style='text-align: center; color: #2E8B57;'>
        🌿 GWU Turfgrass Data Collector
    </h1>
    <p style='text-align: center; color: gray;'>
        Computer Vision Research Data Acquisition System
    </p>
    <hr>
""", unsafe_allow_html=True)

# 구글 드라이브 인증 함수
def authenticate_drive():
    gcp_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        gcp_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build('drive', 'v3', credentials=creds)

# 3. 카메라 UI 중앙 정렬
# (모바일은 꽉 차게, PC는 적당한 크기로 보이게 컬럼 사용)
col1, col2, col3 = st.columns([1, 4, 1])

with col2:
    img_file = st.camera_input("📸 터프그래스 사진 촬영 (Click to Capture)")

# 사진이 찍히면 실행
if img_file is not None:
    # 4. 이미지 정보 확인
    image = Image.open(img_file)
    width, height = image.size
    
    # 5. 결과 보여주기 (컬럼으로 나누기)
    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        st.metric(label="Width", value=f"{width} px")
    with c2:
        st.metric(label="Height", value=f"{height} px")

    # 6. 업로드 진행 (로딩바)
    with st.spinner('구글 드라이브로 전송 중입니다... ☁️'):
        try:
            # 드라이브 연결
            service = authenticate_drive()
            
            # 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"turf_{timestamp}.jpg"
            
            # 메타데이터
            file_metadata = {
                'name': filename,
                'parents': [PARENT_FOLDER_ID]
            }
            
            # 업로드 (이미지 파일 포인터를 처음으로 되돌림)
            img_file.seek(0) 
            media = MediaIoBaseUpload(img_file, mimetype='image/jpeg')
            
            file = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id',
                supportsAllDrives=True
            ).execute()
            
            # 7. 성공 메시지 및 효과
            st.success(f"✅ 저장 완료! (File: {filename})")
            st.balloons() # 풍선 효과 🎉
            
        except Exception as e:
            st.error(f"❌ 업로드 실패: {e}")
