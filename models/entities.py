"""Typed domain entities used by services and views."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class DrugInventoryItem:
    """Inventory input used by the explainable shortage prediction service."""

    id: int
    name: str
    current_stock: int
    minimum_stock: int
    monthly_consumption: int
    availability_score: float
    lead_time_days: int
    supplier_reliability_score: float = 0.75
    supplier_delay_days: int = 0
    shipping_delay_days: int = 0
    emergency_demand_index: float = 0.0
    seasonality_index: float = 0.0
    hospital_criticality: float = 0.5
    historical_volatility: float = 0.25
    review_horizon_days: int = 30
    hospital_type: str = "general"


@dataclass(frozen=True)
class DrugCategory:
    """Drug category used by inventory forms and filters."""

    id: int
    name: str
    description: str


@dataclass(frozen=True)
class Supplier:
    """Supplier profile used by inventory and supply-chain modules."""

    id: int
    name: str
    city: str
    reliability_score: float
    average_lead_time_days: int


@dataclass(frozen=True)
class DrugRecord:
    """Full drug-management record returned by the repository layer."""

    id: int
    name: str
    generic_name: str
    category_id: int | None
    category_name: str
    manufacturer: str
    batch_number: str
    expiration_date: str | None
    supplier_id: int | None
    supplier_name: str
    unit: str
    current_stock: int
    minimum_stock: int
    monthly_consumption: int
    availability_score: float
    lead_time_days: int
    created_at: str


@dataclass(frozen=True)
class DrugFormData:
    """Validated input payload for creating or updating a drug."""

    name: str
    generic_name: str
    category_id: int | None
    manufacturer: str
    batch_number: str
    expiration_date: date | None
    supplier_id: int | None
    unit: str
    current_stock: int
    minimum_stock: int
    monthly_consumption: int
    availability_score: float


@dataclass(frozen=True)
class DrugFilters:
    """Search and filtering options for the drug list."""

    search: str = ""
    category_id: int | None = None
    supplier_id: int | None = None
    stock_status: str = "all"
    expiration_status: str = "all"
    sort_by: str = "name"
    sort_direction: str = "asc"


@dataclass(frozen=True)
class PaginatedDrugResult:
    """Paginated drug-list response."""

    rows: list[DrugRecord]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class InteractionRule:
    """Clinical medication interaction rule stored in the knowledge base."""

    id: int
    primary_drug: str
    secondary_drug: str
    severity: str
    description: str
    clinical_recommendation: str
    reference: str
    mechanism: str
    alternative_drugs: str
    monitoring_plan: str
    evidence_level: str


@dataclass(frozen=True)
class InteractionFormData:
    """Validated payload for creating a drug interaction rule."""

    primary_drug: str
    secondary_drug: str
    severity: str
    description: str
    clinical_recommendation: str
    reference: str
    mechanism: str
    alternative_drugs: str
    monitoring_plan: str
    evidence_level: str


@dataclass(frozen=True)
class InteractionDrugProfile:
    """Drug profile sent to the interaction engine for matching."""

    display_name: str
    aliases: tuple[str, ...]
    source: str


@dataclass(frozen=True)
class InteractionFinding:
    """One detected interaction between two selected drugs."""

    rule_id: int
    drug_a: str
    drug_b: str
    severity: str
    severity_label: str
    description: str
    clinical_recommendation: str
    reference: str
    mechanism: str
    alternative_drugs: str
    monitoring_plan: str
    evidence_level: str
    matched_by: str


@dataclass(frozen=True)
class InteractionAssessment:
    """Complete assessment result for a multi-drug interaction check."""

    selected_drugs: list[str]
    checked_pair_count: int
    findings: list[InteractionFinding]
    highest_severity: str
    safety_summary: str
    recommended_next_step: str


@dataclass(frozen=True)
class ScannerCandidate:
    """One possible inventory match returned by the scanner engine."""

    drug_id: int
    name: str
    generic_name: str
    manufacturer: str
    batch_number: str
    confidence: float
    match_reason: str


@dataclass(frozen=True)
class ScannerInteractionSummary:
    """Interaction summary produced after recognizing a scanned drug."""

    checked_pair_count: int
    finding_count: int
    highest_severity: str
    safety_summary: str
    recommended_next_step: str


@dataclass(frozen=True)
class ScannerPredictionSummary:
    """Shortage-risk summary attached to a scanner result."""

    risk_level: str
    probability: float
    confidence: float
    top_factor: str
    suggested_action: str


@dataclass(frozen=True)
class ScannerAnalysis:
    """Complete scanner analysis result for uploaded drug images."""

    file_name: str
    extracted_text: str
    image_quality: str
    status: str
    recognized_name: str
    matched_drug_id: int | None
    confidence: float
    candidates: list[ScannerCandidate]
    warnings: list[str]
    drug_information: dict[str, str]
    alternative_drugs: list[str]
    interaction_summary: ScannerInteractionSummary | None
    prediction_summary: ScannerPredictionSummary | None
    ai_explanation: str


@dataclass(frozen=True)
class ScannerHistoryRecord:
    """Persisted scanner history row for audit and follow-up."""

    id: int
    image_name: str
    recognized_drug_name: str
    matched_drug_name: str
    confidence: float
    status: str
    warnings: str
    created_at: str


@dataclass(frozen=True)
class NotificationRecord:
    """One user-facing notification displayed in the notification center."""

    id: int
    user_id: int | None
    title: str
    message: str
    severity: str
    notification_type: str
    source_entity_type: str
    source_entity_id: int | None
    action_page: str
    is_read: bool
    created_at: str


@dataclass(frozen=True)
class UserPreferences:
    """Persistent user interface and notification preferences."""

    user_id: int
    theme: str
    language: str
    notifications_enabled: bool
    low_stock_alerts: bool
    expiration_alerts: bool
    prediction_alerts: bool
    interaction_alerts: bool
    email_digest_enabled: bool
    updated_at: str


@dataclass(frozen=True)
class UserProfile:
    """Authenticated user profile with organization context."""

    id: int
    full_name: str
    email: str
    role_code: str
    role_name: str
    hospital_name: str
    pharmacy_name: str
    created_at: str
    last_login_at: str | None
