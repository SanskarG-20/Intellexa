"""
code_workspace_controller.py - Controller layer for code workspace APIs.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas.code import (
    BugPredictionRequest,
    BugPredictionResponse,
    CodeAssistRequest,
    CodeAssistResponse,
    CodeAutocompleteRequest,
    CodeAutocompleteResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
    LearningModeRequest,
    LearningModeResponse,
    ProjectRefactorRequest,
    ProjectRefactorResponse,
    TaskModeRequest,
    TaskModeResponse,
)
from app.services.code_workspace.bug_prediction_service import bug_prediction_service
from app.services.code_workspace.code_service import code_workspace_code_service
from app.services.code_workspace.execution_service import code_execution_service
from app.services.code_workspace.project_refactor_service import project_refactor_engine_service
from app.services.code_workspace.task_mode_service import task_mode_service
from app.services.memory.agentic_memory_service import agentic_memory_service
from app.services.memory.user_pattern_service import user_pattern_memory_service


class CodeWorkspaceController:
    """Thin controller that delegates to dedicated services."""

    async def assist(self, request: CodeAssistRequest, user_id: str) -> CodeAssistResponse:
        try:
            response = await code_workspace_code_service.assist(request, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Code assistance failed: {str(exc)}",
            ) from exc

        # Persist code-assist interactions into the agentic memory graph.
        try:
            interaction_metadata = user_pattern_memory_service.build_interaction_metadata(
                query=request.prompt,
                code=request.code,
                language=request.language,
                action=request.action.value,
                suggestions=[item.title for item in (response.suggestions or [])],
            )

            memory_content = (
                f"Code Action: {request.action}\n"
                f"Language: {request.language}\n"
                f"Prompt: {request.prompt}\n"
                f"Original Code:\n{(request.code or '')[:2000]}\n\n"
                f"Updated Code:\n{(response.updated_code or '')[:2000]}\n\n"
                f"Explanation:\n{(response.explanation or '')[:1000]}"
            )
            await agentic_memory_service.create_memory(
                user_id=user_id,
                content=memory_content,
                source_type="code",
                source_id=request.language,
                metadata={
                    "action": request.action.value,
                    "context_used": bool(response.context_used),
                    "context_sources": response.context_sources,
                    **interaction_metadata,
                },
            )
            user_pattern_memory_service.mark_profile_dirty(user_id)
        except Exception:
            # Memory persistence should not break the API response.
            pass

        return response

    async def autocomplete(
        self,
        request: CodeAutocompleteRequest,
        user_id: str,
    ) -> CodeAutocompleteResponse:
        try:
            return await code_workspace_code_service.autocomplete(request, user_id=user_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Autocomplete failed: {str(exc)}",
            ) from exc

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        try:
            return await code_execution_service.execute(request)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Execution failed: {str(exc)}",
            ) from exc

    async def predict_bugs(self, request: BugPredictionRequest) -> BugPredictionResponse:
        try:
            return await bug_prediction_service.predict(request)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Bug prediction failed: {str(exc)}",
            ) from exc

    async def learning_mode_explain(
        self,
        request: LearningModeRequest,
        user_id: str,
    ) -> LearningModeResponse:
        try:
            response = await code_workspace_code_service.learning_mode_explain(
                request,
                user_id=user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Learning mode failed: {str(exc)}",
            ) from exc

        # Persist learning-mode requests for longitudinal learning personalization.
        try:
            interaction_metadata = user_pattern_memory_service.build_interaction_metadata(
                query=request.prompt,
                code=request.code,
                language=request.language,
                action="learning_mode",
                suggestions=list(response.learning_explanation.step_by_step[:5]),
            )

            memory_content = (
                "Code Action: learning_mode\n"
                f"Language: {request.language}\n"
                f"Prompt: {request.prompt}\n"
                f"Code Snippet:\n{request.code[:2000]}\n\n"
                f"Explanation:\n{response.explanation[:1200]}\n\n"
                f"Analogy:\n{response.learning_explanation.real_world_analogy[:500]}"
            )
            await agentic_memory_service.create_memory(
                user_id=user_id,
                content=memory_content,
                source_type="code",
                source_id="learning-mode",
                metadata={
                    "language": request.language,
                    "step_count": len(response.learning_explanation.step_by_step),
                    "logic_points": len(response.learning_explanation.logic_breakdown),
                    "context_used": bool(response.context_used),
                    **interaction_metadata,
                },
            )
            user_pattern_memory_service.mark_profile_dirty(user_id)
        except Exception:
            pass

        return response

    async def project_refactor(
        self,
        request: ProjectRefactorRequest,
        user_id: str,
    ) -> ProjectRefactorResponse:
        try:
            response = await project_refactor_engine_service.refactor_project(
                request,
                user_id=user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Project refactor failed: {str(exc)}",
            ) from exc

        # Persist summary of project-wide refactor into agentic memory.
        try:
            interaction_metadata = user_pattern_memory_service.build_interaction_metadata(
                query=request.instruction,
                code="",
                language="project",
                action="project_refactor",
                suggestions=[item.path for item in response.updated_files[:5]],
            )

            changed_paths = [item.path for item in response.updated_files[:30]]
            memory_content = (
                f"Code Action: project_refactor\n"
                f"Instruction: {request.instruction}\n"
                f"Input Files: {len(request.files)}\n"
                f"Changed Files: {response.changed_files}\n"
                f"Changed Paths: {', '.join(changed_paths)}\n\n"
                f"Explanation:\n{response.explanation[:1500]}"
            )
            await agentic_memory_service.create_memory(
                user_id=user_id,
                content=memory_content,
                source_type="code",
                source_id="project-refactor",
                metadata={
                    "safe_mode": request.safe_mode,
                    "changed_files": response.changed_files,
                    "warnings": response.warnings[:10],
                    **interaction_metadata,
                },
            )
            user_pattern_memory_service.mark_profile_dirty(user_id)
        except Exception:
            # Memory persistence should not block API responses.
            pass

        return response

    async def task_mode_build(
        self,
        request: TaskModeRequest,
        user_id: str,
    ) -> TaskModeResponse:
        try:
            response = await task_mode_service.build_task_mode_response(
                request,
                user_id=user_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Task mode failed: {str(exc)}",
            ) from exc

        # Persist task-mode snapshots for long-running implementation workflows.
        try:
            interaction_metadata = user_pattern_memory_service.build_interaction_metadata(
                query=request.prompt,
                code="",
                language="task_mode",
                action="task_mode",
                suggestions=[item.title for item in response.steps[:5]],
            )

            completed = response.progress.completed_steps
            total = response.progress.total_steps
            active_step_id = response.progress.active_step_id or "none"
            memory_content = (
                "Code Action: task_mode\n"
                f"Prompt: {request.prompt}\n"
                f"Session: {response.task_session_id}\n"
                f"Progress: {completed}/{total}\n"
                f"Active Step: {active_step_id}\n"
                f"Plan Title: {response.title}\n\n"
                f"Summary:\n{response.summary[:1200]}"
            )
            await agentic_memory_service.create_memory(
                user_id=user_id,
                content=memory_content,
                source_type="code",
                source_id=response.task_session_id,
                metadata={
                    "task_mode": True,
                    "completed_steps": completed,
                    "total_steps": total,
                    "active_step_id": response.progress.active_step_id,
                    "next_step_id": response.progress.next_step_id,
                    **interaction_metadata,
                },
            )
            user_pattern_memory_service.mark_profile_dirty(user_id)
        except Exception:
            pass

        return response


code_workspace_controller = CodeWorkspaceController()
