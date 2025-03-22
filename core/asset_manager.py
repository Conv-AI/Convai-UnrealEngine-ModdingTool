
import base64
import hashlib
import json
import os
import uuid

def get_unique_str():
    """
    Fetch unique string
    """
    return str(uuid.uuid4())

def trim_unique_str(asset_id):
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

def save_metadata(project_dir, field_name, field_value):
    """
    Save or update a key-value pair in ModdingMetaData.txt inside ProjectDir/ConvaiEssentials/.

    Args:
        project_dir (str): Path to the Unreal project directory.
        field_name (str): Key to add or update in the metadata file.
        field_value (Any): Value to assign to the key.
    """
    metadata_dir = os.path.join(project_dir, "ConvaiEssentials")
    os.makedirs(metadata_dir, exist_ok=True)

    metadata_file = os.path.join(metadata_dir, "ModdingMetaData.txt")

    # Load existing metadata if the file exists
    metadata = {}
    if os.path.exists(metadata_file):
        try:
            with open(metadata_file, "r", encoding="utf-8") as file:
                metadata = json.load(file)
        except (json.JSONDecodeError, IOError):
            print("Warning: Existing ModdingMetaData.txt is corrupted or unreadable. Overwriting.")

    # Update/add the field
    metadata[field_name] = field_value

    # Save the updated metadata
    with open(metadata_file, "w", encoding="utf-8") as file:
        json.dump(metadata, file, indent=4)
