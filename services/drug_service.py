"""Business service for drug-management workflows."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from database.repositories import (
    ActivityLogRepository,
    DrugCategoryRepository,
    DrugRepository,
    SupplierRepository,
)
from models.entities import DrugFormData, DrugRecord
from utils.validators import (
    clean_text,
    validate_batch_number,
    validate_future_or_present_date,
    validate_non_negative_int,
    validate_score,
)


@dataclass(frozen=True)
class ServiceResult:
    """Standard result object for mutation operations."""

    success: bool
    message: str
    entity_id: int | None = None


class DrugManagementService:
    """Coordinate validation, persistence, and audit logging for drugs."""

    WRITE_ROLES = {"administrator", "hospital_manager", "pharmacy_manager", "healthcare_org"}
    DELETE_ROLES = {"administrator", "hospital_manager", "pharmacy_manager"}

    @classmethod
    def can_write(cls, role_code: str) -> bool:
        """Return whether the role can create or update inventory data."""

        return role_code in cls.WRITE_ROLES

    @classmethod
    def can_delete(cls, role_code: str) -> bool:
        """Return whether the role can delete drug records."""

        return role_code in cls.DELETE_ROLES

    @staticmethod
    def build_drug_payload(
        name: str,
        generic_name: str,
        category_id: int | None,
        manufacturer: str,
        batch_number: str,
        expiration_date: date | None,
        supplier_id: int | None,
        unit: str,
        current_stock: int,
        minimum_stock: int,
        monthly_consumption: int,
        availability_score: float,
    ) -> DrugFormData:
        """Normalize form values into a typed payload."""

        return DrugFormData(
            name=clean_text(name, 160),
            generic_name=clean_text(generic_name, 160),
            category_id=category_id,
            manufacturer=clean_text(manufacturer, 160),
            batch_number=clean_text(batch_number, 80),
            expiration_date=expiration_date,
            supplier_id=supplier_id,
            unit=clean_text(unit, 40) or "عدد",
            current_stock=int(current_stock),
            minimum_stock=int(minimum_stock),
            monthly_consumption=int(monthly_consumption),
            availability_score=round(float(availability_score), 3),
        )

    @staticmethod
    def validate_drug_payload(data: DrugFormData) -> tuple[bool, str]:
        """Validate all business rules for drug inventory records."""

        if len(data.name) < 2:
            return False, "نام دارو باید حداقل ۲ کاراکتر باشد."
        # Manufacturer is important for traceability but optional because
        # many pharmacy exports do not include it. Missing values are kept as
        # "ثبت‌نشده" by import workflows.
        batch_valid, batch_message = validate_batch_number(data.batch_number)
        if not batch_valid:
            return False, batch_message
        for field_name, value in (
            ("موجودی فعلی", data.current_stock),
            ("حداقل موجودی", data.minimum_stock),
            ("مصرف ماهانه", data.monthly_consumption),
        ):
            is_valid, message = validate_non_negative_int(value, field_name)
            if not is_valid:
                return False, message
        score_valid, score_message = validate_score(data.availability_score, "شاخص دسترسی بازار")
        if not score_valid:
            return False, score_message
        date_valid, date_message = validate_future_or_present_date(data.expiration_date, "تاریخ انقضا")
        if not date_valid:
            return False, date_message
        return True, "اطلاعات دارو معتبر است."

    @classmethod
    def create_drug(
        cls,
        data: DrugFormData,
        user_id: int | None,
        role_code: str,
    ) -> ServiceResult:
        """Create a validated drug record."""

        if not cls.can_write(role_code):
            return ServiceResult(False, "نقش شما اجازه ثبت داروی جدید ندارد.")
        is_valid, message = cls.validate_drug_payload(data)
        if not is_valid:
            return ServiceResult(False, message)
        try:
            drug_id = DrugRepository.create(data)
            ActivityLogRepository.log(
                user_id,
                "create_drug",
                "drug",
                drug_id,
                f"ثبت دارو: {data.name} / بچ: {data.batch_number}",
            )
            return ServiceResult(True, "دارو با موفقیت ثبت شد.", drug_id)
        except sqlite3.IntegrityError:
            return ServiceResult(False, "این ترکیب نام دارو و شماره بچ قبلاً ثبت شده است.")

    @classmethod
    def update_drug(
        cls,
        drug_id: int,
        data: DrugFormData,
        user_id: int | None,
        role_code: str,
    ) -> ServiceResult:
        """Update a validated drug record."""

        if not cls.can_write(role_code):
            return ServiceResult(False, "نقش شما اجازه ویرایش دارو را ندارد.")
        is_valid, message = cls.validate_drug_payload(data)
        if not is_valid:
            return ServiceResult(False, message)
        try:
            DrugRepository.update(drug_id, data)
            ActivityLogRepository.log(
                user_id,
                "update_drug",
                "drug",
                drug_id,
                f"ویرایش دارو: {data.name} / بچ: {data.batch_number}",
            )
            return ServiceResult(True, "اطلاعات دارو با موفقیت به‌روزرسانی شد.", drug_id)
        except sqlite3.IntegrityError:
            return ServiceResult(False, "این ترکیب نام دارو و شماره بچ برای داروی دیگری ثبت شده است.")
        except ValueError as error:
            return ServiceResult(False, str(error))

    @classmethod
    def delete_drug(
        cls,
        record: DrugRecord,
        user_id: int | None,
        role_code: str,
    ) -> ServiceResult:
        """Delete a drug record when the role is authorized."""

        if not cls.can_delete(role_code):
            return ServiceResult(False, "نقش شما اجازه حذف دارو را ندارد.")
        try:
            DrugRepository.delete(record.id)
            ActivityLogRepository.log(
                user_id,
                "delete_drug",
                "drug",
                record.id,
                f"حذف دارو: {record.name} / بچ: {record.batch_number}",
            )
            return ServiceResult(True, "دارو با موفقیت حذف شد.")
        except ValueError as error:
            return ServiceResult(False, str(error))

    @staticmethod
    def create_category(name: str, description: str, user_id: int | None) -> ServiceResult:
        """Create a drug category with validation and audit log."""

        cleaned_name = clean_text(name, 120)
        cleaned_description = clean_text(description, 300)
        if len(cleaned_name) < 2:
            return ServiceResult(False, "نام دسته‌بندی باید حداقل ۲ کاراکتر باشد.")
        try:
            category_id = DrugCategoryRepository.create(cleaned_name, cleaned_description)
            ActivityLogRepository.log(
                user_id,
                "create_category",
                "drug_category",
                category_id,
                cleaned_name,
            )
            return ServiceResult(True, "دسته‌بندی جدید ثبت شد.", category_id)
        except sqlite3.IntegrityError:
            return ServiceResult(False, "این دسته‌بندی قبلاً ثبت شده است.")

    @staticmethod
    def create_supplier(
        name: str,
        city: str,
        reliability_score: float,
        average_lead_time_days: int,
        user_id: int | None,
    ) -> ServiceResult:
        """Create a supplier with validation and audit log."""

        cleaned_name = clean_text(name, 140)
        cleaned_city = clean_text(city, 80)
        if len(cleaned_name) < 2:
            return ServiceResult(False, "نام تأمین‌کننده باید حداقل ۲ کاراکتر باشد.")
        score_valid, score_message = validate_score(reliability_score, "امتیاز اعتماد تأمین‌کننده")
        if not score_valid:
            return ServiceResult(False, score_message)
        if average_lead_time_days < 1 or average_lead_time_days > 180:
            return ServiceResult(False, "زمان تأمین باید بین ۱ تا ۱۸۰ روز باشد.")
        try:
            supplier_id = SupplierRepository.create(
                cleaned_name,
                cleaned_city,
                round(float(reliability_score), 3),
                int(average_lead_time_days),
            )
            ActivityLogRepository.log(
                user_id,
                "create_supplier",
                "supplier",
                supplier_id,
                cleaned_name,
            )
            return ServiceResult(True, "تأمین‌کننده جدید ثبت شد.", supplier_id)
        except sqlite3.IntegrityError:
            return ServiceResult(False, "این تأمین‌کننده قبلاً ثبت شده است.")
