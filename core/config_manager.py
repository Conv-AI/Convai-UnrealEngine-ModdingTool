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
        "github": {
            "convai_plugin": {
                "repo": "Conv-AI/Convai-UnrealEngine-SDK",
                "asset_patterns": [".zip", "plugin", "unreal", "ue"],
                "post_process": True
            },
            "convai_http_plugin": {
                "repo": "Conv-AI/Convai-UnrealEngine-HTTP",
                "asset_patterns": [".zip", "plugin", "unreal", "ue"],
                "post_process": False
            },
            "convai_convenience_pack": {
                "repo": "Conv-AI/Convai-UnrealEngine-CCPack",
                "asset_patterns": [".zip", "pack", "convai", "convenience"],
                "post_process": False
            },
            "convai_pak_manager": {
                "repo": "Conv-AI/Convai-UnrealEngine-PakManager",
                "asset_patterns": [".zip", "plugin", "pak", "manager"],
                "post_process": False
            }
        },
        "google_drive": {
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
        },
        "directory_names": {
            "plugins": "Plugins",
            "content": "Content", 
            "config": "Config",
            "essentials": "ConvaiEssentials",
            "editor": "Editor",
            "source": "Source",
            "templates": "Templates"
        },
        "file_names": {
            "config_files": {
                "default_game": "DefaultGame.ini",
                "default_engine": "DefaultEngine.ini", 
                "default_input": "DefaultInput.ini"
            },
            "metadata_file": "ModdingMetaData.txt",
            "plugin_files": {
                "convai": "ConvAI.uplugin",
                "convai_http": "ConvaiHTTP.uplugin",
                "convai_pak_manager": "ConvaiPakManager.uplugin"
            },
            "build_file": "Convai.Build.cs"
        },
        "asset_names": {
            "uploader_asset": "AssetUploader.uasset",
            "metahumans_folder": "MetaHumans",
            "convenience_pack": "ConvaiConveniencePack",
            "template_name": "TP_Blank"
        },
        "unreal_paths": {
            "engine_binary": "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe",
            "version_file": "Engine/Source/Runtime/Launch/Resources/Version.h"
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
        """Get Unreal Engine version file path."""
        return self.get('unreal_paths.version_file', 'Engine/Source/Runtime/Launch/Resources/Version.h')

# Singleton instance
config = ConfigManager() 