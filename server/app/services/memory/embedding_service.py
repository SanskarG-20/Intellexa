"""
embedding_service.py - Local Embedding Service
Fast, on-device embeddings using sentence-transformers.
No API key needed, works offline.

Model: nomic-ai/nomic-embed-text-v1.5 (768 dims, 8192 token context)
"""

import asyncio
import hashlib
import logging
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
        
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize the embedding model."""
        print("[EmbeddingService] Initializing local embedding service...")
        logger.info("[EmbeddingService] Initializing local embedding service...")
        
        # Try primary model first
        model = LocalEmbeddingModel(PRIMARY_MODEL)
        if model.load():
            self._model = model
            self._model_name = PRIMARY_MODEL
            self._dimension = model.dimension
            print(f"[EmbeddingService] [OK] Using: {PRIMARY_MODEL}")
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
                return
        
        # All models failed
        print("[EmbeddingService] [WARN] All models failed, using hash-based fallback")
        self._use_fallback = True
    
    def _ensure_ready(self) -> None:
        """Ensure the service is ready to generate embeddings."""
        if self._use_fallback:
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
        return True
    
    def is_using_fallback(self) -> bool:
        """Check if using hash-based fallback."""
        return self._use_fallback
    
    def get_model_name(self) -> Optional[str]:
        """Get the loaded model name."""
        return self._model_name


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
