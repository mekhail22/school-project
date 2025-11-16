# streamlit_app.py
"""
Grade 6 attendance app — مع إصلاح إرسال Telegram وظهور نتيجة الإرسال في الواجهة
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

# ------------------ Page config ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ App settings ------------------
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل كل الإعدادات من Streamlit Secrets"""
    try:
        secrets = st.secrets
        
        # Telegram
        BOT_TOKEN = None
        CHAT_ID = None
        
        if hasattr(secrets, 'telegram'):
            if hasattr(secrets.telegram, 'bot_token'):
                BOT_TOKEN = secrets.telegram.bot_token
            if hasattr(secrets.telegram, 'chat_id'):
                CHAT_ID = secrets.telegram.chat_id
        
        # App settings
        PASSWORD = getattr(secrets, 'PASSWORD', '1234')
        SHEET_NAME = getattr(secrets, 'SHEET_NAME', 'school_attendance')
        
        if hasattr(secrets, 'app'):
            if hasattr(secrets.app, 'password'):
                PASSWORD = secrets.app.password
            if hasattr(secrets.app, 'PASSWORD'):
                PASSWORD = secrets.app.PASSWORD
        
        # Service Account
        SERVICE_ACCOUNT = None
        if hasattr(secrets, 'SERVICE_ACCOUNT'):
            SERVICE_ACCOUNT = dict(secrets.SERVICE_ACCOUNT)
            # إصلاح مشكلة الـ private key
            if 'private_key' in SERVICE_ACCOUNT:
                private_key = SERVICE_ACCOUNT['private_key']
                # إصلاح مشكلة الـ newlines
                if "\\n" in private_key:
                    SERVICE_ACCOUNT['private_key'] = private_key.replace("\\n", "\n")
        
        return {
            'BOT_TOKEN': BOT_TOKEN,
            'CHAT_ID': CHAT_ID,
            'PASSWORD': PASSWORD,
            'SHEET_NAME': SHEET_NAME,
            'SERVICE_ACCOUNT': SERVICE_ACCOUNT
        }
        
    except Exception:
        return {
            'BOT_TOKEN': None,
            'CHAT_ID': None,
            'PASSWORD': '1234',
            'SHEET_NAME': 'school_attendance',
            'SERVICE_ACCOUNT': None
        }

# تحميل الإعدادات
secrets_config = load_secrets()

BOT_TOKEN = secrets_config['BOT_TOKEN']
CHAT_ID = secrets_config['CHAT_ID']
PASSWORD = secrets_config['PASSWORD']
SHEET_NAME = secrets_config['SHEET_NAME']
SERVICE_ACCOUNT = secrets_config['SERVICE_ACCOUNT']

# ------------------ الاتصال بـ Google Sheets ------------------
worksheet = None
if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
    try:
        # التحقق من صحة الـ private key
        private_key = SERVICE_ACCOUNT['private_key']
        if not private_key.startswith('-----BEGIN PRIVATE KEY-----'):
            st.error("❌ تنسيق private key غير صحيح")
        else:
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
            gc = gspread.authorize(creds)
            sh = gc.open(SHEET_NAME)
            worksheet = sh.sheet1
            
            # التأكد من وجود العناوين إذا كانت الورقة جديدة
            try:
                current_data = worksheet.get_all_records()
                if not current_data:
                    headers = ["student", "teacher", "status", "date"]
                    worksheet.append_row(headers)
            except Exception:
                headers = ["student", "teacher", "status", "date"]
                worksheet.append_row(headers)
                
    except Exception as e:
        worksheet = None
else:
    worksheet = None

# ------------------ Arabic font for PDF ------------------
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
        except Exception:
            pass
    try:
        if os.path.exists(FONT_PATH):
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
    except Exception:
        pass

    for candidate in ["Arial", "DejaVuSans", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            return FONT_NAME
        except Exception:
            continue

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
    if worksheet is None:
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    
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

# ------------------ Telegram functions ------------------
def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return False, {"error": "credentials_missing"}

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
    except requests.exceptions.RequestException:
        return False, {"exception": "Request failed"}

def record_attendance(selected_absent, teacher_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    failed = []
    success_count = 0
    
    # حفظ في Google Sheets إذا كان متصلاً
    if worksheet:
        try:
            # إضافة جميع الصفوف مرة واحدة
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append(("جميع الطلاب", str(ex)))
    else:
        failed.append(("جميع الطلاب", "لا يوجد اتصال بـ Google Sheets"))

    # إرسال إشعار Telegram
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}\nتم حفظ {success_count} سجل بنجاح"
    
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if BOT_TOKEN and CHAT_ID:
        ok, info = send_telegram_message(message)
        if ok:
            telegram_status = "✅ تم الإرسال بنجاح"
            telegram_details = "تم إرسال الإشعار إلى Telegram"
        else:
            telegram_status = "❌ فشل الإرسال"
            telegram_details = f"تفاصيل الخطأ: {info}"
    else:
        telegram_status = "⚠️ إعدادات Telegram غير مكتملة"
    
    return failed, telegram_status, telegram_details, success_count

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

# ------------------ Image helper ------------------
def get_image_base64(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception:
        return None

logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

# ------------------ Arabic date for header ------------------
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# ------------------ CSS + top toolbar ------------------
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
    .logo-img { 
        width: 48px; height: 48px; border-radius: 12px; 
        object-fit: contain; border: 2px solid rgba(255,255,255,0.3); 
        background: white; padding: 4px;
    }
    .school-info { line-height: 1.3; }
    .school-name { font-size: 17px; font-weight: bold; margin: 0; }
    .school-date { font-size: 12px; opacity: 0.9; margin: 0; }

    .nav-buttons { display: flex; gap: 12px; }
    .nav-btn {
        background: rgba(255, 255, 255, 0.2);
        color: white; border: none; padding: 10px 22px;
        border-radius: 12px; font-size: 15px; font-weight: 600;
        cursor: pointer; transition: all 0.3s ease;
        backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3);
    }
    .nav-btn:hover {
        background: white; color: #1e40af;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(255,255,255,0.4);
    }

    .content-padding { height: 90px; }

    .modal { display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }
    .modal-content { background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; animation: modalPop 0.3s ease; }
    @keyframes modalPop { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .close-btn { position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }
    .close-btn:hover { color: #e11d48; }
    .modal h3 { text-align: center; color: #1e40af; margin-top: 0; }
    .modal p { text-align: center; color: #475569; line-height: 1.6; }

    .searchBox {
      display: flex;
      max-width: 230px;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      background: #2f3640;
      border-radius: 50px;
      position: relative;
      margin: 20px 0;
    }

    .searchButton {
      color: white;
      position: absolute;
      right: 8px;
      width: 50px;
      height: 50px;
      border-radius: 50%;
      background: var(--gradient-2, linear-gradient(90deg, #2AF598 0%, #009EFD 100%));
      border: 0;
      display: inline-block;
      transition: all 300ms cubic-bezier(.23, 1, 0.32, 1);
      cursor: pointer;
    }
    
    .searchButton:hover {
      color: #fff;
      background-color: #1A1A1A;
      box-shadow: rgba(0, 0, 0, 0.5) 0 10px 20px;
      transform: translateY(-3px);
    }
    
    .searchButton:active {
      box-shadow: none;
      transform: translateY(0);
    }

    .searchInput {
      border: none;
      background: none;
      outline: none;
      color: white;
      font-size: 15px;
      padding: 24px 46px 24px 26px;
      width: 100%;
    }
    
    .student-search label {
        display: none !important;
    }
    
    .student-search .stTextInput > div > div > input {
        border: none;
        background: #2f3640;
        outline: none;
        color: white;
        font-size: 15px;
        padding: 24px 46px 24px 26px;
        border-radius: 50px;
        font-family: 'Cairo', sans-serif;
    }
    
    .student-search .stTextInput > div {
        max-width: 230px;
    }

    h1,h2,h3,h4,h5,h6 { color: #1e293b !important; text-align: center; font-family: 'Cairo', sans-serif !important; }
    .stButton>button {
        width: 250px; height: 60px; background: linear-gradient(to right, #2563eb, #1d4ed8);
        color: white; font-size: 20px; font-weight: bold; border-radius: 16px; border: none;
        box-shadow: 0 4px 12px rgba(37,99,235,0.3); transition: all 0.3s ease; margin: 15px auto; display: block;
    }
    .stButton>button:hover {
        background: linear-gradient(to right, #1d4ed8, #1e40af);
        transform: translateY(-2px); box-shadow: 0 6px 16px rgba(37,99,235,0.4);
    }
</style>
""", unsafe_allow_html=True)

# ------------------ Top toolbar HTML ------------------
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

# ------------------ Modals HTML + script ------------------
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

# ------------------ UI / Navigation ------------------
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        pass

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
            with st.spinner("جاري حفظ البيانات في Google Sheets..."):
                try:
                    failed, telegram_status, telegram_details, success_count = record_attendance(selected, teacher_name, status_label)
                except Exception as e:
                    st.error(f"حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                else:
                    if not failed:
                        st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب في Google Sheets")
                        
                        if "✅" in telegram_status:
                            st.success(telegram_status)
                        elif "❌" in telegram_status:
                            st.warning(telegram_status)
                        else:
                            st.info(telegram_status)
                            
                        if telegram_details:
                            with st.expander("تفاصيل إرسال Telegram"):
                                st.write(telegram_details)
                    else:
                        st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {failed}")

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
