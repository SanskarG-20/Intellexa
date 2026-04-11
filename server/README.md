# 🤖 Intellexa Core (IC Chat) Backend

Production-quality backend for Intellexa Core Chatbot using FastAPI, Google Gemini, and Supabase.

## 🚀 Setup Instructions

1.  **Clone the Repository**
    ```bash
    cd server
    ```

2.  **Create a Virtual Environment**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Environment Variables**
    - Copy `.env.example` to `.env`.
    - Fill in your `GEMINI_API_KEY`, `SUPABASE_URL`, and `SUPABASE_KEY`.
    - If you set `GEMINI_MODEL`, use a supported Gemini model such as `gemini-2.5-flash`.

5.  **Database Setup (Supabase)**
    - Create a table named `conversations` with the following schema:
      - `id`: uuid (Primary Key, default: `gen_random_uuid()`)
      - `user_id`: text
      - `message`: text
      - `response`: text
      - `created_at`: timestamp (default: `now()`)

6.  **Run the Server**
    ```bash
    python -m app.main
    ```
    The server will be running at `http://localhost:8000`.
    If Gemini rejects a request, the API now returns a specific error for invalid keys, unsupported models, timeouts, rate limits, and network failures.

## 🛠 API Endpoints

### POST `/api/v1/chat`
**Description**: Send a message to the AI and receive a context-aware response.
**Request Body**:
```json
{
  "message": "Hello, who are you?"
}
```
**Response body**:
```json
{
  "response": "Hello! I am Intellexa Core, your helpful AI assistant..."
}
```

## 📂 Project Structure
- `app/api`: Routes and endpoints.
- `app/services`: Core business logic (LLM integration, context retrieval).
- `app/db`: Database client initialization.
- `app/core`: Configuration and environment settings.
- `app/schemas`: Pydantic models for data validation.

## 🚆 Railway Deployment

This backend is deployment-ready for Railway.

### 1) Create a Railway project
- Connect your GitHub repository.
- Set the service root to `server` (recommended for monorepo layout).

### 2) Configure environment variables in Railway
Add these variables in the Railway service settings:

```env
APP_NAME=Intellexa Core Chat
DEBUG=false
HOST=0.0.0.0

GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-flash

HF_TOKEN=your_huggingface_token
HF_MODEL=meta-llama/Llama-3.1-8B-Instruct

SUPABASE_URL=your_supabase_project_url
SUPABASE_KEY=your_supabase_service_key

SERPAPI_API_KEY=optional_serpapi_key
MOCK_USER_ID=demo_user

# Add your frontend origins as comma-separated values
CORS_ALLOW_ORIGINS=https://your-frontend.vercel.app
```

Notes:
- `PORT` is provided automatically by Railway and used by the app.
- Keep `DEBUG=false` in production.

### 3) Deploy
- Railway will build and start the service automatically.
- Health check endpoint: `GET /`
- Chat endpoint: `POST /api/v1/chat`
