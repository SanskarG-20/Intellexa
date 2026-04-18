"""
task_mode_service.py - AI Project Builder (Task Mode) orchestration.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from app.core.config import settings
from app.schemas.code import (
    TaskModeProgress,
    TaskModeRequest,
    TaskModeResponse,
    TaskModeStep,
    TaskStepStatus,
)
from app.services.code_workspace.context_service import code_workspace_context_service
from app.services.llama_service import llama_service


@dataclass
class _TaskSession:
    session_id: str
    user_id: str
    prompt: str
    language: str
    title: str
    summary: str
    steps: List[TaskModeStep]
    context_used: bool
    context_sources: List[str]
    created_at: float
    updated_at: float


class TaskModeService:
    """Generates and tracks implementation plans for feature-building tasks."""

    JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)

    def __init__(self) -> None:
        self.context_service = code_workspace_context_service
        self._sessions: Dict[str, _TaskSession] = {}

    @staticmethod
    def _normalize_prompt(value: str) -> str:
        return " ".join(str(value or "").split()).strip()

    @staticmethod
    def _clip(value: str, max_chars: int) -> str:
        text = str(value or "")
        if len(text) <= max_chars:
            return text
        head = int(max_chars * 0.65)
        tail = max_chars - head
        return f"{text[:head]}\n...\n{text[-tail:]}"

    @staticmethod
    def _strip_code_fences(text: str) -> str:
        raw = str(text or "").strip()
        if not raw:
            return ""

        match = TaskModeService.JSON_BLOCK_RE.search(raw)
        if match:
            return match.group(1).strip()

        code_match = re.search(r"```(?:[a-zA-Z0-9_+-]+)?\s*\n([\s\S]*?)\n```", raw)
        if code_match:
            return code_match.group(1).strip()

        return raw

    @staticmethod
    def _task_system_prompt(language: str, max_steps: int) -> str:
        return (
            "You are an AI Project Builder. Break feature requests into implementation steps. "
            "Return ONLY valid JSON with this schema: "
            "{\"title\": string, \"summary\": string, \"steps\": "
            "[{\"title\": string, \"description\": string, \"code\": string, "
            "\"acceptance_criteria\": [string]}]}. "
            f"Generate 3 to {max_steps} steps. "
            f"All code must be {language} and concise, production-oriented, and incremental. "
            "Do not wrap JSON or code in markdown fences."
        )

    @staticmethod
    def _extract_json_payload(raw: str) -> Optional[dict]:
        if not raw:
            return None

        text = str(raw).strip()

        # Fast path: direct JSON
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return data
        except Exception:
            pass

        # Scan for any valid top-level JSON object.
        starts = [index for index, ch in enumerate(text) if ch == "{"]
        for start in starts:
            depth = 0
            in_string = False
            escaped = False
            for i in range(start, len(text)):
                ch = text[i]

                if in_string:
                    if escaped:
                        escaped = False
                    elif ch == "\\":
                        escaped = True
                    elif ch == '"':
                        in_string = False
                    continue

                if ch == '"':
                    in_string = True
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = text[start : i + 1]
                        try:
                            data = json.loads(candidate)
                            if isinstance(data, dict):
                                return data
                        except Exception:
                            break

        return None

    @staticmethod
    def _fallback_steps(prompt: str, language: str) -> Tuple[str, str, List[TaskModeStep]]:
        language = str(language or "javascript").lower()

        if language == "python":
            core_snippet = (
                "class FeatureService:\n"
                "    def execute(self, payload: dict) -> dict:\n"
                "        if not isinstance(payload, dict):\n"
                "            raise ValueError('payload must be a dictionary')\n"
                "        return {'ok': True, 'data': payload}\n"
            )
            test_snippet = (
                "def test_feature_service_execute():\n"
                "    service = FeatureService()\n"
                "    result = service.execute({'id': 1})\n"
                "    assert result['ok'] is True\n"
            )
        else:
            core_snippet = (
                "export function executeFeature(payload = {}) {\n"
                "  if (!payload || typeof payload !== 'object') {\n"
                "    throw new Error('payload must be an object');\n"
                "  }\n"
                "  return { ok: true, data: payload };\n"
                "}\n"
            )
            test_snippet = (
                "import { executeFeature } from './feature';\n\n"
                "test('executeFeature returns success shape', () => {\n"
                "  const result = executeFeature({ id: 1 });\n"
                "  expect(result.ok).toBe(true);\n"
                "});\n"
            )

        steps = [
            TaskModeStep(
                id="step-1",
                title="Define feature contract",
                description="Document expected inputs, outputs, and failure cases for the feature.",
                code=(
                    "// Feature contract\n"
                    "// Input: payload object\n"
                    "// Output: { ok: boolean, data: object }\n"
                    "// Errors: invalid payload type"
                ),
                status=TaskStepStatus.IN_PROGRESS,
                acceptance_criteria=[
                    "Inputs and outputs are explicitly defined",
                    "Edge cases are listed",
                ],
            ),
            TaskModeStep(
                id="step-2",
                title="Implement core feature logic",
                description="Build the core service/function with validation and deterministic output.",
                code=core_snippet,
                status=TaskStepStatus.TODO,
                acceptance_criteria=[
                    "Invalid input handling is present",
                    "Core path returns consistent shape",
                ],
            ),
            TaskModeStep(
                id="step-3",
                title="Integrate with API/UI flow",
                description="Wire the feature into existing route/component flow with clear boundaries.",
                code=(
                    "// Route/handler integration skeleton\n"
                    "// 1) Parse request\n"
                    "// 2) Call executeFeature(payload)\n"
                    "// 3) Return normalized response"
                ),
                status=TaskStepStatus.TODO,
                acceptance_criteria=[
                    "Feature is callable from existing flow",
                    "No regressions in previous behavior",
                ],
            ),
            TaskModeStep(
                id="step-4",
                title="Add validation and tests",
                description="Cover happy path and key edge cases to stabilize rollout.",
                code=test_snippet,
                status=TaskStepStatus.TODO,
                acceptance_criteria=[
                    "Tests cover happy path",
                    "Tests cover at least one edge case",
                ],
            ),
        ]

        title = "Feature Build Plan"
        summary = f"Fallback plan for: {prompt}"
        return title, summary, steps

    def _normalize_steps(self, payload_steps: list, max_steps: int) -> List[TaskModeStep]:
        steps: List[TaskModeStep] = []

        for index, item in enumerate(payload_steps[:max_steps], start=1):
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip() or f"Step {index}"
            description = str(item.get("description") or "").strip()
            code = self._strip_code_fences(item.get("code") or "")

            criteria_raw = item.get("acceptance_criteria")
            criteria: List[str] = []
            if isinstance(criteria_raw, list):
                for criterion in criteria_raw[:8]:
                    normalized = str(criterion or "").strip()
                    if normalized:
                        criteria.append(normalized)

            steps.append(
                TaskModeStep(
                    id=f"step-{index}",
                    title=title,
                    description=description,
                    code=code,
                    status=TaskStepStatus.TODO,
                    acceptance_criteria=criteria,
                )
            )

        return steps

    async def _generate_plan(
        self,
        request: TaskModeRequest,
        *,
        user_id: str,
    ) -> Tuple[str, str, List[TaskModeStep], bool, List[str], List[str]]:
        prompt = self._normalize_prompt(request.prompt)
        code = request.code or ""

        user_knowledge = "No relevant user knowledge was found."
        context_sources: List[str] = []

        if request.include_context:
            user_knowledge, context_sources = await self.context_service.retrieve_user_knowledge(
                user_id=user_id,
                prompt=prompt,
                code=code,
                explicit_context=request.context,
                top_k=8,
            )
        elif request.context:
            user_knowledge = self._clip(request.context, 1500)

        max_steps = max(3, min(int(settings.TASK_MODE_MAX_STEPS), 12))
        task_instruction = (
            f"Build this feature: {prompt}\n"
            "Return the implementation plan and code per step as strict JSON only."
        )

        composed = self.context_service.build_prompt(
            user_knowledge=user_knowledge,
            code=code,
            task=task_instruction,
            max_code_chars=settings.CODE_ASSIST_MAX_CODE_CHARS,
        )

        ai_text = await llama_service.get_ai_response(
            composed,
            system_prompt=self._task_system_prompt(request.language, max_steps),
        )

        warnings: List[str] = []
        payload = self._extract_json_payload(ai_text)
        if not payload:
            title, summary, steps = self._fallback_steps(prompt, request.language)
            warnings.append("Task Mode used fallback planning because AI response was not valid JSON.")
            return title, summary, steps, bool(context_sources), context_sources, warnings

        title = str(payload.get("title") or "Project Plan").strip() or "Project Plan"
        summary = str(payload.get("summary") or "").strip()
        steps = self._normalize_steps(payload.get("steps") or [], max_steps=max_steps)

        if not steps:
            title, summary, steps = self._fallback_steps(prompt, request.language)
            warnings.append("Task Mode generated empty steps and switched to fallback planning.")

        if steps and not any(step.status == TaskStepStatus.IN_PROGRESS for step in steps):
            steps[0].status = TaskStepStatus.IN_PROGRESS

        return title, summary, steps, bool(context_sources), context_sources, warnings

    def _cleanup_sessions(self) -> None:
        now = time.time()
        ttl_seconds = max(120, int(settings.TASK_MODE_SESSION_TTL_SECONDS))

        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if (session.updated_at + ttl_seconds) < now
        ]

        for session_id in expired:
            self._sessions.pop(session_id, None)

        max_sessions = max(50, int(settings.TASK_MODE_MAX_SESSIONS))
        if len(self._sessions) <= max_sessions:
            return

        oldest = sorted(self._sessions.values(), key=lambda item: item.updated_at)
        remove_count = len(self._sessions) - max_sessions
        for item in oldest[:remove_count]:
            self._sessions.pop(item.session_id, None)

    @staticmethod
    def _build_progress(steps: List[TaskModeStep]) -> TaskModeProgress:
        total = len(steps)
        completed = sum(1 for step in steps if step.status == TaskStepStatus.COMPLETED)

        active_step = next((step.id for step in steps if step.status == TaskStepStatus.IN_PROGRESS), None)
        next_step = next((step.id for step in steps if step.status == TaskStepStatus.TODO), None)

        completion_percent = 0.0
        if total > 0:
            completion_percent = round((completed / total) * 100.0, 2)

        return TaskModeProgress(
            total_steps=total,
            completed_steps=completed,
            completion_percent=completion_percent,
            active_step_id=active_step,
            next_step_id=next_step,
        )

    @staticmethod
    def _set_step_progress(
        steps: List[TaskModeStep],
        *,
        completed_step_ids: List[str],
        active_step_id: Optional[str],
    ) -> None:
        completed_set = {item for item in completed_step_ids if str(item).strip()}

        # Preserve previously completed steps and apply new completions.
        for step in steps:
            if step.status == TaskStepStatus.COMPLETED:
                completed_set.add(step.id)

        for step in steps:
            if step.id in completed_set:
                step.status = TaskStepStatus.COMPLETED
            else:
                step.status = TaskStepStatus.TODO

        target_active = None
        if active_step_id and active_step_id not in completed_set:
            target_active = active_step_id
        else:
            first_pending = next((item for item in steps if item.status == TaskStepStatus.TODO), None)
            if first_pending:
                target_active = first_pending.id

        if target_active:
            for step in steps:
                if step.id == target_active and step.status != TaskStepStatus.COMPLETED:
                    step.status = TaskStepStatus.IN_PROGRESS
                    break

    async def build_task_mode_response(
        self,
        request: TaskModeRequest,
        *,
        user_id: str,
    ) -> TaskModeResponse:
        prompt = self._normalize_prompt(request.prompt)
        if not prompt:
            raise ValueError("Prompt is required.")

        if len(prompt) > settings.CODE_ASSIST_MAX_PROMPT_CHARS:
            raise ValueError(
                f"Prompt exceeds limit of {settings.CODE_ASSIST_MAX_PROMPT_CHARS} characters."
            )

        self._cleanup_sessions()

        session: Optional[_TaskSession] = None
        if request.session_id and not request.regenerate_plan:
            existing = self._sessions.get(request.session_id)
            if existing and existing.user_id == user_id:
                session = existing

        warnings: List[str] = []
        if not session:
            title, summary, steps, context_used, context_sources, generate_warnings = await self._generate_plan(
                request,
                user_id=user_id,
            )
            warnings.extend(generate_warnings)

            session_id = request.session_id or str(uuid.uuid4())
            now = time.time()
            session = _TaskSession(
                session_id=session_id,
                user_id=user_id,
                prompt=prompt,
                language=request.language,
                title=self._clip(title, 140) or "Project Plan",
                summary=self._clip(summary, 1200),
                steps=steps,
                context_used=context_used,
                context_sources=context_sources,
                created_at=now,
                updated_at=now,
            )
            self._sessions[session_id] = session
        else:
            if prompt != session.prompt:
                warnings.append(
                    "Task Mode used existing session prompt. Set regenerate_plan=true to rebuild plan for a new prompt."
                )

        self._set_step_progress(
            session.steps,
            completed_step_ids=list(request.completed_step_ids or []),
            active_step_id=request.active_step_id,
        )
        session.updated_at = time.time()

        progress = self._build_progress(session.steps)

        return TaskModeResponse(
            task_mode=True,
            task_session_id=session.session_id,
            title=session.title,
            summary=session.summary,
            steps=[step.model_copy(deep=True) for step in session.steps],
            progress=progress,
            context_used=bool(session.context_used and session.context_sources),
            context_sources=list(session.context_sources),
            warnings=warnings,
            cached=False,
        )


task_mode_service = TaskModeService()
