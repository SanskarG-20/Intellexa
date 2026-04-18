"""Smoke tests for Intellexa AI Code Workspace backend services.

Scenarios covered:
1) Small code snippet executes successfully
2) Large project-like prompt handled by code-assist service
3) Syntax error detection
4) Runtime error handling
5) Malicious code blocking
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import List

from app.core.config import settings
from app.schemas.code import CodeAction, CodeAssistRequest, CodeExecutionRequest
from app.services.code_workspace.code_service import code_workspace_code_service
from app.services.code_workspace.execution_service import code_execution_service


@dataclass
class TestResult:
    name: str
    passed: bool
    detail: str


async def test_small_snippet() -> TestResult:
    response = await code_execution_service.execute(
        CodeExecutionRequest(
            code="print('hello from sandbox')",
            language="python",
            stdin="",
            timeout_ms=2000,
        )
    )
    passed = response.success and "hello from sandbox" in (response.result.stdout or "")
    return TestResult(
        name="Small snippet",
        passed=passed,
        detail=f"success={response.success}, stdout={response.result.stdout.strip()!r}",
    )


async def test_large_project_like_prompt() -> TestResult:
    large_code = "\n".join(
        [
            "def util(value):",
            "    return value * 2",
            "",
        ]
        + [f"result_{i} = util({i})" for i in range(1200)]
        + ["print('done')"]
    )

    response = await code_workspace_code_service.assist(
        CodeAssistRequest(
            code=large_code,
            language="python",
            prompt="Refactor this for readability and maintainability.",
            action=CodeAction.REFACTOR,
            include_context=False,
        ),
        user_id=settings.MOCK_USER_ID,
    )

    passed = bool(response.explanation)
    return TestResult(
        name="Large project-like assist",
        passed=passed,
        detail=f"cached={response.cached}, has_updated_code={bool(response.updated_code)}",
    )


async def test_syntax_error() -> TestResult:
    response = await code_execution_service.execute(
        CodeExecutionRequest(
            code="def broken(:\n    pass",
            language="python",
            timeout_ms=2000,
        )
    )
    passed = (not response.success) and "Syntax" in (response.error or "")
    return TestResult(
        name="Syntax error",
        passed=passed,
        detail=f"success={response.success}, error={response.error!r}",
    )


async def test_runtime_error() -> TestResult:
    response = await code_execution_service.execute(
        CodeExecutionRequest(
            code="raise RuntimeError('boom')",
            language="python",
            timeout_ms=2000,
        )
    )
    passed = (not response.success) and "RuntimeError" in (response.result.stderr or "")
    return TestResult(
        name="Runtime error",
        passed=passed,
        detail=f"success={response.success}, stderr={response.result.stderr.strip()!r}",
    )


async def test_malicious_code() -> TestResult:
    response = await code_execution_service.execute(
        CodeExecutionRequest(
            code="import os\nprint(os.listdir('.'))",
            language="python",
            timeout_ms=2000,
        )
    )
    passed = (not response.success) and "blocked" in (response.error or "").lower()
    return TestResult(
        name="Malicious code blocked",
        passed=passed,
        detail=f"success={response.success}, error={response.error!r}",
    )


async def run_all() -> List[TestResult]:
    return [
        await test_small_snippet(),
        await test_large_project_like_prompt(),
        await test_syntax_error(),
        await test_runtime_error(),
        await test_malicious_code(),
    ]


def print_results(results: List[TestResult]) -> None:
    print("\n=== Code Workspace Smoke Tests ===")
    for result in results:
        marker = "PASS" if result.passed else "FAIL"
        print(f"[{marker}] {result.name}: {result.detail}")

    failed = [item for item in results if not item.passed]
    if failed:
        print(f"\n{len(failed)} test(s) failed.")
        raise SystemExit(1)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    output = asyncio.run(run_all())
    print_results(output)
