import json
import httpx
from typing import Dict, Any
from app.core.config import settings

class AutopsyService:
    """
    Service responsible for performing a "Perspective Autopsy" on the user's query.
    Analyzes hidden assumptions, biases, and missing perspectives before responding.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    AUTOPSY_SYSTEM_PROMPT = """You are "Intellexa Mirror AI", a pre-response cognitive analysis engine.
    Your role is to analyze HOW the user is thinking and determine if external data is required.
    Knowledge Cutoff: 2023.

    TASK:
    1. Identify hidden assumptions.
    2. Detect bias (none | implicit | explicit).
    3. Identify missing perspectives.
    4. Determine if the query requires real-time knowledge or 2024+ information.

    OUTPUT (JSON ONLY):
    {
      "assumptions": ["..."],
      "bias_detected": "none | implicit | explicit",
      "bias_explanation": "...",
      "missing_angles": ["..."],
      "needs_search": true | false
    }

    RULES:
    - needs_search is true IF the query involves events after 2023, live scores, current stock prices, or recent world news.
    - Keep output concise."""

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def perform_autopsy(cls, query: str) -> Dict[str, Any]:
        """
        Send the user query to Gemini for a Perspective Autopsy.
        """
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_autopsy(query)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        prompt = f"USER QUERY:\n\"\"\"\n{query}\n\"\"\""

        payload = {
            "systemInstruction": {
                "parts": [{"text": cls.AUTOPSY_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
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
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    raw_content = data["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(raw_content)
                else:
                    provider_msg = response.text
                    try:
                        provider_msg = response.json().get("error", {}).get("message", provider_msg)
                    except:
                        pass
                    print(f"Autopsy engine error ({response.status_code}): {provider_msg}")
                    return cls._build_local_autopsy(query)
            except Exception as e:
                print(f"Failed to perform Perspective Autopsy: {str(e)}")
                return cls._build_local_autopsy(query)

    @staticmethod
    def _build_local_autopsy(query: str) -> Dict[str, Any]:
        text = " ".join(str(query or "").split())
        lower_text = text.lower()

        assumptions = [
            "The query assumes there is enough context to judge the issue without more facts."
        ]
        missing_angles = [
            "Relevant evidence, background, and context that may change the conclusion.",
            "How different people affected by the issue might see it differently.",
        ]
        bias_detected = "none"
        bias_explanation = "No significant bias detected."

        if any(word in lower_text for word in {"man", "men", "woman", "women", "girl", "boy"}):
            assumptions.append("The query treats gender as relevant before establishing why it should be.")
            missing_angles.append("Whether the comparison relies on stereotypes instead of evidence.")

        if any(word in lower_text for word in {"man", "men"}) and any(
            word in lower_text for word in {"woman", "women"}
        ):
            bias_detected = "implicit"
            bias_explanation = (
                "The wording compares people through gender categories, which can introduce bias "
                "if the conclusion is not supported by evidence."
            )

        # Detect if the query requires real-time/post-2023 knowledge
        TEMPORAL_SIGNALS = [
            "2024", "2025", "2026", "today", "now", "current", "latest",
            "recent", "yesterday", "this year", "last year", "won", "winner",
            "score", "result", "news", "update", "happened", "election",
            "released", "launched", "announced"
        ]
        needs_search = any(signal in lower_text for signal in TEMPORAL_SIGNALS)

        return {
            "assumptions": assumptions,
            "bias_detected": bias_detected,
            "bias_explanation": bias_explanation,
            "missing_angles": missing_angles,
            "needs_search": needs_search,
        }

autopsy_service = AutopsyService()
