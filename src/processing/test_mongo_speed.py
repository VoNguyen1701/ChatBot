import time
from src.storage.mongo import get_db

db = get_db()
chunk_col = db["chunks"]

print("=== TEST MONGODB ATLAS ===")


# =========================
# TEST 1: 1 embedding
# =========================

start = time.time()

doc = chunk_col.find_one(
    {"embedding": {"$exists": True}},
    {"embedding": 1}
)

print(f"1 document: {time.time() - start:.3f}s")


# =========================
# TEST 2: 10 embeddings
# =========================

start = time.time()

docs = list(
    chunk_col.find(
        {"embedding": {"$exists": True}},
        {"embedding": 1}
    ).limit(10)
)

print(f"10 documents: {time.time() - start:.3f}s")


# =========================
# TEST 3: 100 embeddings
# =========================

start = time.time()

docs = list(
    chunk_col.find(
        {"embedding": {"$exists": True}},
        {"embedding": 1}
    ).limit(100)
)

print(f"100 documents: {time.time() - start:.3f}s")


# =========================
# TEST 4: 500 embeddings
# =========================

start = time.time()

docs = list(
    chunk_col.find(
        {"embedding": {"$exists": True}},
        {"embedding": 1}
    ).limit(500)
)

print(f"500 documents: {time.time() - start:.3f}s")