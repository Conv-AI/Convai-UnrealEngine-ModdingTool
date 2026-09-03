"""The project shelf: boot, blocked, shelf, new project, run and settings screens."""

from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import threading
import tkinter as tk
import traceback
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Optional

from core.config_manager import config
from core.exceptions import ConvaiToolError
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.logger import logger
from core.unreal_engine_manager import UnrealEngineManager
from gui.theme import apply_styles, theme, widgets

ICON_PATH = Path(__file__).resolve().parent.parent / "resources" / "Convai.ico"


def _label(parent: tk.Misc, text: str, colour: str = "text",
           font: tuple = ("Segoe UI", 10), bg: str = "bg_dark", **kwargs) -> ttk.Label:
    """A label with explicit colours: the shared ttk styles are per-background, not per-role."""
    return ttk.Label(parent, text=text, background=theme[bg], foreground=theme[colour], font=font, **kwargs)


class App:
    """One window showing one screen at a time.

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
        self.log_handler: Optional[logging.Handler] = None
        self.log_queue: Optional[queue.Queue] = None
        self.log_after: Optional[str] = None
        self.run_folder: Optional[str] = None
        self.projects: list[dict] = []

        root.title("Convai Modding Tool")
        root.minsize(600, 440)
        root.configure(bg=theme["bg_dark"])
        apply_styles(root)
        if ICON_PATH.exists():
            root.iconbitmap(str(ICON_PATH))
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.content = ttk.Frame(root, style="TFrame")
        self.content.pack(fill="both", expand=True)

    # --- screen plumbing ----------------------------------------------------

    def _show(self, builder: Callable[[ttk.Frame], None]) -> ttk.Frame:
        for child in self.content.winfo_children():
            child.destroy()
        frame = ttk.Frame(self.content, style="TFrame")
        frame.pack(fill="both", expand=True, padx=18, pady=16)
        builder(frame)
        return frame

    def _on_close(self) -> None:
        if self.running and not messagebox.askyesno(
                "Convai Modding Tool", "A run is in progress. Quit anyway?"):
            return
        self.root.destroy()

    # --- boot ---------------------------------------------------------------

    def show_boot(self) -> None:
        self._show(self._build_boot)
        # The window has to be on screen before the config fetch starts: it retries
        # for minutes when GitHub is unreachable.
        self.root.after(50, self._start_boot)

    def _build_boot(self, parent: ttk.Frame) -> None:
        _label(parent, "Convai Modding Tool", font=("Segoe UI Semibold", 16)).pack(pady=(70, 8))
        _label(parent, "Checking for updates...", colour="text_muted").pack()
        bar = ttk.Progressbar(parent, mode="indeterminate")
        bar.pack(fill="x", padx=60, pady=24)
        bar.start(12)

    def _start_boot(self) -> None:
        def work() -> None:
            try:
                config.load()
                from core.version_manager import VersionManager
                up_to_date = VersionManager.check_version(self.tool_version)
            except Exception as exc:
                self.root.after(0, lambda message=str(exc): self.show_blocked(message))
                return

            if up_to_date:
                self.root.after(0, self.show_shelf)
            else:
                self.root.after(0, lambda: self.show_blocked(
                    "Your version is outdated. Please update to continue.", outdated=True))

        threading.Thread(target=work, daemon=True).start()

    def show_blocked(self, message: str, outdated: bool = False) -> None:
        """Boot failed. Only an outdated tool can be fixed by downloading one."""
        self._show(lambda parent: self._build_blocked(parent, message, outdated))

    def _build_blocked(self, parent: ttk.Frame, message: str, outdated: bool) -> None:
        _label(parent, "Update required" if outdated else "Cannot start", colour="warning",
               font=("Segoe UI Semibold", 15)).pack(pady=(60, 10))
        _label(parent, message, colour="text_muted",
               wraplength=460, justify="center").pack()

        row = ttk.Frame(parent, style="TFrame")
        row.pack(pady=24)
        if outdated:
            widgets.create_button(row, "Download", self._open_download, style="accent").pack(side="left", padx=6)
        widgets.create_button(row, "Retry", self.show_boot).pack(side="left", padx=6)
        widgets.create_button(row, "Quit", self.root.destroy).pack(side="left", padx=6)

    @staticmethod
    def _open_download() -> None:
        from core.version_manager import LATEST_RELEASE_URL
        webbrowser.open(LATEST_RELEASE_URL, new=2)

    # --- shelf --------------------------------------------------------------

    def show_shelf(self) -> None:
        self._show(self._build_shelf)

    def _scan_projects(self) -> list[dict]:
        """Every modding project beside the tool, re-read on each call."""
        entries = []
        for project_dir in self.input_manager.find_existing_projects():
            metadata = FileUtilityManager.get_metadata(project_dir)
            folder = os.path.basename(project_dir.rstrip("\\/"))
            # The folder is a project because the scan found a .uproject in it; the metadata
            # name is only a guess at what that file is called, and a legacy project has none.
            uproject = next(Path(project_dir).glob("*.uproject"), None)
            version = UnrealEngineManager._get_project_engine_version(str(uproject)) if uproject else None
            entries.append({
                "dir": project_dir,
                "name": folder,
                "ue": version or "",
                "type": metadata.get("asset_type") or "",
                "api_key": metadata.get("api_key") or "",
            })
        return entries

    def _build_shelf(self, parent: ttk.Frame) -> None:
        header = ttk.Frame(parent, style="TFrame")
        header.pack(fill="x")
        _label(header, "Your projects", font=("Segoe UI Semibold", 14)).pack(side="left")
        widgets.create_button(header, "⚙", self.open_settings, width=3).pack(side="right")

        self.projects = self._scan_projects()

        body = ttk.Frame(parent, style="TFrame")
        body.pack(fill="both", expand=True, pady=(12, 12))
        self.tree = ttk.Treeview(body, columns=("project", "ue", "type"), show="headings",
                                 style="Custom.Treeview", height=8, selectmode="browse")
        for column, title, width in (("project", "Project", 300), ("ue", "UE", 70), ("type", "Type", 100)):
            self.tree.heading(column, text=title)
            self.tree.column(column, width=width, anchor="w")
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview, style="Vertical.TScrollbar")
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda event: self._on_select())

        for index, entry in enumerate(self.projects):
            self.tree.insert("", "end", iid=str(index), values=(entry["name"], entry["ue"], entry["type"]))

        if not self.projects:
            _label(parent, "No projects found next to the tool",
                   colour="text_muted").pack(anchor="w", pady=(0, 8))

        buttons = ttk.Frame(parent, style="TFrame")
        buttons.pack(fill="x")
        self.update_btn = widgets.create_button(buttons, "Update", self._on_update)
        self.update_btn.pack(side="left", padx=(0, 8))
        self.migrate_btn = widgets.create_button(buttons, "Migrate", self._on_migrate)
        self.migrate_btn.pack(side="left")
        widgets.create_button(buttons, "+ New...", self.show_new_project, style="accent").pack(side="right")
        self._on_select()

        footer = ttk.Frame(parent, style="TFrame")
        footer.pack(fill="x", pady=(14, 0))
        _label(footer, f"v{self.tool_version}", colour="text_muted",
               font=("Segoe UI", 9)).pack(side="left")

        version = config.get_current_unreal_engine_version()
        engine_path = self.input_manager.detect_engine_path("current")
        if engine_path:
            _label(footer, f"UE {version} · {engine_path}", colour="text_muted",
                   font=("Segoe UI", 9)).pack(side="right")
        else:
            _label(footer, f"UE {version} not found", colour="warning",
                   font=("Segoe UI", 9)).pack(side="right")

    def _selected(self) -> Optional[dict]:
        selection = self.tree.selection()
        return self.projects[int(selection[0])] if selection else None

    def _on_select(self) -> None:
        entry = self._selected()
        self.update_btn.configure(state="normal" if entry else "disabled")
        # Migrating a project that already sits on the target engine would only
        # copy it under a new name.
        migratable = bool(entry) and entry["ue"] != config.get_target_unreal_engine_version()
        self.migrate_btn.configure(state="normal" if migratable else "disabled")

    # --- engine paths -------------------------------------------------------

    def _resolve_engine(self, version_type: str) -> Optional[str]:
        """Find the engine before the worker starts; the flows can no longer ask."""
        if version_type == "target":
            cached = self.input_manager.target_unreal_engine_path
            is_valid = UnrealEngineManager.is_valid_target_engine_path
            wanted = config.get_target_unreal_engine_version()
        else:
            cached = self.input_manager.unreal_engine_path
            is_valid = UnrealEngineManager.is_valid_current_engine_path
            wanted = config.get_current_unreal_engine_version()

        detected = cached or self.input_manager.detect_engine_path(version_type)
        if detected:
            return detected

        chosen = filedialog.askdirectory(title=f"Select the Unreal Engine {wanted} installation folder")
        if not chosen:
            return None
        if not is_valid(Path(chosen)):
            messagebox.showerror("Convai Modding Tool",
                                 f"{chosen} is not an Unreal Engine {wanted} installation.")
            return None
        return chosen

    def _on_update(self) -> None:
        entry = self._selected()
        if not entry:
            return
        engine = self._resolve_engine("current")
        if not engine:
            return

        manager = self.input_manager
        manager.reset()
        manager.unreal_engine_path = engine
        manager.project_dir = entry["dir"]
        self.show_run(f"Updating {entry['name']}", self.flows["update"], entry["dir"])

    def _on_migrate(self) -> None:
        entry = self._selected()
        if not entry:
            return
        engine = self._resolve_engine("current")
        if not engine:
            return
        target = self._resolve_engine("target")
        if not target:
            return

        manager = self.input_manager
        manager.reset()
        manager.unreal_engine_path = engine
        manager.target_unreal_engine_path = target
        manager.project_dir = entry["dir"]
        self.show_run(f"Migrating {entry['name']}", self.flows["migrate"], entry["dir"])

    # --- new project --------------------------------------------------------

    def show_new_project(self) -> None:
        self._show(self._build_new_project)

    def _build_new_project(self, parent: ttk.Frame) -> None:
        _label(parent, "New project", font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(0, 14))

        self.name_var = tk.StringVar()
        widgets.create_text_field(parent, "Project name", self.name_var,
                                  hint="letters, digits and underscores")

        self.key_var = tk.StringVar()
        widgets.create_text_field(parent, "Convai API key", self.key_var, show="•")

        self.reuse_combo = None
        keys = {entry["name"]: entry["api_key"] for entry in self._scan_projects() if entry["api_key"]}
        if keys:
            row = ttk.Frame(parent, style="TFrame")
            row.pack(fill="x", pady=(0, 12))
            _label(row, "Reuse key from", colour="text_muted",
                   font=("Segoe UI", 9)).pack(side="left", padx=(0, 8))
            self.reuse_combo = ttk.Combobox(row, values=list(keys), state="readonly", font=("Segoe UI", 10))
            self.reuse_combo.pack(side="left", fill="x", expand=True)
            self.reuse_combo.bind("<<ComboboxSelected>>",
                                  lambda event: self.key_var.set(keys[self.reuse_combo.get()]))

        _, card = widgets.create_card(parent)
        self.type_var = tk.StringVar(value="Scene")
        widgets.create_segmented(card, "Asset type", [("Scene", "Scene"), ("Avatar", "Avatar")], self.type_var)
        self.metahuman_var = tk.BooleanVar(value=False)
        self.metahuman_check = ttk.Checkbutton(card, text="This is a MetaHuman avatar",
                                               variable=self.metahuman_var)
        self.type_var.trace_add("write", lambda *_: self._sync_metahuman())
        self._sync_metahuman()

        self.engine_var = tk.StringVar(value=self.input_manager.detect_engine_path("current") or "")
        widgets.create_text_field(
            parent, f"Unreal Engine {config.get_current_unreal_engine_version()} path", self.engine_var)
        widgets.create_button(parent, "Browse...", self._browse_engine).pack(anchor="e")

        self.form_error = _label(parent, "", colour="error", wraplength=520)
        self.form_error.pack(anchor="w", pady=(8, 0))

        row = ttk.Frame(parent, style="TFrame")
        row.pack(fill="x", pady=(12, 0))
        widgets.create_button(row, "Cancel", self.show_shelf).pack(side="left")
        widgets.create_button(row, "Create", self._on_create, style="accent").pack(side="right")

    def _sync_metahuman(self) -> None:
        if self.type_var.get() == "Avatar":
            self.metahuman_check.pack(anchor="w", pady=(8, 0))
        else:
            self.metahuman_check.pack_forget()
            self.metahuman_var.set(False)

    def _browse_engine(self) -> None:
        chosen = filedialog.askdirectory(title="Select the Unreal Engine installation folder")
        if chosen:
            self.engine_var.set(chosen)

    def _on_create(self) -> None:
        name = self.name_var.get().strip()
        problem = InputManager.validate_project_name(name, self.input_manager.get_script_dir())
        if problem:
            self.form_error.configure(text=problem)
            return

        api_key = self.key_var.get().strip()
        if not api_key:
            self.form_error.configure(text="Enter your Convai API key.")
            return

        engine = self.engine_var.get().strip()
        if not engine or not UnrealEngineManager.is_valid_current_engine_path(Path(engine)):
            self.form_error.configure(
                text=f"Select a valid Unreal Engine {config.get_current_unreal_engine_version()} folder.")
            return

        manager = self.input_manager
        manager.reset()
        manager.project_name = name
        manager.convai_api_key = api_key
        manager.asset_type = self.type_var.get()
        manager.is_metahuman = bool(self.metahuman_var.get())
        manager.unreal_engine_path = engine

        project_dir = os.path.join(str(manager.get_script_dir()), name)
        self.show_run(f"Creating {name}", self.flows["create"], project_dir)

    # --- run ----------------------------------------------------------------

    def show_run(self, title: str, flow: Callable[[], Optional[str]], folder: Optional[str]) -> None:
        self._show(lambda parent: self._build_run(parent, title))
        self._start_run(flow, folder)

    def _build_run(self, parent: ttk.Frame, title: str) -> None:
        self.log_handler = None
        self.log_queue = None
        self.run_folder = None

        _label(parent, title, font=("Segoe UI Semibold", 14)).pack(anchor="w")
        self.run_status = _label(parent, "Working...", colour="text_muted", wraplength=540)
        self.run_status.pack(anchor="w", pady=(4, 10))
        self.run_progress = ttk.Progressbar(parent, mode="indeterminate")
        self.run_progress.pack(fill="x")
        self.run_progress.start(12)

        # Packed from the bottom so a long migration report cannot push the
        # buttons off the window.
        self.run_buttons = ttk.Frame(parent, style="TFrame")
        self.run_buttons.pack(side="bottom", fill="x")
        self.back_btn = widgets.create_button(self.run_buttons, "Back", self.show_shelf)
        self.back_btn.configure(state="disabled")
        self.back_btn.pack(side="left")

        self.log_frame = tk.Frame(parent, bg=theme["bg_input"],
                                  highlightbackground=theme["border"], highlightthickness=1)
        self.log_frame.pack(fill="both", expand=True, pady=12)
        scroll = ttk.Scrollbar(self.log_frame, orient="vertical", style="Vertical.TScrollbar")
        self.log_text = tk.Text(self.log_frame, bg=theme["bg_input"], fg=theme["text"],
                                font=("Consolas", 9), wrap="word", relief="flat",
                                highlightthickness=0, state="disabled", yscrollcommand=scroll.set)
        scroll.configure(command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_log(self) -> None:
        while True:
            try:
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(record.getMessage())

        self.log_after = self.root.after(100, self._drain_log) if self.log_handler is not None else None

    def _start_run(self, flow: Callable[[], Optional[str]], folder: Optional[str]) -> None:
        self.running = True
        self.run_folder = folder
        self.log_queue = queue.Queue()
        self.log_handler = logging.handlers.QueueHandler(self.log_queue)
        logger.logger.addHandler(self.log_handler)
        self._drain_log()

        def work() -> None:
            try:
                result = flow()
            except ConvaiToolError as exc:
                self.root.after(0, lambda message=str(exc): self._finish_run(False, error=message))
                return
            except Exception as exc:
                logger.error(traceback.format_exc())
                self.root.after(0, lambda message=repr(exc): self._finish_run(False, error=message))
                return

            notes = result if isinstance(result, str) else None
            self.root.after(0, lambda: self._finish_run(True, notes=notes))

        threading.Thread(target=work, daemon=True).start()

    def _finish_run(self, ok: bool, notes: Optional[str] = None, error: Optional[str] = None) -> None:
        self.running = False
        if self.log_after is not None:
            # Closing the window with a tick still pending leaves Tcl shouting about a
            # command it has already deleted.
            self.root.after_cancel(self.log_after)
            self.log_after = None
        if self.log_handler is not None:
            logger.logger.removeHandler(self.log_handler)
            self.log_handler = None
            self._drain_log()

        self.run_progress.stop()
        self.run_progress.pack_forget()
        if ok:
            self.run_status.configure(text="Done", foreground=theme["accent"])
        else:
            self.run_status.configure(text=f"Failed: {error}", foreground=theme["error"])

        if notes:
            card, inner = widgets.create_card(self.log_frame.master, "What changed")
            card.pack(before=self.log_frame, fill="x", pady=(0, 12))
            ttk.Label(inner, text=notes, style="Card.TLabel",
                      wraplength=540, justify="left").pack(anchor="w")

        self.back_btn.configure(state="normal")
        if ok and self.run_folder and os.path.isdir(self.run_folder):
            widgets.create_button(self.run_buttons, "Open folder",
                                  lambda: os.startfile(self.run_folder)).pack(side="right")

    # --- settings -----------------------------------------------------------

    def open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("Settings")
        window.configure(bg=theme["bg_dark"])
        window.transient(self.root)
        window.grab_set()
        window.resizable(False, False)

        frame = ttk.Frame(window, style="TFrame")
        frame.pack(fill="both", expand=True, padx=18, pady=16)

        version = config.get_current_unreal_engine_version()
        _label(frame, "Settings", font=("Segoe UI Semibold", 14)).pack(anchor="w", pady=(0, 12))
        _label(frame, f"Unreal Engine {version}").pack(anchor="w")
        _label(frame, self.input_manager.detect_engine_path("current") or "not detected",
               colour="text_muted", font=("Segoe UI", 9), wraplength=420).pack(anchor="w", pady=(0, 16))

        status = _label(frame, "", colour="text_muted", wraplength=420, font=("Segoe UI", 9))
        button = widgets.create_button(
            frame, f"Install Linux toolchain for UE {version}",
            lambda: self._install_toolchain(version, button, status))
        button.pack(anchor="w")
        status.pack(anchor="w", pady=(8, 0))

        state = "on" if config.linux_packaging_enabled() else "off"
        _label(frame, f"Linux packaging is currently {state}. The toolchain is only needed "
                      f"when the asset uploader packages for Linux.",
               colour="text_muted", font=("Segoe UI", 9), wraplength=420).pack(anchor="w", pady=(16, 0))

    def _install_toolchain(self, version: str, button: tk.Button, status: ttk.Label) -> None:
        button.configure(state="disabled")
        status.configure(text="Installing, this can take several minutes...", foreground=theme["text_muted"])

        def work() -> None:
            from core.download_utils import DownloadManager
            try:
                installed = DownloadManager.ensure_toolchain_for_version(version, force=True)
                message = "Toolchain ready." if installed else "Install failed, see the console for details."
                colour = "accent" if installed else "error"
            except Exception as exc:
                message, colour = f"Install failed: {exc}", "error"
            self.root.after(0, lambda: self._toolchain_done(button, status, message, colour))

        threading.Thread(target=work, daemon=True).start()

    @staticmethod
    def _toolchain_done(button: tk.Button, status: ttk.Label, message: str, colour: str) -> None:
        if not status.winfo_exists():
            return
        status.configure(text=message, foreground=theme[colour])
        button.configure(state="normal")


def run_gui(tool_version: str, input_manager: InputManager,
            flows: dict[str, Callable[[], Optional[str]]]) -> None:
    root = tk.Tk()
    app = App(root, tool_version, input_manager, flows)
    app.show_boot()
    root.mainloop()
