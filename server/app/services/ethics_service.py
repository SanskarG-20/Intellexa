import json
from typing import Any, Dict

import httpx

from app.core.config import settings


class EthicsService:
    """
    Lightweight service for checking generated content for bias and harmful risk.
    Uses Gemini when available and falls back to local heuristics.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    ETHICAL_SYSTEM_PROMPT = """You are an AI safety checker.

Given a user query and generated response, detect:
1) bias
2) harmful content

Return JSON only with this shape:
{
  "bias_detected": true,
  "harmful_content": false,
  "risk_level": "low | medium | high",
  "action_taken": "none | flagged | needs_revision"
}

Rules:
- Keep output concise
- risk_level must reflect both bias and harmful content
- If harmful content is present, risk_level cannot be low
- Do not add extra keys"""

    _RISK_ORDER = {"low": 1, "medium": 2, "high": 3}

    _HARMFUL_KEYWORDS = (
        "kill",
        "murder",
        "suicide",
        "self-harm",
        "bomb",
        "terror",
        "rape",
        "lynch",
        "ethnic cleansing",
    )

    _BIAS_KEYWORDS = (
        "inferior",
        "superior",
        "those people",
        "all women",
        "all men",
        "all immigrants",
        "all muslims",
        "all christians",
        "all jews",
        "all blacks",
        "all whites",
        "subhuman",
    )

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def get_ethical_perspectives(
        cls,
        generated_response: str,
        user_query: str,
    ) -> Dict[str, Any]:
        """
        Evaluate generated content for bias and harmful risk.

        Output schema:
        {
          "bias_detected": bool,
          "risk_level": "low" | "medium" | "high",
          "action_taken": str
        }
        """
        response_text = cls._normalize_text(generated_response)
        query_text = cls._normalize_text(user_query)

        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_assessment(response_text, query_text)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        prompt = (
            f"USER QUERY:\n\"\"\"\n{query_text}\n\"\"\"\n\n"
            f"GENERATED RESPONSE:\n\"\"\"\n{response_text}\n\"\"\""
        )

        payload = {
            "systemInstruction": {
                "parts": [{"text": cls.ETHICAL_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json",
            },
        }

        timeout = httpx.Timeout(20.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{url}?key={api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                if response.status_code == 200:
                    data = response.json()
                    raw_content = cls._extract_gemini_text(data)
                    parsed = cls._parse_json_payload(raw_content)
                    return cls._normalize_assessment(parsed, response_text, query_text)

                provider_msg = cls._extract_provider_message(response)
                print(f"Ethical engine error ({response.status_code}): {provider_msg}")

                if cls._should_use_local_fallback(response.status_code):
                    return cls._build_local_assessment(response_text, query_text)

                raise cls.AIServiceError(
                    f"Ethical engine error ({response.status_code}): {provider_msg}",
                    status_code=response.status_code,
                )
            except cls.AIServiceError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                print(f"Failed to evaluate ethics with Gemini: {exc}")
                return cls._build_local_assessment(response_text, query_text)
            except Exception as exc:
                raise cls.AIServiceError(f"Failed to evaluate ethics: {str(exc)}")

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value or "").split())

    @classmethod
    def _extract_gemini_text(cls, data: Dict[str, Any]) -> str:
        text = (
            data.get("candidates", [{}])[0]
            .get("content", {})
            .get("parts", [{}])[0]
            .get("text", "")
        )
        if not isinstance(text, str) or not text.strip():
            raise cls.AIServiceError("Gemini returned an unexpected response format.")
        return text.strip()

    @classmethod
    def _parse_json_payload(cls, raw_content: str) -> Dict[str, Any]:
        try:
            return json.loads(raw_content)
        except json.JSONDecodeError:
            first_brace = raw_content.find("{")
            last_brace = raw_content.rfind("}")
            if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
                raise cls.AIServiceError("Gemini did not return valid JSON.")
            return json.loads(raw_content[first_brace : last_brace + 1])

    @classmethod
    def _normalize_assessment(
        cls,
        payload: Dict[str, Any],
        generated_response: str,
        user_query: str,
    ) -> Dict[str, Any]:
        local = cls._build_local_assessment(generated_response, user_query)

        bias_detected = bool(payload.get("bias_detected", False)) or bool(local["bias_detected"])
        harmful_content = bool(payload.get("harmful_content", False))

        risk_level = str(payload.get("risk_level", "")).strip().lower()
        if risk_level not in cls._RISK_ORDER:
            risk_level = cls._derive_risk_level(bias_detected, harmful_content)

        if harmful_content and risk_level == "low":
            risk_level = "high"

        risk_level = cls._max_risk(risk_level, str(local["risk_level"]))

        action_taken = str(payload.get("action_taken", "")).strip()
        if not action_taken:
            action_taken = cls._default_action(risk_level, bias_detected)

        return {
            "bias_detected": bias_detected,
            "risk_level": risk_level,
            "action_taken": action_taken,
        }

    @classmethod
    def _derive_risk_level(cls, bias_detected: bool, harmful_content: bool) -> str:
        if harmful_content:
            return "high"
        if bias_detected:
            return "medium"
        return "low"

    @classmethod
    def _max_risk(cls, risk_a: str, risk_b: str) -> str:
        score_a = cls._RISK_ORDER.get(str(risk_a).strip().lower(), 1)
        score_b = cls._RISK_ORDER.get(str(risk_b).strip().lower(), 1)
        max_score = max(score_a, score_b)
        for label, score in cls._RISK_ORDER.items():
            if score == max_score:
                return label
        return "low"

    @classmethod
    def _default_action(cls, risk_level: str, bias_detected: bool) -> str:
        if risk_level == "high":
            return "flagged_and_needs_revision"
        if risk_level == "medium" or bias_detected:
            return "flagged"
        return "none"

    @staticmethod
    def _extract_provider_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            return response.text.strip() or "Unknown Gemini error."

        error_payload = data.get("error")
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            if message:
                return str(message)

        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()

        return response.text.strip() or "Unknown Gemini error."

    @staticmethod
    def _should_use_local_fallback(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    @classmethod
    def _build_local_assessment(cls, generated_response: str, user_query: str) -> Dict[str, Any]:
        combined_text = f"{user_query} {generated_response}".lower()

        harmful_detected = any(keyword in combined_text for keyword in cls._HARMFUL_KEYWORDS)
        bias_detected = any(keyword in combined_text for keyword in cls._BIAS_KEYWORDS)

        risk_level = cls._derive_risk_level(bias_detected, harmful_detected)

        return {
            "bias_detected": bias_detected,
            "risk_level": risk_level,
            "action_taken": cls._default_action(risk_level, bias_detected),
        }


ethics_service = EthicsService()
