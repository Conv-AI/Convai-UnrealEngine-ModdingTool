"""The pywebview host: one window, the command transport, and the native dialogs.

This is the only module that knows a webview exists. It wraps what the page asks for
in the frozen command envelope, hands it to the dispatcher, and pushes events back
into the page. No screen logic lives here -- it is a transport, and the seam is the
point: the UI is swappable as long as this file is the only thing that moves.

``python -m gui.host`` opens the app with stub flows, so the UI can be driven without
an Unreal installation.
"""

from __future__ import annotations

import json
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

import webview

from core.input_manager import InputManager
from core.logger import logger

TITLE = "Convai Modding Tool"
MIN_SIZE = (920, 640)
PREFERRED_SIZE = (1120, 760)
BACKGROUND = "#07100A"
# Where Epic installs engines by default; only a starting point for the folder picker.
_ENGINE_ROOT_HINT = r"C:\Program Files\Epic Games"
# Long enough to turn a burst of log lines into one call, short enough that the log
# still reads as live.
GATHER_SECONDS = 0.05
BATCH_LIMIT = 200
CLOSE_WARNING = "Run in progress — closing the tool may interrupt it.\n\nClose anyway?"


def _bundled(*parts: str) -> Path:
    """A file shipped with the tool, from source or unpacked from the onefile exe."""
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root.joinpath(*parts)


def _first_path(chosen: Any) -> Optional[str]:
    """create_file_dialog answers with a tuple, a bare string, or nothing."""
    if not chosen:
        return None
    return chosen if isinstance(chosen, str) else str(chosen[0])


class _JsApi:
    """Everything the page may reach: `window.pywebview.api.command(envelope)`.

    The page builds the envelope, including its id, because that is what a transport
    carries -- a socket would deliver the same object, and replies are matched by that
    id.

    It holds the one bound method rather than the Host: pywebview resolves JS calls by
    walking attributes of this object, so anything reachable from here is reachable from
    the page.
    """

    def __init__(self, dispatch: Callable[[dict], dict]):
        self.command = dispatch


class Host:
    """The window plus the two directions of the bridge.

    `emit` is called from worker threads, `dispatch` from pywebview's JS API threads,
    and `on_closing` from the UI thread; nothing here may assume which one it is on.
    """

    def __init__(self):
        self.window: Any = None
        self.dispatcher: Any = None
        self._lock = threading.Lock()
        self._page_ready = False
        self._pending: list[str] = []
        self._runs: set[str] = set()
        self._installing = False
        self._queue: list[str] = []
        self._wake = threading.Event()
        threading.Thread(target=self._pump, daemon=True).start()

    # --- UI -> Python -------------------------------------------------------

    def dispatch(self, envelope: dict) -> dict:
        # The page calling in is the proof it can take events back: its bridge module
        # is running, which `loaded` alone would not tell us.
        self._release_pending()

        if not isinstance(envelope, dict):
            return {"id": "", "ok": False,
                    "error": {"code": "unknown", "message": "The tool sent a malformed command."}}
        envelope.setdefault("id", uuid4().hex)
        try:
            reply = self.dispatcher.handle(envelope)
        except Exception as error:
            logger.error(traceback.format_exc())
            return {"id": envelope["id"], "ok": False,
                    "error": {"code": "unknown",
                              "message": str(error) or "Something went wrong."}}

        data = reply.get("data") if isinstance(reply, dict) else None
        if isinstance(data, dict) and data.get("runId"):
            self._runs.add(data["runId"])
        return reply

    # --- Python -> UI -------------------------------------------------------

    def emit(self, event: Any, data: Optional[dict] = None) -> None:
        payload = {**event} if isinstance(event, dict) else {"event": event, "data": data or {}}
        payload["type"] = "event"
        name = payload.get("event")
        if name == "runFinished":
            self._runs.discard((payload.get("data") or {}).get("runId"))
        elif name == "toolchain":
            self._installing = (payload.get("data") or {}).get("state") == "installing"

        script = f"window.convai.onEvent({json.dumps(payload)});"
        with self._lock:
            if not self._page_ready:
                self._pending.append(script)
                return
            self._queue.append(script)
        self._wake.set()

    def _release_pending(self) -> None:
        with self._lock:
            if self._page_ready:
                return
            self._page_ready = True
            self._queue.extend(self._pending)
            self._pending = []
        self._wake.set()

    def _pump(self) -> None:
        """Deliver queued events, coalesced.

        Every run_js is a blocking round trip into the webview, and a UBT build logs
        thousands of lines: one call per line would spend the whole build waiting. A
        short gather window turns a burst into one call, and the queue keeps the order
        the events were emitted in.
        """
        while True:
            self._wake.wait()
            self._wake.clear()
            time.sleep(GATHER_SECONDS)
            while True:
                with self._lock:
                    batch, self._queue = self._queue[:BATCH_LIMIT], self._queue[BATCH_LIMIT:]
                if not batch:
                    break
                self._run_js("".join(batch))

    def _run_js(self, script: str) -> None:
        try:
            self.window.run_js(script)
        except Exception:
            # The window has gone: a worker still finishing its run is not an error.
            pass

    # --- native dialogs -----------------------------------------------------

    def choose_folder(self, title: str) -> Optional[str]:
        # pywebview's folder dialog has no title, so the screen that opened it carries
        # the wording. `directory` is the only steer available: start where engines live
        # rather than in the last folder Windows happens to remember.
        return _first_path(self.window.create_file_dialog(
            webview.FOLDER_DIALOG, directory=_ENGINE_ROOT_HINT))

    def save_file(self, title: str, suggested_name: str) -> Optional[str]:
        # Without a filter the save dialog hands back an extensionless file, and the log
        # then opens in nothing.
        return _first_path(self.window.create_file_dialog(
            webview.SAVE_DIALOG, save_filename=suggested_name,
            file_types=("Log file (*.log)", "Text file (*.txt)", "All files (*.*)")))

    # --- window -------------------------------------------------------------

    def close(self) -> None:
        """`app.quit` from the page. Destroying the window ends `webview.start`."""
        self._runs.clear()
        self._installing = False
        self._cancel_sign_in()
        try:
            self.window.destroy()
        except Exception:
            pass

    def on_closing(self) -> bool:
        """False cancels the close.

        A run is in flight between the reply that names its id and the `runFinished`
        that clears it. A toolchain install carries no run id but takes minutes and
        writes to disk, so it counts too -- the `toolchain` events bracket it.
        """
        if not self._runs and not self._installing:
            self._cancel_sign_in()
            return True
        if not self.window.create_confirmation_dialog(TITLE, CLOSE_WARNING):
            return False
        self._cancel_sign_in()
        return True

    def _cancel_sign_in(self) -> None:
        """A sign-in still waiting on the browser holds a thread pywebview will not
        abandon, so the window would close and the process would stay."""
        cancel = getattr(self.dispatcher, "cancel_sign_in", None)
        if cancel is not None:
            cancel()


def run_gui(tool_version: str, input_manager: InputManager,
            flows: dict[str, Callable[[], Optional[str]]]) -> None:
    try:
        from bridge.dispatcher import Dispatcher
    except ModuleNotFoundError:
        from bridge import Dispatcher

    host = Host()
    width, height = PREFERRED_SIZE
    host.window = webview.create_window(
        TITLE,
        str(_bundled("gui", "webui", "index.html")),
        js_api=_JsApi(host.dispatch),
        width=width, height=height, min_size=MIN_SIZE,
        background_color=BACKGROUND,
        # The technical log is there to be copied out of; pywebview disables selection
        # across the page by default.
        text_select=True,
    )
    host.window.events.closing += host.on_closing
    host.dispatcher = Dispatcher(tool_version, input_manager, flows,
                                 emit=host.emit,
                                 choose_folder=host.choose_folder,
                                 save_file=host.save_file,
                                 on_quit=host.close)

    icon = _bundled("resources", "Convai.ico")
    webview.start(icon=str(icon) if icon.exists() else None)


if __name__ == "__main__":
    import time

    def _stub(kind: str) -> Callable[[], Optional[str]]:
        def flow() -> Optional[str]:
            logger.section(f"Stub {kind}")
            for step in ("Checking prerequisites", "Copying files", "Building"):
                logger.step(f"{step}...")
                time.sleep(0.8)
            logger.success("Done")
            return f"Stub {kind}: nothing was actually built."
        return flow

    root = str(Path(__file__).resolve().parent.parent)
    run_gui("0.0.0-dev", InputManager(root),
            {kind: _stub(kind) for kind in ("create", "update", "migrate")})
