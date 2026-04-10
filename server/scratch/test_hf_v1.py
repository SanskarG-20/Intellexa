import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("HF_MODEL")

url = "https://router.huggingface.co/v1/chat/completions"

payload = {
    "model": MODEL,
    "messages": [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello! What is your name?"}
    ],
    "max_tokens": 100
}

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=20.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
