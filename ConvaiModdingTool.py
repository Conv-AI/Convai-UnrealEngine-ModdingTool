import ctypes
import os
from pathlib import Path
import sys
from typing import Optional

from core.compatibility_patcher import patch_source_files
from core.config_manager import config
from core.download_utils import DownloadManager
from core.exceptions import ProjectError
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.logger import logger, suppress_external_logging
from core.unreal_engine_manager import UnrealEngineManager

TOOL_VERSION = "3.0.6"

def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return Path(__file__).resolve().parent.parent

#Managers
input_manager = InputManager(get_script_dir())

def _report_migration(report: dict) -> Optional[str]:
    """
    Show what the update changed, and hand the text to the GUI. The text is built and
    written by update_modding_dependencies, before the step that destroys the evidence.
    """
    notes = report.get("notes")
    if not notes:
        return None

    logger.section("What changed")
    logger.info(notes)
    return notes

def CreateModdingProject():
    """Main execution flow for setting up an Unreal Engine project."""  
    logger.section("Creating New Modding Project")

    FileUtilityManager.validate_ubt_configuration()

    ue_dir = input_manager.get_unreal_engine_path("current")
    project_name = input_manager.get_project_name()
    project_dir = os.path.join(input_manager.get_script_dir(), project_name)
    
    convai_api_key = input_manager.get_api_key()
    asset_type, is_metahuman = input_manager.get_asset_type()
    
    ue_manager = UnrealEngineManager(ue_dir, project_name, project_dir)    
    if not ue_manager.can_create_modding_project():
        raise ProjectError(f"Unreal Engine {ue_manager.engine_version} does not meet the modding project requirements")
    
    logger.step("Setting up project structure...")
    if not ue_manager.build_project_structure():
        raise ProjectError("Failed to build project structure")
    
    logger.step("Creating Modding Plugin...")
    plugin_name = FileUtilityManager.trim_unique_str(FileUtilityManager.generate_unique_str())
    ue_manager.create_content_only_plugin(plugin_name)
    ue_manager.update_ini_files(plugin_name, convai_api_key)
    
    logger.step("Downloading Convai dependencies...")
    DownloadManager.download_modding_dependencies(project_dir, ue_manager.engine_version)
    
    logger.step("Enabling required plugins...")
    required_plugins = (config.get_required_plugins() + [plugin_name] + (config.get_metahuman_plugins() if is_metahuman else []))
    ue_manager.enable_plugins(required_plugins)
    
    logger.step("Saving project metadata...")
    FileUtilityManager.save_metadata(project_dir, {
        "project_name": project_name,
        "plugin_name": plugin_name,
        "asset_type": asset_type, 
        "is_metahuman": is_metahuman,
        "api_key": convai_api_key
    })
    
    logger.step("Configuring project assets...")
    ue_manager.configure_assets_in_project(asset_type, is_metahuman)

    logger.step("Patching plugin source for engine compatibility...")
    patch_source_files(project_dir, ue_manager.engine_version)

    logger.step("Building project...")
    ue_manager.run_unreal_build()

    logger.success("Modding project created successfully!")

def UpdateModdingProject() -> Optional[str]:
    """Main execution flow for updating an existing Unreal Engine modding project."""
    logger.section("Updating Existing Modding Project")
    
    FileUtilityManager.validate_ubt_configuration()
    
    ue_dir = input_manager.get_unreal_engine_path("current")
    project_dir = input_manager.choose_project_dir()

    logger.step("Loading project configuration...")
    metadata = FileUtilityManager.get_metadata(project_dir)        
    asset_type = metadata.get("asset_type")
    is_metahuman = metadata.get("is_metahuman")
    project_name = metadata.get("project_name")
    api_key = metadata.get("api_key")
    plugin_name = metadata.get("plugin_name")

    ue_manager = UnrealEngineManager(ue_dir, project_name, project_dir)
    
    if not ue_manager.can_create_modding_project():
        raise ProjectError(f"Unreal Engine {ue_manager.engine_version} does not meet the modding project requirements")

    report = ue_manager.update_existing_project(asset_type, is_metahuman, plugin_name, api_key)
    notes = _report_migration(report)

    logger.step("Patching plugin source for engine compatibility...")
    patch_source_files(project_dir, ue_manager.engine_version)

    logger.step("Building project...")
    ue_manager.run_unreal_build()

    logger.success("Modding project updated successfully!")
    return notes

def MigrateModdingProject() -> Optional[str]:
    """Main execution flow for migrating an existing Unreal Engine modding project to a new UE version."""
    logger.section("Migrate Existing Modding Project")
    
    FileUtilityManager.validate_ubt_configuration()
    
    # Step 1: Select and update original project
    original_project_dir = input_manager.choose_project_dir()
    current_ue_dir = input_manager.get_unreal_engine_path("current")
    
    # Load project metadata
    metadata = FileUtilityManager.get_metadata(original_project_dir)        
    asset_type = metadata.get("asset_type")
    is_metahuman = metadata.get("is_metahuman")
    original_project_name = metadata.get("project_name")
    api_key = metadata.get("api_key")
    plugin_name = metadata.get("plugin_name")

    # Every later step is named after the project. A legacy project has no metadata to
    # name it with, and the caller reads a plain return as success.
    if not original_project_name:
        raise ProjectError("Project name not found in metadata. This project may not have been created with the modding tool")
    
    # Step 2: Validate migration requirements
    is_migration_needed, current_ue_version, target_ue_version = FileUtilityManager.validate_migration_requirements(original_project_name, original_project_dir)
    # The only remaining "not needed" is a project already on the target engine, which
    # is a finished run, not a failure - hence a return where the rest of this flow raises.
    if not is_migration_needed:
        return None
    
    # Step 3: Update original project
    logger.step("Updating selected project...")
    ue_manager = UnrealEngineManager(current_ue_dir, original_project_name, original_project_dir)

    # The update deletes Plugins/ConvAI before downloading the replacement, and here that
    # is the user's only copy. Migrate needs only the availability half of Update's
    # can_create_modding_project - it builds the copy with the target toolchain instead -
    # and a None engine version reads as "any engine" to that check, so it is guarded first.
    if not ue_manager.engine_version:
        raise ProjectError(f"Could not read the Unreal Engine version at {current_ue_dir}")
    if not DownloadManager.check_convai_plugin_available(ue_manager.engine_version):
        raise ProjectError(f"No Convai plugin release for Unreal Engine {ue_manager.engine_version}")

    # The update writes the notes into the original project, so the copy taken in
    # step 5 carries them too
    report = ue_manager.update_existing_project(asset_type, is_metahuman, plugin_name, api_key)
    notes = _report_migration(report)

    # Step 4: Get target UE path with inline validation
    logger.step(f"Please select the target Unreal Engine {target_ue_version} installation path...")
    target_ue_dir = input_manager.get_unreal_engine_path("target")
    
    # Verify target UE version matches (inline validation)
    target_ue_manager = UnrealEngineManager(target_ue_dir)
    actual_target_version = target_ue_manager.engine_version
    if actual_target_version != target_ue_version:
        logger.warning(f"Target UE path version ({actual_target_version}) doesn't match expected version ({target_ue_version})")
        logger.warning("Continuing with the selected path...")
    
    # Step 5: Create migrated project copy
    success, migrated_directory_name, migrated_project_dir = FileUtilityManager.create_migrated_project_copy(
        original_project_dir, original_project_name, target_ue_version, input_manager.get_script_dir()
    )
    if not success:
        raise ProjectError(f"Failed to copy the project to {original_project_name}_{target_ue_version}")
    
    # Step 6: Update engine version in migrated project
    logger.step(f"Updating engine version to {target_ue_version}...")
    uproject_file = os.path.join(migrated_project_dir, f"{original_project_name}.uproject")
    if not UnrealEngineManager.set_engine_version(uproject_file, target_ue_version):
        raise ProjectError(f"Failed to set the engine version in {original_project_name}.uproject")
    logger.success(f"Updated project to Unreal Engine {target_ue_version}")

    # Step 6.5: Patch Target.cs files for newer UE build compatibility
    logger.step("Patching Target.cs files for target UE build compatibility...")
    FileUtilityManager.patch_target_files(uproject_file)

    # Step 6.6: Patch embedded ConvAI plugin source for target-engine API breaks
    logger.step(f"Patching plugin source for Unreal Engine {target_ue_version} compatibility...")
    patch_source_files(migrated_project_dir, target_ue_version)

    # Step 7: Build migrated project (toolchain setup handled in can_create_migrated_project)
    migration_ue_manager = UnrealEngineManager(target_ue_dir, original_project_name, migrated_project_dir)
    
    # Validate prerequisites for migrated project
    if migration_ue_manager.can_create_migrated_project():
        logger.step(f"Building migrated project with Unreal Engine {target_ue_version}...")
        try:
            migration_ue_manager.run_unreal_build()
            logger.success("Migrated project built successfully!")
        except Exception as e:
            logger.warning(f"Build failed: {e}")
            logger.warning("Project migration completed but build failed")
    else:
        logger.warning("Target UE version validation failed, but project migration completed")
    
    logger.success(f"Successfully migrated project to {migrated_directory_name} with Unreal Engine {target_ue_version}!")
    logger.info(f"Migrated project location: {migrated_project_dir}")
    return notes


def _hide_own_console():
    """Hide the console window the exe opened for itself.

    The build stays console=True because the logger and the UBT child both write to
    stdout. The console is ours alone - i.e. the exe was double-clicked - when every
    process attached to it is this process or, in the onefile build, the bootloader
    parent that spawned it and waits on the same console. A developer's terminal shows
    up as a foreign pid and keeps its window.

    The ppid half assumes ConvaiAssetUploader.spec stays onefile. A onedir build has
    no bootloader parent, so a shell that launched it is the ppid and its window
    would be hidden; drop the getppid line if the spec ever changes.
    """
    if "--console" in sys.argv:
        return

    kernel32 = ctypes.windll.kernel32
    console_window = kernel32.GetConsoleWindow()
    if not console_window:
        return

    processes = (ctypes.c_uint32 * 16)()
    count = kernel32.GetConsoleProcessList(processes, len(processes))
    if not 0 < count <= len(processes):
        return

    owners = {os.getpid()}
    if getattr(sys, "frozen", False):
        owners.add(os.getppid())
    if set(processes[:count]) <= owners:
        ctypes.windll.user32.ShowWindow(console_window, 0)


def main():
    _hide_own_console()
    suppress_external_logging()

    from gui.host import run_gui
    run_gui(TOOL_VERSION, input_manager, {
        "create": CreateModdingProject,
        "update": UpdateModdingProject,
        "migrate": MigrateModdingProject,
    })

if __name__ == "__main__":
    main()
