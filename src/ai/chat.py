# src/ai/chat.py

from src.processing.prompt import build_prompt
from src.ai.qwen import ask_qwen

import ollama


def ask_llm(question, context):

    prompt = f"""
Bạn là trợ lý hỏi đáp văn bản pháp luật.

NHIỆM VỤ:
Trả lời câu hỏi của người dùng CHỈ dựa trên thông tin có trong CONTEXT được cung cấp.

CÁC QUY TẮC BẮT BUỘC:

1. Không sử dụng kiến thức bên ngoài CONTEXT.
2. Không tự suy đoán, không tự bổ sung thông tin pháp luật không xuất hiện trong CONTEXT.
3. Nếu CONTEXT không chứa đủ thông tin để trả lời, hãy trả lời:
   "Thông tin được cung cấp chưa đủ để trả lời câu hỏi này."
4. Trả lời trực tiếp vào câu hỏi, không giải thích dài dòng.
5. Ưu tiên trả lời bằng các thông tin, điều kiện, mức thuế, mức phạt hoặc quy định cụ thể xuất hiện trong CONTEXT.
6. Khi CONTEXT có thông tin về Điều, Khoản, Điểm, hãy nêu rõ nguồn tương ứng.
7. Không được tạo ra số liệu, mức phạt, mức thuế, thời hạn hoặc điều kiện nếu CONTEXT không chứa thông tin đó.
8. Nếu có nhiều quy định trong CONTEXT, chỉ sử dụng những quy định liên quan trực tiếp đến câu hỏi.
9. Không nói rằng bạn đã tra cứu Internet hoặc sử dụng nguồn bên ngoài.
10. Không nhắc đến "Context", "LLM", "AI" hoặc các quy tắc này trong câu trả lời.

ĐỊNH DẠNG TRẢ LỜI:
- Trả lời ngắn gọn, khoảng 1-4 câu nếu câu hỏi đơn giản.
- Nếu câu hỏi yêu cầu nhiều điều kiện, có thể dùng danh sách gạch đầu dòng.
- Cuối câu trả lời ghi nguồn theo dạng:
  "Nguồn: [Tên văn bản] - Điều X, Khoản Y."
- Chỉ ghi nguồn khi thông tin đó thực sự xuất hiện trong CONTEXT.

CONTEXT:
{context}

CÂU HỎI:
{question}

Hãy trả lời câu hỏi dựa CHỈ trên CONTEXT.
"""

    response = ollama.chat(
        model="qwen2.5:3b",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    return response["message"]["content"]