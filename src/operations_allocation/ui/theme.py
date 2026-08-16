"""App-wide visual theme: a Qt Style Sheet (QSS -- Qt's CSS-like styling
language) plus the color palette it's built from. Purely cosmetic
(ARCHITECTURE.md section 9: no business logic in UI components cuts
both ways -- this module contains zero decisions about what the app
does, only how it looks). Applied once, globally, via apply_theme(app)
so every widget in both the Dashboard and Run Detail gets a consistent
look without each widget file hand-rolling its own colors.

Design goals: calm, uncluttered, and legible for someone who has never
used this tool before -- clear visual hierarchy (one obvious primary
action per screen via the "accent" property), generous spacing/rounded
corners so it doesn't look like a raw, unstyled Qt app, and enough
color contrast to be readable without being garish.
"""

from __future__ import annotations

from typing import Any

PALETTE = {
    "background": "#F3F4F6",  # gray-100: window/app background
    "surface": "#FFFFFF",  # panels, tables, inputs
    "border": "#D1D5DB",  # gray-300
    "text": "#111827",  # gray-900
    "text_muted": "#6B7280",  # gray-500
    "primary": "#2563EB",  # blue-600: the one accent color for primary actions
    "primary_hover": "#1D4ED8",  # blue-700
    "primary_pressed": "#1E40AF",  # blue-800
    "danger": "#DC2626",  # red-600: destructive actions (Cancel Run)
    "danger_hover": "#B91C1C",  # red-700
    "disabled_bg": "#E5E7EB",  # gray-200
    "disabled_text": "#9CA3AF",  # gray-400
}

STYLESHEET = f"""
QWidget {{
    background-color: {PALETTE["background"]};
    color: {PALETTE["text"]};
    font-size: 13px;
}}

QMainWindow, QDialog {{
    background-color: {PALETTE["background"]};
}}

QLabel[heading="true"] {{
    font-size: 20px;
    font-weight: 700;
    color: {PALETTE["text"]};
    padding: 4px 0px;
}}

QLabel[subheading="true"] {{
    font-size: 14px;
    font-weight: 600;
    color: {PALETTE["text_muted"]};
    padding-top: 8px;
}}

QGroupBox {{
    background-color: {PALETTE["surface"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 8px;
    margin-top: 12px;
    padding: 10px;
    font-weight: 600;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 6px;
    color: {PALETTE["text"]};
}}

QTableWidget, QPlainTextEdit, QLineEdit, QComboBox, QDateEdit {{
    background-color: {PALETTE["surface"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: {PALETTE["primary"]};
    selection-color: white;
}}

QHeaderView::section {{
    background-color: {PALETTE["background"]};
    color: {PALETTE["text_muted"]};
    font-weight: 600;
    border: none;
    border-bottom: 2px solid {PALETTE["border"]};
    padding: 6px;
}}

QTableWidget::item {{
    padding: 4px;
}}

QPushButton {{
    background-color: {PALETTE["surface"]};
    color: {PALETTE["text"]};
    border: 1px solid {PALETTE["border"]};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
}}

QPushButton:hover {{
    background-color: {PALETTE["background"]};
    border-color: {PALETTE["primary"]};
}}

QPushButton:pressed {{
    background-color: {PALETTE["border"]};
}}

QPushButton:disabled {{
    background-color: {PALETTE["disabled_bg"]};
    color: {PALETTE["disabled_text"]};
    border-color: {PALETTE["disabled_bg"]};
}}

/* One clear primary action per screen -- set via widget.setProperty("accent", True) */
QPushButton[accent="true"] {{
    background-color: {PALETTE["primary"]};
    color: white;
    border: 1px solid {PALETTE["primary"]};
    font-weight: 600;
}}

QPushButton[accent="true"]:hover {{
    background-color: {PALETTE["primary_hover"]};
    border-color: {PALETTE["primary_hover"]};
}}

QPushButton[accent="true"]:pressed {{
    background-color: {PALETTE["primary_pressed"]};
}}

/* Destructive actions (Cancel Run) -- set via widget.setProperty("danger", True) */
QPushButton[danger="true"] {{
    color: {PALETTE["danger"]};
    border-color: {PALETTE["danger"]};
}}

QPushButton[danger="true"]:hover {{
    background-color: {PALETTE["danger"]};
    color: white;
}}

QDialogButtonBox QPushButton {{
    min-width: 80px;
}}
"""


def apply_theme(app: Any) -> None:
    """Applies the global stylesheet. Call once, right after constructing
    the QApplication (see ui.app.main)."""
    app.setStyleSheet(STYLESHEET)
