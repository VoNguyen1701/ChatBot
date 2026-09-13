import os
import json
import time
import re

import faiss
import numpy as np
from bson import ObjectId
from sentence_transformers import SentenceTransformer

from src.storage.mongo import get_db


# =========================================================
# CONFIG
# =========================================================

MODEL_NAME = "BAAI/bge-m3"

FAISS_INDEX_PATH = "data/faiss/legal.index"
FAISS_MAPPING_PATH = "data/faiss/mapping.json"

MIN_SCORE_THRESHOLD = 0.5

# Lấy nhiều candidate trước khi boost/reranking
# Ví dụ cần top 5 -> lấy 20 candidate
CANDIDATE_K = 20


# =========================================================
# LOAD MODEL
# =========================================================

print("[INFO] Loading BGE-M3...")
model = SentenceTransformer(MODEL_NAME)


# =========================================================
# LOAD MONGODB
# =========================================================

db = get_db()
chunk_col = db["chunks"]


# =========================================================
# LOAD FAISS
# =========================================================

print("[INFO] Loading FAISS index...")

if not os.path.exists(FAISS_INDEX_PATH):
    raise FileNotFoundError(
        f"Không tìm thấy FAISS index: {FAISS_INDEX_PATH}"
    )

if not os.path.exists(FAISS_MAPPING_PATH):
    raise FileNotFoundError(
        f"Không tìm thấy FAISS mapping: {FAISS_MAPPING_PATH}"
    )

FAISS_INDEX = faiss.read_index(FAISS_INDEX_PATH)

with open(FAISS_MAPPING_PATH, "r", encoding="utf-8") as f:
    FAISS_MAPPING = json.load(f)

print(f"[INFO] FAISS vectors: {FAISS_INDEX.ntotal}")
print(f"[INFO] FAISS mapping: {len(FAISS_MAPPING)}")


# =========================================================
# QUERY REWRITING / ENRICHMENT
# =========================================================

def enrich_query(query):
    """
    Bổ sung một số thông tin từ câu hỏi để hỗ trợ retrieval.

    Giữ logic đơn giản, không dùng LLM ở bước này.
    """

    query = query.strip()

    # Có thể mở rộng thêm sau này.
    return query


# =========================================================
# EXTRACT NUMBER FROM QUERY
# =========================================================

def extract_numbers_from_query(query):
    """
    Lấy các số dạng:
    Điều 10
    Khoản 2
    Điều 21
    ...
    """

    query_lower = query.lower()

    dieu_numbers = re.findall(
        r"điều\s+(\d+)",
        query_lower
    )

    khoan_numbers = re.findall(
        r"khoản\s+(\d+)",
        query_lower
    )

    return dieu_numbers, khoan_numbers


# =========================================================
# SEMANTIC SEARCH
# =========================================================

def semantic_search(query, top_k=5):

    total_start = time.time()

    print("\n" + "=" * 70)
    print("[SEMANTIC SEARCH]")
    print("=" * 70)

    print(f"[QUERY] {query}")

    # -----------------------------------------------------
    # 1. QUERY ENRICHMENT
    # -----------------------------------------------------

    enriched_query = enrich_query(query)

    # -----------------------------------------------------
    # 2. EMBEDDING
    # -----------------------------------------------------

    start = time.time()

    query_embedding = model.encode(
        [enriched_query],
        normalize_embeddings=True,
        convert_to_numpy=True
    ).astype(np.float32)

    embedding_time = time.time() - start

    print(f"[TIME] Query embedding: {embedding_time:.3f}s")

    # -----------------------------------------------------
    # 3. FAISS SEARCH
    # -----------------------------------------------------

    start = time.time()

    candidate_k = max(CANDIDATE_K, top_k * 4)

    # Không vượt quá số vector trong index
    candidate_k = min(
        candidate_k,
        FAISS_INDEX.ntotal
    )

    scores, indices = FAISS_INDEX.search(
        query_embedding,
        candidate_k
    )

    faiss_time = time.time() - start

    print(
        f"[TIME] FAISS search: {faiss_time:.6f}s"
    )

    # -----------------------------------------------------
    # 4. LẤY MONGODB IDs
    # -----------------------------------------------------

    mongo_ids = []

    valid_candidates = []

    for score, idx in zip(
        scores[0],
        indices[0]
    ):

        if idx == -1:
            continue

        # Mapping lưu ObjectId dưới dạng string
        mongo_id_string = FAISS_MAPPING[idx]

        try:
            mongo_id = ObjectId(
                mongo_id_string
            )
        except Exception:
            print(
                f"[WARNING] Invalid ObjectId: "
                f"{mongo_id_string}"
            )
            continue

        mongo_ids.append(mongo_id)

        valid_candidates.append(
            {
                "faiss_score": float(score),
                "mongo_id": mongo_id_string,
                "faiss_index": int(idx)
            }
        )

    if not mongo_ids:
        print("[WARNING] Không tìm thấy candidate.")

        return []

    # -----------------------------------------------------
    # 5. FETCH CHỈ CANDIDATE TỪ MONGODB
    # -----------------------------------------------------

    start = time.time()

    docs = list(
        chunk_col.find(
            {
                "_id": {
                    "$in": mongo_ids
                }
            },
            {
                "_id": 1,
                "content": 1,
                "doc_id": 1,
                "section_title": 1,
                "hierarchy": 1,
                "parent_doc_id": 1
            }
        )
    )

    mongo_time = time.time() - start

    print(
        f"[TIME] MongoDB fetch "
        f"{len(mongo_ids)} candidates: "
        f"{mongo_time:.3f}s"
    )

    print(
        f"[DEBUG] MongoDB returned: "
        f"{len(docs)} documents"
    )

    # -----------------------------------------------------
    # 6. TẠO DICT ĐỂ LOOKUP NHANH
    # -----------------------------------------------------

    docs_dict = {
        str(doc["_id"]): doc
        for doc in docs
    }

    # -----------------------------------------------------
    # 7. EXTRACT QUERY NUMBER
    # -----------------------------------------------------

    dieu_numbers, khoan_numbers = (
        extract_numbers_from_query(query)
    )

    # -----------------------------------------------------
    # 8. BOOST / RERANKING
    # -----------------------------------------------------

    start = time.time()

    ranked_results = []

    query_lower = query.lower()

    for candidate in valid_candidates:

        mongo_id = candidate["mongo_id"]

        doc = docs_dict.get(mongo_id)

        if not doc:
            continue

        original_score = candidate["faiss_score"]

        boost = 0.0

        # ---------------------------------------------
        # DOCUMENT ID
        # ---------------------------------------------

        doc_id = str(
            doc.get("doc_id", "")
        )

        if doc_id.lower() in query_lower:
            boost += 0.15

        # ---------------------------------------------
        # CONTENT
        # ---------------------------------------------

        content = str(
            doc.get("content", "")
        )

        content_lower = content.lower()

        # ---------------------------------------------
        # HIERARCHY
        # ---------------------------------------------

        hierarchy = doc.get(
            "hierarchy",
            {}
        )

        if not isinstance(hierarchy, dict):
            hierarchy = {}

        dieu_value = str(
            hierarchy.get("dieu", "")
        )

        khoan_value = str(
            hierarchy.get("khoan", "")
        )

        # ---------------------------------------------
        # MATCH ĐIỀU
        # ---------------------------------------------

        for dieu in dieu_numbers:

            if dieu == dieu_value:

                boost += 0.08

            elif f"điều {dieu}" in content_lower:

                boost += 0.05

        # ---------------------------------------------
        # MATCH KHOẢN
        # ---------------------------------------------

        for khoan in khoan_numbers:

            if khoan == khoan_value:

                boost += 0.08

            elif f"khoản {khoan}" in content_lower:

                boost += 0.05

        # ---------------------------------------------
        # FINAL SCORE
        # ---------------------------------------------

        final_score = (
            original_score + boost
        )

        ranked_results.append(
            (
                final_score,
                doc,
                original_score,
                boost
            )
        )

    boost_time = time.time() - start

    print(
        f"[TIME] Boost/rerank: "
        f"{boost_time:.6f}s"
    )

    # -----------------------------------------------------
    # 9. SORT
    # -----------------------------------------------------

    start = time.time()

    ranked_results.sort(
        key=lambda x: x[0],
        reverse=True
    )
    
    sort_time = time.time() - start

    print(
        f"[TIME] Sort: "
        f"{sort_time:.6f}s"
    )

    # -----------------------------------------------------
    # 10. THRESHOLD
    # -----------------------------------------------------

    results = []

    for (
        final_score,
        doc,
        original_score,
        boost
    ) in ranked_results:

        if final_score < MIN_SCORE_THRESHOLD:
            continue

        results.append(
            (
                float(final_score),
                doc
            )
        )

        if len(results) >= top_k:
            break

    # -----------------------------------------------------
    # 11. DEBUG RESULTS
    # -----------------------------------------------------

    print("\n" + "=" * 70)
    print("[FINAL RESULTS]")
    print("=" * 70)

    for rank, (
        score,
        doc
    ) in enumerate(
        results,
        start=1
    ):

        print(
            f"{rank}. "
            f"{score:.4f} | "
            f"[{doc.get('doc_id', 'N/A')}] | "
            f"{doc.get('section_title', '')}"
        )

    # -----------------------------------------------------
    # TOTAL TIME
    # -----------------------------------------------------

    total_time = (
        time.time()
        - total_start
    )

    print(
        f"\n[TIME] semantic_search total: "
        f"{total_time:.3f}s"
    )

    return results