# src/processing/prompt.py
# Chức năng xây dựng prompt cho LLM dựa trên kết quả semantic search
from src.processing.searching import semantic_search
import sys
import hashlib
from pathlib import Path
from tqdm import tqdm
from typing import Dict, List

# Setup path
BASE_DIR = Path(__file__).parent.parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

def build_prompt(question):

    results = semantic_search(
        question,
        top_k=10
    )

    if not results:
        print("[WARNING] Không tìm thấy chunks phù hợp!")
        return None

    context = ""
    print(f"\n[DEBUG] Tìm thấy {len(results)} chunks:")

    for i, (score, doc) in enumerate(results, 1):
        print(
            f"  {i}. Score {score:.4f} | {doc['section_title']}"
        )

        context += f"""
[TÀI LIỆU {i}]
Nguồn: {doc['doc_id']} - {doc['section_title']}

{doc['content']}

"""

    prompt = f"""Bạn là hệ thống tra cứu pháp luật chỉ dựa trên tài liệu đã cho.

QUY TẮC BẮT BUỘC:

1. CHỈ TRẢ LỜI DỰA VÀO TÀI LIỆU:
   - Sử dụng TOÀN BỘ nội dung từ các tài liệu dưới
   - KHÔNG dùng kiến thức bên ngoài
   - KHÔNG suy diễn hoặc bổ sung
   - Nếu không yêu cầu thì lấy văn bản có độ retrieved cao nhất làm câu trả lời chính

2. PHẢI TRÍCH DẪN NGUYÊN VĂN:
   - Không được tóm tắt hoặc paraphrase
   - Nếu cần diễn giải, phải dựa trực tiếp trên tài liệu
   - Phải nêu rõ nguồn [TÀI LIỆU X]

3. NẾU KHÔNG CÓ ĐỦ THÔNG TIN:
   - Trả lời: "Tôi không tìm thấy thông tin trong cơ sở dữ liệu."
   - KHÔNG được bịa hoặc sáng tạo câu trả lời


{'='*60}
CÁC TÀI LIỆU THAM KHẢO:
{'='*60}

{context}
{'='*60}
CÂU HỎI:
{'='*60}

{question}

{'='*60}
TRẢ LỜI (dựa hoàn toàn trên tài liệu trên):
{'='*60}
"""
    
    # ⭐ RETURN prompt
    return prompt

    return prompt