"""
code.py - Code Space Schemas
Pydantic models for Code Space API request/response validation.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


MAX_CODE_ASSIST_PROMPT_CHARS = 4000
MAX_CODE_ASSIST_CODE_CHARS = 120000
MAX_CODE_ASSIST_CONTEXT_CHARS = 8000
MAX_AUTOCOMPLETE_SUGGESTIONS = 10
MAX_EXECUTION_CODE_CHARS = 20000
MAX_EXECUTION_STDIN_CHARS = 4000


class CodeAction(str, Enum):
    """Available code assistant actions."""
    EXPLAIN = "explain"
    GENERATE = "generate"
    FIX = "fix"
    REFACTOR = "refactor"


# ============================================================================
# File Schemas
# ============================================================================

class CodeFileBase(BaseModel):
    """Base schema for code files."""
    filename: str = Field(..., min_length=1, max_length=255)
    path: str = Field(default="/", max_length=500)
    language: str = Field(default="javascript", max_length=50)
    is_folder: bool = Field(default=False)


class CodeFileCreate(CodeFileBase):
    """Schema for creating a new code file."""
    content: str = Field(default="")
    parent_id: Optional[str] = None


class CodeFileUpdate(BaseModel):
    """Schema for updating an existing code file."""
    filename: Optional[str] = Field(None, min_length=1, max_length=255)
    content: Optional[str] = None
    language: Optional[str] = Field(None, max_length=50)


class CodeFileInfo(BaseModel):
    """Schema for code file info (list view)."""
    id: str
    filename: str
    path: str
    language: str
    is_folder: bool
    parent_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


class CodeFileDetail(CodeFileInfo):
    """Schema for detailed code file view."""
    content: str


class CodeFileListResponse(BaseModel):
    """Response schema for listing code files."""
    files: List[CodeFileInfo]
    total: int


class CodeFileDeleteResponse(BaseModel):
    """Response schema for deleting a code file."""
    success: bool
    file_id: str
    message: str


class CodeFileImportItem(BaseModel):
    """Schema for a single file in import batch."""
    filename: str
    path: str
    content: str
    language: str = "javascript"


class CodeFileImportRequest(BaseModel):
    """Schema for importing multiple files."""
    files: List[CodeFileImportItem]


class CodeFileImportResponse(BaseModel):
    """Response schema for import operation."""
    success: bool
    imported_count: int
    files: List[CodeFileInfo]
    errors: Optional[List[str]] = None


# ============================================================================
# Code Assist Schemas
# ============================================================================

class CodeAssistRequest(BaseModel):
    """Schema for code assistance request."""
    code: str = Field(
        default="",
        max_length=MAX_CODE_ASSIST_CODE_CHARS,
        description="Current code in editor",
    )
    language: str = Field(default="javascript", max_length=50, description="Programming language")
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CODE_ASSIST_PROMPT_CHARS,
        description="User instruction or question",
    )
    action: CodeAction = Field(default=CodeAction.EXPLAIN, description="Type of assistance")
    include_context: bool = Field(default=True, description="Whether to include RAG context")
    context: Optional[str] = Field(
        default=None,
        max_length=MAX_CODE_ASSIST_CONTEXT_CHARS,
        description="Optional additional context provided by the client",
    )
    max_suggestions: int = Field(default=5, ge=1, le=10, description="Max suggestions in response")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        if not normalized:
            raise ValueError("prompt must not be empty")
        return normalized


class CodeSuggestion(BaseModel):
    """A single code suggestion."""
    title: str
    description: str
    code_snippet: Optional[str] = None


class CodeAssistResponse(BaseModel):
    """Schema for code assistance response."""
    updated_code: Optional[str] = None
    improved_code: Optional[str] = None
    explanation: str
    suggestions: List[CodeSuggestion] = Field(default_factory=list)
    context_used: bool = False
    context_sources: List[str] = Field(default_factory=list)
    action: CodeAction
    language: str
    warnings: List[str] = Field(default_factory=list)
    cached: bool = False


class CodeAutocompleteRequest(BaseModel):
    """Schema for autocomplete requests."""
    code: str = Field(default="", max_length=MAX_CODE_ASSIST_CODE_CHARS)
    language: str = Field(default="javascript", max_length=50)
    cursor_line: int = Field(default=1, ge=1, le=200000)
    cursor_column: int = Field(default=1, ge=1, le=5000)
    max_suggestions: int = Field(default=3, ge=1, le=MAX_AUTOCOMPLETE_SUGGESTIONS)
    context: Optional[str] = Field(default=None, max_length=MAX_CODE_ASSIST_CONTEXT_CHARS)


class CodeAutocompleteItem(BaseModel):
    """One autocomplete candidate."""
    label: str = Field(..., min_length=1, max_length=60)
    insert_text: str = Field(..., min_length=1, max_length=500)
    detail: str = Field(default="AI suggestion", max_length=160)


class CodeAutocompleteResponse(BaseModel):
    """Autocomplete API response."""
    suggestions: List[CodeAutocompleteItem] = Field(default_factory=list)
    context_used: bool = False
    context_sources: List[str] = Field(default_factory=list)
    cached: bool = False


class CodeExecutionRequest(BaseModel):
    """Schema for sandboxed code execution requests."""
    code: str = Field(..., min_length=1, max_length=MAX_EXECUTION_CODE_CHARS)
    language: str = Field(default="python", max_length=32)
    stdin: str = Field(default="", max_length=MAX_EXECUTION_STDIN_CHARS)
    timeout_ms: int = Field(default=3000, ge=200, le=30000)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return str(value or "python").strip().lower()


class CodeExecutionResult(BaseModel):
    """Execution output payload."""
    stdout: str
    stderr: str
    exit_code: Optional[int] = None
    timed_out: bool = False
    runtime_ms: int = 0
    output_truncated: bool = False


class CodeExecutionResponse(BaseModel):
    """Sandbox execution response."""
    success: bool
    result: CodeExecutionResult
    error: Optional[str] = None


# ============================================================================
# Code History Schemas
# ============================================================================

class CodeHistoryEntry(BaseModel):
    """Schema for a code history entry."""
    id: str
    file_id: str
    action: str
    timestamp: datetime
    content_preview: Optional[str] = None


class CodeHistoryResponse(BaseModel):
    """Response schema for code history."""
    entries: List[CodeHistoryEntry]
    total: int
