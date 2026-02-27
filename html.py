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
from typing import Optional

# WebRTC (HD capture) - optional import (없으면 WebRTC 탭 숨김)
try:
    from streamlit_webrtc import webrtc_streamer, VideoProcessorBase, RTCConfiguration
    WEBRTC_AVAILABLE = True
except Exception:
    WEBRTC_AVAILABLE = False

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

# -------------------------
# 3-shot height settings
# -------------------------
HEIGHTS = [
    ("1 m", "H1m"),
    ("50 cm", "H50cm"),
    ("20 cm", "H20cm"),
]

def init_session():
    if "capture_set_ts" not in st.session_state:
        st.session_state.capture_set_ts = None  # 세트 공통 timestamp
    if "height_captures" not in st.session_state:
        st.session_state.height_captures = {}   # {height_tag: {bytes, mimetype, original_name}}
    if "webrtc_last_bytes" not in st.session_state:
        st.session_state.webrtc_last_bytes = None
    if "webrtc_last_mime" not in st.session_state:
        st.session_state.webrtc_last_mime = None

init_session()

# -------------------------
# Google Drive helpers
# -------------------------
def authenticate_drive():
    gcp_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        gcp_info, scopes=["https://www.googleapis.com/auth/drive"]
    )
    return build("drive", "v3", credentials=creds)

def slugify(text: str, max_len: int = 50) -> str:
    if text is None:
        return "NA"
    text = text.strip()
    if not text:
        return "NA"
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]+", "", text)
    return text[:max_len] if len(text) > max_len else text

def guess_ext(mimetype: str, original_name: Optional[str] = None) -> str:
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

def make_filename(
    turf_setting: str,
    grass_type: str,
    grass_other: str,
    weed_name: str,
    height_tag: str,
    mimetype: str,
    set_timestamp: str,
    original_name: Optional[str] = None,
) -> str:
    turf_part = slugify(turf_setting.replace(" ", ""))
    if grass_type == "Other" and grass_other.strip():
        grass_part = slugify(f"Other_{grass_other}")
    else:
        grass_part = slugify(grass_type)
    weed_part = slugify(weed_name)
    ext = guess_ext(mimetype, original_name)
    # 높이 태그 + 세트 timestamp 고정
    return f"{turf_part}_{grass_part}_{weed_part}_{height_tag}_{set_timestamp}.{ext}"

def try_get_image_size(image_bytes: bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return img, img.size[0], img.size[1]
    except Exception:
        return None, None, None

def upload_bytes_to_drive(image_bytes: bytes, mimetype: str, filename: str):
    service = authenticate_drive()
    buffer = io.BytesIO(image_bytes)
    buffer.seek(0)
    file_metadata = {"name": filename, "parents": [PARENT_FOLDER_ID]}
    media = MediaIoBaseUpload(buffer, mimetype=mimetype)
    service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()

# -------------------------
# Capture set UI (height selector + progress)
# -------------------------
st.subheader("📏 3-shot Capture Set (1m / 50cm / 20cm)")
height_label = st.radio(
    "Select height for this shot",
    [h[0] for h in HEIGHTS],
    horizontal=True
)
height_tag = dict(HEIGHTS)[height_label]

# progress display
cols = st.columns(3)
for i, (lbl, tag) in enumerate(HEIGHTS):
    done = tag in st.session_state.height_captures
    with cols[i]:
        st.write(f"**{lbl}**")
        st.write("✅ Saved" if done else "⬜ Not yet")

c_reset, c_hint = st.columns([1, 3])
with c_reset:
    if st.button("Reset this 3-shot set"):
        st.session_state.capture_set_ts = None
        st.session_state.height_captures = {}
        st.session_state.webrtc_last_bytes = None
        st.session_state.webrtc_last_mime = None
        st.success("Reset done.")
with c_hint:
    st.caption("각 높이에서 한 장씩 저장한 뒤, 아래의 Upload ALL 3 버튼으로 3장을 한 번에 업로드하세요.")

st.write("---")

# -------------------------
# 옵션 UI
# -------------------------
with st.expander("Turf Setting", expanded=True):
    turf_setting = st.selectbox(
        "Select Turf Setting",
        ["Putting Green", "Tees", "Fairway", "Rough"],
        index=0
    )

with st.expander("Turfgrass Type", expanded=True):
    grass_type = st.selectbox(
        "Select Grass Type",
        ["Bentgrass", "Bermuda", "Poa annua", "Ryegrass", "Zoysiagrass", "Other"],
        index=0
    )
    grass_other = ""
    if grass_type == "Other":
        grass_other = st.text_input("If Other, type grass name (optional)", value="")

WEED_OPTIONS = [
    "Algal crusts",
    "Annual bluegrass",
    "Bermudagrass (in cool-season turf)",
    "Cheatgrass",
    "Crabgrass",
    "Creeping bentgrass (in bermuda/zoysia)",
    "Dandelion",
    "Goosegrass",
    "Green kyllinga",
    "Henbit",
    "Mouse-ear chickweed",
    "Other",
    "Oxalis",
    "Plantain",
    "prostrate knotweed",
    "Prostrate spurge",
    "Rough bluegrass",
    "Shepherd’s purse",
    "Silvery thread moss",
    "White clover",
    "Yellow nutsedge",
]

with st.expander("Weed Name", expanded=True):
    weed_selected = st.selectbox("Select Weed Name", WEED_OPTIONS, index=0)
    weed_other = ""
    if weed_selected == "Other":
        weed_other = st.text_input("If Other, type weed name", value="", placeholder="e.g., unknown_weed")

if weed_selected == "Other" and weed_other.strip():
    weed_name = f"Other_{weed_other.strip()}"
else:
    weed_name = weed_selected

st.write("---")

# -------------------------
# helper: store capture for selected height
# -------------------------
def save_shot_for_height(image_bytes: bytes, mimetype: str, original_name: Optional[str]):
    # 세트 timestamp가 없으면, 첫 저장 시점에 고정
    if st.session_state.capture_set_ts is None:
        st.session_state.capture_set_ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.session_state.height_captures[height_tag] = {
        "bytes": image_bytes,
        "mimetype": mimetype,
        "original_name": original_name,
    }

# -------------------------
# Tabs
# -------------------------
tab_names = ["📷 Streamlit Camera", "⬆️ Upload (High-res)"]
if WEBRTC_AVAILABLE:
    tab_names.append("🎥 WebRTC (HD Capture)")
tabs = st.tabs(tab_names)

# 1) Streamlit camera_input
with tabs[0]:
    col1, col2, col3 = st.columns([1, 4, 1])
    with col2:
        cam_file = st.camera_input("📸 (Click to Capture)")

    if cam_file is not None:
        image_bytes = cam_file.getvalue()
        mimetype = cam_file.type or "image/jpeg"

        img, w, h = try_get_image_size(image_bytes)
        if img is not None:
            st.image(img, use_container_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Width", f"{w} px")
            c2.metric("Height", f"{h} px")
        else:
            st.warning("미리보기/해상도 표시가 이 파일 형식에서는 지원되지 않을 수 있어요.")

        if st.button(f"✅ Save this shot for {height_label}", key="btn_save_cam"):
            save_shot_for_height(image_bytes, mimetype, cam_file.name)
            st.success(f"Saved for {height_label} ({height_tag}).")

# 2) file_uploader (high-res)
with tabs[1]:
    up_file = st.file_uploader(
        "Upload a photo (Phone camera original recommended)",
        type=None,
        accept_multiple_files=False
    )

    if up_file is not None:
        image_bytes = up_file.getvalue()
        mimetype = up_file.type or "application/octet-stream"

        img, w, h = try_get_image_size(image_bytes)
        if img is not None:
            st.image(img, use_container_width=True)
            c1, c2 = st.columns(2)
            c1.metric("Width", f"{w} px")
            c2.metric("Height", f"{h} px")
        else:
            st.warning("미리보기/해상도 표시가 이 파일 형식에서는 지원되지 않을 수 있어요(예: HEIC).")

        if st.button(f"✅ Save this upload for {height_label}", key="btn_save_upload"):
            save_shot_for_height(image_bytes, mimetype, up_file.name)
            st.success(f"Saved for {height_label} ({height_tag}).")

# 3) WebRTC HD capture
if WEBRTC_AVAILABLE:
    class HDVideoProcessor(VideoProcessorBase):
        def __init__(self):
            self._lock = threading.Lock()
            self._latest_bgr = None

        def recv(self, frame):
            img = frame.to_ndarray(format="bgr24")
            with self._lock:
                self._latest_bgr = img
            return frame

        def get_latest_bgr(self):
            with self._lock:
                return None if self._latest_bgr is None else self._latest_bgr.copy()

    RTC_CONFIG = RTCConfiguration({"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]})

    with tabs[2]:
        st.caption("HD(ideal 1920x1080)로 카메라를 요청합니다. 브라우저/디바이스 지원 범위 내에서 적용돼요.")

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

        if st.button("📸 Capture frame (HD)", key="btn_capture_webrtc"):
            if webrtc_ctx.video_processor is None:
                st.warning("카메라가 아직 시작되지 않았어요.")
            else:
                bgr = webrtc_ctx.video_processor.get_latest_bgr()
                if bgr is None:
                    st.warning("아직 프레임이 없습니다. 카메라가 뜬 뒤 잠시 후 다시 눌러주세요.")
                else:
                    rgb = bgr[:, :, ::-1]
                    img = Image.fromarray(rgb)

                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=95)
                    st.session_state.webrtc_last_bytes = buf.getvalue()
                    st.session_state.webrtc_last_mime = "image/jpeg"
                    st.success("Frame captured. Now you can save it for the selected height.")

        if st.session_state.webrtc_last_bytes is not None:
            img, w, h = try_get_image_size(st.session_state.webrtc_last_bytes)
            if img is not None:
                st.image(img, use_container_width=True)
                c1, c2 = st.columns(2)
                c1.metric("Width", f"{w} px")
                c2.metric("Height", f"{h} px")

            if st.button(f"✅ Save this frame for {height_label}", key="btn_save_webrtc_frame"):
                save_shot_for_height(
                    st.session_state.webrtc_last_bytes,
                    st.session_state.webrtc_last_mime or "image/jpeg",
                    "webrtc.jpg"
                )
                st.success(f"Saved for {height_label} ({height_tag}).")

# -------------------------
# Upload ALL 3 shots
# -------------------------
st.write("---")
st.subheader("☁️ Upload ALL 3 heights to Google Drive")

missing = [tag for (_, tag) in HEIGHTS if tag not in st.session_state.height_captures]
if missing:
    st.info(f"남은 높이: {', '.join(missing)}")
else:
    st.success("3개 높이 사진이 모두 준비됐어요!")

    if st.button("🚀 Upload ALL 3 images now", key="btn_upload_all3"):
        with st.spinner("구글 드라이브로 3장을 전송 중입니다... ☁️"):
            try:
                set_ts = st.session_state.capture_set_ts or datetime.now().strftime("%Y%m%d_%H%M%S")

                uploaded_files = []
                for lbl, tag in HEIGHTS:
                    item = st.session_state.height_captures[tag]
                    filename = make_filename(
                        turf_setting=turf_setting,
                        grass_type=grass_type,
                        grass_other=grass_other,
                        weed_name=weed_name,
                        height_tag=tag,
                        mimetype=item["mimetype"],
                        set_timestamp=set_ts,
                        original_name=item["original_name"],
                    )
                    upload_bytes_to_drive(item["bytes"], item["mimetype"], filename)
                    uploaded_files.append(filename)

                st.success("✅ Save Done! (3 files uploaded)")
                for f in uploaded_files:
                    st.write(f"- {f}")

                # 업로드 후 다음 세트를 위해 초기화(원치 않으면 이 블록 주석 처리)
                st.session_state.capture_set_ts = None
                st.session_state.height_captures = {}
                st.session_state.webrtc_last_bytes = None
                st.session_state.webrtc_last_mime = None

            except Exception as e:
                st.error(f"❌ Fail: {e}")
