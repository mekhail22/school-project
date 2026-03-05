import streamlit as st
import pandas as pd
from datetime import datetime
import os
import json
import logging
import base64
import requests

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
st.set_page_config(page_title="نظام الغياب", layout="wide", initial_sidebar_state="collapsed")

# ------------------ App settings ------------------
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

# معلمين النظام
TEACHERS = {
    "مينا سمير": {
        "password": "mina1234",
        "display_name": "مينا سمير",
        "classes": ["Class B", "Class C"],
        "role": "teacher"
    },
    "فادي حبيب": {
        "password": "fady5678",
        "display_name": "فادي حبيب",
        "classes": ["Class D", "Class E"],
        "role": "teacher"
    }
}

# مستخدمون وكلمات مرورهم
USERS = {
    # مدير النظام - صلاحيات كاملة
    "admin": {
        "password": "admin1234",
        "role": "admin",
        "display_name": "مدير النظام"
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
import random
import string
for student in ALL_STUDENTS:
    if student in student_passwords:
        USERS[student] = {
            "password": student_passwords[student],
            "role": "student",
            "student_name": student
        }
    else:
        # إنشاء كلمة مرور عشوائية
        password = ''.join(random.choices(string.digits, k=6))
        USERS[student] = {
            "password": password,
            "role": "student",
            "student_name": student
        }

# ------------------ تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل الإعدادات من Streamlit Secrets"""
    try:
        secrets = st.secrets
        
        # Telegram
        BOT_TOKEN = None
        CHAT_ID = None
        
        # محاولة قراءة Telegram بعدة طرق
        if hasattr(secrets, 'telegram'):
            if hasattr(secrets.telegram, 'bot_token'):
                BOT_TOKEN = secrets.telegram.bot_token
            elif hasattr(secrets.telegram, 'get'):
                BOT_TOKEN = secrets.telegram.get('bot_token')
                
            if hasattr(secrets.telegram, 'chat_id'):
                CHAT_ID = secrets.telegram.chat_id
            elif hasattr(secrets.telegram, 'get'):
                CHAT_ID = secrets.telegram.get('chat_id')
        
        # App settings
        SHEET_NAME = 'school_attendance'
        if hasattr(secrets, 'sheets'):
            if hasattr(secrets.sheets, 'name'):
                SHEET_NAME = secrets.sheets.name
            elif hasattr(secrets.sheets, 'get'):
                SHEET_NAME = secrets.sheets.get('name', 'school_attendance')
        
        # Service Account - محاولة قراءة بعدة طرق
        SERVICE_ACCOUNT = None
        
        # الطريقة 1: SERVICE_ACCOUNT_JSON كسلسلة JSON كاملة
        if hasattr(secrets, 'SERVICE_ACCOUNT_JSON'):
            try:
                SERVICE_ACCOUNT = json.loads(secrets.SERVICE_ACCOUNT_JSON)
                logger.info("✅ تم تحميل SERVICE_ACCOUNT من SERVICE_ACCOUNT_JSON")
            except Exception as e:
                logger.error(f"خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
        # الطريقة 2: SERVICE_ACCOUNT كـ section منفصل
        if SERVICE_ACCOUNT is None and hasattr(secrets, 'SERVICE_ACCOUNT'):
            try:
                sa = secrets.SERVICE_ACCOUNT
                SERVICE_ACCOUNT = {
                    'type': sa.type if hasattr(sa, 'type') else sa.get('type', ''),
                    'project_id': sa.project_id if hasattr(sa, 'project_id') else sa.get('project_id', ''),
                    'private_key_id': sa.private_key_id if hasattr(sa, 'private_key_id') else sa.get('private_key_id', ''),
                    'private_key': sa.private_key if hasattr(sa, 'private_key') else sa.get('private_key', ''),
                    'client_email': sa.client_email if hasattr(sa, 'client_email') else sa.get('client_email', ''),
                    'client_id': sa.client_id if hasattr(sa, 'client_id') else sa.get('client_id', ''),
                    'auth_uri': sa.auth_uri if hasattr(sa, 'auth_uri') else sa.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                    'token_uri': sa.token_uri if hasattr(sa, 'token_uri') else sa.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'auth_provider_x509_cert_url': sa.auth_provider_x509_cert_url if hasattr(sa, 'auth_provider_x509_cert_url') else sa.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
                    'client_x509_cert_url': sa.client_x509_cert_url if hasattr(sa, 'client_x509_cert_url') else sa.get('client_x509_cert_url', '')
                }
                logger.info("✅ تم تحميل SERVICE_ACCOUNT من SERVICE_ACCOUNT section")
            except Exception as e:
                logger.error(f"خطأ في تحميل SERVICE_ACCOUNT section: {e}")
        
        # الطريقة 3: محاولة قراءة كل مفتاح على حدة (للتوافق مع الإصدارات القديمة)
        if SERVICE_ACCOUNT is None:
            try:
                required_keys = ['type', 'project_id', 'private_key_id', 'private_key', 'client_email']
                sa_dict = {}
                all_found = True
                
                for key in required_keys:
                    upper_key = key.upper()
                    if hasattr(secrets, upper_key):
                        sa_dict[key] = getattr(secrets, upper_key)
                    elif hasattr(secrets, key):
                        sa_dict[key] = getattr(secrets, key)
                    else:
                        all_found = False
                        break
                
                if all_found:
                    SERVICE_ACCOUNT = sa_dict
                    logger.info("✅ تم تحميل SERVICE_ACCOUNT من مفاتيح منفصلة")
            except Exception as e:
                logger.error(f"خطأ في تحميل SERVICE_ACCOUNT من مفاتيح منفصلة: {e}")
        
        return {
            'BOT_TOKEN': BOT_TOKEN,
            'CHAT_ID': CHAT_ID,
            'SHEET_NAME': SHEET_NAME,
            'SERVICE_ACCOUNT': SERVICE_ACCOUNT
        }
        
    except Exception as e:
        logger.error(f"خطأ في تحميل الإعدادات: {str(e)}")
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
                    headers = ["student", "teacher", "class", "status", "date"]
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

# Helper functions
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
    
    if df.empty:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
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
            "attendance_rate": 0,
            "students": []
        }
    
    # حساب الإحصائيات
    total_records = len(class_df)
    
    # حساب الحضور والغياب
    present_count = 0
    absent_count = 0
    
    if "status" in class_df.columns:
        present_count = len(class_df[class_df["status"] == "حاضر"])
        absent_count = len(class_df[class_df["status"].str.contains("غياب", na=False)])
    
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
            
            if "status" in student_df.columns:
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
    else:
        class_df["date_clean"] = ""
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        elif "حاضر" in status_str:
            return "حاضر"
        return status_str
    
    if "status" in class_df.columns:
        class_df["status_clean"] = class_df["status"].apply(clean_status)
    else:
        class_df["status_clean"] = ""
    
    # ترتيب حسب التاريخ
    if not class_df.empty and 'date' in class_df.columns:
        try:
            class_df = class_df.sort_values("date", ascending=False)
        except:
            pass
    
    # إضافة الأعمدة إذا لم تكن موجودة
    if "student" not in class_df.columns:
        class_df["student"] = ""
    if "teacher" not in class_df.columns:
        class_df["teacher"] = ""
    
    return class_df[["student", "teacher", "date_clean", "status_clean"]]

# Telegram functions
def send_telegram_message(message):
    if not BOT_TOKEN or not CHAT_ID:
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
    if worksheet and rows:
        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append((f"الفصل {class_name}", str(ex)))
    
    # حفظ البيانات محليًا في session_state دائمًا
    try:
        # إنشاء أو تحديث البيانات المحلية
        if "local_attendance_data" not in st.session_state:
            st.session_state["local_attendance_data"] = []
        
        # إضافة الصفوف الجديدة إلى البيانات المحلية
        for row in rows:
            st.session_state["local_attendance_data"].append({
                "student": row[0],
                "teacher": row[1],
                "class": row[2],
                "status": row[3],
                "date": row[4]
            })
        
        logger.info(f"💾 تم حفظ {len(rows)} سجل في الذاكرة المحلية")
        
        # إذا لم يكن هناك اتصال بـ Google Sheets، نستخدم العدد المحلي
        if worksheet is None or len(failed) > 0:
            success_count = len(rows)
            
    except Exception as e:
        failed.append((f"الفصل {class_name}", f"خطأ في الحفظ المحلي: {str(e)}"))
    
    # رسالة تلغرام
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if rows:
        absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
        
        # حساب عدد الحاضرين
        present_count = len(class_students) - len(selected_absent)
        
        # رسالة معدلة
        message = f"""📋 <b>تسجيل الغياب</b>
📅 التاريخ: {date_display}
👨‍🏫 المعلم: {teacher_name}
🏫 الفصل: {class_name}
❌ عدد الغائبين: {len(selected_absent)}
✅ عدد الحاضرين: {present_count}
👥 الطلاب الغائبون: {absent_students}"""
        
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
    if df.empty or "student" not in df.columns:
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
    if not df_matches.empty and 'date' in df_matches.columns:
        try:
            df_matches = df_matches.sort_values("date", ascending=False)
        except:
            pass
    
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

# وظائف خاصة بمدير النظام
def get_all_records():
    """الحصول على جميع سجلات الغياب"""
    df = read_sheet()
    if df.empty:
        return pd.DataFrame()
    
    # تنظيف البيانات
    df = df.copy()
    if "date" in df.columns:
        df["date_clean"] = df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    else:
        df["date_clean"] = ""
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        return status_str
    
    if "status" in df.columns:
        df["status_clean"] = df["status"].apply(clean_status)
    else:
        df["status_clean"] = ""
    
    # ترتيب حسب التاريخ
    if not df.empty and 'date' in df.columns:
        try:
            df = df.sort_values("date", ascending=False)
        except:
            pass
    
    return df

def add_student_to_class(student_name, class_name, password):
    """إضافة طالب جديد إلى فصل"""
    global CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
    if class_name not in CLASSES:
        CLASSES[class_name] = []
    
    # التحقق من عدم وجود الطالب بالفعل
    if student_name in ALL_STUDENTS:
        return False, "الطالب موجود بالفعل في النظام"
    
    # إضافة الطالب إلى الفصل
    CLASSES[class_name].append(student_name)
    STUDENT_TO_CLASS[student_name] = class_name
    ALL_STUDENTS.append(student_name)
    
    # إضافة المستخدم مع كلمة مرور إجبارية
    if not password or password.strip() == "":
        return False, "كلمة المرور مطلوبة"
    
    USERS[student_name] = {
        "password": password.strip(),
        "role": "student",
        "student_name": student_name
    }
    
    return True, f"تم إضافة الطالب {student_name} إلى {class_name}"

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
    
    return True, f"تم حذف الطالب {student_name} من النظام"

def add_class(class_name, teacher_name, students_list=None):
    """إضافة فصل جديد"""
    global CLASSES, TEACHER_CLASSES, STUDENT_TO_CLASS, ALL_STUDENTS
    
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
    
    return True, f"تم حذف الفصل {class_name} وجميع طلابه"

def add_teacher(teacher_name, password, classes):
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
        "role": "teacher"
    }
    
    # إضافة إلى قائمة الفصول
    TEACHER_CLASSES[teacher_name] = classes
    
    # إضافة إلى المستخدمين
    USERS[teacher_name] = TEACHERS[teacher_name]
    
    return True, f"تم إضافة المعلم {teacher_name} بنجاح"

def update_teacher_info(old_teacher_name, new_teacher_name, new_password, new_classes):
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
            "role": "teacher"
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
    
    return True, f"تم حذف المعلم {teacher_name} من النظام"

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
        if "status" in df.columns:
            present_count = len(df[df["status"] == "حاضر"])
            absent_count = len(df[df["status"].str.contains("غياب", na=False)])
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    else:
        present_count = 0
        absent_count = 0
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
    
    return {
        "total_records": total_records,
        "total_students": total_students,
        "total_classes": total_classes,
        "total_teachers": total_teachers,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_rate": attendance_rate,
        "class_stats": class_stats,
        "last_update": datetime.now().strftime("%d/%m/%Y %H:%M")
    }

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

# CSS محسن
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    
    /* إخفاء العناصر الافتراضية */
    #MainMenu, header, footer {visibility: hidden !important;}
    
    /* خلفية التطبيق */
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
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 30px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        z-index: 999999 !important;
        font-family: 'Cairo', sans-serif;
        border-bottom: 3px solid #667eea;
    }
    
    .logo-container {
        display: flex;
        align-items: center;
        gap: 15px;
    }
    
    .logo-img {
        width: 50px;
        height: 50px;
        border-radius: 12px;
        object-fit: contain;
        border: 2px solid #667eea;
        background: white;
        padding: 4px;
        box-shadow: 0 4px 10px rgba(102, 126, 234, 0.3);
    }
    
    .school-info {
        line-height: 1.3;
    }
    
    .school-name {
        font-size: 20px;
        font-weight: bold;
        margin: 0;
        color: #333 !important;
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .school-date {
        font-size: 14px;
        opacity: 0.8;
        margin: 0;
        color: #666 !important;
    }
    
    .content-padding {
        height: 90px;
    }
    
    /* حاوية المحتوى الرئيسي */
    .main-container {
        max-width: 1200px;
        margin: 0 auto;
        padding: 20px;
    }
    
    /* بطاقات المحتوى */
    .content-card {
        background: white;
        border-radius: 20px;
        padding: 30px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        margin-bottom: 30px;
        border: 1px solid rgba(102, 126, 234, 0.2);
    }
    
    /* صفحة تسجيل الدخول */
    .login-container {
        max-width: 450px;
        margin: 60px auto;
        padding: 40px;
        background: white;
        border-radius: 20px;
        box-shadow: 0 20px 60px rgba(0,0,0,0.15);
        text-align: center;
        border: 1px solid rgba(102, 126, 234, 0.2);
    }
    
    .login-title {
        background: linear-gradient(135deg, #667eea, #764ba2);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 32px;
        margin-bottom: 30px;
        font-weight: 700;
    }
    
    /* حقول الإدخال */
    .stTextInput > div > div > input {
        background: #f8f9fa !important;
        color: #333 !important;
        border: 2px solid #e1e4e8 !important;
        font-size: 16px !important;
        padding: 12px 15px !important;
        border-radius: 12px !important;
        direction: rtl !important;
        font-family: 'Cairo', sans-serif !important;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1) !important;
    }
    
    /* الأزرار */
    .stButton > button {
        width: 100% !important;
        background: linear-gradient(135deg, #667eea, #764ba2) !important;
        color: white !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        border-radius: 12px !important;
        border: none !important;
        padding: 12px 20px !important;
        transition: all 0.3s ease !important;
        margin: 10px 0 !important;
        font-family: 'Cairo', sans-serif !important;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3) !important;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4) !important;
    }
    
    /* أزرار ثانوية */
    .stButton > button.secondary {
        background: linear-gradient(135deg, #f5f7fa, #e4e8eb) !important;
        color: #667eea !important;
        box-shadow: none !important;
    }
    
    /* أزرار تسجيل الخروج */
    .stButton > button.logout-btn {
        background: linear-gradient(135deg, #ff6b6b, #ee5a5a) !important;
    }
    
    /* الميترك (الإحصائيات) */
    .stMetric {
        background: white !important;
        border-radius: 15px !important;
        padding: 20px !important;
        box-shadow: 0 5px 20px rgba(0,0,0,0.05) !important;
        border: 1px solid #e1e4e8 !important;
        text-align: center !important;
    }
    
    .stMetric label {
        color: #667eea !important;
        font-weight: 600 !important;
        font-size: 16px !important;
    }
    
    .stMetric div {
        color: #333 !important;
        font-weight: 700 !important;
        font-size: 24px !important;
    }
    
    /* قوائم متعددة الاختيار */
    .stMultiSelect > div > div {
        background: white !important;
        border: 2px solid #e1e4e8 !important;
        border-radius: 12px !important;
        color: #333 !important;
        font-size: 16px !important;
    }
    
    .stMultiSelect > div > div:hover {
        border-color: #667eea !important;
    }
    
    /* مربعات الاختيار */
    .stCheckbox > label {
        color: #333 !important;
        font-size: 16px !important;
        font-weight: 500 !important;
    }
    
    /* الجداول */
    .dataframe {
        background: white !important;
        color: #333 !important;
        border: 1px solid #e1e4e8 !important;
        font-size: 14px !important;
        border-radius: 12px !important;
        overflow: hidden !important;
    }
    
    .dataframe th {
        background: linear-gradient(135deg, #667eea, #764ba2) !important;
        color: white !important;
        border: none !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        padding: 12px !important;
    }
    
    .dataframe td {
        border: 1px solid #e1e4e8 !important;
        color: #333 !important;
        padding: 10px !important;
    }
    
    /* علامات التبويب */
    .admin-tabs {
        display: flex;
        gap: 10px;
        margin-bottom: 30px;
        flex-wrap: wrap;
        justify-content: center;
    }
    
    .admin-tab {
        padding: 12px 25px;
        background: white;
        color: #667eea !important;
        border: 2px solid #667eea;
        border-radius: 10px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
    }
    
    .admin-tab:hover {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white !important;
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(102, 126, 234, 0.3);
    }
    
    .admin-tab.active {
        background: linear-gradient(135deg, #667eea, #764ba2);
        color: white !important;
        border-color: transparent;
    }
    
    /* أقسام الإدارة */
    .admin-section {
        background: white;
        border-radius: 15px;
        padding: 25px;
        margin-bottom: 25px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.05);
        border: 1px solid #e1e4e8;
    }
    
    .admin-section h3 {
        color: #667eea !important;
        border-bottom: 2px solid #e1e4e8;
        padding-bottom: 15px;
        margin-bottom: 20px;
    }
    
    /* رسائل التنبيه */
    .stAlert {
        border-radius: 12px !important;
        padding: 15px !important;
        font-size: 14px !important;
        border: none !important;
    }
    
    .stAlert.stSuccess {
        background: #d4edda !important;
        color: #155724 !important;
        border-right: 4px solid #28a745 !important;
    }
    
    .stAlert.stError {
        background: #f8d7da !important;
        color: #721c24 !important;
        border-right: 4px solid #dc3545 !important;
    }
    
    .stAlert.stWarning {
        background: #fff3cd !important;
        color: #856404 !important;
        border-right: 4px solid #ffc107 !important;
    }
    
    .stAlert.stInfo {
        background: #d1ecf1 !important;
        color: #0c5460 !important;
        border-right: 4px solid #17a2b8 !important;
    }
    
    /* رسالة الترحيب */
    .welcome-message {
        text-align: center;
        padding: 30px;
        margin: 20px 0;
        background: linear-gradient(135deg, #667eea, #764ba2);
        border-radius: 15px;
        color: white !important;
    }
    
    .welcome-text {
        font-size: 24px;
        font-weight: 700;
        margin-bottom: 10px;
    }
    
    /* بيانات تسجيل الدخول للتجربة */
    .demo-credentials {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 15px;
        padding: 20px;
        margin-top: 30px;
        text-align: center;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .demo-title {
        color: white;
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 15px;
    }
    
    .demo-item {
        color: white;
        font-size: 14px;
        margin: 5px 0;
        opacity: 0.9;
    }
    
    .demo-item strong {
        color: #ffd700;
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
        <div></div>
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
if "selected_class" not in st.session_state:
    st.session_state.selected_class = None
if "teacher_mode" not in st.session_state:
    st.session_state.teacher_mode = None
if "admin_tab" not in st.session_state:
    st.session_state.admin_tab = "dashboard"

# صفحة تسجيل الدخول الرئيسية
if st.session_state.page == "login":
    # إخفاء الـ toolbar في صفحة تسجيل الدخول
    st.markdown('<div style="height: 30px"></div>', unsafe_allow_html=True)
    
    # تصميم صفحة تسجيل الدخول
    st.markdown("""
    <div class="login-container">
        <div class="login-title">🔐 تسجيل الدخول</div>
    </div>
    """, unsafe_allow_html=True)
    
    # حاوية الإدخالات
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        # حقل إدخال اسم المستخدم
        username = st.text_input("👤 اسم المستخدم", 
                                placeholder="أدخل اسم المستخدم",
                                key="login_username")
        
        # حقل إدخال كلمة السر
        password = st.text_input("🔑 كلمة المرور", type="password", 
                                placeholder="أدخل كلمة المرور",
                                key="login_password")
        
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
                            st.session_state.page = "admin_dashboard"
                            st.session_state.admin_tab = "dashboard"
                        elif USERS[username]["role"] == "teacher":
                            st.session_state.page = "home"
                            st.session_state.teacher_name = USERS[username]["display_name"]
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
    
    # بيانات تسجيل الدخول للتجربة
    st.markdown("""
    <div class="demo-credentials">
        <div class="demo-title">📋 بيانات تسجيل الدخول للتجربة</div>
        <div class="demo-item"><strong>👑 مدير النظام:</strong> admin | admin1234</div>
        <div class="demo-item"><strong>👨‍🏫 معلم:</strong> مينا سمير | mina1234</div>
        <div class="demo-item"><strong>👨‍🏫 معلم:</strong> فادي حبيب | fady5678</div>
        <div class="demo-item"><strong>👨‍🎓 طالب:</strong> أحمد محمد أحمد | c1001</div>
    </div>
    """, unsafe_allow_html=True)
        
# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    show_toolbar()
    
    st.markdown('<div class="main-container">', unsafe_allow_html=True)
    
    # الصفحة الرئيسية المشتركة (للمعلم والطالب)
    if st.session_state.page == "home":
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        
        if st.session_state.user_role == "teacher":
            # رسالة ترحيب
            st.markdown(f"""
            <div class="welcome-message">
                <div class="welcome-text">👨‍🏫 مرحباً بك {st.session_state.user_name}</div>
                <div style="font-size: 18px; opacity: 0.9;">يمكنك اختيار المهمة التي تريد تنفيذها:</div>
            </div>
            """, unsafe_allow_html=True)
            
            # أزرار المهام الرئيسية
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
            st.markdown(f"""
            <div class="welcome-message">
                <div class="welcome-text">👨‍🎓 مرحباً بك {st.session_state.user_name}</div>
                <div style="font-size: 18px; opacity: 0.9;">يمكنك عرض تقرير الغياب الخاص بك:</div>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", key="student_dashboard_btn", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # زر تسجيل الخروج
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
    
    # صفحة المعلم لتسجيل الغياب وعرض الإحصائيات
    elif st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        teacher_classes = st.session_state.get('teacher_classes', [])
        
        # إذا لم يتم اختيار فصل بعد، عرض أزرار الفصول
        if not st.session_state.selected_class:
            st.markdown('<h2 style="text-align: center; color: #667eea;">🎯 اختر الفصل</h2>', unsafe_allow_html=True)
            
            st.markdown(f"<p style='text-align: center; font-size: 18px;'>👨‍🏫 المعلم: <strong>{teacher_name}</strong></p>", unsafe_allow_html=True)
            
            # عرض أزرار الفصول التي يدرسها المعلم فقط
            if teacher_classes:
                cols = st.columns(len(teacher_classes))
                for idx, class_name in enumerate(teacher_classes):
                    with cols[idx]:
                        if st.button(f"📚 {class_name}", key=f"class_{class_name}", use_container_width=True):
                            st.session_state.selected_class = class_name
                            st.rerun()
            else:
                st.warning("⚠️ لا يوجد فصول موكلة إليك. الرجاء التواصل مع الإدارة.")
        
        # إذا تم اختيار فصل، عرض الخيارات حسب الوضع
        else:
            selected_class = st.session_state.selected_class
            
            # إذا اختار تسجيل الغياب
            if st.session_state.teacher_mode == "record":
                st.markdown(f'<h2 style="text-align: center; color: #667eea;">📝 تسجيل غياب {selected_class}</h2>', unsafe_allow_html=True)
                
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
                        st.metric("المعلم", teacher_name)
                    with col2:
                        st.metric("الفصل", selected_class)
                    with col3:
                        st.metric("عدد الطلاب", len(class_students))
                    
                    st.markdown("---")
                    
                    # اختيار الطلاب الغائبين
                    st.markdown("### 👇 اختر الطلاب الغائبين")
                    selected = st.multiselect(
                        "اختر الطلاب الغائبين",
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

                    st.markdown("---")
                    
                    # زر تسجيل الغياب
                    if st.button("💾 حفظ وتسجيل الغياب", key="record_attendance", use_container_width=True):
                        if excuse and no_excuse:
                            st.warning("⚠️ اختر نوع واحد فقط من أنواع الغياب")
                        elif not (excuse or no_excuse):
                            st.warning("⚠️ من فضلك اختر نوع الغياب")
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
                st.markdown(f'<h2 style="text-align: center; color: #667eea;">📊 إحصائيات {selected_class}</h2>', unsafe_allow_html=True)
                
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
                    if stats["total_records"] > 0 and stats["total_students"] > 0:
                        daily_avg = stats["total_records"] / stats["total_students"]
                        st.metric("متوسط السجلات", f"{daily_avg:.1f}")
                    else:
                        st.metric("متوسط السجلات", "0")
                
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
                
                # عرض جميع السجلات للفصل
                st.markdown("---")
                st.markdown(f"### 📅 سجل الحضور للفصل {selected_class}")
                
                if not history_df.empty:
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
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_bottom", use_container_width=True):
                st.session_state.page = "home"
                st.session_state.selected_class = None
                st.session_state.teacher_mode = None
                st.rerun()
    
    # صفحة الطالب لعرض تقاريره
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        
        st.markdown('<h2 style="text-align: center; color: #667eea;">📊 تقرير الغياب الخاص بي</h2>', unsafe_allow_html=True)
        
        student_name = st.session_state.get('student_name', st.session_state.user_name)
        
        # عرض بيانات الطالب
        df_student = get_student_records(student_name)
        
        if df_student.empty:
            st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        else:
            # حساب الإحصاءات
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
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
    
    # صفحة مدير النظام
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown('<div class="content-card">', unsafe_allow_html=True)
        
        # العنوان
        st.markdown('<h2 style="text-align: center; color: #667eea;">👨‍💼 لوحة تحكم مدير النظام</h2>', unsafe_allow_html=True)
        
        # رسالة ترحيب
        st.markdown(f"""
        <div class="welcome-message">
            <div class="welcome-text">👑 مرحباً بك {st.session_state.get('display_name', st.session_state.user_name)}</div>
            <div style="font-size: 18px; opacity: 0.9;">لوحة التحكم الشاملة لإدارة النظام</div>
        </div>
        """, unsafe_allow_html=True)
        
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
            
            # الحصول على إحصائيات النظام
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
                st.metric("نسبة الحضور", f"{stats['attendance_rate']:.1f}%")
            
            col5, col6, col7, col8 = st.columns(4)
            with col5:
                st.metric("عدد الحضور", stats["present_count"])
            with col6:
                st.metric("عدد الغياب", stats["absent_count"])
            with col7:
                st.metric("عدد المعلمين", stats["total_teachers"])
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
                recent_records_display = recent_records[["student", "teacher", "class", "date_clean", "status_clean"]].copy()
                recent_records_display = recent_records_display.rename(columns={
                    "student": "الطالب",
                    "teacher": "المعلم",
                    "class": "الفصل",
                    "date_clean": "التاريخ",
                    "status_clean": "الحالة"
                })
                
                st.dataframe(recent_records_display, use_container_width=True, hide_index=True)
                
                if st.button("📋 عرض كل السجلات", key="view_all_records"):
                    st.markdown("### 📋 جميع سجلات الغياب")
                    all_records_display = all_records[["student", "teacher", "class", "date_clean", "status_clean"]].copy()
                    all_records_display = all_records_display.rename(columns={
                        "student": "الطالب",
                        "teacher": "المعلم",
                        "class": "الفصل",
                        "date_clean": "التاريخ",
                        "status_clean": "الحالة"
                    })
                    
                    st.dataframe(all_records_display, use_container_width=True, hide_index=True)
            else:
                st.info("لا توجد سجلات غياب في النظام بعد.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "students":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 👥 إدارة الطلاب")
            
            # علامات تبويب فرعية لإدارة الطلاب
            student_tabs = ["add", "edit", "remove", "list"]
            student_tab_names = {
                "add": "➕ إضافة طالب",
                "edit": "✏️ تعديل طالب",
                "remove": "🗑️ حذف طالب",
                "list": "📋 قائمة الطلاب"
            }
            
            student_tab_cols = st.columns(len(student_tabs))
            for idx, student_tab in enumerate(student_tabs):
                with student_tab_cols[idx]:
                    if st.button(student_tab_names[student_tab], key=f"student_tab_{student_tab}", use_container_width=True):
                        st.session_state.student_subtab = student_tab
                        st.rerun()
            
            if "student_subtab" not in st.session_state:
                st.session_state.student_subtab = "add"
            
            st.markdown("---")
            
            # إضافة طالب جديد
            if st.session_state.student_subtab == "add":
                st.markdown("#### ➕ إضافة طالب جديد")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # إدخال اسم الطالب
                    new_student_name = st.text_input("اسم الطالب الجديد *", key="new_student_name")
                    
                    # اختيار الفصل
                    class_options = list(CLASSES.keys())
                    new_student_class = st.selectbox("اختر الفصل *", class_options, key="new_student_class")
                
                with col2:
                    # إدخال كلمة المرور (إجباري)
                    new_student_password = st.text_input("كلمة المرور *", key="new_student_password", type="password",
                                                        help="كلمة المرور مطلوبة")
                    
                    # تأكيد كلمة المرور
                    new_student_password_confirm = st.text_input("تأكيد كلمة المرور *", type="password",
                                                                key="new_student_password_confirm")
                
                # زر الإضافة
                if st.button("➕ إضافة الطالب", key="add_student_btn", use_container_width=True):
                    if not new_student_name.strip():
                        st.error("❌ من فضلك أدخل اسم الطالب")
                    elif not new_student_password:
                        st.error("❌ من فضلك أدخل كلمة المرور")
                    elif new_student_password != new_student_password_confirm:
                        st.error("❌ كلمتا المرور غير متطابقتين")
                    else:
                        success, message = add_student_to_class(
                            new_student_name.strip(),
                            new_student_class,
                            new_student_password
                        )
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
            
            # تعديل طالب
            elif st.session_state.student_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات طالب")
                
                if not ALL_STUDENTS:
                    st.info("لا يوجد طلاب في النظام.")
                else:
                    # اختيار الطالب للتعديل
                    student_to_edit = st.selectbox("اختر الطالب للتعديل", ALL_STUDENTS, key="student_to_edit")
                    
                    if student_to_edit:
                        # عرض البيانات الحالية
                        current_class = STUDENT_TO_CLASS.get(student_to_edit, "")
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # إدخال الاسم الجديد
                            new_student_name = st.text_input("الاسم الجديد", value=student_to_edit, key="edit_student_name")
                            
                            # اختيار الفصل الجديد
                            class_options = list(CLASSES.keys())
                            new_student_class = st.selectbox("الفصل الجديد", class_options, 
                                                           index=class_options.index(current_class) if current_class in class_options else 0,
                                                           key="edit_student_class")
                        
                        with col2:
                            # إدخال كلمة المرور الجديدة (اختياري)
                            st.info("اترك كلمة المرور فارغة إذا لم ترغب في تغييرها")
                            new_student_password = st.text_input("كلمة المرور الجديدة", type="password",
                                                               key="edit_student_password",
                                                               help="اتركه فارغاً للحفاظ على كلمة المرور الحالية")
                        
                        # زر التعديل
                        if st.button("✏️ تحديث بيانات الطالب", key="update_student_btn", use_container_width=True):
                            if not new_student_name.strip():
                                st.error("❌ من فضلك أدخل اسم الطالب")
                            else:
                                success, message = update_student_info(
                                    student_to_edit,
                                    new_student_name.strip(),
                                    new_student_class,
                                    new_student_password if new_student_password else None
                                )
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # حذف طالب
            elif st.session_state.student_subtab == "remove":
                st.markdown("#### ❌ حذف طالب")
                
                if not ALL_STUDENTS:
                    st.info("لا يوجد طلاب في النظام.")
                else:
                    # اختيار الطالب للحذف
                    student_to_delete = st.selectbox("اختر الطالب للحذف", ALL_STUDENTS, key="student_to_delete")
                    
                    if student_to_delete:
                        # عرض معلومات الطالب
                        student_class = STUDENT_TO_CLASS.get(student_to_delete, "")
                        st.warning(f"**الطالب المحدد:** {student_to_delete}")
                        st.warning(f"**الفصل:** {student_class}")
                        
                        # زر الحذف مع تأكيد
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_student", use_container_width=True):
                                success, message = remove_student_from_class(student_to_delete)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                        with col_b:
                            if st.button("إلغاء", key="cancel_delete_student", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            # قائمة الطلاب
            elif st.session_state.student_subtab == "list":
                st.markdown("#### 📋 قائمة جميع الطلاب")
                
                if ALL_STUDENTS:
                    # إنشاء DataFrame للطلاب
                    students_df = pd.DataFrame({
                        "اسم الطالب": ALL_STUDENTS,
                        "الفصل": [STUDENT_TO_CLASS.get(student, "غير محدد") for student in ALL_STUDENTS],
                        "كلمة المرور": [USERS.get(student, {}).get("password", "غير معروفة") for student in ALL_STUDENTS]
                    })
                    
                    st.dataframe(students_df, use_container_width=True, hide_index=True)
                    
                    # عرض عدد الطلاب
                    st.info(f"**إجمالي عدد الطلاب:** {len(ALL_STUDENTS)}")
                    
                    # زر تصدير البيانات
                    csv = students_df.to_csv(index=False).encode('utf-8-sig')
                    st.download_button(
                        label="📥 تحميل قائمة الطلاب (CSV)",
                        data=csv,
                        file_name=f"قائمة_الطلاب_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("لا يوجد طلاب في النظام.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "teachers":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 👨‍🏫 إدارة المعلمين")
            
            # علامات تبويب فرعية لإدارة المعلمين
            teacher_tabs = ["add", "edit", "remove", "list"]
            teacher_tab_names = {
                "add": "➕ إضافة معلم",
                "edit": "✏️ تعديل معلم",
                "remove": "🗑️ حذف معلم",
                "list": "📋 قائمة المعلمين"
            }
            
            teacher_tab_cols = st.columns(len(teacher_tabs))
            for idx, teacher_tab in enumerate(teacher_tabs):
                with teacher_tab_cols[idx]:
                    if st.button(teacher_tab_names[teacher_tab], key=f"teacher_tab_{teacher_tab}", use_container_width=True):
                        st.session_state.teacher_subtab = teacher_tab
                        st.rerun()
            
            if "teacher_subtab" not in st.session_state:
                st.session_state.teacher_subtab = "add"
            
            st.markdown("---")
            
            # إضافة معلم جديد
            if st.session_state.teacher_subtab == "add":
                st.markdown("#### ➕ إضافة معلم جديد")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # إدخال اسم المعلم
                    new_teacher_name = st.text_input("اسم المعلم الجديد *", key="new_teacher_name")
                    
                    # إدخال كلمة المرور (إجباري)
                    new_teacher_password = st.text_input("كلمة المرور *", type="password", key="new_teacher_password")
                
                with col2:
                    # تأكيد كلمة المرور
                    new_teacher_password_confirm = st.text_input("تأكيد كلمة المرور *", type="password", 
                                                               key="new_teacher_password_confirm")
                    
                    # اختيار الفصول
                    class_options = list(CLASSES.keys())
                    new_teacher_classes = st.multiselect("الفصول التي يدرسها *", class_options, key="new_teacher_classes")
                
                # زر الإضافة
                if st.button("➕ إضافة المعلم", key="add_teacher_btn", use_container_width=True):
                    if not new_teacher_name.strip():
                        st.error("❌ من فضلك أدخل اسم المعلم")
                    elif not new_teacher_password:
                        st.error("❌ من فضلك أدخل كلمة المرور")
                    elif new_teacher_password != new_teacher_password_confirm:
                        st.error("❌ كلمتا المرور غير متطابقتين")
                    elif not new_teacher_classes:
                        st.error("❌ من فضلك اختر الفصول التي يدرسها المعلم")
                    else:
                        success, message = add_teacher(
                            new_teacher_name.strip(),
                            new_teacher_password,
                            new_teacher_classes
                        )
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
            
            # تعديل معلم
            elif st.session_state.teacher_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات معلم")
                
                if not TEACHERS:
                    st.info("لا يوجد معلمين في النظام.")
                else:
                    # اختيار المعلم للتعديل
                    teacher_to_edit = st.selectbox("اختر المعلم للتعديل", list(TEACHERS.keys()), key="teacher_to_edit")
                    
                    if teacher_to_edit:
                        # عرض البيانات الحالية
                        current_data = TEACHERS[teacher_to_edit]
                        current_classes = current_data.get("classes", [])
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # إدخال الاسم الجديد
                            new_teacher_name = st.text_input("الاسم الجديد", value=teacher_to_edit, key="edit_teacher_name")
                            
                            # إدخال كلمة المرور الجديدة (اختياري)
                            st.info("اترك كلمة المرور فارغة إذا لم ترغب في تغييرها")
                            new_teacher_password = st.text_input("كلمة المرور الجديدة", type="password", 
                                                               key="edit_teacher_password")
                        
                        with col2:
                            # اختيار الفصول الجديدة
                            class_options = list(CLASSES.keys())
                            new_teacher_classes = st.multiselect("الفصول الجديدة", class_options, 
                                                               default=current_classes, key="edit_teacher_classes")
                        
                        # زر التعديل
                        if st.button("✏️ تحديث بيانات المعلم", key="update_teacher_btn", use_container_width=True):
                            if not new_teacher_name.strip():
                                st.error("❌ من فضلك أدخل اسم المعلم")
                            elif not new_teacher_classes:
                                st.error("❌ من فضلك اختر الفصول التي يدرسها المعلم")
                            else:
                                success, message = update_teacher_info(
                                    teacher_to_edit,
                                    new_teacher_name.strip(),
                                    new_teacher_password if new_teacher_password else None,
                                    new_teacher_classes
                                )
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # حذف معلم
            elif st.session_state.teacher_subtab == "remove":
                st.markdown("#### ❌ حذف معلم")
                
                if not TEACHERS:
                    st.info("لا يوجد معلمين في النظام.")
                else:
                    # اختيار المعلم للحذف
                    teacher_to_delete = st.selectbox("اختر المعلم للحذف", list(TEACHERS.keys()), key="teacher_to_delete")
                    
                    if teacher_to_delete:
                        # عرض معلومات المعلم
                        teacher_classes = TEACHERS[teacher_to_delete].get("classes", [])
                        st.warning(f"**المعلم المحدد:** {teacher_to_delete}")
                        st.warning(f"**الفصول التي يدرسها:** {', '.join(teacher_classes)}")
                        
                        # زر الحذف مع تأكيد
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_teacher", use_container_width=True):
                                success, message = remove_teacher(teacher_to_delete)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                        with col_b:
                            if st.button("إلغاء", key="cancel_delete_teacher", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            # قائمة المعلمين
            elif st.session_state.teacher_subtab == "list":
                st.markdown("#### 📋 قائمة جميع المعلمين")
                
                if TEACHERS:
                    # إنشاء DataFrame للمعلمين
                    teachers_data = []
                    for teacher_name, teacher_info in TEACHERS.items():
                        teachers_data.append({
                            "اسم المعلم": teacher_name,
                            "الفصول": ", ".join(teacher_info.get("classes", [])),
                            "كلمة المرور": teacher_info.get("password", "غير معروفة")
                        })
                    
                    teachers_df = pd.DataFrame(teachers_data)
                    
                    st.dataframe(teachers_df, use_container_width=True, hide_index=True)
                    
                    # عرض عدد المعلمين
                    st.info(f"**إجمالي عدد المعلمين:** {len(TEACHERS)}")
                else:
                    st.info("لا يوجد معلمين في النظام.")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        elif st.session_state.admin_tab == "classes":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 🏫 إدارة الفصول")
            
            # علامات تبويب فرعية لإدارة الفصول
            class_tabs = ["add", "edit", "remove", "list"]
            class_tab_names = {
                "add": "➕ إضافة فصل",
                "edit": "✏️ تعديل فصل",
                "remove": "🗑️ حذف فصل",
                "list": "📋 قائمة الفصول"
            }
            
            class_tab_cols = st.columns(len(class_tabs))
            for idx, class_tab in enumerate(class_tabs):
                with class_tab_cols[idx]:
                    if st.button(class_tab_names[class_tab], key=f"class_tab_{class_tab}", use_container_width=True):
                        st.session_state.class_subtab = class_tab
                        st.rerun()
            
            if "class_subtab" not in st.session_state:
                st.session_state.class_subtab = "add"
            
            st.markdown("---")
            
            # إضافة فصل جديد
            if st.session_state.class_subtab == "add":
                st.markdown("#### ➕ إضافة فصل جديد")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # إدخال اسم الفصل
                    new_class_name = st.text_input("اسم الفصل الجديد *", key="new_class_name")
                    
                    # اختيار المعلم المسؤول
                    teacher_options = list(TEACHERS.keys())
                    if not teacher_options:
                        st.warning("⚠️ لا يوجد معلمين في النظام. الرجاء إضافة معلم أولاً.")
                        new_class_teacher = None
                    else:
                        new_class_teacher = st.selectbox("المعلم المسؤول *", teacher_options, key="new_class_teacher")
                
                with col2:
                    # إدخال قائمة الطلاب (اختياري)
                    st.markdown("**قائمة الطلاب (اختياري)**")
                    new_class_students_text = st.text_area("أسماء الطلاب (افصل بينها بفاصلة)", 
                                                         key="new_class_students", 
                                                         height=150,
                                                         help="اكتب أسماء الطلاب مفصولة بفاصلة، مثال: أحمد محمد، محمود علي، ...")
                
                # زر الإضافة
                if st.button("➕ إضافة الفصل", key="add_class_btn", use_container_width=True):
                    if not new_class_name.strip():
                        st.error("❌ من فضلك أدخل اسم الفصل")
                    elif not new_class_teacher:
                        st.error("❌ من فضلك اختر المعلم المسؤول")
                    else:
                        # تحويل النص إلى قائمة طلاب
                        students_list = []
                        if new_class_students_text.strip():
                            students_list = [s.strip() for s in new_class_students_text.split(",") if s.strip()]
                        
                        success, message = add_class(new_class_name.strip(), new_class_teacher, students_list)
                        if success:
                            st.success(f"✅ {message}")
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
            
            # تعديل فصل
            elif st.session_state.class_subtab == "edit":
                st.markdown("#### ✏️ تعديل بيانات فصل")
                
                if not CLASSES:
                    st.info("لا يوجد فصول في النظام.")
                else:
                    # اختيار الفصل للتعديل
                    class_to_edit = st.selectbox("اختر الفصل للتعديل", list(CLASSES.keys()), key="class_to_edit")
                    
                    if class_to_edit:
                        # الحصول على المعلم المسؤول
                        class_teacher = None
                        for teacher, classes in TEACHER_CLASSES.items():
                            if class_to_edit in classes:
                                class_teacher = teacher
                                break
                        
                        # عرض البيانات الحالية
                        current_students = CLASSES[class_to_edit]
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # إدخال الاسم الجديد
                            new_class_name = st.text_input("الاسم الجديد", value=class_to_edit, key="edit_class_name")
                            
                            # اختيار المعلم الجديد (اختياري)
                            teacher_options = [""] + list(TEACHERS.keys())
                            new_class_teacher = st.selectbox("المعلم الجديد (اختياري)", teacher_options,
                                                           index=teacher_options.index(class_teacher) if class_teacher in teacher_options else 0,
                                                           key="edit_class_teacher")
                        
                        with col2:
                            # عرض الطلاب الحاليين
                            st.markdown("**الطلاب الحاليين:**")
                            for student in current_students:
                                st.markdown(f"- {student}")
                        
                        # زر التعديل
                        if st.button("✏️ تحديث بيانات الفصل", key="update_class_btn", use_container_width=True):
                            if not new_class_name.strip():
                                st.error("❌ من فضلك أدخل اسم الفصل")
                            else:
                                success, message = update_class_info(
                                    class_to_edit,
                                    new_class_name.strip(),
                                    new_class_teacher if new_class_teacher else None
                                )
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
            
            # حذف فصل
            elif st.session_state.class_subtab == "remove":
                st.markdown("#### ❌ حذف فصل")
                
                if not CLASSES:
                    st.info("لا يوجد فصول في النظام.")
                else:
                    # اختيار الفصل للحذف
                    class_to_delete = st.selectbox("اختر الفصل للحذف", list(CLASSES.keys()), key="class_to_delete")
                    
                    if class_to_delete:
                        # عرض معلومات الفصل
                        class_students = CLASSES.get(class_to_delete, [])
                        st.warning(f"**الفصل المحدد:** {class_to_delete}")
                        st.warning(f"**عدد الطلاب:** {len(class_students)}")
                        
                        if class_students:
                            st.warning(f"**الطلاب:** {', '.join(class_students[:5])}{'...' if len(class_students) > 5 else ''}")
                        
                        # زر الحذف مع تأكيد
                        col_a, col_b = st.columns(2)
                        with col_a:
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_class", use_container_width=True):
                                success, message = remove_class(class_to_delete)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                                else:
                                    st.error(f"❌ {message}")
                        with col_b:
                            if st.button("إلغاء", key="cancel_delete_class", use_container_width=True):
                                st.info("تم إلغاء الحذف")
            
            # قائمة الفصول
            elif st.session_state.class_subtab == "list":
                st.markdown("#### 📋 قائمة الفصول")
                
                if CLASSES:
                    # إنشاء DataFrame للفصول
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
                            "قائمة الطلاب": ", ".join(students[:3]) + ("..." if len(students) > 3 else "")
                        })
                    
                    class_df = pd.DataFrame(class_data)
                    st.dataframe(class_df, use_container_width=True, hide_index=True)
                    
                    # عرض عدد الفصول
                    st.info(f"**إجمالي عدد الفصول:** {len(CLASSES)}")
                else:
                    st.info("لا يوجد فصول في النظام.")
            
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
                
                if BOT_TOKEN:
                    st.success("✅ Telegram Bot Token: متوفر")
                else:
                    st.warning("⚠️ Telegram Bot Token: غير متوفر")
                
                if CHAT_ID:
                    st.success("✅ Telegram Chat ID: متوفر")
                else:
                    st.warning("⚠️ Telegram Chat ID: غير متوفر")
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)
        
        # أزرار التحكم
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🏠 العودة للصفحة الرئيسية", key="admin_back_to_home", use_container_width=True):
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
