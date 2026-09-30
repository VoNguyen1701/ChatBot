
import re
import time

from src.storage.mongo import get_db
from rank_bm25 import BM25Okapi


# ============================================================
# MONGODB
# ============================================================

db = get_db()
chunk_col = db["chunks"]


# ============================================================
# TOKENIZER ĐƠN GIẢN CHO TIẾNG VIỆT
# ============================================================

def tokenize(text):
    """
    Tokenizer cơ bản cho tiếng Việt.

    Tạm thời:
    - Chuyển về chữ thường
    - Loại bỏ ký tự đặc biệt
    - Giữ chữ cái tiếng Việt
    - Giữ số
    - Tách token theo khoảng trắng
    """

    text = str(text).lower()

    text = re.sub(
        r"[^\w\sàáảãạăắằẳẵặâấầẩẫậ"
        r"èéẻẽẹêếềểễệ"
        r"ìíỉĩị"
        r"òóỏõọôốồổỗộơớờởỡợ"
        r"ùúủũụưứừửữự"
        r"ỳýỷỹỵ"
        r"đ]",
        " ",
        text,
        flags=re.UNICODE
    )

    tokens = text.split()

    return tokens


# ============================================================
# LOAD DỮ LIỆU TỪ MONGODB
# ============================================================

print("[BM25] Loading chunks from MongoDB...")

start_time = time.time()

docs = list(
    chunk_col.find(
        {},
        {
            # MongoDB internal ID
            "_id": 1,

            # QUAN TRỌNG:
            # chunk_id được dùng làm ID chung
            # giữa BM25, BGE, Hybrid và Golden Dataset
            "chunk_id": 1,

            "content": 1,
            "doc_id": 1,
            "section_title": 1,
            "hierarchy": 1,
            "parent_doc_id": 1
        }
    )
)

print(f"[BM25] Loaded {len(docs)} chunks")


if not docs:
    raise RuntimeError(
        "[BM25] Không tìm thấy chunk nào trong MongoDB."
    )


# ============================================================
# KIỂM TRA chunk_id
# ============================================================

missing_chunk_id = 0

for doc in docs:

    if not doc.get("chunk_id"):
        missing_chunk_id += 1


print(
    f"[BM25] Documents missing chunk_id: "
    f"{missing_chunk_id}"
)


if missing_chunk_id > 0:

    print(
        "[BM25][WARNING] Một số document không có chunk_id."
    )

    print(
        "[BM25][WARNING] Các document này sẽ không thể "
        "merge chính xác với BGE."
    )


# ============================================================
# TOKENIZE TOÀN BỘ CORPUS
# ============================================================

print("[BM25] Tokenizing corpus...")

corpus_tokens = []

for doc in docs:

    content = doc.get(
        "content",
        ""
    )

    tokens = tokenize(content)

    corpus_tokens.append(tokens)


# ============================================================
# BUILD BM25 INDEX
# ============================================================

print("[BM25] Building BM25 index...")

bm25 = BM25Okapi(
    corpus_tokens
)

build_time = time.time() - start_time

print(
    f"[BM25] Index ready: "
    f"{len(docs)} documents"
)

print(
    f"[BM25] Build time: "
    f"{build_time:.3f}s"
)


# ============================================================
# BM25 SEARCH
# ============================================================

def bm25_search(
    query,
    top_k=10
):
    """
    Tìm kiếm BM25 trên toàn bộ chunks.

    Trả về:

        [
            (score, doc),
            ...
        ]

    Trong đó doc luôn chứa chunk_id nếu MongoDB
    có trường chunk_id.
    """

    if not query or not query.strip():

        return []

    query = query.strip()

    query_tokens = tokenize(
        query
    )

    if not query_tokens:

        return []

    # --------------------------------------------------------
    # Tính BM25 score
    # --------------------------------------------------------

    scores = bm25.get_scores(
        query_tokens
    )

    # --------------------------------------------------------
    # Sắp xếp index theo score giảm dần
    # --------------------------------------------------------

    ranked_indices = sorted(
        range(len(scores)),
        key=lambda i: scores[i],
        reverse=True
    )

    results = []

    # --------------------------------------------------------
    # Lấy Top-K
    # --------------------------------------------------------

    for idx in ranked_indices:

        score = float(
            scores[idx]
        )

        # BM25 score <= 0:
        # không có từ khóa phù hợp
        if score <= 0:

            continue

        doc = docs[idx]

        # ----------------------------------------------------
        # Kiểm tra chunk_id
        # ----------------------------------------------------

        if not doc.get("chunk_id"):

            print(
                "[BM25][WARNING] "
                "Document không có chunk_id, "
                "bỏ qua kết quả."
            )

            continue

        results.append(
            (
                score,
                doc
            )
        )

        if len(results) >= top_k:

            break

    return results


# ============================================================
# TEST TRỰC TIẾP
# ============================================================

if __name__ == "__main__":

    query = input(
        "\nNhập câu hỏi: "
    ).strip()

    results = bm25_search(
        query,
        top_k=10
    )

    print("\n" + "=" * 80)
    print("BM25 SEARCH RESULTS")
    print("=" * 80)

    if not results:

        print(
            "Không tìm thấy kết quả."
        )

    else:

        for i, (score, doc) in enumerate(
            results,
            1
        ):

            # ------------------------------------------------
            # Metadata
            # ------------------------------------------------

            chunk_id = doc.get(
                "chunk_id",
                "N/A"
            )

            doc_id = doc.get(
                "doc_id",
                "N/A"
            )

            section_title = doc.get(
                "section_title",
                "N/A"
            )

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
                "N/A"
            )

            khoan = hierarchy.get(
                "khoan",
                "N/A"
            )

            content = str(
                doc.get(
                    "content",
                    ""
                )
            )

            preview = content[:300].replace(
                "\n",
                " "
            )

            # ------------------------------------------------
            # Print
            # ------------------------------------------------

            print(
                f"\nTop {i:02d}"
                f" | Score={score:.4f}"
            )

            print(
                f"Chunk ID={chunk_id}"
            )

            print(
                f"Doc={doc_id}"
                f" | Điều={dieu}"
                f" | Khoản={khoan}"
            )

            print(
                f"Section={section_title}"
            )

            print(
                f"Content={preview}..."
            )