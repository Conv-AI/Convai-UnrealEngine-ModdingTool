"""The widgets the screens are built from.

Every control here carries the five states the design asks for -- normal, hover,
pressed, disabled and keyboard focus -- because plain Tk gives none of them on a dark
palette. Composite widgets (rows, tiles) are built from ``tk`` rather than ``ttk``
containers so their background can be swapped directly on hover and selection.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Iterable, Optional, Sequence

from gui.theme import FONTS, SPACE, theme

# tk.Button colours per kind: (background, foreground, hover background, border).
_BUTTON_KINDS: dict[str, tuple[str, str, str, str]] = {
    "primary": ("accent", "accent_ink", "accent_hover", "accent"),
    "secondary": ("bg_surface_raised", "text_primary", "bg_hover", "border_subtle"),
    "quiet": ("bg_app", "text_secondary", "bg_hover", "bg_app"),
    "danger": ("danger", "accent_ink", "danger", "danger"),
}

_PILL_TONES: dict[str, tuple[str, str, str]] = {
    "ok": ("ok_soft", "ok_soft_border", "ok_soft_text"),
    "warn": ("warn_soft", "warn_soft_border", "warn_soft_text"),
    "danger": ("danger_soft", "danger_soft_border", "danger_soft_text"),
    "neutral": ("bg_surface_raised", "border_subtle", "text_secondary"),
}


class Tooltip:
    """Hover/focus tooltip.

    Tk exposes no accessibility tree, so a control whose visible text does not name its
    subject ("Update project") carries the full name here instead.
    """

    def __init__(self, widget: tk.Misc, text: str):
        self.widget = widget
        self.text = text
        self.window: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<FocusIn>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<FocusOut>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _show(self, _event=None) -> None:
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 12
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self.window, text=self.text, background=theme["bg_surface_raised"],
            foreground=theme["text_primary"], font=FONTS["meta"], justify="left",
            highlightbackground=theme["border_subtle"], highlightthickness=1,
            padx=8, pady=4,
        ).pack()

    def _hide(self, _event=None) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


def button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    kind: str = "secondary",
    accessible_name: str = "",
    compact: bool = False,
    width: Optional[int] = None,
    anchor: str = "center",
) -> tk.Button:
    """A button in one of four kinds: primary, secondary, quiet or danger.

    `accessible_name` is the full name of what the button acts on, for when the visible
    label is generic ("Update project" -> "Update CityGuide").
    """
    background, foreground, hover, border = (theme[token] for token in _BUTTON_KINDS.get(kind, _BUTTON_KINDS["secondary"]))
    font = FONTS["meta"] if compact else (FONTS["body_strong"] if kind == "primary" else FONTS["body"])
    # Tk pads a button in text units, so height comes from pady around the font.
    pady = 6 if compact else 9

    widget = tk.Button(
        parent, text=text, command=command, font=font,
        background=background, foreground=foreground,
        activebackground=hover, activeforeground=foreground,
        disabledforeground=theme["text_disabled"],
        relief="flat", borderwidth=0, padx=14, pady=pady, cursor="hand2",
        anchor=anchor, justify="left" if anchor == "w" else "center",
        highlightthickness=2, highlightbackground=border,
        highlightcolor=theme["border_focus"], takefocus=True,
    )
    if width:
        widget.configure(width=width)

    def enter(_event=None):
        if str(widget["state"]) != "disabled":
            widget.configure(background=hover)

    def leave(_event=None):
        if str(widget["state"]) != "disabled":
            widget.configure(background=background)

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")
    # Space activates a focused Tk button; Return does not, and every screen has a
    # keyboard path that expects it to.
    widget.bind("<Return>", lambda event: widget.invoke(), add="+")

    # set_button_state has to restore these, and Tk keeps no memory of what a disabled
    # widget used to look like.
    widget._enabled_colours = (background, foreground, border)

    if accessible_name:
        Tooltip(widget, accessible_name)
    return widget


def set_button_state(widget: tk.Button, enabled: bool) -> None:
    """Enable or disable a button built by `button`, keeping its colours in step.

    Tk only dims the label, which leaves a disabled primary sitting on full accent green
    -- it still reads as the thing to press, and its text drops to 2.5:1 against that
    fill. A disabled control has to lose the fill as well as the click.
    """
    if enabled:
        background, foreground, border = getattr(
            widget, "_enabled_colours",
            (theme["bg_surface_raised"], theme["text_primary"], theme["border_subtle"]))
        widget.configure(state="normal", background=background, foreground=foreground,
                         highlightbackground=border)
        return

    widget.configure(state="disabled", background=theme["bg_surface_raised"],
                     highlightbackground=theme["border_subtle"])


def pill(parent: tk.Misc, text: str, tone: str = "ok", dot: bool = True) -> tk.Frame:
    """Status pill: a tinted surface with an optional coloured dot.

    Colour never carries the meaning on its own -- the text does, and the dot only
    reinforces it.
    """
    background, border, foreground = (theme[token] for token in _PILL_TONES.get(tone, _PILL_TONES["neutral"]))
    frame = tk.Frame(parent, background=background, highlightbackground=border,
                     highlightthickness=1, padx=8, pady=3)
    if dot:
        canvas = tk.Canvas(frame, width=7, height=7, background=background,
                           highlightthickness=0, borderwidth=0)
        canvas.create_oval(0, 0, 6, 6, fill=foreground, outline=foreground)
        canvas.pack(side="left", padx=(0, 6))
    tk.Label(frame, text=text, background=background, foreground=foreground,
             font=FONTS["meta"]).pack(side="left")
    return frame


def card(parent: tk.Misc, title: str = "", padding: int = SPACE["surface"]) -> tuple[tk.Frame, tk.Frame]:
    """Surface card. Content goes into the returned inner frame.

    The caller packs the outer frame: cards appear in grids as well as columns.
    """
    outer = tk.Frame(parent, background=theme["bg_surface"],
                     highlightbackground=theme["border_subtle"], highlightthickness=1)
    inner = tk.Frame(outer, background=theme["bg_surface"])
    inner.pack(fill="both", expand=True, padx=padding, pady=padding)
    if title:
        tk.Label(inner, text=title, background=theme["bg_surface"],
                 foreground=theme["text_secondary"], font=FONTS["meta_strong"]).pack(anchor="w", pady=(0, SPACE["tight"]))
    return outer, inner


def banner(parent: tk.Misc, text: str, tone: str = "warn",
           action: tuple[str, Callable[[], None]] | None = None) -> tk.Frame:
    """Inline banner with an optional trailing action, e.g. the signed-out notice."""
    background, border, foreground = (theme[token] for token in _PILL_TONES.get(tone, _PILL_TONES["warn"]))
    frame = tk.Frame(parent, background=background, highlightbackground=border,
                     highlightthickness=1, padx=14, pady=10)
    tk.Label(frame, text=text, background=background, foreground=foreground,
             font=FONTS["body"], justify="left", anchor="w").pack(side="left")
    if action:
        label, command = action
        link = tk.Button(frame, text=label, command=command, font=FONTS["body_strong"],
                         background=background, foreground=foreground,
                         activebackground=background, activeforeground=theme["text_primary"],
                         relief="flat", borderwidth=0, cursor="hand2", padx=8, pady=2,
                         highlightthickness=2, highlightbackground=background,
                         highlightcolor=theme["border_focus"], takefocus=True)
        link.bind("<Return>", lambda event: link.invoke(), add="+")
        link.pack(side="right")
    return frame


class Field:
    """Labelled text input with help text and a reserved error line.

    The error line is always present and only its text changes: a message that appears
    from nothing shifts every control below it down as the user types.
    """

    def __init__(self, parent: tk.Misc, label: str, variable: tk.StringVar,
                 help_text: str = "", show: Optional[str] = None,
                 surface: str = "bg_app", width: Optional[int] = None):
        background = theme[surface]
        self.variable = variable
        self.frame = tk.Frame(parent, background=background)
        self.help_text = help_text

        tk.Label(self.frame, text=label, background=background, foreground=theme["text_primary"],
                 font=FONTS["field_title"]).pack(anchor="w")

        box = tk.Frame(self.frame, background=theme["bg_field"],
                       highlightbackground=theme["border_subtle"], highlightthickness=1,
                       highlightcolor=theme["border_focus"])
        box.pack(fill="x", pady=(6, 0))
        self.entry = tk.Entry(
            box, textvariable=variable, font=FONTS["body"], background=theme["bg_field"],
            foreground=theme["text_primary"], insertbackground=theme["text_primary"],
            disabledbackground=theme["bg_surface"], disabledforeground=theme["text_disabled"],
            relief="flat", highlightthickness=0, show=show or "",
        )
        if width:
            self.entry.configure(width=width)
        self.entry.pack(fill="x", padx=10, pady=10)

        self.message = tk.Label(self.frame, text=help_text, background=background,
                                foreground=theme["text_secondary"], font=FONTS["meta"],
                                justify="left", anchor="w", wraplength=560)
        self.message.pack(fill="x", pady=(4, 0))

    def pack(self, **kwargs) -> "Field":
        self.frame.pack(**kwargs)
        return self

    def set_error(self, message: Optional[str]) -> None:
        """Show an error under the field, or restore the help text when cleared."""
        if message:
            self.message.configure(text=message, foreground=theme["danger"])
        else:
            self.message.configure(text=self.help_text, foreground=theme["text_secondary"])

    def focus(self) -> None:
        self.entry.focus_set()

    def set_enabled(self, enabled: bool) -> None:
        self.entry.configure(state="normal" if enabled else "disabled")


class ChoiceTile:
    """A large selectable tile, used for the Scene / Avatar choice.

    A tile is a composite, so every child forwards its click; without that, clicking the
    description text does nothing.
    """

    def __init__(self, parent: tk.Misc, title: str, description: str, value: str,
                 variable: tk.StringVar, on_select: Optional[Callable[[str], None]] = None):
        self.value = value
        self.variable = variable
        self.on_select = on_select

        self.frame = tk.Frame(parent, background=theme["bg_field"], highlightthickness=2,
                              highlightbackground=theme["border_subtle"],
                              highlightcolor=theme["border_focus"], cursor="hand2",
                              takefocus=True, padx=16, pady=16)
        self.title = tk.Label(self.frame, text=title, background=theme["bg_field"],
                              foreground=theme["text_primary"], font=FONTS["section_title"],
                              anchor="w", justify="left")
        self.title.pack(anchor="w")
        self.description = tk.Label(self.frame, text=description, background=theme["bg_field"],
                                    foreground=theme["text_secondary"], font=FONTS["meta"],
                                    anchor="w", justify="left", wraplength=240)
        self.description.pack(anchor="w", pady=(8, 0))

        for widget in (self.frame, self.title, self.description):
            widget.bind("<Button-1>", lambda event: self.select(), add="+")
        self.frame.bind("<Return>", lambda event: self.select(), add="+")
        self.frame.bind("<space>", lambda event: self.select(), add="+")
        variable.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def select(self) -> None:
        self.variable.set(self.value)
        self.frame.focus_set()
        if self.on_select:
            self.on_select(self.value)

    def refresh(self) -> None:
        selected = self.variable.get() == self.value
        background = theme["bg_hover"] if selected else theme["bg_field"]
        border = theme["accent"] if selected else theme["border_subtle"]
        self.frame.configure(background=background, highlightbackground=border)
        for widget in (self.title, self.description):
            widget.configure(background=background)


class StepIndicator:
    """`1 Details -- 2 Project type -- 3 Unreal Engine`.

    Informative only: the steps are not clickable, because a later step's validity
    depends on the earlier ones.
    """

    def __init__(self, parent: tk.Misc, steps: Sequence[str], surface: str = "bg_app"):
        self.background = theme[surface]
        self.frame = tk.Frame(parent, background=self.background)
        self.numbers: list[tk.Label] = []
        self.labels: list[tk.Label] = []

        for index, title in enumerate(steps):
            if index:
                line = tk.Frame(self.frame, background=theme["border_subtle"], height=1, width=28)
                line.pack(side="left", padx=10)
            number = tk.Label(self.frame, text=str(index + 1), background=self.background,
                              foreground=theme["text_secondary"], font=FONTS["meta_strong"],
                              width=3, pady=2)
            number.pack(side="left")
            label = tk.Label(self.frame, text=title, background=self.background,
                             foreground=theme["text_secondary"], font=FONTS["meta"])
            label.pack(side="left", padx=(4, 0))
            self.numbers.append(number)
            self.labels.append(label)

    def set_current(self, index: int) -> None:
        for position, (number, label) in enumerate(zip(self.numbers, self.labels)):
            active = position == index
            done = position < index
            number.configure(
                background=theme["accent"] if active else self.background,
                foreground=theme["accent_ink"] if active else (
                    theme["accent"] if done else theme["text_secondary"]),
            )
            label.configure(
                foreground=theme["text_primary"] if active else theme["text_secondary"],
                font=FONTS["meta_strong"] if active else FONTS["meta"],
            )


class StepList:
    """The run screen's lifecycle steps: done, current, pending.

    The glyphs are ASCII-safe: a Windows console font renders a tick, but the Tk label
    falls back to a box for anything outside the installed font.
    """

    STATES = {
        "done": ("✓", "accent"),
        "active": ("●", "text_primary"),
        "pending": ("○", "text_disabled"),
    }

    def __init__(self, parent: tk.Misc, surface: str = "bg_app"):
        self.background = theme[surface]
        self.frame = tk.Frame(parent, background=self.background)
        self.rows: dict[str, tuple[tk.Label, tk.Label]] = {}

    def set_steps(self, titles: Iterable[str]) -> None:
        for child in self.frame.winfo_children():
            child.destroy()
        self.rows = {}
        for title in titles:
            row = tk.Frame(self.frame, background=self.background)
            row.pack(fill="x", pady=2)
            glyph = tk.Label(row, text=self.STATES["pending"][0], background=self.background,
                             foreground=theme["text_disabled"], font=FONTS["body"], width=2)
            glyph.pack(side="left")
            label = tk.Label(row, text=title, background=self.background,
                             foreground=theme["text_disabled"], font=FONTS["body"],
                             anchor="w", justify="left")
            label.pack(side="left")
            self.rows[title] = (glyph, label)

    def set_state(self, title: str, state: str) -> None:
        if title not in self.rows:
            return
        glyph_text, colour = self.STATES.get(state, self.STATES["pending"])
        glyph, label = self.rows[title]
        glyph.configure(text=glyph_text, foreground=theme[colour])
        label.configure(foreground=theme[colour if state != "done" else "text_secondary"])


class Disclosure:
    """A `Show technical log` toggle over a widget the caller supplies."""

    def __init__(self, parent: tk.Misc, shown_text: str, hidden_text: str,
                 target: tk.Misc, expanded: bool = False,
                 pack_options: Optional[dict] = None):
        self.target = target
        self.shown_text = shown_text
        self.hidden_text = hidden_text
        self.expanded = expanded
        self.pack_options = pack_options or {"fill": "both", "expand": True}
        self.button = button(parent, shown_text if expanded else hidden_text, self.toggle, kind="quiet", compact=True)
        self.apply()

    def toggle(self) -> None:
        self.expanded = not self.expanded
        self.apply()

    def apply(self) -> None:
        self.button.configure(text=self.shown_text if self.expanded else self.hidden_text)
        if self.expanded:
            self.target.pack(**self.pack_options)
        else:
            self.target.pack_forget()


class ProjectRow:
    """One 72 px clickable project row: name, type and engine, and one state.

    Selection is drawn with a raised surface *and* a green left rail, so it survives a
    colour-blind read; the focus ring is separate from selection.
    """

    def __init__(self, parent: tk.Misc, project: dict, on_select: Callable[[dict], None],
                 on_activate: Optional[Callable[[dict], None]] = None):
        self.project = project
        self.on_select = on_select
        self.on_activate = on_activate
        self.selected = False

        self.frame = tk.Frame(parent, background=theme["bg_surface"], height=SPACE["row"],
                              highlightthickness=2, highlightbackground=theme["bg_surface"],
                              highlightcolor=theme["border_focus"], takefocus=True, cursor="hand2")
        self.frame.pack_propagate(False)

        self.rail = tk.Frame(self.frame, background=theme["bg_surface"], width=3)
        self.rail.pack(side="left", fill="y")

        body = tk.Frame(self.frame, background=theme["bg_surface"])
        body.pack(side="left", fill="both", expand=True, padx=12, pady=10)

        top = tk.Frame(body, background=theme["bg_surface"])
        top.pack(fill="x", anchor="w")
        self.name = tk.Label(top, text=project["name"], background=theme["bg_surface"],
                             foreground=theme["text_primary"], font=FONTS["field_title"], anchor="w")
        self.name.pack(side="left")
        self.kind = None
        if project.get("type"):
            self.kind = pill(top, project["type"], tone="neutral", dot=False)
            self.kind.pack(side="left", padx=(8, 0))

        self.meta = tk.Label(body, text=project.get("meta", ""), background=theme["bg_surface"],
                             foreground=theme["text_secondary"], font=FONTS["meta"], anchor="w")
        self.meta.pack(fill="x", anchor="w", pady=(4, 0))

        self.state = tk.Label(self.frame, text=project.get("state", ""), background=theme["bg_surface"],
                              foreground=theme[project.get("state_colour", "text_secondary")],
                              font=FONTS["meta"], anchor="e")
        self.state.pack(side="right", padx=12)

        for widget in (self.frame, body, top, self.name, self.meta, self.state):
            widget.bind("<Button-1>", self._click, add="+")
            widget.bind("<Double-Button-1>", self._activate, add="+")
        self.frame.bind("<Return>", self._activate, add="+")
        self.frame.bind("<Enter>", lambda event: self._paint(hover=True), add="+")
        self.frame.bind("<Leave>", lambda event: self._paint(), add="+")

    def _click(self, _event=None) -> None:
        self.frame.focus_set()
        self.on_select(self.project)

    def _activate(self, _event=None) -> None:
        if self.on_activate:
            self.on_activate(self.project)

    def set_selected(self, selected: bool) -> None:
        self.selected = selected
        self._paint()

    def _paint(self, hover: bool = False) -> None:
        if self.selected:
            background = theme["bg_surface_raised"]
        elif hover:
            background = theme["bg_hover"]
        else:
            background = theme["bg_surface"]
        self.frame.configure(background=background, highlightbackground=background)
        self.rail.configure(background=theme["accent"] if self.selected else background)
        for widget in self.frame.winfo_children():
            if widget is self.rail:
                continue
            self._paint_tree(widget, background)

    def _paint_tree(self, widget: tk.Misc, background: str) -> None:
        # The type pill keeps its own tint; everything else follows the row.
        if self.kind is not None and (widget is self.kind or str(widget).startswith(str(self.kind))):
            return
        try:
            widget.configure(background=background)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            self._paint_tree(child, background)


def scroll_host(parent: tk.Misc, surface: str = "bg_app") -> tuple[tk.Canvas, tk.Frame]:
    """A vertically scrolling area. Content goes in the returned inner frame.

    Returns (canvas, inner); the caller packs the canvas. Horizontal scrolling is
    deliberately absent -- content wraps or ellipsises instead.
    """
    from gui.theme import bind_scroll, fit_canvas_width

    background = theme[surface]
    container = tk.Frame(parent, background=background)
    canvas = tk.Canvas(container, background=background, highlightthickness=0, borderwidth=0)
    scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview,
                              style="Vertical.TScrollbar")
    canvas.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    inner = tk.Frame(canvas, background=background)
    window = canvas.create_window((0, 0), window=inner, anchor="nw")
    inner.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")), add="+")
    fit_canvas_width(canvas, window)
    bind_scroll(canvas, inner)

    canvas.container = container  # the caller packs this, not the canvas itself
    return canvas, inner


def ellipsise(text: str, limit: int = 64, keep: str = "tail") -> str:
    """Shorten text to `limit` characters.

    A path keeps its tail -- that is where the project name is -- while an address keeps
    its head, because the local part identifies the account and the domain rarely does.
    """
    if len(text) <= limit:
        return text
    if keep == "head":
        return text[:limit - 1] + "…"
    return "…" + text[-(limit - 1):]
