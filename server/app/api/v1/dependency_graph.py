"""
dependency_graph.py - API routes for dependency graph visualization.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from app.schemas.dependency_graph import DependencyGraphResponse
from app.services.dependency_graph_service import dependency_graph_service


router = APIRouter(tags=["Dependency Graph"])


@router.get("/dependency-graph", response_model=DependencyGraphResponse)
async def get_dependency_graph(
    refresh: bool = Query(default=False, description="Force dependency graph rebuild."),
    include_external_nodes: Optional[bool] = Query(
        default=None,
        description="Include unresolved external files/functions in graph.",
    ),
    max_nodes: Optional[int] = Query(
        default=None,
        ge=100,
        le=50000,
        description="Optional node cap for frontend rendering limits.",
    ),
    max_edges: Optional[int] = Query(
        default=None,
        ge=100,
        le=120000,
        description="Optional edge cap for frontend rendering limits.",
    ),
):
    payload = await dependency_graph_service.get_dependency_graph(
        refresh=refresh,
        include_external_nodes=include_external_nodes,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    return DependencyGraphResponse(**payload)


@router.get("/api/v1/dependency-graph", response_model=DependencyGraphResponse)
async def get_dependency_graph_versioned(
    refresh: bool = Query(default=False, description="Force dependency graph rebuild."),
    include_external_nodes: Optional[bool] = Query(
        default=None,
        description="Include unresolved external files/functions in graph.",
    ),
    max_nodes: Optional[int] = Query(
        default=None,
        ge=100,
        le=50000,
        description="Optional node cap for frontend rendering limits.",
    ),
    max_edges: Optional[int] = Query(
        default=None,
        ge=100,
        le=120000,
        description="Optional edge cap for frontend rendering limits.",
    ),
):
    payload = await dependency_graph_service.get_dependency_graph(
        refresh=refresh,
        include_external_nodes=include_external_nodes,
        max_nodes=max_nodes,
        max_edges=max_edges,
    )
    return DependencyGraphResponse(**payload)
