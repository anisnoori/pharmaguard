"""International drug reference and normalization services.

This module provides two layers:

1. A deterministic local reference index for common international medicines,
   translated aliases, strengths, and clinical reference notes.
2. Safe optional integrations with public drug-data APIs. Network calls are
   bounded by short timeouts and never block the scanner from returning a
   local, auditable result.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re
from typing import Any
from urllib.parse import quote

try:  # Optional at runtime; the app still works offline.
    import requests
except Exception:  # pragma: no cover - defensive optional dependency.
    requests = None  # type: ignore[assignment]


PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
LOW_SIGNAL_TOKENS = {
    "img",
    "image",
    "photo",
    "screenshot",
    "whatsapp",
    "camera",
    "drug",
    "scan",
    "package",
    "tablet",
    "pill",
    "jpeg",
    "jpg",
    "png",
    "webp",
}


@dataclass(frozen=True)
class DrugReference:
    """One normalized international drug concept used by the scanner."""

    key: str
    canonical_fa: str
    canonical_en: str
    atc_class: str
    fa_class: str
    aliases: tuple[str, ...]
    common_strengths: tuple[str, ...]
    safety_note: str
    source_note: str


@dataclass(frozen=True)
class ReferenceMatch:
    """A scored match between free text and an international drug concept."""

    reference: DrugReference
    score: float
    matched_alias: str
    reason: str


REFERENCES: tuple[DrugReference, ...] = (
    DrugReference(
        key="warfarin",
        canonical_fa="وارفارین",
        canonical_en="Warfarin",
        atc_class="B01AA03",
        fa_class="ضدانعقاد خوراکی",
        aliases=("warfarin", "coumadin", "jantoven", "وارفارین", "وارفرین", "ورفارین"),
        common_strengths=("1", "2", "2.5", "3", "5", "10"),
        safety_note="داروی پرخطر؛ پایش INR و علائم خونریزی ضروری است.",
        source_note="RxNorm/DailyMed-ready reference concept",
    ),
    DrugReference(
        key="aspirin",
        canonical_fa="آسپرین",
        canonical_en="Aspirin",
        atc_class="B01AC06 / N02BA01",
        fa_class="ضدپلاکت / ضددرد سالیسیلاتی",
        aliases=("aspirin", "acetylsalicylic acid", "asa", "آسپرین", "آسپیرین", "استیل سالیسیلیک اسید"),
        common_strengths=("80", "81", "100", "325", "500"),
        safety_note="در کنار ضدانعقادها یا NSAIDها ریسک خونریزی و عوارض گوارشی افزایش می‌یابد.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="ibuprofen",
        canonical_fa="ایبوپروفن",
        canonical_en="Ibuprofen",
        atc_class="M01AE01",
        fa_class="NSAID / ضددرد و ضدالتهاب",
        aliases=("ibuprofen", "advil", "motrin", "ایبوپروفن", "ایبو پروفن", "بروفن", "ژلوفن"),
        common_strengths=("200", "400", "600", "800"),
        safety_note="در بیماران کلیوی، گوارشی، قلبی یا مصرف‌کننده ضدانعقاد باید با احتیاط بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="acetaminophen",
        canonical_fa="استامینوفن",
        canonical_en="Acetaminophen / Paracetamol",
        atc_class="N02BE01",
        fa_class="ضددرد و ضدتب",
        aliases=("acetaminophen", "paracetamol", "tylenol", "استامینوفن", "پاراستامول", "استامینفن"),
        common_strengths=("325", "500", "650", "1000"),
        safety_note="سقف دوز روزانه و بیماری کبدی باید بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),

    DrugReference(
        key="penicillin",
        canonical_fa="پنی‌سیلین",
        canonical_en="Penicillin",
        atc_class="J01CE / J01CR",
        fa_class="آنتی‌بیوتیک بتالاکتام / پنی‌سیلین",
        aliases=(
            "penicillin",
            "penicillin g",
            "penicillin v",
            "benzylpenicillin",
            "phenoxymethylpenicillin",
            "پنی سیلین",
            "پنی‌سیلین",
            "پنسیلین",
            "بنزیل پنی سیلین",
        ),
        common_strengths=("250", "500", "1000000", "1200000"),
        safety_note="سابقه حساسیت به پنی‌سیلین، واکنش آنافیلاکسی و نوع فراورده تزریقی یا خوراکی باید بررسی شود.",
        source_note="RxNorm/DailyMed-ready reference concept",
    ),
    DrugReference(
        key="amoxicillin",
        canonical_fa="آموکسی‌سیلین",
        canonical_en="Amoxicillin",
        atc_class="J01CA04",
        fa_class="آنتی‌بیوتیک بتالاکتام",
        aliases=("amoxicillin", "amoxil", "آموکسی سیلین", "آموکسی‌سیلین", "اموکسی سیلین", "آموکسی"),
        common_strengths=("250", "500", "875"),
        safety_note="سابقه حساسیت به پنی‌سیلین و تنظیم دوز در نارسایی کلیه بررسی شود.",
        source_note="RxNorm/DailyMed-ready reference concept",
    ),
    DrugReference(
        key="metformin",
        canonical_fa="متفورمین",
        canonical_en="Metformin",
        atc_class="A10BA02",
        fa_class="داروی دیابت / بیگوانید",
        aliases=("metformin", "glucophage", "متفورمین", "مت فورمین"),
        common_strengths=("500", "750", "850", "1000"),
        safety_note="عملکرد کلیه، ریسک اسیدوز لاکتیک و مصرف ماده حاجب باید بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="regular_insulin",
        canonical_fa="انسولین رگولار",
        canonical_en="Regular Insulin",
        atc_class="A10AB01",
        fa_class="انسولین کوتاه‌اثر",
        aliases=("regular insulin", "insulin regular", "human insulin", "انسولین رگولار", "انسولین معمولی", "رگولار"),
        common_strengths=("100",),
        safety_note="ریسک هیپوگلیسمی؛ زنجیره سرد و تاریخ انقضا حیاتی است.",
        source_note="RxNorm/DailyMed-ready reference concept",
    ),
    DrugReference(
        key="omeprazole",
        canonical_fa="امپرازول",
        canonical_en="Omeprazole",
        atc_class="A02BC01",
        fa_class="مهارکننده پمپ پروتون",
        aliases=("omeprazole", "prilosec", "امپرازول", "اومپرازول", "امپرازول"),
        common_strengths=("10", "20", "40"),
        safety_note="در مصرف طولانی‌مدت، منیزیم، B12 و ریسک تداخلات باید بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="atorvastatin",
        canonical_fa="آتورواستاتین",
        canonical_en="Atorvastatin",
        atc_class="C10AA05",
        fa_class="استاتین / کاهنده چربی خون",
        aliases=("atorvastatin", "lipitor", "آتورواستاتین", "اتورواستاتین", "آتوروستاتین"),
        common_strengths=("10", "20", "40", "80"),
        safety_note="درد عضلانی، آنزیم‌های کبدی و تداخلات مهارکننده CYP3A4 بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="amlodipine",
        canonical_fa="آملودیپین",
        canonical_en="Amlodipine",
        atc_class="C08CA01",
        fa_class="مسدودکننده کانال کلسیم",
        aliases=("amlodipine", "norvasc", "آملودیپین", "املودیپین"),
        common_strengths=("2.5", "5", "10"),
        safety_note="ادم محیطی، فشار خون و مصرف همزمان داروهای قلبی بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="losartan",
        canonical_fa="لوزارتان",
        canonical_en="Losartan",
        atc_class="C09CA01",
        fa_class="ARB / ضد فشار خون",
        aliases=("losartan", "cozaar", "لوزارتان", "لوزار"),
        common_strengths=("25", "50", "100"),
        safety_note="پتاسیم، عملکرد کلیه و بارداری باید بررسی شود.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="levothyroxine",
        canonical_fa="لووتیروکسین",
        canonical_en="Levothyroxine",
        atc_class="H03AA01",
        fa_class="هورمون تیروئید",
        aliases=("levothyroxine", "synthroid", "لووتیروکسین", "لوتیروکسین", "لووتیروکسین سدیم"),
        common_strengths=("25", "50", "75", "100", "125", "150"),
        safety_note="مصرف ناشتا، فاصله با آهن/کلسیم و پایش TSH اهمیت دارد.",
        source_note="RxNorm/openFDA label-ready reference concept",
    ),
    DrugReference(
        key="cefixime",
        canonical_fa="سفیکسیم",
        canonical_en="Cefixime",
        atc_class="J01DD08",
        fa_class="سفالوسپورین نسل سوم",
        aliases=("cefixime", "suprax", "سفیکسیم", "سفکسیم", "سفیکس"),
        common_strengths=("100", "200", "400"),
        safety_note="حساسیت بتالاکتام و تنظیم دوز در نارسایی کلیه بررسی شود.",
        source_note="RxNorm/DailyMed-ready reference concept",
    ),
)


class InternationalDrugReferenceService:
    """Normalize medication names using local and optional official references."""

    @staticmethod
    def normalize(value: str) -> str:
        """Normalize Persian, Arabic, and English medication text."""

        normalized = value.translate(PERSIAN_DIGITS).strip().lower()
        normalized = normalized.replace("ي", "ی").replace("ك", "ک").replace("ۀ", "ه")
        normalized = normalized.replace("‌", " ")
        normalized = re.sub(r"\b(milligram|milligrams|mg)\b", " میلی گرم ", normalized)
        normalized = re.sub(r"میلی\s*گرم|م\s*گ", " میلی گرم ", normalized)
        normalized = re.sub(r"[^a-z0-9\.\u0600-\u06ff]+", " ", normalized)
        return " ".join(normalized.split())

    @staticmethod
    def extract_strengths(value: str) -> set[str]:
        """Extract likely strength numbers from a label or inventory name."""

        normalized = InternationalDrugReferenceService.normalize(value)
        strengths = set(re.findall(r"(?<!\d)(\d+(?:\.\d+)?)(?=\s*(?:میلی گرم|واحد|iu|ml|عدد)?\b)", normalized))
        return {strength.rstrip("0").rstrip(".") if "." in strength else strength for strength in strengths}

    @classmethod
    def text_has_meaningful_drug_signal(cls, text: str) -> bool:
        """Return False for camera filenames and generic image labels."""

        normalized = cls.normalize(text)
        tokens = set(normalized.split())
        if not normalized or normalized == "متن قابل استخراج ثبت نشده است":
            return False
        non_generic = [token for token in tokens if token not in LOW_SIGNAL_TOKENS and not token.isdigit()]
        return bool(non_generic) and len(normalized) >= 3

    @classmethod
    def match_text(cls, text: str) -> ReferenceMatch | None:
        """Match free text to the best local international drug concept."""

        normalized_text = cls.normalize(text)
        if not cls.text_has_meaningful_drug_signal(normalized_text):
            return None

        best: ReferenceMatch | None = None
        for reference in REFERENCES:
            for alias in reference.aliases + (reference.canonical_fa, reference.canonical_en):
                normalized_alias = cls.normalize(alias)
                if not normalized_alias:
                    continue
                score = cls._alias_score(normalized_text, normalized_alias)
                minimum_score = 0.58
                if normalized_alias in normalized_text or (normalized_alias and normalized_text in normalized_alias and len(normalized_text) >= 5):
                    minimum_score = 0.50
                if score < minimum_score:
                    continue
                reason = "تطبیق نام بین‌المللی"
                if normalized_alias in normalized_text:
                    reason = f"تطبیق مستقیم با «{alias}»"
                match = ReferenceMatch(reference, round(score, 3), alias, reason)
                if best is None or match.score > best.score:
                    best = match
        return best

    @classmethod
    def score_record_against_reference(cls, record: Any, reference: DrugReference) -> float:
        """Score an inventory row against a normalized reference concept."""

        fields = [
            getattr(record, "name", ""),
            getattr(record, "generic_name", ""),
            getattr(record, "manufacturer", ""),
        ]
        text = cls.normalize(" ".join(field for field in fields if field))
        if not text:
            return 0.0
        best = 0.0
        for alias in reference.aliases + (reference.canonical_fa, reference.canonical_en):
            score = cls._alias_score(text, cls.normalize(alias))
            best = max(best, score)
        return round(best, 3)

    @classmethod
    def reference_details(cls, reference: DrugReference) -> dict[str, str]:
        """Return display-ready metadata for a local reference concept."""

        return {
            "مرجع دارویی": f"{reference.canonical_fa} / {reference.canonical_en}",
            "کد/کلاس ATC": reference.atc_class,
            "رده درمانی": reference.fa_class,
            "قدرت‌های رایج": "، ".join(reference.common_strengths) or "ثبت نشده",
            "نکته ایمنی": reference.safety_note,
            "منبع داده": reference.source_note,
        }

    @staticmethod
    @lru_cache(maxsize=256)
    def rxnorm_lookup(term: str) -> dict[str, str]:
        """Safely query RxNorm approximate matching for an English/normalized term."""

        if requests is None or not term.strip():
            return {}
        url = f"https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={quote(term.strip())}&maxEntries=3"
        try:
            response = requests.get(url, timeout=2.5)
            response.raise_for_status()
            payload = response.json()
            candidates = payload.get("approximateGroup", {}).get("candidate", [])
            if not candidates:
                return {}
            first = candidates[0]
            return {
                "RxNorm RXCUI": str(first.get("rxcui", "")),
                "RxNorm Score": str(first.get("score", "")),
                "RxNorm Rank": str(first.get("rank", "")),
            }
        except Exception:
            return {}

    @staticmethod
    @lru_cache(maxsize=128)
    def openfda_label_summary(generic_name: str) -> dict[str, str]:
        """Safely fetch a concise openFDA label summary when internet is available."""

        if requests is None or not generic_name.strip():
            return {}
        query = quote(f'openfda.generic_name:"{generic_name.strip()}"')
        url = f"https://api.fda.gov/drug/label.json?search={query}&limit=1"
        try:
            response = requests.get(url, timeout=3.0)
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                return {}
            label = results[0]
            openfda = label.get("openfda", {})
            brand_names = ", ".join(openfda.get("brand_name", [])[:3])
            route = ", ".join(openfda.get("route", [])[:3])
            warnings = _first_text(label.get("warnings") or label.get("boxed_warning"))
            indications = _first_text(label.get("indications_and_usage"))
            output: dict[str, str] = {}
            if brand_names:
                output["نام‌های تجاری openFDA"] = brand_names
            if route:
                output["Route openFDA"] = route
            if indications:
                output["Indications openFDA"] = _truncate(indications, 260)
            if warnings:
                output["Warnings openFDA"] = _truncate(warnings, 260)
            return output
        except Exception:
            return {}

    @staticmethod
    def _alias_score(text: str, alias: str) -> float:
        """Calculate a robust score between a normalized label and alias."""

        if not text or not alias:
            return 0.0
        if alias == text:
            return 1.0
        alias_tokens = set(alias.split())
        text_tokens = set(text.split())
        if alias in text:
            return 0.96 if len(alias) >= 4 else 0.62
        if alias_tokens and alias_tokens <= text_tokens:
            return 0.91
        overlap = _token_overlap(text_tokens, alias_tokens)
        ratio = _sequence_ratio(text, alias)
        return max(overlap, ratio * 0.72)


def _token_overlap(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Return weighted overlap for normalized tokens."""

    meaningful_a = {token for token in tokens_a if len(token) >= 2 and token not in LOW_SIGNAL_TOKENS}
    meaningful_b = {token for token in tokens_b if len(token) >= 2 and token not in LOW_SIGNAL_TOKENS}
    if not meaningful_a or not meaningful_b:
        return 0.0
    intersection = len(meaningful_a & meaningful_b)
    return intersection / max(len(meaningful_b), 1)


def _sequence_ratio(text: str, alias: str) -> float:
    """Return a lightweight edit-similarity ratio without external dependencies."""

    from difflib import SequenceMatcher

    return SequenceMatcher(None, text, alias).ratio()


def _first_text(value: Any) -> str:
    """Return the first text item from heterogeneous API values."""

    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return ""


def _truncate(value: str, limit: int) -> str:
    """Truncate long external label text for UI display."""

    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 1]}…"
