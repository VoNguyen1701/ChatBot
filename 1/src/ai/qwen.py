import requests

OLLAMA_URL = "http://localhost:11434/api/generate"

def ask_qwen(prompt):

    response = requests.post(
        OLLAMA_URL,
        json={
            "model": "qwen2.5:1.5b",
            "prompt": prompt,
            "stream": False
        }
    )

    return response.json()["response"]