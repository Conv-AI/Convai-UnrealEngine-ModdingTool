"""The window chrome: app bar, scrolling page host and status bar.

The chrome is built once and outlives every screen, so the user always knows where
they are, whether the engine is ready and who they are signed in as. Screens only ever
fill ``Shell.page``.
"""

from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from gui.components import Tooltip, button, pill, scroll_host
from gui.theme import FONTS, NARROW_WIDTH, SPACE, theme


class Shell:
    """Window chrome around a single swappable page."""

    def __init__(self, root: tk.Misc, tool_version: str, on_home: Callable[[], None],
                 on_settings: Callable[[], None], on_account: Callable[[], None],
                 on_engine: Optional[Callable[[], None]] = None):
        self.root = root
        self.on_home = on_home
        self.navigation_enabled = True

        self.container = tk.Frame(root, background=theme["bg_app"])
        self.container.pack(fill="both", expand=True)

        # --- app bar --------------------------------------------------------
        self.bar = tk.Frame(self.container, background=theme["bg_surface"], height=SPACE["app_bar"])
        self.bar.pack(fill="x")
        self.bar.pack_propagate(False)
        tk.Frame(self.container, background=theme["border_subtle"], height=1).pack(fill="x")

        left = tk.Frame(self.bar, background=theme["bg_surface"])
        left.pack(side="left", fill="y", padx=(SPACE["gutter_narrow"], 0))

        self.mark = tk.Canvas(left, width=22, height=22, background=theme["bg_surface"],
                              highlightthickness=0, borderwidth=0)
        self.mark.create_rectangle(0, 0, 22, 22, fill=theme["accent"], outline=theme["accent"])
        self.mark.create_rectangle(5, 5, 17, 17, fill=theme["bg_surface"], outline=theme["bg_surface"])
        self.mark.pack(side="left", pady=SPACE["surface"])

        self.wordmark = tk.Button(
            left, text="Convai Modding Tool", command=self._home, font=("Segoe UI Semibold", 11),
            background=theme["bg_surface"], foreground=theme["text_primary"],
            activebackground=theme["bg_surface"], activeforeground=theme["accent"],
            disabledforeground=theme["text_disabled"], relief="flat", borderwidth=0,
            cursor="hand2", padx=10, highlightthickness=2,
            highlightbackground=theme["bg_surface"], highlightcolor=theme["border_focus"],
            takefocus=True,
        )
        self.wordmark.bind("<Return>", lambda event: self.wordmark.invoke(), add="+")
        self.wordmark.pack(side="left")

        self.breadcrumb = tk.Label(left, text="/ Projects", background=theme["bg_surface"],
                                   foreground=theme["text_secondary"], font=FONTS["body"])
        self.breadcrumb.pack(side="left")

        right = tk.Frame(self.bar, background=theme["bg_surface"])
        right.pack(side="right", fill="y", padx=(0, SPACE["gutter_narrow"]))

        self.settings_btn = button(right, "Settings", on_settings, kind="quiet", compact=True)
        self.settings_btn.configure(background=theme["bg_surface"], highlightbackground=theme["bg_surface"])
        self.settings_btn.pack(side="right", pady=14)

        self.account_btn = tk.Button(
            right, text="Sign in", command=on_account, font=FONTS["meta"],
            background=theme["bg_surface"], foreground=theme["text_secondary"],
            activebackground=theme["bg_hover"], activeforeground=theme["text_primary"],
            disabledforeground=theme["text_disabled"], relief="flat", borderwidth=0,
            cursor="hand2", padx=10, pady=6, compound="left",
            highlightthickness=2, highlightbackground=theme["bg_surface"],
            highlightcolor=theme["border_focus"], takefocus=True,
        )
        self.account_btn.bind("<Return>", lambda event: self.account_btn.invoke(), add="+")
        self.account_btn.pack(side="right", padx=(0, 8), pady=14)

        self.engine_chip = tk.Frame(right, background=theme["bg_surface"])
        self.engine_chip.pack(side="right", padx=(0, 12))
        self._engine_pill: Optional[tk.Frame] = None
        self._on_engine = on_engine or on_settings
        self.set_engine("", ok=False)

        # --- page host ------------------------------------------------------
        self.canvas, self.page = scroll_host(self.container)
        self.canvas.container.pack(fill="both", expand=True)

        # --- status bar -----------------------------------------------------
        tk.Frame(self.container, background=theme["border_subtle"], height=1).pack(fill="x", side="bottom")
        self.status = tk.Frame(self.container, background=theme["bg_surface"], height=SPACE["status_bar"])
        self.status.pack(fill="x", side="bottom")
        self.status.pack_propagate(False)
        self.status_left = tk.Label(self.status, text=f"v{tool_version}", background=theme["bg_surface"],
                                    foreground=theme["text_secondary"], font=FONTS["meta"])
        self.status_left.pack(side="left", padx=SPACE["gutter_narrow"])
        self.status_right = tk.Label(self.status, text="", background=theme["bg_surface"],
                                     foreground=theme["text_secondary"], font=FONTS["meta"])
        self.status_right.pack(side="right", padx=SPACE["gutter_narrow"])

        self.root.bind("<Configure>", self._on_resize, add="+")

    # --- page -------------------------------------------------------------

    def clear_page(self) -> tk.Frame:
        """Empty the page host and return a fresh gutter-padded frame to build into."""
        for child in self.page.winfo_children():
            child.destroy()
        gutter = SPACE["gutter"] if self.root.winfo_width() >= NARROW_WIDTH else SPACE["gutter_narrow"]
        frame = tk.Frame(self.page, background=theme["bg_app"])
        frame.pack(fill="both", expand=True, padx=gutter, pady=SPACE["section"])
        self.canvas.yview_moveto(0)
        return frame

    # --- chrome state -----------------------------------------------------

    def set_breadcrumb(self, text: str) -> None:
        self.breadcrumb.configure(text=f"/ {text}" if text else "")

    def set_engine(self, version: str, ok: bool) -> None:
        """The engine chip: `UE 5.4 ready`, or the same version needing attention."""
        if self._engine_pill is not None:
            self._engine_pill.destroy()
        text = f"UE {version} ready" if ok else (
            f"UE {version} needs attention" if version else "Engine not configured")
        self._engine_pill = pill(self.engine_chip, text, tone="ok" if ok else "warn")
        self._engine_pill.pack()
        self._engine_pill.configure(cursor="hand2")
        for widget in (self._engine_pill, *self._engine_pill.winfo_children()):
            widget.bind("<Button-1>", lambda event: self._on_engine(), add="+")
        Tooltip(self._engine_pill, "Open Settings to change the Unreal Engine installation")

    def set_account(self, name: Optional[str], email: str = "") -> None:
        """Signed out shows `Sign in`; signed in shows an initial and the first name."""
        if name:
            initial = name.strip()[:1].upper() or "?"
            self.account_btn.configure(text=f"  {initial}   {name.split()[0]}",
                                       foreground=theme["text_primary"])
            Tooltip(self.account_btn, f"{name}\n{email}" if email else name)
        else:
            self.account_btn.configure(text="  ?   Sign in", foreground=theme["text_secondary"])
            Tooltip(self.account_btn, "Sign in to Convai")

    def set_status(self, left: Optional[str] = None, right: Optional[str] = None) -> None:
        if left is not None:
            self.status_left.configure(text=left)
        if right is not None:
            self.status_right.configure(text=right)

    def set_navigation_enabled(self, enabled: bool) -> None:
        """A run in progress locks the paths that would discard its context."""
        self.navigation_enabled = enabled
        state = "normal" if enabled else "disabled"
        for widget in (self.wordmark, self.settings_btn, self.account_btn):
            widget.configure(state=state)

    def _home(self) -> None:
        if self.navigation_enabled:
            self.on_home()

    def _on_resize(self, event) -> None:
        # Only the toplevel's own resize matters; every child reports one too.
        if event.widget is not self.root:
            return
        narrow = event.width < NARROW_WIDTH
        if narrow and self.breadcrumb.winfo_ismapped():
            self.breadcrumb.pack_forget()
        elif not narrow and not self.breadcrumb.winfo_ismapped():
            self.breadcrumb.pack(side="left")
