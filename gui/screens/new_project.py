"""New project: name, project type and engine, in three stages.

Every entered value lives in ``state``, not in the widgets, so the screen can be rebuilt
-- on Back, or after a sign-in interruption -- without losing anything the user typed.
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk
from typing import Optional

from core.input_manager import InputManager
from gui.components import (
    ChoiceTile, Field, StepIndicator, Tooltip, button, card, ellipsise, pill, set_button_state,
)
from gui.theme import FONTS, SPACE, theme

# The form column: wide enough for a comfortable field, narrow enough to stay one thing
# to read. Everything inside wraps to WRAP so nothing can widen the column.
FORM_WIDTH = 640
WRAP = FORM_WIDTH - 2 * SPACE["surface"]

STEPS = ("Project details", "Project type", "Unreal Engine")

CREATE_STEPS = [
    "Validating Unreal Engine",
    "Setting up project",
    "Downloading Convai dependencies",
    "Configuring assets",
    "Building project",
]


class NewProjectScreen:
    """The three-stage create form. `state` carries every value between rebuilds."""

    def __init__(self, app, state: Optional[dict] = None):
        self.app = app
        self.state: dict = {"name": "", "type": "Scene", "metahuman": False, "engine": "", "step": 0}
        self.state.update(state or {})

        # Validation only speaks up once the user has left the field, or has been sent
        # back to it by Continue.
        self.name_blurred = bool(self.state["name"])
        self.pending_error: Optional[str] = None

        self.name_field: Optional[Field] = None
        self.name_var: Optional[tk.StringVar] = None
        self.type_var: Optional[tk.StringVar] = None
        self.metahuman_var: Optional[tk.BooleanVar] = None
        self.metahuman_row: Optional[tk.Frame] = None
        self.type_actions: Optional[tk.Frame] = None

    @property
    def has_unsaved_input(self) -> bool:
        """Read by the account menu: signing out mid-form would discard these values."""
        return bool(self.state.get("name") or self.state.get("engine"))

    # --- build --------------------------------------------------------------

    def build(self, parent: tk.Frame) -> None:
        column = tk.Frame(parent, background=theme["bg_app"])
        column.pack(anchor="n")
        # A zero-height strut fixes the column at FORM_WIDTH; nothing inside requests
        # more, so the form never spreads across a wide window.
        tk.Frame(column, background=theme["bg_app"], width=FORM_WIDTH, height=0).pack()

        head = tk.Frame(column, background=theme["bg_app"])
        head.pack(fill="x")
        titles = tk.Frame(head, background=theme["bg_app"])
        titles.pack(side="left", fill="x", expand=True)
        tk.Label(titles, text="New project", background=theme["bg_app"],
                 foreground=theme["text_primary"], font=FONTS["page_title"], anchor="w").pack(anchor="w")
        tk.Label(titles, text="Start with an Unreal project configured for Convai.",
                 background=theme["bg_app"], foreground=theme["text_secondary"], font=FONTS["body"],
                 anchor="w", justify="left", wraplength=WRAP).pack(anchor="w", pady=(4, 0))
        self.chip_host = tk.Frame(head, background=theme["bg_app"])
        self.chip_host.pack(side="right", anchor="n", pady=(6, 0))

        self.stepper = StepIndicator(column, STEPS)
        self.stepper.frame.pack(anchor="w", pady=(SPACE["section"], SPACE["tight"] * 2))

        self.body = tk.Frame(column, background=theme["bg_app"])
        self.body.pack(fill="x")
        self.render()

        # A Create the sign-in modal interrupted, resumed once. Deferred, because
        # `_create` swaps the page out from under this build.
        if self.state.pop("create", False):
            self.body.after(0, self._resume_create)

    def render(self) -> None:
        if not self.body.winfo_exists():
            return
        for child in self.body.winfo_children():
            child.destroy()
        for child in self.chip_host.winfo_children():
            child.destroy()

        step = self.state["step"]
        self.stepper.set_current(step)
        pill(self.chip_host, f"Step {step + 1} of 3", tone="neutral", dot=False).pack()

        outer, inner = card(self.body)
        outer.pack(fill="x")
        (self._build_details, self._build_type, self._build_engine)[step](inner)

    def on_account_changed(self) -> None:
        self.render()

    # --- step 1: project details -------------------------------------------

    def _build_details(self, parent: tk.Frame) -> None:
        self._section(parent, "Project details")

        self.name_var = tk.StringVar(value=self.state["name"])
        self.name_var.trace_add("write", self._on_name_typed)
        self.name_field = Field(parent, "Project name", self.name_var,
                                help_text="Letters, digits, and underscores only.",
                                surface="bg_surface")
        self.name_field.pack(fill="x")
        self.name_field.entry.bind("<FocusOut>", self._on_name_blur, add="+")
        self.name_field.entry.bind("<Return>", lambda event: self._continue_details(), add="+")

        if self.pending_error:
            self.name_field.set_error(self.pending_error)
            self.pending_error = None

        self._account_note(parent)

        actions = self._actions(parent)
        button(actions, "Cancel", self.app.show_shelf).pack(side="right", padx=(SPACE["tight"], 0))
        button(actions, "Continue", self._continue_details, kind="primary",
               accessible_name="Continue to project type").pack(side="right")

        self.name_field.focus()

    def _account_note(self, parent: tk.Frame) -> None:
        """Reassurance, not a credential field: the key never appears in the UI."""
        if self.app.account.is_signed_in:
            who = self.app.account.display_name or "your Convai account"
            tone, title = "ok", "Signed in with Convai"
            detail = (f"This project will be created with {who}. Change accounts from the profile "
                      "menu beside Settings.")
        else:
            tone, title = "warn", "Sign in to continue"
            detail = "Creating a project needs a Convai account. Continue and we'll ask you to sign in."

        background, border, foreground = (theme[f"{tone}_soft"], theme[f"{tone}_soft_border"],
                                          theme[f"{tone}_soft_text"])
        frame = tk.Frame(parent, background=background, highlightbackground=border,
                         highlightthickness=1, padx=12, pady=10)
        frame.pack(fill="x", pady=(SPACE["tight"] * 2, 0))
        tk.Label(frame, text=title, background=background, foreground=foreground,
                 font=FONTS["meta_strong"], anchor="w").pack(anchor="w")
        tk.Label(frame, text=detail, background=background, foreground=foreground,
                 font=FONTS["meta"], anchor="w", justify="left",
                 wraplength=WRAP - 24).pack(anchor="w", pady=(3, 0))

    def _on_name_typed(self, *_args) -> None:
        if self.name_var is None:
            return
        self.state["name"] = self.name_var.get()
        if self.name_blurred and self.name_field is not None and self.name_field.entry.winfo_exists():
            self.name_field.set_error(self._name_problem())

    def _on_name_blur(self, _event=None) -> None:
        self.name_blurred = True
        if self.name_field is not None and self.name_field.entry.winfo_exists():
            self.name_field.set_error(self._name_problem())

    def _name_problem(self) -> Optional[str]:
        return InputManager.validate_project_name(
            self.state["name"].strip(), self.app.input_manager.get_script_dir())

    def _continue_details(self) -> None:
        problem = self._name_problem()
        self.name_blurred = True
        if problem:
            if self.name_field is not None:
                self.name_field.set_error(problem)
                self.name_field.focus()
            return
        # The resume carries the intent, not just the values: the name has already
        # passed validation here, so signing in lands on the step Continue asked for
        # instead of throwing the click away.
        if not self.app.require_account(lambda: self.app.show_new_project({**self.state, "step": 1})):
            return
        self._go(1)

    # --- step 2: project type ----------------------------------------------

    def _build_type(self, parent: tk.Frame) -> None:
        self._section(parent, "What are you creating?",
                      "Choose the starting point that best fits your project.")

        # Fresh variables each render: a ChoiceTile traces the variable it is given, and
        # a trace outliving its destroyed tile would fire against dead widgets.
        self.type_var = tk.StringVar(value=self.state["type"])
        self.metahuman_var = tk.BooleanVar(value=bool(self.state["metahuman"]))

        tiles = tk.Frame(parent, background=theme["bg_surface"])
        tiles.pack(fill="x")
        for column, (title, description, value) in enumerate((
                ("Scene", "Environment or gameplay project.", "Scene"),
                ("Avatar", "Character project with an interactive persona.", "Avatar"))):
            tile = ChoiceTile(tiles, title, description, value, self.type_var, on_select=self._on_type)
            tile.frame.grid(row=0, column=column, sticky="nsew",
                            padx=(0, SPACE["tight"]) if column == 0 else 0)
            tiles.grid_columnconfigure(column, weight=1, uniform="tile")

        # Creation order, not pack order, is what Tk tabs through: the MetaHuman row is
        # built first so a keyboard user reaches it before Back/Continue, and packed with
        # `before=` so re-showing it on Avatar cannot land it under the buttons.
        self.metahuman_row = tk.Frame(parent, background=theme["bg_surface"])
        ttk.Checkbutton(self.metahuman_row, text="This is a MetaHuman avatar",
                        variable=self.metahuman_var, command=self._on_metahuman).pack(anchor="w")
        tk.Label(self.metahuman_row,
                 text="Adds the MetaHuman-specific setup so the character's face, body and animation "
                      "blueprints work with Convai.",
                 background=theme["bg_surface"], foreground=theme["text_secondary"], font=FONTS["meta"],
                 anchor="w", justify="left", wraplength=WRAP - 24).pack(anchor="w", pady=(4, 0), padx=(24, 0))

        self.type_actions = self._actions(parent)
        button(self.type_actions, "Back", lambda: self._go(0)).pack(side="left")
        button(self.type_actions, "Continue", lambda: self._go(2), kind="primary",
               accessible_name="Continue to Unreal Engine").pack(side="right")

        self._sync_metahuman()

    def _on_type(self, value: str) -> None:
        self.state["type"] = value
        self._sync_metahuman()

    def _on_metahuman(self) -> None:
        self.state["metahuman"] = bool(self.metahuman_var.get())

    def _sync_metahuman(self) -> None:
        """MetaHuman is an Avatar-only choice; leaving Avatar unsets it."""
        if self.state["type"] == "Avatar":
            self.metahuman_row.pack(fill="x", pady=(SPACE["tight"] * 2, 0), before=self.type_actions)
        else:
            self.metahuman_row.pack_forget()
            self.state["metahuman"] = False
            if self.metahuman_var is not None:
                self.metahuman_var.set(False)

    # --- step 3: unreal engine ----------------------------------------------

    def _build_engine(self, parent: tk.Frame) -> None:
        self._section(parent, "Unreal Engine setup",
                      "Confirm the Unreal Engine installation for this project.")

        version = self.app.engine_version("current")
        path, valid = self._engine()

        if valid:
            self._engine_card(parent, "ok", f"Unreal Engine {version} detected",
                              ellipsise(path, 58), path, ("Choose folder", "quiet"))
        else:
            # Nothing detected is not the user's mistake yet, so this states the
            # requirement and offers the fix rather than reporting an error.
            self._engine_card(parent, "warn", f"Unreal Engine {version} is required",
                              f"Choose the folder where Unreal Engine {version} is installed. "
                              "The tool needs it to create and build the project.",
                              "", ("Choose folder", "primary"))

        self._summary(parent, version)

        actions = self._actions(parent)
        button(actions, "Back", lambda: self._go(1)).pack(side="left")
        create = button(actions, "Create project", self._create, kind="primary",
                        accessible_name=f"Create {self.state['name'].strip() or 'project'}")
        create.pack(side="right")
        set_button_state(create, valid)
        if not valid:
            tk.Label(actions, text=f"Choose an Unreal Engine {version} folder to continue.",
                     background=theme["bg_surface"], foreground=theme["text_secondary"],
                     font=FONTS["meta"], anchor="e", justify="right",
                     wraplength=WRAP - 220).pack(side="right", padx=(0, SPACE["tight"]))

    def _engine_card(self, parent: tk.Frame, tone: str, title: str, detail: str,
                     tooltip: str, action: tuple[str, str]) -> None:
        background, border, foreground = (theme[f"{tone}_soft"], theme[f"{tone}_soft_border"],
                                          theme[f"{tone}_soft_text"])
        frame = tk.Frame(parent, background=background, highlightbackground=border,
                         highlightthickness=1, padx=14, pady=12)
        frame.pack(fill="x")

        label, kind = action
        button(frame, label, self._choose_engine, kind=kind, compact=True,
               accessible_name=f"Choose the Unreal Engine {self.app.engine_version('current')} folder",
               ).pack(side="right", padx=(SPACE["tight"], 0))

        text = tk.Frame(frame, background=background)
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text=title, background=background, foreground=theme["text_primary"],
                 font=FONTS["body_strong"], anchor="w", justify="left",
                 wraplength=WRAP - 170).pack(anchor="w")
        detail_label = tk.Label(text, text=detail, background=background, foreground=foreground,
                                font=FONTS["meta"], anchor="w", justify="left", wraplength=WRAP - 170)
        detail_label.pack(anchor="w", pady=(3, 0))
        if tooltip:
            Tooltip(detail_label, tooltip)

    def _summary(self, parent: tk.Frame, version: str) -> None:
        frame = tk.Frame(parent, background=theme["bg_field"], padx=14, pady=12)
        frame.pack(fill="x", pady=(SPACE["tight"] * 2, 0))
        tk.Label(frame, text="Project summary", background=theme["bg_field"],
                 foreground=theme["text_primary"], font=FONTS["body_strong"],
                 anchor="w").pack(anchor="w", pady=(0, SPACE["tight"]))

        grid = tk.Frame(frame, background=theme["bg_field"])
        grid.pack(fill="x")
        grid.grid_columnconfigure(0, minsize=110)
        grid.grid_columnconfigure(1, weight=1)

        rows = [("Project", self.state["name"].strip() or "Not named yet"),
                ("Type", self.state["type"])]
        if self.state["type"] == "Avatar":
            rows.append(("MetaHuman", "Included" if self.state["metahuman"] else "Not included"))
        rows.append(("Engine", f"Unreal Engine {version}"))

        for index, (label, value) in enumerate(rows):
            tk.Label(grid, text=label, background=theme["bg_field"], foreground=theme["text_primary"],
                     font=FONTS["meta_strong"], anchor="w").grid(row=index, column=0, sticky="w", pady=2)
            tk.Label(grid, text=value, background=theme["bg_field"], foreground=theme["text_secondary"],
                     font=FONTS["meta"], anchor="w", justify="left", wraplength=WRAP - 140,
                     ).grid(row=index, column=1, sticky="w", padx=(12, 0), pady=2)

    def _engine(self) -> tuple[str, bool]:
        path = self.state.get("engine") or self.app.engine_path("current") or ""
        self.state["engine"] = path
        return path, bool(path) and self.app.is_valid_engine(path, "current")

    def _choose_engine(self) -> None:
        chosen = self.app.choose_engine("current")
        if chosen:
            self.state["engine"] = chosen
            self.render()

    # --- create -------------------------------------------------------------

    def _resume_create(self) -> None:
        if self.body.winfo_exists() and self.app.screen is self:
            self._create()

    def _create(self) -> None:
        path, valid = self._engine()
        if not valid:
            return

        name = self.state["name"].strip()
        problem = InputManager.validate_project_name(name, self.app.input_manager.get_script_dir())
        if problem:
            # The name passed at step 1; a folder of that name can appear beside the
            # tool in between.
            self.pending_error = problem
            self.name_blurred = True
            self._go(0)
            return

        if not self.app.require_account(lambda: self.app.show_new_project({**self.state, "create": True})):
            return

        manager = self.app.input_manager
        manager.reset()
        manager.project_name = name
        manager.convai_api_key = self.app.account.api_key
        manager.asset_type = self.state["type"]
        manager.is_metahuman = bool(self.state["metahuman"])
        manager.unreal_engine_path = path

        project_dir = os.path.join(str(manager.get_script_dir()), name)
        self.app.show_run(f"Creating {name}", self.app.flows["create"], project_dir,
                          steps=list(CREATE_STEPS))

    # --- shared bits --------------------------------------------------------

    def _go(self, step: int) -> None:
        self.state["step"] = step
        self.render()

    @staticmethod
    def _section(parent: tk.Frame, title: str, intro: str = "") -> None:
        tk.Label(parent, text=title, background=theme["bg_surface"], foreground=theme["text_primary"],
                 font=FONTS["section_title"], anchor="w").pack(anchor="w", pady=(0, SPACE["tight"] * 2))
        if intro:
            tk.Label(parent, text=intro, background=theme["bg_surface"],
                     foreground=theme["text_secondary"], font=FONTS["body"], anchor="w",
                     justify="left", wraplength=WRAP).pack(anchor="w", pady=(0, SPACE["tight"] * 2))

    @staticmethod
    def _actions(parent: tk.Frame) -> tk.Frame:
        row = tk.Frame(parent, background=theme["bg_surface"])
        row.pack(fill="x", pady=(SPACE["section"], 0))
        return row
