# src/processing/searching.py
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from src.storage.mongo import get_db
import numpy as np
import re
from datetime import datetime

# =====================
# MODEL
# =====================
model = SentenceTransformer("BAAI/bge-m3")

# =====================
# DB
# =====================
db = get_db()
chunk_col = db["chunks"]

# =====================
# SEARCH CONFIG
# =====================
MIN_SCORE_THRESHOLD = 0.5


def extract_numbers_and_time(query):
    """
    Trích xuất các con số thực thể (Điều, Khoản, Mã luật) và mốc thời gian quy chiếu lịch sử.
    """
    query_lower = query.lower()
    
    dieu_matches = re.findall(r'điều\s+(\d+)', query_lower)
    dieu_nums = [int(m) for m in dieu_matches] if dieu_matches else []
    
    khoan_matches = re.findall(r'khoán\s+(\d+)|khoản\s+(\d+)', query_lower)
    khoan_nums = []
    for m in khoan_matches:
        for val in m:
            if val:
                khoan_nums.append(int(val))
                
    doc_keywords = re.findall(r'\b\d{2,4}\b', query_lower)
    
    # 🌟 TRÍCH XUẤT THỜI GIAN ĐỂ PHÂN LUỒNG TRA CỨU
    target_date = None
    
    # TH1: Tìm năm cụ thể (Ví dụ: "năm 2020", "vào năm 2023")
    year_match = re.search(r'(?:năm|vào năm)\s+(\d{4})', query_lower)
    if year_match:
        year = year_match.group(1)
        target_date = f"{year}-12-31" # Quy về cuối năm đó để quét tầm hiệu lực
    
    # TH2: Tìm ngày cụ thể dạng DD/MM/YYYY hoặc YYYY-MM-DD
    date_match = re.search(r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})', query_lower)
    if date_match:
        d, m, y = date_match.groups()
        target_date = f"{y}-{int(m):02d}-{int(d):02d}"

    return {
        "dieu": dieu_nums,
        "khoan": khoan_nums,
        "keywords": doc_keywords,
        "target_date": target_date
    }


def semantic_search(query, top_k=10):
    # 1. Phân tích thực thể số và mốc thời gian từ câu hỏi
    entities = extract_numbers_and_time(query)
    target_date = entities["target_date"]
    
    # 2. XÂY DỰNG BỘ LỌC DATABASE (MONGO QUERY FILTER) - KHÔNG LOAD ALL CHUNKS LÊN RAM
    db_filter = {"embedding": {"$exists": True}}
    
    if target_date:
        # KỊCH BẢN LỊCH SỬ: Người dùng hỏi về một thời điểm cụ thể trong quá khứ
        # Chunk hợp lệ nếu thời điểm hỏi nằm trong khoảng [valid_from, valid_to]
        db_filter["$and"] = [
            {"valid_from": {"$lte": target_date}},
            {"$or": [
                {"valid_to": None},
                {"valid_to": {"$gte": target_date}}
            ]}
        ]
        print(f"⏰ [TRA CỨU LỊCH SỬ] Lọc văn bản có hiệu lực tại ngày: {target_date}")
    else:
        # KỊCH BẢN HIỆN TẠI: Mặc định tối ưu, loại bỏ hoàn toàn các văn bản đã bị hủy bỏ/hết hiệu lực
        db_filter["status"] = "dang_co_hieu_luc"
        print("⚡ [TRA CỨU HIỆN HÀNH] Chỉ quét các văn bản đang có hiệu lực.")

    # 3. QUERY EXPANSION: Làm giàu ngữ cảnh câu hỏi
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

    # Mã hóa vector của câu hỏi
    query_embedding = model.encode(enriched_query, normalize_embeddings=True)

    # 4. LẤY DỮ LIỆU ĐÃ ĐƯỢC LỌC TỪ DATABASE TRƯỚC
    docs = list(chunk_col.find(db_filter))
    if not docs:
        print(f"[WARN] Không tìm thấy chunk nào phù hợp với bộ lọc thời gian trong DB!")
        return []
    
    scores = []
    for doc in docs:
        # Tính toán cosine similarity trên tập dữ liệu tinh gọn
        base_score = cosine_similarity([query_embedding], [doc["embedding"]])[0][0]
        
        boost = 0.0
        hierarchy = doc.get("hierarchy", {})
        doc_id = str(doc.get("doc_id", "")).lower()
        content_lower = str(doc.get("content", "")).lower()
        
        doc_dieu = hierarchy.get("dieu")
        doc_khoan = hierarchy.get("khoan")
        
        # --- CHIẾN LƯỢC THƯỞNG ĐIỂM TINH CHỈNH TRỌNG SỐ ---
        for kw in entities["keywords"]:
            if kw in doc_id:
                boost += 0.15 

        if doc_dieu and doc_dieu in entities["dieu"]:
            boost += 0.08  
            
        if doc_khoan and doc_khoan in entities["khoan"]:
            boost += 0.08  
            
        for d in entities["dieu"]:
            if f"điều {d}" in content_lower:
                boost += 0.05
        for k in entities["khoan"]:
            if f"khoản {k}" in content_lower:
                boost += 0.05

        final_score = base_score + boost
        scores.append((final_score, doc))

    # 5. Sắp xếp và trả kết quả
    scores.sort(key=lambda x: x[0], reverse=True)

    filtered_scores = [
        (score, doc) for score, doc in scores 
        if score >= MIN_SCORE_THRESHOLD
    ]

    results = filtered_scores[:top_k]

    # In log kiểm tra
    print(f"🔍 Kết quả tìm kiếm cho query: '{query[:50]}...' (Tìm thấy {len(docs)} chunks phù hợp điều kiện thời gian)")
    for i, (score, doc) in enumerate(results):
        print(
            f"{i+1}. {score:.4f} | Status: [{doc.get('status')}] | "
            f"[{doc.get('doc_id')}] - {doc.get('section_title')}"
        )
    
    return results