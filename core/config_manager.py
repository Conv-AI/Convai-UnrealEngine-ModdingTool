import json
import requests
from typing import Dict, List, Any, Optional

from core.logger import logger

class ConfigManager:
    """Manages configuration settings for the Convai Modding Tool."""
    
    _instance = None
    
    # GitHub configuration for fetching config
    GITHUB_REPO = "Conv-AI/Convai-UnrealEngine-ModdingTool"
    GITHUB_BRANCH = "main"
    CONFIG_FILE_PATH = "resources/modding_tool_config.json"
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialize_config()
        return cls._instance
    
    def _initialize_config(self, max_attempts: int = 5):
        """Initialize configuration with retry logic."""
        self._config = None
        self._version_data = None
        
        # First, load config with max attempts
        for attempt in range(max_attempts):
            try:
                self._config = self._load_config_from_github()
                if self._config:
                    break
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Configuration load failed after {max_attempts} attempts: {e}")
        
        # If config loading failed completely, raise error
        if not self._config:
            raise RuntimeError(f"Could not load configuration after {max_attempts} attempts. Please ensure GitHub is accessible.")
        
        # Then, load version data with max attempts
        for attempt in range(max_attempts):
            try:
                self._version_data = self._load_version_from_github()
                if self._version_data:
                    break
                
            except Exception as e:
                if attempt == max_attempts - 1:
                    logger.error(f"Version data load failed after {max_attempts} attempts: {e}")
    
    def _load_config_from_github(self) -> Optional[Dict]:
        """Load configuration from GitHub repository using raw URL."""
        try:            
            raw_url = f"https://raw.githubusercontent.com/{self.GITHUB_REPO}/{self.GITHUB_BRANCH}/{self.CONFIG_FILE_PATH}"
            
            response = requests.get(raw_url, timeout=30)
            response.raise_for_status()
            
            return json.loads(response.text)
                
        except Exception as e:
            logger.debug(f"Failed to load config from GitHub: {e}")
        
        return None
    
    def _load_version_from_github(self) -> Optional[Dict]:
        """Load version data from Version.json on GitHub using raw URL."""
        try:            
            raw_url = f"https://raw.githubusercontent.com/{self.GITHUB_REPO}/{self.GITHUB_BRANCH}/Version.json"
            
            response = requests.get(raw_url, timeout=30)
            response.raise_for_status()
            
            return json.loads(response.text)
                
        except Exception as e:
            logger.debug(f"Failed to load version data from GitHub: {e}")
        
        return None
        
    def get(self, key_path: str, default=None) -> Any:
        """
        Get configuration value using dot notation.
        Example: get('unreal_engine.current_version')
        """
        keys = key_path.split('.')
        value = self._config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_unreal_engine_version(self) -> str:
        """Get current Unreal Engine version from cached version data."""
        if self._version_data:
            return self._version_data.get('current-ue-version', '5.5')
        logger.warning(f"version data is not valid returning 5.5 as ue version")
        return '5.5'
    
    def get_target_unreal_engine_version(self) -> str:
        """Get target Unreal Engine version from cached version data."""
        if self._version_data:
            return self._version_data.get('target-ue-version', '5.6')
        logger.warning(f"version data is not valid returning 5.6 as target ue version")
        return '5.6'
    
    def get_cross_compilation_toolchain(self) -> str:
        """Get cross-compilation toolchain version."""
        return self.get('cross_compilation.toolchain_version', 'v23_clang-18.1.0-rockylinux8')
    
    def get_cross_compilation_env_var(self) -> str:
        """Get cross-compilation environment variable name."""
        return self.get('cross_compilation.environment_variable', 'LINUX_MULTIARCH_ROOT')
    
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
        """Get list of required plugins."""
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
    
    def get_editor_dir_name(self) -> str:
        """Get editor directory name."""
        return self.get('directory_names.editor', 'Editor')
    
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
    def get_uploader_asset_name(self) -> str:
        """Get uploader asset name."""
        return self.get('asset_names.uploader_asset', 'AssetUploader.uasset')
    
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