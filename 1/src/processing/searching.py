# src/processing/searching.py
# Chức năng semantic search: Tính cosine similarity giữa query và chunks đã embedding, trả về top_k kết quả có score cao nhất
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from src.storage.mongo import get_db
import numpy as np
import re

# =====================
# MODEL
# =====================

model = SentenceTransformer("BAAI/bge-m3") #BAAI/bge-m3 ; VoVanPhuc/sup-SimCSE-VietNamese-phobert-base; keepitreal/vietnamese-sber

# =====================
# DB
# =====================

db = get_db()

chunk_col = db["chunks"]

# =====================
# SEARCH
# =====================

MIN_SCORE_THRESHOLD = 0.5

def extract_numbers_from_query(query):
    """
    Trích xuất các con số đi kèm chữ 'Điều', 'Khoản' hoặc số hiệu văn bản từ câu hỏi
    """
    query_lower = query.lower()
    
    # Tìm số Điều (ví dụ: "Điều 5" -> 5)
    dieu_matches = re.findall(r'điều\s+(\d+)', query_lower)
    dieu_nums = [int(m) for m in dieu_matches] if dieu_matches else []
    
    # Tìm số Khoản (ví dụ: "Khoản 25" -> 25)
    khoan_matches = re.findall(r'khoán\s+(\d+)|khoản\s+(\d+)', query_lower)
    khoan_nums = []
    for m in khoan_matches:
        for val in m:
            if val:
                khoan_nums.append(int(val))
                
    # Tìm mã luật nếu có đề cập (ví dụ: "149", "109", "2025")
    doc_keywords = re.findall(r'\b\d{2,4}\b', query_lower)
    
    return {
        "dieu": dieu_nums,
        "khoan": khoan_nums,
        "keywords": doc_keywords
    }

def semantic_search(query, top_k=10):
    # 1. Phân tích thực thể số từ câu hỏi người dùng
    entities = extract_numbers_from_query(query)
    
    # 🌟 KỸ THUẬT TIỀN XỬ LÝ: QUERY EXPANSION (LÀM GIÀU NGỮ CẢNH CỨNG)
    expanded_parts = []
    for kw in entities["keywords"]:
        expanded_parts.append(f"Văn bản {kw}")
    for d in entities["dieu"]:
        expanded_parts.append(f"Điều {d}")
    for k in entities["khoan"]:
        expanded_parts.append(f"Khoản {k}")
        
    if expanded_parts:
        context_prefix = " | ".join(expanded_parts)
        enriched_query = f"{context_prefix} || {query}"
    else:
        enriched_query = query

    # Mã hóa vector của câu hỏi ĐÃ ĐƯỢC LÀM GIÀU
    query_embedding = model.encode(enriched_query, normalize_embeddings=True)

    # 2. Lấy toàn bộ chunks từ DB để quét
    docs = list(chunk_col.find({"embedding": {"$exists": True}}))
    if not docs:
        print("[ERROR] Không có chunks với embedding trong DB!")
        return []
    
    scores = []
    for doc in docs:
        base_score = cosine_similarity([query_embedding], [doc["embedding"]])[0][0]
        
        boost = 0.0
        hierarchy = doc.get("hierarchy", {})
        doc_id = str(doc.get("doc_id", "")).lower()
        content_lower = str(doc.get("content", "")).lower()
        
        doc_dieu = hierarchy.get("dieu")
        doc_khoan = hierarchy.get("khoan")
        
        # --- CHIẾN LƯỢC THƯỞNG ĐIỂM ĐÃ ĐƯỢC TINH CHỈNH TRỌNG SỐ ---
        for kw in entities["keywords"]:
            if kw in doc_id:
                boost += 0.15  # Tăng lên 0.15 để kéo mạnh văn bản luật mục tiêu

        if doc_dieu and doc_dieu in entities["dieu"]:
            boost += 0.08  # Tăng lên 0.08 để kéo mạnh Điều mục tiêu
            
        if doc_khoan and doc_khoan in entities["khoan"]:
            boost += 0.08  # Tăng lên 0.08 để khẳng định Khoản mục tiêu
            
        for d in entities["dieu"]:
            if f"điều {d}" in content_lower:
                boost += 0.05
        for k in entities["khoan"]:
            if f"khoản {k}" in content_lower:
                boost += 0.05

        final_score = base_score + boost
        scores.append((final_score, doc))

    # 4. Sắp xếp lại danh sách
    scores.sort(key=lambda x: x[0], reverse=True)

    filtered_scores = [
        (score, doc) for score, doc in scores 
        if score >= MIN_SCORE_THRESHOLD
    ]

    results = filtered_scores[:top_k]

    # In kết quả kiểm tra ra Terminal
    print(f"\n🔍 Kết quả tìm kiếm cho query: '{query[:50]}...'")
    for i, (score, doc) in enumerate(results):
        print(
            f"{i+1}. {score:.4f} | "
            f"[{doc.get('doc_id')}] - {doc.get('section_title')}"
        )
    
    return results