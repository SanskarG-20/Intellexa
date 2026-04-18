/**
 * CodeSpaceLayout.jsx
 * Main 3-panel layout for the Code Space feature.
 * Left: File Explorer | Center: Code Editor | Right: AI Assistant
 */

import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useUser } from '@clerk/clerk-react';
import FileExplorer from './FileExplorer';
import CodeEditor from './CodeEditor';
import CodeAssistant from './CodeAssistant';
import ExecutionPanel from './ExecutionPanel';
import FileTabs from './FileTabs';
import ImportFromVSCode from './ImportFromVSCode';
import useVirtualFileSystem from '../../hooks/useVirtualFileSystem';
import useCodeExecution from '../../hooks/useCodeExecution';
import * as codeFileService from '../../services/codeFileService';
import { useCodeWorkspaceState } from '../../context/CodeWorkspaceContext';

const DEFAULT_LAYOUT = {
  leftPanel: 240,
  rightPanel: 320,
};

const COLLAB_POLL_INTERVAL_MS = 1200;
const DEFAULT_COLLAB_WORKSPACE_ID = 'intellexa-shared-workspace';
const MAX_ASSIST_PROJECT_CONTEXT_CHARS = 2800;
const MAX_ASSIST_USER_MEMORY_CHARS = 2200;
const MAX_ASSIST_RELATED_FILES = 4;
const MAX_ASSIST_RELATED_FILE_SNIPPET_CHARS = 1800;

function resolveSearchParam(name) {
  if (typeof window === 'undefined') {
    return '';
  }

  const value = new URLSearchParams(window.location.search).get(name);
  return String(value || '').trim();
}

function resolveWorkspaceIdFromUrl() {
  const normalized = resolveSearchParam('workspace');
  return normalized || DEFAULT_COLLAB_WORKSPACE_ID;
}

function resolveOwnerUserIdFromUrl() {
  return resolveSearchParam('owner') || null;
}

function buildFileKey(file) {
  const path = String(file?.path || '/').replace(/\\/g, '/').trim();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  const pathWithSlash = normalizedPath.endsWith('/') ? normalizedPath : `${normalizedPath}/`;
  return `${pathWithSlash}${String(file?.filename || '').trim()}`;
}

function clipText(value, maxChars) {
  const text = String(value || '');
  if (text.length <= maxChars) {
    return text;
  }

  const head = Math.floor(maxChars * 0.7);
  const tail = Math.max(0, maxChars - head);
  return `${text.slice(0, head)}\n...\n${text.slice(-tail)}`;
}

function CodeSpaceLayout() {
  const { user } = useUser();
  const userId = user?.id;
  const { state: workspaceState, actions: workspaceActions } = useCodeWorkspaceState();

  const collaborationWorkspaceId = useMemo(() => resolveWorkspaceIdFromUrl(), []);
  const collaborationOwnerOverride = useMemo(() => resolveOwnerUserIdFromUrl(), []);
  const collaborationActorName = useMemo(() => {
    const preferred = user?.username || user?.fullName || user?.firstName;
    return String(preferred || userId || 'Collaborator').trim();
  }, [user, userId]);
  const collaborationActorId = useMemo(() => {
    if (!collaborationWorkspaceId) {
      return null;
    }

    const fallbackSeed = String(userId || 'anonymous').trim() || 'anonymous';
    if (typeof window === 'undefined') {
      return `${fallbackSeed}-session`;
    }

    const storageKey = `intellexa-collab-actor:${collaborationWorkspaceId}:${fallbackSeed}`;
    const existing = localStorage.getItem(storageKey);
    if (existing && existing.trim()) {
      return existing.trim();
    }

    const generated = `${fallbackSeed}-${Math.random().toString(36).slice(2, 8)}`;
    localStorage.setItem(storageKey, generated);
    return generated;
  }, [collaborationWorkspaceId, userId]);

  const collaborationOwnerUserId = useMemo(() => {
    if (collaborationOwnerOverride) {
      return collaborationOwnerOverride;
    }

    const normalizedUserId = String(userId || '').trim();
    return normalizedUserId || null;
  }, [collaborationOwnerOverride, userId]);

  const collaboration = useMemo(() => {
    const normalizedUserId = String(userId || '').trim();
    const normalizedOwnerId = String(collaborationOwnerUserId || '').trim();

    return {
      enabled: Boolean(collaborationWorkspaceId && collaborationActorId),
      workspaceId: collaborationWorkspaceId,
      ownerUserId: normalizedOwnerId || null,
      actorId: collaborationActorId,
      actorName: collaborationActorName,
      canPersist: Boolean(normalizedUserId && normalizedOwnerId && normalizedUserId === normalizedOwnerId),
    };
  }, [collaborationActorId, collaborationActorName, collaborationOwnerUserId, collaborationWorkspaceId, userId]);

  const [showImport, setShowImport] = useState(false);
  const [assistantExpanded, setAssistantExpanded] = useState(true);
  const [sharedMessages, setSharedMessages] = useState([]);
  const [collaborationParticipants, setCollaborationParticipants] = useState([]);
  const [isCollaborationConnected, setIsCollaborationConnected] = useState(false);
  const [isRealtimeSocketConnected, setIsRealtimeSocketConnected] = useState(false);
  const [selectedCode, setSelectedCode] = useState('');

  const editorCollaboration = useMemo(() => ({
    ...collaboration,
    ready: isCollaborationConnected,
  }), [collaboration, isCollaborationConnected]);

  const collaborationSequenceRef = useRef(0);
  const knownSharedMessageIdsRef = useRef(new Set());
  const realtimeApiRef = useRef(null);

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
    remoteConflicts,
    createFile,
    openFile,
    closeFile,
    updateFileContent,
    saveFile,
    deleteFile,
    renameFile,
    importFiles,
    applyRemoteFileSync,
    applyRemoteFileDeletion,
    clearRemoteConflicts,
    setActiveFileId,
  } = useVirtualFileSystem(userId, collaboration);

  const participantNames = useMemo(() => {
    return (collaborationParticipants || [])
      .map((item) => String(item?.actor_name || item?.userName || item?.actor_id || item?.userId || '').trim())
      .filter(Boolean)
      .slice(0, 5);
  }, [collaborationParticipants]);

  const assistContext = useMemo(() => {
    const activeFileKey = activeFile ? buildFileKey(activeFile) : null;

    const relatedFiles = (openFiles || [])
      .filter((item) => item && item.id !== activeFileId && !item.is_folder)
      .slice(0, MAX_ASSIST_RELATED_FILES)
      .map((item) => ({
        path: buildFileKey(item),
        language: String(item.language || '').toLowerCase(),
        content: clipText(item.content || '', MAX_ASSIST_RELATED_FILE_SNIPPET_CHARS),
      }))
      .filter((item) => item.content.trim().length > 0);

    const fileSummary = (files || [])
      .filter((item) => !item?.is_folder)
      .slice(0, 24)
      .map((item) => `${buildFileKey(item)} [${String(item.language || 'plaintext').toLowerCase()}]`)
      .join('\n');

    const projectContext = clipText(
      [
        `Workspace: ${collaboration.workspaceId}`,
        `Mode: ${collaboration.canPersist ? 'owner' : 'guest'}`,
        `Active file: ${activeFileKey || 'none'}`,
        participantNames.length ? `Participants: ${participantNames.join(', ')}` : '',
        fileSummary ? `Project files:\n${fileSummary}` : '',
      ].filter(Boolean).join('\n\n'),
      MAX_ASSIST_PROJECT_CONTEXT_CHARS,
    );

    const recentChat = (workspaceState.chatHistory || [])
      .slice(0, 4)
      .map((item) => `User: ${String(item?.content || '').slice(0, 240)}`);
    const recentAi = (workspaceState.aiResponses || [])
      .slice(0, 4)
      .map((item) => `AI: ${String(item?.content || item?.summary || '').slice(0, 240)}`);
    const userMemory = clipText(
      [...recentChat, ...recentAi].filter(Boolean).join('\n'),
      MAX_ASSIST_USER_MEMORY_CHARS,
    );

    return {
      projectContext,
      userMemory,
      relatedFiles,
      selectedCode: clipText(selectedCode || '', 60000),
    };
  }, [
    activeFile,
    activeFileId,
    collaboration.canPersist,
    collaboration.workspaceId,
    files,
    openFiles,
    participantNames,
    selectedCode,
    workspaceState.aiResponses,
    workspaceState.chatHistory,
  ]);

  // Sync active file state for global workspace context
  useEffect(() => {
    workspaceActions.setActiveFile(activeFileId);
  }, [activeFileId, workspaceActions]);

  useEffect(() => {
    if (activeFileId) {
      workspaceActions.syncFileContent(activeFileId, activeFile?.content || '');
    }
  }, [activeFile?.content, activeFileId, workspaceActions]);

  useEffect(() => {
    setSharedMessages([]);
    setCollaborationParticipants([]);
    setIsCollaborationConnected(false);
    setIsRealtimeSocketConnected(false);
    collaborationSequenceRef.current = 0;
    knownSharedMessageIdsRef.current = new Set();
  }, [collaboration.workspaceId, collaboration.actorId]);

  useEffect(() => {
    if (!userId || !collaboration.enabled) {
      return;
    }

    let cancelled = false;
    let pollTimerId = null;

    const processRemoteEvents = (events) => {
      const list = Array.isArray(events) ? events : [];
      for (const event of list) {
        if (!event || typeof event.sequence !== 'number') {
          continue;
        }

        collaborationSequenceRef.current = Math.max(collaborationSequenceRef.current, event.sequence);

        if (event.actor_id === collaboration.actorId) {
          continue;
        }

        if (event.event_type === 'file_sync') {
          const syncResult = applyRemoteFileSync(event);
          if (syncResult?.reason === 'local_dirty_conflict') {
            workspaceActions.pushExecutionLog({
              timestamp: new Date().toISOString(),
              message: `Collab conflict: kept local unsaved edits while remote update arrived (${event.file_key || 'file'}).`,
            });
          }
          continue;
        }

        if (event.event_type === 'file_deleted') {
          const deletionResult = applyRemoteFileDeletion(event);
          if (deletionResult?.reason === 'local_dirty_conflict') {
            workspaceActions.pushExecutionLog({
              timestamp: new Date().toISOString(),
              message: `Collab conflict: ignored remote delete due to local unsaved edits (${event.file_key || 'file'}).`,
            });
          }
          continue;
        }

        if (
          event.event_type === 'user_context'
          || event.event_type === 'ai_context'
          || event.event_type === 'ai_suggestion'
        ) {
          const messageText = String(event.payload?.message || '').trim();
          const metadata = event.payload?.metadata || {};
          if (!messageText) {
            continue;
          }

          const messageId = `collab-${event.sequence}`;
          if (knownSharedMessageIdsRef.current.has(messageId)) {
            continue;
          }

          knownSharedMessageIdsRef.current.add(messageId);

          const remoteSuggestion = String(metadata?.suggestion || '').trim();
          const remoteDiff = String(metadata?.diff || '').trim();
          const remoteExplanation = String(metadata?.explanation || messageText).trim();
          setSharedMessages((prev) => [
            ...prev,
            {
              id: messageId,
              role: event.event_type === 'user_context' ? 'user' : 'assistant',
              action: metadata?.action || 'explain',
              content: remoteExplanation,
              suggestion: remoteSuggestion,
              improvedCode: remoteSuggestion,
              diff: remoteDiff,
              diffHunks: Array.isArray(metadata?.diff_hunks) ? metadata.diff_hunks : [],
              requestId: metadata?.request_id || null,
              baseCodeHash: metadata?.base_code_hash || '',
              baseCodeLength: Number(metadata?.base_code_length || 0),
              securitySeverity: metadata?.security_severity || 'none',
              suggestions: [],
              warnings: [],
              isRemote: true,
              senderName: event.actor_name || 'Collaborator',
              contextUsed: false,
              contextSources: [],
            },
          ].slice(-160));
        }
      }
    };

    const syncCollaborationState = async (joinFirst = false) => {
      try {
        if (joinFirst) {
          const joined = await codeFileService.joinCollaborationWorkspace({
            workspaceId: collaboration.workspaceId,
            actorId: collaboration.actorId,
            actorName: collaboration.actorName,
            actorRole: 'user',
          });

          if (!cancelled) {
            setCollaborationParticipants(joined?.participants || []);
            collaborationSequenceRef.current = Math.max(
              collaborationSequenceRef.current,
              Number(joined?.sequence || 0),
            );
          }
        }

        const state = await codeFileService.getCollaborationState({
          workspaceId: collaboration.workspaceId,
          sinceSequence: collaborationSequenceRef.current,
          limit: 80,
          actorId: collaboration.actorId,
          actorName: collaboration.actorName,
        });

        if (cancelled) {
          return;
        }

        setIsCollaborationConnected(true);
        setCollaborationParticipants(state?.participants || []);
        collaborationSequenceRef.current = Math.max(
          collaborationSequenceRef.current,
          Number(state?.sequence || 0),
        );
        processRemoteEvents(state?.events || []);
      } catch (err) {
        if (!cancelled) {
          setIsCollaborationConnected(false);
        }
      }
    };

    void syncCollaborationState(true);
    pollTimerId = setInterval(() => {
      void syncCollaborationState(false);
    }, COLLAB_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      if (pollTimerId) {
        clearInterval(pollTimerId);
      }
    };
  }, [
    applyRemoteFileDeletion,
    applyRemoteFileSync,
    collaboration.actorId,
    collaboration.actorName,
    collaboration.enabled,
    collaboration.workspaceId,
    userId,
    workspaceActions,
  ]);

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
  const handleCodeChange = useCallback((value, meta = {}) => {
    if (activeFileId) {
      updateFileContent(activeFileId, value || '', {
        source: meta.source || 'local',
        persist: meta.persist !== false,
      });
    }
  }, [activeFileId, updateFileContent]);

  const handleRealtimeReady = useCallback((api) => {
    realtimeApiRef.current = api || null;
  }, []);

  // Apply AI-generated code into active file and persist it.
  const handleApplyAssistantCode = useCallback(async (payload) => {
    if (!activeFileId) {
      return;
    }

    const suggestion = String(payload?.suggestion || '').trim();
    if (!suggestion) {
      return;
    }

    const realtimeApi = realtimeApiRef.current;
    const canApplyWithRealtime = Boolean(
      collaboration.enabled
      && realtimeApi
      && typeof realtimeApi.applySuggestionDiff === 'function'
      && (realtimeApi.connectionState === 'connected' || realtimeApi.connectionState === 'fallback')
    );

    if (canApplyWithRealtime) {
      const applyResult = realtimeApi.applySuggestionDiff({
        roomId: realtimeApi.roomId,
        suggestion,
        baseCode: String(payload?.baseCode || activeFile?.content || ''),
      });

      if (applyResult?.applied) {
        workspaceActions.pushExecutionLog({
          timestamp: new Date().toISOString(),
          message: applyResult.partial
            ? 'Applied AI suggestion with partial fuzzy merge (document changed while suggestion was pending).'
            : 'Applied AI suggestion using Yjs diff transaction.',
        });

        if (collaboration.canPersist) {
          await saveFile(activeFileId);
        }
      } else {
        workspaceActions.pushExecutionLog({
          timestamp: new Date().toISOString(),
          message: `AI apply warning: ${String(applyResult?.reason || 'could not apply suggestion diff')}.`,
        });

        updateFileContent(activeFileId, suggestion, {
          source: 'local',
          persist: collaboration.canPersist,
        });

        if (collaboration.canPersist) {
          await saveFile(activeFileId);
        }
      }
    } else {
      updateFileContent(activeFileId, suggestion, {
        source: 'local',
        persist: collaboration.canPersist,
      });

      if (collaboration.canPersist) {
        await saveFile(activeFileId);
      }
    }

    workspaceActions.pushAiResponse({
      type: 'apply_diff',
      fileId: activeFileId,
      timestamp: new Date().toISOString(),
      requestId: String(payload?.requestId || ''),
      preview: suggestion.slice(0, 120),
    });
  }, [
    activeFile?.content,
    activeFileId,
    collaboration.canPersist,
    collaboration.enabled,
    saveFile,
    updateFileContent,
    workspaceActions,
  ]);

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

    if (collaboration.enabled) {
      const content = String(event.payload.content || '').trim();
      if (content) {
        const suggestion = String(event.payload.suggestion || event.payload.improvedCode || '').trim();
        const diffText = String(event.payload.diff || '').trim();
        const hasShareableSuggestion = event.type === 'assistant' && Boolean(suggestion);
        const eventType = hasShareableSuggestion
          ? 'ai_suggestion'
          : event.type === 'assistant'
            ? 'ai_context'
            : 'user_context';

        const metadata = {
          action: event.payload.action,
          intentMode: Boolean(event.payload.intentMode),
          taskMode: Boolean(event.payload.taskMode),
          whyBrokeMode: Boolean(event.payload.whyBrokeMode),
        };

        if (hasShareableSuggestion) {
          Object.assign(metadata, {
            suggestion: suggestion.slice(0, 32000),
            diff: diffText.slice(0, 48000),
            explanation: content.slice(0, 3000),
            request_id: String(event.payload.requestId || '').slice(0, 96),
            base_code_hash: String(event.payload.baseCodeHash || '').slice(0, 96),
            base_code_length: Number(event.payload.baseCodeLength || 0),
            security_severity: String(event.payload.securitySeverity || '').slice(0, 32),
            diff_hunks: Array.isArray(event.payload.diffHunks)
              ? event.payload.diffHunks.slice(0, 120)
              : [],
          });
        }

        void codeFileService.publishCollaborationContext({
          workspaceId: collaboration.workspaceId,
          actorId: collaboration.actorId,
          actorName: collaboration.actorName,
          actorRole: event.type === 'assistant' ? 'ai' : 'user',
          eventType,
          message: content,
          fileId: activeFileId,
          fileKey: activeFile ? buildFileKey(activeFile) : null,
          metadata,
        }).catch(() => {});
      }
    }
  }, [activeFile, activeFileId, collaboration, workspaceActions]);

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
    if (collaboration.enabled && !collaboration.canPersist) {
      workspaceActions.pushExecutionLog({
        timestamp: new Date().toISOString(),
        message: 'Collab note: guest participants do not persist to backend. Changes stay in realtime sync.',
      });
      return;
    }

    if (activeFileId && isDirty[activeFileId]) {
      await saveFile(activeFileId);
    }
  }, [activeFileId, collaboration.canPersist, collaboration.enabled, isDirty, saveFile, workspaceActions]);

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
        <div className="codespace-collab-status">
          <span className={`codespace-collab-indicator ${isRealtimeSocketConnected || isCollaborationConnected ? 'online' : 'offline'}`}>
            {isRealtimeSocketConnected ? 'Realtime' : isCollaborationConnected ? 'Sync' : 'Connecting'}
          </span>
          <span className="codespace-collab-text">Workspace: {collaboration.workspaceId}</span>
          <span className="codespace-collab-text">Mode: {collaboration.canPersist ? 'Owner' : 'Guest'}</span>
          <span className="codespace-collab-text">
            Participants: {collaborationParticipants.length}
          </span>
        </div>

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
          collaboration={editorCollaboration}
          onCollaborationConnectionChange={setIsRealtimeSocketConnected}
          onCollaborationParticipantsChange={setCollaborationParticipants}
          onRealtimeReady={handleRealtimeReady}
          onSelectionChange={setSelectedCode}
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
            sharedMessages={sharedMessages}
            assistContext={assistContext}
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

      {remoteConflicts.length > 0 && (
        <div className="codespace-error-toast">
          {`Collaboration conflict: ${remoteConflicts.length} remote update(s) were held because you have unsaved local edits.`}
          <button onClick={clearRemoteConflicts}>Dismiss</button>
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
