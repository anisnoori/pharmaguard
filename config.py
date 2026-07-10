"""Central configuration for PharmaGuard AI.

All application-wide constants live here so pages and services avoid
hard-coded paths, labels, and security values.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

DATA_DIR = BASE_DIR / "database"
ASSETS_DIR = BASE_DIR / "assets"
STYLE_DIR = ASSETS_DIR / "styles"
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
LOG_DIR = BASE_DIR / "logs"
DB_PATH = DATA_DIR / "pharmaguard.db"


@dataclass(frozen=True)
class AppConfig:
    """Immutable runtime settings used throughout the application."""

    app_name: str = "PharmaGuard AI"
    app_name_fa: str = "فارماگارد هوشمند"
    page_title: str = "PharmaGuard AI | پایش هوشمند زنجیره تأمین دارو"
    page_icon: str = str(ASSETS_DIR / "icons" / "logo.svg")
    default_language: str = "fa"
    default_theme: str = os.getenv("PHARMAGUARD_DEFAULT_THEME", "light").lower()
    bootstrap_admin_email: str = os.getenv("PHARMAGUARD_ADMIN_EMAIL", "anisgulnoori93@gmail.com").strip().lower()
    bootstrap_admin_password: str = os.getenv("PHARMAGUARD_ADMIN_PASSWORD", "ChangeThisStrongPasswordBeforeDeploy")
    bootstrap_admin_name: str = os.getenv("PHARMAGUARD_ADMIN_NAME", "Anisgul Noori")
    session_timeout_minutes: int = 45
    password_iterations: int = 260_000
    database_url: str = f"sqlite:///{DB_PATH}"
    environment: str = os.getenv("APP_ENV", "development")


ROLE_LABELS: dict[str, str] = {
    "administrator": "مدیر سامانه",
    "hospital_manager": "مدیر بیمارستان",
    "pharmacy_manager": "مدیر داروخانه",
    "healthcare_org": "سازمان درمانی",
    "researcher": "پژوهشگر",
    "viewer": "کاربر مشاهده‌گر",
}


RISK_LABELS: dict[str, str] = {
    "critical": "بحرانی",
    "high": "زیاد",
    "medium": "متوسط",
    "low": "کم",
}


INTERACTION_SEVERITY_LABELS: dict[str, str] = {
    "contraindicated": "منع مصرف همزمان",
    "high": "شدید",
    "medium": "متوسط",
    "low": "خفیف",
}


INTERACTION_SEVERITY_ORDER: dict[str, int] = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "contraindicated": 4,
}


def ensure_directories() -> None:
    """Create runtime directories if they do not exist."""

    for directory in (DATA_DIR, UPLOAD_DIR, REPORT_DIR, LOG_DIR):
        directory.mkdir(parents=True, exist_ok=True)


settings = AppConfig()
