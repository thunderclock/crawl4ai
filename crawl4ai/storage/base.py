"""
Base storage backend interface for Crawl4AI
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class StorageConfig:
    """Configuration for storage backend"""
    backend_type: str = "local"  # "local", "minio", "s3", etc.
    profile_name: str = "default"
    
    # Local storage config
    local_path: Optional[str] = None
    
    # Minio/S3 config
    endpoint: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    bucket_name: Optional[str] = None
    secure: bool = True
    region: Optional[str] = None


class StorageBackend(ABC):
    """Abstract base class for storage backends"""
    
    def __init__(self, config: StorageConfig, logger=None):
        """
        Initialize storage backend
        
        Args:
            config: Storage configuration
            logger: Logger instance (optional)
        """
        self.config = config
        self.logger = logger
    
    def _log(self, message: str, level: str = "info"):
        """Log message if logger is available"""
        if self.logger:
            if level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
    
    @abstractmethod
    async def save_storage_state(
        self,
        storage_state: Dict[str, Any],
        profile_name: Optional[str] = None
    ) -> bool:
        """
        Save browser storage state (cookies, localStorage) to storage
        
        Args:
            storage_state: Storage state dictionary from Playwright context.storage_state()
            profile_name: Profile name (overrides config.profile_name if provided)
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def load_storage_state(
        self,
        profile_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Load browser storage state from storage
        
        Args:
            profile_name: Profile name (overrides config.profile_name if provided)
            
        Returns:
            Storage state dictionary or None if not found
        """
        pass
    
    @abstractmethod
    async def save_browser_data_dir(
        self,
        browser_data_dir: Path,
        profile_name: Optional[str] = None
    ) -> bool:
        """
        Save entire browser data directory to storage
        
        Args:
            browser_data_dir: Path to browser data directory
            profile_name: Profile name (overrides config.profile_name if provided)
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def load_browser_data_dir(
        self,
        target_dir: Path,
        profile_name: Optional[str] = None,
        use_latest: bool = True
    ) -> bool:
        """
        Load browser data directory from storage
        
        Args:
            target_dir: Target directory to extract browser data
            profile_name: Profile name (overrides config.profile_name if provided)
            use_latest: If True, load latest version
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    async def save_browser_state(
        self,
        storage_state: Dict[str, Any],
        browser_data_dir: Optional[Path] = None,
        profile_name: Optional[str] = None
    ) -> bool:
        """
        Save both storage state and browser data directory to storage
        
        Args:
            storage_state: Storage state dictionary
            browser_data_dir: Optional path to browser data directory
            profile_name: Profile name (overrides config.profile_name if provided)
            
        Returns:
            True if successful, False otherwise
        """
        pass
    
    @abstractmethod
    def list_profiles(self) -> list:
        """
        List all available profiles in storage
        
        Returns:
            List of profile names
        """
        pass
    
    def _get_profile_name(self, profile_name: Optional[str] = None) -> str:
        """Get profile name, using provided or config default"""
        return profile_name or self.config.profile_name

