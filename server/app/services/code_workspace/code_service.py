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
    CodeLearningExplanation,
    CodeSuggestion,
    LearningModeRequest,
    LearningModeResponse,
)
from app.services.code_workspace.context_service import code_workspace_context_service
from app.services.explanation_service import explanation_service
from app.services.llama_service import llama_service


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

            response = CodeAssistResponse(
                updated_code=None,
                improved_code=None,
                explanation=explanation_text,
                suggestions=self._extract_learning_suggestions(
                    learning_explanation,
                    max_items=max(1, min(request.max_suggestions, 10)),
                ),
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

        cursor_descriptor = f"line {request.cursor_line}, column {request.cursor_column}"

        cache_key = self._cache_key(
            "autocomplete",
            {
                "user_id": user_id,
                "language": request.language,
                "code": sha256(safe_code.encode("utf-8")).hexdigest(),
                "cursor": cursor_descriptor,
                "max": request.max_suggestions,
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
