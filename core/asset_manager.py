import os

from core.download_utils import download_convai_realusion_content
from core.file_utility_manager import FileUtilityManager
     
def configure_assets_in_project(project_dir, asset_type, is_metahuman):
    
    source = os.path.join(project_dir, "Plugins", "ConvaiPakManager", "Content", "Editor", "AssetUploader.uasset")
    destination = os.path.join(project_dir, "Content", "Editor")
    FileUtilityManager.copy_file_to_directory(source, destination)
    
    if asset_type == "Scene" and not is_metahuman:
        FileUtilityManager.remove_metahuman_folder(project_dir)       
    
    if not is_metahuman and asset_type == "Avatar":
        download_convai_realusion_content(project_dir)
