"""Plotly theme helpers for PharmaGuard AI."""

from __future__ import annotations

import streamlit as st

FONT_FAMILY = "Vazirmatn, Tahoma, Arial"


def apply_chart_theme(figure, *, title_x: float = 0.95):
    """Apply RTL-aware light/dark chart styling to a Plotly figure."""

    theme = str(st.session_state.get("theme", "light")).lower()
    dark = theme == "dark"
    text_color = "#e6f1fb" if dark else "#102a43"
    grid_color = "rgba(203, 213, 225, 0.18)" if dark else "rgba(15, 23, 42, 0.10)"
    paper = "rgba(0,0,0,0)"
    figure.update_layout(
        template="plotly_dark" if dark else "plotly_white",
        title_x=title_x,
        font={"family": FONT_FAMILY, "size": 13, "color": text_color},
        paper_bgcolor=paper,
        plot_bgcolor=paper,
        margin={"l": 20, "r": 20, "t": 70, "b": 45},
        legend={"font": {"color": text_color}},
    )
    figure.update_xaxes(color=text_color, gridcolor=grid_color, zerolinecolor=grid_color)
    figure.update_yaxes(color=text_color, gridcolor=grid_color, zerolinecolor=grid_color)
    return figure
