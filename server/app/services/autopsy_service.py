import json
import httpx
from typing import Dict, Any, Optional
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

Your role is to analyze HOW the user is thinking, not to answer the question.

You must perform a "Perspective Autopsy" on the user's query.

--------------------------------------------------

TASK:

1. Identify hidden assumptions  
   - What is the user implicitly assuming to be true?

2. Detect bias  
   - Classify as:
     - "none" → no bias
     - "implicit" → subtle/generalized bias
     - "explicit" → strong or direct bias

3. Explain the bias (if any)  
   - If no bias, return: "No significant bias detected"

4. Identify missing perspectives  
   - What important viewpoints are ignored?

--------------------------------------------------

OUTPUT FORMAT (STRICT JSON ONLY):

{
  "assumptions": [
    "..."
  ],
  "bias_detected": "none | implicit | explicit",
  "bias_explanation": "...",
  "missing_angles": [
    "..."
  ]
}

--------------------------------------------------

GUIDELINES:

- assumptions:
  Extract unstated beliefs, generalizations, or cause-effect assumptions

- bias_detected:
  Use "implicit" if bias is subtle or indirect
  Use "explicit" if bias is strong, direct, or discriminatory

- missing_angles:
  Consider:
    - social factors
    - economic context
    - cultural differences
    - individual variation
    - alternative explanations

--------------------------------------------------

STRICT RULES:

- DO NOT answer the question
- DO NOT suggest solutions
- DO NOT judge or criticize the user
- DO NOT add extra fields
- DO NOT output anything outside JSON
- Keep output concise but insightful"""

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
            return {"error": "Gemini API key not configured."}

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

        async with httpx.AsyncClient(timeout=30.0) as client:
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
                    return {}
            except Exception as e:
                print(f"Failed to perform Perspective Autopsy: {str(e)}")
                return {}

autopsy_service = AutopsyService()
