"""
security_scanner_service.py - Static vulnerability scanning heuristics.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Set, Tuple

from app.schemas.code import (
    BugSeverity,
    SecurityFindingCategory,
    SecurityScanFinding,
    SecurityScanRequest,
    SecurityScanResponse,
)


class SecurityScannerService:
    """Heuristic scanner for common code-level security risks."""

    SEVERITY_RANK = {
        BugSeverity.NONE: 0,
        BugSeverity.LOW: 1,
        BugSeverity.MEDIUM: 2,
        BugSeverity.HIGH: 3,
        BugSeverity.CRITICAL: 4,
    }

    HARDCODED_SECRET_PATTERNS = [
        re.compile(r"\b(?:api[_-]?key|access[_-]?token|secret|client[_-]?secret|password)\b\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
        re.compile(r"\bsk-[A-Za-z0-9\-_]{16,}\b"),
        re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
        re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
        re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
        re.compile(r"Authorization\s*[:=]\s*['\"]Bearer\s+[A-Za-z0-9\-\._~\+/]+=*['\"]", re.IGNORECASE),
    ]

    JS_USER_INPUT_RE = re.compile(
        r"\b(?:req\.(?:body|query|params|headers)|request\.(?:body|query|params|headers)|ctx\.request\.(?:body|query|querystring)|location\.search|window\.location\.search|document\.cookie)\b"
    )
    PY_USER_INPUT_RE = re.compile(
        r"\b(?:request\.(?:args|form|values|json)|request\.get_json\s*\(|input\s*\(|sys\.argv\b|os\.environ\.get\s*\()"
    )

    SANITIZATION_HINT_RE = re.compile(
        r"\b(?:sanitize|escape|validate|validator|schema|pydantic|marshmallow|zod|joi|cerberus|bleach|strip_tags|html\.escape|quote_plus|parametrize|parameterized)\b",
        re.IGNORECASE,
    )

    JS_SQL_INJECTION_RE = re.compile(
        r"\b(?:query|execute|raw)\s*\(\s*(?:`[^`]*\$\{|['\"][^'\"]*['\"]\s*\+|.*req\.(?:body|query|params)|.*request\.(?:body|query|params))",
        re.IGNORECASE,
    )
    PY_SQL_INJECTION_RE = re.compile(
        r"\b(?:execute|executemany|raw)\s*\(\s*(?:f['\"]|['\"][^'\"]*['\"]\s*\+|.*\.format\s*\(|.*%\s*[A-Za-z_\(\[])",
        re.IGNORECASE,
    )
    JS_SQL_STRING_BUILD_RE = re.compile(
        r"\b(?:select|insert|update|delete)\b.*(?:\+|\$\{).*(?:req\.(?:body|query|params)|request\.(?:body|query|params))",
        re.IGNORECASE,
    )
    PY_SQL_STRING_BUILD_RE = re.compile(
        r"\b(?:select|insert|update|delete)\b.*(?:%\s*[A-Za-z_]|\.format\s*\(|\{[A-Za-z_][A-Za-z0-9_]*\})",
        re.IGNORECASE,
    )

    @staticmethod
    def _deduce_language(request: SecurityScanRequest) -> str:
        language = str(request.language or "").strip().lower()
        if language:
            return language

        ext = Path(str(request.filename or "")).suffix.lower()
        mapping = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
        }
        return mapping.get(ext, "javascript")

    @staticmethod
    def _line_snippet(lines: List[str], line_number: Optional[int]) -> Optional[str]:
        if line_number is None:
            return None
        if line_number < 1 or line_number > len(lines):
            return None
        snippet = lines[line_number - 1].strip()
        return snippet[:220] if snippet else None

    @staticmethod
    def _max_severity(values: List[BugSeverity]) -> BugSeverity:
        if not values:
            return BugSeverity.NONE
        return max(values, key=lambda item: SecurityScannerService.SEVERITY_RANK[item])

    @staticmethod
    def _nearby_lines(lines: List[str], line_number: int, radius: int = 2) -> str:
        start = max(0, line_number - 1 - radius)
        end = min(len(lines), line_number + radius)
        return "\n".join(lines[start:end])

    @classmethod
    def _has_sanitization_hint(cls, lines: List[str], line_number: int) -> bool:
        nearby = cls._nearby_lines(lines, line_number, radius=3)
        return bool(cls.SANITIZATION_HINT_RE.search(nearby))

    def _add_finding(
        self,
        findings: List[SecurityScanFinding],
        seen: Set[Tuple[str, str, Optional[int]]],
        *,
        category: SecurityFindingCategory,
        message: str,
        severity: BugSeverity,
        line: Optional[int],
        lines: List[str],
        remediation: str,
    ) -> None:
        key = (category.value, message, line)
        if key in seen:
            return
        seen.add(key)

        findings.append(
            SecurityScanFinding(
                category=category,
                message=message,
                severity=severity,
                line=line,
                snippet=self._line_snippet(lines, line),
                remediation=remediation,
            )
        )

    def _analyze_secret_leaks(
        self,
        lines: List[str],
        findings: List[SecurityScanFinding],
        seen: Set[Tuple[str, str, Optional[int]]],
        *,
        is_js: bool,
    ) -> None:
        for line_number, line in enumerate(lines, start=1):
            for pattern in self.HARDCODED_SECRET_PATTERNS:
                if pattern.search(line):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Potential hardcoded credential or bearer token found.",
                        severity=BugSeverity.CRITICAL,
                        line=line_number,
                        lines=lines,
                        remediation="Move secrets to environment variables or a secret manager and rotate exposed keys.",
                    )
                    break

            lower = line.lower()
            if is_js:
                if "console.log" in lower and re.search(r"token|secret|api[_-]?key|password", lower):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Sensitive token/secret appears to be logged to console.",
                        severity=BugSeverity.HIGH,
                        line=line_number,
                        lines=lines,
                        remediation="Remove sensitive logs or mask secrets before logging.",
                    )

                if re.search(r"\b(?:res\.(?:json|send)|return)\s*\(\s*process\.env\b", line):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Returning process.env can leak server secrets to clients.",
                        severity=BugSeverity.CRITICAL,
                        line=line_number,
                        lines=lines,
                        remediation="Never expose full environment variables in responses.",
                    )
            else:
                if re.search(r"\b(?:print|logger\.(?:info|warning|error|debug))\s*\(.*(?:token|secret|api[_-]?key|password)", line, re.IGNORECASE):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Sensitive token/secret appears in logging output.",
                        severity=BugSeverity.HIGH,
                        line=line_number,
                        lines=lines,
                        remediation="Mask or remove sensitive values from logs.",
                    )

                if re.search(r"\breturn\s+os\.environ\b", line):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Returning os.environ can leak secrets in API responses.",
                        severity=BugSeverity.CRITICAL,
                        line=line_number,
                        lines=lines,
                        remediation="Return only whitelisted, non-sensitive config values.",
                    )

    def _analyze_python(
        self,
        code: str,
        findings: List[SecurityScanFinding],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()

        self._analyze_secret_leaks(lines, findings, seen, is_js=False)

        for line_number, line in enumerate(lines, start=1):
            if re.search(r"\b(?:eval|exec)\s*\(", line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="Dynamic eval/exec can execute untrusted input.",
                    severity=BugSeverity.CRITICAL,
                    line=line_number,
                    lines=lines,
                    remediation="Replace eval/exec with safe parsing or explicit dispatch maps.",
                )

            if re.search(r"\bsubprocess\.(?:run|Popen|call|check_output)\s*\(.*shell\s*=\s*True", line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="subprocess with shell=True increases command injection risk.",
                    severity=BugSeverity.CRITICAL,
                    line=line_number,
                    lines=lines,
                    remediation="Use argument lists and shell=False; validate command inputs.",
                )

            if re.search(r"\b(?:os\.system|subprocess\.(?:run|Popen|call|check_output))\s*\(", line):
                if self.PY_USER_INPUT_RE.search(line) or re.search(r"\+\s*[A-Za-z_]|f['\"]", line):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.INJECTION_RISK,
                        message="Shell/command execution appears to interpolate user-controlled data.",
                        severity=BugSeverity.HIGH,
                        line=line_number,
                        lines=lines,
                        remediation="Validate input and avoid shell interpolation for command execution.",
                    )

            if self.PY_SQL_INJECTION_RE.search(line):
                severity = BugSeverity.HIGH
                if self.PY_USER_INPUT_RE.search(line):
                    severity = BugSeverity.CRITICAL
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="SQL query appears to be built via string interpolation/concatenation.",
                    severity=severity,
                    line=line_number,
                    lines=lines,
                    remediation="Use parameterized queries instead of string-built SQL.",
                )

            if self.PY_SQL_STRING_BUILD_RE.search(line) and self.PY_USER_INPUT_RE.search(line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="SQL statement string is assembled with user-controlled values.",
                    severity=BugSeverity.CRITICAL,
                    line=line_number,
                    lines=lines,
                    remediation="Keep SQL static and bind user data as parameters.",
                )

            if self.PY_USER_INPUT_RE.search(line) and not self._has_sanitization_hint(lines, line_number):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.UNSAFE_INPUT,
                    message="User-controlled input is used without nearby validation or sanitization.",
                    severity=BugSeverity.MEDIUM,
                    line=line_number,
                    lines=lines,
                    remediation="Validate and sanitize input before downstream use.",
                )

    def _analyze_js_ts(
        self,
        code: str,
        findings: List[SecurityScanFinding],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()

        self._analyze_secret_leaks(lines, findings, seen, is_js=True)

        for line_number, line in enumerate(lines, start=1):
            if re.search(r"\b(?:eval|Function)\s*\(", line) or "new Function(" in line:
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="eval/new Function can execute untrusted JavaScript input.",
                    severity=BugSeverity.CRITICAL,
                    line=line_number,
                    lines=lines,
                    remediation="Avoid dynamic code execution and use explicit logic branches.",
                )

            if re.search(r"\bchild_process\.(?:exec|execSync)\s*\(", line):
                severity = BugSeverity.HIGH
                if self.JS_USER_INPUT_RE.search(line) or "${" in line or "+" in line:
                    severity = BugSeverity.CRITICAL
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="Command execution call may allow command injection.",
                    severity=severity,
                    line=line_number,
                    lines=lines,
                    remediation="Use execFile/spawn with fixed args and validate input strictly.",
                )

            if self.JS_SQL_INJECTION_RE.search(line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="Database query appears to concatenate/interpolate user-controlled values.",
                    severity=BugSeverity.HIGH,
                    line=line_number,
                    lines=lines,
                    remediation="Use parameterized placeholders with bound values.",
                )

            if self.JS_SQL_STRING_BUILD_RE.search(line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="SQL string construction includes user-controlled request data.",
                    severity=BugSeverity.CRITICAL,
                    line=line_number,
                    lines=lines,
                    remediation="Avoid SQL string concatenation; use prepared statements with parameters.",
                )

            if self.JS_USER_INPUT_RE.search(line) and not self._has_sanitization_hint(lines, line_number):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.UNSAFE_INPUT,
                    message="Request input appears to be consumed without validation/sanitization.",
                    severity=BugSeverity.MEDIUM,
                    line=line_number,
                    lines=lines,
                    remediation="Add schema validation (e.g., zod/joi) before using request data.",
                )

    def _analyze_generic(
        self,
        code: str,
        findings: List[SecurityScanFinding],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()

        for line_number, line in enumerate(lines, start=1):
            for pattern in self.HARDCODED_SECRET_PATTERNS:
                if pattern.search(line):
                    self._add_finding(
                        findings,
                        seen,
                        category=SecurityFindingCategory.API_LEAK,
                        message="Potential hardcoded credential found.",
                        severity=BugSeverity.CRITICAL,
                        line=line_number,
                        lines=lines,
                        remediation="Remove inline credentials and rotate any exposed secrets.",
                    )
                    break

            if re.search(r"\b(?:eval|exec)\s*\(", line):
                self._add_finding(
                    findings,
                    seen,
                    category=SecurityFindingCategory.INJECTION_RISK,
                    message="Dynamic code execution detected; verify input trust boundaries.",
                    severity=BugSeverity.HIGH,
                    line=line_number,
                    lines=lines,
                    remediation="Avoid dynamic evaluation for untrusted data.",
                )

    @staticmethod
    def _group_by_category(
        findings: List[SecurityScanFinding],
        category: SecurityFindingCategory,
    ) -> List[SecurityScanFinding]:
        return [item for item in findings if item.category == category]

    async def scan(self, request: SecurityScanRequest) -> SecurityScanResponse:
        code = str(request.code or "")
        language = self._deduce_language(request)

        findings: List[SecurityScanFinding] = []
        seen: Set[Tuple[str, str, Optional[int]]] = set()

        if language in {"python", "py"}:
            self._analyze_python(code, findings, seen)
        elif language in {"javascript", "typescript", "js", "jsx", "ts", "tsx"}:
            self._analyze_js_ts(code, findings, seen)
        else:
            self._analyze_generic(code, findings, seen)

        overall = self._max_severity([item.severity for item in findings])

        unsafe_inputs = self._group_by_category(findings, SecurityFindingCategory.UNSAFE_INPUT)
        api_leaks = self._group_by_category(findings, SecurityFindingCategory.API_LEAK)
        injection_risks = self._group_by_category(findings, SecurityFindingCategory.INJECTION_RISK)

        return SecurityScanResponse(
            findings=findings,
            unsafe_inputs=unsafe_inputs,
            api_leaks=api_leaks,
            injection_risks=injection_risks,
            severity=overall,
        )


security_scanner_service = SecurityScannerService()
