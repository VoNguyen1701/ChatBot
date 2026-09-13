import time
from src.storage.mongo import get_db

db = get_db()
chunk_col = db["chunks"]

print("=== TEST MONGODB SPEED ===")

# Test 1
start = time.time()

count = chunk_col.count_documents({
    "embedding": {"$exists": True}
})

print(f"Count: {count}")
print(f"Count time: {time.time() - start:.3f}s")


# Test 2
start = time.time()

cursor = chunk_col.find(
    {"embedding": {"$exists": True}},
    {
        "embedding": 1
    }
)

docs = list(cursor)

print(f"Loaded: {len(docs)}")
print(f"Embedding only: {time.time() - start:.3f}s")


# Test 3
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

print(f"Loaded: {len(docs)}")
print(f"All fields: {time.time() - start:.3f}s")