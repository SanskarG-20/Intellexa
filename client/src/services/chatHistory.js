import { createClient } from "@supabase/supabase-js";

const SUPABASE_URL = import.meta.env.VITE_SUPABASE_URL?.trim();
const SUPABASE_ANON_KEY = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim();

const supabase =
  SUPABASE_URL && SUPABASE_ANON_KEY
    ? createClient(SUPABASE_URL, SUPABASE_ANON_KEY)
    : null;

function ensureSupabaseClient() {
  if (!supabase) {
    throw new Error(
      "Missing Supabase config. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in client env."
    );
  }

  return supabase;
}

function normalizeConversationRow(row) {
  if (!row || typeof row !== "object") {
    return null;
  }

  return {
    id: String(row.id || ""),
    user_id: String(row.user_id || ""),
    message: String(row.message || ""),
    response: String(row.response || ""),
    created_at: row.created_at || null,
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

  const { data, error } = await client
    .from("conversations")
    .select("id, user_id, message, response, created_at")
    .eq("user_id", safeUserId)
    .order("created_at", { ascending: false });

  if (error) {
    throw new Error(error.message || "Failed to fetch user chat history.");
  }

  return (data || [])
    .map(normalizeConversationRow)
    .filter(Boolean)
    .filter((item) => item.id);
}

export async function saveMessage(userId, message, response) {
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

  return normalizeConversationRow(data);
}

export async function getChatById(chatId) {
  const client = ensureSupabaseClient();
  const safeChatId = String(chatId || "").trim();

  if (!safeChatId) {
    throw new Error("A valid chatId is required.");
  }

  const { data, error } = await client
    .from("conversations")
    .select("id, user_id, message, response, created_at")
    .eq("id", safeChatId)
    .maybeSingle();

  if (error) {
    throw new Error(error.message || "Failed to fetch chat by id.");
  }

  return normalizeConversationRow(data);
}
