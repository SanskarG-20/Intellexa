const HF_CHAT_COMPLETIONS_URL = "https://router.huggingface.co/v1/chat/completions";

const PERSPECTIVE_SYSTEM_PROMPT = [
  "You are an ethics reasoning assistant.",
  "Read the user question and context.",
  "Generate 3 perspectives: utilitarian, rights-based, and care ethics.",
  "",
  "Return STRICT JSON only with this exact schema:",
  "{",
  '  "utilitarian": "...",',
  '  "rights_based": "...",',
  '  "care_ethics": "..."',
  "}",
  "",
  "Rules:",
  "- utilitarian: focus on outcomes and overall well-being",
  "- rights_based: focus on rights, duties, and fairness",
  "- care_ethics: focus on relationships, vulnerability, and care",
  "- Keep each value concise and practical",
  "- Do not add extra keys",
].join("\n");

function asCleanString(value) {
  return String(value || "").trim();
}

function normalizeContext(context) {
  if (typeof context === "string") {
    const text = context.trim();
    return text || "No additional context provided.";
  }

  if (context == null) {
    return "No additional context provided.";
  }

  try {
    const serialized = JSON.stringify(context);
    return serialized && serialized !== "{}" ? serialized : "No additional context provided.";
  } catch {
    return "No additional context provided.";
  }
}

function normalizePerspectivePayload(payload) {
  return {
    utilitarian: asCleanString(payload?.utilitarian),
    rights_based: asCleanString(payload?.rights_based),
    care_ethics: asCleanString(payload?.care_ethics),
  };
}

function extractModelText(data) {
  const text = data?.choices?.[0]?.message?.content;

  if (!text || typeof text !== "string") {
    throw new Error("LLaMA returned an unexpected response format.");
  }

  return text.trim();
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    const firstBrace = text.indexOf("{");
    const lastBrace = text.lastIndexOf("}");

    if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) {
      throw new Error("LLaMA did not return valid JSON.");
    }

    return JSON.parse(text.slice(firstBrace, lastBrace + 1));
  }
}

async function generatePerspectives(question, context) {
  if (typeof question !== "string" || !question.trim()) {
    throw new Error("generatePerspectives(question, context) requires a non-empty question string.");
  }

  const token = String(process.env.HF_TOKEN || "").trim();
  const model = String(process.env.HF_MODEL || "meta-llama/Llama-3.1-8B-Instruct").trim();

  if (!token) {
    throw new Error("Missing HF_TOKEN in environment variables.");
  }

  const userPrompt = [
    "USER QUESTION:",
    '"""',
    question.trim(),
    '"""',
    "",
    "CONTEXT:",
    '"""',
    normalizeContext(context),
    '"""',
  ].join("\n");

  const payload = {
    model,
    messages: [
      { role: "system", content: PERSPECTIVE_SYSTEM_PROMPT },
      { role: "user", content: userPrompt },
    ],
    max_tokens: 700,
    temperature: 0.3,
    top_p: 0.9,
    stream: false,
  };

  const response = await fetch(HF_CHAT_COMPLETIONS_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`LLaMA API error ${response.status}: ${errorText}`);
  }

  const data = await response.json();
  const rawText = extractModelText(data);
  const parsed = parseJson(rawText);

  return normalizePerspectivePayload(parsed);
}

const perspectiveService = {
  generatePerspectives,
};

module.exports = {
  perspectiveService,
  generatePerspectives,
};
