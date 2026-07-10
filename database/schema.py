"""Database schema creation for the PharmaGuard AI foundation."""

from __future__ import annotations

import sqlite3

from database.connection import db_session

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name_fa TEXT NOT NULL,
        description TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS hospitals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        city TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'general',
        bed_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS pharmacies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        province TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL,
        license_number TEXT UNIQUE,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        full_name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        role_id INTEGER NOT NULL,
        hospital_id INTEGER,
        pharmacy_id INTEGER,
        is_active INTEGER NOT NULL DEFAULT 1,
        approval_status TEXT NOT NULL DEFAULT 'approved',
        requested_role TEXT NOT NULL DEFAULT '',
        requested_organization_type TEXT NOT NULL DEFAULT '',
        requested_organization_name TEXT NOT NULL DEFAULT '',
        approval_notes TEXT NOT NULL DEFAULT '',
        approved_by INTEGER,
        approved_at TEXT,
        is_system_owner INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_login_at TEXT,
        FOREIGN KEY (role_id) REFERENCES roles(id),
        FOREIGN KEY (hospital_id) REFERENCES hospitals(id),
        FOREIGN KEY (pharmacy_id) REFERENCES pharmacies(id),
        FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS drug_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        description TEXT NOT NULL DEFAULT ''
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS suppliers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        city TEXT NOT NULL DEFAULT '',
        reliability_score REAL NOT NULL DEFAULT 0.75,
        average_lead_time_days INTEGER NOT NULL DEFAULT 7
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS drugs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        generic_name TEXT NOT NULL DEFAULT '',
        category_id INTEGER,
        manufacturer TEXT NOT NULL DEFAULT '',
        batch_number TEXT NOT NULL DEFAULT '',
        expiration_date TEXT,
        supplier_id INTEGER,
        unit TEXT NOT NULL DEFAULT 'عدد',
        current_stock INTEGER NOT NULL DEFAULT 0,
        minimum_stock INTEGER NOT NULL DEFAULT 0,
        monthly_consumption INTEGER NOT NULL DEFAULT 0,
        availability_score REAL NOT NULL DEFAULT 1.0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name, batch_number),
        FOREIGN KEY (category_id) REFERENCES drug_categories(id),
        FOREIGN KEY (supplier_id) REFERENCES suppliers(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS predictions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        drug_id INTEGER NOT NULL,
        risk_level TEXT NOT NULL,
        probability REAL NOT NULL,
        confidence REAL NOT NULL,
        explanation TEXT NOT NULL,
        recommendation TEXT NOT NULL,
        model_version TEXT NOT NULL DEFAULT 'PG-SHORTAGE-XAI-0.5',
        feature_importance_json TEXT NOT NULL DEFAULT '{}',
        top_factors TEXT NOT NULL DEFAULT '',
        suggested_action TEXT NOT NULL DEFAULT '',
        monitoring_plan TEXT NOT NULL DEFAULT '',
        scenario_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (drug_id) REFERENCES drugs(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS interactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        primary_drug TEXT NOT NULL,
        secondary_drug TEXT NOT NULL,
        severity TEXT NOT NULL,
        description TEXT NOT NULL,
        clinical_recommendation TEXT NOT NULL,
        reference TEXT NOT NULL DEFAULT '',
        mechanism TEXT NOT NULL DEFAULT '',
        alternative_drugs TEXT NOT NULL DEFAULT '',
        monitoring_plan TEXT NOT NULL DEFAULT '',
        evidence_level TEXT NOT NULL DEFAULT 'متوسط',
        UNIQUE(primary_drug, secondary_drug)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS scanner_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        image_name TEXT NOT NULL,
        recognized_drug_name TEXT NOT NULL DEFAULT '',
        matched_drug_id INTEGER,
        confidence REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'unmatched',
        extracted_text TEXT NOT NULL DEFAULT '',
        warnings TEXT NOT NULL DEFAULT '',
        suggested_alternatives TEXT NOT NULL DEFAULT '',
        interaction_summary TEXT NOT NULL DEFAULT '',
        prediction_summary TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
        FOREIGN KEY (matched_drug_id) REFERENCES drugs(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'info',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY,
        theme TEXT NOT NULL DEFAULT 'light',
        language TEXT NOT NULL DEFAULT 'fa',
        notifications_enabled INTEGER NOT NULL DEFAULT 1,
        low_stock_alerts INTEGER NOT NULL DEFAULT 1,
        expiration_alerts INTEGER NOT NULL DEFAULT 1,
        prediction_alerts INTEGER NOT NULL DEFAULT 1,
        interaction_alerts INTEGER NOT NULL DEFAULT 1,
        email_digest_enabled INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS drug_references (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_key TEXT NOT NULL UNIQUE,
        canonical_fa TEXT NOT NULL,
        canonical_en TEXT NOT NULL,
        atc_code TEXT NOT NULL DEFAULT '',
        therapeutic_class_fa TEXT NOT NULL DEFAULT '',
        aliases_json TEXT NOT NULL DEFAULT '[]',
        common_strengths_json TEXT NOT NULL DEFAULT '[]',
        safety_note TEXT NOT NULL DEFAULT '',
        source_note TEXT NOT NULL DEFAULT '',
        rxnorm_rxcui TEXT NOT NULL DEFAULT '',
        openfda_cached_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS activity_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL DEFAULT '',
        entity_id INTEGER,
        details TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS import_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_name TEXT NOT NULL,
        total_rows INTEGER NOT NULL DEFAULT 0,
        valid_rows INTEGER NOT NULL DEFAULT 0,
        invalid_rows INTEGER NOT NULL DEFAULT 0,
        duplicate_rows INTEGER NOT NULL DEFAULT 0,
        inserted_rows INTEGER NOT NULL DEFAULT 0,
        updated_rows INTEGER NOT NULL DEFAULT 0,
        skipped_rows INTEGER NOT NULL DEFAULT 0,
        user_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS import_row_errors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id INTEGER NOT NULL,
        row_number INTEGER NOT NULL,
        status TEXT NOT NULL,
        message TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (batch_id) REFERENCES import_batches(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scanner_history_created ON scanner_history(created_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_scanner_history_drug ON scanner_history(matched_drug_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_import_batches_created ON import_batches(created_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_drugs_name ON drugs(name);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_drugs_category ON drugs(category_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_drugs_supplier ON drugs(supplier_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_drugs_expiration ON drugs(expiration_date);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_drugs_stock ON drugs(current_stock, minimum_stock);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_predictions_drug_created ON predictions(drug_id, created_at);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_interactions_primary ON interactions(primary_drug);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_interactions_secondary ON interactions(secondary_drug);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_interactions_severity ON interactions(severity);
    """,
)

MIGRATION_STATEMENTS: tuple[str, ...] = (
    "ALTER TABLE notifications ADD COLUMN notification_type TEXT NOT NULL DEFAULT 'system';",
    "ALTER TABLE notifications ADD COLUMN source_entity_type TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE notifications ADD COLUMN source_entity_id INTEGER;",
    "ALTER TABLE notifications ADD COLUMN action_page TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE notifications ADD COLUMN expires_at TEXT;",
    "CREATE INDEX IF NOT EXISTS idx_notifications_user_read ON notifications(user_id, is_read, created_at);",
    "CREATE INDEX IF NOT EXISTS idx_notifications_source ON notifications(source_entity_type, source_entity_id);",
    "CREATE INDEX IF NOT EXISTS idx_user_preferences_theme ON user_preferences(theme);",
    "ALTER TABLE hospitals ADD COLUMN code TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE hospitals ADD COLUMN province TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE hospitals ADD COLUMN address TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE hospitals ADD COLUMN contact_phone TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE hospitals ADD COLUMN manager_name TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE hospitals ADD COLUMN status TEXT NOT NULL DEFAULT 'active';",
    "ALTER TABLE pharmacies ADD COLUMN province TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE pharmacies ADD COLUMN owner_name TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE pharmacies ADD COLUMN address TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE pharmacies ADD COLUMN contact_phone TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE pharmacies ADD COLUMN service_level TEXT NOT NULL DEFAULT 'retail';",
    "ALTER TABLE pharmacies ADD COLUMN status TEXT NOT NULL DEFAULT 'active';",
    """
    CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name_fa TEXT NOT NULL,
        module TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
        FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_hospitals_status ON hospitals(status);",
    "CREATE INDEX IF NOT EXISTS idx_pharmacies_status ON pharmacies(status);",
    "CREATE INDEX IF NOT EXISTS idx_pharmacies_location ON pharmacies(province, city);",
    "CREATE INDEX IF NOT EXISTS idx_users_role ON users(role_id);",
    "CREATE INDEX IF NOT EXISTS idx_users_hospital ON users(hospital_id);",
    "CREATE INDEX IF NOT EXISTS idx_users_pharmacy ON users(pharmacy_id);",
    "CREATE INDEX IF NOT EXISTS idx_activity_logs_created ON activity_logs(created_at);",
    "CREATE INDEX IF NOT EXISTS idx_role_permissions_role ON role_permissions(role_id);",
    "ALTER TABLE interactions ADD COLUMN mechanism TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE interactions ADD COLUMN alternative_drugs TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE interactions ADD COLUMN monitoring_plan TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE interactions ADD COLUMN evidence_level TEXT NOT NULL DEFAULT 'متوسط';",
    "ALTER TABLE users ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'approved';",
    "ALTER TABLE users ADD COLUMN requested_role TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE users ADD COLUMN requested_organization_type TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE users ADD COLUMN requested_organization_name TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE users ADD COLUMN approval_notes TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE users ADD COLUMN approved_by INTEGER;",
    "ALTER TABLE users ADD COLUMN approved_at TEXT;",
    "ALTER TABLE users ADD COLUMN is_system_owner INTEGER NOT NULL DEFAULT 0;",
    "CREATE INDEX IF NOT EXISTS idx_users_approval_status ON users(approval_status);",
    "CREATE INDEX IF NOT EXISTS idx_users_system_owner ON users(is_system_owner);",
    """
    CREATE TABLE IF NOT EXISTS drug_references (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        reference_key TEXT NOT NULL UNIQUE,
        canonical_fa TEXT NOT NULL,
        canonical_en TEXT NOT NULL,
        atc_code TEXT NOT NULL DEFAULT '',
        therapeutic_class_fa TEXT NOT NULL DEFAULT '',
        aliases_json TEXT NOT NULL DEFAULT '[]',
        common_strengths_json TEXT NOT NULL DEFAULT '[]',
        safety_note TEXT NOT NULL DEFAULT '',
        source_note TEXT NOT NULL DEFAULT '',
        rxnorm_rxcui TEXT NOT NULL DEFAULT '',
        openfda_cached_json TEXT NOT NULL DEFAULT '{}',
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """,
    "CREATE INDEX IF NOT EXISTS idx_drug_references_key ON drug_references(reference_key);",
    "CREATE INDEX IF NOT EXISTS idx_drug_references_en ON drug_references(canonical_en);",
    "ALTER TABLE predictions ADD COLUMN model_version TEXT NOT NULL DEFAULT 'PG-SHORTAGE-XAI-0.5';",
    "ALTER TABLE predictions ADD COLUMN feature_importance_json TEXT NOT NULL DEFAULT '{}';",
    "ALTER TABLE predictions ADD COLUMN top_factors TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE predictions ADD COLUMN suggested_action TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE predictions ADD COLUMN monitoring_plan TEXT NOT NULL DEFAULT '';",
    "ALTER TABLE predictions ADD COLUMN scenario_json TEXT NOT NULL DEFAULT '{}';",
)


def create_schema() -> None:
    """Create all database tables, indexes, and additive migrations."""

    with db_session() as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        _apply_additive_migrations(connection)


def _apply_additive_migrations(connection: sqlite3.Connection) -> None:
    """Apply backward-compatible SQLite migrations for existing local databases."""

    for statement in MIGRATION_STATEMENTS:
        try:
            connection.execute(statement)
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise
