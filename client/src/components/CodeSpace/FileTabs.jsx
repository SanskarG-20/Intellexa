/**
 * FileTabs.jsx
 * Tab bar for open files in the editor.
 */

import { useRef, useEffect } from 'react';

function FileTabs({
  files,
  activeFileId,
  isDirty,
  onSelect,
  onClose,
}) {
  const tabsRef = useRef(null);
  const activeTabRef = useRef(null);

  // Scroll active tab into view
  useEffect(() => {
    if (activeTabRef.current && tabsRef.current) {
      const container = tabsRef.current;
      const tab = activeTabRef.current;
      
      const containerRect = container.getBoundingClientRect();
      const tabRect = tab.getBoundingClientRect();
      
      if (tabRect.left < containerRect.left) {
        container.scrollLeft -= (containerRect.left - tabRect.left + 20);
      } else if (tabRect.right > containerRect.right) {
        container.scrollLeft += (tabRect.right - containerRect.right + 20);
      }
    }
  }, [activeFileId]);

  if (files.length === 0) {
    return <div className="file-tabs-empty" />;
  }

  // Get file icon
  const getFileIcon = (file) => {
    const iconMap = {
      'javascript': '📜',
      'typescript': '📘',
      'python': '🐍',
      'html': '🌐',
      'css': '🎨',
      'json': '📋',
      'markdown': '📝',
      'default': '📄',
    };
    
    return iconMap[file.language] || iconMap.default;
  };

  // Handle middle-click to close
  const handleMouseDown = (e, fileId) => {
    if (e.button === 1) { // Middle click
      e.preventDefault();
      onClose(fileId);
    }
  };

  return (
    <div className="file-tabs" ref={tabsRef}>
      {files.map((file) => {
        const isActive = file.id === activeFileId;
        const isFileDirty = isDirty[file.id];
        
        return (
          <div
            key={file.id}
            ref={isActive ? activeTabRef : null}
            className={`file-tab ${isActive ? 'active' : ''} ${isFileDirty ? 'dirty' : ''}`}
            onClick={() => onSelect(file.id)}
            onMouseDown={(e) => handleMouseDown(e, file.id)}
          >
            <span className="file-tab-icon">{getFileIcon(file)}</span>
            <span className="file-tab-name">{file.filename}</span>
            <span className="file-tab-dirty">{isFileDirty ? '●' : ''}</span>
            <button
              className="file-tab-close"
              onClick={(e) => {
                e.stopPropagation();
                onClose(file.id);
              }}
              title="Close (Ctrl+W)"
            >
              ×
            </button>
          </div>
        );
      })}
    </div>
  );
}

export default FileTabs;
