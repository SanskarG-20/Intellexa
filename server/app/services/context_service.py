from app.db.supabase import supabase
from app.core.config import settings
from typing import List, Dict

class ContextService:
    """
    Service responsible for interacting with the database to retrieve 
    historical context for a given user.
    """
    
    @staticmethod
    async def get_user_context(user_id: str, limit: int = 5) -> str:
        """
        Fetch the last 5 conversations for the user and format 
        them as context for the LLM.
        """
        if not supabase:
            print("Supabase client not initialized. Context retrieval disabled.")
            return ""

        try:
            # Query the 'conversations' table, ordered by created_at descending
            response = supabase.table("conversations")\
                .select("message, response")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .limit(limit)\
                .execute()

            history = response.data
            formatted_context = ""

            # Reverse chronological order as they are retrieved desc but we want 
            # to show history in chronological order.
            for chat in reversed(history):
                formatted_context += f"User: {chat['message']}\n"
                formatted_context += f"Assistant: {chat['response']}\n\n"

            return formatted_context.strip()
            
        except Exception as e:
            # In case of DB failure, we don't block the AI but log the error
            print(f"Error fetching context for user {user_id}: {str(e)}")
            return ""

context_service = ContextService()
