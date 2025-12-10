import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import json
import logging
import base64
import requests
import time

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
st.set_page_config(
    page_title="نظام الغياب - مدرسة الإبداع",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed",
    menu_items={
        'Get Help': None,
        'Report a bug': None,
        'About': "نظام إدارة الغياب الإلكتروني لمدرسة الإبداع"
    }
)

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
        "teacher_name": "مينا سمير",
        "permissions": ["record_attendance", "view_reports", "generate_reports"]
    },
    "فادي حبيب": {
        "password": "teacher123",
        "role": "teacher",
        "teacher_name": "فادي حبيب",
        "permissions": ["record_attendance", "view_reports", "generate_reports"]
    },
    
    # طلاب - لهم صلاحية عرض تقاريرهم فقط
    "ميخائيل صابر فوزي": {
        "password": "student123",
        "role": "student",
        "student_name": "ميخائيل صابر فوزي",
        "permissions": ["view_own_reports"]
    },
    "مينا ريمون خيري": {
        "password": "student123",
        "role": "student",
        "student_name": "مينا ريمون خيري",
        "permissions": ["view_own_reports"]
    },
    "توني هاني نصرالله": {
        "password": "student123",
        "role": "student",
        "student_name": "توني هاني نصرالله",
        "permissions": ["view_own_reports"]
    },
    "يوسف شادي كمال": {
        "password": "student123",
        "role": "student",
        "student_name": "يوسف شادي كمال",
        "permissions": ["view_own_reports"]
    },
    "ادم مايكل فوزي": {
        "password": "student123",
        "role": "student",
        "student_name": "ادم مايكل فوزي",
        "permissions": ["view_own_reports"]
    },
    "مارك نادر فؤاد": {
        "password": "student123",
        "role": "student",
        "student_name": "مارك نادر فؤاد",
        "permissions": ["view_own_reports"]
    },
    "بيشوي عاطف فايز": {
        "password": "student123",
        "role": "student",
        "student_name": "بيشوي عاطف فايز",
        "permissions": ["view_own_reports"]
    },
    "جورج مينا نجيب": {
        "password": "student123",
        "role": "student",
        "student_name": "جورج مينا نجيب",
        "permissions": ["view_own_reports"]
    },
    "كيرلس فادي صادق": {
        "password": "student123",
        "role": "student",
        "student_name": "كيرلس فادي صادق",
        "permissions": ["view_own_reports"]
    },
    "يوستينا مجدي فادي": {
        "password": "student123",
        "role": "student",
        "student_name": "يوستينا مجدي فادي",
        "permissions": ["view_own_reports"]
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
                logger.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
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
                logger.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT: {e}")
        
        return {
            'BOT_TOKEN': BOT_TOKEN,
            'CHAT_ID': CHAT_ID,
            'SHEET_NAME': SHEET_NAME,
            'SERVICE_ACCOUNT': SERVICE_ACCOUNT
        }
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحميل الإعدادات: {str(e)}")
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
                    headers = ["student", "teacher", "status", "date", "timestamp"]
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

# ------------------ إعدادات التطبيق ------------------
APP_NAME = "مدرسة الإبداع"
APP_VERSION = "2.0.1"
SCHOOL_LOGO_URL = "https://cdn-icons-png.flaticon.com/512/2784/2784449.png"
DEFAULT_AVATAR = "👨‍🏫"

# ------------------ دالة لتحميل الصور ------------------
@st.cache_data
def load_image_base64(url):
    """تحميل الصورة وتحويلها إلى base64"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return base64.b64encode(response.content).decode()
    except Exception:
        # استخدام صورة افتراضية
        default_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100" viewBox="0 0 100 100">
            <rect width="100" height="100" fill="#2563eb"/>
            <text x="50" y="60" font-family="Arial" font-size="40" fill="white" text-anchor="middle">🏫</text>
        </svg>'''
        return base64.b64encode(default_svg.encode()).decode()

# تحميل شعار المدرسة
try:
    SCHOOL_LOGO_BASE64 = load_image_base64(SCHOOL_LOGO_URL)
except Exception:
    SCHOOL_LOGO_BASE64 = None

# ------------------ وظائف مساعدة ------------------
def get_current_time():
    """الحصول على الوقت الحالي بتنسيق عربي"""
    now = datetime.now()
    arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", 
                    "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    
    weekday = arabic_weekdays[now.weekday()]
    month = arabic_months[now.month - 1]
    time_str = now.strftime("%I:%M %p")
    
    return f"{weekday}، {now.day} {month} {now.year} | {time_str}"

def get_user_avatar(role, name=""):
    """الحصول على الصورة الرمزية للمستخدم"""
    if role == "teacher":
        return "👨‍🏫"
    elif role == "student":
        return "👨‍🎓"
    else:
        return "👤"

def check_permission(user_role, permission):
    """التحقق من صلاحية المستخدم"""
    if user_role not in st.session_state:
        return False
    
    user_info = USERS.get(st.session_state.user_name, {})
    permissions = user_info.get('permissions', [])
    
    return permission in permissions

# ------------------ CSS وأنماط التطبيق ------------------
def load_custom_css():
    """تحميل CSS المخصص للتطبيق"""
    
    css = f"""
    <style>
    /* إخفاء العناصر الافتراضية لـ Streamlit */
    #MainMenu {{visibility: hidden;}}
    footer {{visibility: hidden;}}
    .stDeployButton {{display:none;}}
    
    /* الشريط العلوي الأزرق */
    .custom-header {{
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%);
        color: white;
        padding: 15px 30px;
        margin: -50px -50px 30px -50px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
        position: sticky;
        top: 0;
        z-index: 1000;
        border-bottom: 4px solid #fbbf24;
    }}
    
    .header-left {{
        display: flex;
        align-items: center;
        gap: 20px;
    }}
    
    .school-logo {{
        width: 60px;
        height: 60px;
        border-radius: 50%;
        background: white;
        padding: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    
    .school-logo img {{
        width: 100%;
        height: 100%;
        object-fit: contain;
    }}
    
    .school-info h1 {{
        margin: 0;
        font-size: 28px;
        font-weight: 800;
        color: white;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.3);
    }}
    
    .school-info p {{
        margin: 5px 0 0 0;
        font-size: 16px;
        color: #dbeafe;
        opacity: 0.9;
    }}
    
    .header-right {{
        display: flex;
        flex-direction: column;
        align-items: flex-end;
        gap: 5px;
    }}
    
    .current-time {{
        font-size: 14px;
        background: rgba(255, 255, 255, 0.15);
        padding: 5px 12px;
        border-radius: 20px;
        backdrop-filter: blur(10px);
    }}
    
    .user-display {{
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 15px;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 25px;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }}
    
    .user-avatar {{
        font-size: 24px;
        background: white;
        width: 40px;
        height: 40px;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: #2563eb;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
    }}
    
    .user-details h4 {{
        margin: 0;
        font-size: 16px;
        font-weight: 600;
    }}
    
    .user-details p {{
        margin: 2px 0 0 0;
        font-size: 12px;
        color: #dbeafe;
    }}
    
    /* القائمة الجانبية */
    .sidebar-container {{
        position: fixed;
        top: 120px;
        right: 20px;
        z-index: 999;
    }}
    
    .hamburger-btn {{
        width: 60px;
        height: 60px;
        background: linear-gradient(135deg, #1e40af, #3b82f6);
        border: none;
        border-radius: 50%;
        color: white;
        font-size: 24px;
        cursor: pointer;
        box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    
    .hamburger-btn:hover {{
        transform: scale(1.1);
        box-shadow: 0 8px 25px rgba(37, 99, 235, 0.6);
    }}
    
    .sidebar-menu {{
        position: fixed;
        top: 120px;
        right: -300px;
        width: 280px;
        background: white;
        border-radius: 20px;
        box-shadow: 0 15px 40px rgba(0, 0, 0, 0.15);
        padding: 20px;
        transition: right 0.3s ease;
        z-index: 1000;
        border: 1px solid #e5e7eb;
    }}
    
    .sidebar-menu.active {{
        right: 20px;
    }}
    
    .sidebar-overlay {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.5);
        z-index: 999;
        display: none;
        backdrop-filter: blur(3px);
    }}
    
    .sidebar-overlay.active {{
        display: block;
    }}
    
    .menu-header {{
        text-align: center;
        margin-bottom: 25px;
        padding-bottom: 15px;
        border-bottom: 2px solid #f3f4f6;
    }}
    
    .menu-header h3 {{
        margin: 0;
        color: #1e40af;
        font-size: 22px;
        font-weight: 700;
    }}
    
    .menu-item {{
        display: flex;
        align-items: center;
        gap: 15px;
        padding: 15px;
        margin: 10px 0;
        border-radius: 12px;
        cursor: pointer;
        transition: all 0.3s ease;
        border: none;
        background: none;
        width: 100%;
        text-align: right;
        font-family: inherit;
        font-size: 16px;
        color: #374151;
    }}
    
    .menu-item:hover {{
        background: linear-gradient(135deg, #eff6ff, #dbeafe);
        transform: translateX(-5px);
        color: #1e40af;
    }}
    
    .menu-item.active {{
        background: linear-gradient(135deg, #2563eb, #1e40af);
        color: white;
    }}
    
    .menu-item i {{
        font-size: 22px;
        width: 30px;
        text-align: center;
    }}
    
    .logout-btn {{
        background: linear-gradient(135deg, #ef4444, #dc2626) !important;
        color: white !important;
        margin-top: 20px !important;
    }}
    
    .logout-btn:hover {{
        background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
    }}
    
    /* محتوى الصفحة */
    .main-content {{
        padding: 30px;
        margin-top: 100px;
        min-height: calc(100vh - 200px);
    }}
    
    .page-container {{
        max-width: 1200px;
        margin: 0 auto;
        background: white;
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.08);
        border: 1px solid #e5e7eb;
    }}
    
    .page-title {{
        font-size: 32px;
        margin-bottom: 30px;
        color: #1e40af;
        text-align: center;
        font-weight: 700;
        padding-bottom: 15px;
        border-bottom: 3px solid #fbbf24;
        position: relative;
    }}
    
    .page-title:after {{
        content: '';
        position: absolute;
        bottom: -3px;
        left: 35%;
        width: 30%;
        height: 3px;
        background: #2563eb;
        border-radius: 2px;
    }}
    
    /* بطاقات الإحصاءات */
    .stats-container {{
        display: flex;
        gap: 20px;
        margin: 30px 0;
        flex-wrap: wrap;
    }}
    
    .stat-card {{
        flex: 1;
        min-width: 200px;
        background: linear-gradient(135deg, #f8fafc, #e2e8f0);
        padding: 25px;
        border-radius: 15px;
        text-align: center;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
        border: 2px solid #e2e8f0;
        transition: all 0.3s ease;
    }}
    
    .stat-card:hover {{
        transform: translateY(-5px);
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
        border-color: #3b82f6;
    }}
    
    .stat-icon {{
        font-size: 40px;
        margin-bottom: 15px;
        color: #2563eb;
    }}
    
    .stat-value {{
        font-size: 32px;
        font-weight: 800;
        color: #1e40af;
        margin: 10px 0;
    }}
    
    .stat-label {{
        font-size: 16px;
        color: #64748b;
        font-weight: 600;
    }}
    
    /* أزرار العمل */
    .action-buttons {{
        display: flex;
        gap: 15px;
        margin: 25px 0;
        flex-wrap: wrap;
    }}
    
    .action-btn {{
        flex: 1;
        min-width: 200px;
        padding: 20px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        border: none;
        border-radius: 12px;
        font-size: 18px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        text-align: center;
    }}
    
    .action-btn:hover {{
        background: linear-gradient(135deg, #1d4ed8, #1e40af);
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(37, 99, 235, 0.3);
    }}
    
    .action-btn.secondary {{
        background: linear-gradient(135deg, #475569, #64748b);
    }}
    
    .action-btn.secondary:hover {{
        background: linear-gradient(135deg, #374151, #475569);
    }}
    
    /* نماذج الإدخال */
    .form-group {{
        margin: 25px 0;
    }}
    
    .form-label {{
        display: block;
        margin-bottom: 10px;
        font-size: 18px;
        font-weight: 600;
        color: #1e293b;
    }}
    
    .form-control {{
        width: 100%;
        padding: 15px;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        font-size: 16px;
        font-family: inherit;
        transition: all 0.3s ease;
        background: white;
        color: #1e293b;
    }}
    
    .form-control:focus {{
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
    }}
    
    /* الجداول */
    .data-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 25px 0;
        background: white;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
    }}
    
    .data-table th {{
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        padding: 15px;
        text-align: right;
        font-weight: 600;
    }}
    
    .data-table td {{
        padding: 12px 15px;
        border-bottom: 1px solid #e5e7eb;
        text-align: right;
    }}
    
    .data-table tr:hover {{
        background: #f8fafc;
    }}
    
    /* التذييل */
    .footer {{
        text-align: center;
        padding: 25px;
        margin-top: 40px;
        color: #64748b;
        font-size: 14px;
        border-top: 1px solid #e5e7eb;
        background: #f8fafc;
        border-radius: 0 0 20px 20px;
    }}
    
    /* رسائل التنبيه */
    .alert-success {{
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
        padding: 15px 20px;
        border-radius: 12px;
        margin: 20px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    
    .alert-error {{
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
        padding: 15px 20px;
        border-radius: 12px;
        margin: 20px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    
    .alert-warning {{
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
        padding: 15px 20px;
        border-radius: 12px;
        margin: 20px 0;
        display: flex;
        align-items: center;
        gap: 10px;
    }}
    
    /* التكيف مع الشاشات الصغيرة */
    @media (max-width: 768px) {{
        .custom-header {{
            padding: 12px 20px;
            flex-direction: column;
            gap: 15px;
            text-align: center;
        }}
        
        .header-left, .header-right {{
            width: 100%;
            justify-content: center;
        }}
        
        .header-right {{
            align-items: center;
        }}
        
        .page-container {{
            padding: 20px;
        }}
        
        .page-title {{
            font-size: 24px;
        }}
        
        .action-buttons {{
            flex-direction: column;
        }}
        
        .sidebar-container {{
            top: 180px;
        }}
        
        .sidebar-menu.active {{
            right: 10px;
            width: 280px;
        }}
    }}
    
    /* إضافات خاصة */
    .connection-status {{
        position: fixed;
        bottom: 20px;
        left: 20px;
        background: rgba(30, 58, 138, 0.9);
        color: white;
        padding: 10px 15px;
        border-radius: 25px;
        font-size: 12px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
        z-index: 100;
        max-width: 300px;
    }}
    
    .connection-status.success {{
        background: rgba(34, 197, 94, 0.9);
    }}
    
    .connection-status.warning {{
        background: rgba(245, 158, 11, 0.9);
    }}
    
    .connection-status.error {{
        background: rgba(239, 68, 68, 0.9);
    }}
    
    /* تأثيرات خاصة */
    .pulse {{
        animation: pulse 2s infinite;
    }}
    
    @keyframes pulse {{
        0% {{ box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }}
        70% {{ box-shadow: 0 0 0 10px rgba(37, 99, 235, 0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }}
    }}
    
    /* إخفاء عناصر Streamlit غير المرغوب فيها */
    .st-emotion-cache-1kyxreq {{
        display: none !important;
    }}
    </style>
    
    <script>
    // دالة لإدارة القائمة الجانبية
    function toggleSidebar() {{
        const sidebar = document.getElementById('sidebarMenu');
        const overlay = document.getElementById('sidebarOverlay');
        const btn = document.getElementById('hamburgerBtn');
        
        if (sidebar.classList.contains('active')) {{
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            btn.innerHTML = '☰';
        }} else {{
            sidebar.classList.add('active');
            overlay.classList.add('active');
            btn.innerHTML = '✕';
        }}
    }}
    
    // إغلاق القائمة عند النقر خارجها
    function closeSidebar(e) {{
        const sidebar = document.getElementById('sidebarMenu');
        const overlay = document.getElementById('sidebarOverlay');
        const btn = document.getElementById('hamburgerBtn');
        
        if (sidebar.classList.contains('active') && 
            !sidebar.contains(e.target) && 
            e.target.id !== 'hamburgerBtn') {{
            sidebar.classList.remove('active');
            overlay.classList.remove('active');
            btn.innerHTML = '☰';
        }}
    }}
    
    // تحديث الوقت
    function updateTime() {{
        const now = new Date();
        const options = {{ 
            weekday: 'long', 
            year: 'numeric', 
            month: 'long', 
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true 
        }};
        
        // تحويل إلى تنسيق عربي
        const arabicDays = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت"];
        const arabicMonths = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", 
                             "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"];
        
        const day = arabicDays[now.getDay()];
        const month = arabicMonths[now.getMonth()];
        const time = now.toLocaleTimeString('ar-EG', {{ hour: '2-digit', minute: '2-digit', hour12: true }});
        
        const timeString = `${{day}}، ${{now.getDate()}} ${{month}} ${{now.getFullYear()}} | ${{time}}`;
        
        const timeElement = document.getElementById('currentTime');
        if (timeElement) {{
            timeElement.textContent = timeString;
        }}
    }}
    
    // تحديث الوقت كل دقيقة
    setInterval(updateTime, 60000);
    
    // تهيئة الأحداث
    document.addEventListener('DOMContentLoaded', function() {{
        updateTime();
        
        // إغلاق القائمة عند النقر على overlay
        document.getElementById('sidebarOverlay').addEventListener('click', function(e) {{
            closeSidebar(e);
        }});
        
        // إغلاق القائمة عند الضغط على Esc
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape') {{
                closeSidebar(e);
            }}
        }});
    }});
    </script>
    """
    
    return css

# ------------------ وظائف PDF ------------------
REGISTERED_FONT = None

def ensure_font():
    """تأكد من تثبيت الخط العربي"""
    global REGISTERED_FONT
    
    if REGISTERED_FONT:
        return REGISTERED_FONT
    
    FONT_PATH = "NotoNaskhArabic-Regular.ttf"
    FONT_NAME = "ArabicCustom"
    
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
            REGISTERED_FONT = FONT_NAME
            return FONT_NAME
    except Exception:
        pass

    # محاولة خطوط بديلة
    for candidate in ["Arial", "DejaVuSans", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            REGISTERED_FONT = FONT_NAME
            return FONT_NAME
        except Exception:
            continue

    return None

def reshape_arabic_text(text):
    """إعادة تشكيل النص العربي للعرض الصحيح"""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet():
    """قراءة البيانات من Google Sheet"""
    if worksheet is None:
        return pd.DataFrame(columns=["student", "teacher", "status", "date", "timestamp"])
    
    try:
        data = worksheet.get_all_records()
    except Exception as e:
        logger.error(f"خطأ في قراءة البيانات: {e}")
        return pd.DataFrame(columns=["student", "teacher", "status", "date", "timestamp"])
    
    df = pd.DataFrame(data)
    
    # تأكد من وجود جميع الأعمدة المطلوبة
    for column in ["student", "teacher", "status", "date", "timestamp"]:
        if column not in df.columns:
            df[column] = ""
    
    return df

def normalize_date_for_pdf(src_date_str):
    """تنسيق التاريخ لملف PDF"""
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
    """إرسال رسالة إلى Telegram"""
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
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في إرسال Telegram: {e}")
        return False, {"exception": "Request failed"}

def record_attendance(selected_absent, teacher_name, absent_label):
    """تسجيل الغياب"""
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = datetime.now().strftime("%d / %m / %Y")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display, timestamp])

    failed = []
    success_count = 0
    
    # حفظ في Google Sheets إذا كان متصلاً
    if worksheet:
        try:
            # إضافة جميع الصفوف مرة واحدة
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
            logger.info(f"تم حفظ {success_count} سجل بنجاح")
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            logger.error(f"خطأ في الإضافة الجماعية: {e}")
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append(("جميع الطلاب", str(ex)))
                logger.error(f"خطأ في الإضافة الفردية: {ex}")
    else:
        failed.append(("جميع الطلاب", "لا يوجد اتصال بـ Google Sheets"))
        logger.warning("لا يوجد اتصال بـ Google Sheets")

    # إرسال إشعار Telegram
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"📋 تم تسجيل الغياب\n\n📅 التاريخ: {date_display}\n👨‍🏫 المعلم: {teacher_name}\n📝 حالة الغياب: {absent_label}\n❌ الغائبون: {absent_students}\n✅ تم حفظ {success_count} سجل بنجاح\n🕐 الوقت: {timestamp}"
    
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if BOT_TOKEN and CHAT_ID:
        ok, info = send_telegram_message(message)
        if ok:
            telegram_status = "✅ تم الإرسال بنجاح"
            telegram_details = "تم إرسال الإشعار إلى Telegram"
            logger.info("تم إرسال إشعار Telegram بنجاح")
        else:
            telegram_status = "❌ فشل الإرسال"
            telegram_details = f"تفاصيل الخطأ: {info}"
            logger.error(f"فشل إرسال Telegram: {info}")
    else:
        telegram_status = "⚠️ إعدادات Telegram غير مكتملة"
        logger.warning("إعدادات Telegram غير مكتملة")
    
    return failed, telegram_status, telegram_details, success_count

def get_student_records(student_name):
    """الحصول على سجلات طالب معين"""
    df = read_sheet()
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة", "الوقت"])
    
    try:
        df_matches = df[df["student"].astype(str).str.contains(student_name, case=False, na=False)].copy()
    except Exception as e:
        logger.error(f"خطأ في البحث عن الطالب: {e}")
        df_matches = df[df["student"].astype(str).str.lower() == student_name.lower()].copy()
    
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة", "الوقت"])
    
    df_matches = df_matches.sort_values(by="timestamp", ascending=False).reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    
    df_matches = df_matches.rename(columns={
        "student": "الطالب", 
        "teacher": "المعلم", 
        "date": "التاريخ", 
        "status": "الحالة",
        "timestamp": "الوقت"
    })
    
    return df_matches[["المرة", "الطالب", "المعلم", "التاريخ", "الحالة", "الوقت"]]

def get_all_records():
    """الحصول على جميع السجلات"""
    df = read_sheet()
    
    if df.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة", "الوقت"])
    
    df = df.sort_values(by="timestamp", ascending=False).reset_index(drop=True)
    df.insert(0, "المرة", range(1, len(df) + 1))
    
    df = df.rename(columns={
        "student": "الطالب", 
        "teacher": "المعلم", 
        "date": "التاريخ", 
        "status": "الحالة",
        "timestamp": "الوقت"
    })
    
    return df[["المرة", "الطالب", "المعلم", "التاريخ", "الحالة", "الوقت"]]

def generate_student_pdf(student_name, df_records):
    """إنشاء ملف PDF لتقرير الطالب"""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4, 
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    
    elements = []
    font_for_style = ensure_font() or "Helvetica"
    
    # تعريف الأنماط
    title_style = ParagraphStyle(
        'Title', 
        fontName=font_for_style, 
        fontSize=20, 
        alignment=1, 
        textColor=colors.darkblue,
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        fontName=font_for_style,
        fontSize=14,
        alignment=2,
        textColor=colors.darkblue,
        spaceAfter=8
    )
    
    normal_style = ParagraphStyle(
        'Normal', 
        fontName=font_for_style, 
        fontSize=12, 
        alignment=2
    )
    
    footer_style = ParagraphStyle(
        'Footer', 
        fontName=font_for_style, 
        fontSize=10, 
        alignment=2, 
        textColor=colors.darkblue
    )
    
    # العنوان
    elements.append(Paragraph(reshape_arabic_text("مدرسة الإبداع"), title_style))
    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب التفصيلي"), title_style))
    elements.append(Spacer(1, 16))
    
    # معلومات الطالب
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), subtitle_style))
    elements.append(Spacer(1, 12))
    
    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        # الإحصائيات
        absent_with_excuse = int((df_records["الحالة"] == "غياب بعذر").sum())
        absent_without_excuse = int((df_records["الحالة"] == "غياب بدون عذر").sum())
        absent_count = absent_with_excuse + absent_without_excuse
        present_count = int((df_records["الحالة"] == "حاضر").sum())
        total_count = len(df_records)
        
        elements.append(Paragraph(reshape_arabic_text("الإحصائيات:"), normal_style))
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب بعذر: {absent_with_excuse}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب بدون عذر: {absent_without_excuse}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"إجمالي عدد السجلات: {total_count}"), normal_style))
        
        if total_count > 0:
            attendance_rate = (present_count / total_count) * 100
            elements.append(Paragraph(reshape_arabic_text(f"نسبة الحضور: {attendance_rate:.1f}%"), normal_style))
        
        elements.append(Spacer(1, 20))
        
        # الجدول
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
        
        table = Table(data, hAlign='CENTER', colWidths=[50, 150, 120, 100, 80])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke])
        ]))
        
        elements.append(table)
    
    elements.append(Spacer(1, 20))
    
    # التذييل
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    current_time = today.strftime("%I:%M %p")
    
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date} - {current_time}"), footer_style))
    elements.append(Paragraph(reshape_arabic_text("نظام إدارة الغياب الإلكتروني - مدرسة الإبداع"), footer_style))
    
    # بناء PDF
    doc.build(elements)
    buffer.seek(0)
    
    return buffer

def generate_summary_report(df_all_records):
    """إنشاء تقرير إحصائي شامل"""
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4, 
        rightMargin=40, 
        leftMargin=40, 
        topMargin=40, 
        bottomMargin=40
    )
    
    elements = []
    font_for_style = ensure_font() or "Helvetica"
    
    # تعريف الأنماط
    title_style = ParagraphStyle(
        'Title', 
        fontName=font_for_style, 
        fontSize=20, 
        alignment=1, 
        textColor=colors.darkblue,
        spaceAfter=12
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        fontName=font_for_style,
        fontSize=14,
        alignment=2,
        textColor=colors.darkblue,
        spaceAfter=8
    )
    
    normal_style = ParagraphStyle(
        'Normal', 
        fontName=font_for_style, 
        fontSize=12, 
        alignment=2
    )
    
    # العنوان
    elements.append(Paragraph(reshape_arabic_text("مدرسة الإبداع"), title_style))
    elements.append(Paragraph(reshape_arabic_text("التقرير الإحصائي الشامل"), title_style))
    elements.append(Spacer(1, 20))
    
    # التاريخ
    today = datetime.now()
    report_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ التقرير: {report_date}"), subtitle_style))
    elements.append(Spacer(1, 15))
    
    # إحصائيات عامة
    if df_all_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات في النظام."), normal_style))
    else:
        total_records = len(df_all_records)
        total_students = df_all_records["الطالب"].nunique()
        total_teachers = df_all_records["المعلم"].nunique()
        
        present_count = (df_all_records["الحالة"] == "حاضر").sum()
        absent_with_excuse = (df_all_records["الحالة"] == "غياب بعذر").sum()
        absent_without_excuse = (df_all_records["الحالة"] == "غياب بدون عذر").sum()
        total_absent = absent_with_excuse + absent_without_excuse
        
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
        
        # عرض الإحصائيات
        stats_data = [
            ["إجمالي السجلات", str(total_records)],
            ["عدد الطلاب", str(total_students)],
            ["عدد المعلمين", str(total_teachers)],
            ["حضور", str(present_count)],
            ["غياب بعذر", str(absent_with_excuse)],
            ["غياب بدون عذر", str(absent_without_excuse)],
            ["إجمالي الغياب", str(total_absent)],
            ["نسبة الحضور", f"{attendance_rate:.1f}%"]
        ]
        
        table = Table(stats_data, colWidths=[150, 80])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        
        # جدول السجلات الأخيرة
        elements.append(Paragraph(reshape_arabic_text("أحدث السجلات:"), subtitle_style))
        elements.append(Spacer(1, 10))
        
        recent_records = df_all_records.head(20)
        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
        table_data = [header]
        
        for _, row in recent_records.iterrows():
            table_data.append([
                reshape_arabic_text(row.get("المرة", "")),
                reshape_arabic_text(row.get("الطالب", "")),
                reshape_arabic_text(row.get("المعلم", "")),
                reshape_arabic_text(row.get("التاريخ", "")),
                reshape_arabic_text(row.get("الحالة", ""))
            ])
        
        table2 = Table(table_data, colWidths=[40, 120, 100, 80, 60])
        table2.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        
        elements.append(table2)
    
    # بناء PDF
    doc.build(elements)
    buffer.seek(0)
    
    return buffer

# ------------------ واجهات المستخدم ------------------
def render_header():
    """عرض الشريط العلوي"""
    
    logo_html = ""
    if SCHOOL_LOGO_BASE64:
        logo_html = f'<img src="data:image/svg+xml;base64,{SCHOOL_LOGO_BASE64}" alt="شعار المدرسة">'
    else:
        logo_html = '<div style="font-size: 32px;">🏫</div>'
    
    user_avatar = get_user_avatar(
        st.session_state.get('user_role', ''), 
        st.session_state.get('user_name', '')
    )
    
    current_time = get_current_time()
    
    header_html = f"""
    <div class="custom-header">
        <div class="header-left">
            <div class="school-logo">
                {logo_html}
            </div>
            <div class="school-info">
                <h1>مدرسة الإبداع</h1>
                <p>نظام إدارة الغياب الإلكتروني | النسخة {APP_VERSION}</p>
            </div>
        </div>
        
        <div class="header-right">
            <div class="current-time" id="currentTime">
                {current_time}
            </div>
            {render_user_display()}
        </div>
    </div>
    
    <!-- القائمة الجانبية -->
    <div class="sidebar-container">
        <button class="hamburger-btn pulse" id="hamburgerBtn" onclick="toggleSidebar()">☰</button>
    </div>
    
    <div class="sidebar-overlay" id="sidebarOverlay" onclick="closeSidebar(event)"></div>
    
    <div class="sidebar-menu" id="sidebarMenu">
        <div class="menu-header">
            <h3>🌙 قائمة التنقل</h3>
        </div>
        {render_menu_items()}
    </div>
    
    <!-- حالة الاتصال -->
    <div class="connection-status {'success' if '✅' in connection_status else 'error' if '❌' in connection_status else 'warning'}">
        📊 {connection_status}
    </div>
    """
    
    return header_html

def render_user_display():
    """عرض معلومات المستخدم"""
    if not st.session_state.get('logged_in', False):
        return '<div class="user-display"><div class="user-avatar">👤</div><div class="user-details"><h4>زائر</h4><p>لم يتم تسجيل الدخول</p></div></div>'
    
    user_role = st.session_state.get('user_role', '')
    user_name = st.session_state.get('user_name', '')
    avatar = get_user_avatar(user_role, user_name)
    role_text = "معلم" if user_role == "teacher" else "طالب"
    
    return f'''
    <div class="user-display">
        <div class="user-avatar">{avatar}</div>
        <div class="user-details">
            <h4>{user_name}</h4>
            <p>{role_text}</p>
        </div>
    </div>
    '''

def render_menu_items():
    """عرض عناصر القائمة"""
    if not st.session_state.get('logged_in', False):
        return ""
    
    user_role = st.session_state.get('user_role', '')
    current_page = st.session_state.get('page', 'home')
    
    menu_items = []
    
    # عناصر القائمة للمعلمين
    if user_role == "teacher":
        menu_items.append({
            "icon": "🏠",
            "label": "الرئيسية",
            "page": "home",
            "active": current_page == "home"
        })
        menu_items.append({
            "icon": "📝",
            "label": "تسجيل الغياب",
            "page": "teacher_attendance",
            "active": current_page == "teacher_attendance"
        })
        menu_items.append({
            "icon": "📊",
            "label": "التقارير",
            "page": "reports",
            "active": current_page == "reports"
        })
        menu_items.append({
            "icon": "👨‍🎓",
            "label": "إدارة الطلاب",
            "page": "students",
            "active": current_page == "students"
        })
    
    # عناصر القائمة للطلاب
    elif user_role == "student":
        menu_items.append({
            "icon": "🏠",
            "label": "الرئيسية",
            "page": "home",
            "active": current_page == "home"
        })
        menu_items.append({
            "icon": "📊",
            "label": "تقريري",
            "page": "student_dashboard",
            "active": current_page == "student_dashboard"
        })
        menu_items.append({
            "icon": "📁",
            "label": "سجلاتي",
            "page": "my_records",
            "active": current_page == "my_records"
        })
    
    # عناصر مشتركة
    menu_items.append({
        "icon": "⚙️",
        "label": "الإعدادات",
        "page": "settings",
        "active": current_page == "settings"
    })
    
    # زر تسجيل الخروج
    menu_items.append({
        "icon": "🚪",
        "label": "تسجيل الخروج",
        "page": "logout",
        "class": "logout-btn"
    })
    
    # بناء HTML للقائمة
    menu_html = ""
    for item in menu_items:
        active_class = "active" if item.get("active", False) else ""
        extra_class = f" {item.get('class', '')}" if item.get('class') else ""
        
        menu_html += f'''
        <button class="menu-item {active_class}{extra_class}" 
                onclick="window.location.href = window.location.pathname + '?page={item['page']}'">
            <i>{item['icon']}</i>
            <span>{item['label']}</span>
        </button>
        '''
    
    return menu_html

def render_login_page():
    """عرض صفحة تسجيل الدخول"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">🚪 تسجيل الدخول</div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col2:
        # رسالة ترحيب
        st.markdown("""
        <div style="text-align: center; margin-bottom: 30px;">
            <div style="font-size: 40px; margin-bottom: 10px;">🏫</div>
            <h2 style="color: #1e40af;">مرحباً بك في نظام الغياب</h2>
            <p style="color: #64748b;">من فضلك سجل الدخول للوصول إلى النظام</p>
        </div>
        """, unsafe_allow_html=True)
        
        # نموذج تسجيل الدخول
        with st.form("login_form"):
            st.markdown('<div class="form-label">اسم المستخدم</div>', unsafe_allow_html=True)
            username = st.text_input(
                "اسم المستخدم",
                placeholder="أدخل اسم المستخدم...",
                label_visibility="collapsed",
                key="username_input"
            )
            
            st.markdown('<div class="form-label">كلمة المرور</div>', unsafe_allow_html=True)
            password = st.text_input(
                "كلمة المرور",
                type="password",
                placeholder="أدخل كلمة المرور...",
                label_visibility="collapsed",
                key="password_input"
            )
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            with col_btn2:
                login_submitted = st.form_submit_button(
                    "✅ تسجيل الدخول",
                    use_container_width=True,
                    type="primary"
                )
            
            if login_submitted:
                if username and password:
                    if username in USERS:
                        if USERS[username]["password"] == password:
                            st.session_state.logged_in = True
                            st.session_state.user_name = username
                            st.session_state.user_role = USERS[username]["role"]
                            
                            if USERS[username]["role"] == "teacher":
                                st.session_state.page = "teacher_attendance"
                                st.session_state.teacher_name = USERS[username]["teacher_name"]
                            else:
                                st.session_state.page = "student_dashboard"
                                st.session_state.student_name = USERS[username]["student_name"]
                            
                            st.success(f"✅ مرحباً بك {username}!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error("❌ كلمة المرور غير صحيحة")
                    else:
                        st.error("❌ اسم المستخدم غير موجود")
                else:
                    st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")
        
        # معلومات المساعدة
        st.markdown("""
        <div style="margin-top: 40px; padding: 20px; background: #f8fafc; border-radius: 15px; border: 2px dashed #cbd5e1;">
            <h4 style="color: #1e40af; margin-bottom: 15px;">💡 معلومات المساعدة:</h4>
            
            <div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 15px;">
                <div style="flex: 1; min-width: 200px; padding: 10px; background: white; border-radius: 10px; border: 1px solid #e2e8f0;">
                    <div style="font-weight: bold; color: #2563eb; margin-bottom: 5px;">👨‍🏫 للمعلمين:</div>
                    <div style="font-size: 14px; color: #475569;">
                        <div>• مينا سمير</div>
                        <div>• فادي حبيب</div>
                        <div><strong>كلمة المرور:</strong> teacher123</div>
                    </div>
                </div>
                
                <div style="flex: 1; min-width: 200px; padding: 10px; background: white; border-radius: 10px; border: 1px solid #e2e8f0;">
                    <div style="font-weight: bold; color: #2563eb; margin-bottom: 5px;">👨‍🎓 للطلاب:</div>
                    <div style="font-size: 14px; color: #475569;">
                        <div>• أدخل اسمك كما في القائمة</div>
                        <div><strong>كلمة المرور:</strong> student123</div>
                    </div>
                </div>
            </div>
            
            <div style="padding: 10px; background: #dbeafe; border-radius: 8px; border: 1px solid #93c5fd;">
                <div style="font-size: 12px; color: #1e40af; text-align: center;">
                    <strong>ملاحظة:</strong> إذا واجهتك أي مشكلة، راجع مدير النظام
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_home_page():
    """عرض الصفحة الرئيسية"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">🏠 الصفحة الرئيسية</div>
    """, unsafe_allow_html=True)
    
    user_role = st.session_state.get('user_role', '')
    user_name = st.session_state.get('user_name', '')
    
    # إحصائيات سريعة
    try:
        df = read_sheet()
        total_records = len(df)
        today = datetime.now().strftime("%d / %m / %Y")
        today_records = len(df[df['date'] == today]) if 'date' in df.columns else 0
    except Exception:
        total_records = 0
        today_records = 0
    
    st.markdown(f"""
    <div class="stats-container">
        <div class="stat-card">
            <div class="stat-icon">👤</div>
            <div class="stat-value">{len(STUDENTS)}</div>
            <div class="stat-label">إجمالي الطلاب</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-icon">📋</div>
            <div class="stat-value">{total_records}</div>
            <div class="stat-label">إجمالي السجلات</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-icon">📅</div>
            <div class="stat-value">{today_records}</div>
            <div class="stat-label">سجلات اليوم</div>
        </div>
        
        <div class="stat-card">
            <div class="stat-icon">👨‍🏫</div>
            <div class="stat-value">{len(TEACHERS)}</div>
            <div class="stat-label">إجمالي المعلمين</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # أزرار الإجراءات حسب دور المستخدم
    st.markdown("""
    <div style="margin: 40px 0;">
        <h3 style="color: #1e40af; text-align: center; margin-bottom: 25px;">🚀 الإجراءات السريعة</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if user_role == "teacher":
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📝 تسجيل الغياب", use_container_width=True, key="btn_attendance"):
                st.session_state.page = "teacher_attendance"
                st.rerun()
        
        with col2:
            if st.button("📊 التقارير", use_container_width=True, key="btn_reports"):
                st.session_state.page = "reports"
                st.rerun()
        
        col3, col4 = st.columns(2)
        
        with col3:
            if st.button("👨‍🎓 إدارة الطلاب", use_container_width=True, key="btn_students"):
                st.session_state.page = "students"
                st.rerun()
        
        with col4:
            if st.button("⚙️ الإعدادات", use_container_width=True, key="btn_settings"):
                st.session_state.page = "settings"
                st.rerun()
    
    elif user_role == "student":
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📊 تقريري", use_container_width=True, key="btn_my_report"):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        with col2:
            if st.button("📁 سجلاتي", use_container_width=True, key="btn_my_records"):
                st.session_state.page = "my_records"
                st.rerun()
        
        col3, col4 = st.columns(2)
        
        with col3:
            if st.button("📥 تحميل PDF", use_container_width=True, key="btn_download_pdf"):
                student_name = st.session_state.get('student_name', user_name)
                df_records = get_student_records(student_name)
                pdf_buffer = generate_student_pdf(student_name, df_records)
                
                st.download_button(
                    label="📥 اضغط لتحميل PDF",
                    data=pdf_buffer,
                    file_name=f"{student_name}_report.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        
        with col4:
            if st.button("⚙️ الإعدادات", use_container_width=True, key="btn_settings"):
                st.session_state.page = "settings"
                st.rerun()
    
    # معلومات النظام
    st.markdown("""
    <div style="margin-top: 40px; padding: 25px; background: linear-gradient(135deg, #f0f9ff, #e2e8f0); border-radius: 15px; border: 2px solid #bae6fd;">
        <h4 style="color: #0369a1; margin-bottom: 15px;">ℹ️ معلومات النظام</h4>
        
        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px;">
            <div style="padding: 12px; background: white; border-radius: 10px;">
                <div style="font-weight: bold; color: #1e40af;">👋 مرحباً بك</div>
                <div style="color: #475569; margin-top: 5px;">{user_name}</div>
            </div>
            
            <div style="padding: 12px; background: white; border-radius: 10px;">
                <div style="font-weight: bold; color: #1e40af;">🎯 دورك</div>
                <div style="color: #475569; margin-top: 5px;">{"معلم" if user_role == "teacher" else "طالب"}</div>
            </div>
            
            <div style="padding: 12px; background: white; border-radius: 10px;">
                <div style="font-weight: bold; color: #1e40af;">📅 تاريخ اليوم</div>
                <div style="color: #475569; margin-top: 5px;">{get_current_time()}</div>
            </div>
            
            <div style="padding: 12px; background: white; border-radius: 10px;">
                <div style="font-weight: bold; color: #1e40af;">🔗 حالة الاتصال</div>
                <div style="color: #475569; margin-top: 5px;">{connection_status}</div>
            </div>
        </div>
    </div>
    """.format(
        user_name=user_name,
        user_role=user_role,
        connection_status=connection_status
    ), unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_teacher_attendance():
    """عرض صفحة تسجيل الغياب للمعلم"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">📝 تسجيل الغياب</div>
    """, unsafe_allow_html=True)
    
    teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
    
    # معلومات المعلم
    st.markdown(f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #dbeafe, #93c5fd); border-radius: 15px; margin-bottom: 30px; border: 2px solid #60a5fa;">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 40px;">👨‍🏫</div>
            <div>
                <h3 style="margin: 0; color: #1e40af;">المعلم: {teacher_name}</h3>
                <p style="margin: 5px 0 0 0; color: #475569;">{get_current_time()}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # نموذج تسجيل الغياب
    with st.form("attendance_form"):
        st.markdown("### 📋 اختر الطلاب الغائبين")
        
        col1, col2 = st.columns(2)
        
        with col1:
            selected_students = st.multiselect(
                "الطلاب",
                STUDENTS,
                placeholder="اختر الطلاب الغائبين...",
                key="absent_students"
            )
        
        with col2:
            st.markdown("### 📝 اختر نوع الغياب")
            excuse = st.checkbox("غياب بعذر", key="excuse_check")
            no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse_check")
        
        # زر الحفظ
        col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
        
        with col_btn2:
            submit_attendance = st.form_submit_button(
                "💾 حفظ وتسجيل الغياب",
                use_container_width=True,
                type="primary"
            )
        
        if submit_attendance:
            # التحقق من البيانات
            if not selected_students:
                st.error("❌ يجب اختيار طالب/طلاب على الأقل")
            elif excuse and no_excuse:
                st.error("❌ لا يمكن اختيار النوعين معاً")
            elif not (excuse or no_excuse):
                st.error("❌ يجب اختيار نوع الغياب")
            else:
                status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                
                with st.spinner("جاري تسجيل الغياب..."):
                    try:
                        failed, telegram_status, telegram_details, success_count = record_attendance(
                            selected_students, 
                            teacher_name, 
                            status_label
                        )
                        
                        if success_count > 0:
                            st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                            
                            # عرض تفاصيل إضافية
                            col_success1, col_success2 = st.columns(2)
                            
                            with col_success1:
                                st.info(f"📅 التاريخ: {datetime.now().strftime('%d / %m / %Y')}")
                            
                            with col_success2:
                                st.info(f"👨‍🏫 المعلم: {teacher_name}")
                            
                            # عرض الطلاب الغائبين
                            if selected_students:
                                st.markdown("### 📋 قائمة الغائبين:")
                                for i, student in enumerate(selected_students, 1):
                                    st.markdown(f"{i}. **{student}** - {status_label}")
                            
                            # تفاصيل Telegram
                            if "✅" in telegram_status:
                                st.success("📱 تم إرسال إشعار Telegram")
                            else:
                                st.warning("⚠️ لم يتم إرسال إشعار Telegram")
                        
                        if failed:
                            st.error("⚠️ حدثت بعض الأخطاء عند التسجيل")
                            for error in failed:
                                st.error(f"• {error[0]}: {error[1]}")
                    
                    except Exception as e:
                        st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
    
    # قائمة الطلاب الكاملة
    st.markdown("### 👨‍🎓 قائمة الطلاب الكاملة")
    
    # عرض الطلاب في شبكة
    cols = st.columns(4)
    for i, student in enumerate(STUDENTS):
        with cols[i % 4]:
            st.markdown(f"""
            <div style="padding: 10px; margin: 5px 0; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0; text-align: center;">
                <div style="font-size: 20px;">👨‍🎓</div>
                <div style="font-weight: 600; color: #1e40af;">{student}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_student_dashboard():
    """عرض صفحة الطالب"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">📊 تقريري</div>
    """, unsafe_allow_html=True)
    
    student_name = st.session_state.get('student_name', st.session_state.user_name)
    
    # معلومات الطالب
    st.markdown(f"""
    <div style="padding: 20px; background: linear-gradient(135deg, #ecfdf5, #a7f3d0); border-radius: 15px; margin-bottom: 30px; border: 2px solid #34d399;">
        <div style="display: flex; align-items: center; gap: 15px;">
            <div style="font-size: 40px;">👨‍🎓</div>
            <div>
                <h3 style="margin: 0; color: #059669;">الطالب: {student_name}</h3>
                <p style="margin: 5px 0 0 0; color: #475569;">{get_current_time()}</p>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # الحصول على سجلات الطالب
    df_student = get_student_records(student_name)
    
    if df_student.empty:
        st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        
        # زر العودة
        if st.button("🏠 العودة للرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    else:
        # الإحصائيات
        present_count = int((df_student["الحالة"] == "حاضر").sum())
        absent_with_excuse = int((df_student["الحالة"] == "غياب بعذر").sum())
        absent_without_excuse = int((df_student["الحالة"] == "غياب بدون عذر").sum())
        total_absent = absent_with_excuse + absent_without_excuse
        total_records = len(df_student)
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
        
        st.markdown("### 📈 إحصائيات الحضور والغياب")
        
        # عرض الإحصائيات في بطاقات
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">✅</div>
                <div class="stat-value">{present_count}</div>
                <div class="stat-label">حضور</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">⚠️</div>
                <div class="stat-value">{absent_with_excuse}</div>
                <div class="stat-label">غياب بعذر</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">❌</div>
                <div class="stat-value">{absent_without_excuse}</div>
                <div class="stat-label">غياب بدون عذر</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            st.markdown(f"""
            <div class="stat-card">
                <div class="stat-icon">📊</div>
                <div class="stat-value">{attendance_rate:.1f}%</div>
                <div class="stat-label">نسبة الحضور</div>
            </div>
            """, unsafe_allow_html=True)
        
        # عرض الجدول
        st.markdown("### 📋 تفاصيل السجلات")
        st.dataframe(
            df_student,
            use_container_width=True,
            hide_index=True,
            column_config={
                "المرة": st.column_config.NumberColumn("المرة", width="small"),
                "الطالب": st.column_config.TextColumn("الطالب", width="large"),
                "المعلم": st.column_config.TextColumn("المعلم", width="medium"),
                "التاريخ": st.column_config.TextColumn("التاريخ", width="medium"),
                "الحالة": st.column_config.TextColumn("الحالة", width="small"),
                "الوقت": st.column_config.TextColumn("الوقت", width="medium")
            }
        )
        
        # أزرار التحميل
        st.markdown("### 📥 خيارات التحميل")
        
        col_download1, col_download2 = st.columns(2)
        
        with col_download1:
            # تحميل PDF
            pdf_buffer = generate_student_pdf(student_name, df_student)
            st.download_button(
                "📥 تحميل تقرير PDF",
                data=pdf_buffer,
                file_name=f"{student_name}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                type="primary"
            )
        
        with col_download2:
            # تحميل Excel
            excel_buffer = io.BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                df_student.to_excel(writer, index=False, sheet_name='سجلات_الغياب')
            excel_buffer.seek(0)
            
            st.download_button(
                "📊 تحميل Excel",
                data=excel_buffer,
                file_name=f"{student_name}_records.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        
        # رسم بياني بسيط
        try:
            st.markdown("### 📊 مخطط الحضور والغياب")
            
            chart_data = pd.DataFrame({
                "الحالة": ["حاضر", "غياب بعذر", "غياب بدون عذر"],
                "العدد": [present_count, absent_with_excuse, absent_without_excuse]
            })
            
            st.bar_chart(chart_data.set_index("الحالة"))
        except Exception:
            pass
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_reports_page():
    """عرض صفحة التقارير للمعلمين"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">📊 التقارير</div>
    """, unsafe_allow_html=True)
    
    if not check_permission(st.session_state.user_role, "view_reports"):
        st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
        return
    
    # الحصول على جميع السجلات
    df_all = get_all_records()
    
    if df_all.empty:
        st.info("ℹ️ لا توجد سجلات في النظام")
        return
    
    # إحصائيات شاملة
    total_records = len(df_all)
    total_students = df_all["الطالب"].nunique()
    total_teachers = df_all["المعلم"].nunique()
    
    present_count = (df_all["الحالة"] == "حاضر").sum()
    absent_with_excuse = (df_all["الحالة"] == "غياب بعذر").sum()
    absent_without_excuse = (df_all["الحالة"] == "غياب بدون عذر").sum()
    total_absent = absent_with_excuse + absent_without_excuse
    
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    # عرض الإحصائيات
    st.markdown("### 📈 الإحصائيات الشاملة")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("إجمالي السجلات", f"{total_records:,}")
    
    with col2:
        st.metric("عدد الطلاب", total_students)
    
    with col3:
        st.metric("عدد المعلمين", total_teachers)
    
    with col4:
        st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
    
    # تقارير متقدمة
    st.markdown("### 📋 تقارير تفصيلية")
    
    tab1, tab2, tab3 = st.tabs(["📊 جميع السجلات", "👨‍🎓 حسب الطالب", "📅 حسب التاريخ"])
    
    with tab1:
        st.dataframe(
            df_all,
            use_container_width=True,
            hide_index=True
        )
        
        # تحميل التقرير الشامل
        st.download_button(
            "📥 تحميل التقرير الشامل PDF",
            data=generate_summary_report(df_all),
            file_name=f"التقرير_الشامل_{datetime.now().strftime('%Y%m%d')}.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    with tab2:
        selected_student = st.selectbox(
            "اختر الطالب",
            options=[""] + sorted(df_all["الطالب"].unique().tolist()),
            key="report_student_select"
        )
        
        if selected_student:
            student_records = df_all[df_all["الطالب"] == selected_student]
            st.dataframe(student_records, use_container_width=True, hide_index=True)
            
            # إحصائيات الطالب
            col_s1, col_s2, col_s3 = st.columns(3)
            
            with col_s1:
                st.metric(
                    "حضور",
                    f"{(student_records['الحالة'] == 'حاضر').sum()}"
                )
            
            with col_s2:
                st.metric(
                    "غياب بعذر",
                    f"{(student_records['الحالة'] == 'غياب بعذر').sum()}"
                )
            
            with col_s3:
                st.metric(
                    "غياب بدون عذر",
                    f"{(student_records['الحالة'] == 'غياب بدون عذر').sum()}"
                )
    
    with tab3:
        date_range = st.date_input(
            "اختر الفترة الزمنية",
            value=[datetime.now().date(), datetime.now().date()],
            key="report_date_range"
        )
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            # تحويل التواريخ إلى تنسيق البحث
            date_format = "%d / %m / %Y"
            
            # محاولة تصفية السجلات حسب التاريخ
            try:
                # تحويل تواريخ DataFrame
                df_all['التاريخ_مفهرس'] = pd.to_datetime(
                    df_all['التاريخ'],
                    format=date_format,
                    errors='coerce'
                )
                
                # تصفية حسب النطاق
                filtered = df_all[
                    (df_all['التاريخ_مفهرس'] >= pd.Timestamp(start_date)) &
                    (df_all['التاريخ_مفهرس'] <= pd.Timestamp(end_date))
                ].drop(columns=['التاريخ_مفهرس'])
                
                st.dataframe(filtered, use_container_width=True, hide_index=True)
                
                if not filtered.empty:
                    st.metric("عدد السجلات في الفترة", len(filtered))
                else:
                    st.info("لا توجد سجلات في هذه الفترة")
                    
            except Exception as e:
                st.error(f"حدث خطأ في تصفية السجلات: {e}")
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_settings_page():
    """عرض صفحة الإعدادات"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">⚙️ الإعدادات</div>
    """, unsafe_allow_html=True)
    
    user_role = st.session_state.get('user_role', '')
    user_name = st.session_state.get('user_name', '')
    
    # معلومات المستخدم
    st.markdown("### 👤 معلومات حسابك")
    
    with st.container():
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown(f"""
            <div style="padding: 20px; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0;">
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                    <div style="font-size: 40px;">{get_user_avatar(user_role, user_name)}</div>
                    <div>
                        <div style="font-size: 18px; font-weight: bold; color: #1e40af;">{user_name}</div>
                        <div style="color: #64748b;">{"معلم" if user_role == "teacher" else "طالب"}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_info2:
            st.markdown(f"""
            <div style="padding: 20px; background: #f8fafc; border-radius: 10px; border: 1px solid #e2e8f0;">
                <div style="color: #475569; margin-bottom: 10px;">📅 تاريخ التسجيل:</div>
                <div style="font-weight: bold; color: #1e40af;">{datetime.now().strftime('%d / %m / %Y')}</div>
                
                <div style="margin-top: 15px; color: #475569;">🔗 حالة الاتصال:</div>
                <div style="font-weight: bold; {'color: #10b981;' if '✅' in connection_status else 'color: #ef4444;'}">
                    {connection_status}
                </div>
            </div>
            """, unsafe_allow_html=True)
    
    # إعدادات النظام
    st.markdown("### ⚙️ إعدادات النظام")
    
    with st.expander("🔧 إعدادات التطبيق", expanded=True):
        col_set1, col_set2 = st.columns(2)
        
        with col_set1:
            st.checkbox("إشعارات Telegram", value=True, key="telegram_notifications")
            st.checkbox("تحديث تلقائي", value=True, key="auto_refresh")
        
        with col_set2:
            st.selectbox("السعة", ["عربي", "English"], key="language")
            st.selectbox("نمط العرض", ["فاتح", "داكن"], key="theme")
    
    # إدارة البيانات
    st.markdown("### 💾 إدارة البيانات")
    
    if user_role == "teacher":
        with st.expander("📊 نسخ احتياطي"):
            col_backup1, col_backup2 = st.columns(2)
            
            with col_backup1:
                if st.button("تحميل نسخة احتياطية", use_container_width=True):
                    df_all = get_all_records()
                    csv_buffer = io.StringIO()
                    df_all.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        "📥 تحميل CSV",
                        data=csv_buffer.getvalue(),
                        file_name=f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
            
            with col_backup2:
                if st.button("طباعة جميع السجلات", use_container_width=True):
                    df_all = get_all_records()
                    st.dataframe(df_all, use_container_width=True)
    
    # تغيير كلمة المرور
    st.markdown("### 🔒 تغيير كلمة المرور")
    
    with st.form("change_password_form"):
        current_pass = st.text_input("كلمة المرور الحالية", type="password")
        new_pass = st.text_input("كلمة المرور الجديدة", type="password")
        confirm_pass = st.text_input("تأكيد كلمة المرور الجديدة", type="password")
        
        if st.form_submit_button("تغيير كلمة المرور", use_container_width=True):
            if current_pass and new_pass and confirm_pass:
                if new_pass == confirm_pass:
                    # هنا يجب ربطه بنظام المصادقة
                    st.success("✅ تم طلب تغيير كلمة المرور")
                else:
                    st.error("❌ كلمات المرور غير متطابقة")
            else:
                st.error("❌ من فضلك املأ جميع الحقول")
    
    # زر تسجيل الخروج
    st.markdown("---")
    
    col_logout1, col_logout2, col_logout3 = st.columns([1, 2, 1])
    
    with col_logout2:
        if st.button("🚪 تسجيل الخروج", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.page = "login"
            st.rerun()
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_my_records_page():
    """عرض صفحة سجلات الطالب"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">📁 سجلاتي</div>
    """, unsafe_allow_html=True)
    
    student_name = st.session_state.get('student_name', st.session_state.user_name)
    df_records = get_student_records(student_name)
    
    if df_records.empty:
        st.info(f"ℹ️ لا توجد سجلات لك يا {student_name}")
    else:
        # عرض السجلات مع خيارات تصفية
        col_filter1, col_filter2 = st.columns(2)
        
        with col_filter1:
            filter_status = st.selectbox(
                "تصفية حسب الحالة",
                options=["الكل", "حاضر", "غياب بعذر", "غياب بدون عذر"],
                key="filter_status"
            )
        
        with col_filter2:
            sort_order = st.selectbox(
                "ترتيب حسب",
                options=["الأحدث أولاً", "الأقدم أولاً", "حسب التاريخ"],
                key="sort_order"
            )
        
        # تطبيق التصفية والترتيب
        if filter_status != "الكل":
            df_filtered = df_records[df_records["الحالة"] == filter_status]
        else:
            df_filtered = df_records.copy()
        
        # تطبيق الترتيب
        if sort_order == "الأحدث أولاً":
            df_filtered = df_filtered.sort_values(by="الوقت", ascending=False)
        elif sort_order == "الأقدم أولاً":
            df_filtered = df_filtered.sort_values(by="الوقت", ascending=True)
        elif sort_order == "حسب التاريخ":
            df_filtered = df_filtered.sort_values(by="التاريخ", ascending=False)
        
        st.dataframe(
            df_filtered,
            use_container_width=True,
            hide_index=True
        )
        
        # ملخص السجلات المصفاة
        st.info(f"📊 عدد السجلات: **{len(df_filtered)}** سجل")
    
    st.markdown("</div>", unsafe_allow_html=True)

def render_students_page():
    """عرض صفحة إدارة الطلاب (للمعلمين فقط)"""
    st.markdown("""
    <div class="page-container">
        <div class="page-title">👨‍🎓 إدارة الطلاب</div>
    """, unsafe_allow_html=True)
    
    if not check_permission(st.session_state.user_role, "record_attendance"):
        st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
        return
    
    st.markdown("### 📋 قائمة الطلاب المسجلين")
    
    # عرض الطلاب في جدول
    students_data = []
    for i, student in enumerate(STUDENTS, 1):
        students_data.append({
            "م": i,
            "اسم الطالب": student,
            "الحالة": "✅ مسجل"
        })
    
    df_students = pd.DataFrame(students_data)
    st.dataframe(
        df_students,
        use_container_width=True,
        hide_index=True,
        column_config={
            "م": st.column_config.NumberColumn("م", width="small"),
            "اسم الطالب": st.column_config.TextColumn("اسم الطالب", width="large"),
            "الحالة": st.column_config.TextColumn("الحالة", width="small")
        }
    )
    
    # إحصائيات
    st.markdown("### 📈 إحصائيات الطلاب")
    
    col_stats1, col_stats2, col_stats3 = st.columns(3)
    
    with col_stats1:
        st.metric("عدد الطلاب", len(STUDENTS))
    
    with col_stats2:
        # حساب نسبة الحضور العامة
        try:
            df_all = get_all_records()
            if not df_all.empty:
                attendance_rate = (df_all["الحالة"] == "حاضر").sum() / len(df_all) * 100
                st.metric("نسبة الحضور العامة", f"{attendance_rate:.1f}%")
            else:
                st.metric("نسبة الحضور العامة", "0%")
        except Exception:
            st.metric("نسبة الحضور العامة", "N/A")
    
    with col_stats3:
        # آخر تحديث
        st.metric("آخر تحديث", datetime.now().strftime("%H:%M"))
    
    # إضافة طالب جديد (وهمي للتوضيح)
    st.markdown("### ➕ إضافة طالب جديد")
    
    with st.form("add_student_form"):
        new_student = st.text_input("اسم الطالب الجديد")
        
        if st.form_submit_button("إضافة طالب", use_container_width=True):
            if new_student:
                st.success(f"✅ تم طلب إضافة الطالب: {new_student}")
                st.info("ملاحظة: هذه خاصية توضيحية. لإضافة طلاب فعلياً، راجع مدير النظام.")
            else:
                st.error("❌ من فضلك أدخل اسم الطالب")
    
    st.markdown("</div>", unsafe_allow_html=True)

# ------------------ التطبيق الرئيسي ------------------
def main():
    """الدالة الرئيسية للتطبيق"""
    
    # تحميل CSS
    st.markdown(load_custom_css(), unsafe_allow_html=True)
    
    # إدارة حالة التطبيق
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False
    if "user_role" not in st.session_state:
        st.session_state.user_role = ""
    if "user_name" not in st.session_state:
        st.session_state.user_name = ""
    if "page" not in st.session_state:
        st.session_state.page = "login"
    
    # التحقق من معلمات URL
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
        if page in ["home", "teacher_attendance", "student_dashboard", 
                   "reports", "settings", "students", "my_records"]:
            st.session_state.page = page
            st.query_params.clear()
            st.rerun()
    
    # عرض الشريط العلوي إذا كان المستخدم مسجلاً دخوله
    if st.session_state.logged_in:
        st.markdown(render_header(), unsafe_allow_html=True)
    
    # عرض المحتوى حسب الصفحة الحالية
    if not st.session_state.logged_in:
        render_login_page()
    else:
        # محتوى الصفحات المختلفة
        if st.session_state.page == "home":
            render_home_page()
        
        elif st.session_state.page == "teacher_attendance":
            if st.session_state.user_role == "teacher":
                render_teacher_attendance()
            else:
                st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
                st.session_state.page = "home"
                st.rerun()
        
        elif st.session_state.page == "student_dashboard":
            if st.session_state.user_role == "student":
                render_student_dashboard()
            else:
                st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
                st.session_state.page = "home"
                st.rerun()
        
        elif st.session_state.page == "reports":
            if st.session_state.user_role == "teacher":
                render_reports_page()
            else:
                st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
                st.session_state.page = "home"
                st.rerun()
        
        elif st.session_state.page == "students":
            if st.session_state.user_role == "teacher":
                render_students_page()
            else:
                st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
                st.session_state.page = "home"
                st.rerun()
        
        elif st.session_state.page == "my_records":
            if st.session_state.user_role == "student":
                render_my_records_page()
            else:
                st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
                st.session_state.page = "home"
                st.rerun()
        
        elif st.session_state.page == "settings":
            render_settings_page()
        
        else:
            st.session_state.page = "home"
            st.rerun()
    
    # تذييل الصفحة
    st.markdown("""
    <div class="footer">
        <div style="display: flex; justify-content: center; gap: 30px; margin-bottom: 10px;">
            <div style="color: #64748b;">📧 support@school.edu</div>
            <div style="color: #64748b;">📞 01234567890</div>
            <div style="color: #64748b;">🏫 مدرسة الإبداع</div>
        </div>
        <div style="color: #94a3b8; font-size: 12px;">
            نظام إدارة الغياب الإلكتروني © 2024 | النسخة {version}
        </div>
    </div>
    """.format(version=APP_VERSION), unsafe_allow_html=True)

# تشغيل التطبيق
if __name__ == "__main__":
    main()
