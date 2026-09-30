import time, json

from src.processing.bm25 import bm25_search
from src.processing.searching import semantic_search
from src.storage.mongo import get_db


# =========================================================
# CONFIG
# =========================================================

ALPHA = 0.7

RETRIEVAL_TOP_K = 10
HYBRID_TOP_K = 10


# =========================================================
# MONGODB
# =========================================================

db = get_db()
chunk_col = db["chunks"]


# =========================================================
# MIN-MAX NORMALIZATION
# =========================================================

def min_max_normalize(score_dict):
    """
    Chuẩn hóa score về khoảng [0, 1].

    score_dict:
        {
            chunk_id: score
        }
    """

    if not score_dict:
        return {}

    scores = list(score_dict.values())

    min_score = min(scores)
    max_score = max(scores)

    # Tất cả score giống nhau
    if max_score == min_score:
        return {
            chunk_id: 1.0
            for chunk_id in score_dict
        }

    normalized = {}

    for chunk_id, score in score_dict.items():

        normalized[chunk_id] = (
            (score - min_score)
            / (max_score - min_score)
        )

    return normalized


# =========================================================
# GET CHUNK ID FROM BGE DOCUMENT
# =========================================================

def get_chunk_id_from_bge_doc(doc):
    """
    BGE semantic_search() hiện tại trả về MongoDB document
    nhưng projection trong searching.py chưa lấy chunk_id.

    Vì vậy:
        1. Nếu doc đã có chunk_id -> dùng luôn.
        2. Nếu chưa có -> lấy MongoDB _id.
        3. Tra lại MongoDB để lấy chunk_id.
    """

    # -----------------------------------------------------
    # Trường hợp document đã có chunk_id
    # -----------------------------------------------------

    chunk_id = doc.get("chunk_id")

    if chunk_id:
        return str(chunk_id)

    # -----------------------------------------------------
    # Lấy MongoDB _id
    # -----------------------------------------------------

    mongo_id = doc.get("_id")

    if mongo_id is None:
        return None

    # -----------------------------------------------------
    # Tra lại MongoDB
    # -----------------------------------------------------

    mongo_doc = chunk_col.find_one(
        {
            "_id": mongo_id
        },
        {
            "_id": 1,
            "chunk_id": 1
        }
    )

    if not mongo_doc:
        return None

    chunk_id = mongo_doc.get("chunk_id")

    if not chunk_id:
        return None

    return str(chunk_id)


# =========================================================
# HYBRID SEARCH
# =========================================================

def hybrid_search(
    query,
    top_k=HYBRID_TOP_K,
    alpha=None,
    verbose=True
):

    if alpha is None:
        alpha = ALPHA
    total_start = time.time()

    # =====================================================
    # 1. BM25
    # =====================================================

    start = time.time()

    bm25_results = bm25_search(
        query,
        top_k=RETRIEVAL_TOP_K
    )

    bm25_time = time.time() - start

    # =====================================================
    # 2. BGE
    # =====================================================

    start = time.time()

    bge_results = semantic_search(
        query,
        top_k=RETRIEVAL_TOP_K
    )

    bge_time = time.time() - start

    # =====================================================
    # 3. DICT SCORE
    # =====================================================

    bm25_scores = {}
    bge_scores = {}

    bm25_docs = {}
    bge_docs = {}

    bm25_ranks = {}
    bge_ranks = {}

    # =====================================================
    # 3A. BM25 RESULTS
    # =====================================================

    for rank, (
        score,
        doc
    ) in enumerate(
        bm25_results,
        start=1
    ):

        chunk_id = doc.get("chunk_id")

        if not chunk_id:

            if verbose:
                print(
                    "[HYBRID][WARNING] "
                    "BM25 result không có chunk_id."
                )

            continue

        chunk_id = str(chunk_id)

        bm25_scores[chunk_id] = float(score)
        bm25_docs[chunk_id] = doc
        bm25_ranks[chunk_id] = rank

    # =====================================================
    # 3B. BGE RESULTS
    # =====================================================

    for rank, (
        score,
        doc
    ) in enumerate(
        bge_results,
        start=1
    ):

        chunk_id = get_chunk_id_from_bge_doc(doc)

        if not chunk_id:

            if verbose:
                print(
                    "[HYBRID][WARNING] "
                    "Không lấy được chunk_id từ BGE result."
                )

            continue

        chunk_id = str(chunk_id)
        doc["chunk_id"] = chunk_id

        bge_scores[chunk_id] = float(score)
        bge_docs[chunk_id] = doc
        bge_ranks[chunk_id] = rank

    # =====================================================
    # 4. MERGE CHUNK IDS
    # =====================================================

    all_chunk_ids = set()

    all_chunk_ids.update(
        bm25_scores.keys()
    )

    all_chunk_ids.update(
        bge_scores.keys()
    )

    # =====================================================
    # 5. NORMALIZE SCORE
    # =====================================================

    bm25_norm = min_max_normalize(
        bm25_scores
    )

    bge_norm = min_max_normalize(
        bge_scores
    )

    # =====================================================
    # 6. CALCULATE HYBRID SCORE
    # =====================================================

    hybrid_results = []

    for chunk_id in all_chunk_ids:

        bm25_raw = bm25_scores.get(
            chunk_id,
            0.0
        )

        bge_raw = bge_scores.get(
            chunk_id,
            0.0
        )

        bm25_normalized = bm25_norm.get(
            chunk_id,
            0.0
        )

        bge_normalized = bge_norm.get(
            chunk_id,
            0.0
        )

        hybrid_score = (
            alpha * bge_normalized
            +
            (1.0 - alpha) * bm25_normalized
        )

        # -------------------------------------------------
        # Ưu tiên document từ BGE nếu có,
        # nếu không thì lấy từ BM25
        # -------------------------------------------------

        doc = bge_docs.get(
            chunk_id
        )

        if doc is None:

            doc = bm25_docs.get(
                chunk_id
            )

        if doc is None:
            continue

        hybrid_results.append(
            {
                "hybrid_score": float(
                    hybrid_score
                ),

                "chunk_id": chunk_id,

                "doc": doc,

                "bm25_score": float(
                    bm25_raw
                ),

                "bm25_norm": float(
                    bm25_normalized
                ),

                "bm25_rank": bm25_ranks.get(
                    chunk_id
                ),

                "bge_score": float(
                    bge_raw
                ),

                "bge_norm": float(
                    bge_normalized
                ),

                "bge_rank": bge_ranks.get(
                    chunk_id
                )
            }
        )

    # =====================================================
    # 7. SORT
    # =====================================================

    hybrid_results.sort(
        key=lambda x: x["hybrid_score"],
        reverse=True
    )

    hybrid_results = hybrid_results[:top_k]

    # =====================================================
    # 8. DEBUG
    # =====================================================

    if verbose:

        print("\n" + "=" * 70)
        print("HYBRID SEARCH")
        print("=" * 70)

        print(
            f"Query : {query}"
        )

        print(
            f"Alpha : {alpha}"
        )

        print(
            f"BM25  : "
            f"{len(bm25_results)} results | "
            f"{bm25_time:.3f}s"
        )

        print(
            f"BGE   : "
            f"{len(bge_results)} results | "
            f"{bge_time:.3f}s"
        )

        print(
            f"Merged unique candidates: "
            f"{len(all_chunk_ids)}"
        )

        print("\n" + "-" * 80)
        print("HYBRID TOP RESULTS")
        print("-" * 80)

        for rank, item in enumerate(
            hybrid_results,
            start=1
        ):

            doc = item["doc"]

            hierarchy = doc.get(
                "hierarchy",
                {}
            )

            if not isinstance(
                hierarchy,
                dict
            ):
                hierarchy = {}

            dieu = hierarchy.get(
                "dieu",
                ""
            )

            khoan = hierarchy.get(
                "khoan",
                ""
            )

            print(
                f"\nTop {rank:02d} | "
                f"Hybrid={item['hybrid_score']:.4f}"
            )

            print(
                f"Chunk ID="
                f"{item['chunk_id']}"
            )

            print(
                f"Doc={doc.get('doc_id', 'N/A')} | "
                f"Điều={dieu} | "
                f"Khoản={khoan}"
            )

            print(
                f"BM25 score="
                f"{item['bm25_score']:.4f} | "
                f"BM25 norm="
                f"{item['bm25_norm']:.4f} | "
                f"BM25 rank="
                f"{item['bm25_rank']}"
            )

            print(
                f"BGE score="
                f"{item['bge_score']:.4f} | "
                f"BGE norm="
                f"{item['bge_norm']:.4f} | "
                f"BGE rank="
                f"{item['bge_rank']}"
            )

        total_time = (
            time.time()
            - total_start
        )

        print(
            "\n" + "-" * 80
        )

        print(
            f"Total time: "
            f"{total_time:.3f}s"
        )

    return [
        (
            item["hybrid_score"],
            item["doc"]
        )
        for item in hybrid_results
    ]


# =========================================================
# GOLDEN DATASET
# =========================================================

def load_golden_dataset():

    path = "datasets/golden_dataset.json"

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        return json.load(f)


def get_relevant_chunk_ids(item):

    relevant_ids = []

    for chunk in item.get(
        "relevant_chunks",
        []
    ):

        chunk_id = chunk.get(
            "chunk_id"
        )

        if chunk_id:
            relevant_ids.append(
                str(chunk_id)
            )

    return relevant_ids


# =========================================================
# EVALUATION
# =========================================================

def evaluate_golden_dataset():

    dataset = load_golden_dataset()

    total = len(dataset)

    recall_1 = 0
    recall_5 = 0
    recall_10 = 0

    reciprocal_ranks = []

    print("\n" + "=" * 90)
    print("HYBRID RETRIEVAL EVALUATION")
    print("=" * 90)

    for index, item in enumerate(
        dataset,
        start=1
    ):

        query_id = item.get(
            "query_id",
            f"q{index:03d}"
        )

        query = item.get(
            "query",
            ""
        )

        relevant_ids = set(
            get_relevant_chunk_ids(
                item
            )
        )

        results = hybrid_search(
            query,
            top_k=10,
            verbose=False
        )

        # -------------------------------------------------
        # Giữ thứ tự ranking
        # -------------------------------------------------

        retrieved_ids = []

        for (
            score,
            doc
        ) in results:

            chunk_id = get_chunk_id_from_bge_doc(
                doc
            )

            if chunk_id:

                retrieved_ids.append(
                    str(chunk_id)
                )

            else:

                # Nếu document đến từ BM25
                chunk_id = doc.get(
                    "chunk_id"
                )

                if chunk_id:

                    retrieved_ids.append(
                        str(chunk_id)
                    )

        # -------------------------------------------------
        # Recall@1
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:1]
        ):

            recall_1 += 1

        # -------------------------------------------------
        # Recall@5
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:5]
        ):

            recall_5 += 1

        # -------------------------------------------------
        # Recall@10
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:10]
        ):

            recall_10 += 1

        # -------------------------------------------------
        # MRR
        # -------------------------------------------------

        rr = 0.0

        for rank, cid in enumerate(
            retrieved_ids,
            start=1
        ):

            if cid in relevant_ids:

                rr = 1.0 / rank

                break

        reciprocal_ranks.append(
            rr
        )

        status = (
            "MATCH"
            if rr > 0
            else "MISS"
        )

        print(
            f"[{index:03d}/{total:03d}] "
            f"{query_id} | "
            f"{status} | "
            f"RR={rr:.4f}"
        )

    # =====================================================
    # FINAL METRICS
    # =====================================================

    recall_1_value = (
        recall_1 / total
        if total
        else 0
    )

    recall_5_value = (
        recall_5 / total
        if total
        else 0
    )

    recall_10_value = (
        recall_10 / total
        if total
        else 0
    )

    mrr_value = (
        sum(reciprocal_ranks) / total
        if total
        else 0
    )

    print("\n" + "=" * 90)
    print("FINAL EVALUATION")
    print("=" * 90)

    print(
        f"Evaluated questions : {total}"
    )

    print(
        f"Recall@1            : "
        f"{recall_1_value:.4f} "
        f"({recall_1_value * 100:.2f}%)"
    )

    print(
        f"Recall@5            : "
        f"{recall_5_value:.4f} "
        f"({recall_5_value * 100:.2f}%)"
    )

    print(
        f"Recall@10           : "
        f"{recall_10_value:.4f} "
        f"({recall_10_value * 100:.2f}%)"
    )

    print(
        f"MRR                 : "
        f"{mrr_value:.4f}"
    )

# =========================================================
# ALPHA EXPERIMENT
# =========================================================

def evaluate_alpha(alpha):

    dataset = load_golden_dataset()

    total = len(dataset)

    recall_1 = 0
    recall_5 = 0
    recall_10 = 0

    reciprocal_ranks = []

    for index, item in enumerate(
        dataset,
        start=1
    ):

        query = item.get(
            "query",
            ""
        )

        relevant_ids = set(
            get_relevant_chunk_ids(
                item
            )
        )

        results = hybrid_search(
            query,
            top_k=10,
            alpha=alpha,
            verbose=False
        )

        # -------------------------------------------------
        # Lấy thứ tự ranking
        # -------------------------------------------------

        retrieved_ids = []

        for score, doc in results:

            chunk_id = doc.get(
                "chunk_id"
            )

            if not chunk_id:

                chunk_id = get_chunk_id_from_bge_doc(
                    doc
                )

            if chunk_id:

                retrieved_ids.append(
                    str(chunk_id)
                )

        # -------------------------------------------------
        # Recall@1
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:1]
        ):

            recall_1 += 1

        # -------------------------------------------------
        # Recall@5
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:5]
        ):

            recall_5 += 1

        # -------------------------------------------------
        # Recall@10
        # -------------------------------------------------

        if any(
            cid in relevant_ids
            for cid in retrieved_ids[:10]
        ):

            recall_10 += 1

        # -------------------------------------------------
        # MRR
        # -------------------------------------------------

        rr = 0.0

        for rank, cid in enumerate(
            retrieved_ids,
            start=1
        ):

            if cid in relevant_ids:

                rr = 1.0 / rank

                break

        reciprocal_ranks.append(rr)

    # -----------------------------------------------------
    # Final metrics
    # -----------------------------------------------------

    if total == 0:

        return {
            "alpha": alpha,
            "recall_1": 0.0,
            "recall_5": 0.0,
            "recall_10": 0.0,
            "mrr": 0.0
        }

    return {
        "alpha": alpha,

        "recall_1": recall_1 / total,

        "recall_5": recall_5 / total,

        "recall_10": recall_10 / total,

        "mrr": sum(
            reciprocal_ranks
        ) / total
    }


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":

    alpha_values = [
        0.66,
        0.67,
        0.68,
        0.69,
        0.70,
        0.71,
        0.72,
        0.73,
        0.74,
        0.75
    ]

    print("\n" + "=" * 100)
    print("HYBRID RETRIEVAL - ALPHA EXPERIMENT")
    print("=" * 100)

    print(
        "\nCác giá trị Alpha được thử:"
    )

    print(
        alpha_values
    )

    print(
        "\nĐang đánh giá trên golden_dataset.json..."
    )

    all_results = []

    for alpha in alpha_values:

        print("\n" + "-" * 100)

        print(
            f"Testing Alpha = {alpha}"
        )

        start_time = time.time()

        result = evaluate_alpha(
            alpha
        )

        elapsed = (
            time.time()
            - start_time
        )

        all_results.append(
            result
        )

        print(
            f"Alpha      : {result['alpha']:.2f}"
        )

        print(
            f"Recall@1   : "
            f"{result['recall_1']:.4f} "
            f"({result['recall_1'] * 100:.2f}%)"
        )

        print(
            f"Recall@5   : "
            f"{result['recall_5']:.4f} "
            f"({result['recall_5'] * 100:.2f}%)"
        )

        print(
            f"Recall@10  : "
            f"{result['recall_10']:.4f} "
            f"({result['recall_10'] * 100:.2f}%)"
        )

        print(
            f"MRR        : "
            f"{result['mrr']:.4f}"
        )

        print(
            f"Time       : "
            f"{elapsed:.2f}s"
        )

    # =====================================================
    # COMPARISON TABLE
    # =====================================================

    print("\n\n" + "=" * 100)
    print("ALPHA COMPARISON")
    print("=" * 100)

    print(
        f"{'Alpha':<10}"
        f"{'Recall@1':<15}"
        f"{'Recall@5':<15}"
        f"{'Recall@10':<15}"
        f"{'MRR':<15}"
    )

    print("-" * 70)

    for result in all_results:

        print(
            f"{result['alpha']:<10.2f}"
            f"{result['recall_1']:<15.4f}"
            f"{result['recall_5']:<15.4f}"
            f"{result['recall_10']:<15.4f}"
            f"{result['mrr']:<15.4f}"
        )

    print("=" * 100)