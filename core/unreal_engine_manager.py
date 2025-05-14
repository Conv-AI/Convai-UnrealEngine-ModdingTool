import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager

class UnrealEngineManager:
    """
    Manages Unreal Engine operations: project setup, building, plugins, and INI configuration.
    """
    def __init__(self, ue_dir: str, project_name: str = None, project_dir: str = None):
        self.ue_dir = ue_dir
        self.project_name = project_name
        self.project_dir = project_dir
        self.engine_version = UnrealEngineManager.extract_engine_version(ue_dir)
    
    @staticmethod
    def extract_engine_version(installation_dir: str) -> str:
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
            print("Error: Version.h not found. Check engine installation.")
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
            print(f"Error reading version: {e}")
        return None

    @staticmethod
    def is_supported_engine_version(engine_version: str) -> bool:
        return engine_version in ["5.3"]

    @staticmethod
    def is_valid_engine_path(path: Path) -> bool:
        if not path.exists():
            return False
        ver = UnrealEngineManager.extract_engine_version(str(path))
        return bool(ver and UnrealEngineManager.is_supported_engine_version(ver))

    def build_project_structure(self) -> bool:
        """
        Creates a new Unreal Engine project based on the TP_Blank template.
        """
        if not all([self.ue_dir, self.project_name, self.project_dir, self.engine_version]):
            raise ValueError("UnrealEngineManager not fully initialized.")
        if len(self.project_name) > 20:
            print("Error: Project name exceeds 20 characters.")
            return False
        if os.path.exists(self.project_dir):
            print(f"Error: Directory exists: {self.project_dir}")
            return False

        template = os.path.join(self.ue_dir, "Templates", "TP_Blank")
        shutil.copytree(template, self.project_dir)
        os.makedirs(os.path.join(self.project_dir, 'Content'), exist_ok=True)
        FileUtilityManager.update_directory_structure(self.project_dir, "TP_Blank", self.project_name)
        self.set_engine_version(
            os.path.join(self.project_dir, f"{self.project_name}.uproject"),
            self.engine_version
        )
        print(f"Created project '{self.project_name}' at {self.project_dir}")
        return True

    @staticmethod
    def set_engine_version(uproject_file: str, engine_version: str) -> None:
        try:
            with open(uproject_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            data['EngineAssociation'] = engine_version
            with open(uproject_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error updating .uproject: {e}")

    def run_unreal_build(self) -> None:
        ubt = os.path.join(
            self.ue_dir,
            "Engine/Binaries/DotNET/UnrealBuildTool/UnrealBuildTool.exe"
        )
        if not os.path.exists(ubt):
            print(f"Error: UBT not found: {ubt}")
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
        print("Building Unreal project...")
        result = subprocess.run(cmd, shell=True)
        if result.returncode != 0:
            print("Compilation failed.")
        else:
            print("Compilation succeeded.")

    def enable_plugins(self, plugins: list[str]) -> None:
        uproject_path = os.path.join(self.project_dir, f"{self.project_name}.uproject")
        for plugin in plugins:
            self._enable_plugin(uproject_path, plugin)

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

    def update_ini_files(self, plugin_name: str, api_key: str) -> None:
        self._update_game_ini(self.project_dir, plugin_name)
        self._update_engine_ini(self.project_dir, api_key)
        self._update_input_ini(self.project_dir)

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
        config_dir = os.path.join(project_dir, "Config")
        os.makedirs(config_dir, exist_ok=True)

        # Path to the DefaultGame.ini file
        default_game_ini_path = os.path.join(config_dir, "DefaultGame.ini")

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

        print(f"DefaultGame.ini has been updated with plugin name: {plugin_name}")

    @staticmethod
    def _update_engine_ini(project_dir, convai_api_key):
        """
        Appends the Convai API key to the DefaultEngine.ini file in the project's Config directory.

        Args:
            project_dir (str): The path to your Unreal project directory.
            api_key (str): The Convai API key entered by the user.
        """
        config_dir = os.path.join(project_dir, "Config")
        os.makedirs(config_dir, exist_ok=True)

        default_engine_ini_path = os.path.join(config_dir, "DefaultEngine.ini")

        # Lines to append
        lines_to_add = f"""
[/Script/EngineSettings.GameMapsSettings]
GlobalDefaultGameMode=/Game/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C

[/Script/Convai.ConvaiSettings]
API_Key={convai_api_key}
"""
        with open(default_engine_ini_path, "a", encoding="utf-8") as file:
            file.write(lines_to_add.strip() + "\n")
    
    @staticmethod
    def _update_input_ini(project_dir):

        config_dir = os.path.join(project_dir, "Config")
        os.makedirs(config_dir, exist_ok=True)
        default_input_ini_path = os.path.join(config_dir, "DefaultInput.ini")

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
+AxisMappings=(AxisName="Move Forward / Backward",Scale=-1.000000,Key=Down)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=Gamepad_LeftY)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=-1.000000,Key=S)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=Up)
+AxisMappings=(AxisName="Move Forward / Backward",Scale=1.000000,Key=W)
+AxisMappings=(AxisName="Move Right / Left",Scale=-1.000000,Key=A)
+AxisMappings=(AxisName="Move Right / Left",Scale=1.000000,Key=D)
+AxisMappings=(AxisName="Move Right / Left",Scale=1.000000,Key=Gamepad_LeftX)
+AxisMappings=(AxisName="Turn Right / Left Gamepad",Scale=1.000000,Key=Gamepad_RightX)
+AxisMappings=(AxisName="Turn Right / Left Gamepad",Scale=-1.000000,Key=Left)
+AxisMappings=(AxisName="Turn Right / Left Gamepad",Scale=1.000000,Key=Right)
+AxisMappings=(AxisName="Turn Right / Left Mouse",Scale=1.000000,Key=MouseX)
DefaultPlayerInputClass=/Script/Engine.PlayerInput
DefaultInputComponentClass=/Script/Engine.InputComponent
DefaultTouchInterface=/Engine/MobileResources/HUD/DefaultVirtualJoysticks.DefaultVirtualJoysticks
-ConsoleKeys=Tilde
+ConsoleKeys=Tilde
    """

        with open(default_input_ini_path, "w", encoding="utf-8") as file:
            file.write(content_to_write.strip() + "\n")

    def update_modding_dependencies(self) -> None:
        paths_to_delete = [
            os.path.join(self.project_dir, "Plugins", "Convai"),
            os.path.join(self.project_dir, "Plugins", "ConvaiHTTP"),
            os.path.join(self.project_dir, "Plugins", "ConvaiPakManager"),
            os.path.join(self.project_dir, "Content", "ConvaiConveniencePack"),
        ]
        zip_dir = os.path.join(self.project_dir, "ConvaiEssentials")
        zip_files = [os.path.join(zip_dir, f) for f in os.listdir(zip_dir) if f.lower().endswith(".zip")]

        FileUtilityManager.delete_paths(paths_to_delete)
        FileUtilityManager.delete_paths(zip_files)
        DownloadManager.download_modding_dependencies(self.project_dir)
    
    def configure_assets_in_project(self, asset_type: str, is_metahuman: bool) -> None:
        source = os.path.join(
            self.project_dir,
            "Plugins",
            "ConvaiPakManager",
            "Content",
            "Editor",
            "AssetUploader.uasset"
        )
        destination = os.path.join(self.project_dir, "Content", "Editor")
        FileUtilityManager.copy_file_to_directory(source, destination)

        if asset_type == "Scene" and not is_metahuman:
            FileUtilityManager.remove_metahuman_folder(self.project_dir)
        if asset_type == "Avatar" and not is_metahuman:
            DownloadManager.download_convai_realusion_content(self.project_dir)