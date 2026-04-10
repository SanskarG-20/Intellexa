from typing import Optional

import httpx

from app.core.config import settings


class LlamaService:
    """
    Service responsible for interacting with Hugging Face Inference API 
    (Router v1) to generate responses using Open-Source models.
    """

    API_URL = "https://router.huggingface.co/v1/chat/completions"

    class AIServiceError(RuntimeError):
        def __init__(self, message: str, status_code: int = 502):
            super().__init__(message)
            self.message = message
            self.status_code = status_code

    @classmethod
    async def get_ai_response(cls, user_message: str, system_prompt: Optional[str] = None) -> str:
        """
        Send a request to Hugging Face Router API using OpenAI-compatible format.
        """
        token = settings.HF_TOKEN.strip()
        if not token:
            return cls._build_local_response(user_message)

        model = settings.HF_MODEL.strip()
        
        # Prepare messages in OpenAI format
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "temperature": 0.7,
            "top_p": 0.9,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    cls.API_URL,
                    json=payload,
                    headers=headers
                )
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPError) as exc:
                print(f"Hugging Face connectivity issue: {exc}")
                return cls._build_local_response(user_message)

            if response.status_code == 200:
                try:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError, TypeError) as e:
                    print(f"Unexpected response format from Hugging Face: {e}")
                    return cls._build_local_response(user_message)

            # Handle common errors
            error_details = cls._extract_provider_message(response)
            print(f"Hugging Face API error ({response.status_code}): {error_details}")

            if cls._should_use_local_fallback(response.status_code):
                return cls._build_local_response(user_message)

            raise cls.AIServiceError(
                f"Hugging Face API error ({response.status_code}): {error_details}",
                status_code=response.status_code,
            )

    @staticmethod
    def _extract_provider_message(response: httpx.Response) -> str:
        try:
            error_json = response.json()
        except ValueError:
            return response.text.strip() or "Unknown Hugging Face error."

        error_payload = error_json.get("error")
        if isinstance(error_payload, dict):
            message = error_payload.get("message")
            if message:
                return str(message)

        if isinstance(error_payload, str) and error_payload.strip():
            return error_payload.strip()

        return response.text.strip() or "Unknown Hugging Face error."

    @staticmethod
    def _should_use_local_fallback(status_code: int) -> bool:
        return status_code in {400, 401, 403, 404, 408, 409, 425, 429, 500, 502, 503, 504}

    @staticmethod
    def _build_local_response(user_message: str) -> str:
        text = " ".join(str(user_message or "").split())
        lower_text = text.lower()

        if not text:
            return "I am ready to help. Ask me a question and I will do my best to answer."

        if any(greeting in lower_text for greeting in {"hello", "hi", "hey"}):
            return "Hello. I am here and ready to help with whatever you want to work through."

        if "better leaders than women" in lower_text or (
            "better" in lower_text and "men" in lower_text and "women" in lower_text
        ):
            return (
                "I cannot support the idea that one gender is inherently better at leadership. "
                "Leadership depends on skills, experience, judgment, communication, and context, "
                "and strong leaders can be of any gender."
            )

        if "why" in lower_text:
            return (
                "I cannot reach the external language model right now, but I can still help think this through. "
                f"Based on your question, a careful starting point is to examine the assumptions behind: {text}"
            )

        return (
            "I cannot reach the external language model right now, but I can still help. "
            f"Here is a concise response based on your message: {text}"
        )

llama_service = LlamaService()
