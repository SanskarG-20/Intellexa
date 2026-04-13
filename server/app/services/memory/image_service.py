"""
image_service.py - Image Processing
Extracts text from images using Gemini Vision and OCR.
"""

import base64
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings
from app.services.memory.chunking_service import chunking_service, TextChunk

# Try new SDK first, fall back to deprecated
try:
    from google import genai
    from google.genai import types
    USE_NEW_SDK = True
except ImportError:
    import google.generativeai as genai
    USE_NEW_SDK = False


@dataclass
class ImageAnalysis:
    """Represents analysis results for an image."""
    caption: str
    extracted_text: str
    description: str
    confidence: float


class ImageServiceError(Exception):
    """Custom exception for image processing errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ImageService:
    """
    Handles image processing using Gemini Vision for captions
    and text extraction.
    """
    
    SUPPORTED_FORMATS = {
        'image/jpeg': 'jpg',
        'image/jpg': 'jpg',
        'image/png': 'png',
        'image/webp': 'webp',
        'image/gif': 'gif'
    }
    
    def __init__(self):
        self.max_file_size = settings.get_max_file_size_bytes()
        self._gemini_model = None
        self._client = None
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Gemini Vision model."""
        try:
            if not settings.GEMINI_API_KEY:
                print("[ImageService] Warning: GEMINI_API_KEY not configured")
                return
            
            if USE_NEW_SDK:
                self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
                self._model_name = 'gemini-2.0-flash'
            else:
                genai.configure(api_key=settings.GEMINI_API_KEY)
                self._gemini_model = genai.GenerativeModel('gemini-1.5-flash')
            
            print("[ImageService] Initialized with Gemini Vision")
        except Exception as e:
            print(f"[ImageService] Warning: Gemini not available: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure Gemini Vision is available."""
        if USE_NEW_SDK and self._client:
            return
        if self._gemini_model is None:
            raise ImageServiceError(
                "Image processing not available. Gemini API not configured.",
                "DEPENDENCY_MISSING"
            )
    
    def validate_image(self, file_bytes: bytes, content_type: str) -> Tuple[bool, str]:
        """
        Validate an image file.
        
        Args:
            file_bytes: Raw image file bytes
            content_type: MIME type of the image
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not file_bytes:
            return False, "Empty file"
        
        if len(file_bytes) > self.max_file_size:
            return False, f"File too large. Max size: {settings.MAX_FILE_SIZE_MB}MB"
        
        if content_type not in self.SUPPORTED_FORMATS:
            return False, f"Unsupported format. Supported: {list(self.SUPPORTED_FORMATS.keys())}"
        
        return True, ""
    
    def _encode_image(self, file_bytes: bytes) -> str:
        """Encode image bytes to base64."""
        return base64.b64encode(file_bytes).decode('utf-8')
    
    async def analyze_image(
        self,
        file_bytes: bytes,
        content_type: str = "image/jpeg"
    ) -> ImageAnalysis:
        """
        Analyze an image using Gemini Vision.
        
        Args:
            file_bytes: Raw image file bytes
            content_type: MIME type of the image
            
        Returns:
            ImageAnalysis object with caption, text, and description
            
        Raises:
            ImageServiceError: If analysis fails
        """
        self._ensure_initialized()
        
        is_valid, error = self.validate_image(file_bytes, content_type)
        if not is_valid:
            raise ImageServiceError(error, "INVALID_IMAGE")
        
        try:
            import google.generativeai as genai
            
            # Determine MIME type for Gemini
            mime_type = content_type
            if mime_type == 'image/jpg':
                mime_type = 'image/jpeg'
            
            # Create image part for Gemini
            image_part = {
                'mime_type': mime_type,
                'data': file_bytes
            }
            
            # Generate comprehensive analysis
            prompt = """Analyze this image and provide:
1. A brief caption (one sentence)
2. Any text visible in the image (transcribe exactly)
3. A detailed description of what you see

Format your response as:
CAPTION: [one sentence caption]
TEXT: [any visible text, or "None" if no text is visible]
DESCRIPTION: [detailed description]"""
            
            response = await self._generate_async(prompt, [image_part])
            
            # Parse response
            caption, extracted_text, description = self._parse_analysis_response(response)
            
            return ImageAnalysis(
                caption=caption,
                extracted_text=extracted_text,
                description=description,
                confidence=0.9  # Default confidence for Gemini
            )
            
        except Exception as e:
            if isinstance(e, ImageServiceError):
                raise
            raise ImageServiceError(
                f"Failed to analyze image: {str(e)}",
                "ANALYSIS_FAILED"
            )
    
    async def _generate_async(self, prompt: str, content: list) -> str:
        """Generate content asynchronously."""
        import asyncio
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._generate_sync,
            prompt,
            content
        )
        return result
    
    def _generate_sync(self, prompt: str, content: list) -> str:
        """Generate content synchronously (run in executor)."""
        response = self._gemini_model.generate_content([prompt, *content])
        return response.text
    
    def _parse_analysis_response(self, response: str) -> Tuple[str, str, str]:
        """Parse Gemini's analysis response."""
        caption = ""
        extracted_text = ""
        description = ""
        
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if line.startswith('CAPTION:'):
                current_section = 'caption'
                caption = line[8:].strip()
            elif line.startswith('TEXT:'):
                current_section = 'text'
                extracted_text = line[5:].strip()
            elif line.startswith('DESCRIPTION:'):
                current_section = 'description'
                description = line[12:].strip()
            elif current_section == 'text':
                extracted_text += " " + line
            elif current_section == 'description':
                description += " " + line
        
        # Clean up
        if extracted_text.lower() in ['none', 'n/a', 'no text']:
            extracted_text = ""
        
        return caption.strip(), extracted_text.strip(), description.strip()
    
    async def extract_text_ocr(self, file_bytes: bytes) -> str:
        """
        Extract text from an image using Gemini Vision.
        
        Args:
            file_bytes: Raw image file bytes
            
        Returns:
            Extracted text string
        """
        self._ensure_initialized()
        
        try:
            import google.generativeai as genai
            
            image_part = {
                'mime_type': 'image/jpeg',  # Default, will work for most images
                'data': file_bytes
            }
            
            prompt = """Extract and transcribe ALL text visible in this image.
Only output the text, nothing else.
If no text is visible, output: [NO TEXT FOUND]"""
            
            response = await self._generate_async(prompt, [image_part])
            
            if '[NO TEXT FOUND]' in response:
                return ""
            
            return response.strip()
            
        except Exception as e:
            print(f"[ImageService] OCR error: {e}")
            return ""
    
    async def generate_caption(self, file_bytes: bytes) -> str:
        """
        Generate a caption for an image.
        
        Args:
            file_bytes: Raw image file bytes
            
        Returns:
            Caption string
        """
        self._ensure_initialized()
        
        try:
            import google.generativeai as genai
            
            image_part = {
                'mime_type': 'image/jpeg',
                'data': file_bytes
            }
            
            prompt = "Provide a brief, one-sentence caption for this image."
            
            response = await self._generate_async(prompt, [image_part])
            return response.strip()
            
        except Exception as e:
            print(f"[ImageService] Caption error: {e}")
            return "Image content"
    
    def process_image(
        self,
        file_bytes: bytes,
        user_id: str,
        document_id: str,
        filename: str = "image.jpg",
        content_type: str = "image/jpeg"
    ) -> List[TextChunk]:
        """
        Process an image file and return text chunks.
        This is a sync wrapper for the async methods.
        
        Args:
            file_bytes: Raw image file bytes
            user_id: The user's ID
            document_id: The document's ID in the database
            filename: Original filename for metadata
            content_type: MIME type of the image
            
        Returns:
            List of TextChunk objects ready for embedding
            
        Note:
            This method should be called from an async context.
            Use asyncio.run() for sync contexts.
        """
        import asyncio
        
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(
            self._process_image_async(
                file_bytes, user_id, document_id, filename, content_type
            )
        )
    
    async def _process_image_async(
        self,
        file_bytes: bytes,
        user_id: str,
        document_id: str,
        filename: str,
        content_type: str
    ) -> List[TextChunk]:
        """Async implementation of process_image."""
        self._ensure_initialized()
        
        is_valid, error = self.validate_image(file_bytes, content_type)
        if not is_valid:
            raise ImageServiceError(error, "INVALID_IMAGE")
        
        # Analyze the image
        analysis = await self.analyze_image(file_bytes, content_type)
        
        # Combine all extracted information
        content_parts = []
        
        if analysis.caption:
            content_parts.append(f"Image Caption: {analysis.caption}")
        
        if analysis.extracted_text:
            content_parts.append(f"Text in Image: {analysis.extracted_text}")
        
        if analysis.description:
            content_parts.append(f"Description: {analysis.description}")
        
        combined_content = "\n\n".join(content_parts)
        
        if not combined_content.strip():
            raise ImageServiceError(
                "No content could be extracted from the image",
                "EMPTY_CONTENT"
            )
        
        # Create a single chunk for the image
        # Images typically produce less text, so one chunk is usually sufficient
        chunk = TextChunk(
            content=combined_content,
            index=0,
            token_count=chunking_service._estimate_tokens(combined_content),
            page_number=None,
            metadata={
                'document_id': document_id,
                'filename': filename,
                'content_type': content_type,
                'user_id': user_id,
                'type': 'image_analysis',
                'caption': analysis.caption,
                'has_text': bool(analysis.extracted_text)
            }
        )
        
        print(f"[ImageService] Processed {filename}: {len(combined_content)} chars")
        return [chunk]


# Singleton instance
image_service = ImageService()
