"""Session-state helpers for Streamlit authentication."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import streamlit as st

from config import settings

SESSION_KEYS: dict[str, Any] = {
    "authenticated": False,
    "user": None,
    "current_page": "landing",
    "theme": settings.default_theme,
    "last_activity_at": None,
}
ALLOWED_THEMES = {"light", "dark", "auto"}


def ensure_session_state() -> None:
    """Initialize required Streamlit session keys."""

    for key, default_value in SESSION_KEYS.items():
        st.session_state.setdefault(key, default_value)


def login_user(user: dict[str, Any]) -> None:
    """Persist authenticated user data in Streamlit session state."""

    st.session_state.authenticated = True
    st.session_state.user = user
    hydrate_user_preferences()
    if _requires_approval(user):
        st.session_state.current_page = "pending_approval"
    else:
        st.session_state.current_page = "dashboard"
    touch_session()


def logout_user() -> None:
    """Clear user session while preserving visual preferences."""

    theme = st.session_state.get("theme", "light")
    for key in SESSION_KEYS:
        st.session_state[key] = SESSION_KEYS[key]
    st.session_state.theme = _safe_theme(theme)
    st.session_state.current_page = "landing"


def hydrate_user_preferences() -> None:
    """Load saved theme/language preferences into session state.

    This is intentionally imported lazily to avoid repository imports during
    module import and to keep the session helper lightweight.
    """

    user = st.session_state.get("user") or {}
    user_id = user.get("id")
    if not user_id:
        st.session_state.theme = _safe_theme(st.session_state.get("theme", settings.default_theme))
        return
    try:
        from database.repositories import UserPreferenceRepository

        preferences = UserPreferenceRepository.get(int(user_id))
        st.session_state.theme = _safe_theme(preferences.theme)
    except Exception:
        st.session_state.theme = _safe_theme(st.session_state.get("theme", settings.default_theme))


def touch_session() -> None:
    """Update last activity timestamp."""

    st.session_state.last_activity_at = datetime.now(timezone.utc)


def session_expired() -> bool:
    """Return True when the authenticated session exceeded timeout."""

    last_activity = st.session_state.get("last_activity_at")
    if not st.session_state.get("authenticated") or last_activity is None:
        return False
    expires_at = last_activity + timedelta(minutes=settings.session_timeout_minutes)
    return datetime.now(timezone.utc) > expires_at


def _safe_theme(theme: Any) -> str:
    """Return a supported theme value."""

    value = str(theme or "light").lower()
    return value if value in ALLOWED_THEMES else "light"


def _requires_approval(user: dict[str, Any]) -> bool:
    """Return True when a user must wait for admin approval."""

    if user.get("role_code") == "administrator":
        return False
    return str(user.get("approval_status", "approved")) != "approved"
