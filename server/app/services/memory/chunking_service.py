"""
chunking_service.py - Text Chunking Operations
Splits text into smaller pieces for embedding and retrieval.
"""

import re
from typing import List, Optional
from dataclasses import dataclass

from app.core.config import settings


@dataclass
class TextChunk:
    """Represents a chunk of text with metadata."""
    content: str
    index: int
    token_count: int
    page_number: Optional[int] = None
    metadata: Optional[dict] = None


class ChunkingService:
    """
    Handles text chunking for document processing.
    Uses a simple token estimation based on word count.
    """
    
    def __init__(self):
        self.max_tokens = settings.CHUNK_MAX_TOKENS
        self.overlap_tokens = settings.CHUNK_OVERLAP_TOKENS
        # Approximate tokens per word (rough estimate for English)
        self.tokens_per_word = 1.3
    
    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a text.
        Uses word count * 1.3 as a rough approximation.
        """
        words = len(text.split())
        return int(words * self.tokens_per_word)
    
    def _split_by_sentence(self, text: str) -> List[str]:
        """Split text into sentences."""
        # Split on sentence boundaries, keeping the delimiter
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _split_by_paragraph(self, text: str) -> List[str]:
        """Split text into paragraphs."""
        paragraphs = re.split(r'\n\s*\n', text)
        return [p.strip() for p in paragraphs if p.strip()]
    
    def chunk_text(
        self,
        text: str,
        max_tokens: Optional[int] = None,
        overlap_tokens: Optional[int] = None
    ) -> List[TextChunk]:
        """
        Chunk text into smaller pieces for embedding.
        
        Args:
            text: The text to chunk
            max_tokens: Maximum tokens per chunk (uses config default if None)
            overlap_tokens: Number of overlapping tokens between chunks
            
        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []
        
        max_tokens = max_tokens or self.max_tokens
        overlap_tokens = overlap_tokens or self.overlap_tokens
        
        # Clean and normalize text
        text = ' '.join(text.split())
        
        # First, try splitting by paragraphs
        paragraphs = self._split_by_paragraph(text)
        
        chunks = []
        current_chunk_text = ""
        current_chunk_tokens = 0
        chunk_index = 0
        
        for para in paragraphs:
            para_tokens = self._estimate_tokens(para)
            
            # If paragraph fits in current chunk, add it
            if current_chunk_tokens + para_tokens <= max_tokens:
                current_chunk_text += ("\n\n" if current_chunk_text else "") + para
                current_chunk_tokens += para_tokens
            else:
                # Save current chunk if it has content
                if current_chunk_text.strip():
                    chunks.append(TextChunk(
                        content=current_chunk_text.strip(),
                        index=chunk_index,
                        token_count=current_chunk_tokens
                    ))
                    chunk_index += 1
                
                # If paragraph is too large, split by sentences
                if para_tokens > max_tokens:
                    sentences = self._split_by_sentence(para)
                    current_chunk_text = ""
                    current_chunk_tokens = 0
                    
                    for sentence in sentences:
                        sent_tokens = self._estimate_tokens(sentence)
                        
                        if current_chunk_tokens + sent_tokens <= max_tokens:
                            current_chunk_text += (" " if current_chunk_text else "") + sentence
                            current_chunk_tokens += sent_tokens
                        else:
                            if current_chunk_text.strip():
                                chunks.append(TextChunk(
                                    content=current_chunk_text.strip(),
                                    index=chunk_index,
                                    token_count=current_chunk_tokens
                                ))
                                chunk_index += 1
                            
                            # If single sentence is too large, just use it
                            if sent_tokens > max_tokens:
                                # Split by words as last resort
                                words = sentence.split()
                                word_chunk = []
                                word_count = 0
                                
                                for word in words:
                                    if word_count + 1 <= max_tokens / self.tokens_per_word:
                                        word_chunk.append(word)
                                        word_count += 1
                                    else:
                                        if word_chunk:
                                            chunks.append(TextChunk(
                                                content=' '.join(word_chunk),
                                                index=chunk_index,
                                                token_count=int(word_count * self.tokens_per_word)
                                            ))
                                            chunk_index += 1
                                        word_chunk = [word]
                                        word_count = 1
                                
                                if word_chunk:
                                    current_chunk_text = ' '.join(word_chunk)
                                    current_chunk_tokens = int(word_count * self.tokens_per_word)
                            else:
                                current_chunk_text = sentence
                                current_chunk_tokens = sent_tokens
                else:
                    # Start new chunk with this paragraph
                    current_chunk_text = para
                    current_chunk_tokens = para_tokens
        
        # Don't forget the last chunk
        if current_chunk_text.strip():
            chunks.append(TextChunk(
                content=current_chunk_text.strip(),
                index=chunk_index,
                token_count=current_chunk_tokens
            ))
        
        # Add overlap between chunks
        if overlap_tokens > 0 and len(chunks) > 1:
            chunks = self._add_overlap(chunks, overlap_tokens)
        
        return chunks
    
    def _add_overlap(self, chunks: List[TextChunk], overlap_tokens: int) -> List[TextChunk]:
        """Add overlapping content between chunks for better retrieval."""
        if len(chunks) <= 1:
            return chunks
        
        overlap_words = int(overlap_tokens / self.tokens_per_word)
        
        result = []
        for i, chunk in enumerate(chunks):
            content = chunk.content
            
            # Add overlap from previous chunk
            if i > 0:
                prev_words = chunks[i-1].content.split()
                overlap_content = ' '.join(prev_words[-overlap_words:])
                content = overlap_content + " ... " + content
            
            result.append(TextChunk(
                content=content,
                index=chunk.index,
                token_count=self._estimate_tokens(content),
                page_number=chunk.page_number,
                metadata=chunk.metadata
            ))
        
        return result
    
    def chunk_with_metadata(
        self,
        text: str,
        page_number: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> List[TextChunk]:
        """
        Chunk text and attach metadata to each chunk.
        
        Args:
            text: The text to chunk
            page_number: Page number this text came from
            metadata: Additional metadata to attach
            
        Returns:
            List of TextChunk objects with metadata
        """
        chunks = self.chunk_text(text)
        
        return [
            TextChunk(
                content=chunk.content,
                index=chunk.index,
                token_count=chunk.token_count,
                page_number=page_number,
                metadata=metadata or {}
            )
            for chunk in chunks
        ]
    
    def chunk_pages(
        self,
        pages: List[dict],
        metadata: Optional[dict] = None
    ) -> List[TextChunk]:
        """
        Chunk a list of pages (e.g., from PDF extraction).
        
        Args:
            pages: List of page dicts with 'page_number' and 'content' keys
            metadata: Additional metadata to attach
            
        Returns:
            List of TextChunk objects
        """
        all_chunks = []
        chunk_index = 0
        
        for page in pages:
            page_num = page.get('page_number', 1)
            page_content = page.get('content', '')
            
            if not page_content.strip():
                continue
            
            page_chunks = self.chunk_text(page_content)
            
            for chunk in page_chunks:
                all_chunks.append(TextChunk(
                    content=chunk.content,
                    index=chunk_index,
                    token_count=chunk.token_count,
                    page_number=page_num,
                    metadata={
                        **(metadata or {}),
                        'page_number': page_num
                    }
                ))
                chunk_index += 1
        
        return all_chunks


# Singleton instance
chunking_service = ChunkingService()
