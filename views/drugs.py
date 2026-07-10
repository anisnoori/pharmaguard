"""Drug management module for PharmaGuard AI.

This page is the operational drug inventory module. It provides searchable drug
inventory, validated create/update/delete workflows, and supply-chain metadata
without leaking SQL or business rules into the Streamlit UI layer.
"""

from __future__ import annotations

from datetime import date, timedelta
from math import ceil
from typing import Any

import pandas as pd
import streamlit as st

from config import RISK_LABELS
from database.repositories import DrugCategoryRepository, DrugRepository, SupplierRepository
from models.entities import DrugFilters, DrugInventoryItem, DrugRecord
from services.drug_service import DrugManagementService
from services.prediction_service import ShortagePredictionService
from utils.persian import fa_number, format_iso_date_fa, percent_fa, parse_iso_date, days_until

CATEGORY_NONE_LABEL = "همه دسته‌ها"
SUPPLIER_NONE_LABEL = "همه تأمین‌کننده‌ها"
FORM_NONE_LABEL = "انتخاب نشده"
STOCK_STATUS_OPTIONS = {
    "همه وضعیت‌ها": "all",
    "کمتر از حداقل مجاز": "low",
    "پایدار": "stable",
}
EXPIRATION_STATUS_OPTIONS = {
    "همه تاریخ‌ها": "all",
    "منقضی‌شده": "expired",
    "نزدیک به انقضا": "soon",
    "دارای اعتبار مناسب": "valid",
}
SORT_OPTIONS = {
    "نام دارو": "name",
    "موجودی": "stock",
    "تاریخ انقضا": "expiration",
    "مصرف ماهانه": "consumption",
    "جدیدترین ثبت": "created",
}
SORT_DIRECTION_OPTIONS = {
    "صعودی": "asc",
    "نزولی": "desc",
}
UNIT_OPTIONS = ["عدد", "جعبه", "ویال", "آمپول", "قرص", "کپسول", "بطری", "بسته"]


def render_drug_management_page() -> None:
    """Render the full drug-management module."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    role_code = str(user["role_code"])
    can_write = DrugManagementService.can_write(role_code)
    can_delete = DrugManagementService.can_delete(role_code)
    categories = DrugCategoryRepository.list_all()
    suppliers = SupplierRepository.list_all()

    _render_page_header(role_name=str(user["role_name"]), can_write=can_write)

    tab_list, tab_create, tab_edit, tab_reference = st.tabs(
        ["فهرست و پایش", "ثبت داروی جدید", "ویرایش و حذف", "دسته‌بندی و تأمین‌کننده"]
    )
    with tab_list:
        _render_drug_list(categories, suppliers)
    with tab_create:
        _render_create_form(categories, suppliers, user, can_write)
    with tab_edit:
        _render_edit_and_delete_form(categories, suppliers, user, can_write, can_delete)
    with tab_reference:
        _render_reference_data(categories, suppliers, user, can_write)


def _render_page_header(role_name: str, can_write: bool) -> None:
    """Render a professional module header."""

    write_hint = "امکان ثبت و ویرایش فعال است." if can_write else "این نقش فقط دسترسی مشاهده دارد."
    st.markdown(
        f"""
        <section class="pg-module-hero">
          <span class="pg-badge">مدیریت موجودی دارویی</span>
          <h1>مدیریت حرفه‌ای داروها و موجودی</h1>
          <p>
            داروها را با دسته‌بندی، تولیدکننده، شماره بچ، تاریخ انقضا، تأمین‌کننده،
            حداقل موجودی و شاخص دسترسی بازار مدیریت کنید. این اطلاعات پایه موتور
            پیش‌بینی کمبود و گزارش‌های مدیریتی فارماگارد است.
          </p>
          <div class="pg-module-meta">
            <span>نقش فعلی: {role_name}</span>
            <span>{write_hint}</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_drug_list(categories: list[Any], suppliers: list[Any]) -> None:
    """Render filters, paginated table, and action selector."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>فهرست داروها</h2>
          <p>برای تصمیم‌گیری سریع، هر دارو همراه با وضعیت موجودی، انقضا و ریسک کمبود نمایش داده می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    filters = _render_filters(categories, suppliers)
    page_size = st.selectbox(
        "تعداد ردیف در صفحه",
        options=[5, 10, 20, 50],
        index=1,
        key="drug_list_page_size",
        help="برای جدول‌های بزرگ، تعداد کمتر باعث خوانایی بهتر می‌شود.",
    )
    total = DrugRepository.list_paginated(filters, page=1, page_size=1).total
    total_pages = max(1, ceil(total / page_size))
    page = st.selectbox(
        "صفحه",
        options=list(range(1, total_pages + 1)),
        format_func=lambda value: fa_number(value),
        key=f"drug_list_page_{total_pages}_{page_size}",
    )

    result = DrugRepository.list_paginated(filters, page=page, page_size=page_size)
    _render_list_summary(result.rows, result.total, page, total_pages)

    if not result.rows:
        st.info("با این فیلترها دارویی پیدا نشد. عبارت جستجو یا فیلترها را تغییر دهید.")
        return

    dataframe = _records_to_dataframe(result.rows)
    st.dataframe(dataframe, use_container_width=True, hide_index=True)
    _render_row_action_selector(result.rows)


def _render_filters(categories: list[Any], suppliers: list[Any]) -> DrugFilters:
    """Render search/filter controls and return a typed filter object."""

    with st.container(border=True):
        st.caption("فیلترهای عملیاتی")
        col1, col2, col3 = st.columns(3)
        with col1:
            search = st.text_input(
                "جستجو",
                placeholder="نام دارو، ژنریک، تولیدکننده یا شماره بچ",
                key="drug_filter_search",
            )
            stock_label = st.selectbox(
                "وضعیت موجودی",
                options=list(STOCK_STATUS_OPTIONS.keys()),
                key="drug_filter_stock",
            )
        with col2:
            category_options = {CATEGORY_NONE_LABEL: None}
            category_options.update({category.name: category.id for category in categories})
            category_label = st.selectbox(
                "دسته‌بندی",
                options=list(category_options.keys()),
                key="drug_filter_category",
            )
            expiration_label = st.selectbox(
                "وضعیت انقضا",
                options=list(EXPIRATION_STATUS_OPTIONS.keys()),
                key="drug_filter_expiration",
            )
        with col3:
            supplier_options = {SUPPLIER_NONE_LABEL: None}
            supplier_options.update({supplier.name: supplier.id for supplier in suppliers})
            supplier_label = st.selectbox(
                "تأمین‌کننده",
                options=list(supplier_options.keys()),
                key="drug_filter_supplier",
            )
            sort_label = st.selectbox(
                "مرتب‌سازی",
                options=list(SORT_OPTIONS.keys()),
                key="drug_filter_sort",
            )
        direction_label = st.radio(
            "جهت مرتب‌سازی",
            options=list(SORT_DIRECTION_OPTIONS.keys()),
            horizontal=True,
            key="drug_filter_direction",
        )

    return DrugFilters(
        search=search,
        category_id=category_options[category_label],
        supplier_id=supplier_options[supplier_label],
        stock_status=STOCK_STATUS_OPTIONS[stock_label],
        expiration_status=EXPIRATION_STATUS_OPTIONS[expiration_label],
        sort_by=SORT_OPTIONS[sort_label],
        sort_direction=SORT_DIRECTION_OPTIONS[direction_label],
    )


def _render_list_summary(rows: list[DrugRecord], total: int, page: int, total_pages: int) -> None:
    """Render compact operational metrics for the current result set."""

    low_stock = sum(1 for record in rows if record.current_stock < record.minimum_stock)
    expiring_soon = sum(1 for record in rows if _expiration_status(record.expiration_date)[0] == "نزدیک به انقضا")
    critical_risk = sum(1 for record in rows if _prediction_for(record).risk_level in {"critical", "high"})
    st.markdown(
        f"""
        <div class="pg-mini-metrics">
          <div><strong>{fa_number(total)}</strong><span>کل نتایج</span></div>
          <div><strong>{fa_number(low_stock)}</strong><span>کمتر از حداقل</span></div>
          <div><strong>{fa_number(expiring_soon)}</strong><span>نزدیک به انقضا</span></div>
          <div><strong>{fa_number(critical_risk)}</strong><span>ریسک زیاد/بحرانی</span></div>
          <div><strong>{fa_number(page)} / {fa_number(total_pages)}</strong><span>صفحه</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _records_to_dataframe(records: list[DrugRecord]) -> pd.DataFrame:
    """Convert drug records to a Persian display DataFrame."""

    rows: list[dict[str, str]] = []
    for record in records:
        prediction = _prediction_for(record)
        stock_label, stock_detail = _stock_status(record)
        expiration_label, expiration_detail = _expiration_status(record.expiration_date)
        stock_days = _stock_days(record)
        rows.append(
            {
                "شناسه": fa_number(record.id),
                "نام دارو": record.name,
                "نام ژنریک": record.generic_name or "ثبت نشده",
                "دسته": record.category_name,
                "تولیدکننده": record.manufacturer or "ثبت نشده",
                "شماره بچ": record.batch_number,
                "تأمین‌کننده": record.supplier_name,
                "تاریخ انقضا": format_iso_date_fa(record.expiration_date),
                "موجودی": fa_number(record.current_stock),
                "حداقل مجاز": fa_number(record.minimum_stock),
                "مصرف ماهانه": fa_number(record.monthly_consumption),
                "پوشش موجودی": f"{fa_number(stock_days)} روز" if stock_days is not None else "نامشخص",
                "وضعیت موجودی": f"{stock_label} · {stock_detail}",
                "وضعیت انقضا": f"{expiration_label} · {expiration_detail}",
                "دسترسی بازار": percent_fa(record.availability_score),
                "ریسک کمبود": RISK_LABELS[prediction.risk_level],
                "احتمال": percent_fa(prediction.probability),
                "پیشنهاد": prediction.recommendation,
            }
        )
    return pd.DataFrame(rows)


def _render_row_action_selector(records: list[DrugRecord]) -> None:
    """Allow users to select a row for edit/delete workflows."""

    options = {f"{record.name} · بچ {record.batch_number} · شناسه {fa_number(record.id)}": record.id for record in records}
    selected_label = st.selectbox(
        "انتخاب دارو برای عملیات بعدی",
        options=list(options.keys()),
        key="drug_selected_from_list",
    )
    if st.button("ارسال به فرم ویرایش", key="drug_send_to_edit", use_container_width=True):
        st.session_state.selected_drug_id = options[selected_label]
        st.success("دارو انتخاب شد. حالا در تب «ویرایش و حذف» اطلاعات آن را ببینید.")


def _render_create_form(categories: list[Any], suppliers: list[Any], user: dict[str, Any], can_write: bool) -> None:
    """Render the create-drug workflow."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>ثبت داروی جدید</h2>
          <p>اطلاعات دقیق دارو باعث می‌شود پیش‌بینی کمبود، گزارش‌ها و هشدارها قابل اعتماد باشند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not can_write:
        st.warning("حساب شما فقط دسترسی مشاهده دارد؛ ثبت داروی جدید برای این نقش غیرفعال است.")

    with st.form("create_drug_form", clear_on_submit=False):
        data = _render_drug_fields(
            categories=categories,
            suppliers=suppliers,
            prefix="create",
            initial=None,
            disabled=not can_write,
        )
        submitted = st.form_submit_button(
            "ثبت داروی جدید",
            type="primary",
            use_container_width=True,
            disabled=not can_write,
        )

    if submitted:
        result = DrugManagementService.create_drug(
            data,
            user_id=int(user["id"]),
            role_code=str(user["role_code"]),
        )
        _show_service_result(result)
        if result.success:
            st.cache_data.clear()


def _render_edit_and_delete_form(
    categories: list[Any],
    suppliers: list[Any],
    user: dict[str, Any],
    can_write: bool,
    can_delete: bool,
) -> None:
    """Render update and delete workflows for a selected drug."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>ویرایش و حذف دارو</h2>
          <p>برای حفظ اعتبار گزارش‌ها، حذف دارو باید آگاهانه انجام شود. ویرایش موجودی و تاریخ انقضا در همین بخش انجام می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    options = DrugRepository.list_for_selection()
    if not options:
        st.info("هنوز دارویی برای ویرایش ثبت نشده است.")
        return

    option_labels = {f"{name} · بچ {batch} · شناسه {fa_number(drug_id)}": drug_id for drug_id, name, batch in options}
    preferred_id = st.session_state.get("selected_drug_id")
    labels = list(option_labels.keys())
    default_index = _find_option_index(labels, option_labels, preferred_id)
    selected_label = st.selectbox(
        "داروی موردنظر را انتخاب کنید",
        options=labels,
        index=default_index,
        key="edit_drug_selector",
    )
    record = DrugRepository.get_by_id(option_labels[selected_label])
    if record is None:
        st.error("داروی انتخاب‌شده پیدا نشد.")
        return

    with st.form(f"edit_drug_form_{record.id}", clear_on_submit=False):
        data = _render_drug_fields(
            categories=categories,
            suppliers=suppliers,
            prefix=f"edit_{record.id}",
            initial=record,
            disabled=not can_write,
        )
        submitted = st.form_submit_button(
            "ذخیره تغییرات دارو",
            type="primary",
            use_container_width=True,
            disabled=not can_write,
        )

    if submitted:
        result = DrugManagementService.update_drug(
            record.id,
            data,
            user_id=int(user["id"]),
            role_code=str(user["role_code"]),
        )
        _show_service_result(result)
        if result.success:
            st.rerun()

    _render_delete_area(record, user, can_delete)


def _render_drug_fields(
    categories: list[Any],
    suppliers: list[Any],
    prefix: str,
    initial: DrugRecord | None,
    disabled: bool,
) -> Any:
    """Render reusable drug form fields and return a normalized payload."""

    category_options = {FORM_NONE_LABEL: None}
    category_options.update({category.name: category.id for category in categories})
    supplier_options = {FORM_NONE_LABEL: None}
    supplier_options.update({supplier.name: supplier.id for supplier in suppliers})

    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input(
            "نام دارو",
            value=initial.name if initial else "",
            placeholder="مثلاً آموکسی‌سیلین ۵۰۰",
            key=f"{prefix}_name",
            disabled=disabled,
        )
        category_label = st.selectbox(
            "دسته‌بندی",
            options=list(category_options.keys()),
            index=_select_index_by_id(category_options, initial.category_id if initial else None),
            key=f"{prefix}_category",
            disabled=disabled,
        )
        manufacturer = st.text_input(
            "تولیدکننده",
            value=initial.manufacturer if initial else "",
            placeholder="مثلاً داروسازی سلامت",
            key=f"{prefix}_manufacturer",
            disabled=disabled,
        )
        expiration_date = st.date_input(
            "تاریخ انقضا",
            value=_initial_expiration_date(initial),
            min_value=date.today(),
            key=f"{prefix}_expiration",
            disabled=disabled,
        )
        current_stock = st.number_input(
            "موجودی فعلی",
            min_value=0,
            step=1,
            value=initial.current_stock if initial else 0,
            key=f"{prefix}_current_stock",
            disabled=disabled,
        )
        monthly_consumption = st.number_input(
            "مصرف ماهانه",
            min_value=0,
            step=1,
            value=initial.monthly_consumption if initial else 0,
            key=f"{prefix}_monthly_consumption",
            disabled=disabled,
        )
    with col2:
        generic_name = st.text_input(
            "نام ژنریک",
            value=initial.generic_name if initial else "",
            placeholder="مثلاً Amoxicillin",
            key=f"{prefix}_generic_name",
            disabled=disabled,
        )
        supplier_label = st.selectbox(
            "تأمین‌کننده",
            options=list(supplier_options.keys()),
            index=_select_index_by_id(supplier_options, initial.supplier_id if initial else None),
            key=f"{prefix}_supplier",
            disabled=disabled,
        )
        batch_number = st.text_input(
            "شماره بچ",
            value=initial.batch_number if initial else "",
            placeholder="مثلاً AMX-1403-A",
            key=f"{prefix}_batch_number",
            disabled=disabled,
        )
        unit = st.selectbox(
            "واحد شمارش",
            options=UNIT_OPTIONS,
            index=_safe_unit_index(initial.unit if initial else "عدد"),
            key=f"{prefix}_unit",
            disabled=disabled,
        )
        minimum_stock = st.number_input(
            "حداقل موجودی مجاز",
            min_value=0,
            step=1,
            value=initial.minimum_stock if initial else 0,
            key=f"{prefix}_minimum_stock",
            disabled=disabled,
        )
        availability_score = st.slider(
            "شاخص دسترسی بازار",
            min_value=0.0,
            max_value=1.0,
            value=initial.availability_score if initial else 0.75,
            step=0.01,
            key=f"{prefix}_availability_score",
            disabled=disabled,
            help="۱ یعنی دسترسی بازار عالی، ۰ یعنی دسترسی بسیار ضعیف.",
        )

    st.caption("راهنما: حداقل موجودی و مصرف ماهانه در موتور پیش‌بینی کمبود استفاده می‌شوند.")
    return DrugManagementService.build_drug_payload(
        name=name,
        generic_name=generic_name,
        category_id=category_options[category_label],
        manufacturer=manufacturer,
        batch_number=batch_number,
        expiration_date=expiration_date,
        supplier_id=supplier_options[supplier_label],
        unit=unit,
        current_stock=int(current_stock),
        minimum_stock=int(minimum_stock),
        monthly_consumption=int(monthly_consumption),
        availability_score=float(availability_score),
    )


def _render_delete_area(record: DrugRecord, user: dict[str, Any], can_delete: bool) -> None:
    """Render a guarded delete operation."""

    st.markdown(
        """
        <div class="pg-danger-zone">
          <h3>حذف کنترل‌شده</h3>
          <p>حذف دارو از فهرست عملیاتی انجام می‌شود و پیش‌بینی‌های وابسته نیز پاک خواهند شد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not can_delete:
        st.info("نقش شما اجازه حذف دارو را ندارد.")
        return

    with st.form(f"delete_drug_form_{record.id}", clear_on_submit=False):
        confirmation = st.text_input(
            "برای حذف، نام دقیق دارو را وارد کنید",
            placeholder=record.name,
            key=f"delete_confirm_{record.id}",
        )
        submitted = st.form_submit_button("حذف قطعی دارو", type="secondary", use_container_width=True)

    if submitted:
        if confirmation.strip() != record.name:
            st.error("نام واردشده با نام دارو یکسان نیست. حذف انجام نشد.")
            return
        result = DrugManagementService.delete_drug(
            record,
            user_id=int(user["id"]),
            role_code=str(user["role_code"]),
        )
        _show_service_result(result)
        if result.success:
            st.session_state.pop("selected_drug_id", None)
            st.rerun()


def _render_reference_data(categories: list[Any], suppliers: list[Any], user: dict[str, Any], can_write: bool) -> None:
    """Render category and supplier reference management."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>دسته‌بندی و تأمین‌کننده‌ها</h2>
          <p>این داده‌ها باعث می‌شوند فیلترها، گزارش‌ها و تحلیل زنجیره تأمین دقیق‌تر باشند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("دسته‌بندی‌های دارویی")
        category_frame = pd.DataFrame(
            [{"شناسه": fa_number(item.id), "نام": item.name, "توضیح": item.description} for item in categories]
        )
        st.dataframe(category_frame, use_container_width=True, hide_index=True)
        _render_category_form(user, can_write)
    with col2:
        st.subheader("تأمین‌کننده‌ها")
        supplier_frame = pd.DataFrame(
            [
                {
                    "شناسه": fa_number(item.id),
                    "نام": item.name,
                    "شهر": item.city,
                    "اعتماد": percent_fa(item.reliability_score),
                    "زمان تأمین": f"{fa_number(item.average_lead_time_days)} روز",
                }
                for item in suppliers
            ]
        )
        st.dataframe(supplier_frame, use_container_width=True, hide_index=True)
        _render_supplier_form(user, can_write)


def _render_category_form(user: dict[str, Any], can_write: bool) -> None:
    """Render add-category form."""

    with st.expander("افزودن دسته‌بندی جدید"):
        if not can_write:
            st.info("برای این نقش، افزودن دسته‌بندی غیرفعال است.")
            return
        with st.form("create_category_form", clear_on_submit=True):
            name = st.text_input("نام دسته‌بندی", key="category_name")
            description = st.text_area("توضیح", key="category_description")
            submitted = st.form_submit_button("ثبت دسته‌بندی", use_container_width=True)
        if submitted:
            result = DrugManagementService.create_category(name, description, int(user["id"]))
            _show_service_result(result)
            if result.success:
                st.rerun()


def _render_supplier_form(user: dict[str, Any], can_write: bool) -> None:
    """Render add-supplier form."""

    with st.expander("افزودن تأمین‌کننده جدید"):
        if not can_write:
            st.info("برای این نقش، افزودن تأمین‌کننده غیرفعال است.")
            return
        with st.form("create_supplier_form", clear_on_submit=True):
            name = st.text_input("نام تأمین‌کننده", key="supplier_name")
            city = st.text_input("شهر", key="supplier_city")
            reliability_score = st.slider(
                "امتیاز اعتماد",
                min_value=0.0,
                max_value=1.0,
                value=0.75,
                step=0.01,
                key="supplier_reliability_score",
            )
            lead_time = st.number_input(
                "میانگین زمان تأمین / روز",
                min_value=1,
                max_value=180,
                value=7,
                step=1,
                key="supplier_lead_time",
            )
            submitted = st.form_submit_button("ثبت تأمین‌کننده", use_container_width=True)
        if submitted:
            result = DrugManagementService.create_supplier(
                name,
                city,
                reliability_score,
                int(lead_time),
                int(user["id"]),
            )
            _show_service_result(result)
            if result.success:
                st.rerun()


def _prediction_for(record: DrugRecord) -> Any:
    """Return an explainable shortage prediction for a drug record."""

    item = DrugInventoryItem(
        id=record.id,
        name=record.name,
        current_stock=record.current_stock,
        minimum_stock=record.minimum_stock,
        monthly_consumption=record.monthly_consumption,
        availability_score=record.availability_score,
        lead_time_days=record.lead_time_days,
    )
    return ShortagePredictionService.predict(item)


def _stock_days(record: DrugRecord) -> int | None:
    """Estimate inventory coverage in days."""

    if record.monthly_consumption <= 0:
        return None
    daily_consumption = max(record.monthly_consumption / 30, 0.1)
    return int(record.current_stock / daily_consumption)


def _stock_status(record: DrugRecord) -> tuple[str, str]:
    """Return stock status and detail text."""

    if record.current_stock < record.minimum_stock:
        shortage = record.minimum_stock - record.current_stock
        return "نیازمند اقدام", f"{fa_number(shortage)} {record.unit} کمتر از حداقل"
    if record.minimum_stock and record.current_stock <= record.minimum_stock * 1.2:
        return "مرزی", "نزدیک به حداقل مجاز"
    return "پایدار", "موجودی قابل قبول"


def _expiration_status(expiration_date: str | None) -> tuple[str, str]:
    """Return expiration status and detail text."""

    remaining_days = days_until(expiration_date)
    if remaining_days is None:
        return "نامشخص", "تاریخ ثبت نشده"
    if remaining_days < 0:
        return "منقضی‌شده", f"{fa_number(abs(remaining_days))} روز گذشته"
    if remaining_days <= 90:
        return "نزدیک به انقضا", f"{fa_number(remaining_days)} روز باقی‌مانده"
    return "معتبر", f"{fa_number(remaining_days)} روز باقی‌مانده"


def _initial_expiration_date(initial: DrugRecord | None) -> date:
    """Return a safe default date for Streamlit date inputs."""

    if initial is None:
        return date.today() + timedelta(days=365)
    parsed = parse_iso_date(initial.expiration_date)
    if parsed is None or parsed < date.today():
        return date.today()
    return parsed


def _select_index_by_id(options: dict[str, int | None], selected_id: int | None) -> int:
    """Return selectbox index by option value."""

    values = list(options.values())
    if selected_id in values:
        return values.index(selected_id)
    return 0


def _safe_unit_index(unit: str) -> int:
    """Return a safe unit index for Streamlit selectbox."""

    return UNIT_OPTIONS.index(unit) if unit in UNIT_OPTIONS else 0


def _find_option_index(labels: list[str], option_labels: dict[str, int], preferred_id: Any) -> int:
    """Find the selector index for the previously selected drug id."""

    if preferred_id is None:
        return 0
    for index, label in enumerate(labels):
        if option_labels[label] == preferred_id:
            return index
    return 0


def _show_service_result(result: Any) -> None:
    """Render a standard service result message."""

    if result.success:
        st.success(result.message)
    else:
        st.error(result.message)
