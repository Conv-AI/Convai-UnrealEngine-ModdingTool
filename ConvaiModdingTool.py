import os
from pathlib import Path
import sys

from core.config_manager import config
from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.unreal_engine_manager import UnrealEngineManager
from core.logger import logger, suppress_external_logging
from core.version_manager import VersionManager

TOOL_VERSION = "2.5.0"

def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return Path(__file__).resolve().parent.parent

#Managers
input_manager = InputManager(get_script_dir(), config.get_default_engine_paths())

def CreateModdingProject():
    """Main execution flow for setting up an Unreal Engine project."""  
    logger.section("Creating New Modding Project")

    FileUtilityManager.validate_ubt_configuration()

    ue_dir = input_manager.get_unreal_engine_path()
    project_name = input_manager.get_project_name()
    project_dir = os.path.join(input_manager.get_script_dir(), project_name)
    
    ue_manager = UnrealEngineManager(ue_dir, project_name, project_dir)    
    if not ue_manager.can_create_modding_project():
        return
    
    convai_api_key = input_manager.get_api_key()
    asset_type, is_metahuman = input_manager.get_asset_type()
    
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
    
    ue_dir = input_manager.get_unreal_engine_path()
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
    
    logger.step("Checking project engine version...")
    if not ue_manager.update_project_engine_version():
        logger.warning("Failed to update project engine version, but continuing...")
    
    logger.step("Updating Convai dependencies...")
    ue_manager.update_modding_dependencies()
    
    logger.step("Configuring project assets...")
    ue_manager.configure_assets_in_project(asset_type, is_metahuman)
    
    ue_manager.update_ini_files(plugin_name, api_key)
    
    logger.step("Building project...")
    ue_manager.run_unreal_build()
    
    logger.success("Modding project updated successfully!")

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

if __name__ == "__main__":
    main()
    input("\nPress Enter to exit...")
