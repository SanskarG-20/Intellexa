"""
execution_service.py - Sandboxed code execution with strict safeguards.
"""

from __future__ import annotations

import ast
import asyncio
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Tuple

from app.core.config import settings
from app.schemas.code import CodeExecutionRequest, CodeExecutionResponse, CodeExecutionResult


class CodeExecutionService:
    """Executes untrusted code inside a constrained runtime."""

    DANGEROUS_IMPORTS = {
        "os",
        "sys",
        "subprocess",
        "socket",
        "requests",
        "httpx",
        "pathlib",
        "shutil",
        "ctypes",
        "multiprocessing",
    }
    DANGEROUS_CALLS = {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "input",
        "breakpoint",
    }

    @staticmethod
    def _truncate(text: str, max_chars: int) -> Tuple[str, bool]:
        if len(text) <= max_chars:
            return text, False
        return text[:max_chars] + "\n...[output truncated]...", True

    def _check_syntax(self, code: str) -> str | None:
        try:
            compile(code, "<sandbox>", "exec")
            return None
        except SyntaxError as exc:
            return f"SyntaxError: {exc.msg} (line {exc.lineno}, col {exc.offset})"

    def _check_ast_safety(self, code: str) -> str | None:
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return f"SyntaxError: {exc.msg}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for item in node.names:
                    base = item.name.split(".")[0]
                    if base in self.DANGEROUS_IMPORTS:
                        return f"Unsafe import blocked: {base}"
            elif isinstance(node, ast.ImportFrom):
                base = (node.module or "").split(".")[0]
                if base in self.DANGEROUS_IMPORTS:
                    return f"Unsafe import blocked: {base}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in self.DANGEROUS_CALLS:
                    return f"Unsafe function blocked: {node.func.id}"

        return None

    def _run_locally(self, request: CodeExecutionRequest, timeout_s: float) -> CodeExecutionResponse:
        python_executable = sys.executable
        start = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="intellexa-sandbox-") as temp_dir:
            script_path = Path(temp_dir) / "main.py"
            script_path.write_text(request.code, encoding="utf-8")

            try:
                completed = subprocess.run(
                    [python_executable, "-I", str(script_path)],
                    input=request.stdin or "",
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                    cwd=temp_dir,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)

                max_output = max(1000, int(settings.CODE_EXECUTION_MAX_OUTPUT_CHARS))
                stdout, stdout_truncated = self._truncate(completed.stdout or "", max_output)
                stderr, stderr_truncated = self._truncate(completed.stderr or "", max_output)

                return CodeExecutionResponse(
                    success=completed.returncode == 0,
                    result=CodeExecutionResult(
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=int(completed.returncode),
                        timed_out=False,
                        runtime_ms=elapsed_ms,
                        output_truncated=stdout_truncated or stderr_truncated,
                    ),
                    error=None,
                )
            except subprocess.TimeoutExpired as exc:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
                return CodeExecutionResponse(
                    success=False,
                    result=CodeExecutionResult(
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=None,
                        timed_out=True,
                        runtime_ms=elapsed_ms,
                        output_truncated=False,
                    ),
                    error=f"Execution timed out after {int(timeout_s * 1000)} ms.",
                )

    def _run_docker(self, request: CodeExecutionRequest, timeout_s: float) -> CodeExecutionResponse:
        start = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="intellexa-docker-") as temp_dir:
            script_path = Path(temp_dir) / "main.py"
            script_path.write_text(request.code, encoding="utf-8")

            cmd = [
                "docker",
                "run",
                "--rm",
                "--network",
                "none",
                "--cpus",
                settings.CODE_EXECUTION_CPU_LIMIT,
                "--memory",
                f"{settings.CODE_EXECUTION_MEMORY_LIMIT_MB}m",
                "-v",
                f"{Path(temp_dir).resolve()}:/workspace",
                "-w",
                "/workspace",
                settings.CODE_EXECUTION_DOCKER_IMAGE,
                "python",
                "-I",
                "/workspace/main.py",
            ]

            try:
                completed = subprocess.run(
                    cmd,
                    input=request.stdin or "",
                    capture_output=True,
                    text=True,
                    timeout=timeout_s,
                )
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                max_output = max(1000, int(settings.CODE_EXECUTION_MAX_OUTPUT_CHARS))
                stdout, stdout_truncated = self._truncate(completed.stdout or "", max_output)
                stderr, stderr_truncated = self._truncate(completed.stderr or "", max_output)

                return CodeExecutionResponse(
                    success=completed.returncode == 0,
                    result=CodeExecutionResult(
                        stdout=stdout,
                        stderr=stderr,
                        exit_code=int(completed.returncode),
                        timed_out=False,
                        runtime_ms=elapsed_ms,
                        output_truncated=stdout_truncated or stderr_truncated,
                    ),
                    error=None,
                )
            except subprocess.TimeoutExpired:
                elapsed_ms = int((time.perf_counter() - start) * 1000)
                return CodeExecutionResponse(
                    success=False,
                    result=CodeExecutionResult(
                        stdout="",
                        stderr="",
                        exit_code=None,
                        timed_out=True,
                        runtime_ms=elapsed_ms,
                        output_truncated=False,
                    ),
                    error=f"Execution timed out after {int(timeout_s * 1000)} ms.",
                )

    async def execute(self, request: CodeExecutionRequest) -> CodeExecutionResponse:
        """Validate and execute code safely."""
        if not settings.CODE_EXECUTION_ENABLED:
            return CodeExecutionResponse(
                success=False,
                result=CodeExecutionResult(
                    stdout="",
                    stderr="",
                    exit_code=None,
                    timed_out=False,
                    runtime_ms=0,
                    output_truncated=False,
                ),
                error="Code execution is disabled by server configuration.",
            )

        language = (request.language or "").lower().strip()
        if language != "python":
            return CodeExecutionResponse(
                success=False,
                result=CodeExecutionResult(
                    stdout="",
                    stderr="",
                    exit_code=None,
                    timed_out=False,
                    runtime_ms=0,
                    output_truncated=False,
                ),
                error="Only python execution is currently supported in sandbox mode.",
            )

        if len(request.code or "") > settings.CODE_EXECUTION_MAX_CODE_CHARS:
            return CodeExecutionResponse(
                success=False,
                result=CodeExecutionResult(
                    stdout="",
                    stderr="",
                    exit_code=None,
                    timed_out=False,
                    runtime_ms=0,
                    output_truncated=False,
                ),
                error=(
                    "Code input exceeds execution limit of "
                    f"{settings.CODE_EXECUTION_MAX_CODE_CHARS} characters."
                ),
            )

        syntax_error = self._check_syntax(request.code)
        if syntax_error:
            return CodeExecutionResponse(
                success=False,
                result=CodeExecutionResult(
                    stdout="",
                    stderr=syntax_error,
                    exit_code=None,
                    timed_out=False,
                    runtime_ms=0,
                    output_truncated=False,
                ),
                error="Syntax validation failed.",
            )

        ast_error = self._check_ast_safety(request.code)
        if ast_error:
            return CodeExecutionResponse(
                success=False,
                result=CodeExecutionResult(
                    stdout="",
                    stderr=ast_error,
                    exit_code=None,
                    timed_out=False,
                    runtime_ms=0,
                    output_truncated=False,
                ),
                error="Execution blocked by safety policy.",
            )

        timeout_ms = min(
            max(request.timeout_ms, 500),
            max(500, int(settings.CODE_EXECUTION_TIMEOUT_MS)),
        )
        timeout_s = timeout_ms / 1000.0

        use_docker = bool(settings.CODE_EXECUTION_USE_DOCKER) and bool(shutil.which("docker"))
        runner = self._run_docker if use_docker else self._run_locally
        return await asyncio.to_thread(runner, request, timeout_s)


code_execution_service = CodeExecutionService()
