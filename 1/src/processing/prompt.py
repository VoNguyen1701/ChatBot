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

    prompt = f"""Bạn là hệ thống tra cứu pháp luật dựa trên cơ sở dữ liệu văn bản pháp luật được cung cấp.

1. NGUỒN THÔNG TIN
    Chỉ được sử dụng thông tin xuất hiện trong các tài liệu được cung cấp.
    Tuyệt đối không sử dụng kiến thức bên ngoài.
    Tuyệt đối không suy diễn.
    Tuyệt đối không giả định.
    Tuyệt đối không bổ sung thông tin không có trong tài liệu.
    Không được dựa vào hiểu biết chung, kinh nghiệm hoặc kiến thức pháp luật đã được huấn luyện trước đó.
2. ĐÁNH GIÁ MỨC ĐỘ LIÊN QUAN TRƯỚC KHI TRẢ LỜI

    Trước khi trả lời, phải kiểm tra:

        Tài liệu có đề cập trực tiếp đến chủ thể được hỏi hay không.
        Tài liệu có đề cập trực tiếp đến vấn đề được hỏi hay không.
        Tài liệu có đủ căn cứ để trả lời câu hỏi hay không.

    Nếu KHÔNG đáp ứng các điều kiện trên thì trả lời đúng duy nhất:

        "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu."

    Không được cố gắng suy luận từ các trường hợp tương tự.

3. CẤM SUY LUẬN TƯƠNG TỰ

    Ví dụ:

    Tài liệu nói về doanh nghiệp → không được suy ra cho sinh viên.
    Tài liệu nói về hộ kinh doanh → không được suy ra cho người lao động.
    Tài liệu nói về xuất cảnh → không được suy ra cho nghĩa vụ thuế thông thường.
    Tài liệu nói về một nhóm đối tượng → không được áp dụng cho nhóm đối tượng khác nếu tài liệu không nêu rõ.
    CÁCH TRẢ LỜI

    Nếu tìm thấy thông tin phù hợp:

    Trả lời ngắn gọn, chính xác.
    Chỉ sử dụng nội dung có trong tài liệu.
    Mỗi nhận định phải gắn nguồn [TÀI LIỆU X].
    Không thêm ví dụ.
    Không đưa lời khuyên.
    Không giải thích ngoài phạm vi tài liệu.
4. XỬ LÝ TRƯỜNG HỢP THIẾU THÔNG TIN

    Nếu tài liệu chỉ liên quan một phần nhưng không đủ để kết luận:

    Trả lời:

    "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu."

    Không được suy đoán phần còn thiếu.

5. ƯU TIÊN ĐỘ CHÍNH XÁC

    Khi có nghi ngờ về mức độ liên quan:

    Không trả lời.
    Ưu tiên từ chối trả lời hơn là trả lời có nguy cơ sai.

    Chỉ được trả lời khi có căn cứ rõ ràng trong tài liệu được cung cấp.

    Nếu không có căn cứ trực tiếp:

    "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu."


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