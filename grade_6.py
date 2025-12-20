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

# Arabic/RTL PDF support
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
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
    # فصل C
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
    
    # فصل B
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
    
    # فصل D
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
    
    # فصل E
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
                connection_status = "✅ متصل"
                
                # إذا كانت الورقة جديدة، أضف العناوين
                if not current_data:
                    headers = ["student", "teacher", "class", "status", "date"]
                    worksheet.append_row(headers)
                
            except Exception as e:
                connection_status = f"✅ متصل ولكن خطأ في القراءة"
                
        except gspread.exceptions.SpreadsheetNotFound:
            connection_status = f"❌ لم يتم العثور على Sheet"
        except Exception as e:
            connection_status = f"❌ خطأ في فتح الـ Sheet"
            
    except Exception as e:
        connection_status = f"❌ فشل في المصادقة"
else:
    connection_status = "❌ إعدادات الاتصال غير كاملة"

# ------------------ باقي الكود ------------------
# Fonts for PDF (Arabic only)
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
        else:
            return None
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
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    try:
        data = worksheet.get_all_records()
    except Exception:
        return pd.DataFrame(columns=["student", "teacher", "class", "status", "date"])
    
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "class", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    return df

def write_sheet(df):
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
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append((f"الفصل {class_name}", str(ex)))
    elif rows:  # إذا كان هناك صفوف ولكن لا يوجد اتصال
        failed.append((f"الفصل {class_name}", "لا يوجد اتصال بـ Google Sheets"))
    
    # رسالة تلغرام بدون جملة "تم حفظ X سجل بنجاح"
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
            else:
                telegram_status = "❌ فشل الإرسال"
                telegram_details = f"تفاصيل الخطأ: {info}"
        else:
            telegram_status = "⚠️ إعدادات Telegram غير مكتملة"
    else:
        telegram_status = "لم يتم الإرسال (لا يوجد طلاب)"
        telegram_details = "لم يتم إرسال رسالة لأن لا يوجد طلاب في الفصل"
    
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

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # استخدام الخط المتاح
    font_for_style = "Helvetica"
    if REGISTERED_FONT:
        font_for_style = REGISTERED_FONT
    
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    
    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), title_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), normal_style))
    elements.append(Spacer(1, 8))

    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        # حساب الغياب بغض النظر عن نوعه (بعذر أو بدون عذر)
        absent_count = int((df_records["الحالة"] == "غياب").sum())
        present_count = int((df_records["الحالة"] == "حاضر").sum())
        total_count = len(df_records)
        
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"إجمالي عدد السجلات: {total_count}"), normal_style))
        
        if total_count > 0:
            attendance_rate = (present_count / total_count) * 100
            elements.append(Paragraph(reshape_arabic_text(f"نسبة الحضور: {attendance_rate:.1f}%"), normal_style))
        
        elements.append(Spacer(1, 10))

        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            data.append([
                reshape_arabic_text(str(row.get("المرة", ""))),
                reshape_arabic_text(str(row.get("الطالب", ""))),
                reshape_arabic_text(str(row.get("المعلم", ""))),
                str(row.get("الفصل", "")),  # اسم الفصل فقط (مثال: Class B)
                reshape_arabic_text(normalize_date_for_pdf(row.get("التاريخ", ""))),
                reshape_arabic_text(str(row.get("الحالة", "")))
            ])
        table = Table(data, hAlign='CENTER', colWidths=[50, 130, 100, 80, 100, 70])
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
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date}"), normal_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def generate_class_full_report(class_name, teacher_name, stats, history_df):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # استخدام الخط المتاح
    font_for_style = "Helvetica"
    if REGISTERED_FONT:
        font_for_style = REGISTERED_FONT
    
    # أنماط النصوص
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=22, alignment=1, textColor=colors.darkblue)
    subtitle_style = ParagraphStyle('Subtitle', fontName=font_for_style, fontSize=16, alignment=1, textColor=colors.navy)
    header_style = ParagraphStyle('Header', fontName=font_for_style, fontSize=14, alignment=2, textColor=colors.black)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    
    # صفحة الغلاف
    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب الشامل"), title_style))
    elements.append(Spacer(1, 20))
    
    # معلومات المعلم والصف فقط
    elements.append(Paragraph(reshape_arabic_text(f"المعلم: {teacher_name}"), normal_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text(f"{class_name}"), normal_style))  # فقط اسم الصف
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ التقرير: {current_date}"), normal_style))
    elements.append(Spacer(1, 20))
    
    # الإحصائيات العامة
    elements.append(Paragraph(reshape_arabic_text("الإحصائيات العامة"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    # جدول الإحصائيات
    stats_data = [
        [reshape_arabic_text("عدد الطلاب"), reshape_arabic_text(str(stats["total_students"]))],
        [reshape_arabic_text("إجمالي السجلات"), reshape_arabic_text(str(stats["total_records"]))],
        [reshape_arabic_text("عدد الحضور"), reshape_arabic_text(str(stats["present_count"]))],
        [reshape_arabic_text("عدد الغياب"), reshape_arabic_text(str(stats["absent_count"]))],
        [reshape_arabic_text("نسبة الحضور"), reshape_arabic_text(f"{stats['attendance_rate']:.1f}%")]
    ]
    
    stats_table = Table(stats_data, colWidths=[150, 100])
    stats_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_for_style),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    elements.append(stats_table)
    
    elements.append(PageBreak())
    
    # إحصائيات الطلاب
    elements.append(Paragraph(reshape_arabic_text("إحصائيات الطلاب"), subtitle_style))
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
                reshape_arabic_text(str(student["total"])),
                reshape_arabic_text(str(student["present"])),
                reshape_arabic_text(str(student["absent"])),
                reshape_arabic_text(f"{student['rate']:.1f}%")
            ])
        
        student_table = Table(student_data, colWidths=[150, 70, 60, 60, 80])
        student_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),  # حجم خط أكبر للرأس
        ]))
        elements.append(student_table)
    
    elements.append(PageBreak())
    
    # سجل الحضور
    elements.append(Paragraph(reshape_arabic_text("سجل الحضور التفصيلي"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    if not history_df.empty:
        history_display = history_df.copy()  # عرض كل السجلات
        
        history_header = [
            reshape_arabic_text("الطالب"),
            reshape_arabic_text("المعلم"),
            reshape_arabic_text("التاريخ"),
            reshape_arabic_text("الحالة")
        ]
        
        history_data = [history_header]
        for _, row in history_display.iterrows():
            history_data.append([
                reshape_arabic_text(str(row.get("student", ""))),
                reshape_arabic_text(str(row.get("teacher", ""))),
                reshape_arabic_text(str(row.get("date_clean", ""))),
                reshape_arabic_text(str(row.get("status_clean", "")))
            ])
        
        # حساب عدد الصفوف في كل صفحة
        rows_per_page = 35
        total_rows = len(history_data) - 1
        
        if total_rows > rows_per_page:
            # تقسيم الجدول إلى صفحات متعددة
            for page_num in range(0, total_rows, rows_per_page):
                if page_num > 0:
                    elements.append(PageBreak())
                    elements.append(Paragraph(reshape_arabic_text(f"سجل الحضور التفصيلي - استكمال"), subtitle_style))
                    elements.append(Spacer(1, 10))
                
                end_idx = min(page_num + rows_per_page, total_rows)
                page_data = [history_header] + history_data[page_num + 1:end_idx + 1]
                
                history_table = Table(page_data, colWidths=[150, 100, 100, 80])
                history_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (-1, -1), font_for_style),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                    ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                    ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ]))
                elements.append(history_table)
        else:
            # إذا كان الجدول صغيراً يكفي لصفحة واحدة
            history_table = Table(history_data, colWidths=[150, 100, 100, 80])
            history_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_for_style),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
            ]))
            elements.append(history_table)
    else:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات حضرور لهذا الفصل بعد."), normal_style))
    
    # الصفحة الأخيرة - التوقيعات
    elements.append(PageBreak())
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("توقيع المعلم:"), header_style))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text(f"{teacher_name}"), normal_style))
    
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("توقيع مدير المدرسة:"), header_style))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("مدير مدرسة السلام الإعدادية الثانويه المشتركه"), normal_style))
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), normal_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# 🆕 **دالة جديدة: إنشاء تقرير PDF شامل للنظام**
def generate_system_report_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # استخدام الخط المتاح
    font_for_style = "Helvetica"
    if REGISTERED_FONT:
        font_for_style = REGISTERED_FONT
    
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=22, alignment=1, textColor=colors.darkblue)
    subtitle_style = ParagraphStyle('Subtitle', fontName=font_for_style, fontSize=16, alignment=2, textColor=colors.navy)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    
    # صفحة الغلاف
    elements.append(Paragraph(reshape_arabic_text("تقرير شامل لنظام الغياب"), title_style))
    elements.append(Spacer(1, 20))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ التقرير: {current_date}"), normal_style))
    elements.append(Spacer(1, 20))
    
    # الإحصائيات العامة
    elements.append(Paragraph(reshape_arabic_text("الإحصائيات العامة للنظام"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    df_all = read_sheet()
    total_records = len(df_all) if not df_all.empty else 0
    
    # جدول الإحصائيات العامة
    stats_data = [
        [reshape_arabic_text("عدد الطلاب"), reshape_arabic_text(str(len(ALL_STUDENTS)))],
        [reshape_arabic_text("عدد الفصول"), reshape_arabic_text(str(len(CLASSES)))],
        [reshape_arabic_text("عدد المعلمين"), reshape_arabic_text(str(len(TEACHER_CLASSES)))],
        [reshape_arabic_text("إجمالي سجلات الغياب"), reshape_arabic_text(str(total_records))]
    ]
    
    stats_table = Table(stats_data, colWidths=[150, 100])
    stats_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_for_style),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    elements.append(stats_table)
    
    elements.append(PageBreak())
    
    # تفاصيل الفصول
    elements.append(Paragraph(reshape_arabic_text("تفاصيل الفصول"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    for class_name, students in CLASSES.items():
        # إحصائيات الفصل
        stats = get_class_statistics(class_name)
        
        # معلومات الفصل - فقط اسم الصف بدون كلمة "الفصل"
        elements.append(Paragraph(reshape_arabic_text(f"{class_name}"), normal_style))
        elements.append(Spacer(1, 5))
        
        # جدول إحصائيات الفصل
        class_stats_data = [
            [reshape_arabic_text("عدد الطلاب"), reshape_arabic_text(str(len(students)))],
            [reshape_arabic_text("عدد السجلات"), reshape_arabic_text(str(stats["total_records"]))],
            [reshape_arabic_text("نسبة الحضور"), reshape_arabic_text(f"{stats['attendance_rate']:.1f}%")],
            [reshape_arabic_text("المعلم المسؤول"), reshape_arabic_text(', '.join([k for k, v in TEACHER_CLASSES.items() if class_name in v]) or 'غير معين')]
        ]
        
        class_stats_table = Table(class_stats_data, colWidths=[100, 80])
        class_stats_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        elements.append(class_stats_table)
        
        elements.append(Spacer(1, 10))
    
    elements.append(PageBreak())
    
    # معلومات المعلمين
    elements.append(Paragraph(reshape_arabic_text("معلومات المعلمين"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    for teacher, classes in TEACHER_CLASSES.items():
        elements.append(Paragraph(reshape_arabic_text(f"المعلم: {teacher}"), normal_style))
        elements.append(Spacer(1, 5))
        
        # اسم الفصول فقط (بدون كلمة "الفصول")
        elements.append(Paragraph(reshape_arabic_text(f"{', '.join(classes)}"), normal_style))
        
        elements.append(Spacer(1, 10))
    
    # الصفحة الأخيرة
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("ملاحظات:"), subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("• هذا التقرير تم إنشاؤه تلقائياً من نظام الغياب الإلكتروني."), normal_style))
    elements.append(Paragraph(reshape_arabic_text("• البيانات محدثة حتى تاريخ إنشاء التقرير."), normal_style))
    elements.append(Paragraph(reshape_arabic_text("• يمكن للمدير الوصول إلى البيانات التفصيلية من لوحة التحكم."), normal_style))
    
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("توقيع مدير النظام:"), subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), normal_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# 🆕 **دالة جديدة: إنشاء تقرير PDF للمعلمين**
def generate_teachers_report_pdf():
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # استخدام الخط المتاح
    font_for_style = "Helvetica"
    if REGISTERED_FONT:
        font_for_style = REGISTERED_FONT
    
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=22, alignment=1, textColor=colors.darkblue)
    subtitle_style = ParagraphStyle('Subtitle', fontName=font_for_style, fontSize=16, alignment=2, textColor=colors.navy)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    
    # صفحة الغلاف
    elements.append(Paragraph(reshape_arabic_text("تقرير المعلمين"), title_style))
    elements.append(Spacer(1, 20))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ التقرير: {current_date}"), normal_style))
    elements.append(Spacer(1, 20))
    
    # معلومات المعلمين
    for teacher, classes in TEACHER_CLASSES.items():
        elements.append(Paragraph(reshape_arabic_text(f"👨‍🏫 المعلم: {teacher}"), subtitle_style))
        elements.append(Spacer(1, 10))
        
        # اسم الفصول فقط
        elements.append(Paragraph(reshape_arabic_text(f"{', '.join(classes)}"), normal_style))
        
        # عرض الفصول التي يدرسها المعلم
        for class_name in classes:
            # الحصول على إحصائيات الفصل
            stats = get_class_statistics(class_name)
            class_students = CLASSES.get(class_name, [])
            
            # معلومات الفصل
            elements.append(Paragraph(reshape_arabic_text(f"📚 {class_name}"), normal_style))
            
            # جدول إحصائيات الفصل
            class_stats_data = [
                [reshape_arabic_text("عدد الطلاب"), reshape_arabic_text(str(len(class_students)))],
                [reshape_arabic_text("عدد السجلات"), reshape_arabic_text(str(stats["total_records"]))],
                [reshape_arabic_text("الحضور"), reshape_arabic_text(str(stats["present_count"]))],
                [reshape_arabic_text("الغياب"), reshape_arabic_text(str(stats["absent_count"]))],
                [reshape_arabic_text("نسبة الحضور"), reshape_arabic_text(f"{stats['attendance_rate']:.1f}%")]
            ]
            
            class_stats_table = Table(class_stats_data, colWidths=[80, 70])
            class_stats_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_for_style),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.lightgrey),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightblue),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
            ]))
            elements.append(class_stats_table)
            
            elements.append(Spacer(1, 10))
        
        # فصل بين المعلمين
        elements.append(Spacer(1, 15))
        elements.append(Paragraph(reshape_arabic_text("________________________________________"), normal_style))
        elements.append(Spacer(1, 15))
    
    # إحصائيات عامة
    elements.append(PageBreak())
    elements.append(Paragraph(reshape_arabic_text("إحصائيات عامة"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    # حساب إجماليات
    total_teachers = len(TEACHER_CLASSES)
    total_classes = len(CLASSES)
    total_students = len(ALL_STUDENTS)
    
    total_stats_data = [
        [reshape_arabic_text("إجمالي عدد المعلمين"), reshape_arabic_text(str(total_teachers))],
        [reshape_arabic_text("إجمالي عدد الفصول"), reshape_arabic_text(str(total_classes))],
        [reshape_arabic_text("إجمالي عدد الطلاب"), reshape_arabic_text(str(total_students))]
    ]
    
    total_stats_table = Table(total_stats_data, colWidths=[120, 80])
    total_stats_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), font_for_style),
        ('FONTSIZE', (0, 0), (-1, -1), 13),
        ('GRID', (0, 0), (-1, -1), 1, colors.gray),
        ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
    ]))
    elements.append(total_stats_table)
    
    # الصفحة الأخيرة
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("ملاحظات:"), subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("• هذا التقرير يوضح أداء المعلمين والفصول المسؤولين عنها."), normal_style))
    elements.append(Paragraph(reshape_arabic_text("• النسب تعتمد على البيانات المسجلة في النظام حتى تاريخ التقرير."), normal_style))
    elements.append(Paragraph(reshape_arabic_text("• يمكن تحديث البيانات من خلال لوحة تحكم المدير."), normal_style))
    
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("توقيع مدير النظام:"), subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), normal_style))
    
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
        color: white !important;
    }
    .badge-admin {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white !important;
    }
    .badge-teacher {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white !important;
    }
    .badge-student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white !important;
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
    /* جميع أزرار Streamlit الأساسية - أبيض */
    .stButton > button {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
        border: none !important;
        border-radius: 12px !important;
        font-weight: 600 !important;
    }
    
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* زر تسجيل الدخول - أبيض */
    button[kind="primary"] {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
    }
    
    button[kind="primary"]:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* زر تسجيل الغياب - أبيض */
    button.attendance-button {
        background: linear-gradient(135deg, #10b981, #059669) !important;
        color: white !important;
    }
    
    button.attendance-button:hover {
        background: linear-gradient(135deg, #059669, #047857) !important;
        color: white !important;
    }
    
    /* أزرار العودة - أبيض */
    button.back-button {
        background: linear-gradient(135deg, #64748b, #475569) !important;
        color: white !important;
    }
    
    button.back-button:hover {
        background: linear-gradient(135deg, #475569, #334155) !important;
        color: white !important;
    }
    
    /* زر تسجيل الخروج - أبيض */
    button.logout-button {
        background: linear-gradient(135deg, #ef4444, #dc2626) !important;
        color: white !important;
    }
    
    button.logout-button:hover {
        background: linear-gradient(135deg, #dc2626, #b91c1c) !important;
        color: white !important;
    }
    
    /* أزرار التنزيل - أبيض */
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
    }
    
    div[data-testid="stDownloadButton"] button:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8) !important;
        color: white !important;
    }
    
    /* أزرار الفصول - أبيض */
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
        color: #1e40af !important;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2563eb !important;
        color: white !important;
        border-color: #2563eb !important;
    }
    /* تحسين ألوان النصوص */
    span, div, p, h1, h2, h3, h4, h5, h6 {
        color: #1e293b !important;
    }
    /* تحسين الـ metric */
    [data-testid="stMetricValue"], [data-testid="stMetricLabel"] {
        color: #1e293b !important;
    }
    /* إصلاح الأزرار داخل النماذج */
    .stForm button {
        color: white !important;
    }
    /* إصلاح نص الأزرار داخل التنزيل */
    .stDownloadButton button {
        color: white !important;
    }
    /* تحسين لون النصوص داخل الرسائل */
    .stAlert [data-testid="stMarkdownContainer"] {
        color: inherit !important;
    }
    
    /* جميع أزرار Streamlit في جميع الصفحات - أبيض */
    .stButton button, button {
        color: white !important;
    }
    
    /* أزرار متعددة الاستخدامات */
    .primary-button, .secondary-button, .success-button, .danger-button {
        color: white !important;
    }
    
    /* أزرار داخل النماذج */
    .stForm button, .stForm .stButton button {
        color: white !important;
    }
    
    /* أزرار اختيار الفصول */
    button[kind="secondary"] {
        color: white !important;
    }
    
    /* أزرار العودة */
    .stButton button[kind="secondary"] {
        color: white !important;
    }
    
    /* أزرار التبويبات */
    .stTabs button {
        color: white !important;
    }
    
    /* أزرار متعددة الاستخدامات */
    div.stButton > button, div[data-testid="stButton"] button {
        color: white !important;
    }
    
    /* أزرار داخل الحاويات */
    .stButton > button > div > p, .stButton > button > div {
        color: white !important;
    }
    
    /* أزرار كبيرة */
    button[data-testid="baseButton-primary"] {
        color: white !important;
    }
    
    button[data-testid="baseButton-secondary"] {
        color: white !important;
    }
    
    /* جميع الأزرار في النظام */
    .stButton > button span, button span, .stButton > button div, button div {
        color: white !important;
    }
    
    /* أزرار خاصة */
    .stButton > button > div > div {
        color: white !important;
    }
    
    /* إصلاح جميع حالات النصوص داخل الأزرار */
    button *, .stButton > button * {
        color: white !important;
    }
    
    /* تنسيق إضافي لضمان ظهور النص أبيض */
    .stButton > button {
        color: white !important;
        text-shadow: 0 1px 1px rgba(0, 0, 0, 0.2);
    }
    
    /* أزرار داخل الجداول */
    td .stButton > button {
        color: white !important;
    }
    
    /* أزرار داخل المودال */
    .modal button, .modal .stButton > button {
        color: white !important;
    }
    
    /* إضافة تظليل للنصوص للمساعدة في الرؤية */
    .stButton > button span, button span {
        text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
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
            <div class="welcome-text">مرحباً بك {st.session_state.user_name} {role_badge}</div>
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
                if st.button("📤 تصدير التقارير", key="admin_reports", use_container_width=True):
                    st.session_state.page = "admin_reports"
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
            
            # زر تحميل PDF (بدون زر إنشاء منفصل)
            pdf_buf = generate_student_pdf(student_name, df_student)
            st.download_button(
                "📥 تحميل تقرير PDF",
                data=pdf_buf,
                file_name=f"تقرير_غياب_{student_name}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        # زر العودة للصفحة الرئيسية في الأسفل
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student_bottom", use_container_width=True, type="secondary"):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة مدير النظام - تصدير التقارير
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_reports":
        st.markdown('<div class="admin-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">📤 تصدير التقارير</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_reports", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### 📄 تقرير شامل للنظام")
            st.info("يمكنك تحميل تقرير PDF شامل يحتوي على جميع إحصائيات النظام")
            
            # إنشاء تقرير شامل
            try:
                pdf_buffer = generate_system_report_pdf()
                
                # زر تحميل التقرير
                st.download_button(
                    label="📥 تحميل التقرير الشامل (PDF)",
                    data=pdf_buffer,
                    file_name=f"تقرير_شامل_النظام_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.success("✅ جاهز للتحميل")
                st.info("""
                **محتويات التقرير الشامل:**
                1. الإحصائيات العامة للنظام
                2. تفاصيل جميع الفصول
                3. معلومات المعلمين والفصول المسؤولين عنها
                4. توقيع مدير النظام
                """)
                
            except Exception as e:
                st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
        
        with col2:
            st.markdown("### 👨‍🏫 تقرير المعلمين")
            st.info("تقرير خاص بأداء المعلمين والفصول المسؤولين عنها")
            
            try:
                pdf_buffer = generate_teachers_report_pdf()
                
                # زر تحميل التقرير
                st.download_button(
                    label="📥 تحميل تقرير المعلمين (PDF)",
                    data=pdf_buffer,
                    file_name=f"تقرير_المعلمين_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
                st.success("✅ جاهز للتحميل")
                st.info("""
                **محتويات تقرير المعلمين:**
                1. معلومات كل معلم والفصول المسؤول عنها
                2. إحصائيات كل فصل (طلاب، سجلات، نسبة حضور)
                3. إحصائيات عامة عن جميع المعلمين
                4. ملاحظات وتوقيع مدير النظام
                """)
                
            except Exception as e:
                st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
        
        st.markdown("---")
        
        # تقارير الفصول
        st.markdown("### 🏫 تقارير الفصول")
        
        # اختيار الفصل
        selected_class = st.selectbox("اختر الفصل", list(CLASSES.keys()))
        
        if selected_class:
            teacher_name = None
            for teacher, classes in TEACHER_CLASSES.items():
                if selected_class in classes:
                    teacher_name = teacher
                    break
            
            if teacher_name:
                # الحصول على إحصائيات الفصل
                stats = get_class_statistics(selected_class)
                history_df = get_class_attendance_history(selected_class)
                
                # إنشاء تقرير الفصل
                try:
                    pdf_buffer = generate_class_full_report(selected_class, teacher_name, stats, history_df)
                    
                    # زر تحميل التقرير
                    st.download_button(
                        label=f"📥 تحميل تقرير {selected_class} (PDF)",
                        data=pdf_buffer,
                        file_name=f"تقرير_{selected_class}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True
                    )
                    
                    st.success("✅ جاهز للتحميل")
                    st.info(f"""
                    **محتويات تقرير {selected_class}:**
                    1. الإحصائيات العامة للفصل
                    2. إحصائيات كل طالب
                    3. سجل الحضور التفصيلي
                    4. توقيعات المعلم ومدير المدرسة
                    """)
                    
                except Exception as e:
                    st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
            else:
                st.warning(f"⚠️ لا يوجد معلم مسؤول عن {selected_class}")
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # صفحة مدير النظام - لوحة التحكم
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown('<div class="admin-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">👑 لوحة تحكم مدير النظام</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_admin", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات لوحة التحكم
        tab1, tab2, tab3 = st.tabs([
            "📊 نظرة عامة",
            "👥 إدارة الطلاب",
            "🏫 إدارة الفصول"
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
        
        st.markdown('</div>', unsafe_allow_html=True)

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
