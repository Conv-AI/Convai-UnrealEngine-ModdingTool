"""The project shelf: the list of projects beside the tool and what can be done to one.

The list and the inspector are two views of the same selection, so every action names
the project it will act on before it starts. Nothing here decides whether an operation
is possible -- that comes from the scan and from ``App`` -- and an action that cannot
run stays visible with its reason in text beside it.
"""

from __future__ import annotations

import threading
import tkinter as tk
from typing import Optional

from gui.components import (ProjectRow, Tooltip, banner, button, card, pill,
                            set_button_state)
from gui.theme import FONTS, NARROW_WIDTH, SPACE, theme

SIGNED_OUT = "Sign in to create or manage Convai projects."
UPDATE_HELP = "Updates Convai plugins and project settings. Your content stays in place."
MIGRATE_HELP = "Creates a copy beside this one. The original project is not changed."
DISCOVERY = "Projects are discovered beside this tool"


class ShelfScreen:
    """Home: search and select a project, then update or migrate it."""

    shortcut_new = True

    def __init__(self, app, select_path: Optional[str] = None):
        self.app = app
        self.select_path = select_path
        self.projects: list[dict] = []
        self.rows: list[ProjectRow] = []
        self.selected: Optional[dict] = None
        self.scanned = False
        self.scanning = False
        self.scan_error: Optional[str] = None
        self.narrow: Optional[bool] = None
        self.query = tk.StringVar()
        self.refresh_buttons: list[tk.Button] = []

    # --- build --------------------------------------------------------------

    def build(self, parent: tk.Frame) -> None:
        self.parent = parent
        self.app.shell.set_status(right=DISCOVERY)

        self._build_title(parent)

        self.banner_host = tk.Frame(parent, background=theme["bg_app"])
        self.banner_host.pack(fill="x")
        self._render_banner()

        body = tk.Frame(parent, background=theme["bg_app"])
        body.pack(fill="both", expand=True, pady=(SPACE["section"], 0))

        self.columns = tk.Frame(body, background=theme["bg_app"])
        self.empty = tk.Frame(body, background=theme["bg_app"])
        self._build_panels()
        self._build_empty()
        self._layout(self.app.root.winfo_width() < NARROW_WIDTH)
        self.columns.pack(fill="both", expand=True)

        # The trace's callback is held by the Tk interpreter, not by the variable, so
        # it outlives the screen too until it is removed.
        self._query_trace = self.query.trace_add("write", lambda *_: self._on_query())
        # The root outlives the screen, so this binding has to go when the page does or
        # every rebuild leaves another handler -- and another whole screen -- behind.
        # Unbinding by funcid removes only this one; unbind("<Configure>") alone would
        # take the shell's own resize handler with it.
        self._resize_id = self.app.root.bind("<Configure>", self._on_resize, add="+")
        parent.bind("<Destroy>", self._on_destroy, add="+")

        self._render_list()
        self._render_inspector()
        self._rescan()

    def _build_title(self, parent: tk.Frame) -> None:
        row = tk.Frame(parent, background=theme["bg_app"])
        row.pack(fill="x", pady=(0, SPACE["section"]))

        text = tk.Frame(row, background=theme["bg_app"])
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text="Projects", background=theme["bg_app"],
                 foreground=theme["text_primary"], font=FONTS["page_title"],
                 anchor="w").pack(anchor="w")
        tk.Label(text, text="Create, update, and migrate the Unreal projects beside this tool.",
                 background=theme["bg_app"], foreground=theme["text_secondary"],
                 font=FONTS["body"], anchor="w", justify="left",
                 wraplength=560).pack(anchor="w", pady=(4, 0))

        new_btn = button(row, "+ New project", self._new_project, kind="primary")
        new_btn.pack(side="right")
        refresh = button(row, "Refresh", self._rescan, kind="quiet",
                         accessible_name="Rescan the folder beside this tool")
        refresh.pack(side="right", padx=(0, SPACE["tight"]))
        self.refresh_buttons = [refresh]

    def _build_panels(self) -> None:
        self.list_panel, list_inner = card(self.columns)
        head = tk.Frame(list_inner, background=theme["bg_surface"])
        head.pack(fill="x")
        self.count = tk.Label(head, text="PROJECTS", background=theme["bg_surface"],
                              foreground=theme["text_secondary"], font=FONTS["meta_strong"])
        self.count.pack(side="left")

        box = tk.Frame(list_inner, background=theme["bg_field"],
                       highlightbackground=theme["border_subtle"], highlightthickness=1,
                       highlightcolor=theme["border_focus"])
        box.pack(fill="x", pady=(SPACE["tight"], SPACE["tight"]))
        self.search = tk.Entry(box, textvariable=self.query, font=FONTS["body"],
                               background=theme["bg_field"], foreground=theme["text_primary"],
                               insertbackground=theme["text_primary"], relief="flat",
                               highlightthickness=0)
        self.search.pack(fill="x", padx=10, pady=8)
        # Tk has no placeholder: a label over the empty entry, hidden once it has text.
        self.hint = tk.Label(box, text="Search projects…", background=theme["bg_field"],
                             foreground=theme["text_disabled"], font=FONTS["body"])
        self.hint.place(in_=self.search, x=0, rely=0.5, anchor="w")
        self.hint.bind("<Button-1>", lambda event: self.search.focus_set(), add="+")
        self.search.bind("<Down>", lambda event: self._move(1), add="+")
        self.search.bind("<Up>", lambda event: self._move(-1), add="+")
        self.search.bind("<Return>", lambda event: self._update(), add="+")

        self.rows_host = tk.Frame(list_inner, background=theme["bg_surface"])
        self.rows_host.pack(fill="both", expand=True)

        self.inspector_panel, inspector_inner = card(self.columns)
        tk.Label(inspector_inner, text="SELECTED PROJECT", background=theme["bg_surface"],
                 foreground=theme["text_secondary"], font=FONTS["meta_strong"]).pack(anchor="w")
        self.inspector = tk.Frame(inspector_inner, background=theme["bg_surface"])
        self.inspector.pack(fill="both", expand=True, pady=(SPACE["tight"], 0))

    def _build_empty(self) -> None:
        outer, inner = card(self.empty, padding=32)
        outer.pack(pady=(48, 0))
        tk.Label(inner, text="No modding projects here yet", background=theme["bg_surface"],
                 foreground=theme["text_primary"], font=FONTS["section_title"]).pack()
        tk.Label(inner, text="The tool lists the Unreal projects that sit in the same folder as "
                             "this tool. Create one and it appears here.",
                 background=theme["bg_surface"], foreground=theme["text_secondary"],
                 font=FONTS["body"], wraplength=380, justify="center").pack(pady=(8, 20))
        actions = tk.Frame(inner, background=theme["bg_surface"])
        actions.pack()
        button(actions, "Create a project", self._new_project, kind="primary").pack(side="left")
        refresh = button(actions, "Refresh", self._rescan, kind="quiet")
        refresh.configure(background=theme["bg_surface"], highlightbackground=theme["bg_surface"])
        refresh.pack(side="left", padx=(SPACE["tight"], 0))
        self.empty_refresh = refresh

    # --- layout -------------------------------------------------------------

    def _layout(self, narrow: bool) -> None:
        """55/45 side by side, or the inspector stacked below the list."""
        self.narrow = narrow
        self.list_panel.grid_forget()
        self.inspector_panel.grid_forget()
        gap = SPACE["section"]
        if narrow:
            self.columns.grid_columnconfigure(0, weight=1, uniform="")
            self.columns.grid_columnconfigure(1, weight=0, uniform="")
            self.list_panel.grid(row=0, column=0, sticky="nsew")
            self.inspector_panel.grid(row=1, column=0, sticky="new", pady=(gap, 0))
        else:
            # A shared uniform group makes the weights literal widths, not just a
            # share of the leftover space.
            self.columns.grid_columnconfigure(0, weight=55, uniform="shelf")
            self.columns.grid_columnconfigure(1, weight=45, uniform="shelf")
            self.list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, gap))
            self.inspector_panel.grid(row=0, column=1, sticky="new")
        self.columns.grid_rowconfigure(0, weight=1)

    def _on_resize(self, event) -> None:
        if event.widget is not self.app.root or not self.columns.winfo_exists():
            return
        narrow = event.width < NARROW_WIDTH
        if narrow != self.narrow:
            self._layout(narrow)

    def _on_destroy(self, event) -> None:
        # Every child reports its own <Destroy>; the screen ends when the page frame goes.
        if event.widget is self.parent:
            self.app.root.unbind("<Configure>", self._resize_id)
            self.query.trace_remove("write", self._query_trace)

    # --- rendering ----------------------------------------------------------

    def _render_banner(self) -> None:
        for child in self.banner_host.winfo_children():
            child.destroy()
        if self.app.account.is_signed_in:
            return
        banner(self.banner_host, SIGNED_OUT, tone="warn",
               action=("Sign in", self.app.open_account)).pack(fill="x")

    def _render(self) -> None:
        """Either the two panels or the empty surface, never both."""
        if self.scanned and not self.projects and not self.scan_error:
            self.columns.pack_forget()
            self.empty.pack(fill="both", expand=True)
            return
        self.empty.pack_forget()
        if not self.columns.winfo_ismapped():
            self.columns.pack(fill="both", expand=True)
        self._render_list()
        self._render_inspector()

    def _render_list(self) -> None:
        for child in self.rows_host.winfo_children():
            child.destroy()
        self.rows = []

        query = self.query.get().strip().lower()
        matches = [p for p in self.projects if query in p["name"].lower()]
        self.count.configure(text=f"PROJECTS ({len(matches)})")

        if self.scan_error:
            self._placeholder(f"Couldn't read the folder beside this tool: {self.scan_error}",
                              colour="danger", action=("Try again", self._rescan))
            return
        if not self.scanned:
            self._placeholder("Looking for projects…")
            return
        if not matches:
            self._placeholder(f"No projects match “{self.query.get().strip()}”.",
                              action=("Clear search", lambda: self.query.set("")))
            return

        if self.selected is None or self.selected["dir"] not in [p["dir"] for p in matches]:
            self.selected = matches[0]

        for project in matches:
            row = ProjectRow(self.rows_host, project, on_select=self._select,
                             on_activate=self._update)
            row.frame.pack(fill="x", pady=(0, 1))
            row.frame.bind("<Down>", lambda event: self._move(1), add="+")
            row.frame.bind("<Up>", lambda event: self._move(-1), add="+")
            row.set_selected(project["dir"] == self.selected["dir"])
            self.rows.append(row)

    def _placeholder(self, text: str, colour: str = "text_secondary",
                     action: Optional[tuple] = None) -> None:
        frame = tk.Frame(self.rows_host, background=theme["bg_surface"])
        frame.pack(fill="x", pady=(SPACE["tight"], 0))
        tk.Label(frame, text=text, background=theme["bg_surface"], foreground=theme[colour],
                 font=FONTS["body"], wraplength=380, justify="left",
                 anchor="w").pack(anchor="w")
        if action:
            label, command = action
            clear = button(frame, label, command, kind="quiet", compact=True)
            clear.configure(background=theme["bg_surface"], highlightbackground=theme["bg_surface"])
            clear.pack(anchor="w", pady=(SPACE["tight"], 0))

    def _render_inspector(self) -> None:
        for child in self.inspector.winfo_children():
            child.destroy()
        project = self.selected
        if project is None:
            tk.Label(self.inspector, text="Select a project to see what you can do with it.",
                     background=theme["bg_surface"], foreground=theme["text_secondary"],
                     font=FONTS["body"], wraplength=320, justify="left",
                     anchor="w").pack(anchor="w")
            return

        title = tk.Frame(self.inspector, background=theme["bg_surface"])
        title.pack(fill="x")
        tk.Label(title, text=project["name"], background=theme["bg_surface"],
                 foreground=theme["text_primary"], font=FONTS["section_title"],
                 wraplength=260, justify="left", anchor="w").pack(side="left")
        if project["type"]:
            pill(title, project["type"], tone="neutral", dot=False).pack(side="left", padx=(8, 0))

        meta = tk.Frame(self.inspector, background=theme["bg_surface"])
        meta.pack(fill="x", pady=(6, 0))
        engine = f"UE {project['ue']}" if project["ue"] else "Engine version not detected"
        tk.Label(meta, text=engine, background=theme["bg_surface"],
                 foreground=theme["text_secondary" if project["ue"] else "warning"],
                 font=FONTS["meta"]).pack(side="left")
        tk.Label(meta, text="·", background=theme["bg_surface"],
                 foreground=theme["text_disabled"], font=FONTS["meta"]).pack(side="left", padx=6)
        signed_in = self.app.account.is_signed_in
        tk.Label(meta, text="Connected" if signed_in else "Sign in to manage",
                 background=theme["bg_surface"],
                 foreground=theme["accent" if signed_in else "warning"],
                 font=FONTS["meta"]).pack(side="left")

        self._render_path(project["dir"])

        actions = tk.Frame(self.inspector, background=theme["bg_surface"])
        actions.pack(fill="x", pady=(SPACE["section"], 0))
        update = button(actions, "Update project", lambda: self._update(project), kind="primary",
                        accessible_name=f"Update {project['name']}")
        update.pack(anchor="w")
        self._helper(actions, UPDATE_HELP)

        target = project["target"]
        reason = self._migrate_reason(project)
        migrate = button(actions, f"Migrate to UE {target}", lambda: self._migrate(project),
                         accessible_name=reason or f"Migrate {project['name']} to UE {target}")
        migrate.pack(anchor="w", pady=(SPACE["section"], 0))
        set_button_state(migrate, not reason)
        self._helper(actions, reason or MIGRATE_HELP, colour="warning" if reason else "text_secondary")

    def _render_path(self, path: str) -> None:
        box = tk.Frame(self.inspector, background=theme["bg_field"],
                       highlightbackground=theme["border_subtle"], highlightthickness=1)
        box.pack(fill="x", pady=(SPACE["tight"] + 4, 0))
        # The entry holds the whole path even when the panel is too narrow to show it,
        # so a selection copied out of it is never a truncated path.
        entry = tk.Entry(box, font=FONTS["meta"], background=theme["bg_field"],
                         foreground=theme["text_secondary"], readonlybackground=theme["bg_field"],
                         relief="flat", highlightthickness=0, width=1)
        entry.insert(0, path)
        entry.configure(state="readonly")
        entry.pack(fill="x", padx=10, pady=8)
        Tooltip(entry, path)

        copy = button(self.inspector, "Copy path", lambda: self._copy_path(path, copy),
                      kind="quiet", compact=True, accessible_name=f"Copy the path to {path}")
        copy.configure(background=theme["bg_surface"], highlightbackground=theme["bg_surface"])
        copy.pack(anchor="w", pady=(4, 0))

    @staticmethod
    def _helper(parent: tk.Misc, text: str, colour: str = "text_secondary") -> None:
        tk.Label(parent, text=text, background=theme["bg_surface"], foreground=theme[colour],
                 font=FONTS["meta"], wraplength=320, justify="left",
                 anchor="w").pack(anchor="w", pady=(6, 0))

    def _migrate_reason(self, project: dict) -> str:
        """Empty when migration can run; otherwise the sentence shown beside the button."""
        target = project["target"]
        if not project["ue"]:
            return "Migration is unavailable: this project's engine version was not detected."
        if not project["migratable"]:
            return f"Migration is unavailable: this project already uses UE {target}."
        if self.app.engine_path("target") is None:
            return f"Choose a UE {target} installation in Settings."
        return ""

    # --- selection ----------------------------------------------------------

    def _select(self, project: dict, scroll: bool = False) -> None:
        self.selected = project
        for row in self.rows:
            row.set_selected(row.project["dir"] == project["dir"])
            if scroll and row.project["dir"] == project["dir"]:
                self._scroll_into_view(row.frame)
        self._render_inspector()

    def _move(self, delta: int) -> str:
        if not self.rows:
            return "break"
        paths = [row.project["dir"] for row in self.rows]
        current = paths.index(self.selected["dir"]) if self.selected and self.selected["dir"] in paths else None
        index = 0 if current is None else max(0, min(len(paths) - 1, current + delta))
        row = self.rows[index]
        self._select(row.project, scroll=True)
        row.frame.focus_set()
        return "break"

    def _scroll_into_view(self, widget: tk.Misc) -> None:
        canvas = self.app.shell.canvas
        page = self.app.shell.page
        if not widget.winfo_exists() or not canvas.winfo_exists():
            return
        canvas.update_idletasks()
        total = max(page.winfo_height(), 1)
        top = widget.winfo_rooty() - page.winfo_rooty()
        bottom = top + widget.winfo_height()
        view_top = canvas.canvasy(0)
        view_height = canvas.winfo_height()
        if top < view_top:
            canvas.yview_moveto(max(0.0, top / total))
        elif bottom > view_top + view_height:
            canvas.yview_moveto(max(0.0, (bottom - view_height) / total))

    def _on_query(self) -> None:
        if self.query.get():
            self.hint.place_forget()
        else:
            self.hint.place(in_=self.search, x=0, rely=0.5, anchor="w")
        self._render_list()
        self._render_inspector()

    # --- actions ------------------------------------------------------------

    def _new_project(self) -> None:
        if self.app.require_account(self._new_project):
            self.app.show_new_project()

    def _update(self, project: Optional[dict] = None) -> None:
        project = project or self.selected
        if not project:
            return
        # Signing in from here resumes the same review, so no work is lost and the
        # failure never arrives halfway through a run.
        if self.app.require_account(lambda: self._update(project)):
            self.app.show_review("update", project)

    def _migrate(self, project: Optional[dict] = None) -> None:
        project = project or self.selected
        if not project or self._migrate_reason(project):
            return
        if self.app.require_account(lambda: self._migrate(project)):
            self.app.show_review("migrate", project)

    def _copy_path(self, path: str, widget: tk.Button) -> None:
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(path)
        widget.configure(text="Copied")
        self.app.root.after(1500, lambda: widget.winfo_exists() and widget.configure(text="Copy path"))

    # --- scanning -----------------------------------------------------------

    def _rescan(self) -> None:
        """Rescan on a worker: the scan walks the filesystem beside the tool."""
        if self.scanning:
            return
        self.scanning = True
        self._set_refreshing(True)
        keep = self.selected["dir"] if self.selected else self.select_path

        def work() -> None:
            try:
                found, error = self.app.scan_projects(), None
            except Exception as exc:
                found, error = [], str(exc)
            self.app.root.after(0, lambda: self._scanned(found, error, keep))

        threading.Thread(target=work, daemon=True).start()

    def _set_refreshing(self, busy: bool) -> None:
        buttons = [b for b in (*self.refresh_buttons, getattr(self, "empty_refresh", None))
                   if b is not None and b.winfo_exists()]
        for widget in buttons:
            widget.configure(text="Refreshing…" if busy else "Refresh")
            set_button_state(widget, not busy)

    def _scanned(self, found: list[dict], error: Optional[str], keep: Optional[str]) -> None:
        if not self.parent.winfo_exists():
            return
        self.scanning = False
        self.scanned = True
        self.projects = found
        self.scan_error = error
        self.selected = next((p for p in found if p["dir"] == keep), None) or (found[0] if found else None)
        self._set_refreshing(False)
        self._render()
        if self.select_path and self.selected and self.selected["dir"] == self.select_path:
            self.app.root.after_idle(
                lambda: self.parent.winfo_exists() and self._select(self.selected, scroll=True))
        self.select_path = None

    # --- account ------------------------------------------------------------

    def on_account_changed(self) -> None:
        self._render_banner()
        self._render_inspector()

    def on_engine_changed(self) -> None:
        """Only the inspector reads the engine, and rebuilding the screen would throw
        away the user's search and cost another filesystem scan."""
        self._render_inspector()
