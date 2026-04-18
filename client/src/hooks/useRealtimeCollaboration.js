/**
 * useRealtimeCollaboration.js
 * Socket.IO + Yjs + Monaco CRDT synchronization for collaborative code editing.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { io } from 'socket.io-client';
import * as Y from 'yjs';
import * as awarenessProtocol from 'y-protocols/awareness';
import { MonacoBinding } from 'y-monaco';

const DEFAULT_SOCKET_PATH = '/realtime/socket.io';
const OUTGOING_FLUSH_MS = 45;
const SNAPSHOT_INTERVAL_MS = 10000;
const MAX_PENDING_UPDATES = 800;
const REMOTE_UPDATE_ORIGIN = 'socket-remote';
const SNAPSHOT_UPDATE_ORIGIN = 'socket-snapshot';
const REMOTE_AWARENESS_ORIGIN = 'socket-awareness-remote';

const USER_COLORS = [
  '#4F8EF7',
  '#F76E6E',
  '#34C77B',
  '#F7B955',
  '#B46EF7',
  '#52C8D9',
  '#E985DA',
  '#7BB3FF',
];

function normalizePath(pathValue) {
  const raw = String(pathValue || '/').replace(/\\/g, '/').trim();
  const withLeadingSlash = raw.startsWith('/') ? raw : `/${raw}`;
  return withLeadingSlash.endsWith('/') ? withLeadingSlash : `${withLeadingSlash}/`;
}

function buildRoomId(workspaceId, fileId) {
  return `${String(workspaceId || 'workspace').trim()}:${String(fileId || '').trim()}`;
}

function pickUserColor(seed) {
  const source = String(seed || 'anonymous');
  let hash = 0;
  for (let i = 0; i < source.length; i += 1) {
    hash = ((hash << 5) - hash) + source.charCodeAt(i);
    hash |= 0;
  }
  const index = Math.abs(hash) % USER_COLORS.length;
  return USER_COLORS[index];
}

function resolveCollabServerUrl() {
  const explicit = String(import.meta.env.VITE_COLLAB_SERVER_URL || '').trim().replace(/\/+$/, '');
  if (explicit) {
    return explicit;
  }

  const apiBase = String(import.meta.env.VITE_API_BASE_URL || '').trim().replace(/\/+$/, '');
  if (apiBase) {
    if (apiBase.endsWith('/api')) {
      return apiBase.slice(0, -4);
    }
    return apiBase;
  }

  if (typeof window !== 'undefined') {
    const host = String(window.location.hostname || '').toLowerCase();
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://localhost:8000';
    }
    return window.location.origin;
  }

  return 'http://localhost:8000';
}

function resolveSocketPath() {
  const raw = String(import.meta.env.VITE_COLLAB_SOCKET_PATH || DEFAULT_SOCKET_PATH).trim();
  if (!raw) {
    return DEFAULT_SOCKET_PATH;
  }
  return raw.startsWith('/') ? raw : `/${raw}`;
}

function uint8ToBase64(uint8Array) {
  if (!(uint8Array instanceof Uint8Array)) {
    return '';
  }

  let binary = '';
  const chunkSize = 0x8000;
  for (let i = 0; i < uint8Array.length; i += chunkSize) {
    const chunk = uint8Array.subarray(i, i + chunkSize);
    binary += String.fromCharCode(...chunk);
  }

  return btoa(binary);
}

function base64ToUint8(base64Value) {
  const safe = String(base64Value || '').trim();
  if (!safe) {
    return null;
  }

  try {
    const binary = atob(safe);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  } catch {
    return null;
  }
}

function createDocEntry({ roomId, fileId, filePath, initialContent }) {
  const ydoc = new Y.Doc();
  const ytext = ydoc.getText('content');
  if (initialContent) {
    ytext.insert(0, String(initialContent));
  }

  const awareness = new awarenessProtocol.Awareness(ydoc);

  return {
    roomId,
    fileId,
    filePath,
    ydoc,
    ytext,
    awareness,
    pendingUpdates: [],
    flushTimer: null,
    lastSnapshotSentAt: 0,
    joined: false,
    detachRuntime: null,
  };
}

function applyRemoteDocument(roomEntry, payload, origin = REMOTE_UPDATE_ORIGIN) {
  if (!roomEntry || !payload) {
    return;
  }

  const snapshot = String(payload.snapshot || '').trim();
  if (snapshot) {
    const snapshotBytes = base64ToUint8(snapshot);
    if (snapshotBytes) {
      Y.applyUpdate(roomEntry.ydoc, snapshotBytes, SNAPSHOT_UPDATE_ORIGIN);
    }
  }

  const updates = Array.isArray(payload.updates) ? payload.updates : [];
  for (const item of updates) {
    const bytes = base64ToUint8(item);
    if (bytes) {
      Y.applyUpdate(roomEntry.ydoc, bytes, origin);
    }
  }
}

function applyAwarenessFromBase64(roomEntry, encodedUpdate) {
  if (!roomEntry) {
    return;
  }

  const bytes = base64ToUint8(encodedUpdate);
  if (!bytes) {
    return;
  }

  awarenessProtocol.applyAwarenessUpdate(roomEntry.awareness, bytes, REMOTE_AWARENESS_ORIGIN);
}

export function useRealtimeCollaboration({
  enabled,
  workspaceId,
  ownerUserId,
  persistLocalChanges = true,
  file,
  editor,
  monaco,
  actorId,
  actorName,
  onContentChange,
  onConnectionChange,
  onParticipantsChange,
}) {
  const [connectionState, setConnectionState] = useState('idle');
  const [participants, setParticipants] = useState([]);

  const socketRef = useRef(null);
  const docsRef = useRef(new Map());
  const activeRoomIdRef = useRef(null);
  const activeBindingRef = useRef(null);

  const socketBaseUrl = useMemo(() => resolveCollabServerUrl(), []);
  const socketPath = useMemo(() => resolveSocketPath(), []);
  const userColor = useMemo(() => pickUserColor(actorId || actorName || 'anonymous'), [actorId, actorName]);

  const roomMeta = useMemo(() => {
    if (!enabled || !file?.id) {
      return null;
    }

    const filePath = `${normalizePath(file.path)}${String(file.filename || '').trim()}`;
    return {
      roomId: buildRoomId(workspaceId, file.id),
      fileId: file.id,
      filePath,
      fileName: String(file.filename || '').trim(),
      language: String(file.language || 'plaintext'),
    };
  }, [enabled, file?.id, file?.filename, file?.language, file?.path, workspaceId]);

  const updateConnection = useCallback((state) => {
    setConnectionState(state);
    onConnectionChange?.(state === 'connected');
  }, [onConnectionChange]);

  const updateParticipants = useCallback((list) => {
    const values = Array.isArray(list) ? list : [];
    setParticipants(values);
    onParticipantsChange?.(values);
  }, [onParticipantsChange]);

  const getOrCreateDocEntry = useCallback(() => {
    if (!roomMeta) {
      return null;
    }

    const existing = docsRef.current.get(roomMeta.roomId);
    if (existing) {
      return existing;
    }

    const entry = createDocEntry({
      roomId: roomMeta.roomId,
      fileId: roomMeta.fileId,
      filePath: roomMeta.filePath,
      initialContent: file?.content || '',
    });

    docsRef.current.set(roomMeta.roomId, entry);
    return entry;
  }, [file?.content, roomMeta]);

  const flushPendingUpdates = useCallback((roomEntry, forceSnapshot = false) => {
    if (!roomEntry) {
      return;
    }

    if (roomEntry.flushTimer) {
      clearTimeout(roomEntry.flushTimer);
      roomEntry.flushTimer = null;
    }

    const socket = socketRef.current;
    if (!socket || !socket.connected || !roomEntry.joined) {
      return;
    }

    if (forceSnapshot || Date.now() - roomEntry.lastSnapshotSentAt > SNAPSHOT_INTERVAL_MS) {
      const snapshot = uint8ToBase64(Y.encodeStateAsUpdate(roomEntry.ydoc));
      if (snapshot) {
        socket.emit('sync-document', {
          roomId: roomEntry.roomId,
          fileId: roomEntry.fileId,
          isSnapshot: true,
          update: snapshot,
        });
        roomEntry.lastSnapshotSentAt = Date.now();
      }
    }

    if (roomEntry.pendingUpdates.length === 0) {
      return;
    }

    const chunk = roomEntry.pendingUpdates.splice(0, Math.min(roomEntry.pendingUpdates.length, 40));
    socket.emit('sync-document', {
      roomId: roomEntry.roomId,
      fileId: roomEntry.fileId,
      isSnapshot: false,
      updates: chunk,
    });

    if (roomEntry.pendingUpdates.length > 0) {
      roomEntry.flushTimer = setTimeout(() => {
        flushPendingUpdates(roomEntry, false);
      }, OUTGOING_FLUSH_MS);
    }
  }, []);

  const queueUpdate = useCallback((roomEntry, encodedUpdate) => {
    if (!roomEntry || !encodedUpdate) {
      return;
    }

    roomEntry.pendingUpdates.push(encodedUpdate);
    if (roomEntry.pendingUpdates.length > MAX_PENDING_UPDATES) {
      roomEntry.pendingUpdates = roomEntry.pendingUpdates.slice(-MAX_PENDING_UPDATES);
    }

    if (!roomEntry.flushTimer) {
      roomEntry.flushTimer = setTimeout(() => {
        flushPendingUpdates(roomEntry, false);
      }, OUTGOING_FLUSH_MS);
    }
  }, [flushPendingUpdates]);

  const joinRoom = useCallback((roomEntry) => {
    const socket = socketRef.current;
    if (!roomEntry || !socket || !socket.connected) {
      return;
    }

    socket.emit('join-room', {
      roomId: roomEntry.roomId,
      fileId: roomEntry.fileId,
      projectId: workspaceId,
      ownerUserId: ownerUserId || null,
    });
  }, [ownerUserId, workspaceId]);

  useEffect(() => {
    if (!enabled || !actorId) {
      updateConnection('disabled');
      return undefined;
    }

    const socket = io(socketBaseUrl, {
      path: socketPath,
      transports: ['websocket', 'polling'],
      reconnection: true,
      reconnectionDelay: 300,
      reconnectionDelayMax: 4000,
      auth: {
        userId: actorId,
        userName: actorName || actorId,
        color: userColor,
      },
    });

    socketRef.current = socket;
    updateConnection('connecting');

    socket.on('connect', () => {
      updateConnection('connected');
      const activeRoomId = activeRoomIdRef.current;
      if (activeRoomId) {
        const activeEntry = docsRef.current.get(activeRoomId);
        joinRoom(activeEntry);
      }
    });

    socket.on('disconnect', () => {
      updateConnection('disconnected');
      const activeRoomId = activeRoomIdRef.current;
      if (!activeRoomId) {
        return;
      }
      const activeEntry = docsRef.current.get(activeRoomId);
      if (activeEntry) {
        activeEntry.joined = false;
      }
    });

    socket.on('room-joined', (payload) => {
      const roomId = String(payload?.roomId || '').trim();
      if (!roomId) {
        return;
      }

      const roomEntry = docsRef.current.get(roomId);
      if (!roomEntry) {
        return;
      }

      roomEntry.joined = true;
      applyRemoteDocument(roomEntry, payload?.document || {}, REMOTE_UPDATE_ORIGIN);

      const awarenessUpdates = payload?.presence?.awareness || [];
      for (const encoded of awarenessUpdates) {
        applyAwarenessFromBase64(roomEntry, encoded);
      }

      if (roomId === activeRoomIdRef.current) {
        updateParticipants(payload?.presence?.users || []);
        onContentChange?.(roomEntry.ytext.toString(), {
          source: 'remote-collab',
          persist: false,
          roomId,
        });
      }

      const hasDocument = Boolean(payload?.document?.hasDocument);
      if (!hasDocument) {
        flushPendingUpdates(roomEntry, true);
      } else {
        flushPendingUpdates(roomEntry, false);
      }
    });

    socket.on('sync-document', (payload) => {
      const roomId = String(payload?.roomId || '').trim();
      const roomEntry = docsRef.current.get(roomId);
      if (!roomEntry) {
        return;
      }

      const updates = Array.isArray(payload?.updates)
        ? payload.updates
        : payload?.update
          ? [payload.update]
          : [];

      applyRemoteDocument(roomEntry, { updates }, REMOTE_UPDATE_ORIGIN);

      if (roomId === activeRoomIdRef.current) {
        onContentChange?.(roomEntry.ytext.toString(), {
          source: 'remote-collab',
          persist: false,
          roomId,
        });
      }
    });

    socket.on('presence-update', (payload) => {
      const roomId = String(payload?.roomId || '').trim();
      const roomEntry = docsRef.current.get(roomId);
      if (!roomEntry) {
        return;
      }

      if (payload?.update) {
        applyAwarenessFromBase64(roomEntry, payload.update);
      }
    });

    socket.on('presence-updated', (payload) => {
      const roomId = String(payload?.roomId || '').trim();
      if (roomId !== activeRoomIdRef.current) {
        return;
      }
      updateParticipants(payload?.users || []);
    });

    socket.on('sync-recovery', (payload) => {
      const roomId = String(payload?.roomId || '').trim();
      const roomEntry = docsRef.current.get(roomId);
      if (!roomEntry) {
        return;
      }

      applyRemoteDocument(roomEntry, payload || {}, REMOTE_UPDATE_ORIGIN);
      if (roomId === activeRoomIdRef.current) {
        onContentChange?.(roomEntry.ytext.toString(), {
          source: 'remote-collab',
          persist: false,
          roomId,
        });
      }
    });

    socket.on('room-error', () => {
      updateConnection('fallback');
    });

    socket.on('connect_error', () => {
      updateConnection('fallback');
    });

    return () => {
      updateParticipants([]);
      updateConnection('idle');
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [
    actorId,
    actorName,
    enabled,
    flushPendingUpdates,
    joinRoom,
    onContentChange,
    socketBaseUrl,
    socketPath,
    updateConnection,
    updateParticipants,
    userColor,
  ]);

  useEffect(() => {
    if (!enabled || !roomMeta || !editor || !monaco) {
      return undefined;
    }

    const model = editor.getModel();
    if (!model) {
      return undefined;
    }

    const roomEntry = getOrCreateDocEntry();
    if (!roomEntry) {
      return undefined;
    }

    roomEntry.awareness.setLocalStateField('user', {
      id: actorId,
      name: actorName || actorId,
      color: userColor,
    });

    if (activeBindingRef.current) {
      activeBindingRef.current.destroy();
      activeBindingRef.current = null;
    }

    const previousRoomId = activeRoomIdRef.current;
    if (previousRoomId && previousRoomId !== roomEntry.roomId) {
      const previousEntry = docsRef.current.get(previousRoomId);
      if (previousEntry?.detachRuntime) {
        previousEntry.detachRuntime();
        previousEntry.detachRuntime = null;
      }

      if (socketRef.current?.connected) {
        socketRef.current.emit('leave-room', { roomId: previousRoomId });
      }
    }

    activeRoomIdRef.current = roomEntry.roomId;

    const onDocUpdate = (update, origin) => {
      const isRemote = origin === REMOTE_UPDATE_ORIGIN || origin === SNAPSHOT_UPDATE_ORIGIN;
      const currentText = roomEntry.ytext.toString();

      if (isRemote) {
        onContentChange?.(currentText, {
          source: 'remote-collab',
          persist: false,
          roomId: roomEntry.roomId,
        });
        return;
      }

      onContentChange?.(currentText, {
        source: 'local-collab',
        persist: Boolean(persistLocalChanges),
        roomId: roomEntry.roomId,
      });

      const encoded = uint8ToBase64(update);
      if (encoded) {
        queueUpdate(roomEntry, encoded);
      }
    };

    const onAwarenessUpdate = ({ added, updated, removed }, origin) => {
      if (origin === REMOTE_AWARENESS_ORIGIN) {
        return;
      }

      const changed = [...added, ...updated, ...removed];
      if (!changed.length) {
        return;
      }

      const encodedUpdate = awarenessProtocol.encodeAwarenessUpdate(roomEntry.awareness, changed);
      const encoded = uint8ToBase64(encodedUpdate);
      if (!encoded || !socketRef.current?.connected || !roomEntry.joined) {
        return;
      }

      socketRef.current.emit('presence-update', {
        roomId: roomEntry.roomId,
        update: encoded,
      });
    };

    roomEntry.ydoc.on('update', onDocUpdate);
    roomEntry.awareness.on('update', onAwarenessUpdate);

    roomEntry.detachRuntime = () => {
      roomEntry.ydoc.off('update', onDocUpdate);
      roomEntry.awareness.off('update', onAwarenessUpdate);
    };

    activeBindingRef.current = new MonacoBinding(
      roomEntry.ytext,
      model,
      new Set([editor]),
      roomEntry.awareness,
    );

    joinRoom(roomEntry);

    return () => {
      if (activeBindingRef.current) {
        activeBindingRef.current.destroy();
        activeBindingRef.current = null;
      }

      if (roomEntry.detachRuntime) {
        roomEntry.detachRuntime();
        roomEntry.detachRuntime = null;
      }
    };
  }, [
    actorId,
    actorName,
    editor,
    enabled,
    getOrCreateDocEntry,
    joinRoom,
    monaco,
    onContentChange,
    persistLocalChanges,
    queueUpdate,
    roomMeta,
    userColor,
  ]);

  useEffect(() => {
    return () => {
      const socket = socketRef.current;
      if (socket && activeRoomIdRef.current) {
        socket.emit('leave-room', { roomId: activeRoomIdRef.current });
      }

      for (const entry of docsRef.current.values()) {
        if (entry.flushTimer) {
          clearTimeout(entry.flushTimer);
          entry.flushTimer = null;
        }

        if (entry.detachRuntime) {
          entry.detachRuntime();
          entry.detachRuntime = null;
        }

        entry.awareness.destroy();
        entry.ydoc.destroy();
      }

      docsRef.current.clear();
      activeRoomIdRef.current = null;
    };
  }, []);

  return {
    connectionState,
    participants,
    roomId: roomMeta?.roomId || null,
  };
}

export default useRealtimeCollaboration;
