"""
Crawl4AI Storage Backend Integration

This module provides a unified interface for storing and loading browser state
(cookies, localStorage, browser data directories) to various storage backends.

Supported backends:
- Local filesystem
- Minio (S3-compatible)
- AWS S3 (future)
- Azure Blob Storage (future)
- Google Cloud Storage (future)
"""

from .base import StorageBackend, StorageConfig
from .local import LocalStorageBackend
from .minio_backend import MinioStorageBackend
from .factory import create_storage_backend

__all__ = [
    "StorageBackend",
    "StorageConfig",
    "LocalStorageBackend",
    "MinioStorageBackend",
    "create_storage_backend",
]

