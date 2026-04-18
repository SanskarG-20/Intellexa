/**
 * codeFileService.js
 * API service for Code Space file operations.
 */

import axios from 'axios';

const DEFAULT_LOCAL_API_BASE_URL = "http://localhost:8000/api";
const DEFAULT_PRODUCTION_API_BASE_URL = "https://intellexa-production.up.railway.app/api";

function normalizeBaseUrl(value) {
  return String(value || '').trim().replace(/\/+$/, '');
}

function buildApiBaseCandidates() {
  const candidates = [];

  const envBase = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
  if (envBase) {
    candidates.push(envBase);
  }

  if (typeof window !== 'undefined') {
    const host = String(window.location.hostname || '').toLowerCase();
    const isLocalHost = host === 'localhost' || host === '127.0.0.1';
    if (!isLocalHost) {
      candidates.push(normalizeBaseUrl(`${window.location.origin}/api`));
      candidates.push(normalizeBaseUrl(DEFAULT_PRODUCTION_API_BASE_URL));
    }
  }

  candidates.push(normalizeBaseUrl(DEFAULT_LOCAL_API_BASE_URL));

  const unique = [];
  const seen = new Set();
  for (const candidate of candidates) {
    if (!candidate || seen.has(candidate)) {
      continue;
    }
    seen.add(candidate);
    unique.push(candidate);
  }
  return unique;
}

const API_BASE_CANDIDATES = buildApiBaseCandidates();
let activeApiBaseUrl = API_BASE_CANDIDATES[0] || normalizeBaseUrl(DEFAULT_LOCAL_API_BASE_URL);
const apiClientByBase = new Map();

function getApiClient(baseUrl) {
  const normalized = normalizeBaseUrl(baseUrl);
  if (apiClientByBase.has(normalized)) {
    return apiClientByBase.get(normalized);
  }

  const apiClient = axios.create({
    baseURL: normalized,
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
  });
  apiClientByBase.set(normalized, apiClient);
  return apiClient;
}

function shouldRetryWithNextBase(error) {
  if (!axios.isAxiosError(error)) {
    return false;
  }
  if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
    return false;
  }
  const status = error.response?.status;
  return !error.response || status === 404 || status === 502 || status === 503 || status === 504;
}

function formatApiError(error, endpointPath) {
  if (!axios.isAxiosError(error)) {
    return error?.message || `Request failed: ${endpointPath}`;
  }

  if (axios.isCancel(error) || error.code === 'ERR_CANCELED') {
    return 'Request was canceled.';
  }

  if (!error.response) {
    return (
      `Network/CORS error while calling ${endpointPath}. ` +
      `Tried API bases: ${API_BASE_CANDIDATES.join(', ')}`
    );
  }

  const backendMessage = error.response?.data?.detail;
  return backendMessage || error.message || `Request failed: ${endpointPath}`;
}

function buildCollaborationHeaders(collaboration) {
  if (!collaboration || !collaboration.workspaceId) {
    return {};
  }

  const headers = {
    'X-Collab-Workspace-Id': String(collaboration.workspaceId || '').trim(),
  };

  if (collaboration.actorId) {
    headers['X-Collab-Actor-Id'] = String(collaboration.actorId).trim();
  }
  if (collaboration.actorName) {
    headers['X-Collab-Actor-Name'] = String(collaboration.actorName).trim();
  }

  return headers;
}

function withCollaborationHeaders(config = {}, collaboration) {
  const collabHeaders = buildCollaborationHeaders(collaboration);
  if (!Object.keys(collabHeaders).length) {
    return config;
  }

  return {
    ...config,
    headers: {
      ...(config.headers || {}),
      ...collabHeaders,
    },
  };
}

async function requestWithFallback(method, path, payload, config = {}) {
  const normalizedActive = normalizeBaseUrl(activeApiBaseUrl);
  const candidates = [
    normalizedActive,
    ...API_BASE_CANDIDATES.filter((candidate) => candidate !== normalizedActive),
  ];

  let lastError = null;

  for (const base of candidates) {
    const apiClient = getApiClient(base);
    try {
      const requestConfig = { ...config };
      let response;

      if (method === 'get' || method === 'delete') {
        response = await apiClient[method](path, requestConfig);
      } else {
        response = await apiClient[method](path, payload, requestConfig);
      }

      activeApiBaseUrl = base;
      return response.data;
    } catch (error) {
      if (!shouldRetryWithNextBase(error)) {
        throw new Error(formatApiError(error, path));
      }
      lastError = error;
    }
  }

  throw new Error(formatApiError(lastError, path));
}

const CODE_API_PREFIX = '/v1/code';

/**
 * List all code files for the user
 */
export async function listCodeFiles(path = '/') {
  return requestWithFallback('get', `${CODE_API_PREFIX}/files`, undefined, {
    params: { path }
  });
}

/**
 * Get a specific code file by ID
 */
export async function getCodeFile(fileId) {
  return requestWithFallback('get', `${CODE_API_PREFIX}/files/${fileId}`);
}

/**
 * List version history for a file.
 */
export async function listFileVersions(fileId, options = {}) {
  const { limit = 30 } = options;
  return requestWithFallback('get', `${CODE_API_PREFIX}/files/${fileId}/versions`, undefined, {
    params: { limit },
  });
}

/**
 * Get one specific version snapshot for a file.
 */
export async function getFileVersion(fileId, versionId) {
  return requestWithFallback('get', `${CODE_API_PREFIX}/files/${fileId}/versions/${versionId}`);
}

/**
 * Compare two versions of a file.
 */
export async function compareFileVersions(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/versions/compare`, {
    file_id: request.fileId,
    from_version_id: request.fromVersionId || null,
    to_version_id: request.toVersionId || null,
  });
}

/**
 * Ask version intelligence why a change likely broke behavior.
 */
export async function whyDidThisBreak(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/versions/why-broke`, {
    file_id: request.fileId,
    question: request.question || 'Why did this break?',
    failure_context: request.failureContext,
    baseline_version_id: request.baselineVersionId || null,
    current_version_id: request.currentVersionId || null,
  });
}

/**
 * Create a new code file
 */
export async function createCodeFile(file, options = {}) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/files`, {
    filename: file.filename,
    path: file.path || '/',
    content: file.content || '',
    language: file.language || 'javascript',
    is_folder: file.isFolder || false,
    parent_id: file.parentId || null,
  }, withCollaborationHeaders({}, options.collaboration));
}

/**
 * Update an existing code file
 */
export async function updateCodeFile(fileId, updates, options = {}) {
  return requestWithFallback('put', `${CODE_API_PREFIX}/files/${fileId}`, {
    filename: updates.filename,
    content: updates.content,
    language: updates.language,
  }, withCollaborationHeaders({}, options.collaboration));
}

/**
 * Delete a code file
 */
export async function deleteCodeFile(fileId, options = {}) {
  return requestWithFallback(
    'delete',
    `${CODE_API_PREFIX}/files/${fileId}`,
    undefined,
    withCollaborationHeaders({}, options.collaboration),
  );
}

/**
 * Import multiple code files
 */
export async function importCodeFiles(files, options = {}) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/files/import`, {
    files: files.map(f => ({
      filename: f.filename,
      path: f.path || '/',
      content: f.content || '',
      language: f.language || 'javascript',
    }))
  }, withCollaborationHeaders({}, options.collaboration));
}

/**
 * Join a shared collaboration workspace.
 */
export async function joinCollaborationWorkspace(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/collaboration/join`, {
    workspace_id: request.workspaceId,
    actor_id: request.actorId || null,
    actor_name: request.actorName || null,
    actor_role: request.actorRole || 'user',
  });
}

/**
 * Poll collaboration state (presence + incremental events).
 */
export async function getCollaborationState(request) {
  return requestWithFallback('get', `${CODE_API_PREFIX}/collaboration/state`, undefined, {
    params: {
      workspace_id: request.workspaceId,
      since_sequence: request.sinceSequence || 0,
      limit: request.limit || 50,
      actor_id: request.actorId || null,
      actor_name: request.actorName || null,
    },
  });
}

/**
 * Publish user or AI context into collaboration event stream.
 */
export async function publishCollaborationContext(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/collaboration/context`, {
    workspace_id: request.workspaceId,
    actor_id: request.actorId || null,
    actor_name: request.actorName || null,
    actor_role: request.actorRole || 'user',
    event_type: request.eventType || 'user_context',
    message: request.message || '',
    file_id: request.fileId || null,
    file_key: request.fileKey || null,
    metadata: request.metadata || {},
  });
}

/**
 * Get file tree structure
 */
export async function getFileTree() {
  return requestWithFallback('get', `${CODE_API_PREFIX}/tree`);
}

/**
 * Request AI code assistance
 */
export async function codeAssist(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/code-assist`, {
    code: request.code || '',
    language: request.language || 'javascript',
    prompt: request.prompt,
    action: request.action || 'explain',
    include_context: request.includeContext !== false,
    context: request.context,
    learning_mode: request.learningMode === true,
    max_suggestions: request.maxSuggestions || 5,
  });
}

/**
 * Build or update Task Mode (AI Project Builder) session.
 */
export async function taskModeBuild(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/task-mode`, {
    prompt: request.prompt,
    code: request.code || '',
    language: request.language || 'javascript',
    include_context: request.includeContext !== false,
    context: request.context,
    session_id: request.taskSessionId || null,
    completed_step_ids: request.completedStepIds || [],
    active_step_id: request.activeStepId || null,
    regenerate_plan: request.regeneratePlan === true,
  });
}

/**
 * Predict potential bugs before execution.
 */
export async function bugPredict(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/bug-predict`, {
    code: request.code || '',
    language: request.language || 'javascript',
    filename: request.filename,
  });
}

/**
 * Scan code for security vulnerabilities.
 */
export async function securityScan(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/security-scan`, {
    code: request.code || '',
    language: request.language || 'javascript',
    filename: request.filename,
  });
}

/**
 * Request Learning Mode deep explanation for a code snippet.
 */
export async function learningModeExplain(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/learning-mode`, {
    code: request.code || '',
    language: request.language || 'javascript',
    prompt: request.prompt || 'Explain this code deeply for learning.',
    include_context: request.includeContext !== false,
    context: request.context,
  });
}

/**
 * Request AI autocomplete suggestions for the current editor state
 */
export async function codeAutocomplete(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/autocomplete`, {
    code: request.code || '',
    language: request.language || 'javascript',
    cursor_line: request.cursorLine || 1,
    cursor_column: request.cursorColumn || 1,
    max_suggestions: request.maxSuggestions || 3,
    context: request.context,
  });
}

/**
 * Execute code in backend sandbox
 */
export async function executeCode(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/execute`, {
    code: request.code || '',
    language: request.language || 'python',
    stdin: request.stdin || '',
    timeout_ms: request.timeoutMs || 3000,
  });
}

/**
 * Run AI project-wide refactor engine.
 */
export async function projectRefactor(request) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/project-refactor`, {
    files: (request.files || []).map((file) => ({
      path: file.path,
      content: file.content || '',
      language: file.language,
    })),
    instruction: request.instruction,
    safe_mode: request.safeMode !== false,
    include_explanation: request.includeExplanation !== false,
    max_files_to_update: request.maxFilesToUpdate || 40,
  });
}

/**
 * Detect language from file extension
 */
export function detectLanguage(filename) {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  
  const languageMap = {
    'js': 'javascript',
    'jsx': 'javascript',
    'ts': 'typescript',
    'tsx': 'typescript',
    'py': 'python',
    'rb': 'ruby',
    'java': 'java',
    'go': 'go',
    'rs': 'rust',
    'c': 'c',
    'cpp': 'cpp',
    'h': 'c',
    'hpp': 'cpp',
    'cs': 'csharp',
    'php': 'php',
    'swift': 'swift',
    'kt': 'kotlin',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'sass': 'scss',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'xml': 'xml',
    'md': 'markdown',
    'sql': 'sql',
    'sh': 'bash',
    'bash': 'bash',
  };
  
  return languageMap[ext] || 'plaintext';
}

export default {
  listCodeFiles,
  getCodeFile,
  listFileVersions,
  getFileVersion,
  compareFileVersions,
  whyDidThisBreak,
  createCodeFile,
  updateCodeFile,
  deleteCodeFile,
  importCodeFiles,
  joinCollaborationWorkspace,
  getCollaborationState,
  publishCollaborationContext,
  getFileTree,
  codeAssist,
  taskModeBuild,
  bugPredict,
  securityScan,
  learningModeExplain,
  codeAutocomplete,
  executeCode,
  projectRefactor,
  detectLanguage,
};
