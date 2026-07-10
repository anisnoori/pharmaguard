"""Reusable validation functions for forms and imports."""

from __future__ import annotations

import re
from datetime import date

EMAIL_PATTERN = re.compile(r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$", re.IGNORECASE)
SAFE_BATCH_PATTERN = re.compile(r"^[\w\-\/\.\u0600-\u06FF ]+$", re.UNICODE)


def validate_email(email: str) -> bool:
    """Return True when an email address has a safe, common format."""

    return bool(EMAIL_PATTERN.fullmatch(email.strip()))


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate minimum password strength for healthcare accounts."""

    if len(password) < 8:
        return False, "رمز عبور باید حداقل ۸ کاراکتر باشد."
    if not re.search(r"[A-Za-z]", password):
        return False, "رمز عبور باید حداقل یک حرف داشته باشد."
    if not re.search(r"\d", password):
        return False, "رمز عبور باید حداقل یک عدد داشته باشد."
    return True, "رمز عبور معتبر است."


def clean_text(value: str, max_length: int = 255) -> str:
    """Normalize short user-provided text fields."""

    return " ".join(value.strip().split())[:max_length]


def validate_non_negative_int(value: int, field_name: str) -> tuple[bool, str]:
    """Validate that integer inventory values are not negative."""

    if value < 0:
        return False, f"{field_name} نمی‌تواند منفی باشد."
    return True, "معتبر است."


def validate_score(value: float, field_name: str) -> tuple[bool, str]:
    """Validate ratio scores used by risk and supplier models."""

    if value < 0 or value > 1:
        return False, f"{field_name} باید بین ۰ و ۱ باشد."
    return True, "معتبر است."


def validate_future_or_present_date(value: date | None, field_name: str) -> tuple[bool, str]:
    """Validate date fields while allowing empty optional dates."""

    if value is None:
        return True, "معتبر است."
    if value < date.today():
        return False, f"{field_name} نمی‌تواند گذشته باشد."
    return True, "معتبر است."


def validate_batch_number(value: str) -> tuple[bool, str]:
    """Validate batch numbers with a conservative character allow-list."""

    cleaned = clean_text(value, 80)
    if not cleaned:
        return True, "شماره بچ ثبت نشده است."
    if not SAFE_BATCH_PATTERN.fullmatch(cleaned):
        return False, "شماره بچ فقط می‌تواند شامل حرف، عدد، فاصله، خط تیره، اسلش و نقطه باشد."
    return True, "معتبر است."
