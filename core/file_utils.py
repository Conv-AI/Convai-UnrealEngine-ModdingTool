import os
import re
import shutil

from core.asset_manager import get_asset_type_from_user

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

def remove_metahuman_if_scene(project_dir, asset_type):
    """
    If user selects Scene, removes the MetaHuman folder from Convai plugin content.

    Args:
        unreal_engine_path (str): The path to the Unreal Engine installation.
    """
    if asset_type == "Scene":
        metahuman_dir = os.path.join(project_dir, "Plugins", "Convai-UnrealEngine-SDK-Dev", "Content", "MetaHumans")
        delete_directory_if_exists(metahuman_dir)
