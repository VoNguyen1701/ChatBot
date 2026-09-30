"""
ĐÁNH GIÁ HYBRID vs HYBRID + RERANKER

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

from src.processing.hybrid_searching import hybrid_search
from src.processing.reranker import rerank


# ============================================================
# CONFIG
# ============================================================

DATASET_PATH = "datasets/golden_dataset.json"

OUTPUT_PATH = "data/eval/reranker_evaluation.json"

TOP_K = 10

HYBRID_ALPHA = 0.70


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

    chunk_id = doc.get(
        "chunk_id"
    )

    if chunk_id:

        return normalize_chunk_id(
            chunk_id
        )

    mongo_id = doc.get(
        "_id"
    )

    if mongo_id is None:
        return None

    try:

        from src.storage.mongo import get_db

        db = get_db()

        collection = db["chunks"]

        mongo_query_id = mongo_id

        if isinstance(
            mongo_id,
            str
        ):

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
# EXTRACT IDS
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
# METRICS
# ============================================================

def calculate_metrics(
    retrieved_ids,
    ground_truth_ids
):

    ground_truth_set = set(
        ground_truth_ids
    )

    # --------------------------------------------------------
    # Recall@1
    # --------------------------------------------------------

    recall_1 = 0

    if len(retrieved_ids) >= 1:

        if retrieved_ids[0] in ground_truth_set:

            recall_1 = 1

    # --------------------------------------------------------
    # Recall@5
    # --------------------------------------------------------

    recall_5 = 0

    if any(
        chunk_id in ground_truth_set
        for chunk_id in retrieved_ids[:5]
    ):

        recall_5 = 1

    # --------------------------------------------------------
    # Recall@10
    # --------------------------------------------------------

    recall_10 = 0

    if any(
        chunk_id in ground_truth_set
        for chunk_id in retrieved_ids[:10]
    ):

        recall_10 = 1

    # --------------------------------------------------------
    # MRR
    # --------------------------------------------------------

    reciprocal_rank = 0.0

    for rank, chunk_id in enumerate(
        retrieved_ids,
        start=1
    ):

        if chunk_id in ground_truth_set:

            reciprocal_rank = 1.0 / rank

            break

    return {
        "recall_at_1": recall_1,
        "recall_at_5": recall_5,
        "recall_at_10": recall_10,
        "reciprocal_rank": reciprocal_rank
    }


# ============================================================
# EVALUATE
# ============================================================

def evaluate(dataset):

    results = []

    print()
    print("=" * 70)
    print("EVALUATING HYBRID + RERANKER")
    print("=" * 70)

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

            continue

        if not ground_truth_ids:

            continue

        try:

            # ------------------------------------------------
            # Hybrid
            # ------------------------------------------------

            with contextlib.redirect_stdout(
                io.StringIO()
            ):

                hybrid_results = hybrid_search(
                    query,
                    top_k=TOP_K,
                    alpha=HYBRID_ALPHA,
                    verbose=False
                )

                # --------------------------------------------
                # Reranker
                # --------------------------------------------

                reranked_results = rerank(
                    query,
                    hybrid_results,
                    top_k=TOP_K
                )

            retrieved_ids = (
                extract_retrieved_ids(
                    reranked_results
                )
            )

            metrics = calculate_metrics(
                retrieved_ids,
                ground_truth_ids
            )

            if metrics["recall_at_10"] == 1:

                status = "MATCH"

            else:

                status = "MISS"

            result = {

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

            results.append(
                result
            )

            print(
                f"[{index:02d}/{len(dataset):02d}] "
                f"{query_id} | {status} | "
                f"R1={metrics['recall_at_1']} "
                f"R5={metrics['recall_at_5']} "
                f"R10={metrics['recall_at_10']} "
                f"RR={metrics['reciprocal_rank']:.4f}"
            )

        except Exception as e:

            print(
                f"[ERROR] {query_id}: {e}"
            )

    # ========================================================
    # SUMMARY
    # ========================================================

    evaluated = len(results)

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
                    for x in results
                ) / evaluated,

            "recall_at_5":
                sum(
                    x["metrics"]["recall_at_5"]
                    for x in results
                ) / evaluated,

            "recall_at_10":
                sum(
                    x["metrics"]["recall_at_10"]
                    for x in results
                ) / evaluated,

            "mrr":
                sum(
                    x["metrics"]["reciprocal_rank"]
                    for x in results
                ) / evaluated
        }

    return summary, results


# ============================================================
# MAIN
# ============================================================

def main():

    dataset = load_dataset()

    summary, results = evaluate(
        dataset
    )

    output = {

        "dataset":
            DATASET_PATH,

        "dataset_size":
            len(dataset),

        "evaluated_questions":
            summary["evaluated_questions"],

        "top_k":
            TOP_K,

        "hybrid_alpha":
            HYBRID_ALPHA,

        "reranker":
            "BAAI/bge-reranker-v2-m3",

        "summary":
            summary,

        "questions":
            results
    }

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output_dir = os.path.dirname(
        OUTPUT_PATH
    )

    if output_dir:

        os.makedirs(
            output_dir,
            exist_ok=True
        )

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
    # PRINT
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("HYBRID + RERANKER SUMMARY")
    print("=" * 70)

    print(
        f"Recall@1  : "
        f"{summary['recall_at_1'] * 100:.2f}%"
    )

    print(
        f"Recall@5  : "
        f"{summary['recall_at_5'] * 100:.2f}%"
    )

    print(
        f"Recall@10 : "
        f"{summary['recall_at_10'] * 100:.2f}%"
    )

    print(
        f"MRR       : "
        f"{summary['mrr']:.4f}"
    )

    print("=" * 70)

    print()
    print(
        f"[SAVED] {OUTPUT_PATH}"
    )


if __name__ == "__main__":

    main()