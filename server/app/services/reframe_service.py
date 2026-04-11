"""
reframe_service.py — Query Reframing (Wow Mode)

Conditionally rewrites user queries into clearer, neutral, and more
analytical versions before answer generation.
"""

import json
import re
from typing import Any, Dict

import httpx

from app.core.config import settings


class ReframeService:
    """
    Service that conditionally reframes user questions when bias,
    strong assumptions, or vagueness are detected.
    """

    GEMINI_API_URL_TEMPLATE = (
        "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    )

    REFRAME_SYSTEM_PROMPT = """You are Intellexa Query Reframer.

Rewrite the user's question into a clearer, unbiased, and analytical version.

GOAL:
- Preserve the original intent
- Remove loaded or biased framing
- Improve precision and scope
- Keep wording neutral and evidence-oriented

OUTPUT JSON ONLY:
{
  "reframed_query": "..."
}

RULES:
- Return a single reframed question
- Do not answer the question
- Do not add explanations outside JSON
- Keep it concise and natural
"""

    VAGUE_PATTERNS = [
        re.compile(r"\bsuggest\s+(a|some)?\s*career\b", re.IGNORECASE),
        re.compile(r"\bwhat\s+should\s+i\s+do\b", re.IGNORECASE),
        re.compile(r"\bany\s+advice\b", re.IGNORECASE),
        re.compile(r"\bhelp\s+me\s+(decide|choose|pick)\b", re.IGNORECASE),
        re.compile(r"\btell\s+me\s+about\b", re.IGNORECASE),
    ]

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    def should_reframe(cls, query: str, autopsy_result: Dict[str, Any] | None) -> bool:
        text = " ".join(str(query or "").split())
        if not text:
            return False

        source = autopsy_result if isinstance(autopsy_result, dict) else {}
        bias_detected = str(source.get("bias_detected", "none")).strip().lower()
        assumptions = source.get("assumptions", [])

        if not isinstance(assumptions, list):
            assumptions = []

        strong_assumptions = [item for item in assumptions if str(item).strip()]
        has_bias = bias_detected in {"implicit", "explicit"}
        has_strong_assumptions = len(strong_assumptions) >= 2
        is_vague = cls._is_vague_query(text)

        return has_bias or has_strong_assumptions or is_vague

    @classmethod
    async def reframe_query(
        cls, query: str, autopsy_result: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Conditionally reframe the query.
        Returns: {"reframed_query": string}
        """
        original = " ".join(str(query or "").split())
        if not original:
            return {"reframed_query": ""}

        if not cls.should_reframe(original, autopsy_result):
            return {"reframed_query": ""}

        api_key = settings.GEMINI_API_KEY.strip()
        if not api_key:
            return cls._build_local_reframe(original)

        model = settings.GEMINI_MODEL.strip()
        url = cls.GEMINI_API_URL_TEMPLATE.format(model=model)

        autopsy_payload = autopsy_result if isinstance(autopsy_result, dict) else {}
        payload = {
            "systemInstruction": {
                "parts": [{"text": cls.REFRAME_SYSTEM_PROMPT}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": (
                                f'USER QUERY:\n"""\n{original}\n"""\n\n'
                                f"AUTOPSY SIGNALS:\n{json.dumps(autopsy_payload, ensure_ascii=False)}"
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.25,
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
                    parsed = json.loads(raw_content)
                    candidate = cls._sanitize_reframe_result(parsed, original)
                    if candidate:
                        return {"reframed_query": candidate}

                provider_msg = response.text
                try:
                    provider_msg = response.json().get("error", {}).get("message", provider_msg)
                except Exception:
                    pass
                print(f"[ReframeService] Gemini error ({response.status_code}): {provider_msg}")
                return cls._build_local_reframe(original)

            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                print(f"[ReframeService] Network error: {exc}")
                return cls._build_local_reframe(original)
            except Exception as exc:
                print(f"[ReframeService] Unexpected error: {exc}")
                return cls._build_local_reframe(original)

    @classmethod
    async def reframeQuery(
        cls, query: str, autopsyResult: Dict[str, Any] | None = None
    ) -> Dict[str, Any]:
        """
        Legacy camelCase alias for compatibility with earlier interface naming.
        """
        return await cls.reframe_query(query, autopsyResult)

    @classmethod
    def _is_vague_query(cls, query: str) -> bool:
        text = " ".join(str(query or "").split())
        lower = text.lower()
        tokens = re.findall(r"[a-z0-9']+", lower)

        if not tokens:
            return False

        if len(tokens) <= 3 and any(
            term in lower for term in {"career", "advice", "plan", "strategy", "choose", "help"}
        ):
            return True

        return any(pattern.search(text) for pattern in cls.VAGUE_PATTERNS)

    @staticmethod
    def _sanitize_reframe_result(result: Dict[str, Any], original_query: str) -> str:
        if not isinstance(result, dict):
            return ""

        candidate = str(result.get("reframed_query", "")).strip()
        if not candidate:
            return ""

        original_norm = re.sub(r"\s+", " ", original_query).strip(" ?!.\t\n\r").lower()
        candidate_norm = re.sub(r"\s+", " ", candidate).strip(" ?!.\t\n\r").lower()

        if not candidate_norm or candidate_norm == original_norm:
            return ""

        if not candidate.endswith("?"):
            candidate = f"{candidate.rstrip('.')}?"

        return candidate

    @classmethod
    def _build_local_reframe(cls, query: str) -> Dict[str, Any]:
        text = " ".join(str(query or "").split())
        lower = text.lower()

        poor_productivity_match = re.match(
            r"^why\s+are\s+poor\s+people\s+less\s+productive\??$", lower
        )
        if poor_productivity_match:
            return {
                "reframed_query": (
                    "What economic, social, and structural factors influence productivity across income groups?"
                )
            }

        reframed = (
            "What evidence-based factors and broader context should be considered when evaluating: "
            f"{text.rstrip('?').strip()}?"
        )

        return {"reframed_query": reframed}


reframe_service = ReframeService()
