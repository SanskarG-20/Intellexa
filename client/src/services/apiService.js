import axios from "axios";
import { useCallback } from "react";
import { useAuth } from "@clerk/clerk-react";

const apiClient = axios.create({
  baseURL: "http://localhost:5000/api",
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30000,
});

async function getAuthorizationHeader(getToken) {
  if (typeof getToken !== "function") {
    throw new Error("sendMessage requires Clerk getToken from useAuth().");
  }

  const token = await getToken();

  if (!token) {
    throw new Error("Missing Clerk auth token. Please sign in and try again.");
  }

  return `Bearer ${token}`;
}

export async function sendMessage(message, getToken) {
  if (typeof message !== "string" || !message.trim()) {
    throw new Error("sendMessage(message) requires a non-empty message string.");
  }

  try {
    const authorization = await getAuthorizationHeader(getToken);

    // Backend expects exactly: { message: string }
    const { data } = await apiClient.post(
      "/v1/chat",
      {
        message: message.trim(),
      },
      {
        headers: {
          Authorization: authorization,
        },
      }
    );

    return {
      response: data?.response ?? "",
      answer: data?.answer ?? null,
      explanation: data?.explanation ?? null,
      ethical_check: data?.ethical_check ?? null,
      trust_score: data?.trust_score ?? null,
      confidence: data?.confidence ?? null,
      ethical_perspectives: data?.ethical_perspectives ?? null,
      audit_results: data?.audit_results ?? null,
      perspective_autopsy: data?.perspective_autopsy ?? null,
    };
  } catch (error) {
    if (axios.isAxiosError(error)) {
      const backendMessage = error.response?.data?.detail;
      throw new Error(
        backendMessage || error.message || "Failed to fetch chat response from backend."
      );
    }

    throw error;
  }
}

export function useApiService() {
  const { getToken } = useAuth();

  const sendAuthenticatedMessage = useCallback(
    async (message) => sendMessage(message, getToken),
    [getToken]
  );

  return {
    sendMessage: sendAuthenticatedMessage,
  };
}

export default apiClient;
