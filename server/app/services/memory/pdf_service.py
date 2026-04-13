"""
pdf_service.py - PDF Document Processing
Extracts text from PDFs and prepares chunks for embedding.
"""

import io
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings
from app.services.memory.chunking_service import chunking_service, TextChunk


@dataclass
class PDFPage:
    """Represents a page extracted from a PDF."""
    page_number: int
    content: str
    char_count: int


class PDFServiceError(Exception):
    """Custom exception for PDF processing errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class PDFService:
    """
    Handles PDF text extraction and chunking.
    Uses PyMuPDF (fitz) for reliable PDF parsing.
    """
    
    def __init__(self):
        self.max_file_size = settings.get_max_file_size_bytes()
        self._fitz = None
        self._initialize()
    
    def _initialize(self) -> None:
        """Lazy initialization of PyMuPDF."""
        try:
            import fitz
            self._fitz = fitz
            print("[PDFService] Initialized with PyMuPDF")
        except ImportError:
            print("[PDFService] Warning: PyMuPDF not available. PDF processing disabled.")
    
    def _ensure_initialized(self) -> None:
        """Ensure PyMuPDF is available."""
        if self._fitz is None:
            raise PDFServiceError(
                "PDF processing not available. PyMuPDF is not installed.",
                "DEPENDENCY_MISSING"
            )
    
    def validate_pdf(self, file_bytes: bytes) -> Tuple[bool, str]:
        """
        Validate a PDF file.
        
        Args:
            file_bytes: Raw PDF file bytes
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file_bytes:
            return False, "Empty file"
        
        if len(file_bytes) > self.max_file_size:
            return False, f"File too large. Max size: {settings.MAX_FILE_SIZE_MB}MB"
        
        # Check PDF signature
        if not file_bytes.startswith(b'%PDF'):
            return False, "Invalid PDF file format"
        
        return True, ""
    
    def extract_text(self, file_bytes: bytes) -> str:
        """
        Extract all text from a PDF file.
        
        Args:
            file_bytes: Raw PDF file bytes
            
        Returns:
            Extracted text as a single string
            
        Raises:
            PDFServiceError: If extraction fails
        """
        self._ensure_initialized()
        
        is_valid, error = self.validate_pdf(file_bytes)
        if not is_valid:
            raise PDFServiceError(error, "INVALID_PDF")
        
        try:
            # Open PDF from bytes
            pdf_document = self._fitz.open(stream=file_bytes, filetype="pdf")
            
            all_text = []
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                text = page.get_text()
                all_text.append(text)
            
            pdf_document.close()
            
            return "\n\n".join(all_text)
            
        except Exception as e:
            if isinstance(e, PDFServiceError):
                raise
            raise PDFServiceError(
                f"Failed to extract text from PDF: {str(e)}",
                "EXTRACTION_FAILED"
            )
    
    def extract_pages(self, file_bytes: bytes) -> List[PDFPage]:
        """
        Extract text from each page of a PDF.
        
        Args:
            file_bytes: Raw PDF file bytes
            
        Returns:
            List of PDFPage objects
            
        Raises:
            PDFServiceError: If extraction fails
        """
        self._ensure_initialized()
        
        is_valid, error = self.validate_pdf(file_bytes)
        if not is_valid:
            raise PDFServiceError(error, "INVALID_PDF")
        
        try:
            pdf_document = self._fitz.open(stream=file_bytes, filetype="pdf")
            
            pages = []
            for page_num in range(len(pdf_document)):
                page = pdf_document[page_num]
                text = page.get_text()
                
                pages.append(PDFPage(
                    page_number=page_num + 1,  # 1-indexed
                    content=text,
                    char_count=len(text)
                ))
            
            pdf_document.close()
            
            return pages
            
        except Exception as e:
            if isinstance(e, PDFServiceError):
                raise
            raise PDFServiceError(
                f"Failed to extract pages from PDF: {str(e)}",
                "EXTRACTION_FAILED"
            )
    
    def process_pdf(
        self,
        file_bytes: bytes,
        user_id: str,
        document_id: str,
        filename: str = "document.pdf"
    ) -> List[TextChunk]:
        """
        Process a PDF file and return text chunks.
        
        Args:
            file_bytes: Raw PDF file bytes
            user_id: The user's ID
            document_id: The document's ID in the database
            filename: Original filename for metadata
            
        Returns:
            List of TextChunk objects ready for embedding
            
        Raises:
            PDFServiceError: If processing fails
        """
        self._ensure_initialized()
        
        # Extract pages
        pages = self.extract_pages(file_bytes)
        
        if not pages:
            raise PDFServiceError(
                "No text content found in PDF",
                "EMPTY_CONTENT"
            )
        
        # Calculate total text length
        total_chars = sum(p.char_count for p in pages)
        if total_chars < 50:
            raise PDFServiceError(
                "PDF contains very little text. May be a scanned document.",
                "MINIMAL_CONTENT"
            )
        
        # Chunk each page
        all_chunks = []
        chunk_index = 0
        
        for page in pages:
            if not page.content.strip():
                continue
            
            # Chunk this page's content
            page_chunks = chunking_service.chunk_text(page.content)
            
            for chunk in page_chunks:
                all_chunks.append(TextChunk(
                    content=chunk.content,
                    index=chunk_index,
                    token_count=chunk.token_count,
                    page_number=page.page_number,
                    metadata={
                        'document_id': document_id,
                        'filename': filename,
                        'page_number': page.page_number,
                        'user_id': user_id
                    }
                ))
                chunk_index += 1
        
        if not all_chunks:
            raise PDFServiceError(
                "No processable content found in PDF",
                "NO_CHUNKS"
            )
        
        print(f"[PDFService] Processed {filename}: {len(pages)} pages, {len(all_chunks)} chunks")
        return all_chunks
    
    def get_page_count(self, file_bytes: bytes) -> int:
        """
        Get the number of pages in a PDF.
        
        Args:
            file_bytes: Raw PDF file bytes
            
        Returns:
            Number of pages
        """
        self._ensure_initialized()
        
        try:
            pdf_document = self._fitz.open(stream=file_bytes, filetype="pdf")
            page_count = len(pdf_document)
            pdf_document.close()
            return page_count
        except Exception:
            return 0
    
    def extract_text_from_page(
        self,
        file_bytes: bytes,
        page_number: int
    ) -> str:
        """
        Extract text from a specific page.
        
        Args:
            file_bytes: Raw PDF file bytes
            page_number: Page number (1-indexed)
            
        Returns:
            Text content of the page
        """
        self._ensure_initialized()
        
        try:
            pdf_document = self._fitz.open(stream=file_bytes, filetype="pdf")
            
            if page_number < 1 or page_number > len(pdf_document):
                return ""
            
            page = pdf_document[page_number - 1]
            text = page.get_text()
            pdf_document.close()
            
            return text
            
        except Exception:
            return ""


# Singleton instance
pdf_service = PDFService()
