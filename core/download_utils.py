import importlib.util
import os
import subprocess
import sys
import zipfile
import shutil
import requests
import time

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

