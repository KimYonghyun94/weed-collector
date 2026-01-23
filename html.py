import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
import io

# ==========================================
# 설정 부분 (여기만 수정하세요)
# 구글 드라이브 폴더 주소창 뒤에 있는 ID를 복사해서 아래에 넣으세요
PARENT_FOLDER_ID = "1zNu4c65H0_h4bN8Sd6R-YrU9Yt-Gh64a"
# ==========================================

# 구글 드라이브 인증 함수
def authenticate_drive():
    # Streamlit Secrets에서 키 가져오기
    gcp_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        gcp_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build('drive', 'v3', credentials=creds)

st.title("Turfgrass Data Collector (Drive) ☁️")

# 카메라 실행
img_file = st.camera_input("Take a picture")

if img_file is not None:
    try:
        # 1. 드라이브 서비스 연결
        service = authenticate_drive()
        
        # 2. 파일명 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"turf_{timestamp}.jpg"
        
        # 3. 업로드할 파일 메타데이터 설정
        file_metadata = {
            'name': filename,
            'parents': [PARENT_FOLDER_ID]
        }
        
        # 4. 파일 업로드
        media = MediaIoBaseUpload(img_file, mimetype='image/jpeg')
        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id'
        ).execute()
        
        st.success(f"구글 드라이브 저장 완료! (File ID: {file.get('id')})")
        
    except Exception as e:
        st.error(f"업로드 실패: {e}")
