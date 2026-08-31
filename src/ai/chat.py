# src/ai/chat.py

from src.processing.prompt import build_prompt
from src.ai.qwen import ask_qwen

import ollama

def ask_llm(question, context):

    prompt = f"""
    Bạn là trợ lý pháp luật.

    Context:

    {context}

    Câu hỏi:

    {question}

    Trả lời dựa trên context.
    """

    response = ollama.chat(
        model="qwen2.5:1.5b",
        messages=[
            {
                "role":"user",
                "content":prompt
            }
        ]
    )

    return response["message"]["content"]