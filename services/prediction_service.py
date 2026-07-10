"""Explainable shortage-risk prediction service for PharmaGuard AI.

The current engine is a deterministic, clinically explainable baseline. It is
built around normalized supply-chain signals so a future trained ML model can
replace the scoring layer without changing Streamlit pages or repositories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from models.entities import DrugInventoryItem


MODEL_VERSION = "PG-SHORTAGE-XAI-0.5"


@dataclass(frozen=True)
class PredictionScenario:
    """Operational context supplied by a hospital, pharmacy, or manager."""

    supplier_delay_days: int = 0
    shipping_delay_days: int = 0
    emergency_demand_index: float = 0.0
    seasonality_index: float = 0.0
    hospital_criticality: float = 0.5
    historical_volatility: float = 0.25
    review_horizon_days: int = 30
    hospital_type: str = "general"


@dataclass(frozen=True)
class PredictionResult:
    """Explainable prediction output for a drug inventory item."""

    risk_level: str
    probability: float
    confidence: float
    explanation: str
    recommendation: str
    feature_importance: dict[str, float]
    suggested_action: str = ""
    monitoring_plan: str = ""
    top_factors: list[str] = field(default_factory=list)
    stock_coverage_days: float = 0.0
    effective_lead_time_days: int = 0
    demand_forecast_units: int = 0
    model_version: str = MODEL_VERSION
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))


class ShortagePredictionService:
    """Predict drug-shortage risk using inventory, demand, and supplier signals."""

    _FEATURE_WEIGHTS: dict[str, float] = {
        "پوشش موجودی": 0.28,
        "شکاف سفارش مجدد": 0.18,
        "فشار مصرف": 0.16,
        "ریسک تأمین‌کننده": 0.14,
        "دسترسی بازار": 0.10,
        "تقاضای فصلی و اضطراری": 0.08,
        "اهمیت بالینی": 0.06,
    }

    @classmethod
    def predict(
        cls,
        item: DrugInventoryItem,
        scenario: PredictionScenario | None = None,
    ) -> PredictionResult:
        """Return an explainable shortage-risk estimate for one drug.

        The score intentionally combines measurable signals instead of a single
        stock threshold. This makes the output useful for action planning while
        remaining transparent for healthcare managers.
        """

        active_scenario = scenario or cls._scenario_from_item(item)
        normalized = cls._normalize_inputs(item, active_scenario)
        weighted = {
            feature: normalized[feature] * weight
            for feature, weight in cls._FEATURE_WEIGHTS.items()
        }
        probability = cls._clip(sum(weighted.values()), 0.02, 0.98)
        risk_level = cls._risk_level(probability)
        confidence = cls._confidence(item, active_scenario, normalized)

        daily_consumption = cls._daily_consumption(item, active_scenario)
        stock_coverage_days = item.current_stock / daily_consumption
        effective_lead_time = cls._effective_lead_time(item, active_scenario)
        demand_forecast = cls._demand_forecast(item, active_scenario)
        top_factors = cls._top_factors(weighted)

        return PredictionResult(
            risk_level=risk_level,
            probability=round(probability, 3),
            confidence=round(confidence, 3),
            explanation=cls._explanation(
                item=item,
                scenario=active_scenario,
                probability=probability,
                stock_coverage_days=stock_coverage_days,
                effective_lead_time=effective_lead_time,
                demand_forecast=demand_forecast,
                top_factors=top_factors,
            ),
            recommendation=cls._recommendation(risk_level, item, effective_lead_time),
            suggested_action=cls._suggested_action(risk_level, item),
            monitoring_plan=cls._monitoring_plan(risk_level),
            feature_importance={key: round(value, 3) for key, value in weighted.items()},
            top_factors=top_factors,
            stock_coverage_days=round(stock_coverage_days, 1),
            effective_lead_time_days=effective_lead_time,
            demand_forecast_units=demand_forecast,
        )

    @classmethod
    def batch_predict(
        cls,
        items: list[DrugInventoryItem],
        scenario: PredictionScenario | None = None,
    ) -> list[tuple[DrugInventoryItem, PredictionResult]]:
        """Predict shortage risk for multiple drugs in a stable order."""

        results = [(item, cls.predict(item, scenario)) for item in items]
        return sorted(results, key=lambda pair: pair[1].probability, reverse=True)

    @staticmethod
    def _scenario_from_item(item: DrugInventoryItem) -> PredictionScenario:
        """Build a default scenario from optional item-level fields."""

        return PredictionScenario(
            supplier_delay_days=max(0, int(getattr(item, "supplier_delay_days", 0))),
            shipping_delay_days=max(0, int(getattr(item, "shipping_delay_days", 0))),
            emergency_demand_index=ShortagePredictionService._clip(
                float(getattr(item, "emergency_demand_index", 0.0)), 0.0, 1.0
            ),
            seasonality_index=ShortagePredictionService._clip(
                float(getattr(item, "seasonality_index", 0.0)), 0.0, 1.0
            ),
            hospital_criticality=ShortagePredictionService._clip(
                float(getattr(item, "hospital_criticality", 0.5)), 0.0, 1.0
            ),
            historical_volatility=ShortagePredictionService._clip(
                float(getattr(item, "historical_volatility", 0.25)), 0.0, 1.0
            ),
            review_horizon_days=max(7, int(getattr(item, "review_horizon_days", 30))),
            hospital_type=str(getattr(item, "hospital_type", "general") or "general"),
        )

    @classmethod
    def _normalize_inputs(
        cls,
        item: DrugInventoryItem,
        scenario: PredictionScenario,
    ) -> dict[str, float]:
        """Normalize all model signals to zero-to-one pressure values."""

        daily_consumption = cls._daily_consumption(item, scenario)
        stock_coverage_days = item.current_stock / daily_consumption
        effective_lead_time = cls._effective_lead_time(item, scenario)
        demand_forecast = cls._demand_forecast(item, scenario)

        coverage_pressure = 1 - cls._clip(stock_coverage_days / max(scenario.review_horizon_days, 1), 0, 1)
        reorder_gap_pressure = cls._clip((effective_lead_time - stock_coverage_days) / 30, 0, 1)
        demand_pressure = cls._clip(demand_forecast / max(item.current_stock + item.minimum_stock, 1), 0, 1)
        supplier_reliability = cls._clip(float(getattr(item, "supplier_reliability_score", 0.75)), 0, 1)
        supplier_pressure = cls._clip(
            (effective_lead_time / 30) * 0.55
            + (1 - supplier_reliability) * 0.45,
            0,
            1,
        )
        market_pressure = cls._clip(1 - item.availability_score, 0, 1)
        seasonal_emergency_pressure = cls._clip(
            scenario.seasonality_index * 0.45
            + scenario.emergency_demand_index * 0.55,
            0,
            1,
        )
        clinical_pressure = cls._clip(scenario.hospital_criticality, 0, 1)

        if item.current_stock < item.minimum_stock:
            coverage_pressure = cls._clip(coverage_pressure + 0.18, 0, 1)
            reorder_gap_pressure = cls._clip(reorder_gap_pressure + 0.14, 0, 1)

        return {
            "پوشش موجودی": coverage_pressure,
            "شکاف سفارش مجدد": reorder_gap_pressure,
            "فشار مصرف": demand_pressure,
            "ریسک تأمین‌کننده": supplier_pressure,
            "دسترسی بازار": market_pressure,
            "تقاضای فصلی و اضطراری": seasonal_emergency_pressure,
            "اهمیت بالینی": clinical_pressure,
        }

    @staticmethod
    def _daily_consumption(item: DrugInventoryItem, scenario: PredictionScenario) -> float:
        """Return expected daily consumption after demand multipliers."""

        monthly = max(float(item.monthly_consumption), 1.0)
        multiplier = 1 + scenario.emergency_demand_index * 0.6 + scenario.seasonality_index * 0.35
        return max((monthly * multiplier) / 30, 0.1)

    @staticmethod
    def _effective_lead_time(item: DrugInventoryItem, scenario: PredictionScenario) -> int:
        """Return expected total replenishment time in days."""

        return max(1, int(item.lead_time_days) + scenario.supplier_delay_days + scenario.shipping_delay_days)

    @classmethod
    def _demand_forecast(cls, item: DrugInventoryItem, scenario: PredictionScenario) -> int:
        """Return expected units consumed within the review horizon."""

        return int(round(cls._daily_consumption(item, scenario) * scenario.review_horizon_days))

    @staticmethod
    def _risk_level(probability: float) -> str:
        """Map shortage probability to a risk level."""

        if probability >= 0.82:
            return "critical"
        if probability >= 0.64:
            return "high"
        if probability >= 0.38:
            return "medium"
        return "low"

    @classmethod
    def _confidence(
        cls,
        item: DrugInventoryItem,
        scenario: PredictionScenario,
        normalized: dict[str, float],
    ) -> float:
        """Estimate confidence from data completeness and scenario uncertainty."""

        completeness = 0.0
        completeness += 0.12 if item.monthly_consumption > 0 else 0
        completeness += 0.10 if item.minimum_stock > 0 else 0
        completeness += 0.08 if item.lead_time_days > 0 else 0
        completeness += 0.06 if 0 < item.availability_score <= 1 else 0
        uncertainty_penalty = scenario.historical_volatility * 0.12
        uncertainty_penalty += normalized["تقاضای فصلی و اضطراری"] * 0.06
        return cls._clip(0.58 + completeness - uncertainty_penalty, 0.52, 0.96)

    @staticmethod
    def _top_factors(weighted: dict[str, float]) -> list[str]:
        """Return the three strongest reasons behind the prediction."""

        return [name for name, _ in sorted(weighted.items(), key=lambda pair: pair[1], reverse=True)[:3]]

    @staticmethod
    def _explanation(
        item: DrugInventoryItem,
        scenario: PredictionScenario,
        probability: float,
        stock_coverage_days: float,
        effective_lead_time: int,
        demand_forecast: int,
        top_factors: list[str],
    ) -> str:
        """Create a Persian natural-language explanation."""

        factors = "، ".join(top_factors)
        return (
            f"برای {item.name}، موجودی فعلی حدود {stock_coverage_days:.1f} روز مصرف را پوشش می‌دهد. "
            f"زمان مؤثر تأمین با تأخیرهای سناریو {effective_lead_time} روز است و تقاضای پیش‌بینی‌شده "
            f"در افق {scenario.review_horizon_days} روزه حدود {demand_forecast} واحد برآورد شد. "
            f"احتمال کمبود {probability:.0%} محاسبه شده و عوامل اثرگذار اصلی شامل {factors} هستند."
        )

    @staticmethod
    def _recommendation(risk_level: str, item: DrugInventoryItem, effective_lead_time: int) -> str:
        """Return an operational recommendation by risk level."""

        if risk_level == "critical":
            return (
                "ثبت سفارش فوری، تماس با تأمین‌کننده جایگزین، محدودسازی مصرف غیرضروری و "
                "اطلاع به مدیر درمان برای تصمیم سریع."
            )
        if risk_level == "high":
            return (
                f"افزایش سطح سفارش حداقل برای پوشش {effective_lead_time + 14} روز، پایش روزانه موجودی "
                "و بررسی تأمین‌کننده دوم."
            )
        if risk_level == "medium":
            return "تنظیم نقطه سفارش، بررسی روند مصرف هفتگی و آماده‌سازی سفارش پیشگیرانه."
        return f"وضعیت {item.name} پایدار است؛ پایش دوره‌ای و به‌روزرسانی داده مصرف ادامه یابد."

    @staticmethod
    def _suggested_action(risk_level: str, item: DrugInventoryItem) -> str:
        """Return the next concrete action for the current user."""

        reorder_quantity = max(item.minimum_stock * 2 - item.current_stock, item.monthly_consumption // 2, 0)
        if risk_level in {"critical", "high"}:
            return f"پیشنهاد سفارش: حداقل {reorder_quantity} واحد و ثبت هشدار مدیریتی برای {item.name}."
        if risk_level == "medium":
            return "پیشنهاد: برنامه سفارش پیشگیرانه بسازید و داده مصرف هفته آینده را دوباره بررسی کنید."
        return "پیشنهاد: بدون اقدام فوری؛ فقط کنترل دوره‌ای موجودی."

    @staticmethod
    def _monitoring_plan(risk_level: str) -> str:
        """Return a monitoring plan aligned with the predicted risk."""

        if risk_level == "critical":
            return "پایش هر شیفت، گزارش روزانه به مدیریت و کنترل مصرف بخش‌های پرمصرف."
        if risk_level == "high":
            return "پایش روزانه موجودی، بررسی وضعیت سفارش و بازبینی تأخیر تأمین‌کننده."
        if risk_level == "medium":
            return "پایش دو بار در هفته و مقایسه مصرف واقعی با پیش‌بینی."
        return "پایش هفتگی طبق روال عادی."

    @staticmethod
    def _clip(value: float, lower: float, upper: float) -> float:
        """Clamp a numeric value to a safe range."""

        return max(lower, min(upper, value))


def prediction_to_jsonable(result: PredictionResult) -> dict[str, Any]:
    """Serialize a prediction result for audit storage or debugging."""

    return {
        "risk_level": result.risk_level,
        "probability": result.probability,
        "confidence": result.confidence,
        "explanation": result.explanation,
        "recommendation": result.recommendation,
        "suggested_action": result.suggested_action,
        "monitoring_plan": result.monitoring_plan,
        "feature_importance": result.feature_importance,
        "top_factors": result.top_factors,
        "stock_coverage_days": result.stock_coverage_days,
        "effective_lead_time_days": result.effective_lead_time_days,
        "demand_forecast_units": result.demand_forecast_units,
        "model_version": result.model_version,
        "generated_at": result.generated_at,
    }
