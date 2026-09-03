"""The application: window, navigation between screens, and the state they share.

Screens live in ``gui.screens``. Each is a class taking this App and building itself
into the frame it is handed; the App owns everything they need in common -- the project
scan, engine resolution, the account session and the run plumbing's entry point.
"""

from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox
from typing import Callable, Optional

from core.config_manager import config
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.unreal_engine_manager import UnrealEngineManager
from gui.account import AccountSession, SignInModal
from gui.shell import Shell
from gui.theme import apply_styles, theme

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "Convai.ico"

MIN_SIZE = (920, 640)
PREFERRED_SIZE = (1120, 760)


class App:
    """One window, one screen at a time, inside persistent chrome.

    The flows are passed in rather than imported: importing the entry module would
    re-execute it. Everything long-running happens on a daemon worker and comes back
    through ``root.after``, so only the Tk thread ever touches a widget.
    """

    def __init__(self, root: tk.Tk, tool_version: str, input_manager: InputManager,
                 flows: dict[str, Callable[[], Optional[str]]]):
        self.root = root
        self.tool_version = tool_version
        self.input_manager = input_manager
        self.flows = flows

        self.running = False
        self.projects: list[dict] = []
        # Engine folders the user picked in Settings. They live here, not on the
        # InputManager, because `reset()` clears that between runs.
        self.engine_overrides: dict[str, str] = {}
        self.escape_action: Optional[Callable[[], None]] = None
        self.account = AccountSession()
        self.screen = None

        root.title("Convai Modding Tool")
        root.minsize(*MIN_SIZE)
        root.geometry("{}x{}".format(*PREFERRED_SIZE))
        root.configure(bg=theme["bg_app"])
        apply_styles(root)
        if ICON_PATH.exists():
            root.iconbitmap(str(ICON_PATH))
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Nothing here may read `config`: its first read fetches the remote config,
        # which retries for minutes when GitHub is unreachable, and this runs before the
        # boot screen is on screen. The chip and the shelf are filled in after boot.
        self.shell = Shell(root, tool_version, on_home=self.show_shelf,
                           on_settings=self.open_settings, on_account=self.open_account)
        self.shell.set_account(None)

        root.bind("<Escape>", lambda event: self._on_escape(), add="+")
        root.bind("<Control-n>", lambda event: self._on_new_shortcut(), add="+")

    # --- screen plumbing ----------------------------------------------------

    def show(self, screen, breadcrumb: str, escape: Optional[Callable[[], None]] = None):
        """Swap the page for `screen` and set the chrome that goes with it."""
        self.screen = screen
        self.escape_action = escape
        self.shell.set_breadcrumb(breadcrumb)
        screen.build(self.shell.clear_page())
        return screen

    def _on_escape(self) -> None:
        if self.escape_action and not self.running:
            self.escape_action()

    def _on_new_shortcut(self) -> None:
        # Ctrl+N is the shelf's shortcut; it must not fire while a form has focus or a
        # run is going.
        if not self.running and isinstance(getattr(self.screen, "shortcut_new", None), bool):
            self.show_new_project()

    def _on_close(self) -> None:
        if self.running and not messagebox.askyesno(
                "Convai Modding Tool",
                "Run in progress — closing the tool may interrupt it.\n\nClose anyway?"):
            return
        self.root.destroy()

    # --- boot ---------------------------------------------------------------

    def show_boot(self) -> None:
        from gui.screens.boot import BootScreen

        self.show(BootScreen(self), "Starting")

    def show_blocked(self, message: str, outdated: bool = False,
                     installed: str = "", required: str = "") -> None:
        from gui.screens.boot import BlockedScreen

        self.show(BlockedScreen(self, message, outdated, installed, required), "Start")

    # --- shelf --------------------------------------------------------------

    def show_shelf(self, select_path: Optional[str] = None) -> None:
        from gui.screens.shelf import ShelfScreen

        self.show(ShelfScreen(self, select_path), "Projects")

    def show_new_project(self, state: Optional[dict] = None) -> None:
        from gui.screens.new_project import NewProjectScreen

        self.show(NewProjectScreen(self, state), "New project", escape=self.show_shelf)

    def show_review(self, kind: str, project: dict) -> None:
        """The Update/Migrate review that runs before any work starts."""
        from gui.screens.review import ReviewScreen

        self.show(ReviewScreen(self, kind, project), "Review",
                  escape=lambda: self.show_shelf(project["dir"]))

    def show_run(self, title: str, flow: Callable[[], Optional[str]], folder: Optional[str],
                 steps: Optional[list[str]] = None, retry: Optional[Callable[[], None]] = None,
                 subject: Optional[str] = None) -> None:
        """`folder` is what the result offers to open, and `subject` what it names -- for a
        migration both are the copy, not the project the run read from."""
        from gui.screens.run import RunScreen

        screen = RunScreen(self, title, flow, folder, steps or [], retry, subject)
        self.show(screen, "Activity")
        screen.start()

    def open_settings(self) -> None:
        from gui.screens.settings import SettingsDialog

        SettingsDialog(self).open()

    # --- account ------------------------------------------------------------

    def open_account(self) -> None:
        """The app-bar account control: the menu when signed in, the modal when not."""
        if self.account.is_signed_in:
            from gui.screens.account_menu import AccountMenu

            AccountMenu(self).open(self.shell.account_btn)
        else:
            SignInModal(self, on_success=self.refresh_account).open()

    def require_account(self, resume: Callable[[], None]) -> bool:
        """Gate a protected action behind sign-in.

        Returns True when the caller may proceed now; otherwise the modal is open and
        `resume` runs after a successful sign-in, so no entered value is lost.
        """
        if self.account.is_signed_in:
            return True
        SignInModal(self, on_success=lambda: (self.refresh_account(), resume())).open()
        return False

    def refresh_account(self) -> None:
        self.shell.set_account(self.account.display_name, self.account.email)
        if self.screen is not None and hasattr(self.screen, "on_account_changed"):
            self.screen.on_account_changed()

    # --- shared state -------------------------------------------------------

    def scan_projects(self) -> list[dict]:
        """Every modding project beside the tool, re-read on each call.

        Only facts the scan can actually establish end up here: a project's state is
        derived from its engine version, never from an assumption about the plugin
        inside it.
        """
        target = config.get_target_unreal_engine_version()
        entries = []
        for project_dir in self.input_manager.find_existing_projects():
            metadata = FileUtilityManager.get_metadata(project_dir)
            folder = os.path.basename(project_dir.rstrip("\\/"))
            # The folder is a project because the scan found a .uproject in it; the
            # metadata name is only a guess at what that file is called, and a legacy
            # project has none.
            uproject = next(Path(project_dir).glob("*.uproject"), None)
            version = UnrealEngineManager._get_project_engine_version(str(uproject)) if uproject else None
            migratable = bool(version) and version != target

            if not version:
                state, colour = "Engine version not detected", "warning"
            elif migratable:
                state, colour = f"Needs migration → UE {target}", "warning"
            else:
                state, colour = "Ready to update", "text_secondary"

            entries.append({
                "dir": project_dir,
                "name": folder,
                "ue": version or "",
                "type": metadata.get("asset_type") or "",
                "is_metahuman": bool(metadata.get("is_metahuman")),
                "api_key": metadata.get("api_key") or "",
                "plugin_name": metadata.get("plugin_name") or "",
                "project_name": metadata.get("project_name") or "",
                "migratable": migratable,
                "target": target,
                "state": state,
                "state_colour": colour,
                "meta": f"UE {version}" if version else "Engine version not detected",
            })
        self.projects = entries
        return entries

    # --- engine -------------------------------------------------------------

    @staticmethod
    def engine_version(version_type: str) -> str:
        return (config.get_target_unreal_engine_version() if version_type == "target"
                else config.get_current_unreal_engine_version())

    @staticmethod
    def is_valid_engine(path: str, version_type: str) -> bool:
        check = (UnrealEngineManager.is_valid_target_engine_path if version_type == "target"
                 else UnrealEngineManager.is_valid_current_engine_path)
        return bool(path) and check(Path(path))

    def engine_path(self, version_type: str = "current") -> Optional[str]:
        """The engine already chosen or detected, if it is still there. Never prompts.

        A remembered path is re-checked rather than trusted: an installation can be moved
        or removed between runs, and every screen that reads this decides from it whether
        an action is available.
        """
        cached = (self.engine_overrides.get(version_type)
                  or (self.input_manager.target_unreal_engine_path if version_type == "target"
                      else self.input_manager.unreal_engine_path))
        if cached and self.is_valid_engine(cached, version_type):
            return cached
        detected = self.input_manager.detect_engine_path(version_type)
        return detected if detected and self.is_valid_engine(detected, version_type) else None

    def set_engine_path(self, version_type: str, path: str) -> None:
        """Remember an engine the user chose, and tell the current screen about it."""
        self.engine_overrides[version_type] = path
        if version_type == "target":
            self.input_manager.target_unreal_engine_path = path
        else:
            self.input_manager.unreal_engine_path = path
        if self.screen is not None and hasattr(self.screen, "on_engine_changed"):
            self.screen.on_engine_changed()

    def choose_engine(self, version_type: str = "current", parent: Optional[tk.Misc] = None) -> Optional[str]:
        """Ask for an engine folder and validate it before returning.

        The picker belongs to the review and settings screens: a native dialog opening
        in the middle of a command the user already confirmed is the surprise this
        redesign removes.
        """
        wanted = self.engine_version(version_type)
        chosen = filedialog.askdirectory(
            parent=parent or self.root,
            title=f"Select the Unreal Engine {wanted} installation folder")
        if not chosen:
            return None
        if not self.is_valid_engine(chosen, version_type):
            messagebox.showerror(
                "Convai Modding Tool",
                f"{chosen} is not an Unreal Engine {wanted} installation.",
                parent=parent or self.root)
            return None
        return chosen

def run_gui(tool_version: str, input_manager: InputManager,
            flows: dict[str, Callable[[], Optional[str]]]) -> None:
    root = tk.Tk()
    app = App(root, tool_version, input_manager, flows)
    app.show_boot()
    root.mainloop()
