"""Profile and account-security view."""

from __future__ import annotations

import streamlit as st

from components.ui import section_header
from services.profile_service import ProfileService
from utils.persian import fa_number


def render_profile_page() -> None:
    """Render current user's profile and security controls."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    user_id = int(user["id"])
    profile = ProfileService.get_profile(user_id)
    if profile is None:
        st.error("پروفایل کاربر پیدا نشد.")
        return

    section_header(
        "پروفایل کاربری",
        "اطلاعات هویتی، نقش سازمانی، امنیت حساب و وضعیت نشست کاربر در این بخش مدیریت می‌شود.",
    )
    _render_profile_summary(profile)
    tab_identity, tab_security = st.tabs(["اطلاعات حساب", "امنیت و رمز عبور"])
    with tab_identity:
        _render_identity_form(profile)
    with tab_security:
        _render_password_form(user_id)


def _render_profile_summary(profile) -> None:
    """Render profile overview metrics."""

    organization = profile.hospital_name or profile.pharmacy_name or "بدون سازمان متصل"
    col1, col2, col3 = st.columns(3)
    col1.metric("نقش", profile.role_name)
    col2.metric("سازمان", organization)
    col3.metric("شناسه کاربر", fa_number(profile.id))
    st.caption(f"آخرین ورود: {profile.last_login_at or 'ثبت نشده'}")


def _render_identity_form(profile) -> None:
    """Render full name and email update form."""

    st.subheader("ویرایش اطلاعات پایه")
    with st.form("profile_identity_form", clear_on_submit=False):
        full_name = st.text_input("نام کامل", value=profile.full_name)
        email = st.text_input("ایمیل", value=profile.email)
        submitted = st.form_submit_button("ذخیره تغییرات", use_container_width=True)
    if submitted:
        try:
            ProfileService.update_identity(profile.id, full_name, email)
            if st.session_state.get("user"):
                st.session_state.user["full_name"] = full_name.strip()
                st.session_state.user["email"] = email.strip().lower()
            st.success("اطلاعات حساب با موفقیت به‌روزرسانی شد.")
            st.rerun()
        except ValueError as error:
            st.error(str(error))


def _render_password_form(user_id: int) -> None:
    """Render password-change form."""

    st.subheader("تغییر رمز عبور")
    st.caption("برای امنیت حساب، رمز فعلی باید تأیید شود و رمز جدید حداقل ۸ کاراکتر داشته باشد.")
    with st.form("profile_password_form", clear_on_submit=True):
        current_password = st.text_input("رمز عبور فعلی", type="password")
        new_password = st.text_input("رمز عبور جدید", type="password")
        confirm_password = st.text_input("تکرار رمز عبور جدید", type="password")
        submitted = st.form_submit_button("تغییر رمز عبور", use_container_width=True)
    if submitted:
        if new_password != confirm_password:
            st.error("رمز جدید و تکرار آن یکسان نیستند.")
            return
        try:
            ProfileService.change_password(user_id, current_password, new_password)
            st.success("رمز عبور با موفقیت تغییر کرد.")
        except ValueError as error:
            st.error(str(error))
