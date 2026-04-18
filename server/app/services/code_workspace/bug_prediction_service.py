"""
bug_prediction_service.py - Static bug prediction before code execution.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from app.schemas.code import (
    BugPredictionRequest,
    BugPredictionResponse,
    BugPredictionWarning,
    BugSeverity,
)


class BugPredictionService:
    """Heuristic static analyzer for potential runtime bugs."""

    JS_ASYNC_FN_RE = re.compile(
        r"^\s*async\s+function\s+([A-Za-z_][A-Za-z0-9_]*)|"
        r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*async\s*\(",
        re.MULTILINE,
    )

    PY_RISKY_ASSIGN_PATTERNS = [
        re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*None\b"),
        re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*.+\.get\("),
        re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*next\("),
    ]

    JS_RISKY_ASSIGN_PATTERNS = [
        re.compile(
            r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"
            r"(?:document\.)?(?:querySelector|getElementById)\("
        ),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*.+\.find\("),
        re.compile(r"^\s*(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*await\s+.+\.find\("),
    ]

    SEVERITY_RANK = {
        BugSeverity.NONE: 0,
        BugSeverity.LOW: 1,
        BugSeverity.MEDIUM: 2,
        BugSeverity.HIGH: 3,
        BugSeverity.CRITICAL: 4,
    }

    @staticmethod
    def _deduce_language(request: BugPredictionRequest) -> str:
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
    def _max_severity(values: List[BugSeverity]) -> BugSeverity:
        if not values:
            return BugSeverity.NONE
        return max(values, key=lambda item: BugPredictionService.SEVERITY_RANK[item])

    @staticmethod
    def _line_snippet(lines: List[str], line_number: Optional[int]) -> Optional[str]:
        if line_number is None:
            return None
        if line_number < 1 or line_number > len(lines):
            return None
        snippet = lines[line_number - 1].strip()
        return snippet[:200] if snippet else None

    @staticmethod
    def _call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = BugPredictionService._call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

    @staticmethod
    def _attach_parents(tree: ast.AST) -> None:
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                setattr(child, "_parent", parent)

    @staticmethod
    def _has_python_guard(lines: List[str], variable: str, line_number: int) -> bool:
        window_start = max(0, line_number - 5)
        guard_patterns = [
            re.compile(rf"\bif\s+{re.escape(variable)}\s+is\s+not\s+None\b"),
            re.compile(rf"\bif\s+{re.escape(variable)}\b\s*:\s*$"),
            re.compile(rf"\bassert\s+{re.escape(variable)}\s+is\s+not\s+None\b"),
        ]

        for index in range(window_start, line_number - 1):
            candidate = lines[index]
            if any(pattern.search(candidate) for pattern in guard_patterns):
                return True
        return False

    @staticmethod
    def _has_js_guard(lines: List[str], variable: str, line_number: int) -> bool:
        window_start = max(0, line_number - 6)
        guard_patterns = [
            re.compile(rf"\bif\s*\(\s*{re.escape(variable)}\s*\)"),
            re.compile(rf"\bif\s*\(\s*{re.escape(variable)}\s*!==?\s*null\s*\)"),
            re.compile(rf"\bif\s*\(\s*{re.escape(variable)}\s*!==?\s*undefined\s*\)"),
            re.compile(rf"\bif\s*\(\s*{re.escape(variable)}\s*!=\s*null\s*\)"),
            re.compile(rf"\b{re.escape(variable)}\?\."),
        ]

        for index in range(window_start, line_number - 1):
            candidate = lines[index]
            if any(pattern.search(candidate) for pattern in guard_patterns):
                return True
        return False

    def _add_warning(
        self,
        warnings: List[BugPredictionWarning],
        seen: Set[Tuple[str, str, Optional[int]]],
        *,
        category: str,
        message: str,
        severity: BugSeverity,
        line: Optional[int],
        lines: List[str],
    ) -> None:
        key = (category, message, line)
        if key in seen:
            return
        seen.add(key)

        warnings.append(
            BugPredictionWarning(
                category=category,
                message=message,
                severity=severity,
                line=line,
                snippet=self._line_snippet(lines, line),
            )
        )

    def _analyze_python(
        self,
        code: str,
        warnings: List[BugPredictionWarning],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()

        risky_vars: Dict[str, int] = {}
        for line_number, line in enumerate(lines, start=1):
            for pattern in self.PY_RISKY_ASSIGN_PATTERNS:
                match = pattern.search(line)
                if match:
                    risky_vars[match.group(1)] = line_number

        for variable, assigned_line in risky_vars.items():
            usage_pattern = re.compile(rf"\b{re.escape(variable)}\s*(?:\.|\[|\()")
            for line_number, line in enumerate(lines, start=1):
                if line_number <= assigned_line:
                    continue
                if not usage_pattern.search(line):
                    continue
                if self._has_python_guard(lines, variable, line_number):
                    continue

                self._add_warning(
                    warnings,
                    seen,
                    category="null-issue",
                    message=(
                        f"'{variable}' may be None before dereference. Guard with explicit None checks."
                    ),
                    severity=BugSeverity.MEDIUM,
                    line=line_number,
                    lines=lines,
                )
                break

        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            self._add_warning(
                warnings,
                seen,
                category="edge-case",
                message=f"Syntax issue prevents reliable analysis: {exc.msg}.",
                severity=BugSeverity.HIGH,
                line=exc.lineno,
                lines=lines,
            )
            return

        self._attach_parents(tree)

        async_functions = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                call_name = self._call_name(node.func)
                parent = getattr(node, "_parent", None)

                if call_name in async_functions and not isinstance(parent, ast.Await):
                    self._add_warning(
                        warnings,
                        seen,
                        category="async-problem",
                        message=(
                            f"Async function '{call_name}' appears to be called without await."
                        ),
                        severity=BugSeverity.HIGH,
                        line=getattr(node, "lineno", None),
                        lines=lines,
                    )

                if call_name in {"time.sleep", "sleep", "requests.get", "requests.post", "subprocess.run"}:
                    container = parent
                    inside_async = False
                    while container is not None:
                        if isinstance(container, ast.AsyncFunctionDef):
                            inside_async = True
                            break
                        container = getattr(container, "_parent", None)

                    if inside_async:
                        self._add_warning(
                            warnings,
                            seen,
                            category="async-problem",
                            message=(
                                f"Blocking call '{call_name}' inside async function can freeze concurrency."
                            ),
                            severity=BugSeverity.HIGH,
                            line=getattr(node, "lineno", None),
                            lines=lines,
                        )

        for line_number, line in enumerate(lines, start=1):
            division_match = re.search(r"/\s*([A-Za-z_][A-Za-z0-9_]*)", line)
            if division_match:
                divisor = division_match.group(1)
                nearby = "\n".join(lines[max(0, line_number - 4): line_number + 1])
                if not re.search(rf"\b{re.escape(divisor)}\s*!?=\s*0\b", nearby):
                    self._add_warning(
                        warnings,
                        seen,
                        category="edge-case",
                        message=f"Division by '{divisor}' without clear zero guard.",
                        severity=BugSeverity.MEDIUM,
                        line=line_number,
                        lines=lines,
                    )

            if re.search(r"\[[0-9]+\]", line):
                nearby = "\n".join(lines[max(0, line_number - 4): line_number + 1])
                if not re.search(r"\blen\(|\bif\s+.+\[", nearby):
                    self._add_warning(
                        warnings,
                        seen,
                        category="edge-case",
                        message="Direct index access may fail on empty or short sequences.",
                        severity=BugSeverity.LOW,
                        line=line_number,
                        lines=lines,
                    )

            if re.search(r"^\s*except\s*:\s*$", line):
                self._add_warning(
                    warnings,
                    seen,
                    category="edge-case",
                    message="Bare 'except:' can hide real runtime failures and edge-case bugs.",
                    severity=BugSeverity.MEDIUM,
                    line=line_number,
                    lines=lines,
                )

    def _extract_js_async_functions(self, code: str) -> Set[str]:
        functions: Set[str] = set()
        for match in self.JS_ASYNC_FN_RE.finditer(code):
            name = match.group(1) or match.group(2)
            if name:
                functions.add(name)
        return functions

    def _analyze_js_ts(
        self,
        code: str,
        warnings: List[BugPredictionWarning],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()

        risky_vars: Dict[str, int] = {}
        for line_number, line in enumerate(lines, start=1):
            for pattern in self.JS_RISKY_ASSIGN_PATTERNS:
                match = pattern.search(line)
                if match:
                    risky_vars[match.group(1)] = line_number

        for variable, assigned_line in risky_vars.items():
            use_pattern = re.compile(rf"\b{re.escape(variable)}\s*(?:\.|\[|\()")
            optional_chain_pattern = re.compile(rf"\b{re.escape(variable)}\s*\?\.")

            for line_number, line in enumerate(lines, start=1):
                if line_number <= assigned_line:
                    continue
                if optional_chain_pattern.search(line):
                    continue
                if not use_pattern.search(line):
                    continue
                if self._has_js_guard(lines, variable, line_number):
                    continue

                self._add_warning(
                    warnings,
                    seen,
                    category="null-issue",
                    message=(
                        f"'{variable}' may be null/undefined before usage. Add guard or optional chaining."
                    ),
                    severity=BugSeverity.MEDIUM,
                    line=line_number,
                    lines=lines,
                )
                break

        async_functions = self._extract_js_async_functions(code)

        for line_number, line in enumerate(lines, start=1):
            if re.search(r"\.forEach\s*\(\s*async\b", line):
                self._add_warning(
                    warnings,
                    seen,
                    category="async-problem",
                    message="'forEach(async ...)' is often not awaited; use for...of with await.",
                    severity=BugSeverity.HIGH,
                    line=line_number,
                    lines=lines,
                )

            if re.search(r"new\s+Promise\s*\(\s*async\b", line):
                self._add_warning(
                    warnings,
                    seen,
                    category="async-problem",
                    message="Avoid 'new Promise(async ...)' anti-pattern; it can mask rejection flow.",
                    severity=BugSeverity.HIGH,
                    line=line_number,
                    lines=lines,
                )

            if ".then(" in line and ".catch(" not in line:
                near = "\n".join(lines[line_number - 1: min(len(lines), line_number + 2)])
                if ".catch(" not in near:
                    self._add_warning(
                        warnings,
                        seen,
                        category="async-problem",
                        message="Promise chain has '.then' without nearby '.catch' error handling.",
                        severity=BugSeverity.MEDIUM,
                        line=line_number,
                        lines=lines,
                    )

            if "JSON.parse(" in line:
                near = "\n".join(lines[max(0, line_number - 4): line_number + 1]).lower()
                if "try" not in near:
                    self._add_warning(
                        warnings,
                        seen,
                        category="edge-case",
                        message="JSON.parse without try/catch may crash on malformed input.",
                        severity=BugSeverity.MEDIUM,
                        line=line_number,
                        lines=lines,
                    )

            division_match = re.search(r"/\s*([A-Za-z_][A-Za-z0-9_]*)", line)
            if division_match:
                divisor = division_match.group(1)
                near = "\n".join(lines[max(0, line_number - 4): line_number + 1])
                if not re.search(rf"\b{re.escape(divisor)}\s*!==?\s*0\b", near):
                    self._add_warning(
                        warnings,
                        seen,
                        category="edge-case",
                        message=f"Division by '{divisor}' without an explicit zero guard.",
                        severity=BugSeverity.MEDIUM,
                        line=line_number,
                        lines=lines,
                    )

            if re.search(r"\[[0-9]+\]", line):
                near = "\n".join(lines[max(0, line_number - 4): line_number + 1])
                if not re.search(r"\blength\b|\bif\s*\(.*\.length", near):
                    self._add_warning(
                        warnings,
                        seen,
                        category="edge-case",
                        message="Direct index access can fail on empty arrays/strings.",
                        severity=BugSeverity.LOW,
                        line=line_number,
                        lines=lines,
                    )

            for async_name in async_functions:
                call_pattern = re.compile(rf"\b{re.escape(async_name)}\s*\(")
                if not call_pattern.search(line):
                    continue
                if re.search(rf"\bawait\s+{re.escape(async_name)}\s*\(", line):
                    continue
                if re.search(
                    rf"\b(?:async\s+function\s+{re.escape(async_name)}|"
                    rf"(?:const|let|var)\s+{re.escape(async_name)}\s*=)",
                    line,
                ):
                    continue

                self._add_warning(
                    warnings,
                    seen,
                    category="async-problem",
                    message=f"Async function '{async_name}' appears to be called without await.",
                    severity=BugSeverity.HIGH,
                    line=line_number,
                    lines=lines,
                )

        for switch_match in re.finditer(r"switch\s*\([^)]*\)\s*\{", code):
            start = switch_match.start()
            brace_depth = 0
            end = None
            for index in range(start, len(code)):
                if code[index] == "{":
                    brace_depth += 1
                elif code[index] == "}":
                    brace_depth -= 1
                    if brace_depth == 0:
                        end = index
                        break

            if end is None:
                continue

            block = code[start:end]
            if "default:" not in block:
                line_number = code[:start].count("\n") + 1
                self._add_warning(
                    warnings,
                    seen,
                    category="edge-case",
                    message="switch statement without default can miss unhandled edge values.",
                    severity=BugSeverity.LOW,
                    line=line_number,
                    lines=lines,
                )

    def _analyze_generic(
        self,
        code: str,
        warnings: List[BugPredictionWarning],
        seen: Set[Tuple[str, str, Optional[int]]],
    ) -> None:
        lines = code.splitlines()
        for line_number, line in enumerate(lines, start=1):
            if "TODO" in line or "FIXME" in line:
                self._add_warning(
                    warnings,
                    seen,
                    category="edge-case",
                    message="Unresolved TODO/FIXME may indicate known bug-prone behavior.",
                    severity=BugSeverity.LOW,
                    line=line_number,
                    lines=lines,
                )

            if re.search(r"\bpass\b", line) and line.strip().startswith("pass"):
                self._add_warning(
                    warnings,
                    seen,
                    category="edge-case",
                    message="No-op placeholder may hide unimplemented edge-case handling.",
                    severity=BugSeverity.LOW,
                    line=line_number,
                    lines=lines,
                )

    async def predict(self, request: BugPredictionRequest) -> BugPredictionResponse:
        code = str(request.code or "")
        language = self._deduce_language(request)

        warnings: List[BugPredictionWarning] = []
        seen: Set[Tuple[str, str, Optional[int]]] = set()

        if language in {"python", "py"}:
            self._analyze_python(code, warnings, seen)
        elif language in {"javascript", "typescript", "js", "jsx", "ts", "tsx"}:
            self._analyze_js_ts(code, warnings, seen)
        else:
            self._analyze_generic(code, warnings, seen)

        # Generic pass for all languages catches universal code smells.
        self._analyze_generic(code, warnings, seen)

        overall = self._max_severity([item.severity for item in warnings])
        return BugPredictionResponse(
            warnings=warnings,
            severity=overall,
        )


bug_prediction_service = BugPredictionService()
