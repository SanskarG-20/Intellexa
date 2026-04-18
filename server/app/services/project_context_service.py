"""
project_context_service.py - Project Context Engine

Scans the repository, extracts structure and symbols, maps dependencies,
and stores context records with embeddings for AI retrieval.
"""

from __future__ import annotations

import ast
import asyncio
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.core.config import settings
from app.services.memory.embedding_service import embedding_service


JS_IMPORT_RE = re.compile(
    r"^\s*import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]",
    re.MULTILINE,
)
JS_REQUIRE_RE = re.compile(
    r"require\(\s*['\"]([^'\"]+)['\"]\s*\)",
    re.MULTILINE,
)
JS_FUNCTION_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)
JS_ARROW_RE = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
    re.MULTILINE,
)
JS_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?class\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


@dataclass
class ParsedRecord:
    file_path: str
    summary: str
    imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    embedding: List[float] = field(default_factory=list)
    signature: str = ""


class ProjectContextService:
    """Indexes project-wide code context with chunked processing and caching."""

    CODE_EXTENSIONS = {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".java",
        ".go",
        ".rs",
        ".php",
        ".rb",
        ".swift",
        ".kt",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
        ".cs",
        ".json",
        ".yaml",
        ".yml",
        ".md",
        ".sql",
        ".sh",
        ".css",
        ".scss",
        ".html",
    }

    RESOLVABLE_JS_EXTENSIONS = (
        "",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        "/index.js",
        "/index.ts",
        "/index.tsx",
    )

    EXCLUDED_DIRS = {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "__pycache__",
        ".next",
        ".cache",
        ".vscode",
    }

    def __init__(self) -> None:
        self.project_root = Path(__file__).resolve().parents[3]
        self.max_files = max(200, int(settings.PROJECT_CONTEXT_MAX_FILES))
        self.max_file_size_bytes = max(4 * 1024, int(settings.PROJECT_CONTEXT_MAX_FILE_SIZE_KB) * 1024)
        self.batch_size = max(10, int(settings.PROJECT_CONTEXT_BATCH_SIZE))
        self.cache_ttl_seconds = max(30, int(settings.PROJECT_CONTEXT_CACHE_TTL_SECONDS))
        self.default_include_embeddings = bool(settings.PROJECT_CONTEXT_INCLUDE_EMBEDDINGS_BY_DEFAULT)

        self._records_by_path: Dict[str, ParsedRecord] = {}
        self._file_structure: Dict[str, Any] = {}
        self._dependency_mapping: Dict[str, List[str]] = {}
        self._generated_at: datetime = datetime.now(timezone.utc)
        self._last_scan_ts: float = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _chunked(items: List[Any], chunk_size: int) -> Iterable[List[Any]]:
        for start in range(0, len(items), chunk_size):
            yield items[start : start + chunk_size]

    def _should_scan(self, refresh: bool) -> bool:
        if refresh:
            return True
        if not self._records_by_path:
            return True
        return (time.time() - self._last_scan_ts) >= self.cache_ttl_seconds

    def _is_candidate_file(self, path: Path) -> bool:
        if path.suffix.lower() not in self.CODE_EXTENSIONS:
            return False
        try:
            if path.stat().st_size > self.max_file_size_bytes:
                return False
        except OSError:
            return False
        return True

    def _scan_files(self) -> List[Tuple[Path, str]]:
        scanned: List[Tuple[Path, str]] = []

        for root, dirs, files in os.walk(self.project_root):
            dirs[:] = [
                name
                for name in dirs
                if name not in self.EXCLUDED_DIRS and not name.startswith(".pytest")
            ]

            root_path = Path(root)
            for filename in files:
                file_path = root_path / filename
                if not self._is_candidate_file(file_path):
                    continue

                rel_path = file_path.relative_to(self.project_root).as_posix()
                scanned.append((file_path, rel_path))
                if len(scanned) >= self.max_files:
                    return scanned

        return scanned

    @staticmethod
    def _signature(path: Path) -> str:
        stat = path.stat()
        return f"{stat.st_size}:{stat.st_mtime_ns}"

    @staticmethod
    def _read_text(path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="ignore")

    @staticmethod
    def _dedupe(values: Iterable[str], max_items: int = 128) -> List[str]:
        unique: List[str] = []
        seen = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            unique.append(normalized)
            if len(unique) >= max_items:
                break
        return unique

    def _parse_python(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        imports: List[str] = []
        functions: List[str] = []
        classes: List[str] = []

        try:
            tree = ast.parse(content)
        except Exception:
            return imports, functions, classes

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                base = "." * node.level + (node.module or "")
                imports.append(base)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                functions.append(node.name)
            elif isinstance(node, ast.ClassDef):
                classes.append(node.name)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        functions.append(f"{node.name}.{child.name}")

        return self._dedupe(imports), self._dedupe(functions), self._dedupe(classes)

    def _parse_js_like(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        imports = self._dedupe(JS_IMPORT_RE.findall(content) + JS_REQUIRE_RE.findall(content))
        functions = self._dedupe(JS_FUNCTION_RE.findall(content) + JS_ARROW_RE.findall(content))
        classes = self._dedupe(JS_CLASS_RE.findall(content))
        return imports, functions, classes

    def _parse_generic(self, content: str) -> Tuple[List[str], List[str], List[str]]:
        imports = self._dedupe(JS_IMPORT_RE.findall(content))
        return imports, [], []

    def _build_summary(
        self,
        file_path: str,
        imports: List[str],
        functions: List[str],
        classes: List[str],
    ) -> str:
        suffix = Path(file_path).suffix.lower() or "text"
        symbols = self._dedupe(classes + functions, max_items=5)
        symbol_preview = ", ".join(symbols) if symbols else "none"
        return (
            f"{suffix} file with {len(imports)} imports, "
            f"{len(functions)} functions, {len(classes)} classes. "
            f"Symbols: {symbol_preview}."
        )

    def _parse_file(self, path: Path, rel_path: str, signature: str) -> ParsedRecord:
        content = self._read_text(path)
        suffix = path.suffix.lower()

        if suffix == ".py":
            imports, functions, classes = self._parse_python(content)
        elif suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            imports, functions, classes = self._parse_js_like(content)
        else:
            imports, functions, classes = self._parse_generic(content)

        summary = self._build_summary(rel_path, imports, functions, classes)

        return ParsedRecord(
            file_path=rel_path,
            summary=summary,
            imports=imports,
            functions=functions,
            classes=classes,
            signature=signature,
        )

    def _build_module_index(self, file_paths: Iterable[str]) -> Dict[str, str]:
        index: Dict[str, str] = {}
        for rel in file_paths:
            rel_path = Path(rel)
            no_ext = rel_path.with_suffix("").as_posix()
            dotted = no_ext.replace("/", ".")
            index[dotted] = rel
            index[rel_path.stem] = index.get(rel_path.stem, rel)
        return index

    def _resolve_relative_js(self, current_file: str, import_name: str) -> Optional[str]:
        current_dir = (self.project_root / Path(current_file).parent).resolve()
        for ext in self.RESOLVABLE_JS_EXTENSIONS:
            candidate = (current_dir / f"{import_name}{ext}").resolve()
            try:
                rel = candidate.relative_to(self.project_root).as_posix()
            except ValueError:
                continue
            if rel in self._records_by_path:
                return rel
        return None

    @staticmethod
    def _resolve_relative_python_module(current_file: str, import_name: str) -> str:
        level = len(import_name) - len(import_name.lstrip("."))
        suffix = import_name[level:].strip(".")
        current_module_parts = Path(current_file).with_suffix("").as_posix().split("/")

        if level > 0:
            base_parts = current_module_parts[:-level]
        else:
            base_parts = current_module_parts

        if suffix:
            base_parts.extend(suffix.split("."))

        return ".".join(part for part in base_parts if part)

    def _map_dependencies(self) -> None:
        module_index = self._build_module_index(self._records_by_path.keys())
        dependency_map: Dict[str, List[str]] = {}

        for rel_path, record in self._records_by_path.items():
            resolved: List[str] = []

            for module_name in record.imports:
                if module_name.startswith("."):
                    python_target = self._resolve_relative_python_module(rel_path, module_name)
                    if python_target in module_index:
                        resolved.append(module_index[python_target])
                    continue

                if module_name.startswith("./") or module_name.startswith("../"):
                    js_target = self._resolve_relative_js(rel_path, module_name)
                    if js_target:
                        resolved.append(js_target)
                    continue

                if module_name in module_index:
                    resolved.append(module_index[module_name])

            record.dependencies = self._dedupe(resolved, max_items=200)
            dependency_map[rel_path] = list(record.dependencies)

        self._dependency_mapping = dependency_map

    async def _embed_changed_records(self, changed_paths: List[str]) -> None:
        changed_records = [self._records_by_path[path] for path in changed_paths if path in self._records_by_path]
        if not changed_records:
            return

        for batch in self._chunked(changed_records, self.batch_size):
            texts = [
                (
                    f"File: {record.file_path}\n"
                    f"Summary: {record.summary}\n"
                    f"Dependencies: {', '.join(record.dependencies[:30])}"
                )
                for record in batch
            ]
            vectors = await embedding_service.embed_batch(texts, skip_failures=False)
            for record, vector in zip(batch, vectors):
                record.embedding = vector or []

    def _build_file_structure(self) -> Dict[str, Any]:
        tree: Dict[str, Any] = {}
        for rel in sorted(self._records_by_path.keys()):
            parts = rel.split("/")
            cursor = tree
            for part in parts[:-1]:
                cursor = cursor.setdefault(part, {})
            cursor.setdefault("__files__", []).append(parts[-1])
        return tree

    async def _reindex(self) -> None:
        scanned_files = self._scan_files()
        signatures: Dict[str, str] = {}
        existing_paths = set(self._records_by_path.keys())
        current_paths = set()

        for path, rel in scanned_files:
            try:
                signature = self._signature(path)
            except OSError:
                continue
            signatures[rel] = signature
            current_paths.add(rel)

        removed_paths = existing_paths - current_paths
        for rel in removed_paths:
            self._records_by_path.pop(rel, None)

        to_parse: List[Tuple[Path, str, str]] = []
        for path, rel in scanned_files:
            signature = signatures.get(rel)
            if not signature:
                continue
            existing = self._records_by_path.get(rel)
            if existing and existing.signature == signature:
                continue
            to_parse.append((path, rel, signature))

        changed_paths: List[str] = []
        for batch in self._chunked(to_parse, self.batch_size):
            for path, rel, signature in batch:
                try:
                    parsed = self._parse_file(path, rel, signature)
                except Exception:
                    continue
                self._records_by_path[rel] = parsed
                changed_paths.append(rel)

        self._map_dependencies()
        await self._embed_changed_records(changed_paths)
        self._file_structure = self._build_file_structure()
        self._generated_at = datetime.now(timezone.utc)
        self._last_scan_ts = time.time()

    async def get_project_context(
        self,
        *,
        refresh: bool = False,
        offset: int = 0,
        limit: int = 200,
        include_embeddings: Optional[bool] = None,
    ) -> Dict[str, Any]:
        include_vectors = self.default_include_embeddings if include_embeddings is None else include_embeddings

        async with self._lock:
            cache_hit = not self._should_scan(refresh)
            if not cache_hit:
                await self._reindex()

            records = sorted(self._records_by_path.values(), key=lambda item: item.file_path)
            bounded_offset = max(0, offset)
            bounded_limit = max(1, min(limit, 2000))
            selected = records[bounded_offset : bounded_offset + bounded_limit]

            files_payload = [
                {
                    "file_path": record.file_path,
                    "summary": record.summary,
                    "dependencies": list(record.dependencies),
                    "imports": list(record.imports),
                    "functions": list(record.functions),
                    "classes": list(record.classes),
                    "embedding": list(record.embedding) if include_vectors else None,
                }
                for record in selected
            ]

            dependency_mapping = {
                record.file_path: list(record.dependencies)
                for record in selected
            }

            return {
                "generated_at": self._generated_at,
                "cache_hit": cache_hit,
                "total_files": len(records),
                "returned_files": len(selected),
                "offset": bounded_offset,
                "limit": bounded_limit,
                "file_structure": self._file_structure,
                "dependency_mapping": dependency_mapping,
                "files": files_payload,
            }


project_context_service = ProjectContextService()
