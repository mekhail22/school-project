import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import json
import logging
import base64
import requests
import sys
import urllib.request
import tempfile

# Arabic/RTL PDF support
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

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

# ------------------ تحميل الخطوط العربية ------------------
def download_arabic_font():
    """تحميل الخط العربي إذا لم يكن موجوداً"""
    font_path = "NotoNaskhArabic-Regular.ttf"
    
    if not os.path.exists(font_path):
        try:
            temp_dir = tempfile.gettempdir()
            temp_font_path = os.path.join(temp_dir, "NotoNaskhArabic-Regular.ttf")
            
            font_urls = [
                "https://raw.githubusercontent.com/googlefonts/noto-fonts/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf",
                "https://fonts.gstatic.com/ea/notonaskharabic/v6/NotoNaskhArabic-Regular.ttf"
            ]
            
            for url in font_urls:
                try:
                    logger.info(f"محاولة تحميل الخط من: {url}")
                    urllib.request.urlretrieve(url, temp_font_path)
                    
                    import shutil
                    shutil.copy(temp_font_path, font_path)
                    logger.info(f"✅ تم تحميل الخط العربي بنجاح")
                    return True
                except Exception as e:
                    logger.warning(f"فشل التحميل من {url}: {e}")
                    continue
            
            logger.error("❌ فشل تحميل الخط العربي")
            return False
        except Exception as e:
            logger.error(f"❌ خطأ في تحميل الخط: {e}")
            return False
    return True

# تحميل الخط
download_arabic_font()

# ------------------ App settings ------------------
# قائمة الطلاب مقسمة على 4 فصول (40 طالب - 10 لكل فصل)
CLASSES = {
    "Class B": [
        "محمد علي محمد", "حسن أحمد حسن", "محمود حسين محمود", "كريم سعيد كريم",
        "أمين خالد أمين", "ياسين رفعت ياسين", "عمر وليد عمر", "سعيد حامد سعيد",
        "نبيل جمال نبيل", "جمال هشام جمال"
    ],
    "Class C": [
        "أحمد محمد أحمد", "محمود سعيد حسين", "علي كمال علي", "يوسف خالد يوسف",
        "خالد أمين خالد", "سامي رفعت سامي", "طارق وليد طارق", "مصطفى حامد مصطفى",
        "هشام نبيل هشام", "وليد جمال وليد"
    ],
    "Class D": [
        "فؤاد محمد فؤاد", "رشاد أحمد رشاد", "صابر حسين صابر", "عادل سعيد عادل",
        "فكري خالد فكري", "رأفت رفعت رأفت", "حسام وليد حسام", "عاطف حامد عاطف",
        "مجدي جمال مجدي", "سليمان هشام سليمان"
    ],
    "Class E": [
        "نبيل محمد نبيل", "رامي أحمد رامي", "عماد حسين عماد", "صلاح سعيد صلاح",
        "مجد خالد مجد", "رافت رفعت رافت", "بسام وليد بسام", "كمال حامد كمال",
        "فاروق جمال فاروق", "أنور هشام أنور"
    ]
}

# إنشاء قاموس عكسي للبحث عن الفصل من اسم الطالب
STUDENT_TO_CLASS = {}
for class_name, students in CLASSES.items():
    for student in students:
        STUDENT_TO_CLASS[student] = class_name

# جميع الطلاب في قائمة واحدة
ALL_STUDENTS = []
for class_name, students in CLASSES.items():
    ALL_STUDENTS.extend(students)

# قائمة المعلمين والفصول التي يدرسونها
TEACHER_CLASSES = {
    "مينا سمير": ["Class B", "Class C"],
    "فادي حبيب": ["Class D", "Class E"]
}

# مستخدمون وكلمات مرورهم (كل مستخدم له كلمة مرور مختلفة)
USERS = {
    # مدير النظام
    "admin": {
        "password": "admin1234",
        "role": "admin",
        "admin_name": "مدير النظام"
    },
    # معلمون - لهم صلاحية تسجيل الغياب
    "مينا سمير": {
        "password": "mina1234",
        "role": "teacher",
        "teacher_name": "مينا سمير",
        "classes": ["Class B", "Class C"]
    },
    "فادي حبيب": {
        "password": "fady5678",
        "role": "teacher",
        "teacher_name": "فادي حبيب",
        "classes": ["Class D", "Class E"]
    },
}

# إضافة الطلاب مع كلمات مرور مختلفة لكل طالب
student_passwords = {
    # Class C
    "أحمد محمد أحمد": "c1001",
    "محمود سعيد حسين": "c1002",
    "علي كمال علي": "c1003",
    "يوسف خالد يوسف": "c1004",
    "خالد أمين خالد": "c1005",
    "سامي رفعت سامي": "c1006",
    "طارق وليد طارق": "c1007",
    "مصطفى حامد مصطفى": "c1008",
    "هشام نبيل هشام": "c1009",
    "وليد جمال وليد": "c1010",
    
    # Class B
    "محمد علي محمد": "b1001",
    "حسن أحمد حسن": "b1002",
    "محمود حسين محمود": "b1003",
    "كريم سعيد كريم": "b1004",
    "أمين خالد أمين": "b1005",
    "ياسين رفعت ياسين": "b1006",
    "عمر وليد عمر": "b1007",
    "سعيد حامد سعيد": "b1008",
    "نبيل جمال نبيل": "b1009",
    "جمال هشام جمال": "b1010",
    
    # Class D
    "فؤاد محمد فؤاد": "d1001",
    "رشاد أحمد رشاد": "d1002",
    "صابر حسين صابر": "d1003",
    "عادل سعيد عادل": "d1004",
    "فكري خالد فكري": "d1005",
    "رأفت رفعت رأفت": "d1006",
    "حسام وليد حسام": "d1007",
    "عاطف حامد عاطف": "d1008",
    "مجدي جمال مجدي": "d1009",
    "سليمان هشام سليمان": "d1010",
    
    # Class E
    "نبيل محمد نبيل": "e1001",
    "رامي أحمد رامي": "e1002",
    "عماد حسين عماد": "e1003",
    "صلاح سعيد صلاح": "e1004",
    "مجد خالد مجد": "e1005",
    "رافت رفعت رافت": "e1006",
    "بسام وليد بسام": "e1007",
    "كمال حامد كمال": "e1008",
    "فاروق جمال فاروق": "e1009",
    "أنور هشام أنور": "e1010",
}

# إضافة الطلاب إلى USERS
for student in ALL_STUDENTS:
    if student in student_passwords:
        USERS[student] = {
            "password": student_passwords[student],
            "role": "student",
            "student_name": student
        }
    else:
        USERS[student] = {
            "password": f"stu{hash(student) % 10000:04d}",
            "role": "student",
            "student_name": student
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

# محاولة الاتصال بـ Google Sheets
def connect_to_google_sheets():
    global worksheet, connection_status
    
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
                    # قراءة صف واحد فقط للاختبار
                    test_row = worksheet.row_values(1) if worksheet.row_count > 0 else []
                    
                    # إذا كانت الورقة جديدة، أضف العناوين
                    if not test_row or len(test_row) < 3:
                        headers = ["student", "teacher", "class", "status", "date"]
                        worksheet.append_row(headers)
                        logger.info("✅ تمت إضافة عناوين الأعمدة")
                    
                    connection_status = "✅ متصل"
                    logger.info(f"✅ اتصال ناجح بـ Google Sheets: {SHEET_NAME}")
                    return True
                    
                except Exception as e:
                    connection_status = f"✅ متصل ولكن خطأ في القراءة: {str(e)}"
                    logger.error(f"❌ خطأ في القراءة: {e}")
                    return False
                    
            except gspread.exceptions.SpreadsheetNotFound:
                connection_status = f"❌ لم يتم العثور على Sheet: {SHEET_NAME}"
                logger.error(f"❌ لم يتم العثور على الورقة: {SHEET_NAME}")
                return False
                
            except Exception as e:
                connection_status = f"❌ خطأ في فتح الـ Sheet: {str(e)}"
                logger.error(f"❌ خطأ في فتح الورقة: {e}")
                return False
                
        except Exception as e:
            connection_status = f"❌ فشل في المصادقة: {str(e)}"
            logger.error(f"❌ فشل في المصادقة: {e}")
            return False
    else:
        connection_status = "❌ إعدادات الاتصال غير كاملة"
        logger.error("❌ SERVICE_ACCOUNT غير موجود أو غير مكتمل")
        return False

# محاولة الاتصال
connect_to_google_sheets()

# ------------------ إعداد الخطوط لـ PDF ------------------
def setup_pdf_fonts():
    """إعداد الخطوط لملفات PDF"""
    try:
        # تسجيل الخط الإنجليزي
        try:
            pdfmetrics.registerFont(TTFont('Helvetica', 'Helvetica'))
            pdfmetrics.registerFont(TTFont('Helvetica-Bold', 'Helvetica-Bold'))
        except:
            pass
        
        # محاولة تسجيل الخط العربي
        arabic_font_loaded = False
        
        # قائمة بمسارات الخطوط العربية المحتملة
        arabic_font_paths = [
            "NotoNaskhArabic-Regular.ttf",
            "arial.ttf",
            "tahoma.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
        ]
        
        for font_path in arabic_font_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
                    arabic_font_loaded = True
                    logger.info(f"✅ تم تحميل الخط العربي من: {font_path}")
                    break
                else:
                    logger.info(f"⚠️ الخط غير موجود: {font_path}")
            except Exception as e:
                logger.error(f"❌ خطأ في تحميل الخط {font_path}: {e}")
                continue
        
        # إذا لم يتم تحميل أي خط عربي، استخدم الخط الإنجليزي
        if not arabic_font_loaded:
            logger.warning("⚠️ لم يتم تحميل خط عربي، سيتم استخدام الخط الإنجليزي")
            pdfmetrics.registerFont(TTFont('ArabicFont', 'Helvetica'))
        
        return arabic_font_loaded
        
    except Exception as e:
        logger.error(f"❌ خطأ في إعداد الخطوط: {e}")
        return False

# إعداد الخطوط
pdf_fonts_loaded = setup_pdf_fonts()

# Helper functions
def reshape_arabic_text(text):
    """تكوين النص العربي للعرض الصحيح"""
    try:
        if not text:
            return ""
        
        text_str = str(text)
        
        # إذا كان النص فارغاً أو إنجليزي فقط، لا تقم بتكوينه
        if not text_str or all(ord(char) < 128 for char in text_str):
            return text_str
        
        try:
            # تكوين النص العربي
            reshaped = arabic_reshaper.reshape(text_str)
            bidi_text = get_display(reshaped)
            return bidi_text
        except Exception as e:
            logger.warning(f"⚠️ خطأ في تكوين النص العربي: {e}")
            return text_str
    except Exception as e:
        logger.error(f"❌ خطأ في reshape_arabic_text: {e}")
        return str(text) if text else ""

def is_arabic_text(text):
    """التحقق إذا كان النص عربي"""
    try:
        text_str = str(text)
        # تحقق إذا كان يحتوي على أحرف عربية
        arabic_chars = any('\u0600' <= char <= '\u06FF' for char in text_str)
        return arabic_chars
    except:
        return False

def get_font_for_text(text):
    """الحصول على الخط المناسب للنص"""
    try:
        if is_arabic_text(text):
            return 'ArabicFont'
        else:
            return 'Helvetica'  
    except:
        return 'Helvetica'
    
def read_sheet():
    """قراءة البيانات من Google Sheets"""
    if worksheet is None:
        logger.error("❌ لا يوجد اتصال بـ Google Sheets")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    try:
        # محاولة قراءة البيانات
        data = worksheet.get_all_records()
        logger.info(f"✅ تم قراءة {len(data)} سجل من Google Sheets")
        
        if not data:
            return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
        
        df = pd.DataFrame(data)
        
        # التأكد من وجود جميع الأعمدة المطلوبة
        required_columns = ["student", "teacher", "class", "status", "date"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = ""
                logger.warning(f"⚠️ العمود {col} غير موجود في البيانات")
        
        # تنظيف البيانات
        for col in required_columns:
            if col in df.columns:
                df[col] = df[col].fillna("").astype(str).str.strip()
        
        return df
        
    except Exception as e:
        logger.error(f"❌ خطأ في قراءة البيانات من Google Sheets: {str(e)}")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])

def write_sheet(df):
    """كتابة البيانات إلى Google Sheets"""
    if worksheet is None:
        return False
    
    try:
        # تنظيف البيانات قبل الحفظ
        df = df.copy()
        for col in ["student", "teacher", "class", "status", "date"]:
            if col not in df.columns:
                df[col] = ""
        
        # تحويل إلى قائمة
        data = [df.columns.tolist()] + df.values.tolist()
        
        # مسح الورقة ثم إضافة البيانات الجديدة
        worksheet.clear()
        worksheet.update('A1', data)
        return True
    except Exception as e:
        st.error(f"خطأ في حفظ البيانات: {str(e)}")
        return False

def normalize_date_for_pdf(src_date_str):
    """تنسيق التاريخ لملف PDF"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    
    s = str(src_date_str).strip()
    
    # إذا كان التاريخ بالفعل بالصيغة الصحيحة
    if " / " in s:
        return s
    
    # محاولة تحليل التاريخ
    try:
        if date_parse:
            dt = date_parse(s, dayfirst=False, yearfirst=False)
            return f"{dt.day:02d} / {dt.month:02d} / {dt.year}"
    except:
        pass
    
    # محاولة التحليل اليدوي
    try:
        # تنسيق dd/mm/yyyy
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
        
        # تنسيق dd-mm-yyyy
        elif "-" in s:
            parts = s.split("-")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
    except:
        pass
    
    # إذا فشل كل شيء، ارجع النص الأصلي
    return s

def normalize_date_for_display(src_date_str):
    """معالجة التاريخ للعرض في الجداول"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    
    s = str(src_date_str).strip()
    
    # إذا كان التاريخ بالفعل بالصيغة الصحيحة
    if " / " in s:
        return s
    
    # محاولة تحليل التاريخ
    try:
        if date_parse:
            dt = date_parse(s, dayfirst=False, yearfirst=False)
            return f"{dt.day:02d} / {dt.month:02d} / {dt.year}"
    except:
        pass
    
    # محاولة التحليل اليدوي
    try:
        # تنسيق dd/mm/yyyy
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
        
        # تنسيق dd-mm-yyyy
        elif "-" in s:
            parts = s.split("-")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
    except:
        pass
    
    # إذا فشل كل شيء، ارجع النص الأصلي
    return s

def get_student_class(student_name):
    """الحصول على فصل الطالب تلقائياً"""
    return STUDENT_TO_CLASS.get(student_name, "")

def get_class_statistics(class_name):
    """الحصول على إحصائيات الفصل"""
    df = read_sheet()
    
    if df.empty or "class" not in df.columns:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # تصفية البيانات للفصل المحدد
    class_df = df[df["class"] == class_name].copy()
    
    if class_df.empty:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # حساب الإحصائيات
    total_records = len(class_df)
    present_count = len(class_df[class_df["status"] == "حاضر"])
    absent_count = len(class_df[class_df["status"].str.contains("غياب", na=False)])
    
    # حساب نسبة الحضور
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    # إحصائيات لكل طالب
    student_stats = []
    class_students = CLASSES.get(class_name, [])
    
    for student in class_students:
        student_df = class_df[class_df["student"] == student]
        student_total = len(student_df)
        student_present = len(student_df[student_df["status"] == "حاضر"])
        student_absent = len(student_df[student_df["status"].str.contains("غياب", na=False)])
        student_rate = (student_present / student_total * 100) if student_total > 0 else 0
        
        student_stats.append({
            "name": student,
            "total": student_total,
            "present": student_present,
            "absent": student_absent,
            "rate": student_rate
        })
    
    return {
        "total_students": len(class_students),
        "total_records": total_records,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_rate": attendance_rate,
        "students": student_stats
    }

def get_class_attendance_history(class_name):
    """الحصول على سجل الحضور للفصل"""
    df = read_sheet()
    
    if df.empty or "class" not in df.columns:
        return pd.DataFrame()
    
    # تصفية البيانات للفصل المحدد
    class_df = df[df["class"] == class_name].copy()
    
    if class_df.empty:
        return pd.DataFrame()
    
    # تنظيف البيانات
    class_df = class_df.copy()
    class_df["date_clean"] = class_df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        return status_str
    
    class_df["status_clean"] = class_df["status"].apply(clean_status)
    
    # ترتيب حسب التاريخ
    class_df = class_df.sort_values("date", ascending=False)
    
    return class_df[["student", "teacher", "date_clean", "status_clean"]] 

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

def record_attendance(selected_absent, teacher_name, class_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    
    # الحصول على جميع طلاب الفصل المحدد
    class_students = CLASSES.get(class_name, [])
    
    # تسجيل جميع طلاب الفصل
    for student in class_students:
        # تحديد حالة الطالب
        if student in selected_absent:
            # إذا كان الطالب في قائمة الغائبين
            status = absent_label
        else:
            # إذا لم يكن في القائمة، فهو حاضر
            status = "حاضر"
        
        # الحصول على فصل الطالب تلقائياً من القاموس
        student_class = get_student_class(student)
        rows.append([student, teacher_name, student_class, status, date_display])
    
    failed = []
    success_count = 0
    
    # حفظ في Google Sheets إذا كان متصلاً
    if worksheet and rows:  # فقط إذا كان هناك صفوف للحفظ
        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
            logger.info(f"✅ تم حفظ {success_count} سجل في Google Sheets")
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
                logger.info(f"✅ تم حفظ {success_count} سجل في Google Sheets (واحداً تلو الآخر)")
            except Exception as ex:
                failed.append((f"الفصل {class_name}", str(ex)))
                logger.error(f"❌ فشل في حفظ البيانات: {ex}")
    elif rows:  # إذا كان هناك صفوف ولكن لا يوجد اتصال
        failed.append((f"الفصل {class_name}", "لا يوجد اتصال بـ Google Sheets"))
        logger.error("❌ لا يوجد اتصال بـ Google Sheets")
    
    # رسالة تلغرام
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if rows:  # فقط إذا كان هناك صفوف (وهذا يعني دائماً يوجد صفوف لأننا نسجل جميع الطلاب)
        absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
        
        # حساب عدد الحاضرين
        present_count = len(class_students) - len(selected_absent)
        
        # رسالة معدلة بدون ذكر عدد السجلات المحفوظة
        message = f"📋 تسجيل الغياب\n📅 التاريخ: {date_display}\n👨‍🏫 المعلم: {teacher_name}\n🏫 الفصل: {class_name}\n❌ عدد الغائبين: {len(selected_absent)}\n✅ عدد الحاضرين: {present_count}\n👥 الطلاب الغائبون: {absent_students}"
        
        if BOT_TOKEN and CHAT_ID:
            ok, info = send_telegram_message(message)
            if ok:
                telegram_status = "✅ تم الإرسال بنجاح"
                telegram_details = "تم إرسال الإشعار إلى Telegram"
                logger.info("✅ تم إرسال رسالة Telegram")
            else:
                telegram_status = "❌ فشل الإرسال"
                telegram_details = f"تفاصيل الخطأ: {info}"
                logger.error(f"❌ فشل إرسال Telegram: {info}")
        else:
            telegram_status = "⚠️ إعدادات Telegram غير مكتملة"
            logger.warning("⚠️ إعدادات Telegram غير مكتملة")
    else:
        telegram_status = "لم يتم الإرسال (لا يوجد طلاب)"
        telegram_details = "لم يتم إرسال رسالة لأن لا يوجد طلاب في الفصل"
        logger.warning("⚠️ لا يوجد طلاب في الفصل")
    
    return failed, telegram_status, telegram_details, success_count

def get_student_records(student_name):
    df = read_sheet()
    if "student" not in df.columns or df.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])
    
    try:
        # البحث بدقة أكبر - مطابقة كاملة للاسم
        df_matches = df[df["student"].astype(str).str.strip() == student_name.strip()].copy()
    except Exception:
        # إذا فشلت، حاول البحث الجزئي
        try:
            df_matches = df[df["student"].astype(str).str.contains(student_name.strip(), case=False, na=False)].copy()
        except Exception:
            df_matches = pd.DataFrame(columns=df.columns)
    
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])
    
    # تنظيف البيانات
    df_matches = df_matches.copy()
    
    # التأكد من وجود جميع الأعمدة
    for col in ["teacher", "class", "date", "status"]:
        if col not in df_matches.columns:
            df_matches[col] = ""
    
    # إصلاح البيانات المختلطة
    def fix_mixed_data(row):
        # إذا كان التاريخ في خانة الفصل
        if pd.notna(row.get("class")) and "/" in str(row.get("class")) and "غياب" not in str(row.get("class")) and "حاضر" not in str(row.get("class")):
            if pd.isna(row.get("date")) or str(row.get("date")).strip() == "":
                row["date"] = row["class"]
                row["class"] = get_student_class(row["student"])
        
        # إذا كانت الحالة في خانة التاريخ
        if pd.notna(row.get("date")) and ("غياب" in str(row.get("date")) or "حاضر" in str(row.get("date"))):
            if pd.isna(row.get("status")) or str(row.get("status")).strip() == "":
                row["status"] = row["date"]
                row["date"] = ""
        
        # إذا كان الفصل فارغاً، نضيفه من اسم الطالب
        if pd.isna(row.get("class")) or str(row.get("class")).strip() == "":
            row["class"] = get_student_class(row["student"])
        
        return row
    
    # تطبيق إصلاح البيانات
    df_matches = df_matches.apply(fix_mixed_data, axis=1)
    
    # تنظيف الحالة - جعل "غياب بعذر" تظهر كـ "غياب"
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        return status_str
    
    df_matches["status_clean"] = df_matches["status"].apply(clean_status)
    df_matches["date_clean"] = df_matches["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    
    # إعادة ترتيب الصفوف
    df_matches = df_matches.sort_values("date", ascending=False)
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    
    # إعادة تسمية الأعمدة
    df_matches = df_matches.rename(columns={
        "student": "الطالب", 
        "teacher": "المعلم", 
        "class": "الفصل", 
        "date_clean": "التاريخ",
        "status_clean": "الحالة"
    })
    
    return df_matches[["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"]]

# ================== إصلاح دالة إنشاء ملفات PDF ==================
def create_pdf_styles():
    """إنشاء أنماط النصوص لملفات PDF"""
    styles = getSampleStyleSheet()
    
    # الحصول على الخطوط المتاحة
    available_fonts = pdfmetrics.getRegisteredFontNames()
    arabic_font = 'ArabicFont' if 'ArabicFont' in available_fonts else 'Helvetica'
    
    # نمط العنوان الرئيسي
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName=arabic_font,
        fontSize=22,
        alignment=1,  # مركز
        textColor=colors.darkblue,
        spaceAfter=20
    )
    
    # نمط العنوان الفرعي
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Heading2'],
        fontName=arabic_font,
        fontSize=16,
        alignment=1,  # مركز
        textColor=colors.navy,
        spaceAfter=12
    )
    
    # نمط النص العربي العادي
    normal_arabic_style = ParagraphStyle(
        'NormalArabic',
        parent=styles['Normal'],
        fontName=arabic_font,
        fontSize=12,
        alignment=2,  # يمين
        spaceAfter=6
    )
    
    # نمط النص الإنجليزي العادي
    normal_english_style = ParagraphStyle(
        'NormalEnglish',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        alignment=0,  # يسار للنص الإنجليزي
        spaceAfter=6
    )
    
    # نمط التذييل
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontName=arabic_font,
        fontSize=10,
        alignment=2,  # يمين
        textColor=colors.darkblue,
        spaceAfter=6
    )
    
    return {
        'title': title_style,
        'subtitle': subtitle_style,
        'normal_arabic': normal_arabic_style,
        'normal_english': normal_english_style,
        'footer': footer_style
    }

def generate_system_report_pdf():
    """إنشاء تقرير PDF شامل للنظام"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # الحصول على الأنماط
    styles = create_pdf_styles()
    
    # صفحة الغلاف
    title_text = reshape_arabic_text("تقرير شامل لنظام الغياب")
    elements.append(Paragraph(title_text, styles['title']))
    elements.append(Spacer(1, 20))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    date_text = reshape_arabic_text(f"تاريخ التقرير: {current_date}")
    elements.append(Paragraph(date_text, styles['normal_arabic']))
    elements.append(Spacer(1, 20))
    
    # الإحصائيات العامة
    stats_title = reshape_arabic_text("الإحصائيات العامة للنظام")
    elements.append(Paragraph(stats_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    df_all = read_sheet()
    total_records = len(df_all) if not df_all.empty else 0
    
    # جدول الإحصائيات العامة
    stats_data = [
        [reshape_arabic_text("عدد الطلاب"), str(len(ALL_STUDENTS))],
        [reshape_arabic_text("عدد الفصول"), str(len(CLASSES))],
        [reshape_arabic_text("عدد المعلمين"), str(len(TEACHER_CLASSES))],
        [reshape_arabic_text("إجمالي سجلات الغياب"), str(total_records)]
    ]
    
    stats_table = Table(stats_data, colWidths=[200, 100])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
    ]))
    elements.append(stats_table)
    
    elements.append(PageBreak())
    
    # تفاصيل الفصول
    classes_title = reshape_arabic_text("تفاصيل الفصول")
    elements.append(Paragraph(classes_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    for class_name, students in CLASSES.items():
        # إحصائيات الفصل
        stats = get_class_statistics(class_name)
        
        # معلومات الفصل
        class_info = reshape_arabic_text(f"الفصل: {class_name}")
        elements.append(Paragraph(class_info, styles['normal_arabic']))
        elements.append(Spacer(1, 5))
        
        # جدول إحصائيات الفصل
        class_stats_data = [
            [reshape_arabic_text("عدد الطلاب"), str(len(students))],
            [reshape_arabic_text("عدد السجلات"), str(stats["total_records"])],
            [reshape_arabic_text("نسبة الحضور"), f"{stats['attendance_rate']:.1f}%"],
            [reshape_arabic_text("المعلم المسؤول"), 
             ', '.join([reshape_arabic_text(k) for k, v in TEACHER_CLASSES.items() if class_name in v]) or reshape_arabic_text('غير معين')]
        ]
        
        class_stats_table = Table(class_stats_data, colWidths=[150, 100])
        class_stats_table.setStyle(TableStyle([
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
        ]))
        elements.append(class_stats_table)
        
        elements.append(Spacer(1, 10))
    
    elements.append(PageBreak())
    
    # معلومات المعلمين
    teachers_title = reshape_arabic_text("معلومات المعلمين")
    elements.append(Paragraph(teachers_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    for teacher, classes in TEACHER_CLASSES.items():
        teacher_name = reshape_arabic_text(f"المعلم: {teacher}")
        elements.append(Paragraph(teacher_name, styles['normal_arabic']))
        elements.append(Spacer(1, 5))
        
        classes_text = reshape_arabic_text(f"الفصول المسؤول عنها: {', '.join(classes)}")
        elements.append(Paragraph(classes_text, styles['normal_arabic']))
        
        # حساب إحصائيات كل فصل يدرسه المعلم
        for class_name in classes:
            stats = get_class_statistics(class_name)
            class_stats_text = reshape_arabic_text(f"  - {class_name}: {stats['total_records']} سجل، نسبة الحضور: {stats['attendance_rate']:.1f}%")
            elements.append(Paragraph(class_stats_text, 
                                     ParagraphStyle('Indent', fontName='ArabicFont', fontSize=11, alignment=2, leftIndent=20)))
        
        elements.append(Spacer(1, 10))
    
    # الصفحة الأخيرة
    elements.append(Spacer(1, 20))
    notes_title = reshape_arabic_text("ملاحظات:")
    elements.append(Paragraph(notes_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    note1 = reshape_arabic_text("• هذا التقرير تم إنشاؤه تلقائياً من نظام الغياب الإلكتروني.")
    elements.append(Paragraph(note1, styles['normal_arabic']))
    
    note2 = reshape_arabic_text("• البيانات محدثة حتى تاريخ إنشاء التقرير.")
    elements.append(Paragraph(note2, styles['normal_arabic']))
    
    note3 = reshape_arabic_text("• يمكن للمدير الوصول إلى البيانات التفصيلية من لوحة التحكم.")
    elements.append(Paragraph(note3, styles['normal_arabic']))
    
    elements.append(Spacer(1, 20))
    signature_title = reshape_arabic_text("توقيع مدير النظام:")
    elements.append(Paragraph(signature_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("________________________"), styles['normal_arabic']))
    elements.append(Spacer(1, 5))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), styles['footer']))
    
    try:
        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء تقرير النظام: {e}")
        return None

def generate_class_full_report(class_name, teacher_name, stats, history_df):
    """إنشاء تقرير PDF لفصل معين"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # الحصول على الأنماط
    styles = create_pdf_styles()
    
    # صفحة الغلاف
    title_text = reshape_arabic_text("تقرير الغياب الشامل")
    elements.append(Paragraph(title_text, styles['title']))
    elements.append(Spacer(1, 20))
    
    elements.append(Spacer(1, 10))
    teacher_text = reshape_arabic_text(f"المعلم: {teacher_name}")
    elements.append(Paragraph(teacher_text, styles['normal_arabic']))
    elements.append(Spacer(1, 10))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    date_text = reshape_arabic_text(f"تاريخ التقرير: {current_date}")
    elements.append(Paragraph(date_text, styles['normal_arabic']))
    elements.append(Spacer(1, 20))
    
    # الإحصائيات العامة
    stats_title = reshape_arabic_text("الإحصائيات العامة")
    elements.append(Paragraph(stats_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    # جدول الإحصائيات
    stats_data = [
        [reshape_arabic_text("عدد الطلاب"), str(stats["total_students"])],
        [reshape_arabic_text("إجمالي السجلات"), str(stats["total_records"])],
        [reshape_arabic_text("عدد الحضور"), str(stats["present_count"])],
        [reshape_arabic_text("عدد الغياب"), str(stats["absent_count"])],
        [reshape_arabic_text("نسبة الحضور"), f"{stats['attendance_rate']:.1f}%"]
    ]
    
    stats_table = Table(stats_data, colWidths=[150, 100])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
    ]))
    elements.append(stats_table)
    
    elements.append(PageBreak())
    
    # إحصائيات الطلاب
    students_title = reshape_arabic_text("إحصائيات الطلاب")
    elements.append(Paragraph(students_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    if stats["students"]:
        # جدول تفصيلي للطلاب
        student_header = [
            reshape_arabic_text("اسم الطالب"),
            reshape_arabic_text("عدد السجلات"),
            reshape_arabic_text("الحضور"),
            reshape_arabic_text("الغياب"),
            reshape_arabic_text("نسبة الحضور %")
        ]
        
        student_data = [student_header]
        for student in stats["students"]:
            student_data.append([
                reshape_arabic_text(student["name"]),
                str(student["total"]),
                str(student["present"]),
                str(student["absent"]),
                f"{student['rate']:.1f}%"
            ])
        
        student_table = Table(student_data, colWidths=[150, 70, 60, 60, 80])
        student_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
        ]))
        elements.append(student_table)
    
    elements.append(PageBreak())
    
    # سجل الحضور
    history_title = reshape_arabic_text("سجل الحضور التفصيلي")
    elements.append(Paragraph(history_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    if not history_df.empty:
        history_header = [
            reshape_arabic_text("الطالب"),
            reshape_arabic_text("المعلم"),
            reshape_arabic_text("التاريخ"),
            reshape_arabic_text("الحالة")
        ]
        
        history_data = [history_header]
        for _, row in history_df.iterrows():
            history_data.append([
                reshape_arabic_text(str(row.get("student", ""))),
                reshape_arabic_text(str(row.get("teacher", ""))),
                reshape_arabic_text(normalize_date_for_pdf(row.get("date_clean", ""))),
                reshape_arabic_text(str(row.get("status_clean", "")))
            ])
        
        history_table = Table(history_data, colWidths=[150, 100, 100, 80])
        history_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ]))
        elements.append(history_table)
    else:
        no_data_text = reshape_arabic_text("لا توجد سجلات حضرور لهذا الفصل بعد.")
        elements.append(Paragraph(no_data_text, styles['normal_arabic']))
    
    # الصفحة الأخيرة - التوقيعات
    elements.append(PageBreak())
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("توقيع المعلم:"), styles['subtitle']))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), styles['normal_arabic']))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text(f"{teacher_name}"), styles['normal_arabic']))
    
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("توقيع مدير المدرسة:"), styles['subtitle']))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), styles['normal_arabic']))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("مدير مدرسة السلام الإعدادية الثانويه المشتركه"), styles['normal_arabic']))
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), styles['footer']))
    
    try:
        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء تقرير الفصل: {e}")
        return None

def generate_student_pdf(student_name, df_records):
    """إنشاء تقرير PDF للطالب"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # الحصول على الأنماط
    styles = create_pdf_styles()
    
    # العنوان
    title_text = reshape_arabic_text("تقرير الغياب")
    elements.append(Paragraph(title_text, styles['title']))
    elements.append(Spacer(1, 8))
    
    # معلومات الطالب
    student_info = reshape_arabic_text(f"الاسم: {student_name}")
    elements.append(Paragraph(student_info, styles['normal_arabic']))
    elements.append(Spacer(1, 8))

    if df_records.empty:
        no_data_text = reshape_arabic_text("لا توجد سجلات لهذا الطالب.")
        elements.append(Paragraph(no_data_text, styles['normal_arabic']))
    else:
        # حساب الغياب بغض النظر عن نوعه
        absent_count = int((df_records["الحالة"] == "غياب").sum())
        present_count = int((df_records["الحالة"] == "حاضر").sum())
        total_count = len(df_records)
        
        # إحصائيات
        stats1 = reshape_arabic_text(f"عدد مرات الغياب: {absent_count}")
        elements.append(Paragraph(stats1, styles['normal_arabic']))
        
        stats2 = reshape_arabic_text(f"عدد مرات الحضور: {present_count}")
        elements.append(Paragraph(stats2, styles['normal_arabic']))
        
        stats3 = reshape_arabic_text(f"إجمالي عدد السجلات: {total_count}")
        elements.append(Paragraph(stats3, styles['normal_arabic']))
        
        if total_count > 0:
            attendance_rate = (present_count / total_count) * 100
            stats4 = reshape_arabic_text(f"نسبة الحضور: {attendance_rate:.1f}%")
            elements.append(Paragraph(stats4, styles['normal_arabic']))
        
        elements.append(Spacer(1, 10))

        # جدول السجلات
        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"]]
        data = [header]
        
        for _, row in df_records.iterrows():
            row_data = [
                str(row.get("المرة", "")),
                reshape_arabic_text(str(row.get("الطالب", ""))),
                reshape_arabic_text(str(row.get("المعلم", ""))),
                str(row.get("الفصل", "")),
                reshape_arabic_text(normalize_date_for_pdf(row.get("التاريخ", ""))),
                reshape_arabic_text(str(row.get("الحالة", "")))
            ]
            data.append(row_data)
        
        table = Table(data, hAlign='CENTER', colWidths=[40, 130, 100, 80, 100, 70])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
        ]))
        elements.append(table)

    elements.append(Spacer(1, 14))
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    footer_text = reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date}")
    elements.append(Paragraph(footer_text, styles['footer']))
    
    try:
        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء تقرير الطالب: {e}")
        return None

def generate_teachers_report_pdf():
    """إنشاء تقرير PDF للمعلمين"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # الحصول على الأنماط
    styles = create_pdf_styles()
    
    # صفحة الغلاف
    title_text = reshape_arabic_text("تقرير المعلمين")
    elements.append(Paragraph(title_text, styles['title']))
    elements.append(Spacer(1, 20))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    date_text = reshape_arabic_text(f"تاريخ التقرير: {current_date}")
    elements.append(Paragraph(date_text, styles['normal_arabic']))
    elements.append(Spacer(1, 20))
    
    # معلومات المعلمين
    for teacher, classes in TEACHER_CLASSES.items():
        teacher_name = reshape_arabic_text(f"المعلم: {teacher}")
        elements.append(Paragraph(teacher_name, styles['subtitle']))
        elements.append(Spacer(1, 10))
        
        classes_text = reshape_arabic_text("الفصول المسؤول عنها:")
        elements.append(Paragraph(classes_text, styles['normal_arabic']))
        
        # عرض الفصول التي يدرسها المعلم
        for class_name in classes:
            # الحصول على إحصائيات الفصل
            stats = get_class_statistics(class_name)
            class_students = CLASSES.get(class_name, [])
            
            # معلومات الفصل
            class_info = reshape_arabic_text(f"الفصل: {class_name}")
            elements.append(Paragraph(class_info, styles['normal_arabic']))
            
            # جدول إحصائيات الفصل
            class_stats_data = [
                [reshape_arabic_text("عدد الطلاب"), str(len(class_students))],
                [reshape_arabic_text("عدد السجلات"), str(stats["total_records"])],
                [reshape_arabic_text("الحضور"), str(stats["present_count"])],
                [reshape_arabic_text("الغياب"), str(stats["absent_count"])],
                [reshape_arabic_text("نسبة الحضور"), f"{stats['attendance_rate']:.1f}%"]
            ]
            
            class_stats_table = Table(class_stats_data, colWidths=[80, 70])
            class_stats_table.setStyle(TableStyle([
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
            ]))
            elements.append(class_stats_table)
            
            elements.append(Spacer(1, 10))
        
        # فصل بين المعلمين
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(reshape_arabic_text("________________________________________"), styles['normal_arabic']))
        elements.append(Spacer(1, 15))
    
    # إحصائيات عامة
    elements.append(PageBreak())
    general_title = reshape_arabic_text("إحصائيات عامة")
    elements.append(Paragraph(general_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    # حساب إجماليات
    total_teachers = len(TEACHER_CLASSES)
    total_classes = len(CLASSES)
    total_students = len(ALL_STUDENTS)
    
    total_stats_data = [
        [reshape_arabic_text("إجمالي عدد المعلمين"), str(total_teachers)],
        [reshape_arabic_text("إجمالي عدد الفصول"), str(total_classes)],
        [reshape_arabic_text("إجمالي عدد الطلاب"), str(total_students)]
    ]
    
    total_stats_table = Table(total_stats_data, colWidths=[120, 80])
    total_stats_table.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 13),
        ('GRID', (0, 0), (-1, -1), 1, colors.gray),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    elements.append(total_stats_table)
    
    # الصفحة الأخيرة
    elements.append(Spacer(1, 30))
    notes_title = reshape_arabic_text("ملاحظات:")
    elements.append(Paragraph(notes_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    
    note1 = reshape_arabic_text("• هذا التقرير يوضح أداء المعلمين والفصول المسؤولين عنها.")
    elements.append(Paragraph(note1, styles['normal_arabic']))
    
    note2 = reshape_arabic_text("• النسب تعتمد على البيانات المسجلة في النظام حتى تاريخ التقرير.")
    elements.append(Paragraph(note2, styles['normal_arabic']))
    
    note3 = reshape_arabic_text("• يمكن تحديث البيانات من خلال لوحة تحكم المدير.")
    elements.append(Paragraph(note3, styles['normal_arabic']))
    
    elements.append(Spacer(1, 20))
    signature_title = reshape_arabic_text("توقيع مدير النظام:")
    elements.append(Paragraph(signature_title, styles['subtitle']))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("________________________"), styles['normal_arabic']))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), styles['footer']))
    
    try:
        doc.build(elements)
        buffer.seek(0)
        return buffer
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء تقرير المعلمين: {e}")
        return None
    

# باقي الكود لا يحتاج إلى تعديل كبير. فقط تأكد من أن CSS والأجزاء الأخرى كما هي.

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
        color: white !important;
    }
    .school-date { 
        font-size: 14px; 
        opacity: 0.9; 
        margin: 0; 
        color: rgba(255, 255, 255, 0.9) !important;
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
        color: white !important;
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
        color: white !important;
    }
    .user-type-badge {
        display: inline-block;
        padding: 6px 15px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 600;
        margin-left: 10px;
    }
    .badge-admin {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
    }
    .badge-teacher {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    .badge-student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
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
        color: white !important;
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
        color: white !important;
    }
    .main-button.teacher {
        background: linear-gradient(135deg, #10b981, #059669);
    }
    .main-button.student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
    }
    .main-button.admin {
        background: linear-gradient(135deg, #1e40af, #2563eb);
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
    /* تنسيقات المدير */
    .admin-page {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }
    .admin-card {
        background: white;
        border-radius: 15px;
        padding: 25px;
        margin: 15px 0;
        box-shadow: 0 5px 15px rgba(0,0,0,0.08);
        border: 2px solid #e2e8f0;
    }
    .admin-section-title {
        color: #1e40af !important;
        font-size: 24px !important;
        border-bottom: 3px solid #ddd6fe;
        padding-bottom: 10px;
        margin-bottom: 20px !important;
    }
    .admin-controls {
        display: flex;
        gap: 15px;
        margin: 20px 0;
        flex-wrap: wrap;
    }
    .admin-button {
        padding: 12px 25px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white !important;
        border: none;
        border-radius: 10px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
    }
    .admin-button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(37, 99, 235, 0.3);
    }
    .admin-button.delete {
        background: linear-gradient(135deg, #ef4444, #dc2626);
    }
    .admin-button.delete:hover {
        background: linear-gradient(135deg, #dc2626, #b91c1c);
    }
    .admin-button.success {
        background: linear-gradient(135deg, #10b981, #059669);
    }
    .admin-button.success:hover {
        background: linear-gradient(135deg, #059669, #047857);
    }
    .student-management-table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
    }
    .student-management-table th {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        padding: 15px;
        text-align: right;
        border: 1px solid #ddd;
    }
    .student-management-table td {
        padding: 12px 15px;
        border: 1px solid #ddd;
        text-align: right;
        background: white;
    }
    .student-management-table tr:nth-child(even) {
        background-color: #f9fafb;
    }
    .student-management-table tr:hover {
        background-color: #f3f4f6;
    }
    /* جميع أزرار Streamlit الأساسية - أزرق */
    .stButton > button {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* زر تسجيل الدخول */
    button[kind="primary"] {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
    }
    
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* زر تسجيل الغياب بلون أخضر */
    button.attendance-button {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important;
    }
    
    button.attendance-button:hover {
        background: linear-gradient(135deg, #059669, #047857) !important;
        color: white !important;
    }
    
    /* أزرار العودة - رمادي */
    button.back-button {
        background: linear-gradient(135deg, #64748b, #475569) !important;
        color: white !important;
    }
    
    button.back-button:hover {
        background: linear-gradient(135deg, #475569, #334155) !important;
        color: white !important;
    }
    
    /* زر تسجيل الخروج - أحمر */
    button.logout-button {
        background: linear-gradient(135deg, #ef4444, #dc2626) !important;
        color: white !important;
    }
    
    button.logout-button:hover {
        background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
        color: white !important;
    }
    
    /* أزرار التنزيل - أزرق */
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
    }
    
    div[data-testid="stDownloadButton"] button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* أزرار الفصول */
    .class-button {
        padding: 15px 30px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white !important;
        border: none;
        border-radius: 12px;
        font-size: 18px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
        min-width: 150px;
    }
    
    .class-button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(37, 99, 235, 0.3);
    }
    
    .student-list-container {
        max-height: 400px;
        overflow-y: auto;
        margin: 20px 0;
        padding: 15px;
        background: white;
        border-radius: 12px;
        border: 2px solid #e2e8f0;
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
    /* تحسين التبويبات */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #f1f5f9;
        padding: 8px;
        border-radius: 12px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: white;
        border-radius: 8px;
        padding: 10px 20px;
        font-weight: 600;
        border: 2px solid transparent;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
        border-color: #2563eb !important;
    }
</style>
""", unsafe_allow_html=True)

# Top toolbar HTML
def show_toolbar():
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">مدرسة السلام الإعدادية الثانويه المشتركه</p>
                <p class="school-date">{formatted_date}</p>
            </div>
        </div>
        <div></div> <!-- مساحة فارغة على اليمين -->
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# إدارة حالة تسجيل الدخول
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "page" not in st.session_state:
    st.session_state.page = "login"
if "selected_class" not in st.session_state:
    st.session_state.selected_class = None
if "teacher_mode" not in st.session_state:
    st.session_state.teacher_mode = None  # 'record' أو 'statistics'

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
                                placeholder="أدخل اسمك ",
                                label_visibility="collapsed")
        
        # حقل إدخال كلمة السر مع تسمية واضحة
        st.markdown('<div class="input-label">كلمة المرور</div>', unsafe_allow_html=True)
        password = st.text_input("كلمة المرور", type="password", 
                                placeholder="أدخل كلمة المرور الخاصة بك",
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
                        if USERS[username]["role"] == "admin":
                            st.session_state.page = "home"
                        elif USERS[username]["role"] == "teacher":
                            st.session_state.page = "home"
                            st.session_state.teacher_name = USERS[username]["teacher_name"]
                            st.session_state.teacher_classes = USERS[username]["classes"]
                            st.session_state.teacher_mode = None
                            st.session_state.selected_class = None
                        else:  # student
                            st.session_state.page = "home"
                            st.session_state.student_name = USERS[username]["student_name"]
                        
                        st.success(f"✅ مرحباً {username}!")
                        st.rerun()
                    else:
                        st.error("❌ كلمة المرور غير صحيحة")
                else:
                    st.error("❌ اسم المستخدم غير موجود")
            else:
                st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")

# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    show_toolbar()
    
    # الصفحة الرئيسية المشتركة
    if st.session_state.page == "home":
        st.markdown('<div class="home-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # عرض نوع المستخدم
        role_badge = ""
        if st.session_state.user_role == "admin":
            role_badge = '<span class="badge-admin">👑 مدير النظام</span>'
        elif st.session_state.user_role == "teacher":
            role_badge = '<span class="badge-teacher">👨‍🏫 معلم</span>'
        else:
            role_badge = '<span class="badge-student">👨‍🎓 طالب</span>'
        
        welcome_html = f"""
        <div class="welcome-message">
            <div class="welcome-text">مرحباً بك {role_badge} {st.session_state.user_name}</div>
            <div class="user-info">اختر المهمة التي تريد تنفيذها:</div>
        </div>
        """
        st.markdown(welcome_html, unsafe_allow_html=True)
        
        # أزرار المهام حسب نوع المستخدم
        if st.session_state.user_role == "admin":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("👑 لوحة التحكم", key="admin_dashboard", use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            with col2:
                if st.button("📊 مراجعة البيانات", key="admin_review", use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
                    
        elif st.session_state.user_role == "teacher":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 تسجيل الغياب", key="main_record", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "record"
                    st.session_state.selected_class = None
                    st.rerun()
            
            with col2:
                if st.button("📊 عرض الإحصائيات", key="main_stats", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "statistics"
                    st.session_state.selected_class = None
                    st.rerun()
        
        elif st.session_state.user_role == "student":
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", key="student_dashboard_btn", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        # زر تسجيل الخروج للجميع
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", key="logout_btn", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.session_state.teacher_classes = None
            st.session_state.page = "login"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة المعلم لتسجيل الغياب وعرض الإحصائيات
    elif st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        st.markdown('<div class="teacher-page">', unsafe_allow_html=True)
        
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        teacher_classes = st.session_state.get('teacher_classes', [])
        
        # إذا لم يتم اختيار فصل بعد، عرض أزرار الفصول
        if not st.session_state.selected_class:
            st.markdown('<div class="home-title">🎯 اختر الفصل</div>', unsafe_allow_html=True)
            
            # عرض اسم المعلم والفصول التي يدرسها
            st.markdown(f"### 👨‍🏫 المعلم: **{teacher_name}**")
            st.markdown(f"### 📚 اختر الفصل:")
            
            # عرض أزرار الفصول التي يدرسها المعلم فقط
            if teacher_classes:
                col1, col2 = st.columns(2)
                cols = [col1, col2]
                
                for idx, class_name in enumerate(teacher_classes):
                    with cols[idx % 2]:
                        if st.button(f"🎯 {class_name}", key=f"class_{class_name}", use_container_width=True):
                            st.session_state.selected_class = class_name
                            st.rerun()
            else:
                st.warning("⚠️ لا يوجد فصول موكلة إليك. الرجاء التواصل مع الإدارة.")
        
        # إذا تم اختيار فصل، عرض الخيارات حسب الوضع
        else:
            selected_class = st.session_state.selected_class
            
            # إذا اختار تسجيل الغياب
            if st.session_state.teacher_mode == "record":
                st.markdown(f'<div class="home-title">📝 تسجيل غياب {selected_class}</div>', unsafe_allow_html=True)
                
                # زر العودة لاختيار فصل آخر
                if st.button("🔄 اختيار فصل آخر", key="change_class_record", use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                st.markdown("---")
                
                # عرض قائمة الطلاب للفصل المحدد
                class_students = CLASSES.get(selected_class, [])
                
                if class_students:
                    # عرض معلومات الفصل
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("اسم المعلم", teacher_name)
                    with col2:
                        st.metric("اسم الفصل", selected_class)
                    with col3:
                        st.metric("عدد الطلاب", len(class_students))
                    
                    st.markdown("---")
                    
                    # اختيار الطلاب الغائبين
                    st.markdown("### 👇 اختر الطلاب الغائبين")
                    selected = st.multiselect(
                        f"اختر الطلاب الغائبين من {selected_class}",
                        class_students,
                        label_visibility="collapsed"
                    )

                    # اختيار نوع الغياب
                    st.markdown("### 📝 اختر نوع الغياب")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        excuse = st.checkbox("غياب بعذر", key="excuse")
                    with col_b:
                        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")

                    if excuse and no_excuse:
                        st.warning("⚠️ اختر نوع واحد فقط.")

                    st.markdown("---")
                    
                    # زر تسجيل الغياب
                    if st.button("💾 حفظ وتسجيل الغياب", key="record_attendance", use_container_width=True):
                        if excuse and no_excuse:
                            st.warning("⚠️ اختر نوع واحد فقط.")
                        elif not (excuse or no_excuse):
                            st.warning("⚠️ من فضلك اختر نوع الغياب.")
                        else:
                            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                            
                            # تسجيل الغياب
                            try:
                                failed, telegram_status, telegram_details, success_count = record_attendance(
                                    selected, teacher_name, selected_class, status_label
                                )
                            except Exception as e:
                                st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                            else:
                                if success_count > 0:
                                    st.success(f"✅ تم تسجيل الغياب بنجاح")
                                    
                                    # عرض ملخص
                                    with st.expander("📊 ملخص التسجيل", expanded=True):
                                        st.markdown(f"""
                                        **تفاصيل التسجيل:**
                                        - **المعلم:** {teacher_name}
                                        - **عدد الطلاب الكلي:** {len(class_students)}
                                        - **عدد الغائبين:** {len(selected)}
                                        - **عدد الحاضرين:** {len(class_students) - len(selected)}
                                        - **نوع الغياب:** {status_label}
                                        - **التاريخ:** {datetime.now().strftime("%d / %m / %Y")}
                                        
                                        **الطلاب الغائبون:**
                                        {', '.join(selected) if selected else "لا أحد"}
                                        """)
                                        
                                        if telegram_status == "✅ تم الإرسال بنجاح":
                                            st.info("📱 تم إرسال إشعار بالغياب إلى التلغرام")
                else:
                    st.error(f"❌ لا يوجد طلاب مسجلين في {selected_class}")
            
            # إذا اختار عرض الإحصائيات
            elif st.session_state.teacher_mode == "statistics":
                st.markdown(f'<div class="home-title">📊 إحصائيات {selected_class}</div>', unsafe_allow_html=True)
                
                # زر العودة لاختيار فصل آخر
                if st.button("🔄 اختيار فصل آخر", key="change_class_stats", use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                st.markdown("---")
                
                # الحصول على إحصائيات الفصل
                stats = get_class_statistics(selected_class)
                history_df = get_class_attendance_history(selected_class)
                
                # عرض الإحصائيات العامة
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("عدد الطلاب", stats["total_students"])
                with col2:
                    st.metric("إجمالي السجلات", stats["total_records"])
                with col3:
                    st.metric("نسبة الحضور", f"{stats['attendance_rate']:.1f}%")
                with col4:
                    if stats["total_records"] > 0:
                        daily_avg = stats["total_records"] / stats["total_students"] if stats["total_students"] > 0 else 0
                        st.metric("متوسط السجلات للطالب", f"{daily_avg:.1f}")
                    else:
                        st.metric("متوسط السجلات للطالب", "0")
                
                st.markdown("---")
                
                # عرض تفاصيل الحضور والغياب
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("### ✅ الحضور")
                    st.metric("عدد مرات الحضور", stats["present_count"])
                with col_b:
                    st.markdown("### ❌ الغياب")
                    st.metric("عدد مرات الغياب", stats["absent_count"])
                
                st.markdown("---")
                
                # عرض إحصائيات كل طالب
                st.markdown("### 👥 إحصائيات الطلاب")
                
                if stats["students"]:
                    # إنشاء DataFrame لإحصائيات الطلاب
                    student_stats_df = pd.DataFrame(stats["students"])
                    student_stats_df = student_stats_df.rename(columns={
                        "name": "اسم الطالب",
                        "total": "عدد السجلات",
                        "present": "حضور",
                        "absent": "غياب",
                        "rate": "نسبة الحضور %"
                    })
                    
                    # تنسيق نسبة الحضور
                    student_stats_df["نسبة الحضور %"] = student_stats_df["نسبة الحضور %"].apply(lambda x: f"{x:.1f}%")
                    
                    st.dataframe(student_stats_df, use_container_width=True, hide_index=True)
                else:
                    st.info("لا توجد سجلات لهذا الفصل بعد.")
                
                # زر تحميل تقرير الفصل الكامل
                st.markdown("---")
                st.markdown("### 📥 تحميل تقرير الفصل")
                
                # إنشاء تقرير PDF كامل
                try:
                    pdf_buffer = generate_class_full_report(selected_class, teacher_name, stats, history_df)
                    
                    if pdf_buffer:
                        # زر تحميل التقرير
                        st.download_button(
                            label="📄 تحميل تقرير الفصل (PDF)",
                            data=pdf_buffer,
                            file_name=f"تقرير_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True,
                            help="سيحتوي التقرير على: الإحصائيات العامة، إحصائيات الطلاب، سجل الحضور التفصيلي"
                        )
                    else:
                        st.error("❌ فشل في إنشاء التقرير. الرجاء التحقق من الخطوط العربية.")
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء إنشاء التقرير: {str(e)}")
                
                # عرض جميع السجلات
                st.markdown("---")
                st.markdown(f"### 📅 سجل الحضور للفصل {selected_class}")
                
                if not history_df.empty:
                    # عرض كل السجلات مع دعم التمرير
                    all_history = history_df.copy()
                    all_history = all_history.rename(columns={
                        "student": "الطالب",
                        "teacher": "المعلم",
                        "date_clean": "التاريخ",
                        "status_clean": "الحالة"
                    })
                    
                    st.dataframe(all_history, use_container_width=True, hide_index=True)
                else:
                    st.info("لا توجد سجلات حضرور لهذا الفصل بعد.")
        
        # زر العودة للصفحة الرئيسية في الأسفل فقط
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_bottom", use_container_width=True, type="secondary"):
            st.session_state.page = "home"
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة الطالب لعرض تقاريره
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown('<div class="student-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">📊 تقرير الغياب الخاص بي</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية في الأعلى
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student_top", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        student_name = st.session_state.get('student_name', st.session_state.user_name)
        
        # عرض بيانات الطالب
        df_student = get_student_records(student_name)
        
        if df_student.empty:
            st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        else:
            # حساب الإحصاءات (الغياب بعذر وبدون عذر يحسبان كغياب)
            absent_count = int((df_student["الحالة"] == "غياب").sum())
            present_count = int((df_student["الحالة"] == "حاضر").sum())
            total_count = len(df_student)
            
            # عرض الإحصاءات
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("عدد مرات الحضور", present_count)
            with col2:
                st.metric("عدد مرات الغياب", absent_count)
            with col3:
                st.metric("إجمالي السجلات", total_count)
            with col4:
                if total_count > 0:
                    attendance_rate = (present_count / total_count) * 100
                    st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
                else:
                    st.metric("نسبة الحضور", "0%")
            
            # عرض الجدول
            st.markdown("### 📋 تفاصيل السجلات:")
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            
            # زر تحميل PDF
            pdf_buf = generate_student_pdf(student_name, df_student)
            if pdf_buf:
                st.download_button(
                    "📥 تحميل تقرير PDF",
                    data=pdf_buf,
                    file_name=f"تقرير_غياب_{student_name}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            else:
                st.error("❌ فشل في إنشاء التقرير")
        
        # زر العودة للصفحة الرئيسية في الأسفل
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student_bottom", use_container_width=True, type="secondary"):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة مدير النظام
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown('<div class="admin-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">👑 لوحة تحكم مدير النظام</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_admin", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # عرض حالة الاتصال
        st.info(f"**حالة الاتصال:** {connection_status}")
        
        # تبويبات لوحة التحكم
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 نظرة عامة",
            "👥 إدارة الطلاب",
            "🏫 إدارة الفصول",
            "📋 مراجعة بيانات الغياب",
            "📤 تصدير التقارير"
        ])
        
        with tab1:
            st.markdown("### 📊 نظرة عامة على النظام")
            
            # إحصائيات النظام
            df_all = read_sheet()
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                total_records = len(df_all) if not df_all.empty else 0
                st.metric("إجمالي السجلات", total_records)
            with col2:
                total_students = len(ALL_STUDENTS)
                st.metric("عدد الطلاب", total_students)
            with col3:
                total_classes = len(CLASSES)
                st.metric("عدد الفصول", total_classes)
            with col4:
                total_teachers = len(TEACHER_CLASSES)
                st.metric("عدد المعلمين", total_teachers)
            
            # عرض بيانات خام للتحقق
            with st.expander("🔍 عرض البيانات الخام للتحقق"):
                if not df_all.empty:
                    st.write(f"عدد الصفوف: {len(df_all)}")
                    st.write("الأعمدة المتاحة:", list(df_all.columns))
                    st.write("عينة من البيانات:")
                    st.dataframe(df_all.head(10), use_container_width=True)
                else:
                    st.info("لا توجد بيانات في الجدول بعد.")
        
        with tab2:
            st.markdown("### 👥 إدارة الطلاب")
            
            # إصلاح البيانات
            if st.button("🔧 إصلاح هيكل البيانات", key="fix_data_structure"):
                try:
                    df_all = read_sheet()
                    if write_sheet(df_all):
                        st.success("✅ تم إصلاح هيكل البيانات")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ خطأ في إصلاح البيانات: {e}")
            
            st.markdown("#### 📋 قائمة الطلاب الحاليين")
            
            # عرض جميع الطلاب حسب الفصول
            for class_name, students in CLASSES.items():
                with st.expander(f"📚 {class_name} ({len(students)} طالب)"):
                    # إنشاء جدول للطلاب
                    student_data = []
                    for idx, student in enumerate(students, 1):
                        password = student_passwords.get(student, "غير معرف")
                        student_data.append({
                            "م": idx,
                            "اسم الطالب": student,
                            "كلمة المرور": password,
                            "الفصل": class_name
                        })
                    
                    student_df = pd.DataFrame(student_data)
                    st.dataframe(student_df, use_container_width=True, hide_index=True)
        
        with tab3:
            st.markdown("### 🏫 إدارة الفصول")
            
            st.markdown("#### 📊 معلومات الفصول الحالية")
            
            for class_name, students in CLASSES.items():
                with st.expander(f"📁 {class_name} - {len(students)} طالب"):
                    st.write(f"**المعلم المسؤول:** {', '.join([k for k, v in TEACHER_CLASSES.items() if class_name in v]) or 'غير معين'}")
                    st.write("**الطلاب:**")
                    for student in students:
                        st.write(f"- {student}")
        
        with tab4:
            st.markdown("### 📋 مراجعة بيانات الغياب")
            
            # عرض جميع بيانات الغياب
            df_all = read_sheet()
            
            if not df_all.empty:
                # تصفية البيانات
                st.markdown("#### 🔍 تصفية البيانات")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    filter_class = st.selectbox("الفصل", ["الكل"] + list(CLASSES.keys()))
                with col2:
                    filter_status = st.selectbox("الحالة", ["الكل", "حاضر", "غياب"])
                with col3:
                    filter_date = st.date_input("التاريخ (اختياري)", value=None)
                
                # تطبيق التصفية
                filtered_df = df_all.copy()
                
                if filter_class != "الكل":
                    filtered_df = filtered_df[filtered_df["class"] == filter_class]
                
                if filter_status != "الكل":
                    if filter_status == "غياب":
                        filtered_df = filtered_df[filtered_df["status"].str.contains("غياب", na=False)]
                    else:
                        filtered_df = filtered_df[filtered_df["status"] == filter_status]
                
                if filter_date:
                    date_str = filter_date.strftime("%d / %m / %Y")
                    filtered_df = filtered_df[filtered_df["date"].astype(str).str.contains(date_str, na=False)]
                
                # عرض البيانات المصفاة
                st.markdown(f"#### 📊 البيانات المصفاة ({len(filtered_df)} سجل)")
                
                if not filtered_df.empty:
                    # تنسيق البيانات للعرض
                    display_df = filtered_df.copy()
                    display_df = display_df.rename(columns={
                        "student": "الطالب",
                        "teacher": "المعلم",
                        "class": "الفصل",
                        "status": "الحالة",
                        "date": "التاريخ"
                    })
                    
                    # إعادة ترتيب الأعمدة
                    display_df = display_df[["التاريخ", "الفصل", "الطالب", "المعلم", "الحالة"]]
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
                    # خيارات إدارة البيانات
                    st.markdown("---")
                    st.markdown("#### ⚙️ إدارة البيانات")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        # زر تصدير البيانات
                        csv = filtered_df.to_csv(index=False)
                        st.download_button(
                            label="📥 تصدير البيانات المصفاة (CSV)",
                            data=csv,
                            file_name=f"بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    
                    with col2:
                        # زر حذف البيانات المصفاة
                        if st.button("🗑️ حذف البيانات المصفاة", use_container_width=True):
                            st.warning("⚠️ هذه العملية لا يمكن التراجع عنها!")
                            if st.button("✅ نعم، احذف البيانات", key="confirm_delete"):
                                try:
                                    # قراءة جميع البيانات
                                    all_data = worksheet.get_all_records()
                                    all_data_df = pd.DataFrame(all_data)
                                    
                                    # إزالة البيانات المصفاة
                                    for _, row in filtered_df.iterrows():
                                        mask = (all_data_df == row).all(axis=1)
                                        all_data_df = all_data_df[~mask]
                                    
                                    # حفظ البيانات الجديدة
                                    write_sheet(all_data_df)
                                    st.success(f"✅ تم حذف {len(filtered_df)} سجل")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ خطأ في حذف البيانات: {str(e)}")
                else:
                    st.info("❌ لا توجد بيانات مطابقة للتصفية.")
            else:
                st.info("📭 لا توجد بيانات غياب بعد.")
        
        with tab5:
            st.markdown("### 📤 تصدير التقارير")
            
            # تبويبات داخلية للتقارير
            report_tab1, report_tab2, report_tab3 = st.tabs([
                "📄 تقرير شامل",
                "👨‍🏫 تقرير المعلمين",
                "⚙️ أدوات النظام"
            ])
            
            with report_tab1:
                st.markdown("#### 📄 تقرير شامل للنظام")
                st.info("يمكنك إنشاء تقرير PDF شامل يحتوي على جميع إحصائيات النظام")
                
                if st.button("📊 إنشاء تقرير شامل (PDF)", use_container_width=True):
                    try:
                        pdf_buffer = generate_system_report_pdf()
                        
                        if pdf_buffer:
                            # زر تحميل التقرير
                            st.download_button(
                                label="📥 تحميل تقرير شامل (PDF)",
                                data=pdf_buffer,
                                file_name=f"تقرير_شامل_النظام_{datetime.now().strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                            
                            st.success("✅ تم إنشاء التقرير بنجاح")
                        else:
                            st.error("❌ فشل في إنشاء التقرير. تحقق من الخطوط العربية.")
                        
                    except Exception as e:
                        st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
            
            with report_tab2:
                st.markdown("#### 👨‍🏫 تقرير المعلمين")
                st.info("تقرير خاص بأداء المعلمين والفصول المسؤولين عنها")
                
                if st.button("👨‍🏫 إنشاء تقرير المعلمين (PDF)", use_container_width=True):
                    try:
                        pdf_buffer = generate_teachers_report_pdf()
                        
                        if pdf_buffer:
                            # زر تحميل التقرير
                            st.download_button(
                                label="📥 تحميل تقرير المعلمين (PDF)",
                                data=pdf_buffer,
                                file_name=f"تقرير_المعلمين_{datetime.now().strftime('%Y%m%d')}.pdf",
                                mime="application/pdf",
                                use_container_width=True
                            )
                            
                            st.success("✅ تم إنشاء تقرير المعلمين بنجاح")
                        else:
                            st.error("❌ فشل في إنشاء التقرير")
                        
                    except Exception as e:
                        st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
            
            with report_tab3:
                st.markdown("#### ⚙️ أدوات النظام")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    # إعادة تعيين النظام
                    if st.button("🔄 إعادة تعيين النظام", use_container_width=True):
                        st.warning("⚠️ سيتم مسح جميع سجلات الغياب. هل أنت متأكد؟")
                        if st.button("✅ نعم، أعد التعيين", key="confirm_reset"):
                            try:
                                worksheet.clear()
                                headers = ["student", "teacher", "class", "status", "date"]
                                worksheet.append_row(headers)
                                st.success("✅ تم إعادة تعيين النظام بنجاح")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ خطأ في إعادة التعيين: {str(e)}")
                
                with col2:
                    # اختبار الاتصال
                    if st.button("🔗 اختبار الاتصال", use_container_width=True):
                        if connect_to_google_sheets():
                            st.success(f"✅ الاتصال ناجح: {connection_status}")
                        else:
                            st.error(f"❌ فشل الاتصال: {connection_status}")
                
                with col3:
                    # نسخة احتياطية للإعدادات
                    if st.button("💾 نسخة إعدادات", use_container_width=True):
                        try:
                            # حفظ الإعدادات الحالية
                            backup_data = {
                                "classes": CLASSES,
                                "teacher_classes": TEACHER_CLASSES,
                                "users": USERS,
                                "student_passwords": student_passwords,
                                "timestamp": datetime.now().isoformat(),
                                "description": "نسخة احتياطية من إعدادات نظام الغياب"
                            }
                            
                            backup_json = json.dumps(backup_data, ensure_ascii=False, indent=2)
                            
                            st.download_button(
                                label="📥 تحميل النسخة الاحتياطية",
                                data=backup_json,
                                file_name=f"نسخة_احتياطية_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                                mime="application/json",
                                use_container_width=True
                            )
                            
                            st.success("✅ تم إنشاء النسخة الاحتياطية بنجاح")
                            
                        except Exception as e:
                            st.error(f"❌ خطأ في إنشاء النسخة الاحتياطية: {str(e)}")
        
        st.markdown('</div>', unsafe_allow_html=True)

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()