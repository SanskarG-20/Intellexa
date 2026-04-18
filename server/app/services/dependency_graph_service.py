"""
dependency_graph_service.py - Build and cache file/function dependency graphs.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from app.core.config import settings
from app.services.project_context_service import ParsedRecord, project_context_service


class DependencyGraphService:
    """Creates a frontend-ready graph from indexed repository context."""

    def __init__(self) -> None:
        self.cache_ttl_seconds = max(15, int(settings.DEPENDENCY_GRAPH_CACHE_TTL_SECONDS))
        self.default_max_nodes = max(200, int(settings.DEPENDENCY_GRAPH_MAX_NODES))
        self.default_max_edges = max(500, int(settings.DEPENDENCY_GRAPH_MAX_EDGES))
        self.default_include_external_nodes = bool(settings.DEPENDENCY_GRAPH_INCLUDE_EXTERNAL_NODES)

        self._cached_payload: Dict[str, Any] = {}
        self._cache_key: str = ""
        self._last_built_ts: float = 0.0
        self._lock = asyncio.Lock()

    @staticmethod
    def _file_node_id(file_path: str) -> str:
        return f"file:{file_path}"

    @staticmethod
    def _function_node_id(file_path: str, symbol: str) -> str:
        return f"function:{file_path}::{symbol}"

    @staticmethod
    def _external_file_node_id(label: str) -> str:
        return f"external:file:{label}"

    @staticmethod
    def _external_function_node_id(label: str) -> str:
        return f"external:function:{label}"

    @staticmethod
    def _dedupe(values: List[str]) -> List[str]:
        seen = set()
        unique: List[str] = []
        for item in values:
            value = str(item or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            unique.append(value)
        return unique

    @staticmethod
    def _symbol_tail(symbol: str) -> str:
        normalized = str(symbol or "").strip()
        if not normalized:
            return ""
        return normalized.split(".")[-1]

    @staticmethod
    def _normalize_call_symbol(symbol: str) -> str:
        normalized = str(symbol or "").strip()
        if not normalized:
            return ""

        normalized = normalized.removeprefix("self.")
        normalized = normalized.removeprefix("this.")
        normalized = normalized.removeprefix("window.")
        normalized = normalized.removeprefix("globalThis.")
        normalized = normalized.strip(". ")
        return normalized

    @staticmethod
    def _node_group_for_file(file_path: str) -> str:
        parts = file_path.split("/")
        if len(parts) <= 1:
            return "."
        return "/".join(parts[:-1])

    def _resolve_callee_node(
        self,
        *,
        current_file: str,
        callee_symbol: str,
        function_nodes_by_key: Dict[str, List[str]],
        function_node_by_exact: Dict[Tuple[str, str], str],
        function_node_file: Dict[str, str],
    ) -> Optional[str]:
        normalized = self._normalize_call_symbol(callee_symbol)
        if not normalized:
            return None

        exact_local = function_node_by_exact.get((current_file, normalized))
        if exact_local:
            return exact_local

        tail = self._symbol_tail(normalized)
        local_candidates = []
        for key in [normalized, tail]:
            for node_id in function_nodes_by_key.get(key, []):
                if function_node_file.get(node_id) == current_file:
                    local_candidates.append(node_id)
        if len(local_candidates) == 1:
            return local_candidates[0]

        for key in [normalized, tail]:
            candidates = function_nodes_by_key.get(key, [])
            if len(candidates) == 1:
                return candidates[0]

        return None

    def _build_graph_payload(
        self,
        records_by_path: Dict[str, ParsedRecord],
        include_external_nodes: bool,
        max_nodes: int,
        max_edges: int,
    ) -> Dict[str, Any]:
        node_limit = max(100, min(max_nodes, 50000))
        edge_limit = max(100, min(max_edges, 120000))

        nodes: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []
        edge_seen: Set[Tuple[str, str, str]] = set()
        truncated = False

        file_dependency_mapping: Dict[str, List[str]] = {}
        function_dependency_mapping: Dict[str, List[str]] = {}

        function_node_by_exact: Dict[Tuple[str, str], str] = {}
        function_nodes_by_key: Dict[str, List[str]] = {}
        function_node_file: Dict[str, str] = {}

        def add_node(
            node_id: str,
            *,
            label: str,
            node_type: str,
            group: Optional[str] = None,
            file_path: Optional[str] = None,
            metadata: Optional[Dict[str, Any]] = None,
        ) -> bool:
            nonlocal truncated
            if node_id in nodes:
                return True
            if len(nodes) >= node_limit:
                truncated = True
                return False
            nodes[node_id] = {
                "id": node_id,
                "label": label,
                "type": node_type,
                "group": group,
                "file_path": file_path,
                "metadata": metadata or {},
            }
            return True

        def add_edge(
            source: str,
            target: str,
            relation_type: str,
            metadata: Optional[Dict[str, Any]] = None,
            weight: float = 1.0,
        ) -> None:
            nonlocal truncated
            if source == target:
                return
            key = (source, target, relation_type)
            if key in edge_seen:
                return
            if len(edges) >= edge_limit:
                truncated = True
                return

            edge_seen.add(key)
            edge_id = f"edge:{len(edges) + 1}"
            edges.append(
                {
                    "id": edge_id,
                    "source": source,
                    "target": target,
                    "relation_type": relation_type,
                    "weight": weight,
                    "metadata": metadata or {},
                }
            )

            if relation_type == "calls":
                function_dependency_mapping.setdefault(source, []).append(target)

        sorted_records = sorted(records_by_path.items(), key=lambda item: item[0])

        for file_path, record in sorted_records:
            file_node_id = self._file_node_id(file_path)
            add_node(
                file_node_id,
                label=file_path,
                node_type="file",
                group=self._node_group_for_file(file_path),
                file_path=file_path,
                metadata={
                    "imports": len(record.imports),
                    "functions": len(record.functions),
                    "classes": len(record.classes),
                    "calls": len(record.function_calls),
                },
            )

        for file_path, record in sorted_records:
            file_node_id = self._file_node_id(file_path)
            for function_name in record.functions:
                function_node_id = self._function_node_id(file_path, function_name)
                created = add_node(
                    function_node_id,
                    label=function_name,
                    node_type="function",
                    group=file_path,
                    file_path=file_path,
                    metadata={"symbol": function_name},
                )
                if not created:
                    continue

                function_node_by_exact[(file_path, function_name)] = function_node_id
                function_node_file[function_node_id] = file_path

                short_name = self._symbol_tail(function_name)
                function_nodes_by_key.setdefault(function_name, []).append(function_node_id)
                function_nodes_by_key.setdefault(short_name, []).append(function_node_id)

                add_edge(
                    file_node_id,
                    function_node_id,
                    "defines",
                    metadata={"file_path": file_path},
                )

        for file_path, record in sorted_records:
            source_file_node_id = self._file_node_id(file_path)
            file_dependency_mapping[file_path] = list(record.dependencies)

            imported_targets = set()

            for dependency in record.dependencies:
                imported_targets.add(dependency)
                target_file_node_id = self._file_node_id(dependency)
                if target_file_node_id in nodes:
                    add_edge(
                        source_file_node_id,
                        target_file_node_id,
                        "imports",
                        metadata={"file_path": file_path},
                    )
                    continue

                if not include_external_nodes:
                    continue

                external_node_id = self._external_file_node_id(dependency)
                if add_node(
                    external_node_id,
                    label=dependency,
                    node_type="external",
                    group="external",
                    file_path=None,
                    metadata={"kind": "file"},
                ):
                    add_edge(
                        source_file_node_id,
                        external_node_id,
                        "imports",
                        metadata={"file_path": file_path},
                    )

            if include_external_nodes:
                for import_name in record.imports:
                    normalized_import = str(import_name or "").strip()
                    if not normalized_import:
                        continue
                    if normalized_import in imported_targets:
                        continue

                    external_import_node_id = self._external_file_node_id(normalized_import)
                    if add_node(
                        external_import_node_id,
                        label=normalized_import,
                        node_type="external",
                        group="external",
                        file_path=None,
                        metadata={"kind": "import"},
                    ):
                        add_edge(
                            source_file_node_id,
                            external_import_node_id,
                            "imports",
                            metadata={
                                "file_path": file_path,
                                "import": normalized_import,
                            },
                        )

        for file_path, record in sorted_records:
            source_file_node_id = self._file_node_id(file_path)

            for caller_symbol, callee_symbols in record.call_mapping.items():
                source_node_id = source_file_node_id
                if caller_symbol and caller_symbol != "__module__":
                    source_node_id = function_node_by_exact.get((file_path, caller_symbol), source_file_node_id)

                for raw_callee_symbol in callee_symbols:
                    target_node_id = self._resolve_callee_node(
                        current_file=file_path,
                        callee_symbol=raw_callee_symbol,
                        function_nodes_by_key=function_nodes_by_key,
                        function_node_by_exact=function_node_by_exact,
                        function_node_file=function_node_file,
                    )

                    if not target_node_id and include_external_nodes:
                        normalized_callee = self._normalize_call_symbol(raw_callee_symbol)
                        if normalized_callee:
                            target_node_id = self._external_function_node_id(normalized_callee)
                            add_node(
                                target_node_id,
                                label=normalized_callee,
                                node_type="external",
                                group="external",
                                file_path=None,
                                metadata={"kind": "function"},
                            )

                    if target_node_id:
                        add_edge(
                            source_node_id,
                            target_node_id,
                            "calls",
                            metadata={
                                "caller": caller_symbol,
                                "callee": raw_callee_symbol,
                                "file_path": file_path,
                            },
                        )

        function_dependency_mapping = {
            source: self._dedupe(targets)
            for source, targets in function_dependency_mapping.items()
        }

        return {
            "truncated": truncated,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "nodes": list(nodes.values()),
            "edges": edges,
            "file_dependency_mapping": file_dependency_mapping,
            "function_dependency_mapping": function_dependency_mapping,
            "legend": {
                "file": "Source file node",
                "function": "Function or method declared in project",
                "external": "Dependency outside scanned files",
                "imports": "File imports another file/module",
                "defines": "File defines function",
                "calls": "Function (or file scope) calls function",
            },
        }

    async def get_dependency_graph(
        self,
        *,
        refresh: bool = False,
        include_external_nodes: Optional[bool] = None,
        max_nodes: Optional[int] = None,
        max_edges: Optional[int] = None,
    ) -> Dict[str, Any]:
        include_external = self.default_include_external_nodes if include_external_nodes is None else bool(include_external_nodes)
        bounded_max_nodes = self.default_max_nodes if max_nodes is None else max(100, int(max_nodes))
        bounded_max_edges = self.default_max_edges if max_edges is None else max(100, int(max_edges))

        async with self._lock:
            await project_context_service.ensure_index(refresh=refresh)
            generated_at = project_context_service.get_generated_at()
            records = project_context_service.get_records_snapshot()

            cache_key = (
                f"{generated_at.isoformat()}|"
                f"{include_external}|{bounded_max_nodes}|{bounded_max_edges}"
            )

            graph_cache_hit = (
                not refresh
                and bool(self._cached_payload)
                and cache_key == self._cache_key
                and (time.time() - self._last_built_ts) < self.cache_ttl_seconds
            )

            if graph_cache_hit:
                payload = dict(self._cached_payload)
            else:
                payload = self._build_graph_payload(
                    records,
                    include_external_nodes=include_external,
                    max_nodes=bounded_max_nodes,
                    max_edges=bounded_max_edges,
                )
                self._cached_payload = dict(payload)
                self._cache_key = cache_key
                self._last_built_ts = time.time()

            payload["generated_at"] = generated_at
            payload["cache_hit"] = graph_cache_hit
            return payload


dependency_graph_service = DependencyGraphService()
