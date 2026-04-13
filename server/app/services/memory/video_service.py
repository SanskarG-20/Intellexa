"""
video_service.py - Video Processing
Extracts audio and transcribes video content using Whisper.
"""

import os
import tempfile
import asyncio
from typing import List, Optional, Tuple
from dataclasses import dataclass

from app.core.config import settings
from app.services.memory.chunking_service import chunking_service, TextChunk


@dataclass
class VideoTranscript:
    """Represents a video transcript."""
    text: str
    duration_seconds: float
    language: str
    segments: List[dict]


class VideoServiceError(Exception):
    """Custom exception for video processing errors."""
    def __init__(self, message: str, code: str):
        self.message = message
        self.code = code
        super().__init__(self.message)


class VideoService:
    """
    Handles video processing including audio extraction
    and transcription using Whisper.
    """
    
    SUPPORTED_FORMATS = {
        'video/mp4': 'mp4',
        'video/quicktime': 'mov',
        'video/x-msvideo': 'avi',
        'video/webm': 'webm',
        'video/x-matroska': 'mkv'
    }
    
    def __init__(self):
        self.max_file_size = settings.get_max_file_size_bytes()
        self._whisper_model = None
        self._initialized = False
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize Whisper model."""
        try:
            from faster_whisper import WhisperModel
            # Use base model for balance of speed and accuracy
            self._whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            self._initialized = True
            print("[VideoService] Initialized with faster-whisper")
        except ImportError:
            print("[VideoService] Warning: faster-whisper not available. Video processing disabled.")
        except Exception as e:
            print(f"[VideoService] Warning: Failed to initialize Whisper: {e}")
    
    def _ensure_initialized(self) -> None:
        """Ensure Whisper is available."""
        if not self._initialized or self._whisper_model is None:
            raise VideoServiceError(
                "Video processing not available. Whisper is not installed.",
                "DEPENDENCY_MISSING"
            )
    
    def validate_video(self, file_bytes: bytes, content_type: str) -> Tuple[bool, str]:
        """
        Validate a video file.
        
        Args:
            file_bytes: Raw video file bytes
            content_type: MIME type of the video
            
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
    
    def _extract_audio(self, video_bytes: bytes, video_path: str) -> str:
        """
        Extract audio from video file using ffmpeg.
        
        Args:
            video_bytes: Raw video file bytes
            video_path: Path to temporary video file
            
        Returns:
            Path to extracted audio file
        """
        import subprocess
        
        audio_path = video_path.rsplit('.', 1)[0] + '.wav'
        
        try:
            # Use ffmpeg to extract audio
            result = subprocess.run(
                [
                    'ffmpeg', '-y', '-i', video_path,
                    '-vn',  # No video
                    '-acodec', 'pcm_s16le',  # WAV format
                    '-ar', '16000',  # 16kHz sample rate (optimal for Whisper)
                    '-ac', '1',  # Mono
                    audio_path
                ],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if result.returncode != 0:
                raise VideoServiceError(
                    f"Audio extraction failed: {result.stderr}",
                    "AUDIO_EXTRACTION_FAILED"
                )
            
            return audio_path
            
        except subprocess.TimeoutExpired:
            raise VideoServiceError(
                "Audio extraction timed out",
                "EXTRACTION_TIMEOUT"
            )
        except FileNotFoundError:
            raise VideoServiceError(
                "ffmpeg not found. Please install ffmpeg for video processing.",
                "FFMPEG_NOT_FOUND"
            )
    
    def transcribe_audio(self, audio_path: str) -> VideoTranscript:
        """
        Transcribe audio file using Whisper.
        
        Args:
            audio_path: Path to audio file
            
        Returns:
            VideoTranscript object
        """
        self._ensure_initialized()
        
        try:
            segments, info = self._whisper_model.transcribe(
                audio_path,
                language=None,  # Auto-detect
                task="transcribe"
            )
            
            # Collect segments
            segment_list = []
            full_text = []
            
            for segment in segments:
                segment_list.append({
                    'start': segment.start,
                    'end': segment.end,
                    'text': segment.text.strip()
                })
                full_text.append(segment.text.strip())
            
            return VideoTranscript(
                text=' '.join(full_text),
                duration_seconds=info.duration,
                language=info.language,
                segments=segment_list
            )
            
        except Exception as e:
            raise VideoServiceError(
                f"Transcription failed: {str(e)}",
                "TRANSCRIPTION_FAILED"
            )
    
    def process_video(
        self,
        file_bytes: bytes,
        user_id: str,
        document_id: str,
        filename: str = "video.mp4",
        content_type: str = "video/mp4"
    ) -> List[TextChunk]:
        """
        Process a video file and return text chunks.
        
        Args:
            file_bytes: Raw video file bytes
            user_id: The user's ID
            document_id: The document's ID in the database
            filename: Original filename for metadata
            content_type: MIME type of the video
            
        Returns:
            List of TextChunk objects ready for embedding
            
        Raises:
            VideoServiceError: If processing fails
        """
        self._ensure_initialized()
        
        is_valid, error = self.validate_video(file_bytes, content_type)
        if not is_valid:
            raise VideoServiceError(error, "INVALID_VIDEO")
        
        # Get file extension
        ext = self.SUPPORTED_FORMATS.get(content_type, 'mp4')
        
        # Create temporary files for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, f"video.{ext}")
            
            try:
                # Write video to temp file
                with open(video_path, 'wb') as f:
                    f.write(file_bytes)
                
                # Extract audio
                print(f"[VideoService] Extracting audio from {filename}...")
                audio_path = self._extract_audio(file_bytes, video_path)
                
                # Transcribe
                print(f"[VideoService] Transcribing audio...")
                transcript = self.transcribe_audio(audio_path)
                
                if not transcript.text.strip():
                    raise VideoServiceError(
                        "No speech detected in video",
                        "NO_SPEECH"
                    )
                
                # Chunk the transcript
                chunks = chunking_service.chunk_text(transcript.text)
                
                # Add metadata
                result_chunks = []
                for chunk in chunks:
                    # Find which segment(s) this chunk belongs to
                    chunk_segments = self._find_segments_for_chunk(
                        chunk.content, transcript.segments
                    )
                    
                    result_chunks.append(TextChunk(
                        content=chunk.content,
                        index=chunk.index,
                        token_count=chunk.token_count,
                        page_number=None,
                        metadata={
                            'document_id': document_id,
                            'filename': filename,
                            'content_type': content_type,
                            'user_id': user_id,
                            'type': 'video_transcript',
                            'language': transcript.language,
                            'duration_seconds': transcript.duration_seconds,
                            'segments': chunk_segments
                        }
                    ))
                
                print(f"[VideoService] Processed {filename}: {transcript.duration_seconds:.1f}s, {len(result_chunks)} chunks")
                return result_chunks
                
            except Exception as e:
                if isinstance(e, VideoServiceError):
                    raise
                raise VideoServiceError(
                    f"Failed to process video: {str(e)}",
                    "PROCESSING_FAILED"
                )
    
    def _find_segments_for_chunk(
        self,
        chunk_content: str,
        segments: List[dict],
        max_segments: int = 10
    ) -> List[dict]:
        """Find transcript segments that overlap with chunk content."""
        matching = []
        chunk_lower = chunk_content.lower()
        
        for segment in segments:
            if len(matching) >= max_segments:
                break
            if segment['text'].lower() in chunk_lower or chunk_lower in segment['text'].lower():
                matching.append({
                    'start': segment['start'],
                    'end': segment['end']
                })
        
        return matching
    
    async def get_video_metadata(self, file_bytes: bytes, content_type: str) -> dict:
        """
        Get basic metadata about a video file.
        
        Args:
            file_bytes: Raw video file bytes
            content_type: MIME type of the video
            
        Returns:
            Dictionary with video metadata
        """
        import subprocess
        
        ext = self.SUPPORTED_FORMATS.get(content_type, 'mp4')
        
        with tempfile.TemporaryDirectory() as temp_dir:
            video_path = os.path.join(temp_dir, f"video.{ext}")
            
            try:
                with open(video_path, 'wb') as f:
                    f.write(file_bytes)
                
                # Use ffprobe to get metadata
                result = subprocess.run(
                    [
                        'ffprobe', '-v', 'quiet',
                        '-print_format', 'json',
                        '-show_format', '-show_streams',
                        video_path
                    ],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    import json
                    return json.loads(result.stdout)
                
            except Exception:
                pass
        
        return {}


# Singleton instance
video_service = VideoService()
