/**
 * MemoryUpload.jsx - File Upload Component for Knowledge Base
 * Supports drag-and-drop upload of PDFs, images, and videos.
 */

import { useState, useCallback, useRef } from "react";
import { useAuth } from "@clerk/clerk-react";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SUPPORTED_FILE_TYPES = {
  pdf: { extensions: [".pdf"], mimeTypes: ["application/pdf"], label: "PDF" },
  image: {
    extensions: [".jpg", ".jpeg", ".png", ".webp", ".gif"],
    mimeTypes: ["image/jpeg", "image/png", "image/webp", "image/gif"],
    label: "Image"
  },
  video: {
    extensions: [".mp4", ".mov", ".avi", ".webm", ".mkv"],
    mimeTypes: ["video/mp4", "video/quicktime", "video/x-msvideo", "video/webm", "video/x-matroska"],
    label: "Video"
  }
};

const MAX_FILE_SIZE_MB = 50;

function detectFileType(file) {
  const extension = "." + file.name.split(".").pop().toLowerCase();
  const mimeType = file.type.toLowerCase();

  for (const [type, config] of Object.entries(SUPPORTED_FILE_TYPES)) {
    if (config.extensions.includes(extension) || config.mimeTypes.includes(mimeType)) {
      return type;
    }
  }
  return null;
}

function MemoryUpload({ onUploadComplete, onUploadError }) {
  const { getToken } = useAuth();
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploadStatus, setUploadStatus] = useState(null);
  const fileInputRef = useRef(null);

  const handleDragOver = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((event) => {
    event.preventDefault();
    event.stopPropagation();
    setIsDragging(false);

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      handleFileSelection(files[0]);
    }
  }, []);

  const handleFileSelection = useCallback((file) => {
    // Validate file size
    const maxSizeBytes = MAX_FILE_SIZE_MB * 1024 * 1024;
    if (file.size > maxSizeBytes) {
      const error = `File too large. Maximum size is ${MAX_FILE_SIZE_MB}MB.`;
      setUploadStatus({ type: "error", message: error });
      onUploadError?.(error);
      return;
    }

    // Validate file type
    const fileType = detectFileType(file);
    if (!fileType) {
      const error = "Unsupported file type. Please upload PDF, image, or video files.";
      setUploadStatus({ type: "error", message: error });
      onUploadError?.(error);
      return;
    }

    setSelectedFile(file);
    setUploadStatus({ type: "info", message: `Ready to upload: ${file.name} (${fileType})` });
  }, [onUploadError]);

  const handleInputChange = useCallback((event) => {
    const files = event.target.files;
    if (files && files.length > 0) {
      handleFileSelection(files[0]);
    }
  }, [handleFileSelection]);

  const handleUpload = useCallback(async () => {
    if (!selectedFile) return;

    setIsUploading(true);
    setUploadProgress(0);
    setUploadStatus({ type: "info", message: "Uploading..." });

    try {
      const token = await getToken();
      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await fetch(`${API_BASE_URL}/api/v1/memory/upload`, {
        method: "POST",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Upload failed: ${response.status}`);
      }

      const result = await response.json();
      
      setUploadProgress(100);
      setUploadStatus({ 
        type: "success", 
        message: `File uploaded successfully! Processing document...` 
      });
      
      setSelectedFile(null);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      
      onUploadComplete?.(result);
      
      // Poll for processing status
      pollProcessingStatus(result.document_id, token);
      
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Upload failed";
      setUploadStatus({ type: "error", message: errorMessage });
      onUploadError?.(errorMessage);
    } finally {
      setIsUploading(false);
    }
  }, [selectedFile, getToken, onUploadComplete, onUploadError]);

  const pollProcessingStatus = async (documentId, token) => {
    let attempts = 0;
    const maxAttempts = 60; // 5 minutes max (5 seconds each)
    
    const poll = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/memory/status/${documentId}`, {
          headers: {
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
        });
        
        if (!response.ok) return;
        
        const status = await response.json();
        
        if (status.status === "ready") {
          setUploadStatus({ 
            type: "success", 
            message: `Document processed! ${status.chunk_count || 0} chunks indexed.` 
          });
          return;
        }
        
        if (status.status === "failed") {
          setUploadStatus({ 
            type: "error", 
            message: `Processing failed: ${status.error || "Unknown error"}` 
          });
          return;
        }
        
        // Still processing, continue polling
        attempts++;
        if (attempts < maxAttempts) {
          setTimeout(poll, 5000);
        }
      } catch (error) {
        console.error("Status polling error:", error);
      }
    };
    
    setTimeout(poll, 2000);
  };

  const handleClearSelection = useCallback(() => {
    setSelectedFile(null);
    setUploadStatus(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }, []);

  return (
    <div className="memory-upload">
      <div
        className={`memory-upload-dropzone ${isDragging ? "is-dragging" : ""}`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        role="button"
        tabIndex={0}
        aria-label="Click to upload or drag and drop files"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp,.gif,.mp4,.mov,.avi,.webm,.mkv"
          onChange={handleInputChange}
          className="memory-upload-input"
          disabled={isUploading}
        />
        
        <div className="memory-upload-icon">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17,8 12,3 7,8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        
        <p className="memory-upload-text">
          {isDragging 
            ? "Drop your file here" 
            : "Drag and drop files here, or click to browse"}
        </p>
        
        <p className="memory-upload-hint">
          Supported: PDF, Images (JPG, PNG, WebP, GIF), Videos (MP4, MOV, WebM)
          <br />
          Max file size: {MAX_FILE_SIZE_MB}MB
        </p>
      </div>

      {selectedFile && (
        <div className="memory-upload-selected">
          <div className="memory-upload-file-info">
            <span className="memory-upload-filename">{selectedFile.name}</span>
            <span className="memory-upload-filesize">
              {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
            </span>
          </div>
          
          <div className="memory-upload-actions">
            <button
              type="button"
              className="memory-upload-clear"
              onClick={handleClearSelection}
              disabled={isUploading}
            >
              Clear
            </button>
            
            <button
              type="button"
              className="memory-upload-submit"
              onClick={handleUpload}
              disabled={isUploading}
            >
              {isUploading ? "Uploading..." : "Upload"}
            </button>
          </div>
        </div>
      )}

      {uploadStatus && (
        <div className={`memory-upload-status memory-upload-status-${uploadStatus.type}`}>
          {uploadStatus.message}
        </div>
      )}

      {isUploading && (
        <div className="memory-upload-progress">
          <div 
            className="memory-upload-progress-bar" 
            style={{ width: `${uploadProgress}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default MemoryUpload;
