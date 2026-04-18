"""
code_workspace_routes.py - Standalone routes for the AI code workspace.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header

from app.controllers.code_workspace_controller import code_workspace_controller
from app.core.config import settings
from app.schemas.code import (
    CodeAssistRequest,
    CodeAssistResponse,
    CodeAutocompleteRequest,
    CodeAutocompleteResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
)


router = APIRouter(tags=["Code Workspace"])


def _resolve_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    authorization: Optional[str] = Header(default=None, alias="Authorization"),
) -> str:
    """Resolve user identity with safe fallback to mock mode."""
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()

    # Future-ready hook: parse Authorization/JWT when backend auth is enabled.
    if authorization and authorization.startswith("Bearer "):
        pass

    return settings.MOCK_USER_ID


@router.post("/code-assist", response_model=CodeAssistResponse)
async def post_code_assist(
    request: CodeAssistRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint requested by spec: POST /code-assist."""
    return await code_workspace_controller.assist(request, user_id=user_id)


@router.post("/api/v1/code/code-assist", response_model=CodeAssistResponse)
async def post_code_assist_versioned(
    request: CodeAssistRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for frontend API clients."""
    return await code_workspace_controller.assist(request, user_id=user_id)


@router.post("/api/v1/code/autocomplete", response_model=CodeAutocompleteResponse)
async def post_code_autocomplete(
    request: CodeAutocompleteRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """LLM-backed autocomplete endpoint."""
    return await code_workspace_controller.autocomplete(request, user_id=user_id)


@router.post("/api/v1/code/execute", response_model=CodeExecutionResponse)
async def post_code_execute(request: CodeExecutionRequest):
    """Sandboxed execution endpoint."""
    return await code_workspace_controller.execute(request)
