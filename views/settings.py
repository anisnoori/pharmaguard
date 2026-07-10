"""Application settings and preferences view."""

from __future__ import annotations

import streamlit as st

from components.ui import section_header
from services.notification_service import NotificationService

THEME_LABELS = {
    "light": "روشن",
    "dark": "تیره",
    "auto": "خودکار",
}


def render_settings_page() -> None:
    """Render user settings and preference forms."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    user_id = int(user["id"])
    preferences = NotificationService.get_preferences(user_id)
    section_header(
        "تنظیمات سامانه",
        "ظاهر برنامه، زبان، رفتار هشدارها و ترجیحات عملیاتی حساب را از این بخش کنترل کنید.",
    )

    tab_theme, tab_notifications, tab_system = st.tabs(["ظاهر و زبان", "هشدارها", "سامانه و داده"])
    with tab_theme:
        _render_theme_settings(user_id, preferences)
    with tab_notifications:
        _render_notification_settings(user_id, preferences)
    with tab_system:
        _render_system_settings()


def _render_theme_settings(user_id: int, preferences) -> None:
    """Render theme and language settings."""

    st.subheader("ظاهر برنامه")
    current_theme_label = THEME_LABELS.get(preferences.theme, "روشن")
    theme_label = st.radio(
        "حالت نمایش",
        options=list(THEME_LABELS.values()),
        index=list(THEME_LABELS.values()).index(current_theme_label),
        horizontal=True,
        key="settings_theme_radio",
    )
    language = st.selectbox("زبان رابط کاربری", options=["فارسی"], index=0, key="settings_language")
    del language
    if st.button("ذخیره ظاهر برنامه", key="settings_save_theme", use_container_width=True):
        theme = _theme_from_label(theme_label)
        NotificationService.update_preferences(user_id, {"theme": theme, "language": "fa"})
        st.session_state.theme = theme
        st.success("تنظیمات ظاهر ذخیره شد و در همه صفحات اعمال می‌شود.")
        st.rerun()
    st.info("پس از ذخیره، ظاهر برنامه روی همه صفحات اعمال می‌شود. حالت خودکار بر اساس تنظیمات سیستم‌عامل انتخاب می‌شود.")


def _render_notification_settings(user_id: int, preferences) -> None:
    """Render notification preferences."""

    st.subheader("ترجیحات هشدارها")
    with st.form("settings_notification_form", clear_on_submit=False):
        notifications_enabled = st.checkbox("فعال بودن مرکز هشدارها", value=preferences.notifications_enabled)
        low_stock_alerts = st.checkbox("هشدار کمبود موجودی", value=preferences.low_stock_alerts)
        expiration_alerts = st.checkbox("هشدار انقضا", value=preferences.expiration_alerts)
        prediction_alerts = st.checkbox("هشدار ریسک پیش‌بینی AI", value=preferences.prediction_alerts)
        interaction_alerts = st.checkbox("هشدار تداخل دارویی", value=preferences.interaction_alerts)
        email_digest_enabled = st.checkbox("خلاصه ایمیلی آینده", value=preferences.email_digest_enabled)
        submitted = st.form_submit_button("ذخیره تنظیمات هشدار", use_container_width=True)
    if submitted:
        NotificationService.update_preferences(
            user_id,
            {
                "notifications_enabled": notifications_enabled,
                "low_stock_alerts": low_stock_alerts,
                "expiration_alerts": expiration_alerts,
                "prediction_alerts": prediction_alerts,
                "interaction_alerts": interaction_alerts,
                "email_digest_enabled": email_digest_enabled,
            },
        )
        st.success("تنظیمات هشدار ذخیره شد.")
        st.rerun()


def _render_system_settings() -> None:
    """Render system-level information and data retention guidance."""

    st.subheader("داده‌های محلی و پشتیبان‌گیری")
    st.markdown(
        """
        دیتابیس عملیاتی SQLite داخل مسیر زیر نگهداری می‌شود:

        `database/pharmaguard.db`

        برای حفظ داده‌ها هنگام رفتن به نسخه جدید، این فایل و پوشه‌های `uploads`، `reports` و `logs` را به نسخه جدید کپی کنید.
        """
    )
    st.warning("قبل از جذب کاربر واقعی، از فایل دیتابیس و پوشه‌های uploads، reports و logs نسخه پشتیبان منظم بگیرید.")


def _theme_from_label(label: str) -> str:
    """Map Persian theme label to stored value."""

    for key, value in THEME_LABELS.items():
        if value == label:
            return key
    return "light"
