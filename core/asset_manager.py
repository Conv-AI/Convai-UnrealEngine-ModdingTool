
import base64
import hashlib
import json
import os
import requests

def get_asset_id(URL):
    """
    Fetch the asset ID from the server.
    """
    try:
        response = requests.get(URL)
        response.raise_for_status()
        asset_id = response.json().get("project_name")  # The original response field

        if not asset_id:
            raise ValueError("Invalid response from server: No project_name field found.")

        return asset_id

    except requests.RequestException as e:
        print(f"Error fetching asset ID: {e}")
        return None

def generate_project_name(asset_id):
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


def save_asset_metadata(project_dir, asset_id):
    """Save the asset ID to PakMetaData.txt inside ProjectDir/ConvaiEssentials/."""
    metadata_dir = os.path.join(project_dir, "ConvaiEssentials")
    os.makedirs(metadata_dir, exist_ok=True)

    metadata_file = os.path.join(metadata_dir, "PakMetaData.txt")
    with open(metadata_file, "w", encoding="utf-8") as file:
        json.dump({"asset_id": asset_id}, file, indent=4)
