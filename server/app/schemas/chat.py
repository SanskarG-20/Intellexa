from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional

class ChatRequest(BaseModel):
    """
    Schema for incoming chat messages.
    """
    message: str = Field(..., description="The user's message to the chatbot.")

class ChatResponse(BaseModel):
    """
    Schema for the chatbot's response.
    """
    perspective_autopsy: Optional[dict] = Field(None, description="Detailed cognitive analysis of the user's query.")
    answer: Optional[dict] = Field(None, description="Multi-perspective answer object.")
    explanation: Optional[List[str]] = Field(None, description="Explanation bullets for how the answer was built.")
    ethical_check: Optional[dict] = Field(None, description="Ethical safety check output.")
    trust_score: Optional[int] = Field(None, description="Deterministic trust score from 0 to 100.")
    confidence: Optional[str] = Field(None, description="Confidence label: low, medium, or high.")

    # Additional compatibility fields used by other server variants.
    trust_evaluation: Optional[dict] = Field(None, description="Compatibility trust object.")
    neutral_reframe: Optional[dict] = Field(None, description="Compatibility neutral reframe payload.")

    # Legacy compatibility fields kept to avoid breaking existing clients.
    response: str = Field(..., description="Primary AI-generated response text.")
    ethical_perspectives: Optional[dict] = Field(None, description="Legacy field retained for compatibility.")
    audit_results: Optional[dict] = Field(None, description="Legacy field retained for compatibility.")

class ConversationEntry(BaseModel):
    """
    Schema for a conversation stored in the database.
    """
    id: Optional[str] = None
    user_id: str
    message: str
    response: str
    created_at: Optional[datetime] = None
