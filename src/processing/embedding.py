# src/processing/embedding.py
# Chức năng embedding lại tất cả chunks trong DB bằng model mới
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import sys
from pathlib import Path
import os

from src.storage.mongo import get_db
# Setup path
BASE_DIR = Path(__file__).parent.parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
# =========================
# CONNECT DB
# =========================

db = get_db()

chunk_col = db["chunks"]

# =========================
# LOAD MODEL
# =========================

print("[INFO] Loading BAAI/bge-m3...") #BAAI/bge-m3 ; VoVanPhuc/sup-SimCSE-VietNamese-phobert-base; keepitreal/vietnamese-sbert ; vinai/phobert-base

model = SentenceTransformer("BAAI/bge-m3")

print("[INFO] Model loaded")

# =========================
# GET CHUNKS
# =========================

documents = list(
    chunk_col.find(
        {
            "$or": [
                {"embedding": {"$exists": False}},
                {"embedding": None}
            ]
        }
    )
)

count = len(documents)

print(f"[INFO] Chunks cần embedding: {count}")


if count == 0:
    print("[INFO] Không có chunk mới cần embedding.")
    print("[INFO] DONE")
    exit()


# =========================
# EMBEDDING
# =========================
success = 0
failed = 0

for doc in tqdm(documents, total=count):

    text = doc.get("content", "")

    if not text or not text.strip():
        continue

    try:

        embedding = model.encode(
            text,
            normalize_embeddings=True
        ).tolist()

        chunk_col.update_one(
            {"_id": doc["_id"]},
            {
                "$set": {
                    "embedding": embedding
                }
            }
        )

        success += 1

    except Exception as e:

        failed += 1

        print(
            f"\n[ERROR] Chunk {doc.get('_id')}: {e}"
        )
print("\n========== EMBEDDING SUMMARY ==========")

print(f"Total cần embedding : {count}")
print(f"Successfully embedded: {success}")
print(f"Failed               : {failed}")

print("[INFO] DONE")