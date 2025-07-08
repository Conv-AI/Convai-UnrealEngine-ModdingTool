import base64
import glob
import hashlib
import os
from pathlib import Path
import re
import shutil
import json
import uuid
import zipfile
import subprocess
import xml.etree.ElementTree as ET
from typing import Dict, Any

from core.logger import logger
from core.config_manager import config

class FileUtilityManager:
    """Utility methods for filesystem and metadata operations."""

    @staticmethod
    def unzip(source_path: str, dest_path: str) -> None:
        """
        Extracts a zip archive to the given destination directory.
        """
        try:
            with zipfile.ZipFile(source_path, 'r') as zip_ref:
                zip_ref.extractall(dest_path)
            logger.debug(f"Extracted archive: {os.path.basename(source_path)}")
        except zipfile.BadZipFile as e:
            logger.error(f"Failed to unzip {source_path} (bad zip): {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during unzip of {source_path}: {e}")
            raise

    @staticmethod
    def copy_file_to_directory(src: str, dst_dir: str) -> None:
        """
        Copies a file into a target directory, creating the directory if needed.
        """
        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy(src, dst_dir)
            logger.debug(f"Copied file: {os.path.basename(src)}")
        except Exception as e:
            logger.error(f"Failed to copy {src} to {dst_dir}: {e}")
            raise

    @staticmethod
    def generate_unique_str() -> str:
        """
        Returns a short UUID-based string for naming collisions.
        """
        return str(uuid.uuid4())

    @staticmethod
    def trim_unique_str(str: str) -> str:
        """
        Generate a 20-character Unreal Engine-compatible project name from the asset ID.
        Ensures that the name starts with a letter (A-Z).
        """
        hash_object = hashlib.sha256(str.encode())  # Hash the asset ID
        base32_encoded = base64.b32encode(hash_object.digest()).decode()  # Base32 encoding (A-Z, 2-7)
        project_name = base32_encoded[:20]  # Truncate to 20 characters

        # Ensure first character is a letter (A-Z)
        if project_name[0].isdigit():
            project_name = "A" + project_name[1:]  # Replace the first character with 'A'

        return project_name

    @staticmethod
    def delete_directory_if_exists(directory_path):
        """
        Deletes the specified directory if it exists.
        """
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            try:
                shutil.rmtree(directory_path)
                logger.debug(f"Deleted directory: {os.path.basename(directory_path)}")
            except Exception as e:
                logger.error(f"Failed to delete directory {directory_path}: {e}")

    @staticmethod 
    def delete_file_if_exists(file_path):
        """
        Deletes a file if it exists.

        Args:
            file_path (str): Path to the file to delete.
        """
        if os.path.exists(file_path):
            if os.path.isfile(file_path):
                try:
                    os.remove(file_path)
                    logger.debug(f"Deleted file: {os.path.basename(file_path)}")
                except OSError as e:
                    logger.error(f"Error deleting file {file_path}: {e}")
            else:
                logger.warning(f"Path exists but is not a file: {file_path}")
        else:
            logger.debug(f"File not found (already deleted): {file_path}")
        
    @staticmethod 
    def delete_paths(paths_to_delete):
        """Delete files or directories based on their type."""
        for path_pattern in paths_to_delete:
            for matched_path in glob.glob(path_pattern):
                if os.path.isfile(matched_path):
                    FileUtilityManager.delete_file_if_exists(matched_path)
                elif os.path.isdir(matched_path):
                    FileUtilityManager.delete_directory_if_exists(matched_path)
                else:
                    logger.warning(f"Path does not exist or unknown type: {matched_path}")

    @staticmethod 
    def update_file_content(file_path, old_value, new_value):
        """
        Replace old_value with new_value in the specified file, preserving case sensitivity.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
        except (UnicodeDecodeError, IOError):
            logger.debug(f"Skipping file due to read error: {file_path}")
            return

        new_content = FileUtilityManager.case_preserving_replace(old_value, new_value, content)
        if content != new_content:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                logger.debug(f"Updated content in {os.path.basename(file_path)}")
            except IOError:
                logger.error(f"Error writing to file: {file_path}")
    
    @staticmethod 
    def rename_file(file_path, old_value, new_value):
        """
        Rename the file if old_value is part of the file name, preserving case.
        """
        directory, file_name = os.path.split(file_path)
        if old_value.lower() in file_name.lower():
            new_file_name = FileUtilityManager.case_preserving_replace(old_value, new_value, file_name)
            new_file_path = os.path.join(directory, new_file_name)
            if not os.path.exists(new_file_path):
                os.rename(file_path, new_file_path)
                logger.debug(f"Renamed file: {file_name} -> {new_file_name}")
    
    @staticmethod 
    def rename_directory(directory, old_value, new_value):
        """
        Rename directories that contain old_value in their names.
        """
        parent_dir = os.path.dirname(directory)
        dir_name = os.path.basename(directory)

        if old_value.lower() in dir_name.lower():
            new_dir_name = FileUtilityManager.case_preserving_replace(old_value, new_value, dir_name)
            new_dir_path = os.path.join(parent_dir, new_dir_name)

            if not os.path.exists(new_dir_path):
                os.rename(directory, new_dir_path)
                logger.debug(f"Renamed directory: {dir_name} -> {new_dir_name}")
                return new_dir_path  # Return the new directory path for further operations

        return directory  # Return the original directory if no renaming occurred
    
    @staticmethod 
    def is_text_file(file_path):
        """
        Check if the file is a text file based on its extension.
        """
        text_extensions = {".cpp", ".h", ".cs", ".ini", ".uproject"}
        return os.path.splitext(file_path)[1].lower() in text_extensions
    
    @staticmethod 
    def update_directory_structure(directory, old_value, new_value):
        """
        Recursively replace old_value with new_value in files and rename directories.
        """
        for root, dirs, files in os.walk(directory, topdown=False):  # Traverse bottom-up for directory renaming
            for file_name in files:
                file_path = os.path.join(root, file_name)
                if FileUtilityManager.is_text_file(file_path):
                    FileUtilityManager.update_file_content(file_path, old_value, new_value)
                FileUtilityManager.rename_file(file_path, old_value, new_value)

            # Rename directories
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                FileUtilityManager.rename_directory(dir_path, old_value, new_value)
    
    @staticmethod 
    def case_preserving_replace(old_value, new_value, text):
        """
        Replace old_value with new_value in the text, preserving the case of the original.
        """
        # Define a function to replace with matching case
        def replace_with_matching_case(match):
            original = match.group(0)
            if original.isupper():
                return new_value.upper()
            elif original.islower():
                return new_value.lower()
            elif original.istitle():
                return new_value.title()
            else:
                return new_value

        # Use re.sub with re.IGNORECASE for case-insensitive matching
        return re.sub(re.escape(old_value), replace_with_matching_case, text, flags=re.IGNORECASE)

    @staticmethod
    def save_metadata(project_dir, metadata):
        """
        Save metadata to ModdingMetaData.txt in the project directory.
        """
        essentials_dir = os.path.join(project_dir, config.get_essentials_dir_name())
        metadata_file = os.path.join(essentials_dir, config.get_metadata_file_name())
        
        # Ensure ConvaiEssentials directory exists
        if not os.path.exists(essentials_dir):
            os.makedirs(essentials_dir)
        
        try:
            with open(metadata_file, "w", encoding="utf-8") as file:
                json.dump(metadata, file, indent=4)
            logger.info(f"Metadata saved to {metadata_file}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

        # For backward compatibility, also check if ModdingMetaData.txt already exists and attempt to read it first
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as file:
                    existing_data = json.load(file)
                # Merge new data with existing data (new data takes precedence)
                existing_data.update(metadata)
                with open(metadata_file, "w", encoding="utf-8") as file:
                    json.dump(existing_data, file, indent=4)
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                logger.warning("Existing metadata file is corrupted or unreadable. Overwriting.")
                with open(metadata_file, "w", encoding="utf-8") as file:
                    json.dump(metadata, file, indent=4)
            except Exception as e:
                logger.error(f"Unexpected error handling metadata: {e}")

    @staticmethod 
    def get_metadata(project_dir):
        """
        Get metadata from ModdingMetaData.txt in the project directory.
        Returns a dictionary with the metadata, or an empty dict if file doesn't exist or can't be read.
        """
        essentials_dir = os.path.join(project_dir, config.get_essentials_dir_name())
        metadata_file = os.path.join(essentials_dir, config.get_metadata_file_name())
        
        # Debug information
        logger.debug(f"Looking for metadata file at: {metadata_file}")
        
        if not os.path.exists(metadata_file):
            logger.warning("Metadata file not found. This may be a legacy project")
            return {}
        
        try:
            with open(metadata_file, "r", encoding="utf-8") as file:
                metadata = json.load(file)
                logger.debug(f"Successfully loaded metadata with keys: {list(metadata.keys())}")
                return metadata
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to load metadata from {metadata_file}. Returning empty metadata")
            return {}
        except Exception as e:
            logger.error(f"Unexpected error reading metadata: {e}")
            return {}

    @staticmethod
    def read_appdata_file(file_path: str) -> str:
        """
        Read a file from the user's AppData/Roaming directory.
        
        Args:
            file_path (str): Relative path from %APPDATA% directory
            
        Returns:
            str: File content as string
            
        Raises:
            FileNotFoundError: If the file doesn't exist
            PermissionError: If the file can't be read
            UnicodeDecodeError: If the file contains invalid UTF-8
        """
        appdata_path = os.environ.get('APPDATA')
        if not appdata_path:
            raise EnvironmentError("APPDATA environment variable not found")
        
        full_path = os.path.join(appdata_path, file_path)
        
        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {full_path}")
        
        try:
            with open(full_path, 'r', encoding='utf-8') as file:
                content = file.read()
            logger.debug(f"Successfully read file: {full_path}")
            return content
        except PermissionError:
            logger.error(f"Permission denied reading file: {full_path}")
            raise
        except UnicodeDecodeError:
            logger.error(f"Invalid UTF-8 encoding in file: {full_path}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading file {full_path}: {e}")
            raise

    @staticmethod
    def read_ubt_build_configuration() -> Dict[str, Any]:
        """
        Read and parse the Unreal Build Tool configuration file.
        
        Returns:
            Dict[str, Any]: Parsed configuration as a dictionary
            
        Raises:
            FileNotFoundError: If BuildConfiguration.xml doesn't exist
            Exception: If XML parsing fails
        """
        config_path = config.get_ubt_config_appdata_path()
        
        try:
            xml_content = FileUtilityManager.read_appdata_file(config_path)
            
            # Parse the XML content
            root = ET.fromstring(xml_content)
            
            # Handle namespace if present
            namespace = ''
            expected_namespace = config.get_ubt_xml_namespace()
            if root.tag.startswith('{'):
                namespace = root.tag[root.tag.find("{")+1:root.tag.find("}")]
            
            # Convert XML to dictionary for easier access
            config_dict = {}
            
            # Look for BuildConfiguration element within the root Configuration
            config_element_name = config.get_ubt_xml_config_element()
            build_config_element = root.find(f'.//{config_element_name}' if not namespace else f'.//{{{namespace}}}{config_element_name}')
            
            if build_config_element is not None:
                # Extract all child elements of BuildConfiguration
                for elem in build_config_element:
                    # Remove namespace from tag name for cleaner keys
                    tag_name = elem.tag
                    if namespace and tag_name.startswith(f'{{{namespace}}}'):
                        tag_name = tag_name.replace(f'{{{namespace}}}', '')
                    
                    if elem.text and elem.text.strip():
                        config_dict[tag_name] = elem.text.strip()
            else:
                # Fallback: look for direct children of root (for simpler XML structures)
                for elem in root:
                    tag_name = elem.tag
                    if namespace and tag_name.startswith(f'{{{namespace}}}'):
                        tag_name = tag_name.replace(f'{{{namespace}}}', '')
                    
                    if elem.text and elem.text.strip():
                        config_dict[tag_name] = elem.text.strip()
            
            logger.debug(f"Successfully parsed UBT configuration with {len(config_dict)} settings")
            return config_dict
            
        except FileNotFoundError:
            logger.error(f"BuildConfiguration.xml not found in AppData. Expected location: %APPDATA%/{config_path}")
            raise
        except ET.ParseError as e:
            logger.error(f"Failed to parse BuildConfiguration.xml: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error reading UBT configuration: {e}")
            raise

    @staticmethod
    def validate_ubt_configuration() -> bool:
        """
        Validate that the UBT configuration has the required settings.
        Checks all required settings defined in the configuration.
        
        Returns:
            bool: True if configuration is valid, False otherwise
            
        Raises:
            SystemExit: If prerequisite is not met
        """
        try:
            config_dict = FileUtilityManager.read_ubt_build_configuration()
            required_settings = config.get_ubt_required_settings()
            
            # Check all required settings
            missing_or_incorrect = []
            for setting_name, expected_value in required_settings.items():
                actual_value = config_dict.get(setting_name, '').lower()
                expected_value_lower = expected_value.lower()
                
                if actual_value != expected_value_lower:
                    missing_or_incorrect.append((setting_name, expected_value))
            
            if missing_or_incorrect:
                logger.error("PREREQUISITE NOT MET: UBT configuration has missing or incorrect settings:")
                for setting_name, expected_value in missing_or_incorrect:
                    logger.error(f"  - {setting_name} must be set to '{expected_value}'")
                
                logger.error("Please add the following to your BuildConfiguration.xml file:")
                FileUtilityManager._log_ubt_xml_template(required_settings)
                logger.error(f"File location: %APPDATA%/{config.get_ubt_config_appdata_path()}")
                raise SystemExit("Tool cannot continue without proper UBT configuration")
            
            return True
            
        except FileNotFoundError:
            logger.error("PREREQUISITE NOT MET: BuildConfiguration.xml not found")
            logger.error(f"Please create BuildConfiguration.xml in %APPDATA%/{config.get_ubt_config_appdata_path()} with the following content:")
            FileUtilityManager._log_ubt_xml_template(config.get_ubt_required_settings())
            raise SystemExit("Tool cannot continue without proper UBT configuration")
        except Exception as e:
            logger.error(f"Failed to validate UBT configuration: {e}")
            raise SystemExit("Tool cannot continue due to UBT configuration validation error")
    
    @staticmethod
    def _log_ubt_xml_template(settings: Dict[str, str]):
        """
        Log the UBT XML template with the given settings.
        
        Args:
            settings: Dictionary of setting names and their values
        """
        namespace = config.get_ubt_xml_namespace()
        root_element = config.get_ubt_xml_root_element()
        config_element = config.get_ubt_xml_config_element()
        
        logger.error("<?xml version=\"1.0\" encoding=\"utf-8\"?>")
        logger.error(f"<{root_element} xmlns=\"{namespace}\">")
        logger.error(f"    <{config_element}>")
        
        for setting_name, value in settings.items():
            logger.error(f"        <{setting_name}>{value}</{setting_name}>")
        
        logger.error(f"    </{config_element}>")
        logger.error(f"</{root_element}>")