from app.services.llama_service import llama_service
from app.services.autopsy_service import autopsy_service
from app.services.context_service import context_service
from app.services.ethics_service import ethics_service
from app.services.audit_service import audit_service
from app.db.supabase import supabase
from app.core.config import settings

class ChatService:
    """
    Business logic layer orchestrating context retrieval, 
    cognitive analysis (autopsy), LLM generation, and ethical auditing.
    """

    @staticmethod
    async def process_chat(user_id: str, message: str) -> dict:
        """
        Main workflow for processing a chat message.
        """
        # 1. Perspective Autopsy - intensive analysis of the user's thinking
        autopsy_res = await autopsy_service.perform_autopsy(message)

        # 2. Retrieve historical context
        context = await context_service.get_user_context(user_id, limit=5)
        
        # 3. Build the system prompt for Llama
        system_prompt = (
            "You are Intellexa Core, a sophisticated AI assistant designed "
            "to provide ethical, context-aware, and helpful responses.\n\n"
        )
        if context:
            system_prompt += f"Here is the recent conversation history for context:\n{context}\n"

        # 4. Generate base response using Llama 3.1
        ai_response = await llama_service.get_ai_response(message, system_prompt=system_prompt)

        # 5. Generate ethical perspectives using the reasoning engine (Gemini)
        ethical_p = await ethics_service.get_ethical_perspectives(ai_response)

        # 6. Audit the response for bias and harmful assumptions (Gemini)
        audit_res = await audit_service.audit_response(ai_response)

        # 7. Save the conversation main response
        if supabase:
            try:
                supabase.table("conversations").insert({
                    "user_id": user_id,
                    "message": message,
                    "response": ai_response
                }).execute()
            except Exception as e:
                print(f"Failed to save conversation: {str(e)}")

        return {
            "response": ai_response,
            "ethical_perspectives": ethical_p,
            "audit_results": audit_res,
            "perspective_autopsy": autopsy_res
        }

chat_service = ChatService()
