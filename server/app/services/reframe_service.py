"""
reframe_service.py — Bias Detection and Neutral Reframing Engine

Analyzes user queries for bias, assumptions, and one-sided framing,
then generates 3 neutral, balanced reformulations of the original question.
"""
import json
import httpx
from typing import Dict, Any, List
from app.core.config import settings


class ReframeService:
    """
    Service that detects bias in user queries and rewrites them as
    3 neutral, balanced, logically equivalent questions.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    REFRAME_SYSTEM_PROMPT = """You are a bias detection and neutral reframing engine.

Your task is to analyze the user query and detect any bias, assumptions, or one-sided framing.
Then, rewrite the query into 3 unbiased, neutral, and logically equivalent questions.

TASK:
1. Identify whether the query contains bias or assumptions.
2. Remove bias, emotional framing, or leading language.
3. Generate 3 alternative neutral questions that:
   - Preserve meaning
   - Are balanced and non-judgmental
   - Consider different neutral perspectives

OUTPUT FORMAT (STRICT JSON ONLY):
{
  "bias_detected": "none | implicit | explicit",
  "neutral_questions": [
    "question 1",
    "question 2",
    "question 3"
  ]
}

RULES:
- Do NOT answer the question
- Do NOT explain reasoning outside JSON
- Do NOT include extra fields
- Do NOT keep emotional or leading wording
- All questions must be neutral and factual in tone
- If no bias exists, still generate 3 neutral reformulations"""

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def reframe_query(cls, query: str) -> Dict[str, Any]:
        """
        Sends the user query to Gemini for bias detection and neutral reframing.
        Falls back to a local heuristic version if Gemini is unavailable.
        """
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_reframe(query)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        payload = {
            "systemInstruction": {
                "parts": [{"text": cls.REFRAME_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": f'USER QUERY:\n"""\n{query}\n"""'}],
                }
            ],
            "generationConfig": {
                "temperature": 0.3,
                "responseMimeType": "application/json",
            },
        }

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{url}?key={api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    raw_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    result = json.loads(raw_content)
                    # Validate schema
                    if "bias_detected" in result and "neutral_questions" in result:
                        return result

                provider_msg = response.text
                try:
                    provider_msg = response.json().get("error", {}).get("message", provider_msg)
                except Exception:
                    pass
                print(f"[ReframeService] Gemini error ({response.status_code}): {provider_msg}")
                return cls._build_local_reframe(query)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                print(f"[ReframeService] Network error: {exc}")
                return cls._build_local_reframe(query)
            except Exception as exc:
                print(f"[ReframeService] Unexpected error: {exc}")
                return cls._build_local_reframe(query)

    @staticmethod
    def _build_local_reframe(query: str) -> Dict[str, Any]:
        """
        Lightweight fallback that generates neutral reframings without Gemini.
        Uses basic text transformation patterns.
        """
        text = " ".join(str(query or "").split())
        lower = text.lower()

        # Detect bias level using simple heuristics
        EXPLICIT_BIAS_SIGNALS = [
            "always", "never", "all men", "all women", "obviously", "clearly",
            "everyone knows", "stupid", "idiots", "inferior", "superior"
        ]
        IMPLICIT_BIAS_SIGNALS = [
            "better than", "worse than", "why do they", "why can't they",
            "should be", "must be", "it's a fact"
        ]

        if any(sig in lower for sig in EXPLICIT_BIAS_SIGNALS):
            bias_level = "explicit"
        elif any(sig in lower for sig in IMPLICIT_BIAS_SIGNALS):
            bias_level = "implicit"
        else:
            bias_level = "none"

        # Generate 3 neutral reformulations
        return {
            "bias_detected": bias_level,
            "neutral_questions": [
                f"What are the different perspectives on: {text}",
                f"What does current research or evidence suggest about: {text}",
                f"What factors or context are relevant when examining: {text}",
            ],
        }


reframe_service = ReframeService()
