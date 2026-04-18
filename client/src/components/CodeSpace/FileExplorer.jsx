/**
 * FileExplorer.jsx
 * Left panel component for file tree navigation.
 */

import { useState, useMemo } from 'react';

function FileExplorer({
  files,
  activeFileId,
  onSelectFile,
  onCreateFile,
  onDeleteFile,
  onRenameFile,
  isLoading,
}) {
  const [expandedFolders, setExpandedFolders] = useState(new Set());
  const [contextMenu, setContextMenu] = useState(null);

  // Build tree structure
  const fileTree = useMemo(() => {
    const tree = {
      name: 'root',
      path: '/',
      isFolder: true,
      children: [],
    };

    // Sort files: folders first, then alphabetically
    const sorted = [...files].sort((a, b) => {
      if (a.isFolder !== b.isFolder) {
        return a.isFolder ? -1 : 1;
      }
      return a.filename.localeCompare(b.filename);
    });

    // Build tree from flat list
    for (const file of sorted) {
      const pathParts = file.path.split('/').filter(Boolean);
      let current = tree;

      for (const part of pathParts) {
        let child = current.children?.find(c => c.name === part);
        if (!child) {
          child = {
            name: part,
            path: `${current.path}${part}/`,
            isFolder: true,
            children: [],
          };
          current.children = current.children || [];
          current.children.push(child);
        }
        current = child;
      }

      current.children = current.children || [];
      current.children.push({
        id: file.id,
        name: file.filename,
        path: file.path,
        isFolder: file.isFolder,
        language: file.language,
      });
    }

    return tree;
  }, [files]);

  // Toggle folder expansion
  const toggleFolder = (path) => {
    setExpandedFolders(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  // Handle right-click context menu
  const handleContextMenu = (e, item) => {
    e.preventDefault();
    setContextMenu({
      x: e.clientX,
      y: e.clientY,
      item,
    });
  };

  // Close context menu
  const closeContextMenu = () => {
    setContextMenu(null);
  };

  // Get file icon based on type
  const getFileIcon = (item) => {
    if (item.isFolder) {
      return expandedFolders.has(item.path) ? '📂' : '📁';
    }
    
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
    
    return iconMap[item.language] || iconMap.default;
  };

  // Render tree recursively
  const renderTree = (node, depth = 0) => {
    if (!node.children || node.children.length === 0) {
      return null;
    }

    return (
      <ul className="file-tree-list" style={{ paddingLeft: depth * 12 }}>
        {node.children.map((item, index) => (
          <li key={item.id || `${item.path}-${index}`} className="file-tree-item">
            {item.isFolder ? (
              <div
                className={`file-tree-folder ${expandedFolders.has(item.path) ? 'expanded' : ''}`}
                onClick={() => toggleFolder(item.path)}
                onContextMenu={(e) => handleContextMenu(e, item)}
              >
                <span className="file-tree-icon">{getFileIcon(item)}</span>
                <span className="file-tree-name">{item.name}</span>
              </div>
            ) : (
              <div
                className={`file-tree-file ${activeFileId === item.id ? 'active' : ''}`}
                onClick={() => onSelectFile(item.id)}
                onContextMenu={(e) => handleContextMenu(e, item)}
              >
                <span className="file-tree-icon">{getFileIcon(item)}</span>
                <span className="file-tree-name">{item.name}</span>
              </div>
            )}
            
            {item.isFolder && expandedFolders.has(item.path) && renderTree(item, depth + 1)}
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="file-explorer" onClick={closeContextMenu}>
      {isLoading && files.length === 0 ? (
        <div className="file-explorer-loading">
          <span>Loading...</span>
        </div>
      ) : (
        <>
          {renderTree(fileTree)}
          
          {files.length === 0 && (
            <div className="file-explorer-empty">
              <p>No files yet</p>
              <button
                className="file-explorer-create-btn"
                onClick={() => onCreateFile('untitled.js', false)}
              >
                Create your first file
              </button>
            </div>
          )}
        </>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <div
          className="file-context-menu"
          style={{
            position: 'fixed',
            left: contextMenu.x,
            top: contextMenu.y,
            zIndex: 1000,
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {!contextMenu.item.isFolder && (
            <>
              <button onClick={() => {
                onSelectFile(contextMenu.item.id);
                closeContextMenu();
              }}>
                Open
              </button>
            </>
          )}
          <button onClick={() => {
            const newName = prompt('New name:', contextMenu.item.name);
            if (newName) {
              onRenameFile(contextMenu.item.id, newName);
            }
            closeContextMenu();
          }}>
            Rename
          </button>
          <button
            className="file-context-menu-danger"
            onClick={() => {
              onDeleteFile(contextMenu.item.id);
              closeContextMenu();
            }}
          >
            Delete
          </button>
        </div>
      )}
    </div>
  );
}

export default FileExplorer;
