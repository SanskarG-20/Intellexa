from app.db.supabase import supabase
from app.core.config import settings
from typing import List, Dict
from app.services.memory.retrieval_service import retrieval_service


class ContextService:
    """
    Service responsible for interacting with the database to retrieve 
    historical context for a given user.
    Now also supports retrieval from user's personal document memory.
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
    
    @staticmethod
    async def get_user_memory_context(user_id: str, query: str, top_k: int = 5) -> Dict:
        """
        Retrieve relevant context from user's personal documents.
        
        Args:
            user_id: The user's ID
            query: The search query
            top_k: Maximum number of results to return
            
        Returns:
            Dictionary with 'context' string and 'sources' list
        """
        try:
            results = await retrieval_service.retrieve_context(
                query=query,
                user_id=user_id,
                top_k=top_k
            )
            
            if not results:
                return {"context": "", "sources": []}
            
            formatted_context = retrieval_service.format_context_for_prompt(results)
            
            sources = [
                {
                    "filename": r.filename,
                    "file_type": r.file_type,
                    "similarity": r.similarity,
                    "page_number": r.page_number
                }
                for r in results
            ]
            
            return {
                "context": formatted_context,
                "sources": sources
            }
            
        except Exception as e:
            print(f"Error fetching memory context for user {user_id}: {str(e)}")
            return {"context": "", "sources": []}


context_service = ContextService()
