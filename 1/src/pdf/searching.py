# src/search/search.py
import os, sys
import numpy as np
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_db

# =========================
# LOAD MODEL
# =========================
print("[INFO] Loading model...")
model = SentenceTransformer("BAAI/bge-m3")
print("[INFO] Model loaded")

# =========================
# CONNECT DB
# =========================
db = get_db()
chunk_col = db["chunks"]

# =========================
# COSINE SIMILARITY
# =========================
def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

# =========================
# SEARCH FUNCTION
# =========================
def semantic_search(query, top_k=5):
    print(f"\n[QUERY] {query}")

    query_vec = model.encode(query, normalize_embeddings=True)

    chunks = list(chunk_col.find({"embedding": {"$exists": True}}))

    results = []
    for chunk in chunks:
        score = cosine_similarity(query_vec, chunk["embedding"])
        results.append((score, chunk))

    results.sort(key=lambda x: x[0], reverse=True)

    print(f"\n[INFO] Top {top_k} results:\n")

    for i, (score, chunk) in enumerate(results[:top_k], 1):
        print(f"{i}. Score: {score:.4f}")
        print(f"   Title: {chunk.get('section_title')}")
        print(f"   Content: {chunk.get('content')[:200]}...\n")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    while True:
        query = input("\nNhập câu hỏi (hoặc 'exit'): ")
        if query.lower() == "exit":
            break
        semantic_search(query)