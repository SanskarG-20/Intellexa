"""
memory.py - Memory API Routes
FastAPI routes for the Multimodal Context Memory System.
"""

import uuid
import asyncio
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Depends, BackgroundTasks
from fastapi.responses import JSONResponse

from app.db.supabase import supabase
from app.core.config import settings
from app.schemas.memory import (
    UploadInitResponse,
    UploadStatusResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentDetailResponse,
    DocumentDeleteResponse,
    ContextQueryRequest,
    ContextQueryResponse,
    ContextResult,
    ChunkListResponse,
    ChunkInfo,
    MemoryStatsResponse,
    MemoryErrorResponse
)
from app.services.memory.storage_service import storage_service, StorageServiceError
from app.services.memory.chunking_service import chunking_service
from app.services.memory.embedding_service import embedding_service, EmbeddingServiceError
from app.services.memory.retrieval_service import retrieval_service
from app.services.memory.pdf_service import pdf_service, PDFServiceError
from app.services.memory.image_service import image_service, ImageServiceError
from app.services.memory.video_service import video_service, VideoServiceError


router = APIRouter(prefix="/api/v1/memory", tags=["Memory"])


# ============================================================================
# Helper Functions
# ============================================================================

def _get_user_id(authorization: Optional[str] = None) -> str:
    """
    Extract user ID from authorization header or use mock user.
    In production, this should validate JWT tokens.
    """
    if authorization and authorization.startswith("Bearer "):
        # In production, decode JWT and extract user_id
        # For now, return a mock user ID
        pass
    return settings.MOCK_USER_ID


def _detect_file_type(content_type: str, filename: str) -> str:
    """Detect file type from content type and filename."""
    if 'pdf' in content_type or filename.lower().endswith('.pdf'):
        return 'pdf'
    elif any(ct in content_type for ct in ['image/', 'jpeg', 'jpg', 'png', 'webp', 'gif']):
        return 'image'
    elif any(ct in content_type for ct in ['video/', 'mp4', 'mov', 'avi', 'webm']):
        return 'video'
    else:
        # Try to guess from extension
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        if ext == 'pdf':
            return 'pdf'
        elif ext in ['jpg', 'jpeg', 'png', 'webp', 'gif']:
            return 'image'
        elif ext in ['mp4', 'mov', 'avi', 'webm', 'mkv']:
            return 'video'
    return 'text'


# ============================================================================
# Background Processing
# ============================================================================

async def process_document_background(
    document_id: str,
    user_id: str,
    file_bytes: bytes,
    file_type: str,
    filename: str,
    content_type: str,
    storage_path: str
):
    """
    Background task to process uploaded document.
    Handles text extraction, chunking, and embedding.
    """
    try:
        # Update status to processing
        await _update_document_status(document_id, 'processing')
        
        # Process based on file type
        if file_type == 'pdf':
            chunks = pdf_service.process_pdf(file_bytes, user_id, document_id, filename)
        elif file_type == 'image':
            chunks = image_service.process_image(
                file_bytes, user_id, document_id, filename, content_type
            )
        elif file_type == 'video':
            chunks = video_service.process_video(
                file_bytes, user_id, document_id, filename, content_type
            )
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
        
        if not chunks:
            await _update_document_status(
                document_id, 'failed', 
                error_message="No content could be extracted from the file"
            )
            return
        
        # Store chunks in database
        chunk_ids = await _store_chunks(document_id, user_id, chunks)
        
        # Generate and store embeddings
        await _store_embeddings(document_id, user_id, chunks, chunk_ids)
        
        # Update status to ready
        await _update_document_status(document_id, 'ready')
        
        print(f"[MemoryAPI] Document {document_id} processed successfully: {len(chunks)} chunks")
        
    except Exception as e:
        print(f"[MemoryAPI] Document processing failed: {e}")
        await _update_document_status(
            document_id, 'failed',
            error_message=str(e)[:500]
        )


async def _update_document_status(
    document_id: str,
    status: str,
    error_message: str = None
):
    """Update document status in database."""
    if not supabase:
        return
    
    update_data = {
        'status': status,
        'updated_at': datetime.utcnow().isoformat()
    }
    if error_message:
        update_data['error_message'] = error_message
    
    try:
        supabase.table('user_documents').update(update_data).eq('id', document_id).execute()
    except Exception as e:
        print(f"[MemoryAPI] Failed to update status: {e}")


async def _store_chunks(
    document_id: str,
    user_id: str,
    chunks: list
) -> list:
    """Store document chunks in database."""
    if not supabase:
        return []
    
    chunk_ids = []
    
    for chunk in chunks:
        try:
            result = supabase.table('document_chunks').insert({
                'document_id': document_id,
                'user_id': user_id,
                'chunk_index': chunk.index,
                'content': chunk.content,
                'content_summary': chunk.content[:200] + '...' if len(chunk.content) > 200 else chunk.content,
                'page_number': chunk.page_number,
                'metadata': chunk.metadata or {}
            }).execute()
            
            if result.data:
                chunk_ids.append(result.data[0]['id'])
        except Exception as e:
            print(f"[MemoryAPI] Failed to store chunk {chunk.index}: {e}")
    
    return chunk_ids


async def _store_embeddings(
    document_id: str,
    user_id: str,
    chunks: list,
    chunk_ids: list
):
    """Generate and store embeddings for chunks."""
    if not supabase or not chunk_ids:
        return
    
    try:
        # Generate embeddings in batch
        texts = [chunk.content for chunk in chunks[:len(chunk_ids)]]
        embeddings = await embedding_service.embed_batch(texts)
        
        # Store embeddings
        for chunk_id, embedding in zip(chunk_ids, embeddings):
            if embedding:
                supabase.table('document_embeddings').insert({
                    'chunk_id': chunk_id,
                    'document_id': document_id,
                    'user_id': user_id,
                    'embedding': embedding
                }).execute()
                
    except Exception as e:
        print(f"[MemoryAPI] Failed to store embeddings: {e}")
        raise


# ============================================================================
# Upload Endpoints
# ============================================================================

@router.post("/upload", response_model=UploadInitResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(_get_user_id)
):
    """
    Upload a document for processing.
    
    Supported file types:
    - PDF: .pdf
    - Images: .jpg, .jpeg, .png, .webp, .gif
    - Videos: .mp4, .mov, .avi, .webm
    
    Max file size: 50MB (configurable)
    """
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    # Validate file size
    file_size_limit = settings.get_max_file_size_bytes()
    
    # Read file content
    file_bytes = await file.read()
    
    if len(file_bytes) > file_size_limit:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {settings.MAX_FILE_SIZE_MB}MB"
        )
    
    # Detect file type
    file_type = _detect_file_type(file.content_type or '', file.filename or 'file')
    
    if file_type == 'text':
        raise HTTPException(
            status_code=415,
            detail="Unsupported file type. Supported: PDF, images, videos"
        )
    
    # Generate document ID
    document_id = str(uuid.uuid4())
    
    # Upload to storage
    try:
        storage_path = await storage_service.upload_file(
            user_id=user_id,
            file_content=file_bytes,
            filename=file.filename or f"document.{file_type}",
            content_type=file.content_type or "application/octet-stream"
        )
    except StorageServiceError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload file: {e.message}"
        )
    
    # Create document record
    try:
        supabase.table('user_documents').insert({
            'id': document_id,
            'user_id': user_id,
            'filename': file.filename or 'document',
            'file_type': file_type,
            'file_size': len(file_bytes),
            'storage_path': storage_path,
            'status': 'pending'
        }).execute()
    except Exception as e:
        # Cleanup storage if database insert fails
        try:
            await storage_service.delete_file(storage_path)
        except:
            pass
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create document record: {str(e)}"
        )
    
    # Start background processing
    background_tasks.add_task(
        process_document_background,
        document_id,
        user_id,
        file_bytes,
        file_type,
        file.filename or 'document',
        file.content_type or 'application/octet-stream',
        storage_path
    )
    
    return UploadInitResponse(
        document_id=document_id,
        status='pending',
        message='File uploaded successfully. Processing started.',
        filename=file.filename or 'document',
        file_type=file_type
    )


@router.get("/status/{document_id}", response_model=UploadStatusResponse)
async def get_upload_status(
    document_id: str,
    user_id: str = Depends(_get_user_id)
):
    """Get the processing status of an uploaded document."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        result = supabase.table('user_documents').select(
            'id, status, error_message, created_at'
        ).eq('id', document_id).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
            )
        
        doc = result.data[0]
        
        # Get chunk count if ready
        chunk_count = None
        if doc['status'] == 'ready':
            count_result = supabase.table('document_chunks').select(
                'id', count='exact'
            ).eq('document_id', document_id).execute()
            chunk_count = count_result.count if hasattr(count_result, 'count') else 0
        
        return UploadStatusResponse(
            document_id=document_id,
            status=doc['status'],
            message="Processing complete" if doc['status'] == 'ready' else "Processing in progress",
            error=doc.get('error_message'),
            chunk_count=chunk_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get status: {str(e)}"
        )


# ============================================================================
# Document Endpoints
# ============================================================================

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user_id: str = Depends(_get_user_id),
    limit: int = 50,
    offset: int = 0
):
    """List all documents for the current user."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Get documents
        result = supabase.table('user_documents').select(
            'id, filename, file_type, file_size, status, created_at, updated_at, error_message'
        ).eq('user_id', user_id).order('created_at', desc=True).range(
            offset, offset + limit - 1
        ).execute()
        
        documents = []
        for doc in (result.data or []):
            # Get chunk count
            chunk_result = supabase.table('document_chunks').select(
                'id', count='exact'
            ).eq('document_id', doc['id']).execute()
            
            chunk_count = chunk_result.count if hasattr(chunk_result, 'count') else 0
            
            documents.append(DocumentInfo(
                id=doc['id'],
                filename=doc['filename'],
                file_type=doc['file_type'],
                file_size=doc.get('file_size'),
                status=doc['status'],
                chunk_count=chunk_count,
                created_at=datetime.fromisoformat(doc['created_at'].replace('Z', '+00:00')),
                updated_at=datetime.fromisoformat(doc['updated_at'].replace('Z', '+00:00')) if doc.get('updated_at') else None,
                error_message=doc.get('error_message')
            ))
        
        # Get total count
        count_result = supabase.table('user_documents').select(
            'id', count='exact'
        ).eq('user_id', user_id).execute()
        total = count_result.count if hasattr(count_result, 'count') else len(documents)
        
        return DocumentListResponse(
            documents=documents,
            total=total
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list documents: {str(e)}"
        )


@router.get("/documents/{document_id}", response_model=DocumentDetailResponse)
async def get_document(
    document_id: str,
    user_id: str = Depends(_get_user_id)
):
    """Get detailed information about a specific document."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Get document
        result = supabase.table('user_documents').select('*').eq(
            'id', document_id
        ).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
            )
        
        doc = result.data[0]
        
        # Get chunks
        chunks_result = supabase.table('document_chunks').select(
            'id, chunk_index, content, page_number'
        ).eq('document_id', document_id).order('chunk_index').execute()
        
        chunks = chunks_result.data or []
        
        # Create preview from first few chunks
        preview = None
        if chunks:
            preview_content = '\n\n'.join(
                chunk['content'][:500] for chunk in chunks[:3]
            )
            preview = preview_content[:1500]
        
        return DocumentDetailResponse(
            id=doc['id'],
            filename=doc['filename'],
            file_type=doc['file_type'],
            file_size=doc.get('file_size'),
            status=doc['status'],
            created_at=datetime.fromisoformat(doc['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(doc['updated_at'].replace('Z', '+00:00')) if doc.get('updated_at') else None,
            chunk_count=len(chunks),
            preview=preview,
            error_message=doc.get('error_message')
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get document: {str(e)}"
        )


@router.delete("/documents/{document_id}", response_model=DocumentDeleteResponse)
async def delete_document(
    document_id: str,
    user_id: str = Depends(_get_user_id)
):
    """Delete a document and all associated data."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Get document
        result = supabase.table('user_documents').select(
            'id, storage_path'
        ).eq('id', document_id).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
            )
        
        doc = result.data[0]
        storage_path = doc.get('storage_path')
        
        # Delete from storage
        if storage_path:
            try:
                await storage_service.delete_file(storage_path)
            except Exception as e:
                print(f"[MemoryAPI] Failed to delete from storage: {e}")
        
        # Delete from database (cascades to chunks and embeddings)
        supabase.table('user_documents').delete().eq('id', document_id).execute()
        
        return DocumentDeleteResponse(
            success=True,
            document_id=document_id,
            message="Document deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete document: {str(e)}"
        )


# ============================================================================
# Query Endpoints
# ============================================================================

@router.post("/query", response_model=ContextQueryResponse)
async def query_context(
    request: ContextQueryRequest,
    user_id: str = Depends(_get_user_id)
):
    """
    Query stored context for relevant information.
    Returns top-k most relevant chunks based on semantic similarity.
    """
    results = await retrieval_service.retrieve_context(
        query=request.query,
        user_id=user_id,
        top_k=request.top_k
    )
    
    # Format results
    context_results = [
        ContextResult(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            content=r.content,
            filename=r.filename,
            file_type=r.file_type,
            similarity=r.similarity,
            page_number=r.page_number
        )
        for r in results
    ]
    
    # Format for LLM prompt
    formatted_context = retrieval_service.format_context_for_prompt(results)
    
    return ContextQueryResponse(
        query=request.query,
        results=context_results,
        formatted_context=formatted_context,
        total_found=len(context_results)
    )


# ============================================================================
# Stats Endpoint
# ============================================================================

@router.get("/stats", response_model=MemoryStatsResponse)
async def get_memory_stats(
    user_id: str = Depends(_get_user_id)
):
    """Get statistics about user's memory storage."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Get document counts
        docs_result = supabase.table('user_documents').select(
            'id, file_type, file_size'
        ).eq('user_id', user_id).execute()
        
        documents = docs_result.data or []
        
        # Get chunk count
        chunks_result = supabase.table('document_chunks').select(
            'id', count='exact'
        ).eq('user_id', user_id).execute()
        
        total_chunks = chunks_result.count if hasattr(chunks_result, 'count') else 0
        
        # Calculate stats
        by_type = {}
        storage_bytes = 0
        
        for doc in documents:
            file_type = doc.get('file_type', 'unknown')
            by_type[file_type] = (by_type.get(file_type, 0) + 1)
            storage_bytes += doc.get('file_size') or 0
        
        return MemoryStatsResponse(
            total_documents=len(documents),
            total_chunks=total_chunks,
            storage_used_bytes=storage_bytes,
            by_type=by_type
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get stats: {str(e)}"
        )


# ============================================================================
# Chunks Endpoint
# ============================================================================

@router.get("/documents/{document_id}/chunks", response_model=ChunkListResponse)
async def list_document_chunks(
    document_id: str,
    user_id: str = Depends(_get_user_id),
    limit: int = 100
):
    """List all chunks for a specific document."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Verify document belongs to user
        doc_result = supabase.table('user_documents').select('id').eq(
            'id', document_id
        ).eq('user_id', user_id).execute()
        
        if not doc_result.data:
            raise HTTPException(
                status_code=404,
                detail="Document not found"
            )
        
        # Get chunks
        chunks_result = supabase.table('document_chunks').select(
            'id, chunk_index, content, page_number, metadata'
        ).eq('document_id', document_id).order('chunk_index').limit(limit).execute()
        
        chunks = [
            ChunkInfo(
                id=chunk['id'],
                document_id=document_id,
                chunk_index=chunk['chunk_index'],
                content=chunk['content'],
                token_count=len(chunk['content'].split()),  # Rough estimate
                page_number=chunk.get('page_number')
            )
            for chunk in (chunks_result.data or [])
        ]
        
        return ChunkListResponse(
            document_id=document_id,
            chunks=chunks,
            total=len(chunks)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list chunks: {str(e)}"
        )
