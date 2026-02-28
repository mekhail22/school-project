import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import logging
import base64
import requests
import time
import hashlib
import random
import string
from pathlib import Path
import io
import csv
from contextlib import contextmanager
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

# Google Sheets / Auth
import gspread
from google.oauth2.service_account import Credentials

# Optional date parser
try:
    from dateutil.parser import parse as date_parse
    from dateutil.relativedelta import relativedelta
    DATEUTIL_AVAILABLE = True
except Exception:
    date_parse = None
    relativedelta = None
    DATEUTIL_AVAILABLE = False

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('attendance_app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("attendance_app")

# ------------------ Page config ------------------
st.set_page_config(
    page_title="نظام إدارة الغياب المدرسي",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ------------------ Constants and Enums ------------------
class UserRole(Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"

class AttendanceStatus(Enum):
    PRESENT = "حاضر"
    ABSENT_EXCUSED = "غياب بعذر"
    ABSENT_UNEXCUSED = "غياب بدون عذر"

class ClassLevel(Enum):
    B = "Class B"
    C = "Class C"
    D = "Class D"
    E = "Class E"

# ------------------ Data Classes ------------------
@dataclass
class User:
    username: str
    password: str
    role: UserRole
    display_name: str
    created_at: datetime
    last_login: Optional[datetime] = None

@dataclass
class Student(User):
    student_name: str = ""
    class_name: ClassLevel = ClassLevel.B
    parent_phone: Optional[str] = None
    address: Optional[str] = None

@dataclass
class Teacher(User):
    classes: List[ClassLevel] = field(default_factory=list)
    specialization: Optional[str] = None
    phone: Optional[str] = None

@dataclass
class AttendanceRecord:
    student: str
    teacher: str
    class_name: str
    status: str
    date: str
    notes: Optional[str] = None
    recorded_at: Optional[datetime] = None

# ------------------ App settings ------------------
CLASSES = {
    "Class B": [
        "محمد علي محمد", 
        "حسن أحمد حسن", 
        "محمود حسين محمود", 
        "كريم سعيد كريم",
        "أمين خالد أمين", 
        "ياسين رفعت ياسين", 
        "عمر وليد عمر", 
        "سعيد حامد سعيد",
        "نبيل جمال نبيل", 
        "جمال هشام جمال"
    ],
    "Class C": [
        "أحمد محمد أحمد", 
        "محمود سعيد حسين", 
        "علي كمال علي", 
        "يوسف خالد يوسف",
        "خالد أمين خالد", 
        "سامي رفعت سامي", 
        "طارق وليد طارق", 
        "مصطفى حامد مصطفى",
        "هشام نبيل هشام", 
        "وليد جمال وليد"
    ],
    "Class D": [
        "فؤاد محمد فؤاد", 
        "رشاد أحمد رشاد", 
        "صابر حسين صابر", 
        "عادل سعيد عادل",
        "فكري خالد فكري", 
        "رأفت رفعت رأفت", 
        "حسام وليد حسام", 
        "عاطف حامد عاطف",
        "مجدي جمال مجدي", 
        "سليمان هشام سليمان"
    ],
    "Class E": [
        "نبيل محمد نبيل", 
        "رامي أحمد رامي", 
        "عماد حسين عماد", 
        "صلاح سعيد صلاح",
        "مجد خالد مجد", 
        "رافت رفعت رافت", 
        "بسام وليد بسام", 
        "كمال حامد كمال",
        "فاروق جمال فاروق", 
        "أنور هشام أنور"
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

# معلمين النظام
TEACHERS = {
    "مينا سمير": {
        "password": "mina1234",
        "display_name": "مينا سمير",
        "classes": ["Class B", "Class C"],
        "role": "teacher",
        "specialization": "رياضيات",
        "phone": "0123456789"
    },
    "فادي حبيب": {
        "password": "fady5678",
        "display_name": "فادي حبيب",
        "classes": ["Class D", "Class E"],
        "role": "teacher",
        "specialization": "علوم",
        "phone": "0123456790"
    }
}

# مستخدمون وكلمات مرورهم
USERS = {
    # مدير النظام - صلاحيات كاملة
    "admin": {
        "password": "admin1234",
        "role": "admin",
        "display_name": "مدير النظام",
        "created_at": datetime.now().isoformat()
    }
}

# إضافة المعلمين إلى USERS
for teacher_name, teacher_info in TEACHERS.items():
    USERS[teacher_name] = teacher_info

# إضافة الطلاب مع كلمات مرور إجبارية
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
            "student_name": student,
            "created_at": datetime.now().isoformat()
        }
    else:
        # إنشاء كلمة مرور عشوائية
        password = ''.join(random.choices(string.digits, k=6))
        USERS[student] = {
            "password": password,
            "role": "student",
            "student_name": student,
            "created_at": datetime.now().isoformat()
        }

# ------------------ تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل الإعدادات من Streamlit Secrets"""
    try:
        secrets = st.secrets
        
        # Telegram
        BOT_TOKEN = getattr(secrets, 'BOT_TOKEN', None)
        CHAT_ID = getattr(secrets, 'CHAT_ID', None)
        
        # App settings
        SHEET_NAME = getattr(secrets, 'SHEET_NAME', 'school_attendance')
        
        # Service Account
        SERVICE_ACCOUNT = None
        
        # الطريقة 1: SERVICE_ACCOUNT_JSON
        if hasattr(secrets, 'SERVICE_ACCOUNT_JSON'):
            try:
                SERVICE_ACCOUNT = json.loads(secrets.SERVICE_ACCOUNT_JSON)
                logger.info("✅ تم تحميل SERVICE_ACCOUNT_JSON بنجاح")
            except Exception as e:
                logger.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
        # الطريقة 2: SERVICE_ACCOUNT كقسم
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
                logger.info("✅ تم تحميل SERVICE_ACCOUNT بنجاح")
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
connection_error = None

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
                    headers = ["student", "teacher", "class", "status", "date"]
                    worksheet.append_row(headers)
                    connection_details += " - تم إنشاء جدول جديد"
                    logger.info("✅ تم إنشاء جدول جديد في Google Sheets")
                
                logger.info(f"✅ تم الاتصال بـ Google Sheets بنجاح - {len(current_data)} سجل")
                
            except Exception as e:
                connection_status = f"⚠️ متصل ولكن خطأ في القراءة: {str(e)}"
                connection_error = str(e)
                logger.warning(f"⚠️ خطأ في قراءة Google Sheets: {str(e)}")
                
        except gspread.exceptions.SpreadsheetNotFound:
            connection_status = f"❌ لم يتم العثور على Google Sheet باسم: {SHEET_NAME}"
            connection_error = f"الملف {SHEET_NAME} غير موجود"
            logger.error(f"❌ لم يتم العثور على Google Sheet: {SHEET_NAME}")
        except Exception as e:
            connection_status = f"❌ خطأ في فتح الـ Sheet: {str(e)}"
            connection_error = str(e)
            logger.error(f"❌ خطأ في فتح Google Sheet: {str(e)}")
            
    except Exception as e:
        connection_status = f"❌ فشل في المصادقة: {str(e)}"
        connection_error = str(e)
        logger.error(f"❌ فشل في مصادقة Google Sheets: {str(e)}")
else:
    connection_status = "⚠️ SERVICE_ACCOUNT غير متوفر - سيتم استخدام التخزين المحلي"
    logger.warning("⚠️ SERVICE_ACCOUNT غير متوفر - سيتم استخدام التخزين المحلي")

# إخفاء رسائل الاتصال بالكامل
if "disable_connection_alerts" not in st.session_state:
    st.session_state.disable_connection_alerts = True

# ------------------ دوال مساعدة للتاريخ ------------------
def parse_date(date_str):
    """تحليل التاريخ من النص"""
    if pd.isna(date_str) or not date_str:
        return None
    
    try:
        if DATEUTIL_AVAILABLE and date_parse:
            return date_parse(str(date_str))
    except:
        pass
    
    # محاولات تحليل يدوية
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d",
        "%d/%m/%y", "%d-%m-%y", "%d %m %Y", "%d %b %Y"
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(str(date_str).strip(), fmt)
        except:
            continue
    
    return None

def format_date(date, format_str="%d / %m / %Y"):
    """تنسيق التاريخ"""
    if isinstance(date, str):
        date = parse_date(date)
    if isinstance(date, datetime):
        return date.strftime(format_str)
    return ""

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

def get_current_date():
    """الحصول على التاريخ الحالي بالتنسيق المطلوب"""
    return datetime.now().strftime("%d / %m / %Y")

def get_current_datetime():
    """الحصول على التاريخ والوقت الحالي"""
    return datetime.now()

def get_arabic_date():
    """الحصول على التاريخ بالعربية"""
    today = datetime.now()
    arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    weekday = arabic_weekdays[today.weekday()]
    month = arabic_months[today.month - 1]
    return f"{weekday}، {today.day} {month} {today.year}"

# ------------------ دوال المساعدة للطلاب والفصول ------------------
def get_student_class(student_name):
    """الحصول على فصل الطالب تلقائياً"""
    return STUDENT_TO_CLASS.get(student_name, "")

def get_class_students(class_name):
    """الحصول على قائمة طلاب الفصل"""
    return CLASSES.get(class_name, [])

def get_all_classes():
    """الحصول على قائمة جميع الفصول"""
    return list(CLASSES.keys())

def get_students_by_class():
    """الحصول على قاموس الطلاب حسب الفصل"""
    return CLASSES.copy()

def get_teacher_classes(teacher_name):
    """الحصول على فصول المعلم"""
    return TEACHER_CLASSES.get(teacher_name, [])

def get_all_teachers():
    """الحصول على قائمة جميع المعلمين"""
    return list(TEACHERS.keys())

def is_teacher(teacher_name):
    """التحقق مما إذا كان المستخدم معلماً"""
    return teacher_name in TEACHERS

def is_student(student_name):
    """التحقق مما إذا كان المستخدم طالباً"""
    return student_name in ALL_STUDENTS

def is_admin(username):
    """التحقق مما إذا كان المستخدم مديراً"""
    return username == "admin"

# ------------------ دوال قراءة وكتابة البيانات ------------------
def read_sheet():
    """قراءة البيانات من Google Sheets أو من نسخة محلية مؤقتة"""
    global worksheet
    
    # 1. أولاً: حاول القراءة من Google Sheets
    if worksheet is not None:
        try:
            data = worksheet.get_all_records()
            df = pd.DataFrame(data)
            
            # التأكد من وجود الأعمدة الأساسية
            for col in ["student", "teacher", "class", "status", "date"]:
                if col not in df.columns:
                    df[col] = ""
            
            logger.info(f"✅ تم تحميل {len(df)} سجل من Google Sheets")
            return df
            
        except Exception as e:
            logger.error(f"❌ خطأ في قراءة Google Sheets: {str(e)}")
    
    # 2. إذا فشل الاتصال: استخدم نسخة محلية من البيانات المخزنة في session_state
    try:
        # التحقق من وجود بيانات في session_state
        if "local_attendance_data" in st.session_state:
            df = pd.DataFrame(st.session_state["local_attendance_data"])
            logger.info(f"📱 تم تحميل {len(df)} سجل من الذاكرة المحلية")
            return df
        else:
            # إذا لم توجد بيانات محلية، أنشئ DataFrame فارغ
            logger.info("📭 لا توجد بيانات في الذاكرة المحلية")
            return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
            
    except Exception as e:
        logger.error(f"❌ خطأ في قراءة الذاكرة المحلية: {str(e)}")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])

def save_to_sheet(rows):
    """حفظ البيانات في Google Sheets"""
    global worksheet
    
    if not rows:
        return 0, []
    
    success_count = 0
    failed = []
    
    if worksheet:
        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
            logger.info(f"✅ تم حفظ {success_count} سجل في Google Sheets")
        except Exception as e:
            logger.error(f"❌ خطأ في الحفظ في Google Sheets: {str(e)}")
            failed.append(("Google Sheets", str(e)))
            
            # محاولة حفظ كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
                logger.info(f"✅ تم حفظ {success_count} سجل في Google Sheets (طريقة بديلة)")
            except Exception as ex:
                logger.error(f"❌ فشل الحفظ في Google Sheets: {str(ex)}")
                failed.append(("Google Sheets (بديل)", str(ex)))
    
    return success_count, failed

def save_to_local(rows):
    """حفظ البيانات محلياً في session_state"""
    try:
        if "local_attendance_data" not in st.session_state:
            st.session_state["local_attendance_data"] = []
        
        for row in rows:
            st.session_state["local_attendance_data"].append({
                "student": row[0],
                "teacher": row[1],
                "class": row[2],
                "status": row[3],
                "date": row[4]
            })
        
        logger.info(f"💾 تم حفظ {len(rows)} سجل في الذاكرة المحلية")
        return len(rows)
    except Exception as e:
        logger.error(f"❌ خطأ في الحفظ المحلي: {str(e)}")
        return 0

def export_to_csv(df, filename=None):
    """تصدير البيانات إلى CSV (محذوفة - لن تستخدم)"""
    # هذه الدالة محذوفة ولن تستخدم
    pass

def import_from_csv(csv_file):
    """استيراد البيانات من CSV"""
    try:
        df = pd.read_csv(csv_file)
        required_cols = ["student", "teacher", "class", "status", "date"]
        
        if all(col in df.columns for col in required_cols):
            rows = df[required_cols].values.tolist()
            return True, rows, "تم استيراد البيانات بنجاح"
        else:
            missing = [col for col in required_cols if col not in df.columns]
            return False, [], f"الأعمدة المفقودة: {', '.join(missing)}"
    except Exception as e:
        return False, [], f"خطأ في الاستيراد: {str(e)}"

# ------------------ دوال الإحصائيات ------------------
def get_class_statistics(class_name):
    """الحصول على إحصائيات الفصل"""
    df = read_sheet()
    
    if df.empty:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "absent_excused": 0,
            "absent_unexcused": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # تصفية البيانات للفصل المحدد
    class_df = pd.DataFrame()
    
    if not df.empty:
        # البحث عن الفصل
        if "class" in df.columns:
            class_df = df[df["class"].astype(str).str.strip() == class_name.strip()]
            
            if class_df.empty:
                # محاولة البحث بدون حساسية لحالة الحروف
                class_df = df[df["class"].astype(str).str.strip().str.lower() == class_name.strip().lower()]
    
    if class_df.empty:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "absent_excused": 0,
            "absent_unexcused": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # حساب الإحصائيات
    total_records = len(class_df)
    
    # حساب الحضور والغياب
    present_count = 0
    absent_count = 0
    absent_excused = 0
    absent_unexcused = 0
    
    if "status" in class_df.columns:
        present_count = len(class_df[class_df["status"] == "حاضر"])
        absent_excused = len(class_df[class_df["status"] == "غياب بعذر"])
        absent_unexcused = len(class_df[class_df["status"] == "غياب بدون عذر"])
        absent_count = absent_excused + absent_unexcused
    
    # حساب نسبة الحضور
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    # إحصائيات لكل طالب
    student_stats = []
    class_students = CLASSES.get(class_name, [])
    
    for student in class_students:
        # البحث عن سجلات الطالب
        if "student" in class_df.columns:
            student_df = class_df[class_df["student"].astype(str).str.strip() == student.strip()]
            student_total = len(student_df)
            student_present = 0
            student_absent = 0
            student_excused = 0
            student_unexcused = 0
            
            if "status" in student_df.columns:
                student_present = len(student_df[student_df["status"] == "حاضر"])
                student_excused = len(student_df[student_df["status"] == "غياب بعذر"])
                student_unexcused = len(student_df[student_df["status"] == "غياب بدون عذر"])
                student_absent = student_excused + student_unexcused
            
            student_rate = (student_present / student_total * 100) if student_total > 0 else 0
            
            student_stats.append({
                "name": student,
                "total": student_total,
                "present": student_present,
                "absent": student_absent,
                "excused": student_excused,
                "unexcused": student_unexcused,
                "rate": student_rate
            })
    
    return {
        "total_students": len(class_students),
        "total_records": total_records,
        "present_count": present_count,
        "absent_count": absent_count,
        "absent_excused": absent_excused,
        "absent_unexcused": absent_unexcused,
        "attendance_rate": attendance_rate,
        "students": student_stats
    }

def get_class_attendance_history(class_name):
    """الحصول على سجل الحضور للفصل"""
    df = read_sheet()
    
    if df.empty:
        return pd.DataFrame()
    
    # تصفية البيانات للفصل المحدد
    class_df = pd.DataFrame()
    
    if not df.empty and "class" in df.columns:
        # البحث عن الفصل
        class_df = df[df["class"].astype(str).str.strip() == class_name.strip()]
        
        if class_df.empty:
            # محاولة البحث بدون حساسية لحالة الحروف
            class_df = df[df["class"].astype(str).str.strip().str.lower() == class_name.strip().lower()]
    
    if class_df.empty:
        return pd.DataFrame()
    
    # تنظيف البيانات
    class_df = class_df.copy()
    
    # معالجة التاريخ
    if "date" in class_df.columns:
        class_df["date_clean"] = class_df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
        class_df["date_obj"] = class_df["date"].apply(lambda x: parse_date(x) if pd.notna(x) else None)
    else:
        class_df["date_clean"] = ""
        class_df["date_obj"] = None
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب بعذر" in status_str:
            return "غياب بعذر"
        elif "غياب بدون عذر" in status_str:
            return "غياب بدون عذر"
        elif "غياب" in status_str:
            return "غياب"
        elif "حاضر" in status_str:
            return "حاضر"
        return status_str
    
    if "status" in class_df.columns:
        class_df["status_clean"] = class_df["status"].apply(clean_status)
    else:
        class_df["status_clean"] = ""
    
    # ترتيب حسب التاريخ
    if not class_df.empty and 'date_obj' in class_df.columns:
        class_df = class_df.sort_values("date_obj", ascending=False, na_position='last')
    
    # إضافة الأعمدة إذا لم تكن موجودة
    if "student" not in class_df.columns:
        class_df["student"] = ""
    if "teacher" not in class_df.columns:
        class_df["teacher"] = ""
    
    return class_df[["student", "teacher", "date_clean", "status_clean"]]

def get_student_records(student_name):
    """الحصول على سجلات طالب معين"""
    df = read_sheet()
    
    if df.empty or "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة", "ملاحظات"])
    
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
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة", "ملاحظات"])
    
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
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب بعذر" in status_str:
            return "غياب بعذر"
        elif "غياب بدون عذر" in status_str:
            return "غياب بدون عذر"
        elif "غياب" in status_str:
            return "غياب"
        elif "حاضر" in status_str:
            return "حاضر"
        return status_str
    
    df_matches["status_clean"] = df_matches["status"].apply(clean_status)
    df_matches["date_clean"] = df_matches["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    df_matches["date_obj"] = df_matches["date"].apply(lambda x: parse_date(x) if pd.notna(x) else None)
    
    # إعادة ترتيب الصفوف
    if not df_matches.empty and 'date_obj' in df_matches.columns:
        df_matches = df_matches.sort_values("date_obj", ascending=False, na_position='last')
    
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    
    # إضافة عمود ملاحظات فارغ
    df_matches["ملاحظات"] = ""
    
    # إعادة تسمية الأعمدة
    df_matches = df_matches.rename(columns={
        "student": "الطالب", 
        "teacher": "المعلم", 
        "class": "الفصل", 
        "date_clean": "التاريخ",
        "status_clean": "الحالة"
    })
    
    return df_matches[["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة", "ملاحظات"]]

def get_all_records():
    """الحصول على جميع سجلات الغياب"""
    df = read_sheet()
    if df.empty:
        return pd.DataFrame()
    
    # تنظيف البيانات
    df = df.copy()
    
    if "date" in df.columns:
        df["date_clean"] = df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
        df["date_obj"] = df["date"].apply(lambda x: parse_date(x) if pd.notna(x) else None)
    else:
        df["date_clean"] = ""
        df["date_obj"] = None
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب بعذر" in status_str:
            return "غياب بعذر"
        elif "غياب بدون عذر" in status_str:
            return "غياب بدون عذر"
        elif "غياب" in status_str:
            return "غياب"
        elif "حاضر" in status_str:
            return "حاضر"
        return status_str
    
    if "status" in df.columns:
        df["status_clean"] = df["status"].apply(clean_status)
    else:
        df["status_clean"] = ""
    
    # ترتيب حسب التاريخ
    if not df.empty and 'date_obj' in df.columns:
        df = df.sort_values("date_obj", ascending=False, na_position='last')
    
    return df

def get_system_statistics():
    """الحصول على إحصائيات النظام"""
    df = read_sheet()
    
    total_records = len(df)
    total_students = len(ALL_STUDENTS)
    total_classes = len(CLASSES)
    total_teachers = len(TEACHERS)
    
    # حساب الحضور والغياب
    if not df.empty:
        present_count = 0
        absent_count = 0
        absent_excused = 0
        absent_unexcused = 0
        
        if "status" in df.columns:
            present_count = len(df[df["status"] == "حاضر"])
            absent_excused = len(df[df["status"] == "غياب بعذر"])
            absent_unexcused = len(df[df["status"] == "غياب بدون عذر"])
            absent_count = absent_excused + absent_unexcused
        
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    else:
        present_count = 0
        absent_count = 0
        absent_excused = 0
        absent_unexcused = 0
        attendance_rate = 0
    
    # إحصائيات الفصول
    class_stats = []
    for class_name, students in CLASSES.items():
        records_count = 0
        if not df.empty and "class" in df.columns:
            records_count = len(df[df["class"] == class_name])
        
        class_stats.append({
            "class": class_name,
            "student_count": len(students),
            "records_count": records_count
        })
    
    # إحصائيات حسب الشهر
    monthly_stats = {}
    if not df.empty and "date" in df.columns:
        for _, row in df.iterrows():
            date = parse_date(row.get("date", ""))
            if date:
                month_key = date.strftime("%Y-%m")
                if month_key not in monthly_stats:
                    monthly_stats[month_key] = {"total": 0, "present": 0, "absent": 0}
                
                monthly_stats[month_key]["total"] += 1
                status = str(row.get("status", ""))
                if "حاضر" in status:
                    monthly_stats[month_key]["present"] += 1
                elif "غياب" in status:
                    monthly_stats[month_key]["absent"] += 1
    
    return {
        "total_records": total_records,
        "total_students": total_students,
        "total_classes": total_classes,
        "total_teachers": total_teachers,
        "present_count": present_count,
        "absent_count": absent_count,
        "absent_excused": absent_excused,
        "absent_unexcused": absent_unexcused,
        "attendance_rate": attendance_rate,
        "class_stats": class_stats,
        "monthly_stats": monthly_stats,
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

# ------------------ دوال Telegram ------------------
def send_telegram_message(message):
    """إرسال رسالة إلى Telegram"""
    if not BOT_TOKEN or not CHAT_ID:
        logger.warning("⚠️ إعدادات Telegram غير مكتملة")
        return False, {"error": "credentials_missing"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}

    try:
        resp = requests.post(url, data=payload, timeout=10)
        try:
            j = resp.json()
        except Exception:
            j = {"raw": resp.text}

        if resp.status_code == 200 and j.get("ok", False):
            logger.info("✅ تم إرسال رسالة Telegram بنجاح")
            return True, j
        else:
            logger.error(f"❌ فشل إرسال رسالة Telegram: {resp.status_code}")
            return False, {"status_code": resp.status_code, "response": j}
    except requests.exceptions.RequestException as e:
        logger.error(f"❌ خطأ في الاتصال بـ Telegram: {str(e)}")
        return False, {"exception": str(e)}

def send_attendance_notification(teacher_name, class_name, absent_students, date, status_label):
    """إرسال إشعار غياب"""
    absent_list = ", ".join(absent_students) if absent_students else "لا أحد"
    present_count = len(CLASSES.get(class_name, [])) - len(absent_students)
    
    message = f"""
<b>📋 تسجيل غياب جديد</b>

📅 التاريخ: {date}
👨‍🏫 المعلم: {teacher_name}
🏫 الفصل: {class_name}
📝 نوع الغياب: {status_label}

📊 الإحصائيات:
• إجمالي الطلاب: {len(CLASSES.get(class_name, []))}
• ✅ الحاضرين: {present_count}
• ❌ الغائبين: {len(absent_students)}

👥 قائمة الغائبين:
{absent_list}
    """
    
    return send_telegram_message(message)

# ------------------ دوال تسجيل الغياب ------------------
def record_attendance(selected_absent, teacher_name, class_name, absent_label):
    """تسجيل الغياب"""
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = get_current_date()
    rows = []
    
    # الحصول على جميع طلاب الفصل المحدد
    class_students = CLASSES.get(class_name, [])
    
    # تسجيل جميع طلاب الفصل
    for student in class_students:
        # تحديد حالة الطالب
        if student in selected_absent:
            status = absent_label
        else:
            status = "حاضر"
        
        # الحصول على فصل الطالب تلقائياً من القاموس
        student_class = get_student_class(student)
        rows.append([student, teacher_name, student_class, status, date_display])
    
    # حفظ في Google Sheets
    sheet_success, sheet_failed = save_to_sheet(rows)
    
    # حفظ محلياً
    local_success = save_to_local(rows)
    
    # إرسال إشعار Telegram
    telegram_sent = False
    telegram_response = None
    
    if rows:
        telegram_sent, telegram_response = send_attendance_notification(
            teacher_name, class_name, selected_absent, date_display, absent_label
        )
    
    # إعداد النتائج
    total_success = max(sheet_success, local_success)
    failed = sheet_failed
    
    telegram_status = "✅ تم الإرسال" if telegram_sent else "❌ فشل الإرسال"
    if not BOT_TOKEN or not CHAT_ID:
        telegram_status = "⚠️ غير مكون"
    
    return failed, telegram_status, str(telegram_response) if telegram_response else "", total_success

# ------------------ دوال إدارة النظام (Admin) ------------------
def add_student_to_class(student_name, class_name, password):
    """إضافة طالب جديد إلى فصل"""
    global CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
    if class_name not in CLASSES:
        CLASSES[class_name] = []
    
    # التحقق من عدم وجود الطالب بالفعل
    if student_name in ALL_STUDENTS:
        return False, "الطالب موجود بالفعل في النظام"
    
    # التحقق من كلمة المرور
    if not password or password.strip() == "":
        return False, "كلمة المرور مطلوبة"
    
    # إضافة الطالب إلى الفصل
    CLASSES[class_name].append(student_name)
    STUDENT_TO_CLASS[student_name] = class_name
    ALL_STUDENTS.append(student_name)
    
    # إضافة المستخدم
    USERS[student_name] = {
        "password": password.strip(),
        "role": "student",
        "student_name": student_name,
        "created_at": datetime.now().isoformat()
    }
    
    logger.info(f"✅ تم إضافة الطالب {student_name} إلى {class_name}")
    return True, f"تم إضافة الطالب {student_name} إلى {class_name}"

def add_multiple_students(students_list, class_name, password_prefix):
    """إضافة عدة طلاب دفعة واحدة"""
    added = []
    failed = []
    
    for i, student_name in enumerate(students_list):
        if not student_name.strip():
            continue
        
        password = f"{password_prefix}{i+1:04d}"
        success, message = add_student_to_class(student_name.strip(), class_name, password)
        
        if success:
            added.append(student_name.strip())
        else:
            failed.append((student_name.strip(), message))
    
    return added, failed

def update_student_info(old_student_name, new_student_name, new_class_name, new_password=None):
    """تعديل بيانات طالب"""
    global CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
    if old_student_name not in ALL_STUDENTS:
        return False, "الطالب غير موجود في النظام"
    
    # إذا تم تغيير الاسم
    if old_student_name != new_student_name:
        # حذف الاسم القديم
        old_class = STUDENT_TO_CLASS.get(old_student_name)
        if old_class and old_student_name in CLASSES.get(old_class, []):
            CLASSES[old_class].remove(old_student_name)
        
        # تحديث القاموس
        STUDENT_TO_CLASS.pop(old_student_name, None)
        ALL_STUDENTS.remove(old_student_name)
        
        # إضافة الاسم الجديد
        STUDENT_TO_CLASS[new_student_name] = new_class_name
        if new_student_name not in ALL_STUDENTS:
            ALL_STUDENTS.append(new_student_name)
        
        # تحديث الفصل للاسم الجديد
        if new_student_name not in CLASSES.get(new_class_name, []):
            CLASSES[new_class_name].append(new_student_name)
        
        # تحديث بيانات المستخدم
        if old_student_name in USERS:
            user_data = USERS[old_student_name].copy()
            if new_password:
                user_data["password"] = new_password
            user_data["student_name"] = new_student_name
            user_data["updated_at"] = datetime.now().isoformat()
            USERS[new_student_name] = user_data
            del USERS[old_student_name]
    
    else:
        # إذا لم يتغير الاسم، فقط تحديث الفصل
        old_class = STUDENT_TO_CLASS.get(old_student_name)
        if old_class != new_class_name:
            # إزالة من الفصل القديم
            if old_class and old_student_name in CLASSES.get(old_class, []):
                CLASSES[old_class].remove(old_student_name)
            
            # إضافة إلى الفصل الجديد
            STUDENT_TO_CLASS[old_student_name] = new_class_name
            if old_student_name not in CLASSES.get(new_class_name, []):
                CLASSES[new_class_name].append(old_student_name)
        
        # تحديث كلمة المرور إذا تم توفيرها
        if new_password and old_student_name in USERS:
            USERS[old_student_name]["password"] = new_password
            USERS[old_student_name]["updated_at"] = datetime.now().isoformat()
    
    logger.info(f"✅ تم تحديث بيانات الطالب {new_student_name}")
    return True, f"تم تحديث بيانات الطالب {new_student_name}"

def remove_student_from_class(student_name):
    """حذف طالب من الفصل"""
    global CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
    if student_name not in STUDENT_TO_CLASS:
        return False, "الطالب غير موجود في النظام"
    
    # الحصول على فصل الطالب
    class_name = STUDENT_TO_CLASS[student_name]
    
    # حذف الطالب من الفصل
    if student_name in CLASSES.get(class_name, []):
        CLASSES[class_name].remove(student_name)
    
    # حذف من القاموس والقائمة
    if student_name in STUDENT_TO_CLASS:
        del STUDENT_TO_CLASS[student_name]
    
    if student_name in ALL_STUDENTS:
        ALL_STUDENTS.remove(student_name)
    
    # حذف المستخدم
    if student_name in USERS:
        del USERS[student_name]
    
    logger.info(f"✅ تم حذف الطالب {student_name} من النظام")
    return True, f"تم حذف الطالب {student_name} من النظام"

def add_class(class_name, teacher_name, students_list=None):
    """إضافة فصل جديد"""
    global CLASSES, TEACHER_CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
    if class_name in CLASSES:
        return False, "الفصل موجود بالفعل"
    
    CLASSES[class_name] = students_list or []
    
    # تحديث قائمة المعلمين
    if teacher_name not in TEACHER_CLASSES:
        TEACHER_CLASSES[teacher_name] = []
    
    if class_name not in TEACHER_CLASSES[teacher_name]:
        TEACHER_CLASSES[teacher_name].append(class_name)
    
    # تحديث قاموس الطلاب للفصل الجديد
    for student in CLASSES[class_name]:
        STUDENT_TO_CLASS[student] = class_name
        if student not in ALL_STUDENTS:
            ALL_STUDENTS.append(student)
            
            # إضافة المستخدم للطالب إذا لم يكن موجوداً
            if student not in USERS:
                USERS[student] = {
                    "password": "".join(random.choices(string.digits, k=6)),
                    "role": "student",
                    "student_name": student,
                    "created_at": datetime.now().isoformat()
                }
    
    logger.info(f"✅ تم إضافة الفصل {class_name} بنجاح تحت إشراف {teacher_name}")
    return True, f"تم إضافة الفصل {class_name} بنجاح تحت إشراف {teacher_name}"

def update_class_info(old_class_name, new_class_name, new_teacher_name):
    """تعديل بيانات فصل"""
    global CLASSES, TEACHER_CLASSES, STUDENT_TO_CLASS
    
    if old_class_name not in CLASSES:
        return False, "الفصل غير موجود"
    
    # الحصول على طلاب الفصل القديم
    students = CLASSES[old_class_name]
    
    # حذف الفصل القديم
    del CLASSES[old_class_name]
    
    # إضافة الفصل الجديد
    CLASSES[new_class_name] = students
    
    # تحديث قائمة المعلمين
    for teacher, classes in list(TEACHER_CLASSES.items()):
        if old_class_name in classes:
            classes.remove(old_class_name)
            if new_class_name not in classes:
                classes.append(new_class_name)
    
    # إذا تم تغيير المعلم
    if new_teacher_name:
        if new_teacher_name not in TEACHER_CLASSES:
            TEACHER_CLASSES[new_teacher_name] = []
        
        if new_class_name not in TEACHER_CLASSES[new_teacher_name]:
            TEACHER_CLASSES[new_teacher_name].append(new_class_name)
    
    # تحديث قاموس الطلاب
    for student in students:
        STUDENT_TO_CLASS[student] = new_class_name
    
    logger.info(f"✅ تم تحديث الفصل إلى {new_class_name}")
    return True, f"تم تحديث الفصل إلى {new_class_name}"

def remove_class(class_name):
    """حذف فصل"""
    global CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS, TEACHER_CLASSES
    
    if class_name not in CLASSES:
        return False, "الفصل غير موجود"
    
    # حذف جميع طلاب هذا الفصل من القوائم
    students_to_remove = CLASSES[class_name]
    
    for student in students_to_remove:
        if student in STUDENT_TO_CLASS:
            del STUDENT_TO_CLASS[student]
        if student in ALL_STUDENTS:
            ALL_STUDENTS.remove(student)
        if student in USERS:
            del USERS[student]
    
    # حذف الفصل من قائمة المعلمين
    for teacher in list(TEACHER_CLASSES.keys()):
        if class_name in TEACHER_CLASSES[teacher]:
            TEACHER_CLASSES[teacher].remove(class_name)
    
    # حذف الفصل
    del CLASSES[class_name]
    
    logger.info(f"✅ تم حذف الفصل {class_name} وجميع طلابه")
    return True, f"تم حذف الفصل {class_name} وجميع طلابه"

def add_teacher(teacher_name, password, classes, specialization=None, phone=None):
    """إضافة معلم جديد"""
    global TEACHERS, TEACHER_CLASSES, USERS
    
    if teacher_name in TEACHERS:
        return False, "المعلم موجود بالفعل في النظام"
    
    if not password or password.strip() == "":
        return False, "كلمة المرور مطلوبة"
    
    # إضافة المعلم
    TEACHERS[teacher_name] = {
        "password": password.strip(),
        "display_name": teacher_name,
        "classes": classes,
        "role": "teacher",
        "specialization": specialization,
        "phone": phone,
        "created_at": datetime.now().isoformat()
    }
    
    # إضافة إلى قائمة الفصول
    TEACHER_CLASSES[teacher_name] = classes
    
    # إضافة إلى المستخدمين
    USERS[teacher_name] = TEACHERS[teacher_name]
    
    logger.info(f"✅ تم إضافة المعلم {teacher_name} بنجاح")
    return True, f"تم إضافة المعلم {teacher_name} بنجاح"

def update_teacher_info(old_teacher_name, new_teacher_name, new_password, new_classes, new_specialization=None, new_phone=None):
    """تعديل بيانات معلم"""
    global TEACHERS, TEACHER_CLASSES, USERS
    
    if old_teacher_name not in TEACHERS:
        return False, "المعلم غير موجود في النظام"
    
    # إذا تم تغيير الاسم
    if old_teacher_name != new_teacher_name:
        # حفظ البيانات القديمة
        old_data = TEACHERS[old_teacher_name].copy()
        
        # حذف القديم
        del TEACHERS[old_teacher_name]
        del USERS[old_teacher_name]
        if old_teacher_name in TEACHER_CLASSES:
            del TEACHER_CLASSES[old_teacher_name]
        
        # إضافة الجديد
        TEACHERS[new_teacher_name] = {
            "password": new_password if new_password else old_data["password"],
            "display_name": new_teacher_name,
            "classes": new_classes if new_classes else old_data["classes"],
            "role": "teacher",
            "specialization": new_specialization if new_specialization else old_data.get("specialization"),
            "phone": new_phone if new_phone else old_data.get("phone"),
            "updated_at": datetime.now().isoformat()
        }
        
        TEACHER_CLASSES[new_teacher_name] = new_classes if new_classes else old_data["classes"]
        USERS[new_teacher_name] = TEACHERS[new_teacher_name]
    else:
        # تحديث البيانات بدون تغيير الاسم
        if new_password:
            TEACHERS[old_teacher_name]["password"] = new_password
        
        if new_classes:
            TEACHERS[old_teacher_name]["classes"] = new_classes
            TEACHER_CLASSES[old_teacher_name] = new_classes
        
        if new_specialization:
            TEACHERS[old_teacher_name]["specialization"] = new_specialization
        
        if new_phone:
            TEACHERS[old_teacher_name]["phone"] = new_phone
        
        TEACHERS[old_teacher_name]["updated_at"] = datetime.now().isoformat()
        USERS[old_teacher_name] = TEACHERS[old_teacher_name]
    
    logger.info(f"✅ تم تحديث بيانات المعلم {new_teacher_name}")
    return True, f"تم تحديث بيانات المعلم {new_teacher_name}"

def remove_teacher(teacher_name):
    """حذف معلم"""
    global TEACHERS, TEACHER_CLASSES, USERS
    
    if teacher_name not in TEACHERS:
        return False, "المعلم غير موجود في النظام"
    
    # حذف المعلم
    del TEACHERS[teacher_name]
    
    if teacher_name in TEACHER_CLASSES:
        del TEACHER_CLASSES[teacher_name]
    
    if teacher_name in USERS:
        del USERS[teacher_name]
    
    logger.info(f"✅ تم حذف المعلم {teacher_name} من النظام")
    return True, f"تم حذف المعلم {teacher_name} من النظام"

# ------------------ دوال المساعدة للصور ------------------
def get_image_base64(image_path):
    """تحويل الصورة إلى Base64"""
    try:
        if os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"خطأ في قراءة الصورة: {str(e)}")
    return None

# محاولة تحميل الشعار
logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

# ------------------ التنسيقات CSS ------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    
    /* إخفاء العناصر الافتراضية */
    #MainMenu, header, footer {
        visibility: hidden !important;
    }
    
    /* الخلفية العامة */
    .stApp {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
    }
    
    /* شريط الأدوات العلوي */
    .top-toolbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 80px;
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 30px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 999999 !important;
        font-family: 'Cairo', sans-serif;
        color: white;
        border-bottom: 3px solid #ffd700;
    }
    
    /* حاوية الشعار */
    .logo-container {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    
    /* صورة الشعار */
    .logo-img {
        width: 50px;
        height: 50px;
        border-radius: 12px;
        object-fit: contain;
        border: 3px solid rgba(255,215,0,0.5);
        background: white;
        padding: 4px;
        box-shadow: 0 4px 10px rgba(0,0,0,0.2);
    }
    
    /* معلومات المدرسة */
    .school-info {
        line-height: 1.3;
    }
    
    .school-name {
        font-size: 22px;
        font-weight: bold;
        margin: 0;
        color: white !important;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
    }
    
    .school-date {
        font-size: 14px;
        opacity: 0.9;
        margin: 0;
        color: rgba(255, 255, 255, 0.9) !important;
    }
    
    /* مساحة المحتوى */
    .content-padding {
        height: 90px;
    }
    
    /* صندوق تسجيل الدخول */
    .login-container {
        max-width: 550px;
        margin: 40px auto;
        padding: 40px;
        background: white;
        border-radius: 30px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.3);
        text-align: center;
        border: 3px solid #ffd700;
    }
    
    /* عنوان تسجيل الدخول */
    .login-title {
        color: #1e3c72;
        font-size: 36px;
        margin-bottom: 30px;
        font-weight: 700;
        text-shadow: 2px 2px 4px rgba(0,0,0,0.1);
    }
    
    /* تسميات الحقول */
    .input-label {
        display: block;
        text-align: right;
        margin: 15px 0 8px 0;
        color: #1e293b;
        font-weight: 600;
        font-size: 16px;
    }
    
    /* حقول الإدخال */
    .login-input {
        width: 100%;
        padding: 18px;
        margin: 5px 0 15px 0;
        border: 2px solid #e2e8f0;
        border-radius: 15px;
        font-size: 18px;
        font-family: 'Cairo', sans-serif;
        text-align: right;
        transition: all 0.3s ease;
        background: white;
        color: #1e293b;
    }
    
    .login-input:focus {
        outline: none;
        border-color: #1e3c72;
        box-shadow: 0 0 0 4px rgba(30,60,114,0.2);
    }
    
    /* زر تسجيل الدخول */
    .login-button {
        width: 100%;
        padding: 18px;
        background: linear-gradient(135deg, #1e3c72, #2a5298);
        color: white !important;
        border: none;
        border-radius: 15px;
        font-size: 22px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        margin-top: 25px;
        font-family: 'Cairo', sans-serif;
        border: 2px solid #ffd700;
    }
    
    .login-button:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 30px rgba(30,60,114,0.4);
        background: linear-gradient(135deg, #2a5298, #1e3c72);
    }
    
    /* قسم معلومات المستخدمين */
    .users-info {
        margin-top: 40px;
        padding: 25px;
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border-radius: 20px;
        border: 3px solid #1e3c72;
        text-align: right;
        direction: rtl;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .users-info h4 {
        color: #1e3c72;
        font-size: 22px;
        margin-bottom: 20px;
        font-weight: 700;
        text-align: center;
        border-bottom: 3px solid #1e3c72;
        padding-bottom: 10px;
    }
    
    /* صف المستخدم */
    .user-row {
        background: white;
        margin: 10px 0;
        padding: 12px 20px;
        border-radius: 12px;
        border-right: 5px solid #1e3c72;
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    
    .user-row:hover {
        transform: translateX(-5px);
        box-shadow: 0 6px 12px rgba(0,0,0,0.15);
    }
    
    /* دور المستخدم */
    .user-role {
        font-weight: 700;
        color: #1e3c72;
        min-width: 100px;
        font-size: 16px;
        background: #e9ecef;
        padding: 4px 12px;
        border-radius: 20px;
        text-align: center;
    }
    
    /* اسم المستخدم */
    .user-name {
        font-weight: 600;
        color: #1e293b;
        flex: 1;
        text-align: right;
        font-size: 16px;
    }
    
    /* كلمة المرور */
    .user-password {
        background: linear-gradient(135deg, #d4edda, #c3e6cb);
        color: #155724;
        font-weight: 700;
        padding: 4px 15px;
        border-radius: 25px;
        font-family: 'Courier New', monospace;
        font-size: 15px;
        min-width: 85px;
        text-align: center;
        border: 1px solid #28a745;
    }
    
    /* الفصل */
    .user-class {
        color: #495057;
        font-size: 14px;
        background: #e9ecef;
        padding: 4px 10px;
        border-radius: 20px;
        font-weight: 600;
    }
    
    /* صندوق المثال */
    .example-box {
        background: linear-gradient(135deg, #fff3cd, #ffe69c);
        border: 2px solid #ffc107;
        border-radius: 12px;
        padding: 15px;
        margin-top: 20px;
        font-size: 15px;
        text-align: right;
        box-shadow: 0 4px 10px rgba(255,193,7,0.3);
    }
    
    .example-box span {
        background: #ffc107;
        color: #856404;
        font-weight: 700;
        padding: 4px 12px;
        border-radius: 25px;
        margin-left: 10px;
        display: inline-block;
        border: 1px solid #856404;
    }
    
    /* الصفحة الرئيسية */
    .home-page {
        max-width: 1000px;
        margin: 0 auto;
        padding: 30px;
        background: white;
        border-radius: 30px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        border: 3px solid #ffd700;
    }
    
    /* عنوان الصفحة الرئيسية */
    .home-title {
        font-size: 42px;
        margin-bottom: 40px;
        color: #1e3c72 !important;
        text-align: center;
        font-weight: 700;
        text-shadow: 3px 3px 6px rgba(0,0,0,0.1);
    }
    
    /* رسالة الترحيب */
    .welcome-message {
        text-align: center;
        padding: 30px;
        margin: 20px 0;
        background: linear-gradient(135deg, #e3f2fd, #bbdefb);
        border-radius: 20px;
        border: 3px solid #1e3c72;
        box-shadow: 0 10px 20px rgba(0,0,0,0.1);
    }
    
    .welcome-text {
        font-size: 28px;
        color: #1e3c72;
        font-weight: 700;
        margin-bottom: 10px;
    }
    
    /* الأزرار الرئيسية */
    .main-button {
        width: 100%;
        padding: 25px;
        background: linear-gradient(135deg, #1e3c72, #2a5298);
        color: white !important;
        border: none;
        border-radius: 20px;
        font-size: 26px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
        font-family: 'Cairo', sans-serif;
        border: 3px solid #ffd700;
        box-shadow: 0 10px 20px rgba(0,0,0,0.2);
    }
    
    .main-button:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 30px rgba(30,60,114,0.4);
        background: linear-gradient(135deg, #2a5298, #1e3c72);
    }
    
    /* صفحة المعلم */
    .teacher-page {
        max-width: 1200px;
        margin: 0 auto;
        padding: 30px;
        background: white;
        border-radius: 30px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        border: 3px solid #ffd700;
    }
    
    /* صفحة الطالب */
    .student-page {
        max-width: 1000px;
        margin: 0 auto;
        padding: 30px;
        background: white;
        border-radius: 30px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        border: 3px solid #ffd700;
    }
    
    /* صفحة المدير */
    .admin-page {
        max-width: 1400px;
        margin: 0 auto;
        padding: 30px;
        background: white;
        border-radius: 30px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.2);
        border: 3px solid #ffd700;
    }
    
    /* عنوان المدير */
    .admin-title {
        font-size: 42px;
        margin-bottom: 40px;
        color: #6f42c1 !important;
        text-align: center;
        font-weight: 700;
        text-shadow: 3px 3px 6px rgba(0,0,0,0.1);
    }
    
    /* رسالة ترحيب المدير */
    .admin-welcome {
        text-align: center;
        padding: 30px;
        margin: 20px 0;
        background: linear-gradient(135deg, #f3e5f5, #e1bee7);
        border-radius: 20px;
        border: 3px solid #6f42c1;
    }
    
    /* أقسام المدير */
    .admin-section {
        background: white;
        border-radius: 20px;
        padding: 30px;
        margin-bottom: 30px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        border: 2px solid #dee2e6;
    }
    
    .admin-section h3 {
        color: #6f42c1 !important;
        border-bottom: 3px solid #6f42c1;
        padding-bottom: 15px;
        margin-bottom: 25px;
        font-size: 26px;
    }
    
    /* تحسين أزرار Streamlit */
    .stButton > button {
        width: 100% !important;
        height: auto !important;
        background: linear-gradient(135deg, #1e3c72, #2a5298) !important;
        color: white !important;
        font-size: 20px !important;
        font-weight: 600 !important;
        border-radius: 15px !important;
        border: 2px solid #ffd700 !important;
        box-shadow: 0 5px 15px rgba(0,0,0,0.2) !important;
        transition: all 0.3s ease !important;
        margin: 10px 0 !important;
        padding: 15px !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2a5298, #1e3c72) !important;
        transform: translateY(-3px) !important;
        box-shadow: 0 10px 25px rgba(30,60,114,0.3) !important;
    }
    
    /* تحسين المقاييس */
    .stMetric {
        background: linear-gradient(135deg, #f8f9fa, #e9ecef) !important;
        border-radius: 15px !important;
        padding: 20px !important;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1) !important;
        border: 2px solid #1e3c72 !important;
    }
    
    .stMetric label {
        color: #1e293b !important;
        font-weight: 600 !important;
        font-size: 18px !important;
    }
    
    .stMetric div {
        color: #1e3c72 !important;
        font-weight: 700 !important;
        font-size: 28px !important;
    }
    
    /* تحسين الجداول */
    .dataframe {
        background: white !important;
        border: 2px solid #1e3c72 !important;
        border-radius: 15px !important;
        overflow: hidden !important;
    }
    
    .dataframe th {
        background: linear-gradient(135deg, #1e3c72, #2a5298) !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        padding: 12px !important;
        text-align: center !important;
    }
    
    .dataframe td {
        padding: 10px !important;
        text-align: center !important;
        border-bottom: 1px solid #dee2e6 !important;
    }
    
    /* تحسين الرسائل */
    .stAlert {
        border-radius: 15px !important;
        padding: 20px !important;
        font-size: 16px !important;
        border: 2px solid !important;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1) !important;
    }
    
    .stAlert.stSuccess {
        background: linear-gradient(135deg, #d4edda, #c3e6cb) !important;
        border-color: #28a745 !important;
        color: #155724 !important;
    }
    
    .stAlert.stError {
        background: linear-gradient(135deg, #f8d7da, #f5c6cb) !important;
        border-color: #dc3545 !important;
        color: #721c24 !important;
    }
    
    .stAlert.stWarning {
        background: linear-gradient(135deg, #fff3cd, #ffe69c) !important;
        border-color: #ffc107 !important;
        color: #856404 !important;
    }
    
    .stAlert.stInfo {
        background: linear-gradient(135deg, #d1ecf1, #bee5eb) !important;
        border-color: #17a2b8 !important;
        color: #0c5460 !important;
    }
    
    /* تحسين حقول الإدخال */
    .stTextInput > div > div > input {
        background: white !important;
        border: 2px solid #1e3c72 !important;
        border-radius: 12px !important;
        font-size: 18px !important;
        padding: 15px !important;
        font-family: 'Cairo', sans-serif !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #ffd700 !important;
        box-shadow: 0 0 0 4px rgba(255,215,0,0.2) !important;
    }
    
    /* تحسين القوائم المنسدلة */
    .stSelectbox > div > div {
        background: white !important;
        border: 2px solid #1e3c72 !important;
        border-radius: 12px !important;
        font-size: 18px !important;
    }
    
    /* تحسين خانات الاختيار */
    .stCheckbox > label {
        color: #1e293b !important;
        font-size: 18px !important;
        font-weight: 500 !important;
    }
    
    /* تحسين القوائم المتعددة */
    .stMultiSelect > div > div {
        background: white !important;
        border: 2px solid #1e3c72 !important;
        border-radius: 12px !important;
        color: #1e293b !important;
        font-size: 16px !important;
    }
    
    /* أزرار الفصول */
    .class-buttons {
        display: flex;
        flex-wrap: wrap;
        gap: 15px;
        margin: 20px 0;
        justify-content: center;
    }
    
    .class-button {
        padding: 15px 30px;
        background: linear-gradient(135deg, #6f42c1, #6610f2);
        color: white !important;
        border: none;
        border-radius: 15px;
        font-size: 18px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
        min-width: 150px;
        border: 2px solid #ffd700;
    }
    
    .class-button:hover {
        background: linear-gradient(135deg, #6610f2, #6f42c1);
        transform: translateY(-3px);
        box-shadow: 0 10px 20px rgba(106,13,173,0.3);
    }
    
    /* حاوية قائمة الطلاب */
    .student-list-container {
        max-height: 400px;
        overflow-y: auto;
        margin: 20px 0;
        padding: 20px;
        background: #f8f9fa;
        border-radius: 15px;
        border: 2px solid #1e3c72;
    }
    
    /* زر العودة */
    .back-button {
        margin-top: 30px !important;
        background: linear-gradient(135deg, #6c757d, #495057) !important;
        border-color: #ffd700 !important;
    }
    
    /* علامات التبويب في صفحة المدير */
    .admin-tabs {
        display: flex;
        justify-content: center;
        gap: 15px;
        margin-bottom: 30px;
        flex-wrap: wrap;
    }
    
    .admin-tab {
        padding: 15px 30px;
        background: linear-gradient(135deg, #e9ecef, #dee2e6);
        color: #495057 !important;
        border: none;
        border-radius: 12px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
        border: 2px solid transparent;
    }
    
    .admin-tab:hover {
        background: linear-gradient(135deg, #dee2e6, #ced4da);
        transform: translateY(-2px);
    }
    
    .admin-tab.active {
        background: linear-gradient(135deg, #1e3c72, #2a5298);
        color: white !important;
        border-color: #ffd700;
        box-shadow: 0 5px 15px rgba(30,60,114,0.3);
    }
    
    /* نموذج الإدارة */
    .admin-form-section {
        background: #f8f9fa;
        padding: 25px;
        border-radius: 15px;
        margin-bottom: 25px;
        border: 2px solid #1e3c72;
    }
    
    .form-title {
        color: #495057 !important;
        font-size: 20px !important;
        font-weight: 600 !important;
        margin-bottom: 20px !important;
    }
    
    /* كلمات المرور الظاهرة */
    .password-cell {
        background: linear-gradient(135deg, #e3f2fd, #bbdefb) !important;
        color: #1e3c72 !important;
        font-weight: 600 !important;
        font-family: 'Courier New', monospace !important;
        padding: 4px 10px !important;
        border-radius: 20px !important;
        border: 1px solid #1e3c72 !important;
    }
    
    /* تنسيقات إضافية */
    .footer-note {
        text-align: center;
        margin-top: 50px;
        padding: 20px;
        color: #6c757d;
        font-size: 14px;
        border-top: 1px solid #dee2e6;
    }
    
    /* تنسيقات للأجهزة المحمولة */
    @media (max-width: 768px) {
        .login-container {
            margin: 20px;
            padding: 20px;
        }
        
        .home-page, .teacher-page, .student-page, .admin-page {
            padding: 15px;
        }
        
        .user-row {
            flex-direction: column;
            align-items: stretch;
        }
        
        .user-role {
            min-width: auto;
        }
        
        .school-name {
            font-size: 18px;
        }
        
        .top-toolbar {
            padding: 0 15px;
        }
    }
</style>
""", unsafe_allow_html=True)

# ------------------ دوال عرض الشريط العلوي ------------------
def show_toolbar():
    """عرض الشريط العلوي"""
    arabic_date = get_arabic_date()
    user_role_display = "مدير النظام" if st.session_state.user_role == "admin" else ("معلم" if st.session_state.user_role == "teacher" else "طالب")
    
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">🏫 مدرسة السلام الإعدادية الثانوية</p>
                <p class="school-date">{arabic_date}</p>
            </div>
        </div>
        <div class="user-status">
            {st.session_state.user_name} | {user_role_display}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# ------------------ دوال التنقل ------------------
def safe_rerun():
    """إعادة تشغيل آمنة"""
    try:
        st.rerun()
    except Exception as e:
        logger.error(f"خطأ في إعادة التشغيل: {str(e)}")

# ------------------ إدارة حالة الجلسة ------------------
# تهيئة حالة الجلسة
session_defaults = {
    "logged_in": False,
    "user_role": "",
    "user_name": "",
    "page": "login",
    "selected_class": None,
    "teacher_mode": None,
    "admin_tab": "dashboard",
    "student_subtab": "list",
    "teacher_subtab": "list",
    "class_subtab": "list",
    "local_attendance_data": []
}

for key, value in session_defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value

# ------------------ الصفحات ------------------
# صفحة تسجيل الدخول
if st.session_state.page == "login":
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <div class="login-title">🔐 نظام إدارة الغياب</div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        # حقل اسم المستخدم
        st.markdown('<div class="input-label">👤 اسم المستخدم</div>', unsafe_allow_html=True)
        username = st.text_input("اسم المستخدم", 
                                placeholder="أدخل اسم المستخدم",
                                label_visibility="collapsed",
                                key="login_username")
        
        # حقل كلمة المرور
        st.markdown('<div class="input-label">🔑 كلمة المرور</div>', unsafe_allow_html=True)
        password = st.text_input("كلمة المرور", type="password", 
                                placeholder="أدخل كلمة المرور",
                                label_visibility="collapsed",
                                key="login_password")
        
        # زر تسجيل الدخول
        login_clicked = st.button("✅ تسجيل الدخول", use_container_width=True, key="login_button")
        
        # معالجة تسجيل الدخول
        if login_clicked:
            if username and password:
                if username in USERS:
                    if USERS[username]["password"] == password:
                        st.session_state.logged_in = True
                        st.session_state.user_name = username
                        st.session_state.user_role = USERS[username]["role"]
                        
                        # تسجيل وقت آخر دخول
                        if username in USERS:
                            USERS[username]["last_login"] = datetime.now().isoformat()
                        
                        # توجيه المستخدم حسب دوره
                        if USERS[username]["role"] == "admin":
                            st.session_state.page = "admin_dashboard"
                            st.session_state.admin_tab = "dashboard"
                        elif USERS[username]["role"] == "teacher":
                            st.session_state.page = "home"
                            st.session_state.teacher_name = USERS[username].get("display_name", username)
                            st.session_state.teacher_classes = USERS[username].get("classes", [])
                            st.session_state.teacher_mode = None
                            st.session_state.selected_class = None
                        else:  # student
                            st.session_state.page = "home"
                            st.session_state.student_name = USERS[username].get("student_name", username)
                        
                        st.success(f"✅ مرحباً {USERS[username].get('display_name', username)}!")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("❌ كلمة المرور غير صحيحة")
                else:
                    st.error("❌ اسم المستخدم غير موجود")
            else:
                st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")
        
        # قسم بيانات الدخول
        st.markdown("""
        <div class="users-info">
            <h4>📋 بيانات الدخول المتاحة</h4>
            
            <div class="user-row">
                <span class="user-role">👑 المدير</span>
                <span class="user-name">admin</span>
                <span class="user-password">admin1234</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🏫 مينا سمير</span>
                <span class="user-name">مينا سمير</span>
                <span class="user-password">mina1234</span>
                <span class="user-class">Class B, C</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🏫 فادي حبيب</span>
                <span class="user-name">فادي حبيب</span>
                <span class="user-password">fady5678</span>
                <span class="user-class">Class D, E</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🎓 Class B</span>
                <span class="user-name">محمد علي محمد</span>
                <span class="user-password">b1001</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🎓 Class C</span>
                <span class="user-name">أحمد محمد أحمد</span>
                <span class="user-password">c1001</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🎓 Class D</span>
                <span class="user-name">فؤاد محمد فؤاد</span>
                <span class="user-password">d1001</span>
            </div>
            
            <div class="user-row">
                <span class="user-role">👨‍🎓 Class E</span>
                <span class="user-name">نبيل محمد نبيل</span>
                <span class="user-password">e1001</span>
            </div>
            
            <div class="example-box">
                <span>💡 مثال</span> اسم المستخدم: <strong>محمد علي محمد</strong> | كلمة المرور: <strong>b1001</strong>
            </div>
            
            <div class="example-box">
                <span>📌 ملاحظة</span> جميع الطلاب في نفس الفصل لهم نفس النمط (b1001-b1010, c1001-c1010, d1001-d1010, e1001-e1010)
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="footer-note">© 2025 جميع الحقوق محفوظة</div>', unsafe_allow_html=True)
    
    st.markdown('</div>', unsafe_allow_html=True)

# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    show_toolbar()
    
    # الصفحة الرئيسية المشتركة (للمعلم والطالب)
    if st.session_state.page == "home":
        st.markdown('<div class="home-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        if st.session_state.user_role == "teacher":
            # رسالة ترحيب للمعلم
            teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
            teacher_classes = st.session_state.get('teacher_classes', [])
            
            welcome_html = f"""
            <div class="welcome-message">
                <div class="welcome-text">مرحباً بك 👨‍🏫 الأستاذ {teacher_name}</div>
                <div class="user-info">📚 الفصول التي تدرسها: {', '.join(teacher_classes)}</div>
            </div>
            """
            st.markdown(welcome_html, unsafe_allow_html=True)
            
            st.markdown("### 📋 اختر المهمة التي تريد تنفيذها:")
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
            # رسالة ترحيب للطالب
            student_name = st.session_state.get('student_name', st.session_state.user_name)
            student_class = get_student_class(student_name)
            
            welcome_html = f"""
            <div class="welcome-message">
                <div class="welcome-text">مرحباً بك 👨‍🎓 {student_name}</div>
                <div class="user-info">🏫 فصل: {student_class}</div>
            </div>
            """
            st.markdown(welcome_html, unsafe_allow_html=True)
            
            if st.button("📊 تقرير الغياب الخاص بي", key="student_dashboard_btn", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        elif st.session_state.user_role == "admin":
            # رسالة ترحيب للمدير
            welcome_html = f"""
            <div class="admin-welcome">
                <div class="admin-welcome-text">مرحباً بك 👑 {st.session_state.user_name}</div>
                <div class="user-info">لوحة التحكم الشاملة لإدارة النظام</div>
            </div>
            """
            st.markdown(welcome_html, unsafe_allow_html=True)
            
            st.markdown("### 📋 اختر المهمة التي تريد تنفيذها:")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 لوحة التحكم", key="admin_dashboard_btn", use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.session_state.admin_tab = "dashboard"
                    st.rerun()
            
            with col2:
                if st.button("📝 تسجيل الغياب", key="admin_record_btn", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "record"
                    st.session_state.selected_class = None
                    st.rerun()
            
            with col3:
                if st.button("📊 الإحصائيات", key="admin_stats_btn", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "statistics"
                    st.session_state.selected_class = None
                    st.rerun()
        
        # زر تسجيل الخروج للجميع
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
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
    elif st.session_state.user_role in ["teacher", "admin"] and st.session_state.page == "teacher_attendance":
        st.markdown('<div class="teacher-page">', unsafe_allow_html=True)
        
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        
        # إذا كان المدير، يمكنه اختيار أي فصل
        if st.session_state.user_role == "admin":
            teacher_classes = list(CLASSES.keys())
        else:
            teacher_classes = st.session_state.get('teacher_classes', [])
        
        # إذا لم يتم اختيار فصل بعد، عرض أزرار الفصول
        if not st.session_state.selected_class:
            st.markdown('<div class="home-title">🎯 اختر الفصل</div>', unsafe_allow_html=True)
            
            st.markdown(f"### 👨‍🏫 المعلم: **{teacher_name}**")
            st.markdown(f"### 📚 اختر الفصل الذي تريد:")
            
            # عرض أزرار الفصول
            if teacher_classes:
                cols = st.columns(2)
                for idx, class_name in enumerate(teacher_classes):
                    with cols[idx % 2]:
                        if st.button(f"🎯 {class_name}", key=f"class_{class_name}", use_container_width=True):
                            st.session_state.selected_class = class_name
                            st.rerun()
            else:
                st.warning("⚠️ لا يوجد فصول متاحة. الرجاء التواصل مع الإدارة.")
        
        # إذا تم اختيار فصل، عرض الخيارات حسب الوضع
        else:
            selected_class = st.session_state.selected_class
            
            # زر العودة لاختيار فصل آخر
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button("🔄 اختيار فصل آخر", key="change_class", use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
            
            st.markdown("---")
            
            # إذا اختار تسجيل الغياب
            if st.session_state.teacher_mode == "record":
                st.markdown(f'<div class="home-title">📝 تسجيل غياب {selected_class}</div>', unsafe_allow_html=True)
                
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
                        "اختر الطلاب الغائبين",
                        class_students,
                        label_visibility="collapsed",
                        key="absent_students"
                    )
                    
                    # اختيار نوع الغياب
                    st.markdown("### 📝 اختر نوع الغياب")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        excuse = st.checkbox("غياب بعذر", key="excuse")
                    with col_b:
                        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")
                    
                    if excuse and no_excuse:
                        st.warning("⚠️ الرجاء اختيار نوع واحد فقط من أنواع الغياب")
                    
                    st.markdown("---")
                    
                    # زر تسجيل الغياب
                    if st.button("💾 حفظ وتسجيل الغياب", key="record_attendance", use_container_width=True):
                        if excuse and no_excuse:
                            st.warning("⚠️ الرجاء اختيار نوع واحد فقط")
                        elif not (excuse or no_excuse):
                            st.warning("⚠️ من فضلك اختر نوع الغياب")
                        else:
                            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                            
                            with st.spinner("جاري تسجيل الغياب..."):
                                try:
                                    failed, telegram_status, telegram_details, success_count = record_attendance(
                                        selected, teacher_name, selected_class, status_label
                                    )
                                except Exception as e:
                                    st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                                    logger.error(f"خطأ في تسجيل الغياب: {str(e)}")
                                else:
                                    if success_count > 0:
                                        st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                                        
                                        # عرض ملخص التسجيل
                                        with st.expander("📊 ملخص التسجيل", expanded=True):
                                            col1, col2 = st.columns(2)
                                            with col1:
                                                st.markdown("**تفاصيل التسجيل:**")
                                                st.markdown(f"""
                                                - 👨‍🏫 المعلم: {teacher_name}
                                                - 🏫 الفصل: {selected_class}
                                                - 📅 التاريخ: {get_current_date()}
                                                - 📝 نوع الغياب: {status_label}
                                                """)
                                            with col2:
                                                st.markdown("**إحصائيات:**")
                                                st.markdown(f"""
                                                - 👥 إجمالي الطلاب: {len(class_students)}
                                                - ❌ عدد الغائبين: {len(selected)}
                                                - ✅ عدد الحاضرين: {len(class_students) - len(selected)}
                                                """)
                                            
                                            if selected:
                                                st.markdown("**الطلاب الغائبون:**")
                                                for student in selected:
                                                    st.markdown(f"- {student}")
                                            else:
                                                st.info("لا يوجد طلاب غائبون")
                                            
                                            if telegram_status == "✅ تم الإرسال":
                                                st.info("📱 تم إرسال إشعار بالغياب إلى التلغرام")
                                            elif telegram_status == "⚠️ غير مكون":
                                                st.warning("📱 لم يتم إعداد إشعارات التلغرام")
                else:
                    st.error(f"❌ لا يوجد طلاب مسجلين في {selected_class}")
            
            # إذا اختار عرض الإحصائيات
            elif st.session_state.teacher_mode == "statistics":
                st.markdown(f'<div class="home-title">📊 إحصائيات {selected_class}</div>', unsafe_allow_html=True)
                
                with st.spinner("جاري تحميل الإحصائيات..."):
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
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown("### ✅ الحضور")
                    st.metric("عدد مرات الحضور", stats["present_count"])
                with col_b:
                    st.markdown("### ❌ الغياب بعذر")
                    st.metric("عدد مرات الغياب بعذر", stats["absent_excused"])
                with col_c:
                    st.markdown("### ❌ الغياب بدون عذر")
                    st.metric("عدد مرات الغياب بدون عذر", stats["absent_unexcused"])
                
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
                        "absent": "إجمالي الغياب",
                        "excused": "غياب بعذر",
                        "unexcused": "غياب بدون عذر",
                        "rate": "نسبة الحضور %"
                    })
                    
                    # تنسيق نسبة الحضور
                    student_stats_df["نسبة الحضور %"] = student_stats_df["نسبة الحضور %"].apply(lambda x: f"{x:.1f}%")
                    
                    st.dataframe(student_stats_df, use_container_width=True, hide_index=True)
                    
                else:
                    st.info("لا توجد سجلات لهذا الفصل بعد.")
                
                # عرض جميع السجلات للفصل
                st.markdown("---")
                st.markdown(f"### 📅 سجل الحضور للفصل {selected_class}")
                
                if not history_df.empty:
                    # عرض السجلات
                    all_history = history_df.copy()
                    all_history = all_history.rename(columns={
                        "student": "الطالب",
                        "teacher": "المعلم",
                        "date_clean": "التاريخ",
                        "status_clean": "الحالة"
                    })
                    
                    st.dataframe(all_history, use_container_width=True, height=400)
                    st.info(f"**عدد السجلات المعروضة:** {len(all_history)} سجل")
                    
                else:
                    st.info("لا توجد سجلات حضور لهذا الفصل بعد.")
        
        # زر العودة للصفحة الرئيسية
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home", use_container_width=True):
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
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        
        st.markdown("---")
        
        student_name = st.session_state.get('student_name', st.session_state.user_name)
        student_class = get_student_class(student_name)
        
        # عرض معلومات الطالب
        col1, col2 = st.columns(2)
        with col1:
            st.info(f"**اسم الطالب:** {student_name}")
        with col2:
            st.info(f"**الفصل:** {student_class}")
        
        # عرض بيانات الطالب
        with st.spinner("جاري تحميل بياناتك..."):
            df_student = get_student_records(student_name)
        
        if df_student.empty:
            st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        else:
            # حساب الإحصاءات
            absent_count = int((df_student["الحالة"].str.contains("غياب", na=False)).sum())
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
            
        # زر العودة للصفحة الرئيسية في الأسفل
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student_bottom", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة مدير النظام
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown('<div class="admin-page">', unsafe_allow_html=True)
        
        # العنوان
        st.markdown('<div class="admin-title">👨‍💼 لوحة تحكم مدير النظام</div>', unsafe_allow_html=True)
        
        # رسالة ترحيب
        welcome_html = f"""
        <div class="admin-welcome">
            <div class="admin-welcome-text">مرحباً بك 👑 {st.session_state.get('display_name', st.session_state.user_name)}</div>
            <div class="user-info">لوحة التحكم الشاملة لإدارة النظام</div>
        </div>
        """
        st.markdown(welcome_html, unsafe_allow_html=True)
        
        # علامات التبويب
        tabs = ["dashboard", "students", "teachers", "classes", "settings"]
        tab_names = {
            "dashboard": "📊 لوحة التحكم",
            "students": "👥 إدارة الطلاب",
            "teachers": "👨‍🏫 إدارة المعلمين",
            "classes": "🏫 إدارة الفصول",
            "settings": "⚙️ الإعدادات"
        }
        
        # عرض علامات التبويب
        cols = st.columns(len(tabs))
        for idx, tab in enumerate(tabs):
            with cols[idx]:
                if st.button(tab_names[tab], key=f"admin_tab_{tab}", use_container_width=True):
                    st.session_state.admin_tab = tab
                    st.rerun()
        
        st.markdown("---")
        
        # محتوى علامات التبويب
        if st.session_state.admin_tab == "dashboard":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 📊 إحصائيات النظام")
            
            with st.spinner("جاري تحميل إحصائيات النظام..."):
                stats = get_system_statistics()
            
            # عرض الإحصائيات
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("إجمالي السجلات", stats["total_records"])
            with col2:
                st.metric("عدد الطلاب", stats["total_students"])
            with col3:
                st.metric("عدد الفصول", stats["total_classes"])
            with col4:
                st.metric("عدد المعلمين", stats["total_teachers"])
            
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("عدد الحضور", stats["present_count"])
            with col6:
                st.metric("عدد الغياب", stats["absent_count"])
            with col7:
                st.metric("نسبة الحضور", f"{stats['attendance_rate']:.1f}%")
            with col8:
                st.metric("آخر تحديث", stats["last_update"])
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # عرض قائمة الفصول
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 🏫 الفصول")
            
            for class_name, students in CLASSES.items():
                with st.expander(f"{class_name} ({len(students)} طالب)"):
                    st.markdown(f"**قائمة الطلاب في {class_name}:**")
                    for student in students:
                        st.markdown(f"- {student}")
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # عرض آخر السجلات
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 📅 آخر سجلات الغياب")
            
            all_records = get_all_records()
            if not all_records.empty:
                recent_records = all_records.head(50)
                display_cols = ["student", "teacher", "class", "date_clean", "status_clean"]
                recent_records_display = recent_records[display_cols].copy() if all(col in recent_records.columns for col in display_cols) else recent_records
                
                # إعادة تسمية الأعمدة
                column_map = {
                    "student": "الطالب",
                    "teacher": "المعلم",
                    "class": "الفصل",
                    "date_clean": "التاريخ",
                    "status_clean": "الحالة"
                }
                recent_records_display = recent_records_display.rename(columns={k: v for k, v in column_map.items() if k in recent_records_display.columns})
                
                st.dataframe(recent_records_display, use_container_width=True, hide_index=True)
                
                if st.button("📋 عرض كل السجلات", key="view_all_records"):
                    st.markdown("### 📋 جميع سجلات الغياب")
                    all_display = all_records.copy()
                    all_display = all_display.rename(columns={k: v for k, v in column_map.items() if k in all_display.columns})
                    st.dataframe(all_display, use_container_width=True, hide_index=True)
                    
            else:
                st.info("لا توجد سجلات غياب في النظام بعد.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "students":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 👥 إدارة الطلاب")
            
            # علامات تبويب فرعية لإدارة الطلاب
            student_tabs = ["list", "add", "edit", "remove", "import"]
            student_tab_names = {
                "list": "📋 قائمة الطلاب",
                "add": "➕ إضافة طالب",
                "edit": "✏️ تعديل طالب",
                "remove": "🗑️ حذف طالب",
                "import": "📥 استيراد"
            }
            
            student_tab_cols = st.columns(len(student_tabs))
            for idx, student_tab in enumerate(student_tabs):
                with student_tab_cols[idx]:
                    if st.button(student_tab_names[student_tab], key=f"student_tab_{student_tab}", use_container_width=True):
                        st.session_state.student_subtab = student_tab
                        st.rerun()
            
            if "student_subtab" not in st.session_state:
                st.session_state.student_subtab = "list"
            
            st.markdown("---")
            
            # قائمة الطلاب
            if st.session_state.student_subtab == "list":
                st.markdown("#### 📋 قائمة جميع الطلاب")
                
                if ALL_STUDENTS:
                    # إنشاء DataFrame للطلاب
                    students_data = []
                    for student in ALL_STUDENTS:
                        students_data.append({
                            "اسم الطالب": student,
                            "الفصل": STUDENT_TO_CLASS.get(student, "غير محدد"),
                            "كلمة المرور": USERS.get(student, {}).get("password", "غير معروفة")
                        })
                    
                    students_df = pd.DataFrame(students_data)
                    st.dataframe(students_df, use_container_width=True, hide_index=True)
                    
                    # عرض عدد الطلاب
                    st.info(f"**إجمالي عدد الطلاب:** {len(ALL_STUDENTS)}")
                    
                else:
                    st.info("لا يوجد طلاب في النظام.")
            
            # إضافة طالب جديد
            elif st.session_state.student_subtab == "add":
                st.markdown("#### ➕ إضافة طالب جديد")
                
                with st.form("add_student_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        new_student_name = st.text_input("اسم الطالب الجديد *", key="new_student_name")
                        new_student_class = st.selectbox("اختر الفصل *", list(CLASSES.keys()), key="new_student_class")
                    
                    with col2:
                        new_student_password = st.text_input("كلمة المرور *", key="new_student_password", type="password")
                        new_student_password_confirm = st.text_input("تأكيد كلمة المرور *", key="new_student_password_confirm", type="password")
                    
                    submitted = st.form_submit_button("➕ إضافة الطالب", use_container_width=True)
                    
                    if submitted:
                        if not new_student_name.strip():
                            st.error("❌ من فضلك أدخل اسم الطالب")
                        elif not new_student_password:
                            st.error("❌ من فضلك أدخل كلمة المرور")
                        elif new_student_password != new_student_password_confirm:
                            st.error("❌ كلمتا المرور غير متطابقتين")
                        else:
                            with st.spinner("جاري إضافة الطالب..."):
                                success, message = add_student_to_class(
                                    new_student_name.strip(),
                                    new_student_class,
                                    new_student_password
                                )
                                if success:
                                    st.success(f"✅ {message}")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # تعديل طالب
            elif st.session_state.student_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات طالب")
                
                if not ALL_STUDENTS:
                    st.info("لا يوجد طلاب في النظام.")
                else:
                    student_to_edit = st.selectbox("اختر الطالب للتعديل", ALL_STUDENTS, key="student_to_edit")
                    
                    if student_to_edit:
                        current_class = STUDENT_TO_CLASS.get(student_to_edit, "")
                        
                        with st.form("edit_student_form"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                new_student_name = st.text_input("الاسم الجديد", value=student_to_edit, key="edit_student_name")
                                class_options = list(CLASSES.keys())
                                new_student_class = st.selectbox(
                                    "الفصل الجديد", 
                                    class_options, 
                                    index=class_options.index(current_class) if current_class in class_options else 0,
                                    key="edit_student_class"
                                )
                            
                            with col2:
                                st.info("اترك كلمة المرور فارغة إذا لم ترغب في تغييرها")
                                new_student_password = st.text_input("كلمة المرور الجديدة", type="password", key="edit_student_password")
                                new_student_password_confirm = st.text_input("تأكيد كلمة المرور الجديدة", type="password", key="edit_student_password_confirm")
                            
                            submitted = st.form_submit_button("✏️ تحديث بيانات الطالب", use_container_width=True)
                            
                            if submitted:
                                if not new_student_name.strip():
                                    st.error("❌ من فضلك أدخل اسم الطالب")
                                elif new_student_password and new_student_password != new_student_password_confirm:
                                    st.error("❌ كلمتا المرور غير متطابقتين")
                                else:
                                    with st.spinner("جاري تحديث البيانات..."):
                                        success, message = update_student_info(
                                            student_to_edit,
                                            new_student_name.strip(),
                                            new_student_class,
                                            new_student_password if new_student_password else None
                                        )
                                        if success:
                                            st.success(f"✅ {message}")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {message}")
            
            # حذف طالب
            elif st.session_state.student_subtab == "remove":
                st.markdown("#### ❌ حذف طالب")
                
                if not ALL_STUDENTS:
                    st.info("لا يوجد طلاب في النظام.")
                else:
                    student_to_delete = st.selectbox("اختر الطالب للحذف", ALL_STUDENTS, key="student_to_delete")
                    
                    if student_to_delete:
                        student_class = STUDENT_TO_CLASS.get(student_to_delete, "")
                        
                        st.warning(f"**الطالب المحدد:** {student_to_delete}")
                        st.warning(f"**الفصل:** {student_class}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_student", use_container_width=True):
                                with st.spinner("جاري حذف الطالب..."):
                                    success, message = remove_student_from_class(student_to_delete)
                                    if success:
                                        st.success(f"✅ {message}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                        with col_b:
                            if st.button("❌ إلغاء", key="cancel_delete_student", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            # استيراد طلاب
            elif st.session_state.student_subtab == "import":
                st.markdown("#### 📥 استيراد طلاب من ملف CSV")
                st.markdown("""
                **تنسيق الملف المطلوب:**
                - يجب أن يحتوي على الأعمدة: `name`, `class`
                - كلمة المرور سيتم إنشاؤها تلقائياً
                """)
                
                uploaded_file = st.file_uploader("اختر ملف CSV", type=['csv'])
                
                if uploaded_file is not None:
                    try:
                        df = pd.read_csv(uploaded_file)
                        st.write("معاينة البيانات:", df.head())
                        
                        if 'name' in df.columns and 'class' in df.columns:
                            if st.button("بدء الاستيراد", use_container_width=True):
                                added = []
                                failed = []
                                
                                with st.spinner("جاري استيراد الطلاب..."):
                                    progress_bar = st.progress(0)
                                    for idx, row in df.iterrows():
                                        student_name = str(row['name']).strip()
                                        class_name = str(row['class']).strip()
                                        
                                        if class_name not in CLASSES:
                                            CLASSES[class_name] = []
                                        
                                        # إنشاء كلمة مرور عشوائية
                                        password = ''.join(random.choices(string.digits, k=6))
                                        
                                        success, message = add_student_to_class(student_name, class_name, password)
                                        if success:
                                            added.append(student_name)
                                        else:
                                            failed.append((student_name, message))
                                        
                                        progress_bar.progress((idx + 1) / len(df))
                                
                                st.success(f"✅ تم استيراد {len(added)} طالب بنجاح")
                                if failed:
                                    st.warning(f"⚠️ فشل استيراد {len(failed)} طالب")
                                    for name, msg in failed:
                                        st.write(f"- {name}: {msg}")
                                
                                if st.button("تحديث الصفحة"):
                                    st.rerun()
                        else:
                            st.error("❌ الملف يجب أن يحتوي على عمودي 'name' و 'class'")
                    except Exception as e:
                        st.error(f"❌ خطأ في قراءة الملف: {str(e)}")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "teachers":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 👨‍🏫 إدارة المعلمين")
            
            # علامات تبويب فرعية لإدارة المعلمين
            teacher_tabs = ["list", "add", "edit", "remove"]
            teacher_tab_names = {
                "list": "📋 قائمة المعلمين",
                "add": "➕ إضافة معلم",
                "edit": "✏️ تعديل معلم",
                "remove": "🗑️ حذف معلم"
            }
            
            teacher_tab_cols = st.columns(len(teacher_tabs))
            for idx, teacher_tab in enumerate(teacher_tabs):
                with teacher_tab_cols[idx]:
                    if st.button(teacher_tab_names[teacher_tab], key=f"teacher_tab_{teacher_tab}", use_container_width=True):
                        st.session_state.teacher_subtab = teacher_tab
                        st.rerun()
            
            if "teacher_subtab" not in st.session_state:
                st.session_state.teacher_subtab = "list"
            
            st.markdown("---")
            
            # قائمة المعلمين
            if st.session_state.teacher_subtab == "list":
                st.markdown("#### 📋 قائمة جميع المعلمين")
                
                if TEACHERS:
                    teachers_data = []
                    for teacher_name, teacher_info in TEACHERS.items():
                        teachers_data.append({
                            "اسم المعلم": teacher_name,
                            "الفصول": ", ".join(teacher_info.get("classes", [])),
                            "كلمة المرور": teacher_info.get("password", "غير معروفة"),
                            "التخصص": teacher_info.get("specialization", "غير محدد"),
                            "الهاتف": teacher_info.get("phone", "غير محدد")
                        })
                    
                    teachers_df = pd.DataFrame(teachers_data)
                    st.dataframe(teachers_df, use_container_width=True, hide_index=True)
                    st.info(f"**إجمالي عدد المعلمين:** {len(TEACHERS)}")
                    
                else:
                    st.info("لا يوجد معلمين في النظام.")
            
            # إضافة معلم جديد
            elif st.session_state.teacher_subtab == "add":
                st.markdown("#### ➕ إضافة معلم جديد")
                
                with st.form("add_teacher_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        new_teacher_name = st.text_input("اسم المعلم الجديد *", key="new_teacher_name")
                        new_teacher_password = st.text_input("كلمة المرور *", key="new_teacher_password", type="password")
                        new_teacher_specialization = st.text_input("التخصص", key="new_teacher_specialization")
                    
                    with col2:
                        new_teacher_password_confirm = st.text_input("تأكيد كلمة المرور *", key="new_teacher_password_confirm", type="password")
                        new_teacher_phone = st.text_input("رقم الهاتف", key="new_teacher_phone")
                        new_teacher_classes = st.multiselect("الفصول التي يدرسها *", list(CLASSES.keys()), key="new_teacher_classes")
                    
                    submitted = st.form_submit_button("➕ إضافة المعلم", use_container_width=True)
                    
                    if submitted:
                        if not new_teacher_name.strip():
                            st.error("❌ من فضلك أدخل اسم المعلم")
                        elif not new_teacher_password:
                            st.error("❌ من فضلك أدخل كلمة المرور")
                        elif new_teacher_password != new_teacher_password_confirm:
                            st.error("❌ كلمتا المرور غير متطابقتين")
                        elif not new_teacher_classes:
                            st.error("❌ من فضلك اختر الفصول التي يدرسها المعلم")
                        else:
                            with st.spinner("جاري إضافة المعلم..."):
                                success, message = add_teacher(
                                    new_teacher_name.strip(),
                                    new_teacher_password,
                                    new_teacher_classes,
                                    new_teacher_specialization if new_teacher_specialization else None,
                                    new_teacher_phone if new_teacher_phone else None
                                )
                                if success:
                                    st.success(f"✅ {message}")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # تعديل معلم
            elif st.session_state.teacher_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات معلم")
                
                if not TEACHERS:
                    st.info("لا يوجد معلمين في النظام.")
                else:
                    teacher_to_edit = st.selectbox("اختر المعلم للتعديل", list(TEACHERS.keys()), key="teacher_to_edit")
                    
                    if teacher_to_edit:
                        current_data = TEACHERS[teacher_to_edit]
                        current_classes = current_data.get("classes", [])
                        
                        with st.form("edit_teacher_form"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                new_teacher_name = st.text_input("الاسم الجديد", value=teacher_to_edit, key="edit_teacher_name")
                                new_teacher_password = st.text_input("كلمة المرور الجديدة", type="password", key="edit_teacher_password")
                                new_teacher_specialization = st.text_input("التخصص", value=current_data.get("specialization", ""), key="edit_teacher_specialization")
                            
                            with col2:
                                new_teacher_password_confirm = st.text_input("تأكيد كلمة المرور الجديدة", type="password", key="edit_teacher_password_confirm")
                                new_teacher_phone = st.text_input("رقم الهاتف", value=current_data.get("phone", ""), key="edit_teacher_phone")
                                new_teacher_classes = st.multiselect("الفصول الجديدة", list(CLASSES.keys()), default=current_classes, key="edit_teacher_classes")
                            
                            st.info("اترك كلمة المرور فارغة إذا لم ترغب في تغييرها")
                            
                            submitted = st.form_submit_button("✏️ تحديث بيانات المعلم", use_container_width=True)
                            
                            if submitted:
                                if not new_teacher_name.strip():
                                    st.error("❌ من فضلك أدخل اسم المعلم")
                                elif new_teacher_password and new_teacher_password != new_teacher_password_confirm:
                                    st.error("❌ كلمتا المرور غير متطابقتين")
                                elif not new_teacher_classes:
                                    st.error("❌ من فضلك اختر الفصول التي يدرسها المعلم")
                                else:
                                    with st.spinner("جاري تحديث البيانات..."):
                                        success, message = update_teacher_info(
                                            teacher_to_edit,
                                            new_teacher_name.strip(),
                                            new_teacher_password if new_teacher_password else None,
                                            new_teacher_classes,
                                            new_teacher_specialization if new_teacher_specialization else None,
                                            new_teacher_phone if new_teacher_phone else None
                                        )
                                        if success:
                                            st.success(f"✅ {message}")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {message}")
            
            # حذف معلم
            elif st.session_state.teacher_subtab == "remove":
                st.markdown("#### ❌ حذف معلم")
                
                if not TEACHERS:
                    st.info("لا يوجد معلمين في النظام.")
                else:
                    teacher_to_delete = st.selectbox("اختر المعلم للحذف", list(TEACHERS.keys()), key="teacher_to_delete")
                    
                    if teacher_to_delete:
                        teacher_classes = TEACHERS[teacher_to_delete].get("classes", [])
                        
                        st.warning(f"**المعلم المحدد:** {teacher_to_delete}")
                        st.warning(f"**الفصول التي يدرسها:** {', '.join(teacher_classes)}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_teacher", use_container_width=True):
                                with st.spinner("جاري حذف المعلم..."):
                                    success, message = remove_teacher(teacher_to_delete)
                                    if success:
                                        st.success(f"✅ {message}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                        with col_b:
                            if st.button("❌ إلغاء", key="cancel_delete_teacher", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "classes":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 🏫 إدارة الفصول")
            
            # علامات تبويب فرعية لإدارة الفصول
            class_tabs = ["list", "add", "edit", "remove"]
            class_tab_names = {
                "list": "📋 قائمة الفصول",
                "add": "➕ إضافة فصل",
                "edit": "✏️ تعديل فصل",
                "remove": "🗑️ حذف فصل"
            }
            
            class_tab_cols = st.columns(len(class_tabs))
            for idx, class_tab in enumerate(class_tabs):
                with class_tab_cols[idx]:
                    if st.button(class_tab_names[class_tab], key=f"class_tab_{class_tab}", use_container_width=True):
                        st.session_state.class_subtab = class_tab
                        st.rerun()
            
            if "class_subtab" not in st.session_state:
                st.session_state.class_subtab = "list"
            
            st.markdown("---")
            
            # قائمة الفصول
            if st.session_state.class_subtab == "list":
                st.markdown("#### 📋 قائمة الفصول")
                
                if CLASSES:
                    class_data = []
                    for class_name, students in CLASSES.items():
                        # الحصول على المعلم المسؤول
                        class_teacher = "غير معين"
                        for teacher, classes in TEACHER_CLASSES.items():
                            if class_name in classes:
                                class_teacher = teacher
                                break
                        
                        class_data.append({
                            "اسم الفصل": class_name,
                            "عدد الطلاب": len(students),
                            "المعلم المسؤول": class_teacher,
                            "قائمة الطلاب": ", ".join(students[:5]) + ("..." if len(students) > 5 else "")
                        })
                    
                    class_df = pd.DataFrame(class_data)
                    st.dataframe(class_df, use_container_width=True, hide_index=True)
                    st.info(f"**إجمالي عدد الفصول:** {len(CLASSES)}")
                    
                else:
                    st.info("لا يوجد فصول في النظام.")
            
            # إضافة فصل جديد
            elif st.session_state.class_subtab == "add":
                st.markdown("#### ➕ إضافة فصل جديد")
                
                with st.form("add_class_form"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        new_class_name = st.text_input("اسم الفصل الجديد *", key="new_class_name")
                        teacher_options = list(TEACHERS.keys())
                        if not teacher_options:
                            st.warning("⚠️ لا يوجد معلمين في النظام. الرجاء إضافة معلم أولاً.")
                            new_class_teacher = None
                        else:
                            new_class_teacher = st.selectbox("المعلم المسؤول *", teacher_options, key="new_class_teacher")
                    
                    with col2:
                        st.markdown("**قائمة الطلاب (اختياري)**")
                        new_class_students_text = st.text_area(
                            "أسماء الطلاب (افصل بينها بفاصلة)", 
                            key="new_class_students", 
                            height=150,
                            help="مثال: أحمد محمد، محمود علي، ..."
                        )
                    
                    submitted = st.form_submit_button("➕ إضافة الفصل", use_container_width=True)
                    
                    if submitted:
                        if not new_class_name.strip():
                            st.error("❌ من فضلك أدخل اسم الفصل")
                        elif not new_class_teacher:
                            st.error("❌ من فضلك اختر المعلم المسؤول")
                        else:
                            students_list = []
                            if new_class_students_text.strip():
                                students_list = [s.strip() for s in new_class_students_text.split(",") if s.strip()]
                            
                            with st.spinner("جاري إضافة الفصل..."):
                                success, message = add_class(new_class_name.strip(), new_class_teacher, students_list)
                                if success:
                                    st.success(f"✅ {message}")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # تعديل فصل
            elif st.session_state.class_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات فصل")
                
                if not CLASSES:
                    st.info("لا يوجد فصول في النظام.")
                else:
                    class_to_edit = st.selectbox("اختر الفصل للتعديل", list(CLASSES.keys()), key="class_to_edit")
                    
                    if class_to_edit:
                        # الحصول على المعلم المسؤول
                        class_teacher = None
                        for teacher, classes in TEACHER_CLASSES.items():
                            if class_to_edit in classes:
                                class_teacher = teacher
                                break
                        
                        current_students = CLASSES[class_to_edit]
                        
                        with st.form("edit_class_form"):
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                new_class_name = st.text_input("الاسم الجديد", value=class_to_edit, key="edit_class_name")
                                teacher_options = [""] + list(TEACHERS.keys())
                                new_class_teacher = st.selectbox(
                                    "المعلم الجديد (اختياري)", 
                                    teacher_options,
                                    index=teacher_options.index(class_teacher) if class_teacher in teacher_options else 0,
                                    key="edit_class_teacher"
                                )
                            
                            with col2:
                                st.markdown("**الطلاب الحاليين:**")
                                for student in current_students[:10]:
                                    st.markdown(f"- {student}")
                                if len(current_students) > 10:
                                    st.markdown(f"... و {len(current_students) - 10} آخرون")
                            
                            submitted = st.form_submit_button("✏️ تحديث بيانات الفصل", use_container_width=True)
                            
                            if submitted:
                                if not new_class_name.strip():
                                    st.error("❌ من فضلك أدخل اسم الفصل")
                                else:
                                    with st.spinner("جاري تحديث البيانات..."):
                                        success, message = update_class_info(
                                            class_to_edit,
                                            new_class_name.strip(),
                                            new_class_teacher if new_class_teacher else None
                                        )
                                        if success:
                                            st.success(f"✅ {message}")
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(f"❌ {message}")
            
            # حذف فصل
            elif st.session_state.class_subtab == "remove":
                st.markdown("#### ❌ حذف فصل")
                
                if not CLASSES:
                    st.info("لا يوجد فصول في النظام.")
                else:
                    class_to_delete = st.selectbox("اختر الفصل للحذف", list(CLASSES.keys()), key="class_to_delete")
                    
                    if class_to_delete:
                        class_students = CLASSES.get(class_to_delete, [])
                        
                        st.warning(f"**الفصل المحدد:** {class_to_delete}")
                        st.warning(f"**عدد الطلاب:** {len(class_students)}")
                        
                        if class_students:
                            st.warning(f"**الطلاب:** {', '.join(class_students[:5])}{'...' if len(class_students) > 5 else ''}")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_class", use_container_width=True):
                                with st.spinner("جاري حذف الفصل..."):
                                    success, message = remove_class(class_to_delete)
                                    if success:
                                        st.success(f"✅ {message}")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"❌ {message}")
                        with col_b:
                            if st.button("❌ إلغاء", key="cancel_delete_class", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "settings":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### ⚙️ إعدادات النظام")
            
            # معلومات النظام
            st.markdown("#### ℹ️ معلومات النظام")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("حالة الاتصال", connection_status)
            with col2:
                st.metric("اسم الـ Sheet", SHEET_NAME if SHEET_NAME else "غير محدد")
            
            # إعدادات الاتصال
            st.markdown("#### 🔗 إعدادات الاتصال")
            with st.expander("تفاصيل الاتصال"):
                if connection_details:
                    st.info(connection_details)
                if connection_error:
                    st.error(f"خطأ: {connection_error}")
                
                if BOT_TOKEN:
                    st.success("✅ Telegram Bot Token: متوفر")
                else:
                    st.warning("⚠️ Telegram Bot Token: غير متوفر")
                
                if CHAT_ID:
                    st.success("✅ Telegram Chat ID: متوفر")
                else:
                    st.warning("⚠️ Telegram Chat ID: غير متوفر")
            
            # إحصائيات النظام
            st.markdown("#### 📊 إحصائيات النظام")
            stats = get_system_statistics()
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("إجمالي المستخدمين", len(USERS))
            with col2:
                st.metric("إجمالي السجلات", stats["total_records"])
            with col3:
                st.metric("آخر تحديث", stats["last_update"])
            
            # زر مسح البيانات المحلية
            st.markdown("#### 🗑️ إدارة البيانات")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ مسح البيانات المحلية", use_container_width=True):
                    if "local_attendance_data" in st.session_state:
                        st.session_state.local_attendance_data = []
                        st.success("✅ تم مسح البيانات المحلية")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.info("لا توجد بيانات محلية")
            
            with col2:
                if st.button("🔄 إعادة تعيين الجلسة", use_container_width=True):
                    for key in list(st.session_state.keys()):
                        if key not in ["logged_in", "user_role", "user_name", "page"]:
                            del st.session_state[key]
                    st.success("✅ تم إعادة تعيين الجلسة")
                    time.sleep(1)
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # أزرار التحكم
        st.markdown("---")
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("🏠 الرئيسية", key="admin_back_to_home", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        with col2:
            if st.button("🚪 تسجيل الخروج", key="admin_logout", use_container_width=True):
                st.session_state.logged_in = False
                st.session_state.user_role = ""
                st.session_state.user_name = ""
                st.session_state.page = "login"
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()

# تذييل الصفحة
st.markdown("""
<div style="text-align: center; padding: 20px; color: #6c757d; font-size: 14px; background: rgba(255,255,255,0.9); margin-top: 50px;">
    © 2025 نظام إدارة الغياب المدرسي - جميع الحقوق محفوظة
</div>
""", unsafe_allow_html=True)
