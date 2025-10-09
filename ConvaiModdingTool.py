import os
from pathlib import Path
import sys
import json

from core.config_manager import config
from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.unreal_engine_manager import UnrealEngineManager
from core.logger import logger, suppress_external_logging
from core.version_manager import VersionManager

TOOL_VERSION = "3.0.0"

def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return Path(__file__).resolve().parent.parent

#Managers
input_manager = InputManager(get_script_dir())

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
        return  
    
    logger.step("Setting up project structure...")
    if not ue_manager.build_project_structure():
        logger.error("Failed to build project structure")
        return
    
    logger.step("Creating content plugin...")
    plugin_name = FileUtilityManager.trim_unique_str(FileUtilityManager.generate_unique_str())
    ue_manager.create_content_only_plugin(plugin_name)
    ue_manager.update_ini_files(plugin_name, convai_api_key)
    
    logger.step("Downloading Convai dependencies...")
    DownloadManager.download_modding_dependencies(project_dir)
    
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
    
    logger.step("Building project...")
    ue_manager.run_unreal_build()
    
    logger.success("Modding project created successfully!")

def UpdateModdingProject():
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
        return
    
    if not ue_manager.update_existing_project(asset_type, is_metahuman, plugin_name, api_key):
        logger.error("Failed to update project")
        return
    
    logger.step("Building project...")
    ue_manager.run_unreal_build()
    
    logger.success("Modding project updated successfully!")

def MigrateModdingProject():
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
    
    # Step 2: Validate migration requirements
    is_migration_needed, current_ue_version, target_ue_version = FileUtilityManager.validate_migration_requirements(original_project_name)
    if not is_migration_needed:
        return
    
    # Step 3: Update original project
    logger.step("Updating selected project...")
    ue_manager = UnrealEngineManager(current_ue_dir, original_project_name, original_project_dir)
        
    if not ue_manager.update_existing_project(asset_type, is_metahuman, plugin_name, api_key):
        logger.error("Failed to update original project")
        return
    
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
        return
    
    # Step 6: Update engine version in migrated project
    logger.step(f"Updating engine version to {target_ue_version}...")
    uproject_file = os.path.join(migrated_project_dir, f"{original_project_name}.uproject")
    if not UnrealEngineManager.set_engine_version(uproject_file, target_ue_version):
        return
    logger.success(f"Updated project to Unreal Engine {target_ue_version}")
    
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
    
def main():
    
    if not VersionManager.check_version(TOOL_VERSION):
        return
    
    suppress_external_logging()
    
    logger.section("Convai Modding Tool")
    logger.info("Welcome to the Convai Modding Tool!")
    
    user_choice = input_manager.get_user_flow_choice()
    
    if user_choice == "create":
        CreateModdingProject()
    elif user_choice == "update":
        UpdateModdingProject()
    elif user_choice == "migrate":
        MigrateModdingProject()

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
