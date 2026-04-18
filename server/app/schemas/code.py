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
MAX_PROJECT_REFACTOR_FILES = 200
MAX_PROJECT_REFACTOR_FILE_CHARS = 120000
MAX_PROJECT_REFACTOR_TOTAL_CHARS = 1200000
MAX_PROJECT_REFACTOR_INSTRUCTION_CHARS = 4000
MAX_LEARNING_STEPS = 10
MAX_LEARNING_LOGIC_ITEMS = 8


class CodeAction(str, Enum):
    """Available code assistant actions."""
    EXPLAIN = "explain"
    GENERATE = "generate"
    FIX = "fix"
    REFACTOR = "refactor"


class BugSeverity(str, Enum):
    """Severity levels for bug prediction warnings."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


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
    learning_mode: bool = Field(
        default=False,
        description="Enable deep educational explanation mode for code understanding",
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


class CodeLearningExplanation(BaseModel):
    """Structured learning-oriented explanation payload for code."""

    step_by_step: List[str] = Field(default_factory=list, max_length=MAX_LEARNING_STEPS)
    logic_breakdown: List[str] = Field(default_factory=list, max_length=MAX_LEARNING_LOGIC_ITEMS)
    real_world_analogy: str = Field(default="")


class LearningModeRequest(BaseModel):
    """Request schema for dedicated learning mode endpoint."""

    code: str = Field(
        ...,
        min_length=1,
        max_length=MAX_CODE_ASSIST_CODE_CHARS,
        description="Code snippet to explain",
    )
    language: str = Field(default="javascript", max_length=50)
    prompt: str = Field(
        default="Explain this code deeply for learning.",
        max_length=MAX_CODE_ASSIST_PROMPT_CHARS,
    )
    include_context: bool = Field(default=True)
    context: Optional[str] = Field(default=None, max_length=MAX_CODE_ASSIST_CONTEXT_CHARS)

    @field_validator("prompt")
    @classmethod
    def normalize_prompt(cls, value: str) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        return normalized or "Explain this code deeply for learning."


class LearningModeResponse(BaseModel):
    """Response schema for dedicated learning mode endpoint."""

    explanation: str
    learning_explanation: CodeLearningExplanation
    warnings: List[str] = Field(default_factory=list)
    context_used: bool = False
    context_sources: List[str] = Field(default_factory=list)
    language: str
    cached: bool = False


class BugPredictionWarning(BaseModel):
    """One static-analysis warning produced by bug prediction engine."""

    category: str = Field(..., description="null-issue | async-problem | edge-case")
    message: str
    severity: BugSeverity
    line: Optional[int] = None
    snippet: Optional[str] = None


class BugPredictionRequest(BaseModel):
    """Input payload for bug prediction analysis."""

    code: str = Field(..., min_length=1, max_length=MAX_CODE_ASSIST_CODE_CHARS)
    language: str = Field(default="javascript", max_length=50)
    filename: Optional[str] = Field(default=None, max_length=255)

    @field_validator("language")
    @classmethod
    def normalize_language(cls, value: str) -> str:
        return str(value or "javascript").strip().lower()


class BugPredictionResponse(BaseModel):
    """Output payload for bug prediction analysis."""

    warnings: List[BugPredictionWarning] = Field(default_factory=list)
    severity: BugSeverity = BugSeverity.NONE


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
    learning_mode: bool = False
    learning_explanation: Optional[CodeLearningExplanation] = None
    warnings: List[str] = Field(default_factory=list)
    cached: bool = False


class ProjectRefactorFile(BaseModel):
    """One project file supplied to the project refactor engine."""

    path: str = Field(..., min_length=1, max_length=500)
    content: str = Field(default="", max_length=MAX_PROJECT_REFACTOR_FILE_CHARS)
    language: Optional[str] = Field(default=None, max_length=50)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = str(value or "").strip().replace("\\", "/")
        if not normalized:
            raise ValueError("path must not be empty")
        if normalized.startswith("/"):
            normalized = normalized.lstrip("/")
        if ".." in normalized.split("/"):
            raise ValueError("path cannot contain parent traversal")
        return normalized


class ProjectRefactorRequest(BaseModel):
    """Request schema for codebase-level refactoring."""

    files: List[ProjectRefactorFile] = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_REFACTOR_FILES,
        description="Project files to refactor",
    )
    instruction: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROJECT_REFACTOR_INSTRUCTION_CHARS,
        description="Refactor directive from the user",
    )
    safe_mode: bool = Field(
        default=True,
        description="Enable conservative protections to avoid breaking changes",
    )
    include_explanation: bool = Field(default=True)
    max_files_to_update: int = Field(default=40, ge=1, le=MAX_PROJECT_REFACTOR_FILES)

    @field_validator("instruction")
    @classmethod
    def validate_instruction(cls, value: str) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        if not normalized:
            raise ValueError("instruction must not be empty")
        return normalized

    @field_validator("files")
    @classmethod
    def validate_files(cls, values: List[ProjectRefactorFile]) -> List[ProjectRefactorFile]:
        seen = set()
        total_chars = 0

        for file_item in values:
            if file_item.path in seen:
                raise ValueError(f"duplicate path found: {file_item.path}")
            seen.add(file_item.path)
            total_chars += len(file_item.content or "")

        if total_chars > MAX_PROJECT_REFACTOR_TOTAL_CHARS:
            raise ValueError(
                f"Total content size exceeds limit of {MAX_PROJECT_REFACTOR_TOTAL_CHARS} characters"
            )

        return values


class ProjectRefactorUpdatedFile(BaseModel):
    """One updated file returned by project refactor engine."""

    path: str
    content: str
    change_summary: str = Field(default="")
    safe: bool = True


class ProjectRefactorResponse(BaseModel):
    """Response payload for project refactor engine."""

    updated_files: List[ProjectRefactorUpdatedFile] = Field(default_factory=list)
    explanation: str
    warnings: List[str] = Field(default_factory=list)
    total_input_files: int = 0
    changed_files: int = 0
    safe_mode: bool = True
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
