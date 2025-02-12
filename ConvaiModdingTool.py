import os
import sys
import json
import re
import importlib.util
import subprocess
import zipfile
import shutil
import requests
import hashlib
import base64
import time

SERVER_URL = "http://localhost:5000/getprojectname"

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

def get_asset_id():
    """
    Fetch the asset ID from the server.
    """
    try:
        response = requests.get(SERVER_URL)
        response.raise_for_status()
        asset_id = response.json().get("project_name")  # The original response field

        if not asset_id:
            raise ValueError("Invalid response from server: No project_name field found.")

        return asset_id

    except requests.RequestException as e:
        print(f"Error fetching asset ID: {e}")
        return None

def generate_project_name(asset_id):
    """
    Generate a 20-character Unreal Engine-compatible project name from the asset ID.
    Ensures that the name starts with a letter (A-Z).
    """
    hash_object = hashlib.sha256(asset_id.encode())  # Hash the asset ID
    base32_encoded = base64.b32encode(hash_object.digest()).decode()  # Base32 encoding (A-Z, 2-7)
    project_name = base32_encoded[:20]  # Truncate to 20 characters

    # Ensure first character is a letter (A-Z)
    if project_name[0].isdigit():
        project_name = "A" + project_name[1:]  # Replace the first character with 'A'

    return project_name


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

def install_gdown():
    """Installs gdown if it's not already installed."""
    subprocess.check_call([sys.executable, "-m", "pip", "install", "gdown"])

def download_from_gdrive(file_id, download_dir, filename):
    """
    Downloads a file from Google Drive to a specified directory.

    Args:
    - file_id (str): The Google Drive file ID.
    - download_dir (str): The directory where the file will be downloaded.
    - filename (str): The name of the downloaded file.
    """
    if not importlib.util.find_spec("gdown"):
        install_gdown()
        importlib.reload(importlib)

    import gdown

    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    destination_path = os.path.join(download_dir, filename)
    url = f"https://drive.google.com/uc?id={file_id}"
    
    print(f"Downloading file from Google Drive: {file_id} to {destination_path}")
    gdown.download(url, destination_path, quiet=False)
    
    if os.path.exists(destination_path):
        print(f"Download complete: {destination_path}")
        return destination_path
    else:
        print("Error: Download failed.")
        return None

def unzip_file(zip_path, destination_path):
    """
    Unzips a ZIP file to a specified destination.

    Args:
    - zip_path (str): The path of the ZIP file to extract.
    - destination_path (str): The directory where the contents should be extracted.
    """
    if not os.path.exists(destination_path):
        os.makedirs(destination_path)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(destination_path)
        print(f"Extracted contents to: {destination_path}")
    except zipfile.BadZipFile:
        print("Error: The downloaded file is not a valid ZIP archive.")


def case_preserving_replace(old_value, new_value, text):
    """
    Replace occurrences of the old_value within the text, preserving the original case of the matched value.
    """
    def replace_with_matching_case(match):
        matched_text = match.group(0)
        if matched_text.isupper():
            return new_value.upper()
        elif matched_text.islower():
            return new_value.lower()
        elif matched_text[0].isupper() and matched_text[1:].islower():
            return new_value.capitalize()
        return new_value

    pattern = re.compile(re.escape(old_value), re.IGNORECASE)
    return pattern.sub(replace_with_matching_case, text)


def update_file_content(file_path, old_value, new_value):
    """
    Replace old_value with new_value in the specified file, preserving case sensitivity.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except (UnicodeDecodeError, IOError):
        print(f"Skipping file due to read error: {file_path}")
        return

    new_content = case_preserving_replace(old_value, new_value, content)
    if content != new_content:
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(new_content)
            #print(f"Updated '{old_value}' to '{new_value}' in {file_path}")
        except IOError:
            print(f"Error writing to file: {file_path}")


def rename_file(file_path, old_value, new_value):
    """
    Rename the file if old_value is part of the file name, preserving case.
    """
    directory, file_name = os.path.split(file_path)
    if old_value.lower() in file_name.lower():
        new_file_name = case_preserving_replace(old_value, new_value, file_name)
        new_file_path = os.path.join(directory, new_file_name)
        if not os.path.exists(new_file_path):
            os.rename(file_path, new_file_path)
            #print(f"Renamed file: {file_path} -> {new_file_path}")
        #else:
            #print(f"File already exists: {new_file_path}")


def rename_directory(directory, old_value, new_value):
    """
    Rename directories that contain old_value in their names.
    """
    parent_dir = os.path.dirname(directory)
    dir_name = os.path.basename(directory)

    if old_value.lower() in dir_name.lower():
        new_dir_name = case_preserving_replace(old_value, new_value, dir_name)
        new_dir_path = os.path.join(parent_dir, new_dir_name)

        if not os.path.exists(new_dir_path):
            os.rename(directory, new_dir_path)
            #print(f"Renamed directory: {directory} -> {new_dir_path}")
            return new_dir_path  # Return the new directory path for further operations
        #else:
           #print(f"Directory already exists: {new_dir_path}")

    return directory  # Return the original directory if no renaming occurred

def is_text_file(file_path):
    """
    Check if the file is a text file based on its extension.
    """
    text_extensions = {".cpp", ".h", ".cs", ".ini", ".uproject"}
    return os.path.splitext(file_path)[1].lower() in text_extensions


def update_directory_structure(directory, old_value, new_value):
    """
    Recursively replace old_value with new_value in files and rename directories.
    """
    for root, dirs, files in os.walk(directory, topdown=False):  # Traverse bottom-up for directory renaming
        for file_name in files:
            file_path = os.path.join(root, file_name)
            if is_text_file(file_path):
                update_file_content(file_path, old_value, new_value)
            rename_file(file_path, old_value, new_value)

        for dir_name in dirs:
            dir_path = os.path.join(root, dir_name)
            rename_directory(dir_path, old_value, new_value)


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


def save_asset_metadata(project_dir, asset_id):
    """Save the asset ID to PakMetaData.txt inside ProjectDir/ConvaiEssentials/."""
    metadata_dir = os.path.join(project_dir, "ConvaiEssentials")
    os.makedirs(metadata_dir, exist_ok=True)

    metadata_file = os.path.join(metadata_dir, "PakMetaData.txt")
    with open(metadata_file, "w", encoding="utf-8") as file:
        json.dump({"asset_id": asset_id}, file, indent=4)


def download_and_extract_plugin(project_dir):
    """Download and extract ConvaiPakManager plugin into ProjectDir/Plugins/."""
    file_id = "1Cioj7IhSV3s-bBHiFbgfcFyUIIsvHyfe"
    download_dir = os.path.join(project_dir, "ConvaiEssentials")
    filename = "ConvaiPakManagerPlugin.zip"

    downloaded_file = download_from_gdrive(file_id, download_dir, filename)
    if downloaded_file:
        unzip_destination = os.path.join(project_dir, "Plugins", "ConvaiPakManager")
        unzip_file(downloaded_file, unzip_destination)


def download_latest_github_release(github_repo, download_dir, filename, max_retries=3):
    """
    Downloads the latest release ZIP from a given GitHub repository.

    Args:
    - github_repo (str): GitHub repository in 'owner/repo' format.
    - download_dir (str): Directory to save the downloaded ZIP.
    - filename (str): Name of the ZIP file to be saved.
    - max_retries (int): Number of retry attempts in case of failure.

    Returns:
    - str: Full path of the downloaded ZIP file or None if failed.
    """

    github_api_url = f"https://api.github.com/repos/{github_repo}/releases/latest"
    zip_path = os.path.join(download_dir, filename)

    os.makedirs(download_dir, exist_ok=True)

    for attempt in range(max_retries):
        try:
            print(f"Fetching latest release from GitHub ({github_repo}), attempt {attempt + 1}...")
            response = requests.get(github_api_url)
            response.raise_for_status()
            release_data = response.json()

            # Find the ZIP download URL
            zip_url = None
            for asset in release_data.get("assets", []):
                if asset["name"].endswith(".zip"):
                    zip_url = asset["browser_download_url"]
                    break

            if not zip_url:
                print(f"Error: No ZIP file found in the latest release of {github_repo}.")
                return None

            print(f"Downloading {zip_url} to {zip_path}...")

            # Download file in chunks to avoid memory overflow
            with requests.get(zip_url, stream=True) as r:
                r.raise_for_status()
                with open(zip_path, "wb") as file:
                    for chunk in r.iter_content(chunk_size=8192):
                        file.write(chunk)

            print(f"Download complete: {zip_path}")
            return zip_path

        except requests.RequestException as e:
            print(f"Download failed (Attempt {attempt + 1} of {max_retries}): {e}")
            time.sleep(2)  # Wait before retrying

    print("Download failed after multiple attempts.")
    return None


def extract_and_install_plugin(zip_path, plugins_dir):
    """
    Extracts a ZIP file and moves the plugin correctly into ProjectDir/Plugins/.

    Args:
    - zip_path (str): Path to the downloaded ZIP file.
    - plugins_dir (str): Destination directory for the plugin.
    
    Returns:
    - str: Final path of the extracted plugin or None if extraction failed.
    """

    if not os.path.exists(zip_path):
        print(f"Error: ZIP file not found at {zip_path}")
        return None

    # Temporary extraction path inside Plugins directory
    temp_extraction_path = os.path.join(plugins_dir, "Temp_Extracted_Plugin")
    os.makedirs(temp_extraction_path, exist_ok=True)

    try:
        # Extract the ZIP
        print(f"Extracting {zip_path} to {temp_extraction_path}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_extraction_path)

        # Locate the plugin folder that contains the .uplugin file
        plugin_folder = None
        for root, dirs, files in os.walk(temp_extraction_path):
            for file in files:
                if file.endswith(".uplugin"):
                    plugin_folder = root
                    break
            if plugin_folder:
                break

        if not plugin_folder:
            print("Error: No .uplugin file found in the extracted content.")
            return None

        # Move the extracted plugin to the Plugins directory
        final_plugin_path = os.path.join(plugins_dir, os.path.basename(plugin_folder))

        # Remove existing folder if already present
        if os.path.exists(final_plugin_path):
            shutil.rmtree(final_plugin_path)

        shutil.move(plugin_folder, final_plugin_path)
        print(f"Plugin successfully installed at: {final_plugin_path}")

        # Cleanup: Remove temporary extraction folder
        shutil.rmtree(temp_extraction_path, ignore_errors=True)

        return final_plugin_path

    except zipfile.BadZipFile:
        print("Error: The downloaded file is not a valid ZIP archive.")
        return None


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
    if not engine_version:
        print("Unable to proceed without a valid Unreal Engine version.")
        exit(1)

    template_dir = os.path.join(unreal_engine_path, "Templates", "TP_Blank")
    project_dir = os.path.join(script_dir, project_name)

    build_project_structure(project_name, template_dir, project_dir, unreal_engine_path, engine_version)    
    save_asset_metadata(project_dir, asset_id)    
    download_and_extract_plugin(project_dir)
    
    # Example usage inside another function
    #essentials_dir = os.path.join(project_dir, "ConvaiEssentials")
    #plugins_dir = os.path.join(project_dir, "Plugins")

    # Download latest release from GitHub
    #zip_file_path = download_latest_github_release("Conv-AI/Convai-UnrealEngine-SDK", essentials_dir, "ConvaiSDK.zip")

    # Extract and install if download was successful
    #if zip_file_path:
    #    extract_and_install_plugin(zip_file_path, plugins_dir)
    
    run_unreal_build(unreal_engine_path, project_name, project_dir)

if __name__ == "__main__":
    main()
