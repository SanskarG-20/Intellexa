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
