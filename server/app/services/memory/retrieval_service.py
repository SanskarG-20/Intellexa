"""
retrieval_service.py - Vector Similarity Search
Retrieves relevant document chunks using pgvector similarity search.
"""

from typing import List, Optional
from dataclasses import dataclass

from app.db.supabase import supabase
from app.core.config import settings
from app.services.memory.embedding_service import embedding_service


@dataclass
class RetrievedContext:
    """Represents a retrieved context chunk."""
    chunk_id: str
    document_id: str
    content: str
    filename: str
    file_type: str
    similarity: float
    page_number: Optional[int] = None


class RetrievalServiceError(Exception):
    """Custom exception for retrieval service errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class RetrievalService:
    """
    Handles retrieval of relevant document chunks using pgvector.
    Performs similarity search against user's stored embeddings.
    """
    
    def __init__(self):
        self.embedding_service = embedding_service
    
    async def retrieve_context(
        self,
        query: str,
        user_id: str,
        top_k: int = 5
    ) -> List[RetrievedContext]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The search query
            user_id: The user's ID
            top_k: Maximum number of results to return
            
        Returns:
            List of RetrievedContext objects
            
        Raises:
            RetrievalServiceError: If retrieval fails
        """
        if not supabase:
            print("[RetrievalService] Supabase client not initialized")
            return []
        
        if not query or not query.strip():
            return []
        
        try:
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_query(query)
            
            if not query_embedding:
                return []
            
            # Perform similarity search using RPC function
            results = await self._similarity_search(
                query_embedding=query_embedding,
                user_id=user_id,
                top_k=top_k
            )
            
            return results
            
        except Exception as e:
            print(f"[RetrievalService] Retrieval error: {e}")
            # Don't raise - retrieval failure shouldn't block chat
            return []
    
    async def _similarity_search(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 5
    ) -> List[RetrievedContext]:
        """
        Perform similarity search using pgvector RPC function.
        
        Args:
            query_embedding: The query vector
            user_id: The user's ID
            top_k: Maximum number of results
            
        Returns:
            List of RetrievedContext objects
        """
        if not supabase:
            return []
        
        try:
            # Call the match_document_embeddings RPC function
            response = supabase.rpc(
                'match_document_embeddings',
                {
                    'query_embedding': query_embedding,
                    'match_user_id': user_id,
                    'match_count': top_k
                }
            ).execute()
            
            if not response.data:
                return []
            
            # Convert to RetrievedContext objects
            results = []
            for item in response.data:
                results.append(RetrievedContext(
                    chunk_id=str(item.get('chunk_id', '')),
                    document_id=str(item.get('document_id', '')),
                    content=item.get('content', ''),
                    filename=item.get('filename', 'Unknown'),
                    file_type=item.get('file_type', 'text'),
                    similarity=item.get('similarity', 0.0)
                ))
            
            return results
            
        except Exception as e:
            print(f"[RetrievalService] Similarity search error: {e}")
            return []
    
    async def retrieve_by_document(
        self,
        document_id: str,
        user_id: str,
        limit: int = 100
    ) -> List[RetrievedContext]:
        """
        Retrieve all chunks for a specific document.
        
        Args:
            document_id: The document's ID
            user_id: The user's ID (for verification)
            limit: Maximum number of chunks to return
            
        Returns:
            List of RetrievedContext objects for the document
        """
        if not supabase:
            return []
        
        try:
            # Get chunks for the document
            response = supabase.table('document_chunks').select(
                'id, document_id, content, page_number, metadata'
            ).eq('document_id', document_id).eq('user_id', user_id).order(
                'chunk_index', desc=False
            ).limit(limit).execute()
            
            if not response.data:
                return []
            
            # Get document metadata
            doc_response = supabase.table('user_documents').select(
                'filename, file_type'
            ).eq('id', document_id).eq('user_id', user_id).execute()
            
            filename = 'Unknown'
            file_type = 'text'
            if doc_response.data:
                filename = doc_response.data[0].get('filename', 'Unknown')
                file_type = doc_response.data[0].get('file_type', 'text')
            
            # Convert to RetrievedContext
            results = []
            for item in response.data:
                metadata = item.get('metadata', {}) or {}
                results.append(RetrievedContext(
                    chunk_id=str(item.get('id', '')),
                    document_id=document_id,
                    content=item.get('content', ''),
                    filename=filename,
                    file_type=file_type,
                    similarity=1.0,  # Full match for direct document retrieval
                    page_number=item.get('page_number') or metadata.get('page_number')
                ))
            
            return results
            
        except Exception as e:
            print(f"[RetrievalService] Document retrieval error: {e}")
            return []
    
    def format_context_for_prompt(
        self,
        contexts: List[RetrievedContext],
        max_length: int = 3000
    ) -> str:
        """
        Format retrieved contexts into a string for LLM prompt injection.
        
        Args:
            contexts: List of retrieved contexts
            max_length: Maximum character length of output
            
        Returns:
            Formatted context string
        """
        if not contexts:
            return ""
        
        formatted_parts = []
        total_length = 0
        
        for i, ctx in enumerate(contexts, 1):
            # Format each context chunk
            source_info = f"[{ctx.filename}"
            if ctx.page_number:
                source_info += f", page {ctx.page_number}"
            source_info += "]"
            
            chunk_text = f"\n{source_info}\n{ctx.content}\n"
            
            if total_length + len(chunk_text) > max_length:
                break
            
            formatted_parts.append(chunk_text)
            total_length += len(chunk_text)
        
        if not formatted_parts:
            return ""
        
        return "--- USER'S PERSONAL CONTEXT ---\n" + "".join(formatted_parts) + "\n--- END CONTEXT ---"


# Singleton instance
retrieval_service = RetrievalService()
