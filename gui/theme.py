"""Green/black palette, ttk styles and the widget factory for the GUI."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable


class Theme:
    """Singleton colour palette.

    Usage:
        from gui.theme import theme
        background = theme["bg_dark"]
    """

    _instance: Theme | None = None

    def __new__(cls) -> Theme:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_colors()
        return cls._instance

    def _init_colors(self) -> None:
        self.colors: dict[str, str] = {
            # Backgrounds
            "bg_dark": "#0A0F0C",
            "bg_card": "#111814",
            "bg_input": "#18211C",
            "bg_toolbar": "#050806",

            # Borders
            "border": "#243029",

            # Text
            "text": "#E4EDE7",
            "text_muted": "#8FA396",

            # Accent colors
            "accent": "#2FD07A",
            "accent_hover": "#4FE494",
            # A bright green is a light colour: text drawn ON the accent has to
            # be dark. White on #2FD07A is 2.0:1 and unreadable.
            "on_accent": "#04140B",

            # Status colors
            "success": "#2FD07A",
            "warning": "#E8B339",
            "error": "#FF6B5E",
        }

    def __getitem__(self, key: str) -> str:
        return self.colors[key]


theme = Theme()


def apply_styles(root: tk.Misc) -> None:
    """Configure every ttk style the app uses.

    Called once on the root window; ttk styles are process-wide, so all
    Toplevels inherit them. Anything not styled here falls back to the 'clam'
    defaults, which are light and look broken against the dark palette --
    Combobox, Treeview and Scrollbar especially.
    """
    c = theme.colors
    style = ttk.Style(root)
    style.theme_use("clam")

    # --- containers ---------------------------------------------------------
    style.configure("TFrame", background=c["bg_dark"])
    style.configure("Card.TFrame", background=c["bg_card"])
    style.configure("Toolbar.TFrame", background=c["bg_toolbar"])

    # --- labels -------------------------------------------------------------
    style.configure("TLabel", background=c["bg_dark"], foreground=c["text"], font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=c["bg_card"], foreground=c["text"], font=("Segoe UI", 10))
    style.configure("Toolbar.TLabel", background=c["bg_toolbar"], foreground=c["text_muted"], font=("Segoe UI", 9))
    style.configure("Header.TLabel", background=c["bg_card"], foreground=c["accent"], font=("Segoe UI Semibold", 11))
    style.configure("Title.TLabel", background=c["bg_toolbar"], foreground=c["text"], font=("Segoe UI Semibold", 12))
    style.configure("Muted.TLabel", background=c["bg_card"], foreground=c["text_muted"], font=("Segoe UI", 9))
    style.configure("Status.TLabel", background=c["bg_toolbar"], foreground=c["text_muted"], font=("Segoe UI", 9))
    style.configure("StatusActive.TLabel", background=c["bg_toolbar"], foreground=c["accent"], font=("Segoe UI", 9))
    style.configure("Step.TLabel", background=c["bg_dark"], foreground=c["text_muted"], font=("Segoe UI Semibold", 9))
    style.configure("SectionTitle.TLabel", background=c["bg_dark"], foreground=c["text"], font=("Segoe UI Semibold", 11))

    # --- radio / check ------------------------------------------------------
    style.configure("TRadiobutton", background=c["bg_card"], foreground=c["text"], font=("Segoe UI", 10))
    style.map("TRadiobutton", background=[("active", c["bg_card"])], foreground=[("active", c["accent"])])

    # clam draws an unstyled indicator that renders as a crossed box on a dark
    # background -- a ticked option reads as switched off. Colour it explicitly.
    indicator = dict(
        indicatorbackground=c["bg_input"],
        indicatorforeground=c["accent"],
        indicatormargin=(0, 0, 8, 0),
        indicatorrelief="flat",
        focuscolor="",
    )
    indicator_map = dict(
        indicatorbackground=[
            ("selected", c["accent"]),
            ("active", c["border"]),
            ("disabled", c["bg_dark"]),
        ],
        indicatorforeground=[("selected", c["on_accent"]), ("disabled", c["text_muted"])],
    )

    style.configure("TCheckbutton", background=c["bg_card"], foreground=c["text"], font=("Segoe UI", 10), **indicator)
    style.map(
        "TCheckbutton",
        background=[("active", c["bg_card"])],
        foreground=[("active", c["accent"]), ("disabled", c["text_muted"])],
        **indicator_map,
    )

    # --- buttons ------------------------------------------------------------
    style.configure("Toolbar.TButton", background=c["bg_input"], foreground=c["text"], font=("Segoe UI", 9), padding=(12, 6))
    style.map("Toolbar.TButton", background=[("active", c["border"]), ("disabled", c["bg_dark"])])

    style.configure("Accent.TButton", background=c["accent"], foreground=c["on_accent"], font=("Segoe UI Semibold", 10), padding=(16, 8))
    style.map("Accent.TButton", background=[("active", c["accent_hover"]), ("disabled", c["border"])])

    # Segmented control: ttk renders a Radiobutton as a toggle button under the
    # Toolbutton style, which beats hand-drawing one on a canvas.
    style.configure(
        "Segment.Toolbutton",
        background=c["bg_input"], foreground=c["text_muted"],
        font=("Segoe UI", 10), padding=(14, 7), borderwidth=0, relief="flat",
        focuscolor=c["bg_input"],
    )
    style.map(
        "Segment.Toolbutton",
        background=[("selected", c["accent"]), ("active", c["border"])],
        foreground=[("selected", c["on_accent"]), ("active", c["text"])],
    )

    # Toolbar on/off pill. A plain Checkbutton would do, but clam draws its
    # indicator as a cross, so a ticked step reads as switched off.
    # An unselected pill keeps a filled background: on the toolbar's near-black
    # it would otherwise read as a plain label rather than something clickable.
    style.configure(
        "Step.Toolbutton",
        background=c["bg_input"], foreground=c["text_muted"],
        font=("Segoe UI", 9), padding=(12, 6), borderwidth=1, relief="flat",
        focuscolor=c["bg_input"], bordercolor=c["border"],
        lightcolor=c["bg_input"], darkcolor=c["bg_input"],
    )
    style.map(
        "Step.Toolbutton",
        background=[("selected", c["accent"]), ("active", c["border"]), ("disabled", c["bg_toolbar"])],
        foreground=[("selected", c["on_accent"]), ("active", c["text"]), ("disabled", c["border"])],
        bordercolor=[("selected", c["accent"]), ("disabled", c["bg_toolbar"])],
        lightcolor=[("selected", c["accent"])],
        darkcolor=[("selected", c["accent"])],
    )

    # --- combobox -----------------------------------------------------------
    style.configure(
        "TCombobox",
        fieldbackground=c["bg_input"], background=c["bg_input"], foreground=c["text"],
        arrowcolor=c["text_muted"], bordercolor=c["border"], lightcolor=c["bg_input"],
        darkcolor=c["bg_input"], insertcolor=c["text"], borderwidth=1, padding=(8, 6),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", c["bg_input"]), ("disabled", c["bg_dark"])],
        foreground=[("readonly", c["text"]), ("disabled", c["text_muted"])],
        background=[("readonly", c["bg_input"]), ("active", c["bg_input"])],
        arrowcolor=[("active", c["accent"])],
        bordercolor=[("focus", c["accent"])],
        selectbackground=[("readonly", c["bg_input"])],
        selectforeground=[("readonly", c["text"])],
    )
    # The dropdown list is a plain Tk Listbox that ttk does not reach, so it
    # stays white unless set through the option database.
    root.option_add("*TCombobox*Listbox.background", c["bg_input"])
    root.option_add("*TCombobox*Listbox.foreground", c["text"])
    root.option_add("*TCombobox*Listbox.selectBackground", c["accent"])
    root.option_add("*TCombobox*Listbox.selectForeground", c["on_accent"])
    root.option_add("*TCombobox*Listbox.font", "{Segoe UI} 10")
    root.option_add("*TCombobox*Listbox.borderWidth", 0)

    # --- menubutton used as a multi-select field ----------------------------
    # Styled to read as a Combobox, since that is what it stands in for.
    style.configure(
        "Field.TMenubutton",
        background=c["bg_input"], foreground=c["text"],
        bordercolor=c["border"], lightcolor=c["bg_input"], darkcolor=c["bg_input"],
        arrowcolor=c["text_muted"], font=("Segoe UI", 10),
        padding=(8, 6), borderwidth=1, relief="flat", anchor="w",
    )
    style.map(
        "Field.TMenubutton",
        background=[("active", c["bg_input"]), ("disabled", c["bg_dark"])],
        foreground=[("disabled", c["text_muted"])],
        arrowcolor=[("active", c["accent"])],
        bordercolor=[("focus", c["accent"])],
    )

    # --- entry --------------------------------------------------------------
    style.configure(
        "TEntry",
        fieldbackground=c["bg_input"], foreground=c["text"], insertcolor=c["text"],
        bordercolor=c["border"], lightcolor=c["bg_input"], darkcolor=c["bg_input"],
        borderwidth=1, padding=(8, 6),
    )
    style.map("TEntry", bordercolor=[("focus", c["accent"])])

    # --- treeview -----------------------------------------------------------
    style.configure(
        "Custom.Treeview",
        background=c["bg_input"], foreground=c["text"], fieldbackground=c["bg_input"],
        borderwidth=0, relief="flat", font=("Segoe UI", 10), rowheight=26,
    )
    style.configure(
        "Custom.Treeview.Heading",
        background=c["bg_card"], foreground=c["text_muted"],
        font=("Segoe UI Semibold", 9), relief="flat", borderwidth=0, padding=(8, 6),
    )
    style.map(
        "Custom.Treeview",
        background=[("selected", c["accent"])],
        foreground=[("selected", c["on_accent"])],
    )
    style.map(
        "Custom.Treeview.Heading",
        background=[("active", c["border"])],
        foreground=[("active", c["text"])],
    )
    # clam draws a raised border around the whole widget by default.
    style.layout("Custom.Treeview", [("Custom.Treeview.treearea", {"sticky": "nswe"})])

    # --- scrollbars ---------------------------------------------------------
    for orient in ("Vertical", "Horizontal"):
        style.configure(
            f"{orient}.TScrollbar",
            background=c["bg_input"], troughcolor=c["bg_dark"], bordercolor=c["bg_dark"],
            arrowcolor=c["text_muted"], lightcolor=c["bg_input"], darkcolor=c["bg_input"],
            borderwidth=0, arrowsize=12,
        )
        style.map(
            f"{orient}.TScrollbar",
            background=[("active", c["border"]), ("disabled", c["bg_dark"])],
            arrowcolor=[("active", c["accent"])],
        )

    # --- misc ---------------------------------------------------------------
    style.configure("TSeparator", background=c["border"])
    style.configure("TProgressbar", background=c["accent"], troughcolor=c["bg_input"], borderwidth=0, thickness=3)
    style.configure("TPanedwindow", background=c["bg_dark"])


def bind_scroll(canvas: tk.Canvas, *widgets: tk.Misc) -> None:
    """Route the mouse wheel to `canvas` only while the pointer is over it.

    A bare ``bind_all`` would scroll whichever canvas registered last no matter
    which window the pointer is in.
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

    Without this the inner frame keeps its requested width, so content wider
    than the window is silently clipped -- there is no horizontal scrollbar to
    reach it.
    """
    canvas.bind(
        "<Configure>",
        lambda e: canvas.itemconfigure(window_id, width=e.width),
        add="+",
    )


class WidgetFactory:
    """Builds the styled widgets the screens are made of.

    Usage:
        from gui.theme import widgets
        card, inner = widgets.create_card(parent, "Your projects")
    """

    def create_card(self, parent: tk.Misc, title: str | None = None) -> tuple[ttk.Frame, ttk.Frame]:
        """Card container; add content to the returned inner frame."""
        card = ttk.Frame(parent, style="Card.TFrame")
        card.pack(fill="x", pady=(0, 12))

        inner = ttk.Frame(card, style="Card.TFrame")
        inner.pack(fill="x", padx=14, pady=12)

        if title:
            ttk.Label(inner, text=title, style="Header.TLabel").pack(anchor="w", pady=(0, 8))

        return card, inner

    def create_button(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        style: str = "default",
        width: int | None = None,
    ) -> tk.Button:
        """Button in one of three flavours: "default", "accent" or "danger"."""
        styles = {
            "default": {
                "bg": theme["bg_input"],
                "fg": theme["text"],
                "activebackground": theme["border"],
                "activeforeground": theme["text"],
            },
            "accent": {
                "bg": theme["accent"],
                "fg": theme["on_accent"],
                "activebackground": theme["accent_hover"],
                "activeforeground": theme["on_accent"],
            },
            "danger": {
                "bg": theme["error"],
                "fg": theme["on_accent"],
                "activebackground": theme["error"],
                "activeforeground": theme["on_accent"],
            },
        }

        btn = tk.Button(
            parent,
            text=text,
            font=("Segoe UI", 9),
            relief="flat",
            padx=12,
            pady=6,
            command=command,
            **styles.get(style, styles["default"]),
        )

        if width:
            btn.configure(width=width)

        return btn

    def create_text_field(
        self,
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        hint: str = "",
        show: str | None = None,
    ) -> tk.Entry:
        """Labelled text input. `show` masks the entry, e.g. the API key."""
        frame = ttk.Frame(parent, style="TFrame")
        frame.pack(fill="x", pady=(0, 12))

        ttk.Label(
            frame,
            text=label,
            font=("Segoe UI Semibold", 10),
            background=theme["bg_dark"],
            foreground=theme["text"],
        ).pack(anchor="w")

        if hint:
            ttk.Label(
                frame,
                text=hint,
                font=("Segoe UI", 9),
                background=theme["bg_dark"],
                foreground=theme["text_muted"],
            ).pack(anchor="w")

        entry_frame = tk.Frame(
            frame,
            bg=theme["bg_input"],
            highlightbackground=theme["border"],
            highlightthickness=1,
            highlightcolor=theme["accent"],
        )
        entry_frame.pack(fill="x", pady=(4, 0))

        entry = tk.Entry(
            entry_frame,
            textvariable=variable,
            font=("Consolas", 10),
            bg=theme["bg_input"],
            fg=theme["text"],
            insertbackground=theme["text"],
            relief="flat",
            show=show or "",
        )
        entry.pack(fill="x", padx=8, pady=8)

        return entry

    def create_segmented(
        self,
        parent: tk.Misc,
        label: str,
        options: list[tuple[str, str]],
        variable: tk.StringVar,
        hint: str = "",
    ) -> ttk.Frame:
        """Labelled row of mutually exclusive buttons.

        Replaces a card of radio buttons for a two- or three-way choice: same
        information, a fraction of the vertical space.
        """
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=(0, 8))

        ttk.Label(row, text=label, style="Card.TLabel", width=12).pack(side="left")

        group = tk.Frame(row, bg=theme["border"])
        group.pack(side="left")

        for text, value in options:
            ttk.Radiobutton(
                group,
                text=text,
                variable=variable,
                value=value,
                style="Segment.Toolbutton",
            ).pack(side="left", padx=1, pady=1)

        if hint:
            ttk.Label(row, text=hint, style="Muted.TLabel").pack(side="left", padx=(10, 0))

        return row

    def create_dropdown(
        self,
        parent: tk.Misc,
        label: str,
        variable: tk.StringVar,
        options: list[str],
        hint: str = "",
    ) -> ttk.Combobox:
        """Labelled read-only dropdown field."""
        frame = ttk.Frame(parent, style="TFrame")
        frame.pack(fill="x", pady=(0, 12))

        ttk.Label(
            frame,
            text=label,
            font=("Segoe UI Semibold", 10),
            background=theme["bg_dark"],
            foreground=theme["text"],
        ).pack(anchor="w")

        if hint:
            ttk.Label(
                frame,
                text=hint,
                font=("Segoe UI", 9),
                background=theme["bg_dark"],
                foreground=theme["text_muted"],
            ).pack(anchor="w")

        combo = ttk.Combobox(
            frame,
            textvariable=variable,
            values=options,
            state="readonly",
            font=("Segoe UI", 10),
        )
        combo.pack(fill="x", pady=(4, 0))

        return combo


widgets = WidgetFactory()
