import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("HF_MODEL")

headers = {"Authorization": f"Bearer {TOKEN}"}

# List of possible endpoints in 2026
endpoints = [
    f"https://router.huggingface.co/v1/chat/completions",
    f"https://router.huggingface.co/openai/v1/chat/completions",
    f"https://router.huggingface.co/v1/{MODEL}/chat/completions",
    f"https://router.huggingface.co/models/{MODEL}",
    f"https://api-inference.huggingface.co/models/{MODEL}"
]

for url in endpoints:
    try:
        # Just head or short post to check
        response = httpx.post(url, json={"messages": [{"role": "user", "content": "hi"}]}, headers=headers, timeout=5.0)
        print(f"URL: {url} -> Status: {response.status_code}")
        print(f"Response: {response.text[:100]}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
