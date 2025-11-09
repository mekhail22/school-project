"""
Streamlit attendance app (complete, improved, and secure).
Place sensitive values in .streamlit/secrets.toml or Streamlit Cloud secrets.
Example secrets.toml structure (do NOT commit this file with real secrets):

# .streamlit/secrets.toml (example)
# SERVICE_ACCOUNT can be the JSON content of your service account as a TOML table:
# SERVICE_ACCOUNT = { "type" = "...", "project_id" = "...", ... }
# Or place the whole JSON string in SERVICE_ACCOUNT_JSON and parse with json.loads.

[SERVICE_ACCOUNT]
type = "service_account"
project_id = "your-project-id"
# ... include all fields from the service account JSON ...

[telegram]
bot_token = "YOUR_BOT_TOKEN"
chat_id = "YOUR_CHAT_ID"

[app]
password = "change_me"

[sheets]
name = "school_attendance"
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

# SERVICE_ACCOUNT (either a TOML table SERVICE_ACCOUNT or JSON string in SERVICE_ACCOUNT_JSON)
SERVICE_ACCOUNT_RAW = None
if "SERVICE_ACCOUNT" in secrets and isinstance(secrets["SERVICE_ACCOUNT"], dict):
    SERVICE_ACCOUNT_RAW = secrets["SERVICE_ACCOUNT"]
elif "SERVICE_ACCOUNT_JSON" in secrets:
    SERVICE_ACCOUNT_RAW = secrets["SERVICE_ACCOUNT_JSON"]
elif "SERVICE_ACCOUNT" in secrets and isinstance(secrets["SERVICE_ACCOUNT"], str):
    SERVICE_ACCOUNT_RAW = secrets["SERVICE_ACCOUNT"]

if not SERVICE_ACCOUNT_RAW:
    st.error("خطأ: الرجاء إضافة SERVICE_ACCOUNT إلى st.secrets (محتوى JSON الخاص بحساب الخدمة).")
    st.stop()

# Normalize SERVICE_ACCOUNT to dict
if isinstance(SERVICE_ACCOUNT_RAW, str):
    try:
        SERVICE_ACCOUNT = json.loads(SERVICE_ACCOUNT_RAW)
    except Exception as e:
        st.error("فشل في قراءة SERVICE_ACCOUNT من st.secrets. تأكد من أنه JSON صالح أو dict. " + str(e))
        st.stop()
else:
    SERVICE_ACCOUNT = SERVICE_ACCOUNT_RAW

telegram_cfg = secrets.get("telegram", {})
BOT_TOKEN = telegram_cfg.get("bot_token")
CHAT_ID = telegram_cfg.get("chat_id")

APP_CFG = secrets.get("app", {})
PASSWORD = APP_CFG.get("password", "1234")

SHEETS_CFG = secrets.get("sheets", {})
SHEET_NAME = SHEETS_CFG.get("name", "school_attendance")

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
    Logs response details for debugging.
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials missing, skipping send.")
        return False, "credentials_missing"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    params = {"chat_id": CHAT_ID, "text": message}
    try:
        resp = requests.get(url, params=params, timeout=8)
        logger.info("Telegram HTTP status: %s", resp.status_code)
        logger.debug("Telegram response text: %s", resp.text)
        try:
            j = resp.json()
        except Exception:
            j = {"raw": resp.text}
        if resp.status_code == 200 and j.get("ok", False):
            return True, j
        return False, j
    except requests.exceptions.RequestException as e:
        logger.exception("Exception while sending Telegram message")
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
    except Exception as e:
        logger.exception("Batch append failed, falling back to per-row append.")
        for r in rows:
            try:
                worksheet.append_row(r, value_input_option="USER_ENTERED")
            except Exception as ex:
                logger.exception("append_row failed for %s", r)
                failed.append((r[0], str(ex)))

    # Send telegram notification (non-blocking)
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    ok, info = send_telegram_message(message)
    if not ok:
        logger.warning("Telegram not sent or failed: %s", info)
    else:
        logger.info("Telegram sent successfully.")
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

st.markdown("""
<div id="about-modal" class="modal"><div class="modal-content"><span class="close-btn" onclick="document.getElementById('about-modal').style.display='none'">×</span><h3>عن المدرسة</h3><p>مدرسة السلام الإعدادية الثانوية المشتركة تُعد من أعرق المدارس الحكومية في المنطقة.</p></div></div>
<div id="contact-modal" class="modal"><div class="modal-content"><span class="close-btn" onclick="document.getElementById('contact-modal').style.display='none'">×</span><h3>اتصل بنا</h3><p>الهاتف: 02-12345678</p><p>البريد: alsalam.school@example.com</p></div></div>
<script>
window.onclick = function(event) {
    var a = document.getElementById('about-modal');
    var b = document.getElementById('contact-modal');
    if (event.target == a) { a.style.display = "none"; }
    if (event.target == b) { b.style.display = "none"; }
}
</script>
""", unsafe_allow_html=True)

# ------------------ Pages / Navigation ------------------
if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            try:
                st.experimental_rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            try:
                st.experimental_rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            try:
                st.experimental_rerun()
            except Exception:
                try:
                    st.rerun()
                except Exception:
                    pass
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page = "home"
        try:
            st.experimental_rerun()
        except Exception:
            try:
                st.rerun()
            except Exception:
                pass

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
            except Exception as e:
                logger.exception("Error during record_attendance")
                st.error("حدث خطأ أثناء تسجيل الغياب. راجع السجلات (logs) للتفاصيل.")
            else:
                if not failed:
                    st.success("تم تسجيل الغياب بنجاح")
                    # safe rerun
                    try:
                        st.experimental_rerun()
                    except AttributeError:
                        try:
                            st.rerun()
                        except Exception as e:
                            logger.exception("Rerun failed")
                            st.warning("تعذر إعادة تحميل الواجهة تلقائياً. يُرجى تحديث الصفحة يدوياً.")
                else:
                    st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {failed}")
    if st.button("رجوع"):
        st.session_state.page = "home"
        try:
            st.experimental_rerun()
        except Exception:
            try:
                st.rerun()
            except Exception:
                pass

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
        try:
            st.experimental_rerun()
        except Exception:
            try:
                st.rerun()
            except Exception:
                pass
