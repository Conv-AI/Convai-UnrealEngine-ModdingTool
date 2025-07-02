import os
import zipfile
import shutil
import requests
import time
import gdown
import json
import re

from core.config_manager import config
from core.file_utility_manager import FileUtilityManager
from core.github_manager import GitHubManager

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
        file_id = config.get_google_drive_id("convai_pak_manager_plugin")
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
    def _find_convai_plugin_directory(project_dir: str) -> str:
        """
        Find the Convai plugin directory in the project plugins folder.
        
        Args:
            project_dir: Project directory path
            
        Returns:
            Path to Convai plugin directory or None if not found
        """
        plugins_dir = os.path.join(project_dir, "Plugins")
        
        if not os.path.exists(plugins_dir):
            return None
        
        # Look for ConvAI plugin directory (case variations)
        for item in os.listdir(plugins_dir):
            item_path = os.path.join(plugins_dir, item)
            if os.path.isdir(item_path):
                # Check if this directory contains ConvAI.uplugin
                uplugin_file = os.path.join(item_path, "ConvAI.uplugin")
                if os.path.exists(uplugin_file):
                    return item_path
        
        return None

    @staticmethod
    def _remove_engine_version_from_uplugin(uplugin_file_path: str) -> bool:
        """
        Remove EngineVersion key from ConvAI.uplugin file.
        
        Args:
            uplugin_file_path: Path to the ConvAI.uplugin file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"🔧 Removing EngineVersion from {uplugin_file_path}")
            
            # Read the JSON file
            with open(uplugin_file_path, 'r', encoding='utf-8') as f:
                plugin_data = json.load(f)
            
            # Remove EngineVersion if it exists
            if 'EngineVersion' in plugin_data:
                del plugin_data['EngineVersion']
                print("✅ Removed EngineVersion key")
            else:
                print("ℹ️ EngineVersion key not found (already removed)")
            
            # Write back the modified JSON
            with open(uplugin_file_path, 'w', encoding='utf-8') as f:
                json.dump(plugin_data, f, indent=4)
            
            return True
            
        except json.JSONDecodeError as e:
            print(f"❌ Error: Invalid JSON in uplugin file: {e}")
            return False
        except Exception as e:
            print(f"❌ Error modifying uplugin file: {e}")
            return False

    @staticmethod
    def _update_convai_build_file(build_file_path: str) -> bool:
        """
        Update Convai.Build.cs to set bEnableConvaiHTTP = true and bUsePrecompiled = false.
        
        Args:
            build_file_path: Path to the Convai.Build.cs file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            print(f"🔧 Updating build settings in {build_file_path}")
            
            # Read the build file
            with open(build_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            modified = False
            
            # 1. Update bEnableConvaiHTTP = true
            pattern_convai_http = r'const\s+bool\s+bEnableConvaiHTTP\s*=\s*(true|false)\s*;'
            replacement_convai_http = 'const bool bEnableConvaiHTTP = true;'
            
            if re.search(pattern_convai_http, content):
                content = re.sub(pattern_convai_http, replacement_convai_http, content)
                print("✅ Set bEnableConvaiHTTP = true")
                modified = True
            else:
                print("⚠️ Warning: bEnableConvaiHTTP declaration not found in build file")
            
            # 2. Update bUsePrecompiled = false
            pattern_precompiled = r'bUsePrecompiled\s*=\s*(true|false)\s*;'
            replacement_precompiled = 'bUsePrecompiled = false;'
            
            if re.search(pattern_precompiled, content):
                content = re.sub(pattern_precompiled, replacement_precompiled, content)
                print("✅ Set bUsePrecompiled = false")
                modified = True
            else:
                print("⚠️ Warning: bUsePrecompiled assignment not found in build file")
            
            # Write back the modified content if any changes were made
            if modified:
                with open(build_file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True
            else:
                print("⚠️ Warning: No build settings were modified")
                return False
                
        except Exception as e:
            print(f"❌ Error modifying build file: {e}")
            return False

    @staticmethod
    def _post_process_convai_plugin(project_dir: str) -> bool:
        """
        Post-process the Convai plugin after extraction.
        
        Args:
            project_dir: Project directory path
            
        Returns:
            True if successful, False otherwise
        """
        print("🔄 Post-processing Convai plugin...")
        
        # Find Convai plugin directory
        convai_plugin_dir = DownloadManager._find_convai_plugin_directory(project_dir)
        if not convai_plugin_dir:
            print("❌ Error: Could not find Convai plugin directory")
            return False
        
        print(f"📁 Found Convai plugin at: {convai_plugin_dir}")
        
        # 1. Remove EngineVersion from ConvAI.uplugin
        uplugin_file = os.path.join(convai_plugin_dir, "ConvAI.uplugin")
        if os.path.exists(uplugin_file):
            if not DownloadManager._remove_engine_version_from_uplugin(uplugin_file):
                print("⚠️ Warning: Failed to modify uplugin file")
        else:
            print(f"⚠️ Warning: ConvAI.uplugin not found at {uplugin_file}")
        
        # 2. Update Convai.Build.cs
        build_file = os.path.join(convai_plugin_dir, "Source", "Convai", "Convai.Build.cs")
        if os.path.exists(build_file):
            if not DownloadManager._update_convai_build_file(build_file):
                print("⚠️ Warning: Failed to modify build file")
        else:
            print(f"⚠️ Warning: Convai.Build.cs not found at {build_file}")
        
        print("✅ Convai plugin post-processing completed")
        return True

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
            download_dir = os.path.join(project_dir, "ConvaiEssentials")
            
            repo = config.get_github_repo(plugin_name)
            asset_patterns = config.get_github_asset_patterns(plugin_name)
            needs_post_process = config.get_github_post_process(plugin_name)
            
            if not repo:
                print(f"❌ Error: {plugin_name} GitHub repository not configured")
                return False
            
            print(f"📦 Downloading {plugin_name} from GitHub: {repo}")
            
            # Download plugin from GitHub
            downloaded_file = github_manager.download_plugin_from_release(
                repo=repo,
                download_dir=download_dir,
                version=version,
                asset_patterns=asset_patterns
            )
            
            if not downloaded_file:
                print(f"❌ Error: Failed to download {plugin_name} from GitHub")
                return False
            
            # Handle content packs vs plugins differently
            if plugin_name == "convai_convenience_pack":
                # Content pack - extract to Content folder
                extracted_path = DownloadManager.extract_content_pack(downloaded_file, project_dir)
                if not extracted_path:
                    print(f"❌ Error: Failed to extract {plugin_name} content pack")
                    return False
            else:
                # Regular plugin - extract to Plugins folder
                extracted_path = DownloadManager.extract_plugin_zip(downloaded_file, project_dir)
                if not extracted_path:
                    print(f"❌ Error: Failed to extract {plugin_name}")
                    return False
            
            # Post-process if needed (Convai-specific modifications)
            if needs_post_process and plugin_name == "convai_plugin":
                if not DownloadManager._post_process_convai_plugin(project_dir):
                    print("⚠️ Warning: Post-processing failed, but plugin was installed")
            
            print(f"✅ Successfully downloaded and installed {plugin_name} from GitHub")
            return True
            
        except Exception as e:
            print(f"❌ Error downloading {plugin_name} from GitHub: {e}")
            return False

    @staticmethod
    def download_modding_dependencies(project_dir):
        """Download all configured plugins from GitHub and Google Drive."""
        
        # Download all configured GitHub plugins
        github_plugins = config.get_github_plugins()
        github_success = True
        
        for plugin_name in github_plugins:
            print(f"📦 Downloading {plugin_name} from GitHub...")
            if not DownloadManager.download_plugin_from_github(project_dir, plugin_name):
                print(f"⚠️ Warning: Failed to download {plugin_name} from GitHub")
                github_success = False
        
        if github_success and github_plugins:
            print(f"✅ Successfully downloaded {len(github_plugins)} plugins from GitHub")
        
    @staticmethod
    def download_convai_realusion_content(project_dir):
        DownloadManager.download_from_gdrive(config.get_google_drive_id("convai_reallusion_content"), os.path.join(project_dir, "ConvaiEssentials"), "ConvaiRealusionContent.zip")
        FileUtilityManager.unzip(os.path.join(project_dir, "ConvaiEssentials", "ConvaiRealusionContent.zip"), os.path.join(project_dir))

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
            print(f"📦 Extracting content pack {zip_path} to {content_dir}...")
            FileUtilityManager.unzip(zip_path, content_dir)
            print(f"✅ Content pack successfully extracted to: {content_dir}")
            return content_dir
        except Exception as e:
            print(f"❌ Error extracting content pack: {e}")
            return None