import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HF_TOKEN")

headers = {"Authorization": f"Bearer {TOKEN}"}

# Try to get models list from the router
urls = [
    "https://router.huggingface.co/models",
    "https://router.huggingface.co/v1/models",
    "https://router.huggingface.co/api/models"
]

for url in urls:
    try:
        response = httpx.get(url, headers=headers, timeout=10.0)
        print(f"URL: {url} -> Status: {response.status_code}")
        if response.status_code == 200:
            print(f"Content: {response.text[:200]}")
    except Exception as e:
        print(f"URL: {url} -> Error: {e}")
