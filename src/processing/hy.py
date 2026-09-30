"""
ĐÁNH GIÁ THỐNG NHẤT BM25 vs BGE vs HYBRID

Xuất kết quả:
    data/eval/retrieval_evaluation.json

Metrics:
    Recall@1
    Recall@5
    Recall@10
    MRR
"""

import json
import os
import contextlib
import io
from typing import Any

from bson import ObjectId

from src.processing.bm25 import bm25_search
from src.processing.searching import semantic_search
from src.processing.hybrid_searching import hybrid_search


# ============================================================
# CONFIG
# ============================================================

DATASET_PATH = "datasets/golden_dataset.json"

OUTPUT_PATH = "data/eval/retrieval_evaluation.json"

TOP_K = 10
HYBRID_ALPHA = 0.7

METHODS = [
    "BM25",
    "BGE",
    "Hybrid",
]


# ============================================================
# LOAD DATASET
# ============================================================

def load_dataset():

    if not os.path.exists(DATASET_PATH):
        raise FileNotFoundError(
            f"Không tìm thấy dataset: {DATASET_PATH}"
        )

    with open(
        DATASET_PATH,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(
            "golden_dataset.json phải là JSON array."
        )

    print(
        f"[DATASET] Loaded {len(data)} questions"
    )

    return data


# ============================================================
# CHUẨN HÓA CHUNK ID
# ============================================================

def normalize_chunk_id(value: Any):

    if value is None:
        return None

    return str(value)


def get_chunk_id_from_doc(doc):

    if not doc:
        return None

    # --------------------------------------------------------
    # Ưu tiên chunk_id
    # --------------------------------------------------------

    chunk_id = doc.get("chunk_id")

    if chunk_id:

        return normalize_chunk_id(
            chunk_id
        )

    # --------------------------------------------------------
    # Nếu BGE chỉ có Mongo _id
    # thì truy vấn chunk_id từ Mongo
    # --------------------------------------------------------

    mongo_id = doc.get("_id")

    if mongo_id is None:
        return None

    try:

        from src.storage.mongo import get_db

        db = get_db()

        collection = db["chunks"]

        mongo_query_id = mongo_id

        if isinstance(mongo_id, str):

            try:

                mongo_query_id = ObjectId(
                    mongo_id
                )

            except Exception:

                mongo_query_id = mongo_id

        mongo_doc = collection.find_one(
            {
                "_id": mongo_query_id
            },
            {
                "_id": 1,
                "chunk_id": 1
            }
        )

        if mongo_doc:

            chunk_id = mongo_doc.get(
                "chunk_id"
            )

            if chunk_id:

                return normalize_chunk_id(
                    chunk_id
                )

    except Exception:

        pass

    return None


# ============================================================
# EXTRACT RETRIEVED IDS
# ============================================================

def extract_retrieved_ids(results):

    retrieved_ids = []

    for score, doc in results:

        chunk_id = get_chunk_id_from_doc(
            doc
        )

        if chunk_id is not None:

            retrieved_ids.append(
                chunk_id
            )

    return retrieved_ids


# ============================================================
# GROUND TRUTH
# ============================================================

def get_ground_truth_ids(item):

    relevant_chunks = item.get(
        "relevant_chunks",
        []
    )

    ground_truth_ids = []

    for chunk in relevant_chunks:

        chunk_id = chunk.get(
            "chunk_id"
        )

        if chunk_id:

            ground_truth_ids.append(
                normalize_chunk_id(
                    chunk_id
                )
            )

    return ground_truth_ids


# ============================================================
# LẤY METADATA CỦA CHUNK
# ============================================================

def get_doc_metadata(doc):

    if not doc:
        return {}

    hierarchy = doc.get(
        "hierarchy",
        {}
    )

    return {
        "doc_id": doc.get("doc_id"),
        "section_title": doc.get(
            "section_title"
        ),
        "chapter": hierarchy.get(
            "chapter"
        ),
        "dieu": hierarchy.get(
            "dieu"
        ),
        "khoan": hierarchy.get(
            "khoan"
        ),
        "diem": hierarchy.get(
            "diem"
        ),
    }


# ============================================================
# METRICS
# ============================================================

def calculate_question_metrics(
    retrieved_ids,
    ground_truth_ids
):

    ground_truth_set = set(
        ground_truth_ids
    )

    # Recall@1

    recall_1 = 0

    if len(retrieved_ids) >= 1:

        if (
            retrieved_ids[0]
            in ground_truth_set
        ):

            recall_1 = 1

    # Recall@5

    recall_5 = 0

    if any(
        chunk_id in ground_truth_set
        for chunk_id in retrieved_ids[:5]
    ):

        recall_5 = 1

    # Recall@10

    recall_10 = 0

    if any(
        chunk_id in ground_truth_set
        for chunk_id in retrieved_ids[:10]
    ):

        recall_10 = 1

    # MRR

    rr = 0.0

    for rank, chunk_id in enumerate(
        retrieved_ids,
        start=1
    ):

        if chunk_id in ground_truth_set:

            rr = 1.0 / rank

            break

    return {
        "recall_at_1": recall_1,
        "recall_at_5": recall_5,
        "recall_at_10": recall_10,
        "reciprocal_rank": rr
    }


# ============================================================
# EVALUATE METHOD
# ============================================================

def evaluate_method(
    dataset,
    method
):

    question_results = []

    print()
    print(
        f"[START] Evaluating {method}..."
    )

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
        ).strip()

        ground_truth_ids = (
            get_ground_truth_ids(item)
        )

        if not query:

            print(
                f"[{index:02d}/{len(dataset):02d}] "
                f"{query_id} | EMPTY"
            )

            continue

        if not ground_truth_ids:

            print(
                f"[{index:02d}/{len(dataset):02d}] "
                f"{query_id} | NO GROUND TRUTH"
            )

            continue

        # ----------------------------------------------------
        # RETRIEVAL
        # ----------------------------------------------------

        try:

            # Ẩn toàn bộ log chi tiết
            # của BM25 / BGE / Hybrid

            with contextlib.redirect_stdout(
                io.StringIO()
            ):

                if method == "BM25":

                    retrieved_results = (
                        bm25_search(
                            query,
                            top_k=TOP_K
                        )
                    )

                elif method == "BGE":

                    retrieved_results = (
                        semantic_search(
                            query,
                            top_k=TOP_K
                        )
                    )

                elif method == "Hybrid":

                    retrieved_results = (
                        hybrid_search(
                            query,
                            top_k=TOP_K,
                            alpha=HYBRID_ALPHA
                        )
                    )

                else:

                    raise ValueError(
                        f"Unknown method: {method}"
                    )

        except Exception as e:

            print(
                f"[ERROR] {query_id}: {e}"
            )

            question_results.append({

                "query_id": query_id,

                "query": query,

                "ground_truth_chunk_ids":
                    ground_truth_ids,

                "retrieved_chunk_ids": [],

                "metrics": {
                    "recall_at_1": 0,
                    "recall_at_5": 0,
                    "recall_at_10": 0,
                    "reciprocal_rank": 0.0
                },

                "status": "ERROR",

                "error": str(e)

            })

            continue

        # ----------------------------------------------------
        # CHUNK IDS
        # ----------------------------------------------------

        retrieved_ids = (
            extract_retrieved_ids(
                retrieved_results
            )
        )

        # ----------------------------------------------------
        # METRICS
        # ----------------------------------------------------

        metrics = calculate_question_metrics(
            retrieved_ids,
            ground_truth_ids
        )

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

        if metrics["recall_at_10"] == 1:

            status = "MATCH"

        else:

            status = "MISS"

        # ----------------------------------------------------
        # LƯU KẾT QUẢ
        # ----------------------------------------------------

        result_item = {

            "query_id": query_id,

            "query": query,

            "ground_truth_chunk_ids":
                ground_truth_ids,

            "retrieved_chunk_ids":
                retrieved_ids,

            "metrics":
                metrics,

            "status":
                status
        }

        question_results.append(
            result_item
        )

        print(
            f"[{index:02d}/{len(dataset):02d}] "
            f"{query_id} | {status} | "
            f"R1={metrics['recall_at_1']} "
            f"R5={metrics['recall_at_5']} "
            f"R10={metrics['recall_at_10']} "
            f"RR={metrics['reciprocal_rank']:.4f}"
        )

    # ========================================================
    # SUMMARY
    # ========================================================

    total = len(question_results)

    valid_results = [
        x
        for x in question_results
        if x["status"] != "ERROR"
    ]

    evaluated = len(valid_results)

    if evaluated == 0:

        summary = {

            "evaluated_questions": 0,

            "recall_at_1": 0.0,

            "recall_at_5": 0.0,

            "recall_at_10": 0.0,

            "mrr": 0.0
        }

    else:

        summary = {

            "evaluated_questions":
                evaluated,

            "recall_at_1":
                sum(
                    x["metrics"]["recall_at_1"]
                    for x in valid_results
                ) / evaluated,

            "recall_at_5":
                sum(
                    x["metrics"]["recall_at_5"]
                    for x in valid_results
                ) / evaluated,

            "recall_at_10":
                sum(
                    x["metrics"]["recall_at_10"]
                    for x in valid_results
                ) / evaluated,

            "mrr":
                sum(
                    x["metrics"]["reciprocal_rank"]
                    for x in valid_results
                ) / evaluated
        }

    return {

        "method": method,

        "alpha":
            HYBRID_ALPHA
            if method == "Hybrid"
            else None,

        "top_k":
            TOP_K,

        "summary":
            summary,

        "questions":
            question_results
    }


# ============================================================
# DEBUG Q018
# ============================================================

def debug_q018(dataset):

    target = None

    for item in dataset:

        if item.get(
            "query_id"
        ) == "q018":

            target = item

            break

    if target is None:

        return None

    query = target.get(
        "query",
        ""
    )

    ground_truth_ids = (
        get_ground_truth_ids(
            target
        )
    )

    with contextlib.redirect_stdout(
        io.StringIO()
    ):

        hybrid_results = hybrid_search(
            query,
            top_k=TOP_K,
            alpha=HYBRID_ALPHA
        )

    retrieved_ids = (
        extract_retrieved_ids(
            hybrid_results
        )
    )

    found = any(
        chunk_id in ground_truth_ids
        for chunk_id in retrieved_ids
    )

    rank = None

    for i, chunk_id in enumerate(
        retrieved_ids,
        start=1
    ):

        if chunk_id in ground_truth_ids:

            rank = i

            break

    return {

        "query_id": "q018",

        "query": query,

        "ground_truth_chunk_ids":
            ground_truth_ids,

        "hybrid_retrieved_chunk_ids":
            retrieved_ids,

        "ground_truth_found":
            found,

        "ground_truth_rank":
            rank
    }


# ============================================================
# FINAL
# ============================================================

def main():

    dataset = load_dataset()

    print()
    print(
        "[INFO] Debugging q018..."
    )

    debug_result = debug_q018(
        dataset
    )

    if debug_result:

        if debug_result[
            "ground_truth_found"
        ]:

            print(
                f"[DEBUG] q018 MATCH "
                f"at rank "
                f"{debug_result['ground_truth_rank']}"
            )

        else:

            print(
                "[DEBUG] q018 MISS"
            )

    # --------------------------------------------------------
    # EVALUATE ALL METHODS
    # --------------------------------------------------------

    evaluations = {}

    for method in METHODS:

        evaluations[method] = (
            evaluate_method(
                dataset,
                method
            )
        )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    final_summary = {}

    for method in METHODS:

        final_summary[method] = (
            evaluations[method]["summary"]
        )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    output = {

        "dataset": DATASET_PATH,

        "dataset_size":
            len(dataset),

        "top_k":
            TOP_K,

        "hybrid_alpha":
            HYBRID_ALPHA,

        "debug_q018":
            debug_result,

        "final_summary":
            final_summary,

        "evaluations":
            evaluations
    }

    # --------------------------------------------------------
    # CREATE DIRECTORY
    # --------------------------------------------------------

    output_dir = os.path.dirname(
        OUTPUT_PATH
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

    # --------------------------------------------------------
    # SAVE JSON
    # --------------------------------------------------------

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    # --------------------------------------------------------
    # PRINT SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    print(
        f"{'METHOD':<15}"
        f"{'R@1':>12}"
        f"{'R@5':>12}"
        f"{'R@10':>12}"
        f"{'MRR':>12}"
    )

    print("-" * 70)

    for method in METHODS:

        summary = final_summary[
            method
        ]

        print(
            f"{method:<15}"
            f"{summary['recall_at_1'] * 100:>11.2f}%"
            f"{summary['recall_at_5'] * 100:>11.2f}%"
            f"{summary['recall_at_10'] * 100:>11.2f}%"
            f"{summary['mrr']:>12.4f}"
        )

    print("=" * 70)

    print()
    print(
        f"[SAVED] {OUTPUT_PATH}"
    )


if __name__ == "__main__":

    main()