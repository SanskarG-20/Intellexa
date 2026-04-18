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
 * Create a new code file
 */
export async function createCodeFile(file) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/files`, {
    filename: file.filename,
    path: file.path || '/',
    content: file.content || '',
    language: file.language || 'javascript',
    is_folder: file.isFolder || false,
    parent_id: file.parentId || null,
  });
}

/**
 * Update an existing code file
 */
export async function updateCodeFile(fileId, updates) {
  return requestWithFallback('put', `${CODE_API_PREFIX}/files/${fileId}`, {
    filename: updates.filename,
    content: updates.content,
    language: updates.language,
  });
}

/**
 * Delete a code file
 */
export async function deleteCodeFile(fileId) {
  return requestWithFallback('delete', `${CODE_API_PREFIX}/files/${fileId}`);
}

/**
 * Import multiple code files
 */
export async function importCodeFiles(files) {
  return requestWithFallback('post', `${CODE_API_PREFIX}/files/import`, {
    files: files.map(f => ({
      filename: f.filename,
      path: f.path || '/',
      content: f.content || '',
      language: f.language || 'javascript',
    }))
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
    max_suggestions: request.maxSuggestions || 5,
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
  createCodeFile,
  updateCodeFile,
  deleteCodeFile,
  importCodeFiles,
  getFileTree,
  codeAssist,
  codeAutocomplete,
  executeCode,
  detectLanguage,
};
