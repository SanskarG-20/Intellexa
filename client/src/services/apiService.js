import axios from "axios";
import { useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.trim() || "http://localhost:8000/api";
const CLERK_TOKEN_TEMPLATE = import.meta.env.VITE_CLERK_TOKEN_TEMPLATE?.trim() || "";

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

function normalizeBackendResponse(data) {
  const rootPayload = data && typeof data === "object" ? data : {};
  const payload =
    rootPayload.data && typeof rootPayload.data === "object"
      ? rootPayload.data
      : rootPayload;

  return {
    response: payload.response ?? "",
    answer: payload.answer ?? null,
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

async function postChatMessage(message, authorization) {
  const requestConfig = authorization
    ? {
        headers: {
          Authorization: authorization,
        },
      }
    : undefined;

  const { data } = await apiClient.post(
    "/v1/chat",
    {
      message: message.trim(),
    },
    requestConfig
  );

  return data;
}

export async function sendMessage(message, getToken) {
  if (typeof message !== "string" || !message.trim()) {
    throw new Error("sendMessage(message) requires a non-empty message string.");
  }

  let authorization = await getAuthorizationHeader(getToken);

  try {
    const data = await postChatMessage(message, authorization);
    return normalizeBackendResponse(data);
  } catch (error) {
    if (axios.isAxiosError(error)) {
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
          const retryData = await postChatMessage(message, refreshedAuthorization);
          return normalizeBackendResponse(retryData);
        } catch {
          throw new Error(
            "401 Unauthorized: auth token was rejected. Verify Clerk token template and backend token verification."
          );
        }
      }

      if (!error.response) {
        throw new Error(
          `Network/CORS error: unable to reach ${API_BASE_URL}/v1/chat. Check backend URL, running server, and CORS.`
        );
      }

      if (statusCode === 404) {
        throw new Error(
          `Endpoint not found: expected POST ${API_BASE_URL}/v1/chat.`
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
    async (message) => {
      if (!isLoaded) {
        throw new Error("Authentication is still loading. Please try again.");
      }

      return sendMessage(message, getToken);
    },
    [getToken, isLoaded]
  );

  return {
    sendMessage: sendAuthenticatedMessage,
  };
}

export { API_BASE_URL };

export default apiClient;
