"""
context_service.py - Workspace context retrieval and prompt construction.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from app.services.memory.retrieval_service import retrieval_service, RetrievedContext


class CodeWorkspaceContextService:
    """Builds user-aware context blocks for code-assist prompts."""

    EMPTY_KNOWLEDGE_TEXT = "No relevant user knowledge was found."
    TARGET_MEMORY_SOURCES = {"docs", "images", "videos"}
    DOC_LIKE_FILE_TYPES = {"pdf", "text", "doc", "docx", "md", "markdown"}
    IMAGE_LIKE_FILE_TYPES = {"image", "jpg", "jpeg", "png", "gif", "webp"}
    VIDEO_LIKE_FILE_TYPES = {"video", "mp4", "mov", "avi", "webm", "mkv"}
    TOKEN_RE = re.compile(r"[a-z0-9_]{3,}")
    STOPWORDS = {
        "about", "after", "again", "also", "been", "being", "between", "could",
        "from", "have", "into", "just", "like", "only", "other", "should", "some",
        "than", "that", "their", "there", "these", "they", "this", "those", "through",
        "under", "were", "what", "when", "where", "which", "while", "with", "would",
        "your", "you", "them", "code", "task", "user", "knowledge", "using", "used",
    }

    @staticmethod
    def _clip_text(value: str, max_chars: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= max_chars:
            return text
        keep_head = int(max_chars * 0.7)
        keep_tail = max_chars - keep_head
        return f"{text[:keep_head]}\n...\n{text[-keep_tail:]}"

    @classmethod
    def _normalize_source_type(cls, item: RetrievedContext) -> str:
        source_type = str(item.source_type or "").strip().lower()
        if source_type:
            return source_type

        file_type = str(item.file_type or "").strip().lower()
        if file_type in cls.IMAGE_LIKE_FILE_TYPES or "image" in file_type:
            return "images"
        if file_type in cls.VIDEO_LIKE_FILE_TYPES or "video" in file_type:
            return "videos"
        if file_type in cls.DOC_LIKE_FILE_TYPES or file_type:
            return "docs"

        return "docs"

    @classmethod
    def _tokenize(cls, text: str) -> List[str]:
        values = cls.TOKEN_RE.findall(str(text or "").lower())
        return [token for token in values if token not in cls.STOPWORDS]

    @classmethod
    def _compute_overlap_score(cls, query: str, candidate: str) -> float:
        query_tokens = set(cls._tokenize(query))
        if not query_tokens:
            return 0.0

        candidate_tokens = set(cls._tokenize(candidate))
        if not candidate_tokens:
            return 0.0

        overlap = query_tokens.intersection(candidate_tokens)
        return len(overlap) / max(1, len(query_tokens))

    def _filter_relevant_knowledge(
        self,
        rows: List[RetrievedContext],
        *,
        query: str,
        max_items: int,
    ) -> List[RetrievedContext]:
        if not rows:
            return []

        candidates = []
        for item in rows:
            source_kind = self._normalize_source_type(item)
            if source_kind not in self.TARGET_MEMORY_SOURCES:
                continue

            content = item.summary or item.content or ""
            if not str(content).strip():
                continue

            similarity = float(item.similarity or 0.0)
            overlap = self._compute_overlap_score(query, content)

            # Relevance filtering:
            # 1) Keep very high semantic matches.
            # 2) Keep medium semantic matches when lexical overlap is present.
            # 3) Drop weak/noisy context.
            keep = False
            if similarity >= 0.72:
                keep = True
            elif similarity >= 0.45 and overlap >= 0.03:
                keep = True
            elif similarity >= 0.35 and overlap >= 0.08:
                keep = True

            if not keep:
                continue

            candidates.append((item, source_kind, similarity, overlap))

        candidates.sort(
            key=lambda row: (
                row[2] + row[3],
                row[2],
                row[3],
            ),
            reverse=True,
        )

        # Ensure diversity across docs/images/videos while preserving relevance.
        selected: List[RetrievedContext] = []
        per_source_cap = {
            "docs": max(2, max_items // 2),
            "images": max(1, max_items // 3),
            "videos": max(1, max_items // 3),
        }
        source_counts = {"docs": 0, "images": 0, "videos": 0}

        for item, source_kind, _, _ in candidates:
            if len(selected) >= max_items:
                break
            if source_counts[source_kind] >= per_source_cap[source_kind]:
                continue

            selected.append(item)
            source_counts[source_kind] += 1

        if len(selected) < max_items:
            selected_ids = {id(item) for item in selected}
            for item, _, _, _ in candidates:
                if len(selected) >= max_items:
                    break
                if id(item) in selected_ids:
                    continue
                selected.append(item)
                selected_ids.add(id(item))

        return selected

    def _format_knowledge(self, results: List[RetrievedContext], max_items: int = 6) -> str:
        if not results:
            return self.EMPTY_KNOWLEDGE_TEXT

        lines: List[str] = []
        for idx, item in enumerate(results[:max_items], start=1):
            source_kind = self._normalize_source_type(item)
            source = item.filename or item.source_type or "memory"
            summary = item.summary or item.content or ""
            summary = self._clip_text(summary, 350)
            lines.append(
                f"{idx}. [{source_kind}] {source} (relevance: {float(item.similarity or 0.0):.2f}) - {summary}"
            )

        return "\n".join(lines) if lines else self.EMPTY_KNOWLEDGE_TEXT

    @staticmethod
    def _extract_sources(results: List[RetrievedContext], max_items: int = 8) -> List[str]:
        values: List[str] = []
        seen = set()
        for item in results[: max_items * 2]:
            source_kind = CodeWorkspaceContextService._normalize_source_type(item)
            source_name = (item.filename or item.source_type or "").strip()
            source = f"{source_kind}:{source_name}" if source_name else source_kind
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
                top_k=max(4, min(top_k * 3, 20)),
                similarity_threshold=0.35,
            )
        except Exception:
            return self.EMPTY_KNOWLEDGE_TEXT, []

        filtered_rows = self._filter_relevant_knowledge(
            context_rows,
            query=query,
            max_items=max(1, min(top_k, 10)),
        )

        if explicit_context and explicit_context.strip():
            explicit_row = RetrievedContext(
                chunk_id="explicit-context",
                document_id="explicit-context",
                content=str(explicit_context),
                filename="Explicit context",
                file_type="text",
                similarity=1.0,
                source_type="docs",
            )
            filtered_rows = [explicit_row] + filtered_rows

        return self._format_knowledge(filtered_rows), self._extract_sources(filtered_rows)

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
            f"Code: {safe_code}\n\n"
            f"Task: {safe_task}"
        )


code_workspace_context_service = CodeWorkspaceContextService()
