import os
import json
import re
from typing import Optional

class PluginManager:
    """Manages plugin-specific operations like post-processing and configuration."""
    
    @staticmethod
    def find_plugin_directory(project_dir: str, uplugin_filename: str) -> Optional[str]:
        """
        Find a plugin directory by looking for the specified .uplugin file.
        
        Args:
            project_dir: Project directory path
            uplugin_filename: Name of the .uplugin file to search for (e.g., "ConvAI.uplugin")
            
        Returns:
            Path to the plugin directory containing the .uplugin file, or None if not found
        """
        plugins_dir = os.path.join(project_dir, "Plugins")
        
        if not os.path.exists(plugins_dir):
            return None
        
        # Look for plugin directory containing the specified .uplugin file
        for item in os.listdir(plugins_dir):
            item_path = os.path.join(plugins_dir, item)
            if os.path.isdir(item_path):
                uplugin_file = os.path.join(item_path, uplugin_filename)
                if os.path.exists(uplugin_file):
                    plugin_name = uplugin_filename.replace('.uplugin', '')
                    print(f"📁 Found {plugin_name} plugin at: {item_path}")
                    return item_path
        
        return None

    @staticmethod
    def remove_engine_version_from_uplugin(uplugin_file_path: str) -> bool:
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
    def update_convai_build_file(build_file_path: str) -> bool:
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
    def post_process_convai_plugin(project_dir: str) -> bool:
        """
        Post-process the Convai plugin after extraction.
        
        Args:
            project_dir: Project directory path
            
        Returns:
            True if successful, False otherwise
        """
        print("🔄 Post-processing Convai plugin...")
        
        # Find Convai plugin directory
        convai_plugin_dir = PluginManager.find_plugin_directory(project_dir, "ConvAI.uplugin")
        if not convai_plugin_dir:
            print("❌ Error: Could not find Convai plugin directory")
            return False
        
        print(f"📁 Found Convai plugin at: {convai_plugin_dir}")
        
        # 1. Remove EngineVersion from ConvAI.uplugin
        uplugin_file = os.path.join(convai_plugin_dir, "ConvAI.uplugin")
        if os.path.exists(uplugin_file):
            if not PluginManager.remove_engine_version_from_uplugin(uplugin_file):
                print("⚠️ Warning: Failed to modify uplugin file")
        else:
            print(f"⚠️ Warning: ConvAI.uplugin not found at {uplugin_file}")
        
        # 2. Update Convai.Build.cs
        build_file = os.path.join(convai_plugin_dir, "Source", "Convai", "Convai.Build.cs")
        if os.path.exists(build_file):
            if not PluginManager.update_convai_build_file(build_file):
                print("⚠️ Warning: Failed to modify build file")
        else:
            print(f"⚠️ Warning: Convai.Build.cs not found at {build_file}")
        
        print("✅ Convai plugin post-processing completed")
        return True 