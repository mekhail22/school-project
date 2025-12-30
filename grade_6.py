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
import csv
import tempfile

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
# جعل المتغيرات قابلة للتعديل
CLASSES = {}
TEACHER_CLASSES = {}
USERS = {}
student_passwords = {}
ALL_STUDENTS = []
STUDENT_TO_CLASS = {}

# تهيئة البيانات
def initialize_data():
    global CLASSES, TEACHER_CLASSES, USERS, student_passwords, ALL_STUDENTS, STUDENT_TO_CLASS
    
    # البيانات الأولية
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
    
    TEACHER_CLASSES = {
        "مينا سمير": ["Class B", "Class C"],
        "فادي حبيب": ["Class D", "Class E"]
    }
    
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
    
    update_users()

# تحديث المستخدمين
def update_users():
    global USERS, ALL_STUDENTS, STUDENT_TO_CLASS
    
    # تحديث قاموس الطالب إلى الفصل
    STUDENT_TO_CLASS = {}
    for class_name, students in CLASSES.items():
        for student in students:
            STUDENT_TO_CLASS[student] = class_name
    
    # تحديث قائمة جميع الطلاب
    ALL_STUDENTS = []
    for class_name, students in CLASSES.items():
        ALL_STUDENTS.extend(students)
    
    # تحديث المستخدمين
    USERS = {
        # مدير النظام
        "admin": {
            "password": "admin1234",
            "role": "admin",
            "admin_name": "مدير النظام"
        },
        # معلمون
        "مينا سمير": {
            "password": "mina1234",
            "role": "teacher",
            "teacher_name": "مينا سمير",
            "classes": TEACHER_CLASSES.get("مينا سمير", [])
        },
        "فادي حبيب": {
            "password": "fady5678",
            "role": "teacher",
            "teacher_name": "فادي حبيب",
            "classes": TEACHER_CLASSES.get("فادي حبيب", [])
        },
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

# تهيئة البيانات لأول مرة
initialize_data()

# ------------------ تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل الإعدادات من Streamlit Secrets"""
    try:
        secrets = st.secrets
        
        # Telegram
        BOT_TOKEN = getattr(secrets.telegram, 'bot_token', None) if hasattr(secrets, 'telegram') else None
        CHAT_ID = getattr(secrets.telegram, 'chat_id', None) if hasattr(secrets, 'telegram') else None
        
        # App settings
        SHEET_NAME = getattr(secrets.sheets, 'name', 'school_attendance') if hasattr(secrets, 'sheets') else 'school_attendance'
        
        # Service Account
        SERVICE_ACCOUNT = None
        
        if hasattr(secrets, 'SERVICE_ACCOUNT'):
            try:
                SERVICE_ACCOUNT = {
                    'type': secrets.SERVICE_ACCOUNT.type,
                    'project_id': secrets.SERVICE_ACCOUNT.project_id,
                    'private_key_id': secrets.SERVICE_ACCOUNT.private_key_id,
                    'private_key': secrets.SERVICE_ACCOUNT.private_key.replace('\\n', '\n'),
                    'client_email': secrets.SERVICE_ACCOUNT.client_email,
                    'client_id': secrets.SERVICE_ACCOUNT.client_id,
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
                    'client_x509_cert_url': secrets.SERVICE_ACCOUNT.client_x509_cert_url if hasattr(secrets.SERVICE_ACCOUNT, 'client_x509_cert_url') else ''
                }
                logger.info("✅ تم تحميل SERVICE_ACCOUNT بنجاح")
            except Exception as e:
                logger.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT: {e}")
                SERVICE_ACCOUNT = None
        
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

def init_google_sheets():
    """تهيئة الاتصال بـ Google Sheets"""
    global worksheet, connection_status
    
    if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
        try:
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
            gc = gspread.authorize(creds)
            
            try:
                sh = gc.open(SHEET_NAME)
                worksheet = sh.sheet1
                connection_status = f"✅ متصل بـ {SHEET_NAME}"
                
                try:
                    current_data = worksheet.get_all_values()
                    if not current_data or len(current_data) == 0:
                        headers = ["student", "teacher", "class", "status", "date"]
                        worksheet.append_row(headers)
                        logger.info("✅ تم إضافة العناوين إلى الورقة")
                    else:
                        logger.info(f"✅ تم تحميل {len(current_data)-1 if len(current_data) > 1 else 0} سجل")
                except Exception as e:
                    logger.error(f"❌ خطأ في التحقق من البيانات: {e}")
                    
            except gspread.exceptions.SpreadsheetNotFound:
                connection_status = f"❌ لم يتم العثور على: {SHEET_NAME}"
                worksheet = None
                logger.error(f"❌ لم يتم العثور على الورقة: {SHEET_NAME}")
                
            except Exception as e:
                connection_status = f"❌ خطأ في فتح الـ Sheet: {str(e)}"
                worksheet = None
                logger.error(f"❌ خطأ في فتح الورقة: {e}")
                
        except Exception as e:
            connection_status = f"❌ فشل في المصادقة: {str(e)}"
            worksheet = None
            logger.error(f"❌ فشل في المصادقة: {e}")
    else:
        connection_status = "❌ إعدادات الاتصال غير كاملة"
        worksheet = None
        logger.warning("❌ إعدادات SERVICE_ACCOUNT غير كاملة")

init_google_sheets()

# ------------------ وظائف المساعدة ------------------
def normalize_date_for_display(src_date_str):
    """معالجة التاريخ للعرض في الجداول"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    
    s = str(src_date_str).strip()
    
    if " / " in s:
        return s
    
    try:
        if date_parse:
            dt = date_parse(s, dayfirst=False, yearfirst=False)
            return f"{dt.day:02d} / {dt.month:02d} / {dt.year}"
    except:
        pass
    
    try:
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
        
        elif "-" in s:
            parts = s.split("-")
            if len(parts) == 3:
                d, m, y = parts
                return f"{int(d.strip()):02d} / {int(m.strip()):02d} / {int(y.strip())}"
        
        elif len(s) == 8 and s.isdigit():
            y = s[0:4]
            m = s[4:6]
            d = s[6:8]
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
            
    except Exception as e:
        logger.error(f"خطأ في معالجة التاريخ {s}: {e}")
    
    return s

def read_sheet():
    """قراءة البيانات من Google Sheets"""
    if worksheet is None:
        logger.warning("❌ لا يوجد اتصال بـ Google Sheets")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    try:
        data = worksheet.get_all_records()
        
        if not data:
            logger.info("📭 الورقة فارغة أو لا توجد بيانات")
            return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
        
        logger.info(f"✅ تم قراءة {len(data)} سجل من Google Sheets")
        
        df = pd.DataFrame(data)
        
        required_columns = ["student", "teacher", "class", "status", "date"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = ""
        
        df = df[required_columns]
        df = df.dropna(how='all')
        df = df.fillna("")
        
        for col in ["student", "teacher", "class", "status"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        if "date" in df.columns:
            df["date"] = df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
        
        return df
        
    except Exception as e:
        logger.error(f"❌ خطأ في قراءة البيانات من Google Sheets: {str(e)}")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])

def append_to_sheet(new_rows):
    """إضافة صفوف جديدة إلى Google Sheets"""
    if worksheet is None:
        logger.error("❌ لا يوجد اتصال بـ Google Sheets")
        return False
    
    try:
        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")
        logger.info(f"✅ تم إضافة {len(new_rows)} سجل جديد إلى Google Sheets")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة البيانات إلى Google Sheets: {str(e)}")
        return False

def clear_all_records():
    """حذف جميع سجلات الغياب"""
    if worksheet is None:
        return False
    
    try:
        # الحصول على جميع البيانات
        all_data = worksheet.get_all_values()
        
        if len(all_data) <= 1:  # فقط العناوين أو فارغ
            return True
        
        # حذف جميع الصفوف ما عدا العناوين
        worksheet.delete_rows(2, len(all_data))
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف السجلات: {e}")
        return False

def delete_specific_records(student_name=None, class_name=None, date_str=None):
    """حذف سجلات محددة"""
    if worksheet is None:
        return False, "لا يوجد اتصال"
    
    try:
        all_data = worksheet.get_all_values()
        
        if len(all_data) <= 1:
            return True, "لا توجد سجلات"
        
        headers = all_data[0]
        
        # البحث عن الصفوف التي تطابق المعايير
        rows_to_delete = []
        for i in range(1, len(all_data)):
            row = all_data[i]
            match = True
            
            if student_name and row[headers.index("student")] != student_name:
                match = False
            
            if class_name and row[headers.index("class")] != class_name:
                match = False
            
            if date_str and row[headers.index("date")] != date_str:
                match = False
            
            if match:
                rows_to_delete.append(i + 1)  # +1 لأن الفهرس في gspread يبدأ من 1
        
        # حذف الصفوف من الأسفل للأعلى
        for row_num in sorted(rows_to_delete, reverse=True):
            worksheet.delete_rows(row_num)
        
        return True, f"تم حذف {len(rows_to_delete)} سجل"
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف السجلات: {e}")
        return False, str(e)

def get_student_class(student_name):
    """الحصول على فصل الطالب"""
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
    
    class_df = df[df["class"].astype(str).str.strip() == class_name.strip()].copy()
    
    if class_df.empty:
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    total_records = len(class_df)
    present_count = len(class_df[class_df["status"].astype(str).str.contains("حاضر", na=False)])
    absent_count = len(class_df[class_df["status"].astype(str).str.contains("غياب", na=False)])
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    student_stats = []
    class_students = CLASSES.get(class_name, [])
    
    for student in class_students:
        student_df = class_df[class_df["student"].astype(str).str.strip() == student.strip()]
        student_total = len(student_df)
        student_present = len(student_df[student_df["status"].astype(str).str.contains("حاضر", na=False)])
        student_absent = len(student_df[student_df["status"].astype(str).str.contains("غياب", na=False)])
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
    
    class_df = df[df["class"].astype(str).str.strip() == class_name.strip()].copy()
    
    if class_df.empty:
        return pd.DataFrame()
    
    class_df["date_clean"] = class_df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        elif "حاضر" in status_str:
            return "حاضر"
        return status_str
    
    class_df["status_clean"] = class_df["status"].apply(clean_status)
    
    try:
        class_df["temp_date"] = pd.to_datetime(class_df["date"], errors='coerce', dayfirst=True)
        class_df = class_df.sort_values("temp_date", ascending=False)
        class_df = class_df.drop(columns=["temp_date"])
    except:
        class_df = class_df.sort_values("date_clean", ascending=False)
    
    return class_df[["student", "teacher", "date_clean", "status_clean"]]

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
    """تسجيل الحضور والغياب"""
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    
    class_students = CLASSES.get(class_name, [])
    
    for student in class_students:
        if student in selected_absent:
            status = absent_label
        else:
            status = "حاضر"
        
        student_class = get_student_class(student)
        rows.append([student, teacher_name, student_class, status, date_display])
    
    success_count = 0
    
    if rows:
        if append_to_sheet(rows):
            success_count = len(rows)
        else:
            logger.warning("⚠️ تم حفظ البيانات محلياً فقط")
            success_count = len(rows)
    
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if rows:
        absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
        present_count = len(class_students) - len(selected_absent)
        
        message = f"📋 تسجيل الغياب\n📅 التاريخ: {date_display}\n👨‍🏫 المعلم: {teacher_name}\n🏫 الفصل: {class_name}\n❌ عدد الغائبين: {len(selected_absent)}\n✅ عدد الحاضرين: {present_count}\n👥 الطلاب الغائبون: {absent_students}"
        
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
    
    return telegram_status, telegram_details, success_count

def get_student_records(student_name):
    """الحصول على سجلات طالب معين"""
    df = read_sheet()
    
    if df.empty or "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])
    
    try:
        df_matches = df[df["student"].astype(str).str.strip() == student_name.strip()].copy()
        
        if df_matches.empty:
            return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])
        
        df_matches["date_clean"] = df_matches["date"].apply(
            lambda x: normalize_date_for_display(x) if pd.notna(x) else ""
        )
        
        def clean_status(status):
            if pd.isna(status):
                return ""
            status_str = str(status).strip()
            if "غياب" in status_str:
                return "غياب"
            elif "حاضر" in status_str:
                return "حاضر"
            return status_str
        
        df_matches["status_clean"] = df_matches["status"].apply(clean_status)
        
        try:
            df_matches["temp_date"] = pd.to_datetime(df_matches["date"], errors='coerce', dayfirst=True)
            df_matches = df_matches.sort_values("temp_date", ascending=False)
            df_matches = df_matches.drop(columns=["temp_date"])
        except:
            df_matches = df_matches.sort_values("date_clean", ascending=False)
        
        df_matches = df_matches.reset_index(drop=True)
        df_matches["المرة"] = range(1, len(df_matches) + 1)
        
        df_matches = df_matches.rename(columns={
            "student": "الطالب",
            "teacher": "المعلم",
            "class": "الفصل",
            "date_clean": "التاريخ",
            "status_clean": "الحالة"
        })
        
        return df_matches[["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"]]
        
    except Exception as e:
        logger.error(f"خطأ في الحصول على سجلات الطالب: {e}")
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])

# ------------------ إدارة الحالة ------------------
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
if "teacher_name" not in st.session_state:
    st.session_state.teacher_name = ""
if "teacher_classes" not in st.session_state:
    st.session_state.teacher_classes = []
if "student_name" not in st.session_state:
    st.session_state.student_name = ""
if "admin_tab" not in st.session_state:
    st.session_state.admin_tab = "نظرة عامة"
if "editing_mode" not in st.session_state:
    st.session_state.editing_mode = None

# ------------------ CSS ------------------
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
    .admin-panel {
        background: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    .action-btn {
        margin: 5px;
        padding: 10px 20px;
        border-radius: 8px;
        border: none;
        cursor: pointer;
        font-weight: bold;
        transition: all 0.3s;
    }
    .btn-success {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    .btn-danger {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
    }
    .btn-warning {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
    }
    .btn-info {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

def show_toolbar():
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">مدرسة السلام الإعدادية الثانويه المشتركه</p>
                <p class="school-date">{datetime.now().strftime('%A، %d %B %Y')}</p>
            </div>
        </div>
        <div></div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# ------------------ صفحة تسجيل الدخول ------------------
if st.session_state.page == "login":
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <div class="login-title">🚪 تسجيل الدخول</div>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        username = st.text_input("اسم المستخدم", 
                                placeholder="أدخل اسمك",
                                label_visibility="collapsed",
                                key="login_username_input")
        
        password = st.text_input("كلمة المرور", 
                                type="password", 
                                placeholder="أدخل كلمة المرور الخاصة بك",
                                label_visibility="collapsed",
                                key="login_password_input")
        
        login_button = st.button("✅ تسجيل الدخول", 
                                use_container_width=True,
                                key="login_main_button")
        
        if login_button:
            if username and password:
                if username in USERS:
                    if USERS[username]["password"] == password:
                        st.session_state.logged_in = True
                        st.session_state.user_name = username
                        st.session_state.user_role = USERS[username]["role"]
                        
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

# ------------------ الصفحة الرئيسية ------------------
elif st.session_state.logged_in:
    show_toolbar()
    
    if st.session_state.page == "home":
        st.markdown("# 🏠 الصفحة الرئيسية")
        
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
        
        if st.session_state.user_role == "admin":
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👑 لوحة التحكم", 
                            key="admin_dashboard_btn", 
                            use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            with col2:
                if st.button("📊 مراجعة البيانات", 
                            key="admin_review_btn", 
                            use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            with col3:
                if st.button("⚙️ إدارة النظام", 
                            key="admin_manage_btn", 
                            use_container_width=True):
                    st.session_state.page = "admin_management"
                    st.rerun()
                    
        elif st.session_state.user_role == "teacher":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 تسجيل الغياب", 
                            key="teacher_record_btn", 
                            use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "record"
                    st.session_state.selected_class = None
                    st.rerun()
            
            with col2:
                if st.button("📊 عرض الإحصائيات", 
                            key="teacher_stats_btn", 
                            use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "statistics"
                    st.session_state.selected_class = None
                    st.rerun()
        
        elif st.session_state.user_role == "student":
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", 
                        key="student_report_btn", 
                        use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", 
                    key="logout_main_btn", 
                    use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.session_state.teacher_classes = None
            st.session_state.page = "login"
            st.rerun()
    
    # صفحة المعلم
    elif st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        teacher_classes = st.session_state.get('teacher_classes', [])
        
        if not st.session_state.selected_class:
            st.markdown("# 🎯 اختر الفصل")
            
            st.markdown(f"### 👨‍🏫 المعلم: **{teacher_name}**")
            st.markdown(f"### 📚 اختر الفصل:")
            
            if teacher_classes:
                col1, col2 = st.columns(2)
                cols = [col1, col2]
                
                for idx, class_name in enumerate(teacher_classes):
                    with cols[idx % 2]:
                        if st.button(f"🎯 {class_name}", 
                                    key=f"teacher_class_{class_name}", 
                                    use_container_width=True):
                            st.session_state.selected_class = class_name
                            st.rerun()
            else:
                st.warning("⚠️ لا يوجد فصول موكلة إليك. الرجاء التواصل مع الإدارة.")
        
        else:
            selected_class = st.session_state.selected_class
            
            if st.session_state.teacher_mode == "record":
                st.markdown(f"# 📝 تسجيل غياب {selected_class}")
                
                if st.button("🔄 اختيار فصل آخر", 
                            key="change_class_btn", 
                            use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                st.markdown("---")
                
                class_students = CLASSES.get(selected_class, [])
                
                if class_students:
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("اسم المعلم", teacher_name)
                    with col2:
                        st.metric("اسم الفصل", selected_class)
                    with col3:
                        st.metric("عدد الطلاب", len(class_students))
                    
                    st.markdown("---")
                    
                    st.markdown("### 👇 اختر الطلاب الغائبين")
                    selected = st.multiselect(
                        f"اختر الطلاب الغائبين من {selected_class}",
                        class_students,
                        label_visibility="collapsed",
                        key=f"multiselect_{selected_class}"
                    )

                    st.markdown("### 📝 اختر نوع الغياب")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        excuse = st.checkbox("غياب بعذر", key=f"excuse_cb_{selected_class}")
                    with col_b:
                        no_excuse = st.checkbox("غياب بدون عذر", key=f"no_excuse_cb_{selected_class}")

                    if excuse and no_excuse:
                        st.warning("⚠️ اختر نوع واحد فقط.")

                    st.markdown("---")
                    
                    if st.button("💾 حفظ وتسجيل الغياب", 
                                key=f"save_attendance_{selected_class}", 
                                use_container_width=True):
                        if excuse and no_excuse:
                            st.warning("⚠️ اختر نوع واحد فقط.")
                        elif not (excuse or no_excuse):
                            st.warning("⚠️ من فضلك اختر نوع الغياب.")
                        else:
                            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                            
                            try:
                                telegram_status, telegram_details, success_count = record_attendance(
                                    selected, teacher_name, selected_class, status_label
                                )
                            except Exception as e:
                                st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                            else:
                                if success_count > 0:
                                    st.success(f"✅ تم تسجيل الغياب بنجاح")
                else:
                    st.error(f"❌ لا يوجد طلاب مسجلين في {selected_class}")
            
            elif st.session_state.teacher_mode == "statistics":
                st.markdown(f"# 📊 إحصائيات {selected_class}")
                
                if st.button("🔄 اختيار فصل آخر", 
                            key="change_class_stats_btn", 
                            use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                st.markdown("---")
                
                stats = get_class_statistics(selected_class)
                history_df = get_class_attendance_history(selected_class)
                
                with st.sidebar:
                    st.markdown("### 🔗 حالة الاتصال")
                    if connection_status.startswith("✅"):
                        st.success(connection_status)
                        df_all = read_sheet()
                        if not df_all.empty:
                            st.info(f"**عدد السجلات الكلية:** {len(df_all)}")
                        else:
                            st.info("**عدد السجلات الكلية:** 0")
                    else:
                        st.error(connection_status)
                    
                    st.markdown("---")
                    st.markdown("### 📊 معلومات النظام")
                    st.info(f"**عدد الطلاب:** {len(ALL_STUDENTS)}")
                    st.info(f"**عدد الفصول:** {len(CLASSES)}")
                    st.info(f"**عدد المعلمين:** {len(TEACHER_CLASSES)}")
                
                st.markdown("### 📈 الإحصائيات العامة")
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
                
                st.markdown("### 📊 تفاصيل الحضور والغياب")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown("##### ✅ الحضور")
                    st.metric("عدد مرات الحضور", stats["present_count"])
                with col_b:
                    st.markdown("##### ❌ الغياب")
                    st.metric("عدد مرات الغياب", stats["absent_count"])
                
                st.markdown("---")
                
                st.markdown("### 👥 إحصائيات الطلاب")
                
                if stats["students"]:
                    student_stats_df = pd.DataFrame(stats["students"])
                    student_stats_df = student_stats_df.rename(columns={
                        "name": "اسم الطالب",
                        "total": "عدد السجلات",
                        "present": "حضور",
                        "absent": "غياب",
                        "rate": "نسبة الحضور %"
                    })
                    
                    student_stats_df["نسبة الحضور %"] = student_stats_df["نسبة الحضور %"].apply(lambda x: f"{x:.1f}%")
                    
                    st.dataframe(student_stats_df, use_container_width=True, hide_index=True)
                else:
                    st.info("📭 لا توجد سجلات لهذا الفصل بعد.")
                
                st.markdown("---")
                st.markdown("### 📥 تصدير بيانات الفصل")
                
                if not history_df.empty:
                    csv_data = history_df.to_csv(index=False, encoding='utf-8-sig')
                    timestamp = int(time.time() * 1000)
                    st.download_button(
                        label="📄 تحميل بيانات الفصل (CSV)",
                        data=csv_data,
                        file_name=f"بيانات_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        help="سيحتوي الملف على: الطالب، المعلم، التاريخ، الحالة",
                        key=f"download_class_data_{selected_class}_{timestamp}"
                    )
                else:
                    st.info("📭 لا توجد بيانات لتصديرها.")
        
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", 
                    key="back_to_home_teacher", 
                    use_container_width=True, 
                    type="secondary"):
            st.session_state.page = "home"
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.rerun()
    
    # صفحة الطالب
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown("# 📊 تقرير الغياب الخاص بي")
        
        if st.button("🏠 العودة للصفحة الرئيسية", 
                    key="back_to_home_student", 
                    use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        student_name = st.session_state.get('student_name', st.session_state.user_name)
        
        df_student = get_student_records(student_name)
        
        if df_student.empty:
            st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
        else:
            absent_count = int((df_student["الحالة"] == "غياب").sum())
            present_count = int((df_student["الحالة"] == "حاضر").sum())
            total_count = len(df_student)
            
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
            
            st.markdown("### 📋 تفاصيل السجلات:")
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            
            csv_data = df_student.to_csv(index=False, encoding='utf-8-sig')
            timestamp = int(time.time() * 1000)
            st.download_button(
                "📥 تحميل تقرير (CSV)",
                data=csv_data,
                file_name=f"تقرير_غياب_{student_name}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True,
                key=f"download_student_report_{student_name}_{timestamp}"
            )
        
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", 
                    key="back_to_home_student_bottom", 
                    use_container_width=True, 
                    type="secondary"):
            st.session_state.page = "home"
            st.rerun()
    
    # ------------------ صفحة إدارة النظام للمدير ------------------
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_management":
        st.markdown("# 👑 إدارة النظام الشاملة")
        
        if st.button("🏠 العودة للصفحة الرئيسية", 
                    key="back_to_home_admin_manage", 
                    use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات الإدارة
        tabs = st.tabs(["👥 إدارة الطلاب", "🏫 إدارة الفصول", "👨‍🏫 إدارة المعلمين", 
                       "📋 إدارة سجلات الغياب", "📥 استيراد/تصدير"])
        
        # تبويب إدارة الطلاب
        with tabs[0]:
            st.markdown("## 👥 إدارة الطلاب")
            
            # قسم إضافة طالب جديد
            st.markdown("### ➕ إضافة طالب جديد")
            with st.container():
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    new_student_name = st.text_input("اسم الطالب", key="new_student_name")
                with col2:
                    new_student_class = st.selectbox("الفصل", list(CLASSES.keys()), key="new_student_class")
                with col3:
                    new_student_password = st.text_input("كلمة المرور", type="password", key="new_student_password")
                with col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_student_btn = st.button("➕ إضافة الطالب", key="add_student_btn")
                
                if add_student_btn:
                    if new_student_name and new_student_class and new_student_password:
                        if new_student_name not in ALL_STUDENTS:
                            CLASSES[new_student_class].append(new_student_name)
                            student_passwords[new_student_name] = new_student_password
                            update_users()
                            st.success(f"✅ تم إضافة الطالب {new_student_name} إلى الفصل {new_student_class}")
                            st.rerun()
                        else:
                            st.error("❌ الطالب موجود بالفعل!")
                    else:
                        st.warning("⚠️ يجب ملء جميع الحقول")
            
            st.markdown("### 📋 قائمة الطلاب حسب الفصول")
            
            # زر تحديث البيانات
            if st.button("🔄 تحديث البيانات", key="refresh_students"):
                update_users()
                st.success("✅ تم تحديث بيانات الطلاب")
                st.rerun()
            
            for class_name, students in CLASSES.items():
                with st.expander(f"📚 {class_name} ({len(students)} طالب)"):
                    if students:
                        # إنشاء DataFrame للطلاب
                        student_data = []
                        for idx, student in enumerate(students, 1):
                            password = student_passwords.get(student, "غير معرف")
                            student_data.append({
                                "م": idx,
                                "اسم الطالب": student,
                                "كلمة المرور": password
                            })
                        
                        student_df = pd.DataFrame(student_data)
                        st.dataframe(student_df, use_container_width=True, hide_index=True)
                        
                        # قسم حذف طالب
                        st.markdown("#### 🗑️ حذف طالب")
                        if students:
                            delete_student = st.selectbox(
                                f"اختر طالب للحذف من {class_name}",
                                students,
                                key=f"delete_student_{class_name}"
                            )
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                if st.button(f"🗑️ حذف {delete_student}", key=f"delete_btn_{delete_student}"):
                                    if delete_student in CLASSES[class_name]:
                                        CLASSES[class_name].remove(delete_student)
                                        if delete_student in student_passwords:
                                            del student_passwords[delete_student]
                                        update_users()
                                        st.success(f"✅ تم حذف الطالب {delete_student}")
                                        st.rerun()
                            with col2:
                                # زر تغيير كلمة المرور
                                new_pass = st.text_input("كلمة مرور جديدة", type="password", 
                                                       key=f"new_pass_{delete_student}")
                                if st.button("🔑 تغيير كلمة المرور", key=f"change_pass_{delete_student}"):
                                    if new_pass:
                                        student_passwords[delete_student] = new_pass
                                        update_users()
                                        st.success(f"✅ تم تغيير كلمة مرور {delete_student}")
                                        st.rerun()
                    else:
                        st.info("📭 لا يوجد طلاب في هذا الفصل")
        
        # تبويب إدارة الفصول
        with tabs[1]:
            st.markdown("## 🏫 إدارة الفصول")
            
            # قسم إضافة فصل جديد
            st.markdown("### ➕ إضافة فصل جديد")
            with st.container():
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_class_name = st.text_input("اسم الفصل الجديد", key="new_class_name_input")
                with col2:
                    new_class_teacher = st.selectbox(
                        "المعلم المسؤول",
                        ["غير معين"] + list(TEACHER_CLASSES.keys()),
                        key="new_class_teacher_select"
                    )
                with col3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_class_btn = st.button("➕ إضافة فصل", key="add_class_btn")
                
                if add_class_btn:
                    if new_class_name and new_class_name not in CLASSES:
                        CLASSES[new_class_name] = []
                        if new_class_teacher != "غير معين":
                            if new_class_teacher not in TEACHER_CLASSES:
                                TEACHER_CLASSES[new_class_teacher] = []
                            TEACHER_CLASSES[new_class_teacher].append(new_class_name)
                        
                        update_users()
                        st.success(f"✅ تم إضافة الفصل {new_class_name}")
                        st.rerun()
                    elif new_class_name in CLASSES:
                        st.error("❌ الفصل موجود بالفعل!")
                    else:
                        st.warning("⚠️ أدخل اسم الفصل")
            
            st.markdown("### 📋 قائمة الفصول")
            
            for class_name, students in CLASSES.items():
                with st.expander(f"🎯 {class_name} ({len(students)} طالب)"):
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.markdown(f"**عدد الطلاب:** {len(students)}")
                        
                        # عرض المعلم المسؤول
                        teacher_name = None
                        for teacher, classes in TEACHER_CLASSES.items():
                            if class_name in classes:
                                teacher_name = teacher
                                break
                        
                        if teacher_name:
                            st.markdown(f"**المعلم المسؤول:** {teacher_name}")
                        else:
                            st.markdown("**المعلم المسؤول:** غير معين")
                    
                    with col2:
                        # تغيير المعلم المسؤول
                        current_teacher = teacher_name if teacher_name else "غير معين"
                        teacher_options = ["غير معين"] + [t for t in TEACHER_CLASSES.keys() if t != current_teacher]
                        
                        new_teacher = st.selectbox(
                            "تغيير المعلم المسؤول",
                            teacher_options,
                            key=f"change_teacher_select_{class_name}",
                            index=teacher_options.index(current_teacher) if current_teacher in teacher_options else 0
                        )
                        
                        if st.button("💾 حفظ", key=f"save_teacher_btn_{class_name}"):
                            # إزالة الفصل من جميع المعلمين
                            for teacher in TEACHER_CLASSES:
                                if class_name in TEACHER_CLASSES[teacher]:
                                    TEACHER_CLASSES[teacher].remove(class_name)
                            
                            # إضافة الفصل للمعلم الجديد
                            if new_teacher != "غير معين":
                                if new_teacher not in TEACHER_CLASSES:
                                    TEACHER_CLASSES[new_teacher] = []
                                TEACHER_CLASSES[new_teacher].append(class_name)
                            
                            update_users()
                            st.success(f"✅ تم تحديث المعلم المسؤول للفصل {class_name}")
                            st.rerun()
                    
                    with col3:
                        # حذف الفصل
                        if len(students) == 0:
                            if st.button(f"🗑️ حذف الفصل", key=f"delete_class_btn_{class_name}"):
                                # حذف الفصل من جميع المعلمين
                                for teacher in TEACHER_CLASSES:
                                    if class_name in TEACHER_CLASSES[teacher]:
                                        TEACHER_CLASSES[teacher].remove(class_name)
                                
                                # حذف الفصل
                                del CLASSES[class_name]
                                
                                update_users()
                                st.success(f"✅ تم حذف الفصل {class_name}")
                                st.rerun()
                        else:
                            st.warning("❌ لا يمكن حذف فصل به طلاب")
                    
                    # عرض قائمة الطلاب في الفصل
                    if students:
                        st.markdown("#### 👥 طلاب الفصل:")
                        for student in students:
                            st.write(f"- {student}")
        
        # تبويب إدارة المعلمين
        with tabs[2]:
            st.markdown("## 👨‍🏫 إدارة المعلمين")
            
            # قسم إضافة معلم جديد
            st.markdown("### ➕ إضافة معلم جديد")
            with st.container():
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    new_teacher_name = st.text_input("اسم المعلم", key="new_teacher_name_input")
                with col2:
                    new_teacher_password = st.text_input("كلمة المرور", type="password", 
                                                        key="new_teacher_password_input")
                with col3:
                    available_classes = list(CLASSES.keys())
                    new_teacher_classes = st.multiselect(
                        "الفصول المسؤول عنها",
                        available_classes,
                        key="new_teacher_classes_select"
                    )
                with col4:
                    st.markdown("<br>", unsafe_allow_html=True)
                    add_teacher_btn = st.button("➕ إضافة معلم", key="add_teacher_btn")
                
                if add_teacher_btn:
                    if new_teacher_name and new_teacher_password:
                        if new_teacher_name not in TEACHER_CLASSES:
                            TEACHER_CLASSES[new_teacher_name] = new_teacher_classes
                            
                            USERS[new_teacher_name] = {
                                "password": new_teacher_password,
                                "role": "teacher",
                                "teacher_name": new_teacher_name,
                                "classes": new_teacher_classes
                            }
                            
                            update_users()
                            st.success(f"✅ تم إضافة المعلم {new_teacher_name}")
                            st.rerun()
                        else:
                            st.error("❌ المعلم موجود بالفعل!")
                    else:
                        st.warning("⚠️ يجب ملء جميع الحقول")
            
            st.markdown("### 📋 قائمة المعلمين")
            
            for teacher_name, classes in TEACHER_CLASSES.items():
                with st.expander(f"👨‍🏫 {teacher_name} ({len(classes)} فصل)"):
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown(f"**الفصول المسؤول عنها:**")
                        if classes:
                            for class_name in classes:
                                st.write(f"- {class_name}")
                        else:
                            st.write("لا يوجد فصول")
                        
                        st.markdown(f"**عدد الفصول:** {len(classes)}")
                    
                    with col2:
                        # تغيير كلمة المرور
                        new_password = st.text_input(
                            "كلمة المرور الجديدة",
                            type="password",
                            key=f"new_teacher_pass_{teacher_name}",
                            placeholder="اترك فارغاً للحفاظ على الكلمة الحالية"
                        )
                        
                        if st.button("🔑 تغيير كلمة المرور", key=f"change_teacher_pass_{teacher_name}"):
                            if new_password:
                                USERS[teacher_name]["password"] = new_password
                                st.success(f"✅ تم تغيير كلمة مرور {teacher_name}")
                                st.rerun()
                        
                        # حذف المعلم
                        if st.button(f"🗑️ حذف المعلم", key=f"delete_teacher_btn_{teacher_name}"):
                            if classes:
                                st.warning(f"⚠️ المعلم {teacher_name} مسؤول عن فصول. اختر معلم لنقل الفصول إليه:")
                                other_teachers = [t for t in TEACHER_CLASSES.keys() if t != teacher_name]
                                
                                if other_teachers:
                                    transfer_to = st.selectbox("نقل الفصول إلى", other_teachers, 
                                                             key=f"transfer_{teacher_name}")
                                    if st.button("✅ نقل وحذف", key=f"confirm_transfer_{teacher_name}"):
                                        for class_name in classes:
                                            TEACHER_CLASSES[transfer_to].append(class_name)
                                        del TEACHER_CLASSES[teacher_name]
                                        del USERS[teacher_name]
                                        update_users()
                                        st.success(f"✅ تم نقل الفصول إلى {transfer_to} وحذف {teacher_name}")
                                        st.rerun()
                                else:
                                    st.error("❌ لا يوجد معلمين آخرين لنقل الفصول إليهم!")
                            else:
                                del TEACHER_CLASSES[teacher_name]
                                del USERS[teacher_name]
                                update_users()
                                st.success(f"✅ تم حذف المعلم {teacher_name}")
                                st.rerun()
        
        # تبويب إدارة سجلات الغياب
        with tabs[3]:
            st.markdown("## 📋 إدارة سجلات الغياب")
            
            df_all = read_sheet()
            
            if not df_all.empty:
                st.info(f"📊 إجمالي السجلات: {len(df_all)}")
                
                # بحث وتصفية
                st.markdown("### 🔍 البحث والتصفية")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    search_student = st.text_input("بحث باسم الطالب", key="search_student_admin_input")
                with col2:
                    search_class = st.selectbox("تصفية بالفصل", ["الكل"] + list(CLASSES.keys()), 
                                              key="search_class_admin_select")
                with col3:
                    search_status = st.selectbox("تصفية بالحالة", ["الكل", "حاضر", "غياب"], 
                                               key="search_status_admin_select")
                with col4:
                    search_date = st.text_input("تصفية بالتاريخ (يوم/شهر/سنة)", key="search_date_admin_input")
                
                # تطبيق التصفية
                filtered_df = df_all.copy()
                
                if search_student:
                    filtered_df = filtered_df[filtered_df["student"].str.contains(search_student, na=False, case=False)]
                
                if search_class != "الكل":
                    filtered_df = filtered_df[filtered_df["class"] == search_class]
                
                if search_status != "الكل":
                    filtered_df = filtered_df[filtered_df["status"].str.contains(search_status, na=False, case=False)]
                
                if search_date:
                    filtered_df = filtered_df[filtered_df["date"].str.contains(search_date, na=False, case=False)]
                
                # عرض البيانات
                st.markdown(f"### 📋 نتائج البحث ({len(filtered_df)} سجل)")
                
                if not filtered_df.empty:
                    display_df = filtered_df.copy()
                    display_df = display_df.reset_index(drop=True)
                    display_df.index = display_df.index + 1
                    display_df = display_df.rename(columns={
                        "student": "الطالب",
                        "teacher": "المعلم",
                        "class": "الفصل",
                        "status": "الحالة",
                        "date": "التاريخ"
                    })
                    
                    st.dataframe(display_df, use_container_width=True)
                    
                    # خيارات الحذف
                    st.markdown("### 🗑️ خيارات حذف السجلات")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        if st.button("🗑️ حذف السجلات المصفاة", key="delete_filtered_btn"):
                            if len(filtered_df) > 0:
                                # حذف سجلات الطلاب المصفاة
                                success_count = 0
                                for _, row in filtered_df.iterrows():
                                    success, message = delete_specific_records(
                                        student_name=row["student"],
                                        date_str=row["date"]
                                    )
                                    if success:
                                        success_count += 1
                                
                                st.success(f"✅ تم حذف {success_count} سجل")
                                st.rerun()
                    
                    with col2:
                        student_to_delete = st.selectbox(
                            "اختر طالب لحذف سجلاته",
                            ["اختر طالباً"] + sorted(df_all["student"].unique().tolist()),
                            key="student_delete_select"
                        )
                        
                        if student_to_delete != "اختر طالباً":
                            student_records = df_all[df_all["student"] == student_to_delete]
                            st.info(f"عدد سجلات الطالب: {len(student_records)}")
                            
                            if st.button(f"🗑️ حذف جميع سجلات {student_to_delete}", key="delete_student_records_btn"):
                                success, message = delete_specific_records(student_name=student_to_delete)
                                if success:
                                    st.success(f"✅ {message}")
                                    st.rerun()
                    
                    with col3:
                        if st.button("🗑️ حذف جميع السجلات", key="delete_all_records_btn"):
                            if clear_all_records():
                                st.success("✅ تم حذف جميع السجلات بنجاح")
                                st.rerun()
                            else:
                                st.error("❌ فشل في حذف السجلات")
                
                else:
                    st.info("📭 لا توجد سجلات مطابقة لبحثك")
                
                # زر تنزيل البيانات المصفاة
                if not filtered_df.empty:
                    csv_data = filtered_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 تحميل البيانات المصفاة (CSV)",
                        data=csv_data,
                        file_name=f"بيانات_مصفاة_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="download_filtered_data_btn"
                    )
            
            else:
                st.info("📭 لا توجد سجلات في قاعدة البيانات")
        
        # تبويب استيراد/تصدير
        with tabs[4]:
            st.markdown("## 📥 استيراد/تصدير البيانات")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📤 تصدير البيانات")
                
                # تصدير بيانات الطلاب
                students_data = []
                for class_name, students in CLASSES.items():
                    for student in students:
                        students_data.append({
                            "اسم_الطالب": student,
                            "الفصل": class_name,
                            "كلمة_المرور": student_passwords.get(student, "")
                        })
                
                if students_data:
                    students_df = pd.DataFrame(students_data)
                    students_csv = students_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات الطلاب (CSV)",
                        data=students_csv,
                        file_name=f"بيانات_الطلاب_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="export_students_btn"
                    )
                else:
                    st.info("📭 لا توجد بيانات طلاب للتصدير")
                
                # تصدير بيانات الفصول
                classes_data = []
                for class_name, students in CLASSES.items():
                    teacher = None
                    for t, classes in TEACHER_CLASSES.items():
                        if class_name in classes:
                            teacher = t
                            break
                    
                    classes_data.append({
                        "اسم_الفصل": class_name,
                        "عدد_الطلاب": len(students),
                        "المعلم_المسؤول": teacher or ""
                    })
                
                if classes_data:
                    classes_df = pd.DataFrame(classes_data)
                    classes_csv = classes_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات الفصول (CSV)",
                        data=classes_csv,
                        file_name=f"بيانات_الفصول_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="export_classes_btn"
                    )
                
                # تصدير بيانات المعلمين
                teachers_data = []
                for teacher_name, classes in TEACHER_CLASSES.items():
                    teachers_data.append({
                        "اسم_المعلم": teacher_name,
                        "الفصول_المسؤول_عنها": ", ".join(classes),
                        "عدد_الفصول": len(classes)
                    })
                
                if teachers_data:
                    teachers_df = pd.DataFrame(teachers_data)
                    teachers_csv = teachers_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات المعلمين (CSV)",
                        data=teachers_csv,
                        file_name=f"بيانات_المعلمين_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key="export_teachers_btn"
                    )
            
            with col2:
                st.markdown("### 📥 استيراد البيانات")
                
                uploaded_file = st.file_uploader("اختر ملف CSV للاستيراد", type=['csv'], 
                                               key="import_csv_file")
                
                if uploaded_file is not None:
                    try:
                        # قراءة الملف
                        import_df = pd.read_csv(uploaded_file, encoding='utf-8')
                        st.success(f"✅ تم تحميل الملف بنجاح ({len(import_df)} سطر)")
                        
                        # عرض عينة من البيانات
                        st.dataframe(import_df.head(5), use_container_width=True)
                        
                        # تحديد نوع البيانات
                        import_type = st.selectbox(
                            "نوع البيانات للاستيراد",
                            ["بيانات الطلاب", "بيانات الغياب"],
                            key="import_type_select"
                        )
                        
                        if import_type == "بيانات الطلاب":
                            # التحقق من الأعمدة
                            required_cols = ["اسم_الطالب", "الفصل"]
                            missing_cols = [col for col in required_cols if col not in import_df.columns]
                            
                            if not missing_cols:
                                if st.button("📥 استيراد بيانات الطلاب", key="import_students_data_btn"):
                                    success_count = 0
                                    for _, row in import_df.iterrows():
                                        student_name = str(row["اسم_الطالب"]).strip()
                                        class_name = str(row["الفصل"]).strip()
                                        password = str(row.get("كلمة_المرور", f"stu{hash(student_name) % 10000:04d}")).strip()
                                        
                                        if class_name in CLASSES and student_name not in CLASSES[class_name]:
                                            CLASSES[class_name].append(student_name)
                                            student_passwords[student_name] = password
                                            success_count += 1
                                    
                                    update_users()
                                    st.success(f"✅ تم استيراد {success_count} طالب بنجاح")
                                    st.rerun()
                            else:
                                st.error(f"❌ الملف يفتقد الأعمدة التالية: {', '.join(missing_cols)}")
                        
                        elif import_type == "بيانات الغياب":
                            # التحقق من الأعمدة
                            required_cols = ["student", "teacher", "class", "status", "date"]
                            missing_cols = [col for col in required_cols if col not in import_df.columns]
                            
                            if not missing_cols:
                                if st.button("📥 استيراد بيانات الغياب", key="import_attendance_data_btn"):
                                    # تحويل البيانات
                                    import_data = import_df[required_cols].values.tolist()
                                    
                                    # إضافة البيانات
                                    if append_to_sheet(import_data):
                                        st.success(f"✅ تم استيراد {len(import_data)} سجل غياب بنجاح")
                                        st.rerun()
                                    else:
                                        st.error("❌ فشل في استيراد البيانات")
                            else:
                                st.error(f"❌ الملف يفتقد الأعمدة التالية: {', '.join(missing_cols)}")
                    
                    except Exception as e:
                        st.error(f"❌ خطأ في قراءة الملف: {str(e)}")

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
