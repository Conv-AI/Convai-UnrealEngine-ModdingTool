"""The signed-in profile menu hanging off the app-bar account button.

A native ``tk.Menu`` cannot carry the two-line identity block the design asks for and
cannot be given the dark palette on Windows, so this is a borderless Toplevel placed
under the button it was opened from.
"""

from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox
from typing import Optional

from gui.account import DASHBOARD_URL, SignInModal
from gui.components import button, ellipsise
from gui.theme import FONTS, theme

MENU_WIDTH = 248


class AccountMenu:
    """Identity, then the three account actions. Closes on Escape, focus loss or choice."""

    def __init__(self, app):
        self.app = app
        self.win: Optional[tk.Toplevel] = None
        self.items: list[tk.Button] = []

    # --- lifecycle ----------------------------------------------------------

    def open(self, anchor_widget: tk.Misc) -> None:
        if self.win is not None:
            return
        self.items = []

        # A child of root, so it is torn down with the window rather than outliving it.
        win = self.win = tk.Toplevel(self.app.root)
        win.wm_overrideredirect(True)
        win.transient(self.app.root)
        win.configure(background=theme["bg_surface_raised"])

        panel = tk.Frame(win, background=theme["bg_surface_raised"],
                         highlightbackground=theme["border_subtle"], highlightthickness=1)
        panel.pack(fill="both", expand=True)

        self._build_identity(panel)
        tk.Frame(panel, background=theme["border_subtle"], height=1).pack(fill="x")
        self._build_items(panel)

        win.bind("<Escape>", lambda event: self.close(), add="+")
        win.bind("<Down>", lambda event: self._move(1), add="+")
        win.bind("<Up>", lambda event: self._move(-1), add="+")
        win.bind("<Destroy>", self._on_destroy, add="+")
        # A Toplevel is in its descendants' bindtags, so one binding covers every item.
        win.bind("<Button-1>", self._on_click, add="+")

        self._place(anchor_widget)
        # An override-redirect window is not managed, so nothing raises it for us, and
        # whether it can hold keyboard focus is up to the window manager. The grab is
        # what makes the menu dismissable: with it, a click anywhere else in the app is
        # delivered here instead of vanishing, and closing on focus loss -- which Windows
        # reports inconsistently for an unmanaged window -- is not needed.
        win.lift()
        win.wm_attributes("-topmost", True)
        win.grab_set()
        if self.items:
            self.items[0].focus_set()

    def close(self) -> None:
        win, self.win = self.win, None
        if win is not None and win.winfo_exists():
            win.grab_release()
            win.destroy()

    def _on_destroy(self, event) -> None:
        # Children report their own destruction through the same binding.
        if event.widget is self.win:
            self.win = None

    def _on_click(self, event) -> str | None:
        """Close on a click outside the menu; the grab routes those here."""
        win = self.win
        if win is None or not win.winfo_exists():
            return None
        inside = (0 <= event.x_root - win.winfo_rootx() < win.winfo_width()
                  and 0 <= event.y_root - win.winfo_rooty() < win.winfo_height())
        if not inside:
            self.close()
            return "break"
        return None

    # --- contents -----------------------------------------------------------

    def _build_identity(self, parent: tk.Misc) -> None:
        account = self.app.account
        block = tk.Frame(parent, background=theme["bg_surface_raised"])
        block.pack(fill="x", padx=14, pady=(12, 10))
        tk.Label(block, text=account.display_name or account.email or "Convai account",
                 background=theme["bg_surface_raised"], foreground=theme["text_primary"],
                 font=FONTS["body_strong"], anchor="w", justify="left",
                 wraplength=MENU_WIDTH - 32).pack(fill="x")
        if account.email:
            tk.Label(block, text=ellipsise(account.email, 34, keep="head"), background=theme["bg_surface_raised"],
                     foreground=theme["text_secondary"], font=FONTS["meta"], anchor="w",
                     justify="left", wraplength=MENU_WIDTH - 32).pack(fill="x", pady=(2, 0))

    def _build_items(self, parent: tk.Misc) -> None:
        holder = tk.Frame(parent, background=theme["bg_surface_raised"])
        holder.pack(fill="x", padx=6, pady=6)
        for text, command in (("Open Convai dashboard", self._open_dashboard),
                              ("Switch account", self._switch_account),
                              ("Log out", self._log_out)):
            item = button(holder, text, command, kind="secondary", anchor="w")
            # `secondary` already sits on bg_surface_raised; only its border has to go,
            # or every row draws a box inside the menu.
            item.configure(highlightbackground=theme["bg_surface_raised"])
            item.pack(fill="x", pady=1)
            self.items.append(item)

    def _place(self, anchor_widget: tk.Misc) -> None:
        win = self.win
        win.update_idletasks()
        # No clamp against screenwidth: that is the primary monitor's width, while rootx
        # is in virtual-desktop coordinates, so it would fling the menu across displays.
        x = anchor_widget.winfo_rootx() + anchor_widget.winfo_width() - MENU_WIDTH
        y = anchor_widget.winfo_rooty() + anchor_widget.winfo_height() + 6
        win.wm_geometry(f"{MENU_WIDTH}x{win.winfo_reqheight()}+{x}+{y}")

    def _move(self, delta: int) -> None:
        if not self.items:
            return
        focused = self.win.focus_get()
        index = self.items.index(focused) if focused in self.items else 0
        self.items[(index + delta) % len(self.items)].focus_set()

    # --- actions ------------------------------------------------------------

    def _open_dashboard(self) -> None:
        self.close()
        webbrowser.open(DASHBOARD_URL, new=2)

    def _switch_account(self) -> None:
        """Sign out only once the replacement sign-in succeeds.

        Clearing the session first would leave a user who cancelled the modal signed out
        of the account they still had.
        """
        self.close()
        SignInModal(self.app, on_success=self.app.refresh_account).open()

    def _log_out(self) -> None:
        self.close()
        if self._discards_work() and not messagebox.askyesno(
                "Convai Modding Tool",
                "Signing out now will discard work you haven't finished.\n\nSign out anyway?",
                parent=self.app.root):
            return
        self.app.account.sign_out()
        self.app.refresh_account()
        self.app.show_shelf()

    def _discards_work(self) -> bool:
        return bool(self.app.running or getattr(self.app.screen, "has_unsaved_input", False))
