"""Persian localization helpers."""

from __future__ import annotations

from datetime import date, datetime

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def fa_number(value: int | float | str) -> str:
    """Convert Latin digits in a value to Persian digits."""

    return str(value).translate(PERSIAN_DIGITS)


def percent_fa(value: float, digits: int = 0) -> str:
    """Format a decimal ratio as a Persian percentage."""

    formatted = f"{value * 100:.{digits}f}%"
    return fa_number(formatted)


def format_iso_date_fa(value: str | None) -> str:
    """Format an ISO date string with Persian digits."""

    if not value:
        return "ثبت نشده"
    return fa_number(value)


def parse_iso_date(value: str | None) -> date | None:
    """Parse an ISO date string safely."""

    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def days_until(value: str | None) -> int | None:
    """Return remaining days until an ISO date."""

    parsed = parse_iso_date(value)
    if parsed is None:
        return None
    return (parsed - date.today()).days
