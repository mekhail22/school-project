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
        if not SERVICE_ACCOUNT and hasattr(secrets, 'service_account'):
            try:
                service_account_info = secrets.service_account
                SERVICE_ACCOUNT = {
                    'type': service_account_info.get('type', ''),
                    'project_id': service_account_info.get('project_id', ''),
                    'private_key_id': service_account_info.get('private_key_id', ''),
                    'private_key': service_account_info.get('private_key', '').replace('\\n', '\n'),
                    'client_email': service_account_info.get('client_email', ''),
                    'client_id': service_account_info.get('client_id', ''),
                    'auth_uri': service_account_info.get('auth_uri', 'https://accounts.google.com/o/oauth2/auth'),
                    'token_uri': service_account_info.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    'auth_provider_x509_cert_url': service_account_info.get('auth_provider_x509_cert_url', 'https://www.googleapis.com/oauth2/v1/certs'),
                    'client_x509_cert_url': service_account_info.get('client_x509_cert_url', '')
                }
            except Exception as e:
                st.error(f"❌ خطأ في تحميل service_account: {e}")
        
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
            connection_status = f"✅ تم الاتصال بـ Google Sheets: {SHEET_NAME}"
            
            # التحقق من وجود العناوين
            try:
                current_data = worksheet.get_all_values()
                if not current_data:
                    # إذا كانت الورقة فارغة، أضف العناوين
                    headers = ["student", "teacher", "class", "status", "date"]
                    worksheet.append_row(headers)
            except Exception as e:
                st.error(f"❌ خطأ في التحقق من البيانات: {e}")
                
        except gspread.exceptions.SpreadsheetNotFound:
            # إذا لم يتم العثور على الـ Sheet، لا ننشئ واحدًا جديدًا
            connection_status = f"❌ لم يتم العثور على Google Sheet: {SHEET_NAME}"
            st.error(f"❌ لم يتم العثور على Google Sheet: {SHEET_NAME}")
            st.info("⚠️ يرجى إنشاء Google Sheet يدويًا وإعطاء حساب الخدمة صلاحية الوصول إليه")
            
        except Exception as e:
            connection_status = f"❌ خطأ في فتح الـ Sheet: {str(e)}"
            st.error(f"❌ خطأ في فتح الـ Sheet: {str(e)}")
            
    except Exception as e:
        connection_status = f"❌ فشل في المصادقة: {str(e)}"
        st.error(f"❌ فشل في المصادقة: {str(e)}")
else:
    connection_status = "❌ إعدادات الاتصال غير كاملة"
    st.error("❌ إعدادات الاتصال غير كاملة. يرجى التحقق من إعدادات SERVICE_ACCOUNT")

# Helper functions
def reshape_arabic_text(text):
    """نسخة مبسطة - إرجاع النص كما هو"""
    try:
        return str(text)
    except:
        return str(text)

def is_arabic_text(text):
    """التحقق إذا كان النص عربي"""
    try:
        text_str = str(text)
        # تحقق إذا كان يحتوي على أحرف عربية
        arabic_chars = any('\u0600' <= char <= '\u06FF' for char in text_str)
        return arabic_chars
    except:
        return False

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
        print(f"خطأ في معالجة التاريخ {s}: {e}")
    
    # إذا فشل كل شيء، ارجع النص الأصلي
    return s

def read_sheet():
    """قراءة البيانات من Google Sheets"""
    if worksheet is None:
        # استخدام البيانات المحلية كبديل
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    try:
        # قراءة جميع البيانات
        data = worksheet.get_all_records()
        
        if not data:
            return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
        
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
        
        return df
        
    except Exception as e:
        st.error(f"❌ خطأ في قراءة البيانات من Google Sheets: {str(e)}")
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])

def append_to_sheet(new_rows):
    """إضافة صفوف جديدة إلى Google Sheets"""
    if worksheet is None:
        st.error("❌ لا يوجد اتصال بـ Google Sheets. البيانات سيتم حفظها محلياً فقط.")
        return False
    
    try:
        # إضافة الصفوف الجديدة
        worksheet.append_rows(new_rows, value_input_option="USER_ENTERED")
        st.success(f"✅ تم إضافة {len(new_rows)} سجل جديد إلى Google Sheets")
        return True
        
    except Exception as e:
        st.error(f"❌ خطأ في إضافة البيانات إلى Google Sheets: {str(e)}")
        return False

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
            st.warning("⚠️ تم حفظ البيانات محلياً فقط بسبب مشكلة في الاتصال")
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
        print(f"خطأ في الحصول على سجلات الطالب: {e}")
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
                                telegram_status, telegram_details, success_count = record_attendance(
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
                
                # زر تحميل البيانات كـ CSV بدلاً من PDF
                st.markdown("---")
                st.markdown("### 📥 تصدير بيانات الفصل")
                
                # تصدير البيانات كـ CSV
                if not history_df.empty:
                    csv_data = history_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📄 تحميل بيانات الفصل (CSV)",
                        data=csv_data,
                        file_name=f"بيانات_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True,
                        help="سيحتوي الملف على: الطالب، المعلم، التاريخ، الحالة"
                    )
                
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
            
            # زر تحميل CSV بدلاً من PDF
            csv_data = df_student.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                "📥 تحميل تقرير (CSV)",
                data=csv_data,
                file_name=f"تقرير_غياب_{student_name}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        
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
        
        # تبويبات لوحة التحكم
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 نظرة عامة",
            "👥 إدارة الطلاب",
            "🏫 إدارة الفصول",
            "📋 مراجعة بيانات الغياب",
            "📤 تصدير البيانات"
        ])
        
        with tab1:
            st.markdown("### 📊 نظرة عامة على النظام")
            
            # عرض حالة الاتصال
            st.markdown(f"#### 🔗 حالة الاتصال: **{connection_status}**")
            
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
            
            # عرض بيانات Google Sheets
            st.markdown("### 📊 بيانات Google Sheets")
            
            if not df_all.empty:
                # عرض عدد السجلات
                st.info(f"📊 تم تحميل {len(df_all)} سجل من Google Sheets")
                
                # عرض عينة من البيانات
                st.markdown("#### عينة من البيانات:")
                display_df = df_all.head(10).copy()
                display_df = display_df.rename(columns={
                    "student": "الطالب",
                    "teacher": "المعلم",
                    "class": "الفصل",
                    "status": "الحالة",
                    "date": "التاريخ"
                })
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("📭 لا توجد بيانات في Google Sheets بعد.")
                
            # رسم بياني لتوزيع الغياب حسب الفصل
            st.markdown("### 📈 توزيع الغياب حسب الفصول")
            
            if not df_all.empty and "class" in df_all.columns and "status" in df_all.columns:
                # حساب الغياب لكل فصل
                class_stats = {}
                for class_name in CLASSES.keys():
                    class_df = df_all[df_all["class"] == class_name]
                    if not class_df.empty:
                        absent_count = len(class_df[class_df["status"].str.contains("غياب", na=False)])
                        present_count = len(class_df[class_df["status"] == "حاضر"])
                        total = len(class_df)
                        class_stats[class_name] = {
                            "absent": absent_count,
                            "present": present_count,
                            "total": total,
                            "rate": (present_count / total * 100) if total > 0 else 0
                        }
                
                if class_stats:
                    # إنشاء DataFrame للتوزيع
                    distribution_df = pd.DataFrame.from_dict(class_stats, orient='index')
                    distribution_df = distribution_df.reset_index()
                    distribution_df.columns = ["الفصل", "غياب", "حضور", "إجمالي", "نسبة الحضور"]
                    
                    st.dataframe(distribution_df, use_container_width=True, hide_index=True)
                else:
                    st.info("لا توجد سجلات للعرض بعد.")
            else:
                st.info("لا توجد بيانات كافية للعرض.")
        
        with tab2:
            st.markdown("### 👥 إدارة الطلاب")
            
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown("#### 📋 قائمة الطلاب الحاليين")
                
                # عرض جميع الطلاب حسب الفصول
                for class_name, students in CLASSES.items():
                    with st.expander(f"📚 {class_name} ({len(students)} طالب)"):
                        # إنشاء جدول للطلاب
                        student_data = []
                        for idx, student in enumerate(students, 1):
                            # الحصول على كلمة المرور
                            password = student_passwords.get(student, "غير معرف")
                            student_data.append({
                                "م": idx,
                                "اسم الطالب": student,
                                "كلمة المرور": password,
                                "الفصل": class_name
                            })
                        
                        student_df = pd.DataFrame(student_data)
                        st.dataframe(student_df, use_container_width=True, hide_index=True)
            
            with col2:
                st.markdown("#### ➕ إضافة طالب جديد")
                
                # إضافة طالب جديد
                with st.form(key="add_student_form"):
                    student_name = st.text_input("اسم الطالب الجديد", placeholder="أدخل الاسم الكامل")
                    student_class = st.selectbox("الفصل", list(CLASSES.keys()))
                    student_password = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
                    
                    submit_button = st.form_submit_button("➕ إضافة الطالب", use_container_width=True)
                    
                    if submit_button:
                        if student_name and student_class and student_password:
                            # التحقق من عدم وجود طالب بنفس الاسم
                            all_students = []
                            for students in CLASSES.values():
                                all_students.extend(students)
                            
                            if student_name in all_students:
                                st.error("❌ هذا الطالب موجود بالفعل!")
                            else:
                                # إضافة الطالب إلى القائمة
                                CLASSES[student_class].append(student_name)
                                student_passwords[student_name] = student_password
                                
                                # تحديث القاموس العكسي
                                STUDENT_TO_CLASS[student_name] = student_class
                                
                                # تحديث المستخدمين
                                USERS[student_name] = {
                                    "password": student_password,
                                    "role": "student",
                                    "student_name": student_name
                                }
                                
                                st.success(f"✅ تمت إضافة الطالب {student_name} إلى {student_class}")
                                st.rerun()
                        else:
                            st.error("❌ من فضلك املأ جميع الحقول")
                
                st.markdown("---")
                st.markdown("#### ❌ حذف طالب")
                
                # حذف طالب
                with st.form(key="delete_student_form"):
                    all_students = []
                    for class_name, students in CLASSES.items():
                        for student in students:
                            all_students.append(f"{student} ({class_name})")
                    
                    student_to_delete = st.selectbox("اختر الطالب للحذف", all_students)
                    
                    delete_button = st.form_submit_button("🗑️ حذف الطالب", use_container_width=True, type="secondary")
                    
                    if delete_button and student_to_delete:
                        # استخراج اسم الطالب من النص
                        student_name = student_to_delete.split(" (")[0]
                        
                        # البحث عن الفصل وإزالة الطالب
                        for class_name, students in CLASSES.items():
                            if student_name in students:
                                CLASSES[class_name].remove(student_name)
                                
                                # حذف من القواميس الأخرى
                                if student_name in STUDENT_TO_CLASS:
                                    del STUDENT_TO_CLASS[student_name]
                                if student_name in student_passwords:
                                    del student_passwords[student_name]
                                if student_name in USERS:
                                    del USERS[student_name]
                                
                                st.success(f"✅ تم حذف الطالب {student_name} من {class_name}")
                                st.rerun()
                                break
        
        with tab3:
            st.markdown("### 🏫 إدارة الفصول")
            
            col1, col2 = st.columns([2, 2])
            
            with col1:
                st.markdown("#### 📊 معلومات الفصول الحالية")
                
                for class_name, students in CLASSES.items():
                    with st.expander(f"📁 {class_name} - {len(students)} طالب"):
                        st.write(f"**المعلم المسؤول:** {', '.join([k for k, v in TEACHER_CLASSES.items() if class_name in v]) or 'غير معين'}")
                        st.write("**الطلاب:**")
                        for student in students:
                            st.write(f"- {student}")
            
            with col2:
                st.markdown("#### ➕ إضافة فصل جديد")
                
                with st.form(key="add_class_form"):
                    new_class_name = st.text_input("اسم الفصل الجديد", placeholder="مثال: Class F")
                    teacher_assigned = st.selectbox("المعلم المسؤول", list(TEACHER_CLASSES.keys()))
                    
                    add_class_button = st.form_submit_button("➕ إضافة الفصل", use_container_width=True)
                    
                    if add_class_button and new_class_name:
                        if new_class_name in CLASSES:
                            st.error("❌ هذا الفصل موجود بالفعل!")
                        else:
                            CLASSES[new_class_name] = []
                            TEACHER_CLASSES[teacher_assigned].append(new_class_name)
                            st.success(f"✅ تمت إضافة الفصل {new_class_name}")
                            st.rerun()
                
                st.markdown("---")
                st.markdown("#### ✏️ تعديل فصل")
                
                with st.form(key="edit_class_form"):
                    class_to_edit = st.selectbox("اختر الفصل", list(CLASSES.keys()))
                    new_class_name = st.text_input("الاسم الجديد (اختياري)", placeholder="اتركه فارغاً إذا لم ترد التغيير")
                    new_teacher = st.selectbox("المعلم الجديد (اختياري)", [""] + list(TEACHER_CLASSES.keys()))
                    
                    edit_class_button = st.form_submit_button("✏️ تعديل الفصل", use_container_width=True)
                    
                    if edit_class_button:
                        if new_class_name and new_class_name != class_to_edit:
                            # تغيير اسم الفصل
                            CLASSES[new_class_name] = CLASSES.pop(class_to_edit)
                            
                            # تحديث القاموس العكسي
                            for student in CLASSES[new_class_name]:
                                STUDENT_TO_CLASS[student] = new_class_name
                            
                            # تحديث TEACHER_CLASSES
                            for teacher, classes in TEACHER_CLASSES.items():
                                if class_to_edit in classes:
                                    classes.remove(class_to_edit)
                                    classes.append(new_class_name)
                            
                            st.success(f"✅ تم تغيير اسم الفصل إلى {new_class_name}")
                        
                        if new_teacher:
                            # تغيير المعلم المسؤول
                            for teacher, classes in TEACHER_CLASSES.items():
                                if class_to_edit in classes:
                                    classes.remove(class_to_edit)
                            TEACHER_CLASSES[new_teacher].append(class_to_edit if not new_class_name else new_class_name)
                            st.success(f"✅ تم تعيين المعلم {new_teacher}")
        
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
                        if st.button("🗑️ حذف البيانات المصفاة", use_container_width=True, type="secondary"):
                            if worksheet:
                                try:
                                    # الحصول على جميع البيانات
                                    all_data = worksheet.get_all_values()
                                    
                                    # البحث عن الصفوف المطابقة
                                    rows_to_delete = []
                                    for i, row in enumerate(all_data[1:], start=2):  # تخطي العنوان
                                        row_data = dict(zip(all_data[0], row))
                                        # التحقق إذا كان الصف مطابق للبيانات المصفاة
                                        match = True
                                        for col in ["student", "teacher", "class", "status", "date"]:
                                            if col in row_data and col in filtered_df.columns:
                                                if str(row_data[col]) != str(filtered_df.iloc[0][col]):
                                                    match = False
                                                    break
                                        if match:
                                            rows_to_delete.append(i)
                                    
                                    # حذف الصفوف بترتيب عكسي
                                    for row_num in sorted(rows_to_delete, reverse=True):
                                        worksheet.delete_rows(row_num)
                                    
                                    st.success(f"✅ تم حذف {len(rows_to_delete)} سجل")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"❌ خطأ في حذف البيانات: {str(e)}")
                            else:
                                st.error("❌ لا يوجد اتصال بـ Google Sheets لحذف البيانات")
                    
                    with col2:
                        # تصدير البيانات المصفاة
                        csv_data = filtered_df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="📥 تصدير البيانات المصفاة (CSV)",
                            data=csv_data,
                            file_name=f"بيانات_الغياب_المصفاة_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                else:
                    st.info("❌ لا توجد بيانات مطابقة للتصفية.")
            else:
                st.info("📭 لا توجد بيانات غياب بعد.")
        
        with tab5:
            st.markdown("### 📤 تصدير البيانات")
            
            # تبويبات داخلية للتصدير
            export_tab1, export_tab2 = st.tabs([
                "📄 تصدير جميع البيانات",
                "⚙️ إعدادات النظام"
            ])
            
            with export_tab1:
                st.markdown("#### 📄 تصدير جميع البيانات")
                st.info("يمكنك تصدير جميع بيانات الغياب إلى ملف CSV")
                
                df_all = read_sheet()
                
                if not df_all.empty:
                    # تحويل التاريخ للتنسيق المناسب
                    df_export = df_all.copy()
                    df_export["date"] = df_export["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
                    
                    csv_data = df_export.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تحميل جميع البيانات (CSV)",
                        data=csv_data,
                        file_name=f"جميع_بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    st.success(f"✅ جاهز للتحميل: {len(df_all)} سجل")
                    st.info("""
                    **محتويات الملف:**
                    1. اسم الطالب
                    2. اسم المعلم
                    3. اسم الفصل
                    4. حالة الحضور
                    5. التاريخ
                    """)
                    
                else:
                    st.info("📭 لا توجد بيانات للتصدير.")
            
            with export_tab2:
                st.markdown("#### ⚙️ إعدادات النظام")
                
                # حالة الاتصال
                st.markdown("##### 🔗 حالة الاتصال")
                st.info(f"حالة الاتصال بـ Google Sheets: **{connection_status}**")
                
                if worksheet:
                    try:
                        # اختبار الاتصال
                        test_data = worksheet.get_all_values()
                        st.success(f"✅ متصل بنجاح - عدد السجلات: {len(test_data)-1 if test_data else 0}")
                    except Exception as e:
                        st.error(f"❌ خطأ في الاتصال: {str(e)}")
                else:
                    st.warning("⚠️ لا يوجد اتصال بـ Google Sheets")
                    st.info("""
                    **لإعداد الاتصال:**
                    1. إنشاء حساب خدمة في Google Cloud Console
                    2. تفعيل Google Sheets API
                    3. إضافة مفاتيح حساب الخدمة إلى Streamlit Secrets
                    4. مشاركة Google Sheet مع حساب الخدمة
                    """)
                
                # إدارة المستخدمين
                st.markdown("##### 🔐 إدارة المستخدمين")
                
                # عرض قائمة المستخدمين
                users_df = pd.DataFrame([
                    {
                        "اسم المستخدم": user,
                        "الدور": data["role"],
                        "الفصول المسؤول" if data["role"] == "teacher" else "الفصل": 
                            ", ".join(data.get("classes", [])) if data.get("classes") else 
                            STUDENT_TO_CLASS.get(data.get("student_name", ""), "")
                    }
                    for user, data in USERS.items()
                ])
                
                st.dataframe(users_df, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.markdown("##### 🛠️ أدوات النظام")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # إعادة تعيين النظام
                    if st.button("🔄 إعادة تعيين النظام", use_container_width=True, type="secondary"):
                        if worksheet:
                            try:
                                worksheet.clear()
                                headers = ["student", "teacher", "class", "status", "date"]
                                worksheet.append_row(headers)
                                st.success("✅ تم إعادة تعيين النظام بنجاح")
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ خطأ في إعادة التعيين: {str(e)}")
                        else:
                            st.error("❌ لا يوجد اتصال بـ Google Sheets")
                
                with col2:
                    # نسخة احتياطية
                    if st.button("💾 إنشاء نسخة احتياطية", use_container_width=True):
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
