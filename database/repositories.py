"""Repository layer for database access.

Keeping SQL here prevents Streamlit pages from containing business data access
logic and makes future migration to PostgreSQL easier.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date
from typing import Any

from auth.security import PasswordHasher
from database.connection import db_session
from models.entities import (
    DrugCategory,
    DrugFilters,
    DrugFormData,
    DrugRecord,
    InteractionFormData,
    InteractionRule,
    PaginatedDrugResult,
    ScannerHistoryRecord,
    Supplier,
    NotificationRecord,
    UserPreferences,
    UserProfile,
)


class UserRepository:
    """Repository for user registration, approval, and authentication."""

    @staticmethod
    def get_by_email(email: str) -> dict[str, Any] | None:
        """Find an enabled user by email, including pending accounts."""

        query = """
            SELECT
                users.id,
                users.full_name,
                users.email,
                users.password_hash,
                roles.code AS role_code,
                roles.name_fa AS role_name,
                users.hospital_id,
                users.pharmacy_id,
                users.is_active,
                users.approval_status,
                users.requested_role,
                users.requested_organization_type,
                users.requested_organization_name,
                users.approval_notes,
                users.is_system_owner
            FROM users
            JOIN roles ON roles.id = users.role_id
            WHERE users.email = ? AND users.is_active = 1
            LIMIT 1;
        """
        with db_session() as connection:
            row = connection.execute(query, (email.strip().lower(),)).fetchone()
        return dict(row) if row else None

    @staticmethod
    def authenticate(email: str, password: str) -> dict[str, Any] | None:
        """Return user data when credentials are valid."""

        user = UserRepository.get_by_email(email)
        if not user:
            return None
        if not PasswordHasher.verify_password(password, user["password_hash"]):
            return None
        with db_session() as connection:
            connection.execute(
                "UPDATE users SET last_login_at = CURRENT_TIMESTAMP WHERE id = ?;",
                (user["id"],),
            )
        user.pop("password_hash", None)
        return user

    @staticmethod
    def create_user(full_name: str, email: str, password: str, role_code: str) -> int:
        """Create an approved user and return its database id."""

        password_hash = PasswordHasher.hash_password(password)
        with db_session() as connection:
            role = connection.execute(
                "SELECT id FROM roles WHERE code = ? LIMIT 1;",
                (role_code,),
            ).fetchone()
            if role is None:
                raise ValueError("نقش انتخاب‌شده معتبر نیست.")
            cursor = connection.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash, role_id, approval_status,
                     requested_role, approved_at)
                VALUES (?, ?, ?, ?, 'approved', ?, CURRENT_TIMESTAMP);
                """,
                (full_name, email.strip().lower(), password_hash, role["id"], role_code),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def create_registration_request(
        full_name: str,
        email: str,
        password: str,
        requested_role: str,
        organization_type: str,
        organization_name: str,
        request_note: str = "",
    ) -> int:
        """Create a self-registration request that requires admin approval."""

        password_hash = PasswordHasher.hash_password(password)
        with db_session() as connection:
            viewer_role = connection.execute(
                "SELECT id FROM roles WHERE code = 'viewer' LIMIT 1;"
            ).fetchone()
            if viewer_role is None:
                raise ValueError("نقش پایه کاربر پیدا نشد.")
            cursor = connection.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash, role_id, is_active, approval_status,
                     requested_role, requested_organization_type, requested_organization_name,
                     approval_notes)
                VALUES (?, ?, ?, ?, 1, 'pending', ?, ?, ?, ?);
                """,
                (
                    full_name.strip(),
                    email.strip().lower(),
                    password_hash,
                    int(viewer_role["id"]),
                    requested_role,
                    organization_type,
                    organization_name.strip(),
                    request_note.strip(),
                ),
            )
            user_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT OR IGNORE INTO user_preferences
                    (user_id, theme, language, notifications_enabled, low_stock_alerts,
                     expiration_alerts, prediction_alerts, interaction_alerts, email_digest_enabled)
                VALUES (?, 'light', 'fa', 1, 1, 1, 1, 1, 0);
                """,
                (user_id,),
            )
            return user_id



def _user_get_profile(user_id: int) -> UserProfile | None:
    """Return the current user profile with organization labels."""

    query = """
        SELECT
            users.id,
            users.full_name,
            users.email,
            roles.code AS role_code,
            roles.name_fa AS role_name,
            COALESCE(hospitals.name, '') AS hospital_name,
            COALESCE(pharmacies.name, '') AS pharmacy_name,
            users.created_at,
            users.last_login_at
        FROM users
        JOIN roles ON roles.id = users.role_id
        LEFT JOIN hospitals ON hospitals.id = users.hospital_id
        LEFT JOIN pharmacies ON pharmacies.id = users.pharmacy_id
        WHERE users.id = ? AND users.is_active = 1
        LIMIT 1;
    """
    with db_session() as connection:
        row = connection.execute(query, (user_id,)).fetchone()
    return UserProfile(**dict(row)) if row else None


def _user_update_identity(user_id: int, full_name: str, email: str) -> None:
    """Update core identity fields for an active user."""

    cleaned_name = full_name.strip()
    cleaned_email = email.strip().lower()
    if len(cleaned_name) < 3:
        raise ValueError("نام کامل باید حداقل ۳ کاراکتر باشد.")
    if "@" not in cleaned_email or "." not in cleaned_email:
        raise ValueError("ایمیل واردشده معتبر نیست.")
    with db_session() as connection:
        try:
            cursor = connection.execute(
                """
                UPDATE users
                SET full_name = ?, email = ?
                WHERE id = ? AND is_active = 1;
                """,
                (cleaned_name, cleaned_email, user_id),
            )
        except sqlite3.IntegrityError as error:
            raise ValueError("این ایمیل قبلاً برای کاربر دیگری ثبت شده است.") from error
        if cursor.rowcount == 0:
            raise ValueError("حساب کاربری پیدا نشد.")


def _user_change_password(user_id: int, current_password: str, new_password: str) -> None:
    """Change password after verifying the current password."""

    if len(new_password) < 8:
        raise ValueError("رمز عبور جدید باید حداقل ۸ کاراکتر باشد.")
    with db_session() as connection:
        row = connection.execute(
            "SELECT password_hash FROM users WHERE id = ? AND is_active = 1 LIMIT 1;",
            (user_id,),
        ).fetchone()
        if row is None:
            raise ValueError("حساب کاربری پیدا نشد.")
        if not PasswordHasher.verify_password(current_password, row["password_hash"]):
            raise ValueError("رمز عبور فعلی صحیح نیست.")
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?;",
            (PasswordHasher.hash_password(new_password), user_id),
        )


UserRepository.get_profile = staticmethod(_user_get_profile)  # type: ignore[attr-defined]
UserRepository.update_identity = staticmethod(_user_update_identity)  # type: ignore[attr-defined]
UserRepository.change_password = staticmethod(_user_change_password)  # type: ignore[attr-defined]


class AnalyticsRepository:
    """Read-only dashboard and landing-page analytics."""

    @staticmethod
    def get_platform_summary() -> dict[str, int]:
        """Return safe aggregate numbers for public-facing operational stats."""

        with db_session() as connection:
            drug_count = connection.execute("SELECT COUNT(*) AS total FROM drugs;").fetchone()["total"]
            prediction_count = connection.execute("SELECT COUNT(*) AS total FROM predictions;").fetchone()["total"]
            interaction_count = connection.execute("SELECT COUNT(*) AS total FROM interactions;").fetchone()["total"]
        return {
            "drugs": int(drug_count),
            "predictions": int(prediction_count),
            "interactions": int(interaction_count),
        }

    @staticmethod
    def get_inventory_snapshot() -> list[dict[str, Any]]:
        """Return drug inventory rows for the initial dashboard."""

        query = """
            SELECT
                drugs.id,
                drugs.name,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                COALESCE(suppliers.reliability_score, 0.75) AS supplier_reliability_score
            FROM drugs
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            ORDER BY drugs.current_stock ASC, drugs.name ASC
            LIMIT 100;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]



class PredictionRepository:
    """Repository for explainable shortage prediction history."""

    @staticmethod
    def create(
        drug_id: int,
        risk_level: str,
        probability: float,
        confidence: float,
        explanation: str,
        recommendation: str,
        model_version: str,
        feature_importance: dict[str, float],
        top_factors: list[str],
        suggested_action: str,
        monitoring_plan: str,
        scenario: dict[str, Any],
    ) -> int:
        """Persist one explainable prediction run and return its id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO predictions
                    (drug_id, risk_level, probability, confidence, explanation,
                     recommendation, model_version, feature_importance_json,
                     top_factors, suggested_action, monitoring_plan, scenario_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    drug_id,
                    risk_level,
                    probability,
                    confidence,
                    explanation,
                    recommendation,
                    model_version,
                    json.dumps(feature_importance, ensure_ascii=False),
                    "، ".join(top_factors),
                    suggested_action,
                    monitoring_plan,
                    json.dumps(scenario, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def latest(limit: int = 25) -> list[dict[str, Any]]:
        """Return recent prediction history with drug names."""

        query = """
            SELECT
                predictions.id,
                drugs.name AS drug_name,
                predictions.risk_level,
                predictions.probability,
                predictions.confidence,
                predictions.model_version,
                predictions.top_factors,
                predictions.suggested_action,
                predictions.created_at
            FROM predictions
            JOIN drugs ON drugs.id = predictions.drug_id
            ORDER BY predictions.created_at DESC, predictions.id DESC
            LIMIT ?;
        """
        with db_session() as connection:
            rows = connection.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def count_by_risk() -> dict[str, int]:
        """Return prediction counts grouped by risk level."""

        query = """
            SELECT risk_level, COUNT(*) AS total
            FROM predictions
            GROUP BY risk_level;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return {str(row["risk_level"]): int(row["total"]) for row in rows}


class DrugCategoryRepository:
    """Repository for drug categories."""

    @staticmethod
    def list_all() -> list[DrugCategory]:
        """Return all categories ordered by name."""

        with db_session() as connection:
            rows = connection.execute(
                "SELECT id, name, description FROM drug_categories ORDER BY name ASC;"
            ).fetchall()
        return [DrugCategory(**dict(row)) for row in rows]

    @staticmethod
    def get_by_name(name: str) -> DrugCategory | None:
        """Return one category by normalized name."""

        with db_session() as connection:
            row = connection.execute(
                """
                SELECT id, name, description
                FROM drug_categories
                WHERE lower(trim(name)) = lower(trim(?))
                LIMIT 1;
                """,
                (name,),
            ).fetchone()
        return DrugCategory(**dict(row)) if row else None

    @staticmethod
    def create(name: str, description: str) -> int:
        """Create a category and return its id."""

        with db_session() as connection:
            cursor = connection.execute(
                "INSERT INTO drug_categories (name, description) VALUES (?, ?);",
                (name, description),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get_or_create(name: str, description: str = "") -> int | None:
        """Return an existing category id or create a new category safely."""

        cleaned = name.strip()
        if not cleaned:
            return None
        existing = DrugCategoryRepository.get_by_name(cleaned)
        if existing:
            return existing.id
        try:
            return DrugCategoryRepository.create(cleaned, description)
        except sqlite3.IntegrityError:
            existing = DrugCategoryRepository.get_by_name(cleaned)
            return existing.id if existing else None


class SupplierRepository:
    """Repository for supply-chain supplier data."""

    @staticmethod
    def list_all() -> list[Supplier]:
        """Return all suppliers ordered by reliability and name."""

        query = """
            SELECT id, name, city, reliability_score, average_lead_time_days
            FROM suppliers
            ORDER BY reliability_score DESC, name ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [Supplier(**dict(row)) for row in rows]

    @staticmethod
    def get_by_name(name: str) -> Supplier | None:
        """Return one supplier by normalized name."""

        query = """
            SELECT id, name, city, reliability_score, average_lead_time_days
            FROM suppliers
            WHERE lower(trim(name)) = lower(trim(?))
            LIMIT 1;
        """
        with db_session() as connection:
            row = connection.execute(query, (name,)).fetchone()
        return Supplier(**dict(row)) if row else None

    @staticmethod
    def create(
        name: str,
        city: str,
        reliability_score: float,
        average_lead_time_days: int,
    ) -> int:
        """Create a supplier and return its id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO suppliers
                    (name, city, reliability_score, average_lead_time_days)
                VALUES (?, ?, ?, ?);
                """,
                (name, city, reliability_score, average_lead_time_days),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def get_or_create(
        name: str,
        city: str = "ثبت‌نشده",
        reliability_score: float = 0.75,
        average_lead_time_days: int = 7,
    ) -> int | None:
        """Return an existing supplier id or create a new supplier safely."""

        cleaned = name.strip()
        if not cleaned:
            return None
        existing = SupplierRepository.get_by_name(cleaned)
        if existing:
            return existing.id
        try:
            return SupplierRepository.create(
                cleaned,
                city,
                reliability_score,
                average_lead_time_days,
            )
        except sqlite3.IntegrityError:
            existing = SupplierRepository.get_by_name(cleaned)
            return existing.id if existing else None


class DrugRepository:
    """Repository for drug inventory CRUD and searchable lists."""

    _SORT_COLUMNS: dict[str, str] = {
        "name": "drugs.name",
        "stock": "drugs.current_stock",
        "expiration": "drugs.expiration_date",
        "created": "drugs.created_at",
        "consumption": "drugs.monthly_consumption",
    }

    @staticmethod
    def list_paginated(
        filters: DrugFilters,
        page: int = 1,
        page_size: int = 10,
    ) -> PaginatedDrugResult:
        """Return filtered and paginated drug records."""

        where_sql, params = DrugRepository._build_where_clause(filters)
        order_column = DrugRepository._SORT_COLUMNS.get(filters.sort_by, "drugs.name")
        direction = "DESC" if filters.sort_direction == "desc" else "ASC"
        offset = max(page - 1, 0) * page_size

        count_query = f"SELECT COUNT(*) AS total FROM drugs {where_sql};"
        data_query = f"""
            SELECT
                drugs.id,
                drugs.name,
                drugs.generic_name,
                drugs.category_id,
                COALESCE(drug_categories.name, 'بدون دسته') AS category_name,
                drugs.manufacturer,
                drugs.batch_number,
                drugs.expiration_date,
                drugs.supplier_id,
                COALESCE(suppliers.name, 'بدون تأمین‌کننده') AS supplier_name,
                drugs.unit,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                drugs.created_at
            FROM drugs
            LEFT JOIN drug_categories ON drug_categories.id = drugs.category_id
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            {where_sql}
            ORDER BY {order_column} {direction}, drugs.id DESC
            LIMIT ? OFFSET ?;
        """
        with db_session() as connection:
            total = int(connection.execute(count_query, params).fetchone()["total"])
            rows = connection.execute(data_query, (*params, page_size, offset)).fetchall()
        return PaginatedDrugResult(
            rows=[DrugRepository._map_record(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )

    @staticmethod
    def list_for_selection() -> list[tuple[int, str, str]]:
        """Return compact drug options for selectors."""

        query = """
            SELECT id, name, batch_number
            FROM drugs
            ORDER BY name ASC, batch_number ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [(int(row["id"]), str(row["name"]), str(row["batch_number"])) for row in rows]

    @staticmethod
    def list_for_scanner() -> list[DrugRecord]:
        """Return inventory records used by the drug-scanner matching engine."""

        query = """
            SELECT
                drugs.id,
                drugs.name,
                drugs.generic_name,
                drugs.category_id,
                COALESCE(drug_categories.name, 'بدون دسته') AS category_name,
                drugs.manufacturer,
                drugs.batch_number,
                drugs.expiration_date,
                drugs.supplier_id,
                COALESCE(suppliers.name, 'بدون تأمین‌کننده') AS supplier_name,
                drugs.unit,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                drugs.created_at
            FROM drugs
            LEFT JOIN drug_categories ON drug_categories.id = drugs.category_id
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            ORDER BY drugs.name ASC, drugs.batch_number ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [DrugRepository._map_record(row) for row in rows]

    @staticmethod
    def get_by_id(drug_id: int) -> DrugRecord | None:
        """Return one drug record by id."""

        filters = DrugFilters()
        where_sql, params = "WHERE drugs.id = ?", (drug_id,)
        query = f"""
            SELECT
                drugs.id,
                drugs.name,
                drugs.generic_name,
                drugs.category_id,
                COALESCE(drug_categories.name, 'بدون دسته') AS category_name,
                drugs.manufacturer,
                drugs.batch_number,
                drugs.expiration_date,
                drugs.supplier_id,
                COALESCE(suppliers.name, 'بدون تأمین‌کننده') AS supplier_name,
                drugs.unit,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                drugs.created_at
            FROM drugs
            LEFT JOIN drug_categories ON drug_categories.id = drugs.category_id
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            {where_sql}
            LIMIT 1;
        """
        del filters
        with db_session() as connection:
            row = connection.execute(query, params).fetchone()
        return DrugRepository._map_record(row) if row else None

    @staticmethod
    def create(data: DrugFormData) -> int:
        """Create a new drug and return its id."""

        payload = DrugRepository._serialize_payload(data)
        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO drugs
                    (name, generic_name, category_id, manufacturer, batch_number,
                     expiration_date, supplier_id, unit, current_stock, minimum_stock,
                     monthly_consumption, availability_score)
                VALUES
                    (:name, :generic_name, :category_id, :manufacturer, :batch_number,
                     :expiration_date, :supplier_id, :unit, :current_stock,
                     :minimum_stock, :monthly_consumption, :availability_score);
                """,
                payload,
            )
            return int(cursor.lastrowid)

    @staticmethod
    def update(drug_id: int, data: DrugFormData) -> None:
        """Update an existing drug."""

        payload = DrugRepository._serialize_payload(data)
        payload["id"] = drug_id
        with db_session() as connection:
            cursor = connection.execute(
                """
                UPDATE drugs
                SET
                    name = :name,
                    generic_name = :generic_name,
                    category_id = :category_id,
                    manufacturer = :manufacturer,
                    batch_number = :batch_number,
                    expiration_date = :expiration_date,
                    supplier_id = :supplier_id,
                    unit = :unit,
                    current_stock = :current_stock,
                    minimum_stock = :minimum_stock,
                    monthly_consumption = :monthly_consumption,
                    availability_score = :availability_score
                WHERE id = :id;
                """,
                payload,
            )
            if cursor.rowcount == 0:
                raise ValueError("داروی انتخاب‌شده پیدا نشد.")

    @staticmethod
    def delete(drug_id: int) -> None:
        """Delete a drug and its cascade-linked predictions."""

        with db_session() as connection:
            cursor = connection.execute("DELETE FROM drugs WHERE id = ?;", (drug_id,))
            if cursor.rowcount == 0:
                raise ValueError("داروی انتخاب‌شده پیدا نشد.")

    @staticmethod
    def get_by_name_and_batch(name: str, batch_number: str) -> DrugRecord | None:
        """Return a drug by normalized name and batch number."""

        query = """
            SELECT
                drugs.id,
                drugs.name,
                drugs.generic_name,
                drugs.category_id,
                COALESCE(drug_categories.name, 'بدون دسته') AS category_name,
                drugs.manufacturer,
                drugs.batch_number,
                drugs.expiration_date,
                drugs.supplier_id,
                COALESCE(suppliers.name, 'بدون تأمین‌کننده') AS supplier_name,
                drugs.unit,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                drugs.created_at
            FROM drugs
            LEFT JOIN drug_categories ON drug_categories.id = drugs.category_id
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            WHERE lower(trim(drugs.name)) = lower(trim(?))
              AND lower(trim(drugs.batch_number)) = lower(trim(?))
            LIMIT 1;
        """
        with db_session() as connection:
            row = connection.execute(query, (name, batch_number)).fetchone()
        return DrugRepository._map_record(row) if row else None

    @staticmethod
    def key_exists(name: str, batch_number: str) -> bool:
        """Return True when a normalized drug/batch pair exists."""

        return DrugRepository.get_by_name_and_batch(name, batch_number) is not None

    @staticmethod
    def _build_where_clause(filters: DrugFilters) -> tuple[str, tuple[Any, ...]]:
        """Build a safe WHERE clause from user filters."""

        conditions: list[str] = []
        params: list[Any] = []
        search = filters.search.strip()
        if search:
            like = f"%{search}%"
            conditions.append(
                """
                (
                    drugs.name LIKE ? OR
                    drugs.generic_name LIKE ? OR
                    drugs.manufacturer LIKE ? OR
                    drugs.batch_number LIKE ?
                )
                """
            )
            params.extend([like, like, like, like])
        if filters.category_id:
            conditions.append("drugs.category_id = ?")
            params.append(filters.category_id)
        if filters.supplier_id:
            conditions.append("drugs.supplier_id = ?")
            params.append(filters.supplier_id)
        if filters.stock_status == "low":
            conditions.append("drugs.current_stock < drugs.minimum_stock")
        elif filters.stock_status == "stable":
            conditions.append("drugs.current_stock >= drugs.minimum_stock")
        if filters.expiration_status == "expired":
            conditions.append("date(drugs.expiration_date) < date('now')")
        elif filters.expiration_status == "soon":
            conditions.append("date(drugs.expiration_date) BETWEEN date('now') AND date('now', '+90 days')")
        elif filters.expiration_status == "valid":
            conditions.append("date(drugs.expiration_date) > date('now', '+90 days')")

        if not conditions:
            return "", tuple()
        return "WHERE " + " AND ".join(conditions), tuple(params)

    @staticmethod
    def _serialize_payload(data: DrugFormData) -> dict[str, Any]:
        """Serialize a dataclass payload for SQLite."""

        payload = asdict(data)
        expiration = payload.get("expiration_date")
        if isinstance(expiration, date):
            payload["expiration_date"] = expiration.isoformat()
        return payload

    @staticmethod
    def _map_record(row: sqlite3.Row) -> DrugRecord:
        """Map a SQLite row to a typed drug record."""

        return DrugRecord(
            id=int(row["id"]),
            name=str(row["name"]),
            generic_name=str(row["generic_name"] or ""),
            category_id=int(row["category_id"]) if row["category_id"] is not None else None,
            category_name=str(row["category_name"]),
            manufacturer=str(row["manufacturer"] or ""),
            batch_number=str(row["batch_number"] or ""),
            expiration_date=str(row["expiration_date"]) if row["expiration_date"] else None,
            supplier_id=int(row["supplier_id"]) if row["supplier_id"] is not None else None,
            supplier_name=str(row["supplier_name"]),
            unit=str(row["unit"] or "عدد"),
            current_stock=int(row["current_stock"]),
            minimum_stock=int(row["minimum_stock"]),
            monthly_consumption=int(row["monthly_consumption"]),
            availability_score=float(row["availability_score"]),
            lead_time_days=int(row["lead_time_days"]),
            created_at=str(row["created_at"]),
        )


class ActivityLogRepository:
    """Repository for auditable user actions."""

    @staticmethod
    def log(
        user_id: int | None,
        action: str,
        entity_type: str = "",
        entity_id: int | None = None,
        details: str = "",
    ) -> None:
        """Persist an activity log row without interrupting user workflow."""

        with db_session() as connection:
            connection.execute(
                """
                INSERT INTO activity_logs
                    (user_id, action, entity_type, entity_id, details)
                VALUES (?, ?, ?, ?, ?);
                """,
                (user_id, action, entity_type, entity_id, details),
            )

class ImportBatchRepository:
    """Repository for auditable CSV/Excel import batches."""

    @staticmethod
    def create(
        file_name: str,
        total_rows: int,
        valid_rows: int,
        invalid_rows: int,
        duplicate_rows: int,
        inserted_rows: int,
        updated_rows: int,
        skipped_rows: int,
        user_id: int | None,
    ) -> int:
        """Persist an import summary and return the batch id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO import_batches
                    (file_name, total_rows, valid_rows, invalid_rows,
                     duplicate_rows, inserted_rows, updated_rows, skipped_rows, user_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    file_name,
                    total_rows,
                    valid_rows,
                    invalid_rows,
                    duplicate_rows,
                    inserted_rows,
                    updated_rows,
                    skipped_rows,
                    user_id,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def add_row_error(batch_id: int, row_number: int, status: str, message: str) -> None:
        """Persist an import row warning or error."""

        with db_session() as connection:
            connection.execute(
                """
                INSERT INTO import_row_errors (batch_id, row_number, status, message)
                VALUES (?, ?, ?, ?);
                """,
                (batch_id, row_number, status, message),
            )

    @staticmethod
    def latest(limit: int = 10) -> list[dict[str, Any]]:
        """Return recent import batches for operational visibility."""

        with db_session() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    file_name,
                    total_rows,
                    valid_rows,
                    invalid_rows,
                    duplicate_rows,
                    inserted_rows,
                    updated_rows,
                    skipped_rows,
                    created_at
                FROM import_batches
                ORDER BY created_at DESC, id DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]



class InteractionRepository:
    """Repository for the drug-interaction knowledge base."""

    @staticmethod
    def list_all(search: str = "", severity: str = "all") -> list[InteractionRule]:
        """Return interaction rules filtered by search text and severity."""

        conditions: list[str] = []
        params: list[Any] = []
        cleaned_search = search.strip()
        if cleaned_search:
            like = f"%{cleaned_search}%"
            conditions.append(
                """
                (
                    primary_drug LIKE ? OR secondary_drug LIKE ? OR
                    description LIKE ? OR clinical_recommendation LIKE ? OR
                    mechanism LIKE ? OR alternative_drugs LIKE ?
                )
                """
            )
            params.extend([like, like, like, like, like, like])
        if severity != "all":
            conditions.append("severity = ?")
            params.append(severity)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                id,
                primary_drug,
                secondary_drug,
                severity,
                description,
                clinical_recommendation,
                reference,
                mechanism,
                alternative_drugs,
                monitoring_plan,
                evidence_level
            FROM interactions
            {where_sql}
            ORDER BY
                CASE severity
                    WHEN 'contraindicated' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    ELSE 1
                END DESC,
                primary_drug ASC,
                secondary_drug ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [InteractionRepository._map_rule(row) for row in rows]

    @staticmethod
    def count_by_severity() -> dict[str, int]:
        """Return interaction counts grouped by severity."""

        query = """
            SELECT severity, COUNT(*) AS total
            FROM interactions
            GROUP BY severity;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return {str(row["severity"]): int(row["total"]) for row in rows}

    @staticmethod
    def create(data: InteractionFormData) -> int:
        """Create a new interaction rule and return its id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO interactions
                    (primary_drug, secondary_drug, severity, description,
                     clinical_recommendation, reference, mechanism,
                     alternative_drugs, monitoring_plan, evidence_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data.primary_drug,
                    data.secondary_drug,
                    data.severity,
                    data.description,
                    data.clinical_recommendation,
                    data.reference,
                    data.mechanism,
                    data.alternative_drugs,
                    data.monitoring_plan,
                    data.evidence_level,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def delete(rule_id: int) -> None:
        """Delete an interaction rule."""

        with db_session() as connection:
            cursor = connection.execute("DELETE FROM interactions WHERE id = ?;", (rule_id,))
            if cursor.rowcount == 0:
                raise ValueError("قانون تداخل انتخاب‌شده پیدا نشد.")

    @staticmethod
    def _map_rule(row: sqlite3.Row) -> InteractionRule:
        """Map a SQLite row to an interaction rule dataclass."""

        return InteractionRule(
            id=int(row["id"]),
            primary_drug=str(row["primary_drug"]),
            secondary_drug=str(row["secondary_drug"]),
            severity=str(row["severity"]),
            description=str(row["description"]),
            clinical_recommendation=str(row["clinical_recommendation"]),
            reference=str(row["reference"] or ""),
            mechanism=str(row["mechanism"] or ""),
            alternative_drugs=str(row["alternative_drugs"] or ""),
            monitoring_plan=str(row["monitoring_plan"] or ""),
            evidence_level=str(row["evidence_level"] or "متوسط"),
        )


class ScannerHistoryRepository:
    """Repository for AI drug-scanner audit history."""

    @staticmethod
    def create(
        user_id: int | None,
        image_name: str,
        recognized_drug_name: str,
        matched_drug_id: int | None,
        confidence: float,
        status: str,
        extracted_text: str,
        warnings: str,
        suggested_alternatives: str,
        interaction_summary: str,
        prediction_summary: str,
    ) -> int:
        """Persist one scanner run and return its database id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO scanner_history
                    (user_id, image_name, recognized_drug_name, matched_drug_id,
                     confidence, status, extracted_text, warnings,
                     suggested_alternatives, interaction_summary, prediction_summary)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    image_name,
                    recognized_drug_name,
                    matched_drug_id,
                    confidence,
                    status,
                    extracted_text,
                    warnings,
                    suggested_alternatives,
                    interaction_summary,
                    prediction_summary,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def latest(limit: int = 30) -> list[ScannerHistoryRecord]:
        """Return recent scanner history rows with matched inventory names."""

        query = """
            SELECT
                scanner_history.id,
                scanner_history.image_name,
                scanner_history.recognized_drug_name,
                COALESCE(drugs.name, 'بدون تطبیق') AS matched_drug_name,
                scanner_history.confidence,
                scanner_history.status,
                scanner_history.warnings,
                scanner_history.created_at
            FROM scanner_history
            LEFT JOIN drugs ON drugs.id = scanner_history.matched_drug_id
            ORDER BY scanner_history.created_at DESC, scanner_history.id DESC
            LIMIT ?;
        """
        with db_session() as connection:
            rows = connection.execute(query, (limit,)).fetchall()
        return [
            ScannerHistoryRecord(
                id=int(row["id"]),
                image_name=str(row["image_name"]),
                recognized_drug_name=str(row["recognized_drug_name"] or ""),
                matched_drug_name=str(row["matched_drug_name"] or "بدون تطبیق"),
                confidence=float(row["confidence"] or 0),
                status=str(row["status"]),
                warnings=str(row["warnings"] or ""),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]


class ReportRepository:
    """Read-only repository for management reporting and analytics."""

    @staticmethod
    def inventory_rows() -> list[dict[str, Any]]:
        """Return current inventory rows with calculated report fields."""

        query = """
            SELECT
                drugs.id,
                drugs.name,
                drugs.generic_name,
                COALESCE(drug_categories.name, 'بدون دسته') AS category_name,
                COALESCE(suppliers.name, 'بدون تأمین‌کننده') AS supplier_name,
                drugs.manufacturer,
                drugs.batch_number,
                drugs.expiration_date,
                drugs.unit,
                drugs.current_stock,
                drugs.minimum_stock,
                drugs.monthly_consumption,
                drugs.availability_score,
                COALESCE(suppliers.average_lead_time_days, 7) AS lead_time_days,
                CASE
                    WHEN drugs.current_stock <= 0 THEN 'critical'
                    WHEN drugs.minimum_stock > 0 AND drugs.current_stock < drugs.minimum_stock THEN 'low'
                    WHEN drugs.monthly_consumption > 0 AND drugs.current_stock > drugs.monthly_consumption * 3 THEN 'overstock'
                    ELSE 'healthy'
                END AS stock_status,
                CASE
                    WHEN drugs.minimum_stock <= 0 THEN 1.0
                    ELSE CAST(drugs.current_stock AS REAL) / CAST(drugs.minimum_stock AS REAL)
                END AS stock_ratio,
                CASE
                    WHEN drugs.minimum_stock > drugs.current_stock THEN drugs.minimum_stock - drugs.current_stock
                    ELSE 0
                END AS stock_gap,
                CASE
                    WHEN drugs.expiration_date IS NULL OR trim(drugs.expiration_date) = '' THEN 'unknown'
                    WHEN date(drugs.expiration_date) < date('now') THEN 'expired'
                    WHEN date(drugs.expiration_date) <= date('now', '+90 days') THEN 'soon'
                    ELSE 'valid'
                END AS expiration_status
            FROM drugs
            LEFT JOIN drug_categories ON drug_categories.id = drugs.category_id
            LEFT JOIN suppliers ON suppliers.id = drugs.supplier_id
            ORDER BY
                CASE stock_status
                    WHEN 'critical' THEN 4
                    WHEN 'low' THEN 3
                    WHEN 'healthy' THEN 2
                    ELSE 1
                END DESC,
                drugs.name ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def prediction_rows(start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
        """Return prediction rows within a date range."""

        where_sql, params = ReportRepository._created_between("predictions.created_at", start_date, end_date)
        query = f"""
            SELECT
                predictions.id,
                drugs.name AS drug_name,
                predictions.risk_level,
                predictions.probability,
                predictions.confidence,
                predictions.explanation,
                predictions.recommendation,
                predictions.model_version,
                predictions.top_factors,
                predictions.suggested_action,
                predictions.monitoring_plan,
                predictions.created_at
            FROM predictions
            JOIN drugs ON drugs.id = predictions.drug_id
            {where_sql}
            ORDER BY predictions.created_at DESC, predictions.id DESC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def interaction_rows() -> list[dict[str, Any]]:
        """Return all interaction knowledge-base rows for reporting."""

        query = """
            SELECT
                id,
                primary_drug,
                secondary_drug,
                severity,
                description,
                clinical_recommendation,
                reference,
                mechanism,
                alternative_drugs,
                monitoring_plan,
                evidence_level
            FROM interactions
            ORDER BY
                CASE severity
                    WHEN 'contraindicated' THEN 4
                    WHEN 'high' THEN 3
                    WHEN 'medium' THEN 2
                    ELSE 1
                END DESC,
                primary_drug ASC,
                secondary_drug ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def import_batch_rows(start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
        """Return import-batch rows within a date range."""

        where_sql, params = ReportRepository._created_between("created_at", start_date, end_date)
        query = f"""
            SELECT
                id,
                file_name,
                total_rows,
                valid_rows,
                invalid_rows,
                duplicate_rows,
                inserted_rows,
                updated_rows,
                skipped_rows,
                created_at
            FROM import_batches
            {where_sql}
            ORDER BY created_at DESC, id DESC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def activity_rows(start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
        """Return recent activity-log rows within a date range."""

        where_sql, params = ReportRepository._created_between("activity_logs.created_at", start_date, end_date)
        query = f"""
            SELECT
                activity_logs.id,
                COALESCE(users.full_name, 'سیستم') AS user_name,
                activity_logs.action,
                activity_logs.entity_type,
                activity_logs.entity_id,
                activity_logs.details,
                activity_logs.created_at
            FROM activity_logs
            LEFT JOIN users ON users.id = activity_logs.user_id
            {where_sql}
            ORDER BY activity_logs.created_at DESC, activity_logs.id DESC
            LIMIT 200;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _created_between(
        column_name: str,
        start_date: str | None,
        end_date: str | None,
    ) -> tuple[str, list[Any]]:
        """Build a safe created-at date filter for reporting queries."""

        conditions: list[str] = []
        params: list[Any] = []
        if start_date:
            conditions.append(f"date({column_name}) >= date(?)")
            params.append(start_date)
        if end_date:
            conditions.append(f"date({column_name}) <= date(?)")
            params.append(end_date)
        if not conditions:
            return "", params
        return "WHERE " + " AND ".join(conditions), params


class NotificationRepository:
    """Repository for actionable user notifications."""

    @staticmethod
    def create(
        user_id: int | None,
        title: str,
        message: str,
        severity: str = "info",
        notification_type: str = "system",
        source_entity_type: str = "",
        source_entity_id: int | None = None,
        action_page: str = "",
    ) -> int:
        """Create one notification and return its database id."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO notifications
                    (user_id, title, message, severity, notification_type,
                     source_entity_type, source_entity_id, action_page)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    title.strip(),
                    message.strip(),
                    severity,
                    notification_type,
                    source_entity_type,
                    source_entity_id,
                    action_page,
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def exists_unread_source(
        user_id: int | None,
        source_entity_type: str,
        source_entity_id: int | None,
        notification_type: str,
    ) -> bool:
        """Avoid creating duplicate active notifications for the same source."""

        query = """
            SELECT 1
            FROM notifications
            WHERE COALESCE(user_id, 0) = COALESCE(?, 0)
              AND source_entity_type = ?
              AND COALESCE(source_entity_id, 0) = COALESCE(?, 0)
              AND notification_type = ?
              AND is_read = 0
            LIMIT 1;
        """
        with db_session() as connection:
            row = connection.execute(
                query,
                (user_id, source_entity_type, source_entity_id, notification_type),
            ).fetchone()
        return row is not None

    @staticmethod
    def list_for_user(
        user_id: int,
        include_read: bool = True,
        severity: str = "all",
        limit: int = 50,
    ) -> list[NotificationRecord]:
        """Return personal and global notifications for one user."""

        conditions = ["(user_id = ? OR user_id IS NULL)"]
        params: list[Any] = [user_id]
        if not include_read:
            conditions.append("is_read = 0")
        if severity != "all":
            conditions.append("severity = ?")
            params.append(severity)
        query = f"""
            SELECT
                id,
                user_id,
                title,
                message,
                severity,
                notification_type,
                source_entity_type,
                source_entity_id,
                action_page,
                is_read,
                created_at
            FROM notifications
            WHERE {' AND '.join(conditions)}
            ORDER BY is_read ASC, created_at DESC, id DESC
            LIMIT ?;
        """
        params.append(limit)
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [NotificationRepository._map_record(row) for row in rows]

    @staticmethod
    def unread_count(user_id: int) -> int:
        """Return unread notification count for the current user."""

        query = """
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE (user_id = ? OR user_id IS NULL) AND is_read = 0;
        """
        with db_session() as connection:
            total = connection.execute(query, (user_id,)).fetchone()["total"]
        return int(total)

    @staticmethod
    def mark_read(notification_id: int, user_id: int) -> None:
        """Mark one notification as read when it belongs to the user or is global."""

        with db_session() as connection:
            connection.execute(
                """
                UPDATE notifications
                SET is_read = 1
                WHERE id = ? AND (user_id = ? OR user_id IS NULL);
                """,
                (notification_id, user_id),
            )

    @staticmethod
    def mark_all_read(user_id: int) -> None:
        """Mark all current notifications as read."""

        with db_session() as connection:
            connection.execute(
                """
                UPDATE notifications
                SET is_read = 1
                WHERE user_id = ? OR user_id IS NULL;
                """,
                (user_id,),
            )

    @staticmethod
    def delete(notification_id: int, user_id: int) -> None:
        """Delete one personal notification. Global notifications are only marked read."""

        with db_session() as connection:
            row = connection.execute(
                "SELECT user_id FROM notifications WHERE id = ? LIMIT 1;",
                (notification_id,),
            ).fetchone()
            if row is None:
                return
            if row["user_id"] is None:
                connection.execute(
                    "UPDATE notifications SET is_read = 1 WHERE id = ?;",
                    (notification_id,),
                )
            else:
                connection.execute(
                    "DELETE FROM notifications WHERE id = ? AND user_id = ?;",
                    (notification_id, user_id),
                )

    @staticmethod
    def _map_record(row: sqlite3.Row) -> NotificationRecord:
        """Map a SQLite row to a notification dataclass."""

        return NotificationRecord(
            id=int(row["id"]),
            user_id=int(row["user_id"]) if row["user_id"] is not None else None,
            title=str(row["title"]),
            message=str(row["message"]),
            severity=str(row["severity"]),
            notification_type=str(row["notification_type"] or "system"),
            source_entity_type=str(row["source_entity_type"] or ""),
            source_entity_id=int(row["source_entity_id"]) if row["source_entity_id"] is not None else None,
            action_page=str(row["action_page"] or ""),
            is_read=bool(row["is_read"]),
            created_at=str(row["created_at"]),
        )


class UserPreferenceRepository:
    """Repository for persistent user preferences."""

    DEFAULTS = {
        "theme": "light",
        "language": "fa",
        "notifications_enabled": 1,
        "low_stock_alerts": 1,
        "expiration_alerts": 1,
        "prediction_alerts": 1,
        "interaction_alerts": 1,
        "email_digest_enabled": 0,
    }

    @staticmethod
    def get(user_id: int) -> UserPreferences:
        """Return preferences, creating defaults if needed."""

        UserPreferenceRepository.ensure(user_id)
        with db_session() as connection:
            row = connection.execute(
                """
                SELECT
                    user_id,
                    theme,
                    language,
                    notifications_enabled,
                    low_stock_alerts,
                    expiration_alerts,
                    prediction_alerts,
                    interaction_alerts,
                    email_digest_enabled,
                    updated_at
                FROM user_preferences
                WHERE user_id = ?
                LIMIT 1;
                """,
                (user_id,),
            ).fetchone()
        if row is None:
            raise ValueError("تنظیمات کاربر پیدا نشد.")
        return UserPreferenceRepository._map_preferences(row)

    @staticmethod
    def ensure(user_id: int) -> None:
        """Create a default preference row for a user if missing."""

        with db_session() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_preferences
                    (user_id, theme, language, notifications_enabled,
                     low_stock_alerts, expiration_alerts, prediction_alerts,
                     interaction_alerts, email_digest_enabled)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    user_id,
                    UserPreferenceRepository.DEFAULTS["theme"],
                    UserPreferenceRepository.DEFAULTS["language"],
                    UserPreferenceRepository.DEFAULTS["notifications_enabled"],
                    UserPreferenceRepository.DEFAULTS["low_stock_alerts"],
                    UserPreferenceRepository.DEFAULTS["expiration_alerts"],
                    UserPreferenceRepository.DEFAULTS["prediction_alerts"],
                    UserPreferenceRepository.DEFAULTS["interaction_alerts"],
                    UserPreferenceRepository.DEFAULTS["email_digest_enabled"],
                ),
            )

    @staticmethod
    def update(user_id: int, values: dict[str, Any]) -> None:
        """Update a safe subset of user preference fields."""

        allowed = {
            "theme",
            "language",
            "notifications_enabled",
            "low_stock_alerts",
            "expiration_alerts",
            "prediction_alerts",
            "interaction_alerts",
            "email_digest_enabled",
        }
        payload = {key: values[key] for key in values if key in allowed}
        if not payload:
            return
        assignments = ", ".join(f"{key} = ?" for key in payload)
        params = [UserPreferenceRepository._db_value(value) for value in payload.values()]
        params.append(user_id)
        UserPreferenceRepository.ensure(user_id)
        with db_session() as connection:
            connection.execute(
                f"""
                UPDATE user_preferences
                SET {assignments}, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?;
                """,
                tuple(params),
            )

    @staticmethod
    def _db_value(value: Any) -> Any:
        """Convert Python booleans to SQLite integers."""

        if isinstance(value, bool):
            return 1 if value else 0
        return value

    @staticmethod
    def _map_preferences(row: sqlite3.Row) -> UserPreferences:
        """Map a SQLite row to user preferences."""

        return UserPreferences(
            user_id=int(row["user_id"]),
            theme=str(row["theme"]),
            language=str(row["language"]),
            notifications_enabled=bool(row["notifications_enabled"]),
            low_stock_alerts=bool(row["low_stock_alerts"]),
            expiration_alerts=bool(row["expiration_alerts"]),
            prediction_alerts=bool(row["prediction_alerts"]),
            interaction_alerts=bool(row["interaction_alerts"]),
            email_digest_enabled=bool(row["email_digest_enabled"]),
            updated_at=str(row["updated_at"]),
        )


class AdminRepository:
    """Administrative repository for users, organizations, roles, and system audit."""

    @staticmethod
    def system_overview() -> dict[str, int]:
        """Return enterprise control-plane counters for the admin panel."""

        queries = {
            "users": "SELECT COUNT(*) AS total FROM users;",
            "active_users": "SELECT COUNT(*) AS total FROM users WHERE is_active = 1 AND approval_status = 'approved';",
            "pending_users": "SELECT COUNT(*) AS total FROM users WHERE approval_status = 'pending';",
            "hospitals": "SELECT COUNT(*) AS total FROM hospitals;",
            "pharmacies": "SELECT COUNT(*) AS total FROM pharmacies;",
            "drugs": "SELECT COUNT(*) AS total FROM drugs;",
            "notifications": "SELECT COUNT(*) AS total FROM notifications WHERE is_read = 0;",
            "predictions": "SELECT COUNT(*) AS total FROM predictions;",
            "logs": "SELECT COUNT(*) AS total FROM activity_logs;",
        }
        with db_session() as connection:
            return {
                key: int(connection.execute(query).fetchone()["total"])
                for key, query in queries.items()
            }

    @staticmethod
    def list_roles() -> list[dict[str, Any]]:
        """Return roles with their permission counts."""

        query = """
            SELECT
                roles.id,
                roles.code,
                roles.name_fa,
                roles.description,
                COUNT(role_permissions.permission_id) AS permission_count
            FROM roles
            LEFT JOIN role_permissions ON role_permissions.role_id = roles.id
            GROUP BY roles.id, roles.code, roles.name_fa, roles.description
            ORDER BY roles.id ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_permissions() -> list[dict[str, Any]]:
        """Return all known permissions grouped by module."""

        query = """
            SELECT id, code, name_fa, module, description
            FROM permissions
            ORDER BY module ASC, code ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_role_permissions() -> list[dict[str, Any]]:
        """Return human-readable role-to-permission matrix rows."""

        query = """
            SELECT
                roles.name_fa AS role_name,
                roles.code AS role_code,
                permissions.name_fa AS permission_name,
                permissions.code AS permission_code,
                permissions.module
            FROM role_permissions
            JOIN roles ON roles.id = role_permissions.role_id
            JOIN permissions ON permissions.id = role_permissions.permission_id
            ORDER BY roles.id ASC, permissions.module ASC, permissions.code ASC;
        """
        with db_session() as connection:
            rows = connection.execute(query).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def list_users(search: str = "", role_code: str = "all", status: str = "all") -> list[dict[str, Any]]:
        """Return users with organization and role labels."""

        conditions: list[str] = []
        params: list[Any] = []
        cleaned = search.strip()
        if cleaned:
            like = f"%{cleaned}%"
            conditions.append("(users.full_name LIKE ? OR users.email LIKE ?)")
            params.extend([like, like])
        if role_code != "all":
            conditions.append("roles.code = ?")
            params.append(role_code)
        if status == "active":
            conditions.append("users.is_active = 1 AND users.approval_status = 'approved'")
        elif status == "inactive":
            conditions.append("users.is_active = 0")
        elif status in {"pending", "rejected", "suspended", "approved"}:
            conditions.append("users.approval_status = ?")
            params.append(status)
        where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT
                users.id,
                users.full_name,
                users.email,
                roles.code AS role_code,
                roles.name_fa AS role_name,
                users.hospital_id,
                COALESCE(hospitals.name, '') AS hospital_name,
                users.pharmacy_id,
                COALESCE(pharmacies.name, '') AS pharmacy_name,
                users.is_active,
                users.approval_status,
                users.requested_role,
                users.requested_organization_type,
                users.requested_organization_name,
                users.approval_notes,
                users.is_system_owner,
                users.created_at,
                users.last_login_at
            FROM users
            JOIN roles ON roles.id = users.role_id
            LEFT JOIN hospitals ON hospitals.id = users.hospital_id
            LEFT JOIN pharmacies ON pharmacies.id = users.pharmacy_id
            {where_sql}
            ORDER BY users.created_at DESC, users.id DESC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def create_user(
        full_name: str,
        email: str,
        password: str,
        role_code: str,
        hospital_id: int | None = None,
        pharmacy_id: int | None = None,
        is_active: bool = True,
    ) -> int:
        """Create an administrative user with optional organization scope."""

        role_id = AdminRepository._role_id_by_code(role_code)
        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO users
                    (full_name, email, password_hash, role_id, hospital_id, pharmacy_id,
                     is_active, approval_status, requested_role, approved_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'approved', ?, CURRENT_TIMESTAMP);
                """,
                (
                    full_name.strip(),
                    email.strip().lower(),
                    PasswordHasher.hash_password(password),
                    role_id,
                    hospital_id,
                    pharmacy_id,
                    1 if is_active else 0,
                    role_code,
                ),
            )
            user_id = int(cursor.lastrowid)
            connection.execute(
                """
                INSERT OR IGNORE INTO user_preferences
                    (user_id, theme, language, notifications_enabled,
                     low_stock_alerts, expiration_alerts, prediction_alerts,
                     interaction_alerts, email_digest_enabled)
                VALUES (?, 'light', 'fa', 1, 1, 1, 1, 1, 0);
                """,
                (user_id,),
            )
            return user_id

    @staticmethod
    def update_user_scope(
        user_id: int,
        role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
        is_active: bool,
    ) -> None:
        """Update role, organization assignment, and active status."""

        role_id = AdminRepository._role_id_by_code(role_code)
        with db_session() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET role_id = ?, hospital_id = ?, pharmacy_id = ?, is_active = ?,
                    approval_status = CASE WHEN ? = 1 THEN 'approved' ELSE approval_status END,
                    approved_at = CASE WHEN ? = 1 THEN COALESCE(approved_at, CURRENT_TIMESTAMP) ELSE approved_at END
                WHERE id = ?;
                """,
                (role_id, hospital_id, pharmacy_id, 1 if is_active else 0, 1 if is_active else 0, 1 if is_active else 0, user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("کاربر انتخاب‌شده پیدا نشد.")

    @staticmethod
    def reset_user_password(user_id: int, new_password: str) -> None:
        """Reset one user password from the admin panel."""

        with db_session() as connection:
            cursor = connection.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?;",
                (PasswordHasher.hash_password(new_password), user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("کاربر انتخاب‌شده پیدا نشد.")

    @staticmethod
    def pending_registration_requests() -> list[dict[str, Any]]:
        """Return public registration requests waiting for admin review."""

        return AdminRepository.list_users(status="pending")

    @staticmethod
    def review_registration_request(
        user_id: int,
        final_role_code: str,
        hospital_id: int | None,
        pharmacy_id: int | None,
        decision: str,
        admin_user_id: int | None,
        notes: str = "",
    ) -> None:
        """Approve, reject, or suspend a registration request."""

        if decision not in {"approved", "rejected", "suspended"}:
            raise ValueError("تصمیم انتخاب‌شده معتبر نیست.")
        role_id = AdminRepository._role_id_by_code(final_role_code)
        is_active = 1 if decision == "approved" else 0
        with db_session() as connection:
            cursor = connection.execute(
                """
                UPDATE users
                SET role_id = ?, hospital_id = ?, pharmacy_id = ?, is_active = ?,
                    approval_status = ?, approved_by = ?, approved_at = CURRENT_TIMESTAMP,
                    approval_notes = ?
                WHERE id = ? AND is_system_owner = 0;
                """,
                (role_id, hospital_id, pharmacy_id, is_active, decision, admin_user_id, notes.strip(), user_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("درخواست انتخاب‌شده پیدا نشد یا قابل تغییر نیست.")

    @staticmethod
    def list_hospitals(search: str = "", status: str = "all") -> list[dict[str, Any]]:
        """Return managed hospitals with assigned user counts."""

        where_sql, params = AdminRepository._organization_where("hospitals", search, status)
        query = f"""
            SELECT
                hospitals.id,
                hospitals.name,
                hospitals.code,
                hospitals.province,
                hospitals.city,
                hospitals.type,
                hospitals.bed_count,
                hospitals.manager_name,
                hospitals.contact_phone,
                hospitals.address,
                hospitals.status,
                hospitals.created_at,
                COUNT(users.id) AS user_count
            FROM hospitals
            LEFT JOIN users ON users.hospital_id = hospitals.id
            {where_sql}
            GROUP BY hospitals.id
            ORDER BY hospitals.created_at DESC, hospitals.id DESC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def create_hospital(data: dict[str, Any]) -> int:
        """Create a hospital organization record."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO hospitals
                    (name, code, province, city, type, bed_count, manager_name,
                     contact_phone, address, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["name"],
                    data.get("code", ""),
                    data.get("province", ""),
                    data.get("city", ""),
                    data.get("type", "general"),
                    int(data.get("bed_count", 0)),
                    data.get("manager_name", ""),
                    data.get("contact_phone", ""),
                    data.get("address", ""),
                    data.get("status", "active"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def update_hospital(hospital_id: int, data: dict[str, Any]) -> None:
        """Update a hospital organization record."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                UPDATE hospitals
                SET name = ?, code = ?, province = ?, city = ?, type = ?, bed_count = ?,
                    manager_name = ?, contact_phone = ?, address = ?, status = ?
                WHERE id = ?;
                """,
                (
                    data["name"],
                    data.get("code", ""),
                    data.get("province", ""),
                    data.get("city", ""),
                    data.get("type", "general"),
                    int(data.get("bed_count", 0)),
                    data.get("manager_name", ""),
                    data.get("contact_phone", ""),
                    data.get("address", ""),
                    data.get("status", "active"),
                    hospital_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("بیمارستان انتخاب‌شده پیدا نشد.")

    @staticmethod
    def list_pharmacies(search: str = "", status: str = "all") -> list[dict[str, Any]]:
        """Return managed pharmacies with assigned user counts."""

        where_sql, params = AdminRepository._organization_where("pharmacies", search, status)
        query = f"""
            SELECT
                pharmacies.id,
                pharmacies.name,
                pharmacies.province,
                pharmacies.city,
                pharmacies.license_number,
                pharmacies.owner_name,
                pharmacies.contact_phone,
                pharmacies.address,
                pharmacies.service_level,
                pharmacies.status,
                pharmacies.created_at,
                COUNT(users.id) AS user_count
            FROM pharmacies
            LEFT JOIN users ON users.pharmacy_id = pharmacies.id
            {where_sql}
            GROUP BY pharmacies.id
            ORDER BY pharmacies.created_at DESC, pharmacies.id DESC;
        """
        with db_session() as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def create_pharmacy(data: dict[str, Any]) -> int:
        """Create a pharmacy organization record."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                INSERT INTO pharmacies
                    (name, province, city, license_number, owner_name, contact_phone,
                     address, service_level, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    data["name"],
                    data.get("province", ""),
                    data.get("city", ""),
                    data.get("license_number", ""),
                    data.get("owner_name", ""),
                    data.get("contact_phone", ""),
                    data.get("address", ""),
                    data.get("service_level", "retail"),
                    data.get("status", "active"),
                ),
            )
            return int(cursor.lastrowid)

    @staticmethod
    def update_pharmacy(pharmacy_id: int, data: dict[str, Any]) -> None:
        """Update a pharmacy organization record."""

        with db_session() as connection:
            cursor = connection.execute(
                """
                UPDATE pharmacies
                SET name = ?, province = ?, city = ?, license_number = ?, owner_name = ?,
                    contact_phone = ?, address = ?, service_level = ?, status = ?
                WHERE id = ?;
                """,
                (
                    data["name"],
                    data.get("province", ""),
                    data.get("city", ""),
                    data.get("license_number", ""),
                    data.get("owner_name", ""),
                    data.get("contact_phone", ""),
                    data.get("address", ""),
                    data.get("service_level", "retail"),
                    data.get("status", "active"),
                    pharmacy_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError("داروخانه انتخاب‌شده پیدا نشد.")

    @staticmethod
    def recent_activity(limit: int = 80) -> list[dict[str, Any]]:
        """Return recent auditable system actions."""

        query = """
            SELECT
                activity_logs.id,
                activity_logs.action,
                activity_logs.entity_type,
                activity_logs.entity_id,
                activity_logs.details,
                activity_logs.created_at,
                COALESCE(users.full_name, 'سامانه') AS actor_name,
                COALESCE(users.email, '') AS actor_email
            FROM activity_logs
            LEFT JOIN users ON users.id = activity_logs.user_id
            ORDER BY activity_logs.created_at DESC, activity_logs.id DESC
            LIMIT ?;
        """
        with db_session() as connection:
            rows = connection.execute(query, (limit,)).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def organization_options() -> dict[str, list[dict[str, Any]]]:
        """Return active hospitals and pharmacies for assignment controls."""

        with db_session() as connection:
            hospitals = connection.execute(
                "SELECT id, name FROM hospitals WHERE status = 'active' ORDER BY name ASC;"
            ).fetchall()
            pharmacies = connection.execute(
                "SELECT id, name FROM pharmacies WHERE status = 'active' ORDER BY name ASC;"
            ).fetchall()
        return {
            "hospitals": [dict(row) for row in hospitals],
            "pharmacies": [dict(row) for row in pharmacies],
        }

    @staticmethod
    def _role_id_by_code(role_code: str) -> int:
        """Return role id or raise a safe validation error."""

        with db_session() as connection:
            row = connection.execute(
                "SELECT id FROM roles WHERE code = ? LIMIT 1;",
                (role_code,),
            ).fetchone()
        if row is None:
            raise ValueError("نقش انتخاب‌شده معتبر نیست.")
        return int(row["id"])

    @staticmethod
    def _organization_where(table_name: str, search: str, status: str) -> tuple[str, list[Any]]:
        """Build a safe WHERE clause for organization tables."""

        conditions: list[str] = []
        params: list[Any] = []
        cleaned = search.strip()
        if cleaned:
            like = f"%{cleaned}%"
            if table_name == "hospitals":
                conditions.append(
                    "(hospitals.name LIKE ? OR hospitals.city LIKE ? OR hospitals.code LIKE ? OR hospitals.manager_name LIKE ?)"
                )
                params.extend([like, like, like, like])
            else:
                conditions.append(
                    "(pharmacies.name LIKE ? OR pharmacies.province LIKE ? OR pharmacies.city LIKE ? OR pharmacies.license_number LIKE ? OR pharmacies.owner_name LIKE ?)"
                )
                params.extend([like, like, like, like, like])
        if status != "all":
            conditions.append(f"{table_name}.status = ?")
            params.append(status)
        if not conditions:
            return "", params
        return "WHERE " + " AND ".join(conditions), params
