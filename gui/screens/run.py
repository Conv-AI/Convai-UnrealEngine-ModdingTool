"""The activity screen: one run, its named steps, its log and its outcome.

This screen owns the run plumbing. The flow runs on a daemon worker and everything it
logs arrives through a ``QueueHandler`` that the Tk thread drains on a timer, so no
widget is ever touched off the Tk thread.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import re
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, ttk
from typing import Callable, Iterable, Optional

from core.exceptions import ConvaiToolError
from core.logger import logger
from gui.components import Disclosure, StepList, button, card, pill
from gui.theme import FONTS, SPACE, theme

# logger.step's glyph. It marks a phase change in the flow, unlike the info, success and
# warning lines that share the log with it.
STEP_GLYPH = "\U0001f527"

LOG_HEIGHT = 160


def _titles(steps: Iterable) -> list[str]:
    """The display title of each step, whether or not it carries markers."""
    return [step[0] if isinstance(step, (tuple, list)) else step for step in steps]


def _marks(steps: Iterable) -> list[tuple[str, ...]]:
    """Per step, the lowercased log phrases that mean the run has reached it.

    A step is either a plain title, matched on itself, or a ``(title, marker)`` pair
    naming the phrase the flow actually logs. The markers are explicit because guessing
    a phase from free text does not fail quietly: an unrelated line ticks a step the run
    has not reached, and the screen then reports progress that never happened.
    """
    marks = []
    for step in steps:
        if isinstance(step, (tuple, list)):
            title, markers = step[0], step[1]
            if isinstance(markers, str):
                markers = (markers,)
        else:
            title, markers = step, (step,)
        marks.append(tuple(marker.lower() for marker in markers))
    return marks


def _match(marks: list[tuple[str, ...]], current: int, text: str) -> Optional[int]:
    """The step a log line belongs to, or None. Never moves backwards."""
    lowered = text.lower()
    for index, markers in enumerate(marks):
        if index > current and any(marker in lowered for marker in markers):
            return index
    return None


def _wrap(label: tk.Label, padding: int = 56) -> None:
    """Keep a label's text wrapping inside its container, at any window width."""
    label.master.bind(
        "<Configure>",
        lambda event: label.configure(wraplength=max(240, event.width - padding)),
        add="+",
    )


class RunScreen:
    """One run: progress while it works, a result surface when it ends."""

    def __init__(self, app, title: str, flow: Callable[[], Optional[str]],
                 folder: Optional[str], steps: Optional[list[str]] = None,
                 retry: Optional[Callable[[], None]] = None,
                 subject: Optional[str] = None):
        self.app = app
        self.title = title
        self.flow = flow
        self.folder = folder
        self.steps = _titles(steps or [])
        self.retry = retry
        # What the result sentence names and what `folder` opens. A migration produces a
        # copy, so both differ from the project the run was started from; everything else
        # takes the subject out of its own title ("Updating CityGuide" -> "CityGuide").
        self.subject = subject or (title.split(" ", 1)[1] if " " in title else title)

        self.marks = _marks(steps or [])
        self.current = -1
        self.step_list: Optional[StepList] = None

        self.log_queue: Optional[queue.Queue] = None
        self.log_handler: Optional[logging.Handler] = None
        self.log_after: Optional[str] = None

    # --- build --------------------------------------------------------------

    def build(self, parent: tk.Frame) -> None:
        self.parent = parent

        head = tk.Frame(parent, background=theme["bg_app"])
        head.pack(fill="x")
        tk.Label(head, text=self.title, background=theme["bg_app"],
                 foreground=theme["text_primary"], font=FONTS["page_title"],
                 anchor="w", justify="left").pack(side="left")
        self.state_holder = tk.Frame(head, background=theme["bg_app"])
        self.state_holder.pack(side="right")
        self.state_pill: Optional[tk.Frame] = None
        self._set_state("In progress", "neutral")

        self.current_label = tk.Label(parent, text="Starting", background=theme["bg_app"],
                                      foreground=theme["text_secondary"], font=FONTS["body"],
                                      anchor="w", justify="left")
        self.current_label.pack(fill="x", pady=(SPACE["tight"], SPACE["tight"]))
        _wrap(self.current_label)

        # The flows report phases, never a fraction, so the bar stays indeterminate and
        # the step label carries the meaning. The style is left default: ttk prepends the
        # orientation to a named style, so "Thin.TProgressbar" resolves to a layout that
        # does not exist -- the theme's "TProgressbar" settings are inherited anyway.
        self.progress = ttk.Progressbar(parent, mode="indeterminate")
        self.progress.pack(fill="x")
        self.progress.start(12)

        if self.steps:
            self.step_list = StepList(parent)
            self.step_list.set_steps(self.steps)
            self.step_list.frame.pack(fill="x", pady=(SPACE["section"], 0))
            self._advance(0)

        self.result = tk.Frame(parent, background=theme["bg_app"])
        self.result.pack(fill="x", pady=(SPACE["section"], 0))

        self._build_log(parent)

    def _build_log(self, parent: tk.Frame) -> None:
        section = tk.Frame(parent, background=theme["bg_app"])
        section.pack(fill="x", pady=(SPACE["section"], 0))

        head = tk.Frame(section, background=theme["bg_app"])
        head.pack(fill="x")
        tk.Label(head, text="Technical log", background=theme["bg_app"],
                 foreground=theme["text_secondary"], font=FONTS["meta_strong"]).pack(side="left")
        button(head, "Save as…", self._save_log, kind="quiet", compact=True,
               accessible_name=f"Save the {self.subject} log to a file").pack(side="right")
        button(head, "Copy", self._copy_log, kind="quiet", compact=True,
               accessible_name=f"Copy the {self.subject} log").pack(side="right", padx=(0, SPACE["tight"]))

        box = tk.Frame(section, background=theme["bg_surface_raised"], height=LOG_HEIGHT,
                       highlightbackground=theme["border_subtle"], highlightthickness=1)
        box.pack_propagate(False)
        scroll = ttk.Scrollbar(box, orient="vertical", style="Vertical.TScrollbar")
        self.log_text = tk.Text(
            box, background=theme["bg_surface_raised"], foreground=theme["text_primary"],
            font=FONTS["mono"], wrap="word", relief="flat", borderwidth=0,
            highlightthickness=0, padx=10, pady=8, state="disabled",
            selectbackground=theme["accent"], selectforeground=theme["accent_ink"],
            insertbackground=theme["text_primary"], yscrollcommand=scroll.set,
        )
        scroll.configure(command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_disclosure = Disclosure(
            head, "Hide technical log", "Show technical log", box,
            pack_options={"fill": "x", "pady": (SPACE["tight"], 0)})
        self.log_disclosure.button.pack(side="left", padx=(SPACE["tight"], 0))

    # --- run ----------------------------------------------------------------

    def start(self) -> None:
        self.app.running = True
        self.app.shell.set_navigation_enabled(False)

        self.log_queue = queue.Queue()
        self.log_handler = logging.handlers.QueueHandler(self.log_queue)
        logger.logger.addHandler(self.log_handler)
        self._drain_log()

        def work() -> None:
            try:
                result = self.flow()
            except ConvaiToolError as exc:
                self.app.root.after(0, lambda message=str(exc): self._finish(False, error=message))
                return
            except Exception as exc:
                logger.error(traceback.format_exc())
                self.app.root.after(0, lambda message=repr(exc): self._finish(False, error=message))
                return

            notes = result if isinstance(result, str) else None
            self.app.root.after(0, lambda: self._finish(True, notes=notes))

        threading.Thread(target=work, daemon=True).start()

    def _drain_log(self) -> None:
        if not self.log_text.winfo_exists():
            return
        while True:
            try:
                record = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append(record.getMessage())

        self.log_after = self.app.root.after(100, self._drain_log) if self.log_handler is not None else None

    def _append(self, text: str) -> None:
        # Only follow the tail when the user is already there; otherwise they are
        # reading something further up and a jump would lose their place.
        at_bottom = self.log_text.yview()[1] >= 0.999
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.configure(state="disabled")
        if at_bottom:
            self.log_text.see("end")
        self._track(text)

    def _track(self, line: str) -> None:
        # Only the flow's own step lines move the step list. Section banners repeat the
        # whole operation's name ("Updating Existing Modding Project") and would match
        # a step further down the list, skipping everything before it.
        text = line.strip()
        if not text.startswith(STEP_GLYPH):
            return
        text = text[len(STEP_GLYPH):].strip().rstrip(".")
        self.current_label.configure(text=text or "Working")

        index = _match(self.marks, self.current, text)
        if index is not None:
            self._advance(index)

    def _advance(self, index: int) -> None:
        if self.step_list is None:
            return
        for position in range(index):
            self.step_list.set_state(self.steps[position], "done")
        self.step_list.set_state(self.steps[index], "active")
        self.current = index

    # --- outcome ------------------------------------------------------------

    def _finish(self, ok: bool, notes: Optional[str] = None, error: Optional[str] = None) -> None:
        self.app.running = False
        if self.log_after is not None:
            # A tick still pending after the window goes leaves Tcl shouting about a
            # command it has already deleted.
            self.app.root.after_cancel(self.log_after)
            self.log_after = None
        if self.log_handler is not None:
            logger.logger.removeHandler(self.log_handler)
            self.log_handler = None
            self._drain_log()
        self.app.shell.set_navigation_enabled(True)

        if not self.parent.winfo_exists():
            return

        self.progress.stop()
        self.progress.pack_forget()
        self.current_label.pack_forget()

        if ok:
            self._succeed(notes)
        else:
            self._fail(error)

    def _succeed(self, notes: Optional[str]) -> None:
        self._set_state("Done", "ok")
        for title in self.steps:
            self.step_list.set_state(title, "done")

        self._surface(f"{self.subject} is ready.", "ok")

        if notes:
            # The toggle is packed before the surface it reveals, so the notes open
            # below the button rather than above it.
            toggle = tk.Frame(self.result, background=theme["bg_app"])
            toggle.pack(fill="x", pady=(SPACE["tight"], 0))
            host = tk.Frame(self.result, background=theme["bg_app"])
            host.pack(fill="x")
            outer, inner = card(host, "What changed")
            summary = tk.Label(inner, text=notes, background=theme["bg_surface"],
                               foreground=theme["text_primary"], font=FONTS["body"],
                               anchor="w", justify="left")
            summary.pack(fill="x")
            _wrap(summary, padding=2 * SPACE["surface"] + 16)
            Disclosure(toggle, "Hide what changed", "What changed", outer,
                       pack_options={"fill": "x", "pady": (SPACE["tight"], 0)}).button.pack(anchor="w")

        actions = self._actions()
        openable = bool(self.folder) and os.path.isdir(self.folder)
        if openable:
            button(actions, "Open project folder", self._open_folder, kind="primary",
                   accessible_name=f"Open the {self.subject} folder").pack(side="left")
        button(actions, "Back to projects", self._back,
               kind="secondary" if openable else "primary").pack(side="left", padx=(SPACE["tight"], 0))
        if not openable:
            tk.Label(actions, text="The project folder is no longer there.",
                     background=theme["bg_app"], foreground=theme["text_secondary"],
                     font=FONTS["meta"]).pack(side="left", padx=(SPACE["tight"], 0))

    def _fail(self, error: Optional[str]) -> None:
        self._set_state("Failed", "danger")
        inner = self._surface(f"{self.subject} was not completed.", "danger")

        detail = tk.Label(inner, text=error or "The run stopped before it finished.",
                          background=theme["danger_soft"], foreground=theme["danger_soft_text"],
                          font=FONTS["body"], anchor="w", justify="left")
        detail.pack(fill="x", pady=(SPACE["tight"], 0))
        _wrap(detail, padding=2 * SPACE["surface"] + 16)

        button(inner, "View technical details", self._show_log, kind="quiet", compact=True,
               accessible_name=f"Show the {self.subject} technical log"
               ).pack(anchor="w", pady=(SPACE["tight"], 0))

        actions = self._actions()
        if self.retry:
            button(actions, "Try again", self.retry, kind="primary",
                   accessible_name=self.title).pack(side="left")
            button(actions, "Back to projects", self._back).pack(side="left", padx=(SPACE["tight"], 0))
        else:
            button(actions, "Back to projects", self._back, kind="primary").pack(side="left")

    def _surface(self, sentence: str, tone: str) -> tk.Frame:
        """The tinted result card. Returns its padded inner frame."""
        background, border, foreground = (theme[f"{tone}_soft"], theme[f"{tone}_soft_border"],
                                          theme[f"{tone}_soft_text"])
        outer = tk.Frame(self.result, background=background, highlightbackground=border,
                         highlightthickness=1)
        outer.pack(fill="x")
        inner = tk.Frame(outer, background=background)
        inner.pack(fill="both", expand=True, padx=SPACE["surface"], pady=SPACE["surface"])
        headline = tk.Label(inner, text=sentence, background=background, foreground=foreground,
                            font=FONTS["section_title"], anchor="w", justify="left")
        headline.pack(fill="x")
        _wrap(headline, padding=2 * SPACE["surface"] + 16)
        return inner

    def _actions(self) -> tk.Frame:
        row = tk.Frame(self.result, background=theme["bg_app"])
        row.pack(fill="x", pady=(SPACE["section"], 0))
        return row

    def _set_state(self, text: str, tone: str) -> None:
        if self.state_pill is not None:
            self.state_pill.destroy()
        self.state_pill = pill(self.state_holder, text, tone=tone)
        self.state_pill.pack()

    # --- actions ------------------------------------------------------------

    def _back(self) -> None:
        self.app.show_shelf(self.folder)

    def _open_folder(self) -> None:
        if self.folder and os.path.isdir(self.folder):
            os.startfile(self.folder)

    def _show_log(self) -> None:
        if not self.log_disclosure.expanded:
            self.log_disclosure.toggle()
        self.log_text.see("end")

    def _log_contents(self) -> str:
        return self.log_text.get("1.0", "end-1c")

    def _copy_log(self) -> None:
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self._log_contents())
        self.app.shell.set_status(right="Technical log copied")

    def _save_log(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self.app.root, title="Save technical log", defaultextension=".log",
            initialfile=f"{self.subject}.log",
            filetypes=[("Log file", "*.log"), ("Text file", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self._log_contents())
        except OSError as exc:
            self.app.shell.set_status(right=f"Could not save the log: {exc.strerror or exc}")
            return
        self.app.shell.set_status(right=f"Log saved to {os.path.basename(path)}")


if __name__ == "__main__":
    # The step tracker is the only inference on this screen, so it is checked against the
    # lines the update flow really logs, in the order it really logs them.
    steps = [("Reading the project", "loading project configuration"),
             ("Checking Unreal Engine", "checking project engine version"),
             ("Updating Convai plugins", "updating convai dependencies"),
             ("Configuring project assets", "configuring project assets"),
             ("Patching for this engine", "patching plugin source"),
             ("Building project", "building project")]
    marks = _marks(steps)
    assert _titles(steps)[0] == "Reading the project"

    seen, current = [], -1
    for line in ("Loading project configuration...", "Checking project engine version...",
                 "Ensuring toolchain for UE 5.8...", "Updating Convai dependencies...",
                 "Removing 1 existing installation(s)...", "Downloading latest dependencies...",
                 "Configuring project assets...",
                 "Patching plugin source for engine compatibility...", "Building project..."):
        hit = _match(marks, current, line)
        if hit is not None:
            current = hit
            seen.append(hit)
    assert seen == [0, 1, 2, 3, 4, 5], seen

    # A line naming an earlier step must not walk the list back.
    assert _match(marks, 3, "Updating Convai dependencies...") is None
    # A nested line that merely shares a word ticks nothing.
    assert _match(marks, 1, "Downloading latest dependencies...") is None
    assert _match(marks, 0, "Ensuring toolchain for UE 5.8...") is None
    print("step matcher ok")
