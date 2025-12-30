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
from datetime import date

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

# ------------------ وظائف المساعدة ------------------
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

# ------------------ CSS ------------------
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
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        margin-bottom: 20px;
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
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if st.button("📊 لوحة التحكم", use_container_width=True, key="admin_dashboard"):
                    st.session_state.page = "admin_dashboard"
                    st.rerun()
            
            with col2:
                if st.button("👥 إدارة الطلاب", use_container_width=True, key="manage_students"):
                    st.session_state.page = "manage_students"
                    st.rerun()
            
            with col3:
                if st.button("📋 إدارة الغياب", use_container_width=True, key="manage_attendance"):
                    st.session_state.page = "manage_attendance"
                    st.rerun()
            
            st.markdown("---")
            
            col4, col5, col6 = st.columns(3)
            
            with col4:
                if st.button("🏫 إدارة الفصول", use_container_width=True, key="manage_classes"):
                    st.session_state.page = "manage_classes"
                    st.rerun()
            
            with col5:
                if st.button("👨‍🏫 إدارة المعلمين", use_container_width=True, key="manage_teachers"):
                    st.session_state.page = "manage_teachers"
                    st.rerun()
            
            with col6:
                if st.button("📥 استيراد/تصدير", use_container_width=True, key="import_export"):
                    st.session_state.page = "import_export"
                    st.rerun()
        
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
    
    # ------------------ صفحة إدارة الطلاب للمدير ------------------
    elif st.session_state.page == "manage_students":
        st.markdown("# 👥 إدارة الطلاب")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الطلاب
        tab1, tab2, tab3 = st.tabs(["📋 عرض الطلاب", "➕ إضافة طالب", "🗑️ حذف طالب"])
        
        with tab1:
            st.markdown("### 📋 قائمة الطلاب حسب الفصول")
            
            for class_name, students in CLASSES.items():
                with st.expander(f"🎯 {class_name} ({len(students)} طالب)"):
                    if students:
                        # إنشاء DataFrame للطلاب
                        student_data = []
                        for idx, student in enumerate(students, 1):
                            password = STUDENT_PASSWORDS.get(student, "غير معرف")
                            student_data.append({
                                "م": idx,
                                "اسم الطالب": student,
                                "كلمة المرور": password
                            })
                        
                        df = pd.DataFrame(student_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("📭 لا يوجد طلاب في هذا الفصل")
        
        with tab2:
            st.markdown("### ➕ إضافة طالب جديد")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                new_student_name = st.text_input("اسم الطالب", key="new_student_name")
            
            with col2:
                new_student_class = st.selectbox("الفصل", list(CLASSES.keys()), key="new_student_class")
            
            with col3:
                new_student_password = st.text_input("كلمة المرور", type="password", key="new_student_password")
            
            if st.button("➕ إضافة الطالب", use_container_width=True, key="add_student_button"):
                if new_student_name and new_student_class and new_student_password:
                    success = add_student(new_student_name, new_student_class, new_student_password)
                    if success:
                        st.success(f"✅ تم إضافة الطالب {new_student_name} إلى الفصل {new_student_class}")
                        st.rerun()
                    else:
                        st.error("❌ الطالب موجود بالفعل!")
                else:
                    st.warning("⚠️ من فضلك املأ جميع الحقول")
        
        with tab3:
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
                    
                    if st.button("🗑️ حذف الطالب", use_container_width=True, key="confirm_delete_student"):
                        success, class_name = delete_student(selected_student)
                        if success:
                            st.success(f"✅ تم حذف الطالب {selected_student} من الفصل {class_name}")
                            st.rerun()
                        else:
                            st.error("❌ فشل في حذف الطالب")
            else:
                st.info("📭 لا يوجد طلاب في النظام")
    
    # ------------------ صفحة إدارة الفصول للمدير ------------------
    elif st.session_state.page == "manage_classes":
        st.markdown("# 🏫 إدارة الفصول")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الفصول
        tab1, tab2, tab3 = st.tabs(["📋 عرض الفصول", "➕ إضافة فصل", "🗑️ حذف فصل"])
        
        with tab1:
            st.markdown("### 📋 قائمة الفصول")
            
            for class_name, students in CLASSES.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"#### {class_name}")
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
                
                with col2:
                    # اختيار معلم جديد
                    teacher_options = ["غير معين"] + list(TEACHERS.keys())
                    new_teacher = st.selectbox(
                        "تغيير المعلم",
                        teacher_options,
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
                            TEACHERS[new_teacher].append(class_name)
                        
                        # تحديث بيانات المستخدم للمعلم
                        if new_teacher != "غير معين" and new_teacher in USERS:
                            USERS[new_teacher]["classes"] = TEACHERS[new_teacher]
                        
                        st.success(f"✅ تم تحديث المعلم المسؤول للفصل {class_name}")
                        st.rerun()
                
                with col3:
                    # زر حذف الفصل
                    if len(students) == 0:
                        if st.button(f"🗑️", key=f"delete_class_{class_name}"):
                            delete_class(class_name)
                            st.success(f"✅ تم حذف الفصل {class_name}")
                            st.rerun()
                    else:
                        st.warning("لا يمكن حذف فصل به طلاب")
                
                # عرض قائمة الطلاب
                if students:
                    with st.expander("👥 عرض الطلاب"):
                        for student in students:
                            st.write(f"- {student}")
                
                st.markdown("---")
        
        with tab2:
            st.markdown("### ➕ إضافة فصل جديد")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                new_class_name = st.text_input("اسم الفصل الجديد", key="new_class_name")
            
            with col2:
                new_class_teacher = st.selectbox(
                    "المعلم المسؤول",
                    ["غير معين"] + list(TEACHERS.keys()),
                    key="new_class_teacher"
                )
            
            with col3:
                st.write("")  # مسافة
                st.write("")
                if st.button("➕ إضافة الفصل", use_container_width=True, key="add_class_button"):
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
            st.markdown("### 🗑️ حذف فصل")
            
            # عرض الفصول الفارغة فقط للحذف
            empty_classes = [class_name for class_name, students in CLASSES.items() if len(students) == 0]
            
            if empty_classes:
                selected_class = st.selectbox(
                    "اختر الفصل للحذف",
                    empty_classes,
                    key="delete_class_select"
                )
                
                if st.button("🗑️ حذف الفصل", use_container_width=True, key="confirm_delete_class"):
                    success = delete_class(selected_class)
                    if success:
                        st.success(f"✅ تم حذف الفصل {selected_class}")
                        st.rerun()
                    else:
                        st.error("❌ فشل في حذف الفصل")
            else:
                st.info("📭 لا توجد فصول فارغة للحذف")
    
    # ------------------ صفحة إدارة المعلمين للمدير ------------------
    elif st.session_state.page == "manage_teachers":
        st.markdown("# 👨‍🏫 إدارة المعلمين")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة المعلمين
        tab1, tab2, tab3 = st.tabs(["📋 عرض المعلمين", "➕ إضافة معلم", "🗑️ حذف معلم"])
        
        with tab1:
            st.markdown("### 📋 قائمة المعلمين")
            
            for teacher_name, classes in TEACHERS.items():
                col1, col2, col3 = st.columns([3, 2, 1])
                
                with col1:
                    st.markdown(f"#### {teacher_name}")
                    st.write(f"**الفصول المسؤول عنها:** {', '.join(classes) if classes else 'لا يوجد'}")
                    st.write(f"**عدد الفصول:** {len(classes)}")
                
                with col2:
                    # تغيير كلمة المرور
                    new_password = st.text_input(
                        "كلمة المرور الجديدة",
                        type="password",
                        key=f"new_pass_{teacher_name}",
                        placeholder="اترك فارغاً للحفاظ على الكلمة الحالية"
                    )
                    
                    if st.button("🔑 تغيير", key=f"change_pass_{teacher_name}"):
                        if new_password:
                            USERS[teacher_name]["password"] = new_password
                            st.success(f"✅ تم تغيير كلمة مرور {teacher_name}")
                            st.rerun()
                
                with col3:
                    # زر حذف المعلم
                    if st.button("🗑️", key=f"delete_teacher_{teacher_name}"):
                        if teacher_name != "مينا سمير" and teacher_name != "فادي حبيب":  # منع حذف المعلمين الأساسيين
                            if classes:
                                st.warning(f"⚠️ المعلم {teacher_name} مسؤول عن فصول. اختر معلم لنقل الفصول إليه:")
                                
                                other_teachers = [t for t in TEACHERS.keys() 
                                               if t != teacher_name and t not in ["مينا سمير", "فادي حبيب"]]
                                
                                if other_teachers:
                                    transfer_to = st.selectbox(
                                        "نقل الفصول إلى",
                                        other_teachers,
                                        key=f"transfer_{teacher_name}"
                                    )
                                    
                                    if st.button("✅ نقل وحذف", key=f"confirm_transfer_{teacher_name}"):
                                        # نقل الفصول
                                        for class_name in classes:
                                            TEACHERS[transfer_to].append(class_name)
                                        
                                        # حذف المعلم
                                        delete_teacher(teacher_name)
                                        
                                        # تحديث بيانات المستخدم للمعلم الجديد
                                        if transfer_to in USERS:
                                            USERS[transfer_to]["classes"] = TEACHERS[transfer_to]
                                        
                                        st.success(f"✅ تم نقل الفصول إلى {transfer_to} وحذف {teacher_name}")
                                        st.rerun()
                                else:
                                    st.error("❌ لا يوجد معلمين آخرين لنقل الفصول إليهم!")
                            else:
                                delete_teacher(teacher_name)
                                st.success(f"✅ تم حذف المعلم {teacher_name}")
                                st.rerun()
                        else:
                            st.error("❌ لا يمكن حذف هذا المعلم الأساسي!")
                
                st.markdown("---")
        
        with tab2:
            st.markdown("### ➕ إضافة معلم جديد")
            
            col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
            
            with col1:
                new_teacher_name = st.text_input("اسم المعلم", key="new_teacher_name")
            
            with col2:
                new_teacher_password = st.text_input("كلمة المرور", type="password", key="new_teacher_password")
            
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
                if st.button("➕ إضافة", use_container_width=True, key="add_teacher_button"):
                    if new_teacher_name and new_teacher_password:
                        success = add_teacher(new_teacher_name, new_teacher_password, new_teacher_classes)
                        if success:
                            st.success(f"✅ تم إضافة المعلم {new_teacher_name}")
                            st.rerun()
                        else:
                            st.error("❌ المعلم موجود بالفعل!")
                    else:
                        st.warning("⚠️ من فضلك املأ جميع الحقول")
        
        with tab3:
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
    
    # ------------------ صفحة إدارة سجلات الغياب للمدير ------------------
    elif st.session_state.page == "manage_attendance":
        st.markdown("# 📋 إدارة سجلات الغياب")
        
        if st.button("🏠 العودة للصفحة الرئيسية", use_container_width=True):
            st.session_state.page = "home"
            st.rerun()
        
        st.markdown("---")
        
        # تبويبات إدارة الغياب
        tab1, tab2, tab3 = st.tabs(["🔍 البحث والتصفية", "🗑️ حذف السجلات", "📊 الإحصائيات"])
        
        with tab1:
            st.markdown("### 🔍 البحث في سجلات الغياب")
            
            col1, col2, col3 = st.columns(3)
            
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
                    ["الكل", "حاضر", "غياب"],
                    key="search_status"
                )
            
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
                    
                    st.dataframe(display_df, use_container_width=True, hide_index=True)
                    
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
                    # حذف جميع السجلات
                    st.info(f"إجمالي السجلات: {len(attendance_records)}")
                    
                    if st.button("🗑️ حذف جميع السجلات", use_container_width=True):
                        st.session_state.attendance_data = []
                        st.success("✅ تم حذف جميع السجلات")
                        st.rerun()
            else:
                st.info("📭 لا توجد سجلات لحذفها")
        
        with tab3:
            st.markdown("### 📊 إحصائيات الغياب")
            
            attendance_records = get_attendance_records()
            
            if attendance_records:
                # تحويل إلى DataFrame
                records_df = pd.DataFrame(attendance_records)
                
                # الإحصائيات العامة
                total_records = len(records_df)
                present_count = len(records_df[records_df["status"] == "حاضر"])
                absent_count = len(records_df[records_df["status"] == "غياب"])
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    st.metric("إجمالي السجلات", total_records)
                
                with col2:
                    st.metric("عدد الحضور", present_count)
                
                with col3:
                    st.metric("عدد الغياب", absent_count)
                
                # إحصائيات حسب الفصول
                st.markdown("#### 📊 إحصائيات الفصول")
                
                class_stats = []
                for class_name in CLASSES.keys():
                    class_records = records_df[records_df["class"] == class_name]
                    if len(class_records) > 0:
                        class_present = len(class_records[class_records["status"] == "حاضر"])
                        class_absent = len(class_records[class_records["status"] == "غياب"])
                        class_total = len(class_records)
                        
                        class_stats.append({
                            "الفصل": class_name,
                            "إجمالي السجلات": class_total,
                            "الحضور": class_present,
                            "الغياب": class_absent,
                            "نسبة الحضور": f"{(class_present/class_total*100):.1f}%" if class_total > 0 else "0%"
                        })
                
                if class_stats:
                    stats_df = pd.DataFrame(class_stats)
                    st.dataframe(stats_df, use_container_width=True, hide_index=True)
                else:
                    st.info("📭 لا توجد سجلات للفصول")
            else:
                st.info("📭 لا توجد سجلات لعرض الإحصائيات")
    
    # ------------------ صفحة استيراد/تصدير للمدير ------------------
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
                                password = str(row.get("كلمة_المرور", f"stu{hash(student_name) % 10000:04d}")).strip()
                                
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
