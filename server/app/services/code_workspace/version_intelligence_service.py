"""
version_intelligence_service.py - Track and analyze code evolution over time.
"""

from __future__ import annotations

import difflib
import hashlib
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from app.db.supabase import supabase
from app.schemas.code import (
    BreakCause,
    CodeBreakAnalysisRequest,
    CodeBreakAnalysisResponse,
    CodeVersionCompareRequest,
    CodeVersionCompareResponse,
    CodeVersionEntry,
    CodeVersionHistoryResponse,
    CodeVersionSnapshotResponse,
    MAX_VERSION_DIFF_CHARS,
)


@dataclass
class _VersionRecord:
    id: str
    file_id: str
    user_id: str
    version_index: int
    content: str
    language: str
    reason: str
    created_at: datetime
    content_hash: str


class VersionIntelligenceService:
    """Tracks file versions and explains regressions between snapshots."""

    TABLE_NAME = "code_file_versions"
    SYMBOL_PATTERNS = [
        re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\("),
        re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b"),
        re.compile(r"^\s*(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*\("),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\("),
    ]

    def __init__(self) -> None:
        self._records: Dict[str, List[_VersionRecord]] = {}
        self._table_available: Optional[bool] = None

    @staticmethod
    def _make_key(user_id: str, file_id: str) -> str:
        return f"{user_id}::{file_id}"

    @staticmethod
    def _hash(content: str) -> str:
        return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()

    @staticmethod
    def _preview(content: str, max_chars: int = 180) -> str:
        normalized = " ".join(str(content or "").split())
        if len(normalized) <= max_chars:
            return normalized
        return normalized[: max_chars - 3] + "..."

    @staticmethod
    def _parse_dt(value) -> datetime:
        if isinstance(value, datetime):
            return value
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except Exception:
            return datetime.utcnow()

    def _to_entry(self, record: _VersionRecord) -> CodeVersionEntry:
        return CodeVersionEntry(
            id=record.id,
            file_id=record.file_id,
            version_index=record.version_index,
            language=record.language,
            reason=record.reason,
            created_at=record.created_at,
            content_hash=record.content_hash,
            content_preview=self._preview(record.content),
        )

    @staticmethod
    def _row_to_record(row: dict) -> _VersionRecord:
        return _VersionRecord(
            id=str(row.get("id") or "").strip(),
            file_id=str(row.get("file_id") or "").strip(),
            user_id=str(row.get("user_id") or "").strip(),
            version_index=int(row.get("version_index") or 1),
            content=str(row.get("content") or ""),
            language=str(row.get("language") or "plaintext"),
            reason=str(row.get("reason") or "manual"),
            created_at=VersionIntelligenceService._parse_dt(row.get("created_at")),
            content_hash=str(row.get("content_hash") or "").strip(),
        )

    def _set_table_unavailable_if_needed(self, exc: Exception) -> None:
        message = str(exc).lower()
        if "code_file_versions" in message and (
            "does not exist" in message or "relation" in message or "not found" in message
        ):
            self._table_available = False

    def _store_local(self, record: _VersionRecord) -> None:
        key = self._make_key(record.user_id, record.file_id)
        values = self._records.setdefault(key, [])
        values.append(record)
        values.sort(key=lambda item: item.version_index)

        # Keep in-memory retention bounded.
        max_entries = 300
        if len(values) > max_entries:
            self._records[key] = values[-max_entries:]

    def _try_insert_remote(self, record: _VersionRecord) -> None:
        if not supabase:
            return
        if self._table_available is False:
            return

        try:
            supabase.table(self.TABLE_NAME).insert(
                {
                    "id": record.id,
                    "file_id": record.file_id,
                    "user_id": record.user_id,
                    "version_index": record.version_index,
                    "content": record.content,
                    "language": record.language,
                    "reason": record.reason,
                    "content_hash": record.content_hash,
                    "created_at": record.created_at.isoformat(),
                }
            ).execute()
            self._table_available = True
        except Exception as exc:
            self._set_table_unavailable_if_needed(exc)

    def _try_list_remote(self, user_id: str, file_id: str, limit: int) -> Optional[List[_VersionRecord]]:
        if not supabase:
            return None
        if self._table_available is False:
            return None

        try:
            response = (
                supabase.table(self.TABLE_NAME)
                .select(
                    "id, file_id, user_id, version_index, content, language, reason, content_hash, created_at"
                )
                .eq("user_id", user_id)
                .eq("file_id", file_id)
                .order("version_index", desc=False)
                .limit(limit)
                .execute()
            )
            self._table_available = True
            rows = response.data or []
            return [self._row_to_record(row) for row in rows]
        except Exception as exc:
            self._set_table_unavailable_if_needed(exc)
            return None

    def _try_get_remote_by_id(self, user_id: str, file_id: str, version_id: str) -> Optional[_VersionRecord]:
        if not supabase:
            return None
        if self._table_available is False:
            return None

        try:
            response = (
                supabase.table(self.TABLE_NAME)
                .select(
                    "id, file_id, user_id, version_index, content, language, reason, content_hash, created_at"
                )
                .eq("user_id", user_id)
                .eq("file_id", file_id)
                .eq("id", version_id)
                .limit(1)
                .execute()
            )
            self._table_available = True
            if not response.data:
                return None
            return self._row_to_record(response.data[0])
        except Exception as exc:
            self._set_table_unavailable_if_needed(exc)
            return None

    def _list_local(self, user_id: str, file_id: str, limit: int) -> List[_VersionRecord]:
        key = self._make_key(user_id, file_id)
        values = self._records.get(key, [])
        return list(values[-limit:])

    def _next_index(self, records: List[_VersionRecord]) -> int:
        if not records:
            return 1
        return max(item.version_index for item in records) + 1

    def _find_record(
        self,
        user_id: str,
        file_id: str,
        version_id: Optional[str],
        *,
        fallback_records: List[_VersionRecord],
    ) -> Optional[_VersionRecord]:
        if not fallback_records:
            return None

        if version_id:
            for item in fallback_records:
                if item.id == version_id:
                    return item
            remote_hit = self._try_get_remote_by_id(user_id, file_id, version_id)
            if remote_hit:
                return remote_hit
            return None

        # Default selection when caller does not specify an ID.
        return fallback_records[-1]

    def track_version(
        self,
        *,
        user_id: str,
        file_id: str,
        content: str,
        language: str,
        reason: str,
    ) -> Optional[CodeVersionEntry]:
        """Persist a version snapshot for a file. Duplicate content hashes are skipped."""
        if not str(file_id or "").strip():
            return None

        safe_content = str(content or "")
        content_hash = self._hash(safe_content)

        # Get baseline list from remote if available, otherwise in-memory cache.
        remote_records = self._try_list_remote(user_id, file_id, limit=300)
        records = remote_records if remote_records is not None else self._list_local(user_id, file_id, limit=300)

        if records:
            latest = records[-1]
            if latest.content_hash == content_hash:
                return self._to_entry(latest)

        record = _VersionRecord(
            id=str(uuid.uuid4()),
            file_id=file_id,
            user_id=user_id,
            version_index=self._next_index(records),
            content=safe_content,
            language=str(language or "plaintext"),
            reason=str(reason or "manual"),
            created_at=datetime.utcnow(),
            content_hash=content_hash,
        )

        self._store_local(record)
        self._try_insert_remote(record)
        return self._to_entry(record)

    def list_versions(
        self,
        *,
        user_id: str,
        file_id: str,
        limit: int,
    ) -> CodeVersionHistoryResponse:
        safe_limit = max(1, min(int(limit or 30), 100))

        remote_records = self._try_list_remote(user_id, file_id, limit=safe_limit)
        records = remote_records if remote_records is not None else self._list_local(user_id, file_id, limit=safe_limit)

        entries = [self._to_entry(item) for item in records]
        entries.sort(key=lambda item: item.version_index, reverse=True)

        return CodeVersionHistoryResponse(
            file_id=file_id,
            versions=entries,
            total=len(entries),
        )

    def get_version_snapshot(
        self,
        *,
        user_id: str,
        file_id: str,
        version_id: str,
    ) -> Optional[CodeVersionSnapshotResponse]:
        records = self._try_list_remote(user_id, file_id, limit=300)
        if records is None:
            records = self._list_local(user_id, file_id, limit=300)

        record = self._find_record(user_id, file_id, version_id, fallback_records=records)
        if not record:
            return None

        return CodeVersionSnapshotResponse(
            version=self._to_entry(record),
            content=record.content,
        )

    @staticmethod
    def _extract_symbols_from_diff(diff_lines: List[str]) -> List[str]:
        symbols = []
        seen = set()

        for line in diff_lines:
            if not line.startswith("+") and not line.startswith("-"):
                continue
            if line.startswith("+++") or line.startswith("---"):
                continue

            body = line[1:]
            for pattern in VersionIntelligenceService.SYMBOL_PATTERNS:
                match = pattern.search(body)
                if match:
                    name = match.group(1)
                    if name and name not in seen:
                        seen.add(name)
                        symbols.append(name)

        return symbols[:25]

    @staticmethod
    def _compute_diff(old: str, new: str, file_id: str) -> Tuple[str, int, int, List[str]]:
        before_lines = str(old or "").splitlines()
        after_lines = str(new or "").splitlines()

        diff_lines = list(
            difflib.unified_diff(
                before_lines,
                after_lines,
                fromfile=f"{file_id}:old",
                tofile=f"{file_id}:new",
                lineterm="",
                n=3,
            )
        )

        added = 0
        removed = 0
        for line in diff_lines:
            if line.startswith("+++") or line.startswith("---") or line.startswith("@@"):
                continue
            if line.startswith("+"):
                added += 1
            elif line.startswith("-"):
                removed += 1

        symbols = VersionIntelligenceService._extract_symbols_from_diff(diff_lines)
        unified = "\n".join(diff_lines)
        if len(unified) > MAX_VERSION_DIFF_CHARS:
            unified = unified[:MAX_VERSION_DIFF_CHARS] + "\n...\n[diff truncated]"

        return unified, added, removed, symbols

    def compare_versions(
        self,
        *,
        user_id: str,
        request: CodeVersionCompareRequest,
    ) -> CodeVersionCompareResponse:
        records = self._try_list_remote(user_id, request.file_id, limit=300)
        if records is None:
            records = self._list_local(user_id, request.file_id, limit=300)

        if len(records) < 2:
            raise ValueError("At least two versions are required to compare changes.")

        from_record = self._find_record(
            user_id,
            request.file_id,
            request.from_version_id,
            fallback_records=records,
        )
        if not from_record:
            # Default baseline: previous version
            from_record = records[-2]

        to_record = self._find_record(
            user_id,
            request.file_id,
            request.to_version_id,
            fallback_records=records,
        )
        if not to_record:
            to_record = records[-1]

        if from_record.id == to_record.id:
            raise ValueError("Please choose two different versions to compare.")

        unified, added, removed, symbols = self._compute_diff(
            from_record.content,
            to_record.content,
            request.file_id,
        )

        summary_parts = [f"Compared v{from_record.version_index} -> v{to_record.version_index}"]
        summary_parts.append(f"+{added} / -{removed} lines")
        if symbols:
            summary_parts.append("Symbols touched: " + ", ".join(symbols[:8]))
        summary = "; ".join(summary_parts)

        return CodeVersionCompareResponse(
            file_id=request.file_id,
            from_version=self._to_entry(from_record),
            to_version=self._to_entry(to_record),
            summary=summary,
            added_lines=added,
            removed_lines=removed,
            changed_symbols=symbols,
            unified_diff=unified,
        )

    @staticmethod
    def _infer_break_causes(
        *,
        compare: CodeVersionCompareResponse,
        failure_context: str,
    ) -> List[BreakCause]:
        causes: List[BreakCause] = []
        context = str(failure_context or "").lower()
        diff_text = str(compare.unified_diff or "").lower()

        if any(token in context for token in ["none", "nonetype", "null", "undefined"]):
            if any(token in diff_text for token in [" is none", "== none", "!= none", "?.", "null", "undefined"]):
                causes.append(
                    BreakCause(
                        title="Null/None handling changed",
                        confidence=0.82,
                        evidence="Failure context references null/None and diff contains guard-condition changes.",
                        recommendation="Audit newly changed branches for missing null checks and add defensive guards.",
                    )
                )

        if any(token in context for token in ["timeout", "promise", "await", "async", "event loop"]):
            if any(token in diff_text for token in ["async", "await", "promise", "then("]):
                causes.append(
                    BreakCause(
                        title="Async control-flow regression",
                        confidence=0.78,
                        evidence="Error mentions async timing and recent diff modified async/await or promise flow.",
                        recommendation="Check awaited calls, timeout values, and unhandled promise branches.",
                    )
                )

        if any(token in context for token in ["import", "module not found", "cannot find", "nameerror"]):
            if any(token in diff_text for token in ["import ", "from ", "require("]):
                causes.append(
                    BreakCause(
                        title="Dependency/import change",
                        confidence=0.74,
                        evidence="Failure indicates missing symbol/module while imports were changed between versions.",
                        recommendation="Validate renamed paths/symbols and ensure runtime dependencies are installed.",
                    )
                )

        if not causes and compare.removed_lines > compare.added_lines * 2:
            causes.append(
                BreakCause(
                    title="Behavior removed during refactor",
                    confidence=0.62,
                    evidence="Diff shows significantly more deletions than additions.",
                    recommendation="Review deleted logic in baseline version and restore required behavior.",
                )
            )

        if not causes:
            causes.append(
                BreakCause(
                    title="Regression introduced in recent change set",
                    confidence=0.55,
                    evidence="Code differs across compared versions and symptoms likely map to touched symbols.",
                    recommendation="Run targeted tests around changed symbols and bisect with earlier versions.",
                )
            )

        return causes[:5]

    def why_did_this_break(
        self,
        *,
        user_id: str,
        request: CodeBreakAnalysisRequest,
    ) -> CodeBreakAnalysisResponse:
        compare = self.compare_versions(
            user_id=user_id,
            request=CodeVersionCompareRequest(
                file_id=request.file_id,
                from_version_id=request.baseline_version_id,
                to_version_id=request.current_version_id,
            ),
        )

        causes = self._infer_break_causes(
            compare=compare,
            failure_context=request.failure_context or "",
        )

        top = causes[0]
        answer = (
            f"Most likely break source is '{top.title}' between "
            f"v{compare.from_version.version_index} and v{compare.to_version.version_index}. "
            f"{top.evidence}"
        )

        return CodeBreakAnalysisResponse(
            file_id=request.file_id,
            answer=answer,
            causes=causes,
            compare=compare,
            context_used=bool(request.failure_context and request.failure_context.strip()),
        )


version_intelligence_service = VersionIntelligenceService()
