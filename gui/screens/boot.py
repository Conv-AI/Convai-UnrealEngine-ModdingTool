"""The start-up screen and the two dead ends it can reach.

Boot owns the checks the tool cannot start without -- the remote configuration and the
version gate -- and shows which one is running, because a stalled network request behind
a single "Checking for updates..." label is indistinguishable from a hang.
"""

from __future__ import annotations

import threading
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Callable, Optional

from core.config_manager import config
from gui.components import Disclosure, StepList, button, card, pill
from gui.theme import FONTS, SPACE, theme

BOOT_WIDTH = 440
BLOCKED_WIDTH = 500

CONFIGURATION = "Checking configuration"
VERSION = "Checking version"
PROJECTS = "Opening projects"

OUTDATED_MESSAGE = "This build is older than the version Convai currently supports."
UNCHECKED_MESSAGE = ("The tool couldn't check whether it is up to date. Check your internet "
                     "connection or VPN, then try again.")


class BootScreen:
    """Product name, the three boot stages, and an indeterminate bar."""

    def __init__(self, app):
        self.app = app
        self.steps: Optional[StepList] = None

    def build(self, parent: tk.Frame) -> None:
        # Nothing on this screen is navigable: boot has no shelf yet, and a blocked
        # start is a dead end by design.
        self.app.shell.set_navigation_enabled(False)

        holder = tk.Frame(parent, background=theme["bg_app"])
        holder.pack(expand=True, pady=(48, 0))

        outer, inner = card(holder)
        outer.pack()
        # A zero-height spacer is the only way to give a pack-managed card a width
        # without also pinning its height.
        tk.Frame(inner, background=theme["bg_surface"], width=BOOT_WIDTH, height=0).pack()

        tk.Label(inner, text="Convai Modding Tool", background=theme["bg_surface"],
                 foreground=theme["text_primary"], font=FONTS["section_title"]).pack(anchor="w")
        tk.Label(inner, text="Getting things ready", background=theme["bg_surface"],
                 foreground=theme["text_secondary"], font=FONTS["body"]).pack(anchor="w", pady=(4, 0))

        self.steps = StepList(inner, surface="bg_surface")
        self.steps.frame.pack(fill="x", pady=(SPACE["section"], 0))
        self.steps.set_steps([CONFIGURATION, VERSION, PROJECTS])
        self.steps.set_state(CONFIGURATION, "active")

        bar = ttk.Progressbar(inner, mode="indeterminate")
        bar.pack(fill="x", pady=(SPACE["section"], 0))
        bar.start(12)

        # The checks run for minutes when GitHub is unreachable, so they wait until the
        # window has actually been painted.
        self.app.root.after(50, self._start)

    # --- boot work ----------------------------------------------------------

    def _start(self) -> None:
        if not self._alive():
            return
        threading.Thread(target=self._work, daemon=True).start()

    def _work(self) -> None:
        try:
            config.load()
            self._stage(CONFIGURATION, VERSION)

            from core.version_manager import VersionManager
            up_to_date = VersionManager.check_version(self.app.tool_version)
        except Exception as exc:
            self._ui(lambda message=str(exc): self.app.show_blocked(message))
            return

        # None means the check itself failed; only a definite False is an outdated build.
        if up_to_date is None:
            self._ui(lambda: self.app.show_blocked(UNCHECKED_MESSAGE))
            return

        if not up_to_date:
            required = self._required_version()
            self._ui(lambda: self.app.show_blocked(
                OUTDATED_MESSAGE, outdated=True,
                installed=self.app.tool_version, required=required))
            return

        self._stage(VERSION, PROJECTS)
        self._restore_account()
        self._ui(lambda: self.app.shell.set_navigation_enabled(True))
        # The shelf reads the account state as it builds, so it comes after the restore.
        self._ui(lambda: (self.app.refresh_account(), self.app.show_shelf()))

    @staticmethod
    def _required_version() -> str:
        """The version the gate actually compares against -- Version.json, not the
        modding_tool_config entry, which is a different file and a different key."""
        try:
            return str(config.remote_config.version_data.get("modding-tool-version", "") or "")
        except Exception:
            return ""

    def _restore_account(self) -> None:
        try:
            self.app.account.restore()
        except Exception:
            # A session that will not restore is a signed-out session, not a failed boot.
            pass

    # --- thread hand-off ----------------------------------------------------

    def _ui(self, action: Callable[[], object]) -> None:
        """Marshal to the Tk thread, tolerating a window that is already gone."""
        try:
            self.app.root.after(0, action)
        except tk.TclError:
            pass

    def _stage(self, done: str, active: str) -> None:
        def apply() -> None:
            if not self._alive():
                return
            self.steps.set_state(done, "done")
            self.steps.set_state(active, "active")

        self._ui(apply)

    def _alive(self) -> bool:
        # The step list, not the page frame: a callback that lands after the page was
        # swapped must not write to labels that have already gone.
        return self.steps is not None and self.steps.frame.winfo_exists()


class BlockedScreen:
    """Boot stopped. Either the tool is too old to run, or a check failed."""

    def __init__(self, app, message: str, outdated: bool = False,
                 installed: str = "", required: str = ""):
        self.app = app
        self.message = message
        self.outdated = outdated
        self.installed = installed
        self.required = required

    def build(self, parent: tk.Frame) -> None:
        # Nothing on this screen is navigable: boot has no shelf yet, and a blocked
        # start is a dead end by design.
        self.app.shell.set_navigation_enabled(False)

        holder = tk.Frame(parent, background=theme["bg_app"])
        holder.pack(expand=True, pady=(48, 0))
        tk.Frame(holder, background=theme["bg_app"], width=BLOCKED_WIDTH, height=0).pack()

        # The colour lives in the pill; the heading and body stay high-contrast.
        pill(holder, "Update required" if self.outdated else "Start-up blocked",
             tone="warn" if self.outdated else "danger").pack(anchor="w")

        title = "A newer version is required" if self.outdated else "We couldn't start the tool"
        tk.Label(holder, text=title, background=theme["bg_app"], foreground=theme["text_primary"],
                 font=FONTS["page_title"], anchor="w", justify="left",
                 wraplength=BLOCKED_WIDTH).pack(anchor="w", pady=(SPACE["tight"], 0))

        if self.outdated:
            self._build_outdated(holder)
        else:
            self._build_failure(holder)

        actions = tk.Frame(holder, background=theme["bg_app"])
        actions.pack(anchor="w", pady=(SPACE["section"], 0))
        if self.outdated:
            primary = button(actions, "Download latest version", self._download, kind="primary")
            primary.pack(side="left")
            button(actions, "Check again", self.app.show_boot).pack(side="left", padx=SPACE["tight"])
        else:
            primary = button(actions, "Try again", self.app.show_boot, kind="primary")
            primary.pack(side="left")
        button(actions, "Quit", self.app.root.destroy, kind="quiet").pack(side="left", padx=SPACE["tight"])
        self.app.root.after(0, lambda: primary.winfo_exists() and primary.focus_set())

    # --- variants -----------------------------------------------------------

    def _build_outdated(self, holder: tk.Frame) -> None:
        tk.Label(holder,
                 text="Update Convai Modding Tool to continue creating, updating, and "
                      "migrating projects.",
                 background=theme["bg_app"], foreground=theme["text_secondary"],
                 font=FONTS["body"], anchor="w", justify="left",
                 wraplength=BLOCKED_WIDTH).pack(anchor="w", pady=(SPACE["tight"], 0))

        outer, inner = card(holder)
        outer.pack(fill="x", pady=(SPACE["section"], 0))
        columns = tk.Frame(inner, background=theme["bg_surface"])
        columns.pack(fill="x")
        columns.columnconfigure(0, weight=1, uniform="version")
        columns.columnconfigure(1, weight=1, uniform="version")
        self._version_cell(columns, 0, "INSTALLED", self.installed)
        self._version_cell(columns, 1, "REQUIRED", self.required or "latest")

        tk.Label(inner, text=self.message or OUTDATED_MESSAGE, background=theme["bg_surface"],
                 foreground=theme["text_secondary"], font=FONTS["meta"], anchor="w",
                 justify="left", wraplength=BLOCKED_WIDTH).pack(anchor="w", pady=(SPACE["tight"], 0))

    @staticmethod
    def _version_cell(parent: tk.Frame, column: int, label: str, version: str) -> None:
        cell = tk.Frame(parent, background=theme["bg_field"], padx=12, pady=10)
        cell.grid(row=0, column=column, sticky="ew",
                  padx=(0, SPACE["tight"]) if column == 0 else 0)
        tk.Label(cell, text=label, background=theme["bg_field"], foreground=theme["text_secondary"],
                 font=FONTS["meta"], anchor="w").pack(anchor="w")
        tk.Label(cell, text=f"v{version}" if version else "unknown", background=theme["bg_field"],
                 foreground=theme["text_primary"], font=FONTS["body_strong"],
                 anchor="w").pack(anchor="w", pady=(2, 0))

    def _build_failure(self, holder: tk.Frame) -> None:
        tk.Label(holder, text=self._plain_cause(), background=theme["bg_app"],
                 foreground=theme["text_secondary"], font=FONTS["body"], anchor="w",
                 justify="left", wraplength=BLOCKED_WIDTH).pack(anchor="w", pady=(SPACE["tight"], 0))

        details = tk.Frame(holder, background=theme["bg_app"])
        details.pack(fill="x", pady=(SPACE["section"], 0))

        box = tk.Frame(details, background=theme["bg_field"],
                       highlightbackground=theme["border_subtle"], highlightthickness=1)
        # width=1 so the Text cannot impose Tk's default 80 characters on the page.
        text = tk.Text(box, height=6, width=1, wrap="word", background=theme["bg_field"],
                       foreground=theme["text_secondary"], font=FONTS["mono"],
                       insertbackground=theme["text_primary"], relief="flat",
                       highlightthickness=0, padx=10, pady=10,
                       selectbackground=theme["bg_hover"], selectforeground=theme["text_primary"])
        scrollbar = ttk.Scrollbar(box, orient="vertical", command=text.yview,
                                  style="Vertical.TScrollbar")
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", self.message or "No details were reported.")
        # Read-only but still selectable and copyable: 'disabled' blocks edits only.
        text.configure(state="disabled")
        scrollbar.pack(side="right", fill="y")
        text.pack(side="left", fill="both", expand=True)

        Disclosure(details, "Hide details", "Show details", box,
                   pack_options={"fill": "x", "pady": (SPACE["tight"], 0)}).button.pack(anchor="w")

    def _plain_cause(self) -> str:
        lowered = self.message.lower()
        if any(word in lowered for word in ("config", "github", "network", "connect", "timed out")):
            return ("The tool couldn't reach Convai's configuration service, so it can't tell "
                    "what to install. Check your internet connection or VPN, then try again.")
        return "A start-up check failed before the tool could open your projects."

    @staticmethod
    def _download() -> None:
        from core.version_manager import LATEST_RELEASE_URL

        webbrowser.open(LATEST_RELEASE_URL, new=2)
