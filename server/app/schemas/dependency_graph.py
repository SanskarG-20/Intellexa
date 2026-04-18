"""
dependency_graph.py - Schemas for dependency graph visualization.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class DependencyGraphNode(BaseModel):
    id: str
    label: str
    type: Literal["file", "function", "external"]
    group: Optional[str] = None
    file_path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DependencyGraphEdge(BaseModel):
    id: str
    source: str
    target: str
    relation_type: Literal["imports", "defines", "calls"]
    weight: float = 1.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DependencyGraphResponse(BaseModel):
    generated_at: datetime
    cache_hit: bool
    truncated: bool
    node_count: int
    edge_count: int
    nodes: List[DependencyGraphNode] = Field(default_factory=list)
    edges: List[DependencyGraphEdge] = Field(default_factory=list)
    file_dependency_mapping: Dict[str, List[str]] = Field(default_factory=dict)
    function_dependency_mapping: Dict[str, List[str]] = Field(default_factory=dict)
    legend: Dict[str, str] = Field(default_factory=dict)
