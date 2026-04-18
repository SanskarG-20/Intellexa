"""
context_service.py - Workspace context retrieval and prompt construction.
"""

from __future__ import annotations

from typing import List, Tuple

from app.services.memory.retrieval_service import retrieval_service, RetrievedContext


class CodeWorkspaceContextService:
    """Builds user-aware context blocks for code-assist prompts."""

    EMPTY_KNOWLEDGE_TEXT = "No relevant user knowledge was found."

    @staticmethod
    def _clip_text(value: str, max_chars: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= max_chars:
            return text
        keep_head = int(max_chars * 0.7)
        keep_tail = max_chars - keep_head
        return f"{text[:keep_head]}\n...\n{text[-keep_tail:]}"

    def _format_knowledge(self, results: List[RetrievedContext], max_items: int = 6) -> str:
        if not results:
            return self.EMPTY_KNOWLEDGE_TEXT

        lines: List[str] = []
        for idx, item in enumerate(results[:max_items], start=1):
            source = item.filename or item.source_type or "memory"
            summary = item.summary or item.content or ""
            summary = self._clip_text(summary, 350)
            lines.append(f"{idx}. [{source}] {summary}")

        return "\n".join(lines) if lines else self.EMPTY_KNOWLEDGE_TEXT

    @staticmethod
    def _extract_sources(results: List[RetrievedContext], max_items: int = 8) -> List[str]:
        values: List[str] = []
        seen = set()
        for item in results[: max_items * 2]:
            source = (item.filename or item.source_type or "").strip()
            if not source or source in seen:
                continue
            seen.add(source)
            values.append(source)
            if len(values) >= max_items:
                break
        return values

    async def retrieve_user_knowledge(
        self,
        *,
        user_id: str,
        prompt: str,
        code: str,
        explicit_context: str | None = None,
        top_k: int = 6,
    ) -> Tuple[str, List[str]]:
        """Retrieve user knowledge from the memory engine for assist/autocomplete."""
        query_parts = [
            (prompt or "").strip(),
            self._clip_text(code or "", 1200),
            (explicit_context or "").strip(),
        ]
        query = "\n".join(part for part in query_parts if part)
        if not query.strip():
            return self.EMPTY_KNOWLEDGE_TEXT, []

        try:
            context_rows = await retrieval_service.retrieve_context(
                query=query,
                user_id=user_id,
                top_k=max(1, min(top_k, 12)),
            )
        except Exception:
            return self.EMPTY_KNOWLEDGE_TEXT, []

        return self._format_knowledge(context_rows), self._extract_sources(context_rows)

    def build_prompt(
        self,
        *,
        user_knowledge: str,
        code: str,
        task: str,
        max_code_chars: int,
    ) -> str:
        """Build prompt using the required deterministic contract."""
        safe_code = self._clip_text(code or "", max_code_chars)
        safe_task = (task or "").strip() or "Explain this code."
        knowledge = (user_knowledge or "").strip() or self.EMPTY_KNOWLEDGE_TEXT

        return (
            f"User Knowledge:\n{knowledge}\n\n"
            f"Code:\n{safe_code}\n\n"
            f"Task:\n{safe_task}"
        )


code_workspace_context_service = CodeWorkspaceContextService()
