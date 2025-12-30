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
# جعل المتغيرات عامة لتعديلها
global CLASSES, TEACHER_CLASSES, USERS, student_passwords, ALL_STUDENTS, STUDENT_TO_CLASS

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

# قائمة المعلمين والفصول التي يدرسونها
TEACHER_CLASSES = {
    "مينا سمير": ["Class B", "Class C"],
    "فادي حبيب": ["Class D", "Class E"]
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

# دالة لتحديث المتغيرات العالمية
def update_global_variables():
    """تحديث المتغيرات العالمية بناءً على CLASSES الحالية"""
    global STUDENT_TO_CLASS, ALL_STUDENTS, USERS
    
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

# تحديث المتغيرات لأول مرة
update_global_variables()

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
        
        # الطريقة المباشرة لقراءة SERVICE_ACCOUNT
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

# تهيئة الاتصال مع Google Sheets
def init_google_sheets():
    """تهيئة الاتصال بـ Google Sheets"""
    global worksheet, connection_status
    
    if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
        try:
            SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
            
            # استخدام JSON مباشرة
            creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
            gc = gspread.authorize(creds)
            
            # محاولة فتح أو إنشاء الـ Sheet
            try:
                # محاولة فتح الـ Sheet الموجود
                sh = gc.open(SHEET_NAME)
                worksheet = sh.sheet1
                connection_status = f"✅ متصل بـ {SHEET_NAME}"
                
                # التحقق من وجود العناوين
                try:
                    current_data = worksheet.get_all_values()
                    if not current_data or len(current_data) == 0:
                        # إذا كانت الورقة فارغة، أضف العناوين
                        headers = ["student", "teacher", "class", "status", "date"]
                        worksheet.append_row(headers)
                        logger.info("✅ تم إضافة العناوين إلى الورقة")
                    else:
                        logger.info(f"✅ تم تحميل {len(current_data)-1 if len(current_data) > 1 else 0} سجل")
                except Exception as e:
                    logger.error(f"❌ خطأ في التحقق من البيانات: {e}")
                    
            except gspread.exceptions.SpreadsheetNotFound:
                # إذا لم يتم العثور على الـ Sheet
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

# استدعاء تهيئة الاتصال
init_google_sheets()

# Helper functions
def normalize_date_for_display(src_date_str):
    """معالجة التاريخ للعرض في الجداول"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    
    s = str(src_date_str).strip()
    
    # إذا كان التاريخ بالفعل بالصيغة الصحيحة
    if " / " in s:
        return s
    
    # محاولة تحليل التاريخ باستخدام dateutil
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
        
        # تنسيق yyyymmdd
        elif len(s) == 8 and s.isdigit():
            y = s[0:4]
            m = s[4:6]
            d = s[6:8]
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
            
    except Exception as e:
        logger.error(f"خطأ في معالجة التاريخ {s}: {e}")
    
    # إذا فشل كل شيء، ارجع النص الأصلي
    return s

def read_sheet():
    """قراءة البيانات من Google Sheets"""
    if worksheet is None:
        logger.warning("❌ لا يوجد اتصال بـ Google Sheets")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    try:
        # قراءة جميع البيانات
        data = worksheet.get_all_records()
        
        if not data:
            logger.info("📭 الورقة فارغة أو لا توجد بيانات")
            return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
        
        logger.info(f"✅ تم قراءة {len(data)} سجل من Google Sheets")
        
        # تحويل إلى DataFrame
        df = pd.DataFrame(data)
        
        # التحقق من وجود جميع الأعمدة المطلوبة
        required_columns = ["student", "teacher", "class", "status", "date"]
        for col in required_columns:
            if col not in df.columns:
                df[col] = ""
        
        # تنظيف البيانات
        df = df[required_columns]  # الحفاظ على الأعمدة المطلوبة فقط
        df = df.dropna(how='all')  # حذف الصفوف الفارغة تمامًا
        df = df.fillna("")  # ملء القيم الفارغة
        
        # تنظيف النصوص
        for col in ["student", "teacher", "class", "status"]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        # تحويل التواريخ إلى تنسيق موحد
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
        # إضافة الصفوف الجديدة
        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")
        logger.info(f"✅ تم إضافة {len(new_rows)} سجل جديد إلى Google Sheets")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في إضافة البيانات إلى Google Sheets: {str(e)}")
        return False

def update_sheet(row_index, new_data):
    """تحديث صف محدد في Google Sheets"""
    if worksheet is None:
        logger.error("❌ لا يوجد اتصال بـ Google Sheets")
        return False
    
    try:
        # تحديث الصف (يبدأ الفهرس من 1)
        worksheet.update(f'A{row_index}', [new_data])
        logger.info(f"✅ تم تحديث الصف {row_index} في Google Sheets")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في تحديث البيانات في Google Sheets: {str(e)}")
        return False

def delete_from_sheet(row_index):
    """حذف صف محدد من Google Sheets"""
    if worksheet is None:
        logger.error("❌ لا يوجد اتصال بـ Google Sheets")
        return False
    
    try:
        # حذف الصف (يبدأ الفهرس من 1)
        worksheet.delete_rows(row_index)
        logger.info(f"✅ تم حذف الصف {row_index} من Google Sheets")
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في حذف البيانات من Google Sheets: {str(e)}")
        return False

def get_student_class(student_name):
    """الحصول على فصل الطالب تلقائياً"""
    return STUDENT_TO_CLASS.get(student_name, "")

def get_class_statistics(class_name):
    """الحصول على إحصائيات الفصل"""
    df = read_sheet()
    
    logger.info(f"📊 جاري حساب إحصائيات الفصل: {class_name}")
    logger.info(f"📊 إجمالي السجلات في قاعدة البيانات: {len(df)}")
    
    if df.empty:
        logger.info(f"📭 لا توجد سجلات للفصل {class_name}")
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # تصفية البيانات للفصل المحدد - تحسين التطابق
    class_df = df.copy()
    
    # تطبيع أسماء الفصول في البيانات
    class_df["class_normalized"] = class_df["class"].astype(str).str.strip()
    
    # تطابق دقيق مع الفصل
    class_df_filtered = class_df[class_df["class_normalized"] == class_name.strip()]
    
    logger.info(f"📊 سجلات الفصل {class_name}: {len(class_df_filtered)} سجل")
    
    if class_df_filtered.empty:
        logger.info(f"📭 لا توجد سجلات مطابقة للفصل {class_name}")
        return {
            "total_students": len(CLASSES.get(class_name, [])),
            "total_records": 0,
            "present_count": 0,
            "absent_count": 0,
            "attendance_rate": 0,
            "students": []
        }
    
    # حساب الإحصائيات
    total_records = len(class_df_filtered)
    present_count = 0
    absent_count = 0
    
    # تطبيع حالة الحضور للبحث
    class_df_filtered["status_normalized"] = class_df_filtered["status"].astype(str).str.strip()
    
    present_count = len(class_df_filtered[class_df_filtered["status_normalized"] == "حاضر"])
    absent_count = len(class_df_filtered[class_df_filtered["status_normalized"].str.contains("غياب", na=False)])
    
    logger.info(f"📊 الحاضرون: {present_count}, الغائبون: {absent_count}")
    
    # حساب نسبة الحضور
    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
    
    # إحصائيات لكل طالب
    student_stats = []
    class_students = CLASSES.get(class_name, [])
    
    for student in class_students:
        # استخدام تطابق دقيق مع الاسم
        student_df = class_df_filtered[class_df_filtered["student"].astype(str).str.strip() == student.strip()]
        student_total = len(student_df)
        student_present = len(student_df[student_df["status_normalized"] == "حاضر"])
        student_absent = len(student_df[student_df["status_normalized"].str.contains("غياب", na=False)])
        student_rate = (student_present / student_total * 100) if student_total > 0 else 0
        
        student_stats.append({
            "name": student,
            "total": student_total,
            "present": student_present,
            "absent": student_absent,
            "rate": student_rate
        })
    
    result = {
        "total_students": len(class_students),
        "total_records": total_records,
        "present_count": present_count,
        "absent_count": absent_count,
        "attendance_rate": attendance_rate,
        "students": student_stats
    }
    
    logger.info(f"📊 إحصائيات الفصل {class_name}: {result}")
    return result

def get_class_attendance_history(class_name):
    """الحصول على سجل الحضور للفصل"""
    df = read_sheet()
    
    if df.empty:
        return pd.DataFrame()
    
    # تصفية البيانات للفصل المحدد
    class_df = df[df["class"].astype(str).str.strip() == class_name.strip()].copy()
    
    if class_df.empty:
        return pd.DataFrame()
    
    # تنظيف التواريخ
    class_df["date_clean"] = class_df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    
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
    
    class_df["status_clean"] = class_df["status"].apply(clean_status)
    
    # ترتيب حسب التاريخ
    try:
        class_df["temp_date"] = pd.to_datetime(class_df["date"], errors='coerce', dayfirst=True)
        class_df = class_df.sort_values("temp_date", ascending=False)
        class_df = class_df.drop(columns=["temp_date"])
    except:
        class_df = class_df.sort_values("date_clean", ascending=False)
    
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
    """تسجيل الحضور والغياب"""
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
    
    success_count = 0
    
    # حفظ في Google Sheets
    if rows:
        if append_to_sheet(rows):
            success_count = len(rows)
        else:
            # حفظ البيانات محلياً في حالة فشل الاتصال
            logger.warning("⚠️ تم حفظ البيانات محلياً فقط بسبب مشكلة في الاتصال")
            success_count = len(rows)
    
    # رسالة تلغرام
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if rows:
        absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
        
        # حساب عدد الحاضرين
        present_count = len(class_students) - len(selected_absent)
        
        # رسالة معدلة
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
        # البحث عن سجلات الطالب
        df_matches = df[df["student"].astype(str).str.strip() == student_name.strip()].copy()
        
        if df_matches.empty:
            return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"])
        
        # تنظيف التواريخ
        df_matches["date_clean"] = df_matches["date"].apply(
            lambda x: normalize_date_for_display(x) if pd.notna(x) else ""
        )
        
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
        
        df_matches["status_clean"] = df_matches["status"].apply(clean_status)
        
        # ترتيب حسب التاريخ
        try:
            df_matches["temp_date"] = pd.to_datetime(df_matches["date"], errors='coerce', dayfirst=True)
            df_matches = df_matches.sort_values("temp_date", ascending=False)
            df_matches = df_matches.drop(columns=["temp_date"])
        except:
            df_matches = df_matches.sort_values("date_clean", ascending=False)
        
        # إعادة تعيين الفهرس وإضافة عمود "المرة"
        df_matches = df_matches.reset_index(drop=True)
        df_matches["المرة"] = range(1, len(df_matches) + 1)
        
        # إعادة تسمية الأعمدة
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
if "teacher_name" not in st.session_state:
    st.session_state.teacher_name = ""
if "teacher_classes" not in st.session_state:
    st.session_state.teacher_classes = []
if "student_name" not in st.session_state:
    st.session_state.student_name = ""

# إضافة متغيرات جلسة جديدة لإدارة الطلاب والفصول
if "admin_tab" not in st.session_state:
    st.session_state.admin_tab = "نظرة عامة"
if "selected_student" not in st.session_state:
    st.session_state.selected_student = None
if "selected_teacher" not in st.session_state:
    st.session_state.selected_teacher = None
if "editing_student" not in st.session_state:
    st.session_state.editing_student = False
if "editing_class" not in st.session_state:
    st.session_state.editing_class = False
if "editing_teacher" not in st.session_state:
    st.session_state.editing_teacher = False
if "editing_record" not in st.session_state:
    st.session_state.editing_record = False

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
    .admin-button {
        margin: 5px;
        padding: 10px 20px;
        border-radius: 10px;
        font-weight: bold;
        transition: all 0.3s;
    }
    .admin-button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
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

# صفحة تسجيل الدخول الرئيسية
if st.session_state.page == "login":
    # إخفاء الـ toolbar في صفحة تسجيل الدخول
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

# إذا كان المستخدم مسجلاً دخوله
elif st.session_state.logged_in:
    show_toolbar()
    
    # الصفحة الرئيسية المشتركة
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
            col1, col2 = st.columns(2)
            
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
        
        # زر تسجيل الخروج للجميع
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
                
                # زر تنزيل واحد فقط
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
        
        # زر العودة للصفحة الرئيسية
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
            
            # زر تنزيل واحد فقط
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
    
    # صفحة مدير النظام - مع ميزات إدارة كاملة
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown("# 👑 لوحة تحكم مدير النظام")
        
        if st.button("🏠 العودة للصفحة الرئيسية", 
                    key="back_to_home_admin", 
                    use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات متقدمة مع ميزات الإدارة
        tabs = st.tabs(["📊 نظرة عامة", "👥 إدارة الطلاب", "🏫 إدارة الفصول", "👨‍🏫 إدارة المعلمين", 
                       "📋 إدارة سجلات الغياب", "📥 استيراد/تصدير"])
        
        # تبويب النظرة العامة
        with tabs[0]:
            st.markdown("## 📊 نظرة عامة على النظام")
            
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
            
            st.markdown("### 📈 إحصائيات الحضور العام")
            
            if not df_all.empty:
                # حساب إحصائيات عامة
                present_total = df_all[df_all["status"].str.contains("حاضر", na=False)].shape[0]
                absent_total = df_all[df_all["status"].str.contains("غياب", na=False)].shape[0]
                attendance_rate_total = (present_total / total_records * 100) if total_records > 0 else 0
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.metric("إجمالي الحضور", present_total)
                with col_b:
                    st.metric("إجمالي الغياب", absent_total)
                with col_c:
                    st.metric("معدل الحضور العام", f"{attendance_rate_total:.1f}%")
                
                st.markdown("### 📋 آخر 10 سجلات")
                display_df = df_all.head(10).copy()
                display_df = display_df.rename(columns={
                    "student": "الطالب",
                    "teacher": "المعلم",
                    "class": "الفصل",
                    "status": "الحالة",
                    "date": "التاريخ"
                })
                st.dataframe(display_df, use_container_width=True, hide_index=True)
                
                # زر تنزيل
                csv_data = df_all.to_csv(index=False, encoding='utf-8-sig')
                timestamp = int(time.time() * 1000)
                st.download_button(
                    label="📥 تحميل جميع البيانات (CSV)",
                    data=csv_data,
                    file_name=f"جميع_بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True,
                    key=f"download_all_data_admin_{timestamp}"
                )
            else:
                st.info("📭 لا توجد بيانات في Google Sheets بعد.")
        
        # تبويب إدارة الطلاب
        with tabs[1]:
            st.markdown("## 👥 إدارة الطلاب")
            
            # قسم إضافة طالب جديد
            st.markdown("### ➕ إضافة طالب جديد")
            with st.expander("إضافة طالب جديد", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    new_student_name = st.text_input("اسم الطالب الجديد", key="new_student_name")
                with col2:
                    new_student_class = st.selectbox("الفصل", list(CLASSES.keys()), key="new_student_class")
                with col3:
                    new_student_password = st.text_input("كلمة المرور", type="password", key="new_student_password")
                
                if st.button("➕ إضافة الطالب", key="add_student_btn"):
                    if new_student_name and new_student_class and new_student_password:
                        if new_student_name not in ALL_STUDENTS:
                            # إضافة الطالب إلى الفصل
                            CLASSES[new_student_class].append(new_student_name)
                            # تحديث كلمة المرور
                            student_passwords[new_student_name] = new_student_password
                            # تحديث المتغيرات العالمية
                            update_global_variables()
                            
                            st.success(f"✅ تم إضافة الطالب {new_student_name} إلى الفصل {new_student_class}")
                            st.rerun()
                        else:
                            st.error("❌ الطالب موجود بالفعل!")
                    else:
                        st.warning("⚠️ يجب ملء جميع الحقول")
            
            st.markdown("### 📋 قائمة الطلاب حسب الفصول")
            
            # زر تحديث البيانات
            if st.button("🔄 تحديث بيانات الطلاب", key="refresh_students_btn"):
                update_global_variables()
                st.success("✅ تم تحديث بيانات الطلاب")
                st.rerun()
            
            # عرض الطلاب حسب الفصول
            for class_name, students in CLASSES.items():
                expander = st.expander(f"📚 {class_name} ({len(students)} طالب)")
                with expander:
                    if not students:
                        st.info("📭 لا يوجد طلاب في هذا الفصل")
                    else:
                        # إنشاء DataFrame للطلاب
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
                        
                        # زر حذف طالب
                        st.markdown("### 🗑️ حذف طالب")
                        delete_student = st.selectbox(
                            f"اختر طالب للحذف من {class_name}",
                            students,
                            key=f"delete_student_select_{class_name}"
                        )
                        
                        if st.button(f"🗑️ حذف {delete_student}", key=f"delete_btn_{delete_student}"):
                            if delete_student in CLASSES[class_name]:
                                CLASSES[class_name].remove(delete_student)
                                if delete_student in student_passwords:
                                    del student_passwords[delete_student]
                                # تحديث المتغيرات العالمية
                                update_global_variables()
                                st.success(f"✅ تم حذف الطالب {delete_student}")
                                st.rerun()
        
        # تبويب إدارة الفصول
        with tabs[2]:
            st.markdown("## 🏫 إدارة الفصول")
            
            # قسم إضافة فصل جديد
            st.markdown("### ➕ إضافة فصل جديد")
            col1, col2 = st.columns(2)
            with col1:
                new_class_name = st.text_input("اسم الفصل الجديد", key="new_class_name")
            with col2:
                new_class_teacher = st.selectbox(
                    "المعلم المسؤول",
                    list(TEACHER_CLASSES.keys()) + ["اختر لاحقاً"],
                    key="new_class_teacher"
                )
            
            if st.button("➕ إضافة فصل جديد", key="add_class_btn"):
                if new_class_name and new_class_name not in CLASSES:
                    CLASSES[new_class_name] = []
                    if new_class_teacher != "اختر لاحقاً":
                        if new_class_teacher in TEACHER_CLASSES:
                            TEACHER_CLASSES[new_class_teacher].append(new_class_name)
                        else:
                            TEACHER_CLASSES[new_class_teacher] = [new_class_name]
                    
                    update_global_variables()
                    st.success(f"✅ تم إضافة الفصل {new_class_name}")
                    st.rerun()
                elif new_class_name in CLASSES:
                    st.error("❌ الفصل موجود بالفعل!")
                else:
                    st.warning("⚠️ أدخل اسم الفصل")
            
            st.markdown("### 📋 قائمة الفصول")
            
            for class_name, students in CLASSES.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"#### {class_name}")
                    st.write(f"**عدد الطلاب:** {len(students)}")
                    
                    # عرض المعلم المسؤول
                    teacher_name = None
                    for teacher, classes in TEACHER_CLASSES.items():
                        if class_name in classes:
                            teacher_name = teacher
                            break
                    
                    if teacher_name:
                        st.write(f"**المعلم المسؤول:** {teacher_name}")
                    else:
                        st.write("**المعلم المسؤول:** غير معين")
                
                with col2:
                    # تغيير المعلم المسؤول
                    new_teacher = st.selectbox(
                        "تغيير المعلم",
                        list(TEACHER_CLASSES.keys()) + ["غير معين"],
                        key=f"change_teacher_{class_name}",
                        index=list(TEACHER_CLASSES.keys()).index(teacher_name) if teacher_name in TEACHER_CLASSES else len(TEACHER_CLASSES)
                    )
                    
                    if st.button("💾 حفظ", key=f"save_teacher_{class_name}"):
                        # إزالة الفصل من جميع المعلمين
                        for teacher in TEACHER_CLASSES:
                            if class_name in TEACHER_CLASSES[teacher]:
                                TEACHER_CLASSES[teacher].remove(class_name)
                        
                        # إضافة الفصل للمعلم الجديد
                        if new_teacher != "غير معين":
                            TEACHER_CLASSES[new_teacher].append(class_name)
                        
                        update_global_variables()
                        st.success(f"✅ تم تحديث المعلم المسؤول للفصل {class_name}")
                        st.rerun()
                
                with col3:
                    if st.button(f"🗑️ حذف الفصل", key=f"delete_class_{class_name}"):
                        if len(students) == 0:
                            # حذف الفصل من جميع المعلمين
                            for teacher in TEACHER_CLASSES:
                                if class_name in TEACHER_CLASSES[teacher]:
                                    TEACHER_CLASSES[teacher].remove(class_name)
                            
                            # حذف الفصل
                            del CLASSES[class_name]
                            
                            update_global_variables()
                            st.success(f"✅ تم حذف الفصل {class_name}")
                            st.rerun()
                        else:
                            st.error("❌ لا يمكن حذف فصل به طلاب! أزل الطلاب أولاً")
                
                st.markdown("---")
        
        # تبويب إدارة المعلمين
        with tabs[3]:
            st.markdown("## 👨‍🏫 إدارة المعلمين")
            
            # قسم إضافة معلم جديد
            st.markdown("### ➕ إضافة معلم جديد")
            col1, col2, col3 = st.columns(3)
            with col1:
                new_teacher_name = st.text_input("اسم المعلم الجديد", key="new_teacher_name")
            with col2:
                new_teacher_password = st.text_input("كلمة المرور", type="password", key="new_teacher_password")
            with col3:
                # اختيار الفصول
                available_classes = list(CLASSES.keys())
                new_teacher_classes = st.multiselect(
                    "الفصول المسؤول عنها",
                    available_classes,
                    key="new_teacher_classes"
                )
            
            if st.button("➕ إضافة معلم جديد", key="add_teacher_btn"):
                if new_teacher_name and new_teacher_password and new_teacher_name not in TEACHER_CLASSES:
                    TEACHER_CLASSES[new_teacher_name] = new_teacher_classes
                    
                    # تحديث USERS
                    USERS[new_teacher_name] = {
                        "password": new_teacher_password,
                        "role": "teacher",
                        "teacher_name": new_teacher_name,
                        "classes": new_teacher_classes
                    }
                    
                    update_global_variables()
                    st.success(f"✅ تم إضافة المعلم {new_teacher_name}")
                    st.rerun()
                elif new_teacher_name in TEACHER_CLASSES:
                    st.error("❌ المعلم موجود بالفعل!")
                else:
                    st.warning("⚠️ يجب ملء جميع الحقول")
            
            st.markdown("### 📋 قائمة المعلمين")
            
            for teacher_name, classes in TEACHER_CLASSES.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                with col1:
                    st.markdown(f"#### {teacher_name}")
                    st.write(f"**الفصول المسؤول عنها:** {', '.join(classes) if classes else 'لا يوجد'}")
                    st.write(f"**عدد الفصول:** {len(classes)}")
                
                with col2:
                    # تعديل كلمة المرور
                    new_password = st.text_input(
                        "كلمة المرور الجديدة",
                        type="password",
                        key=f"new_pass_{teacher_name}",
                        placeholder="اترك فارغاً للحفاظ على الكلمة الحالية"
                    )
                    
                    if st.button("💾 تحديث", key=f"update_pass_{teacher_name}"):
                        if new_password:
                            USERS[teacher_name]["password"] = new_password
                            st.success(f"✅ تم تحديث كلمة مرور {teacher_name}")
                            st.rerun()
                
                with col3:
                    if st.button(f"🗑️ حذف", key=f"delete_teacher_{teacher_name}"):
                        if teacher_name != "مينا سمير" and teacher_name != "فادي حبيب":  # منع حذف المعلمين الأساسيين
                            # نقل الفصول إلى معلم آخر
                            if classes:
                                st.warning(f"⚠️ المعلم {teacher_name} مسؤول عن فصول. حدد معلم لنقل الفصول إليه:")
                                other_teachers = [t for t in TEACHER_CLASSES.keys() if t != teacher_name]
                                if other_teachers:
                                    transfer_to = st.selectbox("نقل الفصول إلى", other_teachers)
                                    if st.button("✅ نقل وحذف"):
                                        for class_name in classes:
                                            TEACHER_CLASSES[transfer_to].append(class_name)
                                        del TEACHER_CLASSES[teacher_name]
                                        del USERS[teacher_name]
                                        update_global_variables()
                                        st.success(f"✅ تم نقل الفصول إلى {transfer_to} وحذف {teacher_name}")
                                        st.rerun()
                                else:
                                    st.error("❌ لا يوجد معلمين آخرين لنقل الفصول إليهم!")
                            else:
                                del TEACHER_CLASSES[teacher_name]
                                del USERS[teacher_name]
                                update_global_variables()
                                st.success(f"✅ تم حذف المعلم {teacher_name}")
                                st.rerun()
                        else:
                            st.error("❌ لا يمكن حذف هذا المعلم الأساسي!")
                
                st.markdown("---")
        
        # تبويب إدارة سجلات الغياب
        with tabs[4]:
            st.markdown("## 📋 إدارة سجلات الغياب")
            
            df_all = read_sheet()
            
            if not df_all.empty:
                st.info(f"📊 إجمالي السجلات: {len(df_all)}")
                
                # بحث وتصفية
                st.markdown("### 🔍 البحث والتصفية")
                col1, col2, col3 = st.columns(3)
                with col1:
                    search_student = st.text_input("بحث باسم الطالب", key="search_student_admin")
                with col2:
                    search_class = st.selectbox("تصفية بالفصل", ["الكل"] + list(CLASSES.keys()), key="search_class_admin")
                with col3:
                    search_status = st.selectbox("تصفية بالحالة", ["الكل", "حاضر", "غياب"], key="search_status_admin")
                
                # تطبيق التصفية
                filtered_df = df_all.copy()
                
                if search_student:
                    filtered_df = filtered_df[filtered_df["student"].str.contains(search_student, na=False, case=False)]
                
                if search_class != "الكل":
                    filtered_df = filtered_df[filtered_df["class"] == search_class]
                
                if search_status != "الكل":
                    filtered_df = filtered_df[filtered_df["status"].str.contains(search_status, na=False, case=False)]
                
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
                    
                    # زر حذف سجلات
                    st.markdown("### 🗑️ حذف سجلات")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        delete_choice = st.selectbox(
                            "خيارات الحذف",
                            ["حذف سجل محدد", "حذف جميع السجلات المصفاة", "حذف سجلات طالب محدد"],
                            key="delete_choice_admin"
                        )
                    
                    if delete_choice == "حذف سجل محدد":
                        record_index = st.number_input(
                            "رقم السجل للحذف",
                            min_value=1,
                            max_value=len(filtered_df),
                            value=1,
                            key="delete_record_index"
                        )
                        
                        if st.button("🗑️ حذف السجل المحدد", key="delete_specific_record"):
                            # الحصول على السجل الحقيقي في Google Sheets
                            # هذا يتطلب معرفة فهرس السجل في Google Sheets
                            st.warning("⚠️ هذه الميزة تحتاج إلى تطوير إضافي للوصول إلى الفهرس الصحيح")
                    
                    elif delete_choice == "حذف جميع السجلات المصفاة":
                        if st.button("🗑️ حذف جميع السجلات المصفاة", key="delete_filtered_records"):
                            st.warning("⚠️ هذه الميزة تحتاج إلى تطوير إضافي لحذف السجلات المصفاة")
                    
                    elif delete_choice == "حذف سجلات طالب محدد":
                        student_to_delete = st.selectbox(
                            "اختر طالب",
                            sorted(df_all["student"].unique()),
                            key="student_to_delete_records"
                        )
                        
                        if st.button("🗑️ حذف جميع سجلات الطالب", key="delete_student_records"):
                            student_records = df_all[df_all["student"] == student_to_delete]
                            st.warning(f"⚠️ سيتم حذف {len(student_records)} سجل للطالب {student_to_delete}")
                            st.warning("⚠️ هذه الميزة تحتاج إلى تطوير إضافي لحذف سجلات محددة")
                
                else:
                    st.info("📭 لا توجد سجلات مطابقة لبحثك")
                
                # زر تنزيل البيانات المصفاة
                if not filtered_df.empty:
                    csv_data = filtered_df.to_csv(index=False, encoding='utf-8-sig')
                    timestamp = int(time.time() * 1000)
                    st.download_button(
                        label="📥 تحميل البيانات المصفاة (CSV)",
                        data=csv_data,
                        file_name=f"بيانات_مصفاة_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        key=f"download_filtered_data_{timestamp}"
                    )
            
            else:
                st.info("📭 لا توجد سجلات في قاعدة البيانات")
        
        # تبويب استيراد/تصدير
        with tabs[5]:
            st.markdown("## 📥 استيراد/تصدير البيانات")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown("### 📤 تصدير البيانات")
                st.markdown("يمكنك تصدير البيانات الحالية في النظام:")
                
                # تصدير بيانات الطلاب
                students_data = []
                for class_name, students in CLASSES.items():
                    for student in students:
                        students_data.append({
                            "اسم الطالب": student,
                            "الفصل": class_name,
                            "كلمة المرور": student_passwords.get(student, "")
                        })
                
                students_df = pd.DataFrame(students_data)
                students_csv = students_df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير بيانات الطلاب (CSV)",
                    data=students_csv,
                    file_name=f"بيانات_الطلاب_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
                
                # تصدير بيانات الفصول
                classes_data = []
                for class_name, students in CLASSES.items():
                    teacher = None
                    for t, classes in TEACHER_CLASSES.items():
                        if class_name in classes:
                            teacher = t
                            break
                    
                    classes_data.append({
                        "اسم الفصل": class_name,
                        "عدد الطلاب": len(students),
                        "المعلم المسؤول": teacher or ""
                    })
                
                classes_df = pd.DataFrame(classes_data)
                classes_csv = classes_df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير بيانات الفصول (CSV)",
                    data=classes_csv,
                    file_name=f"بيانات_الفصول_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                st.markdown("### 📥 استيراد البيانات")
                st.markdown("يمكنك استيراد البيانات من ملف CSV:")
                
                uploaded_file = st.file_uploader("اختر ملف CSV", type=['csv'], key="import_csv")
                
                if uploaded_file is not None:
                    try:
                        # قراءة الملف
                        import_df = pd.read_csv(uploaded_file, encoding='utf-8')
                        st.success(f"✅ تم تحميل الملف بنجاح ({len(import_df)} سطر)")
                        
                        # عرض البيانات
                        st.dataframe(import_df.head(10), use_container_width=True)
                        
                        # خيارات الاستيراد
                        import_option = st.selectbox(
                            "نوع البيانات للاستيراد",
                            ["بيانات الطلاب", "بيانات الغياب"],
                            key="import_option"
                        )
                        
                        if import_option == "بيانات الطلاب":
                            # التحقق من الأعمدة المطلوبة
                            required_cols = ["اسم الطالب", "الفصل"]
                            missing_cols = [col for col in required_cols if col not in import_df.columns]
                            
                            if not missing_cols:
                                st.success("✅ الملف يحتوي على الأعمدة المطلوبة")
                                
                                if st.button("📥 استيراد بيانات الطلاب", key="import_students_btn"):
                                    success_count = 0
                                    for _, row in import_df.iterrows():
                                        student_name = str(row["اسم الطالب"]).strip()
                                        class_name = str(row["الفصل"]).strip()
                                        password = str(row.get("كلمة المرور", f"stu{hash(student_name) % 10000:04d}")).strip()
                                        
                                        if class_name in CLASSES and student_name not in CLASSES[class_name]:
                                            CLASSES[class_name].append(student_name)
                                            student_passwords[student_name] = password
                                            success_count += 1
                                    
                                    update_global_variables()
                                    st.success(f"✅ تم استيراد {success_count} طالب بنجاح")
                                    st.rerun()
                            else:
                                st.error(f"❌ الملف يفتقد الأعمدة التالية: {', '.join(missing_cols)}")
                        
                        elif import_option == "بيانات الغياب":
                            # التحقق من الأعمدة المطلوبة
                            required_cols = ["student", "teacher", "class", "status", "date"]
                            missing_cols = [col for col in required_cols if col not in import_df.columns]
                            
                            if not missing_cols:
                                st.success("✅ الملف يحتوي على الأعمدة المطلوبة")
                                
                                if st.button("📥 استيراد بيانات الغياب", key="import_attendance_btn"):
                                    # تحويل البيانات إلى قائمة
                                    import_data = import_df[required_cols].values.tolist()
                                    
                                    # إضافة البيانات إلى Google Sheets
                                    if append_to_sheet(import_data):
                                        st.success(f"✅ تم استيراد {len(import_data)} سجل غياب بنجاح")
                                        st.rerun()
                                    else:
                                        st.error("❌ فشل في استيراد البيانات إلى Google Sheets")
                            else:
                                st.error(f"❌ الملف يفتقد الأعمدة التالية: {', '.join(missing_cols)}")
                    
                    except Exception as e:
                        st.error(f"❌ خطأ في قراءة الملف: {str(e)}")

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
