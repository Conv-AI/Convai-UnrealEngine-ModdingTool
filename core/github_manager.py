import requests
import os
import re
import time
from typing import Dict, List, Optional, Tuple

from core.logger import logger

# Release listings are fetched once per repo per process: the availability pre-check and
# the download would otherwise burn two of GitHub's 60 unauthenticated calls per hour.
_releases_cache: Dict[str, List[Dict]] = {}


class GitHubManager:
    """
    Manages GitHub API interactions for downloading releases and assets.
    """
    
    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries
    
    def get_latest_release(self, repo: str) -> Optional[Dict]:
        """
        Get the latest release information from a GitHub repository.
        
        Args:
            repo: Repository in 'owner/repo' format
            
        Returns:
            Release information dict or None if failed
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Fetching latest release from {repo}, attempt {attempt + 1}...")
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                logger.debug(f"Failed to fetch release info (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                    
        return None

    def get_release_by_tag(self, repo: str, tag: str) -> Optional[Dict]:
        """
        Get release information for a specific tag from a GitHub repository.
        
        Args:
            repo: Repository in 'owner/repo' format
            tag: Release tag
            
        Returns:
            Release information dict or None if failed
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Fetching release {tag} from {repo}, attempt {attempt + 1}...")
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                logger.debug(f"Failed to fetch release {tag} (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                    
        return None

    def get_releases(self, repo: str, per_page: int = 100) -> Optional[List[Dict]]:
        """
        List a repository's releases, newest first, prereleases included.

        Args:
            repo: Repository in 'owner/repo' format
            per_page: Number of releases to request

        Returns:
            List of release dicts or None if failed
        """
        cached = _releases_cache.get(repo)
        if cached is not None:
            return cached

        api_url = f"https://api.github.com/repos/{repo}/releases?per_page={per_page}"

        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Listing releases from {repo}, attempt {attempt + 1}...")
                response = requests.get(api_url, timeout=30)
                response.raise_for_status()
                releases = response.json()
                _releases_cache[repo] = releases
                return releases
            except requests.RequestException as e:
                logger.debug(f"Failed to list releases (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)

        return None

    @staticmethod
    def asset_matches_engine(asset_name: str, engine_version: str) -> bool:
        """Whether an asset targets exactly this engine. Substring matching would let
        UE5.1 match Convai-UE5.10.zip."""
        return bool(re.search(rf'ue{re.escape(engine_version)}(?!\d|\.\d)', asset_name, re.I))

    @staticmethod
    def find_matching_asset(assets: List[Dict], patterns: List[str],
                            engine_version: str = None) -> Optional[Dict]:
        """
        Find the first asset that matches any of the given patterns.

        Args:
            assets: List of asset dictionaries from GitHub API
            patterns: List of filename patterns to match
            engine_version: Engine version the asset must be built for, or None for any

        Returns:
            Matching asset dict or None if no match found
        """
        for pattern in patterns:
            for asset in assets:
                asset_name = asset.get('name', '')
                if pattern.lower() not in asset_name.lower():
                    continue
                if engine_version and not GitHubManager.asset_matches_engine(asset_name, engine_version):
                    continue
                return asset
        return None

    @staticmethod
    def resolve_plugin_release(releases: List[Dict], engine_version: str, patterns: List[str],
                               marketplace_prefix: str, version: str = None,
                               asset: str = None) -> Optional[Tuple[Dict, Dict, str]]:
        """
        Pick the release to install from a repository that publishes each version twice:
        a compiled release and a 'marketplace-' prerelease shipping source without binaries.

        Args:
            releases: The repository's releases, newest first
            engine_version: Engine version the asset must be built for
            patterns: Asset filename patterns
            marketplace_prefix: Tag prefix of the source-only releases
            version: Pinned version - the compiled release's tag, never the twin's. The
                pair logic still runs, but only against that version.
            asset: Pinned asset filename, matched exactly. Engine matching is bypassed.

        Returns:
            (release, asset, 'marketplace' | 'compiled') or None if no release has an
            asset for this engine. An override that cannot be satisfied returns None
            rather than falling back to another version (ADR 0002).
        """
        if version and marketplace_prefix and version.startswith(marketplace_prefix):
            logger.error(
                f"Override names the twin tag {version}: pin the version "
                f"{version[len(marketplace_prefix):]}, not the twin tag {version}")
            return None

        def half(tag: str) -> str:
            return 'marketplace' if marketplace_prefix and tag.startswith(marketplace_prefix) else 'compiled'

        if asset:
            # An asset pin reaches one artifact directly: engine matching is bypassed,
            # which is the one thing asset_patterns cannot express.
            for release in releases:
                tag = release.get('tag_name', '')
                if version and tag not in (version, marketplace_prefix + version):
                    continue
                for candidate in release.get('assets', []):
                    if candidate.get('name') == asset:
                        return release, candidate, half(tag)
            where = f"release {version}" if version else "any release"
            logger.error(f"Pinned asset {asset} is not in {where}")
            return None

        marketplace = [r for r in releases if r.get('tag_name', '').startswith(marketplace_prefix)]
        compiled = [r for r in releases
                    if not r.get('tag_name', '').startswith(marketplace_prefix)
                    and not r.get('prerelease', False)]

        if version:
            # A pin is the deliberate override of the default, so it also sees releases
            # the prerelease filter hides from automatic selection.
            marketplace = [r for r in releases if r.get('tag_name') == marketplace_prefix + version]
            compiled = [r for r in releases if r.get('tag_name') == version]
            if not marketplace and not compiled:
                logger.error(f"Pinned version {version} has no release in this repository")
                return None

        def match(release: Dict, pats: List[str]) -> Optional[Dict]:
            return GitHubManager.find_matching_asset(release.get('assets', []), pats, engine_version)

        # Prefer the marketplace twin of the newest compiled release: the two are published
        # together, so that pairing is the version users are meant to be on.
        if compiled:
            twin_tag = marketplace_prefix + compiled[0].get('tag_name', '')
            for release in marketplace:
                if release.get('tag_name') == twin_tag:
                    picked = match(release, patterns)
                    if picked:
                        return release, picked, 'marketplace'
                    break

        for release in marketplace:
            picked = match(release, patterns)
            if picked:
                return release, picked, 'marketplace'

        # No source release for this engine: the compiled one is stripped back to source
        # after install, so both paths end up identical.
        for release in compiled:
            picked = match(release, ['.zip'])
            if picked:
                return release, picked, 'compiled'

        if version:
            logger.error(f"Pinned version {version} has no asset for Unreal Engine {engine_version}")
        return None

    def download_file_from_url(self, url: str, file_path: str, filename: str) -> bool:
        """
        Download a file from a URL with progress tracking and retry logic.
        
        Args:
            url: Download URL
            file_path: Full path where file should be saved
            filename: Name of the file for display purposes
            
        Returns:
            True if successful, False otherwise
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        for attempt in range(self.max_retries):
            try:
                logger.debug(f"Downloading {filename} from GitHub, attempt {attempt + 1}...")
                
                response = requests.get(url, stream=True, timeout=30)
                response.raise_for_status()
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded_size = 0
                
                with open(file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded_size += len(chunk)
                            
                            # Update progress every 10% for large files
                            if total_size > 0:
                                progress = (downloaded_size / total_size) * 100
                                if progress % 10 < 1:  # Show progress every ~10%
                                    logger.debug(f"Progress: {progress:.1f}%")
                
                logger.debug(f"Download complete: {filename}")
                return True
                
            except requests.RequestException as e:
                logger.debug(f"Download failed (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(2)
                else:
                    # Clean up partial file on final failure
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        
        return False

    def download_plugin_from_release(self, repo: str, download_dir: str,
                                   version: str = None, asset_patterns: List[str] = None,
                                   engine_version: str = None,
                                   marketplace_prefix: str = None,
                                   asset: str = None) -> Optional[str]:
        """
        Download a plugin from a GitHub release.

        Args:
            repo: Repository in 'owner/repo' format
            download_dir: Directory to save the downloaded file
            version: Pinned version, or None for latest
            asset_patterns: List of filename patterns to match
            engine_version: Engine version the asset must be built for, or None for any
            marketplace_prefix: Tag prefix of the source-only releases, or None to use
                the latest release as-is
            asset: Pinned asset filename, matched exactly. Engine matching is bypassed.

        Returns:
            Path to downloaded file or None if failed. An override that cannot be
            satisfied fails here rather than installing something else (ADR 0002).
        """
        patterns = asset_patterns or ['.zip']

        if marketplace_prefix:
            releases = self.get_releases(repo)
            if releases is None:
                logger.error(f"Failed to list releases for {repo}")
                return None

            resolved = self.resolve_plugin_release(releases, engine_version, patterns,
                                                   marketplace_prefix, version, asset)
            if not resolved:
                if version or asset:
                    logger.error(f"Override on {repo} could not be satisfied, so nothing was installed")
                else:
                    logger.error(f"No {repo} release has an asset for Unreal Engine {engine_version}")
                logger.debug("Available marketplace tags: " + ", ".join(
                    r.get('tag_name', '') for r in releases
                    if r.get('tag_name', '').startswith(marketplace_prefix)))
                return None

            release_info, selected, source = resolved
            asset_name = selected.get('name')
            logger.info(f"Resolved {repo} {release_info.get('tag_name')} ({source}): {asset_name}")
        else:
            if asset and not version:
                # Nothing names the release holding a pinned filename, and
                # /releases/latest would only ever see one release.
                releases = self.get_releases(repo)
                if releases is None:
                    logger.error(f"Failed to list releases for {repo}")
                    return None
                release_info = next(
                    (r for r in releases
                     if any(a.get('name') == asset for a in r.get('assets', []))), None)
                if not release_info:
                    logger.error(f"Pinned asset {asset} is in no {repo} release")
                    return None
            elif version:
                release_info = self.get_release_by_tag(repo, version)
            else:
                release_info = self.get_latest_release(repo)

            if not release_info:
                logger.error(f"Failed to get release information for {repo}")
                return None

            release_name = release_info.get('name', 'Unknown')
            release_tag = release_info.get('tag_name', 'Unknown')
            logger.debug(f"Found release: {release_name} ({release_tag})")

            assets = release_info.get('assets', [])
            if asset:
                selected = next((a for a in assets if a.get('name') == asset), None)
            else:
                selected = self.find_matching_asset(assets, patterns, engine_version)

            if not selected:
                if asset:
                    logger.error(f"Pinned asset {asset} is not in {repo} {release_tag}")
                elif version:
                    logger.error(f"Pinned version {version} of {repo} has no suitable asset")
                else:
                    logger.error(f"No suitable asset found in release.")
                logger.debug("Available assets:")
                for a in assets:
                    logger.debug(f"  - {a.get('name', 'Unknown')}")
                return None

            asset_name = selected.get('name')
            logger.debug(f"Selected asset: {asset_name}")


        if not selected.get('browser_download_url'):
            logger.error("No download URL found in asset")
            return None
        
        # Download the asset
        file_path = os.path.join(download_dir, asset_name)
        if self.download_file_from_url(selected.get('browser_download_url'), file_path, asset_name):
            return file_path
        else:
            logger.error(f"Failed to download {asset_name}")
            return None 
    
    @staticmethod
    def get_file_content(repo: str, branch: str, file_path: str, max_retries: int = 3) -> Optional[str]:
        """Get file content from GitHub using raw URL to avoid rate limits."""
        raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"

        for attempt in range(max_retries):
            try:
                response = requests.get(raw_url, timeout=30)
                response.raise_for_status()
                return response.text
            except requests.RequestException as e:
                if attempt < max_retries - 1:
                    time.sleep(2)

        return None
