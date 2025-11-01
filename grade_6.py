import streamlit as st
import pandas as pd
import csv
import os
from datetime import datetime
import io
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import requests

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ إعدادات عامة ------------------
CSV_FILE = "attendance.csv"
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

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
except Exception:
    try:
        pdfmetrics.registerFont(TTFont('Arabic', 'arial.ttf'))
    except Exception:
        pass

# ------------------ دوال مساعدة ------------------
def ensure_csv_header():
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["student", "teacher", "status", "date"])

def reshape_arabic_text(text):
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        bidi_text = get_display(reshaped)
        return bidi_text
    except Exception:
        return str(text)

def read_csv_normalized():
    ensure_csv_header()
    df = pd.read_csv(CSV_FILE, dtype=str, encoding="utf-8")
    df.rename(columns={c: c.strip() for c in df.columns}, inplace=True)
    rename_map = {}
    if "الطالب" in df.columns and "student" not in df.columns:
        rename_map["الطالب"] = "student"
    if "الاسم" in df.columns and "student" not in df.columns:
        rename_map["الاسم"] = "student"
    if "name" in df.columns and "student" not in df.columns:
        rename_map["name"] = "student"
    if "المدرس" in df.columns and "teacher" not in df.columns:
        rename_map["المدرس"] = "teacher"
    if "teacher_name" in df.columns and "teacher" not in df.columns:
        rename_map["teacher_name"] = "teacher"
    if "الحالة" in df.columns and "status" not in df.columns:
        rename_map["الحالة"] = "status"
    if "state" in df.columns and "status" not in df.columns:
        rename_map["state"] = "status"
    if "التاريخ" in df.columns and "date" not in df.columns:
        rename_map["التاريخ"] = "date"
    if "Date" in df.columns and "date" not in df.columns:
        rename_map["Date"] = "date"
    if rename_map:
        df = df.rename(columns=rename_map)
    for c in ["student", "teacher", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    df = df[["student", "teacher", "status", "date"]]
    return df

def normalize_date_for_pdf(src_date_str):
    """تحويل أي شكل شائع للتاريخ إلى dd / mm / YYYY"""
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

def record_attendance(selected_absent, teacher_name):
    ensure_csv_header()
    date_display = datetime.now().strftime("%d / %m / %Y")
    df = read_csv_normalized()
    new_rows = []
    for student in STUDENTS:
        status = "غائب" if student in selected_absent else "حاضر"
        new_rows.append({"student": student, "teacher": teacher_name, "status": status, "date": date_display})
    df_new = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)
    df_new.to_csv(CSV_FILE, index=False, encoding="utf-8")

def get_student_records(student_name):
    df = read_csv_normalized()
    df_matches = df[df["student"].str.contains(student_name, case=False, na=False)].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المدرس", "التاريخ", "الحالة"])
    df_matches = df_matches.reset_index(drop=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches) + 1))
    df_matches = df_matches.rename(columns={
        "student": "الطالب",
        "teacher": "المدرس",
        "date": "التاريخ",
        "status": "الحالة"
    })
    df_matches = df_matches[["المرة", "الطالب", "المدرس", "التاريخ", "الحالة"]]
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

        # ترتيب الأعمدة المطلوب: الحالة – التاريخ – المدرس – الطالب – المرة
        header = [
            reshape_arabic_text("المرة"),
            reshape_arabic_text("الطالب"),
            reshape_arabic_text("المدرس"),
            reshape_arabic_text("التاريخ"),
            reshape_arabic_text("الحالة")
        ]
        data = [header]

        for _, row in df_records.iterrows():
            حالة = row.get("الحالة", "")
            تاريخ_raw = row.get("التاريخ", "")
            تاريخ = normalize_date_for_pdf(تاريخ_raw)
            مدرس = row.get("المدرس", "")
            طالب = row.get("الطالب", "")
            مرة = row.get("المرة", "")
            data.append([
                reshape_arabic_text(مرة),
                reshape_arabic_text(طالب),
                reshape_arabic_text(مدرس),
                reshape_arabic_text(تاريخ),
                reshape_arabic_text(حالة)
            ])

        table = Table(data, hAlign='CENTER', colWidths=[70, 110, 110, 120, 50])
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
        if st.button("👨‍🏫 مدرس"):
            st.session_state.page = "teacher_login"
            st.rerun()
    with col2:
        if st.button("👦 طالب"):
            st.session_state.page = "student"
            st.rerun()

elif st.session_state.page == "teacher_login":
    st.header("🔐 تسجيل دخول المدرس")
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
    st.subheader(f"👨‍🏫 المدرس: {teacher_name}")

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
            st.dataframe(df_student, use_container_width=True)
            pdf_buf = generate_student_pdf(name_input.strip(), df_student)
            st.download_button("📄 تحميل PDF", data=pdf_buf, file_name=f"{name_input.strip()}_report.pdf", mime="application/pdf")
