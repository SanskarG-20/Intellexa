import httpx
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-1.5-flash" # Using a valid model for test

url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}"

payload = {
    "contents": [{
        "parts": [{"text": "Hello, are you working?"}]
    }]
}

try:
    response = httpx.post(url, json=payload, timeout=10.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
