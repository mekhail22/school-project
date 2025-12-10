import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import io
import os
import json
import base64
import time
from typing import List, Dict, Tuple, Optional
import hashlib

# ==================== إعدادات التطبيق ====================
st.set_page_config(
    page_title="نظام الغياب الذكي - مدرسة الإبداع",
    page_icon="🏫",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'https://www.example.com',
        'Report a bug': 'https://www.example.com/bug',
        'About': "### نظام إدارة الغياب الإلكتروني\nالإصدار 3.0.0\nمدرسة الإبداع © 2024"
    }
)

# ==================== CSS مخصص ====================
st.markdown("""
<style>
    /* إخفاء عناصر Streamlit الافتراضية */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display: none;}
    
    /* الشريط العلوي الرئيسي */
    .main-header {
        background: linear-gradient(135deg, #1e3a8a 0%, #2563eb 50%, #3b82f6 100%);
        padding: 1.5rem 2rem;
        margin: -1rem -1rem 2rem -1rem;
        color: white;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.15);
        border-bottom: 4px solid #fbbf24;
    }
    
    .header-content {
        display: flex;
        justify-content: space-between;
        align-items: center;
        max-width: 1400px;
        margin: 0 auto;
    }
    
    .school-info {
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    
    .school-logo {
        width: 70px;
        height: 70px;
        background: white;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.5rem;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
    }
    
    .school-text h1 {
        margin: 0;
        font-size: 2rem;
        font-weight: 800;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.3);
    }
    
    .school-text p {
        margin: 0.3rem 0 0 0;
        opacity: 0.9;
        font-size: 1rem;
    }
    
    .user-info {
        display: flex;
        align-items: center;
        gap: 1rem;
        background: rgba(255, 255, 255, 0.15);
        padding: 0.8rem 1.5rem;
        border-radius: 50px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    .user-avatar {
        font-size: 1.8rem;
    }
    
    .user-details h4 {
        margin: 0;
        font-size: 1.1rem;
    }
    
    .user-details p {
        margin: 0.2rem 0 0 0;
        font-size: 0.85rem;
        opacity: 0.8;
    }
    
    /* الوقت والتاريخ */
    .time-display {
        text-align: center;
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.1);
        border-radius: 10px;
        margin-top: 0.5rem;
    }
    
    /* القائمة الجانبية */
    .sidebar-nav {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        padding: 1.5rem;
        border-radius: 15px;
        margin: 1rem 0;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    }
    
    .nav-title {
        color: #1e40af;
        font-size: 1.3rem;
        margin-bottom: 1.5rem;
        padding-bottom: 0.8rem;
        border-bottom: 2px solid #e2e8f0;
        text-align: center;
    }
    
    .nav-item {
        display: flex;
        align-items: center;
        gap: 0.8rem;
        padding: 0.9rem 1rem;
        margin: 0.5rem 0;
        border-radius: 10px;
        cursor: pointer;
        transition: all 0.3s ease;
        text-decoration: none;
        color: #374151;
        font-weight: 500;
    }
    
    .nav-item:hover {
        background: linear-gradient(135deg, #dbeafe, #eff6ff);
        transform: translateX(5px);
        color: #1e40af;
    }
    
    .nav-item.active {
        background: linear-gradient(135deg, #3b82f6, #1e40af);
        color: white;
        box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3);
    }
    
    .nav-icon {
        font-size: 1.3rem;
        width: 30px;
        text-align: center;
    }
    
    /* محتوى الصفحات */
    .page-container {
        background: white;
        border-radius: 20px;
        padding: 2rem;
        margin: 1rem 0;
        box-shadow: 0 8px 25px rgba(0, 0, 0, 0.08);
        border: 1px solid #e5e7eb;
    }
    
    .page-title {
        color: #1e40af;
        font-size: 2.2rem;
        margin-bottom: 2rem;
        text-align: center;
        padding-bottom: 1rem;
        border-bottom: 3px solid #fbbf24;
        position: relative;
    }
    
    .page-title:after {
        content: '';
        position: absolute;
        bottom: -3px;
        left: 40%;
        width: 20%;
        height: 3px;
        background: #2563eb;
        border-radius: 2px;
    }
    
    /* البطاقات */
    .stats-card {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        padding: 1.8rem;
        border-radius: 15px;
        text-align: center;
        border: 2px solid #e2e8f0;
        transition: all 0.3s ease;
        height: 100%;
    }
    
    .stats-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 12px 25px rgba(0, 0, 0, 0.1);
        border-color: #3b82f6;
    }
    
    .card-icon {
        font-size: 3rem;
        margin-bottom: 1rem;
        color: #2563eb;
    }
    
    .card-value {
        font-size: 2.8rem;
        font-weight: 800;
        color: #1e40af;
        margin: 0.5rem 0;
    }
    
    .card-label {
        font-size: 1.1rem;
        color: #64748b;
        font-weight: 600;
    }
    
    /* الأزرار */
    .custom-btn {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        border: none;
        padding: 1rem 2rem;
        border-radius: 12px;
        font-size: 1.1rem;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.3s ease;
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.8rem;
        text-decoration: none;
    }
    
    .custom-btn:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af);
        transform: translateY(-3px);
        box-shadow: 0 10px 25px rgba(37, 99, 235, 0.3);
    }
    
    .custom-btn.secondary {
        background: linear-gradient(135deg, #475569, #64748b);
    }
    
    .custom-btn.secondary:hover {
        background: linear-gradient(135deg, #374151, #475569);
    }
    
    .custom-btn.danger {
        background: linear-gradient(135deg, #dc2626, #ef4444);
    }
    
    .custom-btn.danger:hover {
        background: linear-gradient(135deg, #b91c1c, #dc2626);
    }
    
    /* الجداول */
    .data-table {
        width: 100%;
        border-collapse: collapse;
        margin: 1.5rem 0;
        background: white;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 5px 15px rgba(0, 0, 0, 0.05);
    }
    
    .data-table th {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
        padding: 1.2rem;
        text-align: right;
        font-weight: 600;
        font-size: 1.1rem;
    }
    
    .data-table td {
        padding: 1rem 1.2rem;
        border-bottom: 1px solid #e5e7eb;
        text-align: right;
    }
    
    .data-table tr:hover {
        background: #f8fafc;
    }
    
    .data-table tr:last-child td {
        border-bottom: none;
    }
    
    /* نماذج الإدخال */
    .form-group {
        margin: 1.5rem 0;
    }
    
    .form-label {
        display: block;
        margin-bottom: 0.8rem;
        font-size: 1.1rem;
        font-weight: 600;
        color: #1e293b;
    }
    
    .form-control {
        width: 100%;
        padding: 1rem 1.2rem;
        border: 2px solid #e2e8f0;
        border-radius: 12px;
        font-size: 1rem;
        transition: all 0.3s ease;
        background: white;
        color: #1e293b;
    }
    
    .form-control:focus {
        outline: none;
        border-color: #3b82f6;
        box-shadow: 0 0 0 4px rgba(59, 130, 246, 0.2);
    }
    
    /* التنبيهات */
    .alert {
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        margin: 1.5rem 0;
        display: flex;
        align-items: center;
        gap: 1rem;
    }
    
    .alert-success {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    
    .alert-error {
        background: linear-gradient(135deg, #ef4444, #dc2626);
        color: white;
    }
    
    .alert-warning {
        background: linear-gradient(135deg, #f59e0b, #d97706);
        color: white;
    }
    
    .alert-info {
        background: linear-gradient(135deg, #3b82f6, #2563eb);
        color: white;
    }
    
    /* التقدم */
    .progress-container {
        background: #e2e8f0;
        border-radius: 10px;
        height: 10px;
        margin: 1.5rem 0;
        overflow: hidden;
    }
    
    .progress-bar {
        height: 100%;
        background: linear-gradient(135deg, #10b981, #059669);
        border-radius: 10px;
        transition: width 0.5s ease;
    }
    
    /* التذييل */
    .footer {
        text-align: center;
        padding: 2rem;
        margin-top: 3rem;
        color: #64748b;
        border-top: 1px solid #e5e7eb;
        background: #f8fafc;
        border-radius: 0 0 20px 20px;
    }
    
    /* تأثيرات خاصة */
    .pulse {
        animation: pulse 2s infinite;
    }
    
    @keyframes pulse {
        0% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0.4); }
        70% { box-shadow: 0 0 0 10px rgba(37, 99, 235, 0); }
        100% { box-shadow: 0 0 0 0 rgba(37, 99, 235, 0); }
    }
    
    .fade-in {
        animation: fadeIn 0.5s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(20px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* التكيف مع الشاشات الصغيرة */
    @media (max-width: 768px) {
        .header-content {
            flex-direction: column;
            gap: 1rem;
            text-align: center;
        }
        
        .school-info {
            flex-direction: column;
            text-align: center;
        }
        
        .page-title {
            font-size: 1.8rem;
        }
        
        .card-value {
            font-size: 2.2rem;
        }
    }
</style>
""", unsafe_allow_html=True)

# ==================== بيانات التطبيق ====================
class SchoolData:
    """فئة لإدارة بيانات المدرسة"""
    
    def __init__(self):
        self.STUDENTS = [
            "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
            "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
            "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
            "يوستينا مجدي فادي", "ماريو أشرف نادي", "جورج ميلاد صبحي",
            "كيرلس عماد فكري", "مينا ممدوح رزق", "ماجد رضا محمود"
        ]
        
        self.TEACHERS = ["مينا سمير", "فادي حبيب", "هاني جورج", "ريمون فكري"]
        
        self.SUBJECTS = [
            "اللغة العربية", "الرياضيات", "اللغة الإنجليزية", "العلوم",
            "الدراسات الاجتماعية", "التربية الدينية", "الحاسب الآلي", "التربية الرياضية"
        ]
        
        self.GRADES = ["الصف الأول", "الصف الثاني", "الصف الثالث", "الصف الرابع", "الصف الخامس", "الصف السادس"]
        
        self.initialize_session_state()
    
    def initialize_session_state(self):
        """تهيئة حالة الجلسة"""
        defaults = {
            'logged_in': False,
            'user_role': '',
            'user_name': '',
            'user_id': '',
            'current_page': 'login',
            'attendance_data': [],
            'students_data': self.STUDENTS.copy(),
            'teachers_data': self.TEACHERS.copy(),
            'subjects_data': self.SUBJECTS.copy(),
            'grades_data': self.GRADES.copy(),
            'notifications': [],
            'settings': {
                'theme': 'light',
                'language': 'ar',
                'auto_save': True,
                'notifications': True,
                'backup_frequency': 'daily'
            }
        }
        
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value
    
    def get_hashed_password(self, password: str) -> str:
        """تجزئة كلمة المرور"""
        return hashlib.sha256(password.encode()).hexdigest()

class UserManager:
    """مدير المستخدمين والمصادقة"""
    
    def __init__(self):
        self.users = {
            # معلمون
            "مينا سمير": {
                "password": self.hash_password("teacher123"),
                "role": "teacher",
                "email": "mina.samir@school.edu",
                "phone": "01012345678",
                "subjects": ["الرياضيات", "العلوم"],
                "grade": "الصف السادس",
                "permissions": ["record_attendance", "view_reports", "manage_students", "generate_reports"]
            },
            "فادي حبيب": {
                "password": self.hash_password("teacher123"),
                "role": "teacher",
                "email": "fady.habib@school.edu",
                "phone": "01087654321",
                "subjects": ["اللغة العربية", "التربية الدينية"],
                "grade": "الصف الخامس",
                "permissions": ["record_attendance", "view_reports", "generate_reports"]
            },
            
            # طلاب
            "ميخائيل صابر فوزي": {
                "password": self.hash_password("student123"),
                "role": "student",
                "student_id": "2024001",
                "grade": "الصف السادس",
                "parent_phone": "01011112222",
                "birth_date": "2010-05-15",
                "permissions": ["view_own_records", "download_reports"]
            },
            "مينا ريمون خيري": {
                "password": self.hash_password("student123"),
                "role": "student",
                "student_id": "2024002",
                "grade": "الصف السادس",
                "parent_phone": "01022223333",
                "birth_date": "2010-07-20",
                "permissions": ["view_own_records", "download_reports"]
            }
        }
        
        # إضافة باقي الطلاب
        student_base = {
            "password": self.hash_password("student123"),
            "role": "student",
            "permissions": ["view_own_records", "download_reports"]
        }
        
        student_data = [
            ("توني هاني نصرالله", "2024003", "الصف السادس", "2010-03-10"),
            ("يوسف شادي كمال", "2024004", "الصف السادس", "2010-09-05"),
            ("ادم مايكل فوزي", "2024005", "الصف السادس", "2010-11-15"),
            ("مارك نادر فؤاد", "2024006", "الصف السادس", "2010-12-22"),
            ("بيشوي عاطف فايز", "2024007", "الصف السادس", "2010-02-18"),
            ("جورج مينا نجيب", "2024008", "الصف السادس", "2010-08-30"),
            ("كيرلس فادي صادق", "2024009", "الصف السادس", "2010-06-25"),
            ("يوستينا مجدي فادي", "2024010", "الصف السادس", "2010-04-12")
        ]
        
        for name, sid, grade, birth_date in student_data:
            self.users[name] = {
                **student_base,
                "student_id": sid,
                "grade": grade,
                "birth_date": birth_date,
                "parent_phone": f"010{int(sid)}000"
            }
    
    def hash_password(self, password: str) -> str:
        """تجزئة كلمة المرور"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, str, Dict]:
        """مصادقة المستخدم"""
        if username not in self.users:
            return False, "اسم المستخدم غير موجود", {}
        
        user_data = self.users[username]
        hashed_password = self.hash_password(password)
        
        if user_data["password"] != hashed_password:
            return False, "كلمة المرور غير صحيحة", {}
        
        return True, "تم تسجيل الدخول بنجاح", user_data
    
    def get_user_info(self, username: str) -> Optional[Dict]:
        """الحصول على معلومات المستخدم"""
        return self.users.get(username)

class AttendanceManager:
    """مدير نظام الغياب"""
    
    def __init__(self):
        self.attendance_file = "attendance_data.json"
        self.backup_file = "attendance_backup.json"
        self.load_data()
    
    def load_data(self):
        """تحميل بيانات الغياب"""
        try:
            if os.path.exists(self.attendance_file):
                with open(self.attendance_file, 'r', encoding='utf-8') as f:
                    st.session_state.attendance_data = json.load(f)
            else:
                st.session_state.attendance_data = []
        except Exception as e:
            st.error(f"خطأ في تحميل البيانات: {e}")
            st.session_state.attendance_data = []
    
    def save_data(self):
        """حفظ بيانات الغياب"""
        try:
            with open(self.attendance_file, 'w', encoding='utf-8') as f:
                json.dump(st.session_state.attendance_data, f, ensure_ascii=False, indent=2)
            
            # إنشاء نسخة احتياطية
            import shutil
            if os.path.exists(self.attendance_file):
                shutil.copy2(self.attendance_file, self.backup_file)
                
            return True, "تم حفظ البيانات بنجاح"
        except Exception as e:
            return False, f"خطأ في حفظ البيانات: {e}"
    
    def record_attendance(self, student: str, teacher: str, status: str, 
                         date: str, subject: str, notes: str = "") -> Tuple[bool, str]:
        """تسجيل غياب طالب"""
        try:
            record = {
                "id": len(st.session_state.attendance_data) + 1,
                "student": student,
                "teacher": teacher,
                "status": status,
                "date": date,
                "subject": subject,
                "notes": notes,
                "timestamp": datetime.now().isoformat(),
                "recorded_by": st.session_state.get('user_name', 'System')
            }
            
            st.session_state.attendance_data.append(record)
            success, message = self.save_data()
            
            if success:
                # إضافة إشعار
                notification = {
                    "type": "success",
                    "title": "تم تسجيل الغياب",
                    "message": f"تم تسجيل {status} للطالب {student}",
                    "time": datetime.now().strftime("%H:%M")
                }
                st.session_state.notifications.append(notification)
            
            return success, message
            
        except Exception as e:
            return False, f"خطأ في تسجيل الغياب: {e}"
    
    def get_student_records(self, student_name: str, start_date: str = None, 
                           end_date: str = None, subject: str = None) -> List[Dict]:
        """الحصول على سجلات طالب معين"""
        records = st.session_state.attendance_data.copy()
        
        # تصفية حسب اسم الطالب
        student_records = [r for r in records if r["student"] == student_name]
        
        # تطبيق المزيد من المرشحات
        if start_date:
            student_records = [r for r in student_records if r["date"] >= start_date]
        if end_date:
            student_records = [r for r in student_records if r["date"] <= end_date]
        if subject:
            student_records = [r for r in student_records if r["subject"] == subject]
        
        # ترتيب حسب التاريخ
        student_records.sort(key=lambda x: x["date"], reverse=True)
        
        return student_records
    
    def get_all_records(self, filters: Dict = None) -> List[Dict]:
        """الحصول على جميع السجلات مع مرشحات اختيارية"""
        records = st.session_state.attendance_data.copy()
        
        if filters:
            for key, value in filters.items():
                if value:
                    records = [r for r in records if str(r.get(key, '')).lower() == str(value).lower()]
        
        return records
    
    def get_statistics(self) -> Dict:
        """الحصول على إحصائيات الغياب"""
        records = st.session_state.attendance_data
        
        if not records:
            return {
                "total_records": 0,
                "total_students": 0,
                "present_count": 0,
                "absent_count": 0,
                "excused_count": 0,
                "attendance_rate": 0
            }
        
        # إحصائيات عامة
        total_records = len(records)
        unique_students = len(set(r["student"] for r in records))
        
        # إحصائيات حسب الحالة
        status_counts = {}
        for record in records:
            status = record["status"]
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # حساب نسبة الحضور
        present_count = status_counts.get("حاضر", 0)
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
        
        return {
            "total_records": total_records,
            "total_students": unique_students,
            "present_count": present_count,
            "absent_count": status_counts.get("غياب بدون عذر", 0),
            "excused_count": status_counts.get("غياب بعذر", 0),
            "attendance_rate": round(attendance_rate, 2)
        }

# ==================== تهيئة المكونات ====================
school_data = SchoolData()
user_manager = UserManager()
attendance_manager = AttendanceManager()

# ==================== واجهات المستخدم ====================
class Header:
    """الشريط العلوي للتطبيق"""
    
    @staticmethod
    def render():
        """عرض الشريط العلوي"""
        arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", 
                        "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
        today = datetime.now()
        
        header_html = f"""
        <div class="main-header">
            <div class="header-content">
                <div class="school-info">
                    <div class="school-logo">🏫</div>
                    <div class="school-text">
                        <h1>مدرسة الإبداع</h1>
                        <p>نظام إدارة الغياب الإلكتروني | الإصدار 3.0.0</p>
                    </div>
                </div>
                
                <div>
                    <div class="time-display">
                        <div style="font-size: 0.9rem; opacity: 0.8;">اليوم</div>
                        <div style="font-size: 1.2rem; font-weight: 600;">
                            {today.day} {arabic_months[today.month - 1]} {today.year}
                        </div>
                        <div style="font-size: 0.9rem; margin-top: 0.3rem;">
                            {today.strftime('%I:%M %p')}
                        </div>
                    </div>
                </div>
                
                <div class="user-info">
                    <div class="user-avatar">
                        {"👨‍🏫" if st.session_state.user_role == "teacher" else "👨‍🎓"}
                    </div>
                    <div class="user-details">
                        <h4>{st.session_state.user_name}</h4>
                        <p>{"معلم" if st.session_state.user_role == "teacher" else "طالب"}</p>
                    </div>
                </div>
            </div>
        </div>
        """
        
        st.markdown(header_html, unsafe_allow_html=True)

class Sidebar:
    """القائمة الجانبية"""
    
    @staticmethod
    def render():
        """عرض القائمة الجانبية"""
        with st.sidebar:
            st.markdown('<div class="sidebar-nav">', unsafe_allow_html=True)
            st.markdown('<div class="nav-title">🌙 قائمة التنقل</div>', unsafe_allow_html=True)
            
            # عناصر القائمة حسب دور المستخدم
            menu_items = []
            
            if st.session_state.user_role == "teacher":
                menu_items = [
                    {"icon": "🏠", "label": "الرئيسية", "page": "home"},
                    {"icon": "📝", "label": "تسجيل الغياب", "page": "attendance"},
                    {"icon": "📊", "label": "التقارير والإحصائيات", "page": "reports"},
                    {"icon": "👨‍🎓", "label": "إدارة الطلاب", "page": "students"},
                    {"icon": "📅", "label": "الجدول الدراسي", "page": "schedule"},
                    {"icon": "🔔", "label": "الإشعارات", "page": "notifications"},
                    {"icon": "⚙️", "label": "الإعدادات", "page": "settings"}
                ]
            elif st.session_state.user_role == "student":
                menu_items = [
                    {"icon": "🏠", "label": "الرئيسية", "page": "home"},
                    {"icon": "📊", "label": "تقريري الدراسي", "page": "my_report"},
                    {"icon": "📋", "label": "سجلات الغياب", "page": "my_records"},
                    {"icon": "📅", "label": "جدولي الدراسي", "page": "my_schedule"},
                    {"icon": "🏆", "label": "إنجازاتي", "page": "achievements"},
                    {"icon": "⚙️", "label": "الإعدادات", "page": "settings"}
                ]
            
            # عرض عناصر القائمة
            for item in menu_items:
                is_active = st.session_state.current_page == item["page"]
                active_class = "active" if is_active else ""
                
                if st.button(
                    f"{item['icon']} {item['label']}",
                    key=f"nav_{item['page']}",
                    use_container_width=True,
                    type="primary" if is_active else "secondary"
                ):
                    st.session_state.current_page = item["page"]
                    st.rerun()
            
            st.markdown("---")
            
            # زر تسجيل الخروج
            if st.button("🚪 تسجيل الخروج", use_container_width=True, type="secondary"):
                st.session_state.logged_in = False
                st.session_state.user_role = ""
                st.session_state.user_name = ""
                st.session_state.current_page = "login"
                st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
            
            # معلومات الاتصال
            st.markdown("""
            <div style="text-align: center; padding: 1rem; color: #64748b; font-size: 0.9rem;">
                <div>📧 info@school.edu</div>
                <div>📞 01234567890</div>
                <div style="margin-top: 0.5rem; font-size: 0.8rem;">
                    © 2024 مدرسة الإبداع
                </div>
            </div>
            """, unsafe_allow_html=True)

# ==================== صفحات التطبيق ====================
class LoginPage:
    """صفحة تسجيل الدخول"""
    
    @staticmethod
    def render():
        """عرض صفحة تسجيل الدخول"""
        st.markdown("""
        <div style="max-width: 500px; margin: 100px auto; padding: 40px; background: white; 
                    border-radius: 20px; box-shadow: 0 15px 35px rgba(0,0,0,0.1);">
            <div style="text-align: center; margin-bottom: 40px;">
                <div style="font-size: 60px; margin-bottom: 20px;">🏫</div>
                <h1 style="color: #1e40af; margin-bottom: 10px;">مدرسة الإبداع</h1>
                <p style="color: #64748b;">نظام إدارة الغياب الذكي</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2, col3 = st.columns([1, 2, 1])
        
        with col2:
            with st.form("login_form"):
                st.markdown('<div class="form-label">👤 اسم المستخدم</div>', unsafe_allow_html=True)
                username = st.text_input(
                    "اسم المستخدم",
                    placeholder="أدخل اسم المستخدم...",
                    label_visibility="collapsed"
                )
                
                st.markdown('<div class="form-label">🔐 كلمة المرور</div>', unsafe_allow_html=True)
                password = st.text_input(
                    "كلمة المرور",
                    type="password",
                    placeholder="أدخل كلمة المرور...",
                    label_visibility="collapsed"
                )
                
                col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
                with col_btn2:
                    login_clicked = st.form_submit_button(
                        "✅ تسجيل الدخول",
                        use_container_width=True,
                        type="primary"
                    )
                
                if login_clicked:
                    if username and password:
                        success, message, user_data = user_manager.authenticate(username, password)
                        
                        if success:
                            st.session_state.logged_in = True
                            st.session_state.user_name = username
                            st.session_state.user_role = user_data["role"]
                            st.session_state.current_page = "home"
                            
                            # إضافة إشعار ترحيب
                            st.session_state.notifications.append({
                                "type": "info",
                                "title": "مرحباً بك",
                                "message": f"تم تسجيل دخولك بنجاح {username}",
                                "time": datetime.now().strftime("%H:%M")
                            })
                            
                            st.success("✅ تم تسجيل الدخول بنجاح!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"❌ {message}")
                    else:
                        st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")
            
            # معلومات المساعدة
            st.markdown("""
            <div style="margin-top: 40px; padding: 20px; background: #f8fafc; border-radius: 15px;">
                <h4 style="color: #1e40af; margin-bottom: 15px;">💡 معلومات الدخول:</h4>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div style="padding: 12px; background: white; border-radius: 10px; border: 1px solid #e2e8f0;">
                        <div style="font-weight: bold; color: #2563eb;">👨‍🏫 للمعلمين</div>
                        <div style="margin-top: 5px; font-size: 14px;">
                            <div>• مينا سمير</div>
                            <div>• فادي حبيب</div>
                            <div><strong>كلمة المرور:</strong> teacher123</div>
                        </div>
                    </div>
                    
                    <div style="padding: 12px; background: white; border-radius: 10px; border: 1px solid #e2e8f0;">
                        <div style="font-weight: bold; color: #2563eb;">👨‍🎓 للطلاب</div>
                        <div style="margin-top: 5px; font-size: 14px;">
                            <div>• أدخل اسمك</div>
                            <div><strong>كلمة المرور:</strong> student123</div>
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)

class HomePage:
    """الصفحة الرئيسية"""
    
    @staticmethod
    def render():
        """عرض الصفحة الرئيسية"""
        st.markdown('<div class="page-container fade-in">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">🏠 الصفحة الرئيسية</div>', unsafe_allow_html=True)
        
        # رسالة ترحيب
        user_role = "معلم" if st.session_state.user_role == "teacher" else "طالب"
        st.markdown(f"""
        <div style="text-align: center; padding: 20px; background: linear-gradient(135deg, #f0f9ff, #e2e8f0); 
                    border-radius: 15px; margin-bottom: 40px; border: 3px solid #bae6fd;">
            <h2 style="color: #0369a1; margin-bottom: 10px;">مرحباً بك {st.session_state.user_name}</h2>
            <p style="color: #475569; font-size: 18px;">أنت مسجل دخولك كـ <strong>{user_role}</strong> في نظام إدارة الغياب</p>
        </div>
        """, unsafe_allow_html=True)
        
        # إحصائيات سريعة
        stats = attendance_manager.get_statistics()
        
        st.markdown("### 📊 نظرة سريعة على النظام")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">👨‍🎓</div>
                <div class="card-value">{stats['total_students']}</div>
                <div class="card-label">إجمالي الطلاب</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">📋</div>
                <div class="card-value">{stats['total_records']}</div>
                <div class="card-label">إجمالي السجلات</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">📊</div>
                <div class="card-value">{stats['attendance_rate']}%</div>
                <div class="card-label">نسبة الحضور</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col4:
            today = datetime.now().strftime("%Y-%m-%d")
            today_records = len([r for r in st.session_state.attendance_data if r["date"] == today])
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">📅</div>
                <div class="card-value">{today_records}</div>
                <div class="card-label">سجلات اليوم</div>
            </div>
            """, unsafe_allow_html=True)
        
        # أزرار الإجراءات السريعة
        st.markdown("### 🚀 الإجراءات السريعة")
        
        if st.session_state.user_role == "teacher":
            col_a1, col_a2, col_a3, col_a4 = st.columns(4)
            
            with col_a1:
                if st.button("📝 تسجيل غياب", use_container_width=True, type="primary"):
                    st.session_state.current_page = "attendance"
                    st.rerun()
            
            with col_a2:
                if st.button("📊 التقارير", use_container_width=True):
                    st.session_state.current_page = "reports"
                    st.rerun()
            
            with col_a3:
                if st.button("👨‍🎓 الطلاب", use_container_width=True):
                    st.session_state.current_page = "students"
                    st.rerun()
            
            with col_a4:
                if st.button("📅 الجدول", use_container_width=True):
                    st.session_state.current_page = "schedule"
                    st.rerun()
        
        elif st.session_state.user_role == "student":
            col_a1, col_a2, col_a3, col_a4 = st.columns(4)
            
            with col_a1:
                if st.button("📊 تقريري", use_container_width=True, type="primary"):
                    st.session_state.current_page = "my_report"
                    st.rerun()
            
            with col_a2:
                if st.button("📋 سجلاتي", use_container_width=True):
                    st.session_state.current_page = "my_records"
                    st.rerun()
            
            with col_a3:
                if st.button("📅 جدولي", use_container_width=True):
                    st.session_state.current_page = "my_schedule"
                    st.rerun()
            
            with col_a4:
                if st.button("🏆 إنجازاتي", use_container_width=True):
                    st.session_state.current_page = "achievements"
                    st.rerun()
        
        # أحدث السجلات
        st.markdown("### 📋 أحدث السجلات")
        
        if st.session_state.attendance_data:
            recent_records = st.session_state.attendance_data[-5:][::-1]
            
            for record in recent_records:
                status_color = {
                    "حاضر": "#10b981",
                    "غياب بعذر": "#f59e0b",
                    "غياب بدون عذر": "#ef4444"
                }.get(record["status"], "#64748b")
                
                st.markdown(f"""
                <div style="padding: 15px; margin: 10px 0; background: white; border-radius: 10px; 
                            border-left: 4px solid {status_color}; border: 1px solid #e5e7eb;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <strong>{record['student']}</strong> - {record['subject']}
                        </div>
                        <div style="color: {status_color}; font-weight: bold;">
                            {record['status']}
                        </div>
                    </div>
                    <div style="color: #64748b; font-size: 0.9rem; margin-top: 5px;">
                        📅 {record['date']} | 👨‍🏫 {record['teacher']}
                    </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("📭 لا توجد سجلات في النظام بعد")
        
        # معلومات النظام
        st.markdown("### ℹ️ معلومات النظام")
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown("""
            <div style="padding: 20px; background: #f8fafc; border-radius: 15px; border: 1px solid #e2e8f0;">
                <h4 style="color: #1e40af; margin-bottom: 15px;">📅 معلومات اليوم</h4>
                <div style="color: #475569;">
                    <div>📅 <strong>التاريخ:</strong> {}</div>
                    <div>🕐 <strong>الوقت:</strong> {}</div>
                    <div>👤 <strong>المستخدم:</strong> {}</div>
                    <div>🎯 <strong>الدور:</strong> {}</div>
                </div>
            </div>
            """.format(
                datetime.now().strftime("%Y-%m-%d"),
                datetime.now().strftime("%I:%M %p"),
                st.session_state.user_name,
                user_role
            ), unsafe_allow_html=True)
        
        with col_info2:
            st.markdown("""
            <div style="padding: 20px; background: #f8fafc; border-radius: 15px; border: 1px solid #e2e8f0;">
                <h4 style="color: #1e40af; margin-bottom: 15px;">🔧 حالة النظام</h4>
                <div style="color: #475569;">
                    <div>✅ <strong>حالة الاتصال:</strong> نشط</div>
                    <div>💾 <strong>السجلات المحفوظة:</strong> {}</div>
                    <div>📁 <strong>النسخ الاحتياطي:</strong> {}</div>
                    <div>🔄 <strong>آخر تحديث:</strong> {}</div>
                </div>
            </div>
            """.format(
                len(st.session_state.attendance_data),
                "مفعل" if os.path.exists("attendance_backup.json") else "غير مفعل",
                datetime.now().strftime("%H:%M")
            ), unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

class AttendancePage:
    """صفحة تسجيل الغياب"""
    
    @staticmethod
    def render():
        """عرض صفحة تسجيل الغياب"""
        if st.session_state.user_role != "teacher":
            st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
            st.session_state.current_page = "home"
            st.rerun()
            return
        
        st.markdown('<div class="page-container fade-in">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">📝 تسجيل الغياب</div>', unsafe_allow_html=True)
        
        teacher_name = st.session_state.user_name
        
        # معلومات الجلسة
        st.markdown(f"""
        <div style="padding: 20px; background: linear-gradient(135deg, #dbeafe, #93c5fd); 
                    border-radius: 15px; margin-bottom: 30px; border: 2px solid #60a5fa;">
            <div style="display: flex; align-items: center; gap: 20px;">
                <div style="font-size: 50px;">👨‍🏫</div>
                <div>
                    <h3 style="margin: 0; color: #1e40af;">المعلم: {teacher_name}</h3>
                    <p style="margin: 5px 0 0 0; color: #475569;">
                        📅 {datetime.now().strftime('%Y-%m-%d')} | 🕐 {datetime.now().strftime('%I:%M %p')}
                    </p>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # نموذج تسجيل الغياب
        with st.form("attendance_form", clear_on_submit=True):
            st.markdown("### 📋 معلومات الحصة")
            
            col_info1, col_info2 = st.columns(2)
            
            with col_info1:
                selected_subject = st.selectbox(
                    "المادة الدراسية",
                    options=st.session_state.subjects_data,
                    key="attendance_subject"
                )
            
            with col_info2:
                selected_date = st.date_input(
                    "تاريخ الحصة",
                    value=datetime.now(),
                    key="attendance_date"
                )
                date_str = selected_date.strftime("%Y-%m-%d")
            
            st.markdown("### 👨‍🎓 اختيار الطلاب")
            
            # اختيار الطلاب
            selected_students = st.multiselect(
                "الطلاب الغائبون",
                options=st.session_state.students_data,
                placeholder="اختر الطلاب الغائبين...",
                key="absent_students"
            )
            
            st.markdown("### 📝 نوع الغياب")
            
            col_type1, col_type2 = st.columns(2)
            
            with col_type1:
                absence_type = st.radio(
                    "اختر نوع الغياب",
                    options=["غياب بعذر", "غياب بدون عذر"],
                    key="absence_type"
                )
            
            with col_type2:
                notes = st.text_area(
                    "ملاحظات إضافية",
                    placeholder="أدخل أي ملاحظات إضافية...",
                    height=100,
                    key="attendance_notes"
                )
            
            # زر الحفظ
            st.markdown('<div style="height: 30px"></div>', unsafe_allow_html=True)
            
            col_btn1, col_btn2, col_btn3 = st.columns([1, 2, 1])
            
            with col_btn2:
                submit_button = st.form_submit_button(
                    "💾 حفظ وتسجيل الغياب",
                    use_container_width=True,
                    type="primary"
                )
            
            if submit_button:
                if not selected_students:
                    st.error("❌ يجب اختيار طالب واحد على الأقل")
                elif not selected_subject:
                    st.error("❌ يجب اختيار المادة الدراسية")
                else:
                    with st.spinner("جاري تسجيل الغياب..."):
                        # تسجيل غياب لكل طالب مختار
                        success_count = 0
                        failed_students = []
                        
                        for student in selected_students:
                            success, message = attendance_manager.record_attendance(
                                student=student,
                                teacher=teacher_name,
                                status=absence_type,
                                date=date_str,
                                subject=selected_subject,
                                notes=notes
                            )
                            
                            if success:
                                success_count += 1
                            else:
                                failed_students.append((student, message))
                        
                        # تسجيل حضور للطلاب غير المختارين
                        present_students = [s for s in st.session_state.students_data if s not in selected_students]
                        for student in present_students:
                            success, message = attendance_manager.record_attendance(
                                student=student,
                                teacher=teacher_name,
                                status="حاضر",
                                date=date_str,
                                subject=selected_subject,
                                notes="حضور طبيعي"
                            )
                            
                            if success:
                                success_count += 1
                            else:
                                failed_students.append((student, message))
                        
                        # عرض النتائج
                        if success_count > 0:
                            st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                            
                            # تفاصيل التسجيل
                            col_s1, col_s2 = st.columns(2)
                            
                            with col_s1:
                                st.info(f"📅 التاريخ: {date_str}")
                                st.info(f"📚 المادة: {selected_subject}")
                            
                            with col_s2:
                                st.info(f"👨‍🏫 المعلم: {teacher_name}")
                                st.info(f"📝 النوع: {absence_type}")
                            
                            # قائمة الغائبين
                            if selected_students:
                                st.markdown("### 📋 قائمة الغائبين")
                                for i, student in enumerate(selected_students, 1):
                                    st.markdown(f"{i}. **{student}**")
                            
                            # تحميل التقرير
                            st.markdown("---")
                            col_d1, col_d2 = st.columns(2)
                            
                            with col_d1:
                                # إنشاء CSV
                                import csv
                                csv_data = io.StringIO()
                                writer = csv.writer(csv_data)
                                writer.writerow(["الطالب", "الحالة", "التاريخ", "المادة", "المعلم", "ملاحظات"])
                                
                                for student in st.session_state.students_data:
                                    status = absence_type if student in selected_students else "حاضر"
                                    writer.writerow([student, status, date_str, selected_subject, teacher_name, notes])
                                
                                st.download_button(
                                    label="📥 تحميل التقرير (CSV)",
                                    data=csv_data.getvalue(),
                                    file_name=f"تقرير_غياب_{date_str}.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                            
                            with col_d2:
                                if st.button("🔄 تسجيل جديد", use_container_width=True):
                                    st.rerun()
                        
                        if failed_students:
                            st.error("⚠️ حدثت أخطاء في تسجيل بعض الطلاب:")
                            for student, error in failed_students:
                                st.error(f"• {student}: {error}")
        
        # قائمة الطلاب الكاملة
        st.markdown("### 👨‍🎓 قائمة الطلاب الكاملة")
        
        # عرض الطلاب في شبكة
        cols = st.columns(5)
        for i, student in enumerate(st.session_state.students_data):
            with cols[i % 5]:
                st.markdown(f"""
                <div style="padding: 12px; margin: 8px 0; background: #f8fafc; 
                            border-radius: 10px; border: 1px solid #e2e8f0; text-align: center;">
                    <div style="font-size: 24px; margin-bottom: 8px;">👨‍🎓</div>
                    <div style="font-weight: 600; color: #1e40af; font-size: 14px;">{student}</div>
                </div>
                """, unsafe_allow_html=True)
        
        st.markdown('</div>', unsafe_allow_html=True)

class StudentReportPage:
    """صفحة تقرير الطالب"""
    
    @staticmethod
    def render():
        """عرض صفحة تقرير الطالب"""
        if st.session_state.user_role != "student":
            st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
            st.session_state.current_page = "home"
            st.rerun()
            return
        
        student_name = st.session_state.user_name
        
        st.markdown('<div class="page-container fade-in">', unsafe_allow_html=True)
        
        st.markdown(f'<div class="page-title">📊 تقرير الطالب: {student_name}</div>', unsafe_allow_html=True)
        
        # معلومات الطالب
        user_info = user_manager.get_user_info(student_name)
        
        st.markdown(f"""
        <div style="padding: 25px; background: linear-gradient(135deg, #ecfdf5, #a7f3d0); 
                    border-radius: 15px; margin-bottom: 30px; border: 2px solid #34d399;">
            <div style="display: flex; align-items: center; gap: 25px;">
                <div style="font-size: 60px;">👨‍🎓</div>
                <div>
                    <h3 style="margin: 0; color: #059669;">الطالب: {student_name}</h3>
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 15px;">
                        <div>
                            <div style="font-weight: bold; color: #1e40af;">🎓 الصف:</div>
                            <div>{user_info.get('grade', 'غير محدد')}</div>
                        </div>
                        <div>
                            <div style="font-weight: bold; color: #1e40af;">🆔 الرقم:</div>
                            <div>{user_info.get('student_id', 'غير محدد')}</div>
                        </div>
                        <div>
                            <div style="font-weight: bold; color: #1e40af;">📅 تاريخ الميلاد:</div>
                            <div>{user_info.get('birth_date', 'غير محدد')}</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # الحصول على سجلات الطالب
        student_records = attendance_manager.get_student_records(student_name)
        
        if not student_records:
            st.info("📭 لا توجد سجلات غياب لك بعد")
            
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("🏠 العودة للرئيسية", use_container_width=True):
                    st.session_state.current_page = "home"
                    st.rerun()
            
            st.markdown('</div>', unsafe_allow_html=True)
            return
        
        # إحصائيات الطالب
        total_records = len(student_records)
        present_count = len([r for r in student_records if r["status"] == "حاضر"])
        excused_count = len([r for r in student_records if r["status"] == "غياب بعذر"])
        unexcused_count = len([r for r in student_records if r["status"] == "غياب بدون عذر"])
        attendance_rate = (present_count / total_records * 100) if total_records > 0 else 0
        
        st.markdown("### 📈 إحصائيات الحضور والغياب")
        
        col_s1, col_s2, col_s3, col_s4 = st.columns(4)
        
        with col_s1:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">✅</div>
                <div class="card-value">{present_count}</div>
                <div class="card-label">حضور</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_s2:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">⚠️</div>
                <div class="card-value">{excused_count}</div>
                <div class="card-label">غياب بعذر</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_s3:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">❌</div>
                <div class="card-value">{unexcused_count}</div>
                <div class="card-label">غياب بدون عذر</div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_s4:
            st.markdown(f"""
            <div class="stats-card">
                <div class="card-icon">📊</div>
                <div class="card-value">{attendance_rate:.1f}%</div>
                <div class="card-label">نسبة الحضور</div>
            </div>
            """, unsafe_allow_html=True)
        
        # مرشحات العرض
        st.markdown("### 🔍 تصفية السجلات")
        
        col_filter1, col_filter2, col_filter3 = st.columns(3)
        
        with col_filter1:
            filter_status = st.selectbox(
                "حالة الغياب",
                options=["الكل", "حاضر", "غياب بعذر", "غياب بدون عذر"],
                key="student_filter_status"
            )
        
        with col_filter2:
            filter_subject = st.selectbox(
                "المادة",
                options=["الكل"] + st.session_state.subjects_data,
                key="student_filter_subject"
            )
        
        with col_filter3:
            # حساب تواريخ البدء والنهاية
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)
            
            date_range = st.date_input(
                "الفترة الزمنية",
                value=(start_date, end_date),
                key="student_date_range"
            )
        
        # تطبيق المرشحات
        filtered_records = student_records.copy()
        
        if filter_status != "الكل":
            filtered_records = [r for r in filtered_records if r["status"] == filter_status]
        
        if filter_subject != "الكل":
            filtered_records = [r for r in filtered_records if r["subject"] == filter_subject]
        
        if len(date_range) == 2:
            start_date_str, end_date_str = date_range
            filtered_records = [
                r for r in filtered_records 
                if start_date_str.strftime("%Y-%m-%d") <= r["date"] <= end_date_str.strftime("%Y-%m-%d")
            ]
        
        # عرض الجدول
        st.markdown(f"### 📋 تفاصيل السجلات ({len(filtered_records)} سجل)")
        
        if filtered_records:
            # تحويل إلى DataFrame للعرض
            df_display = pd.DataFrame(filtered_records)
            df_display = df_display[["date", "subject", "teacher", "status", "notes"]]
            df_display.columns = ["التاريخ", "المادة", "المعلم", "الحالة", "ملاحظات"]
            
            # تنسيق الجدول
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "التاريخ": st.column_config.TextColumn("التاريخ", width="medium"),
                    "المادة": st.column_config.TextColumn("المادة", width="medium"),
                    "المعلم": st.column_config.TextColumn("المعلم", width="medium"),
                    "الحالة": st.column_config.TextColumn("الحالة", width="small"),
                    "ملاحظات": st.column_config.TextColumn("ملاحظات", width="large")
                }
            )
            
            # تحميل التقارير
            st.markdown("### 📥 تحميل التقارير")
            
            col_download1, col_download2, col_download3 = st.columns(3)
            
            with col_download1:
                # CSV
                csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📄 تحميل CSV",
                    data=csv_data,
                    file_name=f"سجلات_{student_name}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col_download2:
                # Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_display.to_excel(writer, index=False, sheet_name='سجلات_الغياب')
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 تحميل Excel",
                    data=excel_buffer,
                    file_name=f"سجلات_{student_name}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col_download3:
                if st.button("📈 رسم بياني", use_container_width=True):
                    # إنشاء مخطط بسيط
                    import matplotlib.pyplot as plt
                    
                    status_counts = df_display["الحالة"].value_counts()
                    
                    fig, ax = plt.subplots(figsize=(8, 6))
                    colors = ['#10b981', '#f59e0b', '#ef4444']
                    ax.pie(status_counts.values, labels=status_counts.index, autopct='%1.1f%%',
                          colors=colors, startangle=90)
                    ax.set_title('توزيع حالات الغياب')
                    
                    st.pyplot(fig)
        
        else:
            st.info("📭 لا توجد سجلات تطابق معايير البحث")
        
        st.markdown('</div>', unsafe_allow_html=True)

class ReportsPage:
    """صفحة التقارير للمعلمين"""
    
    @staticmethod
    def render():
        """عرض صفحة التقارير"""
        if st.session_state.user_role != "teacher":
            st.error("❌ ليس لديك صلاحية الوصول إلى هذه الصفحة")
            st.session_state.current_page = "home"
            st.rerun()
            return
        
        st.markdown('<div class="page-container fade-in">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">📊 التقارير والإحصائيات</div>', unsafe_allow_html=True)
        
        # إحصائيات عامة
        stats = attendance_manager.get_statistics()
        
        st.markdown("### 📈 إحصائيات عامة")
        
        col_stats1, col_stats2, col_stats3, col_stats4 = st.columns(4)
        
        with col_stats1:
            st.metric("إجمالي السجلات", f"{stats['total_records']:,}")
        
        with col_stats2:
            st.metric("عدد الطلاب", stats['total_students'])
        
        with col_stats3:
            st.metric("نسبة الحضور", f"{stats['attendance_rate']}%")
        
        with col_stats4:
            today = datetime.now().strftime("%Y-%m-%d")
            today_records = len([r for r in st.session_state.attendance_data if r["date"] == today])
            st.metric("سجلات اليوم", today_records)
        
        # مرشحات التقارير
        st.markdown("### 🔍 تصفية البيانات")
        
        with st.expander("خيارات التصفية المتقدمة", expanded=True):
            col_filter1, col_filter2, col_filter3 = st.columns(3)
            
            with col_filter1:
                filter_student = st.selectbox(
                    "الطالب",
                    options=["الكل"] + sorted(st.session_state.students_data),
                    key="report_filter_student"
                )
            
            with col_filter2:
                filter_teacher = st.selectbox(
                    "المعلم",
                    options=["الكل"] + sorted(st.session_state.teachers_data),
                    key="report_filter_teacher"
                )
            
            with col_filter3:
                filter_subject = st.selectbox(
                    "المادة",
                    options=["الكل"] + sorted(st.session_state.subjects_data),
                    key="report_filter_subject"
                )
            
            col_filter4, col_filter5 = st.columns(2)
            
            with col_filter4:
                filter_status = st.selectbox(
                    "حالة الغياب",
                    options=["الكل", "حاضر", "غياب بعذر", "غياب بدون عذر"],
                    key="report_filter_status"
                )
            
            with col_filter5:
                date_range = st.date_input(
                    "الفترة الزمنية",
                    value=[datetime.now() - timedelta(days=30), datetime.now()],
                    key="report_date_range"
                )
        
        # تطبيق المرشحات
        filters = {}
        if filter_student != "الكل":
            filters["student"] = filter_student
        if filter_teacher != "الكل":
            filters["teacher"] = filter_teacher
        if filter_subject != "الكل":
            filters["subject"] = filter_subject
        if filter_status != "الكل":
            filters["status"] = filter_status
        
        if len(date_range) == 2:
            start_date, end_date = date_range
            filters["date_range"] = (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d"))
        
        # الحصول على البيانات المصفاة
        filtered_data = attendance_manager.get_all_records(filters)
        
        if "date_range" in filters:
            start_date, end_date = filters.pop("date_range")
            filtered_data = [r for r in filtered_data if start_date <= r["date"] <= end_date]
        
        # عرض النتائج
        st.markdown(f"### 📋 النتائج ({len(filtered_data)} سجل)")
        
        if filtered_data:
            # تحويل إلى DataFrame
            df_display = pd.DataFrame(filtered_data)
            df_display = df_display[["date", "student", "teacher", "subject", "status", "notes"]]
            df_display.columns = ["التاريخ", "الطالب", "المعلم", "المادة", "الحالة", "ملاحظات"]
            
            # عرض الجدول
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True
            )
            
            # خيارات التحميل
            st.markdown("### 💾 خيارات التحميل")
            
            col_dl1, col_dl2, col_dl3 = st.columns(3)
            
            with col_dl1:
                # CSV
                csv_data = df_display.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 تحميل CSV",
                    data=csv_data,
                    file_name=f"تقرير_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col_dl2:
                # Excel
                excel_buffer = io.BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    df_display.to_excel(writer, index=False, sheet_name='تقرير_الغياب')
                    
                    # إضافة ورقة للإحصائيات
                    stats_df = pd.DataFrame([stats])
                    stats_df.to_excel(writer, index=False, sheet_name='الإحصائيات')
                
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 تحميل Excel",
                    data=excel_buffer,
                    file_name=f"تقرير_مفصل_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            with col_dl3:
                if st.button("📈 إنشاء مخططات", use_container_width=True):
                    # إنشاء مخططات
                    import matplotlib.pyplot as plt
                    
                    # مخطط توزيع الحالات
                    fig1, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
                    
                    # مخطط دائري للحالات
                    status_counts = df_display["الحالة"].value_counts()
                    ax1.pie(status_counts.values, labels=status_counts.index, autopct='%1.1f%%',
                           colors=['#10b981', '#f59e0b', '#ef4444'])
                    ax1.set_title('توزيع حالات الغياب')
                    
                    # مخطط أعمدة للمواد
                    subject_counts = df_display["المادة"].value_counts().head(8)
                    ax2.barh(subject_counts.index, subject_counts.values, color='#3b82f6')
                    ax2.set_title('الغياب حسب المادة (الأكثر شيوعاً)')
                    
                    st.pyplot(fig1)
                    
                    # مخطط الخط الزمني
                    if len(date_range) == 2:
                        fig2, ax3 = plt.subplots(figsize=(10, 6))
                        
                        # تحويل التاريخ
                        df_display['التاريخ_مفهرس'] = pd.to_datetime(df_display['التاريخ'])
                        daily_counts = df_display.groupby('التاريخ_مفهرس').size()
                        
                        ax3.plot(daily_counts.index, daily_counts.values, marker='o', 
                                color='#8b5cf6', linewidth=2)
                        ax3.fill_between(daily_counts.index, daily_counts.values, 
                                        alpha=0.3, color='#8b5cf6')
                        ax3.set_title('عدد السجلات اليومي')
                        ax3.set_xlabel('التاريخ')
                        ax3.set_ylabel('عدد السجلات')
                        ax3.grid(True, alpha=0.3)
                        
                        st.pyplot(fig2)
        
        else:
            st.info("📭 لا توجد بيانات تطابق معايير البحث")
        
        st.markdown('</div>', unsafe_allow_html=True)

class SettingsPage:
    """صفحة الإعدادات"""
    
    @staticmethod
    def render():
        """عرض صفحة الإعدادات"""
        st.markdown('<div class="page-container fade-in">', unsafe_allow_html=True)
        
        st.markdown('<div class="page-title">⚙️ الإعدادات</div>', unsafe_allow_html=True)
        
        # معلومات الحساب
        st.markdown("### 👤 معلومات الحساب")
        
        user_info = user_manager.get_user_info(st.session_state.user_name)
        
        col_info1, col_info2 = st.columns(2)
        
        with col_info1:
            st.markdown(f"""
            <div style="padding: 25px; background: #f8fafc; border-radius: 15px; border: 1px solid #e2e8f0;">
                <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 20px;">
                    <div style="font-size: 50px;">
                        {"👨‍🏫" if st.session_state.user_role == "teacher" else "👨‍🎓"}
                    </div>
                    <div>
                        <h3 style="margin: 0; color: #1e40af;">{st.session_state.user_name}</h3>
                        <p style="margin: 5px 0 0 0; color: #64748b;">
                            {"معلم" if st.session_state.user_role == "teacher" else "طالب"}
                        </p>
                    </div>
                </div>
                
                <div style="color: #475569;">
                    {HomePage.render_user_details(user_info)}
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        with col_info2:
            st.markdown(f"""
            <div style="padding: 25px; background: #f8fafc; border-radius: 15px; border: 1px solid #e2e8f0;">
                <h4 style="color: #1e40af; margin-bottom: 20px;">📊 إحصائيات الحساب</h4>
                
                <div style="color: #475569;">
                    <div style="margin-bottom: 15px;">
                        <div style="font-weight: bold; color: #2563eb;">📅 تاريخ التسجيل:</div>
                        <div>{datetime.now().strftime('%Y-%m-%d')}</div>
                    </div>
                    
                    <div style="margin-bottom: 15px;">
                        <div style="font-weight: bold; color: #2563eb;">🔄 آخر دخول:</div>
                        <div>{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
                    </div>
                    
                    <div style="margin-bottom: 15px;">
                        <div style="font-weight: bold; color: #2563eb;">📋 عدد السجلات:</div>
                        <div>{len(st.session_state.attendance_data)}</div>
                    </div>
                    
                    <div>
                        <div style="font-weight: bold; color: #2563eb;">💾 حجم البيانات:</div>
                        <div>{(len(json.dumps(st.session_state.attendance_data)) / 1024):.2f} كيلوبايت</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        # إعدادات التطبيق
        st.markdown("### 🔧 إعدادات التطبيق")
        
        tab1, tab2, tab3 = st.tabs(["📱 الواجهة", "🔔 الإشعارات", "💾 البيانات"])
        
        with tab1:
            col_ui1, col_ui2 = st.columns(2)
            
            with col_ui1:
                theme = st.selectbox(
                    "النمط",
                    options=["فاتح", "داكن", "تلقائي"],
                    index=0,
                    key="settings_theme"
                )
                
                language = st.selectbox(
                    "اللغة",
                    options=["العربية", "English"],
                    index=0,
                    key="settings_language"
                )
            
            with col_ui2:
                font_size = st.slider(
                    "حجم الخط",
                    min_value=12,
                    max_value=24,
                    value=16,
                    key="settings_font_size"
                )
                
                auto_refresh = st.checkbox(
                    "تحديث تلقائي",
                    value=True,
                    key="settings_auto_refresh"
                )
            
            if st.button("💾 حفظ إعدادات الواجهة", use_container_width=True):
                st.session_state.settings['theme'] = theme
                st.session_state.settings['language'] = 'ar' if language == "العربية" else 'en'
                st.success("✅ تم حفظ إعدادات الواجهة")
        
        with tab2:
            col_not1, col_not2 = st.columns(2)
            
            with col_not1:
                email_notifications = st.checkbox(
                    "الإشعارات عبر البريد الإلكتروني",
                    value=True,
                    key="settings_email_notifications"
                )
                
                push_notifications = st.checkbox(
                    "الإشعارات الفورية",
                    value=True,
                    key="settings_push_notifications"
                )
            
            with col_not2:
                notification_frequency = st.selectbox(
                    "تكرار الإشعارات",
                    options=["فوري", "يومي", "أسبوعي", "شهري"],
                    index=0,
                    key="settings_notification_frequency"
                )
                
                sound_notifications = st.checkbox(
                    "أصوات التنبيه",
                    value=True,
                    key="settings_sound_notifications"
                )
            
            if st.button("💾 حفظ إعدادات الإشعارات", use_container_width=True):
                st.session_state.settings['notifications'] = {
                    'email': email_notifications,
                    'push': push_notifications,
                    'frequency': notification_frequency,
                    'sound': sound_notifications
                }
                st.success("✅ تم حفظ إعدادات الإشعارات")
        
        with tab3:
            col_data1, col_data2 = st.columns(2)
            
            with col_data1:
                auto_save = st.checkbox(
                    "حفظ تلقائي",
                    value=True,
                    key="settings_auto_save"
                )
                
                backup_frequency = st.selectbox(
                    "تكرار النسخ الاحتياطي",
                    options=["يومي", "أسبوعي", "شهري", "يدوي"],
                    index=0,
                    key="settings_backup_frequency"
                )
            
            with col_data2:
                data_retention = st.slider(
                    "فترة احتفاظ البيانات (أشهر)",
                    min_value=1,
                    max_value=36,
                    value=12,
                    key="settings_data_retention"
                )
                
                export_format = st.selectbox(
                    "تنسيق التصدير",
                    options=["CSV", "Excel", "JSON", "PDF"],
                    index=0,
                    key="settings_export_format"
                )
            
            # إدارة البيانات
            st.markdown("### 💾 إدارة البيانات")
            
            col_manage1, col_manage2, col_manage3 = st.columns(3)
            
            with col_manage1:
                if st.button("📥 نسخة احتياطية", use_container_width=True):
                    success, message = attendance_manager.save_data()
                    if success:
                        st.success("✅ تم إنشاء نسخة احتياطية")
                    else:
                        st.error(f"❌ {message}")
            
            with col_manage2:
                if st.button("🔄 استعادة بيانات", use_container_width=True):
                    attendance_manager.load_data()
                    st.success("✅ تم استعادة البيانات")
                    time.sleep(1)
                    st.rerun()
            
            with col_manage3:
                if st.button("🗑️ حذف البيانات", use_container_width=True, type="secondary"):
                    if st.checkbox("تأكيد حذف جميع البيانات"):
                        st.session_state.attendance_data = []
                        if os.path.exists("attendance_data.json"):
                            os.remove("attendance_data.json")
                        if os.path.exists("attendance_backup.json"):
                            os.remove("attendance_backup.json")
                        st.success("✅ تم حذف جميع البيانات")
                        time.sleep(2)
                        st.rerun()
        
        # تغيير كلمة المرور
        st.markdown("### 🔒 تغيير كلمة المرور")
        
        with st.form("change_password_form"):
            current_password = st.text_input("كلمة المرور الحالية", type="password")
            new_password = st.text_input("كلمة المرور الجديدة", type="password")
            confirm_password = st.text_input("تأكيد كلمة المرور", type="password")
            
            if st.form_submit_button("تغيير كلمة المرور", use_container_width=True):
                if current_password and new_password and confirm_password:
                    if new_password == confirm_password:
                        # التحقق من كلمة المرور الحالية
                        hashed_current = user_manager.hash_password(current_password)
                        if hashed_current == user_manager.users[st.session_state.user_name]["password"]:
                            # تحديث كلمة المرور
                            user_manager.users[st.session_state.user_name]["password"] = user_manager.hash_password(new_password)
                            st.success("✅ تم تغيير كلمة المرور بنجاح")
                        else:
                            st.error("❌ كلمة المرور الحالية غير صحيحة")
                    else:
                        st.error("❌ كلمات المرور غير متطابقة")
                else:
                    st.error("❌ من فضلك املأ جميع الحقول")
        
        # تسجيل الخروج
        st.markdown("---")
        
        col_logout1, col_logout2, col_logout3 = st.columns([1, 2, 1])
        
        with col_logout2:
            if st.button("🚪 تسجيل الخروج من جميع الأجهزة", 
                        use_container_width=True, 
                        type="secondary"):
                st.session_state.logged_in = False
                st.session_state.user_role = ""
                st.session_state.user_name = ""
                st.session_state.current_page = "login"
                st.success("✅ تم تسجيل الخروج بنجاح")
                time.sleep(1)
                st.rerun()
        
        st.markdown('</div>', unsafe_allow_html=True)

# ==================== التطبيق الرئيسي ====================
def main():
    """الدالة الرئيسية للتطبيق"""
    
    # التحقق من حالة تسجيل الدخول
    if not st.session_state.logged_in:
        LoginPage.render()
    else:
        # عرض الشريط العلوي
        Header.render()
        
        # عرض القائمة الجانبية
        Sidebar.render()
        
        # عرض الصفحة الحالية
        current_page = st.session_state.current_page
        
        if current_page == "home":
            HomePage.render()
        elif current_page == "attendance":
            AttendancePage.render()
        elif current_page == "my_report":
            StudentReportPage.render()
        elif current_page == "reports":
            ReportsPage.render()
        elif current_page == "settings":
            SettingsPage.render()
        elif current_page == "students":
            # صفحة إدارة الطلاب (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">👨‍🎓 إدارة الطلاب</div>', unsafe_allow_html=True)
            st.info("🚧 هذه الصفحة قيد التطوير")
            st.markdown('</div>', unsafe_allow_html=True)
        elif current_page == "schedule":
            # صفحة الجدول الدراسي (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">📅 الجدول الدراسي</div>', unsafe_allow_html=True)
            st.info("🚧 هذه الصفحة قيد التطوير")
            st.markdown('</div>', unsafe_allow_html=True)
        elif current_page == "my_records":
            # صفحة سجلات الطالب (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">📋 سجلاتي</div>', unsafe_allow_html=True)
            StudentReportPage.render()
            st.markdown('</div>', unsafe_allow_html=True)
        elif current_page == "my_schedule":
            # صفحة جدول الطالب (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">📅 جدولي الدراسي</div>', unsafe_allow_html=True)
            st.info("🚧 هذه الصفحة قيد التطوير")
            st.markdown('</div>', unsafe_allow_html=True)
        elif current_page == "achievements":
            # صفحة إنجازات الطالب (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">🏆 إنجازاتي</div>', unsafe_allow_html=True)
            st.info("🚧 هذه الصفحة قيد التطوير")
            st.markdown('</div>', unsafe_allow_html=True)
        elif current_page == "notifications":
            # صفحة الإشعارات (مبسطة)
            st.markdown('<div class="page-container">', unsafe_allow_html=True)
            st.markdown('<div class="page-title">🔔 الإشعارات</div>', unsafe_allow_html=True)
            
            if st.session_state.notifications:
                for notification in reversed(st.session_state.notifications[-10:]):
                    type_icon = {
                        "success": "✅",
                        "error": "❌",
                        "warning": "⚠️",
                        "info": "ℹ️"
                    }.get(notification["type"], "📌")
                    
                    st.markdown(f"""
                    <div style="padding: 15px; margin: 10px 0; background: white; 
                                border-radius: 10px; border: 1px solid #e5e7eb;
                                border-left: 4px solid {'#10b981' if notification['type'] == 'success' else 
                                                       '#ef4444' if notification['type'] == 'error' else 
                                                       '#f59e0b' if notification['type'] == 'warning' else '#3b82f6'}">
                        <div style="display: flex; justify-content: space-between; align-items: start;">
                            <div>
                                <strong>{type_icon} {notification['title']}</strong>
                                <div style="color: #64748b; margin-top: 5px;">{notification['message']}</div>
                            </div>
                            <div style="font-size: 0.9rem; color: #94a3b8;">{notification['time']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("📭 لا توجد إشعارات جديدة")
            
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.session_state.current_page = "home"
            st.rerun()
    
    # تذييل الصفحة
    st.markdown("""
    <div class="footer">
        <div style="display: flex; justify-content: center; gap: 30px; margin-bottom: 15px; flex-wrap: wrap;">
            <div>📧 support@school.edu</div>
            <div>📞 01234567890</div>
            <div>🏫 شارع المدرسة، القاهرة، مصر</div>
        </div>
        <div style="color: #94a3b8; font-size: 0.9rem;">
            نظام إدارة الغياب الذكي © 2024 | الإصدار 3.0.0 | مدرسة الإبداع
        </div>
    </div>
    """, unsafe_allow_html=True)

# تشغيل التطبيق
if __name__ == "__main__":
    main()
