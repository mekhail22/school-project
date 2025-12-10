# attendance_app.py
# تطبيق Streamlit - نظام غياب مع هيدر ثابت + برجر منيو + تقارير PDF + Google Sheets + Telegram
# ملاحظة: عدّل القيم في st.secrets أو استبدلها يدوياً قبل التشغيل (BOT_TOKEN, CHAT_ID, SERVICE_ACCOUNT)

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
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except Exception:
    ARABIC_SUPPORT = False

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Google Sheets / Auth
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEETS_AVAILABLE = True
except Exception:
    GSHEETS_AVAILABLE = False

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

USERS = {
    "مينا سمير": {"password": "teacher123", "role": "teacher", "teacher_name": "مينا سمير"},
    "فادي حبيب": {"password": "teacher123", "role": "teacher", "teacher_name": "فادي حبيب"},
}

# Add students to USERS programmatically
for s in STUDENTS:
    USERS.setdefault(s, {"password": "student123", "role": "student", "student_name": s})

# ------------------ Secrets loader ------------------
def load_secrets():
    secrets = {}
    try:
        # Telegram
        BOT_TOKEN = None
        CHAT_ID = None
        SERVICE_ACCOUNT = None
        SHEET_NAME = "school_attendance"

        if hasattr(st, "secrets"):
            sec = st.secrets
            # telegram
            try:
                BOT_TOKEN = sec.get("telegram", {}).get("bot_token")
                CHAT_ID = sec.get("telegram", {}).get("chat_id")
            except Exception:
                BOT_TOKEN = None
                CHAT_ID = None

            # sheets
            try:
                SHEET_NAME = sec.get("sheets", {}).get("name", SHEET_NAME)
            except Exception:
                SHEET_NAME = SHEET_NAME

            # service account: either a JSON string in SERVICE_ACCOUNT_JSON or a mapping SERVICE_ACCOUNT
            if "SERVICE_ACCOUNT_JSON" in sec:
                try:
                    SERVICE_ACCOUNT = json.loads(sec["SERVICE_ACCOUNT_JSON"])
                except Exception:
                    SERVICE_ACCOUNT = None
            elif "SERVICE_ACCOUNT" in sec:
                SERVICE_ACCOUNT = sec["SERVICE_ACCOUNT"]

        secrets = {
            "BOT_TOKEN": BOT_TOKEN,
            "CHAT_ID": CHAT_ID,
            "SHEET_NAME": SHEET_NAME,
            "SERVICE_ACCOUNT": SERVICE_ACCOUNT
        }
    except Exception as e:
        logger.warning("Failed to load secrets: %s", e)
        secrets = {"BOT_TOKEN": None, "CHAT_ID": None, "SHEET_NAME": "school_attendance", "SERVICE_ACCOUNT": None}
    return secrets

secrets_config = load_secrets()
BOT_TOKEN = secrets_config.get("BOT_TOKEN")
CHAT_ID = secrets_config.get("CHAT_ID")
SHEET_NAME = secrets_config.get("SHEET_NAME")
SERVICE_ACCOUNT = secrets_config.get("SERVICE_ACCOUNT")

# ------------------ Google Sheets connect ------------------
worksheet = None
connection_status = "غير متصل"
connection_details = ""

if GSHEETS_AVAILABLE and SERVICE_ACCOUNT and isinstance(SERVICE_ACCOUNT, dict) and SERVICE_ACCOUNT.get("private_key"):
    try:
        SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(SERVICE_ACCOUNT, scopes=SCOPES)
        gc = gspread.authorize(creds)
        try:
            sh = gc.open(SHEET_NAME)
            worksheet = sh.sheet1
            try:
                current_data = worksheet.get_all_records()
                connection_status = "✅ متصل بـ Google Sheets"
                connection_details = f"تم تحميل {len(current_data)} سجل"
                if not current_data:
                    headers = ["student", "teacher", "status", "date"]
                    worksheet.append_row(headers)
                    connection_details += " - تم إنشاء جدول جديد"
            except Exception as e:
                connection_status = f"✅ متصل ولكن خطأ في القراءة: {e}"
        except gspread.exceptions.SpreadsheetNotFound:
            connection_status = f"❌ لم يتم العثور على Google Sheet باسم: {SHEET_NAME}"
        except Exception as e:
            connection_status = f"❌ خطأ في فتح الـ Sheet: {e}"
    except Exception as e:
        connection_status = f"❌ فشل في المصادقة: {e}"
else:
    if not GSHEETS_AVAILABLE:
        connection_status = "⚠️ مكتبة gspread غير مثبتة"
    else:
        connection_status = "⚠️ إعدادات Google Service Account غير مكتملة"

# ------------------ Fonts for PDF ------------------
FONT_PATH = "NotoNaskhArabic-Regular.ttf"
FONT_NAME = "ArabicCustom"

def ensure_font():
    # try local file, otherwise fallback to general fonts
    if not os.path.exists(FONT_PATH):
        # attempt to download (best-effort)
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
            pdfmetrics.registerFont(TTFont(FONT_NAME, FONT_PATH))
            return FONT_NAME
    except Exception:
        pass
    # fallback attempts
    for candidate in ["DejaVuSans", "Arial", "Helvetica"]:
        try:
            pdfmetrics.registerFont(TTFont(FONT_NAME, f"{candidate}.ttf"))
            return FONT_NAME
        except Exception:
            continue
    return None

REGISTERED_FONT = ensure_font()

# ------------------ Helpers ------------------
def reshape_arabic_text(text):
    if not ARABIC_SUPPORT:
        return str(text)
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
    except requests.exceptions.RequestException as e:
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
    success_count = 0
    if worksheet:
        try:
            worksheet.append_rows(rows, value_input_option="USER_ENTERED")
            success_count = len(rows)
        except Exception as e:
            # fallback: append one-by-one
            try:
                for r in rows:
                    worksheet.append_row(r, value_input_option="USER_ENTERED")
                    success_count += 1
            except Exception as ex:
                failed.append(("جميع الطلاب", str(ex)))
    else:
        failed.append(("جميع الطلاب", "لا يوجد اتصال بـ Google Sheets"))
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
    df_matches = df_matches.rename(columns={"student": "الطالب", "teacher": "المعلم", "date": "التاريخ", "status": "الحالة"})
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

# ------------------ UI helpers: Header + Burger (Streamlit-friendly) ------------------
def render_header_and_burger(show_header=True):
    # header HTML (fixed) + burger button + sidebar skeleton + minimal JS that tolerates rerenders
    header_html = f"""
    <style>
    /* Reset some streamlit default visibility but keep top toolbar visible */
    /* Main header fixed */
    .my-main-header {{
        width: 100%;
        padding: 8px 18px;
        display: flex;
        align-items: center;
        gap: 12px;
        background: #ffffff;
        border-bottom: 1px solid rgba(0,0,0,0.06);
        position: fixed;
        top: 0;
        left: 0;
        z-index: 9999;
        box-shadow: 0 1px 8px rgba(0,0,0,0.03);
    }}
    .my-main-header img {{
        width:44px; height:44px; border-radius:8px;
    }}
    .my-main-header h2 {{
        margin:0; font-size:18px; color:#0b4a6f; font-weight:700;
    }}
    .header-space{{height:68px; width:100%;}}

    /* burger */
    #my-burger {{
        position: fixed;
        top: 14px;
        right: 16px;
        z-index: 10001;
        width: 52px;
        height: 52px;
        border-radius: 10px;
        display:flex;
        align-items:center;
        justify-content:center;
        background: linear-gradient(135deg,#2563eb,#1e40af);
        color:white;
        box-shadow: 0 6px 18px rgba(37,99,235,0.25);
        cursor: pointer;
    }}
    #my-burger .lines {{ display:block; width:22px; height:2px; background:white; box-shadow: 0 6px 0 0 white, 0 -6px 0 0 white; border-radius:2px; }}
    /* sidebar */
    #my-sidebar {{
        position: fixed;
        top: 0;
        right: 0;
        width: 0;
        height: 100vh;
        background: white;
        z-index:10000;
        box-shadow: -8px 0 30px rgba(0,0,0,0.12);
        overflow: hidden;
        transition: width 0.28s ease;
        padding-top: 80px;
    }}
    #my-sidebar.open {{ width: 300px; }}
    .my-nav-item {{ padding: 14px 18px; font-weight:700; color:#0b4a6f; border-bottom:1px solid #f1f5f9; cursor:pointer; text-align:right; }}
    .my-nav-head {{ padding: 18px; background: linear-gradient(135deg,#1e40af,#2563eb); color:white; font-weight:800; text-align:center; position:absolute; top:0; width:100%; }}
    </style>
    """

    header_html += """
    <div id="my-burger" role="button" aria-label="menu">
        <span class="lines"></span>
    </div>

    <div id="my-sidebar" aria-hidden="true">
        <div class="my-nav-head">🌙 قائمة التنقل</div>
        <div style="margin-top:10px;"></div>
        <div style="direction:rtl; padding:8px;">
            <div class="my-nav-item" onclick="window.location.href=window.location.pathname + '?page=home'">🏠 الصفحة الرئيسية</div>
            <div class="my-nav-item" onclick="window.location.href=window.location.pathname + '?page=teacher_attendance'">📝 تسجيل الغياب</div>
            <div class="my-nav-item" onclick="window.location.href=window.location.pathname + '?page=student_dashboard'">📊 تقريري</div>
            <div class="my-nav-item" onclick="window.location.href=window.location.pathname + '?action=logout'">🚪 تسجيل الخروج</div>
        </div>
    </div>
    """

    # header body (logo + title) - render only when show_header True
    if show_header:
        header_html += """
        <div class="my-main-header" id="myMainHeader">
            <img src="https://i.imgur.com/1Q9Z1Zq.png" alt="logo">
            <h2>مدرسة ميخائيل صابر فوزي</h2>
        </div>
        <div class="header-space"></div>
        """
    else:
        # still keep space so layout not jumpy
        header_html += "<div class='header-space'></div>"

    # JS: resilient to re-renders: attach event after short timeout and guard existence
    header_html += """
    <script>
    (function() {
        function attach() {
            try {
                var burger = document.getElementById('my-burger');
                var sidebar = document.getElementById('my-sidebar');
                if (!burger || !sidebar) return;
                // avoid duplicate handlers
                if (!burger.dataset.attached) {
                    burger.dataset.attached = '1';
                    burger.addEventListener('click', function(e) {
                        if (sidebar.classList.contains('open')) {
                            sidebar.classList.remove('open');
                            sidebar.setAttribute('aria-hidden','true');
                        } else {
                            sidebar.classList.add('open');
                            sidebar.setAttribute('aria-hidden','false');
                        }
                    });
                }
            } catch(e) {
                console.log('attach error', e);
            }
        }
        // try multiple times in case Streamlit re-renders
        setTimeout(attach, 200);
        setTimeout(attach, 600);
        setTimeout(attach, 1200);
    })();
    </script>
    """
    st.markdown(header_html, unsafe_allow_html=True)

# ------------------ App flow (state management) ------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_role" not in st.session_state:
    st.session_state.user_role = ""
if "user_name" not in st.session_state:
    st.session_state.user_name = ""
if "page" not in st.session_state:
    st.session_state.page = "login"

query_params = st.experimental_get_query_params()
# handle logout/page via query params
if "action" in query_params and query_params["action"][0] == "logout":
    st.session_state.logged_in = False
    st.session_state.user_role = ""
    st.session_state.user_name = ""
    st.session_state.page = "login"
    # clear params (best-effort)
    try:
        st.experimental_set_query_params()
    except Exception:
        pass
    st.experimental_rerun()

if "page" in query_params:
    page = query_params["page"][0]
    if page in ["home", "teacher_attendance", "student_dashboard"]:
        st.session_state.page = page
        try:
            st.experimental_set_query_params()
        except Exception:
            pass
        st.experimental_rerun()

# Decide whether to show header (hide on login)
show_header_flag = st.session_state.page != "login"
render_header_and_burger(show_header=show_header_flag)

# Main UI
def login_screen():
    st.markdown("<div style='max-width:680px; margin:0 auto;'>", unsafe_allow_html=True)
    st.markdown("<div style='background:white; padding:28px; border-radius:12px; box-shadow:0 12px 30px rgba(2,6,23,0.06); text-align:center;'>", unsafe_allow_html=True)
    st.markdown("<h2 style='color:#0b4a6f; margin:0 0 10px 0;'>🚪 تسجيل الدخول</h2>", unsafe_allow_html=True)
    username = st.text_input("اسم المستخدم", placeholder="مثال: مينا سمير أو اسم الطالب")
    password = st.text_input("كلمة المرور", type="password", placeholder="كلمة السر")
    if st.button("✅ تسجيل الدخول", use_container_width=True):
        if username and password:
            if username in USERS and USERS[username]["password"] == password:
                st.session_state.logged_in = True
                st.session_state.user_name = username
                st.session_state.user_role = USERS[username]["role"]
                if USERS[username]["role"] == "teacher":
                    st.session_state.teacher_name = USERS[username]["teacher_name"]
                    st.session_state.page = "teacher_attendance"
                else:
                    st.session_state.student_name = USERS[username]["student_name"]
                    st.session_state.page = "student_dashboard"
                st.success(f"✅ مرحباً {username}!")
                st.experimental_rerun()
            else:
                st.error("❌ اسم المستخدم أو كلمة المرور غير صحيحة")
        else:
            st.error("❌ من فضلك أدخل اسم المستخدم وكلمة المرور")
    st.markdown("</div></div>", unsafe_allow_html=True)

def teacher_attendance_page():
    st.markdown("<div style='max-width:980px; margin:0 auto;'>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center; color:#0b4a6f;'>📝 تسجيل الغياب</h1>", unsafe_allow_html=True)
    teacher_name = st.session_state.get("teacher_name", st.session_state.user_name)
    st.markdown("**اختر الطلاب الغائبين:**")
    selected = st.multiselect("اختر الطلاب الغائبين", STUDENTS)
    st.markdown("**اختر نوع الغياب:**")
    col1, col2 = st.columns(2)
    with col1:
        excuse = st.checkbox("غياب بعذر", key="excuse")
    with col2:
        no_excuse = st.checkbox("غياب بدون عذر", key="no_excuse")
    if excuse and no_excuse:
        st.warning("⚠️ اختر نوع واحد فقط.")
    if st.button("💾 حفظ وتسجيل الغياب", use_container_width=True):
        if not selected:
            st.warning("⚠️ يجب اختيار طالب/طلاب أولا.")
        elif excuse and no_excuse:
            st.warning("⚠️ اختر نوع واحد فقط.")
        elif not (excuse or no_excuse):
            st.warning("⚠️ من فضلك اختر نوع الغياب.")
        else:
            status_label = "غياب بعذر" if excuse else "غياب بدون عذر"
            try:
                failed, telegram_status, telegram_details, success_count = record_attendance(selected, teacher_name, status_label)
            except Exception as e:
                st.error(f"❌ حدث خطأ أثناء تسجيل الغياب: {e}")
            else:
                if success_count > 0:
                    st.success(f"✅ تم تسجيل الغياب بنجاح لـ {success_count} طالب")
                if failed:
                    st.error(f"⚠️ حدثت بعض الأخطاء: {failed}")
    st.markdown("</div>", unsafe_allow_html=True)

def student_dashboard_page():
    st.markdown("<div style='max-width:1100px; margin:0 auto;'>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center; color:#0b4a6f;'>📊 تقرير الغياب الخاص بي</h1>", unsafe_allow_html=True)
    student_name = st.session_state.get("student_name", st.session_state.user_name)
    df_student = get_student_records(student_name)
    if df_student.empty:
        st.info(f"ℹ️ لا يوجد سجلات غياب لك يا {student_name}")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            absent_count = int((df_student["الحالة"] == "غياب بعذر").sum() + (df_student["الحالة"] == "غياب بدون عذر").sum())
            st.metric("عدد مرات الغياب", absent_count)
        with col2:
            present_count = int((df_student["الحالة"] == "حاضر").sum())
            st.metric("عدد مرات الحضور", present_count)
        with col3:
            total_count = len(df_student)
            percentage = (present_count / total_count * 100) if total_count > 0 else 0
            st.metric("نسبة الحضور", f"{percentage:.1f}%")
        st.markdown("**تفاصيل السجلات:**")
        st.dataframe(df_student, use_container_width=True, hide_index=True)
        pdf_buf = generate_student_pdf(student_name, df_student)
        st.download_button("📥 تحميل تقرير PDF", data=pdf_buf, file_name=f"{student_name}_report.pdf", mime="application/pdf")
    st.markdown("</div>", unsafe_allow_html=True)

def home_page():
    st.markdown("<div style='max-width:900px; margin:0 auto;'>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align:center; color:#0b4a6f;'>🏠 الصفحة الرئيسية</h1>", unsafe_allow_html=True)
    if st.session_state.user_role == "teacher":
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📝 تسجيل الغياب", use_container_width=True):
                st.session_state.page = "teacher_attendance"
                st.experimental_rerun()
        with col2:
            if st.button("👨‍🎓 عرض تقارير", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.experimental_rerun()
    else:
        col1, col2 = st.columns([2,1])
        with col1:
            if st.button("📊 تقرير الغياب الخاص بي", use_container_width=True):
                st.session_state.page = "student_dashboard"
                st.experimental_rerun()
        with col2:
            st.info("👈 استخدم زر القايمة (البرجر) أعلى يمين للتنقل")
    st.markdown("</div>", unsafe_allow_html=True)

# Main router
if not st.session_state.logged_in:
    # show login
    login_screen()
else:
    # show connected status small bar bottom-left (optional)
    try:
        st.sidebar.title("الحالة")
        st.sidebar.write(connection_status)
        if connection_details:
            st.sidebar.write(connection_details)
    except Exception:
        pass

    # route pages
    if st.session_state.page == "teacher_attendance" and st.session_state.user_role == "teacher":
        teacher_attendance_page()
    elif st.session_state.page == "student_dashboard" and st.session_state.user_role in ("student","teacher"):
        # allow teachers to view student dashboard too (they might want to check)
        student_dashboard_page()
    else:
        home_page()

# That's it - نهاية الملف
