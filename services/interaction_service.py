"""Business service for clinical drug-interaction checking."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from itertools import combinations

from config import INTERACTION_SEVERITY_LABELS, INTERACTION_SEVERITY_ORDER
from database.repositories import ActivityLogRepository, InteractionRepository
from models.entities import (
    InteractionAssessment,
    InteractionDrugProfile,
    InteractionFinding,
    InteractionFormData,
    InteractionRule,
)
from utils.validators import clean_text

SAFE_SEVERITIES = set(INTERACTION_SEVERITY_LABELS)
WRITE_ROLES = {"administrator", "hospital_manager", "pharmacy_manager", "healthcare_org"}
DELETE_ROLES = {"administrator"}
DOSAGE_PATTERN = re.compile(
    r"(?:\d+|[۰-۹]+)\s*(?:mg|mcg|g|iu|unit|ml|میلی\s*گرم|گرم|واحد|عدد)?",
    re.IGNORECASE,
)
SPLIT_PATTERN = re.compile(r"[,،\n;؛]+")


@dataclass(frozen=True)
class InteractionServiceResult:
    """Standard result object for interaction mutations."""

    success: bool
    message: str
    entity_id: int | None = None


class DrugInteractionService:
    """Coordinate interaction matching, validation, and audit logging."""

    @staticmethod
    def can_write(role_code: str) -> bool:
        """Return whether this role can add new clinical interaction rules."""

        return role_code in WRITE_ROLES

    @staticmethod
    def can_delete(role_code: str) -> bool:
        """Return whether this role can delete interaction rules."""

        return role_code in DELETE_ROLES

    @classmethod
    def build_profiles_from_manual_text(cls, raw_text: str) -> list[InteractionDrugProfile]:
        """Parse comma/newline separated manual drug names into profiles."""

        profiles: list[InteractionDrugProfile] = []
        for item in SPLIT_PATTERN.split(raw_text):
            cleaned = clean_text(item, 120)
            if cleaned:
                profiles.append(
                    InteractionDrugProfile(
                        display_name=cleaned,
                        aliases=cls._aliases_for(cleaned, ""),
                        source="manual",
                    )
                )
        return profiles

    @classmethod
    def assess_interactions(
        cls,
        profiles: list[InteractionDrugProfile],
    ) -> InteractionAssessment:
        """Analyze selected drugs against the interaction knowledge base."""

        unique_profiles = cls._deduplicate_profiles(profiles)
        selected_names = [profile.display_name for profile in unique_profiles]
        if len(unique_profiles) < 2:
            return InteractionAssessment(
                selected_drugs=selected_names,
                checked_pair_count=0,
                findings=[],
                highest_severity="low",
                safety_summary="برای بررسی تداخل، حداقل دو دارو را انتخاب یا وارد کنید.",
                recommended_next_step="دو یا چند دارو را انتخاب کنید و سپس تحلیل را اجرا کنید.",
            )

        rules = InteractionRepository.list_all()
        findings: list[InteractionFinding] = []
        checked_pair_count = 0
        matched_rule_ids: set[tuple[int, str, str]] = set()

        for profile_a, profile_b in combinations(unique_profiles, 2):
            checked_pair_count += 1
            for rule in rules:
                matched_by = cls._match_rule(rule, profile_a, profile_b)
                if not matched_by:
                    continue
                key = (rule.id, profile_a.display_name, profile_b.display_name)
                if key in matched_rule_ids:
                    continue
                matched_rule_ids.add(key)
                findings.append(
                    InteractionFinding(
                        rule_id=rule.id,
                        drug_a=profile_a.display_name,
                        drug_b=profile_b.display_name,
                        severity=rule.severity,
                        severity_label=INTERACTION_SEVERITY_LABELS.get(rule.severity, "نامشخص"),
                        description=rule.description,
                        clinical_recommendation=rule.clinical_recommendation,
                        reference=rule.reference,
                        mechanism=rule.mechanism,
                        alternative_drugs=rule.alternative_drugs,
                        monitoring_plan=rule.monitoring_plan,
                        evidence_level=rule.evidence_level,
                        matched_by=matched_by,
                    )
                )

        findings.sort(
            key=lambda item: INTERACTION_SEVERITY_ORDER.get(item.severity, 0),
            reverse=True,
        )
        highest = findings[0].severity if findings else "low"
        summary, next_step = cls._assessment_messages(findings, checked_pair_count)
        return InteractionAssessment(
            selected_drugs=selected_names,
            checked_pair_count=checked_pair_count,
            findings=findings,
            highest_severity=highest,
            safety_summary=summary,
            recommended_next_step=next_step,
        )

    @staticmethod
    def build_rule_payload(
        primary_drug: str,
        secondary_drug: str,
        severity: str,
        description: str,
        clinical_recommendation: str,
        reference: str,
        mechanism: str,
        alternative_drugs: str,
        monitoring_plan: str,
        evidence_level: str,
    ) -> InteractionFormData:
        """Normalize a rule form into a typed payload."""

        return InteractionFormData(
            primary_drug=clean_text(primary_drug, 120),
            secondary_drug=clean_text(secondary_drug, 120),
            severity=severity,
            description=clean_text(description, 700),
            clinical_recommendation=clean_text(clinical_recommendation, 700),
            reference=clean_text(reference, 240),
            mechanism=clean_text(mechanism, 500),
            alternative_drugs=clean_text(alternative_drugs, 500),
            monitoring_plan=clean_text(monitoring_plan, 500),
            evidence_level=clean_text(evidence_level, 80) or "متوسط",
        )

    @classmethod
    def create_rule(
        cls,
        data: InteractionFormData,
        user_id: int | None,
        role_code: str,
    ) -> InteractionServiceResult:
        """Validate and create an interaction rule."""

        if not cls.can_write(role_code):
            return InteractionServiceResult(False, "نقش شما اجازه ثبت قانون تداخل دارویی ندارد.")
        valid, message = cls.validate_rule_payload(data)
        if not valid:
            return InteractionServiceResult(False, message)
        try:
            rule_id = InteractionRepository.create(data)
            ActivityLogRepository.log(
                user_id,
                "create_interaction_rule",
                "interaction",
                rule_id,
                f"ثبت تداخل: {data.primary_drug} + {data.secondary_drug}",
            )
            return InteractionServiceResult(True, "قانون تداخل دارویی با موفقیت ثبت شد.", rule_id)
        except sqlite3.IntegrityError:
            return InteractionServiceResult(False, "این ترکیب دارویی قبلاً در دانشنامه ثبت شده است.")

    @classmethod
    def delete_rule(
        cls,
        rule_id: int,
        user_id: int | None,
        role_code: str,
    ) -> InteractionServiceResult:
        """Delete an interaction rule when the user has permission."""

        if not cls.can_delete(role_code):
            return InteractionServiceResult(False, "فقط مدیر سامانه اجازه حذف قانون تداخل را دارد.")
        try:
            InteractionRepository.delete(rule_id)
            ActivityLogRepository.log(user_id, "delete_interaction_rule", "interaction", rule_id)
            return InteractionServiceResult(True, "قانون تداخل دارویی حذف شد.")
        except ValueError as error:
            return InteractionServiceResult(False, str(error))

    @staticmethod
    def validate_rule_payload(data: InteractionFormData) -> tuple[bool, str]:
        """Validate clinical interaction rule fields."""

        if len(data.primary_drug) < 2 or len(data.secondary_drug) < 2:
            return False, "نام هر دو دارو باید حداقل ۲ کاراکتر باشد."
        if _normalize_name(data.primary_drug) == _normalize_name(data.secondary_drug):
            return False, "دو داروی یکسان نمی‌توانند به عنوان تداخل ثبت شوند."
        if data.severity not in SAFE_SEVERITIES:
            return False, "شدت تداخل انتخاب‌شده معتبر نیست."
        if len(data.description) < 12:
            return False, "توضیح تداخل باید دقیق‌تر نوشته شود."
        if len(data.clinical_recommendation) < 12:
            return False, "توصیه بالینی باید دقیق‌تر نوشته شود."
        if not data.reference:
            return False, "برای اعتمادپذیری، یک مرجع یا توضیح منبع وارد کنید."
        return True, "اطلاعات تداخل معتبر است."

    @classmethod
    def _match_rule(
        cls,
        rule: InteractionRule,
        profile_a: InteractionDrugProfile,
        profile_b: InteractionDrugProfile,
    ) -> str:
        """Return a match explanation if a rule applies to two profiles."""

        primary = rule.primary_drug
        secondary = rule.secondary_drug
        if cls._name_matches_profile(primary, profile_a) and cls._name_matches_profile(secondary, profile_b):
            return f"{primary} با {secondary}"
        if cls._name_matches_profile(primary, profile_b) and cls._name_matches_profile(secondary, profile_a):
            return f"{primary} با {secondary}"
        return ""

    @staticmethod
    def _name_matches_profile(rule_name: str, profile: InteractionDrugProfile) -> bool:
        """Return True when a rule drug name matches any profile alias."""

        normalized_rule = _normalize_name(rule_name)
        if not normalized_rule:
            return False
        for alias in profile.aliases:
            normalized_alias = _normalize_name(alias)
            if not normalized_alias:
                continue
            if normalized_rule == normalized_alias:
                return True
            if len(normalized_rule) >= 4 and normalized_rule in normalized_alias:
                return True
            if len(normalized_alias) >= 4 and normalized_alias in normalized_rule:
                return True
        return False

    @classmethod
    def _aliases_for(cls, name: str, generic_name: str) -> tuple[str, ...]:
        """Build useful matching aliases for a drug name and generic name."""

        aliases: list[str] = []
        for value in (name, generic_name, _remove_dosage(name), _remove_dosage(generic_name)):
            cleaned = clean_text(value, 120) if value else ""
            if cleaned and cleaned not in aliases:
                aliases.append(cleaned)
        return tuple(aliases)

    @classmethod
    def profile_from_drug_record(
        cls,
        name: str,
        generic_name: str,
        batch_number: str = "",
    ) -> InteractionDrugProfile:
        """Create a matching profile from a drug-management record."""

        display = name if not batch_number else f"{name} · بچ {batch_number}"
        return InteractionDrugProfile(
            display_name=display,
            aliases=cls._aliases_for(name, generic_name),
            source="inventory",
        )

    @staticmethod
    def _deduplicate_profiles(
        profiles: list[InteractionDrugProfile],
    ) -> list[InteractionDrugProfile]:
        """Remove duplicate drug profiles while preserving user order."""

        unique: list[InteractionDrugProfile] = []
        seen: set[str] = set()
        for profile in profiles:
            key = _normalize_name(profile.display_name)
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(profile)
        return unique

    @staticmethod
    def _assessment_messages(
        findings: list[InteractionFinding],
        checked_pair_count: int,
    ) -> tuple[str, str]:
        """Return Persian clinical summary and next-step guidance."""

        if not findings:
            return (
                f"در {checked_pair_count} جفت دارویی بررسی‌شده، قانون تداخل ثبت‌شده‌ای پیدا نشد.",
                "نسخه را همچنان با سابقه حساسیت، سن، بارداری، عملکرد کلیه/کبد و تشخیص پزشک بررسی کنید.",
            )
        highest = findings[0].severity
        if highest == "contraindicated":
            return (
                "حداقل یک تداخل با سطح منع مصرف همزمان شناسایی شد.",
                "قبل از مصرف یا تحویل دارو، بررسی پزشک/داروساز مسئول الزامی است.",
            )
        if highest == "high":
            return (
                "حداقل یک تداخل شدید شناسایی شد که می‌تواند ایمنی بیمار را تحت تأثیر قرار دهد.",
                "نیاز به ارزیابی بالینی، انتخاب جایگزین یا برنامه پایش دقیق وجود دارد.",
            )
        if highest == "medium":
            return (
                "تداخل متوسط شناسایی شد؛ مصرف همزمان ممکن است با پایش و آموزش بیمار قابل مدیریت باشد.",
                "شرایط بیمار و داروهای همزمان را بررسی و برنامه پایش را ثبت کنید.",
            )
        return (
            "تداخل خفیف شناسایی شد.",
            "معمولاً با اطلاع‌رسانی، پایش علائم و مستندسازی قابل مدیریت است.",
        )


def _remove_dosage(value: str) -> str:
    """Remove common dosage tokens from a drug name."""

    return clean_text(DOSAGE_PATTERN.sub("", value), 120)


def _normalize_name(value: str) -> str:
    """Normalize Persian/English medication names for resilient matching."""

    normalized = value.strip().lower()
    normalized = normalized.replace("ي", "ی").replace("ك", "ک")
    normalized = normalized.replace("‌", " ")
    normalized = _remove_dosage(normalized)
    normalized = re.sub(r"[^a-z0-9\u0600-\u06ff]+", "", normalized)
    return normalized
