"""The command router: every UI command, over core/.

The dispatcher is the only thing that knows both the frozen v1 command names and the
managers behind them. It never touches a window: native dialogs and quitting arrive as
callables from the host, everything it has to say leaves through `emit`, and a run works
on a daemon thread and reports as it goes.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import queue
import threading
import traceback
import uuid
import webbrowser
from pathlib import Path
from typing import Callable, Optional

from bridge.protocol import (CREATE_STEPS, MIGRATE_STEPS, UPDATE_STEPS, account_view,
                             engine_view, error, event, parse_command, project_view, reply,
                             step_from_line, step_marks, step_titles, steps_view)
from core.account import DASHBOARD_URL, AccountSession, AuthError, BrowserLogin, _verify_key
from core.config_manager import config
from core.exceptions import ConvaiToolError
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.logger import logger
from core.unreal_engine_manager import UnrealEngineManager

INSTALLING = "Installing, this can take several minutes…"
NO_DIALOG = "This build cannot open that dialog."


class BridgeError(Exception):
    """A failure with a code from the contract and a sentence fit to show a user."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _auth_code(exc: AuthError) -> str:
    """core.account tells a rejected key from an outage only by the sentence it raises."""
    message = str(exc).lower()
    if "verify that api key" in message:
        return "invalidKey"
    return "network" if "reach convai" in message else "unknown"


def _version_manager():
    """Imported on use: core.version_manager pulls in the GitHub client."""
    from core.version_manager import VersionManager

    return VersionManager


class Dispatcher:
    """One window's worth of commands. `handle` is the only entry point."""

    def __init__(self, tool_version: str, input_manager: InputManager,
                 flows: dict[str, Callable[[], Optional[str]]],
                 emit: Callable[[dict], None],
                 choose_folder: Optional[Callable[[str], Optional[str]]] = None,
                 save_file: Optional[Callable[[str, str], Optional[str]]] = None,
                 on_quit: Optional[Callable[[], None]] = None):
        self.tool_version = tool_version
        self.input_manager = input_manager
        self.flows = flows
        self.emit = emit
        self.choose_folder = choose_folder
        self.save_file = save_file
        self.on_quit = on_quit

        self.account = AccountSession()
        # Engine folders the user picked. They live here, not on the InputManager,
        # because `reset()` clears that between runs.
        self.engine_overrides: dict[str, str] = {}

        self._lock = threading.Lock()
        self._run_id: Optional[str] = None
        self._log_lines: dict[str, list[str]] = {}
        self._log_subject = ""
        self._installing = False

        self._handlers: dict[str, Callable[[dict], dict]] = {
            "boot": self._boot,
            "projects.list": self._projects_list,
            "project.validateName": self._validate_name,
            "account.status": lambda params: {"account": self._account()},
            "account.signInGoogle": self._sign_in_google,
            "account.signInKey": self._sign_in_key,
            "account.signOut": self._sign_out,
            "account.dashboard": self._dashboard,
            "engine.status": self._engine_status,
            "engine.choose": self._engine_choose,
            "migration.preflight": lambda params: self._preflight(self._project_dir(params)),
            "project.create": self._create,
            "project.update": self._update,
            "project.migrate": self._migrate,
            "path.open": self._open_path,
            "log.save": self._save_log,
            "toolchain.install": self._install_toolchain,
            "packaging.status": self._packaging_status,
            "updates.check": self._check_updates,
            "updates.download": self._download_update,
            "app.quit": self._quit,
        }

    # --- entry point --------------------------------------------------------

    def handle(self, raw) -> dict:
        """Run one command and answer with its envelope. Never raises."""
        command_id = ""
        try:
            command_id, command, params = parse_command(raw)
            handler = self._handlers.get(command)
            if handler is None:
                return error(command_id, "unknown",
                             f"This build does not know the command “{command}”.")
            return reply(command_id, handler(params))
        except BridgeError as exc:
            return error(command_id, exc.code, str(exc))
        except ConvaiToolError as exc:
            return error(command_id, "unknown", str(exc))
        except Exception as exc:
            logger.error(traceback.format_exc())
            return error(command_id, "unknown", f"Something went wrong: {exc}")

    def _emit(self, envelope: dict) -> None:
        # A host that has gone -- a closed window, a dropped socket -- must not take a
        # run down with it.
        try:
            self.emit(envelope)
        except Exception:
            pass

    # --- boot ---------------------------------------------------------------

    def _boot(self, params: dict) -> dict:
        self._stage("config", "active")
        try:
            config.load()
        except ConvaiToolError:
            # The retries are already spent by the time this lands; what the user can act
            # on is the connection, not the fetch that failed.
            raise BridgeError("network",
                              "The tool couldn't reach Convai's configuration service, so it "
                              "can't tell what to install. Check your internet connection or "
                              "VPN, then try again.")
        self._stage("config", "done")

        self._stage("version", "active")
        try:
            # None means the check itself failed; only a definite False is an outdated build.
            up_to_date = _version_manager().check_version(self.tool_version)
        except Exception:
            up_to_date = None
        self._stage("version", "done")

        self._stage("projects", "active")
        try:
            self.account.restore()
        except Exception:
            # A session that will not restore is a signed-out session, not a failed boot.
            pass
        self._stage("projects", "done")

        return {"version": self.tool_version, "upToDate": up_to_date,
                "requiredVersion": self._required_version(), "account": self._account()}

    def _stage(self, stage: str, state: str) -> None:
        self._emit(event("bootStage", {"stage": stage, "state": state}))

    @staticmethod
    def _required_version() -> str:
        """The version the gate actually compares against -- Version.json, not the
        modding_tool_config entry, which is a different file and a different key."""
        try:
            return str(config.remote_config.version_data.get("modding-tool-version", "") or "")
        except Exception:
            return ""

    # --- projects -----------------------------------------------------------

    def _projects_list(self, params: dict) -> dict:
        target = config.get_target_unreal_engine_version()
        signed_in = self.account.is_signed_in
        projects = []
        for project_dir in self.input_manager.find_existing_projects():
            # The metadata name is only a guess at what the .uproject is called, and a
            # legacy project has none, so the engine version comes off whichever file is there.
            uproject = next(Path(project_dir).glob("*.uproject"), None)
            version = UnrealEngineManager._get_project_engine_version(str(uproject)) if uproject else None
            projects.append(project_view(project_dir, FileUtilityManager.get_metadata(project_dir),
                                         version, target, signed_in))
        return {"projects": projects}

    def _validate_name(self, params: dict) -> dict:
        name = str(params.get("name") or "").strip()
        return {"problem": InputManager.validate_project_name(name, self.input_manager.get_script_dir())}

    @staticmethod
    def _project_dir(params: dict) -> str:
        project_dir = str(params.get("dir") or "")
        if not project_dir or not os.path.isdir(project_dir):
            raise BridgeError("notFound", "That project folder is no longer there.")
        return project_dir

    # --- account ------------------------------------------------------------

    def _account(self) -> dict:
        return account_view(self.account.is_signed_in, self.account.display_name, self.account.email)

    def _adopted(self, api_key: str, username: str = "", email: str = "") -> dict:
        self.account.adopt(api_key, username, email)
        account = self._account()
        self._emit(event("accountChanged", {"account": account}))
        return {"account": account}

    def _sign_in_google(self, params: dict) -> dict:
        # The login blocks until the browser comes back or the wait times out, so the
        # host has to call `handle` off whatever thread paints the UI.
        try:
            api_key, username, email = BrowserLogin().run()
        except AuthError as exc:
            raise BridgeError(_auth_code(exc), str(exc))
        return self._adopted(api_key, username, email)

    def _sign_in_key(self, params: dict) -> dict:
        key = str(params.get("key") or "").strip()
        if not key:
            raise BridgeError("invalidKey", "Enter your Convai API key.")
        try:
            _verify_key(key)
        except AuthError as exc:
            raise BridgeError(_auth_code(exc), str(exc))
        return self._adopted(key)

    def _sign_out(self, params: dict) -> dict:
        self.account.sign_out()
        account = self._account()
        self._emit(event("accountChanged", {"account": account}))
        return {"account": account}

    def _dashboard(self, params: dict) -> dict:
        webbrowser.open(DASHBOARD_URL, new=2)
        return {}

    # --- engine -------------------------------------------------------------

    @staticmethod
    def _engine_version(version_type: str) -> str:
        return (config.get_target_unreal_engine_version() if version_type == "target"
                else config.get_current_unreal_engine_version())

    @staticmethod
    def _is_valid_engine(path: Optional[str], version_type: str) -> bool:
        check = (UnrealEngineManager.is_valid_target_engine_path if version_type == "target"
                 else UnrealEngineManager.is_valid_current_engine_path)
        return bool(path) and check(Path(path))

    def _engine_path(self, version_type: str = "current") -> Optional[str]:
        """The engine already chosen or detected, if it is still there.

        A remembered path is re-checked rather than trusted: an installation can be moved
        or removed between runs, and everything that reads this decides from it whether
        an action is available.
        """
        cached = (self.engine_overrides.get(version_type)
                  or (self.input_manager.target_unreal_engine_path if version_type == "target"
                      else self.input_manager.unreal_engine_path))
        if cached and self._is_valid_engine(cached, version_type):
            return cached
        detected = self.input_manager.detect_engine_path(version_type)
        return detected if detected and self._is_valid_engine(detected, version_type) else None

    def _engine(self, version_type: str) -> dict:
        return engine_view(version_type, self._engine_version(version_type),
                           self._engine_path(version_type))

    def _engine_status(self, params: dict) -> dict:
        return {"current": self._engine("current"), "target": self._engine("target"),
                "sameVersion": self._engine_version("current") == self._engine_version("target")}

    def _engine_choose(self, params: dict) -> dict:
        version_type = "target" if params.get("versionType") == "target" else "current"
        if self.choose_folder is None:
            raise BridgeError("unknown", NO_DIALOG)
        version = self._engine_version(version_type)
        chosen = self.choose_folder(f"Select the Unreal Engine {version} installation folder")
        # A cancelled picker changes nothing, so the answer is the engine as it stands.
        if not chosen:
            return {"engine": self._engine(version_type)}
        if not self._is_valid_engine(chosen, version_type):
            raise BridgeError("invalidEngine",
                              f"{chosen} is not an Unreal Engine {version} installation.")
        self._set_engine_path(version_type, chosen)
        return {"engine": self._engine(version_type)}

    def _set_engine_path(self, version_type: str, path: str) -> None:
        self.engine_overrides[version_type] = path
        if version_type == "target":
            self.input_manager.target_unreal_engine_path = path
        else:
            self.input_manager.unreal_engine_path = path

    def _require_engine(self, params: dict, key: str, version_type: str) -> str:
        """The engine a run will use: the one the UI named, or the remembered one."""
        chosen = str(params.get(key) or "")
        version = self._engine_version(version_type)
        if chosen and not self._is_valid_engine(chosen, version_type):
            raise BridgeError("invalidEngine",
                              f"{chosen} is not an Unreal Engine {version} installation.")
        path = chosen or self._engine_path(version_type)
        if not path:
            raise BridgeError("invalidEngine", self._engine(version_type)["reason"])
        self._set_engine_path(version_type, path)
        return path

    # --- migration ----------------------------------------------------------

    def _preflight(self, project_dir: str) -> dict:
        metadata = FileUtilityManager.get_metadata(project_dir)
        name = metadata.get("project_name") or ""
        needed, current_version, target_version = FileUtilityManager.validate_migration_requirements(
            name, project_dir)
        target_version = target_version or config.get_target_unreal_engine_version()

        # FileUtilityManager.create_migrated_project_copy names the copy
        # <metadata project_name>_<target>; a project with no metadata has nothing to
        # name a copy after, and the flow refuses it.
        destination_name = f"{name}_{target_version}" if name else ""
        destination_dir = (os.path.join(str(self.input_manager.get_script_dir()), destination_name)
                           if destination_name else "")
        return {"destinationName": destination_name, "destinationDir": destination_dir,
                "exists": bool(destination_dir) and os.path.isdir(destination_dir),
                "currentVersion": current_version, "targetVersion": target_version,
                "needed": bool(needed)}

    # --- runs ---------------------------------------------------------------

    def _create(self, params: dict) -> dict:
        self._refuse_if_busy()
        self._require_account("Sign in to Convai before creating a project.")
        name = str(params.get("name") or "").strip()
        problem = InputManager.validate_project_name(name, self.input_manager.get_script_dir())
        if problem:
            raise BridgeError("invalidName", problem)
        engine = self._require_engine(params, "enginePath", "current")

        run_id = self._claim()
        manager = self.input_manager
        manager.reset()
        manager.project_name = name
        manager.convai_api_key = self.account.api_key
        manager.asset_type = params.get("assetType") or "Scene"
        manager.is_metahuman = bool(params.get("isMetahuman"))
        manager.unreal_engine_path = engine
        return self._start(run_id, self.flows["create"], CREATE_STEPS, subject=name,
                           folder=os.path.join(str(manager.get_script_dir()), name))

    def _update(self, params: dict) -> dict:
        self._refuse_if_busy()
        self._require_account("Sign in to Convai before updating this project.")
        project_dir = self._project_dir(params)
        engine = self._require_engine(params, "enginePath", "current")

        run_id = self._claim()
        manager = self.input_manager
        manager.reset()
        manager.unreal_engine_path = engine
        manager.project_dir = project_dir
        return self._start(run_id, self.flows["update"], UPDATE_STEPS,
                           subject=os.path.basename(project_dir.rstrip("\\/")), folder=project_dir)

    def _migrate(self, params: dict) -> dict:
        self._refuse_if_busy()
        self._require_account("Sign in to Convai before migrating this project.")
        project_dir = self._project_dir(params)
        destination = self._preflight(project_dir)
        if not destination["destinationName"]:
            raise BridgeError("invalidName",
                              "This project has no Convai metadata, so the tool cannot tell what to "
                              "call the copy. Only projects created by this tool can be migrated.")
        if destination["exists"]:
            raise BridgeError("destinationExists",
                              f"Free the name {destination['destinationName']} before migrating.")
        engine = self._require_engine(params, "enginePath", "current")
        target_engine = self._require_engine(params, "targetEnginePath", "target")

        run_id = self._claim()
        manager = self.input_manager
        manager.reset()
        manager.unreal_engine_path = engine
        manager.project_dir = project_dir
        manager.target_unreal_engine_path = target_engine
        return self._start(run_id, self.flows["migrate"], MIGRATE_STEPS,
                           subject=destination["destinationName"],
                           folder=destination["destinationDir"])

    def _require_account(self, reason: str) -> None:
        if not self.account.is_signed_in:
            raise BridgeError("notSignedIn", reason)

    def _refuse_if_busy(self) -> None:
        """Checked before a run command touches the InputManager the live run is reading."""
        if self._run_id is not None:
            raise BridgeError("busy", "A run is already in progress. Wait for it to finish.")

    def _claim(self) -> str:
        """Take the one run slot, or say it is taken. Held until the run reports back."""
        with self._lock:
            self._refuse_if_busy()
            self._run_id = uuid.uuid4().hex
            # Only the live run's log is kept: the one before it has had its chance to be saved.
            self._log_lines = {self._run_id: []}
            return self._run_id

    def _start(self, run_id: str, flow: Callable[[], Optional[str]], steps: list,
               subject: str, folder: str) -> dict:
        """Run `flow` on a worker, streaming its log and its steps until it reports back."""
        titles, marks = step_titles(steps), step_marks(steps)
        self._log_subject = subject
        records: queue.Queue = queue.Queue()
        handler = logging.handlers.QueueHandler(records)
        logger.logger.addHandler(handler)
        self._emit(event("steps", {"runId": run_id, "steps": steps_view(titles, 0)}))

        finished = threading.Event()
        lines = self._log_lines[run_id]
        # The flow logs on its own thread; the queue keeps its progress from waiting on
        # however slowly the host delivers an event.
        reached = 0

        def pump() -> None:
            nonlocal reached
            while True:
                try:
                    record = records.get(timeout=0.1)
                except queue.Empty:
                    if finished.is_set():
                        return
                    continue
                line = record.getMessage()
                lines.append(line)
                self._emit(event("log", {"runId": run_id, "line": line}))
                index = step_from_line(marks, reached, line)
                if index is not None:
                    reached = index
                    self._emit(event("steps", {"runId": run_id, "steps": steps_view(titles, index)}))

        def work() -> None:
            ok, notes, failure = True, None, None
            try:
                result = flow()
                notes = result if isinstance(result, str) else None
            except ConvaiToolError as exc:
                ok, failure = False, str(exc)
            except Exception as exc:
                logger.error(traceback.format_exc())
                ok, failure = False, repr(exc)
            finally:
                # The handler goes first, so nothing logged after this run can arrive on
                # its stream -- and the drain then ends on an empty queue.
                logger.logger.removeHandler(handler)
                finished.set()

            pumping.join()
            if ok:
                self._emit(event("steps", {"runId": run_id,
                                           "steps": steps_view(titles, len(titles), finished=True)}))
            self._emit(event("runFinished", {"runId": run_id, "ok": ok, "subject": subject,
                                             "folder": folder, "notes": notes, "error": failure}))
            with self._lock:
                if self._run_id == run_id:
                    self._run_id = None

        pumping = threading.Thread(target=pump, daemon=True)
        pumping.start()
        threading.Thread(target=work, daemon=True).start()
        return {"runId": run_id}

    # --- files and folders --------------------------------------------------

    def _open_path(self, params: dict) -> dict:
        path = str(params.get("path") or "")
        if not path or not os.path.exists(path):
            raise BridgeError("notFound", "That folder is no longer there.")
        try:
            os.startfile(path)
        except OSError as exc:
            raise BridgeError("unknown", f"Could not open {path}. {exc}")
        return {}

    def _save_log(self, params: dict) -> dict:
        run_id = str(params.get("runId") or "")
        lines = self._log_lines.get(run_id)
        if lines is None:
            raise BridgeError("notFound", "That log is no longer available.")
        if self.save_file is None:
            raise BridgeError("unknown", NO_DIALOG)
        path = self.save_file("Save technical log", f"{self._log_subject or 'ConvaiModdingTool'}.log")
        if not path:
            return {}
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines))
        except OSError as exc:
            raise BridgeError("unknown", f"Could not save the log: {exc.strerror or exc}")
        return {"path": path}

    # --- settings -----------------------------------------------------------

    def _install_toolchain(self, params: dict) -> dict:
        with self._lock:
            if self._installing:
                raise BridgeError("busy", "The toolchain is already being installed.")
            self._installing = True

        version = config.get_current_unreal_engine_version()
        self._emit(event("toolchain", {"state": "installing", "message": INSTALLING}))
        try:
            from core.download_utils import DownloadManager

            installed = DownloadManager.ensure_toolchain_for_version(version, force=True)
            message = ("Toolchain ready." if installed
                       else "Install failed — see the technical log for details.")
        except Exception as exc:
            installed, message = False, f"Install failed: {exc}"
        finally:
            self._installing = False

        self._emit(event("toolchain", {"state": "done" if installed else "failed",
                                       "message": message}))
        return {"installed": bool(installed)}

    def _packaging_status(self, params: dict) -> dict:
        return {"linuxEnabled": config.linux_packaging_enabled(),
                "engineVersion": config.get_current_unreal_engine_version()}

    def _check_updates(self, params: dict) -> dict:
        try:
            up_to_date = _version_manager().check_version(self.tool_version)
        except Exception:
            up_to_date = None
        return {"upToDate": up_to_date, "latest": self._required_version()}

    def _download_update(self, params: dict) -> dict:
        from core.version_manager import LATEST_RELEASE_URL

        webbrowser.open(LATEST_RELEASE_URL, new=2)
        return {}

    def _quit(self, params: dict) -> dict:
        if self.on_quit is not None:
            self.on_quit()
        return {}
