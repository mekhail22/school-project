# streamlit_app.py
"""
Grade 6 attendance app — مع إصلاح إرسال Telegram وظهور نتيجة الإرسال في الواجهة
"""

import streamlit as st
import pandas as pd
from datetime import datetime
import io
import os
import json
import logging
import base64
import requests

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
st.set_page_config(page_title="نظام الغياب", layout="centered")

# ------------------ App settings ------------------
STUDENTS = [
    "ميخائيل صابر فوزي", "مينا ريمون خيري", "توني هاني نصرالله",
    "يوسف شادي كمال", "ادم مايكل فوزي", "مارك نادر فؤاد",
    "بيشوي عاطف فايز", "جورج مينا نجيب", "كيرلس فادي صادق",
    "يوستينا مجدي فادي"
]
TEACHERS = ["مينا سمير", "فادي حبيب"]

# ------------------ تبسيط تحميل الـ Secrets ------------------
def load_secrets():
    """تحميل كل الإعدادات من Streamlit Secrets بشكل مبسط"""
    try:
        secrets = st.secrets
        
        # Telegram - الطريقة المباشرة
        BOT_TOKEN = None
        CHAT_ID = None
        
        # حاول الوصول للإعدادات بطرق مختلفة
        if hasattr(secrets, 'telegram') and hasattr(secrets.telegram, 'bot_token'):
            BOT_TOKEN = secrets.telegram.bot_token
            CHAT_ID = secrets.telegram.chat_id
        elif hasattr(secrets, 'TELEGRAM_BOT_TOKEN'):
            BOT_TOKEN = secrets.TELEGRAM_BOT_TOKEN
            CHAT_ID = secrets.TELEGRAM_CHAT_ID
        
        # App settings
        PASSWORD = "1234"  # افتراضي
        SHEET_NAME = "school_attendance"  # افتراضي
        
        if hasattr(secrets, 'app') and hasattr(secrets.app, 'password'):
            PASSWORD = secrets.app.password
        if hasattr(secrets, 'app') and hasattr(secrets.app, 'PASSWORD'):
            PASSWORD = secrets.app.PASSWORD
        if hasattr(secrets, 'PASSWORD'):
            PASSWORD = secrets.PASSWORD
            
        if hasattr(secrets, 'sheets') and hasattr(secrets.sheets, 'name'):
            SHEET_NAME = secrets.sheets.name
        if hasattr(secrets, 'SHEET_NAME'):
            SHEET_NAME = secrets.SHEET_NAME
        
        # Service Account
        SERVICE_ACCOUNT = None
        if hasattr(secrets, 'SERVICE_ACCOUNT'):
            SERVICE_ACCOUNT = dict(secrets.SERVICE_ACCOUNT)
        
        return {
            'BOT_TOKEN': BOT_TOKEN,
            'CHAT_ID': CHAT_ID,
            'PASSWORD': PASSWORD,
            'SHEET_NAME': SHEET_NAME,
            'SERVICE_ACCOUNT': SERVICE_ACCOUNT
        }
        
    except Exception as e:
        logger.error(f"خطأ في تحميل الإعدادات: {e}")
        return None

# تحميل الإعدادات
secrets_config = load_secrets()

if not secrets_config:
    st.error("❌ فشل في تحميل إعدادات التطبيق. تأكد من ضبط Secrets في Streamlet Cloud.")
    st.stop()

# تعيين المتغيرات
BOT_TOKEN = secrets_config['BOT_TOKEN']
CHAT_ID = secrets_config['CHAT_ID']
PASSWORD = secrets_config['PASSWORD']
SHEET_NAME = secrets_config['SHEET_NAME']
SERVICE_ACCOUNT = secrets_config['SERVICE_ACCOUNT']

# ------------------ عرض حالة الإعدادات ------------------
def show_secrets_status():
    """عرض حالة الإعدادات في الـ sidebar"""
    st.sidebar.markdown("### 🔧 حالة الإعدادات")
    
    # Telegram
    if BOT_TOKEN and CHAT_ID:
        st.sidebar.success("✅ Telegram: جاهز")
        st.sidebar.write(f"BOT_TOKEN: ✅ موجود")
        st.sidebar.write(f"CHAT_ID: ✅ موجود")
    else:
        st.sidebar.error("❌ Telegram: غير مكتمل")
        st.sidebar.write(f"BOT_TOKEN: {'✅' if BOT_TOKEN else '❌'}")
        st.sidebar.write(f"CHAT_ID: {'✅' if CHAT_ID else '❌'}")
    
    # Service Account
    if SERVICE_ACCOUNT:
        st.sidebar.success("✅ Google Sheets: جاهز")
        st.sidebar.write(f"Service Account: ✅ موجود")
    else:
        st.sidebar.error("❌ Google Sheets: غير مكتمل")
    
    # App Settings
    st.sidebar.info(f"🔑 كلمة السر: {'✅' if PASSWORD else '❌'}")
    st.sidebar.info(f"📊 اسم الورقة: {SHEET_NAME}")

# استدعاء الدالة
show_secrets_status()

# ------------------ التحقق من الإعدادات المطلوبة ------------------
if not SERVICE_ACCOUNT:
    st.error("""
    ❌ SERVICE_ACCOUNT غير موجود في Secrets.
    
    أضف هذه الإعدادات في Streamlit Cloud:
    1. اذهب إلى Settings → Secrets
    2. الصق هذا الكود:
    
    ```toml
    [SERVICE_ACCOUNT]
    type = "service_account"
    project_id = "مشروعك"
    private_key_id = "المفتاح"
    private_key = \"\"\"-----BEGIN PRIVATE KEY-----
    ...
    -----END PRIVATE KEY-----\"\"\"
    client_email = "الحساب@المشروع.iam.gserviceaccount.com"
    client_id = "الرقم"
    auth_uri = "https://accounts.google.com/o/oauth2/auth"
    token_uri = "https://oauth2.googleapis.com/token"
    auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
    client_x509_cert_url = "الرابط"
    ```
    """)
    st.stop()

# ------------------ Connect to Google Sheets ------------------
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
try:
    creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
    gc = gspread.authorize(creds)
except Exception as e:
    logger.exception("Google API auth failed")
    st.error("خطأ في تهيئة اعتماد Google API: " + str(e))
    st.stop()

try:
    sh = gc.open(SHEET_NAME)
    worksheet = sh.sheet1
    st.sidebar.success("✅ تم الاتصال بـ Google Sheets")
except Exception as e:
    logger.exception("Failed opening sheet")
    st.error(f"""
    خطأ في فتح Google Sheet: {str(e)}
    
    تأكد من:
    1. اسم المصنف: {SHEET_NAME}
    2. مشاركة الـ Sheet مع: {SERVICE_ACCOUNT.get('client_email', 'بريد الخدمة')}
    3. منح صلاحية Editor للحساب
    """)
    st.stop()

# ------------------ Arabic font for PDF ------------------
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
            logger.info("Downloaded Arabic font.")
        except Exception as e:
            logger.warning("Failed to download Arabic font: %s", e)
    try:
        if os.path.exists(FONT_PATH):
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
    except Exception as e:
        logger.warning("Failed to register font from path: %s", e)

    # Fallback attempts
    for candidate in ["Arial", "DejaVuSans", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            logger.info("Used fallback font: %s", candidate)
            return FONT_NAME
        except Exception:
            continue

    logger.error("No usable font registered.")
    return None

REGISTERED_FONT = ensure_font()

# ------------------ Helper functions ------------------
def reshape_arabic_text(text):
    try:
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)
    except Exception:
        return str(text)

def read_sheet():
    try:
        data = worksheet.get_all_records()
    except Exception as e:
        logger.exception("Failed to read sheet")
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

# ------------------ Telegram: improved send function ------------------
def send_telegram_message(message):
    """
    Send message to Telegram using POST. Returns (ok: bool, info: dict_or_text).
    """
    if not BOT_TOKEN or not CHAT_ID:
        logger.info("Telegram credentials missing, skipping send.")
        return False, {"error": "credentials_missing", "bot_token_present": bool(BOT_TOKEN), "chat_id_present": bool(CHAT_ID)}

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
    except requests.exceptions.RequestException as e:
        logger.exception("Telegram send exception")
        return False, {"exception": str(e)}

def record_attendance(selected_absent, teacher_name, absent_label):
    if not isinstance(selected_absent, (list, tuple)):
        selected_absent = [selected_absent] if selected_absent else []
    date_display = datetime.now().strftime("%d / %m / %Y")
    rows = []
    for student in STUDENTS:
        status = absent_label if student in selected_absent else "حاضر"
        rows.append([student, teacher_name, status, date_display])

    failed = []
    try:
        worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception:
        logger.exception("Batch append failed, falling back to per-row append.")
        for r in rows:
            try:
                worksheet.append_row(r, value_input_option="USER_ENTERED")
            except Exception as ex:
                logger.exception("append_row failed for %s", r[0])
                failed.append((r[0], str(ex)))

    absent_students = ", ".join(selected_absent) if selected_absent else "لا أحد"
    message = f"تم تسجيل الغياب بتاريخ {date_display}\nالمعلم: {teacher_name}\nحالة الغياب: {absent_label}\nغائبون: {absent_students}"
    
    # إرسال إلى Telegram مع عرض النتيجة
    telegram_status = "لم يتم الإرسال"
    telegram_details = ""
    
    if BOT_TOKEN and CHAT_ID:
        ok, info = send_telegram_message(message)
        if ok:
            telegram_status = "✅ تم الإرسال بنجاح"
            telegram_details = f"تم إرسال الإشعار إلى Telegram"
        else:
            telegram_status = "❌ فشل الإرسال"
            telegram_details = f"تفاصيل الخطأ: {info}"
    else:
        telegram_status = "⚠️ إعدادات Telegram غير مكتملة"
        telegram_details = f"BOT_TOKEN: {'موجود' if BOT_TOKEN else 'مفقود'}, CHAT_ID: {'موجود' if CHAT_ID else 'مفقود'}"
    
    return failed, telegram_status, telegram_details

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

# ------------------ Image helper ------------------
def get_image_base64(image_path):
    try:
        with open(image_path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode('utf-8')
    except Exception as e:
        logger.warning("Failed loading image %s: %s", image_path, e)
        return None

logo_base64 = get_image_base64("images.jpeg")
if logo_base64:
    logo_src = f"data:image/jpeg;base64,{logo_base64}"
else:
    logo_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/f/fe/Flag_of_Egypt.svg/1280px-Flag_of_Egypt.svg.png"

# ------------------ Arabic date for header ------------------
today = datetime.now()
arabic_weekdays = ["الإثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]
arabic_months = ["يناير", "فبراير", "مارس", "أبريل", "مايو", "يونيو", "يوليو", "أغسطس", "سبتمبر", "أكتوبر", "نوفمبر", "ديسمبر"]
weekday = arabic_weekdays[today.weekday()]
month = arabic_months[today.month - 1]
formatted_date = f"{weekday}، {today.day} {month} {today.year}"

# ------------------ باقي الكود بدون تغيير (CSS, HTML, UI) ------------------
# ... [كل الكود الخاص بالواجهة والـ CSS يبقى كما هو بدون تغيير] ...

# ------------------ UI / Navigation ------------------
def safe_rerun():
    try:
        st.rerun()
    except Exception:
        logger.exception("Rerun failed (non-fatal).")

if "page" not in st.session_state:
    st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("نظام الغياب")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("معلم"):
            st.session_state.page = "teacher_login"
            safe_rerun()
    with col2:
        if st.button("طالب"):
            st.session_state.page = "student"
            safe_rerun()

elif st.session_state.page == "teacher_login":
    st.header("تسجيل دخول المعلم")
    teacher_choice = st.selectbox("اختر اسمك:", TEACHERS)
    pwd = st.text_input("كلمة السر:", type="password")
    if st.button("تسجيل الدخول"):
        if pwd == PASSWORD:
            st.session_state.teacher_name = teacher_choice
            st.session_state.page = "teacher_attendance"
            safe_rerun()
        else:
            st.error("كلمة السر غير صحيحة")
    if st.button("رجوع"):
        st.session_state.page = "home"
        safe_rerun()

elif st.session_state.page == "teacher_attendance":
    st.header("تسجيل الغياب")
    teacher_name = st.session_state.get("teacher_name", "غير معروف")
    st.subheader(f"المعلم: {teacher_name}")
    selected = st.multiselect("اختر الغائبين", STUDENTS)
    st.markdown("**اختر نوع الغياب:**")
    col_a, col_b = st.columns(2)
    with col_a:
        excuse = st.checkbox("غياب بعذر", key="excuse")
    with col_b:
        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")
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
            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
            try:
                failed, telegram_status, telegram_details = record_attendance(selected, teacher_name, status_label)
            except Exception as e:
                logger.exception("Error during record_attendance")
                st.error(f"حدث خطأ أثناء تسجيل الغياب: {e}")
            else:
                if not failed:
                    st.success("✅ تم تسجيل الغياب بنجاح في Google Sheets")
                    
                    # عرض حالة Telegram
                    if "✅" in telegram_status:
                        st.success(telegram_status)
                    elif "❌" in telegram_status:
                        st.warning(telegram_status)
                    else:
                        st.info(telegram_status)
                        
                    if telegram_details:
                        with st.expander("تفاصيل إرسال Telegram"):
                            st.write(telegram_details)
                else:
                    st.error(f"حدثت أخطاء عند تسجيل بعض الطلاب: {failed}")

    if st.button("رجوع"):
        st.session_state.page = "home"
        safe_rerun()

elif st.session_state.page == "student":
    st.header("تقارير الغياب")
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

    if st.button("رجوع"):
        if "student_search" in st.session_state:
            del st.session_state.student_search
        st.session_state.page = "home"
        safe_rerun()
