"""The review that stands between picking an action and running it.

Engine paths are resolved here, before any work starts: the old flow opened a native
folder chooser in the middle of a command the user had already confirmed. Every reason
an action cannot run yet is stated in words next to the button it disables.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox
from typing import Callable, Optional

from gui.components import Tooltip, button, card, ellipsise, set_button_state
from gui.theme import FONTS, SPACE, theme

# The run screen's lifecycle steps: a display title, and the phrase the flow logs when it
# reaches that step. The phrases are copied from the logger.step calls in
# ConvaiModdingTool.py, core/unreal_engine_manager.py and core/file_utility_manager.py --
# change one there and the step it drives stops ticking.
UPDATE_STEPS = [
    ("Reading the project", "loading project configuration"),
    ("Checking Unreal Engine", "checking project engine version"),
    ("Updating Convai plugins", "updating convai dependencies"),
    ("Configuring project assets", "configuring project assets"),
    ("Patching for this engine", "patching plugin source"),
    ("Building project", "building project"),
]
MIGRATE_STEPS = [
    ("Checking what the migration needs", "getting target unreal engine version"),
    ("Updating the source project", "updating selected project"),
    ("Copying the project", "creating copy of project for migration"),
    ("Updating the engine version", "updating engine version to"),
    ("Patching for the target engine", "patching target.cs files"),
    ("Building the copy", "building migrated project"),
]

WRAP = 620


class ReviewScreen:
    """`Update <project>` or `Migrate <project> to UE <target>`, before either begins."""

    def __init__(self, app, kind: str, project: dict):
        self.app = app
        self.kind = kind
        self.project = project
        self.name = project["name"]
        self.parent: Optional[tk.Frame] = None

        # A cached path can outlive the installation it points at, so it is re-checked
        # rather than trusted.
        self.engine = self._valid(app.engine_path("current"), "current")
        self.target_engine = self._valid(app.engine_path("target"), "target") if kind == "migrate" else None

    def _valid(self, path: Optional[str], version_type: str) -> Optional[str]:
        return path if path and self.app.is_valid_engine(path, version_type) else None

    # --- naming -------------------------------------------------------------

    @property
    def destination_name(self) -> str:
        # FileUtilityManager.create_migrated_project_copy names the copy
        # <metadata project_name>_<target>; the folder name only stands in for display
        # on a project the flow would refuse anyway.
        base = self.project.get("project_name") or self.name
        return f"{base}_{self.project['target']}"

    @property
    def destination_dir(self) -> str:
        return os.path.join(str(self.app.input_manager.get_script_dir()), self.destination_name)

    # --- screen -------------------------------------------------------------

    def build(self, parent: tk.Frame) -> None:
        self.parent = parent
        self._render()

    def _render(self) -> None:
        """(Re)draw the page. Choosing an engine changes half of it, so it redraws whole."""
        parent = self.parent
        if parent is None or not parent.winfo_exists():
            return
        for child in parent.winfo_children():
            child.destroy()

        migrate = self.kind == "migrate"
        title = (f"Migrate {self.name} to UE {self.project['target']}" if migrate
                 else f"Update {self.name}")
        subtitle = ("The tool copies the project into a new folder and leaves the original alone."
                    if migrate else
                    "Nothing changes until you start the update.")

        tk.Label(parent, text=title, background=theme["bg_app"], foreground=theme["text_primary"],
                 font=FONTS["page_title"], anchor="w", justify="left", wraplength=760).pack(anchor="w")
        tk.Label(parent, text=subtitle, background=theme["bg_app"], foreground=theme["text_secondary"],
                 font=FONTS["body"], anchor="w", justify="left", wraplength=760).pack(
                     anchor="w", pady=(6, SPACE["section"]))

        if migrate:
            self._build_migrate(parent)
        else:
            self._build_update(parent)

        self._build_actions(parent)

    # --- update -------------------------------------------------------------

    def _build_update(self, parent: tk.Frame) -> None:
        outer, inner = card(parent, title="TARGET PROJECT")
        outer.pack(fill="x", pady=(0, SPACE["tight"]))
        self._detail(inner, "Project", self.name)
        self._detail(inner, "Location", ellipsise(self.project["dir"], 72), mono=True,
                     tooltip=self.project["dir"])
        self._engine_row(inner, "Unreal Engine used for this update", "current")

        outer, inner = card(parent, title="WHAT THIS UPDATE DOES")
        outer.pack(fill="x", pady=(0, SPACE["section"]))
        self._lines(inner, [
            "Replaces the Convai plugin in this project with the current release.",
            "Reapplies the project's Convai configuration and asset setup.",
            "Rebuilds the project so the new plugin compiles.",
        ])
        tk.Label(inner, text="Your content and original project folder remain in place.",
                 background=theme["bg_surface"], foreground=theme["ok_soft_text"],
                 font=FONTS["body"], anchor="w", justify="left", wraplength=WRAP).pack(
                     anchor="w", pady=(SPACE["tight"], 0))

    # --- migrate ------------------------------------------------------------

    def _build_migrate(self, parent: tk.Frame) -> None:
        outer, inner = card(parent, title="SOURCE PROJECT")
        outer.pack(fill="x", pady=(0, SPACE["tight"]))
        self._detail(inner, "Project", self.name)
        self._detail(inner, "Location", ellipsise(self.project["dir"], 72), mono=True,
                     tooltip=self.project["dir"])
        self._detail(inner, "Current Unreal Engine version",
                     f"Unreal Engine {self.project['ue']}" if self.project["ue"]
                     else "Not detected in the project file",
                     tone=None if self.project["ue"] else "warning")
        self._engine_row(inner, "Unreal Engine used to update the source project", "current")

        outer, inner = card(parent, title="TARGET UNREAL ENGINE")
        outer.pack(fill="x", pady=(0, SPACE["tight"]))
        self._engine_row(inner, f"Unreal Engine {self.project['target']} installation", "target")

        outer, inner = card(parent, title="DESTINATION")
        outer.pack(fill="x", pady=(0, SPACE["tight"]))
        self._detail(inner, "New folder", self.destination_name)
        self._detail(inner, "Created beside this tool", ellipsise(self.destination_dir, 72),
                     mono=True, tooltip=self.destination_dir)
        tk.Label(inner, text="The original project will not be changed.",
                 background=theme["bg_surface"], foreground=theme["ok_soft_text"],
                 font=FONTS["body"], anchor="w", justify="left", wraplength=WRAP).pack(
                     anchor="w", pady=(SPACE["tight"], 0))

        outer, inner = card(parent, title="WHAT HAPPENS, IN ORDER")
        outer.pack(fill="x", pady=(0, SPACE["section"]))
        self._lines(inner, [
            "Update the source project's Convai plugin and configuration.",
            f"Copy the project into {self.destination_name}.",
            f"Point the copy at Unreal Engine {self.project['target']} and patch it for that version.",
            "Build the copy with the target engine.",
        ], numbered=True)

        if os.path.isdir(self.destination_dir):
            self._destination_conflict(parent)

    def _destination_conflict(self, parent: tk.Frame) -> None:
        """A folder is already sitting on the destination name; stop rather than guess."""
        frame = tk.Frame(parent, background=theme["danger_soft"],
                         highlightbackground=theme["danger_soft_border"], highlightthickness=1,
                         padx=14, pady=12)
        frame.pack(fill="x", pady=(0, SPACE["section"]))
        tk.Label(frame, text=f"{self.destination_name} already exists",
                 background=theme["danger_soft"], foreground=theme["danger_soft_text"],
                 font=FONTS["body_strong"], anchor="w", justify="left", wraplength=WRAP).pack(anchor="w")
        tk.Label(frame,
                 text=("The tool would have to write over a folder it did not create, so the "
                       "migration cannot start. Rename or move the existing folder, then come back."),
                 background=theme["danger_soft"], foreground=theme["danger_soft_text"],
                 font=FONTS["body"], anchor="w", justify="left", wraplength=WRAP).pack(
                     anchor="w", pady=(4, SPACE["tight"]))

        row = tk.Frame(frame, background=theme["danger_soft"])
        row.pack(anchor="w")
        button(row, "Choose a new name", self._explain_rename, compact=True,
               accessible_name=f"How to free the name {self.destination_name}").pack(side="left")
        button(row, "Open existing folder", self._open_destination, compact=True,
               accessible_name=f"Open {self.destination_dir}").pack(side="left", padx=(SPACE["tight"], 0))

    def _explain_rename(self) -> None:
        # There is no rename flow underneath: the copy's name is derived from the
        # project's metadata, so the only fix is to free the folder name.
        if messagebox.askyesno(
                "Convai Modding Tool",
                f"The copy is always named {self.destination_name}, after this project and the "
                f"target engine version.\n\nRename or remove the existing folder to free that name."
                f"\n\nOpen the existing folder now?",
                parent=self.app.root):
            self._open_destination()

    def _open_destination(self) -> None:
        if not os.path.isdir(self.destination_dir):
            self._render()  # it has gone since the page was drawn
            return
        try:
            os.startfile(self.destination_dir)
        except OSError as error:
            messagebox.showerror("Convai Modding Tool",
                                 f"Could not open {self.destination_dir}.\n\n{error}",
                                 parent=self.app.root)

    # --- pieces -------------------------------------------------------------

    def _detail(self, parent: tk.Frame, label: str, value: str, mono: bool = False,
                tone: Optional[str] = None, tooltip: str = "",
                action: Optional[tuple[str, Callable[[], None]]] = None) -> None:
        row = tk.Frame(parent, background=theme["bg_surface"])
        row.pack(fill="x", pady=(0, SPACE["tight"]))
        tk.Label(row, text=label, background=theme["bg_surface"], foreground=theme["text_secondary"],
                 font=FONTS["meta"], anchor="w").pack(anchor="w")

        line = tk.Frame(row, background=theme["bg_surface"])
        line.pack(fill="x", pady=(2, 0))
        text = tk.Label(line, text=value, background=theme["bg_surface"],
                        foreground=theme[tone or ("text_secondary" if mono else "text_primary")],
                        font=FONTS["mono"] if mono else FONTS["body"],
                        anchor="w", justify="left", wraplength=WRAP)
        text.pack(side="left", fill="x", expand=True)
        if tooltip and tooltip != value:
            Tooltip(text, tooltip)
        if action:
            label_text, command = action
            button(line, label_text, command, compact=True,
                   accessible_name=f"{label_text} — {label}").pack(side="right", padx=(SPACE["tight"], 0))

    def _engine_row(self, parent: tk.Frame, label: str, version_type: str) -> None:
        path = self.engine if version_type == "current" else self.target_engine
        wanted = self.app.engine_version(version_type)
        if path:
            value, tone = f"Unreal Engine {wanted} · {ellipsise(path, 56)}", None
            action = ("Change", lambda: self._choose(version_type))
        else:
            value, tone = f"Unreal Engine {wanted} was not found on this computer.", "warning"
            action = ("Choose folder", lambda: self._choose(version_type))
        self._detail(parent, label, value, tone=tone, tooltip=path or "", action=action)

    def _choose(self, version_type: str) -> None:
        chosen = (self.app.choose_engine("target") if version_type == "target"
                  else self.app.choose_engine("current", parent=self.app.root))
        if not chosen:
            return
        # Remembered on the InputManager as well as here: the app-bar chip and the next
        # screen read the path from there, and `reset()` keeps the current engine.
        if version_type == "target":
            self.target_engine = chosen
            self.app.input_manager.target_unreal_engine_path = chosen
        else:
            self.engine = chosen
            self.app.input_manager.unreal_engine_path = chosen
        self._render()

    def _lines(self, parent: tk.Frame, texts: list[str], numbered: bool = False) -> None:
        for index, text in enumerate(texts, start=1):
            row = tk.Frame(parent, background=theme["bg_surface"])
            row.pack(fill="x", pady=(0, 4))
            tk.Label(row, text=f"{index}." if numbered else "•", background=theme["bg_surface"],
                     foreground=theme["accent"], font=FONTS["body"], width=3, anchor="w").pack(
                         side="left", anchor="n")
            tk.Label(row, text=text, background=theme["bg_surface"], foreground=theme["text_primary"],
                     font=FONTS["body"], anchor="w", justify="left", wraplength=WRAP).pack(
                         side="left", fill="x", expand=True)

    # --- actions ------------------------------------------------------------

    def _blockers(self) -> list[str]:
        """Why the primary action cannot run yet, in the order the user would fix them."""
        reasons = []
        if not self.engine:
            reasons.append(
                f"Choose your Unreal Engine {self.app.engine_version('current')} installation above. "
                f"{'The source project is updated with it before it is copied.' if self.kind == 'migrate' else 'The update is built with it.'}")
        if self.kind == "migrate":
            if not self.target_engine:
                reasons.append(
                    f"Choose your Unreal Engine {self.project['target']} installation above. "
                    "The copy is built with it.")
            if not self.project.get("project_name"):
                reasons.append(
                    "This project has no Convai metadata, so the tool cannot tell what to call the "
                    "copy. Only projects created by this tool can be migrated.")
            if os.path.isdir(self.destination_dir):
                reasons.append(f"Free the name {self.destination_name} before migrating.")
        return reasons

    def _build_actions(self, parent: tk.Frame) -> None:
        reasons = self._blockers()
        for reason in reasons:
            tk.Label(parent, text=reason, background=theme["bg_app"], foreground=theme["warning"],
                     font=FONTS["body"], anchor="w", justify="left", wraplength=760).pack(
                         anchor="w", pady=(0, SPACE["tight"]))

        row = tk.Frame(parent, background=theme["bg_app"])
        row.pack(fill="x", pady=(SPACE["tight"], 0))
        button(row, "Back", lambda: self.app.show_shelf(self.project["dir"])).pack(side="left")

        confirm_text = "Create migrated copy" if self.kind == "migrate" else "Update project"
        confirm = button(row, confirm_text, self._confirm, kind="primary",
                         accessible_name=f"{confirm_text} — {self.name}")
        confirm.pack(side="right")
        set_button_state(confirm, not reasons)
        if not reasons:
            confirm.focus_set()

    def _confirm(self) -> None:
        if self._blockers():
            return
        manager = self.app.input_manager
        manager.reset()
        manager.unreal_engine_path = self.engine
        manager.project_dir = self.project["dir"]

        if self.kind == "migrate":
            manager.target_unreal_engine_path = self.target_engine
            # No retry: a second attempt would meet the copy the first one left behind.
            self.app.show_run(f"Migrating {self.name}", self.app.flows["migrate"],
                              self.destination_dir, steps=MIGRATE_STEPS,
                              subject=self.destination_name)
        else:
            self.app.show_run(f"Updating {self.name}", self.app.flows["update"],
                              self.project["dir"], steps=UPDATE_STEPS,
                              retry=lambda: self.app.show_review("update", self.project))
