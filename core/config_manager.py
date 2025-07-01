from typing import Dict, List, Any

class ConfigManager:
    """Manages configuration settings for the Convai Modding Tool."""
    
    # Configuration data stored directly in Python
    _config = {
        "unreal_engine": {
            "current_version": "5.5",
            "target_version": "5.5",
            "supported_versions": ["5.5"],
            "default_paths": [
                "E:/Software/UE_5.5",
                "C:/Program Files/Epic Games/UE_5.5",
            ]
        },
        "cross_compilation": {
            "toolchain_version": "v23_clang-18.1.0-rockylinux8",
            "environment_variable": "LINUX_MULTIARCH_ROOT"
        },
        "google_drive": {
            "convai_pak_manager_plugin": "1Cioj7IhSV3s-bBHiFbgfcFyUIIsvHyfe",
            "convai_convenience_pack": "1y2lkBFo7ebRFt8SIiV9ME1mmRwgpnM3h",
            "plugins_folder": "11n7EZW4SBd4Ri9Q6GuXFdoLrwCZvnnwq",
            "convai_reallusion_content": "1bAatTW4vYycDbGLeO1pGILc3OVOOR3je"
        },
        "project_settings": {
            "max_project_name_length": 20,
            "required_plugins": [
                "ConvAI",
                "ConvaiHTTP", 
                "ConvaiPakManager",
                "JsonBlueprintUtilities"
            ]
        }
    }
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
        return cls._instance
    
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
        """Get current Unreal Engine version."""
        return self.get('unreal_engine.current_version', '5.5')
    
    def get_supported_engine_versions(self) -> List[str]:
        """Get list of supported Unreal Engine versions."""
        return self.get('unreal_engine.supported_versions', ['5.5'])
    
    def get_default_engine_paths(self) -> List[str]:
        """Get list of default Unreal Engine installation paths."""
        return self.get('unreal_engine.default_paths', [])
    
    def get_cross_compilation_toolchain(self) -> str:
        """Get cross-compilation toolchain version."""
        return self.get('cross_compilation.toolchain_version', 'v23_clang-18.1.0-rockylinux8')
    
    def get_cross_compilation_env_var(self) -> str:
        """Get cross-compilation environment variable name."""
        return self.get('cross_compilation.environment_variable', 'LINUX_MULTIARCH_ROOT')
    
    def get_google_drive_id(self, resource_name: str) -> str:
        """Get Google Drive file ID for a specific resource."""
        return self.get(f'google_drive.{resource_name}', '')
    
    def get_required_plugins(self) -> List[str]:
        """Get list of required plugins."""
        return self.get('project_settings.required_plugins', [])
    
    def get_max_project_name_length(self) -> int:
        """Get maximum allowed project name length."""
        return self.get('project_settings.max_project_name_length', 20)
    
    def get_modding_tool_version(self) -> str:
        """Get modding tool version."""
        return self.get('modding_tool.version', '1.0.0')

# Singleton instance
config = ConfigManager() 