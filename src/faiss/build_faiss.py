import os
import json
import time

import faiss
import numpy as np

from src.storage.mongo import get_db


# =========================================================
# CONFIG
# =========================================================

INDEX_DIR = "data/faiss"

INDEX_PATH = os.path.join(
    INDEX_DIR,
    "legal.index"
)

MAPPING_PATH = os.path.join(
    INDEX_DIR,
    "mapping.json"
)


# =========================================================
# BUILD INDEX
# =========================================================

def build_faiss_index():

    print("\n========================================")
    print("BUILD FAISS INDEX")
    print("========================================")

    start_total = time.time()

    # -----------------------------------------------------
    # 1. Kết nối MongoDB
    # -----------------------------------------------------

    db = get_db()
    chunk_col = db["chunks"]

    print("[INFO] Đang đọc embedding từ MongoDB...")

    start_mongo = time.time()

    cursor = chunk_col.find(
        {
            "embedding": {
                "$exists": True
            }
        },
        {
            "_id": 1,
            "embedding": 1
        }
    )

    docs = list(cursor)

    mongo_time = time.time() - start_mongo

    print(
        f"[TIME] MongoDB load: "
        f"{mongo_time:.3f}s"
    )

    print(
        f"[INFO] Tổng chunks có embedding: "
        f"{len(docs)}"
    )

    if not docs:
        print("[ERROR] Không có embedding!")
        return

    # -----------------------------------------------------
    # 2. Tạo ma trận embedding
    # -----------------------------------------------------

    print("[INFO] Đang tạo embedding matrix...")

    start_matrix = time.time()

    embeddings = np.asarray(
        [
            doc["embedding"]
            for doc in docs
        ],
        dtype=np.float32
    )

    matrix_time = time.time() - start_matrix

    print(
        f"[TIME] Build matrix: "
        f"{matrix_time:.3f}s"
    )

    print(
        f"[INFO] Matrix shape: "
        f"{embeddings.shape}"
    )

    # -----------------------------------------------------
    # 3. Kiểm tra dimension
    # -----------------------------------------------------

    dimension = embeddings.shape[1]

    print(
        f"[INFO] Vector dimension: "
        f"{dimension}"
    )

    # -----------------------------------------------------
    # 4. FAISS IndexFlatIP
    # -----------------------------------------------------

    print("[INFO] Đang tạo FAISS IndexFlatIP...")

    index = faiss.IndexFlatIP(dimension)

    # -----------------------------------------------------
    # 5. Add vectors
    # -----------------------------------------------------

    print("[INFO] Đang add vectors vào FAISS...")

    start_faiss = time.time()

    index.add(embeddings)

    faiss_time = time.time() - start_faiss

    print(
        f"[TIME] FAISS add: "
        f"{faiss_time:.3f}s"
    )

    print(
        f"[INFO] FAISS ntotal: "
        f"{index.ntotal}"
    )

    # -----------------------------------------------------
    # 6. Tạo thư mục nếu chưa có
    # -----------------------------------------------------

    os.makedirs(
        INDEX_DIR,
        exist_ok=True
    )

    # -----------------------------------------------------
    # 7. Lưu index
    # -----------------------------------------------------

    print("[INFO] Đang lưu FAISS index...")

    faiss.write_index(
        index,
        INDEX_PATH
    )

    # -----------------------------------------------------
    # 8. Mapping FAISS index -> MongoDB _id
    # -----------------------------------------------------

    print("[INFO] Đang tạo mapping...")

    mapping = []

    for doc in docs:

        mapping.append(
            str(doc["_id"])
        )

    with open(
        MAPPING_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            mapping,
            f,
            ensure_ascii=False,
            indent=2
        )

    # -----------------------------------------------------
    # 9. Summary
    # -----------------------------------------------------

    total_time = time.time() - start_total

    print("\n========================================")
    print("FAISS BUILD SUMMARY")
    print("========================================")

    print(
        f"Chunks indexed : {len(docs)}"
    )

    print(
        f"Dimension      : {dimension}"
    )

    print(
        f"FAISS index    : {INDEX_PATH}"
    )

    print(
        f"Mapping        : {MAPPING_PATH}"
    )

    print(
        f"Total time     : {total_time:.3f}s"
    )

    print("========================================")
    print("[INFO] DONE")
    print("========================================")


if __name__ == "__main__":
    build_faiss_index()