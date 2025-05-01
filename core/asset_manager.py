import json
import os
import msvcrt

from core.download_utils import download_convai_realusion_content
from core.file_utility_manager import FileUtilityManager

def save_metadata(project_dir, data: dict):
    """
    Save or update multiple key-value pairs in ModdingMetaData.txt inside ProjectDir/ConvaiEssentials/.

    Args:
        project_dir (str): Path to the Unreal project directory.
        data (dict): Dictionary of field_name -> field_value to save.
    """
    metadata_dir = os.path.join(project_dir, "ConvaiEssentials")
    os.makedirs(metadata_dir, exist_ok=True)

    metadata_file = os.path.join(metadata_dir, "ModdingMetaData.txt")

    # Load existing metadata if the file exists
    metadata = {}
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as file:
                metadata = json.load(file)
        except (json.JSONDecodeError, IOError):
            print("Warning: Existing ModdingMetaData.txt is corrupted or unreadable. Overwriting.")

    # Update with new data
    metadata.update(data)

    # Save back to file
    with open(metadata_file, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4)

def get_metadata(project_dir):
    """
    Load metadata from ModdingMetaData.txt inside ProjectDir/ConvaiEssentials/.

    Args:
        project_dir (str): Path to the Unreal project directory.

    Returns:
        dict: Loaded metadata dictionary, or empty dict if file not found or corrupted.
    """
    metadata_file = os.path.join(project_dir, "ConvaiEssentials", "ModdingMetaData.txt")

    if not os.path.exists(metadata_file):
        print(f"Warning: Metadata file not found at {metadata_file}. Returning empty metadata.")
        return {}

    try:
        with open(metadata_file, "r", encoding="utf-8") as file:
            metadata = json.load(file)
            return metadata
    except (json.JSONDecodeError, IOError):
        print(f"Warning: Failed to load metadata from {metadata_file}. Returning empty metadata.")
        return {}

def get_asset_type_from_user():
    """
    Prompts the user to choose between Scene (1) or Avatar (2).
    If Avatar is selected, also asks if they are using a MetaHuman.

    Returns:
        tuple: (asset_type: str, is_metahuman: Optional[bool])
    """
    while True:
        print("Select the type of asset you want to create:")
        print("1. Scene")
        print("2. Avatar")
        choice = input("Enter your choice (1 or 2): ").strip()

        if choice == "1":
            return "Scene", False

        elif choice == "2":
            while True:
                meta_input = input("Are you using a MetaHuman for your avatar? (y/n): ").strip().lower()
                if meta_input in ("y", "yes"):
                    return "Avatar", True
                elif meta_input in ("n", "no"):
                    return "Avatar", False
                else:
                    print("Invalid input. Please enter 'y' or 'n'.")

        else:
            print("Invalid input. Please enter 1 or 2.")

def get_api_key():
    print("Enter the Convai API key: ", end='', flush=True)
    key = ""
    while True:
        ch = msvcrt.getch()
        if ch in {b'\r', b'\n'}:
            print()  # Move to next line after Enter
            if key and key.isalnum():
                return key
            else:
                print("Invalid API key. Please enter a valid alphanumeric key.")
                return get_api_key()
        elif ch == b'\x08':  # Backspace
            if len(key) > 0:
                key = key[:-1]
                print('\b \b', end='', flush=True)
        elif ch == b'\x03':  # Ctrl+C
            raise KeyboardInterrupt
        else:
            char = ch.decode()
            if char.isalnum():
                key += char
                print('*', end='', flush=True)
            
def should_remove_metahuman_folder(asset_type, is_metahuman):
    
    if asset_type == "Scene":
        return True
    
    if not is_metahuman :
        return True
    
    return False

def move_asset_uploader_ui(project_dir):
    source = os.path.join(project_dir, "Plugins", "ConvaiPakManager", "Content", "Editor", "AssetUploader.uasset")
    destination = os.path.join(project_dir, "Content", "Editor")
    FileUtilityManager.copy_file_to_directory(source, destination)
    
def configure_assets_in_project(project_dir, asset_type, is_metahuman):
    
    move_asset_uploader_ui(project_dir)
    
    if should_remove_metahuman_folder(asset_type, is_metahuman):
        FileUtilityManager.remove_metahuman_folder(project_dir)
    
    if not is_metahuman and asset_type == "Avatar":
        download_convai_realusion_content(project_dir)

def get_user_flow_choice(script_dir):
    """
    Prompts the user to choose between creating a new project or updating an existing one.

    Returns:
        str: "create" or "update"
    """
    # Scan for existing modding projects
    existing_projects = []
    for root, dirs, files in os.walk(script_dir):
        if "ConvaiEssentials" in dirs and any(f.endswith(".uproject") for f in files):
            existing_projects.append(root)

    if not existing_projects:
        return "create"
    
    while True:
        print("\nWhat do you want to do?")
        print("1. Create a new modding project")
        print("2. Update an existing modding project")
        choice = input("Enter your choice (1 or 2): ").strip()

        if choice == "1":
            return "create"
        elif choice == "2":
            return "update"
        else:
            print("Invalid input. Please enter 1 or 2.")
