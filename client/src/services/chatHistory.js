import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.trim();
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();
const ANALYSIS_CACHE_KEY = "intellexa_chat_analysis_v1";
const LOCAL_CHAT_CACHE_KEY = "intellexa_local_chat_history_v1";

const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
    : null;

export function isCloudHistoryEnabled() {
  return Boolean(supabase);
}

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

function removeCachedStructuredPayload(chatId) {
  const safeChatId = String(chatId || "").trim();
  if (!safeChatId) {
    return;
  }

  const cache = readAnalysisCache();
  if (!(safeChatId in cache)) {
    return;
  }

  delete cache[safeChatId];
  writeAnalysisCache(cache);
}

function toTimestamp(value) {
  const time = new Date(value || "").getTime();
  return Number.isFinite(time) ? time : 0;
}

function sortChatsByDateDesc(items) {
  return [...items].sort((a, b) => toTimestamp(b.created_at) - toTimestamp(a.created_at));
}

function generateLocalChatId() {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }

  return `local_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function readLocalChats() {
  if (typeof window === "undefined") {
    return [];
  }

  try {
    const raw = window.localStorage.getItem(LOCAL_CHAT_CACHE_KEY);
    if (!raw) {
      return [];
    }

    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }

    return parsed
      .map(normalizeConversationRow)
      .filter(Boolean)
      .filter((item) => item.id);
  } catch {
    return [];
  }
}

function writeLocalChats(chats) {
  if (typeof window === "undefined") {
    return;
  }

  const safeChats = Array.isArray(chats)
    ? chats
        .map((chat) => normalizeConversationRow(chat))
        .filter(Boolean)
        .filter((item) => item.id)
    : [];

  try {
    window.localStorage.setItem(LOCAL_CHAT_CACHE_KEY, JSON.stringify(safeChats));
  } catch {
    // Ignore storage quota/permission errors.
  }
}

function updateLocalStructuredPayload(chatId, structuredPayload) {
  const safeChatId = String(chatId || "").trim();
  const safeStructured = sanitizeStructuredPayload(structuredPayload);

  if (!safeChatId || !safeStructured) {
    return;
  }

  const chats = readLocalChats();
  const nextChats = chats.map((chat) =>
    chat.id === safeChatId
      ? {
          ...chat,
          structured_payload: safeStructured,
        }
      : chat
  );

  writeLocalChats(nextChats);
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

  if (!supabase) {
    updateLocalStructuredPayload(safeChatId, safeStructured);
    return true;
  }

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
  const safeUserId = ensureUserId(userId);

  if (!supabase) {
    return sortChatsByDateDesc(
      readLocalChats().filter((item) => item.user_id === safeUserId)
    );
  }

  const client = ensureSupabaseClient();

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
  const safeUserId = ensureUserId(userId);

  const safeMessage = String(message || "").trim();
  const safeResponse = String(response || "").trim();

  if (!safeMessage) {
    throw new Error("saveMessage requires a non-empty user message.");
  }

  if (!supabase) {
    const nextLocalChat = normalizeConversationRow({
      id: generateLocalChatId(),
      user_id: safeUserId,
      message: safeMessage,
      response: safeResponse,
      created_at: new Date().toISOString(),
      structured_payload: sanitizeStructuredPayload(structuredPayload),
    });

    const existing = readLocalChats().filter((chat) => chat.user_id === safeUserId);
    writeLocalChats(sortChatsByDateDesc([nextLocalChat, ...existing]));

    if (nextLocalChat?.id && structuredPayload) {
      const cache = readAnalysisCache();
      cache[nextLocalChat.id] = sanitizeStructuredPayload(structuredPayload);
      writeAnalysisCache(cache);
    }

    return nextLocalChat;
  }

  const client = ensureSupabaseClient();

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
  const safeChatId = String(chatId || "").trim();

  if (!safeChatId) {
    throw new Error("A valid chatId is required.");
  }

  if (!supabase) {
    return readLocalChats().find((item) => item.id === safeChatId) || null;
  }

  const client = ensureSupabaseClient();

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

export async function deleteChatById(chatId, userId) {
  const safeChatId = String(chatId || "").trim();
  const safeUserId = ensureUserId(userId);

  if (!safeChatId) {
    throw new Error("A valid chatId is required.");
  }

  if (!supabase) {
    const chats = readLocalChats();
    const nextChats = chats.filter(
      (item) => !(item.id === safeChatId && item.user_id === safeUserId)
    );
    writeLocalChats(nextChats);
    removeCachedStructuredPayload(safeChatId);
    return;
  }

  const client = ensureSupabaseClient();

  const { error } = await client
    .from("conversations")
    .delete()
    .eq("id", safeChatId)
    .eq("user_id", safeUserId);

  if (error) {
    throw new Error(error.message || "Failed to delete chat.");
  }

  removeCachedStructuredPayload(safeChatId);
}
