"""
Local filesystem storage backend for Crawl4AI
"""

import json
import zipfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from io import BytesIO

from .base import StorageBackend, StorageConfig


class LocalStorageBackend(StorageBackend):
    """Local filesystem storage backend"""
    
    def __init__(self, config: StorageConfig, logger=None):
        """
        Initialize local storage backend
        
        Args:
            config: Storage configuration with local_path set
            logger: Logger instance (optional)
        """
        super().__init__(config, logger)
        
        if not config.local_path:
            # Use default path in user's home directory
            home_dir = Path.home()
            self.base_path = home_dir / ".crawl4ai" / "storage"
        else:
            self.base_path = Path(config.local_path)
        
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._log(f"Local storage backend initialized at: {self.base_path}")
    
    def _get_profile_path(self, profile_name: Optional[str] = None) -> Path:
        """Get profile directory path"""
        profile_name = self._get_profile_name(profile_name)
        return self.base_path / "profiles" / profile_name
    
    def _get_storage_state_path(self, profile_name: Optional[str] = None) -> Path:
        """Get storage state file path"""
        profile_path = self._get_profile_path(profile_name)
        return profile_path / "storage_state.json"
    
    def _get_browser_data_path(self, profile_name: Optional[str] = None) -> Path:
        """Get browser data directory path"""
        profile_path = self._get_profile_path(profile_name)
        return profile_path / "browser_data"
    
    async def save_storage_state(
        self,
        storage_state: Dict[str, Any],
        profile_name: Optional[str] = None
    ) -> bool:
        """Save browser storage state to local filesystem"""
        try:
            profile_path = self._get_profile_path(profile_name)
            profile_path.mkdir(parents=True, exist_ok=True)
            
            storage_state_path = self._get_storage_state_path(profile_name)
            with open(storage_state_path, 'w', encoding='utf-8') as f:
                json.dump(storage_state, f, indent=2, ensure_ascii=False)
            
            self._log(f"Saved storage state to: {storage_state_path}")
            return True
        except Exception as e:
            self._log(f"Error saving storage state: {str(e)}", level="error")
            return False
    
    async def load_storage_state(
        self,
        profile_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load browser storage state from local filesystem"""
        try:
            storage_state_path = self._get_storage_state_path(profile_name)
            
            if not storage_state_path.exists():
                self._log(f"Storage state not found: {storage_state_path}", level="warning")
                return None
            
            with open(storage_state_path, 'r', encoding='utf-8') as f:
                storage_state = json.load(f)
            
            self._log(f"Loaded storage state from: {storage_state_path}")
            return storage_state
        except Exception as e:
            self._log(f"Error loading storage state: {str(e)}", level="error")
            return None
    
    async def save_browser_data_dir(
        self,
        browser_data_dir: Path,
        profile_name: Optional[str] = None
    ) -> bool:
        """Save browser data directory to local filesystem"""
        try:
            if not browser_data_dir.exists():
                self._log(f"Browser data directory does not exist: {browser_data_dir}", level="warning")
                return False
            
            browser_data_path = self._get_browser_data_path(profile_name)
            browser_data_path.mkdir(parents=True, exist_ok=True)
            
            # Create timestamped archive
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_path = browser_data_path / f"browser_data_{timestamp}.zip"
            
            # Create zip archive
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in browser_data_dir.rglob('*'):
                    if file_path.is_file():
                        arc_name = file_path.relative_to(browser_data_dir)
                        zip_file.write(file_path, arc_name)
            
            # Also create/update latest symlink or copy
            latest_path = browser_data_path / "browser_data_latest.zip"
            if latest_path.exists():
                latest_path.unlink()
            shutil.copy2(archive_path, latest_path)
            
            self._log(f"Saved browser data directory to: {archive_path}")
            return True
        except Exception as e:
            self._log(f"Error saving browser data directory: {str(e)}", level="error")
            return False
    
    async def load_browser_data_dir(
        self,
        target_dir: Path,
        profile_name: Optional[str] = None,
        use_latest: bool = True
    ) -> bool:
        """Load browser data directory from local filesystem"""
        try:
            browser_data_path = self._get_browser_data_path(profile_name)
            
            if use_latest:
                archive_path = browser_data_path / "browser_data_latest.zip"
            else:
                # Find most recent archive
                archives = sorted(
                    browser_data_path.glob("browser_data_*.zip"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                if not archives:
                    self._log(f"No browser data archives found for profile: {profile_name}", level="warning")
                    return False
                archive_path = archives[0]
            
            if not archive_path.exists():
                self._log(f"Browser data archive not found: {archive_path}", level="warning")
                return False
            
            # Extract to target directory
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(archive_path, 'r') as zip_file:
                zip_file.extractall(target_dir)
            
            self._log(f"Loaded browser data directory from: {archive_path} -> {target_dir}")
            return True
        except Exception as e:
            self._log(f"Error loading browser data directory: {str(e)}", level="error")
            return False
    
    async def save_browser_state(
        self,
        storage_state: Dict[str, Any],
        browser_data_dir: Optional[Path] = None,
        profile_name: Optional[str] = None
    ) -> bool:
        """Save both storage state and browser data directory"""
        success = True
        
        # Save storage state
        if not await self.save_storage_state(storage_state, profile_name):
            success = False
        
        # Save browser data directory if provided
        if browser_data_dir:
            if not await self.save_browser_data_dir(browser_data_dir, profile_name):
                success = False
        
        return success
    
    def list_profiles(self) -> list:
        """List all available profiles"""
        try:
            profiles_dir = self.base_path / "profiles"
            if not profiles_dir.exists():
                return []
            
            profiles = [
                d.name for d in profiles_dir.iterdir()
                if d.is_dir()
            ]
            return sorted(profiles)
        except Exception as e:
            self._log(f"Error listing profiles: {str(e)}", level="error")
            return []

