import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from core.config_manager import config
from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager
from core.plugin_manager import PluginManager
from core.logger import logger

class UnrealEngineManager:
    """
    Manages Unreal Engine operations: project setup, building, plugins, and INI configuration.
    """
    def __init__(self, ue_dir: str, project_name: str = None, project_dir: str = None):
        self.ue_dir = ue_dir
        self.project_name = project_name
        self.project_dir = project_dir
        self.engine_version = UnrealEngineManager._extract_engine_version(ue_dir)
        
    def build_project_structure(self) -> bool:
        """
        Creates a new Unreal Engine project based on the TP_Blank template.
        """
        if not all([self.ue_dir, self.project_name, self.project_dir, self.engine_version]):
            raise ValueError("UnrealEngineManager not fully initialized.")
        if len(self.project_name) > 20:
            logger.error("Project name exceeds 20 characters")
            return False
        if os.path.exists(self.project_dir):
            logger.error(f"Directory already exists: {self.project_dir}")
            return False

        template = os.path.join(self.ue_dir, "Templates", "TP_Blank")
        shutil.copytree(template, self.project_dir)
        os.makedirs(os.path.join(self.project_dir, 'Content'), exist_ok=True)
        FileUtilityManager.update_directory_structure(self.project_dir, "TP_Blank", self.project_name)
        self._set_engine_version(
            os.path.join(self.project_dir, f"{self.project_name}.uproject"),
            self.engine_version
        )
        logger.success(f"Created project structure for '{self.project_name}'")
        return True

    def run_unreal_build(self) -> None:
        ubt = os.path.join(
            self.ue_dir,
            "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe"
        )
        if not os.path.exists(ubt):
            logger.error(f"UnrealBuildTool not found: {ubt}")
            return
        cmd = [
            ubt,
            f"-Project={self.project_dir}/{self.project_name}.uproject",
            f"-Target={self.project_name}Editor",
            "Win64",
            "Development",
            "-Progress",
            "-NoHotReload",
        ]
        logger.info("Starting project compilation...")
        
        # Run compilation with live output streaming (just like original)
        result = subprocess.run(cmd, shell=True)
        
        # Final status
        if result.returncode != 0:
            logger.error("Compilation failed")
        else:
            logger.success("Compilation completed successfully")
            
        # Log file information for detailed troubleshooting
        log_file = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'UnrealBuildTool', 'Log.txt')
        if os.path.exists(log_file):
            logger.info(f"Full build log also available at: {log_file}")

    def enable_plugins(self, plugins: list[str]) -> None:
        uproject_path = os.path.join(self.project_dir, f"{self.project_name}.uproject")
        enabled_count = 0
        for plugin in plugins:
            if self._enable_plugin(uproject_path, plugin):
                enabled_count += 1
        logger.debug(f"Enabled {enabled_count} plugins in project")

    def create_content_only_plugin(self, plugin_name: str) -> None:
        plugin_dir = Path(self.project_dir) / 'Plugins' / plugin_name
        content_dir = plugin_dir / 'Content'
        os.makedirs(content_dir, exist_ok=True)
        up_file = plugin_dir / f"{plugin_name}.uplugin"
        data = {
            'FileVersion': 3,
            'Version': 1,
            'VersionName': '1.0',
            'FriendlyName': plugin_name,
            'Description': f"{plugin_name} content-only plugin.",
            'Category': 'Other',
            'CreatedBy': 'Convai modding tool',
            'CanContainContent': True,
            'Installed': False,
        }
        with open(up_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        logger.debug(f"Created content plugin: {plugin_name}")

    def update_ini_files(self, plugin_name: str, api_key: str) -> None:
        logger.debug("Updating project configuration files...")
        self._update_game_ini(self.project_dir, plugin_name)
        self._update_engine_ini(self.project_dir, api_key)
        self._update_input_ini(self.project_dir)

    def update_modding_dependencies(self) -> None:
        logger.subsection("Analyzing Current Installation")
        
        content_dir = os.path.join(self.project_dir, config.get_content_dir_name())
        paths_to_delete = []
        
        # Use find_plugin_directory to locate existing Convai plugins from config
        convai_plugin_names = [
            config.get_plugin_file_name("convai"),
            config.get_plugin_file_name("convai_http"), 
            config.get_plugin_file_name("convai_pak_manager")
        ]
        
        plugin_count = 0
        for plugin_file in convai_plugin_names:
            plugin_dir = PluginManager.find_plugin_directory(self.project_dir, plugin_file)
            if plugin_dir:
                paths_to_delete.append(plugin_dir)
                plugin_count += 1
        
        # Add content pack directory if it exists
        convenience_pack_dir = os.path.join(content_dir, config.get_convenience_pack_name())
        content_pack_found = False
        if os.path.exists(convenience_pack_dir):
            paths_to_delete.append(convenience_pack_dir)
            content_pack_found = True
        
        # Get zip files from ConvaiEssentials directory
        zip_dir = os.path.join(self.project_dir, config.get_essentials_dir_name())
        zip_files = []
        if os.path.exists(zip_dir):
            zip_files = [os.path.join(zip_dir, f) for f in os.listdir(zip_dir) if f.lower().endswith(".zip")]

        # Log what was found
        if plugin_count > 0:
            logger.info(f"Found {plugin_count} existing plugin(s) to update")
        if content_pack_found:
            logger.info("Found existing content pack to update")
        if zip_files:
            logger.info(f"Found {len(zip_files)} zip file(s) to clean up")

        # Delete old installations and download fresh copies
        if paths_to_delete:
            logger.step(f"Removing {len(paths_to_delete)} existing installation(s)...")
            FileUtilityManager.delete_paths(paths_to_delete)
        
        if zip_files:
            logger.step("Cleaning up old zip files...")
            FileUtilityManager.delete_paths(zip_files)
        
        logger.step("Downloading latest dependencies...")
        DownloadManager.download_modding_dependencies(self.project_dir)
    
    def configure_assets_in_project(self, asset_type: str, is_metahuman: bool) -> None:
        logger.debug("Configuring project assets...")
        
        # Find ConvaiPakManager plugin directory dynamically
        pak_manager_dir = PluginManager.find_plugin_directory(self.project_dir, config.get_plugin_file_name("convai_pak_manager"))
        if not pak_manager_dir:
            logger.error("ConvaiPakManager plugin directory not found")
            return
        
        source = os.path.join(pak_manager_dir, config.get_content_dir_name(), config.get_editor_dir_name(), config.get_uploader_asset_name())
        destination = os.path.join(self.project_dir, config.get_content_dir_name(), config.get_editor_dir_name())
        
        if not os.path.exists(source):
            logger.error(f"{config.get_uploader_asset_name()} not found at expected location")
            return
            
        FileUtilityManager.copy_file_to_directory(source, destination)

        if asset_type == "Scene" and not is_metahuman:
            self.remove_metahuman_folder()
        if asset_type == "Avatar" and not is_metahuman:
            DownloadManager.download_convai_realusion_content(self.project_dir)
            self.remove_metahuman_folder()
    
    def can_create_modding_project(self) -> None:
        """
        Verifies that all prerequisites for creating a modding project are met.
        Checks Unreal Engine version and cross-compilation toolchain.
        Exits the process with an error message if any check fails.
        """
        # Engine version check
        if not self.engine_version or not UnrealEngineManager.is_supported_engine_version(self.engine_version):
            supported_versions = ', '.join(config.get_supported_engine_versions())
            logger.error(f"Unreal Engine version {self.engine_version} is not supported. Supported versions: {supported_versions}")
            return False

        # Cross-compilation toolchain check
        env_var = config.get_cross_compilation_env_var()
        toolchain_root = os.environ.get(env_var)          
        required_version = config.get_cross_compilation_toolchain()
        
        if not toolchain_root:
            logger.error(f"{env_var} environment variable is not set")
            return False
        
        basename = os.path.basename(toolchain_root.strip("\\/"))        
        if basename != required_version:
            logger.error(f"Cross-compilation toolchain version mismatch. Found '{basename}', expected '{required_version}'")
            return False
        
        if not os.path.exists(toolchain_root):
            logger.error(f"Toolchain path does not exist: {toolchain_root}")
            return False
        
        return True
    
    def remove_metahuman_folder(self) -> None:
        """
        Deletes the MetaHumans folder under the project directory, if it exists.
        """
        # Find the Convai plugin directory and remove MetaHumans folder
        convai_plugin_dir = PluginManager.find_plugin_directory(self.project_dir, config.get_plugin_file_name("convai"))
        if convai_plugin_dir:
            metahuman_dir = os.path.join(convai_plugin_dir, config.get_content_dir_name(), config.get_metahumans_folder_name())
            if os.path.exists(metahuman_dir):
                FileUtilityManager.delete_directory_if_exists(metahuman_dir)
                logger.debug("Removed MetaHumans folder from project")
    
    @staticmethod
    def _extract_engine_version(installation_dir: str) -> str:
        """
        Parses Version.h to determine engine version.
        """
        version_file = os.path.join(
            installation_dir,
            "Engine",
            "Source",
            "Runtime",
            "Launch",
            "Resources",
            "Version.h",
        )
        if not os.path.exists(version_file):
            logger.error("Version.h not found. Check engine installation")
            return None

        version = {}
        try:
            with open(version_file, 'r', encoding='utf-8') as f:
                for line in f:
                    m1 = re.search(r"ENGINE_MAJOR_VERSION\s+(\d+)", line)
                    m2 = re.search(r"ENGINE_MINOR_VERSION\s+(\d+)", line)
                    if m1:
                        version['major'] = m1.group(1)
                    if m2:
                        version['minor'] = m2.group(1)
            if 'major' in version and 'minor' in version:
                return f"{version['major']}.{version['minor']}"
        except Exception as e:
            logger.error(f"Error reading engine version: {e}")
        return None

    @staticmethod
    def is_supported_engine_version(engine_version: str) -> bool:
        return engine_version in config.get_supported_engine_versions()

    @staticmethod
    def is_valid_engine_path(path: Path) -> bool:
        if not path.exists():
            return False
        ver = UnrealEngineManager._extract_engine_version(str(path))
        return bool(ver and UnrealEngineManager.is_supported_engine_version(ver))

    @staticmethod
    def _set_engine_version(uproject_file: str, engine_version: str) -> None:
        try:
            with open(uproject_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['EngineAssociation'] = engine_version
            with open(uproject_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            logger.error(f"Error updating .uproject file: {e}")

    @staticmethod
    def _get_project_engine_version(uproject_file: str) -> str:
        """
        Get the current EngineAssociation from a .uproject file.
        
        Args:
            uproject_file: Path to the .uproject file
            
        Returns:
            Engine version string or None if not found or error
        """
        try:
            with open(uproject_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('EngineAssociation')
        except Exception as e:
            logger.error(f"Error reading .uproject file: {e}")
            return None

    def update_project_engine_version(self) -> bool:
        """
        Update the project's engine version to match the current engine installation.
        
        Returns:
            True if updated or no update needed, False if error
        """
        if not self.project_name or not self.project_dir or not self.engine_version:
            logger.error("UnrealEngineManager not fully initialized for engine version update")
            return False
            
        uproject_file = os.path.join(self.project_dir, f"{self.project_name}.uproject")
        if not os.path.exists(uproject_file):
            logger.error(f"Project file not found: {uproject_file}")
            return False
        
        current_version = self._get_project_engine_version(uproject_file)
        target_version = self.engine_version
        
        if current_version == target_version:
            logger.debug(f"Project engine version is already up to date ({target_version})")
            return True
        
        if current_version:
            logger.step(f"Updating project engine version from {current_version} to {target_version}...")
        else:
            logger.step(f"Setting project engine version to {target_version}...")
            
        self._set_engine_version(uproject_file, target_version)
        logger.success(f"Updated project to Unreal Engine {target_version}")
        return True

    @staticmethod
    def _enable_plugin(
        uproject_path: str,
        name: str,
        marketplace_url: str = "",
    ) -> bool:
        try:
            with open(uproject_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data.setdefault('Plugins', [])
            if any(x.get('Name') == name for x in data['Plugins']):
                return False
            entry = {'Name': name, 'Enabled': True}
            if marketplace_url:
                entry['MarketplaceURL'] = marketplace_url
            data['Plugins'].append(entry)
            with open(uproject_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            return True
        except:
            return False

    @staticmethod
    def _update_game_ini(project_dir, plugin_name):
        """
        Updates the DefaultGame.ini file in the project's Config directory with the required settings.

        This function writes hardcoded settings to DefaultGame.ini. It replaces the <PluginName> placeholder
        with the provided plugin_name.

        Args:
            project_dir (str): The path to your Unreal project directory.
            plugin_name (str): The name of the content-only plugin.
        """
        # Ensure the Config directory exists
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)

        # Path to the DefaultGame.ini file
        default_game_ini_path = os.path.join(config_dir, config.get_config_file_name("default_game"))

        # Hardcoded INI content with <PluginName> placeholder
        ini_content = r'''
[/Script/UnrealEd.ProjectPackagingSettings]
bUseIoStore=False
bGenerateChunks=True
bShareMaterialShaderCode=False
UsePakFile=True

[/Script/Engine.AssetManagerSettings]
-PrimaryAssetTypesToScan=(PrimaryAssetType="Map",AssetBaseClass=/Script/Engine.World,bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=((Path="/Game/Maps")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
-PrimaryAssetTypesToScan=(PrimaryAssetType="PrimaryAssetLabel",AssetBaseClass=/Script/Engine.PrimaryAssetLabel,bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=((Path="/Game")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
+PrimaryAssetTypesToScan=(PrimaryAssetType="Map",AssetBaseClass="/Script/Engine.World",bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=((Path="/Game/Maps")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
+PrimaryAssetTypesToScan=(PrimaryAssetType="PrimaryAssetLabel",AssetBaseClass="/Script/Engine.PrimaryAssetLabel",bHasBlueprintClasses=False,bIsEditorOnly=False,Directories=((Path="/Game"),(Path="/<PluginName>")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
bOnlyCookProductionAssets=False
bShouldManagerDetermineTypeAndName=False
bShouldGuessTypeAndNameInEditor=True
bShouldAcquireMissingChunksOnLoad=False
bShouldWarnAboutInvalidAssets=True
MetaDataTagsForAssetRegistry=()
        '''
        # Replace <PluginName> with the actual plugin name
        ini_content = ini_content.replace("<PluginName>", plugin_name)

        # Write the content to DefaultGame.ini
        with open(default_game_ini_path, "w", encoding="utf-8") as file:
            file.write(ini_content.strip() + "\n")

        logger.debug(f"Updated DefaultGame.ini with plugin: {plugin_name}")

    @staticmethod
    def _update_engine_ini(project_dir, convai_api_key):
        """
        Appends the Convai API key to the DefaultEngine.ini file in the project's Config directory.

        Args:
            project_dir (str): The path to your Unreal project directory.
            api_key (str): The Convai API key entered by the user.
        """
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)

        default_engine_ini_path = os.path.join(config_dir, config.get_config_file_name("default_engine"))

        # Lines to append
        lines_to_add = f"""
[/Script/EngineSettings.GameMapsSettings]
GlobalDefaultGameMode=/Game/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C

[/Script/Convai.ConvaiSettings]
API_Key={convai_api_key}
"""
        with open(default_engine_ini_path, "a", encoding="utf-8") as file:
            file.write(lines_to_add.strip() + "\n")
        logger.debug("Updated DefaultEngine.ini with API key")
    
    @staticmethod
    def _update_input_ini(project_dir):
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)
        default_input_ini_path = os.path.join(config_dir, config.get_config_file_name("default_input"))

        # Lines to append
        content_to_write = f"""
[/Script/Engine.InputSettings]
-AxisConfig=(AxisKeyName="Gamepad_LeftX",AxisProperties=(DeadZone=0.25,Exponent=1.f,Sensitivity=1.f))
-AxisConfig=(AxisKeyName="Gamepad_LeftY",AxisProperties=(DeadZone=0.25,Exponent=1.f,Sensitivity=1.f))
-AxisConfig=(AxisKeyName="Gamepad_RightX",AxisProperties=(DeadZone=0.25,Exponent=1.f,Sensitivity=1.f))
-AxisConfig=(AxisKeyName="Gamepad_RightY",AxisProperties=(DeadZone=0.25,Exponent=1.f,Sensitivity=1.f))
-AxisConfig=(AxisKeyName="MouseX",AxisProperties=(DeadZone=0.f,Exponent=1.f,Sensitivity=0.07f))
-AxisConfig=(AxisKeyName="MouseY",AxisProperties=(DeadZone=0.f,Exponent=1.f,Sensitivity=0.07f))
-AxisConfig=(AxisKeyName="Mouse2D",AxisProperties=(DeadZone=0.f,Exponent=1.f,Sensitivity=0.07f))
+AxisConfig=(AxisKeyName="Gamepad_LeftX",AxisProperties=(DeadZone=0.250000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_LeftY",AxisProperties=(DeadZone=0.250000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_RightX",AxisProperties=(DeadZone=0.250000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_RightY",AxisProperties=(DeadZone=0.250000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MouseX",AxisProperties=(DeadZone=0.000000,Sensitivity=0.070000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MouseY",AxisProperties=(DeadZone=0.000000,Sensitivity=0.070000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Mouse2D",AxisProperties=(DeadZone=0.000000,Sensitivity=0.070000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MouseWheelAxis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_LeftTriggerAxis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_RightTriggerAxis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_Special_Left_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Gamepad_Special_Left_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Left_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Left_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Left_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Right_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Right_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="Vive_Right_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Left_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Left_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Left_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Left_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Left_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Right_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Right_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Right_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Right_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="MixedReality_Right_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Left_Grip_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Left_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Left_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Left_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Right_Grip_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Right_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Right_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="OculusTouch_Right_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Grip_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Grip_Force",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Trackpad_Force",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Left_Trackpad_Touch",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Grip_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Grip_Force",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Trigger_Axis",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Thumbstick_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Thumbstick_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Trackpad_X",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Trackpad_Y",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
+AxisConfig=(AxisKeyName="ValveIndex_Right_Trackpad_Force",AxisProperties=(DeadZone=0.000000,Sensitivity=1.000000,Exponent=1.000000,bInvert=False))
bAltEnterTogglesFullscreen=True
bF11TogglesFullscreen=True
bUseMouseForTouch=False
bEnableMouseSmoothing=True
bEnableFOVScaling=True
bCaptureMouseOnLaunch=True
bEnableLegacyInputScales=True
bAlwaysShowTouchInterface=False
bShowConsoleOnFourFingerTap=True
bEnableGestureRecognizer=False
bUseAutocorrect=False
DefaultViewportMouseCaptureMode=CapturePermanently_IncludingInitialMouseDown
DefaultViewportMouseLockMode=LockOnCapture
FOVScale=0.011110
DoubleClickTime=0.200000
+ActionMappings=(ActionName="Jump",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=Gamepad_FaceButton_Bottom)
+ActionMappings=(ActionName="Jump",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=SpaceBar)
+ActionMappings=(ActionName="PrimaryAction",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=Gamepad_RightTrigger)
+ActionMappings=(ActionName="PrimaryAction",bShift=False,bCtrl=False,bAlt=False,bCmd=False,Key=LeftMouseButton)
+AxisMappings=(AxisName="Look Up / Down Gamepad",Scale=1.000000,Key=Gamepad_RightY)
+AxisMappings=(AxisName="Look Up / Down Mouse",Scale=-1.000000,Key=MouseY)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=W)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=-1.000000,Key=S)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=Up)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=-1.000000,Key=Down)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=Gamepad_LeftY)
+AxisMappings=(AxisName="Move Right / Left",Scale=-1.000000,Key=A)
+AxisMappings=(AxisName="Move Right / Left",Scale=1.000000,Key=D)
+AxisMappings=(AxisName="Move Right / Left",Scale=1.000000,Key=Gamepad_LeftX)
+AxisMappings=(AxisName="Turn Right / Left Gamepad",Scale=1.000000,Key=Gamepad_RightX)
+AxisMappings=(AxisName="Turn Right / Left Mouse",Scale=1.000000,Key=MouseX)
DefaultPlayerInputClass=/Script/EnhancedInput.EnhancedPlayerInput
DefaultInputComponentClass=/Script/EnhancedInput.EnhancedInputComponent
DefaultTouchInterface=/Engine/MobileResources/HUD/DefaultVirtualJoysticks.DefaultVirtualJoysticks
-ConsoleKeys=Tilde
+ConsoleKeys=Tilde
+ConsoleKeys=Caret
"""
        with open(default_input_ini_path, "w", encoding="utf-8") as file:
            file.write(content_to_write.strip() + "\n")
        logger.debug("Updated DefaultInput.ini")
