import os
import zipfile
import shutil
import requests
import time
import gdown
from urllib.parse import unquote

from core.config_manager import config
from core.file_utility_manager import FileUtilityManager
from core.github_manager import GitHubManager
from core.plugin_manager import PluginManager
from core.logger import logger

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
        
        logger.debug(f"Downloading from Google Drive: {filename}")
        gdown.download(url, destination_path, quiet=True)
        
        if os.path.exists(destination_path):
            logger.debug(f"Google Drive download complete: {filename}")
            return destination_path
        else:
            logger.error("Google Drive download failed")
            return None

    @staticmethod
    def download_plugins_from_gdrive_folder(folder_id, project_dir):   
        download_dir = os.path.join(project_dir, config.get_essentials_dir_name())
        os.makedirs(download_dir, exist_ok=True)
        url = f"https://drive.google.com/drive/folders/{folder_id}"
        gdown.download_folder(url, output=download_dir, use_cookies=False, quiet=True)
        
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

        logger.debug(f"Unzipping plugin archive: {os.path.basename(zip_path)}")
        FileUtilityManager.unzip(zip_path, temp_dir)

        # Find a directory that contains a .uplugin file and capture its name
        plugin_folder = None
        uplugin_path = None
        uplugin_name_no_ext = None
        for root, _, files in os.walk(temp_dir):
            for f in files:
                if f.endswith(".uplugin"):
                    plugin_folder = root
                    uplugin_path = os.path.join(root, f)
                    uplugin_name_no_ext = os.path.splitext(f)[0]
                    break
            if plugin_folder:
                break

        if not plugin_folder or not uplugin_path:
            logger.error("No .uplugin file found in extracted archive")
            shutil.rmtree(temp_dir, ignore_errors=True)
            return None

        # Decide final folder name from .uplugin (more reliable than inner folder names)
        final_plugin_folder_name = uplugin_name_no_ext or os.path.basename(plugin_folder)
        final_plugin_path = os.path.join(plugins_dir, final_plugin_folder_name)

        logger.debug(f"Detected plugin folder: {plugin_folder}")
        logger.debug(f"Detected plugin descriptor: {os.path.basename(uplugin_path)}")
        logger.debug(f"Installing plugin to: {final_plugin_path}")

        # Remove existing installation if present
        if os.path.exists(final_plugin_path):
            shutil.rmtree(final_plugin_path, ignore_errors=True)

        try:
            # If the .uplugin is at the zip root (plugin_folder == temp_dir),
            # move the contents of temp_dir into final_plugin_path (not the temp dir itself)
            if os.path.normpath(plugin_folder) == os.path.normpath(temp_dir):
                os.makedirs(final_plugin_path, exist_ok=True)
                for item in os.listdir(temp_dir):
                    src_path = os.path.join(temp_dir, item)
                    dst_path = os.path.join(final_plugin_path, item)
                    shutil.move(src_path, dst_path)
            else:
                # Otherwise move the detected plugin folder as a whole
                shutil.move(plugin_folder, final_plugin_path)

            logger.debug(f"Plugin installed: {final_plugin_folder_name}")
            return final_plugin_path
        finally:
            # Cleanup temporary extraction directory
            shutil.rmtree(temp_dir, ignore_errors=True)

    @staticmethod
    def download_and_extract_plugin(project_dir):
        """Download and extract ConvaiPakManager plugin into ProjectDir/Plugins/."""
        file_id = config.get_google_drive_id("convai_pak_manager_plugin")
        download_dir = os.path.join(project_dir, config.get_essentials_dir_name())
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
                logger.debug(f"Fetching latest release from {github_repo}, attempt {attempt + 1}...")
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
                    logger.error(f"No ZIP file found in the latest release of {github_repo}")
                    return None

                logger.debug(f"Downloading {filename}...")

                # Download file in chunks to avoid memory overflow
                with requests.get(zip_url, stream=True) as r:
                    r.raise_for_status()
                    with open(zip_path, "wb") as file:
                        for chunk in r.iter_content(chunk_size=8192):
                            file.write(chunk)

                logger.debug(f"Download complete: {filename}")
                return zip_path

            except requests.RequestException as e:
                logger.debug(f"Download attempt {attempt + 1} failed: {e}")
                time.sleep(2)  # Wait before retrying

        logger.error("Download failed after multiple attempts")
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
            logger.error(f"ZIP file not found: {zip_path}")
            return None

        # Temporary extraction path inside Plugins directory
        temp_extraction_path = os.path.join(plugins_dir, "Temp_Extracted_Plugin")
        os.makedirs(temp_extraction_path, exist_ok=True)

        try:
            # Extract the ZIP
            logger.debug(f"Extracting plugin from {os.path.basename(zip_path)}...")
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
                logger.error("No .uplugin file found in the extracted content")
                return None

            # Move the extracted plugin to the Plugins directory
            final_plugin_path = os.path.join(plugins_dir, os.path.basename(plugin_folder))

            # Remove existing folder if already present
            if os.path.exists(final_plugin_path):
                shutil.rmtree(final_plugin_path)

            shutil.move(plugin_folder, final_plugin_path)
            logger.debug(f"Plugin installed: {os.path.basename(final_plugin_path)}")

            # Cleanup: Remove temporary extraction folder
            shutil.rmtree(temp_extraction_path, ignore_errors=True)

            return final_plugin_path

        except zipfile.BadZipFile:
            logger.error("The downloaded file is not a valid ZIP archive")
            return None

    @staticmethod
    def download_plugin_from_github(project_dir: str, plugin_name: str, version: str = None) -> bool:
        """
        Generic function to download any plugin from GitHub release.
        
        Args:
            project_dir: Project directory path
            plugin_name: Plugin configuration name (e.g., 'convai_plugin', 'convai_http_plugin')
            version: Specific version to download, or None for latest
            
        Returns:
            True if successful, False otherwise
        """
        try:
            github_manager = GitHubManager()
            download_dir = os.path.join(project_dir, config.get_essentials_dir_name())
            
            repo = config.get_github_repo(plugin_name)
            asset_patterns = config.get_github_asset_patterns(plugin_name)
            needs_post_process = config.get_github_post_process(plugin_name)
            
            if not repo:
                logger.error(f"{plugin_name} GitHub repository not configured")
                return False
            
            # Download plugin from GitHub
            downloaded_file = github_manager.download_plugin_from_release(
                repo=repo,
                download_dir=download_dir,
                version=version,
                asset_patterns=asset_patterns
            )
            
            if not downloaded_file:
                logger.error(f"Failed to download {plugin_name} from GitHub")
                return False
            
            # Handle content packs vs plugins differently
            if plugin_name == "convai_convenience_pack":
                # Content pack - extract to Content folder
                extracted_path = DownloadManager.extract_content_pack(downloaded_file, project_dir)
                if not extracted_path:
                    logger.error(f"Failed to extract {plugin_name} content pack")
                    return False
            else:
                # Regular plugin - extract to Plugins folder
                extracted_path = DownloadManager.extract_plugin_zip(downloaded_file, project_dir)
                if not extracted_path:
                    logger.error(f"Failed to extract {plugin_name}")
                    return False
            
            # Post-process if needed (Convai-specific modifications)
            if needs_post_process and plugin_name == "convai_plugin":
                if not PluginManager.post_process_convai_plugin(project_dir):
                    logger.warning("Post-processing failed, but plugin was installed")
            
            return True
            
        except Exception as e:
            logger.error(f"Error downloading {plugin_name} from GitHub: {e}")
            return False

    @staticmethod
    def download_modding_dependencies(project_dir):
        """Download all configured plugins from GitHub and Google Drive."""
        
        # Download all configured GitHub plugins
        github_plugins = config.get_github_plugins()
        success_count = 0
        
        for i, plugin_name in enumerate(github_plugins, 1):
            logger.progress(i, len(github_plugins), f"Downloading {plugin_name.replace('_', ' ').title()}")
            if DownloadManager.download_plugin_from_github(project_dir, plugin_name):
                success_count += 1
            else:
                logger.warning(f"Failed to download {plugin_name}")
        
        if success_count == len(github_plugins):
            logger.success(f"Downloaded all {len(github_plugins)} dependencies successfully")
        else:
            logger.warning(f"Downloaded {success_count}/{len(github_plugins)} dependencies")
        
    @staticmethod
    def download_convai_realusion_content(project_dir):
        DownloadManager.download_from_gdrive(config.get_google_drive_id("convai_reallusion_content"), os.path.join(project_dir, config.get_essentials_dir_name()), "ConvaiRealusionContent.zip")
        FileUtilityManager.unzip(os.path.join(project_dir, config.get_essentials_dir_name(), "ConvaiRealusionContent.zip"), os.path.join(project_dir))

    @staticmethod
    def extract_content_pack(zip_path, project_dir):
        """
        Extract a content pack to the project's Content folder.
        
        Args:
            zip_path: Path to the downloaded ZIP file
            project_dir: Project directory path
            
        Returns:
            Path to extracted content or None if extraction failed
        """
        content_dir = os.path.join(project_dir, "Content")
        os.makedirs(content_dir, exist_ok=True)
        
        try:
            logger.debug(f"Extracting content pack to Content folder...")
            FileUtilityManager.unzip(zip_path, content_dir)
            logger.debug("Content pack successfully extracted")
            return content_dir
        except Exception as e:
            logger.error(f"Error extracting content pack: {e}")
            return None