"""
memory.py - Pydantic Schemas for Memory API
Defines request/response models for the Multimodal Context Memory System.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional, Dict, Any


# ============================================================================
# Upload Schemas
# ============================================================================

class UploadInitResponse(BaseModel):
    """Response when initiating a file upload."""
    document_id: str = Field(..., description="Unique identifier for the document")
    status: str = Field(..., description="Initial processing status")
    message: str = Field(..., description="Human-readable status message")
    filename: str = Field(..., description="Original filename")
    file_type: str = Field(..., description="Detected file type (pdf, image, video)")


class UploadStatusResponse(BaseModel):
    """Response for checking upload processing status."""
    document_id: str
    status: str = Field(..., description="Processing status: pending, processing, ready, failed")
    message: Optional[str] = None
    error: Optional[str] = None
    chunk_count: Optional[int] = None
    progress: Optional[float] = Field(None, description="Processing progress as percentage")


# ============================================================================
# Document Schemas
# ============================================================================

class DocumentInfo(BaseModel):
    """Information about a stored document."""
    id: str
    filename: str
    file_type: str
    file_size: Optional[int] = None
    status: str
    chunk_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None


class DocumentListResponse(BaseModel):
    """Response for listing user's documents."""
    documents: List[DocumentInfo]
    total: int


class DocumentDetailResponse(BaseModel):
    """Detailed information about a single document."""
    id: str
    filename: str
    file_type: str
    file_size: Optional[int] = None
    status: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    chunk_count: int
    preview: Optional[str] = Field(None, description="First few chunks preview")
    error_message: Optional[str] = None


class DocumentDeleteResponse(BaseModel):
    """Response after deleting a document."""
    success: bool
    document_id: str
    message: str


# ============================================================================
# Query Schemas
# ============================================================================

class ContextQueryRequest(BaseModel):
    """Request for querying stored context."""
    query: str = Field(..., min_length=1, description="The search query")
    top_k: int = Field(5, ge=1, le=20, description="Maximum number of results")


class ContextResult(BaseModel):
    """A single retrieved context chunk."""
    chunk_id: str
    document_id: str
    content: str
    filename: str
    file_type: str
    similarity: float = Field(..., ge=0.0, le=1.0, description="Similarity score (0-1)")
    page_number: Optional[int] = None


class ContextQueryResponse(BaseModel):
    """Response for context query."""
    query: str
    results: List[ContextResult]
    formatted_context: Optional[str] = Field(None, description="Formatted context for LLM prompt")
    total_found: int


# ============================================================================
# Chunk Schemas
# ============================================================================

class ChunkInfo(BaseModel):
    """Information about a document chunk."""
    id: str
    document_id: str
    chunk_index: int
    content: str
    token_count: Optional[int] = None
    page_number: Optional[int] = None


class ChunkListResponse(BaseModel):
    """Response for listing document chunks."""
    document_id: str
    chunks: List[ChunkInfo]
    total: int


# ============================================================================
# Error Schemas
# ============================================================================

class MemoryErrorResponse(BaseModel):
    """Standard error response for memory API."""
    error: str
    code: str
    detail: Optional[str] = None


# ============================================================================
# Stats Schemas
# ============================================================================

class MemoryStatsResponse(BaseModel):
    """Statistics about user's memory storage."""
    total_documents: int
    total_chunks: int
    storage_used_bytes: int
    by_type: Dict[str, int] = Field(..., description="Document counts by type")
