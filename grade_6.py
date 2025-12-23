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
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.fonts import addMapping

# Google Sheets / Auth
import gspread
from google.oauth2.service_account import Credentials

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
        
        # Service Account
        SERVICE_ACCOUNT = None
        
        if hasattr(secrets, 'SERVICE_ACCOUNT_JSON'):
            try:
                SERVICE_ACCOUNT = json.loads(secrets.SERVICE_ACCOUNT_JSON)
            except Exception as e:
                st.error(f"❌ خطأ في تحميل SERVICE_ACCOUNT_JSON: {e}")
        
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

# ------------------ إعداد الخطوط لـ PDF ------------------
def setup_pdf_fonts():
    """إعداد الخطوط لملفات PDF"""
    try:
        # تسجيل الخط الإنجليزي (Helvetica) بشكل افتراضي
        try:
            pdfmetrics.registerFont(TTFont('EnglishFont', 'Helvetica'))
        except:
            pass
        
        # محاولة تحميل خط عربي
        arabic_font_loaded = False
        
        # قائمة بمسارات الخطوط العربية المحتملة
        arabic_font_paths = [
            "NotoNaskhArabic-Regular.ttf",
            "arial.ttf",
            "tahoma.ttf",
            "dejavu-sans.ttf"
        ]
        
        for font_path in arabic_font_paths:
            try:
                if os.path.exists(font_path):
                    pdfmetrics.registerFont(TTFont('ArabicFont', font_path))
                    arabic_font_loaded = True
                    break
            except Exception as e:
                continue
        
        # إذا لم يتم تحميل خط عربي، استخدم الخط الإنجليزي للنصوص العربية
        if not arabic_font_loaded:
            pdfmetrics.registerFont(TTFont('ArabicFont', 'Helvetica'))
        
        return arabic_font_loaded
        
    except Exception as e:
        print(f"خطأ في إعداد الخطوط: {e}")
        return False

# إعداد الخطوط
setup_pdf_fonts()

# Helper functions
def reshape_arabic_text(text):
    """تكوين النص العربي للعرض الصحيح"""
    try:
        text_str = str(text)
        # إذا كان النص إنجليزي فقط، لا تقم بتكوينه
        if all(ord(char) < 128 for char in text_str):
            return text_str
        
        # تكوين النص العربي
        try:
            reshaped = arabic_reshaper.reshape(text_str)
            bidi_text = get_display(reshaped)
            return bidi_text
        except:
            return text_str
    except Exception as e:
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
    
    return failed, success_count

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
    
    # تنظيف الحالة - جعل "غياب بعذر" تظهر كـ "غياب"
    def clean_status(status):
        if pd.isna(status):
            return ""
        status_str = str(status).strip()
        if "غياب" in status_str:
            return "غياب"
        return status_str
    
    df_matches["status_clean"] = df_matches["status"].apply(clean_status)
    
    # إعادة ترتيب الصفوف
    df_matches = df_matches.sort_values("date", ascending=False)
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    
    # إعادة تسمية الأعمدة
    df_matches = df_matches.rename(columns={
        "student": "الطالب", 
        "teacher": "المعلم", 
        "class": "الفصل", 
        "date": "التاريخ",
        "status_clean": "الحالة"
    })
    
    return df_matches[["المرة", "الطالب", "المعلم", "الفصل", "التاريخ", "الحالة"]]

# ================== دوال إنشاء PDF المعدلة ==================
def create_simple_pdf_styles():
    """إنشاء أنماط بسيطة للPDF"""
    styles = getSampleStyleSheet()
    
    # أنماط بسيطة باستخدام Helvetica فقط
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Title'],
        fontName='Helvetica',
        fontSize=22,
        alignment=1,  # مركز
        textColor=colors.darkblue,
        spaceAfter=20
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Heading2'],
        fontName='Helvetica',
        fontSize=16,
        alignment=1,  # مركز
        textColor=colors.navy,
        spaceAfter=12
    )
    
    normal_style = ParagraphStyle(
        'Normal',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=12,
        alignment=2,  # يمين
        spaceAfter=6
    )
    
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        alignment=2,  # يمين
        textColor=colors.darkblue,
        spaceAfter=6
    )
    
    return {
        'title': title_style,
        'subtitle': subtitle_style,
        'normal': normal_style,
        'footer': footer_style
    }

def generate_system_report_pdf():
    """إنشاء تقرير PDF شامل للنظام - نسخة مبسطة"""
    try:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
        elements = []
        
        # الحصول على الأنماط
        styles = create_simple_pdf_styles()
        
        # صفحة الغلاف
        title_text = "تقرير شامل لنظام الغياب"
        elements.append(Paragraph(title_text, styles['title']))
        elements.append(Spacer(1, 20))
        
        today = datetime.now()
        current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
        date_text = f"تاريخ التقرير: {current_date}"
        elements.append(Paragraph(date_text, styles['normal']))
        elements.append(Spacer(1, 20))
        
        # الإحصائيات العامة
        elements.append(Paragraph("الإحصائيات العامة للنظام", styles['subtitle']))
        elements.append(Spacer(1, 10))
        
        df_all = read_sheet()
        total_records = len(df_all) if not df_all.empty else 0
        
        # جدول الإحصائيات العامة
        stats_data = [
            ["عدد الطلاب", str(len(ALL_STUDENTS))],
            ["عدد الفصول", str(len(CLASSES))],
            ["عدد المعلمين", str(len(TEACHER_CLASSES))],
            ["إجمالي سجلات الغياب", str(total_records)]
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
        elements.append(Paragraph("تفاصيل الفصول", styles['subtitle']))
        elements.append(Spacer(1, 10))
        
        for class_name, students in CLASSES.items():
            # إحصائيات الفصل
            stats = get_class_statistics(class_name)
            
            # معلومات الفصل
            elements.append(Paragraph(f"الفصل: {class_name}", styles['normal']))
            elements.append(Spacer(1, 5))
            
            # جدول إحصائيات الفصل
            class_stats_data = [
                ["عدد الطلاب", str(len(students))],
                ["عدد السجلات", str(stats["total_records"])],
                ["نسبة الحضور", f"{stats['attendance_rate']:.1f}%"],
                ["المعلم المسؤول", 
                 ', '.join([k for k, v in TEACHER_CLASSES.items() if class_name in v]) or 'غير معين']
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
        elements.append(Paragraph("معلومات المعلمين", styles['subtitle']))
        elements.append(Spacer(1, 10))
        
        for teacher, classes in TEACHER_CLASSES.items():
            elements.append(Paragraph(f"المعلم: {teacher}", styles['normal']))
            elements.append(Spacer(1, 5))
            
            elements.append(Paragraph(f"الفصول المسؤول عنها: {', '.join(classes)}", styles['normal']))
            
            # حساب إحصائيات كل فصل يدرسه المعلم
            for class_name in classes:
                stats = get_class_statistics(class_name)
                elements.append(Paragraph(f"  - {class_name}: {stats['total_records']} سجل، نسبة الحضور: {stats['attendance_rate']:.1f}%", 
                                         styles['normal']))
            
            elements.append(Spacer(1, 10))
        
        # الصفحة الأخيرة
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("ملاحظات:", styles['subtitle']))
        elements.append(Spacer(1, 10))
        
        elements.append(Paragraph("• هذا التقرير تم إنشاؤه تلقائياً من نظام الغياب الإلكتروني.", styles['normal']))
        elements.append(Paragraph("• البيانات محدثة حتى تاريخ إنشاء التقرير.", styles['normal']))
        elements.append(Paragraph("• يمكن للمدير الوصول إلى البيانات التفصيلية من لوحة التحكم.", styles['normal']))
        
        elements.append(Spacer(1, 20))
        elements.append(Paragraph("توقيع مدير النظام:", styles['subtitle']))
        elements.append(Spacer(1, 10))
        elements.append(Paragraph("________________________", styles['normal']))
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(f"تاريخ الطباعة: {current_date}", styles['footer']))
        
        doc.build(elements)
        buffer.seek(0)
        return buffer
        
    except Exception as e:
        logger.error(f"❌ خطأ في إنشاء تقرير النظام: {e}")
        # إنشاء PDF بديل بسيط في حالة الخطأ
        return create_simple_fallback_pdf()

def create_simple_fallback_pdf():
    """إنشاء PDF بسيط كبديل"""
    buffer = io.BytesIO()
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(buffer, pagesize=A4)
    
    # العنوان
    c.setFont("Helvetica", 24)
    c.drawString(100, 800, "تقرير نظام الغياب")
    
    # التاريخ
    today = datetime.now()
    current_date = f"{today.day:02d}/{today.month:02d}/{today.year}"
    c.setFont("Helvetica", 14)
    c.drawString(100, 770, f"تاريخ التقرير: {current_date}")
    
    # إحصائيات
    c.setFont("Helvetica", 16)
    c.drawString(100, 730, "الإحصائيات العامة:")
    
    c.setFont("Helvetica", 12)
    stats = [
        f"عدد الطلاب: {len(ALL_STUDENTS)}",
        f"عدد الفصول: {len(CLASSES)}", 
        f"عدد المعلمين: {len(TEACHER_CLASSES)}",
    ]
    
    y = 700
    for stat in stats:
        c.drawString(100, y, stat)
        y -= 25
    
    c.showPage()
    c.save()
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
    .home-title {
        font-size: 36px;
        margin-bottom: 30px;
        color: #1e40af !important;
        text-align: center;
        font-weight: 700;
    }
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
    st.session_state.teacher_mode = None

# صفحة تسجيل الدخول الرئيسية
if st.session_state.page == "login":
    # إخفاء الـ toolbar في صفحة تسجيل الدخول
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)
    
    # تصميم صفحة تسجيل الدخول
    st.markdown("""
    <div style="max-width: 500px; margin: 60px auto; padding: 40px; background: white; border-radius: 20px; box-shadow: 0 10px 30px rgba(0,0,0,0.1); text-align: center;">
        <div style="color: #1e40af; font-size: 32px; margin-bottom: 30px; font-weight: 700;">🚪 تسجيل الدخول</div>
    </div>
    """, unsafe_allow_html=True)
    
    # حاوية الإدخالات
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        st.markdown('<div style="height: 20px"></div>', unsafe_allow_html=True)
        
        # حقل إدخال اسم المستخدم
        username = st.text_input("اسم المستخدم", placeholder="أدخل اسمك")
        
        # حقل إدخال كلمة السر
        password = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور الخاصة بك")
        
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
        st.markdown('<div class="home-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # عرض نوع المستخدم
        role_badge = ""
        if st.session_state.user_role == "admin":
            role_badge = '👑 مدير النظام'
        elif st.session_state.user_role == "teacher":
            role_badge = '👨‍🏫 معلم'
        else:
            role_badge = '👨‍🎓 طالب'
        
        st.info(f"مرحباً بك {role_badge} {st.session_state.user_name}")
        
        # أزرار المهام حسب نوع المستخدم
        if st.session_state.user_role == "admin":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("👑 لوحة التحكم", use_container_width=True):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            with col2:
                if st.button("📊 التقارير", use_container_width=True):
                    st.session_state.page = "admin_reports"
                    st.rerun()
                    
        elif st.session_state.user_role == "teacher":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 تسجيل الغياب", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "record"
                    st.session_state.selected_class = None
                    st.rerun()
            
            with col2:
                if st.button("📊 عرض الإحصائيات", use_container_width=True):
                    st.session_state.page = "teacher_attendance"
                    st.session_state.teacher_mode = "statistics"
                    st.session_state.selected_class = None
                    st.rerun()
        
        elif st.session_state.user_role == "student":
            if st.button("👨‍🎓 تقرير الغياب الخاص بي", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.rerun()
        
        # زر تسجيل الخروج للجميع
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.session_state.teacher_classes = None
            st.session_state.page = "login"
            st.rerun()
    
    # صفحة مدير النظام - التقارير
    elif st.session_state.page == "admin_reports":
        st.markdown('<div class="home-title">📤 تصدير التقارير</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.info("يمكنك إنشاء وتحميل التقارير المختلفة للنظام")
        
        # قسم إنشاء تقرير شامل
        st.markdown("### 📄 تقرير شامل للنظام")
        
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
                    st.info("""
                    **محتويات التقرير الشامل:**
                    1. الإحصائيات العامة للنظام
                    2. تفاصيل جميع الفصول
                    3. معلومات المعلمين والفصول المسؤولين عنها
                    4. توقيع مدير النظام
                    """)
                else:
                    st.error("❌ فشل في إنشاء التقرير")
                    
            except Exception as e:
                st.error(f"❌ خطأ في إنشاء التقرير: {str(e)}")
        
        # قسم تصدير البيانات الخام
        st.markdown("---")
        st.markdown("### 📊 تصدير البيانات الخام")
        
        df_all = read_sheet()
        if not df_all.empty:
            csv = df_all.to_csv(index=False)
            st.download_button(
                label="📥 تحميل البيانات الخام (CSV)",
                data=csv,
                file_name=f"بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info("لا توجد بيانات لتصديرها")
    
    # صفحة مدير النظام - لوحة التحكم
    elif st.session_state.user_role == "admin" and st.session_state.page == "admin_dashboard":
        st.markdown('<div class="home-title">👑 لوحة تحكم مدير النظام</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات لوحة التحكم
        tab1, tab2, tab3 = st.tabs(["📊 نظرة عامة", "👥 إدارة الطلاب", "📋 مراجعة البيانات"])
        
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
        
        with tab2:
            st.markdown("### 👥 إدارة الطلاب")
            
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
        
        with tab3:
            st.markdown("### 📋 مراجعة بيانات الغياب")
            
            # عرض جميع بيانات الغياب
            df_all = read_sheet()
            
            if not df_all.empty:
                st.dataframe(df_all, use_container_width=True)
            else:
                st.info("📭 لا توجد بيانات غياب بعد.")
        
        # زر إنشاء تقرير في الأسفل
        st.markdown("---")
        if st.button("📄 إنشاء تقرير شامل", use_container_width=True):
            st.session_state.page = "admin_reports"
            st.rerun()
    
    # صفحة الطالب
    elif st.session_state.user_role == "student" and st.session_state.page == "student_dashboard":
        st.markdown('<div class="home-title">📊 تقرير الغياب الخاص بي</div>', unsafe_allow_html=True)
        
        # زر العودة للصفحة الرئيسية
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
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
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("عدد مرات الحضور", present_count)
            with col2:
                st.metric("عدد مرات الغياب", absent_count)
            with col3:
                st.metric("إجمالي السجلات", total_count)
            
            # عرض الجدول
            st.markdown("### 📋 تفاصيل السجلات:")
            st.dataframe(df_student, use_container_width=True, hide_index=True)
    
    # صفحة المعلم
    elif st.session_state.user_role == "teacher" and st.session_state.page == "teacher_attendance":
        teacher_name = st.session_state.get('teacher_name', st.session_state.user_name)
        teacher_classes = st.session_state.get('teacher_classes', [])
        
        # إذا لم يتم اختيار فصل بعد، عرض أزرار الفصول
        if not st.session_state.selected_class:
            st.markdown('<div class="home-title">🎯 اختر الفصل</div>', unsafe_allow_html=True)
            
            # زر العودة
            if st.button("🏠 العودة", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
            
            # عرض أزرار الفصول التي يدرسها المعلم فقط
            if teacher_classes:
                for class_name in teacher_classes:
                    if st.button(f"🎯 {class_name}", use_container_width=True):
                        st.session_state.selected_class = class_name
                        st.rerun()
            else:
                st.warning("⚠️ لا يوجد فصول موكلة إليك.")
        
        # إذا تم اختيار فصل، عرض الخيارات حسب الوضع
        else:
            selected_class = st.session_state.selected_class
            
            # إذا اختار تسجيل الغياب
            if st.session_state.teacher_mode == "record":
                st.markdown(f'<div class="home-title">📝 تسجيل غياب {selected_class}</div>', unsafe_allow_html=True)
                
                # زر العودة لاختيار فصل آخر
                if st.button("🔄 اختيار فصل آخر", use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                # عرض قائمة الطلاب للفصل المحدد
                class_students = CLASSES.get(selected_class, [])
                
                if class_students:
                    # اختيار الطلاب الغائبين
                    selected = st.multiselect(
                        f"اختر الطلاب الغائبين من {selected_class}",
                        class_students
                    )

                    # اختيار نوع الغياب
                    col_a, col_b = st.columns(2)
                    with col_a:
                        excuse = st.checkbox("غياب بعذر")
                    with col_b:
                        no_excuse = st.checkbox("غياب بدون عذر")

                    # زر تسجيل الغياب
                    if st.button("💾 حفظ وتسجيل الغياب", use_container_width=True):
                        if excuse and no_excuse:
                            st.warning("⚠️ اختر نوع واحد فقط.")
                        elif not (excuse or no_excuse):
                            st.warning("⚠️ من فضلك اختر نوع الغياب.")
                        else:
                            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                            
                            # تسجيل الغياب
                            try:
                                failed, success_count = record_attendance(
                                    selected, teacher_name, selected_class, status_label
                                )
                            except Exception as e:
                                st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                            else:
                                if success_count > 0:
                                    st.success(f"✅ تم تسجيل الغياب بنجاح")
                else:
                    st.error(f"❌ لا يوجد طلاب مسجلين في {selected_class}")
            
            # إذا اختار عرض الإحصائيات
            elif st.session_state.teacher_mode == "statistics":
                st.markdown(f'<div class="home-title">📊 إحصائيات {selected_class}</div>', unsafe_allow_html=True)
                
                # زر العودة لاختيار فصل آخر
                if st.button("🔄 اختيار فصل آخر", use_container_width=True):
                    st.session_state.selected_class = None
                    st.rerun()
                
                # الحصول على إحصائيات الفصل
                stats = get_class_statistics(selected_class)
                
                # عرض الإحصائيات العامة
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("عدد الطلاب", stats["total_students"])
                with col2:
                    st.metric("إجمالي السجلات", stats["total_records"])
                with col3:
                    st.metric("نسبة الحضور", f"{stats['attendance_rate']:.1f}%")
        
        # زر العودة للصفحة الرئيسية
        st.markdown("---")
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.selected_class = None
            st.session_state.teacher_mode = None
            st.rerun()

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
