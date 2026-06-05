# src/processing/test_searching.py
"""
1. 0.7266 | Điều 2 - Khoản 2
2. 0.6045 | Điều 2 - Khoản 1
3. 0.6018 | Điều 6 - Khoản 1
4. 0.5899 | Điều 28 - Khoản 2
5. 0.5875 | Điều 2 - Khoản 1

====================================================================================================
QUERY: q001
QUESTION: Cá nhân cư trú theo Luật Thuế TNCN năm 2025 phải đáp ứng điều kiện có mặt tại Việt Nam bao nhiêu ngày trở lên tính trong một năm dương lịch hoặc trong 12 tháng liên tục kể từ ngày đầu tiên có mặt?
GROUND TRUTH: ['eb964c9d-628b-47d2-84f0-ffef68162f8f']

❌ Top 1 | Score=0.7266 | Điều=None | Khoản=None | ID=6a2002c1102e44da22bdf9c5
❌ Top 2 | Score=0.6045 | Điều=None | Khoản=None | ID=6a2002cb102e44da22bdfc7e
❌ Top 3 | Score=0.6018 | Điều=None | Khoản=None | ID=6a2002c1102e44da22bdf9f3
❌ Top 4 | Score=0.5899 | Điều=None | Khoản=None | ID=6a2002c1102e44da22bdfa4b
❌ Top 5 | Score=0.5875 | Điều=None | Khoản=None | ID=6a2002c1102e44da22bdf9c4

⚠️ NOT FOUND
 {
    "query_id": "q001",
    "query": "Cá nhân cư trú theo Luật Thuế TNCN năm 2025 phải đáp ứng điều kiện có mặt tại Việt Nam bao nhiêu ngày trở lên tính trong một năm dương lịch hoặc trong 12 tháng liên tục kể từ ngày đầu tiên có mặt?",
    "relevant_ids": [
      "eb964c9d-628b-47d2-84f0-ffef68162f8f"
    ],
    "metadata": [
      {
        "doc_id": "109_2025_QH15",
        "dieu": 2,
        "khoan": [
          2
        ]
      }
    ]
  },
"""
import json

from src.processing.searching import semantic_search


with open(
    "datasets/golden_dataset.json",
    "r",
    encoding="utf-8"
) as f:
    dataset = json.load(f)

for item in dataset:

    query_id = item["query_id"]
    question = item["query"]
    relevant_ids = item["relevant_ids"]

    results = semantic_search(
        question,
        top_k=5
    )

    print("\n" + "=" * 100)
    print("QUERY:", query_id)
    print("QUESTION:", question)
    print("GROUND TRUTH:", relevant_ids)
    print()

    found = False

    for rank, (score, doc) in enumerate(results, start=1):

        doc_id = str(doc["_id"])

        if doc_id in relevant_ids:
            found = True
            marker = "✅"
        else:
            marker = "❌"

        print(
            f"{marker} "
            f"Top {rank}"
            f" | Score={score:.4f}"
            f" | Điều={doc.get('dieu')}"
            f" | Khoản={doc.get('khoan')}"
            f" | ID={doc_id}"
        )

    print()

    if found:
        print("🎯 FOUND")
    else:
        print("⚠️ NOT FOUND")