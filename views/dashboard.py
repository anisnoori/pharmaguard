"""Role-aware dashboard views."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.charts import apply_chart_theme

from config import RISK_LABELS
from database.repositories import AnalyticsRepository
from models.entities import DrugInventoryItem
from services.prediction_service import ShortagePredictionService
from utils.persian import fa_number, percent_fa


def render_dashboard() -> None:
    """Render dashboard based on authenticated user role."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    st.markdown(
        f"""
        <section class="pg-dashboard-header">
          <span class="pg-badge">{user['role_name']}</span>
          <h1>سلام، {user['full_name']}</h1>
          <p>این داشبورد بر اساس نقش شما تنظیم شده تا فقط اطلاعات کاربردی و قابل اقدام نمایش داده شود.</p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    role_code = user["role_code"]
    if role_code == "administrator":
        render_admin_dashboard()
    elif role_code == "hospital_manager":
        render_hospital_dashboard()
    elif role_code == "pharmacy_manager":
        render_pharmacy_dashboard()
    else:
        render_viewer_dashboard()


def _render_dashboard_actions() -> None:
    """Render primary operational shortcuts for authenticated users."""

    actions = [
        ("مدیریت دارو", "dashboard_drug_management", "drugs"),
        ("ورود داده", "dashboard_upload", "upload"),
        ("اسکن دارو", "dashboard_scanner", "scanner"),
        ("پیش‌بینی AI", "dashboard_predictions", "predictions"),
        ("گزارش‌ها", "dashboard_reports", "reports"),
        ("هشدارها", "dashboard_notifications", "notifications"),
        ("تنظیمات", "dashboard_settings", "settings"),
    ]
    user = st.session_state.get("user") or {}
    if user.get("role_code") == "administrator":
        actions.insert(0, ("مدیریت سامانه", "dashboard_admin", "admin"))
    columns = st.columns([1] * len(actions))
    for column, (label, key, page) in zip(columns, actions, strict=True):
        with column:
            if st.button(label, key=key, use_container_width=True):
                st.session_state.current_page = page
                st.rerun()


def render_admin_dashboard() -> None:
    """Render global administrative dashboard."""

    summary = AnalyticsRepository.get_platform_summary()
    col1, col2, col3 = st.columns(3)
    col1.metric("داروهای ثبت‌شده", fa_number(summary["drugs"]))
    col2.metric("پیش‌بینی‌های ثبت‌شده", fa_number(summary["predictions"]))
    col3.metric("قوانین تداخل دارویی", fa_number(summary["interactions"]))
    render_inventory_predictions(show_global=True)


def render_hospital_dashboard() -> None:
    """Render hospital-focused operational dashboard."""

    st.info("تمرکز این داشبورد روی داروهای حیاتی بیمارستان، هشدار کمبود و پیشنهاد اقدام است.")
    render_inventory_predictions(show_global=False)


def render_pharmacy_dashboard() -> None:
    """Render pharmacy-focused dashboard."""

    st.info("تمرکز این داشبورد روی موجودی داروخانه، سفارش مجدد و ریسک تداخل دارویی است.")
    render_inventory_predictions(show_global=False)


def render_viewer_dashboard() -> None:
    """Render restricted read-only dashboard."""

    st.warning("حساب شما دسترسی محدود دارد و فقط خلاصه‌های قابل مشاهده نمایش داده می‌شود.")
    render_inventory_predictions(show_global=False)


def render_inventory_predictions(show_global: bool) -> None:
    """Render inventory table with explainable predictions."""

    rows = AnalyticsRepository.get_inventory_snapshot()
    if not rows:
        st.empty().info("هنوز دارویی در سیستم ثبت نشده است.")
        return

    predictions = [_build_prediction_row(row) for row in rows]
    dataframe = pd.DataFrame([item["display"] for item in predictions])

    st.subheader("پایش هوشمند موجودی و ریسک کمبود")
    st.caption("این جدول نشان می‌دهد کدام داروها به اقدام سریع‌تر نیاز دارند و کدام عامل بیشترین اثر را روی ریسک گذاشته است.")
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    _render_risk_chart(rows)

    if show_global:
        st.caption("نمایش آمار کلان فقط برای مدیر سامانه فعال است؛ کاربران عادی آمار عمومی سامانه را نمی‌بینند.")


def _build_prediction_row(row: dict[str, object]) -> dict[str, dict[str, str]]:
    """Convert one database row into a display-ready prediction row."""

    item = _inventory_item_from_row(row)
    prediction = ShortagePredictionService.predict(item)
    return {
        "display": {
            "دارو": item.name,
            "موجودی": fa_number(item.current_stock),
            "حداقل مجاز": fa_number(item.minimum_stock),
            "مصرف ماهانه": fa_number(item.monthly_consumption),
            "ریسک": RISK_LABELS[prediction.risk_level],
            "احتمال": percent_fa(prediction.probability),
            "اعتماد": percent_fa(prediction.confidence),
            "عامل اصلی": prediction.top_factors[0] if prediction.top_factors else "نامشخص",
            "پیشنهاد اقدام": prediction.suggested_action or prediction.recommendation,
        }
    }


def _render_risk_chart(rows: list[dict[str, object]]) -> None:
    """Render an RTL-friendly shortage risk chart."""

    chart_rows = []
    for row in rows:
        item = _inventory_item_from_row(row)
        prediction = ShortagePredictionService.predict(item)
        chart_rows.append({"دارو": item.name, "احتمال ریسک": prediction.probability})

    chart_frame = pd.DataFrame(chart_rows)
    figure = px.bar(
        chart_frame,
        x="دارو",
        y="احتمال ریسک",
        title="احتمال ریسک کمبود دارو",
        text="احتمال ریسک",
    )
    figure.update_traces(texttemplate="%{text:.0%}", textposition="outside", cliponaxis=False)
    figure.update_layout(
        title_x=0.95,
        xaxis_title="دارو",
        yaxis_title="احتمال",
        yaxis_tickformat=".0%",
        font={"family": "Vazirmatn, Tahoma, Arial", "size": 13},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin={"l": 20, "r": 20, "t": 70, "b": 40},
    )
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _inventory_item_from_row(row: dict[str, object]) -> DrugInventoryItem:
    """Map a dashboard database row to the prediction input entity."""

    return DrugInventoryItem(
        id=int(row["id"]),
        name=str(row["name"]),
        current_stock=int(row["current_stock"]),
        minimum_stock=int(row["minimum_stock"]),
        monthly_consumption=int(row["monthly_consumption"]),
        availability_score=float(row["availability_score"]),
        lead_time_days=int(row["lead_time_days"]),
        supplier_reliability_score=float(row.get("supplier_reliability_score", 0.75)),
    )
