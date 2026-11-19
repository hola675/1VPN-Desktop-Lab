"""OneTunnel Qt/PySide6 design system for v0.7 preview."""
from __future__ import annotations

BG = "#07111f"
SURFACE = "#0d1a2b"
SURFACE_2 = "#12243a"
SURFACE_3 = "#18314d"
BORDER = "#203b5a"
TEXT = "#f4f8ff"
MUTED = "#8ea7c4"
SUBTLE = "#607c9d"
ACCENT = "#54d7f4"
ACCENT_HOVER = "#82e5f8"
SUCCESS = "#55d6ad"
WARN = "#f4b860"
DANGER = "#ff7182"

APP_QSS = f"""
* {{
    font-family: "Segoe UI";
    color: {TEXT};
    outline: none;
}}
QMainWindow, QWidget#Root {{
    background: {BG};
}}
QWidget#Sidebar {{
    background: #081523;
    border-right: 1px solid {BORDER};
}}
QLabel#Brand {{
    font-size: 23px;
    font-weight: 700;
}}
QLabel#VersionBadge {{
    color: {ACCENT};
    background: #123247;
    border: 1px solid #1b4a67;
    border-radius: 10px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 700;
}}
QPushButton#NavButton {{
    text-align: left;
    padding: 11px 14px;
    border-radius: 9px;
    border: 0;
    background: transparent;
    color: {MUTED};
    font-size: 12px;
    font-weight: 600;
}}
QPushButton#NavButton:hover {{
    background: {SURFACE};
    color: {TEXT};
}}
QPushButton#NavButton:checked {{
    background: {SURFACE_2};
    color: {TEXT};
    border: 1px solid {BORDER};
}}
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 13px;
}}
QFrame#CardStrong {{
    background: {SURFACE_2};
    border: 1px solid #2a4b70;
    border-radius: 15px;
}}
QLabel#Eyebrow {{
    color: {MUTED};
    font-size: 10px;
    font-weight: 700;
}}
QLabel#HeroStatus {{
    font-size: 24px;
    font-weight: 700;
}}
QLabel#CardValue {{
    font-size: 14px;
    font-weight: 650;
}}
QLabel#Muted {{
    color: {MUTED};
}}
QLabel#Success {{
    color: {SUCCESS};
    font-weight: 650;
}}
QLabel#Warning {{
    color: {WARN};
    font-weight: 650;
}}
QLabel#Danger {{
    color: {DANGER};
    font-weight: 650;
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: {BG};
    border: 0;
    border-radius: 10px;
    padding: 11px 18px;
    font-weight: 750;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#DangerButton {{
    background: {DANGER};
    color: #ffffff;
    border: 0;
    border-radius: 10px;
    padding: 11px 18px;
    font-weight: 750;
}}
QPushButton#Secondary {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 9px 14px;
    font-weight: 650;
}}
QPushButton#Secondary:hover {{
    background: {SURFACE_3};
}}
QPushButton#Ghost {{
    background: transparent;
    color: {MUTED};
    border: 0;
    padding: 8px 10px;
}}
QLineEdit, QComboBox, QSpinBox {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 8px 10px;
    min-height: 20px;
    selection-background-color: {SURFACE_3};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
    color: {SUBTLE};
    background: #0c1726;
}}
QComboBox::drop-down {{
    border: 0;
    width: 26px;
}}
QComboBox QAbstractItemView {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    selection-background-color: {SURFACE_3};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1px solid {BORDER};
    background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
}}
QTableWidget {{
    background: {SURFACE};
    alternate-background-color: #0b1727;
    border: 1px solid {BORDER};
    border-radius: 11px;
    gridline-color: transparent;
    selection-background-color: {SURFACE_3};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE_2};
    color: {MUTED};
    padding: 9px;
    border: 0;
    border-bottom: 1px solid {BORDER};
    font-weight: 700;
}}
QTabWidget::pane {{
    border: 0;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 9px 14px;
    margin-right: 3px;
    border-radius: 8px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    background: {SURFACE_2};
}}
QPlainTextEdit {{
    background: #050c16;
    border: 1px solid {BORDER};
    border-radius: 10px;
    color: {MUTED};
    padding: 8px;
    font-family: "Consolas";
}}
QScrollArea {{
    border: 0;
    background: transparent;
}}
QScrollBar:vertical {{
    width: 10px;
    background: transparent;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 25px;
}}
"""
