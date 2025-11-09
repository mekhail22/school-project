# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests
import gspread
from google.oauth2.service_account import Credentials
import base64
import time
from typing import List

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="wide", initial_sidebar_state="collapsed")

# ------------------ إعدادات عامة (عدلهم لو محتاج) ------------------
SHEET_NAME = "school_attendance"  # اسم المصنف في Google Sheets
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# تهيئة توكن تيليجرام (لو مش عايز تستخدمه ممكن تخليه "")
BOT_TOKEN = "7517001841:AAHezP3dOU-L9xAgHsxQrTXZsbgHpRrHFXM"
CHAT_ID = "8108209758"

# ------------------ الاتصال بـ Google Sheets ------------------
# نتوقع أن المستخدم يحطّ SERVICE_ACCOUNT في streamlit secrets، مثال:
# [SERVICE_ACCOUNT]
# type = "service_account"
# ... كامل JSON هنا ...
gc = None
worksheet = None
try:
    service_account_info = st.secrets["SERVICE_ACCOUNT"]
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
    gc = gspread.authorize(creds)
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
except Exception as e:
    # مش هنوقف التطبيق هنا عشان نسمح بتجربة الواجهه بدون شيت - لكن وضعنا تحذير
    st.warning("لم يتم الاتصال بـ Google Sheets تلقائيًا. إذا أردت حفظ السجلات فعليًا على Google Sheets تأكد من إضافة SERVICE_ACCOUNT في Streamlit Secrets ووجود ملف باسم المصنف الصحيح.")
    # worksheet يظل None -> دوال القراءة/الكتابة تتعامل مع None

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
    except Exception:
        # تجاهل، سنستخدم fallback font
        pass

try:
    if os.path.exists(FONT_PATH):
        pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))
    else:
        # حاول استخدام أي خط عربي موجود في النظام (قد يفشل أحيانًا لكن نحاول)
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
except Exception:
    # لو فشل التسجيل، رابطح باستخدام built-in font لكن ممكن مشاكل بالعربي في PDF
    pass

# ------------------ دوال مساعدة ------------------
def reshape_arabic_text(text: str) -> str:
    """يعالج صياغة النص العربي للعرض في PDF (من arabic_reshaper + bidi)"""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet() -> pd.DataFrame:
    """يرجع DataFrame من Google Sheets، أو فريم فارغ بصيغ الأعمدة المطلوبة"""
    cols = ["student", "teacher", "status", "date"]
    if worksheet is None:
        # لو مفيش ورقة، نرجع فريم فارغ
        return pd.DataFrame(columns=cols)
    try:
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        # نضمن وجود الأعمدة الأساسية
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)

def normalize_date_for_pdf(src_date_str):
    """يحاول يحول أشكال التواريخ المختلفة لشكل 'DD / MM / YYYY'"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    s = str(src_date_str).strip()
    # إزالة مسافات زائدة
    s = s.replace(" ", "")
    try:
        # شكل YYYY-MM-DD أو DD-MM-YYYY
        if "-" in s:
            parts = s.split("-")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        if "/" in s:
            parts = s.split("/")
            if len(parts) == 3:
                if len(parts[0]) == 4:
                    y, m, d = parts
                else:
                    d, m, y = parts
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        # شكل YYYYMMDD
        if len(s) == 8 and s.isdigit():
            y = s[0:4]; m = s[4:6]; d = s[6:8]
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
    except Exception:
        pass
    return s

def send_telegram_message(message: str):
    """يرسل رسالة تيليجرام إن كان التوكن موجود"""
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.get(url, params={"chat_id": CHAT_ID, "text": message}, timeout=5)
    except Exception:
        pass

def record_attendance(selected_absent: List[str], teacher_name: str, absent_label: str) -> List:
    """
    يسجل حالة الحضور/الغياب لكل الطلاب في Google Sheet.
    يرجع قائمة الأخطاء (لو حصلت) لكي نعرضها.
    """
    failed = []
    date_display = datetime.now().strftime("%d / %m / %Y")
    # لو مفيش worksheet، نحفظ في ملف محلي كـ fallback (CSV)
    if worksheet is None:
        local_file = "attendance_local_backup.csv"
        rows = []
        for student in STUDENTS:
            status = absent_label if student in selected_absent else "حاضر"
            rows.append({"student": student, "teacher": teacher_name, "status": status, "date": date_display})
        try:
            df_local = pd.DataFrame(rows)
            if os.path.exists(local_file):
                df_local.to_csv(local_file, mode="a", index=False, header=False, encoding="utf-8-sig")
            else:
                df_local.to_csv(local_file, index=False, encoding="utf-8-sig")
        except Exception as e:
            failed.append(("local_save", str(e)))
        # رسالة تلغرام
        absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
        message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
        send_telegram_message(message)
        return failed

    # لو عندنا Google Sheet فعليًا
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        try:
            worksheet.append_row([student, teacher_name, status, date_display])
            # تأخير صغير لمنع تجاوز حدود الAPI لو فيه الكثير
            time.sleep(0.08)
        except Exception as e:
            failed.append((student, str(e)))
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    send_telegram_message(message)
    return failed

def get_student_records(student_name: str) -> pd.DataFrame:
    """يعيد سجلات الطالب مع رؤوس عربية جاهزة للعرض"""
    df = read_sheet()
    if df.empty or "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    # البحث غير حساس لحالة الحروف
    mask = df["student"].astype(str).str.contains(student_name, case=False, na=False)
    df_matches = df[mask].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"
    })
    # ترتيب الأعمدة النهائية
    cols = ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]
    for c in cols:
        if c not in df_matches.columns:
            df_matches[c] = ""
    return df_matches[cols]

def generate_student_pdf(student_name: str, df_records: pd.DataFrame) -> io.BytesIO:
    """ينشئ PDF تقرير للطالب ويرجّع BytesIO"""
    buffer = io.BytesIO()
    # هوامش مناسبة
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    elements = []
    title_style = ParagraphStyle('Title', fontName='Arabic', fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle('Normal', fontName='Arabic', fontSize=12, alignment=2)
    footer_style = ParagraphStyle('Footer', fontName='Arabic', fontSize=10, alignment=2, textColor=colors.darkblue)

    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), title_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), normal_style))
    elements.append(Spacer(1, 6))

    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        try:
            absent_count = int((df_records["الحالة"] == "غياب بعذر").sum() + (df_records["الحالة"] == "غياب بدون عذر").sum())
            present_count = int((df_records["الحالة"] == "حاضر").sum())
        except Exception:
            absent_count = 0
            present_count = len(df_records)
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Spacer(1, 8))

        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            date_norm = normalize_date_for_pdf(row.get("التاريخ", ""))
            data.append([
                reshape_arabic_text(row.get("المرة", "")),
                reshape_arabic_text(row.get("الطالب", "")),
                reshape_arabic_text(row.get("المعلم", "")),
                reshape_arabic_text(date_norm),
                reshape_arabic_text(row.get("الحالة", ""))
            ])

        col_widths = [50, 150, 120, 100, 80]
        table = Table(data, hAlign='RIGHT', colWidths=col_widths)
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Arabic'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE')
        ]))
        elements.append(table)

    elements.append(Spacer(1, 12))
    today = datetime.now()
    current_date = f"{today.day:02d} / {today.month:02d} / {today.year}"
    elements.append(Paragraph(reshape_arabic_text(f"تاريخ إنشاء التقرير: {current_date}"), footer_style))
    doc.build(elements)
    buffer.seek(0)
    return buffer

def get_image_base64(image_path: str):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception:
        return None

# ------------------ صورة الشعار ------------------
logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    # بديل خارجي إن لم توجد الصورة المحلية
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

# ------------------ إعداد تاريخ اليوم باللغة العربية (للعرض في الشريط العلوي) ------------------
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
# ملاحظة: datetime.weekday() => الاثنين=0 ... الاحد=6
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# ------------------ CSS والـ HTML للشريط العلوي والبحث المصمم ------------------
# هذه الـ CSS مأخوذة من التصميم الذي طلبته مع بعض التعديلات لتتماشى مع Streamlit
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

    /* إخفاء الهيدر والفوتر */
    #MainMenu, header, footer {visibility: hidden !important;}

    .stApp {
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        background-attachment: fixed;
        font-family: 'Cairo', sans-serif;
    }

    /* الشريط العلوي */
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
    }
    .nav-btn:hover {
        background: white; color: #1e40af;
        transform: translateY(-3px);
        box-shadow: 0 8px 20px rgba(255,255,255,0.4);
    }

    .content-padding { height: 90px; }

    /* النافذة المنبثقة */
    .modal { display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }
    .modal-content { background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; animation: modalPop 0.3s ease; }
    @keyframes modalPop { from { transform: scale(0.8); opacity: 0; } to { transform: scale(1); opacity: 1; } }
    .close-btn { position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }
    .close-btn:hover { color: #e11d48; }
    .modal h3 { text-align: center; color: #1e40af; margin-top: 0; }
    .modal p { text-align: center; color: #475569; line-height: 1.6; }

    /* حقل البحث المصمم (سيتم عرضه بجانب حقل Streamlit الحقيقي) */
    .search-container {
        display: flex;
        justify-content: flex-start;
        margin: 15px 20px 10px 20px;
        padding-left: 30px; /* المسافة البسيطة من اليسار */
    }
    .searchBox {
        display: flex;
        max-width: 520px;
        align-items: center;
        justify-content: space-between;
        gap: 8px;
        background: #2f3640;
        border-radius: 50px;
        position: relative;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        padding: 6px;
    }
    .searchButton {
        color: white;
        position: relative;
        right: 8px;
        width: 56px;
        height: 42px;
        border-radius: 28px;
        background: linear-gradient(90deg, #2AF598 0%, #009EFD 100%);
        border: 0;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 300ms cubic-bezier(.23, 1, 0.32, 1);
        cursor: pointer;
        font-size: 16px;
    }
    .searchButton:hover {
        filter: brightness(0.95);
    }
    .searchInput {
        border: none;
        outline: none;
        background: none;
        color: white;
        font-size: 16px;
        padding: 10px 16px;
        width: 100%;
        font-family: 'Cairo', sans-serif;
    }
    .searchInput::placeholder {
        color: #bdc3c7;
    }

    /* تحسينات عامة */
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

    /* تنسيق الجدول للعرض داخل الصفحة */
    .dataframe, .stDataFrame {
        direction: rtl;
    }
</style>
""", unsafe_allow_html=True)

# ------------------ الشريط العلوي (HTML) ------------------
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
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown('<div class="content-padding"></div>', unsafe_allow_html=True)

# ------------------ النوافذ المنبثقة ------------------
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
/* سكربت بسيط لقفل النوافذ عند الضغط خارج المحتوى */
window.addEventListener('click', function(e) {
    var about = document.getElementById('about-modal');
    var contact = document.getElementById('contact-modal');
    if (e.target === about) { about.style.display = 'none'; }
    if (e.target === contact) { contact.style.display = 'none'; }
});
</script>
""", unsafe_allow_html=True)

# ------------------ إدارة الصفحات ------------------
if "page" not in st.session_state:
    st.session_state.page = "home"

# ------------------ الشاشة الرئيسية ------------------
def page_home():
    st.title("نظام الغياب")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            st.experimental_rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            st.experimental_rerun()
    st.markdown("---")
    st.write("مرحبًا! اختر 'معلم' لتسجيل الغياب أو 'طالب' لعرض تقرير الغياب الخاص بك.")

# ------------------ صفحة تسجيل دخول المعلم ------------------
def page_teacher_login():
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("تسجيل الدخول"):
            if pwd == PASSWORD:
                st.session_state.teacher_name = teacher_choice
                st.session_state.page = "teacher_attendance"
                st.experimental_rerun()
            else:
                st.error("كلمة السر غير صحيحة")
    with col2:
        if st.button("رجوع"):
            st.session_state.page = "home"
            st.experimental_rerun()

# ------------------ صفحة تسجيل الغياب للمعلم ------------------
def page_teacher_attendance():
    st.header("تسجيل الغياب")
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    st.subheader(f"المعلم: {teacher_name}")
    # عرض البحث المصمم (مظهري فقط) ثم حقل Streamlit الفعلي
    st.markdown("""
    <div class="search-container">
        <div class="searchBox">
            <input class="searchInput" placeholder="اكتب اسم/بداية اسم الطالب للبحث (مظهري فقط)">
            <button class="searchButton">🔎</button>
        </div>
    </div>
    """, unsafe_allow_html=True)

    selected = st.multiselect("اختر الغائبين:", STUDENTS, key="teacher_selected")
    st.markdown("**اختر نوع الغياب:**")
    excuse = st.radio("", ["غياب بعذر", "غياب بدون عذر"], index=0, key="teacher_excuse")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("تسجيل"):
            if not selected:
                st.warning("يجب اختيار طالب/طلاب أولا.")
            else:
                status_label = excuse
                failed = record_attendance(selected, teacher_name, status_label)
                if not failed:
                    st.success("تم تسجيل الغياب بنجاح")
                else:
                    st.error(f"حدثت أخطاء في التسجيل: {failed}")
    with col2:
        if st.button("رجوع"):
            st.session_state.page = "home"
            st.experimental_rerun()

# ------------------ صفحة الطالب (بحث + عرض + تحميل PDF) ------------------
def page_student():
    st.header("تقارير الغياب")
    # نعرض نفس صندوق البحث المصمم (مظهري) لكن القيمة الفعلية تجي من st.text_input
    st.markdown("""
    <div class="search-container">
        <div class="searchBox">
            <input class="searchInput" placeholder="اكتب اسمك الثلاثي..." readonly>
            <button class="searchButton">🔎</button>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # القيمة الحقيقية
    search_query = st.text_input("اكتب اسمك الثلاثي:", key="student_search", placeholder="مثال: ميخائيل صابر فوزي")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("بحث"):
            if not search_query or search_query.strip() == "":
                st.warning("من فضلك اكتب اسمك للبحث.")
            else:
                df_student = get_student_records(search_query.strip())
                if df_student.empty:
                    st.info("لا يوجد غياب مسجل لهذا الاسم.")
                else:
                    # عرض الجدول - نجعل الاتجاه يمين لليسار
                    st.dataframe(df_student, use_container_width=True)
                    pdf_buf = generate_student_pdf(search_query.strip(), df_student)
                    st.download_button("تحميل PDF", data=pdf_buf, file_name=f"{search_query.strip()}_report.pdf", mime="application/pdf")
    with col2:
        if st.button("مسح البحث"):
            st.session_state.student_search = ""
            st.experimental_rerun()

    if st.button("الرجوع"):
        if "student_search" in st.session_state:
            del st.session_state.student_search
        st.session_state.page = "home"
        st.experimental_rerun()

# ------------------ تحديد الصفحة الحالية وتشغيلها ------------------
if st.session_state.page == "home":
    page_home()
elif st.session_state.page == "teacher_login":
    page_teacher_login()
elif st.session_state.page == "teacher_attendance":
    page_teacher_attendance()
elif st.session_state.page == "student":
    page_student()
else:
    # fallback
    st.session_state.page = "home"
    page_home()
