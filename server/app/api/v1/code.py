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
    CollaborationContextPublishRequest,
    CollaborationContextPublishResponse,
    CollaborationEventType,
    CollaborationJoinRequest,
    CollaborationJoinResponse,
    CollaborationRole,
    CollaborationStateResponse,
    CodeBreakAnalysisRequest,
    CodeBreakAnalysisResponse,
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
    CodeVersionCompareRequest,
    CodeVersionCompareResponse,
    CodeVersionHistoryResponse,
    CodeVersionSnapshotResponse,
    TaskModeRequest,
    TaskModeResponse,
)
from app.services.code_workspace.collaboration_service import collaboration_service
from app.services.code_workspace.version_intelligence_service import version_intelligence_service


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


def _build_file_key(path: str, filename: str) -> str:
    normalized_path = str(path or "/").replace('\\', '/').strip()
    if not normalized_path.startswith('/'):
        normalized_path = f"/{normalized_path}"
    if not normalized_path.endswith('/'):
        normalized_path = f"{normalized_path}/"
    normalized_filename = str(filename or '').strip()
    return f"{normalized_path}{normalized_filename}"


def _resolve_collab_actor_name(preferred: Optional[str], fallback: str) -> str:
    normalized = str(preferred or '').strip()
    if normalized:
        return normalized
    return str(fallback or 'Collaborator')


# ============================================================================
# File CRUD Endpoints
# ============================================================================

@router.post("/collaboration/join", response_model=CollaborationJoinResponse)
async def join_collaboration_workspace(
    request: CollaborationJoinRequest,
    user_id: str = Depends(_get_user_id),
):
    """Join or refresh presence in a shared collaboration workspace."""
    try:
        actor_id = request.actor_id or user_id
        actor_name = _resolve_collab_actor_name(request.actor_name, user_id)
        return collaboration_service.join_workspace(
            workspace_id=request.workspace_id,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=request.actor_role,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to join workspace: {str(e)}")


@router.get("/collaboration/state", response_model=CollaborationStateResponse)
async def get_collaboration_state(
    workspace_id: str,
    since_sequence: int = 0,
    limit: int = 50,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    user_id: str = Depends(_get_user_id),
):
    """Poll incremental collaboration events plus active participant presence."""
    try:
        resolved_actor_id = actor_id or user_id
        resolved_actor_name = _resolve_collab_actor_name(actor_name, user_id)
        return collaboration_service.get_state(
            workspace_id=workspace_id,
            since_sequence=since_sequence,
            limit=limit,
            actor_id=resolved_actor_id,
            actor_name=resolved_actor_name,
            actor_role=CollaborationRole.USER,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch collaboration state: {str(e)}")


@router.post("/collaboration/context", response_model=CollaborationContextPublishResponse)
async def publish_collaboration_context(
    request: CollaborationContextPublishRequest,
    user_id: str = Depends(_get_user_id),
):
    """Publish user or AI context updates into shared workspace stream."""
    if request.event_type in {CollaborationEventType.FILE_SYNC, CollaborationEventType.FILE_DELETED}:
        raise HTTPException(status_code=400, detail="Use file APIs for file sync events.")

    try:
        actor_id = request.actor_id or user_id
        actor_name = _resolve_collab_actor_name(request.actor_name, user_id)
        event = collaboration_service.publish_event(
            workspace_id=request.workspace_id,
            event_type=request.event_type,
            actor_id=actor_id,
            actor_name=actor_name,
            actor_role=request.actor_role,
            file_id=request.file_id,
            file_key=request.file_key,
            payload={
                "message": request.message,
                "metadata": request.metadata,
            },
        )
        return CollaborationContextPublishResponse(success=True, event=event)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to publish context: {str(e)}")

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
    user_id: str = Depends(_get_user_id),
    x_collab_workspace_id: Optional[str] = Header(default=None, alias="X-Collab-Workspace-Id"),
    x_collab_actor_id: Optional[str] = Header(default=None, alias="X-Collab-Actor-Id"),
    x_collab_actor_name: Optional[str] = Header(default=None, alias="X-Collab-Actor-Name"),
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

        # Track initial version snapshot for newly created files.
        if not bool(f.get('is_folder')):
            try:
                version_intelligence_service.track_version(
                    user_id=user_id,
                    file_id=file_id,
                    content=file.content,
                    language=file.language,
                    reason="file_created",
                )
            except Exception:
                pass

        if x_collab_workspace_id and not bool(f.get('is_folder')):
            try:
                collaboration_service.publish_file_sync(
                    workspace_id=x_collab_workspace_id,
                    actor_id=x_collab_actor_id or user_id,
                    actor_name=_resolve_collab_actor_name(x_collab_actor_name, user_id),
                    actor_role=CollaborationRole.USER,
                    file_id=f.get('id'),
                    file_key=_build_file_key(f.get('path') or '/', f.get('filename') or ''),
                    filename=f.get('filename') or '',
                    path=f.get('path') or '/',
                    language=f.get('language') or file.language,
                    content=f.get('content') or '',
                    updated_at=f.get('updated_at') or now,
                )
            except Exception:
                pass
        
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
    user_id: str = Depends(_get_user_id),
    x_collab_workspace_id: Optional[str] = Header(default=None, alias="X-Collab-Workspace-Id"),
    x_collab_actor_id: Optional[str] = Header(default=None, alias="X-Collab-Actor-Id"),
    x_collab_actor_name: Optional[str] = Header(default=None, alias="X-Collab-Actor-Name"),
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

        existing_file = existing.data[0]
        existing_content = str(existing_file.get('content') or '')
        existing_language = str(existing_file.get('language') or 'plaintext')
        existing_filename = str(existing_file.get('filename') or '')
        
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

        # Track version snapshots for content edits and structural changes.
        try:
            version_intelligence_service.track_version(
                user_id=user_id,
                file_id=file_id,
                content=existing_content,
                language=existing_language,
                reason="before_update",
            )

            reason = "file_content_updated"
            if update.filename is not None and update.filename != existing_filename:
                reason = "file_renamed"
            if update.language is not None and update.language != existing_language:
                reason = "language_changed"

            version_intelligence_service.track_version(
                user_id=user_id,
                file_id=file_id,
                content=f.get('content') or '',
                language=f.get('language') or existing_language,
                reason=reason,
            )
        except Exception:
            pass

        if x_collab_workspace_id and not bool(f.get('is_folder')):
            try:
                collaboration_service.publish_file_sync(
                    workspace_id=x_collab_workspace_id,
                    actor_id=x_collab_actor_id or user_id,
                    actor_name=_resolve_collab_actor_name(x_collab_actor_name, user_id),
                    actor_role=CollaborationRole.USER,
                    file_id=f.get('id'),
                    file_key=_build_file_key(f.get('path') or '/', f.get('filename') or ''),
                    filename=f.get('filename') or existing_filename,
                    path=f.get('path') or existing_file.get('path') or '/',
                    language=f.get('language') or existing_language,
                    content=f.get('content') or '',
                    updated_at=f.get('updated_at') or update_data['updated_at'],
                )
            except Exception:
                pass
        
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
    user_id: str = Depends(_get_user_id),
    x_collab_workspace_id: Optional[str] = Header(default=None, alias="X-Collab-Workspace-Id"),
    x_collab_actor_id: Optional[str] = Header(default=None, alias="X-Collab-Actor-Id"),
    x_collab_actor_name: Optional[str] = Header(default=None, alias="X-Collab-Actor-Name"),
):
    """Delete a code file."""
    if not supabase:
        raise HTTPException(
            status_code=503,
            detail="Database not available"
        )
    
    try:
        # Check file exists
        existing = supabase.table('code_files').select('id, filename, path, is_folder').eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        if not existing.data:
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )
        
        filename = existing.data[0]['filename']
        file_path = existing.data[0].get('path') or '/'
        
        # Delete the file
        supabase.table('code_files').delete().eq(
            'id', file_id
        ).eq('user_id', user_id).execute()
        
        # If it was a folder, also delete children
        if existing.data[0]['is_folder']:
            supabase.table('code_files').delete().eq(
                'parent_id', file_id
            ).eq('user_id', user_id).execute()

        if x_collab_workspace_id:
            try:
                collaboration_service.publish_file_deleted(
                    workspace_id=x_collab_workspace_id,
                    actor_id=x_collab_actor_id or user_id,
                    actor_name=_resolve_collab_actor_name(x_collab_actor_name, user_id),
                    file_id=file_id,
                    file_key=_build_file_key(file_path, filename),
                    filename=filename,
                    path=file_path,
                )
            except Exception:
                pass
        
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
    user_id: str = Depends(_get_user_id),
    x_collab_workspace_id: Optional[str] = Header(default=None, alias="X-Collab-Workspace-Id"),
    x_collab_actor_id: Optional[str] = Header(default=None, alias="X-Collab-Actor-Id"),
    x_collab_actor_name: Optional[str] = Header(default=None, alias="X-Collab-Actor-Name"),
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

                try:
                    version_intelligence_service.track_version(
                        user_id=user_id,
                        file_id=f['id'],
                        content=file_item.content,
                        language=language,
                        reason="file_imported",
                    )
                except Exception:
                    pass

                if x_collab_workspace_id:
                    try:
                        collaboration_service.publish_file_sync(
                            workspace_id=x_collab_workspace_id,
                            actor_id=x_collab_actor_id or user_id,
                            actor_name=_resolve_collab_actor_name(x_collab_actor_name, user_id),
                            actor_role=CollaborationRole.USER,
                            file_id=f.get('id'),
                            file_key=_build_file_key(f.get('path') or '/', f.get('filename') or ''),
                            filename=f.get('filename') or file_item.filename,
                            path=f.get('path') or file_item.path,
                            language=f.get('language') or language,
                            content=f.get('content') or file_item.content,
                            updated_at=f.get('updated_at') or now,
                        )
                    except Exception:
                        pass
        except Exception as e:
            errors.append(f"{file_item.filename}: {str(e)}")
    
    return CodeFileImportResponse(
        success=len(imported_files) > 0,
        imported_count=len(imported_files),
        files=imported_files,
        errors=errors if errors else None
    )


@router.get("/files/{file_id}/versions", response_model=CodeVersionHistoryResponse)
async def list_file_versions(
    file_id: str,
    user_id: str = Depends(_get_user_id),
    limit: int = 30,
):
    """List tracked versions for a file (newest first)."""
    safe_limit = max(1, min(int(limit), settings.VERSION_INTELLIGENCE_MAX_LIST_LIMIT))
    try:
        return version_intelligence_service.list_versions(
            user_id=user_id,
            file_id=file_id,
            limit=safe_limit,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list versions: {str(e)}")


@router.get("/files/{file_id}/versions/{version_id}", response_model=CodeVersionSnapshotResponse)
async def get_file_version(
    file_id: str,
    version_id: str,
    user_id: str = Depends(_get_user_id),
):
    """Get a specific version snapshot for a file."""
    try:
        snapshot = version_intelligence_service.get_version_snapshot(
            user_id=user_id,
            file_id=file_id,
            version_id=version_id,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch version: {str(e)}")

    if not snapshot:
        raise HTTPException(status_code=404, detail="Version not found")

    return snapshot


@router.post("/versions/compare", response_model=CodeVersionCompareResponse)
async def compare_versions(
    request: CodeVersionCompareRequest,
    user_id: str = Depends(_get_user_id),
):
    """Compare two versions and return unified diff + impact summary."""
    try:
        return version_intelligence_service.compare_versions(user_id=user_id, request=request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to compare versions: {str(e)}")


@router.post("/versions/why-broke", response_model=CodeBreakAnalysisResponse)
async def why_did_this_break(
    request: CodeBreakAnalysisRequest,
    user_id: str = Depends(_get_user_id),
):
    """Analyze recent version changes and answer: Why did this break?"""
    try:
        return version_intelligence_service.why_did_this_break(user_id=user_id, request=request)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Break analysis failed: {str(e)}")


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


@router.post("/task-mode", response_model=TaskModeResponse)
async def task_mode_build(
    request: TaskModeRequest,
    user_id: str = Depends(_get_user_id),
):
    """AI Project Builder endpoint: creates and updates step-wise feature plans."""
    return await code_workspace_controller.task_mode_build(request, user_id=user_id)


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
