import json
import requests
import os
import time
from typing import Dict, List, Optional

from core.config_manager import config
from core.logger import logger

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

    def find_matching_asset(self, assets: List[Dict], patterns: List[str]) -> Optional[Dict]:
        """
        Find the first asset that matches any of the given patterns.
        
        Args:
            assets: List of asset dictionaries from GitHub API
            patterns: List of filename patterns to match
            
        Returns:
            Matching asset dict or None if no match found
        """
        for pattern in patterns:
            for asset in assets:
                asset_name = asset.get('name', '')
                if pattern.lower() in asset_name.lower():
                    return asset
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
                                   version: str = None, asset_patterns: List[str] = None) -> Optional[str]:
        """
        Download a plugin from a GitHub release.
        
        Args:
            repo: Repository in 'owner/repo' format
            download_dir: Directory to save the downloaded file
            version: Specific version tag, or None for latest
            asset_patterns: List of filename patterns to match
            
        Returns:
            Path to downloaded file or None if failed
        """
        # Get release information
        if version:
            release_info = self.get_release_by_tag(repo, version)
        else:
            release_info = self.get_latest_release(repo)
        
        if not release_info:
            logger.error(f"Failed to get release information for {repo}")
            return None
        
        release_name = release_info.get('name', 'Unknown')
        release_tag = release_info.get('tag_name', 'Unknown')
        logger.debug(f"Found release: {release_name} ({release_tag})")
        
        # Find matching asset
        assets = release_info.get('assets', [])
        asset = self.find_matching_asset(assets, asset_patterns or ['.zip'])
        
        if not asset:
            logger.error(f"No suitable asset found in release.")
            logger.debug("Available assets:")
            for a in assets:
                logger.debug(f"  - {a.get('name', 'Unknown')}")
            return None
        
        asset_name = asset.get('name')
        logger.debug(f"Selected asset: {asset_name}")
        
        if not asset.get('browser_download_url'):
            logger.error("No download URL found in asset")
            return None
        
        # Download the asset
        file_path = os.path.join(download_dir, asset_name)
        if self.download_file_from_url(asset.get('browser_download_url'), file_path, asset_name):
            return file_path
        else:
            logger.error(f"Failed to download {asset_name}")
            return None 