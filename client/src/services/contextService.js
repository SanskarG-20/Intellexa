import axios from "axios";

const DEFAULT_LOCAL_API_BASE_URL = "http://localhost:8000/api";
const DEFAULT_PRODUCTION_API_BASE_URL = "https://intellexa-production.up.railway.app/api";

function normalizeBaseUrl(value) {
  return String(value || "").trim().replace(/\/+$/, "");
}

function buildApiBaseCandidates() {
  const candidates = [];

  const envBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
  if (envBaseUrl) {
    candidates.push(envBaseUrl);
  }

  if (typeof window !== "undefined") {
    const host = String(window.location.hostname || "").toLowerCase();
    const isLocal = host === "localhost" || host === "127.0.0.1";
    if (!isLocal) {
      candidates.push(normalizeBaseUrl(`${window.location.origin}/api`));
      candidates.push(normalizeBaseUrl(DEFAULT_PRODUCTION_API_BASE_URL));
    }
  }

  candidates.push(normalizeBaseUrl(DEFAULT_LOCAL_API_BASE_URL));

  const unique = [];
  const seen = new Set();
  for (const value of candidates) {
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    unique.push(value);
  }

  return unique;
}

const API_BASE_CANDIDATES = buildApiBaseCandidates();
let activeApiBaseUrl = API_BASE_CANDIDATES[0] || normalizeBaseUrl(DEFAULT_LOCAL_API_BASE_URL);
const clients = new Map();

function getClient(baseUrl) {
  const key = normalizeBaseUrl(baseUrl);
  if (clients.has(key)) {
    return clients.get(key);
  }

  const client = axios.create({
    baseURL: key,
    headers: { "Content-Type": "application/json" },
    timeout: 30000,
  });

  clients.set(key, client);
  return client;
}

function shouldRetry(error) {
  if (!axios.isAxiosError(error)) {
    return false;
  }
  if (!error.response) {
    return true;
  }
  const status = error.response.status;
  return status === 404 || status === 502 || status === 503 || status === 504;
}

async function requestWithFallback(paths, params) {
  const normalizedActive = normalizeBaseUrl(activeApiBaseUrl);
  const candidates = [
    normalizedActive,
    ...API_BASE_CANDIDATES.filter((item) => item !== normalizedActive),
  ];

  let lastError = null;
  for (const base of candidates) {
    const client = getClient(base);
    for (const path of paths) {
      try {
        const response = await client.get(path, { params });
        activeApiBaseUrl = base;
        return response.data;
      } catch (error) {
        if (!shouldRetry(error)) {
          throw error;
        }
        lastError = error;
      }
    }
  }

  if (lastError) {
    throw lastError;
  }
  throw new Error("Unable to fetch project context.");
}

export async function getProjectContext(options = {}) {
  const {
    refresh = false,
    offset = 0,
    limit = 200,
    includeEmbeddings = false,
  } = options;

  return requestWithFallback(
    ["/v1/project-context", "/project-context"],
    {
      refresh,
      offset,
      limit,
      include_embeddings: includeEmbeddings,
    },
  );
}

export default {
  getProjectContext,
};
