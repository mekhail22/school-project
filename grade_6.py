# Streamlit attendance app - improved & secured version
# - Moves secrets to st.secrets
# - Uses batch writes to Google Sheets
# - Better error handling & logging
# - Safer font loading with fallbacks
# - Optional dateutil parsing for dates
# - No hardcoded tokens/passwords

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import json
import logging
import base64
import requests

# Arabic PDF support
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

# Optional: date parsing (non-critical)
try:
    from dateutil.parser import parse as date_parse
except Exception:
    date_parse = None

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attendance_app")

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ جلب الإعدادات من st.secrets ------------------
# تهيئة آمنة للقيم الحساسة — ضع هذه القيم داخل .streamlit/secrets.toml أو في واجهة Streamlit Cloud secrets
# مثال secrets.toml:
# SERVICE_ACCOUNT = { "type" = "...", ... }    # أو SERVICE_ACCOUNT = '''{ ... }'''
# telegram = { bot_token = "XXX", chat_id = "YYY" }
# sheets = { name = "school_attendance" }
# app = { password = "1234" }

secrets = st.secrets if hasattr(st, "secrets") else {}

# Service account
SERVICE_ACCOUNT_RAW = secrets.get("SERVICE_ACCOUNT") or secrets.get("google_service_account")
if not SERVICE_ACCOUNT_RAW:
    st.error("خطأ: الرجاء إضافة SERVICE_ACCOUNT إلى st.secrets (محتوى JSON الخاص بحساب الخدمة).")
    st.stop()

# SERVICE_ACCOUNT may be JSON/dict or string; normalize to dict
if isinstance(SERVICE_ACCOUNT_RAW, str):
    try:
        SERVICE_ACCOUNT = json.loads(SERVICE_ACCOUNT_RAW)
    except Exception as e:
        st.error("فشل في قراءة SERVICE_ACCOUNT من st.secrets. تأكد من أنه JSON صالح أو dict. " + str(e))
        st.stop()
else:
    SERVICE_ACCOUNT = SERVICE_ACCOUNT_RAW

# Telegram
telegram_cfg = secrets.get("telegram", {})
BOT_TOKEN = telegram_cfg.get("bot_token")
CHAT_ID = telegram_cfg.get("chat_id")
if not BOT_TOKEN or not CHAT_ID:
    logger.warning("معلومات Telegram غير كاملة في st.secrets.telegram — وظيفة الإشعارات ستكون معطلة.")

# App config
APP_CFG = secrets.get("app", {})
PASSWORD = APP_CFG.get("password", "1234")
SHEETS_CFG = secrets.get("sheets", {})
SHEET_NAME = SHEETS_CFG.get("name", "school_attendance")

# Students & Teachers (consider moving to a sheet or a config file for production)
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ الاتصال بـ Google Sheets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    st.error("خطأ في تهيئة اعتماد Google API: " + str(e))
    logger.exception("Google API auth failed")
    st.stop()

try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
except Exception as e:
    # حاول فتح الصفحة بالاسم الافتراضي Sheet1 أو إنشاء شيت جديد إن أمكن
    logger.exception("Failed opening sheet")
    try:
        sh = gc.open(SHEET_NAME)
        worksheet = sh.sheet1
    except Exception:
        st.error("خطأ في فتح Google Sheet. تأكد من اسم المصنف ومشاركة حساب الخدمة كمحرر (Editor). \n\nتفاصيل: " + str(e))
        st.stop()

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
FONT_NAME = "ArabicCustom"
def ensure_font():
    # تنزيل الخط إذا لم يكن موجودا
    if not os.path.exists(FONT_PATH):
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
        try:
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
            logger.info("تم تنزيل الخط العربي بنجاح.")
        except Exception as e:
            logger.warning("فشل تنزيل الخط العربي: %s", e)

    # تسجيل الخط أو fallback
    try:
        if os.path.exists(FONT_PATH):
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
    except Exception as e:
        logger.warning("فشل تسجيل خط من PATH: %s", e)

    # Try common system fonts as fallback
    for candidate in ["Arial", "DejaVuSans", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            logger.info("استخدمت خطاً احتياطياً: %s", candidate)
            return FONT_NAME
        except Exception:
            continue

    # If all fails, return None and report
    logger.error("لم يتم تسجيل أي خط عربي صالح — قد يظهر PDF بدون دعم RTL تماماً.")
    return None

REGISTERED_FONT = ensure_font()

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
    except Exception as e:
        logger.exception("Failed to read sheet: %s", e)
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
    # try dateutil if available
    if date_parse:
        try:
            dt = date_parse(s, dayfirst=False, yearfirst=False)
            return f"{dt.day:02d} / {dt.month:02d} / {dt.year}"
        except Exception:
            pass
    # fallback parsing (original logic)
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
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials not configured, skipping send.")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.get(url, params={"chat_id": CHAT_ID, "text": message}, timeout=6)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.exception("Failed to send telegram message: %s", e)
        return False

def record_attendance(selected_absent, teacher_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    # Batch write (faster)
    failed = []
    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception as e:
        # إذا فشل الكتابة الدُفعيّة، حاول كتابة كل صف على حدة كحل احتياطي وجمع الأخطاء
        logger.exception("Batch append failed, falling back to per-row append.")
        for r in rows:
            try:
                worksheet.append_row(r, value_input_option="USER_ENTERED")
            except Exception as ex:
                failed.append((r[0], str(ex)))
    # إرسال إشعار تليجرام (اختياري)
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    send_telegram_message(message)
    return failed

def get_student_records(student_name):
    df = read_sheet()
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    # Use case-insensitive contains; for Arabic it should still work but exact matches are better
    try:
        df_matches = df[df["student"].str.contains(student_name, case=False, na=False)].copy()
    except Exception:
        # if contains fails (weird characters), fallback to equality
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
        # count absent types robustly
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

# ------------------ واجهة المستخدم (Streamlit) ------------------
logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"
    st.warning("تحذير: لم يتم العثور على ملف images.jpeg، تم استخدام علم مصر كبديل.")

# تاريخ اليوم
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()] if 0 <= today.weekday() < len(arabic_weekdays) else ""
month = arabic_months[today.month - 1] if 1 <= today.month <= 12 else ""
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# CSS + top bar (unchanged visually)
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    #MainMenu, header, footer {visibility: hidden !important;}
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
    }
    .top-toolbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 70px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 999999 !important;
        font-family: 'Cairo', sans-serif;
        color: white;
    }
    .logo-container { display: flex; align-items: center; gap: 12px; }
    .logo-img { width: 48px; height: 48px; border-radius: 12px; object-fit: contain; border: 2px solid rgba(255,255,255,0.3); background: white; padding: 4px; }
    .school-info { line-height: 1.3; }
    .school-name { font-size: 17px; font-weight: bold; margin: 0; }
    .school-date { font-size: 12px; opacity: 0.9; margin: 0; }
    .nav-buttons { display: flex; gap: 12px; }
    .nav-btn { background: rgba(255, 255, 255, 0.2); color: white; border: none; padding: 10px 22px; border-radius: 12px; font-size: 15px; font-weight: 600; cursor: pointer; transition: all 0.3s ease; backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3); }
    .nav-btn:hover { background: white; color: #1e40af; transform: translateY(-3px); box-shadow: 0 8px 20px rgba(255,255,255,0.4); }
    .content-padding { height: 90px; }
    .modal { display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }
    .modal-content { background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; animation: modalPop 0.3s ease; }
    @keyframes modalPop { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .close-btn { position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }
    .close-btn:hover { color: #e11d48; }
    .modal h3 { text-align: center; color: #1e40af; margin-top: 0; }
    .modal p { text-align: center; color: #475569; line-height: 1.6; }
    .searchBox { display: flex; max-width: 230px; align-items: center; justify-content: space-between; gap: 8px; background: #2f3640; border-radius: 50px; position: relative; margin: 20px 0; }
    .searchButton { color: white; position: absolute; right: 8px; width: 50px; height: 50px; border-radius: 50%; background: var(--gradient-2, linear-gradient(90deg, #2AF598 0%, #009EFD 100%)); border: 0; display: inline-block; transition: all 300ms cubic-bezier(.23, 1, 0.32, 1); cursor: pointer; }
    .searchButton:hover { color: #fff; background-color: #1A1A1A; box-shadow: rgba(0, 0, 0, 0.5) 0 10px 20px; transform: translateY(-3px); }
    .searchButton:active { box-shadow: none; transform: translateY(0); }
    .searchInput { border: none; background: none; outline: none; color: white; font-size: 15px; padding: 24px 46px 24px 26px; width: 100%; }
    .student-search label { display: none !important; }
    .student-search .stTextInput > div > div > input { border: none; background: #2f3640; outline: none; color: white; font-size: 15px; padding: 24px 46px 24px 26px; border-radius: 50px; font-family: 'Cairo', sans-serif; }
    .student-search .stTextInput > div > div > input::placeholder { color: #bdc3c7; }
    .student-search .stTextInput > div { max-width: 230px; }
    h1,h2,h3,h4,h5,h6 { color: #1e293b !important; text-align: center; font-family: 'Cairo', sans-serif !important; }
    .stButton>button { width: 250px; height: 60px; background: linear-gradient(to right, #2563eb, #1d4ed8); color: white; font-size: 20px; font-weight: bold; border-radius: 16px; border: none; box-shadow: 0 4px 12px rgba(37,99,235,0.3); transition: all 0.3s ease; margin: 15px auto; display: block; }
    .stButton>button:hover { background: linear-gradient(to right, #1d4ed8, #1e40af); transform: translateY(-2px); box-shadow: 0 6px 16px rgba(37,99,235,0.4); }
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

st.markdown("""
<div id="about-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="document.getElementById('about-modal').style.display='none'">×</span>
        <h3>عن المدرسة</h3>
        <p>مدرسة السلام الإعدادية الثانوية المشتركة تُعد من أعرق المدارس الحكومية في المنطقة.</p>
        <p>تهدف إلى تقديم تعليم متميز يجمع بين العلم والأخلاق.</p>
    </div>
</div>

<div id="contact-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="document.getElementById('contact-modal').style.display='none'">×</span>
        <h3>اتصل بنا</h3>
        <p>الهاتف: 02-12345678</p>
        <p>البريد: alsalam.school@example.com</p>
        <p>العنوان: حي السلام - القاهرة</p>
    </div>
</div>

<script>
window.onclick = function(event) {
    var aboutModal = document.getElementById('about-modal');
    var contactModal = document.getElementById('contact-modal');
    if (event.target == aboutModal) {
        aboutModal.style.display = "none";
    }
    if (event.target == contactModal) {
        contactModal.style.display = "none";
    }
}
</script>
""", unsafe_allow_html=True)

# ------------------ صفحات التطبيق ------------------
if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            st.experimental_rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            st.experimental_rerun()

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            st.experimental_rerun()
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page = "home"
        st.experimental_rerun()

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
                st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {failed}")
    if st.button("رجوع"):
        st.session_state.page = "home"
        st.experimental_rerun()

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
        st.experimental_rerun()
