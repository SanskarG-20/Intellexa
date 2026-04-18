"""
project_context.py - API routes for project-level context indexing.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.project_context import ProjectContextResponse
from app.services.project_context_service import project_context_service


router = APIRouter(tags=["Project Context"])


@router.get("/project-context", response_model=ProjectContextResponse)
async def get_project_context(
    refresh: bool = Query(default=False, description="Force re-scan even if cache is warm."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    limit: int = Query(default=200, ge=1, le=2000, description="Pagination size."),
    include_embeddings: Optional[bool] = Query(
        default=None,
        description="Override default embedding inclusion in response.",
    ),
):
    """Return parsed project context for AI awareness beyond the active file."""
    payload = await project_context_service.get_project_context(
        refresh=refresh,
        offset=offset,
        limit=limit,
        include_embeddings=include_embeddings,
    )
    return ProjectContextResponse(**payload)


@router.get("/api/v1/project-context", response_model=ProjectContextResponse)
async def get_project_context_versioned(
    refresh: bool = Query(default=False, description="Force re-scan even if cache is warm."),
    offset: int = Query(default=0, ge=0, description="Pagination offset."),
    limit: int = Query(default=200, ge=1, le=2000, description="Pagination size."),
    include_embeddings: Optional[bool] = Query(
        default=None,
        description="Override default embedding inclusion in response.",
    ),
):
    """Versioned alias for clients already under /api/v1 namespace."""
    payload = await project_context_service.get_project_context(
        refresh=refresh,
        offset=offset,
        limit=limit,
        include_embeddings=include_embeddings,
    )
    return ProjectContextResponse(**payload)
