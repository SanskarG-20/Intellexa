# Intellexa

Trust-aware, explainable AI for real-world decision support.

Intellexa doesn’t just answer questions — it questions the question itself.

## Key Idea
Intellexa is built as an AI reasoning system, not a generic chatbot. It evaluates user intent before answering, detects bias and assumptions, can reframe problematic prompts, decides when external search is needed, and returns answers with transparent reasoning, ethical safeguards, and trust signals.

## Why Intellexa Is Different
- Agentic AI workflow: the model decides when to call search tools, instead of relying on keyword-triggered retrieval.
- Cognitive challenge layer: Perspective Autopsy and Clarification Questions actively challenge ambiguous or biased framing.
- Query Reframing layer: biased or vague prompts can be rewritten into neutral, evidence-seeking queries before generation.
- Ethical + explainable by default: responses include risk-aware handling, trust metrics, and a clear Why this answer explanation.

## Features
### Identity and User Context
- Clerk authentication for secure signup/login and protected routes.
- User-scoped session experience in the frontend.
- Supabase-backed chat history with a ChatGPT-like sidebar.

### Agentic Intelligence and Retrieval
- Full chat interface built with React + Vite.
- Agentic RAG flow where LLaMA can decide when web search is needed.
- Integrated web search for real-time information retrieval.
- Query Enhancement Layer that reformulates weak search prompts into stronger intent-aware queries.
- Multi-attempt retrieval path for difficult prompts (base query, enhanced query, broad query).
- Domain-aware ranking so sports, politics, and tech queries prioritize relevant sources.
- Source and citation display in responses.

### Cognitive and Ethical Reasoning
- Perspective Autopsy Engine to detect assumptions, bias, and missing angles.
- Query Reframing (Wow Mode) to conditionally rewrite biased or vague questions.
- Multi-perspective responses across:
  - Utilitarian
  - Rights-based
  - Care ethics
- Ethical AI layer with bias detection, risk categorization, and safe response handling.
- Clarification Question Engine that asks follow-up questions only when needed.

### Trust and Explainability
- Trust score output on a 0 to 100 scale.
- Confidence level labels for answer reliability.
- Explanation Engine with Why this answer transparency.

### Product UX
- ChatGPT-like dashboard layout.
- Sidebar history, smooth scrolling, loading states, and typing effects.
- Reframed Question banner shown above responses when reframing is triggered.
- Stop button to interrupt in-flight generation and typing animation.
- Dedicated analysis and source-aware output views.
- Voice Conversation Mode with continuous listening and natural 5-second silence detection.
- Voice-mode realtime guardrail: for realtime queries, web search is forced and answers are source-grounded.
- Dual-response behavior in voice mode: short spoken reply, full answer plus sources/explanation stored in history.
- Clean voice output policy: voice speaks concise final answers only (no URLs, source lists, or system/debug text).

### Real-Time Collaborative Code Workspace
- Monaco-based multi-user editor with Yjs CRDT synchronization and Socket.IO transport.
- Realtime collaboration supports presence, awareness, and shared room state per file workspace.
- AI assistance is integrated as a non-destructive layer: suggestions are proposed first, then manually applied.
- AI suggestions are shared across collaborators as collaboration events so everyone can review before apply.
- Apply flow uses patch-based Yjs transactions instead of full document replacement to reduce sync breakage.
- Security scanning, test generation, intent coding, refactor, and explanation actions are available inside the same panel.

## System Architecture
Intellexa uses a staged architecture that combines agentic decisioning with retrieval-aware reasoning.

```mermaid
flowchart LR
    U[User Query] --> A[Clerk Auth + Protected Route]
    A --> B[Perspective Autopsy]
  B --> R[Conditional Query Reframing]
  R --> C{Need Clarification?}
    C -->|Yes| D[Clarification Question]
    C -->|No| E[LLaMA Draft Answer]
    D --> E
    E --> F{Agentic Search Decision}
    F -->|Search| G[Web Search Tool]
    F -->|No Search| H[Local Reasoning Path]
    G --> I[RAG Context Fusion]
    H --> I
    I --> J[Multi-Perspective + Ethical Layer]
    J --> K[Explanation + Trust Scoring]
    K --> L[Response + Sources + Metadata]
    L --> M[Supabase Conversation History]
```

### Collaborative AI Editing Architecture
```mermaid
flowchart LR
  U1[User A / User B] --> E[Monaco Editor]
  E --> Y[Yjs Doc + Awareness]
  Y --> S[Socket.IO Realtime Hub]
  S --> E

  U1 --> P[Ask AI]
  P --> A[POST /code-assist]
  A --> C[Context Builder: project_context + related_files + user_memory]
  C --> L[LLM + Assist Orchestration]
  L --> R[suggestion + diff + explanation]
  R --> V[Shared AI Suggestion Event]
  V --> U1

  U1 --> AP[Apply Changes]
  AP --> D[diff-match-patch + Yjs transaction]
  D --> Y
```

## How It Works
1. User logs in via Clerk and sends a prompt from the dashboard.
2. Intellexa runs Perspective Autopsy to inspect assumptions, framing, and potential bias.
3. If needed, Intellexa reframes the query into a clearer, neutral, evidence-oriented version.
4. If the query is ambiguous or sensitive, Clarification Question logic can request a follow-up.
5. LLaMA generates a primary answer draft.
6. The system decides agentically whether web search is required.
7. If needed, live web results are retrieved and fused as context.
8. Intellexa generates multi-perspective output and applies the ethical safety layer.
9. Explanation and trust metrics are computed.
10. Final response is returned with sources; when reframing is used, UI shows Reframed Question above the answer.
11. Conversation history is stored in Supabase.

### How Collaborative AI Assist Works
1. User selects code (or entire file) and clicks Ask AI.
2. Frontend sends `POST /code-assist` with code, prompt, and compact context fields.
3. Backend returns a non-destructive assist payload with `suggestion`, `diff`, and `explanation`.
4. The suggestion is visible in the AI panel and can be broadcast to collaborators as `ai_suggestion` context.
5. When Apply Changes is clicked, patch hunks are merged into the active Yjs document via transaction.
6. Changes propagate through realtime sync without full overwrite.
7. If code changed while suggestion was pending, fuzzy patch merge attempts partial safe apply and logs warnings.

### Code Assist API Contract (Collaborative)
Request (`POST /code-assist`):
```json
{
  "code": "...",
  "prompt": "...",
  "project_context": "...",
  "user_memory": "...",
  "selected_code": "...",
  "related_files": [
    { "path": "src/utils/helpers.ts", "language": "typescript", "content": "..." }
  ]
}
```

Response (non-destructive):
```json
{
  "suggestion": "updated full-file suggestion",
  "diff": "unified diff text",
  "diff_hunks": [
    {
      "change_type": "replace",
      "start_offset": 120,
      "end_offset": 160,
      "replacement": "..."
    }
  ],
  "explanation": "what changed and why"
}
```

### Stability and Performance Notes (Workspace)
- Debounced assist and autocomplete requests to reduce noisy realtime traffic.
- Context payload is clipped and limited (selected code + a few related files), not full project dumps each request.
- Code size and payload fields are bounded in backend schema validation.
- Manual apply gate prevents unsolicited AI edits in shared documents.
- Patch-based apply preserves cursor/awareness behavior better than replace-all writes.

### Voice Mode Realtime Flow
1. User speaks and Intellexa waits for a natural pause before submitting.
2. In voice mode, realtime-intent queries are marked with `voice_mode=true`.
3. Backend enforces web search for realtime voice queries and injects latest verified context.
4. Assistant speaks a concise 1 to 2 sentence reply for low-latency voice UX.
5. Full detailed response (including explanation and sources) is still persisted in chat history.
6. If the user speaks while Intellexa is searching or speaking, the current process is canceled and listening resumes.

### Voice + Real-Time Intelligence
- Backend response contract supports:
  - `full_answer`: detailed response for chat UI and history
  - `short_answer`: concise conversational response for voice playback
  - `sources`: query-specific citations used for grounding
- Voice mode uses `short_answer` only, while chat mode displays `full_answer` with sources.
- Search fallback messaging is user-friendly and avoids noisy system phrasing.
- Query-specific source isolation prevents source leakage between unrelated prompts.

## Tech Stack
- Frontend: React, Vite, Clerk, Axios
- Backend: FastAPI, Uvicorn, Pydantic
- AI Layer: LLaMA via Hugging Face Router, Gemini for reasoning/autopsy/ethics support
- Data Layer: Supabase (conversation storage)
- Optional Retrieval Enhancement: SerpAPI key path with fallback web retrieval strategy

## Installation
### Prerequisites
- Node.js 18+
- Python 3.10+
- npm and pip

### 1) Clone and open project
```bash
git clone https://github.com/SanskarG-20/Intellexa.git
cd Intellexa
```

### 2) Backend setup (FastAPI)
```bash
cd server
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python -m app.main
```

Backend starts on http://localhost:8000 and exposes chat at /api/v1/chat.

### 3) Frontend setup (React + Vite)
```bash
cd client
npm install
npm run dev
```

Frontend runs on http://localhost:5173 by default.

## Environment Variables
Create env files in client and server roots.

### Frontend: client/.env
```env
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
VITE_API_BASE_URL=http://localhost:8000/api
# Production example (Vercel -> Railway):
# VITE_API_BASE_URL=https://your-service.up.railway.app/api
VITE_CLERK_TOKEN_TEMPLATE=
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
```

### Backend: server/.env
```env
APP_NAME=Intellexa Core Chat
DEBUG=true

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
# Testing only: force query reframing for every prompt
FORCE_REFRAME_DEBUG=false

HF_TOKEN=your_huggingface_token
HF_MODEL=meta-llama/Llama-3.1-8B-Instruct

SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_key

SERPAPI_API_KEY=optional_serpapi_key
MOCK_USER_ID=demo_user
```

## Deployment Notes (Vercel + Railway)
- Set Vercel env `VITE_API_BASE_URL` to your Railway backend base URL with `/api` suffix.
- Ensure Railway route `POST /api/v1/chat` is reachable.
- Add your Vercel domain in Railway `CORS_ALLOW_ORIGINS`.
- Redeploy both services after env changes.
- Frontend transport now retries across safe API base candidates (configured env URL, same-origin `/api`, and known production fallback) when network routing fails.

## Folder Structure
```text
Intellexa/
|- client/
|  |- src/
|  |  |- components/
|  |  |- pages/
|  |  |- services/
|  |  |- AppRoutes.jsx
|  |  |- main.jsx
|  |- package.json
|- server/
|  |- app/
|  |  |- api/
|  |  |- core/
|  |  |- db/
|  |  |- schemas/
|  |  |- services/
|  |  |- main.py
|  |- requirements.txt
|- README.md
|- vercel.json
```

## Demo
- Live Demo: https://intellexa-lac.vercel.app/

## Future Improvements
- Full Clerk user ID propagation into backend persistence path.
- Streaming token responses for lower perceived latency.
- Automated evaluation suite for bias, factuality, and citation quality.
- Multi-tenant model routing and cost-aware fallback policy.
- Human review workflows for high-risk prompts.
