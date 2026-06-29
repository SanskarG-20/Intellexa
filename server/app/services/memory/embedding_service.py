"""
embedding_service.py - Local Embedding Service
Fast, on-device embeddings using sentence-transformers.
No API key needed, works offline.

Model: nomic-ai/nomic-embed-text-v1.5 (768 dims, 8192 token context)
"""

import asyncio
import httpx
import hashlib
import logging
import os
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Primary model - best for long documents
PRIMARY_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# Fallback models (smaller, faster)
FALLBACK_MODELS = [
    "BAAI/bge-small-en-v1.5",           # 384 dims, very fast
    "sentence-transformers/all-MiniLM-L6-v2",  # 384 dims, fastest
    "sentence-transformers/all-mpnet-base-v2",  # 768 dims, good quality
]

# Embedding configuration
EMBEDDING_DIMENSION = 768  # nomic-embed-text dimension
MAX_TEXT_LENGTH = 32000   # Characters (model handles 8192 tokens)
BATCH_SIZE = 32           # Large batches for local model (very fast)
TRUNCATE_DIMENSION = None # Set to 384 for smaller vectors (Matryoshka)

# ============================================================================
# EXCEPTIONS
# ============================================================================

class EmbeddingServiceError(Exception):
    """Custom exception for embedding service errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


# ============================================================================
# LOCAL EMBEDDING MODEL WRAPPER
# ============================================================================

class LocalEmbeddingModel:
    """
    Wrapper for sentence-transformers model.
    Handles lazy loading and batch encoding.
    """
    
    def __init__(self, model_name: str, dimension: int = EMBEDDING_DIMENSION):
        self.model_name = model_name
        self._dimension = dimension
        self._model = None
        self._loaded = False
    
    def load(self) -> bool:
        """Load the model (called once on first use)."""
        if self._loaded:
            return True
        
        try:
            from sentence_transformers import SentenceTransformer
            
            print(f"[LocalEmbedding] Loading model: {self.model_name}")
            logger.info(f"[LocalEmbedding] Loading model: {self.model_name}")
            
            # Load model (CPU by default, GPU if available)
            self._model = SentenceTransformer(
                self.model_name,
                trust_remote_code=True,
                device='cpu'  # Change to 'cuda' if GPU available
            )
            
            # Detect actual dimension
            test_embedding = self._model.encode("test", convert_to_numpy=True)
            self._dimension = len(test_embedding)
            
            self._loaded = True
            print(f"[LocalEmbedding] [OK] Model loaded: {self.model_name} ({self._dimension} dims)")
            return True
            
        except ImportError as e:
            print(f"[LocalEmbedding] sentence-transformers not installed: {e}")
            logger.error(f"[LocalEmbedding] sentence-transformers not installed: {e}")
            logger.error("[LocalEmbedding] Run: pip install sentence-transformers torch")
            return False
        except Exception as e:
            print(f"[LocalEmbedding] Failed to load {self.model_name}: {e}")
            logger.error(f"[LocalEmbedding] Failed to load {self.model_name}: {e}")
            return False
    
    def encode(self, texts: List[str], normalize: bool = True) -> List[List[float]]:
        """
        Encode texts to embeddings.
        Very fast batch processing on CPU.
        """
        if not self._loaded or self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")
        
        import numpy as np
        
        # Batch encode (single forward pass for all texts)
        embeddings = self._model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=normalize,
            show_progress_bar=False,
            batch_size=BATCH_SIZE
        )
        
        # Convert to list format
        if isinstance(embeddings, np.ndarray):
            embeddings = embeddings.tolist()
        
        # Optionally truncate dimensions (Matryoshka embedding)
        if TRUNCATE_DIMENSION and TRUNCATE_DIMENSION < self._dimension:
            embeddings = [emb[:TRUNCATE_DIMENSION] for emb in embeddings]
        
        return embeddings
    
    @property
    def dimension(self) -> int:
        return TRUNCATE_DIMENSION if TRUNCATE_DIMENSION else self._dimension
    
    @property
    def is_loaded(self) -> bool:
        return self._loaded


# ============================================================================
# FALLBACK EMBEDDING (Hash-based)
# ============================================================================

def generate_fallback_embedding(text: str, dimension: int = EMBEDDING_DIMENSION) -> List[float]:
    """
    Generate deterministic fallback embedding using SHA256.
    Used when model loading fails.
    """
    if not text or not text.strip():
        return [0.0] * dimension
    
    text_bytes = text.encode('utf-8')
    embedding = []
    
    for i in range(0, dimension, 8):
        hasher = hashlib.sha256(text_bytes + str(i).encode())
        hex_digest = hasher.hexdigest()
        
        for j in range(0, 32, 4):
            if len(embedding) >= dimension:
                break
            value = int(hex_digest[j:j+8], 16) / (16**8)
            embedding.append((value * 2) - 1)
    
    # Normalize
    magnitude = sum(x * x for x in embedding) ** 0.5
    if magnitude > 0:
        embedding = [x / magnitude for x in embedding]
    
    return embedding[:dimension]


# ============================================================================
# MAIN EMBEDDING SERVICE (Singleton)
# ============================================================================

class EmbeddingService:
    """
    Embedding service using local sentence-transformers models.
    
    Features:
    - No API key required
    - Works offline
    - Fast batch processing
    - Model fallbacks
    - Graceful degradation
    """
    
    def __init__(self):
        self._model: Optional[LocalEmbeddingModel] = None
        self._model_name: Optional[str] = None
        self._dimension = EMBEDDING_DIMENSION
        self._use_fallback = False
        self._validated = False
        self._initialized = False
        self._use_gemini_api = False
        self._use_together_api = False
        self.api_key_gemini = ""
        self.api_key_together = ""
    
    def _initialize(self) -> None:
        """Initialize the embedding model."""
        if self._initialized:
            return

        force_fallback = bool(settings.EMBEDDING_FORCE_HASH_FALLBACK)
        is_railway = bool(
            os.getenv("RAILWAY_ENVIRONMENT")
            or os.getenv("RAILWAY_SERVICE_ID")
            or os.getenv("RAILWAY_PROJECT_ID")
        )

        if force_fallback or is_railway:
            # Check if cloud embedding models can be used instead of hash fallback
            self.api_key_gemini = (settings.GEMINI_API_KEY or "").strip()
            self.api_key_together = (settings.TOGETHER_API_KEY or "").strip()

            if self.api_key_gemini and self.api_key_gemini != "your_google_ai_studio_api_key_here":
                self._use_gemini_api = True
                self._model_name = "gemini/text-embedding-004"
                self._dimension = 768
                print("[EmbeddingService] Using Gemini Cloud API for embeddings (Railway / fallback mode).")
                self._initialized = True
                return

            if self.api_key_together and self.api_key_together != "your_together_api_key_here":
                self._use_together_api = True
                self._model_name = settings.TOGETHER_EMBEDDING_MODEL
                self._dimension = 768
                print(f"[EmbeddingService] Using Together AI Cloud API for embeddings ({settings.TOGETHER_EMBEDDING_MODEL}) (Railway / fallback mode).")
                self._initialized = True
                return

            reason = "configuration" if force_fallback else "Railway runtime detection"
            print(f"[EmbeddingService] [INFO] Using hash fallback embeddings ({reason}).")
            self._use_fallback = True
            self._initialized = True
            return

        # Check if cloud embedding models can be used
        self.api_key_gemini = (settings.GEMINI_API_KEY or "").strip()
        self.api_key_together = (settings.TOGETHER_API_KEY or "").strip()

        if self.api_key_gemini and self.api_key_gemini != "your_google_ai_studio_api_key_here":
            self._use_gemini_api = True
            self._model_name = "gemini/text-embedding-004"
            self._dimension = 768
            print("[EmbeddingService] Using Gemini Cloud API for embeddings.")
            self._initialized = True
            return

        if self.api_key_together and self.api_key_together != "your_together_api_key_here":
            self._use_together_api = True
            self._model_name = settings.TOGETHER_EMBEDDING_MODEL
            self._dimension = 768
            print(f"[EmbeddingService] Using Together AI Cloud API for embeddings ({settings.TOGETHER_EMBEDDING_MODEL}).")
            self._initialized = True
            return

        print("[EmbeddingService] Initializing local embedding service...")
        logger.info("[EmbeddingService] Initializing local embedding service...")
        
        # Try primary model first
        model = LocalEmbeddingModel(PRIMARY_MODEL)
        if model.load():
            self._model = model
            self._model_name = PRIMARY_MODEL
            self._dimension = model.dimension
            print(f"[EmbeddingService] [OK] Using: {PRIMARY_MODEL}")
            self._initialized = True
            return
        
        # Try fallback models
        for model_name in FALLBACK_MODELS:
            print(f"[EmbeddingService] Trying fallback: {model_name}")
            model = LocalEmbeddingModel(model_name)
            if model.load():
                self._model = model
                self._model_name = model_name
                self._dimension = model.dimension
                print(f"[EmbeddingService] [OK] Using fallback: {model_name}")
                self._initialized = True
                return
        
        # All models failed
        print("[EmbeddingService] [WARN] All models failed, using hash-based fallback")
        self._use_fallback = True
        self._initialized = True
    
    def _ensure_ready(self) -> None:
        """Ensure the service is ready to generate embeddings."""
        if not self._initialized:
            self._initialize()

        if self._use_fallback or self._use_gemini_api or self._use_together_api:
            return
        if self._model is None or not self._model.is_loaded:
            raise EmbeddingServiceError(
                "Embedding model not loaded",
                "MODEL_NOT_LOADED"
            )
    
    async def validate_model(self) -> Tuple[bool, str]:
        """
        Validate the embedding model works.
        Called at startup.
        """
        if self._validated:
            return True, self._model_name or "fallback"
        
        try:
            result = await self.embed_text("validation test")
            if result and any(x != 0 for x in result):
                self._validated = True
                return True, self._model_name or "fallback"
        except Exception as e:
            logger.error(f"[EmbeddingService] Validation failed: {e}")
        
        return False, "none"
    
    async def embed_text(self, text: str, skip_on_error: bool = False) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            skip_on_error: Return None on error instead of fallback
            
        Returns:
            Embedding vector (768 dims) or None
        """
        if not text or not text.strip():
            return [0.0] * self._dimension
        
        # Truncate if needed
        truncated = text[:MAX_TEXT_LENGTH] if len(text) > MAX_TEXT_LENGTH else text
        
        # Use cloud Gemini API if enabled
        if self._use_gemini_api:
            try:
                embeddings = await self._embed_via_gemini_api([truncated])
                return embeddings[0]
            except Exception as e:
                logger.error(f"[EmbeddingService] Gemini Cloud embedding failed: {e}")
                if skip_on_error:
                    return None
                return generate_fallback_embedding(text, self._dimension)

        # Use cloud Together AI API if enabled
        if self._use_together_api:
            try:
                embeddings = await self._embed_via_together_api([truncated])
                return embeddings[0]
            except Exception as e:
                logger.error(f"[EmbeddingService] Together AI Cloud embedding failed: {e}")
                if skip_on_error:
                    return None
                return generate_fallback_embedding(text, self._dimension)

        # Use fallback if no model
        if self._use_fallback:
            return generate_fallback_embedding(text, self._dimension)
        
        try:
            self._ensure_ready()
            
            # Run in executor to not block event loop
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                self._model.encode,
                [truncated]
            )
            
            return embeddings[0]
            
        except Exception as e:
            logger.error(f"[EmbeddingService] Embedding failed: {e}")
            
            if skip_on_error:
                return None
            
            return generate_fallback_embedding(text, self._dimension)
    
    async def embed_query(self, query: str) -> List[float]:
        """
        Generate embedding for a search query.
        Same as embed_text but never returns None.
        """
        result = await self.embed_text(query, skip_on_error=False)
        return result if result else [0.0] * self._dimension
    
    async def embed_batch(
        self,
        texts: List[str],
        skip_failures: bool = True
    ) -> List[Optional[List[float]]]:
        """
        Generate embeddings for multiple texts efficiently.
        
        Args:
            texts: List of texts to embed
            skip_failures: Return None for failed items
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        logger.info(f"[EmbeddingService] Processing batch: {len(texts)} texts")
        
        # Filter valid texts
        valid_items = [(i, t) for i, t in enumerate(texts) if t and t.strip()]
        
        if not valid_items:
            return [[0.0] * self._dimension for _ in texts]
        
        # Prepare result array
        result: List[Optional[List[float]]] = [None] * len(texts)
        
        # Use cloud Gemini API if enabled
        if self._use_gemini_api:
            try:
                valid_texts = [t[:MAX_TEXT_LENGTH] for _, t in valid_items]
                embeddings_list = await self._embed_via_gemini_api(valid_texts)
                for (orig_idx, _), emb in zip(valid_items, embeddings_list):
                    result[orig_idx] = emb
                for i, emb in enumerate(result):
                    if emb is None:
                        result[i] = [0.0] * self._dimension
                return result
            except Exception as e:
                logger.error(f"[EmbeddingService] Gemini Cloud batch embedding failed: {e}")
                for i, t in enumerate(texts):
                    if result[i] is None:
                        result[i] = generate_fallback_embedding(t, self._dimension) if not skip_failures else [0.0] * self._dimension
                return result

        # Use cloud Together AI API if enabled
        if self._use_together_api:
            try:
                valid_texts = [t[:MAX_TEXT_LENGTH] for _, t in valid_items]
                embeddings_list = await self._embed_via_together_api(valid_texts)
                for (orig_idx, _), emb in zip(valid_items, embeddings_list):
                    result[orig_idx] = emb
                for i, emb in enumerate(result):
                    if emb is None:
                        result[i] = [0.0] * self._dimension
                return result
            except Exception as e:
                logger.error(f"[EmbeddingService] Together AI Cloud batch embedding failed: {e}")
                for i, t in enumerate(texts):
                    if result[i] is None:
                        result[i] = generate_fallback_embedding(t, self._dimension) if not skip_failures else [0.0] * self._dimension
                return result

        # Use fallback if no model
        if self._use_fallback:
            for i, t in enumerate(texts):
                result[i] = generate_fallback_embedding(t, self._dimension) if t else [0.0] * self._dimension
            return result
        
        try:
            self._ensure_ready()
            
            # Extract texts for batch encoding
            valid_texts = [t[:MAX_TEXT_LENGTH] for _, t in valid_items]
            
            # Batch encode (VERY fast - single forward pass)
            loop = asyncio.get_event_loop()
            embeddings_list = await loop.run_in_executor(
                None,
                self._model.encode,
                valid_texts
            )
            
            # Place in correct positions
            for (orig_idx, _), emb in zip(valid_items, embeddings_list):
                result[orig_idx] = emb
            
            # Fill None with zero vectors
            for i, emb in enumerate(result):
                if emb is None:
                    result[i] = [0.0] * self._dimension
            
            logger.info(f"[EmbeddingService] [OK] Batch complete: {len(texts)} embeddings")
            
        except Exception as e:
            logger.error(f"[EmbeddingService] Batch failed: {e}")
            
            # Use fallback for failed items
            for i, t in enumerate(texts):
                if result[i] is None:
                    result[i] = generate_fallback_embedding(t, self._dimension) if not skip_failures else [0.0] * self._dimension
        
        return result
    
    def get_dimension(self) -> int:
        """Return embedding dimension."""
        return self._dimension
    
    def is_initialized(self) -> bool:
        """Check if service is initialized."""
        return self._initialized
    
    def is_using_fallback(self) -> bool:
        """Check if using hash-based fallback."""
        return self._use_fallback
    
    def get_model_name(self) -> Optional[str]:
        """Get the loaded model name."""
        return self._model_name

    async def _embed_via_gemini_api(self, texts: List[str]) -> List[List[float]]:
        """Call Gemini API for embeddings in a single request."""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:batchEmbedContents?key={self.api_key_gemini}"
        requests = [
            {
                "model": "models/text-embedding-004",
                "content": {
                    "parts": [{"text": text}]
                }
            }
            for text in texts
        ]
        payload = {"requests": requests}
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            embeddings = [item["values"] for item in data["embeddings"]]
            return embeddings

    async def _embed_via_together_api(self, texts: List[str]) -> List[List[float]]:
        """Call Together AI API for embeddings in a single request."""
        url = "https://api.together.xyz/v1/embeddings"
        payload = {
            "model": settings.TOGETHER_EMBEDDING_MODEL,
            "input": texts
        }
        headers = {
            "Authorization": f"Bearer {self.api_key_together}",
            "Content-Type": "application/json"
        }
        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

embedding_service = EmbeddingService()


# ============================================================================
# STARTUP VALIDATION
# ============================================================================

async def validate_embedding_service() -> bool:
    """
    Validate embedding service at startup.
    Call from FastAPI lifespan.
    """
    success, model = await embedding_service.validate_model()
    
    if success:
        if model == "fallback":
            logger.warning("[WARN] Embedding service using FALLBACK mode")
            logger.warning("   Install sentence-transformers: pip install sentence-transformers torch")
        else:
            logger.info(f"[OK] Embedding service validated: {model}")
    else:
        logger.error("[ERROR] Embedding service validation failed")
    
    return success
