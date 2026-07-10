"""Professional reports and analytics page."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

from utils.charts import apply_chart_theme

from database.repositories import ActivityLogRepository
from services.report_service import ReportBundle, ReportExportService, ReportFilter, ReportService
from utils.persian import fa_number, percent_fa


RISK_SORT = {"critical": 4, "high": 3, "medium": 2, "low": 1}
SEVERITY_SORT = {"contraindicated": 4, "high": 3, "medium": 2, "low": 1}


def render_reports_page() -> None:
    """Render professional reporting and analytics module."""

    if not st.session_state.get("authenticated"):
        st.session_state.current_page = "login"
        st.rerun()
        return

    st.markdown(
        """
        <section class="pg-module-hero pg-reports-hero">
          <span class="pg-badge">گزارش‌ها و تحلیل مدیریتی</span>
          <h1>گزارش‌های حرفه‌ای برای تصمیم‌گیری درمانی و عملیاتی</h1>
          <p>
            این بخش داده‌های موجودی، پیش‌بینی کمبود، تداخل‌های دارویی، ورود داده و فعالیت‌های سامانه
            را در قالب KPI، نمودار، جدول مدیریتی و خروجی قابل ارائه آماده می‌کند.
          </p>
          <div class="pg-module-meta">
            <span>داشبورد مدیریتی</span>
            <span>تحلیل موجودی</span>
            <span>گزارش AI</span>
            <span>خروجی CSV / Excel / Print</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    filters = _render_filters()
    bundle = ReportService.build(filters)
    _render_kpis(bundle)

    tab_summary, tab_inventory, tab_predictions, tab_interactions, tab_exports = st.tabs(
        ["خلاصه مدیریتی", "موجودی", "پیش‌بینی‌ها", "تداخل‌ها", "خروجی و چاپ"]
    )
    with tab_summary:
        _render_executive_summary(bundle)
    with tab_inventory:
        _render_inventory_report(bundle)
    with tab_predictions:
        _render_prediction_report(bundle)
    with tab_interactions:
        _render_interaction_report(bundle)
    with tab_exports:
        _render_export_center(bundle)


def _render_filters() -> ReportFilter:
    """Render date and scope controls for reports."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۱. بازه و نوع گزارش را انتخاب کنید</h2>
          <p>بازه زمانی روی پیش‌بینی‌ها، ورود داده و فعالیت‌ها اعمال می‌شود؛ موجودی، وضعیت فعلی سامانه را نشان می‌دهد.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    today = date.today()
    col1, col2, col3 = st.columns(3)
    with col1:
        start = st.date_input("از تاریخ", value=today - timedelta(days=30), key="reports_start")
    with col2:
        end = st.date_input("تا تاریخ", value=today, key="reports_end")
    with col3:
        scope = st.selectbox(
            "نوع گزارش",
            options=["executive", "inventory", "prediction", "interaction", "import"],
            format_func=lambda value: {
                "executive": "گزارش مدیریتی جامع",
                "inventory": "گزارش موجودی",
                "prediction": "گزارش پیش‌بینی AI",
                "interaction": "گزارش تداخل دارویی",
                "import": "گزارش ورود داده",
            }[value],
            key="reports_scope",
        )
    if start > end:
        st.warning("تاریخ شروع نباید بعد از تاریخ پایان باشد. سامانه بازه را به صورت خودکار اصلاح کرد.")
        start, end = end, start
    return ReportFilter(start_date=start, end_date=end, report_scope=scope)


def _render_kpis(bundle: ReportBundle) -> None:
    """Render top-level executive KPI cards."""

    kpis = bundle.kpis
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("کل داروها", fa_number(kpis["total_drugs"]), help="تعداد داروهای ثبت‌شده در موجودی فعلی")
    col2.metric("نیازمند اقدام", fa_number(kpis["low_stock"]), help="داروهای بحرانی یا نزدیک به کمبود")
    col3.metric("پیش‌بینی بحرانی", fa_number(kpis["critical_predictions"]), help="پیش‌بینی‌های بحرانی در بازه انتخاب‌شده")
    col4.metric("کیفیت ورود داده", percent_fa(float(kpis["import_quality"])), help="نسبت ردیف‌های معتبر در ورود گروهی داده")


def _render_executive_summary(bundle: ReportBundle) -> None:
    """Render executive summary charts and recommendations."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۲. خلاصه مدیریتی</h2>
          <p>این بخش برای مدیر بیمارستان، داروخانه یا سازمان درمانی طراحی شده تا سریعاً نقاط ریسک را ببیند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        _render_inventory_status_chart(bundle.inventory_frame)
    with col2:
        _render_prediction_risk_chart(bundle.prediction_frame)
    _render_recommendation_panel(bundle)


def _render_inventory_report(bundle: ReportBundle) -> None:
    """Render inventory analytics table and charts."""

    frame = bundle.inventory_frame
    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۳. گزارش موجودی دارویی</h2>
          <p>داروهای دارای کسری، انقضای نزدیک، مصرف بالا و تأمین‌کننده‌های حساس را بررسی کنید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if frame.empty:
        st.info("هنوز دارویی برای گزارش موجودی ثبت نشده است.")
        return

    col1, col2 = st.columns(2)
    with col1:
        _render_category_chart(frame)
    with col2:
        _render_expiration_chart(frame)

    display_frame = frame.copy()
    display_frame["نسبت موجودی"] = display_frame["نسبت موجودی"].map(lambda value: percent_fa(min(float(value), 3.0) / 3.0))
    display_frame["دسترسی بازار"] = display_frame["دسترسی بازار"].map(lambda value: percent_fa(float(value)))
    st.dataframe(display_frame, use_container_width=True, hide_index=True)


def _render_prediction_report(bundle: ReportBundle) -> None:
    """Render AI prediction report."""

    frame = bundle.prediction_frame
    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۴. گزارش پیش‌بینی AI</h2>
          <p>پیش‌بینی‌های ذخیره‌شده با احتمال، اعتماد مدل، عامل اصلی و اقدام پیشنهادی قابل بررسی هستند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if frame.empty:
        st.info("در بازه انتخاب‌شده پیش‌بینی ذخیره‌شده‌ای وجود ندارد.")
        return

    chart_frame = frame.copy()
    chart_frame["اولویت"] = chart_frame["risk_level_raw"].map(RISK_SORT).fillna(0)
    chart_frame = chart_frame.sort_values(["اولویت", "احتمال"], ascending=False).head(15)
    figure = px.bar(
        chart_frame,
        x="نام دارو",
        y="احتمال",
        title="بالاترین ریسک‌های پیش‌بینی‌شده",
        text="ریسک",
    )
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(title_x=0.95, xaxis_title="دارو", yaxis_title="احتمال", yaxis_tickformat=".0%")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)

    display_frame = frame.drop(columns=["risk_level_raw"], errors="ignore").copy()
    display_frame["احتمال"] = display_frame["احتمال"].map(lambda value: percent_fa(float(value)))
    display_frame["اعتماد"] = display_frame["اعتماد"].map(lambda value: percent_fa(float(value)))
    st.dataframe(display_frame, use_container_width=True, hide_index=True)


def _render_interaction_report(bundle: ReportBundle) -> None:
    """Render drug interaction knowledge-base report."""

    frame = bundle.interaction_frame
    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۵. گزارش تداخل دارویی</h2>
          <p>قوانین تداخل دارویی بر اساس شدت، توصیه بالینی و سطح شواهد برای ایمنی بیمار مرور می‌شوند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if frame.empty:
        st.info("هنوز قانون تداخل دارویی ثبت نشده است.")
        return

    chart_frame = frame.copy()
    severity_counts = chart_frame.groupby("شدت", as_index=False).size().rename(columns={"size": "تعداد"})
    figure = px.bar(severity_counts, x="شدت", y="تعداد", title="توزیع قوانین تداخل بر اساس شدت", text="تعداد")
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(title_x=0.95, xaxis_title="شدت", yaxis_title="تعداد")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)

    display_frame = frame.drop(columns=["severity_raw"], errors="ignore")
    st.dataframe(display_frame, use_container_width=True, hide_index=True)


def _render_export_center(bundle: ReportBundle) -> None:
    """Render export and print center."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۶. خروجی مدیریتی و چاپ</h2>
          <p>گزارش را برای ارائه، جلسه مدیریتی، آرشیو داخلی یا بررسی تیم درمان خروجی بگیرید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    excel_payload = ReportExportService.excel_bytes(bundle)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button(
            "دانلود Excel جامع",
            data=excel_payload or b"",
            file_name="pharmaguard_management_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            disabled=excel_payload is None,
            key="download_report_excel",
            use_container_width=True,
        )
    with col2:
        st.download_button(
            "دانلود CSV موجودی",
            data=ReportExportService.csv_bytes(bundle.inventory_frame),
            file_name="pharmaguard_inventory_report.csv",
            mime="text/csv",
            key="download_report_inventory_csv",
            use_container_width=True,
        )
    with col3:
        st.download_button(
            "دانلود نسخه چاپی / PDF",
            data=ReportExportService.html_report_bytes(bundle),
            file_name="pharmaguard_printable_report.html",
            mime="text/html",
            key="download_report_printable_html",
            use_container_width=True,
        )

    if excel_payload is None:
        st.warning("برای خروجی Excel، وابستگی openpyxl باید نصب باشد. دستور `pip install -r requirements.txt` را اجرا کنید.")

    st.info("برای PDF، فایل HTML چاپی را باز کنید و از گزینه Print مرورگر، Save as PDF را انتخاب کنید.")
    _log_report_view()


def _render_inventory_status_chart(frame: pd.DataFrame) -> None:
    """Render inventory status distribution chart."""

    if frame.empty:
        st.info("داده موجودی برای نمودار وجود ندارد.")
        return
    counts = frame.groupby("وضعیت موجودی", as_index=False).size().rename(columns={"size": "تعداد"})
    figure = px.bar(counts, x="وضعیت موجودی", y="تعداد", title="وضعیت موجودی داروها", text="تعداد")
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(title_x=0.95, xaxis_title="وضعیت", yaxis_title="تعداد")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _render_prediction_risk_chart(frame: pd.DataFrame) -> None:
    """Render prediction risk distribution chart."""

    if frame.empty:
        st.info("برای نمودار ریسک، ابتدا یک یا چند پیش‌بینی را در تاریخچه ثبت کنید.")
        return
    counts = frame.groupby("ریسک", as_index=False).size().rename(columns={"size": "تعداد"})
    figure = px.bar(counts, x="ریسک", y="تعداد", title="توزیع ریسک پیش‌بینی‌های ذخیره‌شده", text="تعداد")
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(title_x=0.95, xaxis_title="ریسک", yaxis_title="تعداد")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _render_category_chart(frame: pd.DataFrame) -> None:
    """Render category inventory chart."""

    counts = frame.groupby("دسته‌بندی", as_index=False)["موجودی فعلی"].sum()
    figure = px.bar(counts, x="دسته‌بندی", y="موجودی فعلی", title="موجودی بر اساس دسته‌بندی")
    figure.update_layout(title_x=0.95, xaxis_title="دسته‌بندی", yaxis_title="موجودی")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _render_expiration_chart(frame: pd.DataFrame) -> None:
    """Render expiration status chart."""

    counts = frame.groupby("وضعیت انقضا", as_index=False).size().rename(columns={"size": "تعداد"})
    figure = px.bar(counts, x="وضعیت انقضا", y="تعداد", title="وضعیت انقضای داروها", text="تعداد")
    figure.update_traces(textposition="outside", cliponaxis=False)
    figure.update_layout(title_x=0.95, xaxis_title="وضعیت", yaxis_title="تعداد")
    apply_chart_theme(figure)
    st.plotly_chart(figure, use_container_width=True)


def _render_recommendation_panel(bundle: ReportBundle) -> None:
    """Render concise management recommendations."""

    kpis = bundle.kpis
    recommendations = []
    if int(kpis["low_stock"]) > 0:
        recommendations.append("داروهای دارای کمبود یا ریسک کمبود را اولویت‌بندی و سفارش مجدد را ثبت کنید.")
    if int(kpis["expired"]) > 0:
        recommendations.append("داروهای منقضی‌شده باید فوراً از چرخه مصرف و گزارش موجودی عملیاتی خارج شوند.")
    if int(kpis["critical_predictions"]) > 0:
        recommendations.append("پیش‌بینی‌های بحرانی را با تأمین‌کننده و مسئول داروخانه/بیمارستان پیگیری کنید.")
    if int(kpis["serious_interactions"]) > 0:
        recommendations.append("قوانین تداخل شدید را در فرآیند نسخه‌پیچی و مصرف همزمان داروها برجسته کنید.")
    if not recommendations:
        recommendations.append("در وضعیت فعلی نشانه بحرانی جدی دیده نمی‌شود؛ پایش دوره‌ای را ادامه دهید.")

    html_items = "".join(f"<li>{item}</li>" for item in recommendations)
    st.markdown(
        f"""
        <div class="pg-report-advice">
          <h3>پیشنهادهای مدیریتی</h3>
          <ul>{html_items}</ul>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _log_report_view() -> None:
    """Write a lightweight activity log for report access."""

    user = st.session_state.get("user") or {}
    if st.session_state.get("reports_access_logged"):
        return
    ActivityLogRepository.log(
        user_id=user.get("id"),
        action="report_viewed",
        entity_type="reports",
        details="کاربر صفحه گزارش‌های مدیریتی را مشاهده کرد.",
    )
    st.session_state["reports_access_logged"] = True
