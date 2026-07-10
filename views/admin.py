"""Administrator control panel for users, organizations, permissions, and audit."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import DB_PATH
from services.admin_service import (
    AdminAccessError,
    AdminService,
    HOSPITAL_TYPE_LABEL_BY_CODE,
    HOSPITAL_TYPE_OPTIONS,
    PHARMACY_SERVICE_LABEL_BY_CODE,
    PHARMACY_SERVICE_OPTIONS,
    ROLE_LABEL_BY_CODE,
    ROLE_OPTIONS,
    STATUS_LABEL_BY_CODE,
    STATUS_OPTIONS,
)
from utils.persian import fa_number


ALL_FILTER_LABEL = "همه"
ALL_FILTER_VALUE = "all"


def render_admin_panel_page() -> None:
    """Render the enterprise admin panel for platform administrators."""

    user = st.session_state.get("user")
    try:
        AdminService.assert_admin(user)
    except AdminAccessError as error:
        st.error(str(error))
        st.info("برای دسترسی به مدیریت سامانه باید با حساب مدیر سامانه وارد شوید.")
        return

    st.markdown(
        """
        <section class="pg-dashboard-header">
          <span class="pg-badge">مرکز کنترل مدیریتی</span>
          <h1>مدیریت سامانه فارماگارد</h1>
          <p>کنترل کاربران، سازمان‌ها، نقش‌ها، دسترسی‌ها، لاگ‌ها و سلامت عملیاتی سامانه از این بخش انجام می‌شود.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    _render_overview_cards()

    tabs = st.tabs([
        "درخواست‌های ثبت‌نام",
        "کاربران",
        "بیمارستان‌ها",
        "داروخانه‌ها",
        "نقش‌ها و دسترسی‌ها",
        "لاگ فعالیت",
        "سلامت سامانه",
    ])
    with tabs[0]:
        _render_registration_requests_tab(int(user["id"]))
    with tabs[1]:
        _render_users_tab(int(user["id"]))
    with tabs[2]:
        _render_hospitals_tab(int(user["id"]))
    with tabs[3]:
        _render_pharmacies_tab(int(user["id"]))
    with tabs[4]:
        _render_roles_tab()
    with tabs[5]:
        _render_activity_tab()
    with tabs[6]:
        _render_system_health_tab()


def _render_overview_cards() -> None:
    """Render admin KPIs."""

    overview = AdminService.overview()
    columns = st.columns(4)
    columns[0].metric("کاربران فعال", fa_number(overview["active_users"]))
    columns[1].metric("بیمارستان‌ها", fa_number(overview["hospitals"]))
    columns[2].metric("داروخانه‌ها", fa_number(overview["pharmacies"]))
    columns[3].metric("درخواست‌های باز", fa_number(overview.get("pending_users", 0)))

    columns = st.columns(4)
    columns[0].metric("کل کاربران", fa_number(overview["users"]))
    columns[1].metric("داروهای ثبت‌شده", fa_number(overview["drugs"]))
    columns[2].metric("پیش‌بینی‌های AI", fa_number(overview["predictions"]))
    columns[3].metric("لاگ‌های حسابرسی", fa_number(overview["logs"]))


def _render_registration_requests_tab(admin_user_id: int) -> None:
    """Render pending self-registration approval workflow."""

    st.subheader("درخواست‌های ثبت‌نام عمومی")
    st.caption("کاربران جدید تا زمان تأیید مدیر سامانه به داشبورد، ورود داده، گزارش‌ها و موجودی سازمانی دسترسی ندارند.")
    requests = AdminService.pending_requests()
    if not requests:
        st.success("در حال حاضر درخواست ثبت‌نام باز وجود ندارد.")
        return

    frame = pd.DataFrame([
        {
            "شناسه": row["id"],
            "نام": row["full_name"],
            "ایمیل": row["email"],
            "نقش درخواستی": ROLE_LABEL_BY_CODE.get(str(row.get("requested_role", "")), str(row.get("requested_role", ""))),
            "نوع سازمان": row.get("requested_organization_type", "") or "—",
            "نام سازمان": row.get("requested_organization_name", "") or "—",
            "توضیح": row.get("approval_notes", "") or "—",
            "تاریخ": row.get("created_at", ""),
        }
        for row in requests
    ])
    st.dataframe(frame, use_container_width=True, hide_index=True)

    organizations = AdminService.organization_options()
    options = {f"{row['full_name']} — {row['email']}": row for row in requests}
    selected_label = st.selectbox("انتخاب درخواست برای بررسی", list(options.keys()), key="admin_request_select")
    selected = options[selected_label]
    default_role = ROLE_LABEL_BY_CODE.get(str(selected.get("requested_role") or "viewer"), "کاربر مشاهده‌گر")

    with st.form("admin_review_registration_form"):
        decision_label = st.radio(
            "تصمیم",
            ["تأیید", "رد", "تعلیق"],
            horizontal=True,
            key="admin_request_decision",
        )
        role_label = st.selectbox(
            "نقش نهایی در صورت تأیید",
            list(ROLE_OPTIONS.keys()),
            index=list(ROLE_OPTIONS.keys()).index(default_role) if default_role in ROLE_OPTIONS else 0,
            key="admin_request_final_role",
        )
        hospital_id = _select_organization("اتصال به بیمارستان", organizations["hospitals"], "admin_request_hospital")
        pharmacy_id = _select_organization("اتصال به داروخانه", organizations["pharmacies"], "admin_request_pharmacy")
        notes = st.text_area("یادداشت بررسی", value="", key="admin_request_notes")
        submitted = st.form_submit_button("ثبت تصمیم", type="primary", use_container_width=True)
    if not submitted:
        return
    decision_map = {"تأیید": "approved", "رد": "rejected", "تعلیق": "suspended"}
    try:
        AdminService.review_registration_request(
            admin_user_id=admin_user_id,
            user_id=int(selected["id"]),
            decision=decision_map[decision_label],
            final_role_code=ROLE_OPTIONS[role_label],
            hospital_id=hospital_id,
            pharmacy_id=pharmacy_id,
            notes=notes,
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.success("تصمیم مدیر سامانه ثبت شد.")
    st.rerun()


def _render_users_tab(admin_user_id: int) -> None:
    """Render user management workflows."""

    st.subheader("مدیریت کاربران و سطح دسترسی")
    st.caption("هر کاربر باید نقش، وضعیت و دامنه سازمانی مشخص داشته باشد تا داشبوردهای شخصی‌سازی‌شده درست کار کنند.")

    filter_col1, filter_col2, filter_col3 = st.columns(3)
    search = filter_col1.text_input("جستجوی کاربر", placeholder="نام یا ایمیل", key="admin_user_search")
    role_filter_label = filter_col2.selectbox(
        "فیلتر نقش",
        [ALL_FILTER_LABEL, *ROLE_OPTIONS.keys()],
        key="admin_user_role_filter",
    )
    status_filter_label = filter_col3.selectbox(
        "فیلتر وضعیت",
        [ALL_FILTER_LABEL, "فعال", "غیرفعال", "در انتظار تأیید", "تأیید شده", "رد شده", "تعلیق شده"],
        key="admin_user_status_filter",
    )
    role_filter = ROLE_OPTIONS.get(role_filter_label, ALL_FILTER_VALUE)
    status_filter = STATUS_OPTIONS.get(status_filter_label, ALL_FILTER_VALUE)
    users = AdminService.users(search, role_filter, status_filter)
    _render_users_table(users)

    with st.expander("ساخت کاربر جدید", expanded=False):
        _render_create_user_form(admin_user_id)

    with st.expander("ویرایش نقش، وضعیت و سازمان کاربر", expanded=False):
        _render_update_user_form(admin_user_id, users)

    with st.expander("بازنشانی رمز عبور کاربر", expanded=False):
        _render_reset_password_form(admin_user_id, users)


def _render_users_table(users: list[dict[str, object]]) -> None:
    """Display admin user rows."""

    if not users:
        st.info("کاربری با فیلترهای فعلی پیدا نشد.")
        return
    frame = pd.DataFrame(
        [
            {
                "شناسه": row["id"],
                "نام": row["full_name"],
                "ایمیل": row["email"],
                "نقش": row["role_name"],
                "بیمارستان": row["hospital_name"] or "—",
                "داروخانه": row["pharmacy_name"] or "—",
                "وضعیت": STATUS_LABEL_BY_CODE.get(str(row.get("approval_status", "approved")), "فعال" if int(row["is_active"]) else "غیرفعال"),
                "درخواست": ROLE_LABEL_BY_CODE.get(str(row.get("requested_role", "")), str(row.get("requested_role", "")) or "—"),
                "آخرین ورود": row["last_login_at"] or "ثبت نشده",
            }
            for row in users
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_create_user_form(admin_user_id: int) -> None:
    """Render user creation form."""

    organizations = AdminService.organization_options()
    with st.form("admin_create_user_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        full_name = col1.text_input("نام کامل", key="admin_create_user_name")
        email = col2.text_input("ایمیل", key="admin_create_user_email")
        role_label = col1.selectbox("نقش", list(ROLE_OPTIONS.keys()), key="admin_create_user_role")
        password = col2.text_input("رمز عبور اولیه", type="password", key="admin_create_user_password")
        hospital_id = _select_organization("بیمارستان مرتبط", organizations["hospitals"], "admin_create_user_hospital")
        pharmacy_id = _select_organization("داروخانه مرتبط", organizations["pharmacies"], "admin_create_user_pharmacy")
        is_active = st.checkbox("حساب فعال باشد", value=True, key="admin_create_user_active")
        submitted = st.form_submit_button("ساخت کاربر", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.create_user(
            admin_user_id=admin_user_id,
            full_name=full_name,
            email=email,
            password=password,
            role_code=ROLE_OPTIONS[role_label],
            hospital_id=hospital_id,
            pharmacy_id=pharmacy_id,
            is_active=is_active,
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.success("کاربر جدید با موفقیت ساخته شد.")
    st.rerun()


def _render_update_user_form(admin_user_id: int, users: list[dict[str, object]]) -> None:
    """Render user scope update form."""

    if not users:
        st.info("برای ویرایش، ابتدا حداقل یک کاربر باید در فهرست وجود داشته باشد.")
        return
    organizations = AdminService.organization_options()
    user_options = {f"{row['full_name']} — {row['email']}": row for row in users}
    selected_label = st.selectbox("انتخاب کاربر", list(user_options.keys()), key="admin_update_user_select")
    selected = user_options[selected_label]
    role_label = ROLE_LABEL_BY_CODE.get(str(selected["role_code"]), "کاربر مشاهده‌گر")
    with st.form("admin_update_user_form"):
        role = st.selectbox(
            "نقش جدید",
            list(ROLE_OPTIONS.keys()),
            index=list(ROLE_OPTIONS.keys()).index(role_label),
            key="admin_update_user_role",
        )
        hospital_id = _select_organization(
            "بیمارستان مرتبط",
            organizations["hospitals"],
            "admin_update_user_hospital",
            int(selected["hospital_id"]) if selected["hospital_id"] else None,
        )
        pharmacy_id = _select_organization(
            "داروخانه مرتبط",
            organizations["pharmacies"],
            "admin_update_user_pharmacy",
            int(selected["pharmacy_id"]) if selected["pharmacy_id"] else None,
        )
        is_active = st.checkbox(
            "حساب فعال باشد",
            value=bool(selected["is_active"]),
            key="admin_update_user_active",
        )
        submitted = st.form_submit_button("ذخیره تغییرات کاربر", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.update_user_scope(
            admin_user_id=admin_user_id,
            user_id=int(selected["id"]),
            role_code=ROLE_OPTIONS[role],
            hospital_id=hospital_id,
            pharmacy_id=pharmacy_id,
            is_active=is_active,
        )
    except ValueError as error:
        st.error(str(error))
        return
    st.success("تنظیمات کاربر ذخیره شد.")
    st.rerun()


def _render_reset_password_form(admin_user_id: int, users: list[dict[str, object]]) -> None:
    """Render password reset form."""

    if not users:
        st.info("کاربری برای بازنشانی رمز عبور وجود ندارد.")
        return
    user_options = {f"{row['full_name']} — {row['email']}": row for row in users}
    with st.form("admin_reset_password_form"):
        selected_label = st.selectbox("انتخاب کاربر", list(user_options.keys()), key="admin_reset_user_select")
        new_password = st.text_input("رمز عبور جدید", type="password", key="admin_reset_user_password")
        submitted = st.form_submit_button("بازنشانی رمز عبور", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.reset_password(admin_user_id, int(user_options[selected_label]["id"]), new_password)
    except ValueError as error:
        st.error(str(error))
        return
    st.success("رمز عبور کاربر بازنشانی شد.")


def _render_hospitals_tab(admin_user_id: int) -> None:
    """Render hospital management workflows."""

    st.subheader("مدیریت بیمارستان‌ها")
    filter_col1, filter_col2 = st.columns(2)
    search = filter_col1.text_input("جستجوی بیمارستان", key="admin_hospital_search")
    status_label = filter_col2.selectbox("فیلتر وضعیت", [ALL_FILTER_LABEL, *STATUS_OPTIONS.keys()], key="admin_hospital_status_filter")
    hospitals = AdminService.hospitals(search, STATUS_OPTIONS.get(status_label, ALL_FILTER_VALUE))
    _render_hospital_table(hospitals)

    with st.expander("ثبت بیمارستان جدید", expanded=False):
        _render_hospital_form(admin_user_id)
    with st.expander("ویرایش بیمارستان", expanded=False):
        _render_hospital_edit_form(admin_user_id, hospitals)


def _render_hospital_table(hospitals: list[dict[str, object]]) -> None:
    """Display hospital rows."""

    if not hospitals:
        st.info("بیمارستانی با فیلترهای فعلی پیدا نشد.")
        return
    frame = pd.DataFrame(
        [
            {
                "شناسه": row["id"],
                "نام": row["name"],
                "کد": row["code"] or "—",
                "شهر": row["city"] or "—",
                "نوع": HOSPITAL_TYPE_LABEL_BY_CODE.get(str(row["type"]), str(row["type"])),
                "تخت": row["bed_count"],
                "مدیر": row["manager_name"] or "—",
                "کاربران": row["user_count"],
                "وضعیت": STATUS_LABEL_BY_CODE.get(str(row["status"]), str(row["status"])),
            }
            for row in hospitals
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_hospital_form(admin_user_id: int) -> None:
    """Render hospital create form."""

    with st.form("admin_create_hospital_form", clear_on_submit=True):
        payload = _hospital_form_fields("create")
        submitted = st.form_submit_button("ثبت بیمارستان", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.save_hospital(admin_user_id, payload)
    except ValueError as error:
        st.error(str(error))
        return
    st.success("بیمارستان با موفقیت ثبت شد.")
    st.rerun()


def _render_hospital_edit_form(admin_user_id: int, hospitals: list[dict[str, object]]) -> None:
    """Render hospital update form."""

    if not hospitals:
        st.info("برای ویرایش، ابتدا بیمارستانی در فهرست وجود داشته باشد.")
        return
    options = {f"{row['name']} — {row['city']}": row for row in hospitals}
    selected_label = st.selectbox("انتخاب بیمارستان", list(options.keys()), key="admin_edit_hospital_select")
    selected = options[selected_label]
    with st.form("admin_edit_hospital_form"):
        payload = _hospital_form_fields("edit", selected)
        submitted = st.form_submit_button("ذخیره بیمارستان", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.save_hospital(admin_user_id, payload, int(selected["id"]))
    except ValueError as error:
        st.error(str(error))
        return
    st.success("اطلاعات بیمارستان به‌روزرسانی شد.")
    st.rerun()


def _render_pharmacies_tab(admin_user_id: int) -> None:
    """Render pharmacy management workflows."""

    st.subheader("مدیریت داروخانه‌ها")
    filter_col1, filter_col2 = st.columns(2)
    search = filter_col1.text_input("جستجوی داروخانه", key="admin_pharmacy_search")
    status_label = filter_col2.selectbox("فیلتر وضعیت", [ALL_FILTER_LABEL, *STATUS_OPTIONS.keys()], key="admin_pharmacy_status_filter")
    pharmacies = AdminService.pharmacies(search, STATUS_OPTIONS.get(status_label, ALL_FILTER_VALUE))
    _render_pharmacy_table(pharmacies)

    with st.expander("ثبت داروخانه جدید", expanded=False):
        _render_pharmacy_form(admin_user_id)
    with st.expander("ویرایش داروخانه", expanded=False):
        _render_pharmacy_edit_form(admin_user_id, pharmacies)


def _render_pharmacy_table(pharmacies: list[dict[str, object]]) -> None:
    """Display pharmacy rows."""

    if not pharmacies:
        st.info("داروخانه‌ای با فیلترهای فعلی پیدا نشد.")
        return
    frame = pd.DataFrame(
        [
            {
                "شناسه": row["id"],
                "نام": row["name"],
                "استان": row.get("province") or "—",
                "شهر": row["city"] or "—",
                "مجوز": row["license_number"] or "—",
                "مسئول": row["owner_name"] or "—",
                "سطح خدمت": PHARMACY_SERVICE_LABEL_BY_CODE.get(str(row["service_level"]), str(row["service_level"])),
                "کاربران": row["user_count"],
                "وضعیت": STATUS_LABEL_BY_CODE.get(str(row["status"]), str(row["status"])),
            }
            for row in pharmacies
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_pharmacy_form(admin_user_id: int) -> None:
    """Render pharmacy create form."""

    with st.form("admin_create_pharmacy_form", clear_on_submit=True):
        payload = _pharmacy_form_fields("create")
        submitted = st.form_submit_button("ثبت داروخانه", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.save_pharmacy(admin_user_id, payload)
    except ValueError as error:
        st.error(str(error))
        return
    st.success("داروخانه با موفقیت ثبت شد.")
    st.rerun()


def _render_pharmacy_edit_form(admin_user_id: int, pharmacies: list[dict[str, object]]) -> None:
    """Render pharmacy update form."""

    if not pharmacies:
        st.info("برای ویرایش، ابتدا داروخانه‌ای در فهرست وجود داشته باشد.")
        return
    options = {f"{row['name']} — {row['city']}": row for row in pharmacies}
    selected_label = st.selectbox("انتخاب داروخانه", list(options.keys()), key="admin_edit_pharmacy_select")
    selected = options[selected_label]
    with st.form("admin_edit_pharmacy_form"):
        payload = _pharmacy_form_fields("edit", selected)
        submitted = st.form_submit_button("ذخیره داروخانه", type="primary", use_container_width=True)
    if not submitted:
        return
    try:
        AdminService.save_pharmacy(admin_user_id, payload, int(selected["id"]))
    except ValueError as error:
        st.error(str(error))
        return
    st.success("اطلاعات داروخانه به‌روزرسانی شد.")
    st.rerun()


def _render_roles_tab() -> None:
    """Render roles, permissions, and the permission matrix."""

    st.subheader("نقش‌ها و دسترسی‌ها")
    st.caption("در این نسخه، ماتریس دسترسی‌ها به‌صورت کنترل‌شده و ایمن از Seed سامانه مدیریت می‌شود تا کاربران عادی به آمار یا کنترل‌های غیرمرتبط دسترسی نداشته باشند.")
    roles = AdminService.roles()
    permissions = AdminService.permissions()
    role_permissions = AdminService.role_permissions()
    st.dataframe(pd.DataFrame(_localize_roles(roles)), use_container_width=True, hide_index=True)
    st.markdown("#### فهرست مجوزها")
    st.dataframe(pd.DataFrame(_localize_permissions(permissions)), use_container_width=True, hide_index=True)
    st.markdown("#### ماتریس نقش به مجوز")
    st.dataframe(pd.DataFrame(_localize_role_permissions(role_permissions)), use_container_width=True, hide_index=True)


def _render_activity_tab() -> None:
    """Render recent activity logs."""

    st.subheader("لاگ فعالیت و حسابرسی")
    limit = st.slider("تعداد رکورد", min_value=20, max_value=200, value=80, step=20, key="admin_activity_limit")
    rows = AdminService.activity(limit)
    if not rows:
        st.info("هنوز لاگ فعالیتی ثبت نشده است.")
        return
    frame = pd.DataFrame(
        [
            {
                "زمان": row["created_at"],
                "کاربر": row["actor_name"],
                "ایمیل": row["actor_email"] or "—",
                "عملیات": row["action"],
                "موجودیت": row["entity_type"] or "—",
                "شناسه موجودیت": row["entity_id"] or "—",
                "جزئیات": row["details"] or "—",
            }
            for row in rows
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_system_health_tab() -> None:
    """Render lightweight local system health checks."""

    st.subheader("سلامت سامانه")
    overview = AdminService.overview()
    db_exists = DB_PATH.exists()
    db_size_kb = DB_PATH.stat().st_size / 1024 if db_exists else 0
    col1, col2, col3 = st.columns(3)
    col1.metric("وضعیت دیتابیس", "فعال" if db_exists else "یافت نشد")
    col2.metric("حجم دیتابیس", f"{db_size_kb:.1f} KB")
    col3.metric("رکوردهای عملیاتی", fa_number(sum(overview.values())))
    st.info("این بخش وضعیت فایل دیتابیس، حجم داده‌ها و شمار رکوردهای عملیاتی را برای کنترل سلامت سامانه نشان می‌دهد.")


def _hospital_form_fields(prefix: str, current: dict[str, object] | None = None) -> dict[str, object]:
    """Return hospital form payload from current Streamlit fields."""

    current = current or {}
    col1, col2 = st.columns(2)
    name = col1.text_input("نام بیمارستان", value=str(current.get("name", "")), key=f"admin_{prefix}_hospital_name")
    code = col2.text_input("کد سازمانی", value=str(current.get("code", "")), key=f"admin_{prefix}_hospital_code")
    province = col1.text_input("استان", value=str(current.get("province", "")), key=f"admin_{prefix}_hospital_province")
    city = col2.text_input("شهر", value=str(current.get("city", "")), key=f"admin_{prefix}_hospital_city")
    type_code = str(current.get("type", "general"))
    type_label = HOSPITAL_TYPE_LABEL_BY_CODE.get(type_code, "عمومی")
    type_selected = col1.selectbox(
        "نوع بیمارستان",
        list(HOSPITAL_TYPE_OPTIONS.keys()),
        index=list(HOSPITAL_TYPE_OPTIONS.keys()).index(type_label),
        key=f"admin_{prefix}_hospital_type",
    )
    bed_count = col2.number_input(
        "تعداد تخت",
        min_value=0,
        value=int(current.get("bed_count", 0) or 0),
        step=1,
        key=f"admin_{prefix}_hospital_beds",
    )
    manager_name = col1.text_input("نام مدیر", value=str(current.get("manager_name", "")), key=f"admin_{prefix}_hospital_manager")
    contact_phone = col2.text_input("شماره تماس", value=str(current.get("contact_phone", "")), key=f"admin_{prefix}_hospital_phone")
    address = st.text_area("آدرس", value=str(current.get("address", "")), key=f"admin_{prefix}_hospital_address")
    status_code = str(current.get("status", "active"))
    status_label = STATUS_LABEL_BY_CODE.get(status_code, "فعال")
    status = st.selectbox(
        "وضعیت",
        list(STATUS_OPTIONS.keys()),
        index=list(STATUS_OPTIONS.keys()).index(status_label),
        key=f"admin_{prefix}_hospital_status",
    )
    return {
        "name": name,
        "code": code,
        "province": province,
        "city": city,
        "type": HOSPITAL_TYPE_OPTIONS[type_selected],
        "bed_count": bed_count,
        "manager_name": manager_name,
        "contact_phone": contact_phone,
        "address": address,
        "status": STATUS_OPTIONS[status],
    }


def _pharmacy_form_fields(prefix: str, current: dict[str, object] | None = None) -> dict[str, object]:
    """Return pharmacy form payload from current Streamlit fields."""

    current = current or {}
    col1, col2 = st.columns(2)
    name = col1.text_input("نام داروخانه", value=str(current.get("name", "")), key=f"admin_{prefix}_pharmacy_name")
    province = col2.text_input("استان", value=str(current.get("province", "")), key=f"admin_{prefix}_pharmacy_province")
    city = col1.text_input("شهر", value=str(current.get("city", "")), key=f"admin_{prefix}_pharmacy_city")
    license_number = col2.text_input("شماره مجوز", value=str(current.get("license_number", "")), key=f"admin_{prefix}_pharmacy_license")
    owner_name = col1.text_input("مسئول فنی / مالک", value=str(current.get("owner_name", "")), key=f"admin_{prefix}_pharmacy_owner")
    contact_phone = col2.text_input("شماره تماس", value=str(current.get("contact_phone", "")), key=f"admin_{prefix}_pharmacy_phone")
    service_code = str(current.get("service_level", "retail"))
    service_label = PHARMACY_SERVICE_LABEL_BY_CODE.get(service_code, "خرده‌فروشی")
    service_level = col2.selectbox(
        "سطح خدمت",
        list(PHARMACY_SERVICE_OPTIONS.keys()),
        index=list(PHARMACY_SERVICE_OPTIONS.keys()).index(service_label),
        key=f"admin_{prefix}_pharmacy_service",
    )
    address = st.text_area("آدرس", value=str(current.get("address", "")), key=f"admin_{prefix}_pharmacy_address")
    status_code = str(current.get("status", "active"))
    status_label = STATUS_LABEL_BY_CODE.get(status_code, "فعال")
    status = st.selectbox(
        "وضعیت",
        list(STATUS_OPTIONS.keys()),
        index=list(STATUS_OPTIONS.keys()).index(status_label),
        key=f"admin_{prefix}_pharmacy_status",
    )
    return {
        "name": name,
        "province": province,
        "city": city,
        "license_number": license_number,
        "owner_name": owner_name,
        "contact_phone": contact_phone,
        "address": address,
        "service_level": PHARMACY_SERVICE_OPTIONS[service_level],
        "status": STATUS_OPTIONS[status],
    }


def _select_organization(
    label: str,
    rows: list[dict[str, object]],
    key: str,
    current_id: int | None = None,
) -> int | None:
    """Render a selectbox for optional organization assignment."""

    options = {"بدون اتصال": None}
    options.update({str(row["name"]): int(row["id"]) for row in rows})
    labels = list(options.keys())
    current_label = "بدون اتصال"
    if current_id:
        for item_label, item_id in options.items():
            if item_id == current_id:
                current_label = item_label
                break
    selected = st.selectbox(label, labels, index=labels.index(current_label), key=key)
    return options[selected]


def _localize_roles(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Localize role rows for display."""

    return [
        {
            "شناسه": row["id"],
            "کد": row["code"],
            "نام نقش": row["name_fa"],
            "توضیح": row["description"],
            "تعداد مجوز": row["permission_count"],
        }
        for row in rows
    ]


def _localize_permissions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Localize permission rows for display."""

    return [
        {
            "کد مجوز": row["code"],
            "نام فارسی": row["name_fa"],
            "ماژول": row["module"],
            "توضیح": row["description"],
        }
        for row in rows
    ]


def _localize_role_permissions(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Localize role-permission rows for display."""

    return [
        {
            "نقش": row["role_name"],
            "کد نقش": row["role_code"],
            "مجوز": row["permission_name"],
            "کد مجوز": row["permission_code"],
            "ماژول": row["module"],
        }
        for row in rows
    ]
