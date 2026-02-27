import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from PIL import Image
import io
import re

# ==========================================
# 설정 부분
PARENT_FOLDER_ID = "12WeFmWCJ1RJE-kAzZdzeetp6Hqc32IcX"
# ==========================================

st.set_page_config(
    page_title="GWU Turfgrass Lab",
    page_icon="🌿",
    layout="centered"
)

st.markdown("""
    <h1 style='text-align: center; color: #2E8B57;'>
        🌿 USDA FNPRU Weed Data Collector
    </h1>
    <p style='text-align: center; color: gray;'>
        Computer Vision Research Data Acquisition System
    </p>
    <hr>
""", unsafe_allow_html=True)

def authenticate_drive():
    gcp_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        gcp_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build('drive', 'v3', credentials=creds)

def slugify(text: str, max_len: int = 40) -> str:
    if text is None:
        return "NA"
    text = text.strip()
    if not text:
        return "NA"
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]+", "", text)
    return text[:max_len] if len(text) > max_len else text

# -------------------------
# 옵션 UI
# -------------------------
with st.expander("Turf Setting", expanded=True):
    turf_setting = st.selectbox(
        "Select Turf Setting",
        ["Putting green", "Tees", "Fairway", "Rough"],
        index=0
    )

with st.expander("Turfgrass Type", expanded=True):
    grass_type = st.selectbox(
        "Select Grass Type",
        ["Bent", "KB", "Bermuda", "Poa", "Other"],
        index=0
    )
    grass_other = ""
    if grass_type == "Other":
        grass_other = st.text_input("If Other, type grass name (optional)", value="")

with st.expander("Weed Name", expanded=True):
    weed_name = st.text_input("Type Weed Name", value="", placeholder="e.g., crabgrass")

st.write("---")

# -------------------------
# 카메라 UI 중앙 정렬
# -------------------------
col1, col2, col3 = st.columns([1, 4, 1])
with col2:
    img_file = st.camera_input("📸 (Click to Capture)")

# -------------------------
# 사진이 찍히면 실행
# -------------------------
if img_file is not None:
    # 이미지 열기 (정보 표시용)
    image = Image.open(img_file)
    width, height = image.size

    st.write("---")
    c1, c2 = st.columns(2)
    with c1:
        st.metric(label="Width", value=f"{width} px")
    with c2:
        st.metric(label="Height", value=f"{height} px")

    # 파일명 구성 요소
    turf_part = slugify(turf_setting.replace(" ", ""))

    if grass_type == "Other" and grass_other.strip():
        grass_part = slugify(f"Other_{grass_other}")
    else:
        grass_part = slugify(grass_type)

    weed_part = slugify(weed_name)

    # 원본 mimetype 기준으로 확장자 결정 (대부분 image/jpeg)
    mimetype = img_file.type or "image/jpeg"
    ext = "jpg" if "jpeg" in mimetype else ("png" if "png" in mimetype else "jpg")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{turf_part}_{grass_part}_{weed_part}_{timestamp}.{ext}"

    st.info(f"📄 File name preview: **{filename}**")

    with st.spinner("구글 드라이브로 전송 중입니다... ☁️"):
        try:
            service = authenticate_drive()

            # ✅ 핵심: 원본 바이트 그대로 업로드 (재압축/리사이즈 없음)
            buffer = io.BytesIO(img_file.getvalue())
            buffer.seek(0)

            file_metadata = {
                "name": filename,
                "parents": [PARENT_FOLDER_ID],
            }

            media = MediaIoBaseUpload(buffer, mimetype=mimetype)

            service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()

            st.success(f"✅ Save Done! (File: {filename})")
            # ❌ st.balloons() 제거

        except Exception as e:
            st.error(f"❌ Fail: {e}")
