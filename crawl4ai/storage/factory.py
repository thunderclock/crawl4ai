"""
Factory for creating storage backends
"""

from typing import Optional
from .base import StorageBackend, StorageConfig
from .local import LocalStorageBackend
from .minio_backend import MinioStorageBackend


def create_storage_backend(
    backend_type: str = "local",
    profile_name: str = "default",
    logger=None,
    **kwargs
) -> StorageBackend:
    """
    Create a storage backend instance
    
    Args:
        backend_type: Type of storage backend ("local" or "minio")
        profile_name: Profile name for browser state
        logger: Logger instance (optional)
        **kwargs: Additional backend-specific configuration
        
    Returns:
        StorageBackend instance
        
    Examples:
        # Local storage
        backend = create_storage_backend(
            backend_type="local",
            local_path="/path/to/storage"
        )
        
        # Minio storage
        backend = create_storage_backend(
            backend_type="minio",
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket_name="crawl4ai-browser-state"
        )
    """
    config = StorageConfig(
        backend_type=backend_type,
        profile_name=profile_name,
        **kwargs
    )
    
    if backend_type == "local":
        return LocalStorageBackend(config, logger=logger)
    elif backend_type == "minio":
        return MinioStorageBackend(config, logger=logger)
    else:
        raise ValueError(f"Unsupported storage backend type: {backend_type}")

