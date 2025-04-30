
import os
from pathlib import Path
import sys

from core.asset_manager import configure_assets_in_project, get_api_key, get_asset_type_from_user, get_metadata, get_user_flow_choice, save_metadata, trim_unique_str, get_unique_str
from core.download_utils import download_modding_dependencies
from core.unreal_project import build_project_structure, choose_project_dir, create_content_only_plugin, enable_plugins_in_uproject, extract_engine_version, get_project_name, get_unreal_engine_path, is_supported_engine_version, run_unreal_build, update_ini_files, update_modding_dependencies

def CreateModdingProject():
    """Main execution flow for setting up an Unreal Engine project."""  
    
    if getattr(sys, 'frozen', False):  # Check if running as an exe
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent
    
    unreal_engine_path = get_unreal_engine_path(["E:/Software/UE_5.3", "D:/Software/UnrealEngine/UE_5.3/UE_5.3", "C:/Program Files/Epic Games/UE_5.3"])  
    engine_version = extract_engine_version(unreal_engine_path)        
    if not engine_version or not is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)
    
    project_name = get_project_name(script_dir)
    convai_api_key = get_api_key()
    asset_type, is_metahuman = get_asset_type_from_user()
    project_dir = os.path.join(script_dir, project_name)
    
    # Build project structure and exit if validations fail
    if not build_project_structure(project_name, project_dir, unreal_engine_path, engine_version):
        print("Exiting execution due to invalid project name or existing project directory.")
        exit(1)
    
    plugin_name = trim_unique_str(get_unique_str())
    create_content_only_plugin(project_dir, plugin_name)
    
    update_ini_files(project_dir, plugin_name, convai_api_key)
    
    download_modding_dependencies(project_dir)
    
    enable_plugins_in_uproject(project_dir, project_name, ["ConvAI", "ConvaiHTTP", "ConvaiPakManager", "JsonBlueprintUtilities", plugin_name])
    
    save_metadata(project_dir, {"project_name": project_name,"plugin_name": plugin_name,"asset_type": asset_type, "is_metahuman": is_metahuman})
    
    configure_assets_in_project(project_dir, asset_type, is_metahuman)
    
    run_unreal_build(unreal_engine_path, project_name, project_dir)

def UpdateModdingProject():
    """Main execution flow for updating an existing Unreal Engine modding project."""
    
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = Path(__file__).resolve().parent.parent

    project_dir = choose_project_dir(script_dir)
        
    unreal_engine_path = get_unreal_engine_path(["E:/Software/UE_5.3", "D:/Software/UnrealEngine/UE_5.3/UE_5.3", "C:/Program Files/Epic Games/UE_5.3"])  
    engine_version = extract_engine_version(unreal_engine_path)        
    if not engine_version or not is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)

    metadata = get_metadata(project_dir)        
    asset_type = metadata.get("asset_type")
    is_metahuman = metadata.get("is_metahuman")
    project_name = metadata.get("project_name")
    
    update_modding_dependencies(project_dir)
    configure_assets_in_project(project_dir, asset_type, is_metahuman)
    
    run_unreal_build(unreal_engine_path, project_name, project_dir)
    
def main():
    print("Welcome to the Convai Modding Tool!")
    user_choice = get_user_flow_choice()
    
    if user_choice == "create":
        CreateModdingProject()
    elif user_choice == "update":
        UpdateModdingProject()
    
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
