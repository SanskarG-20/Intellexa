import json
import httpx
from typing import List
from app.core.config import settings

class ExplainService:
    """
    Service responsible for providing step-by-step reasoning 
    for why a specific AI response was generated.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    EXPLAIN_SYSTEM_PROMPT = """You are an explainability engine.

Explain WHY the answer was generated in a clear and structured way.

TASK:
Provide short reasoning steps that justify the answer.

OUTPUT (JSON ONLY):

[
  "Reason 1",
  "Reason 2",
  "Reason 3"
]

GUIDELINES:
- Keep explanations simple and clear
- Focus on logic, not repetition
- Do NOT restate the full answer"""

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def explain_answer(cls, query: str, answer: str) -> List[str]:
        """
        Send the query and answer to Gemini to generate reasoning steps.
        """
        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_explanation(query, answer)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        prompt = f"USER QUERY:\n\"\"\"\n{query}\n\"\"\"\n\nANSWER:\n\"\"\"\n{answer}\n\"\"\""

        payload = {
            "systemInstruction": {
                "parts": [{"text": cls.EXPLAIN_SYSTEM_PROMPT}],
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
                    print(f"Explainability engine error ({response.status_code}): {response.text}")
                    return cls._build_local_explanation(query, answer)
            except Exception as e:
                print(f"Failed to generate explanation: {str(e)}")
                return cls._build_local_explanation(query, answer)

    @staticmethod
    def _build_local_explanation(query: str, answer: str) -> List[str]:
        query_text = " ".join(str(query or "").split()) or "the user's request"
        answer_text = " ".join(str(answer or "").split()) or "the drafted answer"
        return [
            f"The response focuses on the main request in: {query_text}",
            f"It aims to stay concise, relevant, and understandable: {answer_text}",
            "It avoids overcommitting when outside services or extra context are unavailable.",
        ]

explain_service = ExplainService()
