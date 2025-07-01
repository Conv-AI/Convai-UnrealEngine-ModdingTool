import os
from pathlib import Path
import sys

from core.config_manager import config
from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.unreal_engine_manager import UnrealEngineManager

def get_script_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    else:
        return Path(__file__).resolve().parent.parent

#Managers
input_manager = InputManager(get_script_dir(), config.get_default_engine_paths())

def CreateModdingProject():
    """Main execution flow for setting up an Unreal Engine project."""  

    ue_dir = input_manager.get_unreal_engine_path()
    project_name = input_manager.get_project_name()
    project_dir = os.path.join(input_manager.get_script_dir(), project_name)
    
    ue_manager = UnrealEngineManager(ue_dir, project_name, project_dir)    
    if not ue_manager.can_create_modding_project():
        return
    
    convai_api_key = input_manager.get_api_key()
    asset_type, is_metahuman = input_manager.get_asset_type()
    
    if not ue_manager.build_project_structure():
        print("Build project structure failed")
        return
    
    plugin_name = FileUtilityManager.trim_unique_str(FileUtilityManager.generate_unique_str())
    ue_manager.create_content_only_plugin(plugin_name)
    ue_manager.update_ini_files(plugin_name, convai_api_key)
    
    DownloadManager.download_modding_dependencies(project_dir)
    
    required_plugins = config.get_required_plugins() + [plugin_name]
    ue_manager.enable_plugins(required_plugins)
    
    FileUtilityManager.save_metadata(project_dir, {
        "project_name": project_name,
        "plugin_name": plugin_name,
        "asset_type": asset_type, 
        "is_metahuman": is_metahuman,
        "api_key": convai_api_key
    })
    
    ue_manager.configure_assets_in_project(asset_type, is_metahuman)
    ue_manager.run_unreal_build()

def UpdateModdingProject():
    """Main execution flow for updating an existing Unreal Engine modding project."""
    
    ue_dir = input_manager.get_unreal_engine_path()
    project_dir = input_manager.choose_project_dir()

    metadata = FileUtilityManager.get_metadata(project_dir)        
    asset_type = metadata.get("asset_type")
    is_metahuman = metadata.get("is_metahuman")
    project_name = metadata.get("project_name")
    
    ue_manager = UnrealEngineManager(ue_dir, project_name, project_dir)
    
    if not ue_manager.can_create_modding_project():
        return
    
    ue_manager.update_modding_dependencies()
    ue_manager.configure_assets_in_project(asset_type, is_metahuman)
    ue_manager.run_unreal_build()

def main():
    print("Welcome to the Convai Modding Tool!")
    
    user_choice = input_manager.get_user_flow_choice()
    
    if user_choice == "create":
        CreateModdingProject()
    elif user_choice == "update":
        UpdateModdingProject()
    
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
