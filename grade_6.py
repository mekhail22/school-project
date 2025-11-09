"""
Streamlit attendance app (robust secrets parsing + safer Telegram + improved error hints).
This edited version adds:
 - automatic local JSON discovery (if you have a key file in the repo),
 - a small safe diagnostic expander to check presence/type of SERVICE_ACCOUNT and Telegram config,
 - clearer, non-sensitive error hints when parsing fails.

Note: Do NOT paste private keys or tokens in public chat. If you keep a local key file, ensure it's in .gitignore.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
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

st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ Load secrets safely ------------------
secrets = st.secrets if hasattr(st, "secrets") else {}

def _try_json_load(s):
    """Try to json.loads string s, trying also with literal \n -> newline."""
    if not isinstance(s, str):
        raise ValueError("Input not a string for json loading")
    try:
        return json.loads(s)
    except Exception as e1:
        # Attempt to repair: replace literal backslash-n sequences with real newlines
        try:
            repaired = s.replace("\\n", "\n")
            return json.loads(repaired)
        except Exception:
            # Final attempt: strip surrounding quotes (in case user pasted with extra quotes)
            try:
                stripped = s.strip()
                if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
                    inner = stripped[1:-1]
                    inner_repaired = inner.replace("\\n", "\n")
                    return json.loads(inner_repaired)
            except Exception:
                pass
            # raise original error for diagnostics up the stack
            raise e1

def _load_service_account_from_file(path):
    """Load service account JSON from a local file path (returns dict)"""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        logger.info("Loaded SERVICE_ACCOUNT from local file: %s", path)
        logger.warning("Ensure this file is NOT committed to git and is listed in .gitignore.")
        return data
    except Exception as e:
        logger.exception("Failed to load service account JSON from file %s", path)
        raise

def _find_local_service_account_file():
    """Look for common service account filenames in the repo (do not print file contents)."""
    # 1) explicit env override
    envp = os.environ.get("SERVICE_ACCOUNT_FILE")
    if envp and os.path.exists(envp):
        return envp
    # 2) common filenames (matching pattern)
    candidates = glob.glob("attendance-streamlit-app-c3aa8*.json") + glob.glob("key*.json") + glob.glob("*.credentials.json")
    for c in candidates:
        if os.path.isfile(c):
            return c
    # 3) no local file found
    return None

def load_service_account_from_secrets(secrets_obj):
    """
    Tries multiple strategies to obtain a service account dict:
    0) Local file: env SERVICE_ACCOUNT_FILE or common filenames
    1) SERVICE_ACCOUNT as dict (Streamlit cloud table)
    2) SERVICE_ACCOUNT as JSON string (possibly triple-quoted or escaped)
    3) SERVICE_ACCOUNT_JSON key
    4) Environment variable SERVICE_ACCOUNT_JSON
    5) Individual keys: SERVICE_ACCOUNT_CLIENT_EMAIL and SERVICE_ACCOUNT_PRIVATE_KEY (with \\n replacement)
    Returns dict or None.
    """
    # 0) Local file first (convenient for development)
    file_path = _find_local_service_account_file()
    if file_path:
        try:
            return _load_service_account_from_file(file_path)
        except Exception:
            # if file parse fails, continue to other strategies (but log has the exception)
            pass

    # 1) dict directly from st.secrets
    if "SERVICE_ACCOUNT" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT"], dict):
        sa = secrets_obj["SERVICE_ACCOUNT"]
        logger.info("Loaded SERVICE_ACCOUNT from st.secrets as dict.")
        return sa

    # 2) SERVICE_ACCOUNT as JSON string
    raw = None
    if "SERVICE_ACCOUNT" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT"], str):
        raw = secrets_obj["SERVICE_ACCOUNT"]
    elif "SERVICE_ACCOUNT_JSON" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT_JSON"], str):
        raw = secrets_obj["SERVICE_ACCOUNT_JSON"]
    # 3) environment var fallback
    elif os.environ.get("SERVICE_ACCOUNT_JSON"):
        raw = os.environ.get("SERVICE_ACCOUNT_JSON")

    if raw:
        try:
            sa = _try_json_load(raw)
            logger.info("Loaded SERVICE_ACCOUNT from JSON string (secrets or env).")
            return sa
        except Exception as e:
            # Do not expose private_key contents; provide user hint
            logger.exception("Failed to parse SERVICE_ACCOUNT JSON from secrets/env.")
            # Raise a friendly message upward
            raise RuntimeError(
                "فشل في قراءة SERVICE_ACCOUNT: JSON غير صالح. "
                "إن وضعت private_key في ملف .streamlit/secrets.toml فتأكد من استخدام triple-quoted string (\"\"\"...\"\"\") أو تحويل `\\n` إلى newlines. "
                "مثال: private_key = \"-----BEGIN PRIVATE KEY-----\\nMIIE...\\n-----END PRIVATE KEY-----\\n\""
            ) from e

    # 4) Individual keys fallback
    client_email = secrets_obj.get("SERVICE_ACCOUNT_CLIENT_EMAIL") or secrets_obj.get("service_account_client_email")
    private_key = secrets_obj.get("SERVICE_ACCOUNT_PRIVATE_KEY") or secrets_obj.get("service_account_private_key")
    project_id = secrets_obj.get("SERVICE_ACCOUNT_PROJECT_ID") or secrets_obj.get("service_account_project_id")
    private_key_id = secrets_obj.get("SERVICE_ACCOUNT_PRIVATE_KEY_ID") or secrets_obj.get("service_account_private_key_id")
    client_id = secrets_obj.get("SERVICE_ACCOUNT_CLIENT_ID") or secrets_obj.get("service_account_client_id")
    client_x509 = secrets_obj.get("SERVICE_ACCOUNT_CLIENT_X509_URL") or secrets_obj.get("service_account_client_x509_url")

    if client_email and private_key:
        # Replace literal "\n" with real newline if needed
        if "\\n" in private_key and "\n" not in private_key:
            private_key = private_key.replace("\\n", "\n")
        sa = {
            "type": "service_account",
            "project_id": project_id or "",
            "private_key_id": private_key_id or "",
            "private_key": private_key,
            "client_email": client_email,
            "client_id": client_id or "",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_x509_cert_url": client_x509 or ""
        }
        logger.info("Built SERVICE_ACCOUNT dict from individual secret fields (client_email + private_key).")
        return sa

    # nothing found
    return None

# attempt load
try:
    SERVICE_ACCOUNT = load_service_account_from_secrets(secrets)
except RuntimeError as e:
    st.error(str(e))
    st.stop()
if not SERVICE_ACCOUNT:
    st.error(
        "خطأ: الرجاء إضافة SERVICE_ACCOUNT إلى st.secrets (كـ dict أو JSON string) أو وضع ملف JSON محلي واضبط SERVICE_ACCOUNT_FILE. "
        "أفضل طريقة: في Streamlit Cloud ضع SERVICE_ACCOUNT (paste كامل JSON) أو في .streamlit/secrets.toml استخدم triple-quoted string."
    )
    st.stop()

# Load other secrets (telegram, app, sheets)
telegram_cfg = secrets.get("telegram", {}) if isinstance(secrets.get("telegram", {}), dict) else {}
BOT_TOKEN = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")

APP_CFG = secrets.get("app", {}) if isinstance(secrets.get("app", {}), dict) else {}
PASSWORD = APP_CFG.get("password", os.environ.get("APP_PASSWORD", "1234"))

SHEETS_CFG = secrets.get("sheets", {}) if isinstance(secrets.get("sheets", {}), dict) else {}
SHEET_NAME = SHEETS_CFG.get("name", os.environ.get("SHEETS_NAME", "school_attendance"))

# Students & Teachers - you can move these to a sheet for easier management
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ Connect to Google Sheets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    logger.exception("Google API auth failed (credentials may be malformed or permission issues).")
    st.error("خطأ في تهيئة اعتماد Google API: " + str(e))
    st.stop()

try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
except Exception as e:
    logger.exception("Failed opening sheet (check name and that the service account was shared as Editor).")
    st.error("خطأ في فتح Google Sheet. تأكد من اسم المصنف ومشاركة حساب الخدمة كمحرر (Editor). \n\nتفاصيل: " + str(e))
    st.stop()

# ------------------ Ensure Arabic font for PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
FONT_NAME = "ArabicCustom"

def ensure_font():
    if not os.path.exists(FONT_PATH):
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
            logger.info("Downloaded Arabic font.")
        except Exception as e:
            logger.warning("Failed to download Arabic font: %s", e)
    try:
        if os.path.exists(FONT_PATH):
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
    except Exception as e:
        logger.warning("Failed to register font from path: %s", e)

    # Fallback attempts
    for candidate in ["Arial", "DejaVuSans", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            logger.info("Used fallback font: %s", candidate)
            return FONT_NAME
        except Exception:
            continue

    logger.error("No usable font registered.")
    return None

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

def send_telegram_message(message):
    """
    Send message to Telegram. Returns (ok: bool, info: dict_or_text).
    Logs response details for debugging but does NOT print or log tokens/keys.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials missing (BOT_TOKEN/CHAT_ID). Skipping send.")
        return False, "credentials_missing"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        resp = requests.get(url, params=params, timeout=8)
        status = resp.status_code
        # log status and body for debugging (but not sensitive fields)
        logger.info("Telegram HTTP status: %s", status)
        body_text = resp.text if resp.text else ""
        # Try parse json
        try:
            body_json = resp.json()
        except Exception:
            body_json = None

        if status == 200 and body_json and body_json.get("ok", False):
            logger.info("Telegram API returned ok.")
            return True, body_json
        else:
            logger.warning("Telegram send failed: status=%s, body=%s", status, body_text[:1000])
            # return whatever we have for troubleshooting
            return False, body_json or body_text
    except requests.exceptions.RequestException as e:
        logger.exception("Exception while sending Telegram message (network or timeout).")
        return False, str(e)

def record_attendance(selected_absent, teacher_name, absent_label):
    """
    Batch appends rows to Google Sheet. Returns list of failures (empty if none).
    """
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    failed = []
    try:
        # append_rows is faster for batches
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception:
        logger.exception("Batch append failed, falling back to per-row append.")
        for r in rows:
            try:
                worksheet.append_row(r, value_input_option="USER_ENTERED")
            except Exception as ex:
                logger.exception("append_row failed for %s", r[0])
                failed.append((r[0], str(ex)))

    # Send telegram notification (non-blocking)
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    ok, info = send_telegram_message(message)
    if not ok:
        logger.warning("Telegram notification failed: %s", info)
    else:
        logger.info("Telegram notification sent.")
    return failed

def get_student_records(student_name):
    df = read_sheet()
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    try:
        df_matches = df[df["student"].str.contains(student_name, case=False, na=False)].copy()
    except Exception:
        df_matches = df[df["student"].str.lower() == student_name.lower()].copy()
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

# ------------------ Small diagnostic UI (safe, no secrets printed) ------------------
with st.expander("حالة الإعداد (Diagnostic) — اضغط لعرض الحالة"):
    sa_present = bool(SERVICE_ACCOUNT)
    sa_type = type(SERVICE_ACCOUNT).__name__ if SERVICE_ACCOUNT else "None"
    st.write("SERVICE_ACCOUNT موجود؟", "نعم" if sa_present else "لا")
    st.write("نوع SERVICE_ACCOUNT:", sa_type)
    st.write("SHEET NAME:", SHEET_NAME)
    st.write("BOT_TOKEN configured?", "نعم" if bool(BOT_TOKEN) else "لا")
    st.write("CHAT_ID configured?", "نعم" if bool(CHAT_ID) else "لا")
    local_file = _find_local_service_account_file()
    st.write("ملف حساب خدمة محلي موجود؟", local_file if local_file else "لا")
    st.info("هذه النافذة تعرض حالات وجود الإعدادات فقط ولا تكشف أي مفاتيح.")

# ------------------ UI / CSS (kept visually similar) ------------------
logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"
    st.warning("تحذير: لم يتم العثور على ملف images.jpeg، تم استخدام علم مصر كبديل.")

today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()] if 0 <= today.weekday() < len(arabic_weekdays) else ""
month = arabic_months[today.month - 1] if 1 <= today.month <= 12 else ""
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

st.markdown("""
<style>
/* ... same CSS as before (omitted here for brevity in comment) ... */
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
#MainMenu, header, footer {visibility: hidden !important;}
.stApp { background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); font-family: 'Cairo', sans-serif; }
.top-toolbar { position: fixed; top: 0; left: 0; right: 0; height: 70px; background: linear-gradient(135deg, #1e40af, #2563eb); display: flex; justify-content: space-between; align-items: center; padding: 0 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2); z-index: 999999 !important; color: white; }
.logo-img { width: 48px; height: 48px; border-radius: 12px; object-fit: contain; border: 2px solid rgba(255,255,255,0.3); background: white; padding: 4px; }
.content-padding { height: 90px; }
.modal { display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }
.modal-content { background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; }
.close-btn { position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }
.student-search .stTextInput > div > div > input { border: none; background: #2f3640; outline: none; color: white; font-size: 15px; padding: 24px 46px 24px 26px; border-radius: 50px; font-family: 'Cairo', sans-serif; }
.stButton>button { width: 250px; height: 60px; background: linear-gradient(to right, #2563eb, #1d4ed8); color: white; font-size: 20px; font-weight: bold; border-radius: 16px; border: none; box-shadow: 0 4px 12px rgba(37,99,235,0.3); margin: 15px auto; display: block; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"""
<div class="top-toolbar">
    <div style="display:flex;align-items:center;gap:12px">
        <img src="{logo_src}" class="logo-img" alt="شعار">
        <div style="line-height:1.2">
            <div style="font-weight:bold;font-size:17px">مدرسة السلام الإعدادية الثانوية المشتركة</div>
            <div style="font-size:12px;opacity:0.9">{formatted_date}</div>
        </div>
    </div>
    <div style="display:flex;gap:12px">
        <button class="nav-btn" onclick="document.getElementById('about-modal').style.display='flex'">عنا</button>
        <button class="nav-btn" onclick="document.getElementById('contact-modal').style.display='flex'">اتصل بنا</button>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# ------------------ Pages / Navigation ------------------
def safe_rerun():
    """Try experimental_rerun then st.rerun as fallback; swallow exceptions but log."""
    try:
        # st.experimental_rerun may not exist on older streamlit versions
        if hasattr(st, "experimental_rerun"):
            st.experimental_rerun()
        else:
            st.rerun()
    except Exception as e:
        logger.exception("Rerun failed (non-fatal).")

if "page" not in st.session_state:
    st.session_state.page = "home"

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
                failed = record_attendance(selected, teacher_name, status_label)
            except Exception:
                logger.exception("Error during record_attendance")
                st.error("حدث خطأ أثناء تسجيل الغياب. راجع السجلات (logs) للتفاصيل.")
            else:
                if not failed:
                    st.success("تم تسجيل الغياب بنجاح")
                    safe_rerun()
                else:
                    st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {failed}")
    if st.button("اختبار إشعار تليجرام"):
        # small debug button - will attempt to send a test message and report result
        ok, info = send_telegram_message("اختبار من تطبيق نظام الغياب")
        if ok:
            st.success("تم إرسال رسالة اختبار للتليجرام.")
        else:
            st.error(f"فشل إرسال رسالة الاختبار: {info}")

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
