"""Initial reference and operational seed data for PharmaGuard AI."""

from __future__ import annotations

import json

from auth.security import PasswordHasher
from config import settings
from database.connection import db_session
from services.drug_reference_service import REFERENCES

ROLES: tuple[tuple[str, str, str], ...] = (
    ("administrator", "مدیر سامانه", "دسترسی کامل به مدیریت سامانه و داده‌های کلان."),
    ("hospital_manager", "مدیر بیمارستان", "مدیریت موجودی، هشدارها و گزارش‌های بیمارستان."),
    ("pharmacy_manager", "مدیر داروخانه", "مدیریت موجودی داروخانه، تأمین‌کننده‌ها و هشدارها."),
    ("healthcare_org", "سازمان درمانی", "پایش زنجیره تأمین در سطح سازمان."),
    ("researcher", "پژوهشگر", "تحلیل داده‌ها و بررسی روندهای کمبود دارو."),
    ("viewer", "کاربر مشاهده‌گر", "دسترسی محدود برای مشاهده گزارش‌ها."),
)

DRUG_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("آنتی‌بیوتیک", "داروهای ضدعفونت و درمان عفونت‌های باکتریایی."),
    ("قلب و عروق", "داروهای مرتبط با فشار خون، قلب و گردش خون."),
    ("ضددرد", "داروهای تسکین درد و کنترل التهاب."),
    ("دیابت", "داروهای کنترل قند خون و دیابت."),
    ("گوارش", "داروهای مرتبط با معده، روده و کنترل اسید."),
)

SUPPLIERS: tuple[tuple[str, str, float, int], ...] = (
    ("تأمین سلامت البرز", "تهران", 0.88, 5),
    ("دارورسان شرق", "مشهد", 0.76, 9),
    ("پخش درمان نوین", "اصفهان", 0.82, 7),
)

DRUGS: tuple[tuple[str, str, int, str, str, str, int, int, int, int, float], ...] = (
    ("آموکسی‌سیلین ۵۰۰", "Amoxicillin", 1, "داروسازی سیناژن", "AMX-1403-A", "2027-05-20", 1, 95, 180, 240, 0.72),
    ("انسولین رگولار", "Regular Insulin", 4, "داروسازی سلامت", "INS-1403-R", "2027-02-10", 1, 32, 80, 110, 0.58),
    ("وارفارین ۵", "Warfarin", 2, "داروسازی سپید", "WRF-1403-W", "2026-12-15", 1, 45, 60, 70, 0.64),
    ("استامینوفن ۵۰۰", "Acetaminophen", 3, "داروسازی نوین", "ACM-1403-P", "2028-01-30", 1, 890, 250, 500, 0.93),
    ("آسپرین ۸۰", "Aspirin", 2, "داروسازی سپید", "ASP-1403-L", "2027-08-01", 2, 260, 120, 180, 0.81),
    ("ایبوپروفن ۴۰۰", "Ibuprofen", 3, "داروسازی نوین", "IBU-1403-P", "2027-10-14", 2, 410, 130, 220, 0.86),
    ("متفورمین ۵۰۰", "Metformin", 4, "داروسازی سلامت", "MET-1403-D", "2028-03-19", 3, 370, 160, 260, 0.84),
    ("امپرازول ۲۰", "Omeprazole", 5, "داروسازی سیناژن", "OMP-1403-G", "2027-11-05", 3, 185, 90, 130, 0.79),
    ("آتورواستاتین ۲۰", "Atorvastatin", 2, "تأمین بین‌الملل سلامت", "ATV-1404-20", "2028-06-12", 2, 310, 140, 210, 0.83),
    ("آملودیپین ۵", "Amlodipine", 2, "داروسازی سلامت", "AML-1404-05", "2028-04-22", 1, 260, 100, 160, 0.86),
    ("لوزارتان ۵۰", "Losartan", 2, "پخش درمان نوین", "LOS-1404-50", "2028-02-18", 3, 190, 120, 170, 0.76),
    ("لووتیروکسین ۱۰۰", "Levothyroxine", 4, "داروسازی سیناژن", "LTX-1404-100", "2027-09-08", 1, 75, 110, 150, 0.69),
    ("سفیکسیم ۴۰۰", "Cefixime", 1, "داروسازی نوین", "CFX-1404-400", "2027-12-03", 2, 88, 130, 190, 0.71),
)

PERMISSIONS: tuple[tuple[str, str, str, str], ...] = (
    ("dashboard.view", "مشاهده داشبورد", "dashboard", "دسترسی به داشبورد نقش‌محور."),
    ("drugs.manage", "مدیریت دارو", "inventory", "ثبت، ویرایش و حذف داروها."),
    ("imports.manage", "ورود داده", "data", "آپلود و اعتبارسنجی CSV و Excel."),
    ("scanner.use", "استفاده از اسکن دارو", "ai", "اسکن و تحلیل تصویر یا متن بسته دارو."),
    ("predictions.run", "اجرای پیش‌بینی AI", "ai", "اجرای تحلیل ریسک کمبود دارو."),
    ("interactions.manage", "مدیریت تداخل دارویی", "clinical", "بررسی و مدیریت دانشنامه تداخل دارویی."),
    ("reports.view", "مشاهده گزارش‌ها", "analytics", "دسترسی به گزارش‌های مدیریتی."),
    ("notifications.manage", "مدیریت هشدارها", "operations", "مشاهده و پیگیری هشدارهای عملیاتی."),
    ("admin.manage", "مدیریت سامانه", "admin", "دسترسی کامل به پنل ادمین، کاربران و سازمان‌ها."),
)


ROLE_PERMISSION_MAP: dict[str, tuple[str, ...]] = {
    "administrator": tuple(permission[0] for permission in PERMISSIONS),
    "hospital_manager": (
        "dashboard.view",
        "drugs.manage",
        "imports.manage",
        "scanner.use",
        "predictions.run",
        "interactions.manage",
        "reports.view",
        "notifications.manage",
    ),
    "pharmacy_manager": (
        "dashboard.view",
        "drugs.manage",
        "imports.manage",
        "scanner.use",
        "predictions.run",
        "interactions.manage",
        "reports.view",
        "notifications.manage",
    ),
    "healthcare_org": (
        "dashboard.view",
        "predictions.run",
        "reports.view",
        "notifications.manage",
    ),
    "researcher": ("dashboard.view", "predictions.run", "reports.view"),
    "viewer": ("dashboard.view", "reports.view"),
}


INTERACTIONS: tuple[tuple[str, str, str, str, str, str, str, str, str, str], ...] = (
    (
        "وارفارین",
        "آسپرین",
        "high",
        "مصرف همزمان می‌تواند خطر خونریزی گوارشی یا خونریزی سیستمیک را افزایش دهد.",
        "فقط با دستور پزشک استفاده شود؛ INR، علائم خونریزی و ضرورت مصرف ضدپلاکت بررسی شود.",
        "Clinical pharmacology guidance",
        "افزایش اثر ضدانعقادی و مهار عملکرد پلاکتی.",
        "در صورت امکان استامینوفن با دوز کنترل‌شده برای درد، یا ضدپلاکت جایگزین با نظر پزشک.",
        "پایش INR، کبودی، خونریزی لثه، مدفوع تیره و افت هموگلوبین.",
        "بالا",
    ),
    (
        "وارفارین",
        "ایبوپروفن",
        "high",
        "NSAIDها در کنار وارفارین ریسک خونریزی و آسیب گوارشی را بالا می‌برند.",
        "از مصرف خودسرانه پرهیز شود و برای کنترل درد، گزینه کم‌خطرتر انتخاب شود.",
        "Medication safety reference",
        "تحریک مخاط معده و اثر افزایشی روی خونریزی.",
        "استامینوفن کوتاه‌مدت با سقف دوز مجاز و نظر پزشک.",
        "بررسی درد معده، مدفوع سیاه، فشار خون و علائم خونریزی.",
        "بالا",
    ),
    (
        "انسولین",
        "بتابلاکر",
        "medium",
        "بتابلاکرها ممکن است علائم هشداردهنده افت قند خون مثل تپش قلب را پنهان کنند.",
        "به بیمار آموزش داده شود قند خون را منظم پایش کند و علائم غیرمعمول را گزارش دهد.",
        "Medication safety reference",
        "پوشاندن علائم سمپاتیک هیپوگلیسمی.",
        "در صورت امکان بتابلاکر انتخابی‌تر یا درمان جایگزین با ارزیابی پزشک.",
        "پایش قند خون ناشتا و بعد از غذا، آموزش علائم تعریق، گیجی و ضعف.",
        "متوسط",
    ),
    (
        "متفورمین",
        "ماده حاجب یددار",
        "contraindicated",
        "در بیماران پرخطر کلیوی، مصرف همزمان با ماده حاجب می‌تواند ریسک اسیدوز لاکتیک را افزایش دهد.",
        "قبل و بعد از تصویربرداری طبق پروتکل مرکز درمانی، عملکرد کلیه بررسی و مصرف متفورمین مدیریت شود.",
        "Radiology medication safety protocol",
        "اختلال احتمالی عملکرد کلیه و تجمع متفورمین.",
        "کنترل موقت قند خون با درمان جایگزین طبق نظر پزشک.",
        "کراتینین، eGFR، علائم تهوع شدید، ضعف و تنفس غیرطبیعی.",
        "بالا",
    ),
    (
        "آموکسی‌سیلین",
        "وارفارین",
        "medium",
        "برخی آنتی‌بیوتیک‌ها ممکن است پاسخ ضدانعقادی وارفارین را تغییر دهند.",
        "در شروع یا قطع آنتی‌بیوتیک، INR و علائم خونریزی با دقت بیشتری پایش شود.",
        "Anticoagulation safety guidance",
        "تغییر فلور روده و تغییر احتمالی متابولیسم یا پاسخ انعقادی.",
        "انتخاب آنتی‌بیوتیک بر اساس کشت و حساسیت؛ بدون قطع خودسرانه وارفارین.",
        "INR طی چند روز اول درمان و پس از پایان دوره آنتی‌بیوتیک.",
        "متوسط",
    ),
    (
        "امپرازول",
        "وارفارین",
        "low",
        "در برخی بیماران ممکن است تغییر خفیف در پاسخ ضدانعقادی دیده شود.",
        "در بیمار پایدار معمولاً منع مصرف مطلق نیست، اما تغییرات INR باید پیگیری شود.",
        "Drug interaction knowledge base",
        "تداخل احتمالی در مسیرهای متابولیک کبدی.",
        "پنتوپرازول یا درمان غیردارویی رفلاکس در صورت صلاحدید پزشک.",
        "INR، علائم خونریزی و پاسخ بالینی بیمار.",
        "متوسط",
    ),
)



def _seed_role_permissions(connection) -> None:
    """Attach deterministic default permissions to every role."""

    for role_code, permission_codes in ROLE_PERMISSION_MAP.items():
        role_row = connection.execute(
            "SELECT id FROM roles WHERE code = ? LIMIT 1;",
            (role_code,),
        ).fetchone()
        if role_row is None:
            continue
        role_id = int(role_row["id"])
        for permission_code in permission_codes:
            permission_row = connection.execute(
                "SELECT id FROM permissions WHERE code = ? LIMIT 1;",
                (permission_code,),
            ).fetchone()
            if permission_row is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (?, ?);
                """,
                (role_id, int(permission_row["id"])),
            )


def seed_database() -> None:
    """Insert baseline reference data without duplicating records."""

    with db_session() as connection:
        connection.executemany(
            "INSERT OR IGNORE INTO roles (code, name_fa, description) VALUES (?, ?, ?);",
            ROLES,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO permissions (code, name_fa, module, description)
            VALUES (?, ?, ?, ?);
            """,
            PERMISSIONS,
        )
        _seed_role_permissions(connection)
        connection.executemany(
            "INSERT OR IGNORE INTO drug_categories (name, description) VALUES (?, ?);",
            DRUG_CATEGORIES,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO suppliers
                (name, city, reliability_score, average_lead_time_days)
            VALUES (?, ?, ?, ?);
            """,
            SUPPLIERS,
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO hospitals
                (name, city, type, bed_count, code, province, address, contact_phone, manager_name, status)
            VALUES
                ('بیمارستان مرکزی سلامت', 'تهران', 'general', 320, 'HSP-IR-001',
                 'تهران', 'خیابان سلامت، پلاک ۱', '021-00000000', 'مدیر بیمارستان سلامت', 'active');
            """
        )
        connection.execute(
            """
            INSERT OR IGNORE INTO pharmacies
                (name, province, city, license_number, owner_name, address, contact_phone, service_level, status)
            VALUES
                ('داروخانه سلامت ایرانیان', 'تهران', 'تهران', 'PH-IR-1403', 'مسئول فنی داروخانه',
                 'تهران، خیابان سلامت', '021-11111111', 'retail', 'active');
            """
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO drugs
                (name, generic_name, category_id, manufacturer, batch_number,
                 expiration_date, supplier_id, current_stock, minimum_stock,
                 monthly_consumption, availability_score)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            DRUGS,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO interactions
                (primary_drug, secondary_drug, severity, description,
                 clinical_recommendation, reference, mechanism, alternative_drugs,
                 monitoring_plan, evidence_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """,
            INTERACTIONS,
        )
        _seed_bootstrap_admin(connection)
        _seed_drug_references(connection)
        connection.execute(
            """
            INSERT OR IGNORE INTO settings (key, value, description)
            VALUES
                ('system_language', 'fa', 'زبان اصلی رابط کاربری'),
                ('notification_center_enabled', 'true', 'فعال بودن مرکز هشدارها'),
                ('current_release', '0.12.0', 'نسخه فعلی سامانه'),
                ('registration_approval_required', 'true', 'لزوم تأیید ثبت‌نام‌های عمومی توسط مدیر سامانه');
            """
        )
        connection.execute(
            """
            UPDATE settings
            SET value = '0.12.0', updated_at = CURRENT_TIMESTAMP
            WHERE key = 'current_release';
            """
        )


def _seed_bootstrap_admin(connection) -> None:
    """Create or promote the configured system owner safely."""

    admin_role_id = connection.execute(
        "SELECT id FROM roles WHERE code = 'administrator' LIMIT 1;"
    ).fetchone()["id"]
    email = settings.bootstrap_admin_email or "anisgulnoori93@gmail.com"
    password = settings.bootstrap_admin_password or "ChangeThisStrongPasswordBeforeDeploy"
    full_name = settings.bootstrap_admin_name or "مدیر اصلی سامانه"
    password_hash = PasswordHasher.hash_password(password)
    existing = connection.execute(
        "SELECT id FROM users WHERE email = ? LIMIT 1;",
        (email,),
    ).fetchone()
    if existing is None:
        cursor = connection.execute(
            """
            INSERT INTO users
                (full_name, email, password_hash, role_id, is_active, approval_status,
                 requested_role, requested_organization_type, requested_organization_name,
                 approval_notes, approved_at, is_system_owner)
            VALUES (?, ?, ?, ?, 1, 'approved', 'administrator', 'platform',
                    'PharmaGuard AI', 'Bootstrap system owner', CURRENT_TIMESTAMP, 1);
            """,
            (full_name, email, password_hash, admin_role_id),
        )
        admin_user_id = int(cursor.lastrowid)
    else:
        admin_user_id = int(existing["id"])
        connection.execute(
            """
            UPDATE users
            SET role_id = ?, is_active = 1, approval_status = 'approved',
                is_system_owner = 1, approved_at = COALESCE(approved_at, CURRENT_TIMESTAMP),
                requested_role = COALESCE(NULLIF(requested_role, ''), 'administrator'),
                requested_organization_type = COALESCE(NULLIF(requested_organization_type, ''), 'platform'),
                requested_organization_name = COALESCE(NULLIF(requested_organization_name, ''), 'PharmaGuard AI')
            WHERE id = ?;
            """,
            (admin_role_id, admin_user_id),
        )


    connection.execute(
        """
        INSERT OR IGNORE INTO user_preferences
            (user_id, theme, language, notifications_enabled, low_stock_alerts,
             expiration_alerts, prediction_alerts, interaction_alerts, email_digest_enabled)
        VALUES (?, ?, 'fa', 1, 1, 1, 1, 1, 0);
        """,
        (admin_user_id, settings.default_theme),
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO notifications
            (id, user_id, title, message, severity, notification_type,
             source_entity_type, source_entity_id, action_page)
        VALUES
            (1, ?, 'خوش آمدید به مرکز هشدارها',
             'از این بخش می‌توانید هشدارهای کمبود، انقضا و پیام‌های عملیاتی سامانه را مدیریت کنید.',
             'info', 'system', 'user', ?, 'notifications');
        """,
        (admin_user_id, admin_user_id),
    )


def _seed_drug_references(connection) -> None:
    """Persist the local international drug reference catalog for offline use."""

    for reference in REFERENCES:
        connection.execute(
            """
            INSERT OR REPLACE INTO drug_references
                (reference_key, canonical_fa, canonical_en, atc_code, therapeutic_class_fa,
                 aliases_json, common_strengths_json, safety_note, source_note, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP);
            """,
            (
                reference.key,
                reference.canonical_fa,
                reference.canonical_en,
                reference.atc_class,
                reference.fa_class,
                json.dumps(reference.aliases, ensure_ascii=False),
                json.dumps(reference.common_strengths, ensure_ascii=False),
                reference.safety_note,
                reference.source_note,
            ),
        )
