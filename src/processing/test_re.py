from src.processing.hybrid_searching import hybrid_search
from src.processing.reranker import rerank


query = "lương 20 triệu thì đóng thuế bao nhiêu"


print("=" * 70)
print("QUERY")
print("=" * 70)

print(query)


# ============================================================
# HYBRID
# ============================================================

results = hybrid_search(
    query,
    top_k=10,
    alpha=0.70,
    verbose=True
)


print()
print("=" * 70)
print("HYBRID TOP 10")
print("=" * 70)

for rank, (score, doc) in enumerate(
    results,
    start=1
):

    print(
        f"{rank:02d}. "
        f"Hybrid={score:.4f} | "
        f"Chunk={doc.get('chunk_id')} | "
        f"Điều={doc.get('hierarchy', {}).get('dieu')} | "
        f"Khoản={doc.get('hierarchy', {}).get('khoan')}"
    )


# ============================================================
# RERANKER
# ============================================================

reranked = rerank(
    query,
    results,
    top_k=10
)


print()
print("=" * 70)
print("RERANKER TOP 10")
print("=" * 70)

for rank, (score, doc) in enumerate(
    reranked,
    start=1
):

    print(
        f"{rank:02d}. "
        f"Rerank={score:.4f} | "
        f"Chunk={doc.get('chunk_id')} | "
        f"Điều={doc.get('hierarchy', {}).get('dieu')} | "
        f"Khoản={doc.get('hierarchy', {}).get('khoan')}"
    )