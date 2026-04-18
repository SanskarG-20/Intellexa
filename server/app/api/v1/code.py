"""
code.py - Code Space API Routes
FastAPI routes for Code Space file management and AI assistance.
"""

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.db.supabase import supabase
from app.core.config import settings
from app.controllers.code_workspace_controller import code_workspace_controller
from app.schemas.code import (
    CodeFileCreate,
    CodeFileUpdate,
    CodeFileInfo,
    CodeFileDetail,
    CodeFileListResponse,
    CodeFileDeleteResponse,
    CodeFileImportRequest,
    CodeFileImportResponse,
    CodeFileImportItem,
    CodeAssistRequest,
    CodeAssistResponse,
)


router = APIRouter(prefix="/api/v1/code", tags=["Code Space"])


# ============================================================================
# Helper Functions
# ============================================================================

def _get_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """
    Extract user ID from authorization header or use mock user.
    In production, this should validate JWT tokens.
    """
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()

    if authorization and authorization.startswith("Bearer "):
        # In production, decode JWT and extract user_id
        pass
    return settings.MOCK_USER_ID


def _detect_language(filename: str) -> str:
    """Detect programming language from file extension."""
    ext = filename.lower().split('.')[-1] if '.' in filename else ''
    
    language_map = {
        'js': 'javascript',
        'jsx': 'javascript',
        'ts': 'typescript',
        'tsx': 'typescript',
        'py': 'python',
        'rb': 'ruby',
        'java': 'java',
        'go': 'go',
        'rs': 'rust',
        'c': 'c',
        'cpp': 'cpp',
        'h': 'c',
        'hpp': 'cpp',
        'cs': 'csharp',
        'php': 'php',
        'swift': 'swift',
        'kt': 'kotlin',
        'scala': 'scala',
        'r': 'r',
        'm': 'objective-c',
        'sh': 'bash',
        'bash': 'bash',
        'zsh': 'bash',
        'ps1': 'powershell',
        'html': 'html',
        'css': 'css',
        'scss': 'scss',
        'sass': 'scss',
        'less': 'less',
        'json': 'json',
        'yaml': 'yaml',
        'yml': 'yaml',
        'xml': 'xml',
        'md': 'markdown',
        'sql': 'sql',
        'graphql': 'graphql',
        'gql': 'graphql',
        'vue': 'vue',
        'svelte': 'svelte',
    }
    
    return language_map.get(ext, 'plaintext')


# ============================================================================
# File CRUD Endpoints
# ============================================================================

@router.get("/files", response_model=CodeFileListResponse)
async def list_code_files(
    user_id: str = Depends(_get_user_id),
    path: str = "/"
):
    """List all code files for the current user, optionally filtered by path."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        query = supabase.table('code_files').select(
            'id, filename, path, language, is_folder, parent_id, created_at, updated_at'
        ).eq('user_id', user_id)
        
        if path and path != "/":
            query = query.eq('path', path)
        
        result = query.order('is_folder', desc=False).order('filename').execute()
        
        files = [
            CodeFileInfo(
                id=f['id'],
                filename=f['filename'],
                path=f['path'],
                language=f['language'],
                is_folder=f['is_folder'],
                parent_id=f.get('parent_id'),
                created_at=datetime.fromisoformat(f['created_at'].replace('Z', '+00:00')),
                updated_at=datetime.fromisoformat(f['updated_at'].replace('Z', '+00:00')) if f.get('updated_at') else None,
            )
            for f in (result.data or [])
        ]
        
        return CodeFileListResponse(files=files, total=len(files))
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list files: {str(e)}"
        )


@router.get("/files/{file_id}", response_model=CodeFileDetail)
async def get_code_file(
    file_id: str,
    user_id: str = Depends(_get_user_id)
):
    """Get a specific code file with its content."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        result = supabase.table('code_files').select('*').eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )
        
        f = result.data[0]
        
        return CodeFileDetail(
            id=f['id'],
            filename=f['filename'],
            path=f['path'],
            language=f['language'],
            is_folder=f['is_folder'],
            parent_id=f.get('parent_id'),
            created_at=datetime.fromisoformat(f['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(f['updated_at'].replace('Z', '+00:00')) if f.get('updated_at') else None,
            content=f.get('content') or '',
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get file: {str(e)}"
        )


@router.post("/files", response_model=CodeFileDetail)
async def create_code_file(
    file: CodeFileCreate,
    user_id: str = Depends(_get_user_id)
):
    """Create a new code file or folder."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    # Auto-detect language from filename if not provided
    if not file.language or file.language == 'javascript':
        file.language = _detect_language(file.filename)
    
    file_id = str(uuid.uuid4())
    now = datetime.utcnow().isoformat()
    
    try:
        # Check for duplicate filename in same path
        existing = supabase.table('code_files').select('id').eq(
            'user_id', user_id
        ).eq('path', file.path).eq('filename', file.filename).execute()
        
        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"A file named '{file.filename}' already exists in this location"
            )
        
        result = supabase.table('code_files').insert({
            'id': file_id,
            'user_id': user_id,
            'filename': file.filename,
            'path': file.path,
            'content': file.content,
            'language': file.language,
            'is_folder': file.is_folder,
            'parent_id': file.parent_id,
            'created_at': now,
            'updated_at': now,
        }).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to create file"
            )
        
        f = result.data[0]
        
        return CodeFileDetail(
            id=f['id'],
            filename=f['filename'],
            path=f['path'],
            language=f['language'],
            is_folder=f['is_folder'],
            parent_id=f.get('parent_id'),
            created_at=datetime.fromisoformat(f['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(f['updated_at'].replace('Z', '+00:00')),
            content=f.get('content') or '',
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create file: {str(e)}"
        )


@router.put("/files/{file_id}", response_model=CodeFileDetail)
async def update_code_file(
    file_id: str,
    update: CodeFileUpdate,
    user_id: str = Depends(_get_user_id)
):
    """Update a code file's content or metadata."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Check file exists
        existing = supabase.table('code_files').select('*').eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )
        
        # Build update data
        update_data = {'updated_at': datetime.utcnow().isoformat()}
        
        if update.filename is not None:
            update_data['filename'] = update.filename
        if update.content is not None:
            update_data['content'] = update.content
        if update.language is not None:
            update_data['language'] = update.language
        
        result = supabase.table('code_files').update(update_data).eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        if not result.data:
            raise HTTPException(
                status_code=500,
                detail="Failed to update file"
            )
        
        f = result.data[0]
        
        return CodeFileDetail(
            id=f['id'],
            filename=f['filename'],
            path=f['path'],
            language=f['language'],
            is_folder=f['is_folder'],
            parent_id=f.get('parent_id'),
            created_at=datetime.fromisoformat(f['created_at'].replace('Z', '+00:00')),
            updated_at=datetime.fromisoformat(f['updated_at'].replace('Z', '+00:00')),
            content=f.get('content') or '',
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update file: {str(e)}"
        )


@router.delete("/files/{file_id}", response_model=CodeFileDeleteResponse)
async def delete_code_file(
    file_id: str,
    user_id: str = Depends(_get_user_id)
):
    """Delete a code file."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Check file exists
        existing = supabase.table('code_files').select('id, filename, is_folder').eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )
        
        filename = existing.data[0]['filename']
        
        # Delete the file
        supabase.table('code_files').delete().eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        # If it was a folder, also delete children
        if existing.data[0]['is_folder']:
            supabase.table('code_files').delete().eq(
                'parent_id', file_id
            ).eq('user_id', user_id).execute()
        
        return CodeFileDeleteResponse(
            success=True,
            file_id=file_id,
            message=f"'{filename}' deleted successfully"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete file: {str(e)}"
        )


# ============================================================================
# Import Endpoint
# ============================================================================

@router.post("/files/import", response_model=CodeFileImportResponse)
async def import_code_files(
    request: CodeFileImportRequest,
    user_id: str = Depends(_get_user_id)
):
    """Import multiple code files at once."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    imported_files = []
    errors = []
    
    for file_item in request.files:
        try:
            file_id = str(uuid.uuid4())
            now = datetime.utcnow().isoformat()
            
            language = file_item.language or _detect_language(file_item.filename)
            
            result = supabase.table('code_files').insert({
                'id': file_id,
                'user_id': user_id,
                'filename': file_item.filename,
                'path': file_item.path,
                'content': file_item.content,
                'language': language,
                'is_folder': False,
                'created_at': now,
                'updated_at': now,
            }).execute()
            
            if result.data:
                f = result.data[0]
                imported_files.append(CodeFileInfo(
                    id=f['id'],
                    filename=f['filename'],
                    path=f['path'],
                    language=f['language'],
                    is_folder=f['is_folder'],
                    parent_id=f.get('parent_id'),
                    created_at=datetime.fromisoformat(f['created_at'].replace('Z', '+00:00')),
                    updated_at=datetime.fromisoformat(f['updated_at'].replace('Z', '+00:00')),
                ))
        except Exception as e:
            errors.append(f"{file_item.filename}: {str(e)}")
    
    return CodeFileImportResponse(
        success=len(imported_files) > 0,
        imported_count=len(imported_files),
        files=imported_files,
        errors=errors if errors else None
    )


# ============================================================================
# Code Assist Endpoint
# ============================================================================

@router.post("/assist", response_model=CodeAssistResponse)
async def code_assist(
    request: CodeAssistRequest,
    user_id: str = Depends(_get_user_id)
):
    """
    AI Code Assistance endpoint.
    Provides code explanation, generation, fixing, and refactoring.
    Integrates with RAG for context-aware assistance.
    """
    return await code_workspace_controller.assist(request, user_id=user_id)


# ============================================================================
# File Tree Endpoint
# ============================================================================

@router.get("/tree")
async def get_file_tree(
    user_id: str = Depends(_get_user_id)
):
    """Get the complete file tree structure for the user."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        result = supabase.table('code_files').select(
            'id, filename, path, language, is_folder, parent_id'
        ).eq('user_id', user_id).order('is_folder', desc=False).order('filename').execute()
        
        # Build tree structure
        files = result.data or []
        
        # Group by path
        tree = {}
        for f in files:
            path = f['path']
            if path not in tree:
                tree[path] = {'folders': [], 'files': []}
            
            item = {
                'id': f['id'],
                'name': f['filename'],
                'language': f['language'],
                'isFolder': f['is_folder'],
            }
            
            if f['is_folder']:
                tree[path]['folders'].append(item)
            else:
                tree[path]['files'].append(item)
        
        return {
            'tree': tree,
            'total': len(files)
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get file tree: {str(e)}"
        )
