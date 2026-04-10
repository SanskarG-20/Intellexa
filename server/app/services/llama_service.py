import json
from typing import Optional, List, Dict
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
            raise cls.AIServiceError(
                "Hugging Face Token is not configured. Add HF_TOKEN to your .env file.",
                status_code=503,
            )

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

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(
                    cls.API_URL,
                    json=payload,
                    headers=headers
                )
            except Exception as e:
                raise cls.AIServiceError(f"Hugging Face connectivity error: {str(e)}")

            if response.status_code == 200:
                try:
                    data = response.json()
                    return data["choices"][0]["message"]["content"].strip()
                except (KeyError, IndexError, TypeError) as e:
                    raise cls.AIServiceError(f"Unexpected response format from Hugging Face: {str(e)}")

            # Handle common errors
            error_details = response.text
            try:
                error_json = response.json()
                error_details = error_json.get("error", {}).get("message", error_details)
            except:
                pass

            if response.status_code == 503:
                raise cls.AIServiceError(
                    f"Model is currently loading or overloaded on Hugging Face. ({error_details})",
                    status_code=503
                )

            raise cls.AIServiceError(
                f"Hugging Face API error ({response.status_code}): {error_details}",
                status_code=response.status_code
            )

llama_service = LlamaService()
