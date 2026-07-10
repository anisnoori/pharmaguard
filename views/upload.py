"""Bulk CSV/Excel upload module for PharmaGuard AI.

Phase 3 turns data entry from a manual form into an auditable, validated import
workflow with templates, preview, column mapping, duplicate detection, and an
import summary suitable for healthcare inventory operations.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.repositories import DrugRepository
from services.drug_service import DrugManagementService
from services.import_service import (
    DUPLICATE_SKIP,
    DUPLICATE_UPDATE,
    UNMAPPED_LABEL,
    DrugImportService,
    ImportOptions,
    ImportPreviewResult,
)
from utils.persian import fa_number

DUPLICATE_POLICY_LABELS = {
    "رد کردن رکوردهای تکراری": DUPLICATE_SKIP,
    "به‌روزرسانی رکوردهای موجود": DUPLICATE_UPDATE,
}


def render_data_import_page() -> None:
    """Render the complete CSV/Excel upload workflow."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    role_code = str(user["role_code"])
    can_write = DrugManagementService.can_write(role_code)
    _render_page_header(role_name=str(user["role_name"]), can_write=can_write)

    tab_upload, tab_history = st.tabs(["ورود داده", "تاریخچه ورود"])
    with tab_upload:
        _render_template_area()
        _render_upload_workflow(user=user, can_write=can_write)
    with tab_history:
        _render_import_history()


def _render_page_header(role_name: str, can_write: bool) -> None:
    """Render the module hero for data import."""

    write_hint = "ورود گروهی داده برای این نقش فعال است." if can_write else "این نقش فقط اجازه مشاهده دارد."
    st.markdown(
        f"""
        <section class="pg-module-hero">
          <span class="pg-badge">ورود امن CSV / Excel</span>
          <h1>ورود گروهی اطلاعات دارویی بدون خطای عملیاتی</h1>
          <p>
            فایل‌های CSV و Excel را قبل از ورود به دیتابیس پیش‌نمایش، مپ، اعتبارسنجی و کنترل تکراری کنید.
            این فرآیند برای بیمارستان‌ها و داروخانه‌هایی طراحی شده که داده موجودی را از سیستم‌های قدیمی،
            انبار یا فایل‌های اکسل به فارماگارد منتقل می‌کنند.
          </p>
          <div class="pg-module-meta">
            <span>نقش فعلی: {role_name}</span>
            <span>{write_hint}</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_template_area() -> None:
    """Render template downloads and import rules."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۱. قالب پیشنهادی را دریافت کنید</h2>
          <p>استفاده از قالب پیشنهادی خطا را کمتر می‌کند، اما سامانه فایل‌های واقعی داروخانه و بیمارستان را هم با ستون‌های متفاوت می‌پذیرد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        st.download_button(
            "دانلود قالب CSV",
            data=DrugImportService.template_csv_bytes(),
            file_name="pharmaguard_drug_import_template.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_import_template_csv",
        )
    with col2:
        st.download_button(
            "دانلود قالب Excel",
            data=DrugImportService.template_excel_bytes(),
            file_name="pharmaguard_drug_import_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="download_import_template_excel",
        )
    with col3:
        st.info("تاریخ‌ها باید میلادی باشند، مثل 2027-03-20. اعداد فارسی و انگلیسی هر دو قابل پردازش هستند.")


def _render_upload_workflow(user: dict[str, Any], can_write: bool) -> None:
    """Render upload, mapping, validation, and final import."""

    if not can_write:
        st.warning("حساب شما اجازه ورود یا تغییر گروهی داده را ندارد. برای فعال‌سازی، با مدیر سامانه تماس بگیرید.")
        return

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۲. فایل را بارگذاری و ستون‌ها را مپ کنید</h2>
          <p>قبل از ذخیره در دیتابیس، هیچ داده‌ای تغییر نمی‌کند. ابتدا فقط پیش‌نمایش و کنترل کیفیت انجام می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    uploaded_file = st.file_uploader(
        "فایل CSV یا XLSX",
        type=["csv", "xlsx"],
        key="drug_import_file",
        help="حداکثر ۲۰۰۰ ردیف در هر بار ورود داده پشتیبانی می‌شود.",
    )
    if uploaded_file is None:
        _render_empty_upload_state()
        return

    file_bytes = uploaded_file.getvalue()
    sheet_name = _render_sheet_selector(uploaded_file.name, file_bytes)
    try:
        frame = DrugImportService.read_uploaded_table(file_bytes, uploaded_file.name, sheet_name)
    except ValueError as error:
        st.error(str(error))
        return

    _render_source_preview(frame)
    mapping = _render_column_mapping(frame)
    options = _render_import_options()
    _render_validation_area(frame, uploaded_file.name, mapping, options, user)


def _render_empty_upload_state() -> None:
    """Render guidance before a user uploads a file."""

    st.markdown(
        """
        <div class="pg-empty-state">
          <h3>هنوز فایلی انتخاب نشده است</h3>
          <p>قالب CSV یا XLSX را دانلود کنید، اطلاعات داروها را وارد کنید و سپس فایل را اینجا بارگذاری کنید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_sheet_selector(file_name: str, file_bytes: bytes) -> str | None:
    """Render Excel sheet selection when the uploaded file is a workbook."""

    extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if extension != "xlsx":
        return None
    try:
        sheets = DrugImportService.list_excel_sheets(file_bytes)
    except ValueError as error:
        st.error(str(error))
        return None
    return st.selectbox(
        "انتخاب Sheet",
        options=sheets,
        key="drug_import_sheet_selector",
        help="اگر فایل چند Sheet دارد، Sheet حاوی جدول داروها را انتخاب کنید.",
    )


def _render_source_preview(frame: pd.DataFrame) -> None:
    """Show a safe preview of the uploaded table."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۳. پیش‌نمایش فایل</h2>
          <p>این بخش فقط برای بررسی است و هنوز چیزی وارد دیتابیس نشده است.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("تعداد ردیف", fa_number(len(frame)))
    with col2:
        st.metric("تعداد ستون", fa_number(len(frame.columns)))
    with col3:
        st.metric("حداکثر مجاز", fa_number(2000))
    st.dataframe(frame.head(12), use_container_width=True, hide_index=True)


def _render_column_mapping(frame: pd.DataFrame) -> dict[str, str]:
    """Render target-to-source column mapping controls."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۴. مپ کردن ستون‌ها</h2>
          <p>فقط نام دارو ضروری است. موجودی، بچ، انقضا، تأمین‌کننده و سایر اطلاعات اگر در فایل موجود باشند ذخیره می‌شوند و اگر نباشند، رکورد با وضعیت نیازمند تکمیل وارد می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    source_columns = [str(column) for column in frame.columns]
    default_mapping = DrugImportService.build_default_mapping(source_columns)
    selectable_columns = [UNMAPPED_LABEL, *source_columns]
    mapping: dict[str, str] = {}

    with st.container(border=True):
        target_columns = list(DrugImportService.target_columns())
        for start in range(0, len(target_columns), 3):
            columns = st.columns(3)
            for column, target in zip(columns, target_columns[start : start + 3], strict=False):
                label = f"{target.label}{' *' if target.required else ''}"
                default_value = default_mapping.get(target.key, UNMAPPED_LABEL)
                default_index = selectable_columns.index(default_value) if default_value in selectable_columns else 0
                with column:
                    mapping[target.key] = st.selectbox(
                        label,
                        options=selectable_columns,
                        index=default_index,
                        key=f"drug_import_map_{target.key}",
                        help=target.help_text,
                    )
    return mapping


def _render_import_options() -> ImportOptions:
    """Render duplicate and reference-handling options."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۵. تنظیمات کنترل کیفیت</h2>
          <p>نحوه برخورد با رکوردهای تکراری و داده‌های مرجع جدید را مشخص کنید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        duplicate_label = st.selectbox(
            "رفتار با داروی تکراری در دیتابیس",
            options=list(DUPLICATE_POLICY_LABELS.keys()),
            key="drug_import_duplicate_policy",
            help="تکراری یعنی ترکیب نام دارو و شماره بچ از قبل وجود داشته باشد.",
        )
    with col2:
        create_missing_references = st.checkbox(
            "ساخت خودکار دسته‌بندی و تأمین‌کننده جدید",
            value=True,
            key="drug_import_create_references",
            help="اگر خاموش باشد، نام‌های جدیدی که در سیستم وجود ندارند خطا می‌شوند.",
        )
    return ImportOptions(
        duplicate_policy=DUPLICATE_POLICY_LABELS[duplicate_label],
        create_missing_references=create_missing_references,
    )


def _render_validation_area(
    frame: pd.DataFrame,
    file_name: str,
    mapping: dict[str, str],
    options: ImportOptions,
    user: dict[str, Any],
) -> None:
    """Validate the upload and optionally execute the import."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۶. اعتبارسنجی و ورود نهایی</h2>
          <p>پس از اعتبارسنجی، فقط ردیف‌های آماده ثبت یا آماده به‌روزرسانی وارد دیتابیس می‌شوند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("اجرای کنترل کیفیت و پیش‌نمایش نتیجه", type="primary", use_container_width=True, key="drug_import_validate"):
        try:
            preview = DrugImportService.validate_preview(frame, file_name, mapping, options)
            st.session_state["drug_import_preview"] = preview
            st.session_state["drug_import_options"] = options
        except ValueError as error:
            st.session_state.pop("drug_import_preview", None)
            st.error(str(error))
            return

    preview = st.session_state.get("drug_import_preview")
    saved_options = st.session_state.get("drug_import_options")
    if not isinstance(preview, ImportPreviewResult):
        return
    if not isinstance(saved_options, ImportOptions):
        saved_options = options

    _render_preview_result(preview)
    if preview.valid_rows <= 0:
        st.warning("هیچ ردیف آماده ورود وجود ندارد. خطاها و تکراری‌ها را اصلاح کنید و دوباره اعتبارسنجی بگیرید.")
        return

    confirm = st.checkbox(
        "تأیید می‌کنم فقط ردیف‌های معتبر وارد دیتابیس شوند.",
        key="drug_import_final_confirm",
    )
    if st.button(
        "ورود نهایی به دیتابیس",
        type="primary",
        use_container_width=True,
        disabled=not confirm,
        key="drug_import_execute",
    ):
        summary = DrugImportService.execute_import(
            preview=preview,
            options=saved_options,
            user_id=int(user["id"]),
            role_code=str(user["role_code"]),
        )
        _render_execution_summary(summary)
        if summary.inserted_rows + summary.updated_rows > 0:
            st.session_state.pop("drug_import_preview", None)
            st.cache_data.clear()


def _render_preview_result(preview: ImportPreviewResult) -> None:
    """Render validation metrics and row-level outcome."""

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("کل ردیف", fa_number(preview.total_rows))
    with col2:
        st.metric("آماده ثبت", fa_number(preview.create_rows))
    with col3:
        st.metric("آماده به‌روزرسانی", fa_number(preview.update_rows))
    with col4:
        st.metric("تکراری", fa_number(preview.duplicate_rows))
    with col5:
        st.metric("نامعتبر", fa_number(preview.invalid_rows))

    result_frame = DrugImportService.preview_to_dataframe(preview)
    st.dataframe(result_frame, use_container_width=True, hide_index=True)


def _render_execution_summary(summary: Any) -> None:
    """Render final import result."""

    if summary.success:
        st.success(summary.message)
    else:
        st.warning(summary.message)
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("ثبت‌شده", fa_number(summary.inserted_rows))
    with col2:
        st.metric("به‌روزرسانی", fa_number(summary.updated_rows))
    with col3:
        st.metric("ردشده", fa_number(summary.skipped_rows))
    with col4:
        st.metric("خطای اجرا", fa_number(summary.failed_rows))
    if summary.errors:
        with st.expander("جزئیات خطاهای اجرا"):
            for error in summary.errors:
                st.error(error)
    if summary.batch_id:
        st.info(f"شناسه Batch ورود داده: {fa_number(summary.batch_id)}")


def _render_import_history() -> None:
    """Render recent import batches."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>تاریخچه ورود داده</h2>
          <p>برای حسابرسی عملیاتی، هر ورود گروهی همراه با خلاصه کیفیت و تعداد رکوردهای ثبت‌شده نگهداری می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    frame = DrugImportService.latest_imports_dataframe(limit=10)
    if frame.empty:
        st.info("هنوز هیچ ورود گروهی ثبت نشده است.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True)
    current_count = DrugRepository.list_paginated(filters=_empty_filters(), page=1, page_size=1).total
    st.caption(f"تعداد فعلی رکوردهای دارویی در دیتابیس: {fa_number(current_count)}")


def _empty_filters() -> Any:
    """Return an empty DrugFilters object without importing it at module top level."""

    from models.entities import DrugFilters

    return DrugFilters()
