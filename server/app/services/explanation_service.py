from typing import Any, Dict, List


class ExplanationService:
    """
    Service responsible for generating concise explanation bullets
    from the pipeline artifacts.
    """

    @classmethod
    async def generate_explanation(
        cls,
        user_query: str,
        perspective_answer: Dict[str, str],
        ethical_check: Dict[str, Any],
        perspective_autopsy: Dict[str, Any],
        context: str,
    ) -> List[str]:
        bullets: List[str] = []

        query = " ".join(str(user_query or "").split())
        has_context = bool(str(context or "").strip())
        bias_flag = bool((ethical_check or {}).get("bias_detected", False))
        risk_level = str((ethical_check or {}).get("risk_level", "low")).strip().lower() or "low"
        assumptions = (perspective_autopsy or {}).get("assumptions", [])
        missing_angles = (perspective_autopsy or {}).get("missing_angles", [])

        bullets.append(
            "The response combines utilitarian, rights-based, and care-ethics reasoning so the"
            " recommendation is not based on a single value system."
        )

        if has_context:
            bullets.append(
                "Recent conversation context was included to improve relevance and continuity with"
                " prior exchanges."
            )
        else:
            bullets.append(
                "No prior conversation context was available, so the response relied mainly on the"
                " current query."
            )

        if assumptions:
            bullets.append(
                "The autopsy step identified assumptions in the query and those assumptions were"
                " considered before composing the final answer."
            )

        if missing_angles:
            bullets.append(
                "Missing perspectives identified during autopsy were incorporated to reduce"
                " one-sided reasoning."
            )

        if bias_flag:
            bullets.append(
                f"The ethical check flagged possible bias with {risk_level} risk, so the output was"
                " framed more cautiously."
            )
        else:
            bullets.append(
                f"The ethical check did not flag bias and rated risk as {risk_level}, indicating lower"
                " safety concern for this response."
            )

        if query:
            bullets.append("The explanation is directly tied to your query and the generated multi-perspective answer.")

        return bullets[:6]


explanation_service = ExplanationService()
