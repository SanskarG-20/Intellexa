import httpx
import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("HF_TOKEN")
MODEL = os.getenv("HF_MODEL")

url = f"https://router.huggingface.co/models/{MODEL}"

# Correct Llama 3 format for testing
payload = {
    "inputs": "<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n\nHello, are you Llama 3.1?<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n",
    "parameters": {"max_new_tokens": 50}
}

headers = {"Authorization": f"Bearer {TOKEN}"}

try:
    response = httpx.post(url, json=payload, headers=headers, timeout=20.0)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
