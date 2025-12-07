import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime
import io
import os
import json
import logging
import base64
import requests
import hashlib
import uuid

# Arabic/RTL PDF support
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
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
st.set_page_config(page_title="نظام الغياب", layout="wide", initial_sidebar_state="collapsed")

# ------------------ App settings ------------------
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ New Users Database ------------------
USERS_DB_FILE = "users_database.json"

class UsersDatabase:
    """فئة لإدارة قاعدة بيانات المستخدمين"""
    
    def __init__(self):
        self.db_file = USERS_DB_FILE
        self.init_database()
    
    def init_database(self):
        """تهيئة قاعدة البيانات إذا لم تكن موجودة"""
        if not os.path.exists(self.db_file):
            default_data = {
                "users": [],
                "sessions": [],
                "statistics": {
                    "total_users": 0,
                    "total_logins": 0,
                    "total_teachers": 0,
                    "total_students": 0,
                    "active_sessions": 0
                },
                "metadata": {
                    "created_at": datetime.now().isoformat(),
                    "last_updated": datetime.now().isoformat(),
                    "version": "1.0.0"
                }
            }
            self.save_database(default_data)
    
    def load_database(self):
        """تحميل قاعدة البيانات من ملف JSON"""
        try:
            with open(self.db_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # تحديث آخر وقت تحديث
                data["metadata"]["last_updated"] = datetime.now().isoformat()
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            self.init_database()
            return self.load_database()
    
    def save_database(self, data):
        """حفظ قاعدة البيانات إلى ملف JSON"""
        try:
            data["metadata"]["last_updated"] = datetime.now().isoformat()
            with open(self.db_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Error saving database: {str(e)}")
            return False
    
    def hash_password(self, password):
        """تشفير كلمة المرور"""
        salt = "school_attendance_system_salt_2024"
        return hashlib.sha256((password + salt).encode()).hexdigest()
    
    def generate_user_id(self):
        """إنشاء معرف فريد للمستخدم"""
        return f"user_{uuid.uuid4().hex[:8]}"
    
    def generate_session_id(self):
        """إنشاء معرف فريد للجلسة"""
        return f"session_{uuid.uuid4().hex[:12]}"
    
    def register_user(self, name, email, password, user_type, teacher_name=None):
        """تسجيل مستخدم جديد"""
        db = self.load_database()
        
        # التحقق من عدم تكرار الإيميل
        for user in db["users"]:
            if user["email"].lower() == email.lower():
                return False, "Email already exists"
        
        # إنشاء مستخدم جديد
        new_user = {
            "id": self.generate_user_id(),
            "name": name,
            "email": email.lower(),
            "password_hash": self.hash_password(password),
            "user_type": user_type,  # "teacher" أو "student"
            "teacher_name": teacher_name if user_type == "teacher" else None,
            "created_at": datetime.now().isoformat(),
            "last_login": None,
            "login_count": 0,
            "is_active": True,
            "preferences": {
                "theme": "light",
                "language": "ar",
                "notifications": True
            }
        }
        
        db["users"].append(new_user)
        
        # تحديث الإحصائيات
        db["statistics"]["total_users"] = len(db["users"])
        if user_type == "teacher":
            db["statistics"]["total_teachers"] += 1
        else:
            db["statistics"]["total_students"] += 1
        
        if self.save_database(db):
            return True, "User registered successfully"
        else:
            return False, "Failed to save user data"
    
    def authenticate_user(self, email, password):
        """المصادقة على المستخدم"""
        db = self.load_database()
        
        for user in db["users"]:
            if user["email"].lower() == email.lower():
                if user["password_hash"] == self.hash_password(password):
                    if user.get("is_active", True):
                        # تحديث معلومات تسجيل الدخول
                        user["last_login"] = datetime.now().isoformat()
                        user["login_count"] = user.get("login_count", 0) + 1
                        
                        # إنشاء جلسة جديدة
                        session_id = self.generate_session_id()
                        new_session = {
                            "session_id": session_id,
                            "user_id": user["id"],
                            "user_email": email,
                            "user_type": user["user_type"],
                            "login_time": datetime.now().isoformat(),
                            "logout_time": None,
                            "ip_address": "localhost",  # يمكن إضافة IP حقيقي لاحقاً
                            "user_agent": "streamlit_app"
                        }
                        db["sessions"].append(new_session)
                        
                        # تحديث الإحصائيات
                        db["statistics"]["total_logins"] += 1
                        db["statistics"]["active_sessions"] = len([
                            s for s in db["sessions"] if s["logout_time"] is None
                        ])
                        
                        self.save_database(db)
                        
                        # إرجاع بيانات المستخدم والجلسة
                        return True, {
                            "user": user,
                            "session_id": session_id
                        }
                    else:
                        return False, "Account is deactivated"
                else:
                    return False, "Invalid password"
        
        return False, "User not found"
    
    def logout_user(self, session_id):
        """تسجيل خروج المستخدم"""
        db = self.load_database()
        
        for session in db["sessions"]:
            if session["session_id"] == session_id and session["logout_time"] is None:
                session["logout_time"] = datetime.now().isoformat()
                db["statistics"]["active_sessions"] = len([
                    s for s in db["sessions"] if s["logout_time"] is None
                ])
                self.save_database(db)
                return True
        
        return False
    
    def get_user_by_email(self, email):
        """الحصول على بيانات المستخدم بواسطة الإيميل"""
        db = self.load_database()
        
        for user in db["users"]:
            if user["email"].lower() == email.lower():
                return user
        
        return None
    
    def get_user_by_id(self, user_id):
        """الحصول على بيانات المستخدم بواسطة المعرف"""
        db = self.load_database()
        
        for user in db["users"]:
            if user["id"] == user_id:
                return user
        
        return None
    
    def update_user_preferences(self, user_id, preferences):
        """تحديث تفضيلات المستخدم"""
        db = self.load_database()
        
        for user in db["users"]:
            if user["id"] == user_id:
                user["preferences"].update(preferences)
                self.save_database(db)
                return True
        
        return False
    
    def get_all_users(self):
        """الحصول على جميع المستخدمين"""
        db = self.load_database()
        return db["users"]
    
    def get_active_sessions(self):
        """الحصول على الجلسات النشطة"""
        db = self.load_database()
        return [s for s in db["sessions"] if s["logout_time"] is None]
    
    def get_statistics(self):
        """الحصول على إحصائيات قاعدة البيانات"""
        db = self.load_database()
        return db["statistics"]
    
    def get_recent_sessions(self, limit=10):
        """الحصول على أحدث الجلسات"""
        db = self.load_database()
        sessions = db["sessions"][-limit:][::-1]  # أحدث الجلسات أولاً
        return sessions
    
    def reset_password(self, email, new_password):
        """إعادة تعيين كلمة المرور"""
        db = self.load_database()
        
        for user in db["users"]:
            if user["email"].lower() == email.lower():
                user["password_hash"] = self.hash_password(new_password)
                self.save_database(db)
                return True, "Password reset successfully"
        
        return False, "User not found"

# إنشاء كائن قاعدة البيانات
users_db = UsersDatabase()

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
                    headers = ["student", "teacher", "status", "date"]
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

# ------------------ HTML للواجهة التفاعلية ------------------
def show_login_page():
    """عرض صفحة تسجيل الدخول التفاعلية"""
    html_code = """
<div class="container" id="container">
  <div class="form-container sign-up-container">
    <form action="#" id="signupForm">
      <h1>Create Account</h1>
      <div class="social-container">
      </div>
      <span>or use your email for registration</span>
      <input type="text" placeholder="Name" id="signupName" />
      <input type="email" placeholder="Email" id="signupEmail" />
      <input type="password" placeholder="Password" id="signupPassword" />
      <input type="password" placeholder="Confirm Password" id="signupConfirmPassword" />
      <button type="button" onclick="handleSignUp()">Sign Up</button>
    </form>
  </div>
  <div class="form-container sign-in-container">
    <form action="#" id="signinForm">
      <h1>Sign in</h1>
      <div class="social-container">
      </div>
      <span>or use your account</span>
      <input type="email" placeholder="Email" id="signinEmail" />
      <input type="password" placeholder="Password" id="signinPassword" />
      <a href="#" onclick="showForgotPassword()">Forgot your password?</a>
      <button type="button" onclick="handleSignIn()">Sign In</button>
    </form>
  </div>
  <div class="overlay-container">
    <div class="overlay">
      <div class="overlay-panel overlay-left">
        <h1>Welcome Back!</h1>
        <p>To keep connected with us please login with your personal info</p>
        <button class="ghost" id="signIn">Sign In</button>
      </div>
      <div class="overlay-panel overlay-right">
        <h1>Hello, Friend!</h1>
        <p>Enter your personal details and start journey with us</p>
        <button class="ghost" id="signUp">Sign Up</button>
      </div>
    </div>
  </div>
</div>

<style>
@import url("https://fonts.googleapis.com/css?family=Montserrat:400,800");

* {
	box-sizing: border-box;
}

body, html {
	margin: 0;
	padding: 0;
	height: 100%;
	width: 100%;
}

body {
	background: #f6f5f7;
	display: flex;
	justify-content: center;
	align-items: center;
	font-family: "Montserrat", sans-serif;
	overflow: hidden;
}

h1 {
	font-weight: bold;
	margin: 0;
}

h2 {
	text-align: center;
}

p {
	font-size: 14px;
	font-weight: 100;
	line-height: 20px;
	letter-spacing: 0.5px;
	margin: 20px 0 30px;
}

span {
	font-size: 12px;
}

a {
	color: #333;
	font-size: 14px;
	text-decoration: none;
	margin: 15px 0;
}

button {
	border-radius: 20px;
	border: 1px solid #ff4b2b;
	background-color: #ff4b2b;
	color: #ffffff;
	font-size: 12px;
	font-weight: bold;
	padding: 12px 45px;
	letter-spacing: 1px;
	text-transform: uppercase;
	transition: transform 80ms ease-in;
    cursor: pointer;
}

button:active {
	transform: scale(0.95);
}

button:focus {
	outline: none;
}

button.ghost {
	background-color: transparent;
	border-color: #ffffff;
}

form {
	background-color: #ffffff;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-direction: column;
	padding: 0 50px;
	height: 100%;
	text-align: center;
}

input {
	background-color: #eee;
	border: none;
	padding: 12px 15px;
	margin: 8px 0;
	width: 100%;
}

.container {
	background-color: #fff;
	border-radius: 10px;
	box-shadow: 0 14px 28px rgba(0, 0, 0, 0.25), 0 10px 10px rgba(0, 0, 0, 0.22);
	position: relative;
	overflow: hidden;
	width: 100%;
	max-width: 1000px;
	min-height: 700px;
	margin: 20px auto;
}

.form-container {
	position: absolute;
	top: 0;
	height: 100%;
	transition: all 0.6s ease-in-out;
}

.sign-in-container {
	left: 0;
	width: 50%;
	z-index: 2;
}

.container.right-panel-active .sign-in-container {
	transform: translateX(100%);
}

.sign-up-container {
	left: 0;
	width: 50%;
	opacity: 0;
	z-index: 1;
}

.container.right-panel-active .sign-up-container {
	transform: translateX(100%);
	opacity: 1;
	z-index: 5;
	animation: show 0.6s;
}

@keyframes show {
	0%,
	49.99% {
		opacity: 0;
		z-index: 1;
	}

	50%,
	100% {
		opacity: 1;
		z-index: 5;
	}
}

.overlay-container {
	position: absolute;
	top: 0;
	left: 50%;
	width: 50%;
	height: 100%;
	overflow: hidden;
	transition: transform 0.6s ease-in-out;
	z-index: 100;
}

.container.right-panel-active .overlay-container {
	transform: translateX(-100%);
}

.overlay {
	background: #ff416c;
	background: -webkit-linear-gradient(to right, #ff4b2b, #ff416c);
	background: linear-gradient(to right, #ff4b2b, #ff416c);
	background-repeat: no-repeat;
	background-size: cover;
	background-position: 0 0;
	color: #ffffff;
	position: relative;
	left: -100%;
	height: 100%;
	width: 200%;
	transform: translateX(0);
	transition: transform 0.6s ease-in-out;
}

.container.right-panel-active .overlay {
	transform: translateX(50%);
}

.overlay-panel {
	position: absolute;
	display: flex;
	align-items: center;
	justify-content: center;
	flex-direction: column;
	padding: 0 40px;
	text-align: center;
	top: 0;
	height: 100%;
	width: 50%;
	transform: translateX(0);
	transition: transform 0.6s ease-in-out;
}

.overlay-left {
	transform: translateX(-20%);
}

.container.right-panel-active .overlay-left {
	transform: translateX(0);
}

.overlay-right {
	right: 0;
	transform: translateX(0);
}

.container.right-panel-active .overlay-right {
	transform: translateX(20%);
}

.social-container {
	margin: 20px 0;
}

.social-container a {
	border: 1px solid #dddddd;
	border-radius: 50%;
	display: inline-flex;
	justify-content: center;
	align-items: center;
	margin: 0 5px;
	height: 40px;
	width: 40px;
}

/* Streamlit hiding */
[data-testid="stHeader"] { display: none !important; }
[data-testid="stToolbar"] { display: none !important; }
[data-testid="stDecoration"] { display: none !important; }

</style>

<script>
const signUpButton = document.getElementById('signUp');
const signInButton = document.getElementById('signIn');
const container = document.getElementById('container');

signUpButton.addEventListener('click', () => {
	container.classList.add("right-panel-active");
});

signInButton.addEventListener('click', () => {
	container.classList.remove("right-panel-active");
});

function handleSignIn() {
    const email = document.getElementById('signinEmail').value;
    const password = document.getElementById('signinPassword').value;
    
    if (!email || !password) {
        alert('Please fill in both email and password.');
        return;
    }
    
    // التحقق من صحة الإيميل
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        alert('Please enter a valid email address.');
        return;
    }
    
    // إرسال البيانات إلى Streamlit
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: 'login_completed',
        data: {
            email: email,
            password: password,
            action: 'signin'
        }
    }, '*');
}

function handleSignUp() {
    const name = document.getElementById('signupName').value;
    const email = document.getElementById('signupEmail').value;
    const password = document.getElementById('signupPassword').value;
    const confirmPassword = document.getElementById('signupConfirmPassword').value;
    
    if (!name || !email || !password || !confirmPassword) {
        alert('Please fill in all fields.');
        return;
    }
    
    // التحقق من صحة الإيميل
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(email)) {
        alert('Please enter a valid email address.');
        return;
    }
    
    // التحقق من تطابق كلمتي المرور
    if (password !== confirmPassword) {
        alert('Passwords do not match.');
        return;
    }
    
    // التحقق من قوة كلمة المرور
    if (password.length < 6) {
        alert('Password must be at least 6 characters long.');
        return;
    }
    
    // إرسال البيانات إلى Streamlit
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: 'login_completed',
        data: {
            name: name,
            email: email,
            password: password,
            action: 'signup'
        }
    }, '*');
}

function showForgotPassword() {
    const email = prompt("Please enter your email to reset password:");
    if (email) {
        // إرسال طلب استعادة كلمة المرور
        window.parent.postMessage({
            type: 'streamlit:setComponentValue',
            value: 'forgot_password',
            data: { email: email }
        }, '*');
    }
}

// جعل الحاوية تملأ الشاشة كاملة
window.onload = function() {
    const container = document.getElementById('container');
    container.style.width = '95%';
    container.style.maxWidth = '1200px';
    container.style.minHeight = window.innerHeight * 0.8 + 'px';
};
</script>
"""
    
    # إخفاء شريط الأدوات العلوي في صفحة تسجيل الدخول
    st.markdown("""
    <style>
    /* إخفاء header و footer */
    .stApp > header { display: none !important; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    
    /* إخفاء كل شيء غير واجهة تسجيل الدخول */
    .stApp > div:not(:first-child),
    .stApp > div > div:not(:first-child) {
        display: none !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    # إنشاء حاوية مركزية
    col1, col2, col3 = st.columns([1, 10, 1])
    with col2:
        # عرض واجهة تسجيل الدخول التفاعلية
        components.html(html_code, height=800)

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
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    
    try:
        data = worksheet.get_all_records()
    except Exception:
        return pd.DataFrame(columns=["student", "teacher", "status", "date"])
    
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "status", "date"]:
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

def record_attendance(selected_absent, teacher_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    failed = []
    success_count = 0
    
    # حفظ في Google Sheets إذا كان متصلاً
    if worksheet:
        try:
            # إضافة جميع الصفوف مرة واحدة
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
        except Exception as e:
            # إذا فشلت الإضافة الجماعية، نجرب إضافة كل صف على حدة
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append(("جميع الطلاب", str(ex)))
    else:
        failed.append(("جميع الطلاب", "لا يوجد اتصال بـ Google Sheets"))

    # إرسال إشعار Telegram
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}\nتم حفظ {success_count} سجل بنجاح"
    
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
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
    
    return failed, telegram_status, telegram_details, success_count

def get_student_records(student_name):
    df = read_sheet()
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    
    try:
        df_matches = df[df["student"].astype(str).str.contains(student_name, case=False, na=False)].copy()
    except Exception:
        df_matches = df[df["student"].astype(str).str.lower() == student_name.lower()].copy()
    
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"
    })
    return df_matches[["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []
    font_for_style = REGISTERED_FONT or "Helvetica"
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
        absent_count = int((df_records["الحالة"] == "غياب بعذر").sum() + (df_records["الحالة"] == "غياب بدون عذر").sum())
        present_count = int((df_records["الحالة"] == "حاضر").sum())
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Spacer(1, 10))

        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            data.append([
                reshape_arabic_text(row.get("المرة", "")),
                reshape_arabic_text(row.get("الطالب", "")),
                reshape_arabic_text(row.get("المعلم", "")),
                reshape_arabic_text(normalize_date_for_pdf(row.get("التاريخ", ""))),
                reshape_arabic_text(row.get("الحالة", ""))
            ])
        table = Table(data, hAlign='CENTER', colWidths=[60, 150, 120, 110, 70])
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

# ------------------ CSS + Top Toolbar ------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css?family=Montserrat:400,800');
    
    #MainMenu, header, footer {visibility: hidden !important;}
    
    /* Hide Streamlit default elements */
    [data-testid="stHeader"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stDecoration"] { display: none !important; }
    [data-testid="stSidebar"] { display: none !important; }
    
    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
        padding: 0 !important;
        margin: 0 !important;
    }
    
    /* شريط الأدوات العلوي (يظهر فقط في الصفحات الأخرى) */
    .top-toolbar {
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 70px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 999999 !important;
        font-family: 'Cairo', sans-serif;
        color: white;
    }
    .logo-container { display: flex; align-items: center; gap: 12px; }
    .logo-img { 
        width: 48px; height: 48px; border-radius: 12px; 
        object-fit: contain; border: 2px solid rgba(255,255,255,0.3); 
        background: white; padding: 4px;
    }
    .school-info { line-height: 1.3; }
    .school-name { font-size: 17px; font-weight: bold; margin: 0; }
    .school-date { font-size: 12px; opacity: 0.9; margin: 0; }
    .nav-buttons { display: flex; gap: 12px; }
    .nav-btn {
        background: rgba(255, 255, 255, 0.2);
        color: white; border: none; padding: 10px 22px;
        border-radius: 12px; font-size: 15px; font-weight: 600;
        cursor: pointer; transition: all 0.3s ease;
        backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3);
        font-family: 'Cairo', sans-serif;
    }
    .nav-btn:hover {
        background: white; color: #1e40af;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(255,255,255,0.4);
    }
    .content-padding { height: 90px; }
    .modal { display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }
    .modal-content { background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; animation: modalPop 0.3s ease; }
    @keyframes modalPop { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .close-btn { position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }
    .close-btn:hover { color: #e11d48; }
    .modal h3 { text-align: center; color: #1e40af; margin-top: 0; }
    .modal p { text-align: center; color: #475569; line-height: 1.6; }
    .searchBox {
      display: flex;
      max-width: 230px;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      background: #2f3640;
      border-radius: 50px;
      position: relative;
      margin: 20px 0;
    }
    .searchButton {
      color: white;
      position: absolute;
      right: 8px;
      width: 50px;
      height: 50px;
      border-radius: 50%;
      background: var(--gradient-2, linear-gradient(90deg, #2AF598 0%, #009EFD 100%));
      border: 0;
      display: inline-block;
      transition: all 300ms cubic-bezier(.23, 1, 0.32, 1);
      cursor: pointer;
    }
    .searchButton:hover {
      color: #fff;
      background-color: #1A1A1A;
      box-shadow: rgba(0, 0, 0, 0.5) 0 10px 20px;
      transform: translateY(-3px);
    }
    .searchButton:active {
      box-shadow: none;
      transform: translateY(0);
    }
    .searchInput {
      border: none;
      background: none;
      outline: none;
      color: white;
      font-size: 15px;
      padding: 24px 46px 24px 26px;
      width: 100%;
    }
    .student-search label {
        display: none !important;
    }
    .student-search .stTextInput > div > div > input {
        border: none;
        background: #2f3640;
        outline: none;
        color: white;
        font-size: 15px;
        padding: 24px 46px 24px 26px;
        border-radius: 50px;
        font-family: 'Cairo', sans-serif;
    }
    .student-search .stTextInput > div {
        max-width: 230px;
    }
    h1,h2,h3,h4,h5,h6 { color: #1e293b !important; text-align: center; font-family: 'Cairo', sans-serif !important; }
    .stButton>button {
        width: 250px; height: 60px; background: linear-gradient(to right, #2563eb, #1d4ed8);
        color: white; font-size: 20px; font-weight: bold; border-radius: 16px; border: none;
        box-shadow: 0 4px 12px rgba(37,99,235,0.3); transition: all 0.3s ease; margin: 15px auto; display: block;
    }
    .stButton>button:hover {
        background: linear-gradient(to right, #1d4ed8, #1e40af);
        transform: translateY(-2px); box-shadow: 0 6px 16px rgba(37,99,235,0.4);
    }
    /* أنماط للواجهة الإنجليزية */
    .english-font {
        font-family: 'Montserrat', sans-serif !important;
    }
    
    /* Role selection styling */
    .role-selection-container {
        background: white;
        padding: 40px;
        border-radius: 20px;
        box-shadow: 0 10px 40px rgba(0,0,0,0.1);
        max-width: 600px;
        margin: 50px auto;
        text-align: center;
    }
    .role-title {
        color: #1e40af;
        font-size: 28px;
        margin-bottom: 10px;
        font-family: 'Montserrat', sans-serif;
    }
    .role-subtitle {
        color: #6b7280;
        margin-bottom: 40px;
        font-size: 18px;
        font-family: 'Montserrat', sans-serif;
    }
    .role-button {
        width: 100%;
        padding: 20px;
        margin: 15px 0;
        font-size: 20px;
        font-weight: bold;
        border-radius: 12px;
        border: none;
        cursor: pointer;
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 15px;
        font-family: 'Montserrat', sans-serif;
    }
    .teacher-role-btn {
        background: linear-gradient(135deg, #1e40af, #2563eb);
        color: white;
    }
    .teacher-role-btn:hover {
        background: linear-gradient(135deg, #1d4ed8, #1e40af);
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(37,99,235,0.3);
    }
    .student-role-btn {
        background: linear-gradient(135deg, #10b981, #059669);
        color: white;
    }
    .student-role-btn:hover {
        background: linear-gradient(135deg, #0da271, #047857);
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(16,185,129,0.3);
    }
    
    /* Admin panel styles */
    .admin-panel {
        background: white;
        border-radius: 15px;
        padding: 25px;
        margin: 20px 0;
        box-shadow: 0 5px 15px rgba(0,0,0,0.1);
    }
    .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 20px;
        margin: 20px 0;
    }
    .stat-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 20px;
        border-radius: 12px;
        text-align: center;
    }
    .stat-number {
        font-size: 36px;
        font-weight: bold;
        margin: 10px 0;
    }
    .stat-label {
        font-size: 16px;
        opacity: 0.9;
    }
</style>
""", unsafe_allow_html=True)

# ------------------ UI / Navigation ------------------
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        pass

# إدارة حالة الصفحة
if "page" not in st.session_state:
    st.session_state.page = "home"

if "current_user" not in st.session_state:
    st.session_state.current_user = None

if "current_session" not in st.session_state:
    st.session_state.current_session = None

if "show_role_selection" not in st.session_state:
    st.session_state.show_role_selection = False

# وظيفة لعرض لوحة تحكم المدير
def show_admin_panel():
    """عرض لوحة تحكم المدير"""
    st.subheader("📊 لوحة تحكم النظام")
    
    # عرض إحصائيات قاعدة البيانات
    stats = users_db.get_statistics()
    recent_sessions = users_db.get_recent_sessions(5)
    
    # شبكة الإحصائيات
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card">
            <div class="stat-number">{stats['total_users']}</div>
            <div class="stat-label">👥 إجمالي المستخدمين</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
            <div class="stat-number">{stats['total_teachers']}</div>
            <div class="stat-label">👨‍🏫 المعلمين</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
            <div class="stat-number">{stats['total_students']}</div>
            <div class="stat-label">👨‍🎓 الطلاب</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="stat-card" style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%);">
            <div class="stat-number">{stats['total_logins']}</div>
            <div class="stat-label">🔐 مرات الدخول</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # علامات التبويب
    tab1, tab2, tab3 = st.tabs(["📝 المستخدمين", "📊 الجلسات", "⚙️ الإعدادات"])
    
    with tab1:
        st.subheader("قائمة المستخدمين")
        users = users_db.get_all_users()
        
        if users:
            users_df = pd.DataFrame(users)
            # إخفاء الحقول الحساسة
            if "password_hash" in users_df.columns:
                users_df = users_df.drop(columns=["password_hash"])
            
            st.dataframe(users_df, use_container_width=True)
            
            # خيارات المدير
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 تحديث القائمة"):
                    st.rerun()
            with col2:
                if st.button("📥 تصدير البيانات"):
                    csv = users_df.to_csv(index=False)
                    st.download_button(
                        "تحميل كـ CSV",
                        data=csv,
                        file_name="users_data.csv",
                        mime="text/csv"
                    )
        else:
            st.info("لا يوجد مستخدمين مسجلين بعد.")
    
    with tab2:
        st.subheader("الجلسات الأخيرة")
        sessions = users_db.get_recent_sessions(10)
        
        if sessions:
            sessions_df = pd.DataFrame(sessions)
            st.dataframe(sessions_df, use_container_width=True)
        else:
            st.info("لا توجد جلسات مسجلة.")
    
    with tab3:
        st.subheader("إعدادات قاعدة البيانات")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 إعادة تحميل قاعدة البيانات"):
                users_db.init_database()
                st.success("✅ تم إعادة تحميل قاعدة البيانات")
                st.rerun()
        
        with col2:
            if st.button("🗑️ حذف جميع المستخدمين", type="secondary"):
                st.warning("⚠️ هذا الإجراء لا يمكن التراجع عنه!")
                if st.checkbox("أنا متأكد من حذف جميع المستخدمين"):
                    # إعادة تهيئة قاعدة البيانات
                    users_db.init_database()
                    st.success("✅ تم حذف جميع المستخدمين")
                    st.rerun()

# وظيفة لعرض اختيار الدور
def show_role_selection():
    """عرض اختيار المعلم أو الطالب"""
    st.markdown('<div class="role-selection-container">', unsafe_allow_html=True)
    
    # عرض بيانات المستخدم
    if st.session_state.current_user:
        st.markdown(f'<h2 class="role-title">Welcome, {st.session_state.current_user["name"]}!</h2>', unsafe_allow_html=True)
        st.markdown(f'<p style="color: #6b7280; margin-bottom: 30px;">Email: {st.session_state.current_user["email"]}</p>', unsafe_allow_html=True)
    
    st.markdown('<p class="role-subtitle">Are you a Teacher or Student?</p>', unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("👨‍🏫 Teacher", key="teacher_role", use_container_width=True):
            if st.session_state.current_user:
                # تحديث نوع المستخدم في قاعدة البيانات إذا لزم الأمر
                user = users_db.get_user_by_id(st.session_state.current_user["id"])
                if user:
                    user["user_type"] = "teacher"
                    # الحصول على اسم المعلم
                    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS, key="teacher_select")
                    if teacher_choice:
                        user["teacher_name"] = teacher_choice
                        st.session_state.current_user = user
                        st.session_state.page = "teacher_attendance"
                        st.rerun()
    
    with col2:
        if st.button("👨‍🎓 Student", key="student_role", use_container_width=True):
            if st.session_state.current_user:
                # تحديث نوع المستخدم في قاعدة البيانات إذا لزم الأمر
                user = users_db.get_user_by_id(st.session_state.current_user["id"])
                if user:
                    user["user_type"] = "student"
                    st.session_state.current_user = user
                    st.session_state.page = "student"
                    st.rerun()
    
    # زر تسجيل الخروج
    st.markdown("---")
    if st.button("🚪 تسجيل الخروج", use_container_width=True, type="secondary"):
        if st.session_state.current_session:
            users_db.logout_user(st.session_state.current_session)
        st.session_state.current_user = None
        st.session_state.current_session = None
        st.session_state.page = "home"
        st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

# إذا كانت الصفحة الرئيسية، إخفاء كل شيء وإظهار واجهة تسجيل الدخول فقط
if st.session_state.page == "home":
    if st.session_state.show_role_selection and st.session_state.current_user:
        show_role_selection()
    else:
        show_login_page()
        
# إذا كانت الصفحة الأخرى، إظهار شريط الأدوات العلوي
elif st.session_state.page in ["teacher_login", "teacher_attendance", "student", "admin"]:
    st.markdown(f"""
    <div class="top-toolbar">
        <div class="logo-container">
            <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
            <div class="school-info">
                <p class="school-name">مدرسة السلام الإعدادية الثانوية المشتركة</p>
                <p class="school-date">{formatted_date}</p>
            </div>
        </div>
        <div class="nav-buttons">
            <button class="nav-btn" onclick="document.getElementById('about-modal').style.display='flex'">عنا</button>
            <button class="nav-btn" onclick="document.getElementById('contact-modal').style.display='flex'">اتصل بنا</button>
            <button class="nav-btn" onclick="window.location.href='?page=home'">رجوع للواجهة</button>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)
    
    # Modals HTML + script
    st.markdown("""
    <div id="about-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="document.getElementById('about-modal').style.display='none'">×</span>
            <h3>عن المدرسة</h3>
            <p>مدرسة السلام الإعدادية الثانوية المشتركة تُعد من أعرق المدارس الحكومية في المنطقة.</p>
            <p>تهدف إلى تقديم تعليم متميز يجمع بين العلم والأخلاق.</p>
        </div>
    </div>
    <div id="contact-modal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="document.getElementById('contact-modal').style.display='none'">×</span>
            <h3>اتصل بنا</h3>
            <p>الهاتف: 02-12345678</p>
            <p>البريد: alsalam.school@example.com</p>
            <p>العنوان: حي السلام - القاهرة</p>
        </div>
    </div>
    <script>
    window.onclick = function(event) {
        var aboutModal = document.getElementById('about-modal');
        var contactModal = document.getElementById('contact-modal');
        if (event.target == aboutModal) {
            aboutModal.style.display = "none";
        }
        if (event.target == contactModal) {
            contactModal.style.display = "none";
        }
    }
    </script>
    """, unsafe_allow_html=True)

# معالجة بيانات تسجيل الدخول من JavaScript
if "login_data" not in st.session_state:
    st.session_state.login_data = None

# محاكاة استقبال البيانات من JavaScript
# في التطبيق الحقيقي، سيتم استقبال البيانات من components.html
# هنا سنستخدم أزرار اختبار

# شريط اختبار سريع
if st.session_state.page == "home" and not st.session_state.show_role_selection:
    st.sidebar.title("🔧 اختبار سريع (Development)")
    st.sidebar.info("هذا القسم للاختبار فقط")
    
    test_email = st.sidebar.text_input("Email للتجربة", "test@example.com")
    test_password = st.sidebar.text_input("Password للتجربة", "123456", type="password")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        if st.button("تسجيل دخول تجريبي"):
            success, result = users_db.authenticate_user(test_email, test_password)
            if success:
                st.session_state.current_user = result["user"]
                st.session_state.current_session = result["session_id"]
                st.session_state.show_role_selection = True
                st.success(f"✅ تم تسجيل الدخول: {result['user']['name']}")
                st.rerun()
            else:
                st.error(f"❌ {result}")
    
    with col2:
        if st.button("تسجيل مستخدم جديد"):
            # محاولة تسجيل مستخدم جديد
            success, message = users_db.register_user(
                name="Test User",
                email=test_email,
                password=test_password,
                user_type="teacher",
                teacher_name="مينا سمير"
            )
            if success:
                st.success(f"✅ {message}")
            else:
                st.error(f"❌ {message}")

# عرض الصفحة المناسبة بناءً على الحالة
if st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("تسجيل الدخول", use_container_width=True, type="primary"):
            if pwd == "1234":  # كلمة السر الافتراضية
                st.session_state.teacher_name = teacher_choice
                st.session_state.page = "teacher_attendance"
                st.rerun()
            else:
                st.error("كلمة السر غير صحيحة")
    with col2:
        if st.button("رجوع", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.show_role_selection = True
            st.rerun()

elif st.session_state.page == "teacher_attendance":
    st.header("تسجيل الغياب")
    
    # عرض معلومات المستخدم
    if st.session_state.current_user:
        user = st.session_state.current_user
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("👤 الاسم", user.get("name", "غير معروف"))
        with col2:
            st.metric("📧 الإيميل", user.get("email", "غير معروف"))
        with col3:
            teacher_name = user.get("teacher_name", "غير معروف")
            st.metric("👨‍🏫 المعلم", teacher_name)
    
    st.subheader(f"المعلم: {teacher_name if 'teacher_name' in locals() else 'غير معروف'}")

    # اختيار الطلاب الغائبين
    selected = st.multiselect("اختر الغائبين", STUDENTS)

    # اختيار نوع الغياب
    st.markdown("**اختر نوع الغياب:**")
    col_a, col_b = st.columns(2)
    with col_a:
        excuse = st.checkbox("غياب بعذر", key="excuse")
    with col_b:
        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")

    if excuse and no_excuse:
        st.warning("اختر نوع واحد فقط.")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        if st.button("تسجيل الغياب", type="primary", use_container_width=True):
            if not selected:
                st.warning("يجب اختيار طالب/طلاب أولا.")
            elif excuse and no_excuse:
                st.warning("اختر نوع واحد فقط.")
            elif not (excuse or no_excuse):
                st.warning("من فضلك اختر نوع الغياب.")
            else:
                status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
                
                # تسجيل الغياب
                try:
                    failed, telegram_status, telegram_details, success_count = record_attendance(selected, teacher_name, status_label)
                except Exception as e:
                    st.error(f"حدث خطأ أثناء تسجيل الغياب: {str(e)}")
                else:
                    # رسالة نجاح مختصرة فقط
                    if success_count > 0:
                        st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                    if failed:
                        st.error(f"حدثت بعض الأخطاء عند تسجيل: {failed}")

    with col3:
        if st.button("رجوع", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.show_role_selection = True
            st.rerun()

elif st.session_state.page == "student":
    st.header("تقارير الغياب")
    
    # عرض معلومات الطالب
    if st.session_state.current_user:
        st.info(f"👤 **الطالب:** {st.session_state.current_user.get('name', 'غير معروف')}")
    
    st.markdown('<div class="student-search">', unsafe_allow_html=True)
    search_query = st.text_input("بحث", placeholder="اكتب اسم الطالب...", key="student_search")
    st.markdown('</div>', unsafe_allow_html=True)

    if search_query and search_query.strip():
        df_student = get_student_records(search_query.strip())
        if df_student.empty:
            st.info(f"لا يوجد سجلات للطالب: {search_query}")
        else:
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            pdf_buf = generate_student_pdf(search_query, df_student)
            st.download_button(
                "تحميل PDF",
                data=pdf_buf,
                file_name=f"{search_query}_report.pdf",
                mime="application/pdf"
            )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("رجوع", use_container_width=True):
            if "student_search" in st.session_state:
                del st.session_state.student_search
            st.session_state.page = "home"
            st.session_state.show_role_selection = True
            safe_rerun()

# زر للوصول إلى لوحة التحكم (للمطورين فقط)
if st.session_state.page != "home" and st.session_state.current_user:
    if st.session_state.current_user.get("email") == "admin@school.com":
        st.sidebar.markdown("---")
        if st.sidebar.button("🛠️ لوحة تحكم المدير"):
            st.session_state.page = "admin"
            st.rerun()

# إظهار لوحة التحكم إذا كانت الصفحة admin
if st.session_state.page == "admin":
    show_admin_panel()
    
    if st.button("🏠 العودة للواجهة الرئيسية"):
        st.session_state.page = "home"
        st.rerun()
