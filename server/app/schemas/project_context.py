"""
project_context.py - Schemas for project-wide context indexing and retrieval.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProjectContextFile(BaseModel):
    """Context record for one source file."""

    file_path: str
    summary: str
    dependencies: List[str] = Field(default_factory=list)
    imports: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    classes: List[str] = Field(default_factory=list)
    embedding: Optional[List[float]] = None


class ProjectContextResponse(BaseModel):
    """Paginated project context response."""

    generated_at: datetime
    cache_hit: bool
    total_files: int
    returned_files: int
    offset: int
    limit: int
    file_structure: Dict[str, Any] = Field(default_factory=dict)
    dependency_mapping: Dict[str, List[str]] = Field(default_factory=dict)
    files: List[ProjectContextFile] = Field(default_factory=list)
