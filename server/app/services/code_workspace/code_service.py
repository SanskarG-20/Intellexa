"""
code_service.py - AI code assistance and autocomplete orchestration.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.schemas.code import (
    CodeAction,
    CodeAssistRequest,
    CodeAssistResponse,
    CodeAutocompleteItem,
    CodeAutocompleteRequest,
    CodeAutocompleteResponse,
    IntentDecision,
    CodeLearningExplanation,
    CodeSuggestion,
    LearningModeRequest,
    LearningModeResponse,
)
from app.services.code_workspace.context_service import code_workspace_context_service
from app.services.explanation_service import explanation_service
from app.services.llama_service import llama_service
from app.services.memory.user_pattern_service import user_pattern_memory_service


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


class CodeWorkspaceCodeService:
    """Main AI orchestration service for assist and autocomplete."""

    def __init__(self) -> None:
        self.context_service = code_workspace_context_service
        self._cache: Dict[str, _CacheEntry] = {}

    @staticmethod
    def _clip(value: str, max_chars: int) -> str:
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        head = int(max_chars * 0.65)
        tail = max_chars - head
        return f"{text[:head]}\n...\n{text[-tail:]}"

    @staticmethod
    def _normalize_prompt(prompt: str) -> str:
        return " ".join(str(prompt or "").split()).strip()

    def _cache_key(self, namespace: str, payload: Dict[str, Any]) -> str:
        serialized = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        digest = sha256(serialized.encode("utf-8")).hexdigest()
        return f"{namespace}:{digest}"

    def _cache_get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_set(self, key: str, value: Any) -> None:
        ttl = max(5, int(settings.CODE_ASSIST_CACHE_TTL_SECONDS))
        self._cache[key] = _CacheEntry(expires_at=time.time() + ttl, value=value)

        max_items = max(64, int(settings.CODE_ASSIST_CACHE_MAX_ITEMS))
        if len(self._cache) <= max_items:
            return

        stale_keys = sorted(self._cache.keys(), key=lambda item: self._cache[item].expires_at)
        for stale in stale_keys[: len(self._cache) - max_items]:
            self._cache.pop(stale, None)

    @staticmethod
    def _extract_code_block(text: str, language: str) -> Optional[str]:
        pattern = rf"```(?:{re.escape(language)})?\s*\n(.*?)\n```"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()

        generic_match = re.search(r"```\s*\n(.*?)\n```", text, re.DOTALL)
        return generic_match.group(1).strip() if generic_match else None

    @staticmethod
    def _strip_code_blocks(text: str) -> str:
        return re.sub(r"```[\s\S]*?```", "", str(text or "")).strip()

    @staticmethod
    def _extract_suggestions(explanation: str, max_items: int = 5) -> List[CodeSuggestion]:
        suggestions: List[CodeSuggestion] = []
        for line in str(explanation or "").splitlines():
            trimmed = line.strip()
            if not trimmed:
                continue
            if trimmed.startswith("-") or trimmed.startswith("*"):
                value = trimmed[1:].strip()
                if value:
                    suggestions.append(
                        CodeSuggestion(title="Suggestion", description=value[:240])
                    )
            if len(suggestions) >= max_items:
                break

        if not suggestions:
            suggestions.append(
                CodeSuggestion(
                    title="Review",
                    description="Apply the proposed update and run tests before committing.",
                )
            )

        return suggestions[:max_items]

    @staticmethod
    def _extract_text_list(
        payload: Dict[str, Any],
        key: str,
        *,
        max_items: int,
        max_chars: int = 220,
    ) -> List[str]:
        raw_items = payload.get(key)
        if not isinstance(raw_items, list):
            return []

        values: List[str] = []
        seen = set()
        for item in raw_items:
            if isinstance(item, dict):
                text = str(item.get("description") or item.get("title") or "").strip()
            else:
                text = str(item or "").strip()

            if not text:
                continue

            normalized = " ".join(text.split())
            dedupe_key = normalized.lower()
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            values.append(normalized[:max_chars])
            if len(values) >= max_items:
                break

        return values

    @staticmethod
    def _extract_first_json_object(raw: str) -> Optional[Dict[str, Any]]:
        text = str(raw or "").strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
        if fenced:
            try:
                parsed = json.loads(fenced.group(1).strip())
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        starts = [index for index, ch in enumerate(text) if ch == "{"]
        for start in starts:
            depth = 0
            in_string = False
            escaped = False
            for i in range(start, len(text)):
                ch = text[i]

                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue

                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict):
                                return parsed
                        except Exception:
                            break

        return None

    @staticmethod
    def _intent_system_prompt(language: str) -> str:
        return (
            "You are an optimization-focused coding architect. "
            "Convert user intent into production-ready code improvements. "
            "Return strictly valid JSON only with keys: "
            "algorithm, structure, complexity, rationale, optimized_code, explanation, suggestions. "
            "suggestions must be an array of short strings. "
            f"optimized_code must be executable {language} code without markdown fences."
        )

    @staticmethod
    def _test_system_prompt(language: str) -> str:
        return (
            "You are a senior test engineer. "
            "Generate robust unit tests for the provided code. "
            "Return strictly valid JSON only with keys: "
            "test_code, explanation, test_cases, edge_cases, suggestions. "
            "test_cases and edge_cases must be arrays of short strings. "
            "suggestions must be an array of short strings. "
            f"test_code must be executable {language} test code without markdown fences."
        )

    @staticmethod
    def _fallback_intent_plan(
        intent_prompt: str,
        language: str,
    ) -> Dict[str, Any]:
        prompt = str(intent_prompt or "")
        lower = prompt.lower()
        lang = str(language or "javascript").lower()

        if "search" in lower and lang == "python":
            return {
                "algorithm": "Hash-indexed lookup with pre-normalized keys",
                "structure": "One-time dictionary index keyed by normalized searchable tokens",
                "complexity": "Index build O(n), query O(1) average",
                "rationale": (
                    "Intent asks for faster search. Replacing repeated linear scans with a dictionary "
                    "index reduces query latency significantly."
                ),
                "optimized_code": (
                    "from collections import defaultdict\n\n"
                    "def build_search_index(items, key='name'):\n"
                    "    index = defaultdict(list)\n"
                    "    for item in items:\n"
                    "        value = str(item.get(key, '')).strip().lower()\n"
                    "        if value:\n"
                    "            index[value].append(item)\n"
                    "    return index\n\n"
                    "def fast_search(index, query):\n"
                    "    q = str(query or '').strip().lower()\n"
                    "    if not q:\n"
                    "        return []\n"
                    "    return list(index.get(q, []))\n"
                ),
                "explanation": (
                    "This optimization introduces an index-building step and performs constant-time "
                    "lookup for repeated searches instead of scanning every record each time."
                ),
                "suggestions": [
                    "Rebuild the index when source data changes.",
                    "Normalize queries and indexed values consistently.",
                    "Add tests for missing or empty query inputs.",
                ],
            }

        if "search" in lower:
            return {
                "algorithm": "Hash-indexed lookup with normalized keys",
                "structure": "Map-based index built once and reused for queries",
                "complexity": "Index build O(n), query O(1) average",
                "rationale": (
                    "Intent asks for faster search. Pre-indexing prevents repeated full-array scans."
                ),
                "optimized_code": (
                    "export function buildSearchIndex(items, key = 'name') {\n"
                    "  const index = new Map();\n"
                    "  for (const item of items || []) {\n"
                    "    const value = String(item?.[key] ?? '').trim().toLowerCase();\n"
                    "    if (!value) continue;\n"
                    "    const bucket = index.get(value) || [];\n"
                    "    bucket.push(item);\n"
                    "    index.set(value, bucket);\n"
                    "  }\n"
                    "  return index;\n"
                    "}\n\n"
                    "export function fastSearch(index, query) {\n"
                    "  const normalized = String(query ?? '').trim().toLowerCase();\n"
                    "  if (!normalized) return [];\n"
                    "  return [...(index.get(normalized) || [])];\n"
                    "}\n"
                ),
                "explanation": (
                    "This turns repeated linear search into indexed lookup. Build the index once, "
                    "then resolve queries directly from the map."
                ),
                "suggestions": [
                    "Refresh index after mutations.",
                    "Measure before/after latency on representative datasets.",
                    "Handle partial-match search with a secondary prefix index if needed.",
                ],
            }

        return {
            "algorithm": "Precompute hot-path data and reduce repeated work",
            "structure": "Separate preprocessing stage from request-time execution path",
            "complexity": "Depends on workload; optimized path minimizes repeated operations",
            "rationale": "Intent optimization benefits from moving expensive work outside hot execution loops.",
            "optimized_code": (
                "// Optimization template\n"
                "export function preprocess(input) {\n"
                "  return input;\n"
                "}\n\n"
                "export function runOptimized(preprocessed, query) {\n"
                "  return preprocessed;\n"
                "}\n"
            ),
            "explanation": (
                "The optimized structure precomputes reusable data once and keeps request-time "
                "logic lightweight."
            ),
            "suggestions": [
                "Profile baseline performance before deployment.",
                "Add benchmarks to prevent regressions.",
            ],
        }

    @staticmethod
    def _fallback_test_generation(code: str, language: str) -> Dict[str, Any]:
        safe_language = str(language or "javascript").strip().lower()
        source = str(code or "")

        if safe_language == "python":
            function_name = "target_function"
            match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", source)
            if match:
                function_name = match.group(1)

            return {
                "test_code": (
                    "import unittest\n\n"
                    f"from module_under_test import {function_name}\n\n"
                    f"class Test{function_name.title().replace('_', '')}(unittest.TestCase):\n"
                    "    def test_happy_path(self):\n"
                    f"        result = {function_name}(1)\n"
                    "        self.assertIsNotNone(result)\n\n"
                    "    def test_invalid_input_type(self):\n"
                    "        with self.assertRaises((TypeError, ValueError)):\n"
                    f"            {function_name}(None)\n\n"
                    "    def test_boundary_input(self):\n"
                    f"        result = {function_name}(0)\n"
                    "        self.assertIsNotNone(result)\n\n"
                    "if __name__ == '__main__':\n"
                    "    unittest.main()\n"
                ),
                "explanation": (
                    "Generated baseline unit tests covering happy path, invalid input handling, "
                    "and a boundary condition."
                ),
                "test_cases": [
                    "Happy path with valid input returns expected shape/value.",
                    "Invalid input type raises TypeError/ValueError.",
                    "Boundary input at 0 executes without runtime failure.",
                ],
                "edge_cases": [
                    "None/null input.",
                    "Empty collections/strings when applicable.",
                    "Very large inputs for performance or overflow behavior.",
                ],
                "suggestions": [
                    "Add fixture-driven parameterized tests.",
                    "Mock external dependencies for deterministic unit tests.",
                ],
            }

        function_name = "targetFunction"
        match = re.search(r"function\s+([A-Za-z_][A-Za-z0-9_]*)", source)
        if match:
            function_name = match.group(1)

        return {
            "test_code": (
                f"import {{ {function_name} }} from './module-under-test';\n\n"
                f"describe('{function_name}', () => {{\n"
                "  test('handles happy path input', () => {\n"
                f"    const result = {function_name}(1);\n"
                "    expect(result).toBeDefined();\n"
                "  });\n\n"
                "  test('throws on invalid input', () => {\n"
                f"    expect(() => {function_name}(null)).toThrow();\n"
                "  });\n\n"
                "  test('handles boundary input', () => {\n"
                f"    const result = {function_name}(0);\n"
                "    expect(result).toBeDefined();\n"
                "  });\n"
                "});\n"
            ),
            "explanation": (
                "Generated baseline unit tests for nominal flow, invalid input behavior, "
                "and boundary handling."
            ),
            "test_cases": [
                "Happy path with representative valid input.",
                "Invalid/null input produces explicit failure.",
                "Boundary values (0, empty string, empty array) are handled safely.",
            ],
            "edge_cases": [
                "Undefined/null parameters.",
                "Extremely large input values.",
                "Special characters and whitespace-only string inputs.",
            ],
            "suggestions": [
                "Add snapshot tests for stable structured output.",
                "Use table-driven tests for multiple edge values.",
            ],
        }

    @staticmethod
    def _intent_suggestions_from_payload(payload: Dict[str, Any], max_items: int) -> List[CodeSuggestion]:
        raw_items = payload.get("suggestions")
        if not isinstance(raw_items, list):
            return []

        values: List[CodeSuggestion] = []
        for index, item in enumerate(raw_items, start=1):
            if isinstance(item, dict):
                title = str(item.get("title") or f"Optimization {index}").strip()
                description = str(item.get("description") or item.get("detail") or "").strip()
            else:
                title = f"Optimization {index}"
                description = str(item or "").strip()

            if not description:
                continue

            values.append(CodeSuggestion(title=title[:80], description=description[:280]))
            if len(values) >= max_items:
                break

        return values

    def _build_test_response(
        self,
        *,
        ai_text: str,
        code: str,
        language: str,
        context_used: bool,
        context_sources: List[str],
        max_suggestions: int,
    ) -> CodeAssistResponse:
        payload = self._extract_first_json_object(ai_text) or {}

        test_code = str(
            payload.get("test_code")
            or payload.get("tests")
            or payload.get("updated_code")
            or ""
        ).strip()
        if not test_code:
            test_code = self._extract_code_block(ai_text, language) or ""

        explanation = str(payload.get("explanation") or "").strip()
        if not explanation:
            explanation = self._strip_code_blocks(ai_text).strip()

        test_cases = self._extract_text_list(
            payload,
            "test_cases",
            max_items=max(3, min(max_suggestions + 2, 8)),
        )
        edge_cases = self._extract_text_list(
            payload,
            "edge_cases",
            max_items=max(3, min(max_suggestions + 2, 8)),
        )

        warnings: List[str] = []
        fallback = None
        if not test_code or not test_cases or not edge_cases:
            fallback = self._fallback_test_generation(code, language)
            test_code = test_code or str(fallback.get("test_code") or "")
            explanation = explanation or str(fallback.get("explanation") or "")
            test_cases = test_cases or list(fallback.get("test_cases") or [])
            edge_cases = edge_cases or list(fallback.get("edge_cases") or [])
            warnings.append(
                "Test generator used deterministic fallback for missing model output fields."
            )

        if not explanation:
            explanation = (
                "Generated unit test scaffolding with core test cases and edge-case coverage guidance."
            )

        suggestions = self._intent_suggestions_from_payload(payload, max_suggestions)
        if not suggestions and fallback:
            suggestions = [
                CodeSuggestion(title=f"Test Advice {idx}", description=str(item)[:280])
                for idx, item in enumerate((fallback.get("suggestions") or [])[:max_suggestions], start=1)
            ]

        if not suggestions:
            suggestions = [
                CodeSuggestion(title=f"Test Case {idx}", description=value[:280])
                for idx, value in enumerate(test_cases[:max_suggestions], start=1)
            ]

        return CodeAssistResponse(
            updated_code=test_code or None,
            improved_code=test_code or None,
            explanation=explanation,
            test_cases=test_cases,
            edge_cases=edge_cases,
            suggestions=suggestions,
            context_used=context_used,
            context_sources=context_sources,
            action=CodeAction.TEST,
            language=language,
            intent_mode=False,
            intent_decision=None,
            learning_mode=False,
            learning_explanation=None,
            warnings=warnings,
            cached=False,
        )

    def _build_intent_response(
        self,
        *,
        ai_text: str,
        intent_prompt: str,
        language: str,
        context_used: bool,
        context_sources: List[str],
        max_suggestions: int,
    ) -> CodeAssistResponse:
        payload = self._extract_first_json_object(ai_text) or {}

        algorithm = str(payload.get("algorithm") or "").strip()
        structure = str(payload.get("structure") or "").strip()
        complexity = str(payload.get("complexity") or "").strip()
        rationale = str(payload.get("rationale") or "").strip()
        optimized_code = str(payload.get("optimized_code") or "").strip()

        if not optimized_code:
            optimized_code = self._extract_code_block(ai_text, language) or ""

        explanation = str(payload.get("explanation") or "").strip()
        warnings: List[str] = []

        fallback_plan = None
        if not algorithm or not structure or not optimized_code:
            fallback_plan = self._fallback_intent_plan(intent_prompt, language)
            algorithm = algorithm or str(fallback_plan.get("algorithm") or "")
            structure = structure or str(fallback_plan.get("structure") or "")
            complexity = complexity or str(fallback_plan.get("complexity") or "")
            rationale = rationale or str(fallback_plan.get("rationale") or "")
            optimized_code = optimized_code or str(fallback_plan.get("optimized_code") or "")
            warnings.append(
                "Intent mode filled missing model fields with deterministic optimization fallback."
            )

        if not explanation:
            explanation = self._strip_code_blocks(ai_text).strip()
        if not explanation and fallback_plan:
            explanation = str(fallback_plan.get("explanation") or "")
        if not explanation:
            explanation = (
                "Intent-based coding selected an optimization strategy and produced updated code "
                "focused on performance."
            )

        suggestions = self._intent_suggestions_from_payload(payload, max_suggestions)
        if not suggestions and fallback_plan:
            fallback_suggestions = fallback_plan.get("suggestions") or []
            suggestions = [
                CodeSuggestion(title=f"Optimization {index}", description=str(item)[:280])
                for index, item in enumerate(fallback_suggestions[:max_suggestions], start=1)
            ]
        if not suggestions:
            suggestions = self._extract_suggestions(explanation, max_items=max_suggestions)

        intent_decision = IntentDecision(
            algorithm=algorithm,
            structure=structure,
            complexity=complexity,
            rationale=rationale,
        )

        return CodeAssistResponse(
            updated_code=optimized_code or None,
            improved_code=optimized_code or None,
            optimized_code=optimized_code or None,
            explanation=explanation,
            suggestions=suggestions,
            context_used=context_used,
            context_sources=context_sources,
            action=CodeAction.INTENT,
            language=language,
            intent_mode=True,
            intent_decision=intent_decision,
            learning_mode=False,
            learning_explanation=None,
            warnings=warnings,
            cached=False,
        )

    @staticmethod
    def _extract_learning_suggestions(
        learning_explanation: CodeLearningExplanation,
        max_items: int = 5,
    ) -> List[CodeSuggestion]:
        suggestions: List[CodeSuggestion] = []

        for index, step in enumerate(learning_explanation.step_by_step[:max_items], start=1):
            suggestions.append(
                CodeSuggestion(
                    title=f"Learning Step {index}",
                    description=step,
                )
            )

        if not suggestions and learning_explanation.logic_breakdown:
            for index, item in enumerate(learning_explanation.logic_breakdown[:max_items], start=1):
                suggestions.append(
                    CodeSuggestion(
                        title=f"Logic Point {index}",
                        description=item,
                    )
                )

        if not suggestions:
            suggestions.append(
                CodeSuggestion(
                    title="Review",
                    description="Walk through the code line by line and map each line to data flow.",
                )
            )

        return suggestions[:max_items]

    @staticmethod
    def _merge_knowledge_with_pattern_guidance(
        user_knowledge: str,
        pattern_guidance: str,
    ) -> str:
        base = str(user_knowledge or "").strip() or "No relevant user knowledge was found."
        guidance = str(pattern_guidance or "").strip()
        if not guidance:
            return base
        return f"{base}\n\n{guidance}"

    @staticmethod
    def _personalize_suggestions(
        suggestions: List[CodeSuggestion],
        *,
        style_preferences: Dict[str, Any],
        interactions: int,
        language: str,
    ) -> List[CodeSuggestion]:
        if not suggestions:
            return suggestions

        if interactions < max(1, int(settings.USER_PATTERN_MIN_INTERACTIONS)):
            return suggestions

        style_hint = user_pattern_memory_service.build_style_hint(style_preferences, language)
        if not style_hint:
            return suggestions

        updated: List[CodeSuggestion] = []
        for index, suggestion in enumerate(suggestions):
            if index >= 2:
                updated.append(suggestion)
                continue

            combined = " ".join([str(suggestion.description or "").strip(), style_hint]).strip()
            updated.append(
                suggestion.model_copy(update={"description": combined[:320]})
            )

        return updated

    @staticmethod
    def _personalize_autocomplete_suggestions(
        suggestions: List[CodeAutocompleteItem],
        *,
        style_preferences: Dict[str, Any],
        interactions: int,
        language: str,
    ) -> List[CodeAutocompleteItem]:
        if not suggestions:
            return suggestions

        if interactions < max(1, int(settings.USER_PATTERN_MIN_INTERACTIONS)):
            return suggestions

        style_hint = user_pattern_memory_service.build_style_hint(style_preferences, language)

        updated: List[CodeAutocompleteItem] = []
        for item in suggestions:
            insert_text = user_pattern_memory_service.apply_style_to_code_snippet(
                item.insert_text,
                style_preferences,
                language,
            )

            detail = str(item.detail or "AI suggestion").strip() or "AI suggestion"
            if style_hint:
                detail = f"{detail} | style-aware"

            updated.append(
                item.model_copy(
                    update={
                        "insert_text": insert_text[:500],
                        "detail": detail[:160],
                    }
                )
            )

        return updated

    @staticmethod
    def _assist_system_prompt(action: CodeAction, language: str) -> str:
        prompts = {
            CodeAction.EXPLAIN: (
                "You are a senior engineer. Explain code clearly, identify risks, and be specific."
            ),
            CodeAction.GENERATE: (
                "You are a senior engineer. Generate production-ready code with defensive checks."
            ),
            CodeAction.FIX: (
                "You are a senior debugger. Find bugs and provide a corrected version."
            ),
            CodeAction.REFACTOR: (
                "You are a senior refactoring specialist. Improve readability and maintainability "
                "without changing behavior."
            ),
            CodeAction.INTENT: (
                "You are a senior performance engineer. Translate intent into optimized code and "
                "explicitly choose algorithm and data structure."
            ),
            CodeAction.TEST: (
                "You are a senior test engineer. Generate executable unit tests and enumerate edge cases."
            ),
        }
        return (
            prompts.get(action, prompts[CodeAction.EXPLAIN])
            + f" Return the updated {language} code in a fenced block when code changes are needed."
        )

    async def assist(self, request: CodeAssistRequest, user_id: str) -> CodeAssistResponse:
        """Handle code assistance requests with context injection and caching."""
        prompt = self._normalize_prompt(request.prompt)
        if not prompt:
            raise ValueError("Prompt is required.")

        if len(prompt) > settings.CODE_ASSIST_MAX_PROMPT_CHARS:
            raise ValueError(
                f"Prompt exceeds limit of {settings.CODE_ASSIST_MAX_PROMPT_CHARS} characters."
            )

        code = request.code or ""
        if len(code) > settings.CODE_ASSIST_MAX_CODE_CHARS:
            code = self._clip(code, settings.CODE_ASSIST_MAX_CODE_CHARS)

        adaptation_context: Dict[str, Any] = {
            "signature": "none",
            "guidance": "",
            "style_preferences": {},
            "interactions": 0,
        }
        try:
            adaptation_context = await user_pattern_memory_service.get_adaptation_context(
                user_id=user_id,
                language=request.language,
            )
        except Exception:
            adaptation_context = {
                "signature": "none",
                "guidance": "",
                "style_preferences": {},
                "interactions": 0,
            }

        cache_key = self._cache_key(
            "assist",
            {
                "user_id": user_id,
                "prompt": prompt,
                "language": request.language,
                "action": request.action,
                "code": sha256(code.encode("utf-8")).hexdigest(),
                "context": request.include_context,
                "extra_context": request.context or "",
                "learning_mode": bool(request.learning_mode),
                "pattern_signature": adaptation_context.get("signature") or "none",
            },
        )
        cached = self._cache_get(cache_key)
        if cached:
            return cached.model_copy(update={"cached": True})

        user_knowledge = "No relevant user knowledge was found."
        context_sources: List[str] = []
        if request.include_context:
            user_knowledge, context_sources = await self.context_service.retrieve_user_knowledge(
                user_id=user_id,
                prompt=prompt,
                code=code,
                explicit_context=request.context,
                top_k=6,
            )
        elif request.context:
            user_knowledge = self._clip(request.context, 1200)

        user_knowledge = self._merge_knowledge_with_pattern_guidance(
            user_knowledge,
            str(adaptation_context.get("guidance") or ""),
        )

        if request.learning_mode:
            learning_payload = await explanation_service.generate_learning_mode_explanation(
                code_snippet=code,
                language=request.language,
                user_prompt=prompt,
            )

            learning_explanation = CodeLearningExplanation(
                step_by_step=list(learning_payload.get("step_by_step") or []),
                logic_breakdown=list(learning_payload.get("logic_breakdown") or []),
                real_world_analogy=str(learning_payload.get("real_world_analogy") or ""),
            )

            warnings = [str(item) for item in (learning_payload.get("warnings") or []) if str(item).strip()]
            if request.action != CodeAction.EXPLAIN:
                warnings.append(
                    "Learning Mode focuses on explainability; action was treated as educational explanation."
                )

            overview = str(learning_payload.get("overview") or "").strip()
            explanation_text = overview or (
                "Learning Mode produced a deep explanation with step-by-step and logic breakdown outputs."
            )

            learning_suggestions = self._extract_learning_suggestions(
                learning_explanation,
                max_items=max(1, min(request.max_suggestions, 10)),
            )
            learning_suggestions = self._personalize_suggestions(
                learning_suggestions,
                style_preferences=adaptation_context.get("style_preferences") or {},
                interactions=int(adaptation_context.get("interactions") or 0),
                language=request.language,
            )

            response = CodeAssistResponse(
                updated_code=None,
                improved_code=None,
                explanation=explanation_text,
                suggestions=learning_suggestions,
                context_used=bool(request.include_context and context_sources),
                context_sources=context_sources,
                action=request.action,
                language=request.language,
                learning_mode=True,
                learning_explanation=learning_explanation,
                warnings=warnings,
                cached=False,
            )

            self._cache_set(cache_key, response)
            return response

        if request.action == CodeAction.TEST:
            composite_prompt = self.context_service.build_prompt(
                user_knowledge=user_knowledge,
                code=code,
                task=(
                    "Generate unit tests for the provided code. "
                    "Return: executable test code, a concise explanation, explicit test_cases, "
                    "and explicit edge_cases."
                ),
                max_code_chars=settings.CODE_ASSIST_MAX_CODE_CHARS,
            )

            ai_text = await llama_service.get_ai_response(
                composite_prompt,
                system_prompt=self._test_system_prompt(request.language),
            )

            response = self._build_test_response(
                ai_text=ai_text,
                code=code,
                language=request.language,
                context_used=bool(request.include_context and context_sources),
                context_sources=context_sources,
                max_suggestions=max(1, min(request.max_suggestions, 10)),
            )

            response = response.model_copy(
                update={
                    "suggestions": self._personalize_suggestions(
                        list(response.suggestions),
                        style_preferences=adaptation_context.get("style_preferences") or {},
                        interactions=int(adaptation_context.get("interactions") or 0),
                        language=request.language,
                    )
                }
            )

            self._cache_set(cache_key, response)
            return response

        if request.action == CodeAction.INTENT:
            composite_prompt = self.context_service.build_prompt(
                user_knowledge=user_knowledge,
                code=code,
                task=(
                    f"User intent: {prompt}\n"
                    "Decide the best algorithm and structure for optimization and return optimized code."
                ),
                max_code_chars=settings.CODE_ASSIST_MAX_CODE_CHARS,
            )

            ai_text = await llama_service.get_ai_response(
                composite_prompt,
                system_prompt=self._intent_system_prompt(request.language),
            )

            response = self._build_intent_response(
                ai_text=ai_text,
                intent_prompt=prompt,
                language=request.language,
                context_used=bool(request.include_context and context_sources),
                context_sources=context_sources,
                max_suggestions=max(1, min(request.max_suggestions, 10)),
            )

            response = response.model_copy(
                update={
                    "suggestions": self._personalize_suggestions(
                        list(response.suggestions),
                        style_preferences=adaptation_context.get("style_preferences") or {},
                        interactions=int(adaptation_context.get("interactions") or 0),
                        language=request.language,
                    )
                }
            )

            self._cache_set(cache_key, response)
            return response

        composite_prompt = self.context_service.build_prompt(
            user_knowledge=user_knowledge,
            code=code,
            task=prompt,
            max_code_chars=settings.CODE_ASSIST_MAX_CODE_CHARS,
        )

        ai_text = await llama_service.get_ai_response(
            composite_prompt,
            system_prompt=self._assist_system_prompt(request.action, request.language),
        )

        updated_code = self._extract_code_block(ai_text, request.language)
        explanation = self._strip_code_blocks(ai_text) or ai_text

        suggestions = self._extract_suggestions(
            explanation,
            max_items=max(1, min(request.max_suggestions, 10)),
        )
        suggestions = self._personalize_suggestions(
            suggestions,
            style_preferences=adaptation_context.get("style_preferences") or {},
            interactions=int(adaptation_context.get("interactions") or 0),
            language=request.language,
        )

        response = CodeAssistResponse(
            updated_code=updated_code,
            improved_code=updated_code,
            explanation=explanation,
            suggestions=suggestions,
            context_used=bool(request.include_context and context_sources),
            context_sources=context_sources,
            action=request.action,
            language=request.language,
            learning_mode=False,
            learning_explanation=None,
            warnings=[],
            cached=False,
        )

        self._cache_set(cache_key, response)
        return response

    @staticmethod
    def _autocomplete_system_prompt(language: str, max_suggestions: int) -> str:
        return (
            f"You are an autocomplete engine for {language}. "
            f"Return strictly JSON with key suggestions. suggestions must be an array of up to {max_suggestions} items. "
            "Each item must have label, insert_text, and detail. No markdown, no prose."
        )

    @staticmethod
    def _fallback_autocomplete(language: str, max_suggestions: int) -> List[CodeAutocompleteItem]:
        fallback_map = {
            "python": [
                ("def", "def function_name():\n    pass", "Define a function"),
                ("ifmain", "if __name__ == '__main__':\n    main()", "Python entry point"),
                ("try", "try:\n    pass\nexcept Exception as exc:\n    print(exc)", "Error handling"),
            ],
            "javascript": [
                ("fn", "function name(params) {\n  return;\n}", "Function template"),
                ("const", "const value = ", "Const declaration"),
                ("try", "try {\n  \n} catch (error) {\n  console.error(error);\n}", "Error handling"),
            ],
            "typescript": [
                ("interface", "interface Name {\n  key: string;\n}", "Interface template"),
                ("type", "type Name = {\n  key: string;\n};", "Type alias"),
                ("async", "async function run(): Promise<void> {\n  \n}", "Async function"),
            ],
        }

        rows = fallback_map.get(language.lower(), fallback_map["javascript"])
        return [
            CodeAutocompleteItem(label=label, insert_text=insert_text, detail=detail)
            for label, insert_text, detail in rows[:max_suggestions]
        ]

    @staticmethod
    def _parse_autocomplete_json(raw: str, max_suggestions: int) -> List[CodeAutocompleteItem]:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", raw)
            if not match:
                return []
            try:
                parsed = json.loads(match.group(0))
            except json.JSONDecodeError:
                return []

        suggestions = parsed.get("suggestions") if isinstance(parsed, dict) else None
        if not isinstance(suggestions, list):
            return []

        values: List[CodeAutocompleteItem] = []
        for item in suggestions:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or "").strip()
            insert_text = str(item.get("insert_text") or "").strip()
            detail = str(item.get("detail") or "").strip()
            if not label or not insert_text:
                continue
            values.append(
                CodeAutocompleteItem(
                    label=label[:60],
                    insert_text=insert_text[:500],
                    detail=detail[:160] or "AI suggestion",
                )
            )
            if len(values) >= max_suggestions:
                break

        return values

    async def autocomplete(
        self,
        request: CodeAutocompleteRequest,
        user_id: str,
    ) -> CodeAutocompleteResponse:
        """Generate code completions with context and caching."""
        safe_code = request.code or ""
        if len(safe_code) > settings.CODE_ASSIST_MAX_CODE_CHARS:
            safe_code = self._clip(safe_code, settings.CODE_ASSIST_MAX_CODE_CHARS)

        adaptation_context: Dict[str, Any] = {
            "signature": "none",
            "guidance": "",
            "style_preferences": {},
            "interactions": 0,
        }
        try:
            adaptation_context = await user_pattern_memory_service.get_adaptation_context(
                user_id=user_id,
                language=request.language,
            )
        except Exception:
            adaptation_context = {
                "signature": "none",
                "guidance": "",
                "style_preferences": {},
                "interactions": 0,
            }

        cursor_descriptor = f"line {request.cursor_line}, column {request.cursor_column}"

        cache_key = self._cache_key(
            "autocomplete",
            {
                "user_id": user_id,
                "language": request.language,
                "code": sha256(safe_code.encode("utf-8")).hexdigest(),
                "cursor": cursor_descriptor,
                "max": request.max_suggestions,
                "pattern_signature": adaptation_context.get("signature") or "none",
            },
        )
        cached = self._cache_get(cache_key)
        if cached:
            return cached.model_copy(update={"cached": True})

        user_knowledge, sources = await self.context_service.retrieve_user_knowledge(
            user_id=user_id,
            prompt=f"Autocomplete near {cursor_descriptor}",
            code=safe_code,
            explicit_context=request.context,
            top_k=3,
        )
        user_knowledge = self._merge_knowledge_with_pattern_guidance(
            user_knowledge,
            str(adaptation_context.get("guidance") or ""),
        )

        prompt = self.context_service.build_prompt(
            user_knowledge=user_knowledge,
            code=safe_code,
            task=(
                f"Suggest up to {request.max_suggestions} short autocomplete continuations "
                f"for {request.language} at {cursor_descriptor}."
            ),
            max_code_chars=5000,
        )

        raw = await llama_service.get_ai_response(
            prompt,
            system_prompt=self._autocomplete_system_prompt(
                request.language,
                request.max_suggestions,
            ),
        )

        suggestions = self._parse_autocomplete_json(raw, request.max_suggestions)
        if not suggestions:
            suggestions = self._fallback_autocomplete(request.language, request.max_suggestions)
        suggestions = self._personalize_autocomplete_suggestions(
            suggestions,
            style_preferences=adaptation_context.get("style_preferences") or {},
            interactions=int(adaptation_context.get("interactions") or 0),
            language=request.language,
        )

        response = CodeAutocompleteResponse(
            suggestions=suggestions,
            context_used=bool(sources),
            context_sources=sources,
            cached=False,
        )
        self._cache_set(cache_key, response)
        return response

    async def learning_mode_explain(
        self,
        request: LearningModeRequest,
        user_id: str,
    ) -> LearningModeResponse:
        """Dedicated Learning Mode endpoint that reuses assist orchestration."""
        assist_request = CodeAssistRequest(
            code=request.code,
            language=request.language,
            prompt=request.prompt,
            action=CodeAction.EXPLAIN,
            include_context=request.include_context,
            context=request.context,
            learning_mode=True,
            max_suggestions=5,
        )

        response = await self.assist(assist_request, user_id=user_id)

        learning_explanation = response.learning_explanation or CodeLearningExplanation(
            step_by_step=["No learning steps available."],
            logic_breakdown=["No logic breakdown available."],
            real_world_analogy="No analogy available.",
        )

        return LearningModeResponse(
            explanation=response.explanation,
            learning_explanation=learning_explanation,
            warnings=list(response.warnings),
            context_used=bool(response.context_used),
            context_sources=list(response.context_sources),
            language=response.language,
            cached=bool(response.cached),
        )


code_workspace_code_service = CodeWorkspaceCodeService()
