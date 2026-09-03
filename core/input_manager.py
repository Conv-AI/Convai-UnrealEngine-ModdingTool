import os
import re
import winreg
from pathlib import Path
from typing import List, Optional

from core.config_manager import config
from core.exceptions import ProjectError
from core.unreal_engine_manager import UnrealEngineManager

_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")

class InputManager:
    """
    Holds the answers the GUI has collected. The flows read them back through the
    getters and never prompt: nothing here touches stdin.
    """
    def __init__(self, script_dir: str):
        self.script_dir = Path(script_dir)
        self.project_name = None
        self.convai_api_key = None
        self.asset_type = None
        self.is_metahuman = None
        self.unreal_engine_path = None
        self.target_unreal_engine_path = None
        self.project_dir = None

    def reset(self) -> None:
        """Clear per-run answers so a second run cannot inherit the first one's."""
        self.project_name = None
        self.convai_api_key = None
        self.asset_type = None
        self.is_metahuman = None
        self.project_dir = None
        self.target_unreal_engine_path = None

    @staticmethod
    def find_registry_engines():
        engines = []
        reg_path = r"SOFTWARE\EpicGames\Unreal Engine"  # ← raw string avoids the \U error
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                reg_path,
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_64KEY
            ) as base_key:
                i = 0
                while True:
                    try:
                        version = winreg.EnumKey(base_key, i)
                        with winreg.OpenKey(base_key, version) as subkey:
                            install_dir, _ = winreg.QueryValueEx(subkey, "InstalledDirectory")
                            engines.append((version, install_dir))
                        i += 1
                    except OSError:
                        break
        except FileNotFoundError:
            # Key doesn’t exist on this machine
            pass
        return engines

    def get_script_dir(self) -> str:
        return self.script_dir

    def find_existing_projects(self) -> List[str]:
        """Modding projects under the script directory, rescanned on every call."""
        essentials_dir_name = config.get_essentials_dir_name()
        projects = []
        for root, dirs, files in os.walk(str(self.script_dir)):
            if essentials_dir_name in dirs and any(f.endswith('.uproject') for f in files):
                projects.append(root)
                dirs[:] = []  # a project's own Content/ cannot hold another project
        return projects

    @staticmethod
    def detect_engine_path(version_type: str = "current") -> Optional[str]:
        """Registry lookup for an installed engine, exact version first. No prompting."""
        if version_type == "target":
            required_ue_version = config.get_target_unreal_engine_version()
            is_valid_path = UnrealEngineManager.is_valid_target_engine_path
        else:
            required_ue_version = config.get_current_unreal_engine_version()
            is_valid_path = UnrealEngineManager.is_valid_current_engine_path

        engines = InputManager.find_registry_engines()
        for registry_version, registry_path_str in engines:
            if registry_version == required_ue_version and is_valid_path(Path(registry_path_str)):
                return registry_path_str

        for _, registry_path_str in engines:
            if is_valid_path(Path(registry_path_str)):
                return registry_path_str

        return None

    def get_unreal_engine_path(self, version_type: str = "current") -> str:
        cached = self.target_unreal_engine_path if version_type == "target" else self.unreal_engine_path
        if cached:
            return cached

        detected = self.detect_engine_path(version_type)
        if detected:
            if version_type == "target":
                self.target_unreal_engine_path = detected
            else:
                self.unreal_engine_path = detected
            return detected

        required_ue_version = (config.get_target_unreal_engine_version() if version_type == "target"
                               else config.get_current_unreal_engine_version())
        raise ProjectError(f"Unreal Engine {required_ue_version} path not provided")

    def choose_project_dir(self) -> str:
        if not self.project_dir:
            raise ProjectError("No project selected")
        return self.project_dir

    @staticmethod
    def validate_project_name(name: str, root) -> Optional[str]:
        """Returns the reason a project name is unusable, or None when it is fine."""
        if not name:
            return "Project name cannot be empty."

        max_length = config.get_max_project_name_length()
        if len(name) > max_length:
            return f"Project name must not exceed {max_length} characters."

        if name[0].isdigit():
            return "Project name cannot start with a digit."

        if not _NAME_PATTERN.match(name):
            return "Project name can only contain letters, digits, and underscores (no spaces or special characters)."

        if (Path(root) / name).exists():
            return f"A project named '{name}' already exists. Please choose a different name."

        return None

    def get_project_name(self) -> str:
        if not self.project_name:
            raise ProjectError("Project name not provided")
        return self.project_name

    def get_api_key(self) -> str:
        if not self.convai_api_key:
            raise ProjectError("Convai API key not provided")
        return self.convai_api_key

    def get_asset_type(self) -> tuple[str, bool]:
        if not self.asset_type or self.is_metahuman is None:
            raise ProjectError("Asset type not provided")
        return self.asset_type, self.is_metahuman
