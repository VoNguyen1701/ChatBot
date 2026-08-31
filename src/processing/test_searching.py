# src/processing/test_searching.py

import json

from src.processing.searching import semantic_search


with open(
    "datasets/golden_dataset.json",
    "r",
    encoding="utf-8"
) as f:
    dataset = json.load(f)

# Biến đếm tổng quan để đánh giá độ chính xác (Accuracy)
total_queries = len(dataset)
hit_top1 = 0
hit_top5 = 0

for item in dataset:
    query_id = item["query_id"]
    question = item["query"]
    relevant_ids = item["relevant_ids"]

    # Tiến hành tìm kiếm thông minh bằng hàm đã cải tiến boost điểm số
    results = semantic_search(
        question,
        top_k=5
    )

    print("\n" + "=" * 100)
    print("QUERY:", query_id)
    print("QUESTION:", question)
    print("GROUND TRUTH (EXPECTED UUID):", relevant_ids)
    print()

    found = False

    for rank, (score, doc) in enumerate(results, start=1):
        # ⭐ SỬA LỖI 1: Lấy trường 'chunk_id' (UUID) để so khớp với file Golden thay vì lấy '_id' (ObjectId)
        retrieved_uuid = doc.get("chunk_id")

        if retrieved_uuid in relevant_ids:
            found = True
            marker = "✅"
            if rank == 1:
                hit_top1 += 1
            hit_top5 += 1
        else:
            marker = "❌"

        # ⭐ SỬA LỖI 2: Đọc dữ liệu từ tầng 'hierarchy' để log không bị 'None'
        hierarchy = doc.get("hierarchy", {})
        dieu = hierarchy.get("dieu")
        khoan = hierarchy.get("khoan")

        print(
            f"{marker} "
            f"Top {rank}"
            f" | Score={score:.4f}"
            f" | Điều={dieu}"
            f" | Khoản={khoan}"
            f" | ID={retrieved_uuid}"  # Hiển thị UUID rõ ràng để dễ đối chiếu
        )

    print()
    if found:
        print("🎯 STATUS: FOUND")
    else:
        print("⚠️ STATUS: NOT FOUND")

# In thống kê tổng hợp cuối cùng
print("\n" + "═" * 40 + " THỐNG KÊ ĐÁNH GIÁ " + "═" * 40)
print(f"🔹 Tổng số câu hỏi test: {total_queries}")
print(f"🎯 Độ chính xác Top 1 (Acc@1): {(hit_top1 / total_queries) * 100:.2f}%")
print(f"🔍 Tỷ lệ tìm thấy trong Top 5 (Recall@5): {(hit_top5 / total_queries) * 100:.2f}%")
print("═" * 99)