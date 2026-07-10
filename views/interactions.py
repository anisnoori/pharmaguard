"""Drug interaction module for PharmaGuard AI.

Phase 4 turns the interaction feature into a clinically useful workflow:
users can check multiple drugs, understand severity, see recommendations,
review alternatives, and maintain an auditable knowledge base.
"""

from __future__ import annotations

import html
from typing import Any

import pandas as pd
import streamlit as st

from config import INTERACTION_SEVERITY_LABELS
from database.repositories import DrugRepository, InteractionRepository
from models.entities import InteractionAssessment, InteractionDrugProfile, InteractionRule
from services.interaction_service import DrugInteractionService
from utils.persian import fa_number

SEVERITY_FILTER_OPTIONS = {
    "همه شدت‌ها": "all",
    "منع مصرف همزمان": "contraindicated",
    "شدید": "high",
    "متوسط": "medium",
    "خفیف": "low",
}
SEVERITY_INPUT_OPTIONS = {
    "منع مصرف همزمان": "contraindicated",
    "شدید": "high",
    "متوسط": "medium",
    "خفیف": "low",
}
EVIDENCE_LEVELS = ["بالا", "متوسط", "پایین", "نیازمند بررسی"]
DISCLAIMER = (
    "این ابزار برای کمک به تصمیم‌گیری طراحی شده و جایگزین قضاوت پزشک، "
    "داروساز یا پروتکل رسمی مرکز درمانی نیست."
)


def render_interaction_page() -> None:
    """Render the complete drug-interaction module."""

    user = st.session_state.get("user")
    if not user:
        st.session_state.current_page = "login"
        st.rerun()
        return

    role_code = str(user["role_code"])
    can_write = DrugInteractionService.can_write(role_code)
    _render_page_header(str(user["role_name"]), can_write)

    tab_check, tab_library, tab_create, tab_guidance = st.tabs(
        ["بررسی تداخل", "دانشنامه تداخل", "ثبت قانون", "راهنمای ایمنی"]
    )
    with tab_check:
        _render_checker()
    with tab_library:
        _render_library(role_code, user_id=int(user["id"]))
    with tab_create:
        _render_create_rule(user, can_write)
    with tab_guidance:
        _render_guidance()


def _render_page_header(role_name: str, can_write: bool) -> None:
    """Render module hero and trust-focused context."""

    write_hint = "امکان ثبت قانون تداخل فعال است." if can_write else "این نقش فقط دسترسی مشاهده و بررسی دارد."
    counts = InteractionRepository.count_by_severity()
    total_rules = sum(counts.values())
    high_rules = counts.get("high", 0) + counts.get("contraindicated", 0)
    st.markdown(
        f"""
        <section class="pg-module-hero">
          <span class="pg-badge">ایمنی و تداخل دارویی</span>
          <h1>بررسی هوشمند تداخل دارویی با توصیه بالینی</h1>
          <p>
            چند دارو را همزمان انتخاب کنید تا سامانه شدت تداخل، توضیح بالینی،
            جایگزین‌های پیشنهادی، برنامه پایش و اقدام بعدی را به زبان فارسی نمایش دهد.
          </p>
          <div class="pg-module-meta">
            <span>نقش فعلی: {html.escape(role_name)}</span>
            <span>{html.escape(write_hint)}</span>
            <span>{fa_number(total_rules)} قانون دانشنامه</span>
            <span>{fa_number(high_rules)} قانون شدید/منع مصرف</span>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _render_checker() -> None:
    """Render multi-drug interaction checker."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>تحلیل نسخه یا لیست دارویی</h2>
          <p>
            داروهای ثبت‌شده در موجودی را انتخاب کنید یا نام داروهای دیگر را دستی وارد کنید.
            سامانه تمام جفت‌های ممکن را بررسی می‌کند و موارد پرخطر را اول نمایش می‌دهد.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    inventory_profiles = _render_drug_inputs()
    if st.button("تحلیل تداخل دارویی", key="interaction_run_check", use_container_width=True):
        assessment = DrugInteractionService.assess_interactions(inventory_profiles)
        st.session_state.interaction_assessment = assessment

    assessment = st.session_state.get("interaction_assessment")
    if assessment:
        _render_assessment(assessment)
    else:
        _render_empty_checker_state()


def _render_drug_inputs() -> list[InteractionDrugProfile]:
    """Render drug selectors and return selected profiles."""

    drug_options = DrugRepository.list_for_selection()
    label_to_id = {
        f"{name} · بچ {batch or 'بدون بچ'}": drug_id
        for drug_id, name, batch in drug_options
    }

    with st.container(border=True):
        col1, col2 = st.columns([2, 1])
        with col1:
            selected_labels = st.multiselect(
                "انتخاب از داروهای ثبت‌شده",
                options=list(label_to_id.keys()),
                placeholder="مثلاً وارفارین، آسپرین، انسولین...",
                key="interaction_inventory_selection",
                help="داروهایی که در ماژول مدیریت دارو ثبت شده‌اند اینجا نمایش داده می‌شوند.",
            )
        with col2:
            st.info("برای تحلیل دقیق‌تر، نام ژنریک دارو در کنار نام تجاری بررسی می‌شود.")

        manual_text = st.text_area(
            "افزودن دارو به صورت دستی",
            placeholder="هر دارو را با ویرگول یا در خط جدا وارد کنید؛ مثال: آسپرین، بتابلاکر",
            key="interaction_manual_text",
            height=110,
        )

    profiles: list[InteractionDrugProfile] = []
    for label in selected_labels:
        record = DrugRepository.get_by_id(label_to_id[label])
        if record:
            profiles.append(
                DrugInteractionService.profile_from_drug_record(
                    record.name,
                    record.generic_name,
                    record.batch_number,
                )
            )
    profiles.extend(DrugInteractionService.build_profiles_from_manual_text(manual_text))
    return profiles


def _render_empty_checker_state() -> None:
    """Render helpful starter examples for the checker."""

    st.markdown(
        """
        <div class="pg-empty-state">
          <h3>برای شروع، حداقل دو دارو انتخاب کنید.</h3>
          <p>
            داروهای مصرفی همزمان را از فهرست انتخاب کنید یا به‌صورت دستی وارد کنید تا شدت تداخل، هشدار و اقدام پیشنهادی نمایش داده شود.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_assessment(assessment: InteractionAssessment) -> None:
    """Render assessment summary, warnings, and findings."""

    _render_assessment_metrics(assessment)
    _render_assessment_message(assessment)

    if not assessment.findings:
        st.success(assessment.safety_summary)
        st.caption(assessment.recommended_next_step)
        return

    dataframe = pd.DataFrame(
        [
            {
                "داروها": f"{finding.drug_a} + {finding.drug_b}",
                "شدت": finding.severity_label,
                "توضیح": finding.description,
                "توصیه بالینی": finding.clinical_recommendation,
                "جایگزین/اقدام": finding.alternative_drugs or "با پزشک/داروساز بررسی شود",
                "پایش": finding.monitoring_plan or "بر اساس شرایط بیمار",
                "سطح شواهد": finding.evidence_level,
            }
            for finding in assessment.findings
        ]
    )
    st.dataframe(dataframe, use_container_width=True, hide_index=True)

    for index, finding in enumerate(assessment.findings, start=1):
        with st.expander(
            f"جزئیات {fa_number(index)} · {finding.severity_label}: {finding.drug_a} + {finding.drug_b}",
            expanded=index == 1,
        ):
            _render_finding_card(finding)


def _render_assessment_metrics(assessment: InteractionAssessment) -> None:
    """Render compact metrics for an interaction assessment."""

    selected_count = len(assessment.selected_drugs)
    finding_count = len(assessment.findings)
    highest_label = INTERACTION_SEVERITY_LABELS.get(assessment.highest_severity, "خفیف")
    st.markdown(
        f"""
        <div class="pg-mini-metrics">
          <div><strong>{fa_number(selected_count)}</strong><span>داروی بررسی‌شده</span></div>
          <div><strong>{fa_number(assessment.checked_pair_count)}</strong><span>جفت دارویی</span></div>
          <div><strong>{fa_number(finding_count)}</strong><span>تداخل یافت‌شده</span></div>
          <div><strong>{html.escape(highest_label)}</strong><span>بالاترین شدت</span></div>
          <div><strong>بالینی</strong><span>نوع خروجی</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_assessment_message(assessment: InteractionAssessment) -> None:
    """Render severity-aware message block."""

    message = f"{assessment.safety_summary} {assessment.recommended_next_step}"
    if assessment.highest_severity == "contraindicated":
        st.error(message)
    elif assessment.highest_severity == "high":
        st.warning(message)
    elif assessment.findings:
        st.info(message)
    st.caption(DISCLAIMER)


def _render_finding_card(finding: Any) -> None:
    """Render one detailed clinical finding."""

    severity_class = f"pg-interaction-{html.escape(finding.severity)}"
    st.markdown(
        f"""
        <div class="pg-finding-card {severity_class}">
          <div class="pg-finding-header">
            <span>{html.escape(finding.severity_label)}</span>
            <strong>{html.escape(finding.drug_a)} + {html.escape(finding.drug_b)}</strong>
          </div>
          <p><b>توضیح بالینی:</b> {html.escape(finding.description)}</p>
          <p><b>مکانیسم احتمالی:</b> {html.escape(finding.mechanism or 'ثبت نشده')}</p>
          <p><b>توصیه:</b> {html.escape(finding.clinical_recommendation)}</p>
          <p><b>جایگزین یا اقدام پیشنهادی:</b> {html.escape(finding.alternative_drugs or 'با پزشک/داروساز مسئول بررسی شود.')}</p>
          <p><b>برنامه پایش:</b> {html.escape(finding.monitoring_plan or 'بر اساس شرایط بیمار تعیین شود.')}</p>
          <p><b>مرجع:</b> {html.escape(finding.reference or 'ثبت نشده')} · <b>سطح شواهد:</b> {html.escape(finding.evidence_level)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_library(role_code: str, user_id: int) -> None:
    """Render searchable interaction knowledge base."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>دانشنامه تداخل‌های دارویی</h2>
          <p>قوانین ثبت‌شده را جستجو کنید، بر اساس شدت فیلتر بگیرید و جزئیات بالینی هر مورد را ببینید.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.container(border=True):
        col1, col2 = st.columns(2)
        with col1:
            search = st.text_input(
                "جستجو در دانشنامه",
                placeholder="نام دارو، توضیح، توصیه یا جایگزین",
                key="interaction_library_search",
            )
        with col2:
            severity_label = st.selectbox(
                "شدت تداخل",
                options=list(SEVERITY_FILTER_OPTIONS.keys()),
                key="interaction_library_severity",
            )

    rules = InteractionRepository.list_all(
        search=search,
        severity=SEVERITY_FILTER_OPTIONS[severity_label],
    )
    _render_library_summary(rules)
    if not rules:
        st.info("با فیلترهای فعلی، قانونی پیدا نشد.")
        return

    st.dataframe(_rules_to_dataframe(rules), use_container_width=True, hide_index=True)
    _render_rule_details(rules, role_code, user_id)


def _render_library_summary(rules: list[InteractionRule]) -> None:
    """Render library result summary."""

    high_count = sum(1 for rule in rules if rule.severity in {"high", "contraindicated"})
    medium_count = sum(1 for rule in rules if rule.severity == "medium")
    low_count = sum(1 for rule in rules if rule.severity == "low")
    st.markdown(
        f"""
        <div class="pg-mini-metrics">
          <div><strong>{fa_number(len(rules))}</strong><span>نتیجه</span></div>
          <div><strong>{fa_number(high_count)}</strong><span>شدید/منع مصرف</span></div>
          <div><strong>{fa_number(medium_count)}</strong><span>متوسط</span></div>
          <div><strong>{fa_number(low_count)}</strong><span>خفیف</span></div>
          <div><strong>فارسی</strong><span>زبان دانشنامه</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _rules_to_dataframe(rules: list[InteractionRule]) -> pd.DataFrame:
    """Convert interaction rules to a Persian DataFrame."""

    return pd.DataFrame(
        [
            {
                "شناسه": fa_number(rule.id),
                "داروی اول": rule.primary_drug,
                "داروی دوم": rule.secondary_drug,
                "شدت": INTERACTION_SEVERITY_LABELS.get(rule.severity, rule.severity),
                "توضیح": rule.description,
                "توصیه بالینی": rule.clinical_recommendation,
                "جایگزین": rule.alternative_drugs or "ثبت نشده",
                "سطح شواهد": rule.evidence_level,
            }
            for rule in rules
        ]
    )


def _render_rule_details(rules: list[InteractionRule], role_code: str, user_id: int) -> None:
    """Render expandable details and optional admin delete controls."""

    can_delete = DrugInteractionService.can_delete(role_code)
    for rule in rules:
        label = INTERACTION_SEVERITY_LABELS.get(rule.severity, rule.severity)
        with st.expander(f"{label} · {rule.primary_drug} + {rule.secondary_drug}"):
            _render_rule_card(rule)
            if can_delete:
                confirm_key = f"interaction_delete_confirm_{rule.id}"
                confirm_text = st.text_input(
                    "برای حذف، عبارت حذف را بنویسید",
                    key=confirm_key,
                    placeholder="حذف",
                )
                if st.button("حذف قانون", key=f"interaction_delete_{rule.id}"):
                    if confirm_text.strip() != "حذف":
                        st.error("برای حذف باید دقیقاً عبارت حذف را وارد کنید.")
                    else:
                        result = DrugInteractionService.delete_rule(rule.id, user_id, role_code)
                        if result.success:
                            st.success(result.message)
                            st.rerun()
                        else:
                            st.error(result.message)


def _render_rule_card(rule: InteractionRule) -> None:
    """Render a safe HTML card for an interaction rule."""

    severity_label = INTERACTION_SEVERITY_LABELS.get(rule.severity, rule.severity)
    st.markdown(
        f"""
        <div class="pg-finding-card pg-interaction-{html.escape(rule.severity)}">
          <div class="pg-finding-header">
            <span>{html.escape(severity_label)}</span>
            <strong>{html.escape(rule.primary_drug)} + {html.escape(rule.secondary_drug)}</strong>
          </div>
          <p><b>توضیح:</b> {html.escape(rule.description)}</p>
          <p><b>مکانیسم:</b> {html.escape(rule.mechanism or 'ثبت نشده')}</p>
          <p><b>توصیه بالینی:</b> {html.escape(rule.clinical_recommendation)}</p>
          <p><b>جایگزین‌ها:</b> {html.escape(rule.alternative_drugs or 'ثبت نشده')}</p>
          <p><b>پایش:</b> {html.escape(rule.monitoring_plan or 'ثبت نشده')}</p>
          <p><b>مرجع:</b> {html.escape(rule.reference or 'ثبت نشده')} · <b>سطح شواهد:</b> {html.escape(rule.evidence_level)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_create_rule(user: dict[str, Any], can_write: bool) -> None:
    """Render interaction-rule create form."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>ثبت قانون تداخل جدید</h2>
          <p>قوانین جدید باید توضیح بالینی، توصیه عملی، مرجع و برنامه پایش داشته باشند تا قابل اعتماد باشند.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if not can_write:
        st.warning("نقش شما اجازه ثبت قانون تداخل جدید ندارد.")
        return

    with st.form("interaction_rule_create_form"):
        col1, col2 = st.columns(2)
        with col1:
            primary_drug = st.text_input("داروی اول", placeholder="مثلاً وارفارین")
            severity_label = st.selectbox("شدت", options=list(SEVERITY_INPUT_OPTIONS.keys()))
            mechanism = st.text_area("مکانیسم احتمالی", height=95)
            alternative_drugs = st.text_area("جایگزین‌ها یا اقدام پیشنهادی", height=95)
        with col2:
            secondary_drug = st.text_input("داروی دوم", placeholder="مثلاً آسپرین")
            evidence_level = st.selectbox("سطح شواهد", options=EVIDENCE_LEVELS, index=1)
            reference = st.text_input("مرجع یا منبع", placeholder="مثلاً پروتکل بیمارستان / Clinical guidance")
            monitoring_plan = st.text_area("برنامه پایش", height=95)
        description = st.text_area("توضیح تداخل", height=105)
        clinical_recommendation = st.text_area("توصیه بالینی", height=105)
        submitted = st.form_submit_button("ثبت قانون تداخل", use_container_width=True)

    if not submitted:
        return

    payload = DrugInteractionService.build_rule_payload(
        primary_drug=primary_drug,
        secondary_drug=secondary_drug,
        severity=SEVERITY_INPUT_OPTIONS[severity_label],
        description=description,
        clinical_recommendation=clinical_recommendation,
        reference=reference,
        mechanism=mechanism,
        alternative_drugs=alternative_drugs,
        monitoring_plan=monitoring_plan,
        evidence_level=evidence_level,
    )
    result = DrugInteractionService.create_rule(
        payload,
        user_id=int(user["id"]),
        role_code=str(user["role_code"]),
    )
    if result.success:
        st.success(result.message)
        st.session_state.interaction_assessment = None
    else:
        st.error(result.message)


def _render_guidance() -> None:
    """Render professional guidance for safe interpretation."""

    st.markdown(
        """
        <div class="pg-panel-heading">
          <h2>راهنمای تفسیر خروجی</h2>
          <p>هدف این بخش این است که کاربر بداند با هر سطح تداخل چه اقدامی باید انجام دهد.</p>
        </div>
        <div class="pg-grid-4">
          <div class="pg-card pg-severity-guide pg-interaction-contraindicated">
            <span class="pg-badge">منع مصرف</span>
            <h3>اقدام فوری</h3>
            <p>مصرف همزمان معمولاً نباید بدون ارزیابی پزشک یا داروساز مسئول انجام شود.</p>
          </div>
          <div class="pg-card pg-severity-guide pg-interaction-high">
            <span class="pg-badge">شدید</span>
            <h3>ریسک مهم بالینی</h3>
            <p>نیاز به انتخاب جایگزین، تغییر دوز، پایش آزمایشگاهی یا آموزش دقیق بیمار دارد.</p>
          </div>
          <div class="pg-card pg-severity-guide pg-interaction-medium">
            <span class="pg-badge">متوسط</span>
            <h3>قابل مدیریت</h3>
            <p>با بررسی شرایط بیمار، پایش علائم و مستندسازی قابل کنترل است.</p>
          </div>
          <div class="pg-card pg-severity-guide pg-interaction-low">
            <span class="pg-badge">خفیف</span>
            <h3>نیاز به آگاهی</h3>
            <p>معمولاً منع مصرف نیست، اما باید به بیمار هشدار و راهنمایی داده شود.</p>
          </div>
        </div>
        <div class="pg-clinical-note">
          <strong>نکته ایمنی:</strong>
          خروجی سامانه باید همراه با سن، وزن، بارداری، آلرژی، عملکرد کلیه و کبد، تشخیص اصلی،
          دوز مصرفی و داروهای بدون نسخه بیمار تفسیر شود.
        </div>
        """,
        unsafe_allow_html=True,
    )
