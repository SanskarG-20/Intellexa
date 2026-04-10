import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.trim();
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();
const ANALYSIS_CACHE_KEY = "intellexa_chat_analysis_v1";

const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
    : null;

function ensureSupabaseClient() {
  if (!supabase) {
    throw new Error(
      "Missing Supabase config. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in client/.env (VITE_ keys are required for browser access)."
    );
  }

  return supabase;
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sanitizeStructuredPayload(payload) {
  if (!isPlainObject(payload)) {
    return null;
  }

  try {
    return JSON.parse(JSON.stringify(payload));
  } catch {
    return null;
  }
}

function readAnalysisCache() {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(ANALYSIS_CACHE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw);
    return isPlainObject(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writeAnalysisCache(cache) {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.setItem(ANALYSIS_CACHE_KEY, JSON.stringify(cache));
  } catch {
    // Ignore storage quota/permission errors.
  }
}

function readCachedStructuredPayload(chatId) {
  const safeChatId = String(chatId || "").trim();
  if (!safeChatId) {
    return null;
  }

  const cache = readAnalysisCache();
  return sanitizeStructuredPayload(cache[safeChatId]);
}

export async function persistStructuredPayloadForChat(chatId, structuredPayload) {
  const safeChatId = String(chatId || "").trim();
  const safeStructured = sanitizeStructuredPayload(structuredPayload);

  if (!safeChatId || !safeStructured) {
    return false;
  }

  const cache = readAnalysisCache();
  cache[safeChatId] = safeStructured;
  writeAnalysisCache(cache);

  const client = ensureSupabaseClient();

  const { error } = await client
    .from("conversations")
    .update({ structured_payload: safeStructured })
    .eq("id", safeChatId);

  if (error) {
    return false;
  }

  return true;
}

async function runConversationSelect(selectBuilderWithColumns) {
  let result = await selectBuilderWithColumns("id, user_id, message, response, created_at, structured_payload");

  if (result.error && /structured_payload/i.test(result.error.message || "")) {
    result = await selectBuilderWithColumns("id, user_id, message, response, created_at");
  }

  return result;
}

function normalizeConversationRow(row) {
  if (!row || typeof row !== "object") {
    return null;
  }

  const chatId = String(row.id || "");
  const structuredFromRow = sanitizeStructuredPayload(row.structured_payload);
  const structuredFromCache = readCachedStructuredPayload(chatId);

  return {
    id: chatId,
    user_id: String(row.user_id || ""),
    message: String(row.message || ""),
    response: String(row.response || ""),
    created_at: row.created_at || null,
    structured_payload: structuredFromRow || structuredFromCache,
  };
}

function ensureUserId(userId) {
  if (typeof userId !== "string" || !userId.trim()) {
    throw new Error("A valid Clerk userId is required.");
  }

  return userId.trim();
}

export async function getUserChats(userId) {
  const client = ensureSupabaseClient();
  const safeUserId = ensureUserId(userId);

  const { data, error } = await runConversationSelect((columns) =>
    client
      .from("conversations")
      .select(columns)
      .eq("user_id", safeUserId)
      .order("created_at", { ascending: false })
  );

  if (error) {
    throw new Error(error.message || "Failed to fetch user chat history.");
  }

  return (data || [])
    .map(normalizeConversationRow)
    .filter(Boolean)
    .filter((item) => item.id);
}

export async function saveMessage(userId, message, response, structuredPayload = null) {
  const client = ensureSupabaseClient();
  const safeUserId = ensureUserId(userId);

  const safeMessage = String(message || "").trim();
  const safeResponse = String(response || "").trim();

  if (!safeMessage) {
    throw new Error("saveMessage requires a non-empty user message.");
  }

  const payload = {
    user_id: safeUserId,
    message: safeMessage,
    response: safeResponse,
  };

  const { data, error } = await client
    .from("conversations")
    .insert(payload)
    .select("id, user_id, message, response, created_at")
    .single();

  if (error) {
    throw new Error(error.message || "Failed to save message.");
  }

  const normalized = normalizeConversationRow(data);

  if (normalized?.id && structuredPayload) {
    await persistStructuredPayloadForChat(normalized.id, structuredPayload);
    normalized.structured_payload = sanitizeStructuredPayload(structuredPayload);
  }

  return normalized;
}

export async function getChatById(chatId) {
  const client = ensureSupabaseClient();
  const safeChatId = String(chatId || "").trim();

  if (!safeChatId) {
    throw new Error("A valid chatId is required.");
  }

  const { data, error } = await runConversationSelect((columns) =>
    client
      .from("conversations")
      .select(columns)
      .eq("id", safeChatId)
      .maybeSingle()
  );

  if (error) {
    throw new Error(error.message || "Failed to fetch chat by id.");
  }

  return normalizeConversationRow(data);
}
