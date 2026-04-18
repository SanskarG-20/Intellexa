import json
import re
from typing import Any, Dict, List, Optional

from app.services.llama_service import llama_service


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

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _normalize_list(values: Any, *, max_items: int) -> List[str]:
        if not isinstance(values, list):
            return []

        normalized: List[str] = []
        seen = set()
        for item in values:
            text = ExplanationService._normalize_text(str(item or ""))
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
            if len(normalized) >= max_items:
                break

        return normalized

    @staticmethod
    def _extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
        text = str(raw_text or "").strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            return None

        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @classmethod
    def _build_learning_mode_fallback(
        cls,
        code_snippet: str,
        language: str,
        user_prompt: str,
    ) -> Dict[str, Any]:
        lines = [line for line in str(code_snippet or "").splitlines() if line.strip()]
        line_count = len(lines)
        language_name = cls._normalize_text(language) or "code"
        prompt_text = cls._normalize_text(user_prompt)

        step_by_step: List[str] = [
            f"First, identify the primary intent of this {language_name} snippet and its inputs.",
            "Next, track execution flow from top to bottom and note branch conditions.",
            "Then, observe how intermediate values are transformed before final output.",
            "Finally, verify outputs and side effects to confirm the snippet's practical behavior.",
        ]

        logic_breakdown: List[str] = [
            f"Structure: {line_count} non-empty lines are organized into sequential logic blocks.",
        ]

        lower_code = str(code_snippet or "").lower()
        if any(token in lower_code for token in ["if ", "elif", "else", "switch", "case "]):
            logic_breakdown.append("Decision logic: control-flow branches choose different paths based on conditions.")
        if any(token in lower_code for token in ["for ", "while ", "for(", ".map(", ".filter(", ".reduce("]):
            logic_breakdown.append("Iteration logic: repeated operations process collections or repeated states.")
        if any(token in lower_code for token in ["def ", "function ", "=>", "class "]):
            logic_breakdown.append("Abstraction logic: named units encapsulate behavior to keep the code reusable.")
        if any(token in lower_code for token in ["return", "yield", "print(", "console.log("]):
            logic_breakdown.append("Output logic: the snippet emits or returns computed results for downstream use.")

        if prompt_text:
            step_by_step.insert(
                1,
                f"Apply the user focus ('{prompt_text}') while reading each block to connect code to intent.",
            )

        real_world_analogy = (
            "Think of this code like an assembly station: raw inputs enter, each step modifies the workpiece, "
            "decision checks route it through different lanes, and the finished result exits at the end."
        )

        overview = (
            f"This {language_name} snippet can be understood as a sequence of operations that transform inputs "
            "into outputs through explicit control flow and reusable logic blocks."
        )

        return {
            "overview": overview,
            "step_by_step": step_by_step[:10],
            "logic_breakdown": logic_breakdown[:8],
            "real_world_analogy": real_world_analogy,
            "warnings": ["Learning Mode used fallback explanation due unstructured model output."],
        }

    @classmethod
    async def generate_learning_mode_explanation(
        cls,
        code_snippet: str,
        language: str,
        user_prompt: str = "",
    ) -> Dict[str, Any]:
        """Generate deep educational explanation for a code snippet."""
        normalized_code = str(code_snippet or "")
        if not normalized_code.strip():
            return {
                "overview": "No code snippet was provided.",
                "step_by_step": ["Provide a non-empty snippet so Learning Mode can explain execution."],
                "logic_breakdown": ["No logic could be analyzed because code was empty."],
                "real_world_analogy": "It is like trying to review a blueprint that has no drawing.",
                "warnings": ["Empty code snippet."],
            }

        system_prompt = (
            "You are Intellexa Learning Mode, an expert code educator. "
            "Explain code deeply but clearly for learners. "
            "Return JSON only with keys: overview, step_by_step, logic_breakdown, real_world_analogy, warnings. "
            "step_by_step must be an array of 4-10 concise numbered-learning steps. "
            "logic_breakdown must be an array of 3-8 points describing control flow and data flow. "
            "real_world_analogy must be one practical analogy. "
            "warnings should include cautionary notes only when necessary."
        )

        user_payload = json.dumps(
            {
                "language": language,
                "instruction": user_prompt or "Explain this code deeply for learning.",
                "code": normalized_code,
            },
            ensure_ascii=False,
            indent=2,
        )

        try:
            raw = await llama_service.get_ai_response(user_payload, system_prompt=system_prompt)
        except Exception:
            return cls._build_learning_mode_fallback(normalized_code, language, user_prompt)

        parsed = cls._extract_json_object(raw)
        if not parsed:
            return cls._build_learning_mode_fallback(normalized_code, language, user_prompt)

        overview = cls._normalize_text(parsed.get("overview") or "")
        step_by_step = cls._normalize_list(parsed.get("step_by_step"), max_items=10)
        logic_breakdown = cls._normalize_list(parsed.get("logic_breakdown"), max_items=8)
        real_world_analogy = cls._normalize_text(parsed.get("real_world_analogy") or "")
        warnings = cls._normalize_list(parsed.get("warnings"), max_items=6)

        if not overview or not step_by_step or not logic_breakdown or not real_world_analogy:
            return cls._build_learning_mode_fallback(normalized_code, language, user_prompt)

        return {
            "overview": overview,
            "step_by_step": step_by_step,
            "logic_breakdown": logic_breakdown,
            "real_world_analogy": real_world_analogy,
            "warnings": warnings,
        }


explanation_service = ExplanationService()
