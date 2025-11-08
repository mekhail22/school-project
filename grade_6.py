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

# ------------------ إعداد الصفحة ------------------
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ إعدادات عامة ------------------
SHEET_NAME = "school_attendance"
PASSWORD = "1234"
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ الاتصال بـ Google Sheets ------------------
try:
    service_account_info = st.secrets["SERVICE_ACCOUNT"]
except:
    st.error("ضع JSON ملف خدمة السرفيس داخل secrets باسم SERVICE_ACCOUNT.")
    st.stop()

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
creds = Credentials.from_service_account_info(service_account_info, scopes=SCOPES)
gc = gspread.authorize(creds)
sh = gc.open(SHEET_NAME)
worksheet = sh.sheet1

# ------------------ تحميل خط عربي للـ PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
if not os.path.exists(FONT_PATH):
    url = "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoNaskhArabic/NotoNaskhArabic-Regular.ttf"
    r = requests.get(url)
    with open(FONT_PATH, "wb") as f:
        f.write(r.content)
pdfmetrics.registerFont(TTFont('Arabic', FONT_PATH))

# ------------------ دوال مساعدة ------------------
def reshape_arabic_text(text):
    reshaped = arabic_reshaper.reshape(str(text))
    return get_display(reshaped)

def read_sheet():
    data = worksheet.get_all_records()
    df = pd.DataFrame(data)
    for c in ["student", "teacher", "status", "date"]:
        if c not in df.columns:
            df[c] = ""
    return df

def record_attendance(selected_absent, teacher_name, absent_label):
    date_display = datetime.now().strftime("%d / %m / %Y")
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        worksheet.append_row([student, teacher_name, status, date_display])

def get_student_records(student_name):
    df = read_sheet()
    df_matches = df[df["student"].str.contains(student_name, case=False, na=False)].copy()
    if df_matches.empty:
        return pd.DataFrame(columns=["المرة", "الطالب", "المعلم", "التاريخ", "الحالة"])
    df_matches.reset_index(drop=True, inplace=True)
    df_matches.insert(0, "المرة", range(1, len(df_matches)+1))
    df_matches.rename(columns={
        "student":"الطالب","teacher":"المعلم","date":"التاريخ","status":"الحالة"
    }, inplace=True)
    return df_matches[["المرة","الطالب","المعلم","التاريخ","الحالة"]]

def generate_student_pdf(student_name, df_records):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40,leftMargin=40,topMargin=40,bottomMargin=40)
    elements = []
    title_style = ParagraphStyle('Title', fontName='Arabic', fontSize=18, alignment=1, textColor=colors.darkblue)
    normal_style = ParagraphStyle('Normal', fontName='Arabic', fontSize=12, alignment=2)
    footer_style = ParagraphStyle('Footer', fontName='Arabic', fontSize=10, alignment=2, textColor=colors.darkblue)

    elements.append(Paragraph(reshape_arabic_text("تقرير الغياب"), title_style))
    elements.append(Spacer(1,8))
    elements.append(Paragraph(reshape_arabic_text(f"الاسم: {student_name}"), normal_style))
    elements.append(Spacer(1,8))

    if df_records.empty:
        elements.append(Paragraph(reshape_arabic_text("لا توجد سجلات لهذا الطالب."), normal_style))
    else:
        absent_count = (df_records["الحالة"] != "حاضر").sum()
        present_count = (df_records["الحالة"] == "حاضر").sum()
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الغياب: {absent_count}"), normal_style))
        elements.append(Paragraph(reshape_arabic_text(f"عدد مرات الحضور: {present_count}"), normal_style))
        elements.append(Spacer(1,10))

        header = [reshape_arabic_text(h) for h in ["المرة","الطالب","المعلم","التاريخ","الحالة"]]
        data = [header]
        for _, row in df_records.iterrows():
            data.append([reshape_arabic_text(str(row[col])) for col in ["المرة","الطالب","المعلم","التاريخ","الحالة"]])
        table = Table(data, hAlign='CENTER', colWidths=[60,150,120,110,70])
        table.setStyle(TableStyle([
            ('FONTNAME',(0,0),(-1,-1),'Arabic'),
            ('FONTSIZE',(0,0),(-1,-1),11),
            ('GRID',(0,0),(-1,-1),0.5,colors.black),
            ('BACKGROUND',(0,0),(-1,0),colors.lightgrey),
            ('ALIGN',(0,0),(-1,-1),'RIGHT'),
            ('VALIGN',(0,0),(-1,-1),'MIDDLE')
        ]))
        elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ------------------ CSS + الهيدر ------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap');
#MainMenu, header, footer {visibility: hidden !important;}
.stApp {background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%); font-family: 'Cairo', sans-serif;}

.top-toolbar{
position:fixed; top:0; left:0; right:0; height:70px; background:linear-gradient(135deg,#1e40af,#2563eb);
display:flex; justify-content:space-between; align-items:center; padding:0 20px; box-shadow:0 4px 20px rgba(0,0,0,0.2); z-index:999;
color:white; font-family:'Cairo',sans-serif;
}
.logo-container{display:flex;align-items:center;gap:12px;}
.logo-img{width:48px;height:48px;border-radius:12px; object-fit:contain;border:2px solid rgba(255,255,255,0.3); background:white;padding:4px;}
.school-info{line-height:1.3;}
.school-name{font-size:17px;font-weight:bold;margin:0;}
.school-date{font-size:12px;opacity:0.9;margin:0;}
.nav-buttons{display:flex;gap:12px;}
.nav-btn{background:rgba(255,255,255,0.2);color:white;border:none;padding:10px 22px;border-radius:12px;font-size:15px;font-weight:600;cursor:pointer;transition:all 0.3s ease;backdrop-filter:blur(10px);border:1px solid rgba(255,255,255,0.3);}
.nav-btn:hover{background:white;color:#1e40af;transform:translateY(-3px);box-shadow:0 8px 20px rgba(255,255,255,0.4);}
.content-padding{height:90px;}
.searchBox{display:flex;max-width:320px;align-items:center;justify-content:space-between;gap:8px;background:#2f3640;border-radius:50px;position:relative;padding:5px 15px;}
.searchInput{border:none;background:none;outline:none;color:white;font-size:16px;width:100%;padding:10px;font-family:'Cairo',sans-serif;}
.searchButton{background:linear-gradient(90deg,#2AF598 0%,#009EFD 100%);border:none;color:white;padding:10px 18px;border-radius:50px;cursor:pointer;}
button:hover{color:#fff;background-color:#1A1A1A;box-shadow:rgba(0,0,0,0.5) 0 10px 20px;transform:translateY(-3px);}
button:active{box-shadow:none;transform:translateY(0);}
</style>
""", unsafe_allow_html=True)

# ------------------ الهيدر ------------------
today = datetime.now()
arabic_weekdays=["الإثنين","الثلاثاء","الأربعاء","الخميس","الجمعة","السبت","الأحد"]
arabic_months=["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month-1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

logo_url="https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

st.markdown(f"""
<div class="top-toolbar">
<div class="logo-container">
<img src="{logo_url}" class="logo-img">
<div class="school-info">
<p class="school-name">مدرسة السلام الإعدادية الثانوية المشتركة</p>
<p class="school-date">{formatted_date}</p>
</div>
</div>
<div class="nav-buttons">
<button class="nav-btn" onclick="alert('عن المدرسة: مدرسة السلام...')">عنا</button>
<button class="nav-btn" onclick="alert('اتصل بنا: 0123456789')">اتصل بنا</button>
</div>
</div>
<div class="content-padding"></div>
""", unsafe_allow_html=True)

# ------------------ الصفحات ------------------
if "page" not in st.session_state:
    st.session_state.page="home"

# ------------------ الصفحة الرئيسية ------------------
if st.session_state.page=="home":
    st.title("نظام الغياب")
    col1,col2=st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page="teacher_login"
            st.rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page="student"
            st.rerun()

# ------------------ صفحة تسجيل دخول المعلم ------------------
elif st.session_state.page=="teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd==PASSWORD:
            st.session_state.teacher_name=teacher_choice
            st.session_state.page="teacher_attendance"
            st.rerun()
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page="home"
        st.rerun()

# ------------------ صفحة تسجيل الغياب ------------------
elif st.session_state.page=="teacher_attendance":
    st.header("تسجيل الغياب")
    teacher_name=st.session_state.get("teacher_name","غير معروف")
    st.subheader(f"المعلم: {teacher_name}")
    selected=st.multiselect("اختر الغائبين",STUDENTS)
    st.markdown("**اختر نوع الغياب:**")
    col_a,col_b=st.columns(2)
    with col_a:
        excuse=st.checkbox("غياب بعذر",key="excuse")
    with col_b:
        no_excuse=st.checkbox("غياب بدون عذر",key="no_excuse")
    if excuse and no_excuse:
        st.warning("اختر نوع واحد فقط.")
    if st.button("تسجيل"):
        if not selected:
            st.warning("يجب اختيار طالب/طلاب أولا.")
        elif excuse and no_excuse:
            st.warning("اختر نوع واحد فقط.")
        elif not (excuse or no_excuse):
            st.warning("من فضلك اختر نوع الغياب.")
        else:
            status_label="غياب بعذر" if excuse else "غياب بدون عذر"
            record_attendance(selected,teacher_name,status_label)
            st.success("تم تسجيل الغياب بنجاح")
    if st.button("رجوع"):
        st.session_state.page="home"
        st.rerun()

# ------------------ صفحة الطالب ------------------
elif st.session_state.page=="student":
    st.header("تقارير الغياب")
    if "student_search" not in st.session_state:
        st.session_state.student_search=""
    search_query=st.text_input("اكتب اسمك الثلاثي...", key="student_search", placeholder="اكتب اسمك الثلاثي...")
    if st.button("بحث"):
        if search_query.strip()=="":
            st.warning("من فضلك اكتب اسمك الثلاثي للبحث.")
        else:
            df_student=get_student_records(search_query)
            if df_student.empty:
                st.info("لا يوجد غياب مسجل لهذا الاسم.")
            else:
                st.dataframe(df_student.reset_index(drop=True),use_container_width=True)
                pdf_buf=generate_student_pdf(search_query,df_student)
                st.download_button("تحميل PDF",data=pdf_buf,file_name=f"{search_query}_report.pdf",mime="application/pdf")
    if st.button("الرجوع"):
        st.session_state.page="home"
        st.rerun()
