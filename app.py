# -*- coding: utf-8 -*-
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from datetime import datetime, timedelta
from PIL import Image
import io
import re
import os
from typing import Optional, Dict, Any
from zoneinfo import ZoneInfo

# ------------------------------------------
# Optional: Rear camera component (iPad-friendly)
# pip install streamlit-back-camera-input
# ------------------------------------------
try:
    from streamlit_back_camera_input import back_camera_input
    BACK_CAM_AVAILABLE = True
except Exception:
    BACK_CAM_AVAILABLE = False

# ==========================================
# Settings
# ==========================================
PARENT_FOLDER_ID = "12WeFmWCJ1RJE-kAzZdzeetp6Hqc32IcX"

st.set_page_config(
    page_title="GWU Turfgrass Lab",
    page_icon="🌿",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container {
    padding-top: 0.8rem;
    padding-bottom: 1.5rem;
    max-width: 760px;
}

.header h1 {
    margin: 0;
    line-height: 1.08;
    text-align: center;
    color: #2E8B57;
    font-size: 1.9rem;
}

.contact-wrap {
    display:flex;
    justify-content:center;
    margin-top: 0.6rem;
}

.contact-grid {
    display:grid;
    grid-template-columns: auto auto;
    column-gap: 0.7rem;
    row-gap: 0.2rem;
    text-align:left;
    color: gray;
    font-size: 0.98rem;
    line-height: 1.25;
}

.header hr {
    margin-top: 0.9rem;
    margin-bottom: 0.8rem;
}

/* Big tap targets */
div.stButton > button {
    width: 100%;
    min-height: 4rem;
    font-size: 1.08rem;
    font-weight: 700;
    border-radius: 16px;
}

div[data-baseweb="input"] input {
    font-size: 1.2rem !important;
    padding-top: 0.7rem !important;
    padding-bottom: 0.7rem !important;
}

div[data-baseweb="select"] > div {
    min-height: 3rem !important;
    font-size: 1rem !important;
}

.step-card {
    border: 1px solid #dfe6df;
    border-radius: 18px;
    padding: 1rem;
    background: #f9fcf9;
    margin-bottom: 0.8rem;
}

.step-title {
    font-size: 1.45rem;
    font-weight: 800;
    text-align: center;
    color: #1d5f3b;
    margin-bottom: 0.25rem;
}

.step-subtitle {
    font-size: 0.98rem;
    color: #5f6d5f;
    text-align: center;
    margin-bottom: 0.65rem;
}

.summary-card {
    border: 1px solid #dde7dd;
    border-radius: 16px;
    padding: 1rem;
    background: #fbfdfb;
}

.small-muted {
    color: #6b7280;
    font-size: 0.9rem;
    text-align: center;
}

.compact-note {
    font-size: 0.88rem;
    color: #6b7280;
    text-align: center;
    margin-top: 0.4rem;
}

/* make columns a bit tighter on mobile */
div[data-testid="column"] {
    padding-left: 0.18rem !important;
    padding-right: 0.18rem !important;
}
</style>

<div class="header">
  <h1>
    USDA USNA FNPRU<br>
    <div>Weed Data Collector</div>
  </h1>

  <div class="contact-wrap">
    <div class="contact-grid">
      <div>Contact info:</div><div>Jinyoung.barnaby@usda.gov</div>
      <div></div><div>Yonghyun.kim@usda.gov</div>
    </div>
  </div>

  <hr>
</div>
""", unsafe_allow_html=True)

# -------------------------
# Session state
# -------------------------
def init_session():
    if "capture_set_ts" not in st.session_state:
        st.session_state.capture_set_ts = None
    if "capture_set_tz" not in st.session_state:
        st.session_state.capture_set_tz = None
    if "height_captures" not in st.session_state:
        st.session_state.height_captures = {}
    if "drive_service" not in st.session_state:
        st.session_state.drive_service = None
    if "parent_drive_id" not in st.session_state:
        st.session_state.parent_drive_id = None
    if "parent_drive_checked" not in st.session_state:
        st.session_state.parent_drive_checked = False
    if "folder_cache" not in st.session_state:
        st.session_state.folder_cache = {}
    if "rear_cam_nonce" not in st.session_state:
        st.session_state.rear_cam_nonce = 0

    if "form_step" not in st.session_state:
        st.session_state.form_step = 0

    if "form_values" not in st.session_state:
        st.session_state.form_values = {
            "zipcode": "",
            "timezone": None,
            "turf_setting": None,
            "grass_type": "",
            "weed_name": "",
        }

init_session()

# -------------------------
# Constants
# -------------------------
FOLDER_MIME = "application/vnd.google-apps.folder"

HEIGHTS = [
    ("1 m", "H1m"),
    ("50 cm", "H50cm"),
    ("20 cm", "H20cm"),
]
HEIGHT_MAP = dict(HEIGHTS)

TZ_OPTIONS = {
    "EST": "America/New_York",
    "CST": "America/Chicago",
    "MST": "America/Denver",
    "PST": "America/Los_Angeles",
}

TURF_OPTIONS = [
    ("PG", "Putting Green"),
    ("Tees", "Tees"),
    ("Fairway", "Fairway"),
    ("Rough", "Rough"),
]

SKIP = "(skip / optional)"
CONF_LEVEL_OPTIONS = [SKIP, "High", "Medium", "Low"]
GROWTH_STAGE_OPTIONS = [SKIP, "Seedling", "Vegetative", "Flowering", "Seed set", "Senescent"]
PATCH_SIZE_OPTIONS = [SKIP, "0-10cm", "10-30cm", "30-100cm", "<1m"]
HERBICIDE_30D_OPTIONS = [SKIP, "Yes", "No"]

PATCH_CODE_MAP = {
    "0-10cm": "P0_10cm",
    "10-30cm": "P10_30cm",
    "30-100cm": "P30_100cm",
    "<1m": "Plt1m",
}

# -------------------------
# Helpers
# -------------------------
def slugify(text: str, max_len: int = 40) -> str:
    if text is None:
        return "NA"
    text = text.strip()
    if not text:
        return "NA"
    text = text.replace(" ", "_")
    text = re.sub(r"[^A-Za-z0-9_\-]+", "", text)
    return text[:max_len] if len(text) > max_len else text

def normalize_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    if not v or v == SKIP:
        return None
    return v

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

def try_get_image_size(image_bytes: bytes):
    try:
        img = Image.open(io.BytesIO(image_bytes))
        return img, img.size[0], img.size[1]
    except Exception:
        return None, None, None

def format_meta_for_status(meta: Dict[str, Any]) -> str:
    if not meta:
        return ""
    conf = normalize_optional(meta.get("confidence"))
    stage = normalize_optional(meta.get("growth_stage"))
    patch = normalize_optional(meta.get("patch_size"))
    herb = normalize_optional(meta.get("herbicide_30d"))
    bits = []
    if conf:
        bits.append(f"Conf: {conf}")
    if stage:
        bits.append(f"Stage: {stage}")
    if patch:
        bits.append(f"Patch: {patch}")
    if herb:
        bits.append(f"Herb: {herb}")
    return ", ".join(bits)

def make_filename(
    turf_setting: str,
    grass_type: str,
    weed_name: str,
    height_tag: str,
    mimetype: str,
    set_timestamp: str,
    original_name: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    meta = meta or {}

    turf_part = slugify(turf_setting.replace(" ", ""))
    grass_part = slugify(grass_type)
    weed_part = slugify(weed_name)
    ext = guess_ext(mimetype, original_name)

    parts = [turf_part, grass_part, weed_part, height_tag, set_timestamp]

    conf = normalize_optional(meta.get("confidence"))
    stage = normalize_optional(meta.get("growth_stage"))
    patch = normalize_optional(meta.get("patch_size"))
    herb = normalize_optional(meta.get("herbicide_30d"))

    if conf:
        parts.append(slugify(f"Conf{conf}", max_len=18))
    if stage:
        parts.append(slugify(f"Stage{stage}", max_len=22))
    if patch:
        patch_code = PATCH_CODE_MAP.get(patch, slugify(f"P{patch}", max_len=18))
        parts.append(slugify(patch_code, max_len=18))
    if herb:
        parts.append(slugify(f"Herb{herb}", max_len=12))

    return f"{'_'.join(parts)}.{ext}"

def go_to_step(step: int):
    st.session_state.form_step = step
    st.rerun()

def set_form_value(field: str, value: str, next_step: Optional[int] = None):
    st.session_state.form_values[field] = value
    if next_step is not None:
        st.session_state.form_step = next_step
    st.rerun()

def get_selected_values():
    values = st.session_state.form_values
    zipcode = values.get("zipcode", "").strip()
    selected_tz_code = values.get("timezone")
    turf_setting = values.get("turf_setting")
    grass_type = values.get("grass_type", "").strip()
    weed_name = values.get("weed_name", "").strip()
    tz_name = TZ_OPTIONS.get(selected_tz_code, "America/New_York")

    return {
        "zipcode": zipcode,
        "selected_tz_code": selected_tz_code,
        "tz_name": tz_name,
        "turf_setting": turf_setting,
        "grass_type": grass_type,
        "weed_name": weed_name,
    }

def is_form_complete() -> bool:
    v = get_selected_values()
    if not re.fullmatch(r"\d{5}", v["zipcode"]):
        return False
    if not v["selected_tz_code"]:
        return False
    if not v["turf_setting"]:
        return False
    if not v["grass_type"]:
        return False
    if not v["weed_name"]:
        return False
    return True

def render_progress():
    steps = [
        "ZIP Code",
        "Time Zone",
        "Turf Setting",
        "Text Input",
        "Photo Upload"
    ]
    step_idx = min(st.session_state.form_step, len(steps) - 1)
    st.progress((step_idx + 1) / len(steps), text=f"Step {step_idx + 1}/{len(steps)}: {steps[step_idx]}")

def render_step_header(title: str, subtitle: str = ""):
    st.markdown("<div class='step-card'>", unsafe_allow_html=True)
    st.markdown(f"<div class='step-title'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='step-subtitle'>{subtitle}</div>", unsafe_allow_html=True)

def close_step_card():
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------
# Drive helpers
# -------------------------
def get_drive_service():
    if st.session_state.drive_service is not None:
        return st.session_state.drive_service

    gcp_info = st.secrets["gcp_service_account"]
    creds = service_account.Credentials.from_service_account_info(
        gcp_info,
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    service = build("drive", "v3", credentials=creds)
    st.session_state.drive_service = service
    return service

def get_parent_drive_id() -> Optional[str]:
    if st.session_state.parent_drive_checked:
        return st.session_state.parent_drive_id

    service = get_drive_service()
    meta = service.files().get(
        fileId=PARENT_FOLDER_ID,
        fields="id,driveId",
        supportsAllDrives=True
    ).execute()

    st.session_state.parent_drive_id = meta.get("driveId")
    st.session_state.parent_drive_checked = True
    return st.session_state.parent_drive_id

def get_or_create_folder(parent_id: str, folder_name: str) -> str:
    cache_key = f"{parent_id}:{folder_name}"
    if cache_key in st.session_state.folder_cache:
        return st.session_state.folder_cache[cache_key]

    service = get_drive_service()
    drive_id = get_parent_drive_id()

    q = (
        f"mimeType='{FOLDER_MIME}' and "
        f"name='{folder_name}' and "
        f"'{parent_id}' in parents and "
        f"trashed=false"
    )

    if drive_id:
        res = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
            corpora="drive",
            driveId=drive_id,
            includeItemsFromAllDrives=True,
            supportsAllDrives=True
        ).execute()
    else:
        res = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
            corpora="user",
            includeItemsFromAllDrives=True,
            supportsAllDrives=True
        ).execute()

    files = res.get("files", [])
    if files:
        folder_id = files[0]["id"]
        st.session_state.folder_cache[cache_key] = folder_id
        return folder_id

    folder_meta = {
        "name": folder_name,
        "mimeType": FOLDER_MIME,
        "parents": [parent_id]
    }
    created = service.files().create(
        body=folder_meta,
        fields="id",
        supportsAllDrives=True
    ).execute()

    folder_id = created["id"]
    st.session_state.folder_cache[cache_key] = folder_id
    return folder_id

def ensure_zip_date_folder(zipcode: str, tz_name: str, date_str: Optional[str] = None) -> tuple[str, str, str]:
    if date_str is None:
        date_str = datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")

    zip_folder_id = get_or_create_folder(PARENT_FOLDER_ID, zipcode)
    date_folder_id = get_or_create_folder(zip_folder_id, date_str)
    return zip_folder_id, date_folder_id, date_str

def upload_bytes_to_drive(image_bytes: bytes, mimetype: str, filename: str, parent_id: str):
    service = get_drive_service()
    buffer = io.BytesIO(image_bytes)
    buffer.seek(0)

    file_metadata = {"name": filename, "parents": [parent_id]}
    media = MediaIoBaseUpload(buffer, mimetype=mimetype)

    service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id",
        supportsAllDrives=True
    ).execute()

# -------------------------
# Save helpers
# -------------------------
def save_shot_for_height(
    height_tag: str,
    image_bytes: bytes,
    mimetype: str,
    original_name: Optional[str],
    tz_name: str,
    meta: Optional[Dict[str, Any]] = None
):
    if st.session_state.capture_set_ts is None:
        st.session_state.capture_set_tz = tz_name
        st.session_state.capture_set_ts = now_timestamp_str(tz_name)

    st.session_state.height_captures[height_tag] = {
        "bytes": image_bytes,
        "mimetype": mimetype,
        "original_name": original_name,
        "meta": meta or {},
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

def optional_meta_ui(key_suffix: str) -> Dict[str, Any]:
    with st.expander("Optional annotations (can skip all)", expanded=True):
        c1, c2 = st.columns(2)
        conf = c1.selectbox(
            "Image Confidence Level (optional)",
            CONF_LEVEL_OPTIONS,
            index=0,
            key=f"conf_{key_suffix}"
        )
        herb = c2.selectbox(
            "Herbicide Application (within 30 days) (optional)",
            HERBICIDE_30D_OPTIONS,
            index=0,
            key=f"herb_{key_suffix}"
        )

        stage = st.selectbox(
            "Growth Stage (optional)",
            GROWTH_STAGE_OPTIONS,
            index=0,
            key=f"stage_{key_suffix}"
        )

        patch = st.selectbox(
            "Weed Patch Size (optional)",
            PATCH_SIZE_OPTIONS,
            index=0,
            key=f"patch_{key_suffix}"
        )

    return {
        "confidence": normalize_optional(conf),
        "growth_stage": normalize_optional(stage),
        "patch_size": normalize_optional(patch),
        "herbicide_30d": normalize_optional(herb),
    }

# -------------------------
# Step rendering
# -------------------------
render_progress()

# Step 0: ZIP
if st.session_state.form_step == 0:
    render_step_header(
        "Enter ZIP Code",
        "First step"
    )

    zip_input = st.text_input(
        "5-digit ZIP Code",
        value=st.session_state.form_values.get("zipcode", ""),
        placeholder="e.g., 20740",
        max_chars=5
    )
    st.session_state.form_values["zipcode"] = zip_input.strip()

    close_step_card()

    if zip_input and not re.fullmatch(r"\d{5}", zip_input.strip()):
        st.error("Please enter a valid 5-digit ZIP Code.")

    if st.button("Next", key="go_zip_next", use_container_width=True):
        if re.fullmatch(r"\d{5}", zip_input.strip()):
            go_to_step(1)
        else:
            st.error("ZIP Code must be exactly 5 digits.")

# Step 1: Time Zone
elif st.session_state.form_step == 1:
    render_step_header("Select Time Zone", "Horizontal layout for mobile")

    cols = st.columns(4)
    for col, tz_code in zip(cols, TZ_OPTIONS.keys()):
        with col:
            if st.button(tz_code, key=f"btn_tz_{tz_code}", use_container_width=True):
                set_form_value("timezone", tz_code, next_step=2)

    st.markdown("<div class='compact-note'>EST / CST / MST / PST</div>", unsafe_allow_html=True)
    close_step_card()

    if st.button("⬅️ Back", key="back_to_zip", use_container_width=True):
        go_to_step(0)

# Step 2: Turf Setting
elif st.session_state.form_step == 2:
    render_step_header("Select Turf Setting", "Horizontal layout for mobile")

    cols = st.columns(4)
    for col, (label, full_value) in zip(cols, TURF_OPTIONS):
        with col:
            if st.button(label, key=f"btn_turf_{slugify(full_value)}", use_container_width=True):
                set_form_value("turf_setting", full_value, next_step=3)

    st.markdown(
        "<div class='compact-note'>PG = Putting Green</div>",
        unsafe_allow_html=True
    )
    close_step_card()

    if st.button("⬅️ Back", key="back_to_tz", use_container_width=True):
        go_to_step(1)

# Step 3: Text input only
elif st.session_state.form_step == 3:
    render_step_header("Type Information", "No more option lists. Use keyboard input.")

    grass_type = st.text_input(
        "Turfgrass Type",
        value=st.session_state.form_values.get("grass_type", ""),
        placeholder="e.g., Bentgrass"
    )
    weed_name = st.text_input(
        "Weed Name",
        value=st.session_state.form_values.get("weed_name", ""),
        placeholder="e.g., Crabgrass"
    )

    st.session_state.form_values["grass_type"] = grass_type.strip()
    st.session_state.form_values["weed_name"] = weed_name.strip()

    close_step_card()

    if st.button("Next", key="go_photo_step", use_container_width=True):
        if not grass_type.strip():
            st.error("Please type Turfgrass Type.")
        elif not weed_name.strip():
            st.error("Please type Weed Name.")
        else:
            go_to_step(4)

    if st.button("⬅️ Back", key="back_to_turf", use_container_width=True):
        go_to_step(2)

# Step 4: Photo page
elif st.session_state.form_step == 4:
    vals = get_selected_values()
    if not is_form_complete():
        st.error("Required information is incomplete.")
        go_to_step(0)

    zipcode = vals["zipcode"]
    selected_tz_code = vals["selected_tz_code"]
    tz_name = vals["tz_name"]
    turf_setting = vals["turf_setting"]
    grass_type = vals["grass_type"]
    weed_name = vals["weed_name"]

    st.success("✅ Setup complete. You can now upload or capture photos.")

    with st.expander("Selected info", expanded=False):
        st.write(f"- ZIP Code: **{zipcode}**")
        st.write(f"- Time Zone: **{selected_tz_code}**")
        st.write(f"- Turf Setting: **{turf_setting}**")
        st.write(f"- Turfgrass Type: **{grass_type}**")
        st.write(f"- Weed Name: **{weed_name}**")

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("⬅️ Edit Info", key="edit_info_btn", use_container_width=True):
            go_to_step(3)
    with col_b:
        if st.button("Reset Form", key="reset_form_btn", use_container_width=True):
            st.session_state.form_step = 0
            st.session_state.form_values = {
                "zipcode": "",
                "timezone": None,
                "turf_setting": None,
                "grass_type": "",
                "weed_name": "",
            }
            st.session_state.capture_set_ts = None
            st.session_state.capture_set_tz = None
            st.session_state.height_captures = {}
            st.rerun()

    st.markdown("""
    **Quick Guide**
    1) Upload photos in multiples of **3** (3/6/9/...) **OR** capture with camera  
    2) Upload order for each set must be: **1 m → 50 cm → 20 cm**  
    3) For camera/manual mode, save each distance then press **Upload ALL 3 images**
    """)

    tabs = st.tabs(["⬆️ Upload (High-res)", "📷 Camera (Rear-first for iPad)"])

    # =========================
    # 1) Upload tab (batch)
    # =========================
    with tabs[0]:
        up_files = st.file_uploader(
            "Upload photo(s) (phone camera originals recommended)",
            type=None,
            accept_multiple_files=True
        )

        if up_files:
            n = len(up_files)
            st.write(f"Selected: **{n} file(s)**")

            if n % 3 != 0:
                st.error("❌ Please upload in multiples of 3 (3, 6, 9, ...). Each set = 1 m / 50 cm / 20 cm.")
                st.info("Tip: Upload order for each set must be 1 m → 50 cm → 20 cm, then repeat.")
            else:
                num_sets = n // 3
                st.success(f"✅ Batch recognized: **{num_sets} set(s)**")

                st.markdown("### 📦 Batch grouping (by upload order)")
                for s in range(num_sets):
                    i0 = s * 3
                    f1, f2, f3 = up_files[i0], up_files[i0 + 1], up_files[i0 + 2]
                    st.markdown(
                        f"**Set {s+1}**  \n"
                        f"- 1 m   → `{f1.name}`  \n"
                        f"- 50 cm → `{f2.name}`  \n"
                        f"- 20 cm → `{f3.name}`"
                    )

                if st.button(f"🚀 Upload ALL ({num_sets} set(s) / {n} files)", key="btn_upload_batch_3n", use_container_width=True):
                    with st.spinner("Uploading batch to Google Drive... ☁️"):
                        try:
                            base_dt = datetime.now(ZoneInfo(tz_name))
                            date_str = base_dt.strftime("%Y%m%d")
                            _, date_folder_id, _ = ensure_zip_date_folder(zipcode, tz_name, date_str=date_str)

                            uploaded_files = []
                            for s in range(num_sets):
                                set_ts = (base_dt + timedelta(seconds=s)).strftime("%Y%m%d_%H%M%S")
                                i0 = s * 3
                                group = [up_files[i0], up_files[i0 + 1], up_files[i0 + 2]]

                                for (_, height_tag), f in zip(HEIGHTS, group):
                                    image_bytes = f.getvalue()
                                    mimetype = f.type or "application/octet-stream"

                                    filename = make_filename(
                                        turf_setting=turf_setting,
                                        grass_type=grass_type,
                                        weed_name=weed_name,
                                        height_tag=height_tag,
                                        mimetype=mimetype,
                                        set_timestamp=set_ts,
                                        original_name=f.name,
                                        meta=None,
                                    )

                                    upload_bytes_to_drive(image_bytes, mimetype, filename, parent_id=date_folder_id)
                                    uploaded_files.append(filename)

                            st.success(f"✅ Done! Uploaded **{len(uploaded_files)}** files.")
                            for fn in uploaded_files[:15]:
                                st.write(f"- {fn}")
                            if len(uploaded_files) > 15:
                                st.write(f"...and {len(uploaded_files) - 15} more.")

                        except Exception as e:
                            st.error(f"❌ Upload failed: {e}")

    # =========================
    # 2) Camera tab
    # =========================
    with tabs[1]:
        col1, col2, col3 = st.columns([1, 4, 1])
        with col2:
            if BACK_CAM_AVAILABLE:
                a, b = st.columns([1, 3])
                with a:
                    if st.button("🗑️ Clear / Retake", key="btn_clear_rear_cam", use_container_width=True):
                        st.session_state.rear_cam_nonce += 1
                        st.rerun()
                with b:
                    st.caption("📌 Tap the video area to capture")

                cam_key = f"rear_cam_{st.session_state.rear_cam_nonce}"
                cam = back_camera_input(key=cam_key, height=450, width=500)

                if cam is not None:
                    image_bytes = cam.getvalue()
                    mimetype = "image/png"
                    original_name = "rear_camera.png"

                    img, w, h = try_get_image_size(image_bytes)
                    if img is not None:
                        st.image(img, use_container_width=True)
                        c1, c2 = st.columns(2)
                        c1.metric("Width", f"{w} px")
                        c2.metric("Height", f"{h} px")
                    else:
                        st.warning("Preview/size may not be available. Save/upload is still possible.")

                    height_label, height_tag = height_picker_ui("cam")
                    meta = optional_meta_ui("cam")

                    if st.button(f"✅ Save this shot ({height_label})", key="btn_save_cam", use_container_width=True):
                        save_shot_for_height(height_tag, image_bytes, mimetype, original_name, tz_name, meta=meta)
                        st.success(f"Saved for {height_label}.")
            else:
                st.caption("Fallback camera (rear camera cannot be forced on some iPad browsers).")
                cam_file = st.camera_input("📸 (Click to Capture)")
                if cam_file is not None:
                    image_bytes = cam_file.getvalue()
                    mimetype = cam_file.type or "image/jpeg"
                    original_name = cam_file.name

                    img, w, h = try_get_image_size(image_bytes)
                    if img is not None:
                        st.image(img, use_container_width=True)
                        c1, c2 = st.columns(2)
                        c1.metric("Width", f"{w} px")
                        c2.metric("Height", f"{h} px")
                    else:
                        st.warning("Preview/size may not be available for this file type. Save/upload is still possible.")

                    height_label, height_tag = height_picker_ui("cam")
                    meta = optional_meta_ui("cam")

                    if st.button(f"✅ Save this shot ({height_label})", key="btn_save_cam_fallback", use_container_width=True):
                        save_shot_for_height(height_tag, image_bytes, mimetype, original_name, tz_name, meta=meta)
                        st.success(f"Saved for {height_label}.")

    # -------------------------
    # Bottom: 3-shot status + Upload ALL 3
    # -------------------------
    st.write("---")
    st.subheader("📏 3-shot Set Status")

    def checkbox_line(label: str, tag: str) -> str:
        done = tag in st.session_state.height_captures
        box = "✅" if done else "⬜"
        line = f"- {box} **{label}**"
        if done:
            meta = st.session_state.height_captures[tag].get("meta", {}) or {}
            meta_txt = format_meta_for_status(meta)
            if meta_txt:
                line += f"  \n  <span style='color:gray; font-size:0.95rem;'>({meta_txt})</span>"
        return line

    st.markdown("\n".join([
        checkbox_line("1 m", "H1m"),
        checkbox_line("50 cm", "H50cm"),
        checkbox_line("20 cm", "H20cm"),
    ]), unsafe_allow_html=True)

    col_reset, col_tip = st.columns([1, 3])
    with col_reset:
        if st.button("Reset this 3-shot set", key="btn_reset_bottom", use_container_width=True):
            st.session_state.capture_set_ts = None
            st.session_state.capture_set_tz = None
            st.session_state.height_captures = {}
            st.success("Reset completed.")
    with col_tip:
        st.caption("This section is for camera/manual saving. Batch upload bypasses this set.")

    st.subheader("☁️ Upload ALL 3 distances to Google Drive (manual set)")

    missing = [tag for (_, tag) in HEIGHTS if tag not in st.session_state.height_captures]
    if missing:
        st.info(f"Remaining distances: {', '.join(missing)}")
    else:
        st.success("All 3 distances are ready!")

        if st.button("🚀 Upload ALL 3 images now", key="btn_upload_all3", use_container_width=True):
            with st.spinner("Uploading 3 images to Google Drive... ☁️"):
                try:
                    set_tz = st.session_state.capture_set_tz or tz_name
                    set_ts = st.session_state.capture_set_ts or now_timestamp_str(set_tz)
                    date_str = set_ts.split("_")[0]

                    _, date_folder_id, _ = ensure_zip_date_folder(zipcode, set_tz, date_str=date_str)

                    uploaded_files = []
                    for _, tag in HEIGHTS:
                        item = st.session_state.height_captures[tag]
                        meta = item.get("meta", {}) or {}

                        filename = make_filename(
                            turf_setting=turf_setting,
                            grass_type=grass_type,
                            weed_name=weed_name,
                            height_tag=tag,
                            mimetype=item["mimetype"],
                            set_timestamp=set_ts,
                            original_name=item["original_name"],
                            meta=meta,
                        )
                        upload_bytes_to_drive(item["bytes"], item["mimetype"], filename, parent_id=date_folder_id)
                        uploaded_files.append(filename)

                    st.success("✅ Done! (3 files uploaded)")
                    for f in uploaded_files:
                        st.write(f"- {f}")

                    st.session_state.capture_set_ts = None
                    st.session_state.capture_set_tz = None
                    st.session_state.height_captures = {}

                except Exception as e:
                    st.error(f"❌ Upload failed: {e}")
                    st.error(f"❌ Upload failed: {e}")
