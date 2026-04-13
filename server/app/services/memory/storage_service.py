"""
storage_service.py - Supabase Storage Operations
Handles file upload, download, and deletion from Supabase Storage.
"""

import uuid
from typing import Optional, BinaryIO
from datetime import timedelta

from app.db.supabase import supabase
from app.core.config import settings


class StorageServiceError(Exception):
    """Custom exception for storage service errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class StorageService:
    """
    Handles file storage operations using Supabase Storage.
    All files are organized by user_id for proper isolation.
    """
    
    def __init__(self):
        self.bucket_name = settings.SUPABASE_STORAGE_BUCKET
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self) -> None:
        """
        Ensure the storage bucket exists.
        Note: In production, this should be created via Supabase dashboard.
        """
        pass  # Bucket should be created via Supabase dashboard or migration
    
    def _build_storage_path(self, user_id: str, filename: str) -> str:
        """
        Build a unique storage path for a file.
        Format: {user_id}/{uuid}_{filename}
        """
        safe_filename = self._sanitize_filename(filename)
        unique_id = str(uuid.uuid4())[:8]
        return f"{user_id}/{unique_id}_{safe_filename}"
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove potentially dangerous characters from filename."""
        import re
        # Keep only alphanumeric, dots, dashes, and underscores
        sanitized = re.sub(r'[^\w\.\-]', '_', filename)
        # Limit length
        if len(sanitized) > 200:
            name, ext = sanitized.rsplit('.', 1) if '.' in sanitized else (sanitized, '')
            sanitized = name[:190] + ('.' + ext if ext else '')
        return sanitized
    
    async def upload_file(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
        content_type: str = "application/octet-stream"
    ) -> str:
        """
        Upload a file to Supabase Storage.
        
        Args:
            user_id: The user's ID for path isolation
            file_content: Binary content of the file
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            The storage path of the uploaded file
            
        Raises:
            StorageServiceError: If upload fails
        """
        if not supabase:
            raise StorageServiceError(
                "Supabase client not initialized",
                "STORAGE_NOT_INITIALIZED"
            )
        
        storage_path = self._build_storage_path(user_id, filename)
        
        try:
            response = supabase.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_content,
                file_options={"content-type": content_type}
            )
            
            # Check for errors in response
            if hasattr(response, 'error') and response.error:
                raise StorageServiceError(
                    f"Upload failed: {response.error}",
                    "UPLOAD_FAILED"
                )
            
            return storage_path
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to upload file: {str(e)}",
                "UPLOAD_FAILED"
            )
    
    async def download_file(self, storage_path: str) -> bytes:
        """
        Download a file from Supabase Storage.
        
        Args:
            storage_path: The storage path of the file
            
        Returns:
            Binary content of the file
            
        Raises:
            StorageServiceError: If download fails
        """
        if not supabase:
            raise StorageServiceError(
                "Supabase client not initialized",
                "STORAGE_NOT_INITIALIZED"
            )
        
        try:
            response = supabase.storage.from_(self.bucket_name).download(storage_path)
            
            if isinstance(response, bytes):
                return response
            
            if hasattr(response, 'error') and response.error:
                raise StorageServiceError(
                    f"Download failed: {response.error}",
                    "DOWNLOAD_FAILED"
                )
            
            # Response might be bytes directly
            return response
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to download file: {str(e)}",
                "DOWNLOAD_FAILED"
            )
    
    async def delete_file(self, storage_path: str) -> bool:
        """
        Delete a file from Supabase Storage.
        
        Args:
            storage_path: The storage path of the file
            
        Returns:
            True if deletion was successful
            
        Raises:
            StorageServiceError: If deletion fails
        """
        if not supabase:
            raise StorageServiceError(
                "Supabase client not initialized",
                "STORAGE_NOT_INITIALIZED"
            )
        
        try:
            response = supabase.storage.from_(self.bucket_name).remove([storage_path])
            
            if hasattr(response, 'error') and response.error:
                raise StorageServiceError(
                    f"Delete failed: {response.error}",
                    "DELETE_FAILED"
                )
            
            return True
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to delete file: {str(e)}",
                "DELETE_FAILED"
            )
    
    async def get_signed_url(
        self,
        storage_path: str,
        expires_in: int = 3600
    ) -> str:
        """
        Generate a signed URL for temporary file access.
        
        Args:
            storage_path: The storage path of the file
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Signed URL for file access
            
        Raises:
            StorageServiceError: If URL generation fails
        """
        if not supabase:
            raise StorageServiceError(
                "Supabase client not initialized",
                "STORAGE_NOT_INITIALIZED"
            )
        
        try:
            response = supabase.storage.from_(self.bucket_name).create_signed_url(
                storage_path,
                expires_in
            )
            
            if hasattr(response, 'error') and response.error:
                raise StorageServiceError(
                    f"Failed to generate signed URL: {response.error}",
                    "SIGNED_URL_FAILED"
                )
            
            # Response structure: {'signedURL': 'url'} or similar
            if isinstance(response, dict):
                return response.get('signedURL') or response.get('signed_url', '')
            
            return str(response)
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to generate signed URL: {str(e)}",
                "SIGNED_URL_FAILED"
            )
    
    async def list_user_files(self, user_id: str) -> list[dict]:
        """
        List all files for a specific user.
        
        Args:
            user_id: The user's ID
            
        Returns:
            List of file metadata dictionaries
            
        Raises:
            StorageServiceError: If listing fails
        """
        if not supabase:
            raise StorageServiceError(
                "Supabase client not initialized",
                "STORAGE_NOT_INITIALIZED"
            )
        
        try:
            response = supabase.storage.from_(self.bucket_name).list(
                path=user_id,
                limit=100
            )
            
            if hasattr(response, 'error') and response.error:
                raise StorageServiceError(
                    f"Failed to list files: {response.error}",
                    "LIST_FAILED"
                )
            
            return response if isinstance(response, list) else []
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to list files: {str(e)}",
                "LIST_FAILED"
            )
    
    async def delete_user_folder(self, user_id: str) -> bool:
        """
        Delete all files for a specific user (e.g., on account deletion).
        
        Args:
            user_id: The user's ID
            
        Returns:
            True if deletion was successful
        """
        try:
            files = await self.list_user_files(user_id)
            
            if not files:
                return True
            
            # Build list of paths to delete
            paths = [f"{user_id}/{f['name']}" for f in files if isinstance(f, dict)]
            
            if paths:
                response = supabase.storage.from_(self.bucket_name).remove(paths)
                
                if hasattr(response, 'error') and response.error:
                    raise StorageServiceError(
                        f"Failed to delete user folder: {response.error}",
                        "DELETE_FAILED"
                    )
            
            return True
            
        except Exception as e:
            if isinstance(e, StorageServiceError):
                raise
            raise StorageServiceError(
                f"Failed to delete user folder: {str(e)}",
                "DELETE_FAILED"
            )


# Singleton instance
storage_service = StorageService()
