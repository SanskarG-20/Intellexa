"""
code_workspace_controller.py - Controller layer for code workspace APIs.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.schemas.code import (
    CodeAssistRequest,
    CodeAssistResponse,
    CodeAutocompleteRequest,
    CodeAutocompleteResponse,
    CodeExecutionRequest,
    CodeExecutionResponse,
)
from app.services.code_workspace.code_service import code_workspace_code_service
from app.services.code_workspace.execution_service import code_execution_service
from app.services.memory.agentic_memory_service import agentic_memory_service


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
                    "action": request.action,
                    "context_used": bool(response.context_used),
                    "context_sources": response.context_sources,
                },
            )
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


code_workspace_controller = CodeWorkspaceController()
