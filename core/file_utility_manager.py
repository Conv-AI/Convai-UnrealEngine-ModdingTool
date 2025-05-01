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
import logging

# Configure logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

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
        except zipfile.BadZipFile as e:
            logger.error(f"Failed to unzip {source_path} (bad zip): {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during unzip of {source_path}: {e}")
            raise
        finally:
            logger.info(f"Unzip attempted: {source_path} -> {dest_path}")

    @staticmethod
    def copy_file_to_directory(src: str, dst_dir: str) -> None:
        """
        Copies a file into a target directory, creating the directory if needed.
        """
        try:
            os.makedirs(dst_dir, exist_ok=True)
            shutil.copy(src, dst_dir)
        except Exception as e:
            logger.error(f"Failed to copy {src} to {dst_dir}: {e}")
            raise
        finally:
            logger.info(f"Copy attempted: {src} -> {dst_dir}")

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
    def write_metadata(metadata_path: str, data: dict) -> None:
        """
        Writes a JSON file at `metadata_path` containing `data`.
        """
        try:
            os.makedirs(os.path.dirname(metadata_path), exist_ok=True)
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to write metadata to {metadata_path}: {e}")
            raise
        finally:
            logger.info(f"write_metadata attempted at {metadata_path}")

    @staticmethod
    def read_metadata(metadata_path: str) -> dict:
        """
        Reads and returns JSON data from `metadata_path`, or {} if missing or invalid.
        """
        try:
            if not os.path.isfile(metadata_path):
                return {}
            with open(metadata_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error reading {metadata_path}: {e}")
            return {}
        except Exception as e:
            logger.error(f"Error reading metadata from {metadata_path}: {e}")
            raise
        finally:
            logger.info(f"read_metadata attempted at {metadata_path}")

    @staticmethod
    def delete_directory_if_exists(directory_path):
        """
        Deletes the specified directory if it exists.
        """
        if os.path.exists(directory_path) and os.path.isdir(directory_path):
            try:
                shutil.rmtree(directory_path)
                print(f"Deleted directory: {directory_path}")
            except Exception as e:
                print(f"Failed to delete {directory_path}: {e}")

    @staticmethod
    def remove_metahuman_folder(project_dir: str) -> None:
        """
        Deletes the 'MetaHumans' folder under the given project directory, if it exists.
        """
        plugins_dir = Path(project_dir) / "Plugins"
    
        for plugin_path in plugins_dir.glob("*/ConvAI.uplugin"):
            plugin_root = plugin_path.parent  
            metahuman_dir = plugin_root / "Content" / "MetaHumans"
            FileUtilityManager.delete_directory_if_exists(metahuman_dir)
            break 
    
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
                    print(f"Deleted file: {file_path}")
                except OSError as e:
                    print(f"❌ Error deleting file {file_path}: {e}")
            else:
                print(f"⚠️ Warning: Path exists but is not a file: {file_path}")
        else:
            print(f"⚠️ Warning: File not found: {file_path}")
        
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
                    print(f"⚠️ Warning: Path does not exist or unknown type: {matched_path}")

    @staticmethod 
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

        new_content = FileUtilityManager.case_preserving_replace(old_value, new_value, content)
        if content != new_content:
            try:
                with open(file_path, 'w', encoding='utf-8') as file:
                    file.write(new_content)
                #print(f"Updated '{old_value}' to '{new_value}' in {file_path}")
            except IOError:
                print(f"Error writing to file: {file_path}")
    
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
                #print(f"Renamed file: {file_path} -> {new_file_path}")
            #else:
                #print(f"File already exists: {new_file_path}")
    
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
                #print(f"Renamed directory: {directory} -> {new_dir_path}")
                return new_dir_path  # Return the new directory path for further operations
            #else:
            #print(f"Directory already exists: {new_dir_path}")

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

            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                FileUtilityManager.rename_directory(dir_path, old_value, new_value)
    
    @staticmethod 
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
