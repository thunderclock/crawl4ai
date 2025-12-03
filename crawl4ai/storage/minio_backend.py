"""
Minio (S3-compatible) storage backend for Crawl4AI
"""

import json
import zipfile
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from io import BytesIO

try:
    from minio import Minio
    from minio.error import S3Error
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False

from .base import StorageBackend, StorageConfig


class MinioStorageBackend(StorageBackend):
    """Minio (S3-compatible) storage backend"""
    
    def __init__(self, config: StorageConfig, logger=None):
        """
        Initialize Minio storage backend
        
        Args:
            config: Storage configuration with Minio settings
            logger: Logger instance (optional)
        """
        super().__init__(config, logger)
        
        if not MINIO_AVAILABLE:
            raise ImportError(
                "minio package is not installed. Install it with: pip install minio"
            )
        
        if not config.endpoint or not config.access_key or not config.secret_key:
            raise ValueError("Minio configuration requires endpoint, access_key, and secret_key")
        
        self.bucket_name = config.bucket_name or "crawl4ai-browser-state"
        
        # Initialize Minio client
        self.client = Minio(
            endpoint=config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
            region=config.region
        )
        
        # Ensure bucket exists
        self._ensure_bucket()
        self._log(f"Minio storage backend initialized: {config.endpoint}/{self.bucket_name}")
    
    def _ensure_bucket(self):
        """Ensure the bucket exists, create if it doesn't"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                self._log(f"Created bucket: {self.bucket_name}")
            else:
                self._log(f"Bucket already exists: {self.bucket_name}")
        except S3Error as e:
            self._log(f"Error ensuring bucket exists: {str(e)}", level="error")
            raise
    
    def _get_storage_state_key(self, profile_name: Optional[str] = None) -> str:
        """Get object key for storage state JSON"""
        profile_name = self._get_profile_name(profile_name)
        return f"profiles/{profile_name}/storage_state.json"
    
    def _get_browser_data_key(self, profile_name: Optional[str] = None) -> str:
        """Get object key prefix for browser data directory"""
        profile_name = self._get_profile_name(profile_name)
        return f"profiles/{profile_name}/browser_data"
    
    async def save_storage_state(
        self,
        storage_state: Dict[str, Any],
        profile_name: Optional[str] = None
    ) -> bool:
        """Save browser storage state to Minio"""
        try:
            key = self._get_storage_state_key(profile_name)
            data = json.dumps(storage_state, indent=2, ensure_ascii=False).encode('utf-8')
            
            # Upload to Minio
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=key,
                data=BytesIO(data),
                length=len(data),
                content_type='application/json'
            )
            
            self._log(f"Saved storage state to Minio: {key}")
            return True
        except Exception as e:
            self._log(f"Error saving storage state to Minio: {str(e)}", level="error")
            return False
    
    async def load_storage_state(
        self,
        profile_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Load browser storage state from Minio"""
        try:
            key = self._get_storage_state_key(profile_name)
            
            # Check if object exists
            try:
                self.client.stat_object(self.bucket_name, key)
            except S3Error as e:
                if e.code == 'NoSuchKey':
                    self._log(f"Storage state not found in Minio: {key}", level="warning")
                    return None
                raise
            
            # Download from Minio
            response = self.client.get_object(self.bucket_name, key)
            data = response.read()
            response.close()
            response.release_conn()
            
            storage_state = json.loads(data.decode('utf-8'))
            self._log(f"Loaded storage state from Minio: {key}")
            return storage_state
        except Exception as e:
            self._log(f"Error loading storage state from Minio: {str(e)}", level="error")
            return None
    
    async def save_browser_data_dir(
        self,
        browser_data_dir: Path,
        profile_name: Optional[str] = None
    ) -> bool:
        """Save browser data directory to Minio as zip archive"""
        try:
            if not browser_data_dir.exists():
                self._log(f"Browser data directory does not exist: {browser_data_dir}", level="warning")
                return False
            
            # Create zip archive in memory
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # Add all files from browser data directory
                for file_path in browser_data_dir.rglob('*'):
                    if file_path.is_file():
                        arc_name = file_path.relative_to(browser_data_dir)
                        zip_file.write(file_path, arc_name)
            
            zip_buffer.seek(0)
            zip_data = zip_buffer.read()
            
            # Upload timestamped version
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            key_prefix = self._get_browser_data_key(profile_name)
            timestamped_key = f"{key_prefix}/browser_data_{timestamp}.zip"
            
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=timestamped_key,
                data=BytesIO(zip_data),
                length=len(zip_data),
                content_type='application/zip'
            )
            
            # Also save latest version
            latest_key = f"{key_prefix}/browser_data_latest.zip"
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=latest_key,
                data=BytesIO(zip_data),
                length=len(zip_data),
                content_type='application/zip'
            )
            
            self._log(f"Saved browser data directory to Minio: {timestamped_key}")
            return True
        except Exception as e:
            self._log(f"Error saving browser data directory to Minio: {str(e)}", level="error")
            return False
    
    async def load_browser_data_dir(
        self,
        target_dir: Path,
        profile_name: Optional[str] = None,
        use_latest: bool = True
    ) -> bool:
        """Load browser data directory from Minio zip archive"""
        try:
            key_prefix = self._get_browser_data_key(profile_name)
            
            # Determine which archive to load
            if use_latest:
                key = f"{key_prefix}/browser_data_latest.zip"
            else:
                # List all browser data archives and get the most recent
                objects = list(self.client.list_objects(
                    self.bucket_name,
                    prefix=f"{key_prefix}/browser_data_",
                    recursive=True
                ))
                if not objects:
                    self._log(f"No browser data archives found for profile: {profile_name}", level="warning")
                    return False
                
                # Sort by last modified time and get the most recent
                objects = sorted(objects, key=lambda x: x.last_modified, reverse=True)
                key = objects[0].object_name
            
            # Check if object exists
            try:
                self.client.stat_object(self.bucket_name, key)
            except S3Error as e:
                if e.code == 'NoSuchKey':
                    self._log(f"Browser data archive not found in Minio: {key}", level="warning")
                    return False
                raise
            
            # Download from Minio
            response = self.client.get_object(self.bucket_name, key)
            zip_data = response.read()
            response.close()
            response.release_conn()
            
            # Extract to target directory
            target_dir.mkdir(parents=True, exist_ok=True)
            zip_buffer = BytesIO(zip_data)
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                zip_file.extractall(target_dir)
            
            self._log(f"Loaded browser data directory from Minio: {key} -> {target_dir}")
            return True
        except Exception as e:
            self._log(f"Error loading browser data directory from Minio: {str(e)}", level="error")
            return False
    
    async def save_browser_state(
        self,
        storage_state: Dict[str, Any],
        browser_data_dir: Optional[Path] = None,
        profile_name: Optional[str] = None
    ) -> bool:
        """Save both storage state and browser data directory to Minio"""
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
        """List all available profiles in Minio"""
        try:
            profiles = set()
            objects = self.client.list_objects(
                self.bucket_name,
                prefix="profiles/",
                recursive=True
            )
            for obj in objects:
                # Extract profile name from path like "profiles/{profile_name}/..."
                parts = obj.object_name.split('/')
                if len(parts) >= 2:
                    profiles.add(parts[1])
            return sorted(list(profiles))
        except Exception as e:
            self._log(f"Error listing profiles: {str(e)}", level="error")
            return []

