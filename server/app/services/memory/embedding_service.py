"""
embedding_service.py - Gemini Embedding Operations
Generates vector embeddings for text using Google Gemini.
"""

import asyncio
from typing import List, Optional

from app.core.config import settings

try:
    # Try new google.genai package first
    from google import genai
    from google.genai import types
    USE_NEW_SDK = True
except ImportError:
    # Fall back to deprecated google.generativeai
    import google.generativeai as genai
    USE_NEW_SDK = False


class EmbeddingServiceError(Exception):
    """Custom exception for embedding service errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class EmbeddingService:
    """
    Handles embedding generation using Google Gemini's embedding API.
    Uses text-embedding-004 model for 768-dimensional vectors.
    """
    
    def __init__(self):
        self.api_key = settings.GEMINI_API_KEY
        self._client = None
        self.dimension = settings.EMBEDDING_DIMENSION  # 768 for text-embedding-004
        self._initialized = False
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize the Gemini client."""
        if not self.api_key:
            print("[EmbeddingService] Warning: GEMINI_API_KEY not configured")
            return
        
        try:
            if USE_NEW_SDK:
                self._client = genai.Client(api_key=self.api_key)
                self.model = "text-embedding-004"  # New SDK - no prefix
            else:
                genai.configure(api_key=self.api_key)
                self.model = "models/embedding-001"  # Old SDK - use stable embedding-001
                self._client = None
            self._initialized = True
            print(f"[EmbeddingService] Initialized with model: {self.model} (USE_NEW_SDK={USE_NEW_SDK})")
        except Exception as e:
            print(f"[EmbeddingService] Failed to initialize: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure the service is properly initialized."""
        if not self._initialized:
            raise EmbeddingServiceError(
                "Embedding service not initialized. Check GEMINI_API_KEY.",
                "NOT_INITIALIZED"
            )
    
    async def embed_text(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.
        
        Args:
            text: The text to embed
            
        Returns:
            List of floats representing the embedding vector
            
        Raises:
            EmbeddingServiceError: If embedding generation fails
        """
        self._ensure_initialized()
        
        if not text or not text.strip():
            raise EmbeddingServiceError(
                "Cannot embed empty text",
                "EMPTY_TEXT"
            )
        
        try:
            # Truncate very long texts to avoid API limits
            max_chars = 30000  # Gemini's approximate limit
            if len(text) > max_chars:
                text = text[:max_chars]
            
            # Run in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._embed_sync,
                text,
                "retrieval_document"
            )
            
            return result
            
        except Exception as e:
            if isinstance(e, EmbeddingServiceError):
                raise
            raise EmbeddingServiceError(
                f"Failed to generate embedding: {str(e)}",
                "EMBEDDING_FAILED"
            )
    
    def _embed_sync(self, text: str, task_type: str) -> List[float]:
        """Synchronous embedding call (run in executor)."""
        if USE_NEW_SDK and self._client:
            # Use new google.genai SDK
            # Task type should be uppercase for new SDK
            task_type_map = {
                "retrieval_document": "RETRIEVAL_DOCUMENT",
                "retrieval_query": "RETRIEVAL_QUERY"
            }
            mapped_task_type = task_type_map.get(task_type, "RETRIEVAL_DOCUMENT")
            
            result = self._client.models.embed_content(
                model=self.model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=mapped_task_type
                )
            )
            return list(result.embeddings[0].values)
        else:
            # Use deprecated google.generativeai SDK
            result = genai.embed_content(
                model=self.model,
                content=text,
                task_type=task_type
            )
            return list(result['embedding'])
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        Uses 'retrieval_query' task type for better search performance.
        
        Args:
            query: The search query to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        self._ensure_initialized()
        
        if not query or not query.strip():
            raise EmbeddingServiceError(
                "Cannot embed empty query",
                "EMPTY_QUERY"
            )
        
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._embed_sync,
                query,
                "retrieval_query"
            )
            
            return result
            
        except Exception as e:
            if isinstance(e, EmbeddingServiceError):
                raise
            raise EmbeddingServiceError(
                f"Failed to generate query embedding: {str(e)}",
                "EMBEDDING_FAILED"
            )
    
    async def embed_batch(
        self,
        texts: List[str],
        batch_size: int = 5
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        Processes in batches to respect rate limits.
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process per batch
            
        Returns:
            List of embedding vectors
            
        Raises:
            EmbeddingServiceError: If embedding generation fails
        """
        self._ensure_initialized()
        
        if not texts:
            return []
        
        # Filter out empty texts
        valid_texts = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        
        if not valid_texts:
            return [[] for _ in texts]
        
        embeddings = [None] * len(texts)
        
        try:
            # Process in batches
            for batch_start in range(0, len(valid_texts), batch_size):
                batch = valid_texts[batch_start:batch_start + batch_size]
                
                # Process batch concurrently
                tasks = [
                    self.embed_text(text)
                    for _, text in batch
                ]
                batch_results = await asyncio.gather(*tasks)
                
                # Place results in correct positions
                for (orig_idx, _), embedding in zip(batch, batch_results):
                    embeddings[orig_idx] = embedding
                
                # Small delay between batches to respect rate limits
                if batch_start + batch_size < len(valid_texts):
                    await asyncio.sleep(0.5)
            
            return embeddings
            
        except Exception as e:
            if isinstance(e, EmbeddingServiceError):
                raise
            raise EmbeddingServiceError(
                f"Failed to generate batch embeddings: {str(e)}",
                "BATCH_EMBEDDING_FAILED"
            )
    
    def get_dimension(self) -> int:
        """Return the dimension of embeddings."""
        return self.dimension
    
    def is_initialized(self) -> bool:
        """Check if the service is properly initialized."""
        return self._initialized


# Singleton instance
embedding_service = EmbeddingService()
