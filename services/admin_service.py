"""Admin control-plane business logic for PharmaGuard AI."""

from __future__ import annotations

import sqlite3
from typing import Any

from database.repositories import ActivityLogRepository, AdminRepository
from utils.validators import clean_text, validate_email, validate_password_strength


ROLE_OPTIONS: dict[str, str] = {
    "مدیر سامانه": "administrator",
    "مدیر بیمارستان": "hospital_manager",
    "مدیر داروخانه": "pharmacy_manager",
    "سازمان درمانی": "healthcare_org",
    "پژوهشگر": "researcher",
    "کاربر مشاهده‌گر": "viewer",
}

ROLE_LABEL_BY_CODE: dict[str, str] = {value: key for key, value in ROLE_OPTIONS.items()}

STATUS_OPTIONS: dict[str, str] = {
    "فعال": "active",
    "غیرفعال": "inactive",
    "در انتظار تأیید": "pending",
    "تأیید شده": "approved",
    "رد شده": "rejected",
    "تعلیق شده": "suspended",
}

STATUS_LABEL_BY_CODE: dict[str, str] = {value: key for key, value in STATUS_OPTIONS.items()}

HOSPITAL_TYPE_OPTIONS: dict[str, str] = {
    "عمومی": "general",
    "تخصصی": "specialty",
    "آموزشی": "teaching",
    "فوق تخصصی": "tertiary",
}

HOSPITAL_TYPE_LABEL_BY_CODE: dict[str, str] = {value: key for key, value in HOSPITAL_TYPE_OPTIONS.items()}

PHARMACY_SERVICE_OPTIONS: dict[str, str] = {
    "خرده‌فروشی": "retail",
    "بیمارستانی": "hospital",
    "شبانه‌روزی": "24h",
    "توزیع سازمانی": "institutional",
}

PHARMACY_SERVICE_LABEL_BY_CODE: dict[str, str] = {
    value: key for key, value in PHARMACY_SERVICE_OPTIONS.items()
}


class AdminAccessError(PermissionError):
    """Raised when a non-admin user attempts to use admin controls."""


class AdminService:
    """Coordinate admin workflows, validation, and audit logging."""

    @staticmethod
    def assert_admin(user: dict[str, Any] | None) -> None:
        """Ensure the current user has administrator privileges."""

        if not user or user.get("role_code") != "administrator":
            raise AdminAccessError("این بخش فقط برای مدیر سامانه فعال است.")

    @staticmethod
    def overview() -> dict[str, int]:
        """Return control-plane metrics."""

        return AdminRepository.system_overview()

    @staticmethod
    def users(search: str = "", role_code: str = "all", status: str = "all") -> list[dict[str, Any]]:
        """Return filtered users."""

        return AdminRepository.list_users(search, role_code, status)

    @staticmethod
    def create_user(
        admin_user_id: int | None,
        full_name: str,
        email: str,
        password: str,
        role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
        is_active: bool,
    ) -> int:
        """Validate and create a user from the admin panel."""

        cleaned_name = clean_text(full_name, 120)
        cleaned_email = email.strip().lower()
        if len(cleaned_name) < 3:
            raise ValueError("نام کامل باید حداقل ۳ کاراکتر باشد.")
        if not validate_email(cleaned_email):
            raise ValueError("ایمیل واردشده معتبر نیست.")
        is_strong, message = validate_password_strength(password)
        if not is_strong:
            raise ValueError(message)
        hospital_scope, pharmacy_scope = AdminService._normalize_scope(
            role_code,
            hospital_id,
            pharmacy_id,
        )
        try:
            user_id = AdminRepository.create_user(
                full_name=cleaned_name,
                email=cleaned_email,
                password=password,
                role_code=role_code,
                hospital_id=hospital_scope,
                pharmacy_id=pharmacy_scope,
                is_active=is_active,
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("این ایمیل قبلاً ثبت شده است.") from error
        ActivityLogRepository.log(
            admin_user_id,
            "admin_create_user",
            "user",
            user_id,
            f"کاربر {cleaned_email} از پنل مدیریت ساخته شد.",
        )
        return user_id

    @staticmethod
    def update_user_scope(
        admin_user_id: int | None,
        user_id: int,
        role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
        is_active: bool,
    ) -> None:
        """Update role, organization scope, and status for one user."""

        hospital_scope, pharmacy_scope = AdminService._normalize_scope(
            role_code,
            hospital_id,
            pharmacy_id,
        )
        AdminRepository.update_user_scope(
            user_id,
            role_code,
            hospital_scope,
            pharmacy_scope,
            is_active,
        )
        ActivityLogRepository.log(
            admin_user_id,
            "admin_update_user_scope",
            "user",
            user_id,
            "نقش، سازمان یا وضعیت حساب کاربر از پنل مدیریت تغییر کرد.",
        )

    @staticmethod
    def reset_password(admin_user_id: int | None, user_id: int, new_password: str) -> None:
        """Reset a user's password after strength validation."""

        is_strong, message = validate_password_strength(new_password)
        if not is_strong:
            raise ValueError(message)
        AdminRepository.reset_user_password(user_id, new_password)
        ActivityLogRepository.log(
            admin_user_id,
            "admin_reset_password",
            "user",
            user_id,
            "رمز عبور کاربر توسط مدیر سامانه بازنشانی شد.",
        )

    @staticmethod
    def pending_requests() -> list[dict[str, Any]]:
        """Return self-registration requests awaiting approval."""

        return AdminRepository.pending_registration_requests()

    @staticmethod
    def review_registration_request(
        admin_user_id: int | None,
        user_id: int,
        decision: str,
        final_role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
        notes: str = "",
    ) -> None:
        """Approve or reject a pending user with role and organization scope."""

        hospital_scope, pharmacy_scope = AdminService._normalize_scope(
            final_role_code,
            hospital_id,
            pharmacy_id,
        )
        AdminRepository.review_registration_request(
            user_id=user_id,
            final_role_code=final_role_code,
            hospital_id=hospital_scope,
            pharmacy_id=pharmacy_scope,
            decision=decision,
            admin_user_id=admin_user_id,
            notes=clean_text(notes, 300),
        )
        ActivityLogRepository.log(
            admin_user_id,
            f"admin_registration_{decision}",
            "user",
            user_id,
            "درخواست ثبت‌نام عمومی توسط مدیر سامانه بررسی شد.",
        )

    @staticmethod
    def hospitals(search: str = "", status: str = "all") -> list[dict[str, Any]]:
        """Return managed hospitals."""

        return AdminRepository.list_hospitals(search, status)

    @staticmethod
    def save_hospital(admin_user_id: int | None, data: dict[str, Any], hospital_id: int | None = None) -> int:
        """Create or update a hospital after validation."""

        payload = AdminService._validate_hospital(data)
        try:
            if hospital_id:
                AdminRepository.update_hospital(hospital_id, payload)
                entity_id = hospital_id
                action = "admin_update_hospital"
            else:
                entity_id = AdminRepository.create_hospital(payload)
                action = "admin_create_hospital"
        except sqlite3.IntegrityError as error:
            raise ValueError("نام یا کد بیمارستان تکراری است.") from error
        ActivityLogRepository.log(
            admin_user_id,
            action,
            "hospital",
            entity_id,
            f"رکورد بیمارستان {payload['name']} از پنل مدیریت ذخیره شد.",
        )
        return entity_id

    @staticmethod
    def pharmacies(search: str = "", status: str = "all") -> list[dict[str, Any]]:
        """Return managed pharmacies."""

        return AdminRepository.list_pharmacies(search, status)

    @staticmethod
    def save_pharmacy(admin_user_id: int | None, data: dict[str, Any], pharmacy_id: int | None = None) -> int:
        """Create or update a pharmacy after validation."""

        payload = AdminService._validate_pharmacy(data)
        try:
            if pharmacy_id:
                AdminRepository.update_pharmacy(pharmacy_id, payload)
                entity_id = pharmacy_id
                action = "admin_update_pharmacy"
            else:
                entity_id = AdminRepository.create_pharmacy(payload)
                action = "admin_create_pharmacy"
        except sqlite3.IntegrityError as error:
            raise ValueError("نام یا شماره مجوز داروخانه تکراری است.") from error
        ActivityLogRepository.log(
            admin_user_id,
            action,
            "pharmacy",
            entity_id,
            f"رکورد داروخانه {payload['name']} از پنل مدیریت ذخیره شد.",
        )
        return entity_id

    @staticmethod
    def roles() -> list[dict[str, Any]]:
        """Return roles."""

        return AdminRepository.list_roles()

    @staticmethod
    def permissions() -> list[dict[str, Any]]:
        """Return permission catalog."""

        return AdminRepository.list_permissions()

    @staticmethod
    def role_permissions() -> list[dict[str, Any]]:
        """Return role-to-permission matrix rows."""

        return AdminRepository.list_role_permissions()

    @staticmethod
    def activity(limit: int = 80) -> list[dict[str, Any]]:
        """Return recent activity logs."""

        return AdminRepository.recent_activity(limit)

    @staticmethod
    def organization_options() -> dict[str, list[dict[str, Any]]]:
        """Return organization options for user assignment."""

        return AdminRepository.organization_options()

    @staticmethod
    def _normalize_scope(
        role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
    ) -> tuple[int | None, int | None]:
        """Keep user organization scope consistent with selected role."""

        if role_code == "hospital_manager":
            return hospital_id, None
        if role_code == "pharmacy_manager":
            return None, pharmacy_id
        if role_code in {"administrator", "researcher", "viewer", "healthcare_org"}:
            return hospital_id, pharmacy_id
        return None, None

    @staticmethod
    def _validate_hospital(data: dict[str, Any]) -> dict[str, Any]:
        """Validate hospital payload."""

        name = clean_text(str(data.get("name", "")), 160)
        if len(name) < 3:
            raise ValueError("نام بیمارستان باید حداقل ۳ کاراکتر باشد.")
        bed_count = int(data.get("bed_count", 0))
        if bed_count < 0:
            raise ValueError("تعداد تخت نمی‌تواند منفی باشد.")
        return {
            "name": name,
            "code": clean_text(str(data.get("code", "")), 50),
            "province": clean_text(str(data.get("province", "")), 80),
            "city": clean_text(str(data.get("city", "")), 80),
            "type": str(data.get("type", "general")),
            "bed_count": bed_count,
            "manager_name": clean_text(str(data.get("manager_name", "")), 120),
            "contact_phone": clean_text(str(data.get("contact_phone", "")), 40),
            "address": clean_text(str(data.get("address", "")), 255),
            "status": str(data.get("status", "active")),
        }

    @staticmethod
    def _validate_pharmacy(data: dict[str, Any]) -> dict[str, Any]:
        """Validate pharmacy payload."""

        name = clean_text(str(data.get("name", "")), 160)
        if len(name) < 3:
            raise ValueError("نام داروخانه باید حداقل ۳ کاراکتر باشد.")
        return {
            "name": name,
            "city": clean_text(str(data.get("city", "")), 80),
            "license_number": clean_text(str(data.get("license_number", "")), 80),
            "owner_name": clean_text(str(data.get("owner_name", "")), 120),
            "contact_phone": clean_text(str(data.get("contact_phone", "")), 40),
            "address": clean_text(str(data.get("address", "")), 255),
            "service_level": str(data.get("service_level", "retail")),
            "status": str(data.get("status", "active")),
        }
