"""AI-ready drug scanner service.

The scanner is deterministic and auditable. It does not pretend that image OCR
is perfect. It uses three evidence layers in order of reliability:

1. User-entered or locally OCR-extracted label text.
2. International drug normalization using curated references and optional public
   RxNorm/openFDA lookups.
3. Organization inventory matching, batch/strength checks, interaction review,
   and shortage prediction.
"""

from __future__ import annotations

import hashlib
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from config import RISK_LABELS, UPLOAD_DIR, INTERACTION_SEVERITY_LABELS
from database.repositories import (
    ActivityLogRepository,
    DrugRepository,
    ScannerHistoryRepository,
)
from models.entities import (
    DrugInventoryItem,
    DrugRecord,
    InteractionDrugProfile,
    ScannerAnalysis,
    ScannerCandidate,
    ScannerInteractionSummary,
    ScannerPredictionSummary,
)
from services.drug_reference_service import (
    InternationalDrugReferenceService,
    ReferenceMatch,
)
from services.interaction_service import DrugInteractionService
from services.prediction_service import PredictionScenario, ShortagePredictionService
from utils.persian import format_iso_date_fa, percent_fa
from utils.validators import clean_text

SUPPORTED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MIN_CONFIDENT_MATCH = 0.72
HIGH_CONFIDENCE_MATCH = 0.86
MIN_REFERENCE_ONLY_MATCH = 0.58
MIN_REFERENCE_FOR_INVENTORY_MATCH = 0.70


class DrugScannerService:
    """Coordinate image intake, drug recognition, and clinical decision support."""

    @staticmethod
    def save_uploaded_image(file_name: str, content: bytes) -> Path:
        """Store uploaded scanner image with a content fingerprint."""

        safe_name = _safe_file_name(file_name)
        digest = hashlib.sha256(content).hexdigest()[:12]
        scanner_dir = UPLOAD_DIR / "scanner"
        scanner_dir.mkdir(parents=True, exist_ok=True)
        output_path = scanner_dir / f"{digest}_{safe_name}"
        output_path.write_bytes(content)
        return output_path

    @classmethod
    def analyze(
        cls,
        file_name: str,
        content: bytes,
        label_text: str,
        co_medications: str,
        use_international_lookup: bool = True,
    ) -> ScannerAnalysis:
        """Analyze one uploaded drug image and return an explainable result."""

        extension = Path(file_name).suffix.lower()
        warnings = cls._base_warnings(extension, content, label_text)
        extracted_text = cls._build_extracted_text(file_name, label_text)
        reference_match = InternationalDrugReferenceService.match_text(extracted_text)
        inventory_reference_match = (
            reference_match
            if reference_match and reference_match.score >= MIN_REFERENCE_FOR_INVENTORY_MATCH
            else None
        )
        candidates = cls._rank_inventory_candidates(extracted_text, inventory_reference_match)
        best_candidate = candidates[0] if candidates else None

        matched_drug = None
        if best_candidate and best_candidate.confidence >= MIN_CONFIDENT_MATCH:
            matched_drug = DrugRepository.get_by_id(best_candidate.drug_id)

        drug_information = cls._drug_information(matched_drug, reference_match, use_international_lookup)
        alternatives = cls._alternatives_for(matched_drug, candidates)
        prediction_summary = cls._prediction_summary(matched_drug)
        interaction_summary = cls._interaction_summary(matched_drug, reference_match, co_medications)
        warnings.extend(cls._reference_warnings(reference_match, matched_drug))
        warnings.extend(cls._clinical_warnings(matched_drug, prediction_summary, interaction_summary))

        status = cls._status_for(best_candidate, matched_drug, reference_match, warnings)
        recognized_name = cls._recognized_name(matched_drug, reference_match, extracted_text)
        confidence = cls._recognition_confidence(best_candidate, reference_match, matched_drug)
        image_quality = cls._image_quality(content, extracted_text)
        explanation = cls._ai_explanation(status, confidence, extracted_text, matched_drug, reference_match)

        return ScannerAnalysis(
            file_name=file_name,
            extracted_text=extracted_text,
            image_quality=image_quality,
            status=status,
            recognized_name=recognized_name,
            matched_drug_id=matched_drug.id if matched_drug else None,
            confidence=round(confidence, 3),
            candidates=candidates[:5],
            warnings=warnings,
            drug_information=drug_information,
            alternative_drugs=alternatives,
            interaction_summary=interaction_summary,
            prediction_summary=prediction_summary,
            ai_explanation=explanation,
        )

    @staticmethod
    def persist_analysis(
        analysis: ScannerAnalysis,
        user_id: int | None,
    ) -> int:
        """Persist scanner analysis and write an audit event."""

        interaction_summary = ""
        if analysis.interaction_summary:
            interaction_summary = (
                f"{analysis.interaction_summary.safety_summary} | "
                f"{analysis.interaction_summary.recommended_next_step}"
            )
        prediction_summary = ""
        if analysis.prediction_summary:
            prediction_summary = (
                f"{RISK_LABELS.get(analysis.prediction_summary.risk_level, analysis.prediction_summary.risk_level)} | "
                f"{percent_fa(analysis.prediction_summary.probability)} | "
                f"{analysis.prediction_summary.suggested_action}"
            )

        history_id = ScannerHistoryRepository.create(
            user_id=user_id,
            image_name=analysis.file_name,
            recognized_drug_name=analysis.recognized_name,
            matched_drug_id=analysis.matched_drug_id,
            confidence=analysis.confidence,
            status=analysis.status,
            extracted_text=analysis.extracted_text,
            warnings=" | ".join(analysis.warnings),
            suggested_alternatives="، ".join(analysis.alternative_drugs),
            interaction_summary=interaction_summary,
            prediction_summary=prediction_summary,
        )
        ActivityLogRepository.log(
            user_id,
            "scan_drug_image",
            "scanner_history",
            history_id,
            f"اسکن دارو: {analysis.recognized_name} / وضعیت {analysis.status}",
        )
        return history_id

    @staticmethod
    def _base_warnings(extension: str, content: bytes, label_text: str) -> list[str]:
        """Return operational warnings before clinical analysis."""

        warnings: list[str] = []
        if extension not in SUPPORTED_IMAGE_EXTENSIONS:
            warnings.append("فرمت تصویر برای اسکن دارو توصیه نمی‌شود؛ از PNG، JPG یا WEBP استفاده کنید.")
        if len(content) < 12_000:
            warnings.append("حجم تصویر کم است؛ برای تشخیص بهتر، عکس واضح‌تر از بسته یا بلیستر دارو بگیرید.")
        if not label_text.strip():
            warnings.append(
                "در این نسخه، تشخیص قطعی از روی تصویر بدون متن خوانا تضمین نمی‌شود؛ "
                "نام دارو، دوز یا شماره بچ را از روی بسته وارد کنید تا سامانه اشتباه تطبیق ندهد."
            )
        return warnings

    @staticmethod
    def _build_extracted_text(file_name: str, label_text: str) -> str:
        """Build scanner text from manual label input and high-signal file-name tokens."""

        manual = clean_text(label_text, 1_200)
        name_without_ext = Path(file_name).stem
        file_tokens = clean_text(re.sub(r"[_\-]+", " ", name_without_ext), 300)
        if not InternationalDrugReferenceService.text_has_meaningful_drug_signal(file_tokens):
            file_tokens = ""
        joined = " ".join(part for part in (manual, file_tokens) if part).strip()
        return joined or "متن قابل استخراج ثبت نشده است"

    @classmethod
    def _rank_inventory_candidates(
        cls,
        extracted_text: str,
        reference_match: ReferenceMatch | None,
    ) -> list[ScannerCandidate]:
        """Rank inventory records by scanner text and international reference match."""

        records = DrugRepository.list_for_scanner()
        normalized_text = _normalize(extracted_text)
        if not InternationalDrugReferenceService.text_has_meaningful_drug_signal(normalized_text):
            return []

        candidates: list[ScannerCandidate] = []
        extracted_strengths = InternationalDrugReferenceService.extract_strengths(extracted_text)
        for record in records:
            score, reason = cls._candidate_score(normalized_text, record, reference_match, extracted_strengths)
            if score < 0.45:
                continue
            candidates.append(
                ScannerCandidate(
                    drug_id=record.id,
                    name=record.name,
                    generic_name=record.generic_name,
                    manufacturer=record.manufacturer,
                    batch_number=record.batch_number,
                    confidence=round(score, 3),
                    match_reason=reason,
                )
            )
        candidates.sort(key=lambda item: item.confidence, reverse=True)
        return candidates

    @staticmethod
    def _candidate_score(
        normalized_text: str,
        record: DrugRecord,
        reference_match: ReferenceMatch | None,
        extracted_strengths: set[str],
    ) -> tuple[float, str]:
        """Score one inventory item against scanner evidence."""

        direct_score, direct_reason = _direct_record_score(normalized_text, record)
        reference_score = 0.0
        reference_reason = ""
        if reference_match is not None:
            reference_score = InternationalDrugReferenceService.score_record_against_reference(
                record,
                reference_match.reference,
            )
            reference_reason = f"تطبیق با مرجع بین‌المللی {reference_match.reference.canonical_en}"

            if reference_match.score >= MIN_REFERENCE_FOR_INVENTORY_MATCH and reference_score < 0.70:
                if direct_score < 0.90:
                    return max(direct_score * 0.25, 0.0), "رد تطبیق؛ با مرجع دارویی هم‌خوان نیست"

        if reference_match is not None and reference_match.score >= MIN_REFERENCE_FOR_INVENTORY_MATCH:
            score = max(direct_score, reference_score * 0.94, (direct_score * 0.55) + (reference_score * 0.45))
            reason = reference_reason if reference_score >= direct_score and reference_reason else direct_reason
        else:
            score = direct_score
            reason = direct_reason

        record_strengths = InternationalDrugReferenceService.extract_strengths(
            f"{record.name} {record.generic_name} {record.batch_number}"
        )
        if extracted_strengths and record_strengths:
            if extracted_strengths & record_strengths:
                score = min(1.0, score + 0.08)
                reason = f"{reason} + تطبیق دوز"
            elif reference_match and reference_match.score >= MIN_REFERENCE_FOR_INVENTORY_MATCH:
                score = max(0.0, score - 0.08)
                reason = f"{reason}؛ دوز نیازمند بازبینی"

        normalized_batch = _normalize(record.batch_number)
        if normalized_batch and normalized_batch in normalized_text:
            score = min(1.0, score + 0.12)
            reason = "تطبیق نام، مرجع دارویی و شماره بچ"
        return score, reason

    @staticmethod
    def _drug_information(
        record: DrugRecord | None,
        reference_match: ReferenceMatch | None,
        use_international_lookup: bool,
    ) -> dict[str, str]:
        """Return display-ready drug and reference information."""

        info: dict[str, str]
        if record is None:
            info = {
                "وضعیت موجودی": "دارو با اطمینان کافی در موجودی سازمانی پیدا نشد.",
                "اقدام": "دارو را از طریق مدیریت دارو ثبت کنید یا نام/دوز/بچ را دقیق‌تر وارد کنید.",
            }
        else:
            info = {
                "نام دارو": record.name,
                "نام ژنریک": record.generic_name or "ثبت نشده",
                "دسته": record.category_name,
                "تولیدکننده": record.manufacturer or "ثبت نشده",
                "شماره بچ": record.batch_number or "ثبت نشده",
                "تاریخ انقضا": format_iso_date_fa(record.expiration_date),
                "تأمین‌کننده": record.supplier_name,
                "موجودی فعلی": f"{record.current_stock} {record.unit}",
                "حداقل مجاز": f"{record.minimum_stock} {record.unit}",
            }

        if reference_match is not None:
            info.update(InternationalDrugReferenceService.reference_details(reference_match.reference))
            if use_international_lookup:
                info.update(InternationalDrugReferenceService.rxnorm_lookup(reference_match.reference.canonical_en.split("/")[0].strip()))
                info.update(InternationalDrugReferenceService.openfda_label_summary(reference_match.reference.canonical_en.split("/")[0].strip()))
        return info

    @staticmethod
    def _alternatives_for(
        record: DrugRecord | None,
        candidates: list[ScannerCandidate],
    ) -> list[str]:
        """Return alternative candidates when recognition is uncertain."""

        alternatives: list[str] = []
        for candidate in candidates:
            if record and candidate.drug_id == record.id:
                continue
            label = f"{candidate.name} ({candidate.match_reason}، اطمینان {percent_fa(candidate.confidence)})"
            alternatives.append(label)
            if len(alternatives) == 3:
                break
        return alternatives

    @staticmethod
    def _prediction_summary(record: DrugRecord | None) -> ScannerPredictionSummary | None:
        """Attach explainable shortage prediction to a recognized drug."""

        if record is None:
            return None
        item = DrugInventoryItem(
            id=record.id,
            name=record.name,
            current_stock=record.current_stock,
            minimum_stock=record.minimum_stock,
            monthly_consumption=record.monthly_consumption,
            availability_score=record.availability_score,
            lead_time_days=record.lead_time_days,
        )
        scenario = PredictionScenario(review_horizon_days=30, hospital_criticality=0.6)
        prediction = ShortagePredictionService.predict(item, scenario)
        return ScannerPredictionSummary(
            risk_level=prediction.risk_level,
            probability=prediction.probability,
            confidence=prediction.confidence,
            top_factor=prediction.top_factors[0] if prediction.top_factors else "نامشخص",
            suggested_action=prediction.suggested_action or prediction.recommendation,
        )

    @staticmethod
    def _interaction_summary(
        record: DrugRecord | None,
        reference_match: ReferenceMatch | None,
        co_medications: str,
    ) -> ScannerInteractionSummary | None:
        """Attach interaction analysis between recognized/reference drug and co-medications."""

        if not co_medications.strip():
            return None
        profiles: list[InteractionDrugProfile] = []
        if record is not None:
            profiles.append(
                DrugInteractionService.profile_from_drug_record(
                    record.name,
                    record.generic_name,
                    record.batch_number,
                )
            )
        elif reference_match is not None:
            profiles.append(
                InteractionDrugProfile(
                    display_name=reference_match.reference.canonical_fa,
                    aliases=(reference_match.reference.canonical_en, *reference_match.reference.aliases),
                    source="international_reference",
                )
            )
        else:
            return None
        profiles.extend(DrugInteractionService.build_profiles_from_manual_text(co_medications))
        assessment = DrugInteractionService.assess_interactions(profiles)
        return ScannerInteractionSummary(
            checked_pair_count=assessment.checked_pair_count,
            finding_count=len(assessment.findings),
            highest_severity=assessment.highest_severity,
            safety_summary=assessment.safety_summary,
            recommended_next_step=assessment.recommended_next_step,
        )

    @staticmethod
    def _reference_warnings(reference_match: ReferenceMatch | None, record: DrugRecord | None) -> list[str]:
        """Return warnings related to reference-only recognition."""

        if reference_match is None:
            return []
        if record is None and reference_match.score >= MIN_REFERENCE_ONLY_MATCH:
            return [
                "دارو در مرجع بین‌المللی شناسایی شد اما در موجودی سازمانی ثبت نشده است؛ "
                "قبل از تحویل، دارو را در مدیریت دارو ثبت یا موجودی را بازبینی کنید."
            ]
        return []

    @staticmethod
    def _clinical_warnings(
        record: DrugRecord | None,
        prediction: ScannerPredictionSummary | None,
        interaction: ScannerInteractionSummary | None,
    ) -> list[str]:
        """Return actionable warnings from inventory, prediction, and interaction signals."""

        warnings: list[str] = []
        if record is None:
            return warnings
        if record.current_stock <= 0:
            warnings.append("موجودی این دارو صفر است؛ تحویل یا مصرف باید با بررسی موجودی جایگزین انجام شود.")
        elif record.current_stock < record.minimum_stock:
            warnings.append("موجودی دارو کمتر از حداقل مجاز است؛ سفارش مجدد پیشنهاد می‌شود.")
        if prediction and prediction.risk_level in {"critical", "high"}:
            warnings.append("مدل پیش‌بینی، ریسک کمبود قابل توجه برای این دارو نشان می‌دهد.")
        if interaction and interaction.finding_count > 0:
            severity_label = INTERACTION_SEVERITY_LABELS.get(interaction.highest_severity, "نامشخص")
            warnings.append(f"برای داروهای همزمان، تداخل با سطح {severity_label} شناسایی شد.")
        return warnings

    @staticmethod
    def _status_for(
        candidate: ScannerCandidate | None,
        record: DrugRecord | None,
        reference_match: ReferenceMatch | None,
        warnings: list[str],
    ) -> str:
        """Classify scanner result status for workflow routing."""

        if record is None:
            if reference_match and reference_match.score >= MIN_REFERENCE_ONLY_MATCH:
                return "reference_only"
            return "unmatched"
        if candidate is None:
            return "unmatched"
        if candidate.confidence >= HIGH_CONFIDENCE_MATCH and not warnings:
            return "verified"
        if candidate.confidence >= HIGH_CONFIDENCE_MATCH:
            return "action_required"
        return "needs_review"

    @staticmethod
    def _recognized_name(
        record: DrugRecord | None,
        reference_match: ReferenceMatch | None,
        extracted_text: str,
    ) -> str:
        """Return recognized name without over-claiming low-confidence matches."""

        if record is not None:
            return record.name
        if reference_match and reference_match.score >= MIN_REFERENCE_ONLY_MATCH:
            return f"{reference_match.reference.canonical_fa} / {reference_match.reference.canonical_en}"
        return DrugScannerService._fallback_recognized_name(extracted_text)

    @staticmethod
    def _recognition_confidence(
        candidate: ScannerCandidate | None,
        reference_match: ReferenceMatch | None,
        record: DrugRecord | None,
    ) -> float:
        """Return the confidence for the recognized workflow status."""

        if record is not None and candidate is not None:
            return candidate.confidence
        if reference_match is not None:
            return reference_match.score
        return 0.0

    @staticmethod
    def _fallback_recognized_name(extracted_text: str) -> str:
        """Return a safe fallback name when no match exists."""

        text = extracted_text.strip()
        if not text or text == "متن قابل استخراج ثبت نشده است":
            return "نامشخص"
        return text[:80]

    @staticmethod
    def _image_quality(content: bytes, extracted_text: str) -> str:
        """Estimate image and label-text quality for transparent UX."""

        has_text = InternationalDrugReferenceService.text_has_meaningful_drug_signal(extracted_text)
        size = len(content)
        if has_text and size >= 80_000:
            return "مناسب برای تحلیل"
        if has_text:
            return "متن کافی، تصویر نیازمند بازبینی"
        if size >= 350_000:
            return "تصویر مناسب، متن خوانا وارد نشده"
        if size >= 80_000:
            return "قابل قبول، نیازمند متن روی بسته"
        return "نیازمند عکس واضح‌تر"

    @staticmethod
    def _ai_explanation(
        status: str,
        confidence: float,
        extracted_text: str,
        record: DrugRecord | None,
        reference_match: ReferenceMatch | None,
    ) -> str:
        """Explain why the scanner returned its current result."""

        if record is None and reference_match is None:
            return (
                "سامانه متن دارویی کافی برای تطبیق پیدا نکرد و از حدس‌زدن نام دارو خودداری کرد. "
                "برای جلوگیری از خطای بالینی، نام ژنریک/تجاری، دوز و شماره بچ را از روی بسته وارد کنید."
            )
        if record is None and reference_match is not None:
            return (
                f"دارو از روی متن «{extracted_text[:120]}» با مرجع بین‌المللی "
                f"«{reference_match.reference.canonical_en}» تطبیق داده شد، اما در موجودی سازمانی پیدا نشد. "
                f"اطمینان مرجع {percent_fa(confidence)} است."
            )
        status_text = {
            "verified": "تطبیق با اطمینان بالا انجام شد.",
            "action_required": "تطبیق انجام شد اما هشدار عملیاتی وجود دارد.",
            "needs_review": "تطبیق احتمالی است و باید توسط کاربر تأیید شود.",
            "unmatched": "تطبیق قطعی انجام نشد.",
            "reference_only": "تطبیق مرجع انجام شد اما دارو در موجودی سازمانی نیست.",
        }.get(status, "تحلیل کامل شد.")
        reference_text = ""
        if reference_match is not None:
            reference_text = f" مرجع دارویی شناسایی‌شده: {reference_match.reference.canonical_en}."
        return (
            f"{status_text} متن تحلیل‌شده شامل «{extracted_text[:120]}» بود و بهترین تطبیق با "
            f"«{record.name if record else 'نامشخص'}» با اطمینان {percent_fa(confidence)} ثبت شد.{reference_text}"
        )


def _direct_record_score(normalized_text: str, record: DrugRecord) -> tuple[float, str]:
    """Score direct text similarity against inventory fields."""

    fields = {
        "نام تجاری": record.name,
        "نام ژنریک": record.generic_name,
        "تولیدکننده": record.manufacturer,
        "شماره بچ": record.batch_number,
    }
    best_score = 0.0
    best_reason = "شباهت متنی"
    for label, value in fields.items():
        normalized_value = _normalize(value)
        if not normalized_value:
            continue
        ratio = SequenceMatcher(None, normalized_text, normalized_value).ratio()
        containment = 0.0
        if normalized_value in normalized_text:
            containment = 0.96 if len(normalized_value) >= 4 else 0.58
        elif normalized_text in normalized_value and len(normalized_text) >= 4:
            containment = 0.70
        token_score = _token_overlap(normalized_text, normalized_value)
        score = max(ratio * 0.72, containment, token_score)
        if score > best_score:
            best_score = score
            best_reason = f"تطبیق با {label}"
    return best_score, best_reason


def _normalize(value: str) -> str:
    """Normalize Persian and English tokens for resilient scanner matching."""

    return InternationalDrugReferenceService.normalize(value)


def _token_overlap(text_a: str, text_b: str) -> float:
    """Calculate a conservative token-overlap score."""

    tokens_a = {token for token in text_a.split() if len(token) >= 2}
    tokens_b = {token for token in text_b.split() if len(token) >= 2}
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    if not intersection:
        return 0.0
    return intersection / max(len(tokens_b), 1)


def _safe_file_name(file_name: str) -> str:
    """Return a filesystem-safe upload name while preserving the extension."""

    cleaned = re.sub(r"[^a-zA-Z0-9_.\-\u0600-\u06ff]+", "_", file_name.strip())
    return cleaned[:120] or "drug_image.png"
