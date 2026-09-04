import base64
import glob
import hashlib
import json
import os
import re
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile
from typing import Any, Dict, List, Optional

from core.config_manager import config
from core.exceptions import ConfigurationError
from core.logger import logger

# The Pak Manager numbers a project's first Chunk 10, so a project this tool sets up lands
# on the same id the plugin would have minted.
DEFAULT_CHUNK_ID = 10


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
    def copy_directory(src: str, dst: str) -> bool:
        """
        Copies an entire directory tree to a new location.
        
        Args:
            src (str): Source directory path
            dst (str): Destination directory path
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            if os.path.exists(dst):
                logger.error(f"Destination directory already exists: {dst}")
                return False
            
            shutil.copytree(src, dst)
            logger.success(f"Successfully copied directory: {os.path.basename(src)} -> {os.path.basename(dst)}")
            return True
        except Exception as e:
            logger.error(f"Failed to copy directory {src} to {dst}: {e}")
            return False

    @staticmethod
    def generate_unique_str() -> str:
        """
        Returns a short UUID-based string for naming collisions.
        """
        return str(uuid.uuid4())

    @staticmethod
    def trim_unique_str(value: str) -> str:
        """
        Generate a 20-character Unreal Engine-compatible project name from the asset ID.
        Ensures that the name starts with a letter (A-Z).
        """
        hash_object = hashlib.sha256(value.encode())  # Hash the asset ID
        base32_encoded = base64.b32encode(hash_object.digest()).decode()  # Base32 encoding (A-Z, 2-7)
        project_name = base32_encoded[:20]  # Truncate to 20 characters

        # Ensure first character is a letter (A-Z)
        if project_name[0].isdigit():
            project_name = "A" + project_name[1:]  # Replace the first character with 'A'

        return project_name

    @staticmethod
    def delete_directory_if_exists(directory_path: str) -> None:
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
    def delete_file_if_exists(file_path: str) -> None:
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
    def delete_paths(paths_to_delete: List[str]) -> None:
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
    def update_file_content(file_path: str, old_value: str, new_value: str) -> None:
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
    def rename_file(file_path: str, old_value: str, new_value: str) -> None:
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
    def rename_directory(directory: str, old_value: str, new_value: str) -> str:
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
    def is_text_file(file_path: str) -> bool:
        """
        Check if the file is a text file based on its extension.
        """
        text_extensions = {".cpp", ".h", ".cs", ".ini", ".uproject"}
        return os.path.splitext(file_path)[1].lower() in text_extensions
    
    @staticmethod 
    def update_directory_structure(directory: str, old_value: str, new_value: str) -> None:
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
    def case_preserving_replace(old_value: str, new_value: str, text: str) -> str:
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
    def find_metadata_file(project_dir: str) -> Optional[str]:
        """
        The metadata file the Pak Manager would read, or None when the project has none.

        The plugin migrates the flat file into its Chunk and reads per-chunk first, so this
        resolves in the plugin's order. The chunk id is whatever the project's Primary Asset
        Label declares, so it is globbed rather than assumed.
        """
        essentials_dir = os.path.join(project_dir, config.get_essentials_dir_name())
        stem = os.path.splitext(config.get_metadata_file_name())[0]

        # glob.escape: a project path may contain [ or ], which are glob wildcards.
        chunks = os.path.join(glob.escape(essentials_dir), 'ChunkId_*')
        for extension in ('.json', '.txt'):
            # sorted() only to keep the pick deterministic if a project breaks the
            # one-chunk-per-project rule; the plugin reads a single chunk either way.
            found = sorted(glob.glob(os.path.join(chunks, f"{stem}_*{extension}")))
            if found:
                return found[0]

        flat = os.path.join(essentials_dir, config.get_metadata_file_name())
        return flat if os.path.exists(flat) else None

    @staticmethod
    def save_metadata(project_dir: str, metadata: Dict[str, Any]) -> None:
        """
        Save metadata to the project's Chunk, creating ChunkId_10 when there is none.
        Merges with existing metadata if present (new data takes precedence).

        A project that still carries the flat file is written in place: the plugin migrates
        it into the Chunk itself, and it knows the chunk id this tool would have to guess.
        """
        metadata_file = FileUtilityManager.find_metadata_file(project_dir)
        if metadata_file is None:
            metadata_file = os.path.join(
                project_dir, config.get_essentials_dir_name(),
                f"ChunkId_{DEFAULT_CHUNK_ID}",
                f"{os.path.splitext(config.get_metadata_file_name())[0]}_{DEFAULT_CHUNK_ID}.json")

        os.makedirs(os.path.dirname(metadata_file), exist_ok=True)

        # Merge with existing data if present
        existing_data = {}
        if os.path.exists(metadata_file):
            try:
                with open(metadata_file, "r", encoding="utf-8") as file:
                    existing_data = json.load(file)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Existing metadata corrupted, will overwrite")
            except Exception as e:
                logger.error(f"Failed to read existing metadata: {e}")
        
        # Merge new data into existing (new data takes precedence)
        existing_data.update(metadata)
        
        try:
            with open(metadata_file, "w", encoding="utf-8") as file:
                json.dump(existing_data, file, indent=4)
            logger.info(f"Metadata saved to {metadata_file}")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    @staticmethod
    def get_metadata(project_dir: str) -> Dict[str, Any]:
        """
        Get metadata from the project's Chunk, falling back to the flat legacy file.
        Returns a dictionary with the metadata, or an empty dict if file doesn't exist or can't be read.
        """
        metadata_file = FileUtilityManager.find_metadata_file(project_dir)

        # Debug information
        logger.debug(f"Looking for metadata file at: {metadata_file}")

        if metadata_file is None:
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
            bool: True if configuration is valid
            
        Raises:
            ConfigurationError: If prerequisite is not met
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
                logger.warning("UBT configuration has missing or incorrect settings. Attempting auto-fix...")
                if FileUtilityManager.ensure_ubt_configuration_correct():
                    # Re-validate after auto-fix
                    config_dict = FileUtilityManager.read_ubt_build_configuration()
                    missing_or_incorrect = []
                    for setting_name, expected_value in required_settings.items():
                        actual_value = config_dict.get(setting_name, '').lower()
                        if actual_value != expected_value.lower():
                            missing_or_incorrect.append((setting_name, expected_value))
                    if not missing_or_incorrect:
                        logger.success("UBT configuration auto-fix applied successfully")
                        return True
                # If auto-fix failed, guide user
                logger.error("PREREQUISITE NOT MET: Failed to auto-fix UBT configuration. Please ensure the following settings exist:")
                for setting_name, expected_value in required_settings.items():
                    logger.error(f"  - {setting_name} = {expected_value}")
                logger.error("Expected BuildConfiguration.xml template:")
                FileUtilityManager._log_ubt_xml_template(required_settings)
                logger.error(f"File location: {os.environ.get('APPDATA')}/{config.get_ubt_config_appdata_path()}")
                raise ConfigurationError("Tool cannot continue without proper UBT configuration")
            
            return True
            
        except FileNotFoundError:
            logger.warning("BuildConfiguration.xml not found. Attempting to create it...")
            if FileUtilityManager.ensure_ubt_configuration_correct():
                logger.success("Created default UBT BuildConfiguration.xml")
                return True
            logger.error("PREREQUISITE NOT MET: Could not create BuildConfiguration.xml automatically")
            logger.error(f"Please create BuildConfiguration.xml in {os.environ.get('APPDATA')}/{config.get_ubt_config_appdata_path()} with the following content:")
            FileUtilityManager._log_ubt_xml_template(config.get_ubt_required_settings())
            raise ConfigurationError("Tool cannot continue without proper UBT configuration")
        except ConfigurationError:
            raise
        except Exception as e:
            logger.error(f"Failed to validate UBT configuration: {e}")
            raise ConfigurationError(f"Tool cannot continue due to UBT configuration validation error: {e}")
    
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

    @staticmethod
    def _get_ubt_full_path() -> str:
        """
        Resolve the full path to %APPDATA%/.../BuildConfiguration.xml from config.
        """
        appdata_path = os.environ.get('APPDATA')
        if not appdata_path:
            raise EnvironmentError("APPDATA environment variable not found")
        return os.path.join(appdata_path, config.get_ubt_config_appdata_path())

    @staticmethod
    def ensure_ubt_configuration_correct() -> bool:
        """
        Ensure BuildConfiguration.xml exists and contains required settings with expected values.
        Non-destructively creates or updates only the needed elements under BuildConfiguration.
        """
        required_settings = config.get_ubt_required_settings()
        return FileUtilityManager.update_ubt_build_configuration_settings(required_settings)

    @staticmethod
    def update_ubt_build_configuration_settings(settings: Dict[str, str]) -> bool:
        """
        Update or create BuildConfiguration.xml, preserving existing content and adding/updating
        only the provided settings inside the BuildConfiguration element under the root Configuration.
        """
        try:
            full_path = FileUtilityManager._get_ubt_full_path()
            directory = os.path.dirname(full_path)
            os.makedirs(directory, exist_ok=True)

            # Try to load existing XML; if not present, create minimal structure
            root = None
            namespace = None
            root_element_name = config.get_ubt_xml_root_element()
            config_element_name = config.get_ubt_xml_config_element()
            expected_namespace = config.get_ubt_xml_namespace()

            if os.path.exists(full_path):
                try:
                    tree = ET.parse(full_path)
                    root = tree.getroot()
                    if root.tag.startswith('{'):
                        namespace = root.tag[root.tag.find('{')+1:root.tag.find('}')]
                except Exception:
                    root = None  # Fall back to creating a new tree

            if root is None:
                # Create new root with default namespace
                ET.register_namespace('', expected_namespace)
                root = ET.Element(f"{{{expected_namespace}}}{root_element_name}")
                namespace = expected_namespace
                tree = ET.ElementTree(root)
            else:
                # Ensure namespace registration to avoid ns0 prefixes on write
                if namespace:
                    ET.register_namespace('', namespace)
                else:
                    # If no namespace, still register expected to keep tags clean if we add new ones
                    ET.register_namespace('', expected_namespace)

            # Helper to build qualified names
            def qname(name: str) -> str:
                ns = namespace if namespace else None
                return f"{{{ns}}}{name}" if ns else name

            # Find or create BuildConfiguration element
            build_config = root.find(qname(config_element_name))
            if build_config is None:
                build_config = ET.SubElement(root, qname(config_element_name))

            # For each desired setting, add or update element text
            for key, value in settings.items():
                child = build_config.find(qname(key))
                if child is None:
                    child = ET.SubElement(build_config, qname(key))
                child.text = str(value)

            # Write back to disk
            tree.write(full_path, encoding='utf-8', xml_declaration=True)
            logger.debug(f"Updated UBT configuration (non-destructive) at: {full_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to update UBT BuildConfiguration.xml: {e}")
            return False
    
    @staticmethod
    def validate_migration_requirements(original_project_name: str, original_project_dir: str) -> tuple[bool, str, str]:
        """
        Validate requirements for project migration.

        Compares the *project's own* engine version (read from its .uproject
        EngineAssociation) against the configured target UE version — NOT the
        config's current-vs-target, which are equal on a single-version config
        and would wrongly report "no migration needed".

        Args:
            original_project_name: Name of the project to migrate
            original_project_dir: Path to the project directory (holds the .uproject)

        Returns:
            Tuple of (is_valid, project_ue_version, target_ue_version)
        """
        if not original_project_name:
            logger.error("Project name not found in metadata. This project may not have been created with the modding tool.")
            return False, "", ""

        logger.step("Getting target Unreal Engine version...")
        target_ue_version = config.get_target_unreal_engine_version()

        # Read the project's actual engine version from its .uproject.
        project_ue_version = None
        uproject_file = os.path.join(original_project_dir, f"{original_project_name}.uproject")
        if os.path.exists(uproject_file):
            try:
                with open(uproject_file, 'r', encoding='utf-8') as f:
                    project_ue_version = json.load(f).get('EngineAssociation')
            except Exception as e:
                logger.warning(f"Could not read project engine version from {uproject_file}: {e}")
        else:
            logger.warning(f".uproject not found: {uproject_file}")

        logger.info(f"Project UE version: {project_ue_version or 'unknown'}")
        logger.info(f"Target UE version: {target_ue_version}")

        # EngineAssociation is a GUID for source-built engines; treat anything
        # that isn't a plain "major.minor" as unknown and proceed with migration.
        is_plain_version = bool(project_ue_version and re.fullmatch(r"\d+\.\d+", project_ue_version))

        if is_plain_version and project_ue_version == target_ue_version:
            logger.info(f"Project is already using the target UE version ({target_ue_version})")
            logger.success("No migration needed! Project is already using the target UE version.")
            return False, project_ue_version, target_ue_version

        if not is_plain_version:
            logger.warning("Could not determine a plain project UE version; proceeding with migration.")

        return True, project_ue_version or "unknown", target_ue_version
    
    @staticmethod
    def create_migrated_project_copy(original_project_dir: str, original_project_name: str, target_ue_version: str, script_dir: str) -> tuple[bool, str, str]:
        """
        Create a copy of the project for migration.
        
        Args:
            original_project_dir: Path to original project
            original_project_name: Name of the original project
            target_ue_version: Target UE version
            script_dir: Script directory path
            
        Returns:
            Tuple of (success, migrated_directory_name, migrated_project_dir)
        """
        import os
        
        # Create the copied directory with naming format OriginalProjectName_TargetUEVersion
        migrated_directory_name = f"{original_project_name}_{target_ue_version}"
        migrated_project_dir = os.path.join(script_dir, migrated_directory_name)
        
        logger.step(f"Creating copy of project for migration: {migrated_directory_name}")
        if not FileUtilityManager.copy_directory(original_project_dir, migrated_project_dir):
            logger.error("Failed to create project copy for migration")
            return False, "", ""
        
        return True, migrated_directory_name, migrated_project_dir

    @staticmethod
    def patch_target_files(uproject_file: str) -> bool:
        """
        Patch Target.cs files to use latest build settings and include order.
        This ensures compatibility when building projects created with older UE versions.

        Updates:
            - DefaultBuildSettings = BuildSettingsVersion.V* -> BuildSettingsVersion.Latest
            - IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_* -> EngineIncludeOrderVersion.Latest

        Returns:
            True if any files were patched, False otherwise
        """
        # Get the project's Source directory
        project_dir = os.path.dirname(uproject_file)
        source_dir = os.path.join(project_dir, "Source")

        if not os.path.exists(source_dir):
            logger.warning(f"Source directory not found: {source_dir}")
            return False

        patched_count = 0

        # Find all Target.cs files
        for root, _, files in os.walk(source_dir):
            for file_name in files:
                if file_name.endswith(".Target.cs"):
                    target_file = os.path.join(root, file_name)
                    try:
                        with open(target_file, 'r', encoding='utf-8') as f:
                            content = f.read()

                        original_content = content

                        # Replace DefaultBuildSettings = BuildSettingsVersion.V* with Latest
                        content = re.sub(
                            r'DefaultBuildSettings\s*=\s*BuildSettingsVersion\.\w+',
                            'DefaultBuildSettings = BuildSettingsVersion.Latest',
                            content
                        )

                        # Replace IncludeOrderVersion = EngineIncludeOrderVersion.Unreal5_* with Latest
                        content = re.sub(
                            r'IncludeOrderVersion\s*=\s*EngineIncludeOrderVersion\.\w+',
                            'IncludeOrderVersion = EngineIncludeOrderVersion.Latest',
                            content
                        )

                        if content != original_content:
                            with open(target_file, 'w', encoding='utf-8') as f:
                                f.write(content)
                            logger.info(f"Patched Target.cs file: {file_name}")
                            patched_count += 1

                    except Exception as e:
                        logger.warning(f"Failed to patch {target_file}: {str(e)}")

        if patched_count > 0:
            logger.info(f"Patched {patched_count} Target.cs file(s) to use latest build settings")
        else:
            logger.info("No Target.cs files needed patching")

        return patched_count > 0
