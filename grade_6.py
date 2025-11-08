import streamlit as st
import pandas as pd
from datetime import datetime
import io
import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle

# ---------------------------------------------
# دالة إنشاء PDF لتقرير الطالب
# ---------------------------------------------
def generate_student_pdf(student_name, df_student):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    elements = []

    style = ParagraphStyle(name="Arabic", fontName="Helvetica", fontSize=12, alignment=2)
    reshaped_name = get_display(arabic_reshaper.reshape(student_name))
    title = Paragraph(f"<b>تقرير الغياب للطالب:</b> {reshaped_name}", style)
    elements.append(title)
    elements.append(Spacer(1, 12))

    data = [["التاريخ", "الحالة", "المعلم"]]
    for _, row in df_student.iterrows():
        reshaped_teacher = get_display(arabic_reshaper.reshape(str(row["teacher"])))
        reshaped_status = get_display(arabic_reshaper.reshape(str(row["status"])))
        reshaped_date = get_display(arabic_reshaper.reshape(str(row["date"])))
        data.append([reshaped_date, reshaped_status, reshaped_teacher])

    table = Table(data, colWidths=[120, 120, 120])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#009EFD")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 12),
        ("BACKGROUND", (0, 1), (-1, -1), colors.beige),
        ("GRID", (0, 0), (-1, -1), 1, colors.gray),
    ]))
    elements.append(table)
    doc.build(elements)
    buffer.seek(0)
    return buffer

# ---------------------------------------------
# دالة جلب بيانات الطالب
# ---------------------------------------------
def get_student_records(student_name):
    df = pd.read_csv("attendance.csv")
    return df[df["student"].str.contains(student_name, case=False, na=False)]

# ---------------------------------------------
# واجهة التطبيق
# ---------------------------------------------
st.set_page_config(page_title="نظام الغياب", page_icon="📘", layout="centered")

if "page" not in st.session_state:
    st.session_state.page = "home"

# الصفحة الرئيسية
if st.session_state.page == "home":
    st.title("📘 نظام الغياب")
    st.write("مرحبًا! اختر نوع الدخول:")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("👨‍🏫 دخول المعلم"):
            st.session_state.page = "teacher"
    with col2:
        if st.button("👨‍🎓 دخول الطالب"):
            st.session_state.page = "student"

# صفحة المعلم (اختصار)
elif st.session_state.page == "teacher":
    st.header("📘 واجهة المعلم")
    st.info("هنا تضاف بيانات الغياب (الجزء ده اختصرناه).")
    if st.button("🔙 الرجوع"):
        st.session_state.page = "home"
        st.rerun()

# ---------------------------------------------
# صفحة الطالب بمحرك البحث الجديد
# ---------------------------------------------
elif st.session_state.page == "student":
    st.header("📄 تقارير الغياب")

    # CSS الجديد
    st.markdown("""
    <style>
    /* From Uiverse.io by OnlyCodeChannel */
    .searchBox {
      display: flex;
      max-width: 230px;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
      background: #2f3640;
      border-radius: 50px;
      position: relative;
      margin: 0 auto 25px auto;
      box-shadow: 0 4px 12px rgba(0,0,0,0.1);
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
      display: flex;
      align-items: center;
      justify-content: center;
      transition: all 300ms cubic-bezier(.23, 1, 0.32, 1);
      font-weight: bold;
      font-size: 14px;
      font-family: 'Cairo', sans-serif;
    }
    .searchInput {
      border: none;
      background: none;
      outline: none;
      color: white;
      font-size: 15px;
      padding: 24px 46px 24px 26px;
      width: 100%;
      font-family: 'Cairo', sans-serif;
    }
    .searchInput::placeholder {
      color: #bdc3c7;
    }
    </style>
    """, unsafe_allow_html=True)

    # واجهة البحث
    st.markdown("""
    <div class="searchBox">
        <input class="searchInput" type="text" id="studentInput" placeholder="اكتب اسم الطالب الثلاثي...">
        <button class="searchButton" onclick="window.parent.postMessage({type: 'searchStudent', value: document.getElementById('studentInput').value}, '*')">بحث</button>
    </div>
    """, unsafe_allow_html=True)

    # حقل البحث المخفي للربط بين JS و Streamlit
    student_name = st.text_input("", key="student_name_hidden", label_visibility="collapsed")

    # JavaScript لربط الزر مع Streamlit
    st.markdown("""
    <script>
    window.addEventListener('message', (event) => {
        if (event.data.type === 'searchStudent') {
            const input = event.data.value.trim();
            const streamlitInput = window.parent.document.querySelector('input[id^="student_name_hidden"]');
            if (streamlitInput) {
                streamlitInput.value = input;
                streamlitInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }
    });
    </script>
    """, unsafe_allow_html=True)

    # عرض نتائج البحث
    if student_name:
        df_student = get_student_records(student_name)
        if df_student.empty:
            st.info("❌ لا يوجد غياب مسجل لهذا الاسم.")
        else:
            st.dataframe(df_student.reset_index(drop=True), use_container_width=True)
            pdf_buf = generate_student_pdf(student_name, df_student)
            st.download_button(
                "📄 تحميل PDF",
                data=pdf_buf,
                file_name=f"{student_name}_report.pdf",
                mime="application/pdf"
            )
    else:
        st.info("✏️ اكتب اسمك الثلاثي ثم اضغط (بحث) لعرض تقرير الغياب.")

    # زر الرجوع
    if st.button("🔙 الرجوع"):
        st.session_state.student_name_hidden = ""
        st.session_state.page = "home"
        st.rerun()
