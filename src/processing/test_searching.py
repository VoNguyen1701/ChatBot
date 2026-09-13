# src/processing/test_searching.py

import json
from src.processing.searching import semantic_search


# ============================================================
# LOAD GOLDEN DATASET
# ============================================================

with open(
    "datasets/golden_dataset.json",
    "r",
    encoding="utf-8"
) as f:
    dataset = json.load(f)


# ============================================================
# HÀM CHUẨN HÓA KHOẢN
# ============================================================

def normalize_khoan(value):
    """
    Chuẩn hóa khoản.

    Golden Dataset:
        "khoan": [2]

    Search result:
        "khoan": 2

    Hoặc:
        "khoan": []
        "khoan": None
    """

    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


# ============================================================
# KIỂM TRA RESULT CÓ KHỚP GROUND TRUTH KHÔNG
# ============================================================

def is_relevant(doc, expected):
    """
    Kiểm tra một search result có khớp với
    một relevant chunk trong Golden Dataset hay không.

    Không phụ thuộc chunk_id vì semantic_search()
    hiện tại chưa trả chunk_id ra ngoài.
    """

    retrieved_doc_id = doc.get("doc_id")

    hierarchy = doc.get(
        "hierarchy",
        {}
    )

    retrieved_chapter = hierarchy.get(
        "chapter"
    )

    retrieved_dieu = hierarchy.get(
        "dieu"
    )

    retrieved_khoan = normalize_khoan(
        hierarchy.get("khoan")
    )


    # ========================================================
    # DOC ID
    # ========================================================

    expected_doc_id = expected.get(
        "doc_id"
    )

    if retrieved_doc_id != expected_doc_id:
        return False


    # ========================================================
    # CHƯƠNG
    # ========================================================

    expected_chapter = expected.get(
        "chapter"
    )

    if expected_chapter is not None:

        if retrieved_chapter != expected_chapter:
            return False


    # ========================================================
    # ĐIỀU
    # ========================================================

    expected_dieu = expected.get(
        "dieu"
    )

    if expected_dieu is not None:

        if retrieved_dieu != expected_dieu:
            return False


    # ========================================================
    # KHOẢN
    # ========================================================

    expected_khoan = normalize_khoan(
        expected.get("khoan")
    )

    if expected_khoan:

        if retrieved_khoan != expected_khoan:
            return False


    return True


# ============================================================
# TÍNH RECIPROCAL RANK
# ============================================================

def reciprocal_rank(results, relevant_chunks):
    """
    MRR:

        RR = 1 / rank

    của relevant result đầu tiên.

    Nếu không tìm thấy:
        RR = 0
    """

    for rank, (_, doc) in enumerate(
        results,
        start=1
    ):

        for expected in relevant_chunks:

            if is_relevant(
                doc,
                expected
            ):

                return 1.0 / rank

    return 0.0


# ============================================================
# KIỂM TRA RETRIEVAL TOP-K
# ============================================================

def evaluate_recall_at_k(
    results,
    relevant_chunks,
    k
):
    """
    Recall@K theo kiểu "coverage".

    Ví dụ Multi-hop q16 có:

        2 relevant chunks

    Retrieval Top 5 tìm được:

        1 / 2

    => Recall@5 = 0.5

    Nếu tìm được:

        2 / 2

    => Recall@5 = 1.0
    """

    if not relevant_chunks:

        return 0.0


    top_k_results = results[:k]

    matched = set()


    for _, doc in top_k_results:

        for index, expected in enumerate(
            relevant_chunks
        ):

            if index in matched:
                continue

            if is_relevant(
                doc,
                expected
            ):

                matched.add(index)

                break


    return (
        len(matched)
        /
        len(relevant_chunks)
    )


# ============================================================
# THỐNG KÊ
# ============================================================

total_queries = len(dataset)

hit_top1 = 0

recall_at_1_sum = 0.0
recall_at_5_sum = 0.0
recall_at_10_sum = 0.0
recall_at_20_sum = 0.0

mrr_sum = 0.0


# ============================================================
# THỐNG KÊ THEO QUESTION TYPE
# ============================================================

type_stats = {}


# ============================================================
# CHẠY TEST
# ============================================================

for item in dataset:

    query_id = item["query_id"]

    question = item["query"]

    question_type = item.get(
        "question_type",
        "Unknown"
    )

    difficulty = item.get(
        "difficulty",
        "Unknown"
    )

    relevant_chunks = item.get(
        "relevant_chunks",
        []
    )

    answerable = item.get(
        "answerable",
        True
    )


    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    results = semantic_search(
        question,
        top_k=20
    )


    # ========================================================
    # HEADER
    # ========================================================

    print(
        "\n"
        + "=" * 110
    )

    print(
        f"QUERY: {query_id}"
    )

    print(
        f"TYPE: {question_type}"
    )

    print(
        f"DIFFICULTY: {difficulty}"
    )

    print(
        f"QUESTION: {question}"
    )


    # ========================================================
    # GROUND TRUTH
    # ========================================================

    print(
        "\nGROUND TRUTH:"
    )


    if not relevant_chunks:

        print(
            "  Không có relevant chunks"
        )

    else:

        for index, expected in enumerate(
            relevant_chunks,
            start=1
        ):

            print(
                f"  [{index}] "
                f"Doc={expected.get('doc_id')} "
                f"| Chương={expected.get('chapter')} "
                f"| Điều={expected.get('dieu')} "
                f"| Khoản={expected.get('khoan')} "
                f"| Chunk={expected.get('chunk_id')}"
            )


    # ========================================================
    # RECALL @ K
    # ========================================================

    recall1 = evaluate_recall_at_k(
        results,
        relevant_chunks,
        1
    )

    recall5 = evaluate_recall_at_k(
        results,
        relevant_chunks,
        5
    )

    recall10 = evaluate_recall_at_k(
        results,
        relevant_chunks,
        10
    )

    recall20 = evaluate_recall_at_k(
        results,
        relevant_chunks,
        20
    )


    recall_at_1_sum += recall1
    recall_at_5_sum += recall5
    recall_at_10_sum += recall10
    recall_at_20_sum += recall20


    # ========================================================
    # TOP 1 HIT
    # ========================================================

    top1_found = (
        recall1 > 0
    )

    if top1_found:

        hit_top1 += 1


    # ========================================================
    # MRR
    # ========================================================

    rr = reciprocal_rank(
        results,
        relevant_chunks
    )

    mrr_sum += rr


    # ========================================================
    # HIỂN THỊ TOP 20
    # ========================================================

    print(
        "\nRETRIEVAL:"
    )


    for rank, (score, doc) in enumerate(
        results,
        start=1
    ):

        doc_id = doc.get(
            "doc_id"
        )

        hierarchy = doc.get(
            "hierarchy",
            {}
        )

        chapter = hierarchy.get(
            "chapter"
        )

        dieu = hierarchy.get(
            "dieu"
        )

        khoan = hierarchy.get(
            "khoan"
        )


        matched_indices = []


        for index, expected in enumerate(
            relevant_chunks
        ):

            if is_relevant(
                doc,
                expected
            ):

                matched_indices.append(
                    index + 1
                )


        if matched_indices:

            marker = "✅"

            matched_text = (
                f" MATCH={matched_indices}"
            )

        else:

            marker = "❌"

            matched_text = ""


        print(
            f"{marker} "
            f"Top {rank:02d}"
            f" | Score={score:.4f}"
            f" | Doc={doc_id}"
            f" | Chương={chapter}"
            f" | Điều={dieu}"
            f" | Khoản={khoan}"
            f"{matched_text}"
        )


    # ========================================================
    # HIỂN THỊ COVERAGE
    # ========================================================

    print(
        "\nCOVERAGE:"
    )

    print(
        f"  Recall@1  = {recall1:.2f}"
    )

    print(
        f"  Recall@5  = {recall5:.2f}"
    )

    print(
        f"  Recall@10 = {recall10:.2f}"
    )

    print(
        f"  Recall@20 = {recall20:.2f}"
    )

    print(
        f"  RR        = {rr:.2f}"
    )


    # ========================================================
    # STATUS
    # ========================================================

    if not relevant_chunks:

        print(
            "\n⚪ STATUS: NO GROUND TRUTH"
        )

    elif recall5 == 1.0:

        print(
            "\n🎯 STATUS: ALL RELEVANT CHUNKS FOUND IN TOP 5"
        )

    elif recall5 > 0:

        print(
            "\n🟡 STATUS: PARTIAL RETRIEVAL"
        )

    else:

        print(
            "\n🔴 STATUS: NOT FOUND"
        )


    # ========================================================
    # THỐNG KÊ THEO QUESTION TYPE
    # ========================================================

    if question_type not in type_stats:

        type_stats[question_type] = {

            "count": 0,

            "recall1": 0.0,

            "recall5": 0.0,

            "recall10": 0.0,

            "recall20": 0.0,

            "mrr": 0.0,

        }


    type_stats[question_type]["count"] += 1

    type_stats[question_type]["recall1"] += recall1

    type_stats[question_type]["recall5"] += recall5

    type_stats[question_type]["recall10"] += recall10

    type_stats[question_type]["recall20"] += recall20

    type_stats[question_type]["mrr"] += rr


# ============================================================
# THỐNG KÊ CUỐI
# ============================================================

print(
    "\n"
    + "═" * 35
    + " KẾT QUẢ TỔNG "
    + "═" * 35
)


print(
    f"🔹 Tổng số câu hỏi: "
    f"{total_queries}"
)


print(
    f"🎯 Hit@1: "
    f"{hit_top1}/{total_queries} "
    f"= {(hit_top1 / total_queries) * 100:.2f}%"
)


print(
    f"🔍 Recall@1: "
    f"{(recall_at_1_sum / total_queries) * 100:.2f}%"
)


print(
    f"🔍 Recall@5: "
    f"{(recall_at_5_sum / total_queries) * 100:.2f}%"
)


print(
    f"🔍 Recall@10: "
    f"{(recall_at_10_sum / total_queries) * 100:.2f}%"
)


print(
    f"🔍 Recall@20: "
    f"{(recall_at_20_sum / total_queries) * 100:.2f}%"
)


print(
    f"📊 MRR: "
    f"{mrr_sum / total_queries:.4f}"
)


# ============================================================
# THỐNG KÊ THEO QUESTION TYPE
# ============================================================

print(
    "\n"
    + "═" * 35
    + " THEO QUESTION TYPE "
    + "═" * 35
)


for question_type, stats in type_stats.items():

    count = stats["count"]

    print(
        f"\n[{question_type}] "
        f"n={count}"
    )

    print(
        f"  Recall@1  = "
        f"{(stats['recall1'] / count) * 100:.2f}%"
    )

    print(
        f"  Recall@5  = "
        f"{(stats['recall5'] / count) * 100:.2f}%"
    )

    print(
        f"  Recall@10 = "
        f"{(stats['recall10'] / count) * 100:.2f}%"
    )

    print(
        f"  Recall@20 = "
        f"{(stats['recall20'] / count) * 100:.2f}%"
    )

    print(
        f"  MRR       = "
        f"{stats['mrr'] / count:.4f}"
        )


# ============================================================
# MULTI-HOP RIÊNG
# ============================================================

multi_hop_items = [
    item
    for item in dataset
    if item.get("question_type") == "Multi-hop"
]


if multi_hop_items:

    print(
        "\n"
        + "═" * 35
        + " MULTI-HOP "
        + "═" * 35
    )


    for item in multi_hop_items:

        query_id = item["query_id"]

        relevant_count = len(
            item.get(
                "relevant_chunks",
                []
            )
        )

        print(
            f"{query_id}: "
            f"{relevant_count} relevant chunks"
        )


print(
    "\n"
    + "═" * 100
)