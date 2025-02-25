import os
from pathlib import Path
import sys

from core.asset_manager import generate_project_name, get_asset_id, save_asset_metadata
from core.download_utils import download_and_extract_plugin
from core.unreal_project import build_project_structure, enable_convai_plugin_in_uproject, enable_plugin_in_uproject, extract_engine_version, get_unreal_engine_path, is_plugin_installed, is_supported_engine_version, run_unreal_build


def main():
    """Main execution flow for setting up an Unreal Engine project."""
    
    if getattr(sys, 'frozen', False):  # Check if running as an exe
        script_dir = os.path.dirname(os.path.abspath(sys.executable))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    asset_id = get_asset_id()
    if not asset_id:
        print("Failed to fetch asset ID. Exiting.")
        exit(1)

    project_name = generate_project_name(asset_id)
    unreal_engine_path = get_unreal_engine_path()

    engine_version = extract_engine_version(unreal_engine_path)        
    if not engine_version or not is_supported_engine_version(engine_version):
        print(f"❌ Error: Unreal Engine version {engine_version} is not supported. Supported versions: 5.3.")
        exit(1)
    
    template_dir = os.path.join(unreal_engine_path, "Templates", "TP_Blank")
    project_dir = os.path.join(Path(script_dir).parent, project_name)
    uproject_file = os.path.join(project_dir, f"{project_name}.uproject")

    build_project_structure(project_name, template_dir, project_dir, unreal_engine_path, engine_version)    
    save_asset_metadata(project_dir, asset_id)    
    download_and_extract_plugin(project_dir)    
    enable_plugin_in_uproject(uproject_file, "JsonBlueprintUtilities")
        
    run_unreal_build(unreal_engine_path, project_name, project_dir)
    
    if not is_plugin_installed(unreal_engine_path, "Convai"):
        print("❌ Convai plugin is not installed. Install it from the marketplace.")
    else:
        enable_convai_plugin_in_uproject(uproject_file)
    
    input("Press Enter to exit...")  

if __name__ == "__main__":
    main()
