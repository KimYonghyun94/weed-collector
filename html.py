import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime
from PIL import Image
import io
import re
import os
from typing import Optional
from zoneinfo import ZoneInfo

# ==========================================
# Settings
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

st.markdown(
    """
    **Quick Guide**
    1) Choose *Time Zone*, *Turf Setting*, *Turfgrass Type*, and *Weed Name*  
    2) Capture or upload photo(s)  
    3) For each photo, select the distance (1 m / 50 cm / 20 cm) and press **Save**  
    4) After saving all 3 distances, press **Upload ALL 3 images**
    """
)

# -------------------------
# 3-shot distance settings
# -------------------------
HEIGHTS = [
    ("1 m", "H1m"),
    ("50 cm", "H50cm"),
    ("20 cm", "H20cm"),
]
HEIGHT_MAP = dict(HEIGHTS)

# US time zone options (handles DST automatically)
TZ_OPTIONS = {
    "EST": "America/New_York",
    "CST": "America/Chicago",
    "MST": "America/Denver",
    "PST": "America/Los_Angeles",
}

def init_session():
    if "capture_set_ts" not in st.session_state:
        st.session_state.capture_set_ts = None  # fixed timestamp for the 3-shot set
    if "capture_set_tz" not in st.session_state:
        st.session_state.capture_set_tz = None  # fixed tz for the 3-shot set
    if "height_captures" not in st.session_state:
        st.session_state.height_captures = {}   # {height_tag: {bytes, mimetype, original_name}}

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

def slugify(text: str, max_len: int = 40) -> str:
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

def now_timestamp_str(tz_name: str) -> str:
    return datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d_%H%M%S")

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
    return f"{turf_part}_{grass_part}_{weed_part}_{height_tag}_{set_timestamp}.{ext}"

def try_get_image_size(image_bytes: bytes):
    """Preview/size only when PIL can open the image (HEIC may fail depending on environment)."""
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
# Options UI
# -------------------------
with st.expander("Time Zone", expanded=True):
    tz_code = st.selectbox("Select Time Zone", list(TZ_OPTIONS.keys()), index=0)
    tz_name = TZ_OPTIONS[tz_code]

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
# Save helper + distance picker (below images)
# -------------------------
def save_shot_for_height(height_tag: str, image_bytes: bytes, mimetype: str, original_name: Optional[str], tz_name: str):
    # Fix set timestamp & tz on first save (DST handled by ZoneInfo)
    if st.session_state.capture_set_ts is None:
        st.session_state.capture_set_tz = tz_name
        st.session_state.capture_set_ts = now_timestamp_str(tz_name)

    st.session_state.height_captures[height_tag] = {
        "bytes": image_bytes,
        "mimetype": mimetype,
        "original_name": original_name,
    }

def height_picker_ui(key_suffix: str):
    st.markdown("#### 📌 Select distance for this photo")
    chosen = st.radio(
        "Distance",
        [h[0] for h in HEIGHTS],
        horizontal=True,
        key=f"distance_{key_suffix}"
    )
    return chosen, HEIGHT_MAP[chosen]

# -------------------------
# Tabs
# -------------------------
tabs = st.tabs(["📷 Streamlit Camera", "⬆️ Upload (High-res)"])

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
            st.warning("Preview/size may not be available for this file type. Save/upload is still possible.")

        height_label, height_tag = height_picker_ui("cam")

        if st.button(f"✅ Save this shot ({height_label})", key="btn_save_cam"):
            save_shot_for_height(height_tag, image_bytes, mimetype, cam_file.name, tz_name)
            st.success(f"Saved for {height_label}.")

# 2) file_uploader (multi-select)
with tabs[1]:
    up_files = st.file_uploader(
        "Upload photo(s) (phone camera originals recommended)",
        type=None,
        accept_multiple_files=True
    )

    if up_files:
        st.write(f"Selected: **{len(up_files)} file(s)**")

        # If exactly 3 files: optional auto-assign by order
        if len(up_files) == 3:
            if st.button("✅ Auto-assign by order: 1 m → 50 cm → 20 cm", key="btn_auto_assign_3"):
                for (lbl, tag), f in zip(HEIGHTS, up_files):
                    save_shot_for_height(tag, f.getvalue(), f.type or "application/octet-stream", f.name, tz_name)
                st.success("Saved 3 photos to the 3-shot set by order (1 m → 50 cm → 20 cm).")

        # Manual mapping per file
        for i, f in enumerate(up_files):
            with st.expander(f"File {i+1}: {f.name}", expanded=(i == 0)):
                image_bytes = f.getvalue()
                mimetype = f.type or "application/octet-stream"

                img, w, h = try_get_image_size(image_bytes)
                if img is not None:
                    st.image(img, use_container_width=True)
                    c1, c2 = st.columns(2)
                    c1.metric("Width", f"{w} px")
                    c2.metric("Height", f"{h} px")
                else:
                    st.warning("Preview/size may not be available for this file type (e.g., HEIC). Save/upload is still possible.")

                height_label, height_tag = height_picker_ui(f"upload_{i}")

                if st.button(f"✅ Save this file ({height_label})", key=f"btn_save_upload_{i}"):
                    save_shot_for_height(height_tag, image_bytes, mimetype, f.name, tz_name)
                    st.success(f"Saved: {f.name} → {height_label}")

# -------------------------
# Bottom: 3-shot status (checkbox style) + Upload ALL 3
# -------------------------
st.write("---")

st.subheader("📏 3-shot Set Status (checkbox)")

def checkbox_line(label: str, tag: str) -> str:
    done = tag in st.session_state.height_captures
    box = "[x]" if done else "[ ]"
    return f"- {box} **{label}**"

st.markdown("\n".join([
    checkbox_line("1 m", "H1m"),
    checkbox_line("50 cm", "H50cm"),
    checkbox_line("20 cm", "H20cm"),
]))

col_reset, col_tip = st.columns([1, 3])
with col_reset:
    if st.button("Reset this 3-shot set", key="btn_reset_bottom"):
        st.session_state.capture_set_ts = None
        st.session_state.capture_set_tz = None
        st.session_state.height_captures = {}
        st.success("Reset completed.")
with col_tip:
    st.caption("Save one photo for each distance, then upload all 3 together below.")

st.subheader("☁️ Upload ALL 3 distances to Google Drive")

missing = [tag for (_, tag) in HEIGHTS if tag not in st.session_state.height_captures]
if missing:
    st.info(f"Remaining distances: {', '.join(missing)}")
else:
    st.success("All 3 distances are ready!")

    if st.button("🚀 Upload ALL 3 images now", key="btn_upload_all3"):
        with st.spinner("Uploading 3 images to Google Drive... ☁️"):
            try:
                # Keep the set timestamp consistent; if missing, use selected tz
                set_ts = st.session_state.capture_set_ts or now_timestamp_str(st.session_state.capture_set_tz or tz_name)

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

                st.success("✅ Done! (3 files uploaded)")
                for f in uploaded_files:
                    st.write(f"- {f}")

                # Reset for next set
                st.session_state.capture_set_ts = None
                st.session_state.capture_set_tz = None
                st.session_state.height_captures = {}

            except Exception as e:
                st.error(f"❌ Upload failed: {e}")
