/**
 * CodeSpaceLayout.jsx
 * Main 3-panel layout for the Code Space feature.
 * Left: File Explorer | Center: Code Editor | Right: AI Assistant
 */

import { useState, useCallback, useEffect } from 'react';
import { useUser } from '@clerk/clerk-react';
import FileExplorer from './FileExplorer';
import CodeEditor from './CodeEditor';
import CodeAssistant from './CodeAssistant';
import ExecutionPanel from './ExecutionPanel';
import FileTabs from './FileTabs';
import ImportFromVSCode from './ImportFromVSCode';
import useVirtualFileSystem from '../../hooks/useVirtualFileSystem';
import useCodeExecution from '../../hooks/useCodeExecution';
import { useCodeWorkspaceState } from '../../context/CodeWorkspaceContext';

const DEFAULT_LAYOUT = {
  leftPanel: 240,
  rightPanel: 320,
};

function CodeSpaceLayout() {
  const { user } = useUser();
  const userId = user?.id;
  const { state: workspaceState, actions: workspaceActions } = useCodeWorkspaceState();
  
  const [showImport, setShowImport] = useState(false);
  const [assistantExpanded, setAssistantExpanded] = useState(true);

  const {
    isRunning: isExecuting,
    result: executionResult,
    error: executionError,
    runCode,
    clearResult,
  } = useCodeExecution();
  
  const {
    files,
    openFiles,
    activeFile,
    activeFileId,
    isLoading,
    error,
    isDirty,
    createFile,
    openFile,
    closeFile,
    updateFileContent,
    saveFile,
    deleteFile,
    renameFile,
    importFiles,
    setActiveFileId,
  } = useVirtualFileSystem(userId);

  // Sync active file state for global workspace context
  useEffect(() => {
    workspaceActions.setActiveFile(activeFileId);
  }, [activeFileId, workspaceActions]);

  useEffect(() => {
    if (activeFileId) {
      workspaceActions.syncFileContent(activeFileId, activeFile?.content || '');
    }
  }, [activeFile?.content, activeFileId, workspaceActions]);

  // Handle file selection
  const handleFileSelect = useCallback((fileId) => {
    openFile(fileId);
  }, [openFile]);

  // Handle file creation
  const handleCreateFile = useCallback(async (filename, isFolder = false) => {
    const newFile = await createFile(filename, '/', isFolder);
    if (newFile && !isFolder) {
      openFile(newFile.id);
    }
    return newFile;
  }, [createFile, openFile]);

  // Handle file deletion
  const handleDeleteFile = useCallback(async (fileId) => {
    const confirmed = window.confirm('Delete this file?');
    if (confirmed) {
      await deleteFile(fileId);
    }
  }, [deleteFile]);

  // Handle code changes
  const handleCodeChange = useCallback((value) => {
    if (activeFileId) {
      updateFileContent(activeFileId, value || '');
    }
  }, [activeFileId, updateFileContent]);

  // Apply AI-generated code into active file and persist it.
  const handleApplyAssistantCode = useCallback(async (code) => {
    if (!activeFileId) {
      return;
    }

    updateFileContent(activeFileId, code || '');
    await saveFile(activeFileId);
    workspaceActions.pushAiResponse({
      type: 'apply_code',
      fileId: activeFileId,
      timestamp: new Date().toISOString(),
      preview: String(code || '').slice(0, 120),
    });
  }, [activeFileId, saveFile, updateFileContent, workspaceActions]);

  const handleAssistantInteraction = useCallback((event) => {
    if (!event?.type || !event?.payload) {
      return;
    }

    const payload = {
      ...event.payload,
      fileId: activeFileId,
      timestamp: new Date().toISOString(),
    };

    if (event.type === 'user') {
      workspaceActions.pushChatMessage(payload);
    }
    if (event.type === 'assistant') {
      workspaceActions.pushAiResponse(payload);
    }
  }, [activeFileId, workspaceActions]);

  const handleRunCode = useCallback(async (options = {}) => {
    if (!activeFile) {
      return null;
    }

    const response = await runCode({
      code: activeFile.content || '',
      language: activeFile.language || 'javascript',
      stdin: options.stdin || '',
      timeoutMs: options.timeoutMs || 3000,
    });

    const message = response?.success
      ? `Executed ${activeFile.filename} successfully (${response?.result?.runtime_ms || 0}ms).`
      : `Execution failed for ${activeFile.filename}: ${response?.error || 'Unknown error'}`;

    workspaceActions.pushExecutionLog({
      timestamp: new Date().toISOString(),
      message,
    });

    return response;
  }, [activeFile, runCode, workspaceActions]);

  const handleClearExecutionLogs = useCallback(() => {
    workspaceActions.clearExecutionLogs();
    clearResult();
  }, [clearResult, workspaceActions]);

  // Handle save
  const handleSave = useCallback(async () => {
    if (activeFileId && isDirty[activeFileId]) {
      await saveFile(activeFileId);
    }
  }, [activeFileId, isDirty, saveFile]);

  // Handle import
  const handleImport = useCallback(async (importedFiles) => {
    const result = await importFiles(importedFiles);
    if (result?.success) {
      setShowImport(false);
    }
    return result;
  }, [importFiles]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Ctrl/Cmd + S to save
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        handleSave();
      }
      // Ctrl/Cmd + W to close tab
      if ((e.ctrlKey || e.metaKey) && e.key === 'w') {
        e.preventDefault();
        if (activeFileId) {
          closeFile(activeFileId);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleSave, activeFileId, closeFile]);

  return (
    <div className="codespace-layout">
      {/* Left Panel - File Explorer */}
      <aside 
        className="codespace-panel codespace-panel-left"
        style={{ width: DEFAULT_LAYOUT.leftPanel }}
      >
        <div className="codespace-panel-header">
          <h3 className="codespace-panel-title">Explorer</h3>
          <div className="codespace-panel-actions">
            <button
              className="codespace-icon-btn"
              onClick={() => handleCreateFile(prompt('File name:') || 'untitled.js', false)}
              title="New File"
            >
              +
            </button>
            <button
              className="codespace-icon-btn"
              onClick={() => handleCreateFile(prompt('Folder name:') || 'new-folder', true)}
              title="New Folder"
            >
              📁
            </button>
            <button
              className="codespace-icon-btn"
              onClick={() => setShowImport(true)}
              title="Import Files"
            >
              ⬆️
            </button>
          </div>
        </div>
        
        <FileExplorer
          files={files}
          activeFileId={activeFileId}
          onSelectFile={handleFileSelect}
          onCreateFile={handleCreateFile}
          onDeleteFile={handleDeleteFile}
          onRenameFile={renameFile}
          isLoading={isLoading}
        />
      </aside>

      {/* Center Panel - Code Editor */}
      <main className="codespace-main">
        {/* File Tabs */}
        <FileTabs
          files={openFiles}
          activeFileId={activeFileId}
          isDirty={isDirty}
          onSelect={setActiveFileId}
          onClose={closeFile}
        />

        {/* Code Editor */}
        <CodeEditor
          file={activeFile}
          onChange={handleCodeChange}
          onSave={handleSave}
          onRunCode={() => handleRunCode()}
          isLoading={isLoading}
        />

        <ExecutionPanel
          activeFile={activeFile}
          executionResult={executionResult}
          executionError={executionError}
          isRunning={isExecuting}
          logs={workspaceState.executionLogs}
          onRun={handleRunCode}
          onClearLogs={handleClearExecutionLogs}
        />
      </main>

      {/* Right Panel - AI Assistant */}
      <aside 
        className={`codespace-panel codespace-panel-right ${assistantExpanded ? 'expanded' : 'collapsed'}`}
        style={{ width: assistantExpanded ? DEFAULT_LAYOUT.rightPanel : 48 }}
      >
        <div className="codespace-panel-header">
          <h3 className="codespace-panel-title">
            {assistantExpanded ? 'AI Assistant' : 'AI'}
          </h3>
          <button
            className="codespace-icon-btn"
            onClick={() => setAssistantExpanded(!assistantExpanded)}
            title={assistantExpanded ? 'Collapse' : 'Expand'}
          >
            {assistantExpanded ? '»' : '«'}
          </button>
        </div>
        
        {assistantExpanded && (
          <CodeAssistant
            activeFile={activeFile}
            isLoading={isLoading}
            onApplyCode={handleApplyAssistantCode}
            onInteraction={handleAssistantInteraction}
          />
        )}
      </aside>

      {/* Error Display */}
      {(error || executionError) && (
        <div className="codespace-error-toast">
          {error || executionError}
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}

      {/* Import Modal */}
      {showImport && (
        <ImportFromVSCode
          onImport={handleImport}
          onClose={() => setShowImport(false)}
        />
      )}
    </div>
  );
}

export default CodeSpaceLayout;
