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
from datetime import date, timedelta
import random
import string

# ------------------ Page config ------------------
st.set_page_config(page_title="نظام الغياب", layout="wide")

# ------------------ Logging ------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("attendance_app")

# ------------------ إدارة الحالة ------------------
# الحالة الأساسية
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "page" not in st.session_state:
    st.session_state.page = "login"

# الحالة للإدارة
if "current_tab" not in st.session_state:
    st.session_state.current_tab = "نظرة عامة"
if "editing_mode" not in st.session_state:
    st.session_state.editing_mode = None
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "attendance_data" not in st.session_state:
    st.session_state.attendance_data = []
if "messages" not in st.session_state:
    st.session_state.messages = []
if "events" not in st.session_state:
    st.session_state.events = []

# ------------------ تهيئة البيانات ------------------
# البيانات الأولية للفصول
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

# بيانات المعلمين
TEACHERS = {
    "مينا سمير": ["Class B", "Class C"],
    "فادي حبيب": ["Class D", "Class E"]
}

# كلمات مرور الطلاب
STUDENT_PASSWORDS = {
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

# قاعدة بيانات المستخدمين
USERS = {
    "admin": {
        "password": "admin1234",
        "role": "admin",
        "name": "مدير النظام"
    },
    "مينا سمير": {
        "password": "mina1234",
        "role": "teacher",
        "name": "مينا سمير",
        "classes": ["Class B", "Class C"]
    },
    "فادي حبيب": {
        "password": "fady5678",
        "role": "teacher",
        "name": "فادي حبيب",
        "classes": ["Class D", "Class E"]
    },
}

# إضافة الطلاب إلى قاعدة المستخدمين
for class_name, students in CLASSES.items():
    for student in students:
        if student in STUDENT_PASSWORDS:
            USERS[student] = {
                "password": STUDENT_PASSWORDS[student],
                "role": "student",
                "name": student,
                "class": class_name
            }
        else:
            USERS[student] = {
                "password": f"stu{hash(student) % 10000:04d}",
                "role": "student",
                "name": student,
                "class": class_name
            }

# البيانات الأولية للغياب (إذا كانت فارغة)
if len(st.session_state.attendance_data) == 0:
    # إضافة بيانات افتراضية للاختبار
    sample_data = [
        {"id": 1, "date": "2024-01-15", "student": "محمد علي محمد", "class": "Class B", "teacher": "مينا سمير", "status": "حاضر"},
        {"id": 2, "date": "2024-01-15", "student": "حسن أحمد حسن", "class": "Class B", "teacher": "مينا سمير", "status": "غياب بعذر"},
        {"id": 3, "date": "2024-01-16", "student": "أحمد محمد أحمد", "class": "Class C", "teacher": "مينا سمير", "status": "حاضر"},
        {"id": 4, "date": "2024-01-16", "student": "محمود سعيد حسين", "class": "Class C", "teacher": "مينا سمير", "status": "غياب بدون عذر"},
        {"id": 5, "date": "2024-01-17", "student": "فؤاد محمد فؤاد", "class": "Class D", "teacher": "فادي حبيب", "status": "حاضر"},
    ]
    st.session_state.attendance_data = sample_data

# ------------------ وظائف المساعدة الجديدة ------------------
def send_notification(to_user, message, notification_type="info"):
    """إرسال إشعار"""
    notification = {
        "id": len(st.session_state.messages) + 1,
        "to": to_user,
        "message": message,
        "type": notification_type,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "read": False
    }
    st.session_state.messages.append(notification)
    return True

def get_unread_notifications(user_name):
    """الحصول على الإشعارات غير المقروءة"""
    return [msg for msg in st.session_state.messages 
            if msg["to"] == user_name and not msg["read"]]

def mark_notification_as_read(notification_id):
    """تحديد الإشعار كمقروء"""
    for msg in st.session_state.messages:
        if msg["id"] == notification_id:
            msg["read"] = True
            return True
    return False

def add_event(event_title, event_date, event_type, description="", participants=[]):
    """إضافة حدث جديد"""
    event = {
        "id": len(st.session_state.events) + 1,
        "title": event_title,
        "date": event_date,
        "type": event_type,
        "description": description,
        "participants": participants,
        "created_by": st.session_state.user_name,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    st.session_state.events.append(event)
    return True

def get_upcoming_events(days=7):
    """الحصول على الأحداث القادمة"""
    today = date.today()
    future_date = today + timedelta(days=days)
    
    upcoming = []
    for event in st.session_state.events:
        event_date = datetime.strptime(event["date"], "%Y-%m-%d").date()
        if today <= event_date <= future_date:
            upcoming.append(event)
    
    return sorted(upcoming, key=lambda x: x["date"])

def generate_student_report(student_name, start_date=None, end_date=None):
    """تقرير مفصل للطالب"""
    records = get_student_attendance(student_name)
    
    if start_date and end_date:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        records = [r for r in records if start_dt <= datetime.strptime(r["date"], "%Y-%m-%d") <= end_dt]
    
    if not records:
        return None
    
    # تحليل البيانات
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
        "attendance_rate": attendance_rate,
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
    
    # تحليل البيانات
    students = CLASSES[class_name]
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
                "attendance_rate": attendance_rate
            })
    
    # إحصائيات الفصل
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
        "attendance_rate": (present_count / total_records * 100) if total_records > 0 else 0,
        "student_reports": student_reports,
        "records": records
    }

def generate_password(length=6):
    """توليد كلمة مرور عشوائية"""
    return ''.join(random.choices(string.digits, k=length))

# ------------------ وظائف المساعدة الأصلية ------------------
def get_today_date():
    """الحصول على تاريخ اليوم"""
    return date.today().strftime("%Y-%m-%d")

def arabic_date():
    """الحصول على التاريخ بالعربية"""
    arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
    arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", 
                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
    
    today = datetime.now()
    weekday = arabic_weekdays[today.weekday()]
    month = arabic_months[today.month - 1]
    
    return f"{weekday}، {today.day} {month} {today.year}"

def save_attendance_record(record):
    """حفظ سجل حضور"""
    st.session_state.attendance_data.append(record)
    return True

def get_attendance_records():
    """الحصول على سجلات الحضور"""
    return st.session_state.attendance_data

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
    try:
        st.session_state.attendance_data = [r for r in st.session_state.attendance_data 
                                          if r.get("id") != record_id]
        return True
    except:
        return False

def add_student(student_name, class_name, password):
    """إضافة طالب جديد"""
    if student_name not in CLASSES[class_name]:
        CLASSES[class_name].append(student_name)
        STUDENT_PASSWORDS[student_name] = password
        USERS[student_name] = {
            "password": password,
            "role": "student",
            "name": student_name,
            "class": class_name
        }
        return True
    return False

def delete_student(student_name):
    """حذف طالب"""
    # البحث عن الفصل الذي ينتمي إليه الطالب
    for class_name, students in CLASSES.items():
        if student_name in students:
            CLASSES[class_name].remove(student_name)
            if student_name in STUDENT_PASSWORDS:
                del STUDENT_PASSWORDS[student_name]
            if student_name in USERS:
                del USERS[student_name]
            return True, class_name
    return False, None

def add_class(class_name, teacher_name=None):
    """إضافة فصل جديد"""
    if class_name not in CLASSES:
        CLASSES[class_name] = []
        if teacher_name and teacher_name in TEACHERS:
            TEACHERS[teacher_name].append(class_name)
        return True
    return False

def delete_class(class_name):
    """حذف فصل"""
    if class_name in CLASSES:
        # إزالة الفصل من قوائم المعلمين
        for teacher in TEACHERS:
            if class_name in TEACHERS[teacher]:
                TEACHERS[teacher].remove(class_name)
        
        # حذف الفصل
        del CLASSES[class_name]
        return True
    return False

def add_teacher(teacher_name, password, classes):
    """إضافة معلم جديد"""
    if teacher_name not in TEACHERS:
        TEACHERS[teacher_name] = classes
        USERS[teacher_name] = {
            "password": password,
            "role": "teacher",
            "name": teacher_name,
            "classes": classes
        }
        return True
    return False

def delete_teacher(teacher_name):
    """حذف معلم"""
    if teacher_name in TEACHERS:
        del TEACHERS[teacher_name]
        if teacher_name in USERS:
            del USERS[teacher_name]
        return True
    return False

# ------------------ CSS محسّن ------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    
    #MainMenu, header, footer {visibility: hidden !important;}
    
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
    }
    
    .top-toolbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        height: 80px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 30px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.1);
        z-index: 999999;
        color: white;
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
        border: 2px solid rgba(255,255,255,0.3);
        background: white;
        padding: 4px;
    }
    
    .school-info {
        line-height: 1.3;
    }
    
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
    
    .content-padding {
        height: 90px;
    }
    
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
    
    .action-button {
        margin: 5px 0;
        padding: 10px 20px;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        cursor: pointer;
        transition: all 0.3s;
        width: 100%;
    }
    
    .btn-primary {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    
    .btn-secondary {
        background: linear-gradient(135deg, #6b7280, #4b5563);
        color: white;
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
    
    .admin-card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        margin-bottom: 20px;
        border-left: 5px solid #3b82f6;
    }
    
    .stat-card {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        text-align: center;
        border-top: 4px solid;
    }
    
    .stat-card-primary {
        border-color: #3b82f6;
    }
    
    .stat-card-success {
        border-color: #10b981;
    }
    
    .stat-card-warning {
        border-color: #f59e0b;
    }
    
    .stat-card-danger {
        border-color: #ef4444;
    }
    
    .stat-value {
        font-size: 32px;
        font-weight: bold;
        margin: 10px 0;
    }
    
    .stat-label {
        font-size: 14px;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    .data-table {
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
    }
    
    .data-table th {
        background: #f1f5f9;
        padding: 12px;
        text-align: right;
        font-weight: bold;
        border-bottom: 2px solid #e2e8f0;
    }
    
    .data-table td {
        padding: 12px;
        border-bottom: 1px solid #e2e8f0;
    }
    
    .data-table tr:hover {
        background: #f8fafc;
    }
    
    .notification-badge {
        position: absolute;
        top: -5px;
        right: -5px;
        background: #ef4444;
        color: white;
        border-radius: 50%;
        width: 20px;
        height: 20px;
        font-size: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
    }
    
    .event-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        border-left: 4px solid;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
    }
    
    .event-meeting {
        border-color: #3b82f6;
    }
    
    .event-exam {
        border-color: #ef4444;
    }
    
    .event-holiday {
        border-color: #10b981;
    }
    
    .event-other {
        border-color: #8b5cf6;
    }
    
    .chart-container {
        background: white;
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.08);
        margin: 20px 0;
    }
    
    .quick-action {
        text-align: center;
        padding: 15px;
        border-radius: 10px;
        background: white;
        box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        transition: transform 0.2s;
        cursor: pointer;
        height: 100%;
    }
    
    .quick-action:hover {
        transform: translateY(-5px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    
    .quick-action-icon {
        font-size: 24px;
        margin-bottom: 10px;
    }
    
    .status-present {
        color: green;
        font-weight: bold;
    }
    
    .status-excused {
        color: orange;
        font-weight: bold;
    }
    
    .status-unexcused {
        color: red;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

def show_toolbar():
    """عرض شريط الأدوات العلوي"""
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">مدرسة السلام الإعدادية الثانويه المشتركه</p>
                <p class="school-date">{arabic_date()}</p>
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
        username = st.text_input("اسم المستخدم", 
                                placeholder="أدخل اسم المستخدم",
                                label_visibility="collapsed",
                                key="login_username")
        
        password = st.text_input("كلمة المرور", 
                                type="password",
                                placeholder="أدخل كلمة المرور",
                                label_visibility="collapsed",
                                key="login_password")
        
        if st.button("✅ تسجيل الدخول", use_container_width=True, key="login_button"):
            if username and password:
                if username in USERS:
                    if USERS[username]["password"] == password:
                        st.session_state.logged_in = True
                        st.session_state.user_name = username
                        st.session_state.user_role = USERS[username]["role"]
                        st.session_state.page = "home"
                        
                        st.success(f"✅ مرحباً {username}!")
                        st.rerun()
                    else:
                        st.error("❌ كلمة المرور غير صحيحة")
                else:
                    st.error("❌ اسم المستخدم غير موجود")
            else:
                st.warning("⚠️ من فضلك أدخل اسم المستخدم وكلمة المرور")

# ------------------ إذا كان المستخدم مسجلاً دخوله ------------------
elif st.session_state.logged_in:
    show_toolbar()
    
    # ------------------ الصفحة الرئيسية ------------------
    if st.session_state.page == "home":
        st.markdown("# 🏠 الصفحة الرئيسية")
        
        # عرض معلومات المستخدم
        role_badge = ""
        if st.session_state.user_role == "admin":
            role_badge = '<span class="user-type-badge badge-admin">👑 مدير النظام</span>'
        elif st.session_state.user_role == "teacher":
            role_badge = '<span class="user-type-badge badge-teacher">👨‍🏫 معلم</span>'
        else:
            role_badge = '<span class="user-type-badge badge-student">👨‍🎓 طالب</span>'
        
        welcome_html = f"""
        <div class="welcome-message">
            <div class="welcome-text">مرحباً بك {role_badge} {st.session_state.user_name}</div>
            <div class="user-info">اختر المهمة التي تريد تنفيذها:</div>
        </div>
        """
        st.markdown(welcome_html, unsafe_allow_html=True)
        
        # الأزرار حسب نوع المستخدم
        if st.session_state.user_role == "admin":
            st.markdown("### ⚡ الإجراءات السريعة")
            
            # صف الإجراءات السريعة 1
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("👥 إدارة الطلاب", use_container_width=True, key="quick_manage_students"):
                    st.session_state.page = "manage_students"
                    st.rerun()
            
            with col2:
                if st.button("🏫 إدارة الفصول", use_container_width=True, key="quick_manage_classes"):
                    st.session_state.page = "manage_classes"
                    st.rerun()
            
            with col3:
                if st.button("👨‍🏫 إدارة المعلمين", use_container_width=True, key="quick_manage_teachers"):
                    st.session_state.page = "manage_teachers"
                    st.rerun()
            
            # صف الإجراءات السريعة 2
            col4, col5, col6 = st.columns(3)
            
            with col4:
                if st.button("📋 إدارة الغياب", use_container_width=True, key="quick_manage_attendance"):
                    st.session_state.page = "manage_attendance"
                    st.rerun()
            
            with col5:
                if st.button("📊 التقارير والإحصائيات", use_container_width=True, key="quick_reports"):
                    st.session_state.page = "reports"
                    st.rerun()
            
            with col6:
                if st.button("📥 استيراد/تصدير", use_container_width=True, key="quick_import_export"):
                    st.session_state.page = "import_export"
                    st.rerun()
            
            st.markdown("---")
            
            # لوحة الإحصائيات
            st.markdown("### 📊 لوحة إحصائيات النظام")
            
            # جمع الإحصائيات
            total_students = sum(len(students) for students in CLASSES.values())
            total_classes = len(CLASSES)
            total_teachers = len(TEACHERS)
            total_records = len(st.session_state.attendance_data)
            present_count = len([r for r in st.session_state.attendance_data if r["status"] == "حاضر"])
            attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
            
            # عرض الإحصائيات
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.markdown(f"""
                <div class="stat-card stat-card-primary">
                    <div class="stat-value">{total_students}</div>
                    <div class="stat-label">الطلاب</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col2:
                st.markdown(f"""
                <div class="stat-card stat-card-success">
                    <div class="stat-value">{total_classes}</div>
                    <div class="stat-label">الفصول</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col3:
                st.markdown(f"""
                <div class="stat-card stat-card-warning">
                    <div class="stat-value">{total_teachers}</div>
                    <div class="stat-label">المعلمين</div>
                </div>
                """, unsafe_allow_html=True)
            
            with col4:
                st.markdown(f"""
                <div class="stat-card stat-card-danger">
                    <div class="stat-value">{attendance_rate:.1f}%</div>
                    <div class="stat-label">نسبة الحضور</div>
                </div>
                """, unsafe_allow_html=True)
            
            # عرض توزيع الطلاب على الفصول
            st.markdown("#### 📊 توزيع الطلاب على الفصول")
            
            for class_name, students in CLASSES.items():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**{class_name}**")
                with col2:
                    st.write(f"**{len(students)}** طالب")
                
                # شريط التقدم
                progress = len(students) / max(len(s) for s in CLASSES.values()) if CLASSES.values() else 0
                st.progress(progress)
        
        elif st.session_state.user_role == "teacher":
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("📝 تسجيل الغياب", use_container_width=True, key="record_attendance"):
                    st.session_state.page = "record_attendance"
                    st.rerun()
            
            with col2:
                if st.button("📊 تقارير الحضور", use_container_width=True, key="attendance_reports"):
                    st.session_state.page = "attendance_reports"
                    st.rerun()
        
        else:  # طالب
            if st.button("👨‍🎓 سجل غيابي", use_container_width=True, key="my_attendance"):
                st.session_state.page = "my_attendance"
                st.rerun()
        
        # زر تسجيل الخروج
        st.markdown("---")
        if st.button("🚪 تسجيل الخروج", use_container_width=True, key="logout_button"):
            st.session_state.logged_in = False
            st.session_state.user_role = ""
            st.session_state.user_name = ""
            st.session_state.page = "login"
            st.rerun()
    
    # ------------------ صفحة إدارة الطلاب الكاملة ------------------
    elif st.session_state.page == "manage_students":
        st.markdown("# 👥 إدارة الطلاب")
        
        col1, col2 = st.columns([1, 4])
        with col1:
            if st.button("🏠 الرئيسية", use_container_width=True):
                st.session_state.page = "home"
                st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الطلاب
        tab1, tab2, tab3, tab4 = st.tabs(["📋 عرض الطلاب", "➕ إضافة طالب", "✏️ تعديل طالب", "🗑️ حذف طالب"])
        
        with tab1:
            st.markdown("### 📋 قائمة الطلاب حسب الفصول")
            
            # خيارات البحث والتصفية
            col1, col2 = st.columns(2)
            with col1:
                search_query = st.text_input("🔍 بحث عن طالب", placeholder="اكتب اسم الطالب...")
            with col2:
                filter_class = st.selectbox("تصفية بالفصل", ["الكل"] + list(CLASSES.keys()))
            
            for class_name, students in CLASSES.items():
                if filter_class != "الكل" and filter_class != class_name:
                    continue
                
                # تطبيق البحث
                display_students = students
                if search_query:
                    display_students = [s for s in students if search_query in s]
                
                if display_students:
                    with st.expander(f"🎯 {class_name} ({len(display_students)}/{len(students)} طالب)"):
                        # إنشاء DataFrame للطلاب
                        student_data = []
                        for idx, student in enumerate(display_students, 1):
                            password = STUDENT_PASSWORDS.get(student, "غير معرف")
                            student_data.append({
                                "م": idx,
                                "اسم الطالب": student,
                                "كلمة المرور": password
                            })
                        
                        df = pd.DataFrame(student_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                        
                        # إحصائيات الفصل
                        col_a, col_b, col_c = st.columns(3)
                        with col_a:
                            st.metric("عدد الطلاب", len(students))
                        with col_b:
                            # حساب نسبة الحضور للفصل
                            class_records = get_class_attendance(class_name)
                            if class_records:
                                present_count = len([r for r in class_records if r["status"] == "حاضر"])
                                attendance_rate = (present_count / len(class_records) * 100) if class_records else 0
                                st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
                            else:
                                st.metric("نسبة الحضور", "0%")
        
        with tab2:
            st.markdown("### ➕ إضافة طالب جديد")
            
            with st.form("add_student_form"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    new_student_name = st.text_input("اسم الطالب*", key="new_student_name")
                
                with col2:
                    new_student_class = st.selectbox("الفصل*", list(CLASSES.keys()), key="new_student_class")
                
                with col3:
                    new_student_password = st.text_input("كلمة المرور*", type="password", key="new_student_password", value=generate_password())
                
                # أزرار الإضافة
                col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 2])
                with col_btn1:
                    submit_add = st.form_submit_button("➕ إضافة الطالب", use_container_width=True)
                with col_btn2:
                    generate_pass = st.form_submit_button("🎲 توليد كلمة مرور", use_container_width=True)
                
                if generate_pass:
                    new_password = generate_password()
                    st.session_state["new_student_password"] = new_password
                    st.info(f"كلمة المرور المولدة: **{new_password}**")
                    st.rerun()
                
                if submit_add:
                    if new_student_name and new_student_class and new_student_password:
                        success = add_student(new_student_name, new_student_class, new_student_password)
                        if success:
                            st.success(f"✅ تم إضافة الطالب {new_student_name} إلى الفصل {new_student_class}")
                            st.rerun()
                        else:
                            st.error("❌ الطالب موجود بالفعل!")
                    else:
                        st.warning("⚠️ من فضلك املأ جميع الحقول المطلوبة (*)")
        
        with tab3:
            st.markdown("### ✏️ تعديل بيانات طالب")
            
            # جمع جميع الطلاب
            all_students = []
            for class_name, students in CLASSES.items():
                for student in students:
                    all_students.append({
                        "name": student,
                        "class": class_name,
                        "password": STUDENT_PASSWORDS.get(student, "")
                    })
            
            if all_students:
                student_options = [f"{s['name']} ({s['class']})" for s in all_students]
                
                selected_student_str = st.selectbox(
                    "اختر الطالب للتعديل",
                    student_options,
                    key="edit_student_select"
                )
                
                if selected_student_str:
                    # استخراج بيانات الطالب
                    selected_name = selected_student_str.split(" (")[0]
                    selected_student = next((s for s in all_students if s["name"] == selected_name), None)
                    
                    if selected_student:
                        with st.form("edit_student_form"):
                            col1, col2, col3 = st.columns(3)
                            
                            with col1:
                                edit_name = st.text_input("اسم الطالب", value=selected_student["name"])
                            
                            with col2:
                                edit_class = st.selectbox(
                                    "الفصل",
                                    list(CLASSES.keys()),
                                    index=list(CLASSES.keys()).index(selected_student["class"])
                                )
                            
                            with col3:
                                edit_password = st.text_input(
                                    "كلمة المرور",
                                    value=selected_student["password"],
                                    type="password"
                                )
                            
                            if st.form_submit_button("💾 حفظ التعديلات", use_container_width=True):
                                if edit_name and edit_class and edit_password:
                                    # حذف الطالب القديم
                                    delete_student(selected_student["name"])
                                    
                                    # إضافة الطالب الجديد
                                    add_student(edit_name, edit_class, edit_password)
                                    
                                    st.success(f"✅ تم تحديث بيانات الطالب بنجاح")
                                    st.rerun()
                                else:
                                    st.warning("⚠️ من فضلك املأ جميع الحقول")
            else:
                st.info("📭 لا يوجد طلاب في النظام")
        
        with tab4:
            st.markdown("### 🗑️ حذف طالب")
            
            # جمع جميع الطلاب في قائمة واحدة
            all_students = []
            for class_name, students in CLASSES.items():
                for student in students:
                    all_students.append({
                        "name": student,
                        "class": class_name
                    })
            
            if all_students:
                student_options = [f"{s['name']} ({s['class']})" for s in all_students]
                
                selected_student_str = st.selectbox(
                    "اختر الطالب للحذف",
                    student_options,
                    key="delete_student_select"
                )
                
                if selected_student_str:
                    # استخراج اسم الطالب من النص المختار
                    selected_student = selected_student_str.split(" (")[0]
                    
                    # عرض معلومات الطالب قبل الحذف
                    st.warning(f"⚠️ أنت على وشك حذف الطالب: **{selected_student}**")
                    
                    # عرض سجل الغياب للطالب
                    student_records = get_student_attendance(selected_student)
                    if student_records:
                        st.info(f"📋 هذا الطالب لديه {len(student_records)} سجل غياب سيتم حذفها أيضاً")
                    
                    col1, col2 = st.columns(2)
                    with col1:
                        confirm = st.checkbox("أقر بأنني أريد حذف هذا الطالب وجميع سجلاته")
                    with col2:
                        if st.button("🗑️ حذف الطالب", use_container_width=True, disabled=not confirm):
                            success, class_name = delete_student(selected_student)
                            if success:
                                st.success(f"✅ تم حذف الطالب {selected_student} من الفصل {class_name}")
                                st.rerun()
                            else:
                                st.error("❌ فشل في حذف الطالب")
            else:
                st.info("📭 لا يوجد طلاب في النظام")
    
    # ------------------ صفحة إدارة الفصول الكاملة ------------------
    elif st.session_state.page == "manage_classes":
        st.markdown("# 🏫 إدارة الفصول")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الفصول
        tab1, tab2, tab3, tab4 = st.tabs(["📋 عرض الفصول", "➕ إضافة فصل", "✏️ تعديل فصل", "🗑️ حذف فصل"])
        
        with tab1:
            st.markdown("### 📋 قائمة الفصول")
            
            # البحث عن فصل
            search_class = st.text_input("🔍 بحث عن فصل", placeholder="اكتب اسم الفصل...")
            
            for class_name, students in CLASSES.items():
                if search_class and search_class.lower() not in class_name.lower():
                    continue
                
                # بطاقة الفصل
                with st.container():
                    st.markdown(f"#### {class_name}")
                    
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.write(f"**عدد الطلاب:** {len(students)}")
                        
                        # عرض المعلم المسؤول
                        teacher_names = []
                        for teacher, classes in TEACHERS.items():
                            if class_name in classes:
                                teacher_names.append(teacher)
                        
                        if teacher_names:
                            st.write(f"**المعلم المسؤول:** {', '.join(teacher_names)}")
                        else:
                            st.write("**المعلم المسؤول:** غير معين")
                        
                        # زر عرض الطلاب
                        with st.expander("👥 عرض قائمة الطلاب"):
                            for student in students:
                                st.write(f"- {student}")
                    
                    with col2:
                        # اختيار معلم جديد
                        teacher_options = ["غير معين"] + list(TEACHERS.keys())
                        
                        # تحديد المعلم الحالي
                        current_teacher = "غير معين"
                        for teacher in TEACHERS:
                            if class_name in TEACHERS[teacher]:
                                current_teacher = teacher
                                break
                        
                        new_teacher = st.selectbox(
                            "تغيير المعلم",
                            teacher_options,
                            index=teacher_options.index(current_teacher) if current_teacher in teacher_options else 0,
                            key=f"change_teacher_{class_name}"
                        )
                        
                        if st.button("💾 حفظ", key=f"save_teacher_{class_name}"):
                            # إزالة الفصل من جميع المعلمين
                            for teacher in TEACHERS:
                                if class_name in TEACHERS[teacher]:
                                    TEACHERS[teacher].remove(class_name)
                            
                            # إضافة الفصل للمعلم الجديد
                            if new_teacher != "غير معين":
                                if new_teacher not in TEACHERS:
                                    TEACHERS[new_teacher] = []
                                if class_name not in TEACHERS[new_teacher]:
                                    TEACHERS[new_teacher].append(class_name)
                            
                            # تحديث بيانات المستخدم للمعلم
                            if new_teacher != "غير معين" and new_teacher in USERS:
                                USERS[new_teacher]["classes"] = TEACHERS[new_teacher]
                            
                            st.success(f"✅ تم تحديث المعلم المسؤول للفصل {class_name}")
                            st.rerun()
                    
                    with col3:
                        # إحصائيات الفصل
                        class_records = get_class_attendance(class_name)
                        if class_records:
                            present_count = len([r for r in class_records if r["status"] == "حاضر"])
                            attendance_rate = (present_count / len(class_records) * 100) if class_records else 0
                            st.metric("الحضور", f"{attendance_rate:.1f}%")
                        else:
                            st.metric("الحضور", "0%")
                    
                    st.markdown("---")
        
        with tab2:
            st.markdown("### ➕ إضافة فصل جديد")
            
            with st.form("add_class_form"):
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    new_class_name = st.text_input("اسم الفصل الجديد*", key="new_class_name")
                
                with col2:
                    new_class_teacher = st.selectbox(
                        "المعلم المسؤول",
                        ["غير معين"] + list(TEACHERS.keys()),
                        key="new_class_teacher"
                    )
                
                with col3:
                    st.write("")  # مسافة
                    st.write("")
                    submit_add = st.form_submit_button("➕ إضافة الفصل", use_container_width=True)
                
                if submit_add:
                    if new_class_name:
                        success = add_class(new_class_name, new_class_teacher if new_class_teacher != "غير معين" else None)
                        if success:
                            st.success(f"✅ تم إضافة الفصل {new_class_name}")
                            st.rerun()
                        else:
                            st.error("❌ الفصل موجود بالفعل!")
                    else:
                        st.warning("⚠️ من فضلك أدخل اسم الفصل")
        
        with tab3:
            st.markdown("### ✏️ تعديل بيانات الفصل")
            
            if CLASSES:
                selected_class = st.selectbox(
                    "اختر الفصل للتعديل",
                    list(CLASSES.keys()),
                    key="edit_class_select"
                )
                
                if selected_class:
                    # عرض الطلاب الحاليين
                    current_students = CLASSES[selected_class]
                    
                    st.markdown(f"#### طلاب الفصل {selected_class}")
                    
                    if current_students:
                        for student in current_students:
                            col1, col2, col3 = st.columns([3, 1, 1])
                            with col1:
                                st.write(student)
                            with col2:
                                new_name = st.text_input("اسم جديد", key=f"edit_{student}_name", placeholder="اترك فارغاً للحفاظ على الاسم")
                            with col3:
                                if st.button("تحديث", key=f"update_{student}"):
                                    if new_name and new_name != student:
                                        # تحديث اسم الطالب في جميع الأماكن
                                        index = CLASSES[selected_class].index(student)
                                        CLASSES[selected_class][index] = new_name
                                        
                                        # تحديث كلمة المرور إذا كانت موجودة
                                        if student in STUDENT_PASSWORDS:
                                            STUDENT_PASSWORDS[new_name] = STUDENT_PASSWORDS[student]
                                            del STUDENT_PASSWORDS[student]
                                        
                                        # تحديث بيانات المستخدم
                                        if student in USERS:
                                            USERS[new_name] = USERS[student]
                                            USERS[new_name]["name"] = new_name
                                            del USERS[student]
                                        
                                        st.success(f"✅ تم تحديث اسم الطالب")
                                        st.rerun()
                    else:
                        st.info("📭 لا يوجد طلاب في هذا الفصل")
                    
                    # إضافة طالب جديد
                    st.markdown("#### إضافة طالب جديد للفصل")
                    col1, col2 = st.columns(2)
                    with col1:
                        new_student_name = st.text_input("اسم الطالب الجديد", key="add_to_class_student")
                    with col2:
                        new_student_pass = st.text_input("كلمة المرور", type="password", key="add_to_class_pass")
                    
                    if st.button("➕ إضافة طالب للفصل", use_container_width=True):
                        if new_student_name and new_student_pass:
                            if new_student_name not in CLASSES[selected_class]:
                                CLASSES[selected_class].append(new_student_name)
                                STUDENT_PASSWORDS[new_student_name] = new_student_pass
                                USERS[new_student_name] = {
                                    "password": new_student_pass,
                                    "role": "student",
                                    "name": new_student_name,
                                    "class": selected_class
                                }
                                st.success(f"✅ تم إضافة الطالب {new_student_name} إلى الفصل {selected_class}")
                                st.rerun()
                            else:
                                st.error("❌ الطالب موجود بالفعل في هذا الفصل")
                        else:
                            st.warning("⚠️ من فضلك املأ جميع الحقول")
            else:
                st.info("📭 لا توجد فصول في النظام")
        
        with tab4:
            st.markdown("### 🗑️ حذف فصل")
            
            # عرض الفصول الفارغة فقط للحذف
            empty_classes = [class_name for class_name, students in CLASSES.items() if len(students) == 0]
            
            if empty_classes:
                selected_class = st.selectbox(
                    "اختر الفصل للحذف",
                    empty_classes,
                    key="delete_class_select"
                )
                
                if selected_class:
                    st.warning(f"⚠️ أنت على وشك حذف الفصل: **{selected_class}**")
                    
                    confirm = st.checkbox("أقر بأنني أريد حذف هذا الفصل")
                    
                    if st.button("🗑️ حذف الفصل", use_container_width=True, disabled=not confirm):
                        success = delete_class(selected_class)
                        if success:
                            st.success(f"✅ تم حذف الفصل {selected_class}")
                            st.rerun()
                        else:
                            st.error("❌ فشل في حذف الفصل")
            else:
                st.info("📭 لا توجد فصول فارغة للحذف")
    
    # ------------------ صفحة إدارة المعلمين الكاملة ------------------
    elif st.session_state.page == "manage_teachers":
        st.markdown("# 👨‍🏫 إدارة المعلمين")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة المعلمين
        tab1, tab2, tab3, tab4 = st.tabs(["📋 عرض المعلمين", "➕ إضافة معلم", "✏️ تعديل معلم", "🗑️ حذف معلم"])
        
        with tab1:
            st.markdown("### 📋 قائمة المعلمين")
            
            for teacher_name, classes in TEACHERS.items():
                with st.container():
                    col1, col2, col3 = st.columns([3, 2, 1])
                    
                    with col1:
                        st.markdown(f"#### {teacher_name}")
                        st.write(f"**الفصول المسؤول عنها:** {', '.join(classes) if classes else 'لا يوجد'}")
                        st.write(f"**عدد الفصول:** {len(classes)}")
                        
                        # عرض تفاصيل الفصول
                        if classes:
                            with st.expander("📚 تفاصيل الفصول"):
                                for class_name in classes:
                                    student_count = len(CLASSES.get(class_name, []))
                                    st.write(f"- {class_name} ({student_count} طالب)")
                    
                    with col2:
                        # تغيير كلمة المرور
                        st.markdown("#### 🔑 تغيير كلمة المرور")
                        new_password = st.text_input(
                            "كلمة المرور الجديدة",
                            type="password",
                            key=f"new_pass_{teacher_name}",
                            placeholder="اترك فارغاً للحفاظ على الكلمة الحالية"
                        )
                        
                        if st.button("💾 حفظ", key=f"change_pass_{teacher_name}"):
                            if new_password:
                                USERS[teacher_name]["password"] = new_password
                                st.success(f"✅ تم تغيير كلمة مرور {teacher_name}")
                                st.rerun()
                    
                    with col3:
                        # إحصائيات المعلم
                        total_students = sum(len(CLASSES.get(class_name, [])) for class_name in classes)
                        st.metric("الطلاب", total_students)
                    
                    st.markdown("---")
        
        with tab2:
            st.markdown("### ➕ إضافة معلم جديد")
            
            with st.form("add_teacher_form"):
                col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
                
                with col1:
                    new_teacher_name = st.text_input("اسم المعلم*", key="new_teacher_name")
                
                with col2:
                    new_teacher_password = st.text_input("كلمة المرور*", type="password", key="new_teacher_password", value=generate_password())
                
                with col3:
                    available_classes = list(CLASSES.keys())
                    new_teacher_classes = st.multiselect(
                        "الفصول المسؤول عنها",
                        available_classes,
                        key="new_teacher_classes"
                    )
                
                with col4:
                    st.write("")
                    st.write("")
                    submit_add = st.form_submit_button("➕ إضافة", use_container_width=True)
                
                if submit_add:
                    if new_teacher_name and new_teacher_password:
                        success = add_teacher(new_teacher_name, new_teacher_password, new_teacher_classes)
                        if success:
                            st.success(f"✅ تم إضافة المعلم {new_teacher_name}")
                            st.rerun()
                        else:
                            st.error("❌ المعلم موجود بالفعل!")
                    else:
                        st.warning("⚠️ من فضلك املأ جميع الحقول المطلوبة (*)")
        
        with tab3:
            st.markdown("### ✏️ تعديل بيانات معلم")
            
            if TEACHERS:
                selected_teacher = st.selectbox(
                    "اختر المعلم للتعديل",
                    list(TEACHERS.keys()),
                    key="edit_teacher_select"
                )
                
                if selected_teacher:
                    current_classes = TEACHERS[selected_teacher]
                    
                    with st.form("edit_teacher_form"):
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            # تغيير الفصول
                            available_classes = list(CLASSES.keys())
                            updated_classes = st.multiselect(
                                "الفصول المسؤول عنها",
                                available_classes,
                                default=current_classes,
                                key="updated_teacher_classes"
                            )
                        
                        with col2:
                            # تغيير كلمة المرور
                            st.markdown("#### تغيير كلمة المرور")
                            new_password = st.text_input(
                                "كلمة المرور الجديدة",
                                type="password",
                                placeholder="اترك فارغاً للحفاظ على الكلمة الحالية",
                                key="edit_teacher_password"
                            )
                        
                        if st.form_submit_button("💾 حفظ التعديلات", use_container_width=True):
                            # تحديث الفصول
                            TEACHERS[selected_teacher] = updated_classes
                            
                            # تحديث كلمة المرور إذا تم إدخالها
                            if new_password:
                                USERS[selected_teacher]["password"] = new_password
                            
                            # تحديث بيانات المستخدم
                            if selected_teacher in USERS:
                                USERS[selected_teacher]["classes"] = updated_classes
                            
                            st.success(f"✅ تم تحديث بيانات المعلم {selected_teacher}")
                            st.rerun()
            else:
                st.info("📭 لا يوجد معلمين في النظام")
        
        with tab4:
            st.markdown("### 🗑️ حذف معلم")
            
            # عرض المعلمين الذين يمكن حذفهم (ليسوا معلمين أساسيين)
            deletable_teachers = [t for t in TEACHERS.keys() 
                                if t not in ["مينا سمير", "فادي حبيب"]]
            
            if deletable_teachers:
                selected_teacher = st.selectbox(
                    "اختر المعلم للحذف",
                    deletable_teachers,
                    key="delete_teacher_select"
                )
                
                if selected_teacher:
                    teacher_classes = TEACHERS[selected_teacher]
                    
                    if teacher_classes:
                        st.warning(f"⚠️ المعلم {selected_teacher} مسؤول عن الفصول التالية:")
                        for class_name in teacher_classes:
                            st.write(f"- {class_name}")
                        
                        st.info("اختر معلم لنقل الفصول إليه:")
                        
                        other_teachers = [t for t in deletable_teachers if t != selected_teacher]
                        
                        if other_teachers:
                            transfer_to = st.selectbox(
                                "نقل الفصول إلى",
                                other_teachers,
                                key="transfer_teacher_select"
                            )
                            
                            if st.button("✅ نقل وحذف", use_container_width=True, key="confirm_delete_transfer"):
                                # نقل الفصول
                                for class_name in teacher_classes:
                                    if class_name not in TEACHERS[transfer_to]:
                                        TEACHERS[transfer_to].append(class_name)
                                
                                # حذف المعلم
                                delete_teacher(selected_teacher)
                                
                                # تحديث بيانات المستخدم للمعلم الجديد
                                if transfer_to in USERS:
                                    USERS[transfer_to]["classes"] = TEACHERS[transfer_to]
                                
                                st.success(f"✅ تم نقل الفصول إلى {transfer_to} وحذف {selected_teacher}")
                                st.rerun()
                        else:
                            st.error("❌ لا يوجد معلمين آخرين لنقل الفصول إليهم!")
                    else:
                        if st.button("🗑️ حذف المعلم", use_container_width=True, key="confirm_delete_teacher"):
                            delete_teacher(selected_teacher)
                            st.success(f"✅ تم حذف المعلم {selected_teacher}")
                            st.rerun()
            else:
                st.info("📭 لا يوجد معلمين يمكن حذفهم")
    
    # ------------------ صفحة إدارة سجلات الغياب الكاملة ------------------
    elif st.session_state.page == "manage_attendance":
        st.markdown("# 📋 إدارة سجلات الغياب")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الغياب
        tab1, tab2, tab3, tab4 = st.tabs(["🔍 البحث والتصفية", "✏️ تعديل السجلات", "🗑️ حذف السجلات", "📊 الإحصائيات"])
        
        with tab1:
            st.markdown("### 🔍 البحث في سجلات الغياب")
            
            with st.form("search_form"):
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    search_student = st.text_input("بحث باسم الطالب", key="search_student")
                
                with col2:
                    search_class = st.selectbox(
                        "تصفية بالفصل",
                        ["الكل"] + list(CLASSES.keys()),
                        key="search_class"
                    )
                
                with col3:
                    search_status = st.selectbox(
                        "تصفية بالحالة",
                        ["الكل", "حاضر", "غياب بعذر", "غياب بدون عذر"],
                        key="search_status"
                    )
                
                with col4:
                    date_range = st.checkbox("تحديد نطاق تاريخي")
                
                if date_range:
                    col5, col6 = st.columns(2)
                    with col5:
                        start_date = st.date_input("من تاريخ")
                    with col6:
                        end_date = st.date_input("إلى تاريخ")
                
                search_submit = st.form_submit_button("🔍 بحث", use_container_width=True)
            
            # الحصول على سجلات الغياب
            attendance_records = get_attendance_records()
            
            if attendance_records:
                # تحويل إلى DataFrame للبحث
                records_df = pd.DataFrame(attendance_records)
                
                # تطبيق البحث
                if search_student:
                    records_df = records_df[records_df["student"].str.contains(search_student, na=False)]
                
                if search_class != "الكل":
                    records_df = records_df[records_df["class"] == search_class]
                
                if search_status != "الكل":
                    records_df = records_df[records_df["status"] == search_status]
                
                if date_range:
                    records_df["date_dt"] = pd.to_datetime(records_df["date"])
                    records_df = records_df[(records_df["date_dt"] >= pd.Timestamp(start_date)) & 
                                          (records_df["date_dt"] <= pd.Timestamp(end_date))]
                    records_df = records_df.drop(columns=["date_dt"])
                
                st.markdown(f"### 📋 النتائج ({len(records_df)} سجل)")
                
                if not records_df.empty:
                    # إعادة تسمية الأعمدة للعرض
                    display_df = records_df[["date", "student", "class", "teacher", "status"]].copy()
                    display_df = display_df.rename(columns={
                        "date": "التاريخ",
                        "student": "الطالب",
                        "class": "الفصل",
                        "teacher": "المعلم",
                        "status": "الحالة"
                    })
                    
                    # تنسيق الألوان حسب الحالة
                    def color_status(val):
                        if val == "حاضر":
                            return 'color: green; font-weight: bold'
                        elif "بعذر" in val:
                            return 'color: orange; font-weight: bold'
                        else:
                            return 'color: red; font-weight: bold'
                    
                    styled_df = display_df.style.applymap(color_status, subset=['الحالة'])
                    
                    st.dataframe(styled_df, use_container_width=True, hide_index=True)
                    
                    # زر تصدير النتائج
                    csv_data = display_df.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 تصدير النتائج (CSV)",
                        data=csv_data,
                        file_name=f"نتائج_البحث_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("📭 لا توجد سجلات مطابقة لبحثك")
            else:
                st.info("📭 لا توجد سجلات غياب في النظام")
        
        with tab2:
            st.markdown("### ✏️ تعديل سجلات الغياب")
            
            attendance_records = get_attendance_records()
            
            if attendance_records:
                # اختيار السجل للتعديل
                record_options = []
                for record in attendance_records:
                    option_text = f"{record['date']} - {record['student']} - {record['status']}"
                    record_options.append(option_text)
                
                selected_record_text = st.selectbox(
                    "اختر سجل للتعديل",
                    record_options,
                    key="edit_record_select"
                )
                
                if selected_record_text:
                    # استخراج بيانات السجل المختار
                    record_index = record_options.index(selected_record_text)
                    selected_record = attendance_records[record_index]
                    
                    with st.form("edit_record_form"):
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            new_date = st.date_input(
                                "التاريخ",
                                value=datetime.strptime(selected_record["date"], "%Y-%m-%d").date()
                            )
                        
                        with col2:
                            new_status = st.selectbox(
                                "الحالة",
                                ["حاضر", "غياب بعذر", "غياب بدون عذر"],
                                index=["حاضر", "غياب بعذر", "غياب بدون عذر"].index(selected_record["status"])
                            )
                        
                        with col3:
                            st.write("")
                            st.write("")
                            submit_edit = st.form_submit_button("💾 حفظ التعديلات", use_container_width=True)
                        
                        if submit_edit:
                            # تحديث السجل
                            selected_record["date"] = new_date.strftime("%Y-%m-%d")
                            selected_record["status"] = new_status
                            
                            st.success("✅ تم تحديث السجل بنجاح")
                            st.rerun()
            else:
                st.info("📭 لا توجد سجلات للتعديل")
        
        with tab3:
            st.markdown("### 🗑️ حذف سجلات الغياب")
            
            attendance_records = get_attendance_records()
            
            if attendance_records:
                st.warning("⚠️ خيارات حذف السجلات:")
                
                col1, col2 = st.columns(2)
                
                with col1:
                    # حذف سجلات طالب محدد
                    all_students = sorted(set([r["student"] for r in attendance_records]))
                    
                    if all_students:
                        student_to_delete = st.selectbox(
                            "اختر طالب لحذف سجلاته",
                            all_students,
                            key="delete_student_records"
                        )
                        
                        if student_to_delete:
                            student_records = [r for r in attendance_records if r["student"] == student_to_delete]
                            st.info(f"عدد سجلات الطالب: {len(student_records)}")
                            
                            if st.button("🗑️ حذف سجلات الطالب", use_container_width=True):
                                st.session_state.attendance_data = [r for r in attendance_records 
                                                                   if r["student"] != student_to_delete]
                                st.success(f"✅ تم حذف {len(student_records)} سجل للطالب {student_to_delete}")
                                st.rerun()
                
                with col2:
                    # حذف سجلات فترة محددة
                    st.markdown("#### حذف سجلات فترة محددة")
                    
                    col_a, col_b = st.columns(2)
                    with col_a:
                        delete_start_date = st.date_input("من تاريخ", key="delete_start")
                    with col_b:
                        delete_end_date = st.date_input("إلى تاريخ", key="delete_end")
                    
                    if delete_start_date and delete_end_date:
                        period_records = [r for r in attendance_records 
                                        if delete_start_date <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= delete_end_date]
                        
                        st.info(f"عدد السجلات في الفترة: {len(period_records)}")
                        
                        if st.button("🗑️ حذف سجلات الفترة", use_container_width=True):
                            st.session_state.attendance_data = [r for r in attendance_records 
                                                               if not (delete_start_date <= datetime.strptime(r["date"], "%Y-%m-%d").date() <= delete_end_date)]
                            st.success(f"✅ تم حذف {len(period_records)} سجل")
                            st.rerun()
                
                st.markdown("---")
                
                # حذف جميع السجلات
                st.markdown("#### حذف جميع السجلات")
                st.info(f"إجمالي السجلات: {len(attendance_records)}")
                
                confirm_all = st.checkbox("أقر بأنني أريد حذف جميع السجلات")
                
                if st.button("🗑️ حذف جميع السجلات", use_container_width=True, disabled=not confirm_all):
                    st.session_state.attendance_data = []
                    st.success("✅ تم حذف جميع السجلات")
                    st.rerun()
            else:
                st.info("📭 لا توجد سجلات لحذفها")
        
        with tab4:
            st.markdown("### 📊 إحصائيات الغياب")
            
            attendance_records = get_attendance_records()
            
            if attendance_records:
                # تحويل إلى DataFrame
                records_df = pd.DataFrame(attendance_records)
                
                # الإحصائيات العامة
                total_records = len(records_df)
                present_count = len(records_df[records_df["status"] == "حاضر"])
                absent_excused = len(records_df[records_df["status"] == "غياب بعذر"])
                absent_unexcused = len(records_df[records_df["status"] == "غياب بدون عذر"])
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("إجمالي السجلات", total_records)
                
                with col2:
                    st.metric("عدد الحضور", present_count)
                
                with col3:
                    st.metric("غياب بعذر", absent_excused)
                
                with col4:
                    st.metric("غياب بدون عذر", absent_unexcused)
                
                st.markdown("---")
                
                # إحصائيات حسب الفصول
                st.markdown("#### 📊 إحصائيات الفصول")
                
                class_stats = []
                for class_name in CLASSES.keys():
                    class_records = records_df[records_df["class"] == class_name]
                    if len(class_records) > 0:
                        class_present = len(class_records[class_records["status"] == "حاضر"])
                        class_absent_excused = len(class_records[class_records["status"] == "غياب بعذر"])
                        class_absent_unexcused = len(class_records[class_records["status"] == "غياب بدون عذر"])
                        class_total = len(class_records)
                        
                        class_stats.append({
                            "الفصل": class_name,
                            "إجمالي السجلات": class_total,
                            "الحضور": class_present,
                            "غياب بعذر": class_absent_excused,
                            "غياب بدون عذر": class_absent_unexcused,
                            "نسبة الحضور": f"{(class_present/class_total*100):.1f}%" if class_total > 0 else "0%"
                        })
                
                if class_stats:
                    stats_df = pd.DataFrame(class_stats)
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)
                    
                    # عرض نسب الحضور
                    st.markdown("#### 📈 نسب الحضور")
                    
                    for stat in class_stats:
                        col1, col2, col3 = st.columns([2, 3, 1])
                        with col1:
                            st.write(f"**{stat['الفصل']}**")
                        with col2:
                            progress = int(stat['نسبة الحضور'].replace('%', '')) / 100
                            st.progress(progress)
                        with col3:
                            st.write(f"**{stat['نسبة الحضور']}**")
                else:
                    st.info("📭 لا توجد سجلات للفصول")
            else:
                st.info("📭 لا توجد سجلات لعرض الإحصائيات")
    
    # ------------------ صفحة التقارير والإحصائيات ------------------
    elif st.session_state.page == "reports":
        st.markdown("# 📊 التقارير والإحصائيات")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات التقارير
        tab1, tab2, tab3, tab4 = st.tabs(["📈 تقارير الفصول", "👤 تقارير الطلاب", "👨‍🏫 تقارير المعلمين", "📅 التقارير الزمنية"])
        
        with tab1:
            st.markdown("### 📈 تقارير الفصول")
            
            selected_class = st.selectbox(
                "اختر الفصل",
                list(CLASSES.keys()),
                key="class_report_select"
            )
            
            if selected_class:
                # نطاق التاريخ
                col1, col2 = st.columns(2)
                with col1:
                    start_date = st.date_input("من تاريخ", key="class_start_date")
                with col2:
                    end_date = st.date_input("إلى تاريخ", key="class_end_date")
                
                if st.button("📊 إنشاء التقرير", use_container_width=True):
                    report = generate_class_report(
                        selected_class,
                        start_date.strftime("%Y-%m-%d") if start_date else None,
                        end_date.strftime("%Y-%m-%d") if end_date else None
                    )
                    
                    if report:
                        st.markdown(f"#### تقرير الفصل: {selected_class}")
                        
                        # عرض إحصائيات الفصل
                        col_a, col_b, col_c, col_d = st.columns(4)
                        
                        with col_a:
                            st.metric("عدد الطلاب", report["total_students"])
                        
                        with col_b:
                            st.metric("إجمالي السجلات", report["total_records"])
                        
                        with col_c:
                            st.metric("نسبة الحضور", f"{report['attendance_rate']:.1f}%")
                        
                        with col_d:
                            absences = report["absent_excused"] + report["absent_unexcused"]
                            st.metric("إجمالي الغياب", absences)
                        
                        st.markdown("---")
                        
                        # تفاصيل الطلاب
                        st.markdown("#### 📋 تفاصيل الطلاب")
                        
                        if report["student_reports"]:
                            student_df = pd.DataFrame(report["student_reports"])
                            st.dataframe(student_df, use_container_width=True, hide_index=True)
                            
                            # عرض نسب الحضور للطلاب
                            st.markdown("#### 📊 نسب الحضور للطلاب")
                            
                            for student_report in report["student_reports"]:
                                col1, col2, col3 = st.columns([3, 3, 1])
                                with col1:
                                    st.write(f"**{student_report['student_name']}**")
                                with col2:
                                    progress = student_report['attendance_rate'] / 100
                                    st.progress(progress)
                                with col3:
                                    st.write(f"**{student_report['attendance_rate']:.1f}%**")
                        
                        # زر تصدير التقرير
                        csv_data = pd.DataFrame(report["student_reports"]).to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="📥 تصدير تقرير الفصل",
                            data=csv_data,
                            file_name=f"تقرير_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    else:
                        st.info("📭 لا توجد بيانات للفصل في هذه الفترة")
        
        with tab2:
            st.markdown("### 👤 تقارير الطلاب")
            
            # جمع جميع الطلاب
            all_students = []
            for class_name, students in CLASSES.items():
                for student in students:
                    all_students.append({
                        "name": student,
                        "class": class_name
                    })
            
            if all_students:
                student_options = [f"{s['name']} ({s['class']})" for s in all_students]
                
                selected_student_str = st.selectbox(
                    "اختر الطالب",
                    student_options,
                    key="student_report_select"
                )
                
                if selected_student_str:
                    selected_student = selected_student_str.split(" (")[0]
                    
                    # نطاق التاريخ
                    col1, col2 = st.columns(2)
                    with col1:
                        start_date = st.date_input("من تاريخ", key="student_start_date")
                    with col2:
                        end_date = st.date_input("إلى تاريخ", key="student_end_date")
                    
                    if st.button("📊 إنشاء التقرير", use_container_width=True):
                        report = generate_student_report(
                            selected_student,
                            start_date.strftime("%Y-%m-%d") if start_date else None,
                            end_date.strftime("%Y-%m-%d") if end_date else None
                        )
                        
                        if report:
                            st.markdown(f"#### تقرير الطالب: {selected_student}")
                            
                            # إحصائيات الطالب
                            col_a, col_b, col_c, col_d = st.columns(4)
                            
                            with col_a:
                                st.metric("إجمالي الأيام", report["total_days"])
                            
                            with col_b:
                                st.metric("أيام الحضور", report["present_count"])
                            
                            with col_c:
                                st.metric("نسبة الحضور", f"{report['attendance_rate']:.1f}%")
                            
                            with col_d:
                                total_absent = report["absent_excused"] + report["absent_unexcused"]
                                st.metric("إجمالي الغياب", total_absent)
                            
                            # تفاصيل الغياب
                            col_x, col_y = st.columns(2)
                            with col_x:
                                st.metric("غياب بعذر", report["absent_excused"])
                            with col_y:
                                st.metric("غياب بدون عذر", report["absent_unexcused"])
                            
                            st.markdown("---")
                            
                            # سجلات الطالب
                            st.markdown("#### 📋 سجل الغياب")
                            
                            if report["records"]:
                                records_df = pd.DataFrame(report["records"])
                                display_df = records_df[["date", "class", "teacher", "status"]].copy()
                                display_df = display_df.rename(columns={
                                    "date": "التاريخ",
                                    "class": "الفصل",
                                    "teacher": "المعلم",
                                    "status": "الحالة"
                                })
                                
                                st.dataframe(display_df, use_container_width=True, hide_index=True)
                                
                                # عرض نسب الحضور
                                st.markdown("#### 📊 توزيع حالات الحضور")
                                
                                status_data = pd.DataFrame({
                                    "الحالة": ["حاضر", "غياب بعذر", "غياب بدون عذر"],
                                    "العدد": [report["present_count"], report["absent_excused"], report["absent_unexcused"]]
                                })
                                
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("حاضر", report["present_count"])
                                with col2:
                                    st.metric("غياب بعذر", report["absent_excused"])
                                with col3:
                                    st.metric("غياب بدون عذر", report["absent_unexcused"])
                            
                            # زر تصدير التقرير
                            csv_data = display_df.to_csv(index=False, encoding='utf-8-sig')
                            st.download_button(
                                label="📥 تصدير تقرير الطالب",
                                data=csv_data,
                                file_name=f"تقرير_الطالب_{selected_student}_{datetime.now().strftime('%Y%m%d')}.csv",
                                mime="text/csv",
                                use_container_width=True
                            )
                        else:
                            st.info("📭 لا توجد بيانات للطالب في هذه الفترة")
            else:
                st.info("📭 لا يوجد طلاب في النظام")
        
        with tab3:
            st.markdown("### 👨‍🏫 تقارير المعلمين")
            
            if TEACHERS:
                selected_teacher = st.selectbox(
                    "اختر المعلم",
                    list(TEACHERS.keys()),
                    key="teacher_report_select"
                )
                
                if selected_teacher:
                    teacher_classes = TEACHERS[selected_teacher]
                    
                    st.markdown(f"#### المعلم: {selected_teacher}")
                    st.markdown(f"**الفصول المسؤول عنها:** {', '.join(teacher_classes)}")
                    
                    # إحصائيات المعلم
                    attendance_records = get_attendance_records()
                    teacher_records = [r for r in attendance_records if r["teacher"] == selected_teacher]
                    
                    if teacher_records:
                        # تحليل البيانات
                        total_records = len(teacher_records)
                        present_count = len([r for r in teacher_records if r["status"] == "حاضر"])
                        absent_excused = len([r for r in teacher_records if r["status"] == "غياب بعذر"])
                        absent_unexcused = len([r for r in teacher_records if r["status"] == "غياب بدون عذر"])
                        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            st.metric("إجمالي السجلات", total_records)
                        
                        with col2:
                            st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
                        
                        with col3:
                            st.metric("إجمالي الطلاب", sum(len(CLASSES[c]) for c in teacher_classes))
                        
                        with col4:
                            st.metric("عدد الفصول", len(teacher_classes))
                        
                        st.markdown("---")
                        
                        # إحصائيات كل فصل
                        st.markdown("#### 📊 إحصائيات الفصول")
                        
                        class_stats = []
                        for class_name in teacher_classes:
                            class_records = [r for r in teacher_records if r["class"] == class_name]
                            if class_records:
                                class_present = len([r for r in class_records if r["status"] == "حاضر"])
                                class_absent = len(class_records) - class_present
                                class_rate = (class_present / len(class_records) * 100) if class_records else 0
                                
                                class_stats.append({
                                    "الفصل": class_name,
                                    "عدد السجلات": len(class_records),
                                    "الحضور": class_present,
                                    "الغياب": class_absent,
                                    "نسبة الحضور": f"{class_rate:.1f}%"
                                })
                        
                        if class_stats:
                            stats_df = pd.DataFrame(class_stats)
                            st.dataframe(stats_df, use_container_width=True, hide_index=True)
                            
                            # عرض نسب الحضور
                            st.markdown("#### 📈 نسب الحضور للفصول")
                            
                            for stat in class_stats:
                                col1, col2, col3 = st.columns([2, 3, 1])
                                with col1:
                                    st.write(f"**{stat['الفصل']}**")
                                with col2:
                                    progress = int(stat['نسبة الحضور'].replace('%', '')) / 100
                                    st.progress(progress)
                                with col3:
                                    st.write(f"**{stat['نسبة الحضور']}**")
                    else:
                        st.info("📭 لا توجد سجلات للمعلم")
            else:
                st.info("📭 لا يوجد معلمين في النظام")
        
        with tab4:
            st.markdown("### 📅 التقارير الزمنية")
            
            # اختيار نوع التقرير
            report_type = st.selectbox(
                "نوع التقرير",
                ["تقرير شهري", "تقرير أسبوعي", "تقرير سنوي"],
                key="time_report_type"
            )
            
            if report_type == "تقرير شهري":
                selected_month = st.selectbox(
                    "اختر الشهر",
                    ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو",
                     "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"],
                    key="month_select"
                )
                
                selected_year = st.number_input("السنة", min_value=2023, max_value=2030, value=2024, key="year_select")
            
            elif report_type == "تقرير أسبوعي":
                selected_week = st.date_input("اختر أسبوع", key="week_select")
            
            else:  # تقرير سنوي
                selected_year = st.number_input("السنة", min_value=2023, max_value=2030, value=2024, key="annual_year_select")
            
            if st.button("📊 إنشاء التقرير الزمني", use_container_width=True):
                st.info("🚧 هذه الميزة قيد التطوير")
    
    # ------------------ صفحة استيراد/تصدير ------------------
    elif st.session_state.page == "import_export":
        st.markdown("# 📥 استيراد/تصدير البيانات")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات الاستيراد والتصدير
        tab1, tab2 = st.tabs(["📤 تصدير البيانات", "📥 استيراد البيانات"])
        
        with tab1:
            st.markdown("### 📤 تصدير البيانات")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # تصدير بيانات الطلاب
                students_data = []
                for class_name, students in CLASSES.items():
                    for student in students:
                        students_data.append({
                            "اسم_الطالب": student,
                            "الفصل": class_name,
                            "كلمة_المرور": STUDENT_PASSWORDS.get(student, "")
                        })
                
                if students_data:
                    students_df = pd.DataFrame(students_data)
                    students_csv = students_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات الطلاب",
                        data=students_csv,
                        file_name=f"بيانات_الطلاب_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("📭 لا توجد بيانات طلاب للتصدير")
            
            with col2:
                # تصدير بيانات الفصول
                classes_data = []
                for class_name, students in CLASSES.items():
                    teacher_names = []
                    for teacher, classes in TEACHERS.items():
                        if class_name in classes:
                            teacher_names.append(teacher)
                    
                    classes_data.append({
                        "اسم_الفصل": class_name,
                        "عدد_الطلاب": len(students),
                        "المعلم_المسؤول": ", ".join(teacher_names) if teacher_names else ""
                    })
                
                if classes_data:
                    classes_df = pd.DataFrame(classes_data)
                    classes_csv = classes_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات الفصول",
                        data=classes_csv,
                        file_name=f"بيانات_الفصول_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("📭 لا توجد بيانات فصول للتصدير")
            
            with col3:
                # تصدير بيانات الغياب
                attendance_records = get_attendance_records()
                
                if attendance_records:
                    attendance_df = pd.DataFrame(attendance_records)
                    attendance_csv = attendance_df.to_csv(index=False, encoding='utf-8-sig')
                    
                    st.download_button(
                        label="📥 تصدير بيانات الغياب",
                        data=attendance_csv,
                        file_name=f"بيانات_الغياب_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                else:
                    st.info("📭 لا توجد بيانات غياب للتصدير")
        
        with tab2:
            st.markdown("### 📥 استيراد البيانات")
            
            uploaded_file = st.file_uploader("اختر ملف CSV للاستيراد", type=['csv'], key="import_file")
            
            if uploaded_file is not None:
                try:
                    # قراءة الملف
                    import_df = pd.read_csv(uploaded_file, encoding='utf-8')
                    st.success(f"✅ تم تحميل الملف بنجاح ({len(import_df)} سطر)")
                    
                    # عرض عينة من البيانات
                    st.dataframe(import_df.head(), use_container_width=True)
                    
                    # تحديد نوع البيانات
                    import_type = st.selectbox(
                        "نوع البيانات للاستيراد",
                        ["بيانات الطلاب", "بيانات الغياب"],
                        key="import_type"
                    )
                    
                    if import_type == "بيانات الطلاب":
                        # التحقق من الأعمدة المطلوبة
                        if "اسم_الطالب" in import_df.columns and "الفصل" in import_df.columns:
                            success_count = 0
                            for _, row in import_df.iterrows():
                                student_name = str(row["اسم_الطالب"]).strip()
                                class_name = str(row["الفصل"]).strip()
                                password = str(row.get("كلمة_المرور", generate_password())).strip()
                                
                                if class_name in CLASSES and student_name not in CLASSES[class_name]:
                                    success = add_student(student_name, class_name, password)
                                    if success:
                                        success_count += 1
                            
                            st.success(f"✅ تم استيراد {success_count} طالب بنجاح")
                            st.rerun()
                        else:
                            st.error("❌ الملف يجب أن يحتوي على أعمدة: اسم_الطالب، الفصل")
                    
                    elif import_type == "بيانات الغياب":
                        # التحقق من الأعمدة المطلوبة
                        required_cols = ["student", "class", "teacher", "status", "date"]
                        missing_cols = [col for col in required_cols if col not in import_df.columns]
                        
                        if not missing_cols:
                            success_count = 0
                            for _, row in import_df.iterrows():
                                record = {
                                    "id": len(st.session_state.attendance_data) + 1,
                                    "date": row["date"],
                                    "student": row["student"],
                                    "class": row["class"],
                                    "teacher": row["teacher"],
                                    "status": row["status"]
                                }
                                save_attendance_record(record)
                                success_count += 1
                            
                            st.success(f"✅ تم استيراد {success_count} سجل غياب بنجاح")
                            st.rerun()
                        else:
                            st.error(f"❌ الملف يفتقد الأعمدة: {', '.join(missing_cols)}")
                
                except Exception as e:
                    st.error(f"❌ خطأ في قراءة الملف: {str(e)}")
    
    # ------------------ صفحة تسجيل الغياب للمعلم ------------------
    elif st.session_state.page == "record_attendance":
        st.markdown("# 📝 تسجيل الغياب")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        teacher_name = st.session_state.user_name
        
        # عرض الفصول التي يدرسها المعلم
        if teacher_name in TEACHERS:
            teacher_classes = TEACHERS[teacher_name]
            
            if teacher_classes:
                selected_class = st.selectbox(
                    "اختر الفصل",
                    teacher_classes,
                    key="select_class_for_attendance"
                )
                
                if selected_class:
                    st.markdown(f"### 🎯 الفصل: {selected_class}")
                    
                    # عرض طلاب الفصل
                    students = CLASSES.get(selected_class, [])
                    
                    if students:
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("المعلم", teacher_name)
                        
                        with col2:
                            st.metric("الفصل", selected_class)
                        
                        with col3:
                            st.metric("عدد الطلاب", len(students))
                        
                        st.markdown("---")
                        
                        # اختيار الطلاب الغائبين
                        st.markdown("### 👇 اختر الطلاب الغائبين")
                        
                        selected_absent = st.multiselect(
                            "الطلاب الغائبين",
                            students,
                            key="select_absent_students"
                        )
                        
                        # نوع الغياب
                        col_a, col_b = st.columns(2)
                        
                        with col_a:
                            excuse = st.checkbox("غياب بعذر", key="excuse_checkbox")
                        
                        with col_b:
                            no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse_checkbox")
                        
                        if excuse and no_excuse:
                            st.warning("⚠️ اختر نوع واحد فقط من الغياب")
                        
                        # زر الحفظ
                        if st.button("💾 حفظ وتسجيل الغياب", use_container_width=True):
                            if excuse or no_excuse:
                                status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                                today_date = get_today_date()
                                
                                # تسجيل حضور جميع طلاب الفصل
                                for student in students:
                                    record_id = len(st.session_state.attendance_data) + 1
                                    
                                    if student in selected_absent:
                                        status = status_label
                                    else:
                                        status = "حاضر"
                                    
                                    record = {
                                        "id": record_id,
                                        "date": today_date,
                                        "student": student,
                                        "class": selected_class,
                                        "teacher": teacher_name,
                                        "status": status
                                    }
                                    
                                    save_attendance_record(record)
                                
                                st.success(f"✅ تم تسجيل الغياب بنجاح")
                                st.info(f"📊 الحاضرون: {len(students) - len(selected_absent)} | الغائبون: {len(selected_absent)}")
                            else:
                                st.warning("⚠️ من فضلك اختر نوع الغياب")
                    else:
                        st.warning("⚠️ لا يوجد طلاب في هذا الفصل")
            else:
                st.warning("⚠️ لا توجد فصول مخصصة لك")
        else:
            st.error("❌ بيانات المعلم غير موجودة")
    
    # ------------------ صفحة تقارير الحضور للمعلم ------------------
    elif st.session_state.page == "attendance_reports":
        st.markdown("# 📊 تقارير الحضور")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        teacher_name = st.session_state.user_name
        
        if teacher_name in TEACHERS:
            teacher_classes = TEACHERS[teacher_name]
            
            if teacher_classes:
                selected_class = st.selectbox(
                    "اختر الفصل لعرض التقارير",
                    teacher_classes,
                    key="select_class_for_report"
                )
                
                if selected_class:
                    # الحصول على سجلات الفصل
                    class_records = get_class_attendance(selected_class)
                    
                    if class_records:
                        st.markdown(f"### 📋 سجل غياب الفصل: {selected_class}")
                        
                        # تحويل السجلات إلى DataFrame
                        records_df = pd.DataFrame(class_records)
                        
                        # إعادة تسمية الأعمدة
                        display_df = records_df[["date", "student", "status"]].copy()
                        display_df = display_df.rename(columns={
                            "date": "التاريخ",
                            "student": "الطالب",
                            "status": "الحالة"
                        })
                        
                        st.dataframe(display_df, use_container_width=True, hide_index=True)
                        
                        # الإحصائيات
                        st.markdown("### 📈 إحصائيات الفصل")
                        
                        total_records = len(records_df)
                        present_count = len(records_df[records_df["status"] == "حاضر"])
                        absent_count = len(records_df[records_df["status"].str.contains("غياب")])
                        
                        col1, col2, col3 = st.columns(3)
                        
                        with col1:
                            st.metric("إجمالي السجلات", total_records)
                        
                        with col2:
                            st.metric("عدد الحضور", present_count)
                        
                        with col3:
                            st.metric("عدد الغياب", absent_count)
                        
                        # زر التصدير
                        csv_data = display_df.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="📥 تصدير تقرير الفصل",
                            data=csv_data,
                            file_name=f"تقرير_الفصل_{selected_class}_{datetime.now().strftime('%Y%m%d')}.csv",
                            mime="text/csv",
                            use_container_width=True
                        )
                    else:
                        st.info(f"📭 لا توجد سجلات غياب للفصل {selected_class}")
            else:
                st.warning("⚠️ لا توجد فصول مخصصة لك")
        else:
            st.error("❌ بيانات المعلم غير موجودة")
    
    # ------------------ صفحة سجل الغياب للطالب ------------------
    elif st.session_state.page == "my_attendance":
        st.markdown("# 👨‍🎓 سجل غيابي")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        student_name = st.session_state.user_name
        
        # الحصول على سجلات الطالب
        student_records = get_student_attendance(student_name)
        
        if student_records:
            st.markdown(f"### 📋 سجل الغياب للطالب: {student_name}")
            
            # تحويل السجلات إلى DataFrame
            records_df = pd.DataFrame(student_records)
            
            # إعادة تسمية الأعمدة
            display_df = records_df[["date", "class", "teacher", "status"]].copy()
            display_df = display_df.rename(columns={
                "date": "التاريخ",
                "class": "الفصل",
                "teacher": "المعلم",
                "status": "الحالة"
            })
            
            st.dataframe(display_df, use_container_width=True, hide_index=True)
            
            # الإحصائيات
            st.markdown("### 📈 إحصائياتي")
            
            total_records = len(records_df)
            present_count = len(records_df[records_df["status"] == "حاضر"])
            absent_count = len(records_df[records_df["status"].str.contains("غياب")])
            attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("إجمالي الأيام", total_records)
            
            with col2:
                st.metric("أيام الحضور", present_count)
            
            with col3:
                st.metric("أيام الغياب", absent_count)
            
            with col4:
                st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
            
            # زر التصدير
            csv_data = display_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 تصدير سجلي",
                data=csv_data,
                file_name=f"سجل_غيابي_{student_name}_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.info(f"📭 لا توجد سجلات غياب لك يا {student_name}")

# إذا حاول الوصول مباشرة بدون تسجيل دخول
else:
    st.session_state.page = "login"
    st.rerun()
