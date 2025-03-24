import os
from pathlib import Path
import sys

from core.asset_manager import get_asset_type_from_user, save_metadata, trim_unique_str, get_unique_str
from core.download_utils import download_modding_dependencies
from core.file_utils import remove_metahuman_if_scene
from core.unreal_project import build_project_structure, create_content_only_plugin, enable_plugins_in_uproject, extract_engine_version, get_project_name, get_unreal_engine_path, is_supported_engine_version, run_unreal_build, update_default_game_ini, verify_convai_plugin

def main():
    """Main execution flow for setting up an Unreal Engine project."""  
    
    if getattr(sys, 'frozen', False):  # Check if running as an exe
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        
    unreal_engine_path = get_unreal_engine_path()        
    engine_version = extract_engine_version(unreal_engine_path)        
    if not engine_version or not is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)
    
    project_name = get_project_name()
    asset_type = get_asset_type_from_user()
    project_dir = os.path.join(Path(script_dir).parent, project_name)
            
    # Build project structure and exit if validations fail
    if not build_project_structure(project_name, project_dir, unreal_engine_path, engine_version):
        print("Exiting execution due to invalid project name or existing project directory.")
        exit(1)
    
    plugin_name = trim_unique_str(get_unique_str())
    create_content_only_plugin(project_dir, plugin_name)
    
    update_default_game_ini(project_dir, plugin_name)
    
    download_modding_dependencies(project_dir)
    enable_plugins_in_uproject(project_dir, project_name, ["ConvAI", "ConvaiHTTP", "ConvaiPakManager", "JsonBlueprintUtilities", plugin_name])
    
    save_metadata(project_dir, "project_name", project_name)
    save_metadata(project_dir, "plugin_name", plugin_name)
    save_metadata(project_dir, "asset_type", asset_type)
    
    remove_metahuman_if_scene(project_dir, asset_type)
    
    run_unreal_build(unreal_engine_path, project_name, project_dir)
    input("Press Enter to exit...")

if __name__ == "__main__":
    main()
