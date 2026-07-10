"""Public Persian landing pages for PharmaGuard AI."""

from __future__ import annotations

import streamlit as st

from components.ui import card_grid, metric_card, section_header
from database.repositories import AnalyticsRepository
from utils.persian import fa_number


def render_landing_page() -> None:
    """Render the public product homepage before authentication."""

    st.markdown(
        """
        <section class="pg-hero">
          <span class="pg-kicker">هوش مصنوعی برای امنیت دارویی</span>
          <h1>کمبود دارو را قبل از بحران پیش‌بینی کنید.</h1>
          <p>
            فارماگارد هوشمند یک پلتفرم سلامت دیجیتال برای بیمارستان‌ها، داروخانه‌ها،
            سازمان‌های درمانی و مدیران زنجیره تأمین است. این سامانه موجودی دارو،
            ریسک کمبود، تداخل دارویی و گزارش‌های مدیریتی را در یک محیط فارسی، امن و قابل اعتماد
            یکپارچه می‌کند.
          </p>
        </section>
        """,
        unsafe_allow_html=True,
    )

    _render_landing_actions()
    render_stats()
    render_features()
    render_target_users()
    render_ai_section()
    render_faq()


def _render_landing_actions() -> None:
    """Render primary landing page actions with stable Streamlit keys."""

    st.markdown('<div class="pg-inline-actions"></div>', unsafe_allow_html=True)
    cta_cols = st.columns([1.15, 1.0, 1.2, 3.7])
    with cta_cols[0]:
        if st.button(
            "شروع استفاده",
            use_container_width=True,
            type="primary",
            key="landing_start_cta",
        ):
            st.session_state.current_page = "register"
            st.rerun()
    with cta_cols[1]:
        if st.button("ورود", use_container_width=True, key="landing_login_cta"):
            st.session_state.current_page = "login"
            st.rerun()
    with cta_cols[2]:
        if st.button(
            "مشاهده امکانات",
            use_container_width=True,
            key="landing_features_cta",
        ):
            st.session_state.current_page = "features"
            st.rerun()


def render_features_page() -> None:
    """Render the extended features page."""

    section_header(
        "امکانات کلیدی فارماگارد",
        "هر قابلیت برای یک مسئله واقعی در مدیریت دارو طراحی شده است: کاهش کمبود، افزایش ایمنی بیمار، تصمیم‌گیری سریع‌تر و شفافیت مدیریتی.",
    )
    render_features()
    render_target_users()
    render_ai_section()


def render_stats() -> None:
    """Render public trust-building product statistics."""

    summary = AnalyticsRepository.get_platform_summary()
    stats_html = "".join(
        [
            metric_card(
                "داروی قابل پایش",
                fa_number(summary["drugs"]),
                "داروهای موجود در پایگاه عملیاتی برای شروع پایش.",
            ),
            metric_card(
                "پیش‌بینی قابل توضیح",
                fa_number(summary["predictions"]),
                "زیرساخت آماده برای ثبت خروجی‌های هوش مصنوعی.",
            ),
            metric_card(
                "قانون تداخل دارویی",
                fa_number(summary["interactions"]),
                "پایه اولیه دانش دارویی برای هشدار بالینی.",
            ),
        ]
    )
    section_header(
        "اعتماد، شفافیت و تصمیم‌گیری سریع",
        "سامانه از ابتدا با دیتابیس ساختاریافته، نقش‌های کاربری و خروجی‌های قابل توضیح طراحی شده است.",
    )
    st.markdown(f"<div class='pg-grid-3'>{stats_html}</div>", unsafe_allow_html=True)


def render_features() -> None:
    """Render product feature cards."""

    cards = [
        {
            "badge": "هوش مصنوعی",
            "title": "پیش‌بینی کمبود دارو",
            "description": "تحلیل موجودی، مصرف، زمان تأمین و دسترسی بازار برای تشخیص ریسک قبل از بحران.",
        },
        {
            "badge": "ایمنی بیمار",
            "title": "بررسی تداخل دارویی",
            "description": "نمایش شدت، توضیح بالینی، هشدار و پیشنهاد اقدام برای مصرف همزمان داروها.",
        },
        {
            "badge": "موجودی",
            "title": "مدیریت موجودی",
            "description": "کنترل موجودی، نقطه سفارش، انقضا، دسته دارویی، تولیدکننده و تأمین‌کننده.",
        },
        {
            "badge": "گزارش",
            "title": "گزارش‌های مدیریتی",
            "description": "شاخص‌های کلیدی، نمودار روند، خروجی مدیریتی و گزارش قابل ارائه برای تصمیم‌گیران سلامت.",
        },
        {
            "badge": "اسکن دارو",
            "title": "اسکن هوشمند دارو",
            "description": "زیرساخت آماده برای تشخیص دارو، نمایش هشدار، معرفی جایگزین و ارزیابی ریسک کمبود.",
        },
        {
            "badge": "تجربه فارسی",
            "title": "رابط کاربری راست‌به‌چپ",
            "description": "صفحه اصلی، فرم‌ها، داشبورد و محتوای فارسی برای استفاده راحت و قابل اعتماد.",
        },
    ]
    card_grid(cards, columns=3)


def render_target_users() -> None:
    """Render target user value propositions."""

    section_header(
        "برای چه کسانی ساخته شده است؟",
        "داشبورد هر نقش فقط داده‌های مرتبط با همان نقش را نشان می‌دهد؛ مدیر سامانه، بیمارستان و داروخانه نیازهای متفاوت دارند.",
    )
    card_grid(
        [
            {
                "badge": "بیمارستان",
                "title": "بیمارستان‌ها",
                "description": "پایش داروهای حیاتی، هشدار کمبود و تصمیم‌گیری سریع برای ایمنی بیمار.",
            },
            {
                "badge": "داروخانه",
                "title": "داروخانه‌ها",
                "description": "کنترل موجودی، سفارش به‌موقع و بررسی تداخل دارویی در نقطه ارائه خدمت.",
            },
            {
                "badge": "سازمان درمانی",
                "title": "سازمان‌های درمانی",
                "description": "تحلیل ریسک، گزارش مدیریتی و پایش زنجیره تأمین در سطح سازمانی.",
            },
        ],
        columns=3,
    )


def render_ai_section() -> None:
    """Render explainable AI value proposition."""

    st.markdown(
        """
        <section class="pg-section">
          <div class="pg-card">
            <span class="pg-badge">هوش مصنوعی قابل توضیح</span>
            <h2 class="pg-section-title">هوش مصنوعی قابل توضیح، نه فقط یک عدد</h2>
            <p class="pg-section-subtitle">
              خروجی پیش‌بینی باید احتمال ریسک، سطح ریسک، اعتماد مدل، دلیل تصمیم،
              عوامل اثرگذار و پیشنهاد اقدام را نمایش دهد. بنابراین مدیر درمان فقط «کمبود داریم» نمی‌بیند،
              بلکه می‌فهمد چرا این اتفاق ممکن است رخ دهد و چه اقدامی باید انجام شود.
            </p>
          </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_faq() -> None:
    """Render Persian FAQ content."""

    st.markdown(
        "<section class='pg-section'><h2 class='pg-section-title'>سوالات متداول</h2></section>",
        unsafe_allow_html=True,
    )
    with st.expander("فارماگارد هوشمند دقیقاً چه مشکلی را حل می‌کند؟"):
        st.write(
            "این سامانه ریسک کمبود دارو را قبل از وقوع تشخیص می‌دهد و به سازمان کمک می‌کند زودتر تصمیم بگیرد."
        )
    with st.expander("آیا صفحه اول برنامه باید ورود باشد؟"):
        st.write("خیر. کاربر ابتدا باید ارزش محصول را در صفحه اصلی ببیند، سپس وارد یا ثبت‌نام کند.")
    with st.expander("آیا داشبورد همه کاربران یکسان است؟"):
        st.write(
            "خیر. نقش کاربر تعیین می‌کند چه داده‌هایی نمایش داده شود؛ مدیر سامانه، بیمارستان و داروخانه نیازهای متفاوت دارند."
        )
