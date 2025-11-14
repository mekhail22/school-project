# streamlit_app.py
"""
Grade 6 attendance app — مع تثبيت رسالة التسجيل لمدة سنة في Google Sheet (meta) + session_state fallback.
(مهم: لا تضيف مفاتيح أو ملفات JSON في هذا الملف. استخدم st.secrets أو متغيرات البيئة.)
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import os
import json
import logging
import base64
import requests
import glob

# Arabic/RTL PDF support
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Google Sheets / Auth
import gspread
from google.oauth2.service_account import Credentials

# Optional date parser
try:
    from dateutil.parser import parse as date_parse
except Exception:
    date_parse = None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attendance_app")

# ------------------ Page config ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ App settings ------------------
SHEET_NAME = "school_attendance"
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# Name of meta worksheet used to persist last-notification
META_SHEET_TITLE = "meta_attendance"

# ------------------ Service account utilities ------------------
def _try_json_load(s: str):
    if not isinstance(s, str):
        raise ValueError("Expected string for JSON load")
    try:
        return json.loads(s)
    except Exception:
        try:
            repaired = s.replace("\\n", "\n")
            return json.loads(repaired)
        except Exception:
            stripped = s.strip()
            if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
                inner = stripped[1:-1]
                try:
                    return json.loads(inner.replace("\\n", "\n"))
                except Exception:
                    pass
            raise

def _find_local_service_account_file():
    envp = os.environ.get("SERVICE_ACCOUNT_FILE")
    if envp and os.path.exists(envp):
        return envp
    candidates = glob.glob("attendance-streamlit-app-*.json") + glob.glob("attendance-streamlit-app-cacd*.json") + glob.glob("key*.json") + glob.glob("*.credentials.json")
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def _load_service_account_from_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def load_service_account(secrets_obj):
    file_path = _find_local_service_account_file()
    if file_path:
        try:
            sa = _load_service_account_from_file(file_path)
            logger.info("Loaded SERVICE_ACCOUNT from local file (not printed).")
            return sa
        except Exception as e:
            logger.warning("Failed to parse local service account file %s: %s", file_path, e)

    if "SERVICE_ACCOUNT" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT"], dict):
        logger.info("Loaded SERVICE_ACCOUNT from st.secrets (dict).")
        return secrets_obj["SERVICE_ACCOUNT"]

    raw = None
    if "SERVICE_ACCOUNT" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT"], str):
        raw = secrets_obj["SERVICE_ACCOUNT"]
    elif "SERVICE_ACCOUNT_JSON" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT_JSON"], str):
        raw = secrets_obj["SERVICE_ACCOUNT_JSON"]
    elif os.environ.get("SERVICE_ACCOUNT_JSON"):
        raw = os.environ.get("SERVICE_ACCOUNT_JSON")

    if raw:
        try:
            sa = _try_json_load(raw)
            logger.info("Loaded SERVICE_ACCOUNT from JSON string (secrets/env).")
            return sa
        except Exception as e:
            logger.exception("Failed to parse SERVICE_ACCOUNT JSON from secrets/env.")
            raise RuntimeError(
                "فشل في قراءة SERVICE_ACCOUNT: JSON غير صالح. "
                "إن وضعت private_key في ملف .streamlit/secrets.toml فتأكد من استخدام triple-quoted string أو تحويل `\\n` إلى newlines."
            ) from e

    client_email = secrets_obj.get("SERVICE_ACCOUNT_CLIENT_EMAIL") or secrets_obj.get("service_account_client_email")
    private_key = secrets_obj.get("SERVICE_ACCOUNT_PRIVATE_KEY") or secrets_obj.get("service_account_private_key")
    if client_email and private_key:
        if "\\n" in private_key and "\n" not in private_key:
            private_key = private_key.replace("\\n", "\n")
        sa = {
            "type": "service_account",
            "project_id": secrets_obj.get("SERVICE_ACCOUNT_PROJECT_ID", ""),
            "private_key_id": secrets_obj.get("SERVICE_ACCOUNT_PRIVATE_KEY_ID", ""),
            "private_key": private_key,
            "client_email": client_email,
            "client_id": secrets_obj.get("SERVICE_ACCOUNT_CLIENT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": secrets_obj.get("SERVICE_ACCOUNT_CLIENT_X509_URL", "")
        }
        logger.info("Built SERVICE_ACCOUNT dict from individual secret fields.")
        return sa

    return None

# ---------- Load service account ----------
secrets = st.secrets if hasattr(st, "secrets") else {}

try:
    SERVICE_ACCOUNT = load_service_account(secrets)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if not SERVICE_ACCOUNT:
    st.error("خطأ: لم يتم العثور على SERVICE_ACCOUNT. ضع ملف JSON في Secrets باسم SERVICE_ACCOUNT أو اضبط SERVICE_ACCOUNT_FILE.")
    st.stop()

def _ensure_sa_dict(sa):
    if isinstance(sa, dict):
        return sa
    if isinstance(sa, str):
        return _try_json_load(sa)
    raise RuntimeError("SERVICE_ACCOUNT must be dict or JSON string")

try:
    SERVICE_ACCOUNT = _ensure_sa_dict(SERVICE_ACCOUNT)
except Exception as e:
    st.error(str(e))
    st.stop()

# ------------------ Load other secrets ------------------
telegram_cfg = secrets.get("telegram", {}) if isinstance(secrets.get("telegram", {}), dict) else {}
BOT_TOKEN = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")

APP_CFG = secrets.get("app", {}) if isinstance(secrets.get("app", {}), dict) else {}
PASSWORD = APP_CFG.get("password", os.environ.get("APP_PASSWORD", "1234"))

SHEETS_CFG = secrets.get("sheets", {}) if isinstance(secrets.get("sheets", {}), dict) else {}
SHEET_NAME = SHEETS_CFG.get("name", os.environ.get("SHEETS_NAME", SHEET_NAME))

# ------------------ Connect to Google Sheets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    logger.exception("Google API auth failed")
    st.error("خطأ في تهيئة اعتماد Google API: " + str(e))
    st.stop()

try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
except Exception as e:
    logger.exception("Failed opening sheet")
    st.error("خطأ في فتح Google Sheet. تأكد من اسم المصنف ومشاركة حساب الخدمة كمحرر (Editor). \n\nتفاصيل: " + str(e))
    st.stop()

# Helper: get or create meta worksheet (to persist last-notification)
def _get_meta_sheet(spreadsheet):
    try:
        # try open existing sheet
        for w in spreadsheet.worksheets():
            if w.title == META_SHEET_TITLE:
                return w
        # not found -> try to add
        try:
            return spreadsheet.add_worksheet(title=META_SHEET_TITLE, rows="50", cols="5")
        except Exception as e:
            logger.warning("Cannot create meta worksheet: %s", e)
            # fallback: return None
            return None
    except Exception as e:
        logger.exception("Error obtaining meta sheet")
        return None

meta_sheet = _get_meta_sheet(sh)

# ------------------ Arabic font for PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
FONT_NAME = "ArabicCustom"

def ensure_font():
    if os.path.exists(FONT_PATH):
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
        except Exception as e:
            logger.warning("Failed to register local font: %s", e)
    # try download
    try:
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
        pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
        return FONT_NAME
    except Exception as e:
        logger.warning("Could not download/register Arabic font (continuing with fallback): %s", e)
    return "Helvetica"

REGISTERED_FONT = ensure_font()

# ------------------ Helper functions ------------------
def reshape_arabic_text(text):
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet():
    try:
        data = worksheet.get_all_records()
    except Exception as e:
        logger.exception("Failed to read sheet")
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    return df

def normalize_date_for_pdf(src_date_str):
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    s = str(src_date_str).strip()
    if date_parse:
        try:
            dt = date_parse(s, dayfirst=False, yearfirst=False)
            return f"{dt.day:02d} / {dt.month:02d} / {dt.year}"
        except Exception:
            pass
    s2 = s.replace(" ", "")
    try:
        if "-" in s2:
            parts = s2.split("-")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        if "/" in s2:
            parts = s2.split("/")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        if len(s2) == 8 and s2.isdigit():
            y = s2[0:4]; m = s2[4:6]; d = s2[6:8]
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
    except Exception:
        pass
    return s

# ------------------ Telegram: improved send function (POST + detailed info) ------------------
def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials missing, skipping send.")
        return False, {"error": "credentials_missing", "bot_token_present": bool(BOT_TOKEN), "chat_id_present": bool(CHAT_ID)}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}

    try:
        resp = requests.post(url, data=payload, timeout=10)
        try:
            j = resp.json()
        except Exception:
            j = {"raw": resp.text}

        if resp.status_code == 200 and j.get("ok", False):
            return True, j
        return False, {"status_code": resp.status_code, "response": j}
    except requests.exceptions.RequestException as e:
        logger.exception("Telegram send exception")
        return False, {"exception": str(e)}

# ------------------ Meta storage helpers ------------------
def write_meta_message_on_sheet(spreadsheet, meta_ws, message_text, iso_ts):
    """Write message + iso timestamp to meta worksheet (A1,B1). Returns True/False."""
    if meta_ws is None:
        return False
    try:
        # write to A1 and B1
        meta_ws.update("A1", [[message_text]])
        meta_ws.update("B1", [[iso_ts]])
        return True
    except Exception as e:
        logger.warning("Failed to write meta on sheet: %s", e)
        return False

def read_meta_message_from_sheet(meta_ws):
    """Return (message_text, iso_ts) or (None,None)"""
    if meta_ws is None:
        return None, None
    try:
        # read A1, B1
        vals = meta_ws.get_values("A1:B1")
        if not vals or len(vals) == 0:
            return None, None
        row = vals[0]
        msg = row[0] if len(row) > 0 else None
        ts = row[1] if len(row) > 1 else None
        return msg, ts
    except Exception as e:
        logger.warning("Failed to read meta from sheet: %s", e)
        return None, None

# ------------------ record attendance (updated to write meta) ------------------
def record_attendance(selected_absent, teacher_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    failed = []
    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception:
        logger.exception("Batch append failed, falling back to per-row append.")
        for r in rows:
            try:
                worksheet.append_row(r, value_input_option="USER_ENTERED")
            except Exception as ex:
                logger.exception("append_row failed for %s", r[0])
                failed.append((r[0], str(ex)))

    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"

    ok, info = send_telegram_message(message)
    if not ok:
        logger.warning("Telegram notification failed: %s", info)
    else:
        logger.info("Telegram notification sent.")

    # write meta to sheet: message + iso timestamp
    iso_ts = datetime.utcnow().isoformat()
    meta_written = write_meta_message_on_sheet(sh, meta_sheet, message, iso_ts)

    # also store in session_state as fallback (so UI can read immediately)
    st.session_state.attendance_last = {
        "failed": failed,
        "telegram_ok": ok,
        "telegram_info": info,
        "status_label": absent_label,
        "meta_written": meta_written,
        "meta_iso_ts": iso_ts
    }

    return failed, ok, info

# ------------------ read last meta (check if within 365 days) ------------------
def get_persistent_attendance_message():
    """
    Try read from meta_sheet; if found and timestamp within 365 days, return message dict.
    Else, fallback to st.session_state.attendance_last if present.
    """
    # try sheet first
    try:
        msg, iso_ts = read_meta_message_from_sheet(meta_sheet)
        if msg and iso_ts:
            try:
                ts = datetime.fromisoformat(iso_ts)
                if datetime.utcnow() - ts <= timedelta(days=365):
                    return {
                        "message": msg,
                        "ts": ts,
                        "source": "sheet"
                    }
            except Exception:
                pass
    except Exception:
        pass

    # fallback to session_state
    last = st.session_state.get("attendance_last")
    if last:
        # build readable message (we stored message text only in meta but here construct)
        status_label = last.get("status_label", "")
        # reconstruct message if possible
        # prefer telegram_info raw if exists, else use generic success
        if not last.get("failed"):
            # success
            msg_text = f"تم تسجيل الغياب ({status_label}) بنجاح ✔️"
        else:
            msg_text = f"حدثت أخطاء عند التسجيل: {last.get('failed')}"
        return {
            "message": msg_text,
            "ts": datetime.fromisoformat(last.get("meta_iso_ts")) if last.get("meta_iso_ts") else datetime.utcnow(),
            "source": "session"
        }
    return None

# ------------------ the rest: get_student_records, generate_student_pdf, UI etc. ------------------
def get_student_records(student_name):
    df = read_sheet()
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    try:
        df_matches = df[df["student"].astype(str).str.contains(student_name, case=False, na=False)].copy()
    except Exception:
        df_matches = df[df["student"].astype(str).str.lower() == student_name.lower()].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"
    })
    return df_matches[["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    font_for_style = REGISTERED_FONT or "Helvetica"
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    footer_style = ParagraphStyle('Footer', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.darkblue)

    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), title_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), normal_style))
    elements.append(Spacer(1, 8))

    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        absent_count = int((df_records["الحالة"] == "غياب بعذر").sum() + (df_records["الحالة"] == "غياب بدون عذر").sum())
        present_count = int((df_records["الحالة"] == "حاضر").sum())
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Spacer(1, 10))

        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            data.append([
                reshape_arabic_text(row.get("المرة", "")),
                reshape_arabic_text(row.get("الطالب", "")),
                reshape_arabic_text(row.get("المعلم", "")),
                reshape_arabic_text(normalize_date_for_pdf(row.get("التاريخ", ""))),
                reshape_arabic_text(row.get("الحالة", ""))
            ])
        table = Table(data, hAlign='CENTER', colWidths=[60, 150, 120, 110, 70])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        elements.append(table)

    elements.append(Spacer(1, 14))
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date}"), footer_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def get_image_base64(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning("Failed loading image %s: %s", image_path, e)
        return None

logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

# Arabic date for header
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# CSS + toolbar (same as original) — kept as-is
st.markdown("""
<style>
/* (المحتوى كما في سؤالك الأصلي — محذوف هنا لتقليل الطول في العرض) */
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="top-toolbar">
    <div class="logo-container">
        <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
        <div class="school-info">
            <p class="school-name">مدرسة السلام الإعدادية الثانوية المشتركة</p>
            <p class="school-date">{formatted_date}</p>
        </div>
    </div>
    <div class="nav-buttons">
        <button class="nav-btn" onclick="document.getElementById('about-modal').style.display='flex'">عنا</button>
        <button class="nav-btn" onclick="document.getElementById('contact-modal').style.display='flex'">اتصل بنا</button>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# Modals HTML (kept)
st.markdown("""
<div id="about-modal" class="modal"><div class="modal-content"><span class="close-btn" onclick="document.getElementById('about-modal').style.display='none'">×</span><h3>عن المدرسة</h3><p>مدرسة السلام الإعدادية الثانوية المشتركة...</p></div></div>
<div id="contact-modal" class="modal"><div class="modal-content"><span class="close-btn" onclick="document.getElementById('contact-modal').style.display='none'">×</span><h3>اتصل بنا</h3><p>الهاتف: 02-12345678</p></div></div>
<script>
window.onclick = function(event) {
    var aboutModal = document.getElementById('about-modal');
    var contactModal = document.getElementById('contact-modal');
    if (event.target == aboutModal) { aboutModal.style.display = "none"; }
    if (event.target == contactModal) { contactModal.style.display = "none"; }
}
</script>
""", unsafe_allow_html=True)

# UI navigation helpers
def safe_rerun():
    try:
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        else:
            st.rerun()
    except Exception:
        logger.exception("Rerun failed (non-fatal).")

if "attendance_last" not in st.session_state:
    st.session_state.attendance_last = None

if "page" not in st.session_state:
    st.session_state.page = "home"

# --- Pages ---
if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            safe_rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            safe_rerun()

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            safe_rerun()
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page = "home"
        safe_rerun()

elif st.session_state.page == "teacher_attendance":
    st.header("تسجيل الغياب")
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    st.subheader(f"المعلم: {teacher_name}")
    selected = st.multiselect("اختر الغائبين", STUDENTS)
    st.markdown("**اختر نوع الغياب:**")
    col_a, col_b = st.columns(2)
    with col_a:
        excuse = st.checkbox("غياب بعذر", key="excuse")
    with col_b:
        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")
    if excuse and no_excuse:
        st.warning("اختر نوع واحد فقط.")

    # زر التسجيل
    if st.button("تسجيل"):
        if not selected:
            st.warning("يجب اختيار طالب/طلاب أولا.")
        elif excuse and no_excuse:
            st.warning("اختر نوع واحد فقط.")
        elif not (excuse or no_excuse):
            st.warning("من فضلك اختر نوع الغياب.")
        else:
            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
            try:
                failed, telegram_ok, telegram_info = record_attendance(selected, teacher_name, status_label)
            except Exception as e:
                logger.exception("Error during record_attendance")
                st.session_state.attendance_last = {
                    "failed": [("internal", str(e))],
                    "telegram_ok": False,
                    "telegram_info": {"exception": str(e)},
                    "status_label": status_label,
                    "meta_written": False,
                    "meta_iso_ts": datetime.utcnow().isoformat()
                }
            else:
                # recorded into session_state inside record_attendance
                pass
            # no safe_rerun() here; the UI will read the persistent meta if any

    # Display persistent message if within one year (sheet first, then session_state)
    persistent = get_persistent_attendance_message()
    if persistent:
        st.success(persistent["message"])
        with st.expander("تفاصيل الحالة (ثابتة حتى سنة)"):
            st.write("مصدر الرسالة:", persistent.get("source"))
            st.write("وقت التسجيل (UTC):", persistent.get("ts"))
    else:
        # no persistent success message — but if session_state.attendance_last exists show local result
        last = st.session_state.get("attendance_last")
        if last:
            if not last.get("failed"):
                st.success(f"تم تسجيل الغياب ({last.get('status_label')}) بنجاح ✔️")
            else:
                st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {last.get('failed')}")
            with st.expander("نتيجة إشعار Telegram (debug) — مؤقتة"):
                st.write("telegram_ok:", last.get("telegram_ok"))
                st.write("telegram_info:", last.get("telegram_info"))

    if st.button("رجوع"):
        st.session_state.page = "home"
        safe_rerun()

elif st.session_state.page == "student":
    st.header("تقارير الغياب")
    st.markdown('<div class="student-search">', unsafe_allow_html=True)
    search_query = st.text_input("بحث", placeholder="اكتب اسم الطالب...", key="student_search")
    st.markdown('</div>', unsafe_allow_html=True)

    if search_query and search_query.strip():
        df_student = get_student_records(search_query.strip())
        if df_student.empty:
            st.info(f"لا يوجد سجلات للطالب: {search_query}")
        else:
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            pdf_buf = generate_student_pdf(search_query, df_student)
            st.download_button(
                "تحميل PDF",
                data=pdf_buf,
                file_name=f"{search_query}_report.pdf",
                mime="application/pdf"
            )

    if st.button("رجوع"):
        if "student_search" in st.session_state:
            del st.session_state.student_search
        st.session_state.page = "home"
        safe_rerun()
