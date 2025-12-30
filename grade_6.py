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
# قائمة الطلاب مقسمة على 4 فصول
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
for student in ALL_STUDENTS:
    if student in student_passwords:
        USERS[student] = {
            "password": student_passwords[student],
            "role": "student",
            "student_name": student
        }
    else:
        # إنشاء كلمة مرور عشوائية
        import random
        import string
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
        BOT_TOKEN = getattr(secrets.telegram, 'bot_token', None)
        CHAT_ID = getattr(secrets.telegram, 'chat_id', None)
        
        # App settings
        SHEET_NAME = getattr(secrets.sheets, 'name', 'school_attendance')
        
        # Service Account
        SERVICE_ACCOUNT = None
        
        # الطريقة 1: SERVICE_ACCOUNT_JSON
        if hasattr(secrets, 'SERVICE_ACCOUNT_JSON'):
            try:
                SERVICE_ACCOUNT = json.loads(secrets.SERVICE_ACCOUNT_JSON)
            except Exception as e:
                st.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
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
    # معالجة مشكلة أسماء الفصول بالعربية والإنجليزية
    class_df = pd.DataFrame()
    
    # البحث عن الفصل بأي شكل من الأشكال
    if not df.empty:
        # تحويل جميع أسماء الفصول إلى حروف صغيرة وإزالة المسافات
        df_lower = df.copy()
        df_lower['class_lower'] = df_lower['class'].astype(str).str.strip().str.lower()
        search_class = str(class_name).strip().lower()
        
        # البحث عن التطابقات
        class_matches = df_lower[df_lower['class_lower'] == search_class]
        
        if not class_matches.empty:
            class_df = class_matches.copy()
        else:
            # محاولة البحث الجزئي
            class_df = df[df['class'].astype(str).str.contains(str(class_name).strip(), case=False, na=False)]
    
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
        # البحث عن سجلات الطالب
        student_df = class_df[class_df["student"].astype(str).str.strip() == student.strip()]
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
    # معالجة مشكلة أسماء الفصول بالعربية والإنجليزية
    class_df = pd.DataFrame()
    
    if not df.empty:
        # تحويل جميع أسماء الفصول إلى حروف صغيرة وإزالة المسافات
        df_lower = df.copy()
        df_lower['class_lower'] = df_lower['class'].astype(str).str.strip().str.lower()
        search_class = str(class_name).strip().lower()
        
        # البحث عن التطابقات
        class_matches = df_lower[df_lower['class_lower'] == search_class]
        
        if not class_matches.empty:
            class_df = class_matches.copy()
        else:
            # محاولة البحث الجزئي
            class_df = df[df['class'].astype(str).str.contains(str(class_name).strip(), case=False, na=False)]
    
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
    if not class_df.empty and 'date' in class_df.columns:
        try:
            class_df = class_df.sort_values("date", ascending=False)
        except:
            pass
    
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
    footer_style = ParagraphStyle('Footer', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.darkblue)

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
                reshape_arabic_text(str(row.get("الفصل", ""))),
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
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date}"), footer_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer

# 🆕 **دالة جديدة: توليد تقرير PDF كامل للفصل**
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
    footer_style = ParagraphStyle('Footer', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.darkblue)
    
    # صفحة الغلاف
    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب الشامل"), title_style))
    elements.append(Spacer(1, 20))
    
    elements.append(Spacer(1, 10))
    elements.append(Paragraph(reshape_arabic_text(f"المعلم: {teacher_name}"), normal_style))
    elements.append(Spacer(1, 10))
    
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
        # ✅ **عرض كل السجلات، ليس فقط 50**
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
                reshape_arabic_text(normalize_date_for_pdf(row.get("date_clean", ""))),
                reshape_arabic_text(str(row.get("status_clean", "")))
            ])
        
        # حساب عدد الصفوف في كل صفحة (تقريباً 35 صف في الصفحة)
        rows_per_page = 35
        total_rows = len(history_data) - 1  # ناقص رأس الجدول
        
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
                
                # إضافة رقم الصفحة
                elements.append(Spacer(1, 10))
                elements.append(Paragraph(reshape_arabic_text(f"الصفحة {page_num//rows_per_page + 1} من {((total_rows - 1)//rows_per_page) + 1}"), 
                                         ParagraphStyle('PageNumber', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.gray)))
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
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), footer_style))
    
    doc.build(elements)
    buffer.seek(0)
    return buffer

# 🆕 **وظائف خاصة بمدير النظام**
def get_all_records():
    """الحصول على جميع سجلات الغياب"""
    df = read_sheet()
    if df.empty:
        return pd.DataFrame()
    
    # تنظيف البيانات
    df = df.copy()
    df["date_clean"] = df["date"].apply(lambda x: normalize_date_for_display(x) if pd.notna(x) else "")
    
    # تنظيف الحالة
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        return status_str
    
    df["status_clean"] = df["status"].apply(clean_status)
    
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
    global CLASSES, TEACHER_CLASSES
    
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
        class_stats.append({
            "class": class_name,
            "student_count": len(students),
            "records_count": len(df[df["class"] == class_name]) if not df.empty else 0
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

def generate_admin_report():
    """توليد تقرير PDF كامل للمدير"""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    
    # استخدام الخط المتاح
    font_for_style = "Helvetica"
    if REGISTERED_FONT:
        font_for_style = REGISTERED_FONT
    
    # أنماط النصوص
    title_style = ParagraphStyle('Title', fontName=font_for_style, fontSize=24, alignment=1, textColor=colors.darkblue)
    subtitle_style = ParagraphStyle('Subtitle', fontName=font_for_style, fontSize=18, alignment=1, textColor=colors.navy)
    header_style = ParagraphStyle('Header', fontName=font_for_style, fontSize=14, alignment=2, textColor=colors.black)
    normal_style = ParagraphStyle('Normal', fontName=font_for_style, fontSize=12, alignment=2)
    footer_style = ParagraphStyle('Footer', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.darkblue)
    
    # الحصول على إحصائيات النظام
    stats = get_system_statistics()
    
    # صفحة الغلاف
    elements.append(Paragraph(reshape_arabic_text("تقرير إدارة النظام"), title_style))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text("نظام إدارة الغياب المدرسي"), subtitle_style))
    elements.append(Spacer(1, 20))
    
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ التقرير: {current_date}"), normal_style))
    elements.append(Spacer(1, 30))
    
    elements.append(PageBreak())
    
    # الإحصائيات العامة للنظام
    elements.append(Paragraph(reshape_arabic_text("إحصائيات النظام العامة"), subtitle_style))
    elements.append(Spacer(1, 15))
    
    # جدول الإحصائيات
    stats_data = [
        [reshape_arabic_text("إجمالي السجلات"), reshape_arabic_text(str(stats["total_records"]))],
        [reshape_arabic_text("عدد الطلاب"), reshape_arabic_text(str(stats["total_students"]))],
        [reshape_arabic_text("عدد الفصول"), reshape_arabic_text(str(stats["total_classes"]))],
        [reshape_arabic_text("عدد المعلمين"), reshape_arabic_text(str(stats["total_teachers"]))],
        [reshape_arabic_text("عدد الحضور"), reshape_arabic_text(str(stats["present_count"]))],
        [reshape_arabic_text("عدد الغياب"), reshape_arabic_text(str(stats["absent_count"]))],
        [reshape_arabic_text("نسبة الحضور العامة"), reshape_arabic_text(f"{stats['attendance_rate']:.1f}%")]
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
    
    # إحصائيات الفصول
    elements.append(Paragraph(reshape_arabic_text("إحصائيات الفصول"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    if stats["class_stats"]:
        class_header = [
            reshape_arabic_text("اسم الفصل"),
            reshape_arabic_text("عدد الطلاب"),
            reshape_arabic_text("عدد السجلات")
        ]
        
        class_data = [class_header]
        for class_stat in stats["class_stats"]:
            class_data.append([
                reshape_arabic_text(class_stat["class"]),
                reshape_arabic_text(str(class_stat["student_count"])),
                reshape_arabic_text(str(class_stat["records_count"]))
            ])
        
        class_table = Table(class_data, colWidths=[150, 100, 100])
        class_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), font_for_style),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        elements.append(class_table)
    
    elements.append(PageBreak())
    
    # قائمة جميع الطلاب
    elements.append(Paragraph(reshape_arabic_text("قائمة الطلاب"), subtitle_style))
    elements.append(Spacer(1, 10))
    
    if ALL_STUDENTS:
        # تقسيم الطلاب إلى صفحات
        students_per_page = 40
        total_pages = (len(ALL_STUDENTS) - 1) // students_per_page + 1
        
        for page_num in range(total_pages):
            if page_num > 0:
                elements.append(PageBreak())
                elements.append(Paragraph(reshape_arabic_text(f"قائمة الطلاب - استكمال"), subtitle_style))
                elements.append(Spacer(1, 10))
            
            start_idx = page_num * students_per_page
            end_idx = min((page_num + 1) * students_per_page, len(ALL_STUDENTS))
            page_students = ALL_STUDENTS[start_idx:end_idx]
            
            # إنشاء جدول للطلاب
            student_data = []
            for i, student in enumerate(page_students, start=1):
                student_class = STUDENT_TO_CLASS.get(student, "غير محدد")
                student_data.append([
                    reshape_arabic_text(str(i + start_idx)),
                    reshape_arabic_text(student),
                    reshape_arabic_text(student_class)
                ])
            
            # إضافة رأس الجدول
            student_data.insert(0, [
                reshape_arabic_text("م"),
                reshape_arabic_text("اسم الطالب"),
                reshape_arabic_text("الفصل")
            ])
            
            student_table = Table(student_data, colWidths=[40, 200, 100])
            student_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (-1, -1), font_for_style),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
            ]))
            elements.append(student_table)
            
            # إضافة رقم الصفحة
            elements.append(Spacer(1, 10))
            elements.append(Paragraph(reshape_arabic_text(f"الصفحة {page_num + 1} من {total_pages}"), 
                                     ParagraphStyle('PageNumber', fontName=font_for_style, fontSize=10, alignment=2, textColor=colors.gray)))
    else:
        elements.append(Paragraph(reshape_arabic_text("لا توجد طلاب في النظام."), normal_style))
    
    # الصفحة الأخيرة - التوقيعات
    elements.append(PageBreak())
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("توقيع مدير النظام:"), header_style))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(reshape_arabic_text(f"{st.session_state.get('user_name', 'مدير النظام')}"), normal_style))
    
    elements.append(Spacer(1, 50))
    elements.append(Paragraph(reshape_arabic_text("ختم المدرسة:"), header_style))
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text("________________________"), normal_style))
    
    elements.append(Spacer(1, 30))
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ الطباعة: {current_date}"), footer_style))
    elements.append(Paragraph(reshape_arabic_text(f"آخر تحديث: {stats['last_update']}"), footer_style))
    
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
    }
    .badge-teacher {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    .badge-student {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    .badge-admin {
        background: linear-gradient(135deg, #8b5cf6, #7c3aed);
        color: white;
    }
    .home-page {
        max-width: 1000px;
        margin: 0 auto;
        padding: 20px;
    }
    .admin-page {
        max-width: 1200px;
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
    .admin-title {
        font-size: 36px;
        margin-bottom: 30px;
        color: #7c3aed !important;
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
        background: linear-gradient(135deg, #8b5cf6, #7c3aed);
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
    .admin-welcome {
        text-align: center;
        padding: 25px;
        margin: 20px 0;
        background: linear-gradient(135deg, #f5f3ff, #ede9fe);
        border-radius: 15px;
        border: 3px solid #ddd6fe;
    }
    .welcome-text {
        font-size: 24px;
        color: #0369a1;
        font-weight: 700;
    }
    .admin-welcome-text {
        font-size: 24px;
        color: #7c3aed;
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
    
    /* ===== التعديلات لجعل نص الأزرار أبيض ===== */
    .stButton > button {
        width: 100% !important;
        height: auto !important;
        background: linear-gradient(135deg, #1e40af, #2563eb) !important;
        color: white !important;
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
        color: white !important;
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
    
    /* أزرار المدير - نص أبيض */
    button.admin-button,
    button.admin-button span,
    button.admin-button p,
    button.admin-button div {
        background: linear-gradient(135deg, #8b5cf6, #7c3aed) !important;
        color: white !important;
    }
    
    button.admin-button:hover,
    button.admin-button:hover span,
    button.admin-button:hover p,
    button.admin-button:hover div {
        background: linear-gradient(135deg, #7c3aed, #6d28d9) !important;
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
        background: linear-gradient(135deg, #8b5cf6, #7c3aed);
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
        background: linear-gradient(135deg, #7c3aed, #6d28d9);
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(123, 92, 246, 0.3);
    }
    
    .class-button.active {
        background: linear-gradient(135deg, #10b981, #059669);
        border: 3px solid #059669;
    }
    
    .class-button.disabled {
        background: linear-gradient(135deg, #94a3b8, #64748b);
        cursor: not-allowed;
        opacity: 0.6;
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
    /* تحسين صفحة المعلم */
    .teacher-page {
        max-width: 1000px;
        margin: 0 auto;
        padding: 20px;
    }
    /* تحسين صفحة الطالب */
    .student-page {
        max-width: 1000px;
        margin: 0 auto;
        padding: 20px;
    }
    /* تحسين صفحة المدير */
    .admin-section {
        background: white;
        border-radius: 15px;
        padding: 25px;
        margin-bottom: 25px;
        box-shadow: 0 5px 15px rgba(0,0,0,0.05);
        border: 2px solid #e2e8f0;
    }
    .admin-section h3 {
        color: #7c3aed !important;
        border-bottom: 2px solid #ddd6fe;
        padding-bottom: 10px;
        margin-bottom: 20px;
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
    /* زر تحميل التقرير الكامل */
    .full-report-button {
        background: linear-gradient(135deg, #8b5cf6, #7c3aed) !important;
        color: white !important;
        padding: 15px 30px !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 16px !important;
        border: none !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        margin-top: 20px !important;
    }
    .full-report-button:hover {
        background: linear-gradient(135deg, #7c3aed, #6d28d9) !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 5px 15px rgba(123, 92, 246, 0.3) !important;
    }
    
    /* زر العودة للصفحة الرئيسية في الأسفل */
    .bottom-back-button {
        margin-top: 40px !important;
        margin-bottom: 20px !important;
        background: linear-gradient(135deg, #64748b, #475569) !important;
        color: white !important;
        border: 3px solid rgba(100, 116, 139, 0.2) !important;
    }
    .bottom-back-button:hover {
        background: linear-gradient(135deg, #475569, #334155) !important;
        border-color: #64748b !important;
    }
    
    /* علامات التبويب في صفحة المدير */
    .admin-tabs {
        display: flex;
        justify-content: center;
        gap: 10px;
        margin-bottom: 30px;
        flex-wrap: wrap;
    }
    .admin-tab {
        padding: 12px 25px;
        background: linear-gradient(135deg, #e2e8f0, #cbd5e1);
        color: #475569 !important;
        border: none;
        border-radius: 10px;
        font-size: 16px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        text-align: center;
    }
    .admin-tab:hover {
        background: linear-gradient(135deg, #cbd5e1, #94a3b8);
        transform: translateY(-2px);
    }
    .admin-tab.active {
        background: linear-gradient(135deg, #8b5cf6, #7c3aed);
        color: white !important;
        box-shadow: 0 5px 15px rgba(123, 92, 246, 0.3);
    }
    
    /* تحسين حقول الإدخال في صفحة المدير */
    .admin-input {
        margin-bottom: 15px !important;
    }
    
    .admin-form-section {
        background: #f8fafc;
        padding: 20px;
        border-radius: 10px;
        margin-bottom: 20px;
        border: 2px solid #e2e8f0;
    }
    
    .form-title {
        color: #475569 !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        margin-bottom: 15px !important;
    }
    
    /* تخصيص لرؤية كلمات المرور */
    .password-visible {
        color: #1e40af !important;
        font-weight: 600 !important;
        background: #f0f9ff !important;
        padding: 5px 10px !important;
        border-radius: 5px !important;
        border: 1px solid #bae6fd !important;
    }
</style>
""", unsafe_allow_html=True)

# Top toolbar HTML (يظهر فقط بعد تسجيل الدخول)
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
        
        # حقل إدخال اسم المستخدم
        st.markdown('<div class="input-label">اسم المستخدم</div>', unsafe_allow_html=True)
        username = st.text_input("اسم المستخدم", 
                                placeholder="أدخل اسمك",
                                label_visibility="collapsed")
        
        # حقل إدخال كلمة السر
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
        
# إذا كان المستخدم مسجلاً دخوله، عرض الصفحات الأخرى
elif st.session_state.logged_in:
    show_toolbar()
    
    # الصفحة الرئيسية المشتركة (للمعلم والطالب)
    if st.session_state.page == "home":
        st.markdown('<div class="home-page">', unsafe_allow_html=True)
        
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # 🆕 **الزرارين الجديدين للمعلم في الصفحة الرئيسية**
        if st.session_state.user_role == "teacher":
            # رسالة ترحيب
            welcome_html = f"""
            <div class="welcome-message">
                <div class="welcome-text">مرحباً بك 👨‍🏫 {st.session_state.user_name}</div>
                <div class="user-info">يمكنك اختيار المهمة التي تريد تنفيذها:</div>
            </div>
            """
            st.markdown(welcome_html, unsafe_allow_html=True)
            
            # أزرار المهام الرئيسية
            st.markdown("### 📋 اختر المهمة:")
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
            
            st.markdown("---")
        
        elif st.session_state.user_role == "student":
            # رسالة ترحيب للطالب
            welcome_html = f"""
            <div class="welcome-message">
                <div class="welcome-text">مرحباً بك 👨‍🎓 {st.session_state.user_name}</div>
                <div class="user-info">يمكنك عرض تقرير الغياب الخاص بك:</div>
            </div>
            """
            st.markdown(welcome_html, unsafe_allow_html=True)
            
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", key="student_dashboard_btn", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        # زر تسجيل الخروج للجميع
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
                
                # 🆕 **زر تحميل تقرير الفصل الكامل**
                st.markdown("---")
                st.markdown("### 📥 تحميل تقرير كامل")
                
                # إنشاء تقرير PDF كامل
                try:
                    pdf_buffer = generate_class_full_report(selected_class, teacher_name, stats, history_df)
                    
                    # زر تحميل التقرير
                    st.download_button(
                        label="📄 تحميل تقرير الفصل الكامل (PDF)",
                        data=pdf_buffer,
                        file_name=f"تقرير_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        help="سيحتوي التقرير على: الإحصائيات العامة، إحصائيات الطلاب، سجل الحضور التفصيلي"
                    )
                    
                    # معلومات عن التقرير
                    with st.expander("📋 محتويات التقرير"):
                        st.markdown("""
                        **يحتوي التقرير الكامل على:**
                        1. **صفحة الغلاف**: معلومات الفصل والمعلم
                        2. **الإحصائيات العامة**: 
                           - عدد الطلاب
                           - إجمالي السجلات
                           - عدد الحضور والغياب
                           - نسبة الحضور
                        3. **إحصائيات الطلاب**: 
                           - تفاصيل كل طالب (حضور، غياب، نسبة)
                        4. **سجل الحضور التفصيلي**: 
                           - جميع سجلات الحضور/الغياب
                        5. **صفحة التوقيعات**:
                           - توقيع المعلم
                           - توقيع مدير المدرسة
                        """)
                except Exception as e:
                    st.error(f"❌ حدث خطأ أثناء إنشاء التقرير: {str(e)}")
                
                # 🆕 **تعديل: عرض جميع السجلات في آخر جزء**
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
                    
                    # إظهار عدد السجلات الفعلي
                    st.info(f"**عدد السجلات المعروضة:** {len(all_history)}")
                else:
                    st.info("لا توجد سجلات حضرور لهذا الفصل بعد.")
                    
                    # زر اختبار الاتصال
                    if st.button("🔍 اختبار الاتصال بالسجلات", key="test_records_connection"):
                        df = read_sheet()
                        st.info(f"**إجمالي السجلات في النظام:** {len(df)}")
                        if not df.empty:
                            st.dataframe(df.head(10), use_container_width=True)
        
        # 🆕 **زر العودة للصفحة الرئيسية في الأسفل فقط**
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
            
            # زر تحميل PDF
            pdf_buf = generate_student_pdf(student_name, df_student)
            st.download_button(
                "📥 تحميل تقرير PDF",
                data=pdf_buf,
                file_name=f"تقرير_غياب_{student_name}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        
        # 🆕 **زر العودة للصفحة الرئيسية في الأسفل**
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", key="back_to_home_from_student_bottom", use_container_width=True, type="secondary"):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)
    
    # 🆕 صفحة مدير النظام
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
        tabs = ["dashboard", "students", "teachers", "classes", "reports", "settings"]
        tab_names = {
            "dashboard": "📊 لوحة التحكم",
            "students": "👥 إدارة الطلاب",
            "teachers": "👨‍🏫 إدارة المعلمين",
            "classes": "🏫 إدارة الفصول",
            "reports": "📋 التقارير",
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
                    new_student_password = st.text_input("كلمة المرور *", type="password", key="new_student_password",
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
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_student", use_container_width=True, type="secondary"):
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
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_teacher", use_container_width=True, type="secondary"):
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
                            if st.button("🗑️ تأكيد الحذف", key="confirm_delete_class", use_container_width=True, type="secondary"):
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
        
        elif st.session_state.admin_tab == "reports":
            st.markdown('<div class="admin-section">', unsafe_allow_html=True)
            st.markdown("### 📋 التقارير")
            
            # تقرير النظام الكامل
            st.markdown("#### 📄 تقرير النظام الكامل")
            st.markdown("قم بتحميل تقرير PDF شامل يحتوي على:")
            st.markdown("""
            1. إحصائيات النظام العامة
            2. قائمة الفصول وعدد طلابها
            3. قائمة جميع الطلاب
            4. توقيعات وإجراءات النظام
            """)
            
            # زر تحميل التقرير
            try:
                admin_report_buffer = generate_admin_report()
                
                st.download_button(
                    label="📥 تحميل تقرير النظام الكامل (PDF)",
                    data=admin_report_buffer,
                    file_name=f"تقرير_النظام_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception as e:
                st.error(f"❌ حدث خطأ أثناء إنشاء التقرير: {str(e)}")
            
            st.markdown("---")
            
            # تقارير الفصول (باللغة الإنجليزية للفصول)
            st.markdown("#### 🏫 تقارير الفصول (Class Reports)")
            st.markdown("قم بتحميل تقارير PDF لكل فصل على حدة. **يرجى كتابة اسم الفصل بالإنجليزية:**")
            
            # زر لإظهار أسماء الفصول الإنجليزية
            with st.expander("🔤 أسماء الفصول بالإنجليزية"):
                st.markdown("""
                **قائمة أسماء الفصول بالإنجليزية:**
                - Class B
                - Class C  
                - Class D
                - Class E
                
                **ملاحظة:** يرجى كتابة اسم الفصل بالإنجليزية كما هو موضح أعلاه.
                """)
            
            # إدخال اسم الفصل بالإنجليزية
            report_class_name = st.text_input("اكتب اسم الفصل (بالإنجليزية)", 
                                            placeholder="مثال: Class B",
                                            key="report_class_name_input")
            
            if report_class_name.strip():
                selected_report_class = report_class_name.strip()
                
                # التحقق من أن اسم الفصل موجود
                if selected_report_class not in CLASSES:
                    st.warning(f"⚠️ الفصل '{selected_report_class}' غير موجود في النظام.")
                    st.info("**الفصول المتاحة:** " + ", ".join(CLASSES.keys()))
                else:
                    # الحصول على إحصائيات الفصل
                    stats = get_class_statistics(selected_report_class)
                    history_df = get_class_attendance_history(selected_report_class)
                    
                    # عرض معلومات سريعة عن الفصل
                    st.info(f"**الفصل:** {selected_report_class}")
                    st.info(f"**عدد الطلاب:** {len(CLASSES.get(selected_report_class, []))}")
                    st.info(f"**عدد السجلات:** {stats['total_records']}")
                    
                    # اسم المعلم (افتراضي أو من البيانات)
                    teacher_name = "المعلم"
                    if not history_df.empty and "teacher" in history_df.columns:
                        teachers = history_df["teacher"].unique()
                        if len(teachers) > 0:
                            teacher_name = teachers[0]
                    
                    try:
                        class_report_buffer = generate_class_full_report(selected_report_class, teacher_name, stats, history_df)
                        
                        st.download_button(
                            label=f"📥 تحميل تقرير {selected_report_class}",
                            data=class_report_buffer,
                            file_name=f"تقرير_{selected_report_class}_{datetime.now().strftime('%Y%m%d')}.pdf",
                            mime="application/pdf",
                            use_container_width=True
                        )
                    except Exception as e:
                        st.error(f"❌ حدث خطأ أثناء إنشاء التقرير: {str(e)}")
            
            st.markdown("---")
            
            # تصدير البيانات
            st.markdown("#### 📊 تصدير البيانات")
            st.markdown("تصدير جميع بيانات الغياب بتنسيق CSV (بدلاً من Excel لتجنب المشاكل):")
            
            all_records = get_all_records()
            if not all_records.empty:
                # تحويل إلى CSV
                csv_data = all_records.to_csv(index=False).encode('utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير جميع البيانات (CSV)",
                    data=csv_data,
                    file_name=f"بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            else:
                st.info("لا توجد بيانات للتصدير.")
            
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
            
            # إدارة المستخدمين مع عرض كلمات المرور
            st.markdown("#### 👥 إدارة المستخدمين")
            
            user_types = {
                "admin": "👑 مدير النظام",
                "teacher": "👨‍🏫 معلم",
                "student": "👨‍🎓 طالب"
            }
            
            # إنشاء DataFrame للمستخدمين مع كلمات المرور الظاهرة
            users_data = []
            for username, user_info in USERS.items():
                users_data.append({
                    "اسم المستخدم": username,
                    "الدور": user_types.get(user_info.get("role", "unknown"), "غير معروف"),
                    "كلمة المرور": user_info.get("password", "غير معروفة")
                })
            
            users_df = pd.DataFrame(users_data)
            
            # استخدام CSS لجعل كلمات المرور بارزة
            st.markdown("""
            <style>
            .password-cell {
                background-color: #f0f9ff !important;
                color: #1e40af !important;
                font-weight: 600 !important;
                border: 1px solid #bae6fd !important;
            }
            </style>
            """, unsafe_allow_html=True)
            
            # عرض جدول المستخدمين
            st.dataframe(users_df, use_container_width=True, hide_index=True)
            
            # زر تصدير بيانات المستخدمين
            if not users_df.empty:
                csv_users = users_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 تحميل بيانات المستخدمين",
                    data=csv_users,
                    file_name=f"بيانات_المستخدمين_{datetime.now().strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            st.markdown('</div>', unsafe_allow_html=True)
        
        # زر العودة والتحكم
        st.markdown("---")
        col_a, col_b = st.columns(2)
        
        with col_a:
            if st.button("🏠 العودة للصفحة الرئيسية", key="admin_back_to_home", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        
        with col_b:
            if st.button("🚪 تسجيل الخروج", key="admin_logout", use_container_width=True, type="secondary"):
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
