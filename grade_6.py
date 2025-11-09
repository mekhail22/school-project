# app.py
# تطبيق Streamlit: نظام الغياب (متكامل) - تصميم جميل + بحث فعلي في صفحة الطالب والمعلم
import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
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
BOT_TOKEN = ""  # لو عايز إشعارات تيليجرام حط التوكن هنا
CHAT_ID = ""

# ------------------ الاتصال بـ Google Sheets ------------------
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
    # نعرض تحذير لكن نسمح بتشغيل الواجهة لتجربة التصميم والبحث (بس الحفظ مش هينفذ)
    st.warning("لم يتم الاتصال بـ Google Sheets تلقائيًا. لو عايز التسجيل يشتغل فعليًا: ضع بيانات SERVICE_ACCOUNT في Streamlit Secrets واسم المصنف صحيح.")

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    try:
        url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            with open(FONT_PATH, "wb") as f:
                f.write(r.content)
    except Exception:
        pass

try:
    if os.path.exists(FONT_PATH):
        pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))
    else:
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
except Exception:
    # ممكن يفشل لو مافيش arial.ttf على النظام لكن نستمر
    pass

# ------------------ دوال مساعدة ------------------
def reshape_arabic_text(text: str) -> str:
    """يعالج النص العربي للعرض في PDF (arabic_reshaper + bidi)"""
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet() -> pd.DataFrame:
    """يقرأ البيانات من Google Sheets أو يرجع فريم فارغ"""
    cols = ["student", "teacher", "status", "date"]
    if worksheet is None:
        return pd.DataFrame(columns=cols)
    try:
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        for c in cols:
            if c not in df.columns:
                df[c] = ""
        return df[cols]
    except Exception:
        return pd.DataFrame(columns=cols)

def normalize_date_for_pdf(src_date_str):
    """يحاول توحيد شكل التاريخ إلى DD / MM / YYYY"""
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    s = str(src_date_str).strip().replace(" ", "")
    try:
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
    يسجل الحضور/الغياب في Google Sheets فقط.
    يرجع قائمة الأخطاء لو حصلت.
    """
    failed = []
    date_display = datetime.now().strftime("%d / %m / %Y")
    if worksheet is None:
        # لا نعمل أي حفظ محلي كما طلبت (محوش مش عايزه) — نبلغ المستخدم
        failed.append(("no_sheet", "Google Sheets not connected; recording disabled."))
        return failed

    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        try:
            worksheet.append_row([student, teacher_name, status, date_display])
            time.sleep(0.08)  # تأخير بسيط لتفادي حدود الAPI
        except Exception as e:
            failed.append((student, str(e)))
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    send_telegram_message(message)
    return failed

def get_student_records(student_name: str) -> pd.DataFrame:
    """يعيد سجلات الطالب برؤوس عربية جاهزة للعرض"""
    df = read_sheet()
    if df.empty or "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    mask = df["student"].astype(str).str.contains(student_name, case=False, na=False)
    df_matches = df[mask].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"
    })
    cols = ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]
    for c in cols:
        if c not in df_matches.columns:
            df_matches[c] = ""
    return df_matches[cols]

def generate_student_pdf(student_name: str, df_records: pd.DataFrame) -> io.BytesIO:
    """ينشئ PDF تقرير للطالب ويرجع BytesIO"""
    buffer = io.BytesIO()
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

# ------------------ لوجو وصياغة التاريخ ------------------
logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# ------------------ CSS (يشمل تعديل ستايل حقل st.text_input ليظهر كشكل الهالو) ------------------
st.markdown(f"""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');

    /* اخفاء الهيدر والفوتر */
    #MainMenu, header, footer {{visibility: hidden !important;}}

    .stApp {{
        background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
        font-family: 'Cairo', sans-serif;
    }}

    /* الشريط العلوي */
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
        z-index: 999999 !important;
        color: white;
    }}
    .logo-container {{ display: flex; align-items: center; gap: 12px; }}
    .logo-img {{ width: 48px; height: 48px; border-radius: 12px; object-fit: contain; border: 2px solid rgba(255,255,255,0.3); background: white; padding: 4px; }}
    .school-name {{ font-size: 17px; font-weight: bold; margin: 0; }}
    .school-date {{ font-size: 12px; opacity: 0.9; margin: 0; }}

    .nav-buttons {{ display: flex; gap: 12px; }}
    .nav-btn {{
        background: rgba(255, 255, 255, 0.2);
        color: white; border: none; padding: 10px 22px;
        border-radius: 12px; font-size: 15px; font-weight: 600;
        cursor: pointer;
        backdrop-filter: blur(10px); border: 1px solid rgba(255,255,255,0.3);
    }}
    .nav-btn:hover {{
        background: white; color: #1e40af;
        transform: translateY(-3px);
    }}

    .content-padding {{ height: 90px; }}

    /* نافذة المودال */
    .modal {{ display: none; position: fixed; z-index: 1000000; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.5); backdrop-filter: blur(5px); justify-content: center; align-items: center; }}
    .modal-content {{ background: white; padding: 25px; border-radius: 16px; width: 90%; max-width: 500px; box-shadow: 0 10px 30px rgba(0,0,0,0.2); position: relative; }}
    .close-btn {{ position: absolute; top: 10px; left: 15px; font-size: 28px; font-weight: bold; color: #aaa; cursor: pointer; }}
    .close-btn:hover {{ color: #e11d48; }}

    /* تصميم صندوق البحث "الهالو" - نطبقه على input ذو placeholder المحدد */
    input[placeholder="اكتب اسمك الثلاثي:"], input[placeholder="اكتب اسم/بداية اسم الطالب للبحث (مظهري فقط)"], input[placeholder="اكتب اسم المعلم..."] {{
        background: #2f3640;
        color: white !important;
        border-radius: 50px;
        padding: 12px 18px;
        border: none;
        width: 520px;
        height: 44px;
        box-shadow: 0 6px 18px rgba(0,0,0,0.08);
        font-size: 16px;
        font-family: 'Cairo', sans-serif;
        outline: none;
    }}
    input[placeholder="اكتب اسمك الثلاثي:"]::placeholder {{
        color: #cbd5e1;
    }}

    /* ازالة حدود الفورم الافتراضي حول الinput */
    .stTextInput > div > div > input {{
        box-shadow: none;
    }}

    /* زرار البحث بجنب الinput - نخصص زرار ستريمليت الأساسي (اللي في .stButton) */
    .stButton > button {{
        background: linear-gradient(90deg,#2AF598 0%,#009EFD 100%);
        color: white; border: none; padding: 10px 18px; border-radius: 28px;
        font-size: 16px; height:44px;
    }}

    /* زر الرجوع العام */
    .back-btn {{
        background: linear-gradient(90deg,#f97316, #ef4444);
        color: white; padding: 10px 18px; border-radius: 12px; border: none;
    }}

    /* اتجاه الجدول عربي (RTL) */
    .dataframe, .stDataFrame {{
        direction: rtl;
    }}
</style>
""", unsafe_allow_html=True)

# ------------------ الشريط العلوي ------------------
st.markdown(f"""
<div class="top-toolbar">
    <div class="logo-container">
        <img src="{logo_src}" class="logo-img" alt="شعار المدرسة">
        <div>
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

# ------------------ مودالات بسيطة ------------------
st.markdown("""
<div id="about-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="document.getElementById('about-modal').style.display='none'">×</span>
        <h3>عن المدرسة</h3>
        <p>مدرسة السلام الإعدادية الثانوية المشتركة تهدف لتقديم تعليم متميز يجمع بين العلم والأخلاق.</p>
    </div>
</div>
<div id="contact-modal" class="modal">
    <div class="modal-content">
        <span class="close-btn" onclick="document.getElementById('contact-modal').style.display='none'">×</span>
        <h3>اتصل بنا</h3>
        <p>الهاتف: 02-12345678</p>
        <p>البريد: alsalam.school@example.com</p>
    </div>
</div>
<script>
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

# ------------------ صفحات التطبيق ------------------
def page_home():
    st.title("نظام الغياب")
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("👨‍🏫 معلم"):
            st.session_state.page = "teacher_login"
            st.experimental_rerun()
    with c2:
        if st.button("👩‍🎓 طالب"):
            st.session_state.page = "student"
            st.experimental_rerun()
    st.markdown("---")
    st.write("مرحبًا! اختر 'معلم' لتسجيل الغياب أو 'طالب' لعرض تقرير الغياب الخاص بك.")

def page_teacher_login():
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسم المعلم:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    c1, c2 = st.columns([1,1])
    with c1:
        if st.button("دخول"):
            if pwd == PASSWORD:
                st.session_state.teacher_name = teacher_choice
                st.session_state.page = "teacher_attendance"
                st.experimental_rerun()
            else:
                st.error("كلمة السر غير صحيحة")
    with c2:
        if st.button("رجوع"):
            st.session_state.page = "home"
            st.experimental_rerun()

def page_teacher_attendance():
    st.header("تسجيل الغياب - صفحة المعلم")
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    st.subheader(f"المعلم: {teacher_name}")

    # --- حقل البحث المصمم (حقيقي) ---
    st.write("البحث عن طالب (للعرض السريع قبل التسجيل):")
    teacher_search = st.text_input("اكتب اسم الطالب للبحث:", placeholder="اكتب اسم/بداية اسم الطالب للبحث (مظهري فقط)", key="teacher_search")
    col_a, col_b = st.columns([3,1])
    with col_b:
        if st.button("بحث عن الطالب"):
            if teacher_search.strip() == "":
                st.warning("من فضلك اكتب جزء من اسم الطالب للبحث.")
            else:
                df_found = get_student_records(teacher_search.strip())
                if df_found.empty:
                    st.info("لا توجد سجلات لهذا الاسم.")
                else:
                    st.dataframe(df_found, use_container_width=True)

    st.markdown("---")
    # اختيار الغائبين
    selected = st.multiselect("اختر الغائبين:", STUDENTS, key="teacher_selected")
    st.markdown("**نوع الغياب:**")
    excuse = st.radio("", ["غياب بعذر", "غياب بدون عذر"], index=0, key="teacher_excuse")
    col1, col2 = st.columns([1,1])
    with col1:
        if st.button("تسجيل الغياب"):
            if not selected:
                st.warning("يجب اختيار طالب/طلاب أولا.")
            else:
                status_label = excuse
                failed = record_attendance(selected, teacher_name, status_label)
                if not failed:
                    st.success("تم تسجيل الغياب بنجاح")
                else:
                    st.error(f"حدثت أخطاء: {failed}")
    with col2:
        if st.button("رجوع"):
            st.session_state.page = "home"
            st.experimental_rerun()

def page_student():
    st.header("تقارير الغياب - صفحة الطالب")
    # --- صندوق البحث المصمم فعليًا (ستايل مطبق على st.text_input) ---
    st.write("اكتب اسمك ثلاثيًا لعرض تقرير الغياب:")
    search_query = st.text_input("اكتب اسمك الثلاثي:", key="student_search", placeholder="اكتب اسمك الثلاثي:")
    col1, col2, col3 = st.columns([1,1,1])
    with col1:
        if st.button("بحث"):
            if not search_query or search_query.strip() == "":
                st.warning("من فضلك اكتب اسمك للبحث.")
            else:
                df_student = get_student_records(search_query.strip())
                if df_student.empty:
                    st.info("لا يوجد غياب مسجل لهذا الاسم.")
                else:
                    st.dataframe(df_student, use_container_width=True)
                    pdf_buf = generate_student_pdf(search_query.strip(), df_student)
                    st.download_button("تحميل PDF", data=pdf_buf, file_name=f"{search_query.strip()}_report.pdf", mime="application/pdf")
    with col2:
        if st.button("مسح البحث"):
            st.session_state.student_search = ""
            st.experimental_rerun()
    with col3:
        if st.button("رجوع للصفحة الرئيسية"):
            if "student_search" in st.session_state:
                del st.session_state.student_search
            st.session_state.page = "home"
            st.experimental_rerun()

# ------------------ تشغيل الصفحة المناسبة ------------------
if st.session_state.page == "home":
    page_home()
elif st.session_state.page == "teacher_login":
    page_teacher_login()
elif st.session_state.page == "teacher_attendance":
    page_teacher_attendance()
elif st.session_state.page == "student":
    page_student()
else:
    st.session_state.page = "home"
    page_home()
