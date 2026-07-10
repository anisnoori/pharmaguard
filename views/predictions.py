"""Advanced explainable AI shortage-prediction page."""

from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.charts import apply_chart_theme

from config import RISK_LABELS
from database.repositories import (
    ActivityLogRepository,
    AnalyticsRepository,
    DrugRepository,
    PredictionRepository,
    SupplierRepository,
)
from models.entities import DrugInventoryItem, DrugRecord
from services.prediction_service import (
    PredictionResult,
    PredictionScenario,
    ShortagePredictionService,
)
from utils.persian import fa_number, percent_fa


RISK_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


def render_prediction_page() -> None:
    """Render the advanced AI prediction module."""

    if not st.session_state.get("authenticated"):
        st.session_state.current_page = "login"
        st.rerun()
        return

    st.markdown(
        """
        <section class="pg-module-hero">
          <span class="pg-badge">پیش‌بینی هوشمند قابل توضیح</span>
          <h1>پیش‌بینی هوشمند کمبود دارو با توضیح قابل اقدام</h1>
          <p>
            این بخش احتمال کمبود، اعتماد تحلیل، عوامل اثرگذار، افق مصرف، تأخیر تأمین‌کننده و پیشنهاد اقدام را برای تصمیم‌گیری عملیاتی محاسبه می‌کند.
          </p>
          <div class="pg-module-meta">
            <span>تحلیل موجودی و مصرف</span>
            <span>تأخیر تأمین و حمل</span>
            <span>تقاضای اضطراری و فصلی</span>
            <span>توضیح‌پذیری AI</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    tab_single, tab_batch, tab_history = st.tabs(
        ["تحلیل یک دارو", "پایش گروهی", "تاریخچه پیش‌بینی"]
    )
    with tab_single:
        _render_single_prediction()
    with tab_batch:
        _render_batch_prediction()
    with tab_history:
        _render_prediction_history()


def _render_single_prediction() -> None:
    """Render scenario-based prediction for one selected drug."""

    options = DrugRepository.list_for_selection()
    if not options:
        st.info("برای اجرای پیش‌بینی، ابتدا حداقل یک دارو در بخش مدیریت دارو ثبت کنید.")
        return

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۱. دارو و سناریوی عملیاتی را انتخاب کنید</h2>
          <p>سناریو کمک می‌کند مدل وضعیت واقعی بیمارستان یا داروخانه را دقیق‌تر در نظر بگیرد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected = st.selectbox(
        "داروی مورد بررسی",
        options=options,
        format_func=lambda item: f"{item[1]} · بچ {item[2] or 'بدون بچ'}",
        key="prediction_selected_drug",
    )
    drug = DrugRepository.get_by_id(int(selected[0]))
    if drug is None:
        st.error("داروی انتخاب‌شده پیدا نشد.")
        return

    scenario = _render_scenario_controls(prefix="single")
    item = _item_from_record(drug, scenario)
    result = ShortagePredictionService.predict(item, scenario)

    _render_prediction_result(drug, result)
    _render_feature_importance(result)
    _render_ai_explanation(result)

    if st.button("ثبت این پیش‌بینی در تاریخچه", key="save_single_prediction", use_container_width=True):
        _save_prediction(drug.id, result, scenario)
        st.success("پیش‌بینی با جزئیات قابل توضیح در تاریخچه ثبت شد.")


def _render_batch_prediction() -> None:
    """Render batch risk ranking for all drugs in inventory."""

    rows = AnalyticsRepository.get_inventory_snapshot()
    if not rows:
        st.info("هنوز دارویی برای پایش گروهی ثبت نشده است.")
        return

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۲. پایش گروهی داروهای موجودی</h2>
          <p>این بخش همه داروها را رتبه‌بندی می‌کند تا تیم درمان سریع‌تر بداند کدام دارو نیاز به اقدام دارد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    scenario = _render_scenario_controls(prefix="batch", compact=True)
    items = [_item_from_snapshot_row(row, scenario) for row in rows]
    predictions = ShortagePredictionService.batch_predict(items, scenario)

    table_rows = []
    for item, result in predictions:
        table_rows.append(
            {
                "دارو": item.name,
                "ریسک": RISK_LABELS[result.risk_level],
                "احتمال": percent_fa(result.probability),
                "اعتماد": percent_fa(result.confidence),
                "پوشش موجودی": fa_number(f"{result.stock_coverage_days:.1f} روز"),
                "زمان تأمین مؤثر": fa_number(f"{result.effective_lead_time_days} روز"),
                "عامل اول": result.top_factors[0] if result.top_factors else "نامشخص",
                "پیشنهاد": result.suggested_action,
                "risk_sort": RISK_ORDER[result.risk_level],
                "probability_sort": result.probability,
            }
        )

    frame = pd.DataFrame(table_rows)
    display_frame = frame.drop(columns=["risk_sort", "probability_sort"])
    st.dataframe(display_frame, use_container_width=True, hide_index=True)
    _render_batch_chart(frame)


def _render_prediction_history() -> None:
    """Render recent stored prediction runs."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۳. تاریخچه پیش‌بینی‌ها</h2>
          <p>پیش‌بینی‌های ذخیره‌شده برای حسابرسی، گزارش مدیریتی و مقایسه تصمیم‌ها نگهداری می‌شوند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    rows = PredictionRepository.latest(limit=30)
    if not rows:
        st.info("هنوز پیش‌بینی ذخیره‌شده‌ای وجود ندارد. از تب «تحلیل یک دارو» یک پیش‌بینی ثبت کنید.")
        return

    frame = pd.DataFrame(
        [
            {
                "شناسه": fa_number(row["id"]),
                "دارو": row["drug_name"],
                "ریسک": RISK_LABELS.get(row["risk_level"], row["risk_level"]),
                "احتمال": percent_fa(float(row["probability"])),
                "اعتماد": percent_fa(float(row["confidence"])),
                "عوامل اصلی": row["top_factors"],
                "اقدام پیشنهادی": row["suggested_action"],
                "نسخه مدل": row["model_version"],
                "زمان ثبت": fa_number(row["created_at"]),
            }
            for row in rows
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_scenario_controls(prefix: str, compact: bool = False) -> PredictionScenario:
    """Render stable scenario controls without RTL slider overflow."""

    st.markdown('<div class="pg-scenario-panel">', unsafe_allow_html=True)
    if compact:
        columns = st.columns(3)
    else:
        columns = st.columns(2)

    with columns[0]:
        horizon = st.number_input(
            "افق بررسی پیش‌بینی / روز",
            min_value=7,
            max_value=90,
            value=30,
            step=1,
            key=f"{prefix}_horizon",
        )
        supplier_delay = st.number_input(
            "تأخیر احتمالی تأمین‌کننده / روز",
            min_value=0,
            max_value=30,
            value=2,
            step=1,
            key=f"{prefix}_supplier_delay",
        )
        shipping_delay = st.number_input(
            "تأخیر حمل و توزیع / روز",
            min_value=0,
            max_value=21,
            value=1,
            step=1,
            key=f"{prefix}_shipping_delay",
        )

    with columns[1]:
        emergency = st.number_input(
            "شاخص تقاضای اضطراری / ۰ تا ۱",
            min_value=0.0,
            max_value=1.0,
            value=0.15,
            step=0.05,
            key=f"{prefix}_emergency",
        )
        seasonality = st.number_input(
            "شاخص مصرف فصلی / ۰ تا ۱",
            min_value=0.0,
            max_value=1.0,
            value=0.10,
            step=0.05,
            key=f"{prefix}_seasonality",
        )
        criticality = st.number_input(
            "اهمیت بالینی دارو برای سازمان / ۰ تا ۱",
            min_value=0.0,
            max_value=1.0,
            value=0.55,
            step=0.05,
            key=f"{prefix}_criticality",
        )

    volatility = st.number_input(
        "نوسان تاریخی مصرف / ۰ تا ۱",
        min_value=0.0,
        max_value=1.0,
        value=0.25,
        step=0.05,
        key=f"{prefix}_volatility",
        help="هرچه مصرف قبلی نامنظم‌تر باشد، اعتماد تحلیل کمتر و ریسک عملیاتی بیشتر می‌شود.",
    )
    hospital_type = st.selectbox(
        "نوع سازمان درمانی",
        options=["general", "teaching", "emergency", "specialty", "pharmacy"],
        format_func=lambda value: {
            "general": "بیمارستان عمومی",
            "teaching": "بیمارستان آموزشی",
            "emergency": "مرکز اورژانس",
            "specialty": "مرکز تخصصی",
            "pharmacy": "داروخانه",
        }[value],
        key=f"{prefix}_hospital_type",
    )
    st.markdown('</div>', unsafe_allow_html=True)
    return PredictionScenario(
        supplier_delay_days=int(supplier_delay),
        shipping_delay_days=int(shipping_delay),
        emergency_demand_index=float(emergency),
        seasonality_index=float(seasonality),
        hospital_criticality=float(criticality),
        historical_volatility=float(volatility),
        review_horizon_days=int(horizon),
        hospital_type=hospital_type,
    )

def _render_prediction_result(drug: DrugRecord, result: PredictionResult) -> None:
    """Render main prediction KPIs."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>نتیجه پیش‌بینی</h2>
          <p>خروجی زیر برای تصمیم عملیاتی طراحی شده و همراه با دلیل و اقدام پیشنهادی است.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("ریسک کمبود", RISK_LABELS[result.risk_level])
    col2.metric("احتمال", percent_fa(result.probability))
    col3.metric("اعتماد مدل", percent_fa(result.confidence))
    col4.metric("پوشش موجودی", fa_number(f"{result.stock_coverage_days:.1f} روز"))

    st.markdown(
        f"""
        <div class="pg-clinical-note">
          <strong>اقدام پیشنهادی برای {drug.name}:</strong><br>
          {result.suggested_action}<br><br>
          <strong>برنامه پایش:</strong><br>
          {result.monitoring_plan}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_feature_importance(result: PredictionResult) -> None:
    """Render feature importance chart and top-factor cards."""

    importance_rows = [
        {"عامل": name, "اثر": value}
        for name, value in sorted(
            result.feature_importance.items(),
            key=lambda pair: pair[1],
            reverse=True,
        )
    ]
    frame = pd.DataFrame(importance_rows)
    figure = px.bar(
        frame,
        x="اثر",
        y="عامل",
        orientation="h",
        title="اهمیت عوامل در پیش‌بینی کمبود",
        text="اثر",
    )
    figure.update_traces(texttemplate="%{text:.2f}", textposition="outside", cliponaxis=False)
    figure.update_layout(
        title_x=0.95,
        xaxis_title="سهم در امتیاز ریسک",
        yaxis_title="عامل",
        yaxis={"autorange": "reversed"},
        font={"family": "Vazirmatn, Tahoma, Arial", "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 70, "b": 40},
    )
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _render_ai_explanation(result: PredictionResult) -> None:
    """Render natural-language AI explanation and recommendation."""

    st.markdown(
        f"""
        <div class="pg-finding-card pg-prediction-explanation">
          <div class="pg-finding-header">
            <strong>توضیح AI</strong>
            <span>{result.model_version}</span>
          </div>
          <p>{result.explanation}</p>
          <p><b>توصیه مدیریتی:</b> {result.recommendation}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_batch_chart(frame: pd.DataFrame) -> None:
    """Render batch prediction ranking chart."""

    if frame.empty:
        return
    chart_frame = frame.sort_values("probability_sort", ascending=False).head(12)
    figure = px.bar(
        chart_frame,
        x="دارو",
        y="probability_sort",
        title="رتبه‌بندی ریسک کمبود در موجودی",
        text="probability_sort",
    )
    figure.update_traces(texttemplate="%{text:.0%}", textposition="outside", cliponaxis=False)
    figure.update_layout(
        title_x=0.95,
        xaxis_title="دارو",
        yaxis_title="احتمال کمبود",
        yaxis_tickformat=".0%",
        font={"family": "Vazirmatn, Tahoma, Arial", "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 70, "b": 40},
    )
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _item_from_record(drug: DrugRecord, scenario: PredictionScenario) -> DrugInventoryItem:
    """Build a prediction item from a full drug record and scenario."""

    supplier_reliability = _supplier_reliability(drug.supplier_id)
    return DrugInventoryItem(
        id=drug.id,
        name=drug.name,
        current_stock=drug.current_stock,
        minimum_stock=drug.minimum_stock,
        monthly_consumption=drug.monthly_consumption,
        availability_score=drug.availability_score,
        lead_time_days=drug.lead_time_days,
        supplier_reliability_score=supplier_reliability,
        supplier_delay_days=scenario.supplier_delay_days,
        shipping_delay_days=scenario.shipping_delay_days,
        emergency_demand_index=scenario.emergency_demand_index,
        seasonality_index=scenario.seasonality_index,
        hospital_criticality=scenario.hospital_criticality,
        historical_volatility=scenario.historical_volatility,
        review_horizon_days=scenario.review_horizon_days,
        hospital_type=scenario.hospital_type,
    )


def _item_from_snapshot_row(row: dict[str, object], scenario: PredictionScenario) -> DrugInventoryItem:
    """Build a prediction item from an analytics snapshot row."""

    return DrugInventoryItem(
        id=int(row["id"]),
        name=str(row["name"]),
        current_stock=int(row["current_stock"]),
        minimum_stock=int(row["minimum_stock"]),
        monthly_consumption=int(row["monthly_consumption"]),
        availability_score=float(row["availability_score"]),
        lead_time_days=int(row["lead_time_days"]),
        supplier_reliability_score=float(row.get("supplier_reliability_score", 0.75)),
        supplier_delay_days=scenario.supplier_delay_days,
        shipping_delay_days=scenario.shipping_delay_days,
        emergency_demand_index=scenario.emergency_demand_index,
        seasonality_index=scenario.seasonality_index,
        hospital_criticality=scenario.hospital_criticality,
        historical_volatility=scenario.historical_volatility,
        review_horizon_days=scenario.review_horizon_days,
        hospital_type=scenario.hospital_type,
    )


def _supplier_reliability(supplier_id: int | None) -> float:
    """Return supplier reliability score for the selected drug."""

    if supplier_id is None:
        return 0.75
    for supplier in SupplierRepository.list_all():
        if supplier.id == supplier_id:
            return supplier.reliability_score
    return 0.75


def _save_prediction(drug_id: int, result: PredictionResult, scenario: PredictionScenario) -> None:
    """Persist prediction and activity log records."""

    prediction_id = PredictionRepository.create(
        drug_id=drug_id,
        risk_level=result.risk_level,
        probability=result.probability,
        confidence=result.confidence,
        explanation=result.explanation,
        recommendation=result.recommendation,
        model_version=result.model_version,
        feature_importance=result.feature_importance,
        top_factors=result.top_factors,
        suggested_action=result.suggested_action,
        monitoring_plan=result.monitoring_plan,
        scenario=asdict(scenario),
    )
    user = st.session_state.get("user") or {}
    ActivityLogRepository.log(
        user_id=user.get("id"),
        action="prediction_created",
        entity_type="prediction",
        entity_id=prediction_id,
        details=f"AI shortage prediction created for drug #{drug_id} with risk {result.risk_level}.",
    )
