#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Xóa tất cả embeddings cũ từ MongoDB
Sau đó chạy: python -m src.processing.embedding
"""

from src.storage.mongo import get_db

db = get_db()
chunk_col = db["chunks"]

# =========================
# XÓA TẤT CẢ EMBEDDINGS CŨ
# =========================

print("[INFO] Xóa tất cả embeddings cũ...")

result = chunk_col.update_many(
    {},
    {"$unset": {"embedding": ""}}
)

print(f"[INFO] ✅ Đã xóa {result.modified_count} documents")

total = chunk_col.count_documents({})
print(f"[INFO] Tổng chunks: {total}")

# =========================
# Bây giờ chạy: python -m src.processing.embedding
# =========================

print("\n[NEXT STEP]")
print("Chạy lệnh: python -m src.processing.embedding")
print("để re-embed tất cả chunks bằng keepitreal/vietnamese-sbert")
