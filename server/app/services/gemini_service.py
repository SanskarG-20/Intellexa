import json
from typing import Optional

import httpx

from app.core.config import settings


class GeminiService:
    """
    Service responsible for interacting with the Google Gemini API to
    generate structured AI-powered analysis.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )
    DEFAULT_FALLBACK_MODEL = "gemini-2.5-flash"
    MIRROR_SYSTEM_PROMPT = """You are "Intellexa Mirror AI", a cognitive analysis engine.

Analyze the user's query BEFORE answering.

TASK:
1. Identify hidden assumptions
2. Detect bias (none / implicit / explicit)
3. Explain the bias (if any)
4. Identify missing perspectives

OUTPUT (JSON ONLY):

{
  "assumptions": ["..."],
  "bias_detected": "none | implicit | explicit",
  "bias_explanation": "...",
  "missing_angles": ["..."]
}

RULES:
- Do NOT answer the question
- Be neutral and analytical
- No extra text outside JSON"""
    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Hidden assumptions or premises in the user's query.",
            },
            "bias_detected": {
                "type": "string",
                "enum": ["none", "implicit", "explicit"],
                "description": "Whether bias is absent, implicit, or explicit.",
            },
            "bias_explanation": {
                "type": "string",
                "description": "Short neutral explanation of the bias, if any.",
            },
            "missing_angles": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Relevant perspectives or angles not covered by the query.",
            },
        },
        "required": [
            "assumptions",
            "bias_detected",
            "bias_explanation",
            "missing_angles",
        ],
        "propertyOrdering": [
            "assumptions",
            "bias_detected",
            "bias_explanation",
            "missing_angles",
        ],
    }

    class AIServiceError(RuntimeError):
        """
        Raised when the upstream AI provider fails in a known way.
        """

        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def get_ai_response(cls, user_message: str) -> str:
        """
        Send a request to the Gemini API with user input and return strict JSON.
        """
        api_key = (settings.GEMINI_API_KEY or "").strip()
        if not api_key or api_key == "your_google_ai_studio_api_key_here":
            raise cls.AIServiceError(
                "Gemini is not configured yet. Add a valid GEMINI_API_KEY to your .env file.",
                status_code=503,
            )

        model_candidates = [settings.GEMINI_MODEL.strip()]
        if cls.DEFAULT_FALLBACK_MODEL not in model_candidates:
            model_candidates.append(cls.DEFAULT_FALLBACK_MODEL)

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            last_error: Optional[GeminiService.AIServiceError] = None

            for model_name in model_candidates:
                payload = {
                    "systemInstruction": {
                        "parts": [{"text": cls.MIRROR_SYSTEM_PROMPT}],
                    },
                    "contents": [
                        {
                            "role": "user",
                            "parts": [{"text": user_message}],
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.2,
                        "topP": 1,
                        "maxOutputTokens": 1024,
                        "responseMimeType": "application/json",
                        "responseJsonSchema": cls.RESPONSE_SCHEMA,
                    },
                }

                try:
                    response = await client.post(
                        cls.GEMINI_API_URL_TEMPLATE.format(model=model_name),
                        json=payload,
                        headers={
                            "Content-Type": "application/json",
                            "x-goog-api-key": api_key,
                        },
                    )
                except httpx.TimeoutException as exc:
                    print(f"Gemini timeout for model {model_name}: {exc}")
                    return cls._build_local_analysis(user_message)
                except httpx.NetworkError as exc:
                    print(f"Gemini network failure for model {model_name}: {exc}")
                    return cls._build_local_analysis(user_message)
                except httpx.HTTPError as exc:
                    print(f"Gemini HTTP error for model {model_name}: {exc}")
                    return cls._build_local_analysis(user_message)

                if response.status_code == 200:
                    try:
                        data = response.json()
                        raw_content = cls._extract_text_content(data)
                        return cls._normalize_analysis_json(raw_content)
                    except (ValueError, KeyError, IndexError, TypeError) as exc:
                        print(f"Gemini returned an unexpected response format: {exc}")
                        return cls._build_local_analysis(user_message)

                provider_message = cls._extract_provider_message(response)
                last_error = cls._build_error(response.status_code, provider_message, model_name)
                print(f"Gemini API Error {response.status_code} ({model_name}): {provider_message}")

                if cls._should_use_local_fallback(response.status_code):
                    return cls._build_local_analysis(user_message)

                if not cls._should_retry_with_fallback(
                    response.status_code, provider_message, model_name
                ):
                    raise last_error

            if last_error:
                raise last_error

            raise cls.AIServiceError("Gemini did not return a usable response.", status_code=502)

    @staticmethod
    def _extract_text_content(data: dict) -> str:
        candidates = data.get("candidates") or []
        if not candidates:
            raise KeyError("Missing candidates in Gemini response.")

        parts = candidates[0]["content"]["parts"]
        text_chunks = [part.get("text", "") for part in parts if isinstance(part, dict)]
        text = "".join(text_chunks).strip()
        if not text:
            raise ValueError("Gemini response contained no text parts.")
        return text

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

    @classmethod
    def _should_retry_with_fallback(cls, status_code: int, provider_message: str, model_name: str) -> bool:
        if model_name == cls.DEFAULT_FALLBACK_MODEL:
            return False

        message = provider_message.lower()
        return status_code in {400, 404} and any(
            term in message for term in {"model", "not found", "unsupported", "permission"}
        )

    @classmethod
    def _build_error(
        cls, status_code: int, provider_message: str, model_name: str
    ) -> "GeminiService.AIServiceError":
        message_lower = provider_message.lower()

        if status_code in {401, 403}:
            return cls.AIServiceError(
                "Gemini rejected the API key. Update GEMINI_API_KEY in your .env file.",
                status_code=502,
            )

        if status_code == 429:
            return cls.AIServiceError(
                "Gemini rate limit or quota reached. Wait a moment or check your Google AI Studio usage.",
                status_code=429,
            )

        if status_code in {400, 404} and any(
            term in message_lower for term in {"model", "not found", "unsupported", "permission"}
        ):
            return cls.AIServiceError(
                f"Gemini could not use model '{model_name}'. Set GEMINI_MODEL to a supported model, "
                f"such as '{cls.DEFAULT_FALLBACK_MODEL}'.",
                status_code=502,
            )

        if status_code >= 500:
            return cls.AIServiceError(
                "Gemini is having a server-side problem right now. Please try again shortly.",
                status_code=502,
            )

        return cls.AIServiceError(
            f"Gemini returned an error: {provider_message}",
            status_code=502,
        )

    @classmethod
    def _normalize_analysis_json(cls, raw_content: str) -> str:
        parsed = cls._parse_json_object(raw_content)
        if not isinstance(parsed, dict):
            raise cls.AIServiceError(
                "Gemini returned a response, but it was not valid JSON.",
                status_code=502,
            )

        normalized = {
            "assumptions": cls._ensure_string_list(parsed.get("assumptions")),
            "bias_detected": cls._normalize_bias_value(parsed.get("bias_detected")),
            "bias_explanation": cls._ensure_string(parsed.get("bias_explanation")),
            "missing_angles": cls._ensure_string_list(parsed.get("missing_angles")),
        }
        return json.dumps(normalized, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json_object(raw_content: str):
        stripped = raw_content.strip()

        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        try:
            return json.loads(stripped[start : end + 1])
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _ensure_string(value) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _ensure_string_list(cls, value) -> list[str]:
        if isinstance(value, list):
            items = []
            for item in value:
                text = cls._ensure_string(item)
                if text:
                    items.append(text)
            return items

        if value is None:
            return []

        text = cls._ensure_string(value)
        return [text] if text else []

    @staticmethod
    def _normalize_bias_value(value) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"none", "implicit", "explicit"}:
            return normalized
        return "none"

    @staticmethod
    def _should_use_local_fallback(status_code: int) -> bool:
        return status_code in {408, 409, 425, 429, 500, 502, 503, 504}

    @classmethod
    def _build_local_analysis(cls, user_message: str) -> str:
        text = cls._ensure_string(user_message)
        lower_text = text.lower()

        assumptions: list[str] = []
        missing_angles: list[str] = []
        bias_detected = "none"
        bias_explanation = ""

        if any(word in lower_text for word in {"he", "she", "him", "her", "man", "woman", "lady", "girl", "boy"}):
            assumptions.append("The people mentioned are being compared as if gender is relevant to the judgment.")
            missing_angles.append("Whether the situations are actually comparable aside from the people involved.")

        if any(phrase in lower_text for phrase in {"same", "too", "also", "similar"}):
            assumptions.append("The query assumes the two events are materially similar enough to warrant the same response.")

        if any(phrase in lower_text for phrase in {"last night", "today", "yesterday", "recently"}):
            assumptions.append("The query assumes limited recent observations provide enough context for comparison.")
            missing_angles.append("Timeline details, legal context, and whether both cases were documented in the same way.")

        if "punish" in lower_text or "punished" in lower_text:
            assumptions.append("The query assumes punishment is the main or appropriate frame for evaluating the incident.")
            missing_angles.append("Due process, evidence quality, intent, and any institutional or legal procedure involved.")

        if any(word in lower_text for word in {"she", "her", "lady", "woman", "girl"}) and any(
            word in lower_text for word in {"he", "him", "man", "boy"}
        ):
            bias_detected = "implicit"
            bias_explanation = (
                "The query frames the comparison through gender categories, which can introduce an implicit bias "
                "if gender is treated as relevant before the facts of the cases are established."
            )

        if not assumptions:
            assumptions.append("The query assumes there is enough context to evaluate the issue without more factual detail.")

        if not missing_angles:
            missing_angles.extend(
                [
                    "The broader factual context behind the event.",
                    "How different stakeholders might interpret the situation.",
                ]
            )

        normalized = {
            "assumptions": assumptions,
            "bias_detected": bias_detected,
            "bias_explanation": bias_explanation,
            "missing_angles": missing_angles,
        }
        return json.dumps(normalized, ensure_ascii=False, indent=2)


gemini_service = GeminiService()
