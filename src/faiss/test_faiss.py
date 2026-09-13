import json
import time

import faiss
import numpy as np

from bson import ObjectId
from sentence_transformers import SentenceTransformer
from src.storage.mongo import get_db


INDEX_PATH = "data/faiss/legal.index"
MAPPING_PATH = "data/faiss/mapping.json"


# =========================================================
# LOAD MODEL
# =========================================================

print("[INFO] Loading BGE-M3...")

model = SentenceTransformer(
    "BAAI/bge-m3"
)


# =========================================================
# LOAD FAISS
# =========================================================

print("[INFO] Loading FAISS index...")

start = time.time()

index = faiss.read_index(
    INDEX_PATH
)

print(
    f"[TIME] Load FAISS: "
    f"{time.time() - start:.3f}s"
)

print(
    f"[INFO] FAISS vectors: "
    f"{index.ntotal}"
)


# =========================================================
# LOAD MAPPING
# =========================================================

with open(
    MAPPING_PATH,
    "r",
    encoding="utf-8"
) as f:

    mapping = json.load(f)


# =========================================================
# MONGO
# =========================================================

db = get_db()
chunk_col = db["chunks"]


# =========================================================
# SEARCH
# =========================================================

query = input(
    "\nNhập câu hỏi: "
)

print(
    f"\n[QUERY] {query}"
)


# ---------------------------------------------------------
# Query embedding
# ---------------------------------------------------------

start = time.time()

query_embedding = model.encode(
    query,
    normalize_embeddings=True
)

query_embedding = np.asarray(
    query_embedding,
    dtype=np.float32
)

query_embedding = query_embedding.reshape(
    1,
    -1
)

print(
    f"[TIME] Query embedding: "
    f"{time.time() - start:.3f}s"
)


# ---------------------------------------------------------
# FAISS search
# ---------------------------------------------------------

start = time.time()

scores, indices = index.search(
    query_embedding,
    10
)

faiss_time = time.time() - start

print(
    f"[TIME] FAISS search: "
    f"{faiss_time:.6f}s"
)


# =========================================================
# FETCH MONGO DOCUMENTS
# =========================================================

print("\n========================================")
print("DEBUG MAPPING")
print("========================================")

print("[DEBUG] FAISS indices:")
print(indices[0])

print("\n[DEBUG] MongoDB IDs from mapping:")

for i, idx in enumerate(indices[0], start=1):

    if idx == -1:
        continue

    mongo_id = mapping[idx]

    print(
        f"{i}. FAISS index = {idx}"
        f" | MongoDB _id = {mongo_id}"
        f" | type = {type(mongo_id)}"
    )


# =========================================================
# FETCH MONGO
# =========================================================

mongo_ids = []

for idx in indices[0]:

    if idx == -1:
        continue

    mongo_id = mapping[idx]

    try:
        mongo_ids.append(
            ObjectId(mongo_id)
        )
    except Exception:
        print(
            f"[WARNING] Không thể chuyển ObjectId: "
            f"{mongo_id}"
        )


print("\n[DEBUG] Query MongoDB với:")
print(mongo_ids)


start = time.time()

docs = list(
    chunk_col.find(
        {
            "_id": {
                "$in": mongo_ids
            }
        },
        {
            "embedding": 0
        }
    )
)

mongo_time = time.time() - start


print(
    f"\n[TIME] MongoDB fetch top 10: "
    f"{mongo_time:.3f}s"
)

print(
    f"[DEBUG] MongoDB trả về: "
    f"{len(docs)} documents"
)


# =========================================================
# SHOW MONGO IDS
# =========================================================

print("\n[DEBUG] MongoDB IDs thực tế:")

for doc in docs:

    print(
        f"_id = {doc.get('_id')}"
        f" | type = {type(doc.get('_id'))}"
    )

# =========================================================
# CREATE DICT
# =========================================================

docs_dict = {
    str(doc["_id"]): doc
    for doc in docs
}


# =========================================================
# SHOW RESULTS
# =========================================================

print("\n========================================")
print("FAISS RESULTS")
print("========================================")


for rank, (score, idx) in enumerate(
    zip(scores[0], indices[0]),
    start=1
):

    if idx == -1:
        continue

    mongo_id = mapping[idx]

    doc = docs_dict.get(
        mongo_id
    )

    if not doc:
        continue

    print(
        f"\n{rank}. "
        f"{score:.4f}"
        f" | [{doc.get('doc_id')}]"
        f" - {doc.get('section_title')}"
    )

    content = str(
        doc.get("content", "")
    ).replace(
        "\n",
        " "
    )

    print(
        f"   {content[:300]}..."
    )