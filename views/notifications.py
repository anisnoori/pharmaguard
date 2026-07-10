"""Notification center view."""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from components.ui import section_header
from services.notification_service import NotificationService
from utils.persian import fa_number

SEVERITY_LABELS = {
    "all": "همه",
    "critical": "بحرانی",
    "warning": "هشدار",
    "info": "اطلاع‌رسانی",
    "success": "موفق",
}

SEVERITY_CLASS = {
    "critical": "pg-notification-critical",
    "warning": "pg-notification-warning",
    "info": "pg-notification-info",
    "success": "pg-notification-success",
}


def render_notifications_page() -> None:
    """Render user notification center."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    user_id = int(user["id"])
    section_header(
        "مرکز هشدارها",
        "هشدارهای قابل اقدام درباره کمبود موجودی، انقضا، ریسک پیش‌بینی و پیام‌های سامانه را در یک محل مدیریت کنید.",
    )
    _render_notification_actions(user_id)
    _render_notification_filters(user_id)


def _render_notification_actions(user_id: int) -> None:
    """Render action buttons and unread metrics."""

    unread = NotificationService.unread_count(user_id)
    col1, col2, col3, col4 = st.columns([1, 1, 1, 2])
    with col1:
        st.metric("خوانده‌نشده", fa_number(unread))
    with col2:
        if st.button("تولید هشدارهای عملیاتی", key="notifications_generate", use_container_width=True):
            summary = NotificationService.generate_operational_alerts(user_id)
            st.success(
                f"{fa_number(summary.created_count)} هشدار جدید ایجاد شد؛ "
                f"{fa_number(summary.skipped_duplicate_count)} هشدار تکراری رد شد."
            )
            st.rerun()
    with col3:
        if st.button("علامت‌گذاری همه به عنوان خوانده‌شده", key="notifications_mark_all", use_container_width=True):
            NotificationService.mark_all_read(user_id)
            st.success("همه هشدارها خوانده‌شده شدند.")
            st.rerun()
    with col4:
        st.info("برای جلوگیری از شلوغی، تولید هشدارها با دکمه انجام می‌شود و در هر اجرای صفحه تکرار نمی‌شود.")


def _render_notification_filters(user_id: int) -> None:
    """Render notification list with filters."""

    col1, col2 = st.columns(2)
    with col1:
        include_read = st.checkbox("نمایش هشدارهای خوانده‌شده", value=True, key="notifications_include_read")
    with col2:
        severity_label = st.selectbox(
            "سطح هشدار",
            options=list(SEVERITY_LABELS.values()),
            index=0,
            key="notifications_severity_filter",
        )
    severity = _severity_from_label(severity_label)
    notifications = NotificationService.inbox(user_id, include_read=include_read, severity=severity)

    if not notifications:
        st.empty().info("در حال حاضر هشداری برای نمایش وجود ندارد.")
        return

    dataframe = pd.DataFrame(
        [
            {
                "عنوان": item.title,
                "سطح": SEVERITY_LABELS.get(item.severity, item.severity),
                "نوع": item.notification_type,
                "وضعیت": "خوانده‌شده" if item.is_read else "جدید",
                "زمان": item.created_at,
            }
            for item in notifications
        ]
    )
    st.dataframe(dataframe, hide_index=True, use_container_width=True)

    st.subheader("جزئیات هشدارها")
    for item in notifications:
        _render_notification_item(user_id, item)


def _render_notification_item(user_id: int, item) -> None:
    """Render one notification card."""

    status = "خوانده‌شده" if item.is_read else "جدید"
    css_class = SEVERITY_CLASS.get(item.severity, "pg-notification-info")
    st.markdown(
        (
            f'<article class="pg-notification-card {css_class}">'
            f'<div><span class="pg-badge">{html.escape(SEVERITY_LABELS.get(item.severity, item.severity))}</span>'
            f'<span class="pg-notification-status">{status}</span></div>'
            f'<h3>{html.escape(item.title)}</h3>'
            f'<p>{html.escape(item.message)}</p>'
            f'<small>{html.escape(item.created_at)}</small>'
            '</article>'
        ),
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        if not item.is_read and st.button("خواندم", key=f"notification_read_{item.id}", use_container_width=True):
            NotificationService.mark_read(item.id, user_id)
            st.rerun()
    with col2:
        if st.button("حذف/پنهان‌سازی", key=f"notification_delete_{item.id}", use_container_width=True):
            NotificationService.delete(item.id, user_id)
            st.rerun()
    with col3:
        if item.action_page and st.button("رفتن به بخش مرتبط", key=f"notification_action_{item.id}", use_container_width=True):
            st.session_state.current_page = item.action_page
            st.rerun()


def _severity_from_label(label: str) -> str:
    """Map Persian severity label back to stored code."""

    for key, value in SEVERITY_LABELS.items():
        if value == label:
            return key
    return "all"
