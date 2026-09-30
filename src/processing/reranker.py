"""
RERANKER

Nhận:
    Query
    Top-K kết quả từ Hybrid

Trả về:
    Các chunk được sắp xếp lại theo điểm reranker
"""

from sentence_transformers import CrossEncoder


# ============================================================
# CONFIG
# ============================================================

# Model reranker
MODEL_NAME = "BAAI/bge-reranker-v2-m3"

# Số kết quả đưa vào reranker
RERANK_TOP_K = 10

# ============================================================
# LOAD MODEL
# ============================================================

print("[RERANKER] Loading model...")

model = CrossEncoder(
    MODEL_NAME,
    max_length=512
)

print(
    f"[RERANKER] Model loaded: {MODEL_NAME}"
)


# ============================================================
# RERANK
# ============================================================

def rerank(
    query,
    results,
    top_k=RERANK_TOP_K
):
    """
    results:
        [
            (score, doc),
            ...
        ]

    return:
        [
            (reranker_score, doc),
            ...
        ]
    """

    if not results:
        return []

    # --------------------------------------------------------
    # Chuẩn bị cặp:
    # (query, document)
    # --------------------------------------------------------

    pairs = []

    valid_results = []

    for score, doc in results:

        if not doc:
            continue

        content = doc.get(
            "content",
            ""
        )

        if not content:
            continue

        pairs.append(
            (
                query,
                content
            )
        )

        valid_results.append(
            (score, doc)
        )

    if not pairs:
        return []

    # --------------------------------------------------------
    # Predict
    # --------------------------------------------------------

    scores = model.predict(
        pairs,
        show_progress_bar=False
    )

    # --------------------------------------------------------
    # Ghép score + document
    # --------------------------------------------------------

    reranked = []

    for index, score in enumerate(scores):

        _, doc = valid_results[index]

        reranked.append(
            (
                float(score),
                doc
            )
        )

    # --------------------------------------------------------
    # Sort giảm dần
    # --------------------------------------------------------

    reranked.sort(
        key=lambda x: x[0],
        reverse=True
    )

    return reranked[:top_k]