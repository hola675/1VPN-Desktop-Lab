"""OneTunnel UI v0.6 design tokens and Tk/ttk helpers.

Visual goal: calm premium shell, strong connection hierarchy, advanced details
progressively disclosed. No network behavior lives in this module.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = "#08111f"
SURFACE = "#0f1c2e"
SURFACE_2 = "#14253b"
SURFACE_3 = "#19304b"
BORDER = "#233b59"
TEXT = "#f3f8ff"
MUTED = "#91a9c6"
SUBTLE = "#667f9e"
ACCENT = "#55d3f3"
ACCENT_HOVER = "#83e3f8"
SUCCESS = "#55d6ad"
WARN = "#f4b860"
DANGER = "#ff7182"

FONT = "Segoe UI"
MONO = "Consolas"


def apply_root(window: tk.Misc, *, title: str, geometry: str, minsize: tuple[int, int]):
    window.title(title)
    window.geometry(geometry)
    window.minsize(*minsize)
    window.configure(bg=BG)


def configure_ttk(root: tk.Misc):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        "OneTunnel.TCombobox",
        fieldbackground=SURFACE_2,
        background=SURFACE_2,
        foreground=TEXT,
        arrowcolor=MUTED,
        bordercolor=BORDER,
        lightcolor=BORDER,
        darkcolor=BORDER,
        padding=8,
        font=(FONT, 10),
    )
    style.map(
        "OneTunnel.TCombobox",
        fieldbackground=[("readonly", SURFACE_2), ("disabled", SURFACE)],
        foreground=[("readonly", TEXT), ("disabled", SUBTLE)],
        selectbackground=[("readonly", SURFACE_2)],
        selectforeground=[("readonly", TEXT)],
    )

    style.configure(
        "OneTunnel.Treeview",
        background=SURFACE,
        fieldbackground=SURFACE,
        foreground=TEXT,
        rowheight=34,
        borderwidth=0,
        relief="flat",
        font=(FONT, 9),
    )
    style.configure(
        "OneTunnel.Treeview.Heading",
        background=SURFACE_2,
        foreground=MUTED,
        relief="flat",
        font=(FONT, 9, "bold"),
        padding=(8, 8),
    )
    style.map(
        "OneTunnel.Treeview",
        background=[("selected", SURFACE_3)],
        foreground=[("selected", TEXT)],
    )
    style.map(
        "OneTunnel.Treeview.Heading",
        background=[("active", SURFACE_3)],
    )

    style.configure(
        "OneTunnel.TNotebook",
        background=BG,
        borderwidth=0,
        tabmargins=0,
    )
    style.configure(
        "OneTunnel.TNotebook.Tab",
        background=SURFACE,
        foreground=MUTED,
        padding=(16, 9),
        font=(FONT, 9, "bold"),
        borderwidth=0,
    )
    style.map(
        "OneTunnel.TNotebook.Tab",
        background=[("selected", SURFACE_2), ("active", SURFACE_2)],
        foreground=[("selected", TEXT), ("active", TEXT)],
    )


def label(parent, text: str, *, color=MUTED, size=10, bold=False, bg=None, **kwargs):
    return tk.Label(
        parent,
        text=text,
        fg=color,
        bg=bg or parent["bg"],
        font=(FONT, size, "bold" if bold else "normal"),
        anchor=kwargs.pop("anchor", "w"),
        justify=kwargs.pop("justify", "left"),
        **kwargs,
    )


def button(
    parent,
    text: str,
    command,
    *,
    variant: str = "secondary",
    width: int | None = None,
    compact: bool = False,
):
    palette = {
        "primary": (ACCENT, BG, ACCENT_HOVER, BG),
        "success": (SUCCESS, BG, "#7de2c1", BG),
        "danger": (DANGER, "#fff6f7", "#ff8d9a", "#ffffff"),
        "secondary": (SURFACE_2, TEXT, SURFACE_3, TEXT),
        "ghost": (BG, MUTED, SURFACE, TEXT),
    }
    bg, fg, active_bg, active_fg = palette[variant]
    options = dict(
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=active_fg,
        relief="flat",
        bd=0,
        font=(FONT, 9 if compact else 10, "bold"),
        padx=10 if compact else 16,
        pady=6 if compact else 10,
        cursor="hand2",
        highlightthickness=0,
    )
    if width is not None:
        options["width"] = width
    return tk.Button(parent, **options)


def card(parent, *, padx=18, pady=16, bg=SURFACE):
    return tk.Frame(
        parent,
        bg=bg,
        padx=padx,
        pady=pady,
        highlightbackground=BORDER,
        highlightthickness=1,
        bd=0,
    )


def entry(parent, *, secret=False, mono=False):
    return tk.Entry(
        parent,
        bg=SURFACE_2,
        fg=TEXT,
        insertbackground=TEXT,
        selectbackground=SURFACE_3,
        selectforeground=TEXT,
        relief="flat",
        highlightbackground=BORDER,
        highlightcolor=ACCENT,
        highlightthickness=1,
        font=(MONO if mono else FONT, 10),
        show="*" if secret else "",
    )


def badge(parent, text: str, *, tone: str = "neutral"):
    tones = {
        "neutral": (SURFACE_2, MUTED),
        "success": ("#103328", SUCCESS),
        "warning": ("#332a17", WARN),
        "danger": ("#351a24", DANGER),
        "accent": ("#123247", ACCENT),
    }
    bg, fg = tones[tone]
    return tk.Label(
        parent,
        text=text,
        bg=bg,
        fg=fg,
        font=(FONT, 8, "bold"),
        padx=9,
        pady=4,
    )
