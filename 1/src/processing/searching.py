# src/processing/searching.py
# Chức năng semantic search: Tính cosine similarity giữa query và chunks đã embedding, trả về top_k kết quả có score cao nhất
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from src.storage.mongo import get_db
import numpy as np

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

MIN_SCORE_THRESHOLD = 0.5  # Lọc score tối thiểu

def semantic_search(query, top_k=10):

    query_embedding = model.encode(
        query,
        normalize_embeddings=True
    )

    docs = list(
        chunk_col.find(
            {"embedding": {"$exists": True}}
        )
    )

    if not docs:
        print("[ERROR] Không có chunks với embedding trong DB!")
        return []

    scores = []

    for doc in docs:

        score = cosine_similarity(
            [query_embedding],
            [doc["embedding"]]
        )[0][0]

        scores.append(
            (score, doc)
        )

    scores.sort(
        key=lambda x: x[0],
        reverse=True
    )

    # Lọc theo threshold trước khi lấy top_k
    filtered_scores = [
        (score, doc) for score, doc in scores 
        if score >= MIN_SCORE_THRESHOLD
    ]

    # Lấy top_k kết quả
    results = filtered_scores[:top_k]

    # In kết quả
    for i, (score, doc) in enumerate(results):
        print(
            f"{i+1}. "
            f"{score:.4f} | "
            f"{doc['section_title']}"
        )
    
    # ⭐ RETURN kết quả
    return results