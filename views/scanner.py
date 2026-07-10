"""Drug scanner page for PharmaGuard AI."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import INTERACTION_SEVERITY_LABELS, RISK_LABELS
from database.repositories import DrugRepository, ScannerHistoryRepository
from models.entities import ScannerAnalysis
from services.scanner_service import DrugScannerService, SUPPORTED_IMAGE_EXTENSIONS
from utils.persian import fa_number, percent_fa

STATUS_LABELS = {
    "verified": "تأییدشده",
    "action_required": "نیازمند اقدام",
    "needs_review": "نیازمند بازبینی",
    "unmatched": "بدون تطبیق قطعی",
    "reference_only": "شناسایی مرجع؛ خارج از موجودی",
}


def render_scanner_page() -> None:
    """Render the drug scanner module."""

    if not st.session_state.get("authenticated"):
        st.session_state.current_page = "login"
        st.rerun()
        return

    st.markdown(
        """
        <section class="pg-module-hero">
          <span class="pg-badge">اسکن هوشمند دارو</span>
          <h1>اسکن هوشمند دارو با تطبیق محافظه‌کارانه و مرجع بین‌المللی</h1>
          <p>
            تصویر بسته یا بلیستر دارو را بارگذاری کنید. سامانه متن خوانا، نام دارو، دوز و شماره بچ را با موجودی
            سازمانی و مرجع دارویی بین‌المللی تطبیق می‌دهد. در این نسخه از حدس‌زدن روی عکس‌های نامشخص جلوگیری
            می‌شود تا دارو اشتباه نمایش داده نشود.
          </p>
          <div class="pg-module-meta">
            <span>مرجع دارویی بین‌المللی</span>
            <span>تطبیق محافظه‌کارانه</span>
            <span>تحلیل تداخل</span>
            <span>پیش‌بینی کمبود</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )

    tab_scan, tab_history, tab_guide = st.tabs(["اسکن دارو", "تاریخچه اسکن", "راهنمای عکس مناسب"])
    with tab_scan:
        _render_scan_workflow()
    with tab_history:
        _render_scanner_history()
    with tab_guide:
        _render_scanner_guide()


def _render_scan_workflow() -> None:
    """Render image upload, analysis controls, and scan result."""

    if not DrugRepository.list_for_selection():
        st.info("برای استفاده از اسکنر، ابتدا چند دارو را در بخش مدیریت دارو ثبت کنید تا سامانه بتواند تصویر را با موجودی تطبیق دهد.")
        return

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۱. تصویر و اطلاعات خوانا را وارد کنید</h2>
          <p>برای جلوگیری از تشخیص اشتباه، نام دارو/دوز/شماره بچ را از روی بسته وارد کنید. سامانه در صورت نبود متن کافی از حدس قطعی خودداری می‌کند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_upload, col_context = st.columns([1, 1])
    with col_upload:
        uploaded = st.file_uploader(
            "تصویر بسته، بلیستر یا برچسب دارو",
            type=[ext.replace(".", "") for ext in sorted(SUPPORTED_IMAGE_EXTENSIONS)],
            key="scanner_image_upload",
            help="فرمت‌های پیشنهادی: PNG، JPG، JPEG، WEBP",
        )
        if uploaded is not None:
            st.image(uploaded, caption="پیش‌نمایش تصویر بارگذاری‌شده", use_container_width=True)

    with col_context:
        label_text = st.text_area(
            "متن خوانا روی بسته / نام دارو / دوز / تولیدکننده / شماره بچ",
            placeholder="مثلاً: وارفارین ۵ میلی‌گرم، بچ WRF-1403، شرکت داروسازی ...",
            height=140,
            key="scanner_label_text",
        )
        co_medications = st.text_area(
            "داروهای همزمان بیمار برای بررسی تداخل، اختیاری",
            placeholder="مثلاً: آسپرین، ایبوپروفن، متفورمین",
            height=100,
            key="scanner_co_medications",
        )
        use_international_lookup = st.checkbox(
            "استعلام تکمیلی از RxNorm / openFDA در صورت اتصال اینترنت",
            value=True,
            key="scanner_use_international_lookup",
            help="اگر اینترنت در محیط اجرا فعال باشد، اطلاعات مرجع دارویی از APIهای عمومی تکمیل می‌شود؛ در غیر این صورت سامانه از مرجع داخلی استفاده می‌کند.",
        )

    if st.button("تحلیل تصویر دارو", key="run_drug_scanner", use_container_width=True):
        if uploaded is None:
            st.error("ابتدا تصویر دارو را بارگذاری کنید.")
            return
        content = uploaded.getvalue()
        DrugScannerService.save_uploaded_image(uploaded.name, content)
        analysis = DrugScannerService.analyze(
            file_name=uploaded.name,
            content=content,
            label_text=label_text,
            co_medications=co_medications,
            use_international_lookup=use_international_lookup,
        )
        st.session_state["scanner_last_analysis"] = analysis
        st.success("تحلیل اسکن دارو کامل شد.")

    analysis = st.session_state.get("scanner_last_analysis")
    if isinstance(analysis, ScannerAnalysis):
        _render_scan_result(analysis)


def _render_scan_result(analysis: ScannerAnalysis) -> None:
    """Render scanner analysis result in clinical workflow blocks."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>۲. نتیجه تشخیص و تصمیم‌یار بالینی</h2>
          <p>این خروجی برای کمک به تصمیم‌گیری است و جایگزین نظر پزشک یا داروساز مسئول نیست.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("وضعیت", STATUS_LABELS.get(analysis.status, analysis.status))
    col2.metric("داروی تشخیص‌داده‌شده", analysis.recognized_name)
    col3.metric("اطمینان تطبیق", percent_fa(analysis.confidence))
    col4.metric("کیفیت تصویر", analysis.image_quality)

    if analysis.warnings:
        for warning in analysis.warnings:
            st.warning(warning)

    st.info(analysis.ai_explanation)

    col_info, col_ai = st.columns([1, 1])
    with col_info:
        st.subheader("اطلاعات دارو")
        info_frame = pd.DataFrame(
            [{"فیلد": key, "مقدار": value} for key, value in analysis.drug_information.items()]
        )
        st.dataframe(info_frame, use_container_width=True, hide_index=True)

    with col_ai:
        _render_prediction_box(analysis)
        _render_interaction_box(analysis)

    _render_candidates(analysis)
    _render_alternatives(analysis)
    _render_save_history_button(analysis)


def _render_prediction_box(analysis: ScannerAnalysis) -> None:
    """Render attached shortage prediction summary."""

    st.subheader("ریسک کمبود مرتبط با داروی اسکن‌شده")
    prediction = analysis.prediction_summary
    if prediction is None:
        st.caption("برای نمایش ریسک کمبود، دارو باید با موجودی سامانه تطبیق داده شود.")
        return
    st.markdown(
        f"""
        <div class="pg-card pg-risk-card">
          <span class="pg-badge">{RISK_LABELS.get(prediction.risk_level, prediction.risk_level)}</span>
          <h3>احتمال کمبود: {percent_fa(prediction.probability)}</h3>
          <p>اعتماد مدل: {percent_fa(prediction.confidence)} · عامل اصلی: {prediction.top_factor}</p>
          <p>{prediction.suggested_action}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_interaction_box(analysis: ScannerAnalysis) -> None:
    """Render attached drug-interaction summary."""

    st.subheader("بررسی تداخل با داروهای همزمان")
    interaction = analysis.interaction_summary
    if interaction is None:
        st.caption("برای تحلیل تداخل، در فرم اسکن داروهای همزمان بیمار را وارد کنید.")
        return
    severity = INTERACTION_SEVERITY_LABELS.get(interaction.highest_severity, interaction.highest_severity)
    st.markdown(
        f"""
        <div class="pg-card">
          <span class="pg-badge">{severity}</span>
          <h3>{fa_number(interaction.finding_count)} مورد تداخل در {fa_number(interaction.checked_pair_count)} جفت بررسی‌شده</h3>
          <p>{interaction.safety_summary}</p>
          <p>{interaction.recommended_next_step}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_candidates(analysis: ScannerAnalysis) -> None:
    """Render ranked inventory candidates."""

    st.subheader("کاندیدهای تطبیق با موجودی")
    if not analysis.candidates:
        st.caption("کاندید مناسبی از موجودی پیدا نشد.")
        return
    frame = pd.DataFrame(
        [
            {
                "دارو": candidate.name,
                "ژنریک": candidate.generic_name or "ثبت نشده",
                "تولیدکننده": candidate.manufacturer or "ثبت نشده",
                "بچ": candidate.batch_number or "ثبت نشده",
                "اطمینان": percent_fa(candidate.confidence),
                "دلیل تطبیق": candidate.match_reason,
            }
            for candidate in analysis.candidates
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_alternatives(analysis: ScannerAnalysis) -> None:
    """Render alternative matching candidates."""

    if not analysis.alternative_drugs:
        return
    st.subheader("گزینه‌های نزدیک برای بازبینی")
    for item in analysis.alternative_drugs:
        st.caption(f"• {item}")


def _render_save_history_button(analysis: ScannerAnalysis) -> None:
    """Render audit save action."""

    user = st.session_state.get("user", {})
    if st.button("ثبت نتیجه اسکن در تاریخچه", key="scanner_save_history", use_container_width=True):
        history_id = DrugScannerService.persist_analysis(analysis, user_id=user.get("id"))
        st.success(f"نتیجه اسکن با شناسه {fa_number(history_id)} در تاریخچه ثبت شد.")


def _render_scanner_history() -> None:
    """Render recent scanner history."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>تاریخچه اسکن دارو</h2>
          <p>این بخش برای حسابرسی، پیگیری خطاهای تشخیص و بازبینی ایمنی داروها نگهداری می‌شود.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    rows = ScannerHistoryRepository.latest(limit=40)
    if not rows:
        st.info("هنوز هیچ اسکن ثبت‌شده‌ای وجود ندارد.")
        return
    frame = pd.DataFrame(
        [
            {
                "شناسه": fa_number(row.id),
                "تصویر": row.image_name,
                "تشخیص": row.recognized_drug_name or "نامشخص",
                "تطبیق موجودی": row.matched_drug_name,
                "اطمینان": percent_fa(row.confidence),
                "وضعیت": STATUS_LABELS.get(row.status, row.status),
                "هشدارها": row.warnings or "بدون هشدار",
                "زمان": fa_number(row.created_at),
            }
            for row in rows
        ]
    )
    st.dataframe(frame, use_container_width=True, hide_index=True)


def _render_scanner_guide() -> None:
    """Render scanner usage guidance."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>راهنمای عکس مناسب برای اسکن دارو</h2>
          <p>کیفیت تصویر مستقیماً روی دقت تشخیص و تصمیم‌یار دارویی اثر می‌گذارد.</p>
        </div>
        <div class="pg-grid-3">
          <div class="pg-card">
            <span class="pg-badge">نور کافی</span>
            <h3>برچسب باید خوانا باشد</h3>
            <p>نام دارو، دوز، تولیدکننده، تاریخ انقضا و شماره بچ باید در تصویر واضح دیده شود.</p>
          </div>
          <div class="pg-card">
            <span class="pg-badge">کادر درست</span>
            <h3>تصویر را از روبه‌رو بگیرید</h3>
            <p>از عکس تار، زاویه‌دار، خیلی نزدیک یا بخشی از بسته که متن کامل ندارد استفاده نکنید.</p>
          </div>
          <div class="pg-card">
            <span class="pg-badge">ایمنی</span>
            <h3>نتیجه را بازبینی کنید</h3>
            <p>اسکنر تصمیم‌یار است؛ قبل از تحویل یا مصرف، تطبیق دارو، بیمار، دوز و نسخه باید تأیید شود.</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
