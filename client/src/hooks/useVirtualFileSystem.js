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

export function useVirtualFileSystem(userId) {
  const [files, setFiles] = useState([]);
  const [openFiles, setOpenFiles] = useState([]);
  const [activeFileId, setActiveFileId] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isDirty, setIsDirty] = useState({});

  const saveTimeoutRef = useRef(null);
  const pendingChangesRef = useRef({});

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
        });
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
  }, [userId]);

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
        });

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
    [userId],
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
        await codeFileService.updateCodeFile(fileId, { content });
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
  }, [userId]);

  const updateFileContent = useCallback(
    (fileId, content) => {
      setIsDirty((prev) => ({ ...prev, [fileId]: true }));

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
        });

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
    [openFiles, userId],
  );

  const deleteFile = useCallback(
    async (fileId) => {
      setIsLoading(true);
      setError(null);

      try {
        await codeFileService.deleteCodeFile(fileId);
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
    [closeFile, userId],
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
        });

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
    [userId],
  );

  const importFiles = useCallback(
    async (filesToImport) => {
      setIsLoading(true);
      setError(null);

      try {
        const response = await codeFileService.importCodeFiles(filesToImport);
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
    [userId],
  );

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
    loadFiles,
    createFile,
    openFile,
    closeFile,
    updateFileContent,
    saveFile,
    deleteFile,
    renameFile,
    importFiles,
    setActiveFileId,
  };
}

export default useVirtualFileSystem;
