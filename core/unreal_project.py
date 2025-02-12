import json
import os
import re
import shutil
import subprocess
import sys

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


def build_project_structure(project_name, template_dir, project_dir, ue_path, engine_version):
    """
    Create a new Unreal Engine project from a template.
    """
    if os.path.exists(project_dir):
        print(f"Error: Project directory already exists: {project_dir}")
        return

    # Copy template
    shutil.copytree(template_dir, project_dir)

    # Create missing Content folder if it doesn't exist
    content_dir = os.path.join(project_dir, 'Content')
    if not os.path.exists(content_dir):
        os.makedirs(content_dir)

    # Replace all occurrences of template name in the project
    update_directory_structure(project_dir, "TP_Blank", project_name)

    # Update the .uproject file with the correct engine version
    uproject_file = os.path.join(project_dir, f"{project_name}.uproject")
    set_engine_version(uproject_file, engine_version)

    print(f"Project '{project_name}' created successfully at {project_dir}")

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
