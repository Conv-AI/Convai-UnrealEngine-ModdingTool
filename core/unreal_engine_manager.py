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
        
    @staticmethod
    def _parse_ini_sections(raw: str):
        sections = {}
        current = None
        for raw_line in raw.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line
                sections.setdefault(current, [])
            else:
                if current is None:
                    # Skip lines before any section header
                    continue
                sections[current].append(line)
        return sections

    @staticmethod
    def _extract_ini_key(line: str):
        # Handles lines like `Key=Value`, `+Key=Value`, `-Key=Value`
        op = None
        rest = line
        if line and line[0] in ['+', '-']:
            op = line[0]
            rest = line[1:]
        if '=' in rest:
            key = rest.split('=', 1)[0].strip()
        else:
            key = rest.strip()
        return op, key

    @staticmethod
    def _merge_ini_file(target_path: str, desired_content: str, not_found_warning: str):
        """
        Merge desired INI content into an existing INI file at target_path.
        - Overrides scalar keys
        - De-duplicates +/- entries
        - Preserves unrelated content
        """
        existing_sections = {}
        if os.path.exists(target_path):
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    current = None
                    for raw_line in f.read().splitlines():
                        line = raw_line.rstrip('\n')
                        if not line.strip():
                            if current is not None:
                                existing_sections.setdefault(current, []).append("")
                            continue
                        if line.strip().startswith('[') and line.strip().endswith(']'):
                            current = line.strip()
                            existing_sections.setdefault(current, [])
                        else:
                            if current is None:
                                continue
                            existing_sections.setdefault(current, []).append(line.strip())
            except Exception as e:
                logger.warn(f"{not_found_warning}: {e}")
                existing_sections = {}
        
        desired_sections = UnrealEngineManager._parse_ini_sections(desired_content)

        for section, desired_lines in desired_sections.items():
            existing_lines = existing_sections.get(section, [])
            to_add_after_cleanup = []
            for dline in desired_lines:
                op, key = UnrealEngineManager._extract_ini_key(dline)
                if op is None:
                    new_existing = []
                    for eline in existing_lines:
                        eop, ekey = UnrealEngineManager._extract_ini_key(eline.strip())
                        if ekey == key and eop is None:
                            continue
                        new_existing.append(eline)
                    existing_lines = new_existing
                    to_add_after_cleanup.append(dline)
                else:
                    existing_lines = [eline for eline in existing_lines if eline.strip() != dline]
                    to_add_after_cleanup.append(dline)

            seen = set()
            unique_to_add = []
            for line in to_add_after_cleanup:
                if line not in seen:
                    unique_to_add.append(line)
                    seen.add(line)

            # Avoid introducing a blank line before newly appended settings
            while existing_lines and existing_lines[-1] == "":
                existing_lines.pop()

            existing_lines.extend(unique_to_add)
            existing_sections[section] = existing_lines

        section_order = list(existing_sections.keys())
        for sec in desired_sections.keys():
            if sec not in section_order:
                section_order.append(sec)

        with open(target_path, 'w', encoding='utf-8') as f:
            first = True
            for sec in section_order:
                if not first:
                    f.write("\n")
                first = False
                f.write(f"{sec}\n")
                lines = existing_sections.get(sec, [])
                # Trim leading/trailing blank lines within the section to avoid a blank right after header
                start_idx = 0
                end_idx = len(lines) - 1
                while start_idx <= end_idx and lines[start_idx] == "":
                    start_idx += 1
                while end_idx >= start_idx and lines[end_idx] == "":
                    end_idx -= 1
                for i in range(start_idx, end_idx + 1):
                    line = lines[i]
                    if line == "":
                        f.write("\n")
                    else:
                        f.write(f"{line}\n")

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
        Ensures required settings exist in DefaultGame.ini by overriding existing scalar keys
        and de-duplicating array-style (+/-) entries within their sections.

        Args:
            project_dir (str): The path to your Unreal project directory.
            plugin_name (str): The name of the content-only plugin.
        """
        # Ensure the Config directory exists
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)

        # Path to the DefaultGame.ini file
        default_game_ini_path = os.path.join(config_dir, config.get_config_file_name("default_game"))

        # Desired settings content with <PluginName> placeholder
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
        ini_content = ini_content.replace("<PluginName>", plugin_name)

        UnrealEngineManager._merge_ini_file(
            default_game_ini_path,
            ini_content,
            "Failed to read existing DefaultGame.ini, will recreate"
        )
        logger.debug(f"Merged DefaultGame.ini with plugin: {plugin_name}")

    @staticmethod
    def _update_engine_ini(project_dir, convai_api_key):
        """
        Ensures required settings exist in DefaultEngine.ini by overriding existing scalar keys
        and de-duplicating array-style (+/-) entries within their sections.

        Args:
            project_dir (str): The path to your Unreal project directory.
            api_key (str): The Convai API key entered by the user.
        """
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)

        default_engine_ini_path = os.path.join(config_dir, config.get_config_file_name("default_engine"))

        # Desired settings content (by section)
        lines_to_add = f"""
[/Script/EngineSettings.GameMapsSettings]
GlobalDefaultGameMode=/Game/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C

[/Script/WindowsTargetPlatform.WindowsTargetSettings]
DefaultGraphicsRHI=DefaultGraphicsRHI_DX12
-D3D12TargetedShaderFormats=PCD3D_SM5
+D3D12TargetedShaderFormats=PCD3D_SM6
-D3D11TargetedShaderFormats=PCD3D_SM5
+D3D11TargetedShaderFormats=PCD3D_SM5
Compiler=Default
AudioSampleRate=48000
AudioCallbackBufferFrameSize=1024
AudioNumBuffersToEnqueue=1
AudioMaxChannels=0
AudioNumSourceWorkers=4
SpatializationPlugin=
SourceDataOverridePlugin=
ReverbPlugin=
OcclusionPlugin=
CompressionOverrides=(bOverrideCompressionTimes=False,DurationThreshold=5.000000,MaxNumRandomBranches=0,SoundCueQualityIndex=0)
CacheSizeKB=65536
MaxChunkSizeOverrideKB=0
bResampleForDevice=False
MaxSampleRate=48000.000000
HighSampleRate=32000.000000
MedSampleRate=24000.000000
LowSampleRate=12000.000000
MinSampleRate=8000.000000
CompressionQualityModifier=1.000000
AutoStreamingThreshold=0.000000
SoundCueCookQualityIndex=-1

[/Script/HardwareTargeting.HardwareTargetingSettings]
TargetedHardwareClass=Desktop
AppliedTargetedHardwareClass=Desktop
DefaultGraphicsPerformance=Maximum
AppliedDefaultGraphicsPerformance=Maximum

[/Script/Engine.RendererSettings]
r.GenerateMeshDistanceFields=True
r.DynamicGlobalIlluminationMethod=0
r.ReflectionMethod=2
r.RayTracing=False
r.Shadow.Virtual.Enable=1
r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange=True
r.DefaultFeature.LocalExposure.HighlightContrastScale=0.8
r.DefaultFeature.LocalExposure.ShadowContrastScale=0.8
r.GPUSkin.Support16BitBoneIndex=True
r.GPUSkin.UnlimitedBoneInfluences=True
SkeletalMesh.UseExperimentalChunking=1
r.VirtualTextures=True
r.AllowGlobalClipPlane=False
r.PostProcessing.PropagateAlpha=0
r.SkinCache.CompileShaders=True
r.SkinCache.BlendUsingVertexColorForRecomputeTangents=2
r.SkinCache.SceneMemoryLimitInMB=1500.000000
r.SkinCache.DefaultBehavior=0
r.RayTracing.ForceAllRayTracingEffects=-1
r.RayTracing.AmbientOcclusion=-1
r.RayTracing.Reflections=0
r.RayTracing.Shadows=1
r.RayTracing.GlobalIllumination=0
r.GPUSkin.UnlimitedBoneInfluences=True
r.HairStrands.SkyLighting=1
r.HairStrands.SkyAO=1
r.HairStrands.Visibility.MaterialPass=1
r.HairStrands.Visibility.FullCoverageThreshold=0.9
r.HairStrands.Visibility.MSAA.MeanSamplePerPixel=1.0
r.HairStrands.RasterizationScale=1.0
r.HairStrands.Voxelization.DensityScale=1
r.HairStrands.Voxelization.DepthBiasScale_Shadow=2
r.HairStrands.Voxelization.DepthBiasScale_Light=1
r.HairStrands.Voxelization.DepthBiasScale_Environment=1
r.HairStrands.Voxelization.GPUDriven=1
r.HairStrands.Voxelization.Virtual.VoxelWorldSize=0.15
r.HairStrands.Voxelization.Virtual.VoxelPageCountPerDim=9
r.HairStrands.Voxelization.Raymarching.SteppingScale=1.0
r.HairStrands.Voxelization.Raymarching.SteppingScale.Shadow=1
r.HairStrands.DeepShadow.RandomType=2
r.HairStrands.CardsAtlas.DefaultResolution=4096
r.HairStrands.CardsAtlas.DefaultResolution.LOD0=4096
r.HairStrands.CardsAtlas.DefaultResolution.LOD1=4096
r.HairStrands.CardsAtlas.DefaultResolution.LOD2=4096
r.HairStrands.CardsAtlas.DefaultResolution.LOD3=2048
r.HairStrands.CardsAtlas.DefaultResolution.LOD4=1024
r.HairStrands.CardsAtlas.DefaultResolution.LOD5=512
r.HairStrands.ComposeAfterTranslucency=0
r.HairStrands.AsyncLoad=1
r.HairStrands.BindingAsyncLoad=1
r.HairStrands.SimulationRestUpdate=1
r.HairStrands.MaxSimulatedLOD=0
r.SSGI.Enable=1
r.Bloom.HalfResolutionFFT=1
r.VelocityOutputPass=0
r.Velocity.EnableVertexDeformation=0
r.TemporalAA.Algorithm=1
r.Lumen.HardwareRayTracing=True
r.ReflectionCaptureResolution=512
r.HairStrands.LODMode=False
r.AllowStaticLighting=True

[/Script/WorldPartitionEditor.WorldPartitionEditorSettings]
CommandletClass=Class'/Script/UnrealEd.WorldPartitionConvertCommandlet'

[/Script/Engine.UserInterfaceSettings]
bAuthorizeAutomaticWidgetVariableCreation=False
FontDPIPreset=Standard
FontDPI=72

[/Script/AndroidFileServerEditor.AndroidFileServerRuntimeSettings]
bEnablePlugin=True
bAllowNetworkConnection=True
SecurityToken=656E3AB6430070D5F2A84DA9F8AB861D
bIncludeInShipping=False
bAllowExternalStartInShipping=False
bCompileAFSProject=False
bUseCompression=False
bLogFiles=False
bReportStats=False
ConnectionType=USBOnly
bUseManualIPAddress=False
ManualIPAddress=

[/Script/LinuxTargetPlatform.LinuxTargetSettings]
SpatializationPlugin=
SourceDataOverridePlugin=
ReverbPlugin=
OcclusionPlugin=
SoundCueCookQualityIndex=-1
-TargetedRHIs=SF_VULKAN_SM5
+TargetedRHIs=SF_VULKAN_SM5
+TargetedRHIs=SF_VULKAN_SM6

[/Script/Engine.NetworkSettings]
n.VerifyPeer=False

[/Script/WebSocketNetworking.WebSocketNetDriver]
MaxClientRate=300000
MaxInternetClientRate=200000

[/Script/IOSRuntimeSettings.IOSRuntimeSettings]
MinimumiOSVersion=IOS_16

[/Script/Engine.CollisionProfile]
-Profiles=(Name="NoCollision",CollisionEnabled=NoCollision,ObjectTypeName="WorldStatic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore),(Channel="Camera",Response=ECR_Ignore)),HelpMessage="No collision",bCanModify=False)
-Profiles=(Name="BlockAll",CollisionEnabled=QueryAndPhysics,ObjectTypeName="WorldStatic",CustomResponses=,HelpMessage="WorldStatic object that blocks all actors by default. All new custom channels will use its own default response. ",bCanModify=False)
-Profiles=(Name="OverlapAll",CollisionEnabled=QueryOnly,ObjectTypeName="WorldStatic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Overlap),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldStatic object that overlaps all actors by default. All new custom channels will use its own default response. ",bCanModify=False)
-Profiles=(Name="BlockAllDynamic",CollisionEnabled=QueryAndPhysics,ObjectTypeName="WorldDynamic",CustomResponses=,HelpMessage="WorldDynamic object that blocks all actors by default. All new custom channels will use its own default response. ",bCanModify=False)
-Profiles=(Name="OverlapAllDynamic",CollisionEnabled=QueryOnly,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Overlap),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldDynamic object that overlaps all actors by default. All new custom channels will use its own default response. ",bCanModify=False)
-Profiles=(Name="IgnoreOnlyPawn",CollisionEnabled=QueryOnly,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that ignores Pawn and Vehicle. All other channels will be set to default.",bCanModify=False)
-Profiles=(Name="OverlapOnlyPawn",CollisionEnabled=QueryOnly,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Pawn",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that overlaps Pawn, Camera, and Vehicle. All other channels will be set to default. ",bCanModify=False)
-Profiles=(Name="Pawn",CollisionEnabled=QueryAndPhysics,ObjectTypeName="Pawn",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Pawn object. Can be used for capsule of any playerable character or AI. ",bCanModify=False)
-Profiles=(Name="Spectator",CollisionEnabled=QueryOnly,ObjectTypeName="Pawn",CustomResponses=((Channel="WorldStatic",Response=ECR_Block),(Channel="Pawn",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore),(Channel="WorldDynamic",Response=ECR_Ignore),(Channel="Camera",Response=ECR_Ignore),(Channel="PhysicsBody",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore),(Channel="Destructible",Response=ECR_Ignore)),HelpMessage="Pawn object that ignores all other actors except WorldStatic.",bCanModify=False)
-Profiles=(Name="CharacterMesh",CollisionEnabled=QueryOnly,ObjectTypeName="Pawn",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Pawn object that is used for Character Mesh. All other channels will be set to default.",bCanModify=False)
-Profiles=(Name="PhysicsActor",CollisionEnabled=QueryAndPhysics,ObjectTypeName="PhysicsBody",CustomResponses=,HelpMessage="Simulating actors",bCanModify=False)
-Profiles=(Name="Destructible",CollisionEnabled=QueryAndPhysics,ObjectTypeName="Destructible",CustomResponses=,HelpMessage="Destructible actors",bCanModify=False)
-Profiles=(Name="InvisibleWall",CollisionEnabled=QueryAndPhysics,ObjectTypeName="WorldStatic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="WorldStatic object that is invisible.",bCanModify=False)
-Profiles=(Name="InvisibleWallDynamic",CollisionEnabled=QueryAndPhysics,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that is invisible.",bCanModify=False)
-Profiles=(Name="Trigger",CollisionEnabled=QueryOnly,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Ignore),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldDynamic object that is used for trigger. All other channels will be set to default.",bCanModify=False)
-Profiles=(Name="Ragdoll",CollisionEnabled=QueryAndPhysics,ObjectTypeName="PhysicsBody",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Simulating Skeletal Mesh Component. All other channels will be set to default.",bCanModify=False)
-Profiles=(Name="Vehicle",CollisionEnabled=QueryAndPhysics,ObjectTypeName="Vehicle",CustomResponses=,HelpMessage="Vehicle object that blocks Vehicle, WorldStatic, and WorldDynamic. All other channels will be set to default.",bCanModify=False)
-Profiles=(Name="UI",CollisionEnabled=QueryOnly,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Block),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldStatic object that overlaps all actors by default. All new custom channels will use its own default response. ",bCanModify=False)
+Profiles=(Name="NoCollision",CollisionEnabled=NoCollision,bCanModify=False,ObjectTypeName="WorldStatic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore),(Channel="Camera",Response=ECR_Ignore)),HelpMessage="No collision")
+Profiles=(Name="BlockAll",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="WorldStatic",CustomResponses=,HelpMessage="WorldStatic object that blocks all actors by default. All new custom channels will use its own default response. ")
+Profiles=(Name="OverlapAll",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="WorldStatic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Overlap),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldStatic object that overlaps all actors by default. All new custom channels will use its own default response. ")
+Profiles=(Name="BlockAllDynamic",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=,HelpMessage="WorldDynamic object that blocks all actors by default. All new custom channels will use its own default response. ")
+Profiles=(Name="OverlapAllDynamic",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Overlap),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldDynamic object that overlaps all actors by default. All new custom channels will use its own default response. ")
+Profiles=(Name="IgnoreOnlyPawn",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that ignores Pawn and Vehicle. All other channels will be set to default.")
+Profiles=(Name="OverlapOnlyPawn",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Pawn",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that overlaps Pawn, Camera, and Vehicle. All other channels will be set to default. ")
+Profiles=(Name="Pawn",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="Pawn",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Pawn object. Can be used for capsule of any playerable character or AI. ")
+Profiles=(Name="Spectator",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="Pawn",CustomResponses=((Channel="WorldStatic"),(Channel="Pawn",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore),(Channel="WorldDynamic",Response=ECR_Ignore),(Channel="Camera",Response=ECR_Ignore),(Channel="PhysicsBody",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore),(Channel="Destructible",Response=ECR_Ignore)),HelpMessage="Pawn object that ignores all other actors except WorldStatic.")
+Profiles=(Name="CharacterMesh",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="Pawn",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Pawn object that is used for Character Mesh. All other channels will be set to default.")
+Profiles=(Name="PhysicsActor",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="PhysicsBody",CustomResponses=,HelpMessage="Simulating actors")
+Profiles=(Name="Destructible",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="Destructible",CustomResponses=,HelpMessage="Destructible actors")
+Profiles=(Name="InvisibleWall",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="WorldStatic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="WorldStatic object that is invisible.")
+Profiles=(Name="InvisibleWallDynamic",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="Visibility",Response=ECR_Ignore)),HelpMessage="WorldDynamic object that is invisible.")
+Profiles=(Name="Trigger",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="WorldDynamic",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility",Response=ECR_Ignore),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="WorldDynamic object that is used for trigger. All other channels will be set to default.")
+Profiles=(Name="Ragdoll",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="PhysicsBody",CustomResponses=((Channel="Pawn",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore)),HelpMessage="Simulating Skeletal Mesh Component. All other channels will be set to default.")
+Profiles=(Name="Vehicle",CollisionEnabled=QueryAndPhysics,bCanModify=False,ObjectTypeName="Vehicle",CustomResponses=,HelpMessage="Vehicle object that blocks Vehicle, WorldStatic, and WorldDynamic. All other channels will be set to default.")
+Profiles=(Name="UI",CollisionEnabled=QueryOnly,bCanModify=False,ObjectTypeName="UI",CustomResponses=((Channel="WorldStatic",Response=ECR_Overlap),(Channel="Pawn",Response=ECR_Overlap),(Channel="Visibility"),(Channel="WorldDynamic",Response=ECR_Overlap),(Channel="Camera",Response=ECR_Overlap),(Channel="PhysicsBody",Response=ECR_Overlap),(Channel="Vehicle",Response=ECR_Overlap),(Channel="Destructible",Response=ECR_Overlap)),HelpMessage="UI")
+Profiles=(Name="NPC",CollisionEnabled=QueryAndPhysics,bCanModify=True,ObjectTypeName="NPC",CustomResponses=((Channel="UI",Response=ECR_Ignore)),HelpMessage="NPC")
+DefaultChannelResponses=(Channel=ECC_GameTraceChannel1,DefaultResponse=ECR_Block,bTraceType=False,bStaticObject=False,Name="UI")
+DefaultChannelResponses=(Channel=ECC_GameTraceChannel2,DefaultResponse=ECR_Block,bTraceType=False,bStaticObject=False,Name="NPC")
+EditProfiles=(Name="UI",CustomResponses=((Channel="WorldStatic",Response=ECR_Ignore),(Channel="WorldDynamic",Response=ECR_Ignore),(Channel="Pawn",Response=ECR_Ignore),(Channel="Visibility",Response=ECR_Ignore),(Channel="Camera",Response=ECR_Ignore),(Channel="PhysicsBody",Response=ECR_Ignore),(Channel="Vehicle",Response=ECR_Ignore),(Channel="Destructible",Response=ECR_Ignore),(Channel="EngineTraceChannel2",Response=ECR_Ignore),(Channel="EngineTraceChannel3",Response=ECR_Ignore),(Channel="EngineTraceChannel4",Response=ECR_Ignore),(Channel="EngineTraceChannel5",Response=ECR_Ignore),(Channel="EngineTraceChannel6",Response=ECR_Ignore),(Channel="NPC",Response=ECR_Ignore),(Channel="GameTraceChannel3",Response=ECR_Ignore),(Channel="GameTraceChannel4",Response=ECR_Ignore),(Channel="GameTraceChannel5",Response=ECR_Ignore),(Channel="GameTraceChannel6",Response=ECR_Ignore),(Channel="GameTraceChannel7",Response=ECR_Ignore),(Channel="GameTraceChannel8",Response=ECR_Ignore),(Channel="GameTraceChannel9",Response=ECR_Ignore),(Channel="GameTraceChannel10",Response=ECR_Ignore),(Channel="GameTraceChannel11",Response=ECR_Ignore),(Channel="GameTraceChannel12",Response=ECR_Ignore),(Channel="GameTraceChannel13",Response=ECR_Ignore),(Channel="GameTraceChannel14",Response=ECR_Ignore),(Channel="GameTraceChannel15",Response=ECR_Ignore),(Channel="GameTraceChannel16",Response=ECR_Ignore),(Channel="GameTraceChannel17",Response=ECR_Ignore),(Channel="GameTraceChannel18",Response=ECR_Ignore)))
-ProfileRedirects=(OldName="BlockingVolume",NewName="InvisibleWall")
-ProfileRedirects=(OldName="InterpActor",NewName="IgnoreOnlyPawn")
-ProfileRedirects=(OldName="StaticMeshComponent",NewName="BlockAllDynamic")
-ProfileRedirects=(OldName="SkeletalMeshActor",NewName="PhysicsActor")
-ProfileRedirects=(OldName="InvisibleActor",NewName="InvisibleWallDynamic")
+ProfileRedirects=(OldName="BlockingVolume",NewName="InvisibleWall")
+ProfileRedirects=(OldName="InterpActor",NewName="IgnoreOnlyPawn")
+ProfileRedirects=(OldName="StaticMeshComponent",NewName="BlockAllDynamic")
+ProfileRedirects=(OldName="SkeletalMeshActor",NewName="PhysicsActor")
+ProfileRedirects=(OldName="InvisibleActor",NewName="InvisibleWallDynamic")
-CollisionChannelRedirects=(OldName="Static",NewName="WorldStatic")
-CollisionChannelRedirects=(OldName="Dynamic",NewName="WorldDynamic")
-CollisionChannelRedirects=(OldName="VehicleMovement",NewName="Vehicle")
-CollisionChannelRedirects=(OldName="PawnMovement",NewName="Pawn")
+CollisionChannelRedirects=(OldName="Static",NewName="WorldStatic")
+CollisionChannelRedirects=(OldName="Dynamic",NewName="WorldDynamic")
+CollisionChannelRedirects=(OldName="VehicleMovement",NewName="Vehicle")
+CollisionChannelRedirects=(OldName="PawnMovement",NewName="Pawn")

[/Script/Convai.ConvaiSettings]
API_Key={convai_api_key}
"""
        
        UnrealEngineManager._merge_ini_file(
            default_engine_ini_path,
            lines_to_add,
            "Failed to read existing DefaultEngine.ini, will recreate"
        )
        logger.debug("Merged DefaultEngine.ini with required settings and API key")
    
    @staticmethod
    def _update_input_ini(project_dir):
        config_dir = os.path.join(project_dir, config.get_config_dir_name())
        os.makedirs(config_dir, exist_ok=True)
        default_input_ini_path = os.path.join(config_dir, config.get_config_file_name("default_input"))

        # Desired settings content
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
        
        UnrealEngineManager._merge_ini_file(
            default_input_ini_path,
            content_to_write,
            "Failed to read existing DefaultInput.ini, will recreate"
        )
        logger.debug("Merged DefaultInput.ini")
