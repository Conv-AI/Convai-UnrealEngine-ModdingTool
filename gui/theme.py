"""Design tokens, ttk styles and scrolling helpers for the GUI.

The palette, type scale and spacing scale come from docs/ui-design.md. Screens read
tokens through ``theme``, ``FONTS`` and ``SPACE`` rather than repeating literals, so a
token change lands everywhere at once.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class Theme:
    """Singleton colour palette.

    Usage:
        from gui.theme import theme
        background = theme["bg_app"]
    """

    _instance: Theme | None = None

    def __new__(cls) -> Theme:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_colors()
        return cls._instance

    def _init_colors(self) -> None:
        self.colors: dict[str, str] = {
            # Surfaces, in depth order: canvas, card, selected/input, hover.
            "bg_app": "#07100A",
            "bg_surface": "#0E1911",
            "bg_surface_raised": "#142219",
            "bg_hover": "#1B3022",

            # Borders
            "border_subtle": "#203527",
            "border_focus": "#42E18B",

            # Text
            "text_primary": "#EEF7F0",
            "text_secondary": "#A5B9AA",
            "text_disabled": "#65796B",

            # Accent
            "accent": "#35D878",
            "accent_hover": "#58E996",
            # A bright green is a light colour: text drawn ON the accent has to be
            # dark. White on #35D878 is 1.9:1 and unreadable.
            "accent_ink": "#04130A",

            # Status
            "warning": "#F0BD45",
            "danger": "#FF7469",

            # Status pills and inline banners: a tinted surface, its border and the
            # text colour that stays legible on it.
            "ok_soft": "#0A2112",
            "ok_soft_border": "#255A39",
            "ok_soft_text": "#93EFBB",
            "warn_soft": "#211B0C",
            "warn_soft_border": "#4B3B14",
            "warn_soft_text": "#F6D47F",
            "danger_soft": "#241010",
            "danger_soft_border": "#5C2A24",
            "danger_soft_text": "#FFB3AB",

            # Inputs sit a shade below their surface so the field edge reads without
            # relying on the border alone.
            "bg_field": "#09130D",
        }

    def __getitem__(self, key: str) -> str:
        return self.colors[key]


theme = Theme()


# Point sizes, not pixels: Tk scales points with the Windows display setting, so the
# type scale survives 150% scaling where a pixel size would not.
FONTS: dict[str, tuple] = {
    "page_title": ("Segoe UI Semibold", 24),
    "section_title": ("Segoe UI Semibold", 16),
    "field_title": ("Segoe UI Semibold", 12),
    "body": ("Segoe UI", 10),
    "body_strong": ("Segoe UI Semibold", 10),
    "meta": ("Segoe UI", 9),
    "meta_strong": ("Segoe UI Semibold", 9),
    "mono": ("Consolas", 9),
}

# 8 px grid. `gutter_narrow` is the screen gutter below 1000 px wide.
SPACE: dict[str, int] = {
    "gutter": 32,
    "gutter_narrow": 24,
    "surface": 20,
    "tight": 8,
    "section": 24,
    "app_bar": 64,
    "status_bar": 32,
    "row": 72,
    "hit": 44,
    "hit_compact": 36,
}

# Below this the shell drops to the narrow gutter and stacks the shelf columns.
NARROW_WIDTH = 1000


def apply_styles(root: tk.Misc) -> None:
    """Configure every ttk style the app uses.

    Called once on the root window; ttk styles are process-wide, so all Toplevels
    inherit them. Anything not styled here falls back to the 'clam' defaults, which are
    light and look broken against the dark palette -- Combobox, Treeview and Scrollbar
    especially.
    """
    c = theme.colors
    style = ttk.Style(root)
    style.theme_use("clam")

    # --- containers ---------------------------------------------------------
    for name, background in (
        ("TFrame", c["bg_app"]),
        ("App.TFrame", c["bg_app"]),
        ("Surface.TFrame", c["bg_surface"]),
        ("Raised.TFrame", c["bg_surface_raised"]),
        ("Field.TFrame", c["bg_field"]),
        ("OkSoft.TFrame", c["ok_soft"]),
        ("WarnSoft.TFrame", c["warn_soft"]),
        ("DangerSoft.TFrame", c["danger_soft"]),
    ):
        style.configure(name, background=background)

    # --- labels -------------------------------------------------------------
    # One style per (surface, role) pair: ttk resolves a label's background from its
    # style, not from the frame it happens to be packed into.
    label_roles = {
        "": ("text_primary", FONTS["body"]),
        "Muted.": ("text_secondary", FONTS["body"]),
        "Meta.": ("text_secondary", FONTS["meta"]),
        "Title.": ("text_primary", FONTS["page_title"]),
        "Section.": ("text_primary", FONTS["section_title"]),
        "Field.": ("text_primary", FONTS["field_title"]),
        "Strong.": ("text_primary", FONTS["body_strong"]),
        "Label.": ("text_secondary", FONTS["meta_strong"]),
        "Disabled.": ("text_disabled", FONTS["body"]),
        "Warning.": ("warning", FONTS["body"]),
        "Danger.": ("danger", FONTS["body"]),
        "Accent.": ("accent", FONTS["body"]),
    }
    surfaces = {
        "TLabel": "bg_app",
        "OnSurface.TLabel": "bg_surface",
        "OnRaised.TLabel": "bg_surface_raised",
        "OnField.TLabel": "bg_field",
    }
    for suffix, background in surfaces.items():
        for prefix, (colour, font) in label_roles.items():
            style.configure(f"{prefix}{suffix}", background=c[background],
                            foreground=c[colour], font=font)

    # Pill text sits on its own tint, so it needs its own foregrounds.
    style.configure("OkPill.TLabel", background=c["ok_soft"], foreground=c["ok_soft_text"], font=FONTS["meta"])
    style.configure("WarnPill.TLabel", background=c["warn_soft"], foreground=c["warn_soft_text"], font=FONTS["meta"])
    style.configure("DangerPill.TLabel", background=c["danger_soft"], foreground=c["danger_soft_text"], font=FONTS["meta"])
    style.configure("OkBanner.TLabel", background=c["ok_soft"], foreground=c["ok_soft_text"], font=FONTS["body"])
    style.configure("WarnBanner.TLabel", background=c["warn_soft"], foreground=c["warn_soft_text"], font=FONTS["body"])
    style.configure("DangerBanner.TLabel", background=c["danger_soft"], foreground=c["danger_soft_text"], font=FONTS["body"])

    # --- radio / check ------------------------------------------------------
    style.configure("TRadiobutton", background=c["bg_surface"], foreground=c["text_primary"], font=FONTS["body"])
    style.map("TRadiobutton", background=[("active", c["bg_surface"])], foreground=[("active", c["accent"])])

    # clam draws an unstyled indicator that renders as a crossed box on a dark
    # background -- a ticked option reads as switched off. Colour it explicitly.
    indicator = dict(
        indicatorbackground=c["bg_surface_raised"],
        indicatorforeground=c["accent"],
        indicatormargin=(0, 0, 8, 0),
        indicatorrelief="flat",
        focuscolor="",
    )
    indicator_map = dict(
        indicatorbackground=[
            ("selected", c["accent"]),
            ("active", c["bg_hover"]),
            ("disabled", c["bg_app"]),
        ],
        indicatorforeground=[("selected", c["accent_ink"]), ("disabled", c["text_disabled"])],
    )

    for name, background in (("TCheckbutton", c["bg_surface"]),
                             ("OnRaised.TCheckbutton", c["bg_surface_raised"]),
                             ("OnField.TCheckbutton", c["bg_field"])):
        style.configure(name, background=background, foreground=c["text_primary"],
                        font=FONTS["body"], **indicator)
        style.map(
            name,
            background=[("active", background)],
            foreground=[("active", c["accent"]), ("disabled", c["text_disabled"])],
            **indicator_map,
        )

    # --- combobox -----------------------------------------------------------
    style.configure(
        "TCombobox",
        fieldbackground=c["bg_field"], background=c["bg_field"], foreground=c["text_primary"],
        arrowcolor=c["text_secondary"], bordercolor=c["border_subtle"], lightcolor=c["bg_field"],
        darkcolor=c["bg_field"], insertcolor=c["text_primary"], borderwidth=1, padding=(8, 8),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["bg_field"]), ("disabled", c["bg_app"])],
        foreground=[("readonly", c["text_primary"]), ("disabled", c["text_disabled"])],
        background=[("readonly", c["bg_field"]), ("active", c["bg_field"])],
        arrowcolor=[("active", c["accent"])],
        bordercolor=[("focus", c["border_focus"])],
        selectbackground=[("readonly", c["bg_field"])],
        selectforeground=[("readonly", c["text_primary"])],
    )
    # The dropdown list is a plain Tk Listbox that ttk does not reach, so it stays
    # white unless set through the option database.
    root.option_add("*TCombobox*Listbox.background", c["bg_surface_raised"])
    root.option_add("*TCombobox*Listbox.foreground", c["text_primary"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["accent_ink"])
    root.option_add("*TCombobox*Listbox.font", "{Segoe UI} 10")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    # Tk menus (the account menu, any context menu) are native-light by default.
    root.option_add("*Menu.background", c["bg_surface_raised"])
    root.option_add("*Menu.foreground", c["text_primary"])
    root.option_add("*Menu.activeBackground", c["bg_hover"])
    root.option_add("*Menu.activeForeground", c["text_primary"])
    root.option_add("*Menu.selectColor", c["accent"])
    root.option_add("*Menu.borderWidth", 0)
    root.option_add("*Menu.activeBorderWidth", 0)
    root.option_add("*Menu.font", "{Segoe UI} 10")

    # --- entry --------------------------------------------------------------
    style.configure(
        "TEntry",
        fieldbackground=c["bg_field"], foreground=c["text_primary"], insertcolor=c["text_primary"],
        bordercolor=c["border_subtle"], lightcolor=c["bg_field"], darkcolor=c["bg_field"],
        borderwidth=1, padding=(8, 8),
    )
    style.map("TEntry", bordercolor=[("focus", c["border_focus"])])

    # --- scrollbars ---------------------------------------------------------
    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background=c["bg_surface_raised"], troughcolor=c["bg_app"], bordercolor=c["bg_app"],
            arrowcolor=c["text_secondary"], lightcolor=c["bg_surface_raised"],
            darkcolor=c["bg_surface_raised"], borderwidth=0, arrowsize=12,
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", c["bg_hover"]), ("disabled", c["bg_app"])],
            arrowcolor=[("active", c["accent"])],
        )

    # --- misc ---------------------------------------------------------------
    style.configure("TSeparator", background=c["border_subtle"])
    style.configure("TProgressbar", background=c["accent"], troughcolor=c["bg_surface_raised"],
                    borderwidth=0, thickness=4)
    style.configure("Thin.TProgressbar", background=c["accent"], troughcolor=c["bg_surface_raised"],
                    borderwidth=0, thickness=4)


def bind_scroll(canvas: tk.Canvas, *widgets: tk.Misc) -> None:
    """Route the mouse wheel to `canvas` only while the pointer is over it.

    A bare ``bind_all`` would scroll whichever canvas registered last no matter which
    window the pointer is in.
    """
    def on_wheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def enable(_event=None):
        canvas.bind_all("<MouseWheel>", on_wheel)

    def disable(_event=None):
        canvas.unbind_all("<MouseWheel>")

    for widget in (canvas, *widgets):
        widget.bind("<Enter>", enable, add="+")
        widget.bind("<Leave>", disable, add="+")

    canvas.winfo_toplevel().bind("<Destroy>", lambda e: disable(), add="+")


def fit_canvas_width(canvas: tk.Canvas, window_id: int) -> None:
    """Keep a scrolled inner frame exactly as wide as its canvas.

    Without this the inner frame keeps its requested width, so content wider than the
    window is silently clipped -- there is no horizontal scrollbar to reach it.
    """
    canvas.bind(
        "<Configure>",
        lambda e: canvas.itemconfigure(window_id, width=e.width),
        add="+",
    )
