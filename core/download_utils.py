import os
import zipfile
import shutil
import requests
import time
import gdown

from core.file_utility_manager import FileUtilityManager

class DownloadManager:
    
    @staticmethod
    def download_from_gdrive(file_id, download_dir, filename):
        """
        Downloads a file from Google Drive to a specified directory.

        Args:
        - file_id (str): The Google Drive file ID.
        - download_dir (str): The directory where the file will be downloaded.
        - filename (str): The name of the downloaded file.
        """

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

    @staticmethod
    def download_plugins_from_gdrive_folder(folder_id, project_dir):   
        download_dir = os.path.join(project_dir, "ConvaiEssentials")
        os.makedirs(download_dir, exist_ok=True)
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        gdown.download_folder(url, output=download_dir, use_cookies=False, quiet=False)
        
        for f in os.listdir(download_dir):
            file_path = os.path.join(download_dir, f)
            if os.path.isfile(file_path) and f.lower().endswith(".zip"):
                DownloadManager.extract_plugin_zip(file_path, project_dir)

    @staticmethod
    def extract_plugin_zip(zip_path, project_dir):
        plugins_dir = os.path.join(project_dir, "Plugins")
        os.makedirs(plugins_dir, exist_ok=True)
        temp_dir = os.path.join(plugins_dir, "Temp_Extract_Plugin")
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)
        FileUtilityManager.unzip(zip_path, temp_dir)
        plugin_folder = None
        for root, _, files in os.walk(temp_dir):
            if any(f.endswith(".uplugin") for f in files):
                plugin_folder = root
                break
        if not plugin_folder:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None
        final_plugin_path = os.path.join(plugins_dir, os.path.basename(plugin_folder))
        if os.path.exists(final_plugin_path):
            shutil.rmtree(final_plugin_path, ignore_errors=True)
        shutil.move(plugin_folder, final_plugin_path)
        shutil.rmtree(temp_dir, ignore_errors=True)
        return final_plugin_path

    @staticmethod
    def download_and_extract_plugin(project_dir):
        """Download and extract ConvaiPakManager plugin into ProjectDir/Plugins/."""
        file_id = "1Cioj7IhSV3s-bBHiFbgfcFyUIIsvHyfe"
        download_dir = os.path.join(project_dir, "ConvaiEssentials")
        filename = "ConvaiPakManagerPlugin.zip"

        downloaded_file = DownloadManager.download_from_gdrive(file_id, download_dir, filename)
        if downloaded_file:
            unzip_destination = os.path.join(project_dir, "Plugins", "ConvaiPakManager")
            FileUtilityManager.unzip(downloaded_file, unzip_destination)

    @staticmethod
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

    @staticmethod
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

    @staticmethod
    def download_modding_dependencies(project_dir):
        #CC pak
        DownloadManager.download_from_gdrive("1y2lkBFo7ebRFt8SIiV9ME1mmRwgpnM3h", os.path.join(project_dir, "ConvaiEssentials"), "ConvaiConveniencePack.zip")
        FileUtilityManager.unzip(os.path.join(project_dir, "ConvaiEssentials", "ConvaiConveniencePack.zip"), os.path.join(project_dir, "Content"))
        
        #Necessary plugins
        DownloadManager.download_plugins_from_gdrive_folder("11n7EZW4SBd4Ri9Q6GuXFdoLrwCZvnnwq", project_dir)

    @staticmethod
    def download_convai_realusion_content(project_dir):
        DownloadManager.download_from_gdrive("1bAatTW4vYycDbGLeO1pGILc3OVOOR3je", os.path.join(project_dir, "ConvaiEssentials"), "ConvaiRealusionContent.zip")
        FileUtilityManager.unzip(os.path.join(project_dir, "ConvaiEssentials", "ConvaiRealusionContent.zip"), os.path.join(project_dir))