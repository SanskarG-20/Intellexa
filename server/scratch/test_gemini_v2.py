import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-2.5-flash"

url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

payload = {
    "contents": [{
        "parts": [{"text": "Hello, are you working?"}]
    }]
}

headers = {
    "Content-Type": "application/json",
    "x-goog-api-key": API_KEY,
}

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=10.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
