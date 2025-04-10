import json
import os
import re
import shutil
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from core.file_utils import update_directory_structure

def set_engine_version(uproject_file, engine_version):
    """
    Update the EngineAssociation field in the .uproject file to match the specified engine version.
    """
    try:
        with open(uproject_file, 'r', encoding='utf-8') as file:
            uproject_data = json.load(file)

        # Update or add the EngineAssociation field
        uproject_data['EngineAssociation'] = engine_version

        with open(uproject_file, 'w', encoding='utf-8') as file:
            json.dump(uproject_data, file, indent=4)
        #print(f"Updated EngineAssociation to '{engine_version}' in {uproject_file}")

    except (json.JSONDecodeError, IOError) as e:
        print(f"Error updating EngineAssociation in .uproject file: {e}")

def run_unreal_build(ue_directory, project_name, project_dir):
    """
    Compiles the Unreal Engine project after creation using UnrealBuildTool.exe (UBT).
    """
    ubt_path = os.path.join(ue_directory, "Engine", "Binaries", "DotNET", "UnrealBuildTool", "UnrealBuildTool.exe")

    if not os.path.exists(ubt_path):
        print(f"Error: UnrealBuildTool.exe not found at {ubt_path}")
        return

    uproject_path = os.path.join(project_dir, f"{project_name}.uproject")

    build_command = [
        ubt_path,
        f"-Project={uproject_path}",
        f"-Target={project_name}Editor",
        "Win64",  
        "Development",
        "-Progress",
        "-NoHotReload"
    ]

    print("Running Unreal Compilation Command...")
    result = subprocess.run(build_command, shell=True)

    if result.returncode != 0:
        print("Error: Unreal Compilation failed.")
    else:
        print("Unreal Compilation completed successfully!")

def build_project_structure(project_name, project_dir, ue_path, engine_version):
    """
    Create a new Unreal Engine project from a template.
    Performs validation on the project name:
    - The project name must not exceed 20 characters.
    - The project directory must not already exist.
    
    Returns:
        bool: True if the project structure was built successfully, False otherwise.
    """
    # Validate project name length
    if len(project_name) > 20:
        print("Error: Project name is invalid. It should not exceed 20 characters.")
        return False

    # Validate that the project directory does not already exist
    if os.path.exists(project_dir):
        print(f"Error: Project directory already exists: {project_dir}")
        return False

    template_dir = os.path.join(ue_path, "Templates", "TP_Blank")
    
    # Copy template
    shutil.copytree(template_dir, project_dir)

    # Create missing Content folder if it doesn't exist
    content_dir = os.path.join(project_dir, 'Content')
    if not os.path.exists(content_dir):
        os.makedirs(content_dir)

    # Replace all occurrences of the template name in the project
    update_directory_structure(project_dir, "TP_Blank", project_name)

    # Update the .uproject file with the correct engine version
    uproject_file = os.path.join(project_dir, f"{project_name}.uproject")
    set_engine_version(uproject_file, engine_version)

    print(f"Project '{project_name}' created successfully at {project_dir}")
    return True

def extract_engine_version(installation_dir):
    """
    Parse the Version.h file to get the Unreal Engine version.
    """
    version_file = os.path.join(installation_dir, "Engine", "Source", "Runtime", "Launch", "Resources", "Version.h")

    if not os.path.exists(version_file):
        print("Error: Version.h file not found. Please check the installation directory.")
        return None

    version = {}
    try:
        with open(version_file, 'r', encoding='utf-8') as file:
            lines = file.readlines()
            for line in lines:
                major_match = re.search(r"^\s*#define\s+ENGINE_MAJOR_VERSION\s+(\d+)", line)
                minor_match = re.search(r"^\s*#define\s+ENGINE_MINOR_VERSION\s+(\d+)", line)
                if major_match:
                    version['major'] = major_match.group(1)
                if minor_match:
                    version['minor'] = minor_match.group(1)
                    
        if 'major' in version and 'minor' in version:
            return f"{version['major']}.{version['minor']}"
        else:
            print("Error: Unable to parse Unreal Engine version from Version.h. Ensure the file contains the expected version defines.")
            print("Debug Info: Parsed lines:")
            for line in lines:
                print(line.strip())
            return None

    except Exception as e:
        print(f"Error reading Version.h: {e}")
        return None

def is_valid_engine_path(ue_path: Path) -> bool:
    if not ue_path.exists():
        return False
    
    engine_version = extract_engine_version(ue_path)
    if not engine_version or not is_supported_engine_version(engine_version):
        return False
    return True

def get_unreal_engine_path(default_paths=None):
    """
    Retrieve and validate the Unreal Engine installation directory.

    Args:
        default_paths (str or list of str, optional): One or more default Unreal Engine paths to try.

    Returns:
        str: A valid Unreal Engine directory path.
    """
    if default_paths is None:
        default_paths = []
    elif isinstance(default_paths, str):
        default_paths = [default_paths]

    for default_path in default_paths:
        path_obj = Path(default_path)
        if is_valid_engine_path(path_obj):
            response = input(f"Found valid Unreal Engine path: {path_obj}\nDo you want to use this path? (Y/N): ").strip().lower()
            if response in ("", "y", "yes"):
                return str(path_obj)

    while True:
        user_input = input("Enter the Unreal Engine 5.3 installation directory: ").strip()
        engine_path = Path(user_input)
        if is_valid_engine_path(engine_path):
            print(f"Using Unreal Engine path: {engine_path}")
            return str(engine_path)
        else:
            print("Invalid path Unreal Engine 5.3 path")

def is_plugin_installed(ue_dir, plugin_name):
    """
    Checks if a plugin is installed in the Unreal Engine project.

    Args:
        project_dir (str): The base project directory.
        plugin_name (str): The name of the plugin.

    Returns:
        bool: True if the plugin exists, False otherwise.
    """
    plugin_path = os.path.join(ue_dir, "Engine", "Plugins", "Marketplace", plugin_name)
    
    return os.path.isdir(plugin_path)

def enable_plugin_in_uproject(uproject_path, plugin_name, marketplace_url=""):
    """
    Adds a specified plugin entry to the Plugins array in the .uproject file if not already present.

    Args:
        uproject_path (str): The path to the .uproject file.
        plugin_name (str): The name of the plugin to enable.
        marketplace_url (str, optional): The Marketplace URL for the plugin (default: empty string).

    Returns:
        bool: True if the plugin was added, False if it was already present or failed to update.
    """
    if not os.path.exists(uproject_path):
        print(f"❌ .uproject file not found: {uproject_path}")
        return False

    try:
        # Read the existing .uproject file
        with open(uproject_path, "r", encoding="utf-8") as file:
            uproject_data = json.load(file)

        # Ensure the "Plugins" array exists
        if "Plugins" not in uproject_data:
            uproject_data["Plugins"] = []

        # Plugin entry
        plugin_entry = {
            "Name": plugin_name,
            "Enabled": True,
        }

        if marketplace_url:
            plugin_entry["MarketplaceURL"] = marketplace_url

        # Check if the plugin is already enabled
        if any(plugin.get("Name") == plugin_name for plugin in uproject_data["Plugins"]):
            return False  # Plugin already enabled

        # Add the plugin entry
        uproject_data["Plugins"].append(plugin_entry)

        # Write back to the .uproject file
        with open(uproject_path, "w", encoding="utf-8") as file:
            json.dump(uproject_data, file, indent=4)

        return True

    except json.JSONDecodeError:
        print("❌ Error: Failed to parse .uproject JSON.")
        return False
    except IOError:
        print("❌ Error: Unable to write to the .uproject file.")
        return False

def enable_plugins_in_uproject(project_dir, project_name, PluginNames):
    for It in PluginNames:
        enable_plugin_in_uproject(os.path.join(project_dir, f"{project_name}.uproject"), It)

def is_supported_engine_version(engine_version):
    """
    Checks if the given engine version is supported.

    Args:
        engine_version (str): The extracted Unreal Engine version (e.g., '5.3').
        supported_versions (list, optional): A list of supported versions (default: ['5.3']).

    Returns:
        bool: True if the version is supported, False otherwise.
    """
    supported_versions = ["5.3"]

    return engine_version in supported_versions

def create_content_only_plugin(project_dir: str, plugin_name: str):
    plugin_dir = Path(project_dir) / "Plugins" / plugin_name
    content_dir = plugin_dir / "Content"
    uplugin_path = plugin_dir / f"{plugin_name}.uplugin"

    # Create plugin and content directories
    os.makedirs(content_dir, exist_ok=True)

    # Define the .uplugin file content
    uplugin_data = {
        "FileVersion": 3,
        "Version": 1,
        "VersionName": "1.0",
        "FriendlyName": plugin_name,
        "Description": f"{plugin_name} content-only plugin.",
        "Category": "Other",
        "CreatedBy": "Convai modding tool",
        "CreatedByURL": "",
        "DocsURL": "",
        "MarketplaceURL": "",
        "SupportURL": "",
        "CanContainContent": True,
        "IsBetaVersion": False,
        "IsExperimentalVersion": False,
        "Installed": False,
    }

    # Save the .uplugin file
    with open(uplugin_path, "w") as f:
        json.dump(uplugin_data, f, indent=4)
   
def is_valid_project_name(name: str, root_dir: Path):
    return (
        name and                      # name is not empty
        not name[0].isdigit() and     # doesn't start with a digit
        not (root_dir / name).exists()  # doesn't already exist
    )

def get_project_name(project_root_dir: str):
    """
    Prompt for or retrieve a valid project name that:
    - Doesn't start with a number
    - Doesn't already exist under the specified project root directory

    Args:
        project_root_dir (str or Path): Directory where the new project will be created.

    Returns:
        str: A validated project name.
    """
    root_dir = Path(project_root_dir)

    while True:
        name = input(f"Enter the Project Name: ").strip()
        if is_valid_project_name(name, root_dir):
            return name
        else :
            print("Enter a valid project name")

def is_version_greater(v1, v2):
    """
    Compare two semantic version strings (e.g., "3.6.1" and "3.5.2").
    Returns True if v1 is greater than v2, else False.
    """
    def parse_version(v):
        return [int(part) for part in v.split('.')]
    
    v1_parts = parse_version(v1)
    v2_parts = parse_version(v2)
    
    # Pad the shorter version with zeros (e.g., "3.6" becomes [3,6,0])
    max_length = max(len(v1_parts), len(v2_parts))
    v1_parts.extend([0] * (max_length - len(v1_parts)))
    v2_parts.extend([0] * (max_length - len(v2_parts)))
    
    return v1_parts > v2_parts

def verify_convai_plugin(ue_dir):
    """
    Verifies if the Convai plugin is installed and its version is greater than 3.5.2.
    If verification fails, it prompts the user to update the plugin using prompt_update_convai_plugin.
    
    Args:
        ue_dir (str): The Unreal Engine installation directory.
        
    Returns:
        bool: True if the Convai plugin is installed and its version is greater than 3.5.2,
              False otherwise.
    """
    plugin_name = "Convai"
    update_url = "https://www.fab.com/listings/ba3145af-d2ef-434a-8bc3-f3fa1dfe7d5c"
    
    # Check if the plugin is installed.
    if not is_plugin_installed(ue_dir, plugin_name):
        prompt_update_convai_plugin(update_url, "Convai plugin is not installed.")
        return False
    
    # Construct the path to the Convai plugin directory.
    plugin_path = os.path.join(ue_dir, "Engine", "Plugins", "Marketplace", plugin_name)
    
    # Search for the .uplugin file in the plugin directory.
    uplugin_file = None
    for filename in os.listdir(plugin_path):
        if filename.endswith(".uplugin"):
            uplugin_file = os.path.join(plugin_path, filename)
            break
    
    if not uplugin_file or not os.path.exists(uplugin_file):
        prompt_update_convai_plugin(update_url, "Error: .uplugin file not found for Convai plugin.")
        return False
    
    # Load and parse the .uplugin file.
    try:
        with open(uplugin_file, "r", encoding="utf-8") as f:
            plugin_data = json.load(f)
    except Exception as e:
        prompt_update_convai_plugin(update_url, f"Error reading .uplugin file: {e}")
        return False
    
    version_name = plugin_data.get("VersionName", "")
    if not version_name:
        prompt_update_convai_plugin(update_url, "Error: VersionName not found in the .uplugin file.")
        return False
    
    if is_version_greater(version_name, "3.5.1"):
        print(f"Verification successful: Convai plugin version is {version_name}.")
        return True
    else:
        prompt_update_convai_plugin(update_url, f"Error: You need to update the Convai plugin. Current version: {version_name}.")
        return False

def prompt_update_convai_plugin(update_url, error_message):
    """
    Prompts the user to update the Convai plugin by printing an error message,
    waiting 2 seconds, and opening the update URL in the default web browser.
    
    Args:
        update_url (str): The URL to open for updating the plugin.
        error_message (str): The error message to display.
    """
    print(error_message)
    print("Please update the Convai plugin. Opening update link in your browser shortly...")
    time.sleep(2)
    webbrowser.open(update_url)
    
def update_default_game_ini(project_dir, plugin_name):
    """
    Updates the DefaultGame.ini file in the project's Config directory with the required settings.
    
    This function writes hardcoded settings to DefaultGame.ini. It replaces the <PluginName> placeholder
    with the provided plugin_name.
    
    Args:
        project_dir (str): The path to your Unreal project directory.
        plugin_name (str): The name of the content-only plugin.
    """
    # Ensure the Config directory exists
    config_dir = os.path.join(project_dir, "Config")
    os.makedirs(config_dir, exist_ok=True)
    
    # Path to the DefaultGame.ini file
    default_game_ini_path = os.path.join(config_dir, "DefaultGame.ini")
    
    # Hardcoded INI content with <PluginName> placeholder
    ini_content = r'''
[/Script/UnrealEd.ProjectPackagingSettings]
bUseIoStore=False
bGenerateChunks=True
bShareMaterialShaderCode=False
UsePakFile=True

[/Script/Engine.AssetManagerSettings]
-PrimaryAssetTypesToScan=(PrimaryAssetType="Map",AssetBaseClass=/Script/Engine.World,bHasBlueprintClasses=False,bIsEditorOnly=True,Directories=((Path="/Game/Maps")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
-PrimaryAssetTypesToScan=(PrimaryAssetType="PrimaryAssetLabel",AssetBaseClass=/Script/Engine.PrimaryAssetLabel,bHasBlueprintClasses=False,bIsEditorOnly=True,Directories=((Path="/Game")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
+PrimaryAssetTypesToScan=(PrimaryAssetType="Map",AssetBaseClass="/Script/Engine.World",bHasBlueprintClasses=False,bIsEditorOnly=True,Directories=((Path="/Game/Maps")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
+PrimaryAssetTypesToScan=(PrimaryAssetType="PrimaryAssetLabel",AssetBaseClass="/Script/Engine.PrimaryAssetLabel",bHasBlueprintClasses=False,bIsEditorOnly=True,Directories=((Path="/Game"),(Path="/<PluginName>")),SpecificAssets=,Rules=(Priority=-1,ChunkId=-1,bApplyRecursively=True,CookRule=Unknown))
bOnlyCookProductionAssets=False
bShouldManagerDetermineTypeAndName=False
bShouldGuessTypeAndNameInEditor=True
bShouldAcquireMissingChunksOnLoad=False
bShouldWarnAboutInvalidAssets=True
MetaDataTagsForAssetRegistry=()
    '''
    # Replace <PluginName> with the actual plugin name
    ini_content = ini_content.replace("<PluginName>", plugin_name)
    
    # Write the content to DefaultGame.ini
    with open(default_game_ini_path, "w", encoding="utf-8") as file:
        file.write(ini_content.strip() + "\n")
    
    print(f"DefaultGame.ini has been updated with plugin name: {plugin_name}")

def update_default_engine_ini(project_dir, convai_api_key):
    """
    Appends the Convai API key to the DefaultEngine.ini file in the project's Config directory.

    Args:
        project_dir (str): The path to your Unreal project directory.
        api_key (str): The Convai API key entered by the user.
    """
    config_dir = os.path.join(project_dir, "Config")
    os.makedirs(config_dir, exist_ok=True)

    default_engine_ini_path = os.path.join(config_dir, "DefaultEngine.ini")

    # Lines to append
    lines_to_add = f"""
[/Script/EngineSettings.GameMapsSettings]
GlobalDefaultGameMode=/Game/ConvaiConveniencePack/Sample/BP_SampleGameMode.BP_SampleGameMode_C

[/Script/Convai.ConvaiSettings]
API_Key={convai_api_key}
"""
    with open(default_engine_ini_path, "a", encoding="utf-8") as file:
        file.write(lines_to_add.strip() + "\n")