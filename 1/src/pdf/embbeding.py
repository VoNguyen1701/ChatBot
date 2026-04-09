# src/pdf/embbeding.py
import uuid, os, sys
from tqdm import tqdm
from sentence_transformers import SentenceTransformer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)
# =========================
# 1. LOAD MODEL
# =========================
from datetime import datetime

print("[INFO] Loading model BAAI/bge-m3...")
model = SentenceTransformer("BAAI/bge-m3")  # 🔥 best for Vietnamese
print("[INFO] ✅ Model loaded successfully")


# =========================
# 2. CONNECT DB
# =========================
from storage.mongo import get_db

try:
    db = get_db()
    chunk_col = db["chunks"]

    # test connection
    chunk_col.find_one()

    print("[INFO] ✅ MongoDB connected successfully")

except Exception as e:
    print(f"[ERROR] MongoDB connection failed: {e}")
    exit(1)

# =========================
# 3. EMBEDDING FUNCTION
# =========================
def embed_text(text):
    """Tạo vector embedding từ text"""
    return model.encode(text, normalize_embeddings=True).tolist()


# =========================
# 4. STATS & INFO
# =========================
def get_embedding_stats():
    """Lấy thông tin về chunks"""
    total = chunk_col.count_documents({})
    embedded = chunk_col.count_documents({"embedding": {"$exists": True}})
    need_embed = total - embedded
    
    return {"total": total, "embedded": embedded, "need_embed": need_embed}


# =========================
# 5. RUN EMBEDDING
# =========================
def run_embedding(batch_size=32, force_reembed=False):
    """Chạy embedding cho chunks"""
    
    stats_before = get_embedding_stats()
    print(f"\n[INFO] === Embedding Statistics ===")
    print(f"  Total chunks: {stats_before['total']}")
    print(f"  Already embedded: {stats_before['embedded']}")
    print(f"  Need embedding: {stats_before['need_embed']}")
    
    query = {} if force_reembed else {"embedding": {"$exists": False}}
    chunks = list(chunk_col.find(query))
    
    if not chunks:
        print("[INFO] Không có chunks nào cần embedding. Thoát chương trình.")
        return
    
    print(f"\n[INFO] Starting embedding for {len(chunks)} chunks...")
    start_time = datetime.now()
    
    embedded_count = 0
    failed_count = 0
    
    try:
        for i in tqdm(range(0, len(chunks), batch_size), desc="Embedding"):
            batch = chunks[i:i + batch_size]
            try:
                texts = [c["content"] for c in batch]
                vectors = model.encode(texts, normalize_embeddings=True)
                for chunk, vec in zip(batch, vectors):
                    chunk_col.update_one(
                        {"_id": chunk["_id"]},
                        {"$set": {"embedding": vec.tolist(), "embedded_at": datetime.now()}}
                    )
                    embedded_count += 1
            except Exception as e:
                print(f"[ERROR] Batch {i} failed: {e}")
                failed_count += len(batch)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats_after = get_embedding_stats()
        
        print(f"\n[INFO] === Embedding Complete ===")
        print(f"  ✅ Successfully embedded: {embedded_count}")
        print(f"  ❌ Failed: {failed_count}")
        print(f"  Total embedded now: {stats_after['embedded']}")
        print(f"  Time taken: {elapsed:.2f}s")
        
    except KeyboardInterrupt:
        print("\n[WARNING] Embedding được tạm dừng bởi người dùng.")


# =========================
# 6. PREVIEW EMBEDDING
# =========================
def preview_embeddings(limit=3):
    """Xem trước chunks có embedding"""
    chunks = list(chunk_col.find({"embedding": {"$exists": True}}).limit(limit))
    
    if not chunks:
        print("[INFO] Không có chunks nào đã được embedding. Chạy `python embbeding.py` để bắt đầu embedding.")
        return
    
    print(f"\n[INFO] === Preview {len(chunks)} Embedded Chunks ===")
    for i, chunk in enumerate(chunks, 1):
        vec = chunk.get("embedding", [])
        print(f"\n  Chunk {i}: {chunk.get('section_title', 'N/A')}")
        print(f"    Vector dim: {len(vec)} | Content: {len(chunk.get('content', ''))} chars")


# =========================
# 7. MAIN
# =========================
if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    preview = "--preview" in sys.argv
    
    if preview:
        preview_embeddings()
    else:
        run_embedding(batch_size=32, force_reembed=force)
        print("\n[INFO] Done. Chạy `python embbeding.py --preview` để xem trước embedding.")