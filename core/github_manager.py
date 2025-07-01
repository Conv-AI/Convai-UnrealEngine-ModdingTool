import requests
import os
import time
from typing import Dict, List, Optional, Tuple

class GitHubManager:
    """Manages GitHub repository operations for downloading releases and assets."""
    
    def __init__(self, max_retries: int = 3, retry_delay: int = 2):
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session = requests.Session()
        # Set a user agent to avoid rate limiting
        self.session.headers.update({
            'User-Agent': 'Convai-Modding-Tool/1.0.0'
        })
    
    def get_latest_release(self, repo: str) -> Optional[Dict]:
        """
        Get the latest release information from a GitHub repository.
        
        Args:
            repo: Repository in 'owner/repo' format
            
        Returns:
            Dictionary containing release information or None if failed
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        
        for attempt in range(self.max_retries):
            try:
                print(f"Fetching latest release from {repo}, attempt {attempt + 1}...")
                response = self.session.get(api_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                print(f"Failed to fetch release info (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        return None
    
    def get_release_by_tag(self, repo: str, tag: str) -> Optional[Dict]:
        """
        Get specific release information by tag from a GitHub repository.
        
        Args:
            repo: Repository in 'owner/repo' format
            tag: Release tag (e.g., 'v1.0.0')
            
        Returns:
            Dictionary containing release information or None if failed
        """
        api_url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
        
        for attempt in range(self.max_retries):
            try:
                print(f"Fetching release {tag} from {repo}, attempt {attempt + 1}...")
                response = self.session.get(api_url, timeout=30)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as e:
                print(f"Failed to fetch release {tag} (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        return None
    
    def get_release(self, repo: str, version: Optional[str] = None) -> Optional[Dict]:
        """
        Get release information. If version is None, gets latest release.
        
        Args:
            repo: Repository in 'owner/repo' format
            version: Specific version tag, or None for latest
            
        Returns:
            Dictionary containing release information or None if failed
        """
        if version:
            return self.get_release_by_tag(repo, version)
        else:
            return self.get_latest_release(repo)
    
    def find_release_asset(self, release_data: Dict, asset_patterns: List[str]) -> Optional[Dict]:
        """
        Find a release asset that matches one of the given patterns.
        
        Args:
            release_data: Release data from GitHub API
            asset_patterns: List of patterns to match against asset names
            
        Returns:
            Asset dictionary or None if no match found
        """
        assets = release_data.get("assets", [])
        
        for asset in assets:
            asset_name = asset.get("name", "").lower()
            for pattern in asset_patterns:
                if pattern.lower() in asset_name:
                    return asset
        
        return None
    
    def download_release_asset(self, asset: Dict, download_dir: str, filename: Optional[str] = None) -> Optional[str]:
        """
        Download a release asset.
        
        Args:
            asset: Asset dictionary from GitHub API
            download_dir: Directory to save the file
            filename: Custom filename, or None to use original name
            
        Returns:
            Path to downloaded file or None if failed
        """
        if not asset:
            print("No asset provided for download")
            return None
        
        download_url = asset.get("browser_download_url")
        if not download_url:
            print("No download URL found in asset")
            return None
        
        os.makedirs(download_dir, exist_ok=True)
        
        if filename is None:
            filename = asset.get("name", "download.zip")
        
        file_path = os.path.join(download_dir, filename)
        
        for attempt in range(self.max_retries):
            try:
                print(f"Downloading {filename} from GitHub, attempt {attempt + 1}...")
                
                with self.session.get(download_url, stream=True, timeout=30) as response:
                    response.raise_for_status()
                    
                    # Get file size for progress tracking
                    total_size = int(response.headers.get('content-length', 0))
                    downloaded_size = 0
                    
                    with open(file_path, "wb") as file:
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                file.write(chunk)
                                downloaded_size += len(chunk)
                                
                                # Simple progress indicator
                                if total_size > 0:
                                    progress = (downloaded_size / total_size) * 100
                                    print(f"\rProgress: {progress:.1f}%", end="", flush=True)
                
                print(f"\nDownload complete: {file_path}")
                return file_path
                
            except requests.RequestException as e:
                print(f"\nDownload failed (Attempt {attempt + 1}/{self.max_retries}): {e}")
                if os.path.exists(file_path):
                    os.remove(file_path)  # Clean up partial download
                
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
        
        return None
    
    def download_plugin_from_release(self, repo: str, download_dir: str, 
                                   version: Optional[str] = None, 
                                   asset_patterns: Optional[List[str]] = None) -> Optional[str]:
        """
        Download a plugin from GitHub release.
        
        Args:
            repo: Repository in 'owner/repo' format
            download_dir: Directory to save the plugin
            version: Specific version or None for latest
            asset_patterns: Patterns to match asset names (defaults to common plugin patterns)
            
        Returns:
            Path to downloaded file or None if failed
        """
        if asset_patterns is None:
            asset_patterns = [".zip", "plugin", "unreal", "ue"]
        
        # Get release information
        release_data = self.get_release(repo, version)
        if not release_data:
            print(f"Failed to get release information for {repo}")
            return None
        
        release_name = release_data.get("name", "Unknown")
        release_tag = release_data.get("tag_name", "Unknown")
        print(f"Found release: {release_name} ({release_tag})")
        
        # Find suitable asset
        asset = self.find_release_asset(release_data, asset_patterns)
        if not asset:
            print(f"No suitable asset found in release. Available assets:")
            for a in release_data.get("assets", []):
                print(f"  - {a.get('name', 'Unknown')}")
            return None
        
        asset_name = asset.get("name", "plugin.zip")
        print(f"Selected asset: {asset_name}")
        
        # Download the asset
        return self.download_release_asset(asset, download_dir, asset_name) 