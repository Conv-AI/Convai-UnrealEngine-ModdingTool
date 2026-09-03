# core/self_VersionManager.py
import json
from typing import Optional

from core.github_manager import GitHubManager
from core.logger import logger

REPO = "Conv-AI/Convai-UnrealEngine-ModdingTool"
BRANCH = "main"
VERSION_JSON_PATH = "Version.json"
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

        raw = GitHubManager.get_file_content(REPO, BRANCH, VERSION_JSON_PATH)
        if not raw:
            logger.info("Could not fetch Version.json")
            logger.info(f"Download the latest version here: {LATEST_RELEASE_URL}")
            return None

        try:
            data = json.loads(raw)
            remote_version = data.get("modding-tool-version", "").strip()
        except Exception:
            logger.info("Invalid Version.json")
            logger.info(f"Download the latest version here: {LATEST_RELEASE_URL}")
            return None

        logger.info(f"Current version: {current_version}")
        logger.info(f"Latest version:  {remote_version or 'unknown'}")

        if not remote_version:
            logger.info("Version.json carries no modding-tool-version")
            return None

        if current_version == remote_version:
            logger.success("Modding tool is up to date.")
            return True

        logger.step("Newer version detected")
        logger.info(f"Download the latest version here: {LATEST_RELEASE_URL}")
        return False
