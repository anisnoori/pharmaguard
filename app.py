"""Main Streamlit entrypoint for PharmaGuard AI."""

from __future__ import annotations

import streamlit as st

from auth.session import ensure_session_state, hydrate_user_preferences, logout_user, session_expired, touch_session
from components.layout import load_design_system, render_footer, render_navbar
from config import settings
from database.init_db import initialize_database
from views.admin import render_admin_panel_page
from views.auth import render_login_page, render_register_page
from views.dashboard import render_dashboard
from views.drugs import render_drug_management_page
from views.interactions import render_interaction_page
from views.landing import render_features_page, render_landing_page
from views.notifications import render_notifications_page
from views.pending import render_pending_approval_page
from views.predictions import render_prediction_page
from views.profile import render_profile_page
from views.reports import render_reports_page
from views.scanner import render_scanner_page
from views.settings import render_settings_page
from views.upload import render_data_import_page


def bootstrap() -> None:
    """Configure page, session, design system, and database."""

    st.set_page_config(
        page_title=settings.page_title,
        page_icon=settings.page_icon,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    ensure_session_state()
    initialize_database()
    hydrate_user_preferences()
    load_design_system()


def route_current_page() -> None:
    """Route user to the selected page."""

    current_page = st.session_state.get("current_page", "landing")
    if session_expired():
        logout_user()
        st.warning("نشست شما منقضی شد. لطفاً دوباره وارد شوید.")
        current_page = "login"

    if st.session_state.get("authenticated"):
        touch_session()
        user = st.session_state.get("user") or {}
        approval_status = str(user.get("approval_status", "approved"))
        if user.get("role_code") != "administrator" and approval_status != "approved":
            if current_page not in {"pending_approval", "landing", "features"}:
                st.session_state.current_page = "pending_approval"
                current_page = "pending_approval"

    render_navbar()

    if current_page == "landing":
        render_landing_page()
    elif current_page == "features":
        render_features_page()
    elif current_page == "login":
        render_login_page()
    elif current_page == "register":
        render_register_page()
    elif current_page == "pending_approval":
        render_pending_approval_page()
    elif current_page == "dashboard":
        render_dashboard()
    elif current_page == "drugs":
        render_drug_management_page()
    elif current_page == "upload":
        render_data_import_page()
    elif current_page == "interactions":
        render_interaction_page()
    elif current_page == "predictions":
        render_prediction_page()
    elif current_page == "reports":
        render_reports_page()
    elif current_page == "scanner":
        render_scanner_page()
    elif current_page == "notifications":
        render_notifications_page()
    elif current_page == "profile":
        render_profile_page()
    elif current_page == "settings":
        render_settings_page()
    elif current_page == "admin":
        render_admin_panel_page()
    else:
        st.session_state.current_page = "landing"
        st.rerun()

    render_footer()


def main() -> None:
    """Application entrypoint."""

    bootstrap()
    route_current_page()


if __name__ == "__main__":
    main()
