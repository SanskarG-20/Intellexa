"""
dependency_parser.py - File parser logic for dependency graph extraction.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List


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
JS_CALL_RE = re.compile(r"\b([A-Za-z_][A-Za-z0-9_\.]*)\s*\(")


@dataclass
class ParseArtifacts:
    imports: List[str] = field(default_factory=list)
    functions: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    function_calls: List[str] = field(default_factory=list)
    call_mapping: Dict[str, List[str]] = field(default_factory=dict)


class FileParserLogic:
    """Language-aware parser for imports, symbols, and call relationships."""

    JS_CALL_BLOCKLIST = {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "class",
        "return",
        "import",
        "typeof",
        "new",
        "super",
    }

    PY_CALL_BLOCKLIST = {
        "print",
        "len",
        "str",
        "int",
        "float",
        "dict",
        "list",
        "set",
        "tuple",
        "range",
        "isinstance",
        "getattr",
        "setattr",
        "hasattr",
        "type",
        "open",
    }

    @staticmethod
    def _dedupe(values: Iterable[str], max_items: int = 256) -> List[str]:
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

    @classmethod
    def _dedupe_mapping(cls, mapping: Dict[str, List[str]]) -> Dict[str, List[str]]:
        return {
            key: cls._dedupe(values, max_items=512)
            for key, values in mapping.items()
            if key and values
        }

    @staticmethod
    def _python_call_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = FileParserLogic._python_call_name(node.value)
            return f"{base}.{node.attr}" if base else node.attr
        return ""

    @classmethod
    def _parse_python(cls, content: str) -> ParseArtifacts:
        try:
            tree = ast.parse(content)
        except Exception:
            return ParseArtifacts()

        imports: List[str] = []

        class Visitor(ast.NodeVisitor):
            def __init__(self) -> None:
                self.class_stack: List[str] = []
                self.function_stack: List[str] = []
                self.functions: List[str] = []
                self.classes: List[str] = []
                self.function_calls: List[str] = []
                self.call_mapping: Dict[str, List[str]] = {}

            def _current_caller(self) -> str:
                if self.function_stack:
                    return self.function_stack[-1]
                return "__module__"

            def _record_call(self, call_name: str) -> None:
                if not call_name:
                    return
                self.function_calls.append(call_name)
                caller = self._current_caller()
                self.call_mapping.setdefault(caller, []).append(call_name)

            def _function_label(self, node_name: str) -> str:
                if self.class_stack:
                    return f"{self.class_stack[-1]}.{node_name}"
                return node_name

            def visit_Import(self, node: ast.Import) -> None:
                for alias in node.names:
                    imports.append(alias.name)
                self.generic_visit(node)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                base = "." * node.level + (node.module or "")
                imports.append(base)
                self.generic_visit(node)

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                self.classes.append(node.name)
                self.class_stack.append(node.name)
                self.generic_visit(node)
                self.class_stack.pop()

            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                label = self._function_label(node.name)
                self.functions.append(label)
                self.function_stack.append(label)
                self.generic_visit(node)
                self.function_stack.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                label = self._function_label(node.name)
                self.functions.append(label)
                self.function_stack.append(label)
                self.generic_visit(node)
                self.function_stack.pop()

            def visit_Call(self, node: ast.Call) -> None:
                call_name = FileParserLogic._python_call_name(node.func)
                self._record_call(call_name)
                self.generic_visit(node)

        visitor = Visitor()
        visitor.visit(tree)

        filtered_calls = [
            name
            for name in visitor.function_calls
            if name.split(".")[-1] not in cls.PY_CALL_BLOCKLIST
        ]
        filtered_mapping: Dict[str, List[str]] = {}
        for caller, callees in visitor.call_mapping.items():
            cleaned = [
                name
                for name in callees
                if name.split(".")[-1] not in cls.PY_CALL_BLOCKLIST
            ]
            if cleaned:
                filtered_mapping[caller] = cleaned

        return ParseArtifacts(
            imports=cls._dedupe(imports),
            functions=cls._dedupe(visitor.functions),
            classes=cls._dedupe(visitor.classes),
            function_calls=cls._dedupe(filtered_calls, max_items=512),
            call_mapping=cls._dedupe_mapping(filtered_mapping),
        )

    @classmethod
    def _parse_js_like(cls, content: str) -> ParseArtifacts:
        imports = cls._dedupe(JS_IMPORT_RE.findall(content) + JS_REQUIRE_RE.findall(content))
        functions = cls._dedupe(JS_FUNCTION_RE.findall(content) + JS_ARROW_RE.findall(content))
        classes = cls._dedupe(JS_CLASS_RE.findall(content))

        raw_calls = JS_CALL_RE.findall(content)
        function_calls = [
            call_name
            for call_name in raw_calls
            if call_name.split(".")[-1] not in cls.JS_CALL_BLOCKLIST
        ]

        call_mapping = {"__module__": cls._dedupe(function_calls, max_items=512)} if function_calls else {}

        return ParseArtifacts(
            imports=imports,
            functions=functions,
            classes=classes,
            function_calls=cls._dedupe(function_calls, max_items=512),
            call_mapping=cls._dedupe_mapping(call_mapping),
        )

    @classmethod
    def _parse_generic(cls, content: str) -> ParseArtifacts:
        imports = cls._dedupe(JS_IMPORT_RE.findall(content))
        return ParseArtifacts(imports=imports)

    @classmethod
    def parse(cls, file_path: str, content: str) -> ParseArtifacts:
        suffix = Path(file_path).suffix.lower()
        if suffix == ".py":
            return cls._parse_python(content)
        if suffix in {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
            return cls._parse_js_like(content)
        return cls._parse_generic(content)
