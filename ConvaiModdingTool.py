import os
from pathlib import Path
import sys

from core.asset_manager import save_metadata, trim_unique_str, get_unique_str
from core.download_utils import download_from_gdrive, download_modding_dependencies, download_plugins_from_gdrive_folder, unzip_file
from core.unreal_project import build_project_structure, create_content_only_plugin, enable_plugin_in_uproject, extract_engine_version, get_unreal_engine_path, is_supported_engine_version, run_unreal_build


def main():
    """Main execution flow for setting up an Unreal Engine project."""
    
    if getattr(sys, 'frozen', False):  # Check if running as an exe
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    project_name = trim_unique_str(get_unique_str())
    plugin_name = trim_unique_str(get_unique_str())
    unreal_engine_path = get_unreal_engine_path()

    engine_version = extract_engine_version(unreal_engine_path)        
    if not engine_version or not is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)
    
    project_dir = os.path.join(Path(script_dir).parent, project_name)
    
    build_project_structure(project_name, project_dir, unreal_engine_path, engine_version)
    create_content_only_plugin(project_dir, plugin_name)
    download_modding_dependencies(project_dir)
    
    PluginName = ["ConvAI", "ConvaiHTTP", "ConvaiPakManager", "JsonBlueprintUtilities", plugin_name]
    for It in PluginName:
        enable_plugin_in_uproject(os.path.join(project_dir, f"{project_name}.uproject"), It)
    
    run_unreal_build(unreal_engine_path, project_name, project_dir)
    
    save_metadata(project_dir, "project_name", project_name)
    save_metadata(project_dir, "plugin_name", plugin_name)
    
    input("Press Enter to exit...")  

if __name__ == "__main__":
    main()
