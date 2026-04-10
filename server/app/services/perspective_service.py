import json
from typing import Dict

from app.services.llama_service import LlamaService, llama_service


class PerspectiveService:
    """
    Service responsible for generating multi-perspective answers.
    Uses LLaMA with a strict JSON prompt and falls back to deterministic templates.
    """

    SYSTEM_PROMPT = """You are an ethical reasoning assistant.

Generate three concise perspectives from the provided material.

Return JSON only with this exact schema:
{
  "utilitarian": "...",
  "rights_based": "...",
  "care_ethics": "..."
}

Rules:
- utilitarian: focus on outcomes and collective wellbeing
- rights_based: focus on rights, duties, fairness
- care_ethics: focus on empathy, relationships, vulnerability
- Keep each field practical and distinct
- Do not add extra keys"""

    @classmethod
    async def generate_perspectives(
        cls,
        user_query: str,
        context: str,
        base_answer: str,
    ) -> Dict[str, str]:
        prompt = (
            f"USER QUERY:\n\"\"\"\n{(user_query or '').strip()}\n\"\"\"\n\n"
            f"CONTEXT:\n\"\"\"\n{(context or '').strip() or 'No prior context.'}\n\"\"\"\n\n"
            f"BASE ANSWER:\n\"\"\"\n{(base_answer or '').strip()}\n\"\"\""
        )

        try:
            raw = await llama_service.get_ai_response(prompt, system_prompt=cls.SYSTEM_PROMPT)
            parsed = cls._parse_json_payload(raw)
            return cls._normalize(parsed, base_answer)
        except (LlamaService.AIServiceError, ValueError, json.JSONDecodeError):
            return cls._build_local_perspectives(base_answer)

    @staticmethod
    def _parse_json_payload(raw: str) -> Dict[str, str]:
        text = str(raw or "").strip()
        if not text:
            raise ValueError("Empty LLaMA perspective response.")

        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            first_brace = text.find("{")
            last_brace = text.rfind("}")
            if first_brace == -1 or last_brace == -1 or last_brace <= first_brace:
                raise
            payload = json.loads(text[first_brace : last_brace + 1])

        if not isinstance(payload, dict):
            raise ValueError("Perspective response is not an object.")

        return payload

    @staticmethod
    def _normalize(payload: Dict[str, str], base_answer: str) -> Dict[str, str]:
        normalized = {
            "utilitarian": str(payload.get("utilitarian", "")).strip(),
            "rights_based": str(payload.get("rights_based", "")).strip(),
            "care_ethics": str(payload.get("care_ethics", "")).strip(),
        }

        if all(normalized.values()):
            return normalized

        fallback = PerspectiveService._build_local_perspectives(base_answer)
        for key, value in normalized.items():
            if not value:
                normalized[key] = fallback[key]

        return normalized

    @staticmethod
    def _build_local_perspectives(base_answer: str) -> Dict[str, str]:
        answer = " ".join(str(base_answer or "").split())
        if not answer:
            answer = "No answer was available to expand."

        return {
            "utilitarian": (
                "Utilitarian view: prefer the option that creates the most overall benefit "
                f"and the least overall harm. Base answer: {answer}"
            ),
            "rights_based": (
                "Rights-based view: ensure individual rights, consent, and fairness are preserved "
                f"while applying the recommendation. Base answer: {answer}"
            ),
            "care_ethics": (
                "Care ethics view: prioritize empathy, relationships, and the impact on vulnerable "
                f"people when applying this response. Base answer: {answer}"
            ),
        }


perspective_service = PerspectiveService()
