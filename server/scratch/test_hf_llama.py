import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("HF_MODEL")

url = f"https://api-inference.huggingface.co/models/{MODEL}"

payload = {
    "inputs": "Hello, are you Llama 3.1?",
    "parameters": {"max_new_tokens": 50}
}

headers = {"Authorization": f"Bearer {TOKEN}"}

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=20.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
