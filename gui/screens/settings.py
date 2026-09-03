"""The Settings dialog: engine installations, Linux packaging and the tool version.

Everything slow here -- the toolchain install and the update check -- runs on a daemon
thread and reports back through ``root.after``. The dialog can be closed while one is
still running, so each completion checks its widgets are alive before touching them.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser

from core.config_manager import config
from gui.components import Tooltip, button, card, ellipsise, pill, scroll_host, set_button_state
from gui.theme import FONTS, SPACE, theme

WIDTH = 600
# Wrap widths: card content is WIDTH less the scrollbar, the dialog gutter and the card
# padding. A row that shares its line with buttons gets what those leave behind.
WRAP = 500
ROW_WRAP = 310
INSTALLING = "Installing, this can take several minutes…"


class SettingsDialog:
    """Modal settings, grouped into Unreal Engine, Packaging and About.

    Each section is a row of explanatory text with its action to the right; the row's
    second line doubles as that action's status, so progress appears where the user is
    already looking instead of at the bottom of the dialog.
    """

    def __init__(self, app):
        self.app = app
        self.window: tk.Toplevel | None = None
        self._engine_rows: dict[str, tuple[tk.Frame, tk.Label, Tooltip]] = {}

    # --- lifecycle ----------------------------------------------------------

    def open(self) -> None:
        window = tk.Toplevel(self.app.root)
        self.window = window
        window.title("Settings")
        window.configure(background=theme["bg_app"])
        window.transient(self.app.root)
        window.resizable(False, True)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.bind("<Escape>", lambda event: self.close(), add="+")

        # The title row stays outside the scrolled area: Close must never scroll away.
        self.head = tk.Frame(window, background=theme["bg_app"])
        self.head.pack(fill="x", padx=SPACE["surface"], pady=(SPACE["tight"] * 2, 0))
        self._build_title(self.head)

        self.canvas, host = scroll_host(window)
        self.canvas.container.pack(fill="both", expand=True)
        self.body = tk.Frame(host, background=theme["bg_app"])
        self.body.pack(fill="both", expand=True, padx=SPACE["surface"], pady=SPACE["tight"] * 2)
        window.bind("<MouseWheel>", self._on_wheel, add="+")

        self._build_engine(self.body)
        self._build_packaging(self.body)
        self._build_about(self.body)

        window.update_idletasks()
        self._place(window)
        window.grab_set()
        self.close_btn.focus_set()
        # A toolchain install outlives the dialog that started it, so its result has to
        # find whichever dialog is open when it lands -- not the one that is gone.
        self.app.settings_dialog = self

    def _place(self, window: tk.Toplevel) -> None:
        """Size to the content, but never past the screen -- at 150% scaling it would."""
        root = self.app.root
        wanted = self.head.winfo_reqheight() + self.body.winfo_reqheight() + SPACE["tight"] * 6
        height = max(min(wanted, window.winfo_screenheight() - 120), 360)
        x = root.winfo_rootx() + max((root.winfo_width() - WIDTH) // 2, 0)
        y = root.winfo_rooty() + 60
        window.minsize(WIDTH, min(height, 400))
        window.geometry(f"{WIDTH}x{height}+{max(x, 0)}+{max(y, 0)}")

    def _on_wheel(self, event) -> str:
        # The dialog is modal, so a window-level wheel binding cannot reach the main
        # window. "break" stops scroll_host's bind_all from scrolling this twice.
        self.canvas.yview_scroll(int(-event.delta / 120), "units")
        return "break"

    def close(self) -> None:
        if self.window is not None and self.window.winfo_exists():
            self.window.grab_release()
            self.window.destroy()
        self.window = None
        if getattr(self.app, "settings_dialog", None) is self:
            self.app.settings_dialog = None

    # --- sections -----------------------------------------------------------

    def _build_title(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, background=theme["bg_app"])
        row.pack(fill="x")

        self.close_btn = button(row, "Close", self.close, accessible_name="Close Settings",
                                compact=True)
        self.close_btn.pack(side="right", anchor="n")

        text = tk.Frame(row, background=theme["bg_app"])
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text="Settings", background=theme["bg_app"],
                 foreground=theme["text_primary"], font=FONTS["page_title"],
                 anchor="w").pack(fill="x", anchor="w")
        tk.Label(text, text="Configure the local tools your projects are built with.",
                 background=theme["bg_app"], foreground=theme["text_secondary"],
                 font=FONTS["meta"], anchor="w", justify="left",
                 wraplength=WRAP).pack(fill="x", anchor="w", pady=(2, 0))

    def _build_engine(self, parent: tk.Frame) -> None:
        inner = self._section(parent, "Unreal Engine",
                              "Used when creating, updating and migrating projects.")
        self._engine_row(inner, "current")
        self._divider(inner)
        self._engine_row(inner, "target")

    def _build_packaging(self, parent: tk.Frame) -> None:
        version = config.get_current_unreal_engine_version()
        enabled = config.linux_packaging_enabled()
        # The install runs on a daemon thread with no lock of its own, and the dialog is
        # rebuilt on every open: the in-flight flag lives on the App or reopening Settings
        # would start a second install over the first.
        installing = getattr(self.app, "toolchain_installing", False)
        inner = self._section(parent, "Packaging", "")
        row, text = self._row(inner)
        self.toolchain_btn = button(
            row, "Install Linux toolchain", self._install_toolchain, compact=True,
            accessible_name=f"Install the Linux cross-compilation toolchain for UE {version}")
        self.toolchain_btn.pack(side="right", padx=(SPACE["tight"], 0))

        self._strong(text, f"Linux packaging is {'on' if enabled else 'off'}")
        if installing:
            status = INSTALLING
        elif enabled:
            status = (f"Packaging builds a Linux target, which needs the cross-compilation "
                      f"toolchain for UE {version}.")
        else:
            status = "The Linux toolchain is not needed unless packaging is turned on."
        self.toolchain_status = self._meta(text, status)
        set_button_state(self.toolchain_btn, not installing)

    def _build_about(self, parent: tk.Frame) -> None:
        inner = self._section(parent, "About", "")
        row, text = self._row(inner)
        self.updates_btn = button(row, "Check for updates", self._check_updates,
                                  kind="quiet", compact=True)
        self.updates_btn.pack(side="right", padx=(SPACE["tight"], 0))
        # Packed only once an update is found, and to the left of the check so the button
        # the user just pressed does not move out from under the pointer.
        self.download_btn = button(row, "Download", self._open_download, compact=True,
                                   accessible_name="Download the latest Convai Modding Tool")

        self._strong(text, f"Convai Modding Tool v{self.app.tool_version}")
        self.updates_status = self._meta(text, "Updates are checked each time the tool starts.")

    # --- unreal engine rows -------------------------------------------------

    def _engine_row(self, parent: tk.Frame, version_type: str) -> None:
        version = self.app.engine_version(version_type)
        row, text = self._row(parent)
        button(row, "Choose folder", lambda: self._choose_engine(version_type), compact=True,
               accessible_name=f"Choose the Unreal Engine {version} installation folder"
               ).pack(side="right", padx=(SPACE["tight"], 0))

        head = tk.Frame(text, background=theme["bg_surface"])
        head.pack(fill="x", anchor="w")
        tk.Label(head, text=f"Unreal Engine {version}", background=theme["bg_surface"],
                 foreground=theme["text_primary"], font=FONTS["field_title"]).pack(side="left")
        badge = tk.Frame(head, background=theme["bg_surface"])
        badge.pack(side="left", padx=(SPACE["tight"], 0))

        detail = self._meta(text, "")
        self._engine_rows[version_type] = (badge, detail, Tooltip(detail, ""))
        self._refresh_engine(version_type)

    def _refresh_engine(self, version_type: str) -> None:
        badge, detail, tip = self._engine_rows[version_type]
        version = self.app.engine_version(version_type)
        # A cached path can outlive the installation it points at, so it is re-checked
        # rather than trusted: a deleted engine has to read as missing, not "Ready".
        path = self.app.engine_path(version_type)
        if path and not self.app.is_valid_engine(path, version_type):
            path = None

        for child in badge.winfo_children():
            child.destroy()
        pill(badge, "Ready" if path else "Not found", tone="ok" if path else "warn").pack()

        if path:
            message, colour = f"Ready · {ellipsise(path, 44)}", "ok_soft_text"
        elif version_type == "target":
            message = f"Migrating a project to UE {version} needs a UE {version} installation."
            colour = "warn_soft_text"
        else:
            message = f"Creating and updating projects need an Unreal Engine {version} installation."
            colour = "warn_soft_text"
        detail.configure(text=message, foreground=theme[colour])
        # The path is ellipsised in place, so the tooltip carries the whole of it.
        tip.text = path or ""

    def _choose_engine(self, version_type: str) -> None:
        chosen = self.app.choose_engine(version_type, parent=self.window)
        if not chosen:
            return
        self.app.set_engine_path(version_type, chosen)
        self._refresh_engine(version_type)
        self._refresh_screen()

    def _refresh_screen(self) -> None:
        """Repaint the screen behind the modal.

        A screen works out its engine-dependent text -- the shelf's "choose a UE x.y
        installation in Settings" -- when it is built, so a choice made here leaves it
        contradicting the dialog that is still on top of it.
        """
        from gui.screens.shelf import ShelfScreen

        screen = self.app.screen
        if hasattr(screen, "on_engine_changed"):
            return  # App.set_engine_path already told it
        if isinstance(screen, ShelfScreen):
            # Only the shelf can be rebuilt from under the dialog; a review holds
            # answers and a run is in flight.
            self.app.show_shelf(screen.selected["dir"] if screen.selected else None)

    # --- toolchain ----------------------------------------------------------

    def _install_toolchain(self) -> None:
        version = config.get_current_unreal_engine_version()
        self.app.toolchain_installing = True
        set_button_state(self.toolchain_btn, False)
        self.toolchain_status.configure(text=INSTALLING, foreground=theme["text_secondary"])

        def work() -> None:
            from core.download_utils import DownloadManager
            try:
                installed = DownloadManager.ensure_toolchain_for_version(version, force=True)
                message = ("Toolchain ready." if installed
                           else "Install failed — see the console for details.")
                colour = "accent" if installed else "danger"
            except Exception as exc:
                message, colour = f"Install failed: {exc}", "danger"
            self.app.root.after(0, lambda: self._toolchain_done(message, colour))

        threading.Thread(target=work, daemon=True).start()

    def _toolchain_done(self, message: str, colour: str) -> None:
        # Cleared before anything can return early: the flag is what keeps a second
        # install from starting, and this dialog may be long gone.
        self.app.toolchain_installing = False
        live = getattr(self.app, "settings_dialog", None)
        if live is None or not live.toolchain_status.winfo_exists():
            return
        live.toolchain_status.configure(text=message, foreground=theme[colour])
        set_button_state(live.toolchain_btn, True)

    # --- updates ------------------------------------------------------------

    def _check_updates(self) -> None:
        set_button_state(self.updates_btn, False)
        self.download_btn.pack_forget()
        self.updates_status.configure(text="Checking…", foreground=theme["text_secondary"])

        def work() -> None:
            from core.version_manager import VersionManager
            try:
                up_to_date = VersionManager.check_version(self.app.tool_version)
                if up_to_date is None:
                    # The check failed rather than answered; offering a download would
                    # send the user off to fix a problem they do not have.
                    result = ("Couldn't check for updates. Try again.", "danger", False)
                else:
                    result = (("This is the latest version.", "accent", False) if up_to_date
                              else ("A newer version is available.", "warning", True))
            except Exception:
                result = ("Couldn't check for updates. Try again.", "danger", False)
            self.app.root.after(0, lambda: self._updates_done(*result))

        threading.Thread(target=work, daemon=True).start()

    def _updates_done(self, message: str, colour: str, outdated: bool) -> None:
        if not self.updates_status.winfo_exists():
            return
        self.updates_status.configure(text=message, foreground=theme[colour])
        set_button_state(self.updates_btn, True)
        if outdated:
            self.download_btn.pack(side="right", padx=(SPACE["tight"], 0))

    @staticmethod
    def _open_download() -> None:
        from core.version_manager import LATEST_RELEASE_URL

        webbrowser.open(LATEST_RELEASE_URL, new=2)

    # --- building blocks ----------------------------------------------------

    @staticmethod
    def _section(parent: tk.Frame, title: str, subtitle: str) -> tk.Frame:
        outer, inner = card(parent, padding=SPACE["tight"] * 2)
        outer.pack(fill="x", pady=(0, SPACE["tight"] + 4))
        tk.Label(inner, text=title, background=theme["bg_surface"],
                 foreground=theme["text_primary"], font=FONTS["section_title"],
                 anchor="w").pack(fill="x", anchor="w")
        if subtitle:
            tk.Label(inner, text=subtitle, background=theme["bg_surface"],
                     foreground=theme["text_secondary"], font=FONTS["meta"], anchor="w",
                     justify="left", wraplength=WRAP).pack(fill="x", anchor="w", pady=(2, 0))
        return inner

    @staticmethod
    def _row(parent: tk.Frame) -> tuple[tk.Frame, tk.Frame]:
        """A settings row: the row itself, and its left-hand text column.

        The text column expands, but every label in it carries a wraplength, so its
        request can never grow past what the row's actions leave.
        """
        row = tk.Frame(parent, background=theme["bg_surface"])
        row.pack(fill="x", pady=(SPACE["tight"] + 2, 0))
        text = tk.Frame(row, background=theme["bg_surface"])
        text.pack(side="left", fill="x", expand=True)
        return row, text

    @staticmethod
    def _divider(parent: tk.Frame) -> None:
        tk.Frame(parent, background=theme["border_subtle"], height=1).pack(
            fill="x", pady=(SPACE["tight"], 0))

    @staticmethod
    def _strong(parent: tk.Frame, text: str) -> tk.Label:
        label = tk.Label(parent, text=text, background=theme["bg_surface"],
                         foreground=theme["text_primary"], font=FONTS["field_title"],
                         anchor="w", justify="left", wraplength=ROW_WRAP)
        label.pack(fill="x", anchor="w")
        return label

    @staticmethod
    def _meta(parent: tk.Frame, text: str) -> tk.Label:
        """The row's second line: its explanation, and where its action reports back."""
        label = tk.Label(parent, text=text, background=theme["bg_surface"],
                         foreground=theme["text_secondary"], font=FONTS["meta"], anchor="w",
                         justify="left", wraplength=ROW_WRAP)
        label.pack(fill="x", anchor="w", pady=(4, 0))
        return label
