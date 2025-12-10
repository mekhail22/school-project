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
st.set_page_config(page_title="نظام الغياب", layout="wide")

# ------------------ App settings ------------------
# قائمة الطلاب
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]

# قائمة المعلمين
TEACHERS = ["مينا سمير", "فادي حبيب"]

# مستخدمون وكلمات مرورهم
USERS = {
    # معلمون - لهم صلاحية تسجيل الغياب
    "مينا سمير": {
        "password": "teacher123",
        "role": "teacher",
        "teacher_name": "مينا سمير"
    },
    "فادي حبيب": {
        "password": "teacher123",
        "role": "teacher",
        "teacher_name": "فادي حبيب"
    },
    
    # طلاب - لهم صلاحية عرض تقاريرهم فقط
    "ميخائيل صابر فوزي": {
        "password": "student123",
        "role": "student",
        "student_name": "ميخائيل صابر فوزي"
    },
    "مينا ريمون خيري": {
        "password": "student123",
        "role": "student",
        "student_name": "مينا ريمون خيري"
    },
    "توني هاني نصرالله": {
        "password": "student123",
        "role": "student",
        "student_name": "توني هاني نصرالله"
    },
    "يوسف شادي كمال": {
        "password": "student123",
        "role": "student",
        "student_name": "يوسف شادي كمال"
    },
    "ادم مايكل فوزي": {
        "password": "student123",
        "role": "student",
        "student_name": "ادم مايكل فوزي"
    },
    "مارك نادر فؤاد": {
        "password": "student123",
        "role": "student",
        "student_name": "مارك نادر فؤاد"
    },
    "بيشوي عاطف فايز": {
        "password": "student123",
        "role": "student",
        "student_name": "بيشوي عاطف فايز"
    },
    "جورج مينا نجيب": {
        "password": "student123",
        "role": "student",
        "student_name": "جورج مينا نجيب"
    },
    "كيرلس فادي صادق": {
        "password": "student123",
        "role": "student",
        "student_name": "كيرلس فادي صادق"
    },
    "يوستينا مجدي فادي": {
        "password": "student123",
        "role": "student",
        "student_name": "يوستينا مجدي فادي"
    }
}

# ------------------ تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل الإعدادات من Streamlit Secrets"""
    try:
        secrets = st.secrets
        
        # Telegram
        BOT_TOKEN = getattr(secrets.telegram, 'bot_token', None)
        CHAT_ID = getattr(secrets.telegram, 'chat_id', None)
        
        # App settings
        SHEET_NAME = getattr(secrets.sheets, 'name', 'school_attendance')
        
        # Service Account - محاولة قراءة SERVICE_ACCOUNT_JSON أولاً
        SERVICE_ACCOUNT = None
        
        # الطريقة 1: SERVICE_ACCOUNT_JSON
        if hasattr(secrets, 'SERVICE_ACCOUNT_JSON'):
            try:
                SERVICE_ACCOUNT = json.loads(secrets.SERVICE_ACCOUNT_JSON)
            except Exception as e:
                st.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
        # الطريقة 2: SERVICE_ACCOUNT كقسم (للتوافق مع الإصدارات القديمة)
        if not SERVICE_ACCOUNT and hasattr(secrets, 'SERVICE_ACCOUNT'):
            try:
                SERVICE_ACCOUNT = {
                    'type': getattr(secrets.SERVICE_ACCOUNT, 'type', ''),
                    'project_id': getattr(secrets.SERVICE_ACCOUNT, 'project_id', ''),
                    'private_key_id': getattr(secrets.SERVICE_ACCOUNT, 'private_key_id', ''),
                    'private_key': getattr(secrets.SERVICE_ACCOUNT, 'private_key', ''),
                    'client_email': getattr(secrets.SERVICE_ACCOUNT, 'client_email', ''),
                    'client_id': getattr(secrets.SERVICE_ACCOUNT, 'client_id', ''),
                    'auth_uri': getattr(secrets.SERVICE_ACCOUNT, 'auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                    'token_uri': getattr(secrets.SERVICE_ACCOUNT, 'token_uri', 'https://oauth2.googleapis.com/token'),
                    'auth_provider_x509_cert_url': getattr(secrets.SERVICE_ACCOUNT, 'auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
                    'client_x509_cert_url': getattr(secrets.SERVICE_ACCOUNT, 'client_x509_cert_url', '')
                }
            except Exception as e:
                st.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT: {e}")
        
        return {
            'BOT_TOKEN': BOT_TOKEN,
            'CHAT_ID': CHAT_ID,
            'SHEET_NAME': SHEET_NAME,
            'SERVICE_ACCOUNT': SERVICE_ACCOUNT
        }
        
    except Exception as e:
        st.error(f"❌ خطأ في تحميل الإعدادات: {str(e)}")
        return {
            'BOT_TOKEN': None,
            'CHAT_ID': None,
            'SHEET_NAME': 'school_attendance',
            'SERVICE_ACCOUNT': None
        }

# تحميل الإعدادات
secrets_config = load_secrets()

BOT_TOKEN = secrets_config['BOT_TOKEN']
CHAT_ID = secrets_config['CHAT_ID']
SHEET_NAME = secrets_config['SHEET_NAME']
SERVICE_ACCOUNT = secrets_config['SERVICE_ACCOUNT']

# ------------------ الاتصال بـ Google Sheets ------------------
worksheet = None
connection_status = "غير متصل"
connection_details = ""

# محاولة الاتصال بـ Google Sheets
if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        
        # استخدام JSON مباشرة
        creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
        gc = gspread.authorize(creds)
        
        # محاولة فتح الـ Sheet
        try:
            sh = gc.open(SHEET_NAME)
            worksheet = sh.sheet1
            
            # اختبار الاتصال
            try:
                current_data = worksheet.get_all_records()
                connection_status = "✅ متصل بـ Google Sheets"
                connection_details = f"تم تحميل {len(current_data)} سجل"
                
                # إذا كانت الورقة جديدة، أضف العناوين
                if not current_data:
                    headers = ["student", "teacher", "status", "date"]
                    worksheet.append_row(headers)
                    connection_details += " - تم إنشاء جدول جديد"
                
            except Exception as e:
                connection_status = f"✅ متصل ولكن خطأ في القراءة: {str(e)}"
                
        except gspread.exceptions.SpreadsheetNotFound:
            connection_status = f"❌ لم يتم العثور على Google Sheet باسم: {SHEET_NAME}"
        except Exception as e:
            connection_status = f"❌ خطأ في فتح الـ Sheet: {str(e)}"
            
    except Exception as e:
        connection_status = f"❌ فشل في المصادقة: {str(e)}"
else:
    connection_status = "❌ SERVICE_ACCOUNT غير موجود أو private_key مفقود"

# إخفاء رسائل الاتصال بالكامل
if "disable_connection_alerts" not in st.session_state:
    st.session_state.disable_connection_alerts = True

# ------------------ باقي الكود ------------------
# Arabic font for PDF
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

# Helper functions
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

# Telegram functions
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

# Image helper
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

# Arabic date for header
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# CSS مع برجر منيو محسن
# === التغيير الأساسي هنا: لم أعد أخفي عنصر header حتى يظهر الشريط فوق مرة تانية ===
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    /* إزالة إخفاء الهيدر: عرض الشريط العلوي للستريملت سيعود */
    #MainMenu, footer {visibility: hidden !important;}
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
        color: #1e293b;
    }
    /* برجر منيو - حل أبسط */
    .burger-container {
        position: fixed;
        top: 20px;
        right: 20px;
        z-index: 1000001;
    }
    .burger-btn {
        display: flex;
        flex-direction: column;
        gap: 5px;
        cursor: pointer;
        padding: 12px;
        background: rgba(37, 99, 235, 0.9);
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        transition: all 0.3s ease;
        border: none;
        width: 50px;
        height: 50px;
        justify-content: center;
        align-items: center;
    }
    .burger-btn:hover {
        background: rgba(37, 99, 235, 1);
        transform: scale(1.05);
    }
    .burger-line {
        width: 25px;
        height: 3px;
        background: white;
        border-radius: 2px;
        transition: all 0.3s ease;
    }
    .burger-btn.active .burger-line:nth-child(1) {
        transform: rotate(45deg) translate(5px, 5px);
    }
    .burger-btn.active .burger-line:nth-child(2) {
        opacity: 0;
    }
    .burger-btn.active .burger-line:nth-child(3) {
        transform: rotate(-45deg) translate(7px, -6px);
    }
    /* قائمة التنقل مبسطة */
    .nav-sidebar {
        position: fixed;
        top: 0;
        right: 0;
        width: 0;
        height: 100vh;
        background: white;
        box-shadow: -5px 0 25px rgba(0,0,0,0.15);
        z-index: 1000000;
        transition: width 0.3s ease;
        overflow: hidden;
        padding-top: 80px;
    }
    .nav-sidebar.open {
        width: 280px;
    }
    .nav-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0,0,0,0.5);
        z-index: 999999;
        display: none;
        backdrop-filter: blur(3px);
    }
    .nav-overlay.open {
        display: block;
    }
    .nav-item {
        padding: 15px 20px;
        color: #1e293b;
        text-decoration: none;
        display: flex;
        align-items: center;
        gap: 15px;
        font-size: 16px;
        font-weight: 600;
        border-bottom: 1px solid #f1f5f9;
        transition: all 0.3s ease;
        cursor: pointer;
        width: 100%;
        background: none;
        border: none;
        text-align: right;
        font-family: 'Cairo', sans-serif;
    }
    .nav-item:hover {
        background: #f0f9ff;
        color: #1e40af;
    }
    .nav-item i {
        font-size: 20px;
        width: 30px;
        text-align: center;
    }
    .nav-header {
        padding: 20px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        text-align: center;
        border-bottom: 3px solid rgba(255,255,255,0.2);
        position: absolute;
        top: 0;
        width: 100%;
    }
    .nav-header h3 {
        margin: 0;
        font-size: 18px;
        font-weight: 700;
    }
    .user-info-nav {
        padding: 15px 20px;
        background: #f8fafc;
        border-bottom: 1px solid #e2e8f0;
        text-align: center;
        margin-top: 60px;
    }
    .user-name {
        font-size: 16px;
        font-weight: 700;
        color: #1e40af;
        margin-bottom: 5px;
    }
    .user-role {
        font-size: 12px;
        color: #64748b;
        background: #e2e8f0;
        padding: 3px 10px;
        border-radius: 20px;
        display: inline-block;
    }
    .content-padding { 
        height: 20px; 
        margin-top: 20px;
    }
    /* صفحة تسجيل الدخول */
    .login-container {
        max-width: 500px;
        margin: 60px auto;
        padding: 40px;
        background: white;
        border-radius: 20px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        text-align: center;
    }
    .login-title {
        color: #1e40af;
        font-size: 32px;
        margin-bottom: 30px;
        font-weight: 700;
    }
    .input-label {
        display: block;
        text-align: right;
        margin: 15px 0 8px 0;
        color: #1e293b;
        font-weight: 600;
        font-size: 16px;
    }
    .login-input {
        width: 100%;
        padding: 18px;
        margin: 5px 0 15px 0;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        font-size: 18px;
        font-family: 'Cairo', sans-serif;
        text-align: right;
        transition: all 0.3s ease;
        background: white;
        color: #1e293b;
    }
    .login-input:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
    }
    .login-input::placeholder {
        color: #64748b !important;
        font-size: 16px !important;
        opacity: 0.9 !important;
    }
    .login-button {
        width: 100%;
        padding: 18px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        border: none;
        border-radius: 12px;
        font-size: 20px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        margin-top: 25px;
        font-family: 'Cairo', sans-serif;
    }
    .login-button:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(37, 99, 235, 0.4);
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
    }
    /* إخفاء البرجر منيو في صفحة تسجيل الدخول */
    .login-screen .burger-container {
        display: none !important;
    }
    /* بقية الأنماط تبقى كما هي */
    .home-page {
        max-width: 800px;
        margin: 40px auto 20px auto;
        padding: 20px;
    }
    .home-title {
        font-size: 36px;
        margin-bottom: 30px;
        color: #1e40af !important;
        text-align: center;
        font-weight: 700;
    }
    .welcome-message {
        text-align: center;
        padding: 20px;
        margin: 10px 0 30px 0;
        background: linear-gradient(135deg, #f0f9ff, #e2e8f0);
        border-radius: 15px;
        border: 3px solid #bae6fd;
    }
    .welcome-text {
        font-size: 22px;
        color: #0369a1;
        font-weight: 700;
    }
    .user-info {
        font-size: 16px;
        color: #475569;
        margin-top: 8px;
    }
    .teacher-page, .student-page {
        max-width: 900px;
        margin: 40px auto 20px auto;
        padding: 20px;
    }
    .page-title {
        font-size: 32px;
        margin-bottom: 25px;
        color: #1e40af !important;
        text-align: center;
        font-weight: 700;
    }
    .stButton > button {
        width: 100% !important;
        height: auto !important;
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        border: 2px solid rgba(59, 130, 246, 0.2) !important;
        box-shadow: 0 5px 15px rgba(37,99,235,0.2) !important;
        transition: all 0.3s ease !important;
        margin: 15px 0 !important;
        padding: 16px !important;
        display: block !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 25px rgba(37,99,235,0.3) !important;
        border-color: #3b82f6 !important;
    }
</style>
""", unsafe_allow_html=True)

# إضافة HTML للبرجر منيو (طريقة مباشرة)
st.markdown("""
<div class="burger-container">
    <button class="burger-btn" id="burgerBtn">
        <div class="burger-line"></div>
        <div class="burger-line"></div>
        <div class="burger-line"></div>
    </button>
</div>

<div class="nav-overlay" id="navOverlay"></div>

<div class="nav-sidebar" id="navSidebar">
    <div class="nav-header">
        <h3>🌙 قائمة التنقل</h3>
    </div>
    <div id="userNavInfo" class="user-info-nav">
        <div class="user-name" id="navUserName">...</div>
        <div class="user-role" id="navUserRole">...</div>
    </div>
    <div id="navItems"></div>
</div>

<script>
(function(){
    // نستخدم IIFE لتجنب مشاكل النطاق مع Streamlit
    let menuOpen = false;
    const sidebar = document.getElementById('navSidebar');
    const overlay = document.getElementById('navOverlay');
    const burgerBtn = document.getElementById('burgerBtn');

    function toggleMenu() {
        menuOpen = !menuOpen;
        if (menuOpen) {
            sidebar.classList.add('open');
            overlay.classList.add('open');
            burgerBtn.classList.add('active');
        } else {
            sidebar.classList.remove('open');
            overlay.classList.remove('open');
            burgerBtn.classList.remove('active');
        }
    }

    // Attach events safely
    burgerBtn.addEventListener('click', toggleMenu);
    overlay.addEventListener('click', toggleMenu);

    // Functions to be called from Python via injected script
    window.updateNavInfo = function(userName, userRole) {
        document.getElementById('navUserName').textContent = userName || '...';
        document.getElementById('navUserRole').textContent = userRole === 'teacher' ? 'معلم' : 'طالب';
        updateNavItems(userRole);
    }

    function updateNavItems(userRole) {
        const navItems = document.getElementById('navItems');
        navItems.innerHTML = '';
        addNavItem('🏠', 'الصفحة الرئيسية', 'home');
        if (userRole === 'teacher') {
            addNavItem('📝', 'تسجيل الغياب', 'teacher_attendance');
        } else if (userRole === 'student') {
            addNavItem('📊', 'تقريري', 'student_dashboard');
        }
        addNavItem('🚪', 'تسجيل الخروج', 'logout');
    }

    function addNavItem(icon, text, page) {
        const navItems = document.getElementById('navItems');
        const button = document.createElement('button');
        button.className = 'nav-item';
        button.innerHTML = `<i>${icon}</i><span>${text}</span>`;
        button.addEventListener('click', function() {
            if (page === 'logout') {
                window.location.href = window.location.pathname + '?action=logout';
            } else {
                window.location.href = window.location.pathname + '?page=' + page;
            }
            toggleMenu();
        });
        navItems.appendChild(button);
    }

    // Close on ESC
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && menuOpen) {
            toggleMenu();
        }
    });
})();
</script>
""", unsafe_allow_html=True)

# UI / Navigation
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        pass

# إدارة حالة تسجيل الدخول
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "page" not in st.session_state:
    st.session_state.page = "login"

# التحقق من طلبات URL
query_params = st.query_params
if "action" in query_params and query_params["action"] == "logout":
    st.session_state.logged_in = False
    st.session_state.user_role = ""
    st.session_state.user_name = ""
    st.session_state.page = "login"
    st.query_params.clear()
    st.rerun()

if "page" in query_params:
    page = query_params["page"]
    if page in ["home", "teacher_attendance", "student_dashboard"]:
        st.session_state.page = page
        st.query_params.clear()
        st.rerun()

# صفحة تسجيل الدخول الرئيسية
if st.session_state.page == "login":
    # إخفاء البرجر منيو في صفحة تسجيل الدخول
    st.markdown("""
    <style>
    .burger-container { display: none !important; }
    </style>
    """, unsafe_allow_html=True)
    
    # تصميم صفحة تسجيل الدخول
    st.markdown("""
    <div class="login-screen">
        <div class="login-container">
            <div class="login-title">🚪 تسجيل الدخول</div>
    """, unsafe_allow_html=True)
    
    # حاوية الإدخالات
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        # حقل إدخال اسم المستخدم
        st.markdown('<div class="input-label">اسم المستخدم</div>', unsafe_allow_html=True)
        username = st.text_input("اسم المستخدم", 
                                placeholder="مثال: مينا سمير أو اسم الطالب",
                                label_visibility="collapsed")
        
        # حقل إدخال كلمة السر
        st.markdown('<div class="input-label">كلمة المرور</div>', unsafe_allow_html=True)
        password = st.text_input("كلمة المرور", type="password", 
                                placeholder="أدخل كلمة المرور هنا",
                                label_visibility="collapsed")
        
        # زر تسجيل الدخول
        login_button = st.button("✅ تسجيل الدخول", use_container_width=True)
        
        # معالجة تسجيل الدخول
        if login_button:
            if username and password:
                if username in USERS:
                    if USERS[username]["password"] == password:
                        st.session_state.logged_in = True
                        st.session_state.user_name = username
                        st.session_state.user_role = USERS[username]["role"]
                        
                        # توجيه المستخدم حسب دوره
                        if USERS[username]["role"] == "teacher":
                            st.session_state.page = "teacher_attendance"
                            st.session_state.teacher_name = USERS[username]["teacher_name"]
                        else:  # student
                            st.session_state.page = "student_dashboard"
                            st.session_state.student_name = USERS[username]["student_name"]
                        
                        st.success(f"✅ مرحباً {username}!")
                        st.rerun()
                    else:
                        st.error("❌ كلمة المرور غير صحيحة")
                else:
                    st.error("❌ اسم المستخدم غير موجود")
            else:
                st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")
        
        # معلومات مساعدة
        st.markdown("""
        <div style="margin-top: 20px; padding: 12px; background: #f8fafc; border-radius: 8px; text-align: center; border: 1px solid #e2e8f0;">
            <p style="margin: 0; color: #64748b; font-size: 13px;">
                <strong>المعلمون:</strong> مينا سمير، فادي حبيب
            </p>
            <p style="margin: 3px 0; color: #64748b; font-size: 13px;">
                كلمة المرور: <strong>teacher123</strong>
            </p>
            <p style="margin: 3px 0 0 0; color: #64748b; font-size: 12px;">
                <strong>الطلاب:</strong> ادخل اسمك كما هو في القائمة
            </p>
            <p style="margin: 0; color: #64748b; font-size: 12px;">
                كلمة المرور: <strong>student123</strong>
            </p>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div></div>", unsafe_allow_html=True)

# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    # تحديث البرجر منيو بمعلومات المستخدم
    user_role = st.session_state.get('user_role', '')
    user_role_display = "معلم" if user_role == "teacher" else "طالب"
    
    # إضافة JavaScript لتحديث البرجر منيو
    st.markdown(f"""
    <script>
    updateNavInfo('{st.session_state.user_name}', '{user_role}');
    </script>
    """, unsafe_allow_html=True)
    
    # عرض رسالة ترحيب
    st.markdown(f"""
    <div class="welcome-message">
        <div class="welcome-text">مرحباً بك {st.session_state.user_name}</div>
        <div class="user-info">أنت مسجل دخولك كـ {user_role_display}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # صفحة المعلم لتسجيل الغياب
    if st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        st.markdown('<div class="teacher-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">📝 تسجيل الغياب</div>', unsafe_allow_html=True)
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        
        # اختيار الطلاب الغائبين
        st.markdown("**اختر الطلاب الغائبين:**")
        selected = st.multiselect("اختر الطلاب الغائبين", STUDENTS, label_visibility="collapsed")

        # اختيار نوع الغياب
        st.markdown("**اختر نوع الغياب:**")
        col_a, col_b = st.columns(2)
        with col_a:
            excuse = st.checkbox("غياب بعذر", key="excuse")
        with col_b:
            no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")

        if excuse and no_excuse:
            st.warning("⚠️ اختر نوع واحد فقط.")

        if st.button("💾 حفظ وتسجيل الغياب", key="record_attendance", use_container_width=True):
            if not selected:
                st.warning("⚠️ يجب اختيار طالب/طلاب أولا.")
            elif excuse and no_excuse:
                st.warning("⚠️ اختر نوع واحد فقط.")
            elif not (excuse or no_excuse):
                st.warning("⚠️ من فضلك اختر نوع الغياب.")
            else:
                status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                
                # تسجيل الغياب
                try:
                    failed, telegram_status, telegram_details, success_count = record_attendance(selected, teacher_name, status_label)
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                else:
                    # رسالة نجاح مختصرة فقط
                    if success_count > 0:
                        st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                    if failed:
                        st.error(f"⚠️ حدثت بعض الأخطاء عند تسجيل: {failed}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة الطالب لعرض تقاريره
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown('<div class="student-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">📊 تقرير الغياب الخاص بي</div>', unsafe_allow_html=True)
        student_name = st.session_state.get('student_name', st.session_state.user_name)
        
        # عرض بيانات الطالب مباشرة
        df_student = get_student_records(student_name)
        
        if df_student.empty:
            st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        else:
            # عرض الإحصاءات
            col1, col2, col3 = st.columns(3)
            with col1:
                absent_count = int((df_student["الحالة"] == "غياب بعذر").sum() + (df_student["الحالة"] == "غياب بدون عذر").sum())
                st.metric("عدد مرات الغياب", absent_count)
            with col2:
                present_count = int((df_student["الحالة"] == "حاضر").sum())
                st.metric("عدد مرات الحضور", present_count)
            with col3:
                total_count = len(df_student)
                percentage = (present_count / total_count * 100) if total_count > 0 else 0
                st.metric("نسبة الحضور", f"{percentage:.1f}%")
            
            # عرض الجدول
            st.markdown("**تفاصيل السجلات:**")
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            
            # زر تحميل PDF
            pdf_buf = generate_student_pdf(student_name, df_student)
            st.download_button(
                "📥 تحميل تقرير PDF",
                data=pdf_buf,
                file_name=f"{student_name}_report.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # الصفحة الرئيسية المشتركة
    elif st.session_state.page == "home":
        st.markdown('<div class="home-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # عرض الأزرار حسب نوع المستخدم
        col1, col2 = st.columns(2)
        
        if st.session_state.user_role == "teacher":
            with col1:
                if st.button("📝 تسجيل الغياب", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.rerun()
            
            with col2:
                if st.button("👨‍🎓 عرض تقارير", use_container_width=True):
                    st.session_state.page = "student_dashboard"
                    st.rerun()
        
        elif st.session_state.user_role == "student":
            with col1:
                if st.button("📊 تقرير الغياب الخاص بي", use_container_width=True):
                    st.session_state.page = "student_dashboard"
                    st.rerun()
            
            with col2:
                st.info("👈 استخدم البرجر منيو للتنقل")
        
        # زر تسجيل الخروج
        st.markdown('<div style="margin-top: 40px;">', unsafe_allow_html=True)
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.page = "login"
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # إضافة مسافة في الأسفل
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
