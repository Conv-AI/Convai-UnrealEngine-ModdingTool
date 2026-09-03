import os
import json
import re
import shutil
from typing import Optional, Tuple

from core.config_manager import config
from core.logger import logger

# The declaration is spelled BEnableConvaiHttp in V4 and bEnableConvaiHTTP in V3, so the
# match is case-insensitive and the replacement keeps whatever spelling it found: renaming
# the declaration alone would leave the use sites pointing at a symbol that no longer exists.
HTTP_FLAG_PATTERN = r'(const\s+bool\s+bEnableConvaiHttp\s*=\s*)(?:true|false)\s*;'


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
        plugins_dir = os.path.join(project_dir, config.get_plugins_dir_name())
        
        if not os.path.exists(plugins_dir):
            return None
        
        # Look for plugin directory containing the specified .uplugin file
        for item in os.listdir(plugins_dir):
            item_path = os.path.join(plugins_dir, item)
            if os.path.isdir(item_path):
                uplugin_file = os.path.join(item_path, uplugin_filename)
                if os.path.exists(uplugin_file):
                    plugin_name = uplugin_filename.replace('.uplugin', '')
                    logger.debug(f"Found {plugin_name} plugin directory")
                    return item_path
        
        return None

    @staticmethod
    def clean_uplugin(uplugin_file_path: str) -> bool:
        """
        Strip EngineVersion and Installed from ConvAI.uplugin.

        EngineVersion is dropped because migrate installs the plugin under the current
        engine and only then bumps the copy to the target one. Installed: true is what
        makes UBT skip compiling the plugin from source.

        Args:
            uplugin_file_path: Path to the ConvAI.uplugin file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(uplugin_file_path, 'r', encoding='utf-8') as f:
                plugin_data = json.load(f)

            for key in ('EngineVersion', 'Installed'):
                if plugin_data.pop(key, None) is not None:
                    logger.debug(f"Removed {key} key from plugin descriptor")

            with open(uplugin_file_path, 'w', encoding='utf-8') as f:
                json.dump(plugin_data, f, indent=4)

            return True

        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in uplugin file: {e}")
            return False
        except Exception as e:
            logger.error(f"Error modifying uplugin file: {e}")
            return False

    @staticmethod
    def strip_precompiled(plugin_dir: str) -> bool:
        """Remove shipped build output so UBT compiles the plugin from source."""
        for name in ("Binaries", "Intermediate"):
            path = os.path.join(plugin_dir, name)
            if not os.path.exists(path):
                continue
            shutil.rmtree(path, ignore_errors=True)
            # A locked .dll leaves the tree behind on Windows and UBT then links the
            # shipped build instead of compiling.
            if os.path.exists(path):
                logger.error(f"Could not remove precompiled {name} from the Convai plugin")
                return False
            logger.info(f"Removed precompiled {name} from the Convai plugin")
        return True

    @staticmethod
    def set_convai_http_enabled(content: str) -> Tuple[str, int]:
        """Turn on the ConvaiHTTP compile flag, returning (content, substitutions)."""
        return re.subn(HTTP_FLAG_PATTERN, r'\1true;', content, flags=re.IGNORECASE)

    @staticmethod
    def update_convai_build_file(build_file_path: str) -> bool:
        """
        Update Convai.Build.cs to compile with ConvaiHTTP enabled.

        Args:
            build_file_path: Path to the Convai.Build.cs file

        Returns:
            True if successful, False otherwise
        """
        try:
            with open(build_file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            content, count = PluginManager.set_convai_http_enabled(content)
            if count == 0:
                logger.error("bEnableConvaiHttp declaration not found in build file")
                return False

            with open(build_file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            logger.debug("Enabled ConvaiHTTP in build file")
            return True

        except Exception as e:
            logger.error(f"Error modifying build file: {e}")
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
        logger.debug("Post-processing Convai plugin...")
        
        # Find Convai plugin directory
        convai_plugin_file = config.get_plugin_file_name("convai")
        convai_plugin_dir = PluginManager.find_plugin_directory(project_dir, convai_plugin_file)
        if not convai_plugin_dir:
            logger.error("Could not find Convai plugin directory")
            return False
        
        # 1. Force a source build, whether the zip was the marketplace or the compiled one.
        # Surviving Binaries and a surviving "Installed": true each make UBT reuse the
        # shipped build, which compiles ConvaiHTTP out again however step 2 goes.
        if not PluginManager.strip_precompiled(convai_plugin_dir):
            return False

        uplugin_file = os.path.join(convai_plugin_dir, convai_plugin_file)
        if not PluginManager.clean_uplugin(uplugin_file):
            logger.error(f"Failed to modify {convai_plugin_file}")
            return False

        # 2. Update Convai.Build.cs. A miss here silently compiles ConvaiHTTP out, so it
        # fails the run rather than warning after a ten-minute build.
        build_file = os.path.join(convai_plugin_dir, "Source", "Convai", config.get_build_file_name())
        if not os.path.exists(build_file):
            logger.error("Convai.Build.cs not found in plugin directory")
            return False

        if not PluginManager.update_convai_build_file(build_file):
            return False

        logger.debug("Convai plugin post-processing completed")
        return True