"""Authentication views for login and controlled registration."""

from __future__ import annotations

import sqlite3

import streamlit as st

from auth.session import login_user
from database.repositories import UserRepository
from utils.validators import clean_text, validate_email, validate_password_strength

ROLE_OPTIONS = {
    "مدیر بیمارستان": "hospital_manager",
    "مدیر داروخانه": "pharmacy_manager",
    "سازمان درمانی": "healthcare_org",
    "پژوهشگر": "researcher",
    "کاربر مشاهده‌گر": "viewer",
}

ORGANIZATION_OPTIONS = {
    "بیمارستان": "hospital",
    "داروخانه": "pharmacy",
    "شرکت دارویی / پخش": "pharma_company",
    "دانشگاه / مرکز پژوهشی": "university",
    "سازمان دولتی / وزارتخانه": "government",
    "سایر": "other",
}


def render_login_page() -> None:
    """Render secure login form."""

    st.markdown(
        """
        <div class="pg-form-card">
          <span class="pg-badge">ورود امن</span>
          <h2>ورود به فارماگارد هوشمند</h2>
          <p>برای مشاهده داشبورد تخصصی، ایمیل سازمانی و رمز عبور خود را وارد کنید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="pg-auth-container">', unsafe_allow_html=True)
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("ایمیل", placeholder="ایمیل ادمین یا ایمیل سازمانی")
        password = st.text_input("رمز عبور", type="password", placeholder="رمز عبور")
        remember_me = st.checkbox("مرا به خاطر بسپار")
        submitted = st.form_submit_button("ورود", type="primary", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    if submitted:
        _handle_login_submission(email, password, remember_me)

    st.caption("اگر حساب شما تازه ساخته شده است، تا زمان تأیید مدیر سامانه فقط صفحه وضعیت حساب را مشاهده می‌کنید.")


def _handle_login_submission(email: str, password: str, remember_me: bool) -> None:
    """Validate and authenticate the login form submission."""

    if not validate_email(email):
        st.error("ایمیل واردشده معتبر نیست.")
        return

    user = UserRepository.authenticate(email, password)
    if user is None:
        st.error("ایمیل یا رمز عبور اشتباه است یا حساب شما غیرفعال شده است.")
        return

    login_user(user)
    if remember_me:
        st.toast("ورود با موفقیت انجام شد.")
    st.rerun()


def render_register_page() -> None:
    """Render public registration request form."""

    st.markdown(
        """
        <div class="pg-form-card">
          <span class="pg-badge">ثبت درخواست دسترسی</span>
          <h2>ساخت حساب سازمانی کنترل‌شده</h2>
          <p>ثبت‌نام عمومی مستقیماً دسترسی سازمانی نمی‌دهد. درخواست شما برای مدیر سامانه ارسال می‌شود و پس از تأیید، نقش و سازمان فعال خواهد شد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="pg-auth-container">', unsafe_allow_html=True)
    with st.form("register_form", clear_on_submit=False):
        full_name = st.text_input("نام کامل", placeholder="مثلاً: مدیر داروخانه سلامت")
        email = st.text_input("ایمیل کاری", placeholder="name@organization.com")
        col1, col2 = st.columns(2)
        role_label = col1.selectbox("نقش درخواستی", list(ROLE_OPTIONS.keys()))
        organization_label = col2.selectbox("نوع سازمان", list(ORGANIZATION_OPTIONS.keys()))
        organization_name = st.text_input("نام سازمان", placeholder="مثلاً: داروخانه سلامت / بیمارستان مرکزی")
        request_note = st.text_area(
            "توضیح کوتاه درخواست",
            placeholder="مثلاً: برای مدیریت موجودی داروخانه و ورود فایل موجودی نیاز به دسترسی دارم.",
            height=90,
        )
        password = st.text_input("رمز عبور", type="password", placeholder="حداقل ۸ کاراکتر، شامل حرف و عدد")
        password_confirm = st.text_input("تکرار رمز عبور", type="password")
        submitted = st.form_submit_button("ارسال درخواست ثبت‌نام", type="primary", use_container_width=True)

    st.markdown('</div>', unsafe_allow_html=True)

    if submitted:
        _handle_register_submission(
            full_name,
            email,
            role_label,
            organization_label,
            organization_name,
            request_note,
            password,
            password_confirm,
        )


def _handle_register_submission(
    full_name: str,
    email: str,
    role_label: str,
    organization_label: str,
    organization_name: str,
    request_note: str,
    password: str,
    password_confirm: str,
) -> None:
    """Validate and create a pending access request."""

    cleaned_name = clean_text(full_name, 120)
    cleaned_org_name = clean_text(organization_name, 160)
    if len(cleaned_name) < 3:
        st.error("نام کامل باید حداقل ۳ کاراکتر باشد.")
        return
    if not validate_email(email):
        st.error("ایمیل واردشده معتبر نیست.")
        return
    if len(cleaned_org_name) < 2:
        st.error("نام سازمان را وارد کنید تا مدیر سامانه بتواند درخواست را بررسی کند.")
        return

    is_strong, message = validate_password_strength(password)
    if not is_strong:
        st.error(message)
        return
    if password != password_confirm:
        st.error("تکرار رمز عبور با رمز اصلی یکسان نیست.")
        return

    try:
        UserRepository.create_registration_request(
            full_name=cleaned_name,
            email=email,
            password=password,
            requested_role=ROLE_OPTIONS[role_label],
            organization_type=ORGANIZATION_OPTIONS[organization_label],
            organization_name=cleaned_org_name,
            request_note=clean_text(request_note, 300),
        )
    except sqlite3.IntegrityError:
        st.error("این ایمیل قبلاً ثبت شده است.")
        return
    except ValueError as error:
        st.error(str(error))
        return

    st.success("درخواست شما ثبت شد. پس از تأیید مدیر سامانه، دسترسی سازمانی فعال می‌شود.")
    st.session_state.current_page = "login"
    st.info("اکنون می‌توانید وارد شوید؛ تا زمان تأیید، فقط صفحه انتظار تأیید را خواهید دید.")
