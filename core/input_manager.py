import os
import msvcrt
from pathlib import Path

from core.unreal_engine_manager import UnrealEngineManager

class InputManager:
    """Handles all user input prompts across the Convai Modding Tool."""

    @staticmethod
    def get_asset_type():
        """
        Prompts the user to choose between Scene (1) or Avatar (2).
        Returns:
            tuple: (asset_type: str, is_metahuman: bool)
        """
        while True:
            print("Select the type of asset you want to create:")
            print("1. Scene")
            print("2. Avatar")
            choice = input("Enter your choice (1 or 2): ").strip()

            if choice == "1":
                return "Scene", False

            elif choice == "2":
                while True:
                    meta_input = input("Are you using a MetaHuman for your avatar? (y/n): ").strip().lower()
                    if meta_input in ("y", "yes"):
                        return "Avatar", True
                    elif meta_input in ("n", "no"):
                        return "Avatar", False
                    else:
                        print("Invalid input. Please enter 'y' or 'n'.")

            else:
                print("Invalid input. Please enter 1 or 2.")

    @staticmethod
    def get_api_key():
        """
        Prompts the user to enter the Convai API key, masking input.
        Returns:
            str: The entered API key.
        """
        print("Enter the Convai API key: ", end="", flush=True)
        key = ""
        while True:
            ch = msvcrt.getch()
            # Enter key finishes input
            if ch in {b'\r', b'\n'}:
                print()
                if key and key.isalnum():
                    return key
                else:
                    print("Invalid API key. Please enter a valid alphanumeric key.")
                    return InputManager.get_api_key()

            # Handle backspace
            elif ch == b'\x08':
                if key:
                    key = key[:-1]
                    print('\b \b', end='', flush=True)

            # Ctrl+C
            elif ch == b'\x03':
                raise KeyboardInterrupt

            else:
                char = ch.decode(errors='ignore')
                if char.isalnum():
                    key += char
                    print('*', end='', flush=True)

    @staticmethod
    def get_user_flow_choice(script_dir):
        """
        Prompts the user to choose between creating a new project or updating an existing one.
        Returns:
            str: "create" or "update"
        """
        existing_projects = []
        for root, dirs, files in os.walk(script_dir):
            if "ConvaiEssentials" in dirs and any(f.endswith(".uproject") for f in files):
                existing_projects.append(root)

        if not existing_projects:
            return "create"

        while True:
            print("\nWhat do you want to do?")
            print("1. Create a new modding project")
            print("2. Update an existing modding project")
            choice = input("Enter your choice (1 or 2): ").strip()

            if choice == "1":
                return "create"
            elif choice == "2":
                return "update"
            else:
                print("Invalid input. Please enter 1 or 2.")

    @staticmethod
    def get_project_name(project_root_dir):
        """
        Prompts for or retrieves a valid project name
        (not starting with a digit, and not already existing).
        Returns:
            str: A validated project name.
        """
        root_dir = Path(project_root_dir)
        while True:
            name = input("Enter the Project Name: ").strip()
            if name and not name[0].isdigit() and not (root_dir / name).exists():
                return name
            print("Enter a valid project name")

    @staticmethod
    def get_unreal_engine_path(default_paths=None):
        """
        Retrieves and validates the Unreal Engine installation directory.
        Returns:
            str: A valid Unreal Engine 5.3 path.
        """
        if default_paths is None:
            default_paths = []
        elif isinstance(default_paths, str):
            default_paths = [default_paths]

        for default_path in default_paths:
            path_obj = Path(default_path)
            if UnrealEngineManager.is_valid_engine_path(path_obj):
                response = input(f"Found valid Unreal Engine path: {path_obj}\nDo you want to use this path? (Y/N): ").strip().lower()
                if response in ("", "y", "yes"):
                    return str(path_obj)

        while True:
            user_input = input("Enter the Unreal Engine 5.3 installation directory: ").strip()
            engine_path = Path(user_input)
            if UnrealEngineManager.is_valid_engine_path(engine_path):
                print(f"Using Unreal Engine path: {engine_path}")
                return str(engine_path)
            else:
                print("Invalid path. Please enter a valid Unreal Engine 5.3 directory.")

    @staticmethod
    def choose_project_dir(script_dir):
        """
        Prompts the user to select an existing modding project to update.
        Returns:
            str: Path to the selected project directory.
        """
        candidate_dirs = []
        for root, dirs, files in os.walk(script_dir):
            if "ConvaiEssentials" in dirs and any(f.endswith(".uproject") for f in files):
                candidate_dirs.append(root)

        if not candidate_dirs:
            print(f"❌ No modding projects found under:\n   {script_dir}")
            input("Press Enter to exit...")
            exit(1)

        while True:
            print("\nSelect a project to update:")
            for idx, path in enumerate(candidate_dirs, 1):
                print(f"  {idx}. {os.path.basename(path)}")
            choice = input(f"\nEnter choice [1-{len(candidate_dirs)}]: ").strip()
            try:
                sel = int(choice)
                if 1 <= sel <= len(candidate_dirs):
                    return candidate_dirs[sel - 1]
            except ValueError:
                pass
            print(f"❌ '{choice}' is not valid. Enter a number between 1 and {len(candidate_dirs)}.")
