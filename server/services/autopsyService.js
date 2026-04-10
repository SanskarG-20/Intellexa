const GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models";

const AUTOPSY_SYSTEM_PROMPT = [
  "You are an AI reasoning analyst.",
  "Analyze the user's question before answering it.",
  "",
  "Return STRICT JSON only with this exact schema:",
  "{",
  '  "assumptions": ["..."],',
  '  "bias_detected": "none | implicit | explicit",',
  '  "missing_angles": ["..."]',
  "}",
  "",
  "Rules:",
  "- assumptions: hidden assumptions in the question",
  "- bias_detected: framing/bias classification",
  "- missing_angles: perspectives not considered",
  "- Keep each field concise and useful",
  "- Do not add extra keys",
].join("\n");

function toStringArray(value) {
  if (!Array.isArray(value)) return [];

  return value
    .map((item) => String(item || "").trim())
    .filter(Boolean);
}

function normalizeAutopsyPayload(payload) {
  const assumptions = toStringArray(payload?.assumptions);
  const missingAngles = toStringArray(payload?.missing_angles);
  const biasDetected = String(payload?.bias_detected || "none").trim().toLowerCase();

  return {
    assumptions,
    bias_detected: biasDetected || "none",
    missing_angles: missingAngles,
  };
}

function extractGeminiText(data) {
  const text = data?.candidates?.[0]?.content?.parts?.[0]?.text;

  if (!text || typeof text !== "string") {
    throw new Error("Gemini returned an unexpected response format.");
  }

  return text.trim();
}

function parseGeminiJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    const firstBrace = text.indexOf("{");
    const lastBrace = text.lastIndexOf("}");

    if (firstBrace === -1 || lastBrace === -1 || lastBrace <= firstBrace) {
      throw new Error("Gemini did not return valid JSON.");
    }

    const candidate = text.slice(firstBrace, lastBrace + 1);
    return JSON.parse(candidate);
  }
}

async function analyzeQuestion(question) {
  if (typeof question !== "string" || !question.trim()) {
    throw new Error("analyzeQuestion(question) requires a non-empty question string.");
  }

  const apiKey = String(process.env.GEMINI_API_KEY || "").trim();
  const model = String(process.env.GEMINI_MODEL || "gemini-2.5-flash").trim();

  if (!apiKey) {
    throw new Error("Missing GEMINI_API_KEY in environment variables.");
  }

  const url = `${GEMINI_API_BASE}/${encodeURIComponent(model)}:generateContent?key=${apiKey}`;

  const body = {
    systemInstruction: {
      parts: [{ text: AUTOPSY_SYSTEM_PROMPT }],
    },
    contents: [
      {
        role: "user",
        parts: [{ text: `USER QUESTION:\n\"\"\"\n${question.trim()}\n\"\"\"` }],
      },
    ],
    generationConfig: {
      temperature: 0.2,
      responseMimeType: "application/json",
    },
  };

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Gemini API error ${response.status}: ${errorText}`);
  }

  const data = await response.json();
  const rawText = extractGeminiText(data);
  const parsed = parseGeminiJson(rawText);

  return normalizeAutopsyPayload(parsed);
}

const autopsyService = {
  analyzeQuestion,
};

module.exports = {
  autopsyService,
  analyzeQuestion,
};
