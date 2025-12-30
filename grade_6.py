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
import tempfile
from datetime import date, timedelta
import random
import string

# ------------------ Page config ------------------
st.set_page_config(
    page_title="نظام الغياب المدرسي",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ------------------ إدارة الحالة ------------------
# تهيئة حالة الجلسة
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "page" not in st.session_state:
    st.session_state.page = "login"
if "attendance_data" not in st.session_state:
    st.session_state.attendance_data = []
if "CLASSES" not in st.session_state:
    st.session_state.CLASSES = {}
if "TEACHERS" not in st.session_state:
    st.session_state.TEACHERS = {}
if "STUDENT_PASSWORDS" not in st.session_state:
    st.session_state.STUDENT_PASSWORDS = {}
if "USERS" not in st.session_state:
    st.session_state.USERS = {
        "admin": {
            "password": "admin1234",
            "role": "admin",
            "name": "مدير النظام"
        }
    }

# ------------------ CSS التنسيقات ------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    
    * {
        font-family: 'Cairo', sans-serif !important;
        direction: rtl !important;
    }
    
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
    }
    
    .main-header {
        text-align: center;
        padding: 25px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        border-radius: 20px;
        margin: 20px 0;
        box-shadow: 0 8px 25px rgba(0,0,0,0.15);
    }
    
    .login-container {
        max-width: 450px;
        margin: 80px auto;
        padding: 40px 30px;
        background: white;
        border-radius: 20px;
        box-shadow: 0 15px 35px rgba(0,0,0,0.1);
        text-align: center;
        border: 1px solid #e2e8f0;
    }
    
    .welcome-box {
        background: linear-gradient(135deg, #f0f9ff, #e0f2fe);
        padding: 25px;
        border-radius: 15px;
        margin: 25px 0;
        border: 3px solid #bae6fd;
        text-align: center;
    }
    
    .stat-card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.08);
        text-align: center;
        border-top: 5px solid;
        margin: 10px 0;
        transition: transform 0.3s;
    }
    
    .stat-card:hover {
        transform: translateY(-5px);
    }
    
    .card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 5px 20px rgba(0,0,0,0.08);
        margin: 15px 0;
        border-right: 5px solid #3b82f6;
    }
    
    .btn-action {
        width: 100%;
        padding: 12px;
        margin: 8px 0;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        font-size: 16px;
        cursor: pointer;
        transition: all 0.3s;
        text-align: center;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    
    .btn-primary:hover {
        background: linear-gradient(135deg, #2563eb, #1d4ed8);
        box-shadow: 0 5px 15px rgba(37, 99, 235, 0.3);
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
        background: linear-gradient(135deg, #06b6d4, #0891b2);
        color: white;
    }
    
    .badge {
        display: inline-block;
        padding: 6px 15px;
        border-radius: 20px;
        font-size: 14px;
        font-weight: 600;
        margin-right: 10px;
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
        background: linear-gradient(135deg, #8b5cf6, #7c3aed);
        color: white;
    }
    
    .data-table {
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
    }
    
    .data-table th {
        background: #f1f5f9;
        padding: 12px 15px;
        text-align: right;
        font-weight: bold;
        border-bottom: 2px solid #e2e8f0;
        color: #475569;
    }
    
    .data-table td {
        padding: 12px 15px;
        border-bottom: 1px solid #e2e8f0;
    }
    
    .data-table tr:hover {
        background: #f8fafc;
    }
    
    .status-present {
        color: #059669;
        font-weight: bold;
        background: #d1fae5;
        padding: 4px 10px;
        border-radius: 8px;
        display: inline-block;
    }
    
    .status-absent {
        color: #dc2626;
        font-weight: bold;
        background: #fee2e2;
        padding: 4px 10px;
        border-radius: 8px;
        display: inline-block;
    }
    
    .status-excused {
        color: #d97706;
        font-weight: bold;
        background: #fef3c7;
        padding: 4px 10px;
        border-radius: 8px;
        display: inline-block;
    }
    
    .class-box {
        text-align: center;
        padding: 20px;
        border-radius: 12px;
        margin: 10px;
        color: white;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        transition: transform 0.3s;
    }
    
    .class-box:hover {
        transform: translateY(-5px);
    }
    
    .class-1 { background: linear-gradient(135deg, #3b82f6, #2563eb); }
    .class-2 { background: linear-gradient(135deg, #10b981, #059669); }
    .class-3 { background: linear-gradient(135deg, #f59e0b, #d97706); }
    .class-4 { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
    .class-5 { background: linear-gradient(135deg, #ec4899, #db2777); }
    .class-6 { background: linear-gradient(135deg, #14b8a6, #0d9488); }
    
    .class-count {
        font-size: 36px;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .class-label {
        font-size: 18px;
        font-weight: 600;
    }
    
    .stSelectbox div[data-baseweb="select"] > div {
        text-align: right;
        direction: rtl;
    }
    
    .stTextInput input {
        text-align: right;
        direction: rtl;
    }
    
    .stDateInput div {
        text-align: right;
        direction: rtl;
    }
</style>
""", unsafe_allow_html=True)

# ------------------ وظائف المساعدة ------------------
def arabic_date():
    """الحصول على التاريخ بالعربية"""
    arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", 
                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    
    today = datetime.now()
    weekday = arabic_weekdays[today.weekday()]
    month = arabic_months[today.month - 1]
    
    return f"{weekday}، {today.day} {month} {today.year}"

def get_today_date():
    """الحصول على تاريخ اليوم"""
    return date.today().strftime("%Y-%m-%d")

def generate_password(length=6):
    """توليد كلمة مرور عشوائية"""
    return ''.join(random.choices(string.digits, k=length))

def get_attendance_records():
    """الحصول على سجلات الحضور"""
    return st.session_state.attendance_data

def save_attendance_record(record):
    """حفظ سجل حضور"""
    if st.session_state.attendance_data:
        record["id"] = max([r.get("id", 0) for r in st.session_state.attendance_data]) + 1
    else:
        record["id"] = 1
    
    st.session_state.attendance_data.append(record)
    return True

def get_student_attendance(student_name):
    """الحصول على سجلات طالب معين"""
    return [record for record in st.session_state.attendance_data 
            if record.get("student") == student_name]

def get_class_attendance(class_name):
    """الحصول على سجلات فصل معين"""
    return [record for record in st.session_state.attendance_data 
            if record.get("class") == class_name]

def delete_attendance_record(record_id):
    """حذف سجل حضور"""
    st.session_state.attendance_data = [r for r in st.session_state.attendance_data 
                                      if r.get("id") != record_id]
    return True

def add_student(student_name, class_name, password):
    """إضافة طالب جديد"""
    if class_name not in st.session_state.CLASSES:
        st.session_state.CLASSES[class_name] = []
    
    if student_name not in st.session_state.CLASSES[class_name]:
        st.session_state.CLASSES[class_name].append(student_name)
        st.session_state.STUDENT_PASSWORDS[student_name] = password
        st.session_state.USERS[student_name] = {
            "password": password,
            "role": "student",
            "name": student_name,
            "class": class_name
        }
        return True
    return False

def delete_student(student_name):
    """حذف طالب"""
    for class_name, students in st.session_state.CLASSES.items():
        if student_name in students:
            st.session_state.CLASSES[class_name].remove(student_name)
            if student_name in st.session_state.STUDENT_PASSWORDS:
                del st.session_state.STUDENT_PASSWORDS[student_name]
            if student_name in st.session_state.USERS:
                del st.session_state.USERS[student_name]
            return True, class_name
    return False, None

def add_class(class_name, teacher_name=None):
    """إضافة فصل جديد"""
    if class_name not in st.session_state.CLASSES:
        st.session_state.CLASSES[class_name] = []
        if teacher_name and teacher_name in st.session_state.TEACHERS:
            st.session_state.TEACHERS[teacher_name].append(class_name)
        return True
    return False

def delete_class(class_name):
    """حذف فصل"""
    if class_name in st.session_state.CLASSES:
        for teacher in st.session_state.TEACHERS:
            if class_name in st.session_state.TEACHERS[teacher]:
                st.session_state.TEACHERS[teacher].remove(class_name)
        del st.session_state.CLASSES[class_name]
        return True
    return False

def add_teacher(teacher_name, password, classes):
    """إضافة معلم جديد"""
    if teacher_name not in st.session_state.TEACHERS:
        st.session_state.TEACHERS[teacher_name] = classes
        st.session_state.USERS[teacher_name] = {
            "password": password,
            "role": "teacher",
            "name": teacher_name,
            "classes": classes
        }
        return True
    return False

def delete_teacher(teacher_name):
    """حذف معلم"""
    if teacher_name in st.session_state.TEACHERS:
        del st.session_state.TEACHERS[teacher_name]
        if teacher_name in st.session_state.USERS:
            del st.session_state.USERS[teacher_name]
        return True
    return False

def generate_student_report(student_name, start_date=None, end_date=None):
    """تقرير مفصل للطالب"""
    records = get_student_attendance(student_name)
    
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        records = [r for r in records if start_dt <= datetime.strptime(r["date"], "%Y-%m-%d") <= end_dt]
    
    if not records:
        return None
    
    total_days = len(records)
    present_count = len([r for r in records if r["status"] == "حاضر"])
    absent_excused = len([r for r in records if r["status"] == "غياب بعذر"])
    absent_unexcused = len([r for r in records if r["status"] == "غياب بدون عذر"])
    
    attendance_rate = (present_count / total_days * 100) if total_days > 0 else 0
    
    return {
        "student_name": student_name,
        "total_days": total_days,
        "present_count": present_count,
        "absent_excused": absent_excused,
        "absent_unexcused": absent_unexcused,
        "attendance_rate": round(attendance_rate, 1),
        "records": records
    }

def generate_class_report(class_name, start_date=None, end_date=None):
    """تقرير مفصل للفصل"""
    records = get_class_attendance(class_name)
    
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        records = [r for r in records if start_dt <= datetime.strptime(r["date"], "%Y-%m-%d") <= end_dt]
    
    if not records:
        return None
    
    students = st.session_state.CLASSES.get(class_name, [])
    student_reports = []
    
    for student in students:
        student_records = [r for r in records if r["student"] == student]
        if student_records:
            total_days = len(student_records)
            present_count = len([r for r in student_records if r["status"] == "حاضر"])
            attendance_rate = (present_count / total_days * 100) if total_days > 0 else 0
            
            student_reports.append({
                "student_name": student,
                "total_days": total_days,
                "present_count": present_count,
                "attendance_rate": round(attendance_rate, 1)
            })
    
    total_records = len(records)
    present_count = len([r for r in records if r["status"] == "حاضر"])
    absent_excused = len([r for r in records if r["status"] == "غياب بعذر"])
    absent_unexcused = len([r for r in records if r["status"] == "غياب بدون عذر"])
    
    return {
        "class_name": class_name,
        "total_students": len(students),
        "total_records": total_records,
        "present_count": present_count,
        "absent_excused": absent_excused,
        "absent_unexcused": absent_unexcused,
        "attendance_rate": round((present_count / total_records * 100) if total_records > 0 else 0, 1),
        "student_reports": student_reports,
        "records": records
    }

# ------------------ تحميل البيانات من Google Sheets ------------------
def load_data_from_google_sheets():
    """تحميل البيانات من Google Sheets"""
    try:
        # روابط Google Sheets
        STUDENTS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_XohJg8cVgDQO1kU-HW5z7J5pCD-zKbJ8cD2nK7Z7l6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6/pub?output=csv"
        TEACHERS_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_XohJg8cVgDQO1kU-HW5z7J5pCD-zKbJ8cD2nK7Z7l6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6/pub?output=csv"
        ATTENDANCE_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQ_XohJg8cVgDQO1kU-HW5z7J5pCD-zKbJ8cD2nK7Z7l6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6mY6Qp6/pub?output=csv"
        
        # تحميل بيانات الطلاب
        students_df = pd.read_csv(STUDENTS_URL)
        st.session_state.CLASSES = {}
        st.session_state.STUDENT_PASSWORDS = {}
        
        for _, row in students_df.iterrows():
            student_name = str(row['اسم الطالب']).strip()
            student_class = str(row['الفصل']).strip()
            student_password = str(row['كلمة المرور']).strip()
            
            # تحويل أسماء الفصول إلى صيغة عربية
            class_mapping = {
                'A': 'الصف الأول', 'B': 'الصف الثاني', 'C': 'الصف الثالث', 'D': 'الصف الرابع',
                'أ': 'الصف الأول', 'ب': 'الصف الثاني', 'ج': 'الصف الثالث', 'د': 'الصف الرابع',
                '1': 'الصف الأول', '2': 'الصف الثاني', '3': 'الصف الثالث', '4': 'الصف الرابع'
            }
            
            if student_class in class_mapping:
                student_class = class_mapping[student_class]
            elif not student_class.startswith('الصف'):
                student_class = f"الصف {student_class}"
            
            if student_class not in st.session_state.CLASSES:
                st.session_state.CLASSES[student_class] = []
            
            st.session_state.CLASSES[student_class].append(student_name)
            st.session_state.STUDENT_PASSWORDS[student_name] = student_password
            
            # إضافة الطالب إلى المستخدمين
            st.session_state.USERS[student_name] = {
                "password": student_password,
                "role": "student",
                "name": student_name,
                "class": student_class
            }
        
        # تحميل بيانات المعلمين
        teachers_df = pd.read_csv(TEACHERS_URL)
        st.session_state.TEACHERS = {}
        
        for _, row in teachers_df.iterrows():
            teacher_name = str(row['اسم المعلم']).strip()
            teacher_password = str(row['كلمة المرور']).strip()
            classes_str = str(row['الفصول']).strip()
            
            classes = []
            if classes_str:
                for c in classes_str.split(','):
                    c = c.strip()
                    class_mapping = {
                        'A': 'الصف الأول', 'B': 'الصف الثاني', 'C': 'الصف الثالث', 'D': 'الصف الرابع',
                        'أ': 'الصف الأول', 'ب': 'الصف الثاني', 'ج': 'الصف الثالث', 'د': 'الصف الرابع',
                        '1': 'الصف الأول', '2': 'الصف الثاني', '3': 'الصف الثالث', '4': 'الصف الرابع'
                    }
                    
                    if c in class_mapping:
                        classes.append(class_mapping[c])
                    elif not c.startswith('الصف'):
                        classes.append(f"الصف {c}")
                    else:
                        classes.append(c)
            
            st.session_state.TEACHERS[teacher_name] = classes
            
            # إضافة المعلم إلى المستخدمين
            st.session_state.USERS[teacher_name] = {
                "password": teacher_password,
                "role": "teacher",
                "name": teacher_name,
                "classes": classes
            }
        
        # تحميل بيانات الغياب
        attendance_df = pd.read_csv(ATTENDANCE_URL)
        st.session_state.attendance_data = []
        
        for idx, row in attendance_df.iterrows():
            # تحويل الفصل
            class_name = str(row['الفصل']).strip()
            class_mapping = {
                'A': 'الصف الأول', 'B': 'الصف الثاني', 'C': 'الصف الثالث', 'D': 'الصف الرابع',
                'أ': 'الصف الأول', 'ب': 'الصف الثاني', 'ج': 'الصف الثالث', 'د': 'الصف الرابع',
                '1': 'الصف الأول', '2': 'الصف الثاني', '3': 'الصف الثالث', '4': 'الصف الرابع'
            }
            
            if class_name in class_mapping:
                class_name = class_mapping[class_name]
            elif not class_name.startswith('الصف'):
                class_name = f"الصف {class_name}"
            
            record = {
                "id": idx + 1,
                "date": str(row['التاريخ']).strip(),
                "student": str(row['اسم الطالب']).strip(),
                "class": class_name,
                "teacher": str(row['المعلم']).strip(),
                "status": str(row['الحالة']).strip()
            }
            st.session_state.attendance_data.append(record)
        
        return True
        
    except Exception as e:
        st.error(f"❌ خطأ في تحميل البيانات: {str(e)}")
        return False

# ------------------ تحميل البيانات ------------------
if not st.session_state.CLASSES:
    with st.spinner("🔄 جاري تحميل البيانات من Google Sheets..."):
        if load_data_from_google_sheets():
            st.success("✅ تم تحميل البيانات بنجاح")
        else:
            st.error("❌ فشل في تحميل البيانات")

# ------------------ صفحة تسجيل الدخول ------------------
if st.session_state.page == "login":
    st.markdown(f"""
    <div class="main-header">
        <h1>📊 نظام إدارة الغياب المدرسي</h1>
        <p style="opacity: 0.9;">مدرسة السلام الإعدادية الثانوية المشتركة</p>
        <p style="font-size: 18px;">{arabic_date()}</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("""
    <div class="login-container">
        <h2 style="color: #1e40af; margin-bottom: 30px;">🚪 تسجيل الدخول</h2>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 3, 1])
    
    with col2:
        username = st.text_input("", placeholder="اسم المستخدم", label_visibility="collapsed")
        password = st.text_input("", placeholder="كلمة المرور", type="password", label_visibility="collapsed")
        
        if st.button("✅ تسجيل الدخول", use_container_width=True, type="primary"):
            if username and password:
                if username in st.session_state.USERS:
                    if st.session_state.USERS[username]["password"] == password:
                        st.session_state.logged_in = True
                        st.session_state.user_name = username
                        st.session_state.user_role = st.session_state.USERS[username]["role"]
                        st.session_state.page = "home"
                        st.success(f"✅ مرحباً بك {username}")
                        st.rerun()
                    else:
                        st.error("❌ كلمة المرور غير صحيحة")
                else:
                    st.error("❌ اسم المستخدم غير موجود")
            else:
                st.warning("⚠️ من فضلك أدخل اسم المستخدم وكلمة المرور")

# ------------------ الصفحة الرئيسية ------------------
elif st.session_state.logged_in:
    # شريط التنقل
    col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])
    
    with col1:
        role_badge = ""
        if st.session_state.user_role == "admin":
            role_badge = '<span class="badge badge-admin">👑 مدير النظام</span>'
        elif st.session_state.user_role == "teacher":
            role_badge = '<span class="badge badge-teacher">👨‍🏫 معلم</span>'
        else:
            role_badge = '<span class="badge badge-student">👨‍🎓 طالب</span>'
        
        st.markdown(f"""
        <div style="padding: 15px; background: white; border-radius: 10px; margin-bottom: 20px;">
            <h3 style="margin: 0; color: #1e40af;">مرحباً {st.session_state.user_name} {role_badge}</h3>
            <p style="margin: 5px 0 0 0; color: #64748b;">{arabic_date()}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        if st.button("🏠 الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
    
    with col3:
        if st.session_state.user_role == "admin":
            if st.button("👥 الطلاب", use_container_width=True):
                st.session_state.page = "students"
                st.rerun()
        elif st.session_state.user_role == "teacher":
            if st.button("📝 الغياب", use_container_width=True):
                st.session_state.page = "attendance"
                st.rerun()
        else:
            if st.button("📊 تقريري", use_container_width=True):
                st.session_state.page = "my_report"
                st.rerun()
    
    with col4:
        if st.session_state.user_role == "admin":
            if st.button("📊 التقارير", use_container_width=True):
                st.session_state.page = "reports"
                st.rerun()
        elif st.session_state.user_role == "teacher":
            if st.button("📊 التقارير", use_container_width=True):
                st.session_state.page = "teacher_reports"
                st.rerun()
    
    with col5:
        if st.button("🚪 خروج", use_container_width=True, type="secondary"):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.page = "login"
            st.rerun()
    
    st.markdown("---")
    
    # المحتوى الرئيسي حسب الصفحة
    if st.session_state.page == "home":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>🏠 الصفحة الرئيسية</h2>", unsafe_allow_html=True)
        
        # إحصائيات عامة
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            total_students = sum(len(students) for students in st.session_state.CLASSES.values())
            st.markdown(f"""
            <div class="stat-card" style="border-top-color: #3b82f6;">
                <h3 style="margin: 0; color: #3b82f6;">{total_students}</h3>
                <p style="margin: 5px 0 0 0; color: #64748b;">إجمالي الطلاب</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            total_classes = len(st.session_state.CLASSES)
            st.markdown(f"""
            <div class="stat-card" style="border-top-color: #10b981;">
                <h3 style="margin: 0; color: #10b981;">{total_classes}</h3>
                <p style="margin: 5px 0 0 0; color: #64748b;">عدد الفصول</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            total_teachers = len(st.session_state.TEACHERS)
            st.markdown(f"""
            <div class="stat-card" style="border-top-color: #f59e0b;">
                <h3 style="margin: 0; color: #f59e0b;">{total_teachers}</h3>
                <p style="margin: 5px 0 0 0; color: #64748b;">عدد المعلمين</p>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            total_records = len(st.session_state.attendance_data)
            st.markdown(f"""
            <div class="stat-card" style="border-top-color: #8b5cf6;">
                <h3 style="margin: 0; color: #8b5cf6;">{total_records}</h3>
                <p style="margin: 5px 0 0 0; color: #64748b;">سجلات الغياب</p>
            </div>
            """, unsafe_allow_html=True)
        
        # عرض الفصول
        st.markdown("<h3 style='margin-top: 30px;'>📚 الفصول الدراسية</h3>", unsafe_allow_html=True)
        
        if st.session_state.CLASSES:
            class_colors = ["class-1", "class-2", "class-3", "class-4", "class-5", "class-6"]
            
            for idx, (class_name, students) in enumerate(st.session_state.CLASSES.items()):
                color_class = class_colors[idx % len(class_colors)]
                
                col1, col2 = st.columns([3, 1])
                with col1:
                    with st.expander(f"🎯 {class_name} ({len(students)} طالب)"):
                        for student in students:
                            st.write(f"👨‍🎓 {student}")
                
                with col2:
                    st.markdown(f"""
                    <div class="class-box {color_class}">
                        <div class="class-count">{len(students)}</div>
                        <div class="class-label">{class_name}</div>
                    </div>
                    """, unsafe_allow_html=True)
        
        # أزرار الإجراءات السريعة
        st.markdown("<h3 style='margin-top: 30px;'>⚡ الإجراءات السريعة</h3>", unsafe_allow_html=True)
        
        if st.session_state.user_role == "admin":
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👥 إدارة الطلاب", use_container_width=True, type="primary"):
                    st.session_state.page = "students"
                    st.rerun()
            
            with col2:
                if st.button("🏫 إدارة الفصول", use_container_width=True, type="primary"):
                    st.session_state.page = "classes"
                    st.rerun()
            
            with col3:
                if st.button("👨‍🏫 إدارة المعلمين", use_container_width=True, type="primary"):
                    st.session_state.page = "teachers"
                    st.rerun()
            
            col4, col5, col6 = st.columns(3)
            
            with col4:
                if st.button("📝 تسجيل الغياب", use_container_width=True, type="secondary"):
                    st.session_state.page = "attendance"
                    st.rerun()
            
            with col5:
                if st.button("📊 التقارير", use_container_width=True, type="secondary"):
                    st.session_state.page = "reports"
                    st.rerun()
            
            with col6:
                if st.button("📥 تصدير بيانات", use_container_width=True, type="secondary"):
                    st.session_state.page = "export"
                    st.rerun()
        
        elif st.session_state.user_role == "teacher":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 تسجيل الغياب", use_container_width=True, type="primary"):
                    st.session_state.page = "attendance"
                    st.rerun()
            
            with col2:
                if st.button("📊 تقارير الفصول", use_container_width=True, type="primary"):
                    st.session_state.page = "teacher_reports"
                    st.rerun()
        
        else:  # طالب
            if st.button("📊 عرض سجل الغياب", use_container_width=True, type="primary"):
                st.session_state.page = "my_report"
                st.rerun()
    
    # ------------------ صفحة إدارة الطلاب ------------------
    elif st.session_state.page == "students" and st.session_state.user_role == "admin":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>👥 إدارة الطلاب</h2>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📋 عرض الطلاب", "➕ إضافة طالب", "🗑️ حذف طالب"])
        
        with tab1:
            st.markdown("<h3>📋 قائمة الطلاب حسب الفصول</h3>", unsafe_allow_html=True)
            
            for class_name, students in st.session_state.CLASSES.items():
                with st.expander(f"{class_name} ({len(students)} طالب)"):
                    df = pd.DataFrame({
                        "اسم الطالب": students,
                        "كلمة المرور": [st.session_state.STUDENT_PASSWORDS.get(s, "") for s in students]
                    })
                    st.dataframe(df, use_container_width=True)
        
        with tab2:
            st.markdown("<h3>➕ إضافة طالب جديد</h3>", unsafe_allow_html=True)
            
            with st.form("add_student_form"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    student_name = st.text_input("اسم الطالب*")
                
                with col2:
                    class_name = st.selectbox("الفصل*", list(st.session_state.CLASSES.keys()))
                
                with col3:
                    password = st.text_input("كلمة المرور*", value=generate_password(), type="password")
                
                if st.form_submit_button("➕ إضافة الطالب", use_container_width=True):
                    if student_name and class_name and password:
                        if add_student(student_name, class_name, password):
                            st.success(f"✅ تم إضافة الطالب {student_name}")
                            st.rerun()
                        else:
                            st.error("❌ الطالب موجود بالفعل")
                    else:
                        st.warning("⚠️ من فضلك املأ جميع الحقول")
        
        with tab3:
            st.markdown("<h3>🗑️ حذف طالب</h3>", unsafe_allow_html=True)
            
            # جمع جميع الطلاب
            all_students = []
            for class_name, students in st.session_state.CLASSES.items():
                for student in students:
                    all_students.append(f"{student} ({class_name})")
            
            if all_students:
                selected_student = st.selectbox("اختر الطالب", all_students)
                
                if st.button("🗑️ حذف الطالب", use_container_width=True, type="secondary"):
                    student_name = selected_student.split(" (")[0]
                    success, class_name = delete_student(student_name)
                    if success:
                        st.success(f"✅ تم حذف الطالب {student_name}")
                        st.rerun()
                    else:
                        st.error("❌ فشل في حذف الطالب")
            else:
                st.info("📭 لا يوجد طلاب")
    
    # ------------------ صفحة إدارة الفصول ------------------
    elif st.session_state.page == "classes" and st.session_state.user_role == "admin":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>🏫 إدارة الفصول</h2>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📋 عرض الفصول", "➕ إضافة فصل", "🗑️ حذف فصل"])
        
        with tab1:
            for class_name, students in st.session_state.CLASSES.items():
                st.markdown(f"""
                <div class="card">
                    <h4>{class_name} ({len(students)} طالب)</h4>
                    <p><strong>المعلمون:</strong> {', '.join([t for t in st.session_state.TEACHERS if class_name in st.session_state.TEACHERS[t]]) or 'لا يوجد'}</p>
                </div>
                """, unsafe_allow_html=True)
        
        with tab2:
            with st.form("add_class_form"):
                class_name = st.text_input("اسم الفصل الجديد*")
                teacher = st.selectbox("المعلم المسؤول", ["غير معين"] + list(st.session_state.TEACHERS.keys()))
                
                if st.form_submit_button("➕ إضافة الفصل", use_container_width=True):
                    if class_name:
                        if add_class(class_name, teacher if teacher != "غير معين" else None):
                            st.success(f"✅ تم إضافة الفصل {class_name}")
                            st.rerun()
                        else:
                            st.error("❌ الفصل موجود بالفعل")
                    else:
                        st.warning("⚠️ من فضلك أدخل اسم الفصل")
        
        with tab3:
            empty_classes = [c for c, s in st.session_state.CLASSES.items() if len(s) == 0]
            
            if empty_classes:
                selected_class = st.selectbox("اختر الفصل (الفصول الفارغة فقط)", empty_classes)
                
                if st.button("🗑️ حذف الفصل", use_container_width=True, type="secondary"):
                    if delete_class(selected_class):
                        st.success(f"✅ تم حذف الفصل {selected_class}")
                        st.rerun()
                    else:
                        st.error("❌ فشل في حذف الفصل")
            else:
                st.info("📭 لا توجد فصول فارغة")
    
    # ------------------ صفحة إدارة المعلمين ------------------
    elif st.session_state.page == "teachers" and st.session_state.user_role == "admin":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>👨‍🏫 إدارة المعلمين</h2>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📋 عرض المعلمين", "➕ إضافة معلم", "🗑️ حذف معلم"])
        
        with tab1:
            for teacher, classes in st.session_state.TEACHERS.items():
                st.markdown(f"""
                <div class="card">
                    <h4>{teacher}</h4>
                    <p><strong>الفصول:</strong> {', '.join(classes) if classes else 'لا يوجد'}</p>
                    <p><strong>عدد الطلاب:</strong> {sum(len(st.session_state.CLASSES.get(c, [])) for c in classes)}</p>
                </div>
                """, unsafe_allow_html=True)
        
        with tab2:
            with st.form("add_teacher_form"):
                teacher_name = st.text_input("اسم المعلم*")
                password = st.text_input("كلمة المرور*", value=generate_password())
                classes = st.multiselect("الفصول المسؤول عنها", list(st.session_state.CLASSES.keys()))
                
                if st.form_submit_button("➕ إضافة معلم", use_container_width=True):
                    if teacher_name and password:
                        if add_teacher(teacher_name, password, classes):
                            st.success(f"✅ تم إضافة المعلم {teacher_name}")
                            st.rerun()
                        else:
                            st.error("❌ المعلم موجود بالفعل")
                    else:
                        st.warning("⚠️ من فضلك املأ جميع الحقول")
        
        with tab3:
            deletable_teachers = list(st.session_state.TEACHERS.keys())
            
            if deletable_teachers:
                selected_teacher = st.selectbox("اختر المعلم", deletable_teachers)
                
                if st.button("🗑️ حذف المعلم", use_container_width=True, type="secondary"):
                    if delete_teacher(selected_teacher):
                        st.success(f"✅ تم حذف المعلم {selected_teacher}")
                        st.rerun()
                    else:
                        st.error("❌ فشل في حذف المعلم")
            else:
                st.info("📭 لا يوجد معلمين")
    
    # ------------------ صفحة تسجيل الغياب ------------------
    elif st.session_state.page == "attendance" and (st.session_state.user_role in ["admin", "teacher"]):
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>📝 تسجيل الغياب</h2>", unsafe_allow_html=True)
        
        # للمعلمين، عرض الفصول الخاصة بهم فقط
        if st.session_state.user_role == "teacher":
            teacher_classes = st.session_state.USERS[st.session_state.user_name]["classes"]
            if not teacher_classes:
                st.warning("⚠️ لا توجد فصول مخصصة لك")
                st.stop()
            selected_class = st.selectbox("اختر الفصل", teacher_classes)
        else:
            # للمدير، عرض جميع الفصول
            selected_class = st.selectbox("اختر الفصل", list(st.session_state.CLASSES.keys()))
        
        students = st.session_state.CLASSES.get(selected_class, [])
        
        if students:
            st.markdown(f"### 🎯 الفصل: {selected_class}")
            st.markdown(f"#### عدد الطلاب: {len(students)}")
            
            # اختيار تاريخ
            attendance_date = st.date_input("تاريخ الحضور", value=date.today())
            
            # اختيار الطلاب الغائبين
            absent_students = st.multiselect("الطلاب الغائبين", students)
            
            # نوع الغياب
            col1, col2 = st.columns(2)
            with col1:
                excused = st.checkbox("غياب بعذر")
            with col2:
                unexcused = st.checkbox("غياب بدون عذر")
            
            if st.button("💾 حفظ وتسجيل الغياب", use_container_width=True, type="primary"):
                if excused and unexcused:
                    st.warning("⚠️ اختر نوع واحد فقط من الغياب")
                else:
                    status = "غياب بعذر" if excused else ("غياب بدون عذر" if unexcused else "حاضر")
                    
                    for student in students:
                        student_status = status if student in absent_students else "حاضر"
                        
                        record = {
                            "id": len(st.session_state.attendance_data) + 1,
                            "date": attendance_date.strftime("%Y-%m-%d"),
                            "student": student,
                            "class": selected_class,
                            "teacher": st.session_state.user_name,
                            "status": student_status
                        }
                        
                        save_attendance_record(record)
                    
                    st.success(f"✅ تم تسجيل الغياب بنجاح")
                    st.info(f"الحاضرون: {len(students) - len(absent_students)} | الغائبون: {len(absent_students)}")
        else:
            st.warning("⚠️ لا يوجد طلاب في هذا الفصل")
    
    # ------------------ صفحة التقارير (للمدير) ------------------
    elif st.session_state.page == "reports" and st.session_state.user_role == "admin":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>📊 التقارير والإحصائيات</h2>", unsafe_allow_html=True)
        
        tab1, tab2, tab3 = st.tabs(["📈 تقارير الفصول", "👤 تقارير الطلاب", "👨‍🏫 تقارير المعلمين"])
        
        with tab1:
            selected_class = st.selectbox("اختر الفصل", list(st.session_state.CLASSES.keys()))
            
            if st.button("إنشاء التقرير", use_container_width=True):
                report = generate_class_report(selected_class)
                
                if report:
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.metric("عدد الطلاب", report["total_students"])
                    
                    with col2:
                        st.metric("إجمالي السجلات", report["total_records"])
                    
                    with col3:
                        st.metric("نسبة الحضور", f"{report['attendance_rate']}%")
                    
                    with col4:
                        st.metric("إجمالي الغياب", report["absent_excused"] + report["absent_unexcused"])
                    
                    # عرض بيانات الطلاب
                    st.markdown("### 📋 تفاصيل الطلاب")
                    if report["student_reports"]:
                        df = pd.DataFrame(report["student_reports"])
                        df = df.rename(columns={
                            "student_name": "اسم الطالب",
                            "total_days": "إجمالي الأيام",
                            "present_count": "أيام الحضور",
                            "attendance_rate": "نسبة الحضور"
                        })
                        st.dataframe(df, use_container_width=True)
        
        with tab2:
            # جمع جميع الطلاب
            all_students = []
            for class_name, students in st.session_state.CLASSES.items():
                for student in students:
                    all_students.append(f"{student} ({class_name})")
            
            if all_students:
                selected_student = st.selectbox("اختر الطالب", all_students)
                
                if st.button("إنشاء تقرير الطالب", use_container_width=True):
                    student_name = selected_student.split(" (")[0]
                    report = generate_student_report(student_name)
                    
                    if report:
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("إجمالي الأيام", report["total_days"])
                        
                        with col2:
                            st.metric("أيام الحضور", report["present_count"])
                        
                        with col3:
                            st.metric("نسبة الحضور", f"{report['attendance_rate']}%")
                        
                        with col4:
                            st.metric("إجمالي الغياب", report["absent_excused"] + report["absent_unexcused"])
                        
                        # عرض السجلات
                        st.markdown("### 📋 سجل الغياب")
                        if report["records"]:
                            df = pd.DataFrame(report["records"])
                            df = df[["date", "class", "teacher", "status"]]
                            df = df.rename(columns={
                                "date": "التاريخ",
                                "class": "الفصل",
                                "teacher": "المعلم",
                                "status": "الحالة"
                            })
                            st.dataframe(df, use_container_width=True)
        
        with tab3:
            selected_teacher = st.selectbox("اختر المعلم", list(st.session_state.TEACHERS.keys()))
            
            if selected_teacher:
                teacher_classes = st.session_state.TEACHERS[selected_teacher]
                st.markdown(f"**الفصول المسؤول عنها:** {', '.join(teacher_classes)}")
                
                # حساب إحصائيات المعلم
                teacher_records = [r for r in st.session_state.attendance_data if r["teacher"] == selected_teacher]
                
                if teacher_records:
                    total_records = len(teacher_records)
                    present_count = len([r for r in teacher_records if r["status"] == "حاضر"])
                    attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric("إجمالي السجلات", total_records)
                    
                    with col2:
                        st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
                    
                    with col3:
                        st.metric("عدد الفصول", len(teacher_classes))
    
    # ------------------ صفحة التقارير (للمعلم) ------------------
    elif st.session_state.page == "teacher_reports" and st.session_state.user_role == "teacher":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>📊 تقارير الفصول</h2>", unsafe_allow_html=True)
        
        teacher_classes = st.session_state.USERS[st.session_state.user_name]["classes"]
        
        if teacher_classes:
            selected_class = st.selectbox("اختر الفصل", teacher_classes)
            
            # الحصول على سجلات الفصل
            class_records = get_class_attendance(selected_class)
            
            if class_records:
                st.markdown(f"### 📋 سجل غياب الفصل: {selected_class}")
                
                # تحويل إلى DataFrame
                df = pd.DataFrame(class_records)
                df = df[["date", "student", "status"]]
                df = df.rename(columns={
                    "date": "التاريخ",
                    "student": "الطالب",
                    "status": "الحالة"
                })
                
                st.dataframe(df, use_container_width=True)
                
                # الإحصائيات
                total_records = len(class_records)
                present_count = len([r for r in class_records if r["status"] == "حاضر"])
                absent_count = total_records - present_count
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("إجمالي السجلات", total_records)
                
                with col2:
                    st.metric("عدد الحضور", present_count)
                
                with col3:
                    st.metric("عدد الغياب", absent_count)
            else:
                st.info(f"📭 لا توجد سجلات غياب للفصل {selected_class}")
        else:
            st.warning("⚠️ لا توجد فصول مخصصة لك")
    
    # ------------------ صفحة تقرير الطالب ------------------
    elif st.session_state.page == "my_report" and st.session_state.user_role == "student":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>📊 سجل الغياب الشخصي</h2>", unsafe_allow_html=True)
        
        student_name = st.session_state.user_name
        student_records = get_student_attendance(student_name)
        
        if student_records:
            st.markdown(f"### 👨‍🎓 الطالب: {student_name}")
            
            # تحويل إلى DataFrame
            df = pd.DataFrame(student_records)
            df = df[["date", "class", "teacher", "status"]]
            df = df.rename(columns={
                "date": "التاريخ",
                "class": "الفصل",
                "teacher": "المعلم",
                "status": "الحالة"
            })
            
            st.dataframe(df, use_container_width=True)
            
            # الإحصائيات
            total_records = len(student_records)
            present_count = len([r for r in student_records if r["status"] == "حاضر"])
            absent_excused = len([r for r in student_records if r["status"] == "غياب بعذر"])
            absent_unexcused = len([r for r in student_records if r["status"] == "غياب بدون عذر"])
            attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("إجمالي الأيام", total_records)
            
            with col2:
                st.metric("أيام الحضور", present_count)
            
            with col3:
                st.metric("أيام الغياب", absent_excused + absent_unexcused)
            
            with col4:
                st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
            
            # تفاصيل الغياب
            if absent_excused + absent_unexcused > 0:
                col1, col2 = st.columns(2)
                with col1:
                    st.metric("غياب بعذر", absent_excused)
                with col2:
                    st.metric("غياب بدون عذر", absent_unexcused)
        else:
            st.info(f"📭 لا توجد سجلات غياب لك يا {student_name}")
    
    # ------------------ صفحة تصدير البيانات ------------------
    elif st.session_state.page == "export" and st.session_state.user_role == "admin":
        st.markdown("<h2 style='text-align: center; color: #1e40af;'>📥 تصدير البيانات</h2>", unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            # تصدير بيانات الطلاب
            students_data = []
            for class_name, students in st.session_state.CLASSES.items():
                for student in students:
                    students_data.append({
                        "اسم الطالب": student,
                        "الفصل": class_name,
                        "كلمة المرور": st.session_state.STUDENT_PASSWORDS.get(student, "")
                    })
            
            if students_data:
                df = pd.DataFrame(students_data)
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير بيانات الطلاب",
                    data=csv,
                    file_name="بيانات_الطلاب.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col2:
            # تصدير بيانات الغياب
            if st.session_state.attendance_data:
                df = pd.DataFrame(st.session_state.attendance_data)
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير بيانات الغياب",
                    data=csv,
                    file_name="بيانات_الغياب.csv",
                    mime="text/csv",
                    use_container_width=True
                )
        
        with col3:
            # تصدير بيانات المعلمين
            teachers_data = []
            for teacher, classes in st.session_state.TEACHERS.items():
                teachers_data.append({
                    "اسم المعلم": teacher,
                    "الفصول": ", ".join(classes)
                })
            
            if teachers_data:
                df = pd.DataFrame(teachers_data)
                csv = df.to_csv(index=False, encoding='utf-8-sig')
                
                st.download_button(
                    label="📥 تصدير بيانات المعلمين",
                    data=csv,
                    file_name="بيانات_المعلمين.csv",
                    mime="text/csv",
                    use_container_width=True
                )

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
