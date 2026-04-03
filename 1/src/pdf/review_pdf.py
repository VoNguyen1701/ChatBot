# src/pdf/review_pdf.py
import os, sys, re, uuid
from tqdm import tqdm
import pdfplumber

# =========================
# SETUP PATH
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_mongo_client
# =========================
# 7. DEBUG VIEW DATA
# =========================
def preview_data(db, limit_docs=2, limit_chunks=5):
    doc_col = db["documents"]
    chunk_col = db["chunks"]

    print("\n========== DOCUMENTS ==========")
    docs = list(doc_col.find().limit(limit_docs))

    for doc in docs:
        print("\n--- DOCUMENT ---")
        print(f"ID: {doc['_id']}")
        print(f"File: {doc['file_name']}")
        print(f"Category: {doc['category']}")
        print(f"Metadata: {doc['metadata']}")

        print("\nChunks:")
        chunks = list(chunk_col.find({"parent_doc_id": doc["_id"]}).limit(limit_chunks))

        for i, c in enumerate(chunks):
            print(f"\nChunk {i+1}:")
            print(f"Title: {c['section_title']}")
            print(f"Length: {c['content_length']}")
            print(f"Content preview: {c['content'][:300]}...")

    print("\n========== DONE ==========")
if __name__ == "__main__":
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")

    client = get_mongo_client()
    db = client["legal_rag_db"]

    # process_and_store(DATA_RAW_PATH, db)  # comment lại nếu đã insert rồi

    preview_data(db)