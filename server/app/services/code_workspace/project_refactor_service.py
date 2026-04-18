"""
project_refactor_service.py - AI project-wide refactor engine.
"""

from __future__ import annotations

import ast
import json
import re
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from app.core.config import settings
from app.schemas.code import (
    ProjectRefactorFile,
    ProjectRefactorRequest,
    ProjectRefactorResponse,
    ProjectRefactorUpdatedFile,
)
from app.services.llama_service import llama_service


@dataclass
class _CacheEntry:
    expires_at: float
    value: ProjectRefactorResponse


class ProjectRefactorEngineService:
    """Refactors a set of project files with conservative safety checks."""

    JS_EXPORT_FN_RE = re.compile(
        r"^\s*export\s+(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
        re.MULTILINE,
    )
    JS_EXPORT_CLASS_RE = re.compile(
        r"^\s*export\s+class\s+([A-Za-z_][A-Za-z0-9_]*)",
        re.MULTILINE,
    )
    JS_EXPORT_VAR_RE = re.compile(
        r"^\s*export\s+(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)",
        re.MULTILINE,
    )
    JS_EXPORT_LIST_RE = re.compile(r"^\s*export\s*\{([^}]*)\}", re.MULTILINE)
    JS_MODULE_EXPORTS_RE = re.compile(r"module\.exports\s*=\s*\{([^}]*)\}", re.MULTILINE)

    def __init__(self) -> None:
        self._cache: Dict[str, _CacheEntry] = {}

    @staticmethod
    def _dedupe(values: Iterable[str]) -> List[str]:
        unique: List[str] = []
        seen = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
        return unique

    @staticmethod
    def _normalize_text(value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _clip(value: str, max_chars: int) -> str:
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        head = int(max_chars * 0.75)
        tail = max_chars - head
        return f"{text[:head]}\n...\n{text[-tail:]}"

    @staticmethod
    def _extract_json_block(raw: str) -> Optional[Dict[str, Any]]:
        text = str(raw or "").strip()
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

    def _cache_key(self, request: ProjectRefactorRequest, user_id: str) -> str:
        file_fingerprints = [
            {
                "path": file.path,
                "content_sha": sha256((file.content or "").encode("utf-8")).hexdigest(),
            }
            for file in request.files
        ]
        payload = {
            "user_id": user_id,
            "instruction": request.instruction,
            "safe_mode": request.safe_mode,
            "max_files_to_update": request.max_files_to_update,
            "file_fingerprints": file_fingerprints,
        }
        digest = sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        return f"project-refactor:{digest}"

    def _cache_get(self, key: str) -> Optional[ProjectRefactorResponse]:
        entry = self._cache.get(key)
        if not entry:
            return None
        if entry.expires_at < time.time():
            self._cache.pop(key, None)
            return None
        return entry.value

    def _cache_set(self, key: str, value: ProjectRefactorResponse) -> None:
        ttl = max(10, int(settings.PROJECT_REFACTOR_CACHE_TTL_SECONDS))
        self._cache[key] = _CacheEntry(
            expires_at=time.time() + ttl,
            value=value,
        )

        max_items = max(32, int(settings.PROJECT_REFACTOR_CACHE_MAX_ITEMS))
        if len(self._cache) <= max_items:
            return

        stale = sorted(self._cache.items(), key=lambda item: item[1].expires_at)
        for stale_key, _ in stale[: len(self._cache) - max_items]:
            self._cache.pop(stale_key, None)

    @staticmethod
    def _detect_language(path: str, supplied: Optional[str]) -> str:
        if supplied and supplied.strip():
            return supplied.strip().lower()

        ext = Path(path).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".php": "php",
            ".rb": "ruby",
            ".c": "c",
            ".cpp": "cpp",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
            ".scss": "scss",
            ".sql": "sql",
        }
        return mapping.get(ext, "plaintext")

    def _collect_python_public_symbols(self, content: str) -> Set[str]:
        symbols: Set[str] = set()
        try:
            tree = ast.parse(content)
        except Exception:
            return symbols

        explicit_exports: Set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if not node.name.startswith("_"):
                    symbols.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "__all__":
                        if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                            for item in node.value.elts:
                                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                                    explicit_exports.add(item.value)

        if explicit_exports:
            return explicit_exports
        return symbols

    @classmethod
    def _collect_js_public_symbols(cls, content: str) -> Set[str]:
        symbols: Set[str] = set()

        symbols.update(cls.JS_EXPORT_FN_RE.findall(content))
        symbols.update(cls.JS_EXPORT_CLASS_RE.findall(content))
        symbols.update(cls.JS_EXPORT_VAR_RE.findall(content))

        for group in cls.JS_EXPORT_LIST_RE.findall(content):
            for raw_item in group.split(","):
                item = raw_item.strip()
                if not item:
                    continue
                if " as " in item:
                    item = item.split(" as ")[-1].strip()
                symbols.add(item)

        for group in cls.JS_MODULE_EXPORTS_RE.findall(content):
            for raw_item in group.split(","):
                item = raw_item.strip()
                if not item:
                    continue
                if ":" in item:
                    item = item.split(":", 1)[0].strip()
                symbols.add(item)

        if "export default" in content:
            symbols.add("default")

        return {symbol for symbol in symbols if symbol}

    def _collect_public_symbols(self, path: str, content: str) -> Set[str]:
        ext = Path(path).suffix.lower()
        if ext == ".py":
            return self._collect_python_public_symbols(content)
        if ext in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            return self._collect_js_public_symbols(content)
        return set()

    @staticmethod
    def _is_valid_python(content: str) -> bool:
        try:
            ast.parse(content)
            return True
        except Exception:
            return False

    def _validate_update(
        self,
        path: str,
        old_content: str,
        new_content: str,
        safe_mode: bool,
    ) -> Tuple[bool, List[str]]:
        warnings: List[str] = []

        if not new_content.strip() and old_content.strip():
            warnings.append(f"Rejected {path}: generated content was empty.")
            return False, warnings

        if len(old_content) > 400 and len(new_content) < max(80, int(len(old_content) * 0.2)):
            warnings.append(f"Rejected {path}: change looked destructive (large shrink).")
            return False, warnings

        ext = Path(path).suffix.lower()
        if ext == ".py" and self._is_valid_python(old_content) and not self._is_valid_python(new_content):
            warnings.append(f"Rejected {path}: generated Python code has syntax issues.")
            return False, warnings

        if safe_mode:
            old_symbols = self._collect_public_symbols(path, old_content)
            new_symbols = self._collect_public_symbols(path, new_content)
            removed_symbols = sorted(old_symbols - new_symbols)
            if removed_symbols:
                preview = ", ".join(removed_symbols[:8])
                warnings.append(
                    f"Rejected {path}: potential public API removal ({preview})."
                )
                return False, warnings

            similarity = SequenceMatcher(None, old_content, new_content).ratio()
            if len(old_content) > 600 and similarity < 0.12:
                warnings.append(
                    f"Rejected {path}: low similarity score ({similarity:.2f}) indicates risky rewrite."
                )
                return False, warnings

        return True, warnings

    @staticmethod
    def _sanitize_update_content(content: str) -> str:
        return str(content or "").replace("\r\n", "\n")

    def _build_system_prompt(self, safe_mode: bool) -> str:
        safety_instruction = (
            "Preserve behavior and avoid breaking changes. Keep public APIs and exported symbols stable."
            if safe_mode
            else "Prefer safe changes, but allow broader restructuring when necessary."
        )

        return (
            "You are a senior software architect performing project-wide refactors. "
            "Your job is to improve structure, rename unclear local variables, and remove redundancy. "
            f"{safety_instruction} "
            "Return JSON only in this format: "
            '{"explanation":"...","warnings":["..."],"updated_files":[{"path":"...","content":"...","change_summary":"..."}]}. '
            "Return only files that you changed. Do not invent file paths."
        )

    def _build_user_prompt(
        self,
        files: List[ProjectRefactorFile],
        instruction: str,
        safe_mode: bool,
        max_files_to_update: int,
    ) -> Tuple[str, List[str]]:
        warnings: List[str] = []

        max_files_in_prompt = max(1, int(settings.PROJECT_REFACTOR_MAX_FILES_IN_PROMPT))
        max_file_chars = max(1000, int(settings.PROJECT_REFACTOR_MAX_FILE_CHARS_IN_PROMPT))
        max_prompt_chars = max(10000, int(settings.PROJECT_REFACTOR_MAX_PROMPT_CHARS))

        selected_files = sorted(files, key=lambda item: item.path)[:max_files_in_prompt]
        payload_files = []

        for file_item in selected_files:
            clipped = self._clip(file_item.content, max_file_chars)
            if clipped != file_item.content:
                warnings.append(
                    f"Prompt clipping applied to {file_item.path}; full file is still used for validation."
                )
            payload_files.append(
                {
                    "path": file_item.path,
                    "language": self._detect_language(file_item.path, file_item.language),
                    "content": clipped,
                }
            )

        if len(files) > len(selected_files):
            warnings.append(
                f"Only {len(selected_files)} files were included in model context due prompt limits."
            )

        payload = {
            "instruction": instruction,
            "max_files_to_update": max_files_to_update,
            "safe_mode_expected": bool(safe_mode),
            "files": payload_files,
        }

        prompt = json.dumps(payload, ensure_ascii=False, indent=2)
        if len(prompt) > max_prompt_chars:
            prompt = self._clip(prompt, max_prompt_chars)
            warnings.append("Prompt was clipped to configured size limits.")

        return prompt, self._dedupe(warnings)

    def _parse_model_response(
        self,
        raw_text: str,
    ) -> Tuple[List[Dict[str, str]], str, List[str]]:
        parsed = self._extract_json_block(raw_text)
        if not parsed:
            return (
                [],
                "Model response was not structured JSON; no unsafe changes were applied.",
                ["Unable to parse model output as JSON."],
            )

        explanation = self._normalize_text(parsed.get("explanation") or "")
        warnings = [str(item) for item in (parsed.get("warnings") or []) if str(item).strip()]

        candidates_raw = (
            parsed.get("updated_files")
            or parsed.get("files")
            or parsed.get("changes")
            or []
        )
        candidates: List[Dict[str, str]] = []

        if isinstance(candidates_raw, list):
            for item in candidates_raw:
                if not isinstance(item, dict):
                    continue

                path = str(
                    item.get("path")
                    or item.get("file")
                    or item.get("file_path")
                    or ""
                ).strip()
                content = str(
                    item.get("content")
                    or item.get("updated_content")
                    or item.get("code")
                    or ""
                )
                summary = self._normalize_text(
                    item.get("change_summary")
                    or item.get("summary")
                    or item.get("reason")
                    or ""
                )
                if not path:
                    continue

                candidates.append(
                    {
                        "path": path.replace("\\", "/").lstrip("/"),
                        "content": content,
                        "change_summary": summary,
                    }
                )

        if not explanation:
            explanation = "Refactor analysis completed with conservative safeguards."

        return candidates, explanation, self._dedupe(warnings)

    def _apply_deterministic_cleanup(
        self,
        files: List[ProjectRefactorFile],
        max_files_to_update: int,
        safe_mode: bool,
    ) -> List[ProjectRefactorUpdatedFile]:
        updates: List[ProjectRefactorUpdatedFile] = []

        for file_item in files:
            if len(updates) >= max_files_to_update:
                break

            original = str(file_item.content or "")
            cleaned_lines = [line.rstrip() for line in original.replace("\r\n", "\n").split("\n")]

            collapsed: List[str] = []
            blank_streak = 0
            for line in cleaned_lines:
                if line.strip() == "":
                    blank_streak += 1
                    if blank_streak > 2:
                        continue
                else:
                    blank_streak = 0
                collapsed.append(line)

            cleaned = "\n".join(collapsed)

            if cleaned == original:
                continue

            is_safe, _ = self._validate_update(
                file_item.path,
                original,
                cleaned,
                safe_mode=safe_mode,
            )
            if not is_safe:
                continue

            updates.append(
                ProjectRefactorUpdatedFile(
                    path=file_item.path,
                    content=cleaned,
                    change_summary="Removed trailing whitespace and excessive blank lines.",
                    safe=True,
                )
            )

        return updates

    async def refactor_project(
        self,
        request: ProjectRefactorRequest,
        user_id: str,
    ) -> ProjectRefactorResponse:
        cache_key = self._cache_key(request, user_id)
        cached = self._cache_get(cache_key)
        if cached:
            return cached.model_copy(update={"cached": True})

        prompt, prompt_warnings = self._build_user_prompt(
            request.files,
            request.instruction,
            request.safe_mode,
            request.max_files_to_update,
        )

        raw_response = await llama_service.get_ai_response(
            prompt,
            system_prompt=self._build_system_prompt(request.safe_mode),
        )
        candidates, explanation, model_warnings = self._parse_model_response(raw_response)

        warnings = self._dedupe(prompt_warnings + model_warnings)
        input_map = {file_item.path: file_item for file_item in request.files}

        accepted_updates: List[ProjectRefactorUpdatedFile] = []

        for candidate in candidates:
            if len(accepted_updates) >= request.max_files_to_update:
                warnings.append(
                    f"Reached max_files_to_update limit ({request.max_files_to_update})."
                )
                break

            path = candidate["path"]
            source = input_map.get(path)
            if not source:
                warnings.append(f"Ignored unknown file path from model output: {path}")
                continue

            old_content = str(source.content or "")
            new_content = self._sanitize_update_content(candidate["content"])

            if new_content == old_content:
                continue

            is_safe, safety_warnings = self._validate_update(
                path,
                old_content,
                new_content,
                safe_mode=request.safe_mode,
            )
            warnings.extend(safety_warnings)
            if not is_safe:
                continue

            accepted_updates.append(
                ProjectRefactorUpdatedFile(
                    path=path,
                    content=new_content,
                    change_summary=candidate.get("change_summary") or "Refactor applied.",
                    safe=True,
                )
            )

        if not accepted_updates:
            fallback_updates = self._apply_deterministic_cleanup(
                request.files,
                max_files_to_update=request.max_files_to_update,
                safe_mode=request.safe_mode,
            )
            if fallback_updates:
                accepted_updates = fallback_updates
                warnings.append(
                    "No model changes were safely applicable; applied deterministic safe cleanup instead."
                )
                explanation = (
                    explanation
                    + " Conservative formatting cleanup was applied to remove redundant whitespace."
                ).strip()

        response = ProjectRefactorResponse(
            updated_files=accepted_updates,
            explanation=(
                explanation
                if request.include_explanation
                else "Project refactor completed with safe modifications."
            ),
            warnings=self._dedupe(warnings),
            total_input_files=len(request.files),
            changed_files=len(accepted_updates),
            safe_mode=request.safe_mode,
            cached=False,
        )

        self._cache_set(cache_key, response)
        return response


project_refactor_engine_service = ProjectRefactorEngineService()
