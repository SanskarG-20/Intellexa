/**
 * ImportFromVSCode.jsx
 * Modal for importing files from VS Code or local filesystem.
 */

import { useState, useCallback, useRef } from 'react';
import { detectLanguage } from '../../services/codeFileService';

const ACCEPTED_EXTENSIONS = [
  '.js', '.jsx', '.ts', '.tsx', '.py', '.java', '.go', '.rs',
  '.c', '.cpp', '.h', '.hpp', '.cs', '.php', '.rb', '.swift',
  '.html', '.css', '.scss', '.sass', '.less', '.json', '.yaml', '.yml',
  '.xml', '.md', '.txt', '.sql', '.sh', '.bash',
];

function ImportFromVSCode({ onImport, onClose }) {
  const [isDragging, setIsDragging] = useState(false);
  const [importedFiles, setImportedFiles] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState(null);
  
  const fileInputRef = useRef(null);

  // Process files
  const processFiles = useCallback(async (fileList) => {
    setIsProcessing(true);
    setError(null);
    
    const files = [];
    
    for (const file of fileList) {
      // Check extension
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        continue;
      }
      
      try {
        const content = await readFileContent(file);
        const path = file.webkitRelativePath || `/${file.name}`;
        
        files.push({
          filename: file.name,
          path: path.substring(0, path.lastIndexOf('/')) || '/',
          content,
          language: detectLanguage(file.name),
        });
      } catch (err) {
        console.error(`Failed to read ${file.name}:`, err);
      }
    }
    
    setImportedFiles(files);
    setIsProcessing(false);
  }, []);

  // Read file content
  const readFileContent = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  // Handle file selection
  const handleFileSelect = useCallback((e) => {
    const files = e.target.files;
    if (files?.length) {
      processFiles(files);
    }
  }, [processFiles]);

  // Handle drag events
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    setIsDragging(false);
    
    const files = e.dataTransfer.files;
    if (files?.length) {
      processFiles(files);
    }
  }, [processFiles]);

  // Handle import
  const handleImport = useCallback(async () => {
    if (importedFiles.length === 0) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const result = await onImport(importedFiles);
      if (result?.success) {
        onClose();
      } else {
        setError(result?.errors?.join(', ') || 'Import failed');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setIsProcessing(false);
    }
  }, [importedFiles, onImport, onClose]);

  // Handle folder selection
  const handleFolderSelect = useCallback((e) => {
    const files = e.target.files;
    if (files?.length) {
      processFiles(files);
    }
  }, [processFiles]);

  return (
    <div className="import-modal-overlay" onClick={onClose}>
      <div className="import-modal" onClick={(e) => e.stopPropagation()}>
        <div className="import-modal-header">
          <h2>Import Files</h2>
          <button className="import-modal-close" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="import-modal-body">
          {/* Drop Zone */}
          <div
            className={`import-drop-zone ${isDragging ? 'dragging' : ''}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept={ACCEPTED_EXTENSIONS.join(',')}
              onChange={handleFileSelect}
              style={{ display: 'none' }}
            />
            
            <div className="import-drop-zone-content">
              <span className="import-drop-zone-icon">📁</span>
              <p>Drag & drop files here</p>
              <p className="import-drop-zone-hint">
                or click to select files
              </p>
            </div>
          </div>

          {/* Folder Selection */}
          <div className="import-folder-section">
            <p>Import from folder:</p>
            <label className="import-folder-btn">
              Select Folder
              <input
                type="file"
                webkitdirectory=""
                directory=""
                onChange={handleFolderSelect}
                style={{ display: 'none' }}
              />
            </label>
          </div>

          {/* File Preview */}
          {importedFiles.length > 0 && (
            <div className="import-preview">
              <h4>{importedFiles.length} files selected</h4>
              <ul className="import-file-list">
                {importedFiles.slice(0, 10).map((file, index) => (
                  <li key={index} className="import-file-item">
                    <span className="import-file-icon">
                      {file.language === 'javascript' ? '📜' : 
                       file.language === 'python' ? '🐍' : '📄'}
                    </span>
                    <span className="import-file-name">{file.filename}</span>
                    <span className="import-file-path">{file.path}</span>
                  </li>
                ))}
                {importedFiles.length > 10 && (
                  <li className="import-file-more">
                    +{importedFiles.length - 10} more files
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="import-error">
              {error}
            </div>
          )}
        </div>

        <div className="import-modal-footer">
          <button
            className="import-cancel-btn"
            onClick={onClose}
            disabled={isProcessing}
          >
            Cancel
          </button>
          <button
            className="import-confirm-btn"
            onClick={handleImport}
            disabled={isProcessing || importedFiles.length === 0}
          >
            {isProcessing ? 'Importing...' : `Import ${importedFiles.length} Files`}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ImportFromVSCode;
