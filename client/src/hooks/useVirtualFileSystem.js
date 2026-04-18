/**
 * useVirtualFileSystem.js
 * Resilient workspace file state with local persistence + backend sync.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import * as codeFileService from '../services/codeFileService';

const LOCAL_STORAGE_PREFIX = 'intellexa_code_files';
const LOCAL_HISTORY_PREFIX = 'intellexa_code_history';
const DEBOUNCE_MS = 500;
const MAX_HISTORY_ENTRIES = 20;
const REMOTE_STALE_TOLERANCE_MS = 300;

const DEFAULT_PROJECT_BLUEPRINT = [
  { filename: 'project', path: '/', isFolder: true, content: '', language: 'plaintext' },
  { filename: 'src', path: '/project/', isFolder: true, content: '', language: 'plaintext' },
  { filename: 'utils', path: '/project/src/', isFolder: true, content: '', language: 'plaintext' },
  {
    filename: 'index.js',
    path: '/project/src/',
    isFolder: false,
    language: 'javascript',
    content: [
      '// Intellexa AI Workspace starter file',
      'export function bootstrapWorkspace() {',
      "  console.log('Intellexa Code Workspace ready.');",
      '}',
      '',
      'bootstrapWorkspace();',
      '',
    ].join('\n'),
  },
];

function normalizePath(pathValue) {
  const raw = String(pathValue || '/').replace(/\\/g, '/').trim();
  const withLeadingSlash = raw.startsWith('/') ? raw : `/${raw}`;
  return withLeadingSlash.endsWith('/') ? withLeadingSlash : `${withLeadingSlash}/`;
}

function buildFileKey(pathValue, filenameValue) {
  return `${normalizePath(pathValue)}${String(filenameValue || '').trim()}`;
}

function buildLocalCollabId(fileKey) {
  const safe = String(fileKey || 'remote-file')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  return `collab-${safe || 'file'}`.slice(0, 80);
}

function isFolderEntry(file) {
  return Boolean(file?.is_folder || file?.isFolder);
}

function getStorageKey(userId) {
  return `${LOCAL_STORAGE_PREFIX}:${userId || 'anonymous'}`;
}

function getHistoryKey(userId) {
  return `${LOCAL_HISTORY_PREFIX}:${userId || 'anonymous'}`;
}

function getLocalFiles(userId) {
  try {
    const stored = localStorage.getItem(getStorageKey(userId));
    return stored ? JSON.parse(stored) : {};
  } catch {
    return {};
  }
}

function saveLocalFile(userId, file) {
  try {
    const files = getLocalFiles(userId);
    files[file.id] = file;
    localStorage.setItem(getStorageKey(userId), JSON.stringify(files));
  } catch (err) {
    console.error('[VirtualFS] Failed to save local file:', err);
  }
}

function removeLocalFile(userId, fileId) {
  try {
    const files = getLocalFiles(userId);
    delete files[fileId];
    localStorage.setItem(getStorageKey(userId), JSON.stringify(files));
  } catch (err) {
    console.error('[VirtualFS] Failed to remove local file:', err);
  }
}

function appendFileHistory(userId, fileId, content) {
  try {
    const key = getHistoryKey(userId);
    const payload = JSON.parse(localStorage.getItem(key) || '{}');
    const entries = Array.isArray(payload[fileId]) ? payload[fileId] : [];
    entries.unshift({ timestamp: new Date().toISOString(), content: String(content || '') });
    payload[fileId] = entries.slice(0, MAX_HISTORY_ENTRIES);
    localStorage.setItem(key, JSON.stringify(payload));
  } catch (err) {
    console.error('[VirtualFS] Failed to save file history:', err);
  }
}

function mergeRemoteAndLocal(remoteFiles, localFilesMap) {
  const merged = [...remoteFiles];
  for (const localFile of Object.values(localFilesMap)) {
    const existingIndex = merged.findIndex((item) => item.id === localFile.id);
    if (existingIndex >= 0) {
      merged[existingIndex] = { ...merged[existingIndex], ...localFile };
    } else {
      merged.push(localFile);
    }
  }
  return merged;
}

export function useVirtualFileSystem(userId, collaboration = null) {
  const [files, setFiles] = useState([]);
  const [openFiles, setOpenFiles] = useState([]);
  const [activeFileId, setActiveFileId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isDirty, setIsDirty] = useState({});
  const [remoteConflicts, setRemoteConflicts] = useState([]);

  const saveTimeoutRef = useRef(null);
  const pendingChangesRef = useRef({});
  const filesRef = useRef([]);
  const isDirtyRef = useRef({});
  const remoteAppliedAtRef = useRef({});

  useEffect(() => {
    filesRef.current = files;
  }, [files]);

  useEffect(() => {
    isDirtyRef.current = isDirty;
  }, [isDirty]);

  const buildCollaborationOptions = useCallback(() => {
    if (!collaboration || collaboration.enabled === false || !collaboration.workspaceId) {
      return {};
    }

    return {
      collaboration: {
        workspaceId: collaboration.workspaceId,
        actorId: collaboration.actorId,
        actorName: collaboration.actorName,
      },
    };
  }, [collaboration]);

  const activeFile = openFiles.find((f) => f.id === activeFileId) || null;

  const bootstrapDefaultProject = useCallback(async () => {
    const createdFiles = [];

    for (const item of DEFAULT_PROJECT_BLUEPRINT) {
      try {
        const created = await codeFileService.createCodeFile({
          filename: item.filename,
          path: item.path,
          content: item.content,
          language: item.language,
          isFolder: item.isFolder,
        }, buildCollaborationOptions());
        createdFiles.push(created);
        saveLocalFile(userId, created);
      } catch {
        const localFile = {
          id: `local-${item.filename}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          filename: item.filename,
          path: item.path,
          content: item.content,
          language: item.language,
          is_folder: item.isFolder,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        createdFiles.push(localFile);
        saveLocalFile(userId, localFile);
      }
    }

    return createdFiles;
  }, [buildCollaborationOptions, userId]);

  const openFile = useCallback(
    async (fileId) => {
      const existing = openFiles.find((f) => f.id === fileId);
      if (existing) {
        setActiveFileId(fileId);
        return existing;
      }

      setIsLoading(true);
      setError(null);

      try {
        const file = await codeFileService.getCodeFile(fileId);
        setOpenFiles((prev) => [...prev, file]);
        setActiveFileId(fileId);
        return file;
      } catch (err) {
        const localFiles = getLocalFiles(userId);
        const localFile = localFiles[fileId];
        if (localFile) {
          setOpenFiles((prev) => [...prev, localFile]);
          setActiveFileId(fileId);
          return localFile;
        }
        setError(err.message || 'Failed to open file');
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [openFiles, userId],
  );

  const loadFiles = useCallback(async () => {
    if (!userId) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const response = await codeFileService.listCodeFiles();
      const remoteFiles = response.files || [];
      const localFilesMap = getLocalFiles(userId);

      let mergedFiles = mergeRemoteAndLocal(remoteFiles, localFilesMap);

      if (mergedFiles.length === 0) {
        mergedFiles = await bootstrapDefaultProject();
      }

      setFiles(mergedFiles);

      if (!activeFileId) {
        const firstEditable = mergedFiles.find((file) => !isFolderEntry(file));
        if (firstEditable) {
          setActiveFileId(firstEditable.id);
          if (typeof firstEditable.content === 'string') {
            setOpenFiles([firstEditable]);
          } else {
            try {
              const detail = await codeFileService.getCodeFile(firstEditable.id);
              setOpenFiles([detail]);
              saveLocalFile(userId, detail);
            } catch {
              const localFiles = getLocalFiles(userId);
              if (localFiles[firstEditable.id]) {
                setOpenFiles([localFiles[firstEditable.id]]);
              }
            }
          }
        }
      }
    } catch (err) {
      console.error('[VirtualFS] Failed to load files:', err);
      setError(err.message || 'Failed to load files');

      const localFilesMap = getLocalFiles(userId);
      const localFiles = Object.values(localFilesMap);
      if (localFiles.length > 0) {
        setFiles(localFiles);
      } else {
        const seeded = await bootstrapDefaultProject();
        setFiles(seeded);
      }
    } finally {
      setIsLoading(false);
    }
  }, [activeFileId, bootstrapDefaultProject, userId]);

  useEffect(() => {
    if (userId) {
      void loadFiles();
    }
  }, [userId, loadFiles]);

  const createFile = useCallback(
    async (filename, path = '/', isFolder = false) => {
      setIsLoading(true);
      setError(null);

      try {
        const language = codeFileService.detectLanguage(filename);
        const newFile = await codeFileService.createCodeFile({
          filename,
          path,
          content: '',
          language,
          isFolder,
        }, buildCollaborationOptions());

        setFiles((prev) => [...prev, newFile]);
        saveLocalFile(userId, newFile);
        return newFile;
      } catch (err) {
        console.error('[VirtualFS] Failed to create file:', err);
        setError(err.message || 'Failed to create file');

        const localFile = {
          id: `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          filename,
          path,
          content: '',
          language: codeFileService.detectLanguage(filename),
          is_folder: isFolder,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };

        setFiles((prev) => [...prev, localFile]);
        saveLocalFile(userId, localFile);
        return localFile;
      } finally {
        setIsLoading(false);
      }
    },
    [buildCollaborationOptions, userId],
  );

  const closeFile = useCallback(
    (fileId) => {
      setOpenFiles((prev) => prev.filter((f) => f.id !== fileId));
      setIsDirty((prev) => {
        const next = { ...prev };
        delete next[fileId];
        return next;
      });

      if (activeFileId === fileId) {
        const remaining = openFiles.filter((f) => f.id !== fileId);
        setActiveFileId(remaining.length > 0 ? remaining[0].id : null);
      }
    },
    [activeFileId, openFiles],
  );

  const savePendingChanges = useCallback(async () => {
    const pending = { ...pendingChangesRef.current };
    pendingChangesRef.current = {};

    for (const [fileId, content] of Object.entries(pending)) {
      try {
        await codeFileService.updateCodeFile(fileId, { content }, buildCollaborationOptions());
        appendFileHistory(userId, fileId, content);
        setIsDirty((prev) => {
          const next = { ...prev };
          delete next[fileId];
          return next;
        });
      } catch (err) {
        console.error(`[VirtualFS] Failed to save ${fileId}:`, err);
      }
    }
  }, [buildCollaborationOptions, userId]);

  const updateFileContent = useCallback(
    (fileId, content, options = {}) => {
      const source = String(options.source || 'local').trim().toLowerCase();
      const persist = options.persist !== false;
      const isRemoteSource = source.startsWith('remote');

      if (!isRemoteSource && persist) {
        setIsDirty((prev) => ({ ...prev, [fileId]: true }));
      } else if (!persist) {
        setIsDirty((prev) => {
          if (!Object.prototype.hasOwnProperty.call(prev, fileId)) {
            return prev;
          }

          const next = { ...prev };
          delete next[fileId];
          return next;
        });
      }

      setOpenFiles((prev) =>
        prev.map((file) =>
          file.id === fileId ? { ...file, content, updated_at: new Date().toISOString() } : file,
        ),
      );

      setFiles((prev) =>
        prev.map((file) =>
          file.id === fileId ? { ...file, content, updated_at: new Date().toISOString() } : file,
        ),
      );

      const localFiles = getLocalFiles(userId);
      const current = localFiles[fileId] || {};
      saveLocalFile(userId, { ...current, id: fileId, content, updated_at: new Date().toISOString() });

      if (!persist) {
        return;
      }

      pendingChangesRef.current[fileId] = content;
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        void savePendingChanges();
      }, DEBOUNCE_MS);
    },
    [savePendingChanges, userId],
  );

  const saveFile = useCallback(
    async (fileId) => {
      const file = openFiles.find((item) => item.id === fileId);
      if (!file) {
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        await codeFileService.updateCodeFile(fileId, {
          content: file.content,
          filename: file.filename,
          language: file.language,
        }, buildCollaborationOptions());

        appendFileHistory(userId, fileId, file.content || '');
        setIsDirty((prev) => {
          const next = { ...prev };
          delete next[fileId];
          return next;
        });
        saveLocalFile(userId, file);
      } catch (err) {
        console.error('[VirtualFS] Failed to save file:', err);
        setError(err.message || 'Failed to save file');
      } finally {
        setIsLoading(false);
      }
    },
    [buildCollaborationOptions, openFiles, userId],
  );

  const deleteFile = useCallback(
    async (fileId) => {
      setIsLoading(true);
      setError(null);

      try {
        await codeFileService.deleteCodeFile(fileId, buildCollaborationOptions());
        setFiles((prev) => prev.filter((f) => f.id !== fileId));
        closeFile(fileId);
        removeLocalFile(userId, fileId);
      } catch (err) {
        console.error('[VirtualFS] Failed to delete file:', err);
        setError(err.message || 'Failed to delete file');
      } finally {
        setIsLoading(false);
      }
    },
    [buildCollaborationOptions, closeFile, userId],
  );

  const renameFile = useCallback(
    async (fileId, newFilename) => {
      setIsLoading(true);
      setError(null);

      try {
        const language = codeFileService.detectLanguage(newFilename);
        await codeFileService.updateCodeFile(fileId, {
          filename: newFilename,
          language,
        }, buildCollaborationOptions());

        setFiles((prev) =>
          prev.map((file) =>
            file.id === fileId ? { ...file, filename: newFilename, language } : file,
          ),
        );

        setOpenFiles((prev) =>
          prev.map((file) =>
            file.id === fileId ? { ...file, filename: newFilename, language } : file,
          ),
        );

        const localFiles = getLocalFiles(userId);
        if (localFiles[fileId]) {
          localFiles[fileId].filename = newFilename;
          localFiles[fileId].language = language;
          localStorage.setItem(getStorageKey(userId), JSON.stringify(localFiles));
        }
      } catch (err) {
        console.error('[VirtualFS] Failed to rename file:', err);
        setError(err.message || 'Failed to rename file');
      } finally {
        setIsLoading(false);
      }
    },
    [buildCollaborationOptions, userId],
  );

  const importFiles = useCallback(
    async (filesToImport) => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await codeFileService.importCodeFiles(filesToImport, buildCollaborationOptions());
        if (response.files?.length) {
          setFiles((prev) => [...prev, ...response.files]);
          for (const file of response.files) {
            saveLocalFile(userId, file);
          }
        }
        return response;
      } catch (err) {
        console.error('[VirtualFS] Failed to import files:', err);
        setError(err.message || 'Failed to import files');
        return { success: false, errors: [err.message || 'Import failed'] };
      } finally {
        setIsLoading(false);
      }
    },
    [buildCollaborationOptions, userId],
  );

  const applyRemoteFileSync = useCallback((event) => {
    const payload = event?.payload || {};
    const remotePath = normalizePath(payload.path || '/');
    const remoteFilename = String(payload.filename || '').trim();
    const remoteFileKey = String(event?.file_key || buildFileKey(remotePath, remoteFilename)).trim();
    const remoteUpdatedAt = String(payload.updated_at || event?.timestamp || new Date().toISOString());
    const remoteUpdatedMs = Date.parse(remoteUpdatedAt);

    if (!remoteFileKey || !remoteFilename) {
      return { applied: false, reason: 'invalid_event' };
    }

    const allFiles = filesRef.current || [];
    let target = allFiles.find((item) => item.id === event?.file_id);
    if (!target) {
      target = allFiles.find((item) => buildFileKey(item.path, item.filename) === remoteFileKey);
    }

    const targetId = target?.id || buildLocalCollabId(remoteFileKey);
    const localUpdatedMs = target?.updated_at ? Date.parse(target.updated_at) : 0;
    const staleByLocal = (
      Number.isFinite(remoteUpdatedMs)
      && Number.isFinite(localUpdatedMs)
      && (remoteUpdatedMs + REMOTE_STALE_TOLERANCE_MS) < localUpdatedMs
    );
    const staleByApplied = (
      Number.isFinite(remoteUpdatedMs)
      && Number.isFinite(remoteAppliedAtRef.current[remoteFileKey])
      && (remoteUpdatedMs + REMOTE_STALE_TOLERANCE_MS) < remoteAppliedAtRef.current[remoteFileKey]
    );

    if (staleByLocal || staleByApplied) {
      return { applied: false, reason: 'stale_event', fileId: targetId };
    }

    if (isDirtyRef.current[targetId]) {
      const conflict = {
        fileId: targetId,
        fileKey: remoteFileKey,
        actorName: event?.actor_name || 'Collaborator',
        timestamp: new Date().toISOString(),
        reason: 'local_unsaved_changes',
      };

      setRemoteConflicts((prev) => [conflict, ...prev].slice(0, 25));
      return { applied: false, reason: 'local_dirty_conflict', fileId: targetId };
    }

    const nextFile = {
      ...(target || {}),
      id: targetId,
      filename: remoteFilename,
      path: remotePath,
      content: String(payload.content || ''),
      language: String(payload.language || target?.language || 'plaintext'),
      is_folder: false,
      updated_at: remoteUpdatedAt,
      created_at: target?.created_at || remoteUpdatedAt,
    };

    setFiles((prev) => {
      const exists = prev.some((item) => item.id === targetId);
      if (exists) {
        return prev.map((item) => (item.id === targetId ? nextFile : item));
      }
      return [...prev, nextFile];
    });

    setOpenFiles((prev) => {
      const exists = prev.some((item) => item.id === targetId);
      if (exists) {
        return prev.map((item) => (item.id === targetId ? nextFile : item));
      }
      return prev;
    });

    saveLocalFile(userId, nextFile);
    remoteAppliedAtRef.current[remoteFileKey] = Number.isFinite(remoteUpdatedMs)
      ? remoteUpdatedMs
      : Date.now();

    return { applied: true, fileId: targetId, fileKey: remoteFileKey };
  }, [userId]);

  const applyRemoteFileDeletion = useCallback((event) => {
    const payload = event?.payload || {};
    const remotePath = normalizePath(payload.path || '/');
    const remoteFilename = String(payload.filename || '').trim();
    const remoteFileKey = String(event?.file_key || buildFileKey(remotePath, remoteFilename)).trim();

    if (!remoteFileKey) {
      return { applied: false, reason: 'invalid_event' };
    }

    const allFiles = filesRef.current || [];
    let target = allFiles.find((item) => item.id === event?.file_id);
    if (!target) {
      target = allFiles.find((item) => buildFileKey(item.path, item.filename) === remoteFileKey);
    }

    if (!target) {
      return { applied: false, reason: 'not_found' };
    }

    if (isDirtyRef.current[target.id]) {
      setRemoteConflicts((prev) => [
        {
          fileId: target.id,
          fileKey: remoteFileKey,
          actorName: event?.actor_name || 'Collaborator',
          timestamp: new Date().toISOString(),
          reason: 'remote_delete_conflict',
        },
        ...prev,
      ].slice(0, 25));
      return { applied: false, reason: 'local_dirty_conflict', fileId: target.id };
    }

    setFiles((prev) => prev.filter((item) => item.id !== target.id));
    setOpenFiles((prev) => prev.filter((item) => item.id !== target.id));
    removeLocalFile(userId, target.id);

    if (activeFileId === target.id) {
      setActiveFileId(null);
    }

    return { applied: true, fileId: target.id, fileKey: remoteFileKey };
  }, [activeFileId, userId]);

  const clearRemoteConflicts = useCallback(() => {
    setRemoteConflicts([]);
  }, []);

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        void savePendingChanges();
      }
    };
  }, [savePendingChanges]);

  return {
    files,
    openFiles,
    activeFile,
    activeFileId,
    isLoading,
    error,
    isDirty,
    remoteConflicts,
    loadFiles,
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
  };
}

export default useVirtualFileSystem;
