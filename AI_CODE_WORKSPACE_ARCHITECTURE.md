# AI Code Workspace Architecture (Intellexa)

## 1. System Architecture

Intellexa Code Workspace is organized in layered modules:

- Frontend (React + Monaco)
  - Workspace shell: explorer + editor + assistant + output panel
  - Virtual file system: in-memory + backend sync + local persistence
  - AI integration: code assist + autocomplete + apply-code workflow
  - Execution panel: sandbox run output + logs
- Backend (FastAPI)
  - Routes layer: request/response contracts and endpoint exposure
  - Controller layer: endpoint orchestration and memory persistence hooks
  - Services layer:
    - context service
    - code service
    - execution service
  - Memory retrieval layer: agentic memory graph + vector retrieval

## 2. Frontend Implementation

Key modules:

- `client/src/components/CodeSpace/CodeSpaceLayout.jsx`
  - 3-panel developer layout plus bottom output/log panel
  - Integrates file system, assistant, execution, and workspace state
- `client/src/components/CodeSpace/CodeEditor.jsx`
  - Monaco editor with multi-language highlighting
  - Keyboard shortcuts: save and run
  - AI autocomplete provider with 300ms debounce
- `client/src/components/CodeSpace/FileExplorer.jsx`
  - Create, delete, rename files and folders
- `client/src/components/CodeSpace/FileTabs.jsx`
  - Multiple open file tabs
- `client/src/components/CodeSpace/CodeAssistant.jsx`
  - Explain, generate, fix, refactor actions
  - Apply generated code into active file
- `client/src/components/CodeSpace/ExecutionPanel.jsx`
  - Sandbox execution controls, stdout/stderr, runtime metadata, and logs

State management:

- `client/src/context/CodeWorkspaceContext.jsx`
  - Maintains active file, file contents, chat history, AI responses, and execution logs
- `client/src/hooks/useVirtualFileSystem.js`
  - Persistent virtual FS with backend sync, auto-save, and local fallback
  - Default project bootstrapping: `/project`, `/project/src`, `/project/src/utils`, `index.js`

## 3. Backend APIs

Primary endpoints:

- `POST /code-assist`
- `POST /api/v1/code/code-assist`
- `POST /api/v1/code/autocomplete`
- `POST /api/v1/code/execute`

Core code files endpoint remains compatible:

- `GET /api/v1/code/files`
- `POST /api/v1/code/files`
- `PUT /api/v1/code/files/{file_id}`
- `DELETE /api/v1/code/files/{file_id}`
- `POST /api/v1/code/files/import`

Contracts are implemented in:

- `server/app/schemas/code.py`

## 4. Execution Sandbox

Implemented in:

- `server/app/services/code_workspace/execution_service.py`

Safety controls:

- Input size limits
- Python syntax pre-check before execution
- AST-based policy checks (blocks dangerous imports/calls)
- Timeout limits (`timeout_ms`)
- Output truncation to prevent oversized payloads
- Optional Docker execution mode (feature flag)

Result contract includes:

- stdout, stderr, exit code, timed_out, runtime_ms, output_truncated

## 5. Memory Context Integration

Implemented in:

- `server/app/services/code_workspace/context_service.py`
- `server/app/services/code_workspace/code_service.py`

Before LLM call, context is injected with strict contract:

```
User Knowledge:
<retrieved context>

Code:
<current code>

Task:
<instruction>
```

Context source:

- Agentic memory retrieval through existing memory retrieval stack
- Returned `context_sources` are propagated to client responses

## 6. Error Handling and Edge Cases

Handled across schemas/services/UI:

- Empty prompt validation
- Long code/prompt limit validation
- API fallback and transport retries for frontend code APIs
- Graceful AI failures (fallback responses instead of crashes)
- Syntax/runtime execution failures surfaced in output panel
- Malicious code blocked by sandbox safety policy
- Local persistence fallback when backend is unavailable

## 7. Performance and Scalability

Implemented optimizations:

- Debounced auto-save (500ms)
- Debounced autocomplete (300ms)
- In-memory response cache for assist/autocomplete
- Backend output truncation and payload size caps
- Local-first resilience in virtual file system

## 8. Verification

Executed checks:

- Backend compile: `python -m compileall app` (pass)
- Frontend production build: `npm run build` (pass)
- Smoke tests: `server/scratch/code_workspace_smoke_tests.py` (all pass)

Smoke-test scenarios validated:

1. small code snippet execution
2. large project-like code assist request
3. syntax error handling
4. runtime error handling
5. malicious code blocking
