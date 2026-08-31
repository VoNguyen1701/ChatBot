# src/processing/embedding.py
# Chức năng embedding lại tất cả chunks trong DB bằng model mới
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import sys
from pathlib import Path

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

documents = chunk_col.find({})  # Lấy TẤT CẢ chunks

count = chunk_col.count_documents({})

print(f"[INFO] Re-embedding {count} chunks...")

# =========================
# EMBEDDING
# =========================

for doc in tqdm(documents, total=count):

    text = doc.get("content", "")

    if not text.strip():
        continue

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

print("[INFO] DONE")