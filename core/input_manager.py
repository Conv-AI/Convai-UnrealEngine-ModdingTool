import os
import msvcrt
from pathlib import Path
import re

from core.unreal_engine_manager import UnrealEngineManager

class InputManager:
    """Handles all user input prompts across the Convai Modding Tool."""
    def __init__(self, script_dir: str, default_engine_paths: list[str] = None):
        self.script_dir = Path(script_dir)
        self.default_engine_paths = default_engine_paths or []
        self._existing_projects = None

        # Cached inputs
        self.project_name = None
        self.convai_api_key = None
        self.asset_type = None
        self.is_metahuman = None
        self.unreal_engine_path = None

    def get_script_dir(self) -> str:
        return self.script_dir
    
    def get_user_flow_choice(self) -> str:
        if self._existing_projects is None:
            self._existing_projects = []
            for root, dirs, files in os.walk(self.script_dir):
                if 'ConvaiEssentials' in dirs and any(f.endswith('.uproject') for f in files):
                    self._existing_projects.append(root)
        if not self._existing_projects:
            return 'create'
        while True:
            print('\nWhat do you want to do?')
            print('1. Create a new modding project')
            print('2. Update an existing modding project')
            choice = input('Enter your choice (1 or 2): ').strip()
            if choice == '1':
                return 'create'
            if choice == '2':
                return 'update'
            print('Invalid input. Please enter 1 or 2.')

    def choose_project_dir(self) -> str:
        if self._existing_projects is None:
            self.get_user_flow_choice()
        if not self._existing_projects:
            print(f'❌ No modding projects found under:\n   {self.script_dir}')
            input('Press Enter to exit...')
            exit(1)
        while True:
            print('\nSelect a project to update:')
            for idx, path in enumerate(self._existing_projects, 1):
                print(f'  {idx}. {Path(path).name}')
            choice = input(f'Enter choice [1-{len(self._existing_projects)}]: ').strip()
            try:
                sel = int(choice)
                if 1 <= sel <= len(self._existing_projects):
                    return self._existing_projects[sel - 1]
            except ValueError:
                pass
            print(f"❌ '{choice}' is not valid. Enter a number between 1 and {len(self._existing_projects)}.")

    def get_unreal_engine_path(self) -> str:
        if self.unreal_engine_path:
            return self.unreal_engine_path
        for default in self.default_engine_paths:
            path_obj = Path(default)
            if UnrealEngineManager.is_valid_engine_path(path_obj):
                resp = input(f'Found valid Unreal Engine path: {path_obj}\nUse this? (Y/N): ').strip().lower()
                if resp in ('', 'y', 'yes'):
                    self.unreal_engine_path = str(path_obj)
                    return self.unreal_engine_path
        while True:
            user_input = input('Enter the Unreal Engine 5.3 installation directory: ').strip()
            engine_path = Path(user_input)
            if UnrealEngineManager.is_valid_engine_path(engine_path):
                print(f'Using Unreal Engine path: {engine_path}')
                self.unreal_engine_path = str(engine_path)
                return self.unreal_engine_path
            print('Invalid path. Please enter a valid Unreal Engine 5.3 directory.')

    def get_project_name(self) -> str:
        if self.project_name:
            return self.project_name
        
        root = self.script_dir
        name_pattern = re.compile(r"^[a-zA-Z0-9_]{1,20}$")  

        while True:
            name = input('Enter the Project Name : ').strip()
            
            # Check if the name is empty
            if not name:
                print("Error: Project name cannot be empty. Please enter a valid project name.")
                continue
            
            # Check if the name exceeds 20 characters
            if len(name) > 20:
                print("Error: Project name must not exceed 20 characters. Please try again.")
                continue
            
            # Check if the name starts with a digit
            if name[0].isdigit():
                print("Error: Project name cannot start with a digit. Please try again.")
                continue
            
            # Check for invalid characters (only letters, digits, and underscores allowed)
            if not name_pattern.match(name):
                print("Error: Project name can only contain letters, digits, and underscores (no spaces or special characters).")
                continue
            
            # Check if the project name already exists
            if (root / name).exists():
                print(f"Error: A project named '{name}' already exists. Please choose a different name.")
                continue
            
            self.project_name = name
            return name

    def get_api_key(self) -> str:
        if self.convai_api_key:
            return self.convai_api_key
        print('Enter the Convai API key: ', end='', flush=True)
        key = ''
        while True:
            ch = msvcrt.getch()
            if ch in {b'\r', b'\n'}:
                print()
                if key and key.isalnum():
                    self.convai_api_key = key
                    return key
                print('Invalid API key. Please enter a valid alphanumeric key.')
                return self.get_api_key()
            if ch == b'\x08':
                if key:
                    key = key[:-1]
                    print('\b \b', end='', flush=True)
            elif ch == b'\x03':
                raise KeyboardInterrupt
            else:
                char = ch.decode(errors='ignore')
                if char.isalnum():
                    key += char
                    print('*', end='', flush=True)

    def get_asset_type(self) -> tuple[str, bool]:
        if self.asset_type and self.is_metahuman is not None:
            return self.asset_type, self.is_metahuman
        while True:
            print('Select the type of asset you want to create:')
            print('1. Scene')
            print('2. Avatar')
            choice = input('Enter your choice (1 or 2): ').strip()
            if choice == '1':
                self.asset_type, self.is_metahuman = 'Scene', False
                return self.asset_type, self.is_metahuman
            if choice == '2':
                while True:
                    meta = input('Are you using a MetaHuman for your avatar? (y/n): ').strip().lower()
                    if meta in ('y', 'yes'):
                        self.asset_type, self.is_metahuman = 'Avatar', True
                        return self.asset_type, self.is_metahuman
                    if meta in ('n', 'no'):
                        self.asset_type, self.is_metahuman = 'Avatar', False
                        return self.asset_type, self.is_metahuman
                    print('Invalid input. Please enter y or n.')
            print('Invalid input. Please enter 1 or 2.')
