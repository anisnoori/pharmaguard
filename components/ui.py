"""Reusable UI primitives for PharmaGuard AI pages.

The helpers in this module keep HTML generation centralized, safe, and
consistent. Compact HTML is used intentionally to prevent Streamlit Markdown
from interpreting indented blocks as code blocks on some versions.
"""

from __future__ import annotations

import html

import streamlit as st


def section_header(title: str, subtitle: str) -> None:
    """Render a consistent Persian section heading."""

    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    st.markdown(
        (
            '<section class="pg-section">'
            f'<h2 class="pg-section-title">{safe_title}</h2>'
            f'<p class="pg-section-subtitle">{safe_subtitle}</p>'
            '</section>'
        ),
        unsafe_allow_html=True,
    )


def card_grid(cards: list[dict[str, str]], columns: int = 3) -> None:
    """Render a responsive HTML card grid.

    Args:
        cards: List of dictionaries containing badge, title, and description.
        columns: Desired grid density. Supports 3 or 4 columns.
    """

    grid_class = "pg-grid-4" if columns == 4 else "pg-grid-3"
    rendered_cards = []
    for card in cards:
        badge = html.escape(card.get("badge", ""))
        title = html.escape(card.get("title", ""))
        description = html.escape(card.get("description", ""))
        rendered_cards.append(
            '<div class="pg-card">'
            f'<span class="pg-badge">{badge}</span>'
            f'<h3>{title}</h3>'
            f'<p>{description}</p>'
            '</div>'
        )

    st.markdown(
        f'<div class="{grid_class}">{"".join(rendered_cards)}</div>',
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, caption: str) -> str:
    """Return a safe HTML metric card string."""

    safe_label = html.escape(label)
    safe_value = html.escape(value)
    safe_caption = html.escape(caption)
    return (
        '<div class="pg-card pg-stat">'
        f'<strong>{safe_value}</strong>'
        f'<span>{safe_label}</span>'
        f'<p>{safe_caption}</p>'
        '</div>'
    )
