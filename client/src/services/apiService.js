import axios from "axios";
import { useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";

const DEFAULT_LOCAL_API_BASE_URL = "http://localhost:8000/api";
const DEFAULT_PRODUCTION_API_BASE_URL = "https://intellexa-production.up.railway.app/api";

function normalizeBaseUrl(value) {
  return String(value || "")
    .trim()
    .replace(/\/+$/, "");
}

function buildApiBaseCandidates() {
  const candidates = [];

  const envBaseUrl = normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL);
  if (envBaseUrl) {
    candidates.push(envBaseUrl);
  }

  if (typeof window !== "undefined") {
    const host = String(window.location.hostname || "").toLowerCase();
    const isLocalHost = host === "localhost" || host === "127.0.0.1";

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
const API_BASE_URL = API_BASE_CANDIDATES[0] || normalizeBaseUrl(DEFAULT_LOCAL_API_BASE_URL);
let activeApiBaseUrl = API_BASE_URL;
const CLERK_TOKEN_TEMPLATE = import.meta.env.VITE_CLERK_TOKEN_TEMPLATE?.trim() || "";

const apiClientsByBaseUrl = new Map();

function getApiClient(baseUrl) {
  const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
  if (apiClientsByBaseUrl.has(normalizedBaseUrl)) {
    return apiClientsByBaseUrl.get(normalizedBaseUrl);
  }

  const apiClient = axios.create({
    baseURL: normalizedBaseUrl,
    headers: {
      "Content-Type": "application/json",
    },
    timeout: 30000,
  });

  apiClientsByBaseUrl.set(normalizedBaseUrl, apiClient);
  return apiClient;
}

function normalizeBackendResponse(data) {
  const rootPayload = data && typeof data === "object" ? data : {};
  const payload =
    rootPayload.data && typeof rootPayload.data === "object"
      ? rootPayload.data
      : rootPayload;

  const finalAnswer = payload.final_answer ?? payload.finalResponse ?? payload.output ?? null;
  const fullAnswer = payload.full_answer ?? payload.response ?? finalAnswer ?? null;
  const shortAnswer = payload.short_answer ?? payload.shortAnswer ?? null;
  const sources =
    payload.sources ??
    payload.citations ??
    payload.references ??
    payload.web_sources ??
    payload.search_results ??
    null;
  const toolCalls = payload.tool_calls ?? payload.tools ?? payload.tool_invocations ?? null;
  const reframedQuery =
    payload.reframed_query ??
    payload.reframedQuery ??
    payload.neutral_reframe?.reframed_query ??
    payload.neutral_reframe?.reframedQuery ??
    null;
  const searchUsed =
    payload.search_used ??
    payload.web_search_used ??
    payload.search_performed ??
    payload.tool_search_used ??
    null;

  return {
    response: payload.response ?? "",
    final_answer: finalAnswer,
    full_answer: typeof fullAnswer === "string" ? fullAnswer : "",
    short_answer: typeof shortAnswer === "string" ? shortAnswer : "",
    answer: payload.answer ?? null,
    sources,
    citations: payload.citations ?? null,
    references: payload.references ?? null,
    search_used: searchUsed,
    reframed_query: typeof reframedQuery === "string" ? reframedQuery : null,
    tool_calls: toolCalls,
    tool_events: payload.tool_events ?? null,
    explanation: payload.explanation ?? null,
    ethical_check: payload.ethical_check ?? null,
    trust_score: payload.trust_score ?? null,
    confidence: payload.confidence ?? null,
    ethical_perspectives: payload.ethical_perspectives ?? null,
    audit_results: payload.audit_results ?? null,
    perspective_autopsy: payload.perspective_autopsy ?? null,
  };
}

async function getAuthorizationHeader(getToken, { forceRefresh = false } = {}) {
  if (typeof getToken !== "function") {
    return null;
  }

  let token = null;

  if (CLERK_TOKEN_TEMPLATE) {
    token = await getToken({
      template: CLERK_TOKEN_TEMPLATE,
      skipCache: forceRefresh,
    });
  }

  if (!token) {
    token = await getToken({ skipCache: forceRefresh });
  }

  if (!token) {
    return null;
  }

  return `Bearer ${token}`;
}

function shouldRetryWithNextBaseUrl(error) {
  if (!axios.isAxiosError(error)) {
    return false;
  }

  if (axios.isCancel(error) || error.code === "ERR_CANCELED") {
    return false;
  }

  const statusCode = error.response?.status;
  return !error.response || statusCode === 404 || statusCode === 502 || statusCode === 503 || statusCode === 504;
}

async function postChatMessage(
  message,
  authorization,
  signal,
  requestMeta = {},
  baseUrl = activeApiBaseUrl
) {
  const apiClient = getApiClient(baseUrl);
  const requestConfig = {};

  if (authorization) {
    requestConfig.headers = {
      Authorization: authorization,
    };
  }

  if (signal) {
    requestConfig.signal = signal;
  }

  const { data } = await apiClient.post(
    "/v1/chat",
    {
      message: message.trim(),
      voice_mode: Boolean(requestMeta?.voiceMode),
    },
    requestConfig
  );

  return data;
}

async function postChatMessageWithBaseFallback(message, authorization, signal, requestMeta = {}) {
  const normalizedActiveBase = normalizeBaseUrl(activeApiBaseUrl);
  const candidateBaseUrls = [
    normalizedActiveBase,
    ...API_BASE_CANDIDATES.filter((candidate) => candidate !== normalizedActiveBase),
  ];

  let lastAxiosError = null;

  for (const baseUrl of candidateBaseUrls) {
    try {
      const data = await postChatMessage(message, authorization, signal, requestMeta, baseUrl);
      activeApiBaseUrl = baseUrl;
      return data;
    } catch (error) {
      if (!axios.isAxiosError(error)) {
        throw error;
      }

      if (!shouldRetryWithNextBaseUrl(error)) {
        throw error;
      }

      lastAxiosError = error;
    }
  }

  if (lastAxiosError) {
    throw lastAxiosError;
  }

  throw new Error("Unable to reach any configured API base URL.");
}

export async function sendMessage(message, getToken, options = {}) {
  if (typeof message !== "string" || !message.trim()) {
    throw new Error("sendMessage(message) requires a non-empty message string.");
  }

  const signal = options?.signal;
  const requestMeta = {
    voiceMode: Boolean(options?.voiceMode || options?.requestMeta?.voiceMode),
  };

  let authorization = await getAuthorizationHeader(getToken);

  try {
    const data = await postChatMessageWithBaseFallback(
      message,
      authorization,
      signal,
      requestMeta
    );
    return normalizeBackendResponse(data);
  } catch (error) {
    if (axios.isAxiosError(error)) {
      if (axios.isCancel(error) || error.code === "ERR_CANCELED") {
        throw new Error("Request canceled by user.");
      }

      const statusCode = error.response?.status;

      if (statusCode === 401) {
        if (!authorization) {
          throw new Error(
            "401 Unauthorized: backend requires a valid auth token. Sign in again or configure the Clerk token template."
          );
        }

        try {
          const refreshedAuthorization = await getAuthorizationHeader(getToken, {
            forceRefresh: true,
          });

          if (!refreshedAuthorization) {
            throw new Error("Unable to refresh auth token.");
          }

          authorization = refreshedAuthorization;
          const retryData = await postChatMessageWithBaseFallback(
            message,
            refreshedAuthorization,
            signal,
            requestMeta
          );
          return normalizeBackendResponse(retryData);
        } catch {
          throw new Error(
            "401 Unauthorized: auth token was rejected. Verify Clerk token template and backend token verification."
          );
        }
      }

      if (!error.response) {
        throw new Error(
          `Network/CORS error: unable to reach chat API. Tried: ${API_BASE_CANDIDATES.join(
            ", "
          )}. Check backend URL, running server, and CORS.`
        );
      }

      if (statusCode === 404) {
        throw new Error(
          `Endpoint not found: expected POST ${activeApiBaseUrl}/v1/chat.`
        );
      }

      const backendMessage = error.response?.data?.detail;
      throw new Error(
        backendMessage || error.message || "Failed to fetch chat response from backend."
      );
    }

    throw error;
  }
}

export function useApiService() {
  const { getToken, isLoaded } = useAuth();

  const sendAuthenticatedMessage = useCallback(
    async (message, options = {}) => {
      if (!isLoaded) {
        throw new Error("Authentication is still loading. Please try again.");
      }

      return sendMessage(message, getToken, options);
    },
    [getToken, isLoaded]
  );

  return {
    sendMessage: sendAuthenticatedMessage,
  };
}

export { API_BASE_URL };

export default apiClient;
