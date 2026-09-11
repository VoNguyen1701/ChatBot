# src/processing/searching.py

from sentence_transformers import SentenceTransformer
from src.storage.mongo import get_db
from sklearn.metrics.pairwise import cosine_similarity

import numpy as np
import re
import time


# ============================================================
# MODEL
# ============================================================

print("[INIT] Loading BGE-M3...")

model = SentenceTransformer("BAAI/bge-m3") #BAAI/bge-m3 ; VoVanPhuc/sup-SimCSE-VietNamese-phobert-base; keepitreal/vietnamese-sber

print("[INIT] BGE-M3 loaded.")


# ============================================================
# DATABASE
# ============================================================

db = get_db()
chunk_col = db["chunks"]


# ============================================================
# CONFIG
# ============================================================

MIN_SCORE_THRESHOLD = 0.5


# ============================================================
# CACHE
# ============================================================

# Các biến này sẽ chứa dữ liệu trong RAM
CACHED_DOCS = None
CACHED_EMBEDDINGS = None


def load_embedding_cache():
    """
    Load toàn bộ chunks có embedding từ MongoDB Atlas
    một lần duy nhất và lưu vào RAM.
    """

    global CACHED_DOCS
    global CACHED_EMBEDDINGS

    # Nếu cache đã tồn tại thì không load lại
    if CACHED_DOCS is not None and CACHED_EMBEDDINGS is not None:
        return

    print("\n==================================================")
    print("[CACHE] Loading embeddings from MongoDB Atlas...")
    print("==================================================")

    start = time.time()

    cursor = chunk_col.find(
        {"embedding": {"$exists": True}},
        {
            "embedding": 1,
            "content": 1,
            "doc_id": 1,
            "section_title": 1,
            "hierarchy": 1
        }
    )

    docs = list(cursor)

    if not docs:
        print("[ERROR] Không có chunks với embedding trong DB!")
        CACHED_DOCS = []
        CACHED_EMBEDDINGS = np.empty((0, 1024), dtype=np.float32)
        return

    # Tạo NumPy matrix
    embeddings = np.asarray(
        [doc["embedding"] for doc in docs],
        dtype=np.float32
    )

    CACHED_DOCS = docs
    CACHED_EMBEDDINGS = embeddings

    elapsed = time.time() - start

    print(f"[CACHE] Loaded chunks: {len(CACHED_DOCS)}")
    print(f"[CACHE] Embedding shape: {CACHED_EMBEDDINGS.shape}")
    print(f"[CACHE] Load time: {elapsed:.3f}s")

    print("==================================================\n")


# ============================================================
# QUERY ENTITY EXTRACTION
# ============================================================

def extract_numbers_from_query(query):
    """
    Trích xuất các con số liên quan đến:
    - Điều
    - Khoản
    - Số hiệu văn bản
    """

    query_lower = query.lower()

    # Điều
    dieu_matches = re.findall(
        r'điều\s+(\d+)',
        query_lower
    )

    dieu_nums = [
        int(m)
        for m in dieu_matches
    ]

    # Khoản
    khoan_matches = re.findall(
        r'khoản\s+(\d+)',
        query_lower
    )

    khoan_nums = [
        int(m)
        for m in khoan_matches
    ]

    # Mã / số hiệu văn bản
    doc_keywords = re.findall(
        r'\b\d{2,4}\b',
        query_lower
    )

    return {
        "dieu": dieu_nums,
        "khoan": khoan_nums,
        "keywords": doc_keywords
    }


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_search(query, top_k=10):

    global CACHED_DOCS
    global CACHED_EMBEDDINGS

    total_start = time.time()

    # --------------------------------------------------------
    # 1. LOAD CACHE
    # --------------------------------------------------------

    load_embedding_cache()

    if not CACHED_DOCS:
        print("[ERROR] Không có dữ liệu để search.")
        return []

    # --------------------------------------------------------
    # 2. PHÂN TÍCH QUERY
    # --------------------------------------------------------

    entities = extract_numbers_from_query(query)

    expanded_parts = []

    for kw in entities["keywords"]:
        expanded_parts.append(
            f"Văn bản {kw}"
        )

    for d in entities["dieu"]:
        expanded_parts.append(
            f"Điều {d}"
        )

    for k in entities["khoan"]:
        expanded_parts.append(
            f"Khoản {k}"
        )

    if expanded_parts:

        context_prefix = " | ".join(
            expanded_parts
        )

        enriched_query = (
            f"{context_prefix} || {query}"
        )

    else:

        enriched_query = query

    # --------------------------------------------------------
    # 3. EMBEDDING QUERY
    # --------------------------------------------------------

    start = time.time()

    query_embedding = model.encode(
        enriched_query,
        normalize_embeddings=True
    )

    query_embedding = np.asarray(
        query_embedding,
        dtype=np.float32
    )

    print(
        f"[TIME] Query embedding: "
        f"{time.time() - start:.3f}s"
    )

    # --------------------------------------------------------
    # 4. VECTOR SIMILARITY
    # --------------------------------------------------------

    start = time.time()

    # Vì cả query và chunk embedding đều normalize,
    # cosine similarity = dot product

    base_scores = np.dot(
        CACHED_EMBEDDINGS,
        query_embedding
    )

    print(
        f"[TIME] Vector similarity: "
        f"{time.time() - start:.3f}s"
    )

    # --------------------------------------------------------
    # 5. BOOST
    # --------------------------------------------------------

    start = time.time()

    final_scores = base_scores.copy()

    for i, doc in enumerate(CACHED_DOCS):

        boost = 0.0

        hierarchy = doc.get(
            "hierarchy",
            {}
        )

        doc_id = str(
            doc.get("doc_id", "")
        ).lower()

        content_lower = str(
            doc.get("content", "")
        ).lower()

        doc_dieu = hierarchy.get(
            "dieu"
        )

        doc_khoan = hierarchy.get(
            "khoan"
        )

        # ----------------------------------------------------
        # Boost số hiệu văn bản
        # ----------------------------------------------------

        for kw in entities["keywords"]:

            if kw in doc_id:

                boost += 0.15

        # ----------------------------------------------------
        # Boost Điều
        # ----------------------------------------------------

        if (
            doc_dieu
            and doc_dieu in entities["dieu"]
        ):

            boost += 0.08

        # ----------------------------------------------------
        # Boost Khoản
        # ----------------------------------------------------

        if (
            doc_khoan
            and doc_khoan in entities["khoan"]
        ):

            boost += 0.08

        # ----------------------------------------------------
        # Boost nội dung
        # ----------------------------------------------------

        for d in entities["dieu"]:

            if f"điều {d}" in content_lower:

                boost += 0.05

        for k in entities["khoan"]:

            if f"khoản {k}" in content_lower:

                boost += 0.05

        final_scores[i] += boost

    print(
        f"[TIME] Boost: "
        f"{time.time() - start:.3f}s"
    )

    # --------------------------------------------------------
    # 6. SORT
    # --------------------------------------------------------

    start = time.time()

    # Lấy index theo thứ tự giảm dần
    sorted_indices = np.argsort(
        final_scores
    )[::-1]

    print(
        f"[TIME] Sort: "
        f"{time.time() - start:.3f}s"
    )

    # --------------------------------------------------------
    # 7. FILTER + TOP K
    # --------------------------------------------------------

    results = []

    for idx in sorted_indices:

        score = float(
            final_scores[idx]
        )

        if score < MIN_SCORE_THRESHOLD:
            break

        results.append(
            (
                score,
                CACHED_DOCS[idx]
            )
        )

        if len(results) >= top_k:
            break

    # --------------------------------------------------------
    # 8. PRINT RESULTS
    # --------------------------------------------------------

    print(
        f"\n🔍 Kết quả tìm kiếm cho query: "
        f"'{query[:50]}...'"
    )

    for i, (score, doc) in enumerate(results):

        print(
            f"{i + 1}. {score:.4f} | "
            f"[{doc.get('doc_id')}] - "
            f"{doc.get('section_title')}"
        )

    print(
        f"[TIME] TOTAL semantic_search: "
        f"{time.time() - total_start:.3f}s"
    )

    return results