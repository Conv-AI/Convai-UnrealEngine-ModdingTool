import json
import os
import re
import shutil
import subprocess
import sys
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
                # Debug: Print each line being read
                # print(f"Parsing line: {line.strip()}")

                major_match = re.search(r"^\s*#define\s+ENGINE_MAJOR_VERSION\s+(\d+)", line)
                minor_match = re.search(r"^\s*#define\s+ENGINE_MINOR_VERSION\s+(\d+)", line)

                if major_match:
                    version['major'] = major_match.group(1)
                    #print(f"Found major version: {version['major']}")  # Debug
                if minor_match:
                    version['minor'] = minor_match.group(1)
                    #print(f"Found minor version: {version['minor']}")  # Debug

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

def get_unreal_engine_path():
    """Retrieve the Unreal Engine installation directory."""
    return sys.argv[1] if len(sys.argv) > 1 else input("Enter the Unreal Engine installation directory: ")

def is_plugin_installed(project_dir, plugin_name):
    """
    Checks if a plugin is installed in the Unreal Engine project.

    Args:
        project_dir (str): The base project directory.
        plugin_name (str): The name of the plugin.

    Returns:
        bool: True if the plugin exists, False otherwise.
    """
    plugin_path = os.path.join(project_dir, "Engine", "Plugins", "Marketplace", plugin_name)
    
    return os.path.isdir(plugin_path)

def enable_convai_plugin_in_uproject(uproject_path):
    """
    Adds the ConvAI plugin entry to the Plugins array in the .uproject file if not already present.

    Args:
        uproject_path (str): The path to the .uproject file.

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

        # ConvAI Plugin entry
        convai_plugin_entry = {
            "Name": "ConvAI",
            "Enabled": True,
            "MarketplaceURL": "com.epicgames.launcher://ue/marketplace/product/696326c90d80462b8775712d2b6cc2a7"
        }

        # Check if ConvAI is already enabled
        if any(plugin.get("Name") == "ConvAI" for plugin in uproject_data["Plugins"]):
            #print("✅ ConvAI plugin is already enabled in the .uproject file.")
            return False

        # Add the plugin entry
        uproject_data["Plugins"].append(convai_plugin_entry)

        # Write back to the .uproject file
        with open(uproject_path, "w", encoding="utf-8") as file:
            json.dump(uproject_data, file, indent=4)

        #print("✅ ConvAI plugin added to the .uproject file.")
        return True

    except json.JSONDecodeError:
        print("❌ Error: Failed to parse .uproject JSON.")
        return False
    except IOError:
        print("❌ Error: Unable to write to the .uproject file.")
        return False

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
   
def get_project_name():
    """Retrieve the project name from command line arguments or by prompting the user."""
    return sys.argv[2] if len(sys.argv) > 2 else input("Enter the Project Name: ")
