import json
import os
import time
import requests
from dataclasses import dataclass
from typing import Dict, List, Any, Optional

from core.logger import logger
from core.exceptions import ConfigurationError


@dataclass(frozen=True)
class RemoteConfig:
    """Immutable configuration loaded from remote source."""
    config: Dict[str, Any]
    version_data: Dict[str, Any]
    uploader_config: Dict[str, Any]


# Used when resources/asset_uploader_config.json cannot be fetched. The exe bundles
# no data files, so the fallback has to live in code.
DEFAULT_ASSET_UPLOADER_CONFIG = {
    "unreal-engine": {
        "windows": {
            "should-package": True,
            "configuration": "Shipping"
        },
        "linux": {
            "should-package": False,
            "configuration": "Shipping"
        }
    },
    "raw-project-upload": True
}


class ConfigManager:
    """Manages configuration settings for the Convai Modding Tool."""

    _instance: Optional['ConfigManager'] = None

    # GitHub configuration for fetching config
    GITHUB_REPO = "Conv-AI/Convai-UnrealEngine-ModdingTool"
    GITHUB_BRANCH = "main"
    CONFIG_FILE_PATH = "resources/modding_tool_config.json"
    VERSION_FILE_PATH = "Version.json"
    UPLOADER_CONFIG_FILE_PATH = "resources/asset_uploader_config.json"

    # Config ships via main, so a config change cannot be exercised until it is merged -
    # and merging it early breaks every distributed exe. Set either of these to try one
    # first: a branch name, or a checkout directory to read the files straight off disk.
    BRANCH_ENV = "CONVAI_MODDING_CONFIG_BRANCH"
    LOCAL_ENV = "CONVAI_MODDING_CONFIG_DIR"

    def __new__(cls) -> 'ConfigManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, max_attempts: int = 5, timeout: int = 30):
        if self._initialized:
            return
        self._max_attempts = max_attempts
        self._timeout = timeout
        # Loaded lazily so importing core.* never blocks on the network; seed this
        # directly with a RemoteConfig to run offline.
        self._remote_config: Optional[RemoteConfig] = None
        self._initialized = True

    @property
    def remote_config(self) -> RemoteConfig:
        self.load()
        return self._remote_config

    def load(self) -> None:
        """Fetch the remote configuration once. Safe to call repeatedly."""
        if self._remote_config is not None:
            return

        config_data = self._fetch_json(self.CONFIG_FILE_PATH)
        if not config_data:
            local_dir = os.environ.get(self.LOCAL_ENV)
            if local_dir:
                raise ConfigurationError(
                    f"Failed to read config from {self.LOCAL_ENV}={local_dir}. "
                    f"Expected {self.CONFIG_FILE_PATH} under it."
                )
            raise ConfigurationError(
                f"Failed to load config after {self._max_attempts} attempts. "
                "Please ensure GitHub is accessible."
            )

        version_data = self._fetch_json(self.VERSION_FILE_PATH) or {}

        uploader = self._fetch_json(self.UPLOADER_CONFIG_FILE_PATH)
        if uploader is None:
            logger.warning("Could not fetch asset uploader config, using built-in default")
            uploader = DEFAULT_ASSET_UPLOADER_CONFIG

        self._remote_config = RemoteConfig(
            config=config_data,
            version_data=version_data,
            uploader_config=uploader
        )

    def _fetch_json(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Fetch JSON from GitHub with retry logic and exponential backoff."""
        local_dir = os.environ.get(self.LOCAL_ENV)
        if local_dir:
            local_path = os.path.join(local_dir, *file_path.split('/'))
            try:
                with open(local_path, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
            except (OSError, json.JSONDecodeError) as e:
                # Don't fall through to the network: a half-local config is worse than a
                # clear stop, and the caller turns None into a visible failure.
                logger.error(f"{self.LOCAL_ENV} is set but {local_path} is unusable: {e}")
                return None
            logger.warning(f"Using local config override: {local_path}")
            return data

        branch = os.environ.get(self.BRANCH_ENV) or self.GITHUB_BRANCH
        if branch != self.GITHUB_BRANCH:
            logger.warning(f"Using config branch override: {branch}")
        url = f"https://raw.githubusercontent.com/{self.GITHUB_REPO}/{branch}/{file_path}"
        
        for attempt in range(self._max_attempts):
            try:
                response = requests.get(url, timeout=self._timeout)
                response.raise_for_status()
                return response.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                logger.debug(f"Attempt {attempt + 1} failed for {file_path}: {e}")
                if attempt < self._max_attempts - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s, 8s
        return None
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation.
        Example: get('unreal_engine.current_version')
        """
        keys = key_path.split('.')
        value = self.remote_config.config
        
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return default
            value = value[key]
        
        return value
    
    def get_current_unreal_engine_version(self) -> str:
        """Get current Unreal Engine version from cached version data."""
        version = self.remote_config.version_data.get('current-ue-version')
        if version:
            return version
        logger.warning("Version data is not valid, returning 5.5 as UE version")
        return '5.5'
    
    def get_target_unreal_engine_version(self) -> str:
        """Get target Unreal Engine version from cached version data."""
        version = self.remote_config.version_data.get('target-ue-version')
        if version:
            return version
        logger.warning("Version data is not valid, returning 5.8 as target UE version")
        return '5.8'
    
    def get_cross_compilation_toolchain(self, ue_version: str = None) -> str:
        """Get cross-compilation toolchain version for a specific UE version."""
        if ue_version is None:
            ue_version = self.get_current_unreal_engine_version()
        
        # Convert version format from "5.6" to "5_6" for JSON key lookup
        version_key = ue_version.replace('.', '_')
        lookup_path = f'cross_compilation.toolchain_versions.{version_key}'
        
        return self.get(lookup_path, 'v23_clang-18.1.0-rockylinux8')
    
    def get_cross_compilation_toolchain_url(self, toolchain_version: str) -> str:
        """Get download URL for a specific toolchain version."""
        lookup_path = f'cross_compilation.toolchain_download_urls.{toolchain_version}'
        result = self.get(lookup_path, '')
        
        # Fallback URLs if not found in config
        if not result:
            fallback_urls = {
                'v23_clang-18.1.0-rockylinux8': 'https://cdn.unrealengine.com/CrossToolchain_Linux/v23_clang-18.1.0-rockylinux8.exe',
                'v25_clang-18.1.0-rockylinux8': 'https://cdn.unrealengine.com/CrossToolchain_Linux/v25_clang-18.1.0-rockylinux8.exe'
            }
            result = fallback_urls.get(toolchain_version, '')
            if result:
                logger.info(f"🔄 Using fallback URL for {toolchain_version}")
        
        return result
    
    def get_cross_compilation_download_directory(self) -> str:
        """Get cross-compilation toolchain download directory (for .exe installers)."""
        directory = self.get('cross_compilation.toolchain_download_directory', '%APPDATA%\\ConvaiModdingTool\\Downloads')
        return os.path.expandvars(directory)
    
    def get_cross_compilation_install_directory(self) -> str:
        """Get cross-compilation toolchain installation directory (for extracted toolchains)."""
        return self.get('cross_compilation.toolchain_install_directory', 'C:\\UnrealToolchains')
    
    def get_cross_compilation_env_var(self) -> str:
        """Get cross-compilation environment variable name."""
        return self.get('cross_compilation.environment_variable', 'LINUX_MULTIARCH_ROOT')

    @staticmethod
    def _linux_enabled(uploader_cfg: Optional[Dict[str, Any]]) -> bool:
        """Read unreal-engine.linux.should-package out of an uploader config."""
        if not isinstance(uploader_cfg, dict):
            return False
        engine = uploader_cfg.get('unreal-engine')
        if not isinstance(engine, dict):
            return False
        linux = engine.get('linux')
        if not isinstance(linux, dict):
            return False
        return bool(linux.get('should-package', False))

    def linux_packaging_enabled(self) -> bool:
        """Whether the AssetUploader will package for Linux, gating all toolchain work."""
        return self._linux_enabled(self.remote_config.uploader_config)

    def get_google_drive_id(self, resource_name: str) -> str:
        """Get Google Drive file ID for a specific resource."""
        return self.get(f'google_drive.{resource_name}', '')
    
    def get_github_repo(self, plugin_name: str) -> str:
        """Get GitHub repository for a specific plugin."""
        return self.get(f'github.{plugin_name}.repo', '')
    
    def get_github_asset_patterns(self, plugin_name: str) -> List[str]:
        """Get GitHub asset patterns for a specific plugin."""
        return self.get(f'github.{plugin_name}.asset_patterns', ['.zip'])
    
    def get_github_post_process(self, plugin_name: str) -> bool:
        """Get whether a plugin needs post-processing after download."""
        return self.get(f'github.{plugin_name}.post_process', False)
    
    def get_github_plugins(self) -> List[str]:
        """Get list of all GitHub plugins configured."""
        github_config = self.get('github', {})
        return list(github_config.keys())
    
    def get_required_plugins(self) -> List[str]:
        """Get list of required plugins."""
        return self.get('project_settings.required_plugins', [])
    
    def get_metahuman_plugins(self) -> List[str]:
        """Get list of MetaHuman plugins."""
        return self.get('project_settings.metahuman_plugins', [])
    
    def get_max_project_name_length(self) -> int:
        """Get maximum allowed project name length."""
        return self.get('project_settings.max_project_name_length', 20)
    
    def get_modding_tool_version(self) -> str:
        """Get modding tool version."""
        return self.get('modding_tool.version', '1.0.0')

    # Directory name getters
    def get_plugins_dir_name(self) -> str:
        """Get plugins directory name."""
        return self.get('directory_names.plugins', 'Plugins')
    
    def get_content_dir_name(self) -> str:
        """Get content directory name."""
        return self.get('directory_names.content', 'Content')
    
    def get_config_dir_name(self) -> str:
        """Get config directory name."""
        return self.get('directory_names.config', 'Config')
    
    def get_essentials_dir_name(self) -> str:
        """Get essentials directory name."""
        return self.get('directory_names.essentials', 'ConvaiEssentials')
    
    # File name getters
    def get_config_file_name(self, file_type: str) -> str:
        """Get configuration file name by type."""
        return self.get(f'file_names.config_files.{file_type}', f'Default{file_type.title()}.ini')
    
    def get_metadata_file_name(self) -> str:
        """Get metadata file name."""
        return self.get('file_names.metadata_file', 'ModdingMetaData.txt')
    
    def get_plugin_file_name(self, plugin_type: str) -> str:
        """Get plugin file name by type."""
        return self.get(f'file_names.plugin_files.{plugin_type}', f'{plugin_type}.uplugin')
    
    def get_build_file_name(self) -> str:
        """Get build file name."""
        return self.get('file_names.build_file', 'Convai.Build.cs')
    
    # Asset name getters
    def get_metahumans_folder_name(self) -> str:
        """Get MetaHumans folder name."""
        return self.get('asset_names.metahumans_folder', 'MetaHumans')
    
    def get_convenience_pack_name(self) -> str:
        """Get convenience pack name."""
        return self.get('asset_names.convenience_pack', 'ConvaiConveniencePack')
    
    def get_template_name(self) -> str:
        """Get Unreal Engine template name."""
        return self.get('asset_names.template_name', 'TP_Blank')
    
    # Unreal Engine path getters
    def get_engine_binary_path(self) -> str:
        """Get Unreal Engine binary path."""
        return self.get('unreal_paths.engine_binary', 'Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe')
    
    def get_version_file_path(self) -> str:
        """Get version file path relative to engine directory."""
        return self.get('unreal_paths.version_file', 'Engine/Source/Runtime/Launch/Resources/Version.h')
    
    # UBT Configuration getters
    def get_ubt_config_appdata_path(self) -> str:
        """Get UBT BuildConfiguration.xml path relative to AppData."""
        return self.get('ubt_configuration.appdata_path', 'Unreal Engine/UnrealBuildTool/BuildConfiguration.xml')
    
    def get_ubt_xml_namespace(self) -> str:
        """Get UBT XML namespace."""
        return self.get('ubt_configuration.xml_namespace', 'https://www.unrealengine.com/BuildConfiguration')
    
    def get_ubt_required_settings(self) -> Dict[str, str]:
        """Get UBT required settings and their expected values."""
        return self.get('ubt_configuration.required_settings', {'bAllowUBALocalExecutor': 'false'})
    
    def get_ubt_xml_root_element(self) -> str:
        """Get UBT XML root element name."""
        return self.get('ubt_configuration.xml_template.root_element', 'Configuration')
    
    def get_ubt_xml_config_element(self) -> str:
        """Get UBT XML configuration element name."""
        return self.get('ubt_configuration.xml_template.config_element', 'BuildConfiguration')


# Singleton instance
config = ConfigManager()
