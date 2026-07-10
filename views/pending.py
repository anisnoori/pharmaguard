"""Pending approval page for controlled public registration."""

from __future__ import annotations

import streamlit as st

from config import ROLE_LABELS

ORG_LABELS = {
    "hospital": "بیمارستان",
    "pharmacy": "داروخانه",
    "pharma_company": "شرکت دارویی / پخش",
    "university": "دانشگاه / مرکز پژوهشی",
    "government": "سازمان دولتی / وزارتخانه",
    "other": "سایر",
    "platform": "سامانه",
}

STATUS_LABELS = {
    "pending": "در انتظار تأیید مدیر سامانه",
    "rejected": "رد شده",
    "suspended": "تعلیق شده",
    "disabled": "غیرفعال",
}


def render_pending_approval_page() -> None:
    """Render a safe holding page for unapproved users."""

    user = st.session_state.get("user") or {}
    status = str(user.get("approval_status", "pending"))
    requested_role = str(user.get("requested_role", "viewer"))
    org_type = str(user.get("requested_organization_type", ""))
    org_name = str(user.get("requested_organization_name", ""))

    st.markdown(
        f"""
        <section class="pg-module-hero pg-access-state">
          <span class="pg-badge">کنترل دسترسی سازمانی</span>
          <h1>{STATUS_LABELS.get(status, 'در انتظار بررسی')}</h1>
          <p>
            حساب شما ساخته شده، اما هنوز برای دسترسی به داده‌های دارویی، موجودی، گزارش‌ها و داشبورد سازمانی تأیید نشده است.
            این کنترل برای حفاظت از داده‌های حساس بیمارستان‌ها و داروخانه‌ها انجام می‌شود.
          </p>
          <div class="pg-module-meta">
            <span>نقش درخواستی: {ROLE_LABELS.get(requested_role, requested_role or 'ثبت نشده')}</span>
            <span>نوع سازمان: {ORG_LABELS.get(org_type, org_type or 'ثبت نشده')}</span>
            <span>نام سازمان: {org_name or 'ثبت نشده'}</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if status == "pending":
        st.info("درخواست شما در پنل مدیر سامانه نمایش داده می‌شود. پس از تأیید، داشبورد اختصاصی شما فعال خواهد شد.")
    elif status == "rejected":
        st.error("درخواست شما رد شده است. برای اصلاح اطلاعات، با مدیر سامانه تماس بگیرید.")
    elif status == "suspended":
        st.warning("حساب شما موقتاً تعلیق شده است و دسترسی سازمانی ندارد.")
    else:
        st.warning("وضعیت حساب شما اجازه دسترسی به بخش‌های سامانه را نمی‌دهد.")
