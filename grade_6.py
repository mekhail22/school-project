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

# ------------------ قاعدة بيانات المستخدمين ------------------
USERS_DB_FILE = "users_database.json"

def init_users_database():
    """تهيئة قاعدة بيانات المستخدمين"""
    if not os.path.exists(USERS_DB_FILE):
        # كلمة سر المدرسين الافتراضية
        default_password = "123456"
        
        default_data = {
            "users": [
                {
                    "id": "teacher_001",
                    "name": "مينا سمير",
                    "email": "mina@school.com",
                    "password_hash": hashlib.sha256(default_password.encode()).hexdigest(),
                    "user_type": "teacher",
                    "teacher_name": "مينا سمير",
                    "created_at": datetime.now().isoformat(),
                    "last_login": None,
                    "login_count": 0
                },
                {
                    "id": "teacher_002",
                    "name": "فادي حبيب",
                    "email": "fady@school.com",
                    "password_hash": hashlib.sha256(default_password.encode()).hexdigest(),
                    "user_type": "teacher",
                    "teacher_name": "فادي حبيب",
                    "created_at": datetime.now().isoformat(),
                    "last_login": None,
                    "login_count": 0
                }
            ],
            "login_history": [],
            "statistics": {
                "total_users": 2,
                "total_logins": 0,
                "total_teachers": 2,
                "total_students": 0
            }
        }
        
        with open(USERS_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_data, f, ensure_ascii=False, indent=2)
        
        print(f"✅ تم إنشاء قاعدة البيانات مع {len(default_data['users'])} مدرس")
    
    return load_users_database()

def load_users_database():
    """تحميل قاعدة بيانات المستخدمين"""
    try:
        with open(USERS_DB_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ خطأ في تحميل قاعدة البيانات: {e}")
        return init_users_database()

def save_users_database(data):
    """حفظ قاعدة بيانات المستخدمين"""
    try:
        with open(USERS_DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"❌ خطأ في حفظ قاعدة البيانات: {e}")
        return False

def hash_password(password):
    """تشفير كلمة المرور"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(email, password):
    """المصادقة على المستخدم"""
    db = load_users_database()
    
    password_hash = hash_password(password)
    
    for user in db["users"]:
        if user["email"] == email and user["password_hash"] == password_hash:
            # تحديث معلومات تسجيل الدخول
            user["last_login"] = datetime.now().isoformat()
            user["login_count"] = user.get("login_count", 0) + 1
            
            # تسجيل في سجل الدخول
            login_record = {
                "user_id": user["id"],
                "login_time": datetime.now().isoformat(),
                "user_type": user["user_type"]
            }
            db["login_history"].append(login_record)
            db["statistics"]["total_logins"] += 1
            
            save_users_database(db)
            
            return True, user
    
    return False, None

def register_user(name, email, password, user_type="student"):
    """تسجيل مستخدم جديد"""
    db = load_users_database()
    
    # التحقق من عدم تكرار الإيميل
    for user in db["users"]:
        if user["email"] == email:
            return False, "الإيميل مستخدم بالفعل"
    
    # إنشاء مستخدم جديد
    new_user = {
        "id": f"user_{len(db['users']) + 1:03d}",
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
        "user_type": user_type,
        "teacher_name": None,
        "created_at": datetime.now().isoformat(),
        "last_login": None,
        "login_count": 0
    }
    
    db["users"].append(new_user)
    db["statistics"]["total_users"] = len(db["users"])
    
    if user_type == "teacher":
        db["statistics"]["total_teachers"] += 1
    else:
        db["statistics"]["total_students"] += 1
    
    if save_users_database(db):
        return True, "تم التسجيل بنجاح"
    else:
        return False, "خطأ في حفظ البيانات"

# تهيئة قاعدة البيانات عند بدء التشغيل
if "db_initialized" not in st.session_state:
    init_users_database()
    st.session_state.db_initialized = True

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

# محاولة الاتصال بـ Google Sheets
if SERVICE_ACCOUNT and SERVICE_ACCOUNT.get('private_key'):
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
        gc = gspread.authorize(creds)
        
        try:
            sh = gc.open(SHEET_NAME)
            worksheet = sh.sheet1
            st.success("✅ متصل بـ Google Sheets")
        except Exception as e:
            st.warning(f"⚠️ لا يمكن الاتصال بـ Google Sheets: {str(e)}")
    except Exception as e:
        st.warning(f"⚠️ فشل في المصادقة: {str(e)}")

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
    
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: 'signin',
        data: {
            email: email,
            password: password
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
    
    if (password !== confirmPassword) {
        alert('Passwords do not match.');
        return;
    }
    
    window.parent.postMessage({
        type: 'streamlit:setComponentValue',
        value: 'signup',
        data: {
            name: name,
            email: email,
            password: password
        }
    }, '*');
}
</script>
"""
    
    # إخفاء شريط الأدوات العلوي في صفحة تسجيل الدخول
    st.markdown("""
    <style>
    .stApp > header { display: none !important; }
    footer { visibility: hidden; }
    #MainMenu { visibility: hidden; }
    </style>
    """, unsafe_allow_html=True)
    
    # عرض واجهة تسجيل الدخول التفاعلية
    components.html(html_code, height=700)

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

# ------------------ CSS ------------------
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
    @import url('https://fonts.googleapis.com/css?family=Montserrat:400,800');
    
    .stApp {{
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
    }}
    
    .top-toolbar {{
        position: fixed;
        top: 0; left: 0; right: 0;
        height: 70px;
        background: linear-gradient(135deg, #1e40af, #2563eb);
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 20px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        z-index: 999999;
        font-family: 'Cairo', sans-serif;
        color: white;
    }}
    
    .logo-container {{ display: flex; align-items: center; gap: 12px; }}
    .logo-img {{ 
        width: 48px; height: 48px; border-radius: 12px; 
        object-fit: contain; border: 2px solid rgba(255,255,255,0.3); 
        background: white; padding: 4px;
    }}
    
    .school-info {{ line-height: 1.3; }}
    .school-name {{ font-size: 17px; font-weight: bold; margin: 0; }}
    .school-date {{ font-size: 12px; opacity: 0.9; margin: 0; }}
    
    .nav-buttons {{ display: flex; gap: 12px; }}
    .nav-btn {{
        background: rgba(255, 255, 255, 0.2);
        color: white; border: none; padding: 10px 22px;
        border-radius: 12px; font-size: 15px; font-weight: 600;
        cursor: pointer; transition: all 0.3s ease;
        backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3);
        font-family: 'Cairo', sans-serif;
    }}
    
    .nav-btn:hover {{
        background: white; color: #1e40af;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(255,255,255,0.4);
    }}
    
    .content-padding {{ height: 90px; }}
    
    h1,h2,h3 {{ color: #1e293b !important; text-align: center; font-family: 'Cairo', sans-serif !important; }}
    
    .stButton>button {{
        background: linear-gradient(to right, #2563eb, #1d4ed8);
        color: white; font-size: 16px; font-weight: bold;
        border-radius: 12px; border: none;
        box-shadow: 0 4px 12px rgba(37,99,235,0.3);
        transition: all 0.3s ease;
    }}
    
    .stButton>button:hover {{
        background: linear-gradient(to right, #1d4ed8, #1e40af);
        transform: translateY(-2px);
        box-shadow: 0 6px 16px rgba(37,99,235,0.4);
    }}
</style>
""", unsafe_allow_html=True)

# ------------------ إدارة حالة التطبيق ------------------
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

# ------------------ واجهة اختيار الدور ------------------
def show_role_selection():
    """عرض اختيار المعلم أو الطالب"""
    st.markdown("""
    <div style="text-align: center; margin: 50px 0;">
        <h1 style="color: #1e40af;">مرحباً بك في نظام الغياب</h1>
        <p style="color: #6b7280; font-size: 18px; margin-bottom: 40px;">اختر نوع الدخول:</p>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style="background: white; padding: 30px; border-radius: 15px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
            <h2 style="color: #1e40af;">👨‍🏫 معلم</h2>
            <p style="color: #6b7280;">لتسجيل حضور وغياب الطلاب</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("دخول كمعلم", key="teacher_btn", use_container_width=True, type="primary"):
            st.session_state.page = "teacher_login"
            safe_rerun()
    
    with col2:
        st.markdown("""
        <div style="background: white; padding: 30px; border-radius: 15px; text-align: center; box-shadow: 0 5px 15px rgba(0,0,0,0.1);">
            <h2 style="color: #10b981;">👨‍🎓 طالب</h2>
            <p style="color: #6b7280;">للعرض والبحث في سجلات الغياب</p>
        </div>
        """, unsafe_allow_html=True)
        
        if st.button("دخول كطالب", key="student_btn", use_container_width=True, type="secondary"):
            st.session_state.page = "student"
            safe_rerun()

# ------------------ التنفيذ الرئيسي ------------------
if st.session_state.page == "home":
    # في الصفحة الرئيسية، نعرض واجهة اختيار الدور مباشرة
    show_role_selection()
    
    # أضفنا أزرار تسجيل الدخول السريع للمدرسين (لتسهيل التجربة)
    st.markdown("---")
    st.subheader("🔧 دخول سريع للمعلمين (للتجربة)")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("مينا سمير", use_container_width=True):
            st.session_state.current_user = {
                "name": "مينا سمير",
                "email": "mina@school.com",
                "user_type": "teacher",
                "teacher_name": "مينا سمير"
            }
            st.session_state.teacher_name = "مينا سمير"
            st.session_state.page = "teacher_attendance"
            safe_rerun()
    
    with col2:
        if st.button("فادي حبيب", use_container_width=True):
            st.session_state.current_user = {
                "name": "فادي حبيب",
                "email": "fady@school.com",
                "user_type": "teacher",
                "teacher_name": "فادي حبيب"
            }
            st.session_state.teacher_name = "فادي حبيب"
            st.session_state.page = "teacher_attendance"
            safe_rerun()

elif st.session_state.page == "teacher_login":
    # شريط الأدوات العلوي
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
            <button class="nav-btn" onclick="window.location.href='?page=home'">🏠 الرجوع</button>
        </div>
    </div>
    <div class="content-padding"></div>
    """, unsafe_allow_html=True)
    
    st.header("👨‍🏫 تسجيل دخول المعلم")
    
    # طريقة 1: الدخول باستخدام النظام الجديد
    st.subheader("الدخول بالنظام الجديد")
    
    email = st.text_input("البريد الإلكتروني:", key="teacher_email")
    password = st.text_input("كلمة المرور:", type="password", key="teacher_password")
    
    if st.button("تسجيل الدخول", use_container_width=True, type="primary"):
        if email and password:
            success, user = authenticate_user(email, password)
            if success:
                st.session_state.current_user = user
                st.session_state.teacher_name = user["teacher_name"] if user["user_type"] == "teacher" else user["name"]
                st.session_state.page = "teacher_attendance"
                st.success(f"✅ مرحباً أستاذ {user['name']}")
                safe_rerun()
            else:
                st.error("❌ البريد الإلكتروني أو كلمة المرور غير صحيحة")
        else:
            st.warning("⚠️ الرجاء إدخال البريد الإلكتروني وكلمة المرور")
    
    st.markdown("---")
    
    # طريقة 2: الدخول السريع للمدرسين المسجلين
    st.subheader("الدخول السريع")
    
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("مينا سمير (mina@school.com)", use_container_width=True):
            success, user = authenticate_user("mina@school.com", "123456")
            if success:
                st.session_state.current_user = user
                st.session_state.teacher_name = "مينا سمير"
                st.session_state.page = "teacher_attendance"
                st.success("✅ تم تسجيل الدخول بنجاح")
                safe_rerun()
    
    with col2:
        if st.button("فادي حبيب (fady@school.com)", use_container_width=True):
            success, user = authenticate_user("fady@school.com", "123456")
            if success:
                st.session_state.current_user = user
                st.session_state.teacher_name = "فادي حبيب"
                st.session_state.page = "teacher_attendance"
                st.success("✅ تم تسجيل الدخول بنجاح")
                safe_rerun()
    
    # زر الرجوع
    if st.button("🏠 الرجوع للصفحة الرئيسية", use_container_width=True):
        st.session_state.page = "home"
        safe_rerun()

elif st.session_state.page == "teacher_attendance":
    # شريط الأدوات العلوي
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    
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
            <div style="color: white; font-weight: bold;">👨‍🏫 {teacher_name}</div>
            <button class="nav-btn" onclick="window.location.href='?page=home'">🏠 الرئيسية</button>
            <button class="nav-btn" onclick="window.location.href='?page=teacher_login'">🚪 تسجيل الخروج</button>
        </div>
    </div>
    <div class="content-padding"></div>
    """, unsafe_allow_html=True)
    
    st.header(f"📝 تسجيل الغياب - الأستاذ: {teacher_name}")
    
    # عرض معلومات المعلم
    if st.session_state.current_user:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.info(f"👤 **الاسم:** {st.session_state.current_user.get('name', 'غير معروف')}")
        with col2:
            st.info(f"📧 **البريد:** {st.session_state.current_user.get('email', 'غير معروف')}")
        with col3:
            st.info(f"📅 **آخر دخول:** {st.session_state.current_user.get('last_login', 'غير معروف')}")
    
    st.markdown("---")
    
    # قسم تسجيل الغياب
    st.subheader("تسجيل حضور وغياب الطلاب")
    
    selected = st.multiselect("اختر الطلاب الغائبين:", STUDENTS)
    
    col1, col2 = st.columns(2)
    with col1:
        excuse = st.checkbox("غياب بعذر", key="excuse")
    with col2:
        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")
    
    if excuse and no_excuse:
        st.warning("⚠️ اختر نوع واحد فقط من الغياب.")
    
    if st.button("💾 حفظ وتسجيل الغياب", type="primary", use_container_width=True):
        if not selected:
            st.warning("⚠️ الرجاء اختيار طالب واحد على الأقل.")
        elif excuse and no_excuse:
            st.warning("⚠️ اختر نوع واحد فقط من الغياب.")
        elif not (excuse or no_excuse):
            st.warning("⚠️ الرجاء تحديد نوع الغياب.")
        else:
            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
            
            # تسجيل الغياب
            try:
                failed, telegram_status, telegram_details, success_count = record_attendance(selected, teacher_name, status_label)
                
                if success_count > 0:
                    st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                    st.balloons()
                
                if failed:
                    st.error(f"حدثت بعض الأخطاء: {failed}")
                    
            except Exception as e:
                st.error(f"❌ حدث خطأ أثناء التسجيل: {str(e)}")
    
    # زر الرجوع
    if st.button("🏠 الرجوع للصفحة الرئيسية", use_container_width=True):
        st.session_state.page = "home"
        st.session_state.current_user = None
        safe_rerun()

elif st.session_state.page == "student":
    # شريط الأدوات العلوي
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
            <button class="nav-btn" onclick="window.location.href='?page=home'">🏠 الرئيسية</button>
        </div>
    </div>
    <div class="content-padding"></div>
    """, unsafe_allow_html=True)
    
    st.header("📊 تقارير الغياب للطلاب")
    
    st.info("""
    يمكنك البحث عن سجلات غياب أي طالب من خلال إدخال اسمه في الحقل أدناه.
    يمكنك أيضاً تحميل التقرير كملف PDF.
    """)
    
    search_query = st.text_input("🔍 ابحث عن اسم الطالب:", placeholder="أدخل اسم الطالب هنا...")
    
    if search_query and search_query.strip():
        df_student = get_student_records(search_query.strip())
        
        if df_student.empty:
            st.warning(f"⚠️ لا توجد سجلات للطالب: {search_query}")
        else:
            st.success(f"✅ تم العثور على {len(df_student)} سجل للطالب: {search_query}")
            
            # عرض البيانات
            st.dataframe(df_student, use_container_width=True, hide_index=True)
            
            # إحصائيات
            col1, col2, col3 = st.columns(3)
            with col1:
                absent_count = ((df_student["الحالة"] == "غياب بعذر").sum() + 
                               (df_student["الحالة"] == "غياب بدون عذر").sum())
                st.metric("عدد مرات الغياب", absent_count)
            
            with col2:
                present_count = (df_student["الحالة"] == "حاضر").sum()
                st.metric("عدد مرات الحضور", present_count)
            
            with col3:
                total_count = len(df_student)
                attendance_rate = (present_count / total_count * 100) if total_count > 0 else 0
                st.metric("نسبة الحضور", f"{attendance_rate:.1f}%")
            
            # زر تحميل PDF
            pdf_buf = generate_student_pdf(search_query, df_student)
            st.download_button(
                "📥 تحميل التقرير كـ PDF",
                data=pdf_buf,
                file_name=f"تقرير_غياب_{search_query}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    
    # زر الرجوع
    if st.button("🏠 الرجوع للصفحة الرئيسية", use_container_width=True):
        st.session_state.page = "home"
        safe_rerun()

# ------------------ معلومات إضافية في الشريط الجانبي ------------------
with st.sidebar:
    st.header("ℹ️ معلومات النظام")
    
    st.info(f"""
    **المدرسة:** السلام الإعدادية الثانوية  
    **عدد الطلاب:** {len(STUDENTS)}  
    **عدد المعلمين:** {len(TEACHERS)}  
    **التاريخ:** {datetime.now().strftime("%Y-%m-%d")}
    """)
    
    if worksheet:
        st.success("✅ متصل بـ Google Sheets")
    else:
        st.warning("⚠️ غير متصل بـ Google Sheets")
    
    if st.session_state.current_user:
        st.markdown("---")
        st.subheader("👤 معلومات المستخدم")
        st.write(f"**الاسم:** {st.session_state.current_user.get('name', 'غير معروف')}")
        st.write(f"**الدور:** {st.session_state.current_user.get('user_type', 'غير معروف')}")
        
        if st.button("🚪 تسجيل الخروج", use_container_width=True):
            st.session_state.page = "home"
            st.session_state.current_user = None
            safe_rerun()
    
    # زر لإعادة تعيين النظام (للتطوير)
    st.markdown("---")
    if st.button("🔄 إعادة تعيين النظام", type="secondary", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("✅ تم إعادة تعيين النظام")
        safe_rerun()
