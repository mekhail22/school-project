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
        "student_name": "بيشوي عاطف فاز"
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

# CSS + top toolbar
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    #MainMenu, header, footer {visibility: hidden !important;}
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
        color: #1e293b;
    }
    .top-toolbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 80px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 30px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        z-index: 999999 !important;
        font-family: 'Cairo', sans-serif;
        color: white;
    }
    .logo-container { display: flex; align-items: center; gap: 15px; }
    .logo-img { 
        width: 50px; height: 50px; border-radius: 12px; 
        object-fit: contain; border: 2px solid rgba(255,255,255,0.3); 
        background: white; padding: 4px;
    }
    .school-info { line-height: 1.3; }
    .school-name { 
        font-size: 20px; 
        font-weight: bold; 
        margin: 0; 
        color: white !important; /* اسم المدرسة أبيض */
    }
    .school-date { 
        font-size: 14px; 
        opacity: 0.9; 
        margin: 0; 
        color: rgba(255, 255, 255, 0.9) !important; /* التاريخ أبيض مع شفافية */
    }
    .content-padding { height: 90px; }
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
        color: #94a3b8;
        font-size: 16px;
    }
    .login-button {
        width: 100%;
        padding: 18px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white !important; /* نص أبيض */
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
        color: white !important; /* نص أبيض عند hover */
    }
    .user-type-badge {
        display: inline-block;
        padding: 6px 15px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 600;
        margin-left: 10px;
    }
    .badge-teacher {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    .badge-student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    /* صفحة رئيسية أكبر */
    .home-page {
        max-width: 800px;
        margin: 0 auto;
        padding: 20px;
    }
    .home-title {
        font-size: 36px;
        margin-bottom: 30px;
        color: #1e40af !important;
        text-align: center;
        font-weight: 700;
    }
    .main-buttons-container {
        display: flex;
        flex-direction: column;
        gap: 20px;
        margin-top: 40px;
    }
    .main-button {
        width: 100%;
        padding: 25px;
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white !important; /* نص أبيض */
        border: none;
        border-radius: 15px;
        font-size: 24px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
        font-family: 'Cairo', sans-serif;
        margin: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 15px;
        border: 3px solid rgba(59, 130, 246, 0.2);
    }
    .main-button:hover {
        transform: translateY(-4px);
        box-shadow: 0 15px 30px rgba(59, 130, 246, 0.3);
        border-color: #3b82f6;
        color: white !important; /* نص أبيض عند hover */
    }
    .main-button.teacher {
        background: linear-gradient(135deg, #10b981, #059669);
    }
    .main-button.student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
    }
    .main-button.logout {
        background: linear-gradient(135deg, #ef4444, #dc2626);
    }
    .welcome-message {
        text-align: center;
        padding: 25px;
        margin: 20px 0;
        background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
        border-radius: 15px;
        border: 3px solid #bae6fd;
    }
    .welcome-text {
        font-size: 24px;
        color: #0369a1;
        font-weight: 700;
    }
    .user-info {
        font-size: 18px;
        color: #475569;
        margin-top: 10px;
    }
    /* تحسين ألوان المتركس */
    .stMetric {
        background: white !important;
        border-radius: 12px !important;
        padding: 20px !important;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08) !important;
        border: 2px solid #e2e8f0 !important;
    }
    .stMetric label {
        color: #1e293b !important;
        font-weight: 600 !important;
        font-size: 18px !important;
    }
    .stMetric div {
        color: #1e40af !important;
        font-weight: 700 !important;
        font-size: 28px !important;
    }
    /* تحسين أزرار الغياب */
    .attendance-checkbox {
        background: white !important;
        border: 3px solid #3b82f6 !important;
        border-radius: 10px !important;
        padding: 15px !important;
        margin: 10px 0 !important;
    }
    .attendance-checkbox label {
        color: #1e293b !important;
        font-weight: 600 !important;
        font-size: 18px !important;
    }
    
    /* =========================================== */
    /* ===== التعديلات لجعل نص الأزرار أبيض ===== */
    /* =========================================== */
    
    /* زر تسجيل الدخول الرئيسي */
    .stButton > button {
        width: 100% !important;
        height: auto !important;
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important; /* نص أبيض */
        font-size: 20px !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        border: 3px solid rgba(59, 130, 246, 0.2) !important;
        box-shadow: 0 5px 15px rgba(37,99,235,0.2) !important;
        transition: all 0.3s ease !important;
        margin: 15px 0 !important;
        padding: 18px !important;
        display: block !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 25px rgba(37,99,235,0.3) !important;
        border-color: #3b82f6 !important;
        color: white !important; /* نص أبيض عند hover */
    }
    
    /* جميع نصوص الأزرار - نص أبيض */
    button, 
    button span,
    button div,
    button p,
    button label,
    .stButton button,
    .stButton button span,
    .stButton button p,
    .stButton button div,
    .stButton button label,
    div[data-testid="stButton"] button,
    div[data-testid="stButton"] button span,
    div[data-testid="stButton"] button p,
    div[data-testid="stButton"] button div,
    div[data-testid="stButton"] button label,
    div[data-testid="column"] button,
    div[data-testid="column"] button span,
    div[data-testid="column"] button p,
    div[data-testid="column"] button div,
    div[data-testid="column"] button label {
        color: white !important;
    }
    
    /* hover states - نص أبيض */
    button:hover,
    button:hover span,
    button:hover div,
    button:hover p,
    button:hover label,
    .stButton button:hover,
    .stButton button:hover span,
    .stButton button:hover p,
    .stButton button:hover div,
    .stButton button:hover label,
    div[data-testid="stButton"] button:hover,
    div[data-testid="stButton"] button:hover span,
    div[data-testid="stButton"] button:hover p,
    div[data-testid="stButton"] button:hover div,
    div[data-testid="stButton"] button:hover label,
    div[data-testid="column"] button:hover,
    div[data-testid="column"] button:hover span,
    div[data-testid="column"] button:hover p,
    div[data-testid="column"] button:hover div,
    div[data-testid="column"] button:hover label {
        color: white !important;
    }
    
    /* زر تسجيل الغياب بلون مختلف - نص أبيض */
    button.attendance-button,
    button.attendance-button span,
    button.attendance-button p,
    button.attendance-button div {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important;
    }
    
    button.attendance-button:hover,
    button.attendance-button:hover span,
    button.attendance-button:hover p,
    button.attendance-button:hover div {
        background: linear-gradient(135deg, #059669, #047857) !important;
        color: white !important;
    }
    
    /* أزرار العودة - نص أبيض */
    button.back-button,
    button.back-button span,
    button.back-button p,
    button.back-button div {
        background: linear-gradient(135deg, #64748b, #475569) !important;
        color: white !important;
    }
    
    button.back-button:hover,
    button.back-button:hover span,
    button.back-button:hover p,
    button.back-button:hover div {
        background: linear-gradient(135deg, #475569, #334155) !important;
        color: white !important;
    }
    
    /* زر تسجيل الخروج - نص أبيض */
    button.logout-button,
    button.logout-button span,
    button.logout-button p,
    button.logout-button div {
        background: linear-gradient(135deg, #ef4444, #dc2626) !important;
        color: white !important;
    }
    
    button.logout-button:hover,
    button.logout-button:hover span,
    button.logout-button:hover p,
    button.logout-button:hover div {
        background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
        color: white !important;
    }
    
    /* أزرار التنزيل - نص أبيض */
    div[data-testid="stDownloadButton"] button,
    div[data-testid="stDownloadButton"] button span,
    div[data-testid="stDownloadButton"] button p,
    div[data-testid="stDownloadButton"] button div {
        background: linear-gradient(135deg, #8b5cf6, #7c3aed) !important;
        color: white !important;
    }
    
    div[data-testid="stDownloadButton"] button:hover,
    div[data-testid="stDownloadButton"] button:hover span,
    div[data-testid="stDownloadButton"] button:hover p,
    div[data-testid="stDownloadButton"] button:hover div {
        background: linear-gradient(135deg, #7c3aed, #6d28d9) !important;
        color: white !important;
    }
    
    /* أزرار المعلم - نص أبيض */
    button.teacher-button,
    button.teacher-button span,
    button.teacher-button p,
    button.teacher-button div {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important;
    }
    
    button.teacher-button:hover,
    button.teacher-button:hover span,
    button.teacher-button:hover p,
    button.teacher-button:hover div {
        background: linear-gradient(135deg, #059669, #047857) !important;
        color: white !important;
    }
    
    /* أزرار الطالب - نص أبيض */
    button.student-button,
    button.student-button span,
    button.student-button p,
    button.student-button div {
        background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
        color: white !important;
    }
    
    button.student-button:hover,
    button.student-button:hover span,
    button.student-button:hover p,
    button.student-button:hover div {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* تحسين الملتيسيليكت */
    .stMultiSelect > div > div {
        background: white !important;
        border: 3px solid #3b82f6 !important;
        border-radius: 12px !important;
        color: #1e293b !important;
        font-size: 16px !important;
    }
    .stMultiSelect > div > div:hover {
        border-color: #2563eb !important;
    }
    .stMultiSelect label {
        color: #1e293b !important;
        font-weight: 600 !important;
        font-size: 18px !important;
    }
    /* تحسين الرسائل */
    .stAlert {
        border-radius: 12px !important;
        padding: 20px !important;
        font-size: 16px !important;
        border: 2px solid !important;
    }
    .stAlert.stSuccess {
        background: #d1fae5 !important;
        border-color: #86efac !important;
        color: #065f46 !important;
    }
    .stAlert.stError {
        background: #fee2e2 !important;
        border-color: #fca5a5 !important;
        color: #991b1b !important;
    }
    .stAlert.stWarning {
        background: #fef3c7 !important;
        border-color: #fcd34d !important;
        color: #92400e !important;
    }
    .stAlert.stInfo {
        background: #dbeafe !important;
        border-color: #93c5fd !important;
        color: #1e40af !important;
    }
    /* تحسين الأقسام */
    .stHeader {
        color: #1e40af !important;
        border-bottom: 3px solid #e2e8f0 !important;
        padding-bottom: 15px !important;
        font-size: 32px !important;
        margin-bottom: 20px !important;
    }
    .stSubheader {
        color: #475569 !important;
        font-size: 24px !important;
    }
    /* تحسين الجداول */
    .dataframe {
        background: white !important;
        color: #1e293b !important;
        border: 2px solid #e2e8f0 !important;
        font-size: 16px !important;
    }
    .dataframe th {
        background: #f1f5f9 !important;
        color: #1e40af !important;
        border: 2px solid #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 16px !important;
    }
    .dataframe td {
        border: 2px solid #e2e8f0 !important;
        color: #475569 !important;
        font-size: 15px !important;
    }
    /* تحسين حقول الإدخال */
    .stTextInput > div > div > input {
        background: white !important;
        color: #1e293b !important;
        border: 3px solid #e2e8f0 !important;
        font-size: 18px !important;
        padding: 15px !important;
        border-radius: 10px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #3b82f6 !important;
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2) !important;
    }
    /* تحسين السيلكت بوكس */
    .stSelectbox > div > div {
        background: white !important;
        color: #1e293b !important;
        border: 3px solid #e2e8f0 !important;
        font-size: 18px !important;
    }
    /* تحسين الشيك بوكس */
    .stCheckbox > label {
        color: #1e293b !important;
        font-size: 18px !important;
        font-weight: 500 !important;
    }
    /* تحسين محتوى الصفحة */
    .main-content {
        color: #1e293b !important;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #1e40af !important;
    }
    p, span, div {
        color: #475569 !important;
    }
    /* تحسين صفحة المعلم */
    .teacher-page {
        max-width: 900px;
        margin: 0 auto;
        padding: 20px;
    }
    /* تحسين صفحة الطالب */
    .student-page {
        max-width: 900px;
        margin: 0 auto;
        padding: 20px;
    }
    /* تحسين المساعدة */
    .help-info {
        background: #f8fafc;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        padding: 20px;
        margin-top: 30px;
        text-align: center;
    }
    .help-title {
        color: #1e40af;
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 10px;
    }
    .help-text {
        color: #64748b;
        font-size: 14px;
        line-height: 1.6;
    }
</style>
""", unsafe_allow_html=True)

# Top toolbar HTML (يظهر فقط بعد تسجيل الدخول)
def show_toolbar():
    user_role = st.session_state.get('user_role', '')
    badge_class = "badge-teacher" if user_role == "teacher" else "badge-student"
    badge_text = "معلم" if user_role == "teacher" else "طالب"
    
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">مدرسة السلام الإعدادية</p>
                <p class="school-date">{formatted_date}</p>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 15px;">
            <span class="user-type-badge {badge_class}">{badge_text}</span>
            <div style="color: white; font-size: 16px; font-weight: 600;">{st.session_state.user_name}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

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

# صفحة تسجيل الدخول الرئيسية
if st.session_state.page == "login":
    # إخفاء الـ toolbar في صفحة تسجيل الدخول
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)
    
    # تصميم صفحة تسجيل الدخول
    st.markdown("""
    <div class="login-container">
        <div class="login-title">🚪 تسجيل الدخول</div>
    </div>
    """, unsafe_allow_html=True)
    
    # حاوية الإدخالات
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        # حقل إدخال اسم المستخدم مع تسمية واضحة
        st.markdown('<div class="input-label">اسم المستخدم</div>', unsafe_allow_html=True)
        username = st.text_input("اسم المستخدم", 
                                placeholder="أدخل اسمك (مثال: مينا سمير)",
                                label_visibility="collapsed")
        
        # حقل إدخال كلمة السر مع تسمية واضحة
        st.markdown('<div class="input-label">كلمة المرور</div>', unsafe_allow_html=True)
        password = st.text_input("كلمة المرور", type="password", 
                                placeholder="أدخل كلمة المرور",
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
        <div class="help-info">
            <div class="help-title">معلومات تسجيل الدخول</div>
            <div class="help-text">
                <p><strong>المعلمون:</strong> مينا سمير، فادي حبيب</p>
                <p>كلمة المرور: <strong>teacher123</strong></p>
                <p><strong>الطلاب:</strong> ادخل اسمك كما هو في القائمة</p>
                <p>كلمة المرور: <strong>student123</strong></p>
            </div>
        </div>
        """, unsafe_allow_html=True)

# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    show_toolbar()
    
    # عرض رسالة ترحيب
    user_role_display = "معلم" if st.session_state.user_role == "teacher" else "طالب"
    st.markdown(f"""
    <div class="welcome-message">
        <div class="welcome-text">مرحباً بك {st.session_state.user_name}</div>
        <div class="user-info">أنت مسجل دخولك كـ {user_role_display}</div>
    </div>
    """, unsafe_allow_html=True)
    
    # صفحة المعلم لتسجيل الغياب
    if st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        st.markdown('<div class="teacher-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">📝 تسجيل الغياب</div>', unsafe_allow_html=True)
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        st.markdown(f'<h3 style="text-align: center; color: #475569;">المعلم: {teacher_name}</h3>', unsafe_allow_html=True)

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
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    
    # صفحة الطالب لعرض تقاريره
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown('<div class="student-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">📊 تقرير الغياب الخاص بي</div>', unsafe_allow_html=True)
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
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    
    # الصفحة الرئيسية المشتركة
    elif st.session_state.page == "home":
        st.markdown('<div class="home-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # عرض الأزرار حسب نوع المستخدم
        st.markdown('<div class="main-buttons-container">', unsafe_allow_html=True)
        
        if st.session_state.user_role == "teacher":
            if st.button("👨‍🏫 تسجيل الغياب", key="teacher_attendance_btn", use_container_width=True):
                st.session_state.page = "teacher_attendance"
                st.rerun()
        
        elif st.session_state.user_role == "student":
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", key="student_dashboard_btn", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        # زر تسجيل الخروج للجميع
        if st.button("🚪 تسجيل الخروج", key="logout_btn", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.page = "login"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
