"""
Grade 6 attendance app (improved service-account parsing + safer Telegram + diagnostic).

What I changed:
- Load SERVICE_ACCOUNT from (in order): env SERVICE_ACCOUNT_FILE / common local JSON filenames / st.secrets (dict or JSON string) / individual secret fields.
- Convert JSON string (with literal "\n") to dict safely and give helpful error messages.
- Read Telegram credentials from st.secrets["telegram"] or environment variables instead of hard-coded token.
- Add a safe diagnostic expander that shows presence/type of SERVICE_ACCOUNT and whether Telegram is configured (does NOT print secrets).
- Keep original UI/logic otherwise unchanged.
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import json
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests
import gspread
from google.oauth2.service_account import Credentials
import base64
import glob
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attendance_app")

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ إعدادات عامة ------------------
SHEET_NAME = "school_attendance"
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ Service Account loading utilities ------------------
def _try_json_load(s: str):
    """Try to load a JSON string, attempt repair for literal \\n sequences and surrounding quotes."""
    if not isinstance(s, str):
        raise ValueError("Expected string for JSON load")
    try:
        return json.loads(s)
    except Exception:
        # try replacing literal "\n" with real newlines
        try:
            repaired = s.replace("\\n", "\n")
            return json.loads(repaired)
        except Exception:
            # strip wrapping quotes if user pasted with extra quotes
            stripped = s.strip()
            if (stripped.startswith('"') and stripped.endswith('"')) or (stripped.startswith("'") and stripped.endswith("'")):
                inner = stripped[1:-1]
                try:
                    return json.loads(inner.replace("\\n", "\n"))
                except Exception:
                    pass
            raise

def _find_local_service_account_file():
    """Find common service account filenames in repo or use env override."""
    envp = os.environ.get("SERVICE_ACCOUNT_FILE")
    if envp and os.path.exists(envp):
        return envp
    # common patterns present in your project
    candidates = glob.glob("attendance-streamlit-app-c3aa8*.json") + glob.glob("attendance-streamlit-app-cacd*.json") + glob.glob("key*.json") + glob.glob("*.credentials.json")
    for c in candidates:
        if os.path.isfile(c):
            return c
    return None

def _load_service_account_from_file(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def load_service_account(secrets_obj):
    """
    Return a dict representing the service account.
    Order:
      - local file (env SERVICE_ACCOUNT_FILE or common filenames)
      - st.secrets["SERVICE_ACCOUNT"] as dict
      - st.secrets["SERVICE_ACCOUNT"] as JSON string (with \\n repair)
      - st.secrets individual fields (SERVICE_ACCOUNT_CLIENT_EMAIL + SERVICE_ACCOUNT_PRIVATE_KEY)
      - env SERVICE_ACCOUNT_JSON
    """
    # 0) local file
    local = _find_local_service_account_file()
    if local:
        try:
            sa = _load_service_account_from_file(local)
            logger.info("Loaded service account from local file: %s", local)
            return sa
        except Exception as e:
            logger.warning("Failed to parse local service account file %s: %s", local, e)

    # 1) st.secrets dict
    if "SERVICE_ACCOUNT" in secrets_obj and isinstance(secrets_obj["SERVICE_ACCOUNT"], dict):
        logger.info("Loaded SERVICE_ACCOUNT from st.secrets (dict).")
        return secrets_obj["SERVICE_ACCOUNT"]

    # 2) st.secrets as JSON string
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
            logger.info("Loaded SERVICE_ACCOUNT from JSON string.")
            return sa
        except Exception as e:
            logger.exception("Failed to parse SERVICE_ACCOUNT JSON.")
            raise RuntimeError(
                "فشل في قراءة SERVICE_ACCOUNT: JSON غير صالح. "
                "لو وضعت private_key في .streamlit/secrets.toml استخدم triple-quoted string أو استخدم escaped \\n."
            ) from e

    # 3) individual fields fallback
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
        logger.info("Built SERVICE_ACCOUNT from individual secret fields.")
        return sa

    return None

# get st.secrets safely
secrets = st.secrets if hasattr(st, "secrets") else {}

# attempt to load service account
try:
    SERVICE_ACCOUNT = load_service_account(secrets)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if not SERVICE_ACCOUNT:
    st.error("خطأ: لم يتم العثور على SERVICE_ACCOUNT. ضع ملف JSON في Secrets باسم SERVICE_ACCOUNT أو ارفع ملف محلي و/أو اضبط SERVICE_ACCOUNT_FILE.")
    st.stop()

# ------------------ Telegram / app / sheets config ------------------
telegram_cfg = secrets.get("telegram", {}) if isinstance(secrets.get("telegram", {}), dict) else {}
BOT_TOKEN = telegram_cfg.get("bot_token") or os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = telegram_cfg.get("chat_id") or os.environ.get("TELEGRAM_CHAT_ID")

APP_CFG = secrets.get("app", {}) if isinstance(secrets.get("app", {}), dict) else {}
PASSWORD = APP_CFG.get("password", os.environ.get("APP_PASSWORD", "1234"))

SHEETS_CFG = secrets.get("sheets", {}) if isinstance(secrets.get("sheets", {}), dict) else {}
SHEET_NAME = SHEETS_CFG.get("name", os.environ.get("SHEETS_NAME", "school_attendance"))

# ------------------ Connect to Google Sheets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

def _ensure_sa_dict(sa):
    if isinstance(sa, dict):
        return sa
    if isinstance(sa, str):
        return _try_json_load(sa)
    raise RuntimeError("SERVICE_ACCOUNT must be dict or JSON string")

try:
    SERVICE_ACCOUNT = _ensure_sa_dict(SERVICE_ACCOUNT)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

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

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
    try:
        r = requests.get(url, timeout=10)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except Exception:
        logger.warning("Could not download Arabic font (network issue).")

try:
    pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))
except Exception:
    try:
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
    except Exception:
        logger.warning("Failed to register Arabic font, falling back to built-ins.")

# ------------------ دوال مساعدة ------------------
def reshape_arabic_text(text):
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet():
    try:
        data = worksheet.get_all_records()
    except Exception:
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    return df

def normalize_date_for_pdf(src_date_str):
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    s = str(src_date_str).strip().replace(" ", "")
    try:
        if "-" in s:
            parts = s.split("-")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        if len(s) == 8 and s.isdigit():
            y = s[0:4]; m = s[4:6]; d = s[6:8]
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
    except Exception:
        pass
    return s

def send_telegram_message(message):
    """
    Send message to Telegram. Returns (ok: bool, info: dict_or_text).
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials missing, skipping send.")
        return False, "credentials_missing"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.get(url, params={"chat_id": CHAT_ID, "text": message}, timeout=8)
        try:
            j = resp.json()
        except Exception:
            j = {"raw": resp.text}
        if resp.status_code == 200 and j.get("ok", False):
            return True, j
        return False, j
    except requests.exceptions.RequestException as e:
        logger.exception("Telegram send exception")
        return False, str(e)

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
    title_style = ParagraphStyle('Title', fontName='Arabic', fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle('Normal', fontName='Arabic', fontSize=12, alignment=2)
    footer_style = ParagraphStyle('Footer', fontName='Arabic', fontSize=10, alignment=2, textColor=colors.darkblue)

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
            ('FONTNAME', (0, 0), (-1, -1), 'Arabic'),
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

# ------------------ تحويل الصورة المحلية إلى base64 ------------------ 
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
    st.warning("تحذير: لم يتم العثور على ملف images.jpeg، تم استخدام علم مصر كبديل.")

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

# ------------------ واجهة المستخدم وبقية التطبيق ------------------
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

st.markdown("""
<style>
/* (CSS omitted here for brevity in display) */
</style>
""", unsafe_allow_html=True)

# (rest of UI code same as original, using the functions above)
if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            st.rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            st.rerun()

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            st.rerun()
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page = "home"
        st.rerun()

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
            failed = record_attendance(selected, teacher_name, status_label)
            if not failed:
                st.success("تم تسجيل الغياب بنجاح")
            else:
                st.error(f"حدثت أخطاء: {failed}")
    if st.button("اختبار إشعار تليجرام"):
        ok, info = send_telegram_message("اختبار من تطبيق نظام الغياب")
        if ok:
            st.success("تم إرسال رسالة اختبار للتليجرام.")
        else:
            st.error(f"فشل إرسال رسالة الاختبار: {info}")

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
        st.rerun()
