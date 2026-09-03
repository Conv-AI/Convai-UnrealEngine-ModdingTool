"""The wire format and the pure logic behind it.

Nothing here does I/O or knows what carries the envelopes, so this module is what
survives if the transport later becomes a WebSocket instead of a JS binding. The step
markers and the project wording live here for the same reason: they are the tool's
copy, not the window's.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

# logger.step's glyph. It marks a phase change in the flow, unlike the info, success and
# warning lines that share the log with it.
STEP_GLYPH = "\U0001f527"

# A step is a display title and the phrase the flow logs when it reaches it. The phrases
# are copied from the logger.step calls in ConvaiModdingTool.py, core/unreal_engine_manager.py
# and core/file_utility_manager.py -- change one there and the step it drives stops ticking.
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
CREATE_STEPS = [
    "Validating Unreal Engine",
    "Setting up project",
    "Downloading Convai dependencies",
    "Configuring assets",
    "Building project",
]


# --- envelopes --------------------------------------------------------------

def reply(id: str, data: Optional[dict] = None) -> dict:
    return {"id": id, "ok": True, "data": data or {}}


def error(id: str, code: str, message: str) -> dict:
    return {"id": id, "ok": False, "error": {"code": code, "message": message}}


def event(name: str, data: Optional[dict] = None) -> dict:
    return {"type": "event", "event": name, "data": data or {}}


def parse_command(raw: Any) -> tuple[str, str, dict]:
    """(id, command, params) out of a dict or the JSON text of one."""
    if isinstance(raw, (str, bytes)):
        raw = json.loads(raw)
    if not isinstance(raw, dict):
        raise ValueError("a command is an object with an id and a command name")
    params = raw.get("params")
    return (str(raw.get("id") or ""), str(raw.get("command") or ""),
            params if isinstance(params, dict) else {})


# --- steps ------------------------------------------------------------------

def step_titles(steps: Iterable) -> list[str]:
    """The display title of each step, whether or not it carries markers."""
    return [step[0] if isinstance(step, (tuple, list)) else step for step in steps]


def step_marks(steps: Iterable) -> list[tuple[str, ...]]:
    """Per step, the lowercased log phrases that mean the run has reached it.

    A step is either a plain title, matched on itself, or a ``(title, marker)`` pair
    naming the phrase the flow actually logs. The markers are explicit because guessing
    a phase from free text does not fail quietly: an unrelated line ticks a step the run
    has not reached, and the UI then reports progress that never happened.
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


def match_step(marks: list[tuple[str, ...]], current: int, text: str) -> Optional[int]:
    """The step a log line belongs to, or None. Never moves backwards."""
    lowered = text.lower()
    for index, markers in enumerate(marks):
        if index > current and any(marker in lowered for marker in markers):
            return index
    return None


def step_from_line(marks: list[tuple[str, ...]], current: int, line: str) -> Optional[int]:
    """The step a whole log line reaches, or None.

    Only the flow's own step lines count. Section banners repeat the whole operation's
    name ("Updating Existing Modding Project") and would match a step further down the
    list, skipping everything before it.
    """
    text = line.strip()
    if not text.startswith(STEP_GLYPH):
        return None
    return match_step(marks, current, text[len(STEP_GLYPH):].strip().rstrip("."))


def steps_view(titles: list[str], current: int, finished: bool = False) -> list[dict]:
    """The `steps` event's payload: every title with the state it is in now."""
    states = []
    for index, title in enumerate(titles):
        if finished or index < current:
            state = "done"
        elif index == current:
            state = "active"
        else:
            state = "pending"
        states.append({"title": title, "state": state})
    return states


# --- shared shapes ----------------------------------------------------------

def account_view(signed_in: bool, name: Optional[str], email: str) -> dict:
    """Never the API key, a token, an expiry or a file path -- only who is signed in."""
    return {"signedIn": bool(signed_in), "name": name or None, "email": email or ""}


def engine_view(version_type: str, version: str, path: Optional[str]) -> dict:
    """`path` is what the caller has already re-validated, so None reads as not ready."""
    if path:
        reason = None
    elif version_type == "target":
        reason = f"Migrating a project to UE {version} needs a UE {version} installation."
    else:
        reason = f"Creating and updating projects need an Unreal Engine {version} installation."
    return {"versionType": version_type, "version": version, "path": path or None,
            "ready": bool(path), "reason": reason}


def project_view(project_dir: str, metadata: dict, engine_version: Optional[str],
                 target_version: str, signed_in: bool) -> dict:
    """One scanned project.

    Only facts the scan can establish end up here: the state is derived from the
    project's engine version, never from an assumption about the plugin inside it, and
    the API key in the metadata is not the UI's business.
    """
    migratable = bool(engine_version) and engine_version != target_version
    if not engine_version:
        state, tone = "Engine version not detected", "warn"
    elif migratable:
        state, tone = f"Needs migration \u2192 UE {target_version}", "warn"
    else:
        state, tone = "Ready to update", "muted"

    return {
        "dir": project_dir,
        # The folder is a project because the scan found a .uproject in it; the metadata
        # name is only a guess at what that file is called, and a legacy project has none.
        "name": os.path.basename(project_dir.rstrip("\\/")),
        "ue": engine_version or "",
        "assetType": metadata.get("asset_type") or "",
        "isMetahuman": bool(metadata.get("is_metahuman")),
        "migratable": migratable,
        "target": target_version,
        "state": state,
        "stateTone": tone,
        "meta": f"UE {engine_version}" if engine_version else "Engine version not detected",
        "connected": bool(signed_in),
    }
