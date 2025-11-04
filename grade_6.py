# كامل ومعدل — نفس الشكل القديم لكن من غير عمود الزيادة، وكلمة "مدرس" اتحولت لـ "معلم"
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

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ إعدادات عامة ------------------
SHEET_NAME = "school_attendance"  # اسم Google Sheet (المصنف)
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]  # أسماء المعلمين (المتغير اسمه TEACHERS لكن العرض بالعربي "المعلم")

# ------------------ الاتصال بـ Google Sheets ------------------
# تأكد إنك خزنت JSON خدمة السرفيس في secrets كـ SERVICE_ACCOUNT (json object)
service_account_info = st.secrets["SERVICE_ACCOUNT"]
SCOPES = ["https://www.googleapis.com/auth/spreadsheets","https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(creds)

# نفتح المصنف
try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
except Exception as e:
    st.error("خطأ في فتح Google Sheet. تأكد من اسم المصنف ومشاركة الـ service account كـ Editor.")
    st.stop()

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
    try:
        r = requests.get(url, timeout=10)
        with open(FONT_PATH, "wb") as f:
            f.write(r.content)
    except Exception:
        pass

try:
    pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))
except:
    try:
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
    except:
        pass

# ------------------ دوال مساعدة ------------------
def reshape_arabic_text(text):
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped)
        return bidi_text
    except:
        return str(text)

def read_sheet():
    """
    يقرأ كل السجلات من الورقة ويتأكد من وجود الأعمدة: student, teacher, status, date
    """
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    return df

def normalize_date_for_pdf(src_date_str):
    if pd.isna(src_date_str) or str(src_date_str).strip() == "":
        return ""
    s = str(src_date_str).strip().replace(" ", "")
    parts = None
    if "-" in s:
        parts = s.split("-")
        if len(parts) == 3:
            if len(parts[0]) == 4:
                y, m, d = parts
            else:
                d, m, y = parts
            try:
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
            except:
                return s
    if "/" in s:
        parts = s.split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4:
                y, m, d = parts
            else:
                d, m, y = parts
            try:
                return f"{int(d):02d} / {int(m):02d} / {int(y)}"
            except:
                return s
    if len(s) == 8 and s.isdigit():
        y = s[0:4]; m = s[4:6]; d = s[6:8]
        try:
            return f"{int(d):02d} / {int(m):02d} / {int(y)}"
        except:
            return s
    return s

def send_telegram_message(message):
    BOT_TOKEN = "7517001841:AAFZZQM1hiprXxhPhK4GMfFwu-eP-DkOdMU"
    CHAT_ID = "8108209758"
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.get(url, params={"chat_id": CHAT_ID, "text": message}, timeout=5)
    except:
        pass

def record_attendance(selected_absent, teacher_name):
    """
    يسجل لكل طالب (student, teacher, status, date) في Google Sheet
    """
    date_display = datetime.now().strftime("%Y-%m-%d")  # التاريخ مخزن بصيغة yyyy-mm-dd
    new_rows = []
    for student in STUDENTS:
        status = "غائب" if student in selected_absent else "حاضر"
        new_rows.append([student, teacher_name, status, date_display])
    for row in new_rows:
        worksheet.append_row(row)
    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"📌 تم تسجيل الغياب بتاريخ {date_display}\n👨‍🏫 المعلم: {teacher_name}\nغائبون: {absent_students}"
    send_telegram_message(message)

def get_student_records(student_name):
    """
    يعيد DataFrame منسق بأعمدة: المرة, الطالب, المعلم, التاريخ, الحالة
    ويجعل 'المرة' أول عمود (قابل للعرض كعمود عادي)
    """
    df = read_sheet()
    # تطبيع أسماء الأعمدة لو مكتوبة بالعربية أو إنجليزية في الشيت
    # لكن نعمل فلتر بسيط على عمود 'student'
    if "student" not in df.columns:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches = df[df["student"].str.contains(student_name, case=False, na=False)].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches = df_matches.reset_index(drop=True)
    # نحول الأعمدة لأسماء عربية مرتبة
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب",
        "teacher": "المعلم",
        "date": "التاريخ",
        "status": "الحالة"
    })
    df_matches = df_matches[["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
    return df_matches

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    elements = []

    title_style = ParagraphStyle(name='Title', fontName='Arabic', fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle(name='Normal', fontName='Arabic', fontSize=12, alignment=2)
    footer_style = ParagraphStyle(name='Footer', fontName='Arabic', fontSize=10, alignment=2, textColor=colors.darkblue)

    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), title_style))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), normal_style))
    elements.append(Spacer(1, 8))

    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        absent_count = (df_records["الحالة"] == "غائب").sum()
        present_count = (df_records["الحالة"] == "حاضر").sum()
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Spacer(1, 10))

        header = [reshape_arabic_text(h) for h in ["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            data.append([
                reshape_arabic_text(row["المرة"]),
                reshape_arabic_text(row["الطالب"]),
                reshape_arabic_text(row["المعلم"]),
                reshape_arabic_text(normalize_date_for_pdf(row["التاريخ"])),
                reshape_arabic_text(row["الحالة"])
            ])
        table = Table(data, hAlign='CENTER', colWidths=[60, 150, 120, 110, 70])
        table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Arabic'),
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

# ------------------ CSS ------------------
st.markdown("""
<style>
body { background-color: white; }
h1,h2,h3,h4 { text-align: center; color: #1e293b; font-family: 'Cairo', sans-serif; }
.stButton>button {
  width: 250px;
  height: 60px;
  background-color: #2563eb;
  color: white;
  font-size: 20px;
  font-weight: bold;
  border-radius: 12px;
  display: block;
  margin: 10px auto;
}
.stButton>button:hover {
  background-color: #1e40af;
  transform: scale(1.02);
}
</style>
""", unsafe_allow_html=True)

# ------------------ الصفحات ------------------
if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍🏫 معلم"):
            st.session_state.page = "teacher_login"
            st.rerun()
    with col2:
        if st.button("👦 طالب"):
            st.session_state.page = "student"
            st.rerun()

elif st.session_state.page == "teacher_login":
    st.header("🔐 تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            st.rerun()
        else:
            st.error("❌ كلمة السر غير صحيحة")
    if st.button("🔙 رجوع"):
        st.session_state.page = "home"
        st.rerun()

elif st.session_state.page == "teacher_attendance":
    st.header("📋 تسجيل الغياب")
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    st.subheader(f"👨‍🏫 المعلم: {teacher_name}")

    selected = []
    cols = st.columns(5)
    for i, student in enumerate(STUDENTS):
        col = cols[i % 5]
        with col:
            if st.checkbox(student, key=f"chk_{i}"):
                selected.append(student)

    if st.button("✅ تسجيل"):
        record_attendance(selected, teacher_name)
        st.success("✅ تم تسجيل الغياب بنجاح!")

    if st.button("🔙 رجوع"):
        st.session_state.page = "home"
        st.rerun()

elif st.session_state.page == "student":
    st.header("📄 تقارير الغياب")
    name_input = st.text_input("✏️ اكتب اسمك الثلاثي:")

    if name_input.strip():
        df_student = get_student_records(name_input.strip())
        if df_student.empty:
            st.info("✅ لا يوجد غياب مسجل لهذا الاسم.")
        else:
            # عرض الجدول بدون عمود الـ index الزائد، مع إظهار "المرة" كعمود عادي أولى
            try:
                # إزالة الفهرس تمامًا قبل العرض
                df_display = df_student.reset_index(drop=True)
                st.dataframe(df_display, use_container_width=True)

            except:
                # fallback لو الـ styler مش مدعوم في البيئة
                st.dataframe(df_student, use_container_width=True)

            pdf_buf = generate_student_pdf(name_input.strip(), df_student)
            st.download_button("📄 تحميل PDF", data=pdf_buf, file_name=f"{name_input.strip()}_report.pdf", mime="application/pdf")

    if st.button("🔙 الرجوع"):
        st.session_state.page = "home"
        st.rerun()
