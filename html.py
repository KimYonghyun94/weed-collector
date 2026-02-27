import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from PIL import Image
import io
import re
import os
import threading

# WebRTC (HD capture)
from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration

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
    return build("drive", "v3", credentials=creds)


def slugify(text: str, max_len: int = 40) -> str:
    if text is None:
        return "NA"
    text = text.strip()
    if not text:
        return "NA"
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]+", "", text)
    return text[:max_len] if len(text) > max_len else text


def guess_ext(mimetype: str, original_name: str | None = None) -> str:
    mt = (mimetype or "").lower()
    if "jpeg" in mt or "jpg" in mt:
        return "jpg"
    if "png" in mt:
        return "png"
    if "heic" in mt or "heif" in mt:
        return "heic"
    if original_name:
        _, ext = os.path.splitext(original_name)
        if ext:
            return ext.lstrip(".").lower()
    return "jpg"


def make_filename(turf_setting: str, grass_type: str, grass_other: str, weed_name: str,
                  mimetype: str, original_name: str | None = None) -> str:
    turf_part = slugify(turf_setting.replace(" ", ""))

    if grass_type == "Other" and grass_other.strip():
        grass_part = slugify(f"Other_{grass_other}")
    else:
        grass_part = slugify(grass_type)

    weed_part = slugify(weed_name)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = guess_ext(mimetype, original_name)
    return f"{turf_part}_{grass_part}_{weed_part}_{timestamp}.{ext}"


def try_get_image_size(image_bytes: bytes):
    """PIL로 열릴 때만 해상도 표시. (HEIC 등은 환경에 따라 실패 가능)"""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return img, img.size[0], img.size[1]
    except Exception:
        return None, None, None


def upload_bytes_to_drive(image_bytes: bytes, mimetype: str, filename: str):
    service = authenticate_drive()
    buffer = io.BytesIO(image_bytes)
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
# WebRTC Video Processor
# -------------------------
class HDVideoProcessor(VideoProcessorBase):
    def __init__(self):
        self._lock = threading.Lock()
        self._latest_bgr = None  # numpy array (bgr24)

    def recv(self, frame):
        img = frame.to_ndarray(format="bgr24")
        with self._lock:
            self._latest_bgr = img
        return frame

    def get_latest_bgr(self):
        with self._lock:
            if self._latest_bgr is None:
                return None
            return self._latest_bgr.copy()


RTC_CONFIG = RTCConfiguration(
    {"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]}
)


# -------------------------
# 입력 방식: 탭 3개
# -------------------------
tab_cam, tab_upload, tab_webrtc = st.tabs(
    ["📷 Streamlit Camera", "⬆️ Upload (High-res)", "🎥 WebRTC (HD Capture)"]
)

# 1) Streamlit 기본 camera_input
with tab_cam:
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        cam_file = st.camera_input("📸 (Click to Capture)")

    if cam_file is not None:
        image_bytes = cam_file.getvalue()
        mimetype = cam_file.type or "image/jpeg"
        filename = make_filename(turf_setting, grass_type, grass_other, weed_name, mimetype, cam_file.name)

        st.info(f"📄 File name preview: **{filename}**")

        img, w, h = try_get_image_size(image_bytes)
        if img is not None:
            st.image(img, use_container_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Width", f"{w} px")
            c2.metric("Height", f"{h} px")
        else:
            st.warning("미리보기/해상도 표시가 이 파일 형식에서는 지원되지 않을 수 있어요. 업로드는 가능합니다.")

        if st.button("☁️ Upload to Google Drive", key="btn_upload_cam"):
            with st.spinner("구글 드라이브로 전송 중입니다... ☁️"):
                try:
                    upload_bytes_to_drive(image_bytes, mimetype, filename)
                    st.success(f"✅ Save Done! (File: {filename})")
                except Exception as e:
                    st.error(f"❌ Fail: {e}")

# 2) 고해상도 원본 업로드: file_uploader
with tab_upload:
    up_file = st.file_uploader(
        "Upload a photo (Phone camera original recommended)",
        type=None,  # 모든 확장자 허용(HEIC 등도)
        accept_multiple_files=False
    )

    if up_file is not None:
        image_bytes = up_file.getvalue()
        mimetype = up_file.type or "application/octet-stream"
        filename = make_filename(turf_setting, grass_type, grass_other, weed_name, mimetype, up_file.name)

        st.info(f"📄 File name preview: **{filename}**")

        img, w, h = try_get_image_size(image_bytes)
        if img is not None:
            st.image(img, use_container_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Width", f"{w} px")
            c2.metric("Height", f"{h} px")
        else:
            st.warning("미리보기/해상도 표시가 이 파일 형식에서는 지원되지 않을 수 있어요(예: HEIC). 업로드는 가능합니다.")

        if st.button("☁️ Upload to Google Drive", key="btn_upload_file"):
            with st.spinner("구글 드라이브로 전송 중입니다... ☁️"):
                try:
                    upload_bytes_to_drive(image_bytes, mimetype, filename)
                    st.success(f"✅ Save Done! (File: {filename})")
                except Exception as e:
                    st.error(f"❌ Fail: {e}")

# 3) WebRTC HD 캡처
with tab_webrtc:
    st.caption("HD(ideal 1920x1080)로 카메라를 요청합니다. 브라우저/디바이스가 지원하는 범위 내에서 적용돼요.")

    webrtc_ctx = webrtc_streamer(
        key="webrtc_hd",
        video_processor_factory=HDVideoProcessor,
        rtc_configuration=RTC_CONFIG,
        media_stream_constraints={
            "video": {
                "width": {"ideal": 1920},
                "height": {"ideal": 1080},
                "frameRate": {"ideal": 30, "max": 60},
                "facingMode": "environment",
            },
            "audio": False,
        },
        async_processing=True,
    )

    # 캡처 버튼 -> 세션에 저장
    if st.button("📸 Capture frame (HD)", key="btn_capture_webrtc"):
        if webrtc_ctx.video_processor is None:
            st.warning("카메라가 아직 시작되지 않았어요.")
        else:
            bgr = webrtc_ctx.video_processor.get_latest_bgr()
            if bgr is None:
                st.warning("아직 프레임이 없습니다. 카메라가 뜬 뒤 잠시 후 다시 눌러주세요.")
            else:
                # BGR -> RGB (numpy slicing)
                rgb = bgr[:, :, ::-1]
                img = Image.fromarray(rgb)

                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=95)
                st.session_state["webrtc_captured_bytes"] = buf.getvalue()
                st.session_state["webrtc_captured_mime"] = "image/jpeg"

    # 캡처된 이미지가 있으면 미리보기 + 업로드
    if "webrtc_captured_bytes" in st.session_state:
        image_bytes = st.session_state["webrtc_captured_bytes"]
        mimetype = st.session_state.get("webrtc_captured_mime", "image/jpeg")
        filename = make_filename(turf_setting, grass_type, grass_other, weed_name, mimetype, "webrtc.jpg")

        st.info(f"📄 File name preview: **{filename}**")

        img, w, h = try_get_image_size(image_bytes)
        if img is not None:
            st.image(img, use_container_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Width", f"{w} px")
            c2.metric("Height", f"{h} px")

        if st.button("☁️ Upload to Google Drive", key="btn_upload_webrtc"):
            with st.spinner("구글 드라이브로 전송 중입니다... ☁️"):
                try:
                    upload_bytes_to_drive(image_bytes, mimetype, filename)
                    st.success(f"✅ Save Done! (File: {filename})")
                except Exception as e:
                    st.error(f"❌ Fail: {e}")
