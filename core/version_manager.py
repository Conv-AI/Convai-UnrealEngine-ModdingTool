# core/self_VersionManager.py
from typing import Optional

from core.config_manager import config
from core.logger import logger

LATEST_RELEASE_URL = "https://github.com/Conv-AI/Convai-UnrealEngine-ModdingTool/releases/latest"

class VersionManager:
    @staticmethod
    def check_version(current_version: str) -> Optional[bool]:
        """
        Compare local version with Version.json on GitHub.
        Returns:
            True  -> tool is up to date
            False -> tool is outdated (user should update)
            None  -> the check could not be made (unreachable or unreadable Version.json)

        A None is not a False: telling a user their build is outdated because GitHub was
        unreachable sends them to a download page that would have changed nothing.
        """
        logger.section("Updater")
        logger.step("Checking for updates...")

        # Read the Version.json the config already loaded, not a second copy off main:
        # that load is the one that honours CONVAI_MODDING_CONFIG_DIR, so a separate
        # fetch here would compare a local checkout against main and call it up to date.
        version_data = config.remote_config.version_data
        remote_version = str(version_data.get("modding-tool-version", "")).strip()

        logger.info(f"Current version: {current_version}")
        logger.info(f"Latest version:  {remote_version or 'unknown'}")

        if not remote_version:
            logger.info("Version.json is unreadable or carries no modding-tool-version")
            logger.info(f"Download the latest version here: {LATEST_RELEASE_URL}")
            return None

        if current_version == remote_version:
            logger.success("Modding tool is up to date.")
            return True

        logger.step("Newer version detected")
        logger.info(f"Download the latest version here: {LATEST_RELEASE_URL}")
        return False
