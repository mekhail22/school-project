# streamlit_app.py
"""
Grade 6 attendance app — الإصدار النهائي المضمون على Streamlit Cloud
"""
import streamlit as st
import pandas as pd
from datetime import datetime
import io
import json
import requests
import logging

# Arabic/RTL PDF support
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Google Sheets
import gspread
from google.oauth2.service_account import Credentials

logging.basicConfig(level=logging.INFO)

# ==================== Page Config ====================
st.set_page_config(page_title="نظام الغياب - مدرسة السلام", layout="centered")

# ==================== Session State Init ====================
for key in ["page", "show_about", "show_contact"]:
    if key not in st.session_state:
        st.session_state[key] = "home" if key == "page" else False

# ==================== Constants ====================
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ==================== Load Secrets ====================
def load_secrets():
    try:
        secrets = st.secrets
        return {
            'BOT_TOKEN': getattr(secrets.telegram, 'bot_token', None),
            'CHAT_ID': getattr(secrets.telegram, 'chat_id', None),
            'PASSWORD': getattr(secrets.app, 'password', '1234'),
            'SHEET_NAME': getattr(secrets.sheets, 'name', 'school_attendance'),
            'SERVICE_ACCOUNT': json.loads(secrets.SERVICE_ACCOUNT_JSON) if hasattr(secrets, 'SERVICE_ACCOUNT_JSON') else None
        }
    except Exception as e:
        st.error(f"خطأ في الإعدادات: {e}")
        return {'BOT_TOKEN': None, 'CHAT_ID': None, 'PASSWORD': '1234', 'SHEET_NAME': 'school_attendance', 'SERVICE_ACCOUNT': None}

secrets_config = load_secrets()
BOT_TOKEN = secrets_config['BOT_TOKEN']
CHAT_ID = secrets_config['CHAT_ID']
PASSWORD = secrets_config['PASSWORD']
SHEET_NAME = secrets_config['SHEET_NAME']
SERVICE_ACCOUNT = secrets_config['SERVICE_ACCOUNT']

# ==================== Google Sheets Connection ====================
worksheet = None
if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open(SHEET_NAME)
        worksheet = sh.sheet1
        st.success("متصل بـ Google Sheets ✅")
    except Exception as e:
        st.error(f"فشل الاتصال بـ Google Sheets: {e}")
else:
    st.warning("Service Account غير موجود")

# ==================== Arabic Font (في الذاكرة - مضمون على Cloud) ====================
@st.cache_data(show_spinner=False)
def register_arabic_font():
    font_name = "ArabicFont"
    try:
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        buffer = io.BytesIO(r.content)
        pdfmetrics.registerFont(TTFont(font_name, buffer))
        return font_name
    except:
        return "Helvetica"

ARABIC_FONT = register_arabic_font()

# ==================== Helper Functions ====================
def reshape_arabic_text(text):
    try:
        return get_display(arabic_reshaper.reshape(str(text)))
    except:
        return str(text)

def read_sheet():
    if not worksheet:
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    try:
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])

def normalize_date_for_pdf(date_str):
    if pd.isna(date_str) or not str(date_str).strip():
        return ""
    return str(date_str).strip()

def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
        return False, "Missing credentials"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(url, data={"chat_id": CHAT_ID, "text": message}, timeout=10)
        return resp.status_code == 200 and resp.json().get("ok"), resp.json()
    except:
        return False, "Request failed"

def record_attendance(selected_absent, teacher_name, absent_label):
    if not worksheet:
        return [], "❌ لا اتصال بـ Sheets", "", 0

    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = [[s, teacher_name, absent_label if s in selected_absent else "حاضر", date_display] for s in STUDENTS]
    
    success_count = 0
    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
        success_count = len(rows)
    except:
        for row in rows:
            try:
                worksheet.append_row(row, value_input_option="USER_ENTERED")
                success_count += 1
            except:
                pass

    absent_str = ", ".join(selected_absent) if selected_absent else "لا أحد"
    msg = f"تسجيل غياب {date_display}\nالمعلم: {teacher_name}\nالحالة: {absent_label}\nالغائبون: {absent_str}"
    tg_ok, _ = send_telegram_message(msg)
    tg_status = "✅ Telegram" if tg_ok else "❌ Telegram"

    return [], tg_status, "", success_count

def get_student_records(student_name):
    df = read_sheet()
    if df.empty or "student" not in df.columns:
        return pd.DataFrame()
    matches = df[df["student"].astype(str).str.contains(student_name, case=False, na=False)].copy()
    if matches.empty:
        return pd.DataFrame()
    matches = matches.reset_index(drop=True)
    matches.insert(0, "المرة", range(1, len(matches)+1))
    return matches.rename(columns={"student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"})

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=40)
    elements = []
    style_title = ParagraphStyle('Title', fontName=ARABIC_FONT, fontSize=20, alignment=1, spaceAfter=20, textColor=colors.darkblue)
    style_normal = ParagraphStyle('Normal', fontName=ARABIC_FONT, fontSize=12, alignment=1, leading=18)
    
    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), style_title))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), style_normal))
    elements.append(Spacer(1, 12))
    
    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات"), style_normal))
    else:
        absent = len(df_records[df_records["الحالة"].str.contains("غياب")])
        present = len(df_records) - absent
        elements.append(Paragraph(reshape_arabic_text(f"عدد الغياب: {absent}"), style_normal))
        elements.append(Paragraph(reshape_arabic_text(f"عدد الحضور: {present}"), style_normal))
        elements.append(Spacer(1, 20))
        
        data = [[reshape_arabic_text(h) for h in ["المرة", "المعلم", "التاريخ", "الحالة"]]]
        for _, r in df_records.iterrows():
            data.append([reshape_arabic_text(str(r[c])) for c in ["المرة", "المعلم", "التاريخ", "الحالة"]])
        
        table = Table(data, colWidths=[70, 150, 120, 120])
        table.setStyle(TableStyle([
            ('FONTNAME', (0,0), (-1,-1), ARABIC_FONT),
            ('FONTSIZE', (0,0), (-1,-1), 11),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('BACKGROUND', (0,0), (-1,0), colors.lightblue),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ]))
        elements.append(table)
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {datetime.now().strftime('%d/%m/%Y')}"), style_normal))
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ==================== CSS + Header ====================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    #MainMenu, header, footer {visibility: hidden !important;}
    .stApp {background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); font-family: 'Cairo', sans-serif;}
    .top-toolbar {position: fixed; top: 0; left: 0; right: 0; height: 70px; background: linear-gradient(135deg, #1e40af, #2563eb);
                  display: flex; justify-content: space-between; align-items: center; padding: 0 20px; box-shadow: 0 4px 20px rgba(0,0,0,0.2);
                  z-index: 999999; color: white;}
    .logo-img {width: 48px; height: 48px; border-radius: 12px; object-fit: contain; background: white; padding: 4px;}
    .nav-btn {background: rgba(255,255,255,0.2); color: white; border: none; padding: 10px 22px; border-radius: 12px;
              font-weight: 600; cursor: pointer; transition: 0.3s;}
    .nav-btn:hover {background: white; color: #1e40af;}
    .content-padding {height: 90px;}
    .modal {display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.6); justify-content: center; align-items: center;}
    .modal[style*="flex"] {display: flex !important;}
    .modal-content {background: white; padding: 30px; border-radius: 16px; width: 90%; max-width: 500px; position: relative;}
    .close-btn {position: absolute; top: 10px; left: 15px; font-size: 32px; cursor: pointer; color: #aaa;}
    .close-btn:hover {color: #e11d48;}
    h1,h2,h3,h4 {text-align: center; color: #1e293b;}
    .stButton>button {width: 250px; height: 60px; background: linear-gradient(to right, #2563eb, #1d4ed8);
                      color: white; font-size: 20px; border-radius: 16px; margin: 15px auto; display: block;}
</style>
""", unsafe_allow_html=True)

# تاريخ عربي
today = datetime.now()
arabic_days = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
formatted_date = f"{arabic_days[today.weekday()]}، {today.day} {arabic_months[today.month-1]} {today.year}"

# شعار (غير الرابط ده بتاعك)
logo_src = "https://i.imgur.com/3z3z3z3.jpeg"  # أو أي رابط مباشر للشعار

st.markdown(f"""
<div class="top-toolbar">
    <div style="display:flex; align-items:center; gap:12px;">
Avoid        <img src="{logo_src}" class="logo-img">
        <div>
            <p style="margin:0; font-size:18px; font-weight:bold;">مدرسة السلام الإعدادية الثانوية المشتركة</p>
            <p style="margin:0; font-size:13px; opacity:0.9;">{formatted_date}</p>
        </div>
    </div>
    <div>
        <button class="nav-btn" id="about-btn">عنا</button>
        <button class="nav-btn" id="contact-btn">اتصل بنا</button>
    </div>
</div>
<div class="content-padding"></div>
""", unsafe_allow_html=True)

# أزرار حقيقية مخفية لتشغيل المودال
c1, c2 = st.columns(2)
with c1:
    if st.button("عنا", key="open_about"):
        st.session_state.show_about = True
        st.rerun()
with c2:
    if st.button("اتصل بنا", key="open_contact"):
        st.session_state.show_contact = True
        st.rerun()

# عرض المودال
if st.session_state.show_about or st.session_state.show_contact:
    st.markdown(f"""
    <div class="modal" style="display:flex;">
        <div class="modal-content">
            <span class="close-btn" onclick="this.parentElement.parentElement.style.display='none'">×</span>
            {'''
            <h3>عن المدرسة</h3>
            <p>مدرسة السلام الإعدادية الثانوية المشتركة تُعد من أعرق المدارس الحكومية في المنطقة.</p>
            <p>تهدف إلى تقديم تعليم متميز يجمع بين العلم والأخلاق.</p>
            ''' if st.session_state.show_about else '''
            <h3>اتصل بنا</h3>
            <p>الهاتف: 02-12345678</p>
            <p>البريد: alsalam.school@example.com</p>
            <p>العنوان: حي السلام - القاهرة</p>
            '''}
            <button onclick="this.parentElement.parentElement.style.display='none'" 
                    style="background:#dc3545;color:white;padding:10px 20px;border:none;border-radius:8px;cursor:pointer;margin-top:20px;">
                إغلاق
            </button>
        </div>
    </div>
    """, unsafe_allow_html=True)
    if st.button("إغلاق", key="close_modal"):
        st.session_state.show_about = False
        st.session_state.show_contact = False
        st.rerun()

# ==================== Navigation ====================
if st.session_state.page == "home":
    st.title("🔵 نظام تسجيل الغياب")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("👨‍🏫 دخول المعلم", use_container_width=True):
            st.session_state.page = "teacher_login"
            st.rerun()
    with c2:
        if st.button("👨‍🎓 تقرير الطالب", use_container_width=True):
            st.session_state.page = "student"
            st.rerun()

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher = st.selectbox("اختر اسمك", TEACHERS)
    pwd = st.text_input("كلمة السر", type="password")
    if st.button("دخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher
            st.session_state.page = "teacher_attendance"
            st.rerun()
        else:
            st.error("كلمة السر خاطئة")
    if st.button("رجوع"): 
        st.session_state.page = "home"
        st.rerun()

elif st.session_state.page == "teacher_attendance":
    st.header("تسجيل الغياب اليومي")
    st.write(f"**المعلم:** {st.session_state.teacher_name}")
    absent = st.multiselect("اختر الطلاب الغائبين", STUDENTS)
    col1, col2 = st.columns(2)
    with col1:
        excuse = st.checkbox("غياب بعذر")
    with col2:
        no_excuse = st.checkbox("غياب بدون عذر")
    
    if st.button("تسجيل الغياب"):
        if not absent:
            st.warning("اختر طالب واحد على الأقل")
        elif excuse and no_excuse:
            st.warning("اختر نوع واحد فقط")
        elif not (excuse or no_excuse):
            st.warning("حدد نوع الغياب")
        else:
            label = "غياب بعذر" if excuse else "غياب بدون عذر"
            failed, tg, _, count = record_attendance(absent, st.session_state.teacher_name, label)
            if count > 0:
                st.success(f"تم تسجيل {count} سجل بنجاح! {tg}")
            else:
                st.error("فشل التسجيل")
    if st.button("تسجيل خروج"):
        st.session_state.page = "home"
        st.rerun()

elif st.session_state.page == "student":
    st.header("تقرير غياب الطالب")
    query = st.text_input("اكتب اسم الطالب", placeholder="مثال: ميخائيل")
    if query:
        df = get_student_records(query)
        if df.empty:
            st.info("لا توجد سجلات لهذا الطالب")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)
            pdf = generate_student_pdf(query, df[["المرة", "المعلم", "التاريخ", "الحالة"]])
            st.download_button("تحميل التقرير PDF", pdf, f"{query}_غياب.pdf", "application/pdf")
    if st.button("رجوع"):
        st.session_state.page = "home"
        st.rerun()
