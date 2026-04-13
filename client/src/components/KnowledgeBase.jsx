/**
 * KnowledgeBase.jsx - Document Management Component
 * Displays user's uploaded documents and allows deletion.
 */

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

const FILE_TYPE_ICONS = {
  pdf: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  ),
  image: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
      <circle cx="8.5" cy="8.5" r="1.5" />
      <polyline points="21,15 16,10 5,21" />
    </svg>
  ),
  video: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="23,7 16,12 23,17 23,7" />
      <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
    </svg>
  ),
  default: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14,2 14,8 20,8" />
    </svg>
  )
};

const STATUS_COLORS = {
  pending: "#f59e0b",
  processing: "#3b82f6",
  ready: "#10b981",
  failed: "#ef4444"
};

function formatFileSize(bytes) {
  if (!bytes) return "Unknown size";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(dateString) {
  if (!dateString) return "";
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function KnowledgeBase({ refreshTrigger }) {
  const { getToken } = useAuth();
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [stats, setStats] = useState(null);

  const fetchDocuments = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const token = await getToken();
      
      const response = await fetch(`${API_BASE_URL}/api/v1/memory/documents`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch documents: ${response.status}`);
      }

      const data = await response.json();
      setDocuments(data.documents || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load documents");
    } finally {
      setIsLoading(false);
    }
  }, [getToken]);

  const fetchStats = useCallback(async () => {
    try {
      const token = await getToken();
      
      const response = await fetch(`${API_BASE_URL}/api/v1/memory/stats`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (response.ok) {
        const data = await response.json();
        setStats(data);
      }
    } catch (err) {
      console.error("Failed to fetch stats:", err);
    }
  }, [getToken]);

  useEffect(() => {
    fetchDocuments();
    fetchStats();
  }, [fetchDocuments, fetchStats, refreshTrigger]);

  const handleDelete = async (documentId, filename) => {
    if (!window.confirm(`Delete "${filename}"? This cannot be undone.`)) {
      return;
    }

    setDeletingId(documentId);

    try {
      const token = await getToken();
      
      const response = await fetch(`${API_BASE_URL}/api/v1/memory/documents/${documentId}`, {
        method: "DELETE",
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to delete document: ${response.status}`);
      }

      setDocuments((prev) => prev.filter((doc) => doc.id !== documentId));
      fetchStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete document");
    } finally {
      setDeletingId(null);
    }
  };

  const handleRefresh = () => {
    fetchDocuments();
    fetchStats();
  };

  if (isLoading) {
    return (
      <div className="knowledge-base">
        <div className="knowledge-base-loading">
          <div className="knowledge-base-spinner" />
          <p>Loading your knowledge base...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="knowledge-base">
      <div className="knowledge-base-header">
        <h2 className="knowledge-base-title">My Knowledge</h2>
        <button
          type="button"
          className="knowledge-base-refresh"
          onClick={handleRefresh}
          aria-label="Refresh documents"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <polyline points="23,4 23,10 17,10" />
            <polyline points="1,20 1,14 7,14" />
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
          </svg>
          Refresh
        </button>
      </div>

      {error && (
        <div className="knowledge-base-error">
          {error}
          <button type="button" onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {stats && (
        <div className="knowledge-base-stats">
          <div className="knowledge-base-stat">
            <span className="knowledge-base-stat-value">{stats.total_documents}</span>
            <span className="knowledge-base-stat-label">Documents</span>
          </div>
          <div className="knowledge-base-stat">
            <span className="knowledge-base-stat-value">{stats.total_chunks}</span>
            <span className="knowledge-base-stat-label">Chunks</span>
          </div>
          <div className="knowledge-base-stat">
            <span className="knowledge-base-stat-value">
              {formatFileSize(stats.storage_used_bytes)}
            </span>
            <span className="knowledge-base-stat-label">Storage Used</span>
          </div>
        </div>
      )}

      {documents.length === 0 ? (
        <div className="knowledge-base-empty">
          <div className="knowledge-base-empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14,2 14,8 20,8" />
              <line x1="12" y1="18" x2="12" y2="12" />
              <line x1="9" y1="15" x2="15" y2="15" />
            </svg>
          </div>
          <p>No documents uploaded yet</p>
          <p className="knowledge-base-empty-hint">
            Upload PDFs, images, or videos to build your personal knowledge base
          </p>
        </div>
      ) : (
        <div className="knowledge-base-list">
          {documents.map((doc) => (
            <div key={doc.id} className="knowledge-base-item">
              <div className="knowledge-base-item-icon">
                {FILE_TYPE_ICONS[doc.file_type] || FILE_TYPE_ICONS.default}
              </div>
              
              <div className="knowledge-base-item-content">
                <h3 className="knowledge-base-item-filename">{doc.filename}</h3>
                <div className="knowledge-base-item-meta">
                  <span className="knowledge-base-item-type">{doc.file_type.toUpperCase()}</span>
                  <span className="knowledge-base-item-size">{formatFileSize(doc.file_size)}</span>
                  {doc.chunk_count !== null && (
                    <span className="knowledge-base-item-chunks">
                      {doc.chunk_count} chunks
                    </span>
                  )}
                  <span 
                    className="knowledge-base-item-status"
                    style={{ color: STATUS_COLORS[doc.status] }}
                  >
                    {doc.status}
                  </span>
                </div>
                <p className="knowledge-base-item-date">
                  Uploaded {formatDate(doc.created_at)}
                </p>
                {doc.error_message && (
                  <p className="knowledge-base-item-error">{doc.error_message}</p>
                )}
              </div>
              
              <div className="knowledge-base-item-actions">
                <button
                  type="button"
                  className="knowledge-base-item-delete"
                  onClick={() => handleDelete(doc.id, doc.filename)}
                  disabled={deletingId === doc.id}
                  aria-label={`Delete ${doc.filename}`}
                >
                  {deletingId === doc.id ? (
                    <span className="knowledge-base-item-deleting">Deleting...</span>
                  ) : (
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polyline points="3,6 5,6 21,6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default KnowledgeBase;
