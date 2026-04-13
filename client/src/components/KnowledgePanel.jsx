/**
 * KnowledgePanel.jsx - Combined Upload & Knowledge Base Panel
 * A tabbed interface for managing personal knowledge.
 */

import { useState, useCallback } from "react";
import MemoryUpload from "./MemoryUpload";
import KnowledgeBase from "./KnowledgeBase";

function KnowledgePanel({ onUploadComplete }) {
  const [activeTab, setActiveTab] = useState("documents");
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleUploadComplete = useCallback((result) => {
    // Trigger refresh of document list
    setRefreshTrigger((prev) => prev + 1);
    onUploadComplete?.(result);
  }, [onUploadComplete]);

  return (
    <div className="knowledge-panel">
      <div className="knowledge-panel-tabs">
        <button
          type="button"
          className={`knowledge-panel-tab ${activeTab === "documents" ? "is-active" : ""}`}
          onClick={() => setActiveTab("documents")}
        >
          My Documents
        </button>
        <button
          type="button"
          className={`knowledge-panel-tab ${activeTab === "upload" ? "is-active" : ""}`}
          onClick={() => setActiveTab("upload")}
        >
          Upload
        </button>
      </div>

      <div className="knowledge-panel-content">
        {activeTab === "documents" ? (
          <KnowledgeBase refreshTrigger={refreshTrigger} />
        ) : (
          <MemoryUpload 
            onUploadComplete={handleUploadComplete}
            onUploadError={(error) => console.error("Upload error:", error)}
          />
        )}
      </div>
    </div>
  );
}

export default KnowledgePanel;
