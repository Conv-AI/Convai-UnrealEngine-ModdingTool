import os
import shutil
import subprocess
import time
import zipfile
from typing import Optional

import gdown
import requests

from core.config_manager import config
from core.file_utility_manager import FileUtilityManager
from core.github_manager import GitHubManager
from core.plugin_manager import PluginManager
from core.logger import logger

class DownloadManager:
    
    @staticmethod
    def download_from_gdrive(file_id: str, download_dir: str, filename: str) -> Optional[str]:
        """
        Downloads a file from Google Drive to a specified directory.

        Args:
        - file_id (str): The Google Drive file ID.
        - download_dir (str): The directory where the file will be downloaded.
        - filename (str): The name of the downloaded file.
        
        Returns:
            Path to downloaded file or None if failed.
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
    def extract_plugin_zip(zip_path: str, project_dir: str) -> Optional[str]:
        """
        Extracts a plugin ZIP file to the project's Plugins directory.
        
        Returns:
            Path to extracted plugin or None if extraction failed.
        """
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
    def download_modding_dependencies(project_dir: str, exclude_plugins: list[str] = None) -> None:
        """Download all configured plugins from GitHub and Google Drive.
        
        Args:
            project_dir: Project directory path
            exclude_plugins: List of plugin names to exclude from download (e.g., ['convai_plugin'])
        """
        exclude_plugins = exclude_plugins or []
        
        # Download all configured GitHub plugins (excluding any specified)
        github_plugins = [p for p in config.get_github_plugins() if p not in exclude_plugins]
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
    def download_convai_realusion_content(project_dir: str) -> None:
        DownloadManager.download_from_gdrive(config.get_google_drive_id("convai_reallusion_content"), os.path.join(project_dir, config.get_essentials_dir_name()), "ConvaiRealusionContent.zip")
        FileUtilityManager.unzip(os.path.join(project_dir, config.get_essentials_dir_name(), "ConvaiRealusionContent.zip"), os.path.join(project_dir))

    @staticmethod
    def extract_content_pack(zip_path: str, project_dir: str) -> Optional[str]:
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
    
    @staticmethod
    def is_toolchain_downloaded(ue_version: str) -> tuple[bool, str]:
        """
        Check if the toolchain installer is already downloaded.
        
        Args:
            ue_version: The UE version to check toolchain for
            
        Returns:
            Tuple of (is_downloaded, installer_path)
        """
        from core.config_manager import config
        
        toolchain_version = config.get_cross_compilation_toolchain(ue_version)
        download_directory = config.get_cross_compilation_download_directory()
        
        # Check for downloaded installer in the download directory
        exe_filename = f"{toolchain_version}.exe"
        exe_path = os.path.join(download_directory, exe_filename)
        
        if os.path.exists(exe_path):
            logger.info(f"✅ Found downloaded installer: {exe_path}")
            return True, exe_path
        
        logger.info(f"❌ Installer not found: {exe_path}")
        return False, exe_path
    
    @staticmethod
    def is_toolchain_installed(ue_version: str) -> bool:
        """
        Check if the cross-compilation toolchain for a specific UE version is installed.
        Checks multiple common locations including AppData and system directories.
        
        Args:
            ue_version: The UE version to check toolchain for (e.g., "5.5", "5.6")
            
        Returns:
            True if toolchain is installed, False otherwise
        """
        from core.config_manager import config
        
        toolchain_version = config.get_cross_compilation_toolchain(ue_version)
        
        # Check multiple possible locations
        possible_locations = [
            # 1. Configured system install directory
            config.get_cross_compilation_install_directory(),
            # 2. User directory (fallback installation location)
            config.get_cross_compilation_download_directory().replace("Downloads", "Toolchains"),
            # 3. Legacy C:\UnrealToolchains location
            f"C:\\UnrealToolchains",
            # 4. Unreal Engine's default toolchain location
            f"C:\\UnrealEngine\\Toolchains"
        ]
        
        for base_dir in possible_locations:
            toolchain_path = os.path.join(base_dir, toolchain_version)
            
            if not os.path.exists(toolchain_path):
                logger.info(f"🔍 Toolchain not found at: {toolchain_path}")
                continue
                
            # Check if toolchain directory has expected structure (contains build directory)
            build_path = os.path.join(toolchain_path, "build")
            if not os.path.exists(build_path):
                logger.info(f"🔍 Toolchain build directory not found at: {build_path}")
                continue
                
            logger.info(f"✅ Found toolchain {toolchain_version} at: {toolchain_path}")
            
            # Update environment variable to point to found toolchain
            env_var = config.get_cross_compilation_env_var()
            
            # Always ensure the environment variable points to the correct toolchain for this UE version
            # (The toolchain installer might have set it to a different version)
            expected_toolchain_path = os.path.join(
                config.get_cross_compilation_install_directory(), 
                toolchain_version
            )
            
            DownloadManager._set_environment_variable_permanently(env_var, expected_toolchain_path)
            logger.info(f"🔧 Set {env_var}={expected_toolchain_path}")
            
            return True
            
        logger.info(f"❌ Toolchain {toolchain_version} not found in any location")
        return False
    
    @staticmethod
    def install_toolchain_from_installer(ue_version: str, installer_path: str) -> bool:
        """
        Install toolchain from a downloaded installer executable.
        
        Args:
            ue_version: The UE version to install toolchain for
            installer_path: Path to the downloaded .exe installer
            
        Returns:
            True if installation successful, False otherwise
        """
        from core.config_manager import config
        import ctypes
        import sys
        import subprocess
        import os
        
        try:
            toolchain_version = config.get_cross_compilation_toolchain(ue_version)
            install_directory = config.get_cross_compilation_install_directory()
            toolchain_path = os.path.join(install_directory, toolchain_version)
            
            logger.info(f"🔧 Installing toolchain from: {installer_path}")
            logger.info(f"🔧 Installing to: {toolchain_path}")
            
            # Check if we have admin privileges
            def is_admin():
                try:
                    return ctypes.windll.shell32.IsUserAnAdmin()
                except:
                    return False
            
            if not is_admin():
                logger.warning("⚠️  Admin privileges required for system-wide installation")
                logger.info("🔄 Launching installer - please complete the installation and then press Enter...")
                
                # Use the simplest approach: just launch the exe like double-clicking it
                try:
                    # Launch installer like double-clicking in Windows Explorer
                    logger.info("🎯 Launching installer GUI...")
                    os.startfile(installer_path)
                    
                    # Wait for user to complete installation
                    logger.info("⏸️  Waiting for installation to complete...")
                    print("\n📋 Please complete the installer and press Enter when finished...", end="", flush=True)
                    
                    # Use sys.stdin.readline() as alternative to input()
                    import sys
                    sys.stdin.flush()
                    user_input = sys.stdin.readline()
                    
                    logger.info("🔍 Checking installation results...")
                    
                except Exception as e:
                    logger.error(f"Failed to launch installer: {e}")
                    # Fallback: Try with subprocess.Popen (fire and forget)
                    try:
                        logger.info("🔄 Trying alternative launch method...")
                        subprocess.Popen([installer_path], shell=True)
                        logger.info("⏸️  Waiting for installation to complete...")
                        print("\n📋 Please complete the installer and press Enter when finished...", end="", flush=True)
                        
                        # Use sys.stdin.readline() as alternative to input()
                        import sys
                        sys.stdin.flush()
                        user_input = sys.stdin.readline()
                        
                        logger.info("🔍 Checking installation results...")
                    except Exception as e2:
                        logger.error(f"All launch methods failed: {e2}")
                        return False
            else:
                # We have admin privileges, install normally
                install_command = [installer_path, "/S", f"/D={toolchain_path}"]
                result = subprocess.run(install_command, check=True, capture_output=True, text=True)
                logger.info(f"🔧 Installer completed successfully")
            
            # Verify installation by checking if toolchain directory exists and has build folder
            if os.path.exists(toolchain_path) and os.path.exists(os.path.join(toolchain_path, "build")):
                logger.success(f"Successfully installed toolchain {toolchain_version} for UE {ue_version}")
                
                # Set environment variable to the actual installation path
                env_var = config.get_cross_compilation_env_var()
                
                # Always set to the specific toolchain path for this UE version
                # (The installer might have set it to a generic or different path)
                DownloadManager._set_environment_variable_permanently(env_var, toolchain_path)
                logger.info(f"🔧 Set {env_var}={toolchain_path}")
                
                # Keep the installer for future use (caching)
                logger.info(f"💾 Keeping installer cached at: {installer_path}")
                
                return True
            else:
                logger.error(f"Toolchain installation verification failed - directory or build folder not found")
                return False
                
        except subprocess.CalledProcessError as e:
            logger.error(f"Installation failed: {e}")
            if hasattr(e, 'stderr') and e.stderr:
                logger.error(f"Installer stderr: {e.stderr}")
            return False
        except Exception as e:
            logger.error(f"Failed to install toolchain: {e}")
            return False
    
    @staticmethod
    def download_and_install_toolchain(ue_version: str) -> bool:
        """
        Download and install the cross-compilation toolchain for a specific UE version.
        Uses a 3-step process: Check installed -> Check downloaded -> Download & Install
        
        Args:
            ue_version: The UE version to install toolchain for (e.g., "5.5", "5.6")
            
        Returns:
            True if successful, False otherwise
        """
        from core.config_manager import config
        
        try:
            toolchain_version = config.get_cross_compilation_toolchain(ue_version)
            
            # Step 1: Check if already installed anywhere
            if DownloadManager.is_toolchain_installed(ue_version):
                logger.info(f"✅ Toolchain {toolchain_version} is already installed and configured")
                return True
            
            # Step 2: Check if installer is already downloaded
            is_downloaded, installer_path = DownloadManager.is_toolchain_downloaded(ue_version)
            
            if is_downloaded:
                logger.info(f"📦 Found downloaded installer, proceeding with installation...")
                return DownloadManager.install_toolchain_from_installer(ue_version, installer_path)
            
            # Step 3: Download the installer
            download_url = config.get_cross_compilation_toolchain_url(toolchain_version)
            
            if not download_url:
                logger.error(f"No download URL configured for toolchain {toolchain_version}")
                return False
            
            # Use download directory for the installer
            download_directory = config.get_cross_compilation_download_directory()
            
            # Create download directory if it doesn't exist
            os.makedirs(download_directory, exist_ok=True)
            
            logger.info(f"📥 Downloading toolchain {toolchain_version} for UE {ue_version}...")
            
            # Download the toolchain executable file
            exe_filename = f"{toolchain_version}.exe"
            exe_path = os.path.join(download_directory, exe_filename)
            
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            
            with open(exe_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = (downloaded_size / total_size) * 100
                            print(f"\rDownloading: {progress:.1f}%", end='', flush=True)
            
            print()  # New line after progress
            logger.success(f"Downloaded {exe_filename}")
            
            # Step 4: Install from the downloaded installer
            return DownloadManager.install_toolchain_from_installer(ue_version, exe_path)
                
        except Exception as e:
            logger.error(f"Failed to download/install toolchain: {e}")
            return False
    
    @staticmethod
    def ensure_toolchain_for_version(ue_version: str) -> bool:
        """
        Ensure the correct toolchain is installed for a specific UE version.
        First checks existing installations, then downloads and installs if not present.
        
        Args:
            ue_version: The UE version to ensure toolchain for (e.g., "5.5", "5.6")
            
        Returns:
            True if toolchain is available, False otherwise
        """
        from core.config_manager import config
        import os
        
        toolchain_version = config.get_cross_compilation_toolchain(ue_version)
        logger.info(f"🔍 Ensuring toolchain {toolchain_version} for UE {ue_version}")
        
        if DownloadManager.is_toolchain_installed(ue_version):
            logger.success(f"Toolchain for UE {ue_version} is ready!")
            return True
        
        logger.info(f"📦 Toolchain for UE {ue_version} not found, downloading and installing...")
        return DownloadManager.download_and_install_toolchain(ue_version)
    
    @staticmethod
    def _set_environment_variable_permanently(var_name: str, var_value: str) -> bool:
        """
        Set environment variable permanently in Windows system registry.
        
        Args:
            var_name: Name of the environment variable
            var_value: Value to set
            
        Returns:
            True if successful, False otherwise
        """
        try:
            import winreg
            import ctypes
            
            # Check if we have admin privileges
            def is_admin():
                try:
                    return ctypes.windll.shell32.IsUserAnAdmin()
                except:
                    return False
            
            if is_admin():
                # Set as system environment variable (requires admin)
                try:
                    key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        "SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment",
                        0,
                        winreg.KEY_SET_VALUE
                    )
                    
                    winreg.SetValueEx(key, var_name, 0, winreg.REG_EXPAND_SZ, var_value)
                    winreg.CloseKey(key)
                    logger.info(f"✅ Set {var_name} as system environment variable")
                    
                except Exception as e:
                    logger.error(f"Failed to set system environment variable: {e}")
                    return False
            else:
                # No admin privileges - try to elevate and set system variable
                logger.info(f"🔐 Admin privileges required to set system environment variable")
                logger.info(f"🔄 Attempting to set {var_name} with elevation...")
                
                try:
                    # Use a simpler PowerShell command with proper escaping
                    import subprocess
                    
                    # Build the command as a list to avoid escaping issues
                    ps_command = [
                        "powershell", "-Command",
                        f"Start-Process powershell -ArgumentList '-Command \"Set-ItemProperty -Path ''HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Session Manager\\Environment'' -Name ''{var_name}'' -Value ''{var_value}'' -Type ExpandString\"' -Verb RunAs -Wait"
                    ]
                    
                    result = subprocess.run(ps_command, timeout=60, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        logger.info(f"✅ Set {var_name} as system environment variable with elevation")
                    else:
                        logger.error("Failed to set system environment variable with elevation")
                        return False
                        
                except Exception as e:
                    logger.error(f"Failed to elevate for system environment variable: {e}")
                    return False
            
            # Notify system of environment change
            try:
                # Broadcast WM_SETTINGCHANGE message
                HWND_BROADCAST = 0xFFFF
                WM_SETTINGCHANGE = 0x001A
                SMTO_ABORTIFHUNG = 0x0002
                
                ctypes.windll.user32.SendMessageTimeoutW(
                    HWND_BROADCAST,
                    WM_SETTINGCHANGE,
                    0,
                    "Environment",
                    SMTO_ABORTIFHUNG,
                    5000,
                    None
                )
                logger.debug(f"Broadcasted system environment change for {var_name}")
            except Exception as e:
                logger.debug(f"Failed to broadcast environment change: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to set environment variable: {e}")
            return False
    
    
    # End of DownloadManager class