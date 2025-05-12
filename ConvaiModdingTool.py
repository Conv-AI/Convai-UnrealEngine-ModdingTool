import os
from pathlib import Path
import sys

from core.download_utils import DownloadManager
from core.file_utility_manager import FileUtilityManager
from core.input_manager import InputManager
from core.unreal_engine_manager import UnrealEngineManager

def CreateModdingProject(script_dir):
    """Main execution flow for setting up an Unreal Engine project."""  
        
    unreal_engine_path = InputManager.get_unreal_engine_path(["E:/Software/UE_5.3", "D:/Software/UnrealEngine/UE_5.3/UE_5.3", "C:/Program Files/Epic Games/UE_5.3"])  
    engine_version = UnrealEngineManager.extract_engine_version(unreal_engine_path)        
    if not engine_version or not UnrealEngineManager.is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)
    
    project_name = InputManager.get_project_name(script_dir)
    convai_api_key = InputManager.get_api_key()
    asset_type, is_metahuman = InputManager.get_asset_type()
    project_dir = os.path.join(script_dir, project_name)
    
    # Build project structure and exit if validations fail
    if not UnrealEngineManager.build_project_structure(project_name, project_dir, unreal_engine_path, engine_version):
        print("Exiting execution due to invalid project name or existing project directory.")
        exit(1)
    
    plugin_name = FileUtilityManager.trim_unique_str(FileUtilityManager.generate_unique_str())
    UnrealEngineManager.create_content_only_plugin(project_dir, plugin_name)
    
    UnrealEngineManager.update_ini_files(project_dir, plugin_name, convai_api_key)
    
    DownloadManager.download_modding_dependencies(project_dir)
    
    UnrealEngineManager.enable_plugins(project_dir, project_name, ["ConvAI", "ConvaiHTTP", "ConvaiPakManager", "JsonBlueprintUtilities", plugin_name])
    
    FileUtilityManager.save_metadata(project_dir, {"project_name": project_name,"plugin_name": plugin_name,"asset_type": asset_type, "is_metahuman": is_metahuman})
    
    UnrealEngineManager.configure_assets_in_project(project_dir, asset_type, is_metahuman)
    
    UnrealEngineManager.run_unreal_build(unreal_engine_path, project_name, project_dir)

def UpdateModdingProject(script_dir):
    """Main execution flow for updating an existing Unreal Engine modding project."""
    
    project_dir = InputManager.choose_project_dir(script_dir)
    
    unreal_engine_path = InputManager.get_unreal_engine_path(["E:/Software/UE_5.3", "D:/Software/UnrealEngine/UE_5.3/UE_5.3", "C:/Program Files/Epic Games/UE_5.3"])  
    engine_version = UnrealEngineManager.extract_engine_version(unreal_engine_path)        
    if not engine_version or not UnrealEngineManager.is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)

    metadata = FileUtilityManager.get_metadata(project_dir)        
    asset_type = metadata.get("asset_type")
    is_metahuman = metadata.get("is_metahuman")
    project_name = metadata.get("project_name")
    
    UnrealEngineManager.update_modding_dependencies(project_dir)
    UnrealEngineManager.configure_assets_in_project(project_dir, asset_type, is_metahuman)
    
    UnrealEngineManager.run_unreal_build(unreal_engine_path, project_name, project_dir)

def main():
    print("Welcome to the Convai Modding Tool!")
    
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = Path(__file__).resolve().parent.parent
    
    user_choice = InputManager.get_user_flow_choice(script_dir)
    
    if user_choice == "create":
        CreateModdingProject(script_dir)
    elif user_choice == "update":
        UpdateModdingProject(script_dir)
    
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
