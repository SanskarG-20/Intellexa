"""
user_pattern_service.py - Learns user query and coding-style patterns.
Builds lightweight personalization guidance from persisted code memories.
"""

from __future__ import annotations

import json
import re
import time
from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.db.supabase import supabase


@dataclass
class _CachedProfile:
    expires_at: float
    value: Dict[str, Any]


class UserPatternMemoryService:
    """Tracks user query/style patterns and exposes adaptation guidance."""

    QUERY_STOPWORDS = {
        "about", "after", "again", "also", "been", "being", "between", "build",
        "can", "code", "does", "from", "have", "into", "just", "like", "make",
        "need", "only", "other", "please", "should", "some", "than", "that",
        "their", "there", "these", "they", "this", "those", "through", "under",
        "were", "what", "when", "where", "which", "while", "with", "would",
        "your", "you", "help", "want", "using", "used", "fix", "write",
    }

    IDENTIFIER_STOPWORDS = {
        "if", "else", "for", "while", "return", "class", "function", "const", "let",
        "var", "def", "async", "await", "try", "except", "import", "from", "None",
        "true", "false", "null", "undefined", "new", "public", "private", "protected",
        "static", "final", "switch", "case", "break", "continue", "default", "in",
        "of", "and", "or", "not", "pass", "with", "lambda",
    }

    SEMICOLON_LANGUAGES = {
        "javascript", "typescript", "java", "c", "cpp", "csharp", "php", "rust", "go",
    }

    def __init__(self) -> None:
        self._cache: Dict[str, _CachedProfile] = {}

    @staticmethod
    def _normalize_text(value: str, *, max_chars: int = 600) -> str:
        normalized = " ".join(str(value or "").split()).strip()
        return normalized[:max_chars]

    @staticmethod
    def _safe_dict(value: Any) -> Dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _dominant(counter: Counter, *, min_count: int = 2, min_ratio: float = 0.45) -> str:
        if not counter:
            return "unknown"

        value, count = counter.most_common(1)[0]
        total = sum(counter.values())
        if count < min_count:
            return "unknown"
        if total <= 0:
            return "unknown"
        if (count / total) < min_ratio:
            return "mixed"
        return str(value)

    def _extract_query_terms(self, query: str, *, max_terms: int = 12) -> List[str]:
        words = re.findall(r"[a-z0-9_]{3,}", str(query or "").lower())
        filtered = [word for word in words if word not in self.QUERY_STOPWORDS]

        counts = Counter(filtered)
        return [term for term, _ in counts.most_common(max_terms)]

    def _detect_indentation(self, code: str) -> str:
        tab_lines = 0
        space_indents: Counter[int] = Counter()

        for raw_line in str(code or "").splitlines():
            if not raw_line.strip():
                continue

            indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]
            if not indent:
                continue

            if "\t" in indent:
                tab_lines += 1
                continue

            space_count = len(indent)
            if space_count > 0:
                space_indents[space_count] += 1

        space_lines = sum(space_indents.values())
        if tab_lines == 0 and space_lines == 0:
            return "unknown"

        if tab_lines > space_lines:
            return "tabs"

        if not space_indents:
            return "mixed"

        common_indent = space_indents.most_common(1)[0][0]
        if common_indent <= 2:
            return "spaces_2"
        if common_indent <= 4:
            return "spaces_4"
        return "spaces_4"

    def _detect_quote_style(self, code: str) -> str:
        text = str(code or "")
        single = len(re.findall(r"'[^'\n]{0,120}'", text))
        double = len(re.findall(r'"[^"\n]{0,120}"', text))

        if single == 0 and double == 0:
            return "unknown"

        if single >= (double * 1.4):
            return "single"
        if double >= (single * 1.4):
            return "double"
        return "mixed"

    def _detect_semicolon_style(self, code: str, language: str) -> str:
        if str(language or "").lower() not in self.SEMICOLON_LANGUAGES:
            return "not_applicable"

        candidates: List[str] = []
        for raw_line in str(code or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("//") or line.startswith("#"):
                continue
            if line in {"{", "}", "};"}:
                continue
            candidates.append(line)

        if not candidates:
            return "unknown"

        semicolons = sum(1 for line in candidates if line.endswith(";"))
        ratio = semicolons / len(candidates)

        if ratio >= 0.75:
            return "prefer"
        if ratio <= 0.25:
            return "avoid"
        return "mixed"

    def _detect_naming_style(self, code: str) -> str:
        text = str(code or "")

        names: List[str] = []
        names.extend(re.findall(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        names.extend(re.findall(r"function\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        names.extend(re.findall(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)", text))
        names.extend(re.findall(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", text))

        if not names:
            names.extend(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", text))

        filtered = [name for name in names if name not in self.IDENTIFIER_STOPWORDS]
        if not filtered:
            return "unknown"

        votes = Counter()
        for name in filtered[:120]:
            if "_" in name and name.lower() == name:
                votes["snake_case"] += 1
            elif name[:1].islower() and any(char.isupper() for char in name):
                votes["camelCase"] += 1
            elif name[:1].isupper() and any(char.islower() for char in name):
                votes["PascalCase"] += 1

        if not votes:
            return "unknown"
        return self._dominant(votes, min_count=3, min_ratio=0.40)

    def analyze_code_style(self, code: str, language: str) -> Dict[str, str]:
        snippet = str(code or "")
        if not snippet.strip():
            return {
                "indentation": "unknown",
                "quotes": "unknown",
                "semicolons": "unknown",
                "naming": "unknown",
            }

        return {
            "indentation": self._detect_indentation(snippet),
            "quotes": self._detect_quote_style(snippet),
            "semicolons": self._detect_semicolon_style(snippet, language),
            "naming": self._detect_naming_style(snippet),
        }

    def build_interaction_metadata(
        self,
        *,
        query: str,
        code: str,
        language: str,
        action: str,
        suggestions: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        normalized_query = self._normalize_text(query, max_chars=600)
        normalized_language = str(language or "").strip().lower()[:50]
        normalized_action = str(action or "").strip().lower()[:40]

        return {
            "query_text": normalized_query,
            "query_keywords": self._extract_query_terms(normalized_query),
            "language": normalized_language,
            "action": normalized_action,
            "style_profile": self.analyze_code_style(code, normalized_language),
            "suggestion_titles": [self._normalize_text(item, max_chars=80) for item in (suggestions or [])[:6]],
        }

    def mark_profile_dirty(self, user_id: str) -> None:
        self._cache.pop(str(user_id or ""), None)

    async def _fetch_recent_code_memory_rows(self, user_id: str) -> List[Dict[str, Any]]:
        if not supabase:
            return []

        max_rows = max(10, min(int(settings.USER_PATTERN_MAX_MEMORY_ROWS), 200))

        try:
            response = (
                supabase.table("agent_memories")
                .select("metadata, created_at")
                .eq("user_id", user_id)
                .eq("source_type", "code")
                .order("created_at", desc=True)
                .limit(max_rows)
                .execute()
            )
            return list(response.data or [])
        except Exception:
            return []

    async def _build_profile(self, user_id: str) -> Dict[str, Any]:
        rows = await self._fetch_recent_code_memory_rows(user_id)

        query_terms = Counter()
        actions = Counter()
        languages = Counter()
        indentation = Counter()
        quotes = Counter()
        semicolons = Counter()
        naming = Counter()

        for row in rows:
            metadata = self._safe_dict(row.get("metadata"))

            for term in metadata.get("query_keywords") or []:
                text = str(term or "").strip().lower()
                if text:
                    query_terms[text] += 1

            action = str(metadata.get("action") or "").strip().lower()
            if action:
                actions[action] += 1

            language = str(metadata.get("language") or "").strip().lower()
            if language:
                languages[language] += 1

            style = self._safe_dict(metadata.get("style_profile"))
            indent = str(style.get("indentation") or "").strip().lower()
            quote = str(style.get("quotes") or "").strip().lower()
            semi = str(style.get("semicolons") or "").strip().lower()
            naming_style = str(style.get("naming") or "").strip()

            if indent and indent not in {"unknown", "mixed"}:
                indentation[indent] += 1
            if quote and quote not in {"unknown", "mixed"}:
                quotes[quote] += 1
            if semi and semi not in {"unknown", "mixed", "not_applicable"}:
                semicolons[semi] += 1
            if naming_style and naming_style not in {"unknown", "mixed"}:
                naming[naming_style] += 1

        max_terms = max(3, min(int(settings.USER_PATTERN_MAX_QUERY_TERMS), 20))
        top_terms = [term for term, _ in query_terms.most_common(max_terms)]
        common_actions = [term for term, _ in actions.most_common(4)]
        dominant_language = languages.most_common(1)[0][0] if languages else ""

        style_preferences = {
            "indentation": self._dominant(indentation),
            "quotes": self._dominant(quotes),
            "semicolons": self._dominant(semicolons),
            "naming": self._dominant(naming),
        }

        profile = {
            "interactions": len(rows),
            "top_query_terms": top_terms,
            "common_actions": common_actions,
            "dominant_language": dominant_language,
            "style_preferences": style_preferences,
        }

        profile_signature = sha256(
            json.dumps(profile, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()[:16]

        profile["signature"] = profile_signature
        return profile

    def _build_guidance(self, profile: Dict[str, Any], language: str) -> str:
        min_interactions = max(1, int(settings.USER_PATTERN_MIN_INTERACTIONS))
        interactions = int(profile.get("interactions") or 0)
        if interactions < min_interactions:
            return ""

        style = self._safe_dict(profile.get("style_preferences"))
        terms = list(profile.get("top_query_terms") or [])
        actions = list(profile.get("common_actions") or [])
        dominant_language = str(profile.get("dominant_language") or "").strip()

        lines: List[str] = [
            "User Pattern Profile:",
            f"- Prior interactions analyzed: {interactions}",
        ]

        if terms:
            lines.append(f"- Frequent query themes: {', '.join(terms[:6])}")
        if actions:
            lines.append(f"- Frequent actions: {', '.join(actions[:4])}")

        style_hints = []
        if style.get("indentation") not in {"", "unknown", "mixed"}:
            style_hints.append(f"indentation={style['indentation']}")
        if style.get("quotes") not in {"", "unknown", "mixed"}:
            style_hints.append(f"quotes={style['quotes']}")
        if style.get("semicolons") not in {"", "unknown", "mixed", "not_applicable"}:
            style_hints.append(f"semicolons={style['semicolons']}")
        if style.get("naming") not in {"", "unknown", "mixed"}:
            style_hints.append(f"naming={style['naming']}")

        if style_hints:
            lines.append(f"- Coding style preferences: {', '.join(style_hints)}")

        if dominant_language and dominant_language != str(language or "").strip().lower():
            lines.append(f"- Typical language in past requests: {dominant_language}")

        lines.append("- Adapt suggestions to these preferences unless current instructions conflict.")
        return "\n".join(lines)

    async def get_adaptation_context(self, *, user_id: str, language: str) -> Dict[str, Any]:
        if not settings.USER_PATTERN_ENABLED:
            return {
                "signature": "disabled",
                "guidance": "",
                "style_preferences": {},
                "interactions": 0,
            }

        safe_user_id = str(user_id or "").strip()
        if not safe_user_id:
            return {
                "signature": "anonymous",
                "guidance": "",
                "style_preferences": {},
                "interactions": 0,
            }

        cached = self._cache.get(safe_user_id)
        now = time.time()
        if cached and cached.expires_at >= now:
            profile = dict(cached.value)
        else:
            profile = await self._build_profile(safe_user_id)
            ttl = max(10, int(settings.USER_PATTERN_CACHE_TTL_SECONDS))
            self._cache[safe_user_id] = _CachedProfile(
                expires_at=now + ttl,
                value=dict(profile),
            )

        return {
            "signature": str(profile.get("signature") or "none"),
            "guidance": self._build_guidance(profile, language),
            "style_preferences": self._safe_dict(profile.get("style_preferences")),
            "interactions": int(profile.get("interactions") or 0),
        }

    @staticmethod
    def build_style_hint(style_preferences: Dict[str, Any], language: str) -> str:
        style = style_preferences if isinstance(style_preferences, dict) else {}

        parts: List[str] = []
        indentation = str(style.get("indentation") or "").strip().lower()
        quotes = str(style.get("quotes") or "").strip().lower()
        semicolons = str(style.get("semicolons") or "").strip().lower()
        naming = str(style.get("naming") or "").strip()

        if indentation in {"spaces_2", "spaces_4", "tabs"}:
            parts.append(indentation.replace("_", " "))
        if quotes in {"single", "double"}:
            parts.append(f"{quotes} quotes")

        if semicolons == "prefer":
            parts.append("keep semicolons")
        elif semicolons == "avoid":
            parts.append("minimal semicolons")

        if naming and naming not in {"unknown", "mixed"}:
            parts.append(f"{naming} naming")

        if not parts:
            return ""

        prefix = str(language or "").strip().lower()
        if prefix:
            return f"Style match ({prefix}): {', '.join(parts)}."
        return f"Style match: {', '.join(parts)}."

    @staticmethod
    def apply_style_to_code_snippet(snippet: str, style_preferences: Dict[str, Any], language: str) -> str:
        text = str(snippet or "")
        style = style_preferences if isinstance(style_preferences, dict) else {}
        normalized_language = str(language or "").strip().lower()

        indentation = str(style.get("indentation") or "").strip().lower()
        if indentation in {"spaces_2", "spaces_4"}:
            spaces = 2 if indentation == "spaces_2" else 4
            text = re.sub(r"^(\t+)", lambda m: " " * (spaces * len(m.group(1))), text, flags=re.MULTILINE)

        if normalized_language in UserPatternMemoryService.SEMICOLON_LANGUAGES:
            semicolons = str(style.get("semicolons") or "").strip().lower()
            if semicolons == "avoid":
                text = re.sub(r";\s*$", "", text, flags=re.MULTILINE)

            quotes = str(style.get("quotes") or "").strip().lower()
            if quotes == "single":
                text = re.sub(r'"([A-Za-z0-9_ ./:-]{1,60})"', r"'\1'", text)

        return text[:500]


user_pattern_memory_service = UserPatternMemoryService()
