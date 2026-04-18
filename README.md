# Intellexa

## 1. Hero Section

Trust-aware, explainable AI for real-world decision support.

Intellexa is a full-stack AI product that reasons before it responds. It combines agentic retrieval, cognitive challenge, ethical safeguards, and transparent explanation in one unified system.

Built with a production-style architecture, Intellexa includes authenticated chat, source-grounded responses, voice mode, and a collaborative AI coding workspace with non-destructive apply flows.

**Intellexa doesn’t just answer questions — it questions the question itself.**

---

## 2. 🚀 What is Intellexa?

Intellexa is an AI assistant designed for higher-stakes questions where trust and reasoning matter.

Instead of only generating text, it first inspects the query for assumptions, ambiguity, and bias. It can then reframe weak prompts, decide when live search is needed, and return answers with sources, confidence, and explanation.

The result is a system that feels less like a generic chatbot and more like a reasoning partner.

---

## 3. 🧠 Core Differentiators

- **Agentic AI decisioning**: The system decides when retrieval is necessary instead of blindly searching every time.
- **Cognitive challenge layer**: Perspective Autopsy and Clarification Questions challenge vague or biased framing before final generation.
- **Ethical + explainable by default**: Responses include trust signals, confidence labels, and a Why this answer layer.
- **Query reframing engine**: Prompts can be transformed into clearer, neutral, evidence-seeking versions before answer synthesis.

---

## 4. ✨ Key Features (Grouped)

### Intelligence and Retrieval
- Agentic RAG flow with conditional web retrieval.
- Query enhancement for weak prompts, plus multi-attempt retrieval fallback.
- Domain-aware relevance filtering for better source quality.
- Source and citation display in final responses.

### Cognitive and Ethical Reasoning
- Perspective Autopsy to detect assumptions, bias, and missing angles.
- Query Reframing (Wow Mode) for neutral and evidence-oriented prompts.
- Clarification Question Engine for ambiguous or sensitive queries.
- Multi-perspective reasoning output across utilitarian, rights-based, and care ethics lenses.

### Trust and Explainability
- Trust score output on a 0 to 100 scale.
- Confidence labels for response reliability.
- Why this answer explanation layer.

### Voice and UX
- Clerk-authenticated, user-scoped dashboard experience.
- Supabase-backed conversation history with sidebar flow.
- Voice Conversation Mode with continuous listening and silence-aware turns.
- Voice-mode realtime guardrails: realtime voice queries force source-grounded retrieval.
- Dual-answer contract: concise short answer for speech, full answer with sources for chat/history.

### Collaborative Coding Workspace
- Monaco multi-user editor with Yjs CRDT sync over Socket.IO.
- Presence and awareness synchronization across shared rooms.
- Non-destructive AI coding assist: suggest first, apply manually.
- Shared AI suggestion events for team-wide review before apply.
- Patch-based Yjs apply flow using diff-match-patch to avoid full-document overwrites.
- Built-in code actions: explain, generate, test generation, security scan, fix, refactor, intent coding, task builder, and why broke analysis.

---

## 5. 🏗️ System Architecture

Intellexa follows a staged reasoning pipeline: understand intent, decide on retrieval, synthesize ethically, and return transparent outputs.

~~~mermaid
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
~~~

Collaborative coding is handled as a realtime, non-destructive layer on top of shared documents.

~~~mermaid
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
~~~

---

## 6. ⚙️ How It Works

1. User signs in via Clerk and submits a query.
2. Intellexa runs Perspective Autopsy to inspect assumptions and framing.
3. If needed, query reframing produces a clearer, neutral version.
4. Clarification logic asks follow-up questions only when uncertainty is high.
5. LLaMA drafts the response.
6. Agentic routing decides whether live web retrieval is required.
7. Retrieved context is filtered and fused into final reasoning.
8. Multi-perspective and ethical layers refine the answer.
9. Trust score, confidence, and explanation metadata are generated.
10. Final response is returned with sources and stored in Supabase history.

---

## 7. 💻 Collaborative AI Coding

Intellexa includes a collaborative code workspace where AI assistance is safe by design: suggestions never overwrite shared code automatically.

### Flow
1. A collaborator selects code (or full file) and submits Ask AI.
2. Frontend sends code plus compact context fields: project context, user memory, selected code, related files.
3. Backend returns a non-destructive payload with suggestion, unified diff, diff hunks, and explanation.
4. Suggestion metadata can be shared with all collaborators as realtime events.
5. Apply Changes triggers patch merge into the Yjs document via transaction.
6. If the file changed in the meantime, fuzzy patching attempts partial safe merge and reports conflicts.

### API Contract (Code Assist)
Request:
~~~json
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
~~~

Response:
~~~json
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
~~~

### Stability Notes
- Debounced assist/autocomplete to reduce noisy realtime traffic.
- Context payload clipping to avoid full-project dumps.
- Schema-level bounds for code and request payload size.
- Manual apply gate to prevent unsolicited AI edits.
- Patch transactions preserve awareness/cursor behavior better than replace-all writes.

---

## 8. 🎤 Voice + Real-Time Intelligence

Intellexa voice mode is optimized for realtime usability without sacrificing traceability.

- Continuous listening with silence-aware turn capture.
- Voice requests are flagged through voice_mode metadata.
- Realtime voice queries enforce web-grounded retrieval when needed.
- Speech output uses concise short answers for low-latency interaction.
- Full detailed answers with sources and explanation are still persisted in chat history.
- If the user speaks while response/search is active, the current cycle is interrupted and listening resumes.

---

## 9. 🧪 Tech Stack

- **Frontend**: React, Vite, Axios, Clerk
- **Backend**: FastAPI, Uvicorn, Pydantic
- **AI Layer**: LLaMA via Hugging Face Router, Gemini for autopsy/ethics/explainability
- **Data Layer**: Supabase (chat history)
- **Collaboration**: Monaco Editor, Yjs, Socket.IO, diff-match-patch
- **Retrieval**: Web search pipeline with optional SerpAPI path

---

## 10. 🚀 Getting Started

### Prerequisites
- Node.js 18+
- Python 3.10+
- npm and pip

### 1) Clone repository
~~~bash
git clone https://github.com/SanskarG-20/Intellexa.git
cd Intellexa
~~~

### 2) Start backend
~~~bash
cd server
python -m venv .venv

# Windows PowerShell
.venv\Scripts\Activate.ps1

# macOS/Linux
# source .venv/bin/activate

pip install -r requirements.txt
python -m app.main
~~~

Backend default: http://localhost:8000

### 3) Start frontend
~~~bash
cd client
npm install
npm run dev
~~~

Frontend default: http://localhost:5173

---

## 11. 🔐 Environment Variables

Create environment files in client and server directories.

### client/.env
~~~env
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
VITE_API_BASE_URL=http://localhost:8000/api
VITE_CLERK_TOKEN_TEMPLATE=
VITE_SUPABASE_URL=your_supabase_project_url
VITE_SUPABASE_ANON_KEY=your_supabase_anon_key
~~~

### server/.env
~~~env
APP_NAME=Intellexa Core Chat
DEBUG=true

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash
FORCE_REFRAME_DEBUG=false

HF_TOKEN=your_huggingface_token
HF_MODEL=meta-llama/Llama-3.1-8B-Instruct

SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_key

SERPAPI_API_KEY=optional_serpapi_key
MOCK_USER_ID=demo_user
~~~

---

## 12. 📁 Folder Structure

~~~text
Intellexa/
|- client/
|  |- src/
|  |  |- components/
|  |  |- pages/
|  |  |- services/
|  |- package.json
|- server/
|  |- app/
|  |  |- api/
|  |  |- schemas/
|  |  |- services/
|  |  |- main.py
|  |- requirements.txt
|- README.md
|- vercel.json
~~~

---

## 13. 🌍 Deployment

- Frontend deployed on Vercel, backend on Railway.
- Set VITE_API_BASE_URL to Railway backend URL with /api suffix.
- Ensure POST /api/v1/chat is reachable from frontend origin.
- Add frontend domain to backend CORS allow-list.
- Redeploy both services after environment updates.

---

## 14. 🎥 Demo

Live demo: https://intellexa-lac.vercel.app/

---

## 15. 🔮 Future Improvements

- Full Clerk user ID propagation across all backend persistence paths.
- Token streaming for lower perceived latency.
- Automated evaluation for bias, factuality, and citation quality.
- Cost-aware model routing and resilient fallback orchestration.
- Human review workflows for high-risk prompts.
