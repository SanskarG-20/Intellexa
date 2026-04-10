from fastapi import APIRouter, HTTPException

from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import chat_service
from app.services.llama_service import LlamaService
from app.services.ethics_service import EthicsService

from app.services.autopsy_service import AutopsyService
from app.services.ethics_service import EthicsService
from app.services.audit_service import AuditService

router = APIRouter(prefix="/api/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Primary chat endpoint for Intellexa Core.
    Accepts a user message and returns a context-aware AI response 
    augmented with perspective autopsy, ethical perspectives, and bias auditing.
    """
    try:
        user_id = settings.MOCK_USER_ID
        result = await chat_service.process_chat(user_id, request.message)
        return ChatResponse(**result)
    except (LlamaService.AIServiceError, EthicsService.AIServiceError, AuditService.AIServiceError, AutopsyService.AIServiceError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while processing your request: {str(exc)}",
        )
