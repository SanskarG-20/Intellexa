function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

function toFiniteNumber(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }

  return value;
}

function normalizeContextRelevance(value) {
  if (typeof value === "boolean") {
    return value ? 1 : 0;
  }

  const numeric = toFiniteNumber(value);
  if (numeric === null) {
    return 0.5;
  }

  if (numeric >= 0 && numeric <= 1) {
    return numeric;
  }

  if (numeric >= 0 && numeric <= 100) {
    return numeric / 100;
  }

  return clamp(numeric, 0, 1);
}

function normalizeBoolean(value) {
  if (typeof value === "boolean") {
    return value;
  }

  if (typeof value === "string") {
    const normalized = value.trim().toLowerCase();
    return normalized === "true" || normalized === "1" || normalized === "yes";
  }

  if (typeof value === "number") {
    return value === 1;
  }

  return false;
}

function getResponseLength(responseLengthInput, responseText) {
  const numericLength = toFiniteNumber(responseLengthInput);

  if (numericLength !== null) {
    return Math.max(0, Math.round(numericLength));
  }

  if (typeof responseText === "string") {
    return responseText.trim().length;
  }

  return 0;
}

function resolveCompleteness(completenessInput, responseLength) {
  if (typeof completenessInput === "boolean") {
    return completenessInput;
  }

  const numeric = toFiniteNumber(completenessInput);
  if (numeric !== null) {
    const normalized = numeric > 1 ? numeric / 100 : numeric;
    return normalized >= 0.6;
  }

  return responseLength >= 120;
}

function getVaguenessPenalty(responseLength, isComplete) {
  if (!isComplete && responseLength < 60) {
    return 25;
  }

  if (!isComplete) {
    return 20;
  }

  if (responseLength < 80) {
    return 12;
  }

  return 0;
}

function calculateTrustScore(input = {}) {
  const contextRelevance = input.contextRelevance ?? input.context_relevance;
  const biasDetected = input.biasDetected ?? input.bias_detected;
  const responseLengthInput = input.responseLength ?? input.response_length;
  const responseText = input.responseText ?? input.response_text;
  const completenessInput =
    input.completeness ?? input.responseComplete ?? input.response_complete;

  let score = 100;

  if (normalizeBoolean(biasDetected)) {
    score -= 35;
  }

  const contextScore = normalizeContextRelevance(contextRelevance);
  const contextPenalty = Math.round((1 - contextScore) * 30);
  score -= contextPenalty;

  const responseLength = getResponseLength(responseLengthInput, responseText);
  const isComplete = resolveCompleteness(completenessInput, responseLength);
  score -= getVaguenessPenalty(responseLength, isComplete);

  return {
    trust_score: clamp(Math.round(score), 0, 100),
  };
}

const trustService = {
  calculateTrustScore,
};

module.exports = {
  trustService,
  calculateTrustScore,
};
