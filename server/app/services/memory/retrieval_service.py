"""
retrieval_service.py - Vector Similarity Search
Retrieves relevant document chunks using pgvector similarity search.
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from app.db.supabase import supabase
from app.core.config import settings
from app.services.memory.embedding_service import embedding_service
from app.services.memory.agentic_memory_service import agentic_memory_service


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
    memory_id: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    keywords: Optional[List[str]] = None
    source_type: Optional[str] = None
    related_memories: Optional[List[str]] = None


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
        top_k: int = 10,
        similarity_threshold: float = 0.3
    ) -> List[RetrievedContext]:
        """
        Retrieve relevant context for a query.
        
        Args:
            query: The search query
            user_id: The user's ID
            top_k: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0-1) to include
            
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
            print(f"[RetrievalService] Searching for: '{query[:50]}...' for user: {user_id[:8]}...")
            
            # Generate query embedding
            query_embedding = await self.embedding_service.embed_query(query)
            
            if not query_embedding:
                print("[RetrievalService] Failed to generate query embedding")
                return []
            
            print(f"[RetrievalService] Query embedding generated: {len(query_embedding)} dims")
            
            # Retrieve chunk-level vector context.
            document_results = await self._similarity_search(
                query_embedding=query_embedding,
                user_id=user_id,
                top_k=top_k,
                similarity_threshold=similarity_threshold
            )

            # Retrieve graph-linked, evolving memory context.
            agentic_rows = await agentic_memory_service.retrieve_context(
                query=query,
                user_id=user_id,
                top_k=max(4, top_k),
                query_embedding=query_embedding,
            )
            agentic_results = self._convert_agentic_rows(agentic_rows)

            results = self._merge_context_results(
                document_results=document_results,
                agentic_results=agentic_results,
                top_k=top_k,
            )
            
            print(
                f"[RetrievalService] Found {len(results)} merged results "
                f"(documents={len(document_results)}, agentic={len(agentic_results)})"
            )
            
            return results
            
        except Exception as e:
            print(f"[RetrievalService] Retrieval error: {e}")
            import traceback
            traceback.print_exc()
            # Don't raise - retrieval failure shouldn't block chat
            return []

    @staticmethod
    def _convert_agentic_rows(rows: List[Dict[str, Any]]) -> List[RetrievedContext]:
        """Convert agentic memory rows to RetrievedContext records."""
        converted: List[RetrievedContext] = []
        for row in rows or []:
            memory_id = str(row.get('id', '')).strip()
            if not memory_id:
                continue

            source_type = str(row.get('source_type') or 'other')
            source_id = str(row.get('source_id') or memory_id)
            summary = str(row.get('summary') or '').strip()
            content = str(row.get('content') or '').strip()
            if summary and summary not in content:
                content_text = f"Summary: {summary}\nDetails: {content}"
            else:
                content_text = content

            converted.append(
                RetrievedContext(
                    chunk_id=memory_id,
                    document_id=source_id,
                    content=content_text,
                    filename=f"memory::{source_type}",
                    file_type=source_type,
                    similarity=max(0.0, min(1.0, float(row.get('similarity') or 0.0))),
                    page_number=None,
                    memory_id=memory_id,
                    summary=summary or None,
                    tags=list(row.get('tags') or []),
                    keywords=list(row.get('keywords') or []),
                    source_type=source_type,
                    related_memories=list(row.get('related_memories') or []),
                )
            )

        return converted

    @staticmethod
    def _merge_context_results(
        document_results: List[RetrievedContext],
        agentic_results: List[RetrievedContext],
        top_k: int,
    ) -> List[RetrievedContext]:
        """
        Merge semantic chunk results with graph-linked memory results.
        Deduplicates by content identity and keeps highest-confidence entries.
        """
        merged: Dict[str, RetrievedContext] = {}

        for item in (document_results or []) + (agentic_results or []):
            key = item.memory_id or f"chunk::{item.chunk_id}"
            existing = merged.get(key)
            if not existing or item.similarity > existing.similarity:
                merged[key] = item

        ranked = list(merged.values())
        ranked.sort(key=lambda row: row.similarity, reverse=True)
        return ranked[:top_k]
    
    async def _similarity_search(
        self,
        query_embedding: List[float],
        user_id: str,
        top_k: int = 10,
        similarity_threshold: float = 0.3
    ) -> List[RetrievedContext]:
        """
        Perform similarity search using pgvector RPC function.
        
        Args:
            query_embedding: The query vector
            user_id: The user's ID
            top_k: Maximum number of results
            similarity_threshold: Minimum similarity score to include
            
        Returns:
            List of RetrievedContext objects
        """
        if not supabase:
            return []
        
        try:
            print(f"[RetrievalService] Calling RPC match_document_embeddings with user_id={user_id[:8]}...")
            
            # Call the match_document_embeddings RPC function
            response = supabase.rpc(
                'match_document_embeddings',
                {
                    'query_embedding': query_embedding,
                    'match_user_id': user_id,
                    'match_count': top_k * 2  # Get more to filter by threshold
                }
            ).execute()
            
            print(f"[RetrievalService] RPC response: {len(response.data) if response.data else 0} results")
            
            if not response.data:
                print("[RetrievalService] No data returned from RPC")
                return []
            
            # Convert to RetrievedContext objects and filter by threshold
            results = []
            for item in response.data:
                similarity = item.get('similarity', 0.0)
                
                # Filter by similarity threshold
                if similarity < similarity_threshold:
                    print(f"[RetrievalService] Skipping low similarity: {item.get('filename')} ({similarity:.3f} < {similarity_threshold})")
                    continue
                
                results.append(RetrievedContext(
                    chunk_id=str(item.get('chunk_id', '')),
                    document_id=str(item.get('document_id', '')),
                    content=item.get('content', ''),
                    filename=item.get('filename', 'Unknown'),
                    file_type=item.get('file_type', 'text'),
                    similarity=similarity,
                    page_number=item.get('page_number')
                ))
                print(f"[RetrievalService] [OK] Result: {item.get('filename')} - similarity: {similarity:.3f}")
            
            # Limit to top_k after filtering
            results = results[:top_k]
            
            return results
            
        except Exception as e:
            print(f"[RetrievalService] Similarity search error: {e}")
            import traceback
            traceback.print_exc()
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
        max_length: int = 6000
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
            source_info = f"[DOCUMENT: {ctx.filename}"
            if ctx.page_number:
                source_info += f", Page {ctx.page_number}"
            source_info += f", Relevance: {ctx.similarity:.0%}]"

            if ctx.source_type and ctx.source_type != 'document_chunk':
                source_info = f"[MEMORY: {ctx.source_type}, Relevance: {ctx.similarity:.0%}]"
                if ctx.tags:
                    source_info += f" Tags={', '.join(ctx.tags[:4])}"
                if ctx.related_memories:
                    source_info += f" Linked={len(ctx.related_memories)}"
            
            chunk_text = f"\n{source_info}\n{ctx.content}\n"
            
            if total_length + len(chunk_text) > max_length:
                break
            
            formatted_parts.append(chunk_text)
            total_length += len(chunk_text)
        
        if not formatted_parts:
            return ""
        
        return "--- USER'S PERSONAL DOCUMENTS (READ CAREFULLY) ---\n" + "".join(formatted_parts) + "\n--- END OF USER'S DOCUMENTS ---"


# Singleton instance
retrieval_service = RetrievalService()
