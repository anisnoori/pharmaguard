"""CSV and Excel import workflow for PharmaGuard AI.

The import service keeps parsing, column mapping, validation, duplicate
inspection, and persistence outside Streamlit pages. This makes the Upload
module testable and protects the database from malformed bulk data.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
from importlib.util import find_spec
from io import BytesIO, StringIO
from typing import Any
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd

from database.repositories import (
    ActivityLogRepository,
    DrugCategoryRepository,
    DrugRepository,
    ImportBatchRepository,
    SupplierRepository,
)
from models.entities import DrugFormData
from services.drug_service import DrugManagementService, ServiceResult
from utils.validators import clean_text

UNMAPPED_LABEL = "انتخاب نشده"
DUPLICATE_SKIP = "skip"
DUPLICATE_UPDATE = "update"
MAX_IMPORT_ROWS = 2_000

PERSIAN_TO_LATIN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


@dataclass(frozen=True)
class TargetColumn:
    """A canonical import field that can be mapped from uploaded columns."""

    key: str
    label: str
    required: bool
    aliases: tuple[str, ...]
    help_text: str


@dataclass(frozen=True)
class ImportOptions:
    """User-selected behavior for an import batch."""

    duplicate_policy: str = DUPLICATE_SKIP
    create_missing_references: bool = True


@dataclass(frozen=True)
class ImportRowValidation:
    """Validation outcome for one source row."""

    row_number: int
    status: str
    status_label: str
    messages: tuple[str, ...]
    payload: DrugFormData | None
    category_name: str
    supplier_name: str
    existing_drug_id: int | None
    source_key: tuple[str, str] | None


@dataclass(frozen=True)
class ImportPreviewResult:
    """Complete validation preview for a mapped upload."""

    file_name: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    create_rows: int
    update_rows: int
    rows: tuple[ImportRowValidation, ...]


@dataclass(frozen=True)
class ImportExecutionSummary:
    """Result of the actual database import operation."""

    success: bool
    message: str
    batch_id: int | None
    total_rows: int
    inserted_rows: int
    updated_rows: int
    skipped_rows: int
    failed_rows: int
    errors: tuple[str, ...]


TARGET_COLUMNS: tuple[TargetColumn, ...] = (
    TargetColumn(
        "name",
        "نام دارو",
        True,
        ("name", "drug name", "drug_name", "medicine", "item name", "نام دارو", "نام کالا", "نام محصول", "دارو", "کالا", "نام"),
        "نام تجاری یا رایج دارو؛ مانند آموکسی‌سیلین ۵۰۰.",
    ),
    TargetColumn(
        "generic_name",
        "نام ژنریک",
        False,
        ("generic", "generic name", "generic_name", "نام ژنریک", "ژنریک"),
        "نام علمی/ژنریک دارو؛ مانند Amoxicillin.",
    ),
    TargetColumn(
        "category",
        "دسته‌بندی",
        False,
        ("category", "drug category", "category_name", "دسته", "دسته‌بندی", "گروه دارویی"),
        "گروه دارویی برای فیلتر و گزارش.",
    ),
    TargetColumn(
        "manufacturer",
        "تولیدکننده",
        False,
        ("manufacturer", "producer", "company", "brand owner", "تولیدکننده", "شرکت", "سازنده", "تولید کننده"),
        "نام شرکت تولیدکننده یا واردکننده.",
    ),
    TargetColumn(
        "batch_number",
        "شماره بچ",
        False,
        ("batch", "batch number", "batch_number", "lot", "lot_number", "serial", "شماره بچ", "بچ", "سری ساخت", "سری", "کد کالا"),
        "شناسه یکتای بچ یا سری ساخت.",
    ),
    TargetColumn(
        "expiration_date",
        "تاریخ انقضا",
        False,
        ("expiration", "expiry", "expiration date", "expiry_date", "exp", "تاریخ انقضا", "انقضا", "تاریخ اعتبار", "اعتبار"),
        "تاریخ میلادی با قالب 2027-03-20.",
    ),
    TargetColumn(
        "supplier",
        "تأمین‌کننده",
        False,
        ("supplier", "vendor", "distributor", "تأمین‌کننده", "تامین کننده", "توزیع‌کننده"),
        "نام تأمین‌کننده یا توزیع‌کننده دارو.",
    ),
    TargetColumn(
        "unit",
        "واحد شمارش",
        False,
        ("unit", "واحد", "واحد شمارش"),
        "عدد، جعبه، ویال، آمپول، قرص، کپسول، بطری یا بسته.",
    ),
    TargetColumn(
        "current_stock",
        "موجودی فعلی",
        False,
        ("current stock", "current_stock", "stock", "inventory", "qty", "quantity", "count", "تعداد", "موجودی", "موجودی فعلی", "مانده", "موجودی انبار"),
        "مقدار موجودی فعلی به عدد صحیح.",
    ),
    TargetColumn(
        "minimum_stock",
        "حداقل موجودی",
        False,
        ("minimum stock", "minimum_stock", "min stock", "min_stock", "حداقل موجودی", "نقطه سفارش"),
        "حداقل موجودی مجاز یا نقطه سفارش.",
    ),
    TargetColumn(
        "monthly_consumption",
        "مصرف ماهانه",
        False,
        ("monthly consumption", "monthly_consumption", "consumption", "مصرف", "مصرف ماهانه"),
        "مصرف متوسط ماهانه به عدد صحیح.",
    ),
    TargetColumn(
        "availability_score",
        "شاخص دسترسی بازار",
        False,
        ("availability", "availability_score", "market access", "شاخص دسترسی", "شاخص دسترسی بازار", "دسترسی بازار"),
        "عدد بین ۰ و ۱. اگر درصد وارد شود، خودکار به نسبت تبدیل می‌شود.",
    ),
)

TEMPLATE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "نام دارو": "آموکسی‌سیلین ۵۰۰",
        "نام ژنریک": "Amoxicillin",
        "دسته‌بندی": "آنتی‌بیوتیک",
        "تولیدکننده": "داروسازی سلامت",
        "شماره بچ": "AMX-1405-A",
        "تاریخ انقضا": "2027-03-20",
        "تأمین‌کننده": "پخش درمان نو",
        "واحد شمارش": "جعبه",
        "موجودی فعلی": 420,
        "حداقل موجودی": 180,
        "مصرف ماهانه": 260,
        "شاخص دسترسی بازار": 0.82,
    },
    {
        "نام دارو": "انسولین رگولار",
        "نام ژنریک": "Regular insulin",
        "دسته‌بندی": "داروهای غدد",
        "تولیدکننده": "بیوتک سلامت",
        "شماره بچ": "INS-1405-B",
        "تاریخ انقضا": "2027-08-15",
        "تأمین‌کننده": "توزیع ایمن دارو",
        "واحد شمارش": "ویال",
        "موجودی فعلی": 85,
        "حداقل موجودی": 120,
        "مصرف ماهانه": 90,
        "شاخص دسترسی بازار": 0.64,
    },
)


class DrugImportService:
    """Coordinate upload parsing, validation, preview, and import execution."""

    @staticmethod
    def target_columns() -> tuple[TargetColumn, ...]:
        """Return the canonical import schema."""

        return TARGET_COLUMNS

    @staticmethod
    def template_csv_bytes() -> bytes:
        """Return a UTF-8 CSV template that opens cleanly in Excel."""

        frame = pd.DataFrame(TEMPLATE_ROWS)
        buffer = StringIO()
        frame.to_csv(buffer, index=False)
        return ("\ufeff" + buffer.getvalue()).encode("utf-8")

    @staticmethod
    def template_excel_bytes() -> bytes:
        """Return an Excel template in memory without requiring openpyxl.

        The user can download the template even when the local Python
        environment has not installed Excel-reading dependencies yet. Uploading
        Excel files still requires ``openpyxl`` and is checked separately.
        """

        instructions = [
            {"فیلد": column.label, "اجباری": "بله" if column.required else "خیر", "راهنما": column.help_text}
            for column in TARGET_COLUMNS
        ]
        return _build_minimal_xlsx(
            sheets=(
                ("Drugs", list(TEMPLATE_ROWS)),
                ("Guide", instructions),
            )
        )

    @staticmethod
    def list_excel_sheets(file_bytes: bytes) -> list[str]:
        """Return sheet names for an Excel workbook."""

        _ensure_openpyxl_available()
        try:
            workbook = pd.ExcelFile(BytesIO(file_bytes), engine="openpyxl")
        except Exception as error:  # noqa: BLE001 - pandas/openpyxl exposes several exception types.
            raise ValueError("فایل Excel قابل خواندن نیست. لطفاً قالب فایل را بررسی کنید.") from error
        return [str(sheet) for sheet in workbook.sheet_names]

    @staticmethod
    def read_uploaded_table(file_bytes: bytes, file_name: str, sheet_name: str | None = None) -> pd.DataFrame:
        """Read CSV or Excel bytes into a normalized dataframe."""

        extension = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
        try:
            if extension == "csv":
                frame = DrugImportService._read_csv(file_bytes)
            elif extension == "xlsx":
                _ensure_openpyxl_available()
                frame = pd.read_excel(BytesIO(file_bytes), sheet_name=sheet_name or 0, dtype=object, engine="openpyxl")
            elif extension == "xls":
                raise ValueError("برای پایداری سیستم، فایل XLS قدیمی پشتیبانی نمی‌شود. فایل را با فرمت XLSX یا CSV ذخیره و دوباره بارگذاری کنید.")
            else:
                raise ValueError("فقط فایل‌های CSV و XLSX پشتیبانی می‌شوند.")
        except ValueError:
            raise
        except Exception as error:  # noqa: BLE001 - surface a Persian user-facing message.
            raise ValueError("خواندن فایل ناموفق بود. ساختار فایل یا encoding را بررسی کنید.") from error

        frame = frame.dropna(how="all").copy()
        if frame.empty:
            raise ValueError("فایل بارگذاری‌شده هیچ ردیف قابل پردازشی ندارد.")
        if len(frame) > MAX_IMPORT_ROWS:
            raise ValueError(f"حداکثر {MAX_IMPORT_ROWS} ردیف در هر بار ورود داده پشتیبانی می‌شود.")
        frame.columns = [clean_text(str(column), 120) for column in frame.columns]
        return frame

    @staticmethod
    def build_default_mapping(source_columns: list[str]) -> dict[str, str]:
        """Auto-map uploaded headers to canonical fields when possible."""

        normalized_sources = {_normalize_header(column): column for column in source_columns}
        mapping: dict[str, str] = {}
        for target in TARGET_COLUMNS:
            selected = UNMAPPED_LABEL
            for alias in target.aliases:
                normalized_alias = _normalize_header(alias)
                if normalized_alias in normalized_sources:
                    selected = normalized_sources[normalized_alias]
                    break
            mapping[target.key] = selected
        return mapping

    @staticmethod
    def validate_preview(
        frame: pd.DataFrame,
        file_name: str,
        mapping: dict[str, str],
        options: ImportOptions,
    ) -> ImportPreviewResult:
        """Validate mapped rows and identify duplicate behavior before writing."""

        _validate_mapping(mapping)
        category_map = _reference_map(DrugCategoryRepository.list_all())
        supplier_map = _reference_map(SupplierRepository.list_all())
        seen_keys: set[tuple[str, str]] = set()
        rows: list[ImportRowValidation] = []

        for zero_index, (_, source_row) in enumerate(frame.iterrows()):
            row_number = zero_index + 2
            validation = DrugImportService._validate_row(
                source_row=source_row,
                row_number=row_number,
                mapping=mapping,
                options=options,
                category_map=category_map,
                supplier_map=supplier_map,
                seen_keys=seen_keys,
            )
            rows.append(validation)

        valid_rows = sum(1 for row in rows if row.status in {"valid_create", "valid_update"})
        invalid_rows = sum(1 for row in rows if row.status == "invalid")
        duplicate_rows = sum(1 for row in rows if row.status in {"duplicate_upload", "duplicate_database"})
        create_rows = sum(1 for row in rows if row.status == "valid_create")
        update_rows = sum(1 for row in rows if row.status == "valid_update")
        return ImportPreviewResult(
            file_name=file_name,
            total_rows=len(rows),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            duplicate_rows=duplicate_rows,
            create_rows=create_rows,
            update_rows=update_rows,
            rows=tuple(rows),
        )

    @staticmethod
    def execute_import(
        preview: ImportPreviewResult,
        options: ImportOptions,
        user_id: int | None,
        role_code: str,
    ) -> ImportExecutionSummary:
        """Persist all valid preview rows into the operational database."""

        if not DrugManagementService.can_write(role_code):
            return ImportExecutionSummary(
                success=False,
                message="نقش شما اجازه ورود گروهی داده را ندارد.",
                batch_id=None,
                total_rows=preview.total_rows,
                inserted_rows=0,
                updated_rows=0,
                skipped_rows=preview.total_rows,
                failed_rows=0,
                errors=(),
            )

        inserted = 0
        updated = 0
        failed = 0
        skipped = 0
        errors: list[str] = []

        for row in preview.rows:
            if row.status not in {"valid_create", "valid_update"} or row.payload is None:
                skipped += 1
                continue
            payload = DrugImportService._resolve_references(row, options)
            if payload is None:
                failed += 1
                errors.append(f"ردیف {row.row_number}: دسته‌بندی یا تأمین‌کننده قابل resolve نیست.")
                continue
            if row.status == "valid_update" and row.existing_drug_id:
                result = DrugManagementService.update_drug(row.existing_drug_id, payload, user_id, role_code)
                if result.success:
                    updated += 1
                else:
                    failed += 1
                    errors.append(f"ردیف {row.row_number}: {result.message}")
            else:
                result = DrugManagementService.create_drug(payload, user_id, role_code)
                if result.success:
                    inserted += 1
                else:
                    failed += 1
                    errors.append(f"ردیف {row.row_number}: {result.message}")

        duplicate_rows = sum(1 for row in preview.rows if row.status in {"duplicate_upload", "duplicate_database"})
        batch_id = ImportBatchRepository.create(
            file_name=preview.file_name,
            total_rows=preview.total_rows,
            valid_rows=preview.valid_rows,
            invalid_rows=preview.invalid_rows,
            duplicate_rows=duplicate_rows,
            inserted_rows=inserted,
            updated_rows=updated,
            skipped_rows=skipped,
            user_id=user_id,
        )
        for row in preview.rows:
            if row.status not in {"valid_create", "valid_update"}:
                ImportBatchRepository.add_row_error(batch_id, row.row_number, row.status, " | ".join(row.messages))
        for message in errors:
            ImportBatchRepository.add_row_error(batch_id, 0, "execution_error", message)

        ActivityLogRepository.log(
            user_id,
            "import_drugs",
            "import_batch",
            batch_id,
            f"ورود گروهی داروها: {inserted} ثبت، {updated} به‌روزرسانی، {failed} خطا",
        )
        success = failed == 0 and (inserted + updated) > 0
        if success:
            message = "ورود داده با موفقیت انجام شد."
        elif inserted + updated > 0:
            message = "بخشی از داده‌ها وارد شد اما چند ردیف خطا داشت."
        else:
            message = "هیچ ردیف معتبری وارد نشد."
        return ImportExecutionSummary(
            success=success,
            message=message,
            batch_id=batch_id,
            total_rows=preview.total_rows,
            inserted_rows=inserted,
            updated_rows=updated,
            skipped_rows=skipped,
            failed_rows=failed,
            errors=tuple(errors),
        )

    @staticmethod
    def preview_to_dataframe(preview: ImportPreviewResult) -> pd.DataFrame:
        """Convert preview rows to a Persian dataframe for Streamlit."""

        rows = []
        for row in preview.rows:
            payload = row.payload
            rows.append(
                {
                    "ردیف فایل": row.row_number,
                    "وضعیت": row.status_label,
                    "نام دارو": payload.name if payload else "-",
                    "شماره بچ": payload.batch_number if payload else "-",
                    "تولیدکننده": payload.manufacturer if payload else "-",
                    "موجودی": payload.current_stock if payload else "-",
                    "حداقل موجودی": payload.minimum_stock if payload else "-",
                    "مصرف ماهانه": payload.monthly_consumption if payload else "-",
                    "دسته‌بندی": row.category_name or "-",
                    "تأمین‌کننده": row.supplier_name or "-",
                    "پیام کنترل کیفیت": " | ".join(row.messages) if row.messages else "آماده ورود",
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def latest_imports_dataframe(limit: int = 8) -> pd.DataFrame:
        """Return recent import batches as a Persian dataframe."""

        rows = []
        for item in ImportBatchRepository.latest(limit):
            rows.append(
                {
                    "شناسه": item["id"],
                    "نام فایل": item["file_name"],
                    "کل ردیف": item["total_rows"],
                    "معتبر": item["valid_rows"],
                    "نامعتبر": item["invalid_rows"],
                    "تکراری": item["duplicate_rows"],
                    "ثبت‌شده": item["inserted_rows"],
                    "به‌روزرسانی": item["updated_rows"],
                    "ردشده": item["skipped_rows"],
                    "زمان": item["created_at"],
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _read_csv(file_bytes: bytes) -> pd.DataFrame:
        """Read CSV with common UTF encodings used in Persian spreadsheets."""

        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "cp1256"):
            try:
                return pd.read_csv(BytesIO(file_bytes), dtype=object, encoding=encoding)
            except Exception as error:  # noqa: BLE001 - retry known encodings.
                last_error = error
        raise ValueError("فایل CSV قابل خواندن نیست. لطفاً encoding را UTF-8 قرار دهید.") from last_error

    @staticmethod
    def _validate_row(
        source_row: pd.Series,
        row_number: int,
        mapping: dict[str, str],
        options: ImportOptions,
        category_map: dict[str, int],
        supplier_map: dict[str, int],
        seen_keys: set[tuple[str, str]],
    ) -> ImportRowValidation:
        """Validate one mapped source row."""

        errors: list[str] = []
        warnings: list[str] = []
        values = {target.key: _cell_value(source_row, mapping.get(target.key, UNMAPPED_LABEL)) for target in TARGET_COLUMNS}

        name = clean_text(values["name"], 160)
        generic_name = clean_text(values["generic_name"], 160)
        category_name = clean_text(values["category"], 120)
        manufacturer = clean_text(values["manufacturer"], 160)
        batch_number = clean_text(values["batch_number"], 80)
        supplier_name = clean_text(values["supplier"], 140)
        unit = clean_text(values["unit"], 40) or "عدد"

        if not name:
            errors.append("نام دارو الزامی است.")
        if not manufacturer:
            manufacturer = "ثبت‌نشده"
            warnings.append("تولیدکننده در فایل نبود و به‌صورت «ثبت‌نشده» ذخیره می‌شود.")
        if not batch_number:
            warnings.append("شماره بچ در فایل نبود؛ تکراری‌ها بر اساس نام دارو کنترل می‌شوند.")

        expiration_date = _parse_optional_date(values["expiration_date"], "تاریخ انقضا", warnings)
        current_stock = _parse_optional_non_negative_int(values["current_stock"], "موجودی فعلی", warnings, default=0)
        minimum_stock = _parse_optional_non_negative_int(values["minimum_stock"], "حداقل موجودی", warnings, default=0)
        monthly_consumption = _parse_optional_non_negative_int(values["monthly_consumption"], "مصرف ماهانه", warnings, default=0)
        availability_score = _parse_score(values["availability_score"], errors)

        category_id = category_map.get(_normalize_reference(category_name)) if category_name else None
        supplier_id = supplier_map.get(_normalize_reference(supplier_name)) if supplier_name else None
        if category_name and category_id is None and not options.create_missing_references:
            errors.append(f"دسته‌بندی «{category_name}» در سیستم ثبت نشده است.")
        if supplier_name and supplier_id is None and not options.create_missing_references:
            errors.append(f"تأمین‌کننده «{supplier_name}» در سیستم ثبت نشده است.")
        if category_name and category_id is None and options.create_missing_references:
            warnings.append("دسته‌بندی جدید هنگام ورود ساخته می‌شود.")
        if supplier_name and supplier_id is None and options.create_missing_references:
            warnings.append("تأمین‌کننده جدید هنگام ورود ساخته می‌شود.")

        payload: DrugFormData | None = None
        if not errors:
            payload = DrugManagementService.build_drug_payload(
                name=name,
                generic_name=generic_name,
                category_id=category_id,
                manufacturer=manufacturer,
                batch_number=batch_number,
                expiration_date=expiration_date,
                supplier_id=supplier_id,
                unit=unit,
                current_stock=current_stock,
                minimum_stock=minimum_stock,
                monthly_consumption=monthly_consumption,
                availability_score=availability_score,
            )
            is_valid, message = DrugManagementService.validate_drug_payload(payload)
            if not is_valid:
                errors.append(message)

        source_key = (_normalize_reference(name), _normalize_reference(batch_number)) if name else None
        if source_key and source_key in seen_keys:
            return ImportRowValidation(
                row_number=row_number,
                status="duplicate_upload",
                status_label="تکراری داخل فایل",
                messages=("این دارو قبلاً در همین فایل آمده است؛ اگر شماره بچ وجود داشته باشد، با آن تفکیک می‌شود.",),
                payload=payload,
                category_name=category_name,
                supplier_name=supplier_name,
                existing_drug_id=None,
                source_key=source_key,
            )
        if source_key:
            seen_keys.add(source_key)

        if errors:
            return ImportRowValidation(
                row_number=row_number,
                status="invalid",
                status_label="نامعتبر",
                messages=tuple(errors),
                payload=payload,
                category_name=category_name,
                supplier_name=supplier_name,
                existing_drug_id=None,
                source_key=source_key,
            )

        existing = DrugRepository.get_by_name_and_batch(name, batch_number)
        if existing and options.duplicate_policy == DUPLICATE_SKIP:
            return ImportRowValidation(
                row_number=row_number,
                status="duplicate_database",
                status_label="تکراری در دیتابیس",
                messages=("این دارو قبلاً در دیتابیس ثبت شده و طبق تنظیم فعلی رد می‌شود.",),
                payload=payload,
                category_name=category_name,
                supplier_name=supplier_name,
                existing_drug_id=existing.id,
                source_key=source_key,
            )
        if existing and options.duplicate_policy == DUPLICATE_UPDATE:
            warnings.append("رکورد موجود با داده‌های فایل به‌روزرسانی می‌شود.")
            return ImportRowValidation(
                row_number=row_number,
                status="valid_update",
                status_label="آماده به‌روزرسانی",
                messages=tuple(warnings),
                payload=payload,
                category_name=category_name,
                supplier_name=supplier_name,
                existing_drug_id=existing.id,
                source_key=source_key,
            )

        return ImportRowValidation(
            row_number=row_number,
            status="valid_create",
            status_label="آماده ثبت",
            messages=tuple(warnings),
            payload=payload,
            category_name=category_name,
            supplier_name=supplier_name,
            existing_drug_id=None,
            source_key=source_key,
        )

    @staticmethod
    def _resolve_references(row: ImportRowValidation, options: ImportOptions) -> DrugFormData | None:
        """Resolve missing category/supplier references right before persistence."""

        if row.payload is None:
            return None
        category_id = row.payload.category_id
        supplier_id = row.payload.supplier_id
        if category_id is None and row.category_name and options.create_missing_references:
            category_id = DrugCategoryRepository.get_or_create(row.category_name, "ثبت‌شده از طریق ورود گروهی")
        if supplier_id is None and row.supplier_name and options.create_missing_references:
            supplier_id = SupplierRepository.get_or_create(row.supplier_name)
        return replace(row.payload, category_id=category_id, supplier_id=supplier_id)


def _ensure_openpyxl_available() -> None:
    """Raise a user-friendly error when the Excel reader is missing."""

    if find_spec("openpyxl") is None:
        raise ValueError(
            "برای خواندن فایل Excel باید پکیج openpyxl نصب باشد. "
            "در ترمینال پروژه این دستور را اجرا کنید: pip install -r requirements.txt"
        )


def _build_minimal_xlsx(sheets: tuple[tuple[str, list[dict[str, Any]]], ...]) -> bytes:
    """Build a simple XLSX workbook using only Python's standard library."""

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as workbook_zip:
        workbook_zip.writestr("[Content_Types].xml", _xlsx_content_types(len(sheets)))
        workbook_zip.writestr("_rels/.rels", _xlsx_root_relationships())
        workbook_zip.writestr("xl/workbook.xml", _xlsx_workbook_xml(sheets))
        workbook_zip.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships(len(sheets)))
        workbook_zip.writestr("xl/styles.xml", _xlsx_styles_xml())
        for index, (_, rows) in enumerate(sheets, start=1):
            workbook_zip.writestr(f"xl/worksheets/sheet{index}.xml", _xlsx_sheet_xml(rows))
    return buffer.getvalue()


def _xlsx_content_types(sheet_count: int) -> str:
    """Return XLSX content types."""

    sheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        f'{sheet_overrides}'
        '</Types>'
    )


def _xlsx_root_relationships() -> str:
    """Return package root relationships."""

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '</Relationships>'
    )


def _xlsx_workbook_xml(sheets: tuple[tuple[str, list[dict[str, Any]]], ...]) -> str:
    """Return workbook XML with sheet names."""

    sheet_xml = "".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, (name, _) in enumerate(sheets, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets>{sheet_xml}</sheets>'
        '</workbook>'
    )


def _xlsx_workbook_relationships(sheet_count: int) -> str:
    """Return workbook relationships."""

    sheet_relationships = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f'{sheet_relationships}'
        f'<Relationship Id="rId{styles_id}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        '</Relationships>'
    )


def _xlsx_styles_xml() -> str:
    """Return minimal workbook styles."""

    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Arial"/></font></fonts>'
        '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '</styleSheet>'
    )


def _xlsx_sheet_xml(rows: list[dict[str, Any]]) -> str:
    """Return one worksheet XML using inline strings."""

    headers = list(rows[0].keys()) if rows else []
    xml_rows = [_xlsx_row_xml(1, headers)]
    for row_index, row in enumerate(rows, start=2):
        xml_rows.append(_xlsx_row_xml(row_index, [row.get(header, "") for header in headers]))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData>'
        '</worksheet>'
    )


def _xlsx_row_xml(row_index: int, values: list[Any]) -> str:
    """Return one worksheet row."""

    cells = "".join(_xlsx_cell_xml(row_index, column_index, value) for column_index, value in enumerate(values, start=1))
    return f'<row r="{row_index}">{cells}</row>'


def _xlsx_cell_xml(row_index: int, column_index: int, value: Any) -> str:
    """Return one inline-string cell."""

    cell_ref = f"{_column_letter(column_index)}{row_index}"
    escaped_value = xml_escape(str(value))
    return f'<c r="{cell_ref}" t="inlineStr"><is><t>{escaped_value}</t></is></c>'


def _column_letter(index: int) -> str:
    """Convert a one-based column number to an Excel column letter."""

    letters = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _validate_mapping(mapping: dict[str, str]) -> None:
    """Validate that all required target columns are mapped."""

    missing = [column.label for column in TARGET_COLUMNS if column.required and mapping.get(column.key) == UNMAPPED_LABEL]
    if missing:
        joined = "، ".join(missing)
        raise ValueError(f"ستون‌های اجباری مپ نشده‌اند: {joined}")


def _reference_map(items: list[Any]) -> dict[str, int]:
    """Build a normalized name-to-id map for categories and suppliers."""

    return {_normalize_reference(item.name): int(item.id) for item in items}


def _cell_value(row: pd.Series, column_name: str | None) -> str:
    """Return one cell as a clean string from a mapped column."""

    if not column_name or column_name == UNMAPPED_LABEL or column_name not in row.index:
        return ""
    value = row[column_name]
    if pd.isna(value):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def _parse_optional_non_negative_int(
    value: str,
    field_name: str,
    warnings: list[str],
    default: int = 0,
) -> int:
    """Parse an optional non-negative integer used by flexible imports."""

    normalized = _normalize_number(value)
    if normalized == "":
        warnings.append(f"{field_name} در فایل نبود و مقدار پیش‌فرض {default} ثبت می‌شود.")
        return default
    try:
        number = int(float(normalized))
    except ValueError:
        warnings.append(f"{field_name} قابل تبدیل به عدد نبود و مقدار پیش‌فرض {default} ثبت شد.")
        return default
    if number < 0:
        warnings.append(f"{field_name} منفی بود و مقدار پیش‌فرض {default} ثبت شد.")
        return default
    return number


def _parse_score(value: str, errors: list[str]) -> float:
    """Parse availability score as 0..1, accepting percent-like 0..100 values."""

    normalized = _normalize_number(value)
    if normalized == "":
        return 0.75
    try:
        score = float(normalized)
    except ValueError:
        errors.append("شاخص دسترسی بازار باید عددی بین ۰ و ۱ باشد.")
        return 0.75
    if score > 1 and score <= 100:
        score = score / 100
    if score < 0 or score > 1:
        errors.append("شاخص دسترسی بازار باید بین ۰ و ۱ باشد.")
        return 0.75
    return round(score, 3)


def _parse_optional_date(value: str, field_name: str, warnings: list[str]) -> date | None:
    """Parse optional Gregorian date strings without rejecting the whole row."""

    normalized = clean_text(value.translate(PERSIAN_TO_LATIN_DIGITS), 40).replace("/", "-")
    if not normalized:
        warnings.append(f"{field_name} در فایل نبود؛ هشدارهای انقضا برای این ردیف فعال نمی‌شود.")
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y", "%m-%d-%Y"):
        try:
            parsed = datetime.strptime(normalized, fmt).date()
            return parsed
        except ValueError:
            continue
    try:
        parsed_any = pd.to_datetime(normalized, errors="raise").date()
        return parsed_any
    except Exception:  # noqa: BLE001 - final fallback for parsing.
        warnings.append(f"{field_name} قابل خواندن نبود و خالی ذخیره شد.")
        return None


def _normalize_number(value: str) -> str:
    """Normalize Persian/Arabic digits and common separators."""

    return (
        clean_text(value, 80)
        .translate(PERSIAN_TO_LATIN_DIGITS)
        .replace(",", "")
        .replace("،", "")
        .replace("٪", "")
        .replace("%", "")
    )


def _normalize_header(value: str) -> str:
    """Normalize column headers for auto-mapping."""

    return clean_text(value, 140).replace("_", " ").replace("-", " ").casefold()


def _normalize_reference(value: str) -> str:
    """Normalize entity references for duplicate and lookup checks."""

    return clean_text(value, 180).casefold()
