from typing import Any, Dict, Iterable


class TrustService:
    """
    Deterministic trust scoring utility.

    Inputs:
    - context relevance (bool or numeric)
    - bias_detected (bool)
    - response length/completeness
    """

    @classmethod
    def calculate_trust_score(
        cls,
        context_relevance: Any,
        bias_detected: bool,
        response_text: str,
        explanation: Iterable[str] | None = None,
    ) -> Dict[str, int]:
        score = 100

        context_score = cls._normalize_context_relevance(context_relevance)
        context_penalty = round((1 - context_score) * 30)
        score -= context_penalty

        if bool(bias_detected):
            score -= 35

        response_length = len(str(response_text or "").strip())
        is_complete = cls._is_complete_response(response_length, explanation)
        score -= cls._vagueness_penalty(response_length, is_complete)

        return {"trust_score": max(0, min(100, int(round(score))))}

    @staticmethod
    def _normalize_context_relevance(value: Any) -> float:
        if isinstance(value, bool):
            return 1.0 if value else 0.0

        try:
            numeric = float(value)
        except (TypeError, ValueError):
            return 0.5

        if 0 <= numeric <= 1:
            return numeric
        if 0 <= numeric <= 100:
            return numeric / 100

        return max(0.0, min(1.0, numeric))

    @staticmethod
    def _is_complete_response(response_length: int, explanation: Iterable[str] | None) -> bool:
        if response_length >= 120:
            return True

        if not explanation:
            return False

        items = [str(item).strip() for item in explanation if str(item).strip()]
        return len(items) >= 3 and response_length >= 80

    @staticmethod
    def _vagueness_penalty(response_length: int, is_complete: bool) -> int:
        if not is_complete and response_length < 60:
            return 25
        if not is_complete:
            return 20
        if response_length < 80:
            return 12
        return 0

    @classmethod
    async def evaluate_trust(cls, autopsy: Dict[str, Any], ethics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compatibility wrapper retained for older orchestrators.
        """
        bias_detected = bool((ethics or {}).get("bias_detected", False))
        score_payload = cls.calculate_trust_score(
            context_relevance=0.5,
            bias_detected=bias_detected,
            response_text="",
            explanation=[],
        )
        score = int(score_payload.get("trust_score", 0))

        if score >= 80:
            confidence = "high"
        elif score >= 55:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "trust_score": score,
            "confidence": confidence,
            "justification": "Computed from deterministic local trust rules.",
        }

trust_service = TrustService()
