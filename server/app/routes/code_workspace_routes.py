"""
code_workspace_routes.py - Standalone routes for the AI code workspace.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException

from app.controllers.code_workspace_controller import code_workspace_controller
from app.core.config import settings
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
    BugPredictionRequest,
    BugPredictionResponse,
    CodeAssistRequest,
    CodeAssistResponse,
    CodeAutocompleteRequest,
    CodeAutocompleteResponse,
    CodeVersionCompareRequest,
    CodeVersionCompareResponse,
    CodeVersionHistoryResponse,
    CodeVersionSnapshotResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
    LearningModeRequest,
    LearningModeResponse,
    ProjectRefactorRequest,
    ProjectRefactorResponse,
    TaskModeRequest,
    TaskModeResponse,
)
from app.services.code_workspace.collaboration_service import collaboration_service
from app.services.code_workspace.version_intelligence_service import version_intelligence_service


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


def _resolve_collab_actor_name(preferred: Optional[str], fallback: str) -> str:
    normalized = str(preferred or "").strip()
    if normalized:
        return normalized
    return str(fallback or "Collaborator")


@router.post("/collaboration/join", response_model=CollaborationJoinResponse)
async def post_collaboration_join(
    request: CollaborationJoinRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for joining collaboration workspace presence."""
    try:
        return collaboration_service.join_workspace(
            workspace_id=request.workspace_id,
            actor_id=request.actor_id or user_id,
            actor_name=_resolve_collab_actor_name(request.actor_name, user_id),
            actor_role=request.actor_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Collaboration join failed: {str(exc)}") from exc


@router.post("/api/v1/code/collaboration/join", response_model=CollaborationJoinResponse)
async def post_collaboration_join_versioned(
    request: CollaborationJoinRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for joining collaboration workspace presence."""
    return await post_collaboration_join(request, user_id=user_id)


@router.get("/collaboration/state", response_model=CollaborationStateResponse)
async def get_collaboration_state(
    workspace_id: str,
    since_sequence: int = 0,
    limit: int = 50,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for collaboration incremental state polling."""
    try:
        return collaboration_service.get_state(
            workspace_id=workspace_id,
            since_sequence=since_sequence,
            limit=limit,
            actor_id=actor_id or user_id,
            actor_name=_resolve_collab_actor_name(actor_name, user_id),
            actor_role=CollaborationRole.USER,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Collaboration state failed: {str(exc)}") from exc


@router.get("/api/v1/code/collaboration/state", response_model=CollaborationStateResponse)
async def get_collaboration_state_versioned(
    workspace_id: str,
    since_sequence: int = 0,
    limit: int = 50,
    actor_id: Optional[str] = None,
    actor_name: Optional[str] = None,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for collaboration incremental state polling."""
    return await get_collaboration_state(
        workspace_id=workspace_id,
        since_sequence=since_sequence,
        limit=limit,
        actor_id=actor_id,
        actor_name=actor_name,
        user_id=user_id,
    )


@router.post("/collaboration/context", response_model=CollaborationContextPublishResponse)
async def post_collaboration_context(
    request: CollaborationContextPublishRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for publishing shared user/AI context updates."""
    if request.event_type in {CollaborationEventType.FILE_SYNC, CollaborationEventType.FILE_DELETED}:
        raise HTTPException(status_code=400, detail="Use file APIs for file sync events.")

    try:
        event = collaboration_service.publish_event(
            workspace_id=request.workspace_id,
            event_type=request.event_type,
            actor_id=request.actor_id or user_id,
            actor_name=_resolve_collab_actor_name(request.actor_name, user_id),
            actor_role=request.actor_role,
            file_id=request.file_id,
            file_key=request.file_key,
            payload={
                "message": request.message,
                "metadata": request.metadata,
            },
        )
        return CollaborationContextPublishResponse(success=True, event=event)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Collaboration context failed: {str(exc)}") from exc


@router.post("/api/v1/code/collaboration/context", response_model=CollaborationContextPublishResponse)
async def post_collaboration_context_versioned(
    request: CollaborationContextPublishRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for publishing shared user/AI context updates."""
    return await post_collaboration_context(request, user_id=user_id)


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


@router.post("/bug-predict", response_model=BugPredictionResponse)
async def post_bug_predict(request: BugPredictionRequest):
    """Canonical endpoint for static bug prediction before execution."""
    return await code_workspace_controller.predict_bugs(request)


@router.post("/api/v1/code/bug-predict", response_model=BugPredictionResponse)
async def post_bug_predict_versioned(request: BugPredictionRequest):
    """Versioned alias for static bug prediction."""
    return await code_workspace_controller.predict_bugs(request)


@router.post("/learning-mode", response_model=LearningModeResponse)
async def post_learning_mode(
    request: LearningModeRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for deep educational code explanations."""
    return await code_workspace_controller.learning_mode_explain(request, user_id=user_id)


@router.post("/api/v1/code/learning-mode", response_model=LearningModeResponse)
async def post_learning_mode_versioned(
    request: LearningModeRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for Learning Mode explanations."""
    return await code_workspace_controller.learning_mode_explain(request, user_id=user_id)


@router.post("/project-refactor", response_model=ProjectRefactorResponse)
async def post_project_refactor(
    request: ProjectRefactorRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for project-wide AI refactoring."""
    return await code_workspace_controller.project_refactor(request, user_id=user_id)


@router.post("/api/v1/code/project-refactor", response_model=ProjectRefactorResponse)
async def post_project_refactor_versioned(
    request: ProjectRefactorRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for project-wide AI refactoring."""
    return await code_workspace_controller.project_refactor(request, user_id=user_id)


@router.post("/task-mode", response_model=TaskModeResponse)
async def post_task_mode(
    request: TaskModeRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for AI Project Builder Task Mode."""
    return await code_workspace_controller.task_mode_build(request, user_id=user_id)


@router.post("/api/v1/code/task-mode", response_model=TaskModeResponse)
async def post_task_mode_versioned(
    request: TaskModeRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Versioned alias for AI Project Builder Task Mode."""
    return await code_workspace_controller.task_mode_build(request, user_id=user_id)


@router.get("/version-intelligence/files/{file_id}/versions", response_model=CodeVersionHistoryResponse)
async def get_file_versions(
    file_id: str,
    limit: int = 30,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for tracked file versions."""
    try:
        return version_intelligence_service.list_versions(
            user_id=user_id,
            file_id=file_id,
            limit=limit,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Version listing failed: {str(exc)}") from exc


@router.get(
    "/version-intelligence/files/{file_id}/versions/{version_id}",
    response_model=CodeVersionSnapshotResponse,
)
async def get_file_version(
    file_id: str,
    version_id: str,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for one file version snapshot."""
    try:
        snapshot = version_intelligence_service.get_version_snapshot(
            user_id=user_id,
            file_id=file_id,
            version_id=version_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Version fetch failed: {str(exc)}") from exc

    if not snapshot:
        raise HTTPException(status_code=404, detail="Version not found")

    return snapshot


@router.post("/version-intelligence/compare", response_model=CodeVersionCompareResponse)
async def post_version_compare(
    request: CodeVersionCompareRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for version diff + impact summary."""
    try:
        return version_intelligence_service.compare_versions(user_id=user_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Version compare failed: {str(exc)}") from exc


@router.post("/version-intelligence/why-broke", response_model=CodeBreakAnalysisResponse)
async def post_version_why_broke(
    request: CodeBreakAnalysisRequest,
    user_id: str = Depends(_resolve_user_id),
):
    """Canonical endpoint for answering: Why did this break?"""
    try:
        return version_intelligence_service.why_did_this_break(user_id=user_id, request=request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Break analysis failed: {str(exc)}") from exc
