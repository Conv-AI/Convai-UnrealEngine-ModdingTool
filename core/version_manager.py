# core/self_VersionManager.py
import json
import sys
import webbrowser

from core.github_manager import GitHubManager
from core.logger import logger

REPO = "Conv-AI/Convai-UnrealEngine-ModdingTool"
BRANCH = "main"
VERSION_JSON_PATH = "Version.json"
LATEST_RELEASE_URL = "https://github.com/Conv-AI/Convai-UnrealEngine-ModdingTool/releases/latest"

class VersionManager:
    @staticmethod
    def check_version(current_version: str) -> bool:
        """
        Compare local version with Version.json on GitHub.
        Returns:
            True  -> tool is up to date
            False -> tool is outdated (user should update)
        """
        logger.section("Updater")
        logger.step("Checking for updates...")

        raw = GitHubManager.get_file_content(REPO, BRANCH, VERSION_JSON_PATH)
        if not raw:
            logger.info("Could not fetch Version.json")
            VersionManager._prompt_open_download_page("Could not fetch Version.json.")
            return False

        try:
            data = json.loads(raw)
            remote_version = data.get("modding-tool-version", "").strip()
        except Exception:
            logger.info("Invalid Version.json")
            VersionManager._prompt_open_download_page("Invalid Version.json.")
            return False

        logger.info(f"Current version: {current_version}")
        logger.info(f"Latest version:  {remote_version or 'unknown'}")

        if current_version == remote_version:
            logger.success("Modding tool is up to date.")
            return True

        logger.step("Newer version detected")
        VersionManager._prompt_open_download_page("Your version is outdated. Please update to continue.")
        return False

    @staticmethod
    def _prompt_open_download_page(reason: str) -> None:
        """
        Ask user if they want to open the download page.
        """
        print(f"\n[UPDATE REQUIRED] {reason}\n", file=sys.stderr)

        if sys.stdin and sys.stdin.isatty():
            choice = input("Do you want to open the download page now? [y/n]: ").strip().lower()
            if choice in ("y", "yes"):
                try:
                    webbrowser.open(LATEST_RELEASE_URL, new=2)
                    print("Opening download page in your browser...")
                except Exception:
                    print(f"Could not open browser. Please visit:\n{LATEST_RELEASE_URL}")
            else:
                print(f"You can manually download it from:\n{LATEST_RELEASE_URL}")
        else:
            # No interactive input (e.g., double-click execution)
            print(f"Please download the latest version here:\n{LATEST_RELEASE_URL}")