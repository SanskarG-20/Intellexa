import json
from typing import Dict

import httpx

from app.core.config import settings

class EthicsService:
    """
    Service responsible for transforming an AI response into 
    multiple ethical perspectives using Gemini.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    ETHICAL_SYSTEM_PROMPT = """You are an ethical reasoning engine.

Transform the given answer into three ethical perspectives:

1. Utilitarian → focus on outcomes and overall benefit
2. Rights-based → focus on individual rights and fairness
3. Care ethics → focus on empathy, relationships, and impact on vulnerable groups

OUTPUT (JSON ONLY):

{
  "utilitarian": "...",
  "rights_based": "...",
  "care_ethics": "..."
}

RULES:
- Keep each perspective clear and distinct
- Do NOT repeat the same idea in all three
- Do NOT add extra fields"""

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def get_ethical_perspectives(cls, base_answer: str) -> Dict[str, str]:
        """
        Send the base answer to Gemini to be analyzed from ethical perspectives.
        """
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_perspectives(base_answer)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        prompt = f"BASE ANSWER:\n\"\"\"\n{base_answer}\n\"\"\""

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
                "temperature": 0.4,
                "responseMimeType": "application/json",
            },
        }

        timeout = httpx.Timeout(30.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{url}?key={api_key}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    raw_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(raw_content)

                provider_msg = cls._extract_provider_message(response)
                print(f"Ethical engine error ({response.status_code}): {provider_msg}")

                if cls._should_use_local_fallback(response.status_code):
                    return cls._build_local_perspectives(base_answer)

                raise cls.AIServiceError(
                    f"Ethical engine error ({response.status_code}): {provider_msg}",
                    status_code=response.status_code,
                )
            except cls.AIServiceError:
                raise
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                print(f"Failed to generate ethical perspectives with Gemini: {exc}")
                return cls._build_local_perspectives(base_answer)
            except Exception as exc:
                raise cls.AIServiceError(f"Failed to generate ethical perspectives: {str(exc)}")

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

    @staticmethod
    def _build_local_perspectives(base_answer: str) -> Dict[str, str]:
        answer = " ".join(str(base_answer or "").split())
        if not answer:
            answer = "No answer was available to analyze."

        return {
            "utilitarian": (
                f"From a utilitarian view, this response should be judged by whether it leads to "
                f"helpful outcomes, reduces harm, and improves understanding: {answer}"
            ),
            "rights_based": (
                f"From a rights-based view, the response should respect dignity, fairness, privacy, "
                f"and each person's autonomy while making its point: {answer}"
            ),
            "care_ethics": (
                f"From a care ethics view, the response should show empathy, account for context, "
                f"and consider how vulnerable people may be affected: {answer}"
            ),
        }

ethics_service = EthicsService()
