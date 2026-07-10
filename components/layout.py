"""Shared layout components for PharmaGuard AI."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import streamlit as st

from auth.session import logout_user
from config import STYLE_DIR, settings
from services.notification_service import NotificationService


NavAction = tuple[str, str, Callable[[], None]]


def _read_css_file(path: Path) -> str:
    """Read CSS safely from disk."""

    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_design_system() -> None:
    """Inject the unified RTL design system into Streamlit.

    Streamlit sanitizes or prints script tags in some environments, so theme
    variables must be applied with CSS only. This avoids the visible
    ``<script>...`` artifact that appeared at the top of pages.
    """

    css_parts = []
    for file_name in (
        "variables.css",
        "light.css",
        "dark.css",
        "layout.css",
        "components.css",
        "forms.css",
        "cards.css",
        "animations.css",
        "streamlit_overrides.css",
        "responsive.css",
        "final_overrides.css",
    ):
        css_parts.append(_read_css_file(STYLE_DIR / file_name))

    theme = str(st.session_state.get("theme", settings.default_theme)).lower()
    css_parts.append(_theme_override_css(theme))
    st.markdown(f"<style>{''.join(css_parts)}</style>", unsafe_allow_html=True)


def _theme_override_css(theme: str) -> str:
    """Return script-free CSS variables and Streamlit widget overrides."""

    dark_variables = """
      --pg-bg: #081827;
      --pg-surface: #0f2438;
      --pg-card: rgba(15, 36, 56, 0.96);
      --pg-card-solid: #0f2438;
      --pg-border: rgba(203, 213, 225, 0.16);
      --pg-text: #e6f1fb;
      --pg-heading: #f6fbff;
      --pg-muted: #9fb3c8;
      --pg-soft: rgba(28, 126, 214, 0.20);
      --pg-soft-2: rgba(231, 245, 255, 0.08);
      --pg-divider: rgba(203, 213, 225, 0.12);
      --pg-input: #132c43;
      --pg-hero-gradient: linear-gradient(135deg, rgba(15, 36, 56, 0.98), rgba(8, 24, 39, 0.88));
    """
    light_variables = """
      --pg-bg: #f7fafc;
      --pg-surface: #ffffff;
      --pg-card: rgba(255, 255, 255, 0.92);
      --pg-card-solid: #ffffff;
      --pg-border: rgba(15, 23, 42, 0.10);
      --pg-text: #102a43;
      --pg-heading: #0b2540;
      --pg-muted: #627d98;
      --pg-soft: #e7f5ff;
      --pg-soft-2: #f1f8ff;
      --pg-divider: rgba(15, 23, 42, 0.08);
      --pg-input: #ffffff;
      --pg-hero-gradient: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(231, 245, 255, 0.65));
    """
    if theme == "dark":
        variables = dark_variables
    elif theme == "auto":
        return f"""
        :root, html, body, .stApp {{{light_variables}}}
        @media (prefers-color-scheme: dark) {{
          :root, html, body, .stApp {{{dark_variables}}}
        }}
        {_theme_widget_override()}
        """
    else:
        variables = light_variables
    return f"""
    :root, html, body, .stApp {{{variables}}}
    {_theme_widget_override()}
    """


def _theme_widget_override() -> str:
    """Return high-specificity CSS that forces theme variables into Streamlit."""

    return """
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stAppViewContainer"] > .main {
      background: radial-gradient(circle at 12% 8%, rgba(28, 126, 214, 0.12), transparent 30%),
                  radial-gradient(circle at 88% 96%, rgba(112, 72, 232, 0.10), transparent 34%),
                  var(--pg-bg) !important;
      color: var(--pg-text) !important;
    }
    .pg-navbar, .pg-card, .pg-form-card, .pg-footer, [data-testid="stMetric"],
    [data-testid="stForm"], [data-testid="stExpander"] details {
      background: var(--pg-card) !important;
      color: var(--pg-text) !important;
      border-color: var(--pg-border) !important;
    }
    .pg-hero, .pg-module-hero, .pg-dashboard-header {
      background: var(--pg-hero-gradient) !important;
      color: var(--pg-text) !important;
      border-color: var(--pg-border) !important;
    }
    h1, h2, h3, h4, h5, h6, .pg-brand, .pg-section-title, .pg-card h2, .pg-card h3 {
      color: var(--pg-heading) !important;
    }
    p, span, label, .pg-section-subtitle, .pg-card p, .pg-module-hero p, .pg-hero p {
      color: var(--pg-text) !important;
    }
    .stTextInput input, .stTextArea textarea, .stNumberInput input, .stDateInput input,
    [data-baseweb="select"] > div, [data-testid="stFileUploader"] section {
      background: var(--pg-input) !important;
      color: var(--pg-text) !important;
      border-color: var(--pg-border) !important;
    }
    [data-testid="stDataFrame"], [data-testid="stTable"] {
      background: var(--pg-card-solid) !important;
      color: var(--pg-text) !important;
      border-color: var(--pg-border) !important;
    }
    """


def _go_to(page: str) -> None:
    """Navigate to a logical application page."""

    st.session_state.current_page = page
    st.rerun()


def render_navbar() -> None:
    """Render top navigation with public and authenticated actions."""

    user = st.session_state.get("user")
    st.markdown(
        f"""
        <div class="pg-navbar">
          <div class="pg-brand">
            <span class="pg-logo-mark"></span>
            <span>{settings.app_name_fa}</span>
          </div>
          <div class="pg-badge">پایش هوشمند زنجیره تأمین دارو</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    actions = _authenticated_actions() if user else _public_actions()
    _render_nav_actions(actions)


def _render_nav_actions(actions: list[NavAction]) -> None:
    """Render actions in responsive rows to avoid overcrowded nav buttons."""

    row_size = 6 if len(actions) > 6 else len(actions)
    for start in range(0, len(actions), row_size):
        row_actions = actions[start:start + row_size]
        columns = st.columns([1] * len(row_actions))
        for column, (label, key, action) in zip(columns, row_actions, strict=True):
            with column:
                if st.button(label, use_container_width=True, key=key):
                    action()


def _public_actions() -> list[NavAction]:
    """Return public navigation actions."""

    return [
        ("خانه", "nav_home", lambda: _go_to("landing")),
        ("امکانات", "nav_features", lambda: _go_to("features")),
        ("ورود", "nav_login", lambda: _go_to("login")),
        ("ثبت نام", "nav_register", lambda: _go_to("register")),
    ]


def _authenticated_actions() -> list[NavAction]:
    """Return authenticated navigation actions."""

    user = st.session_state.get("user") or {}
    approval_status = str(user.get("approval_status", "approved"))
    if user.get("role_code") != "administrator" and approval_status != "approved":
        return [
            ("خانه", "nav_home", lambda: _go_to("landing")),
            ("وضعیت حساب", "nav_pending", lambda: _go_to("pending_approval")),
            ("امکانات", "nav_features", lambda: _go_to("features")),
            ("خروج از حساب", "nav_logout", _logout_and_return_home),
        ]

    unread = 0
    try:
        if user.get("id"):
            unread = NotificationService.unread_count(int(user["id"]))
    except Exception:
        unread = 0
    notification_label = f"هشدارها ({unread})" if unread else "هشدارها"
    actions = [
        ("داشبورد", "nav_dashboard", lambda: _go_to("dashboard")),
        ("مدیریت دارو", "nav_drugs", lambda: _go_to("drugs")),
        ("ورود داده", "nav_upload", lambda: _go_to("upload")),
        ("اسکن دارو", "nav_scanner", lambda: _go_to("scanner")),
        ("پیش‌بینی AI", "nav_predictions", lambda: _go_to("predictions")),
        ("تداخل دارویی", "nav_interactions", lambda: _go_to("interactions")),
        ("گزارش‌ها", "nav_reports", lambda: _go_to("reports")),
        (notification_label, "nav_notifications", lambda: _go_to("notifications")),
        ("پروفایل", "nav_profile", lambda: _go_to("profile")),
        ("تنظیمات", "nav_settings", lambda: _go_to("settings")),
    ]
    if user.get("role_code") == "administrator":
        actions.insert(0, ("مدیریت سامانه", "nav_admin", lambda: _go_to("admin")))
    actions.append(("خروج", "nav_logout", _logout_and_return_home))
    return actions


def _logout_and_return_home() -> None:
    """End the session and return to the public homepage."""

    logout_user()
    st.session_state.current_page = "landing"
    st.rerun()


def render_footer() -> None:
    """Render public footer."""

    st.markdown(
        """
        <footer class="pg-footer">
          <strong>فارماگارد هوشمند</strong><br>
          سامانه هوشمند پایش زنجیره تأمین دارو، پیش‌بینی کمبود و افزایش ایمنی بیمار.
        </footer>
        """,
        unsafe_allow_html=True,
    )
