from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class ChatRequest(BaseModel):
    """
    Schema for incoming chat messages.
    """
    message: str = Field(..., description="The user's message to the chatbot.")

class ChatResponse(BaseModel):
    """
    Schema for the chatbot's response.
    """
    response: str = Field(..., description="The AI-generated response.")
    ethical_perspectives: Optional[dict] = Field(None, description="Ethical analysis of the response.")
    audit_results: Optional[dict] = Field(None, description="AI ethics audit evaluation.")
    perspective_autopsy: Optional[dict] = Field(None, description="Detailed cognitive analysis of the user's query.")

class ConversationEntry(BaseModel):
    """
    Schema for a conversation stored in the database.
    """
    id: Optional[str] = None
    user_id: str
    message: str
    response: str
    created_at: Optional[datetime] = None
