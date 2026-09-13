# datas/build.py
" Tạo golden dataset cho eval"
import json
from pathlib import Path

import pandas as pd
from pymongo import MongoClient


# ==========================================
# MongoDB
# ==========================================

client = MongoClient(
    "mongodb://dungnguyet17012005_db_user:Dungnguyet17012005~@ac-hzf04zl-shard-00-00.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-01.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-02.bzpmnh4.mongodb.net:27017/?ssl=true&replicaSet=atlas-qutlkr-shard-0&authSource=admin&appName=Cluster0"
)

db = client["legal_rag_db"]
chunks_col = db["chunks"]


# ============================================================
# 2. PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[1]

excel_path = BASE_DIR / "data" / "eval" / "ques.xlsx"

output_dir = BASE_DIR / "datasets"
output_dir.mkdir(exist_ok=True)

output_file = output_dir / "golden_dataset.json"


# ============================================================
# 3. HÀM CHUYỂN GIÁ TRỊ EXCEL
# ============================================================

def clean_string(value):
    """
    Chuyển giá trị Excel thành string sạch.
    """
    if pd.isna(value):
        return None

    value = str(value).strip()

    if value == "":
        return None

    return value


def parse_int(value):
    """
    Chuyển Excel 29 / 29.0 -> 29.
    """
    if pd.isna(value):
        return None

    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def parse_int_list(value):
    """
    Chuyển:

        1       -> [1]
        1;2     -> [1, 2]
        1; 2; 3 -> [1, 2, 3]

    Nếu rỗng -> [].
    """

    if pd.isna(value):
        return []

    raw = str(value).strip()

    if not raw:
        return []

    result = []

    for item in raw.split(";"):
        item = item.strip()

        if not item:
            continue

        try:
            result.append(int(float(item)))
        except (ValueError, TypeError):
            print(
                f"[WARN] Không thể chuyển thành số: {item}"
            )

    return result


def parse_bool(value):
    """
    Chuyển TRUE/FALSE trong Excel thành bool Python.
    """

    if pd.isna(value):
        return True

    value = str(value).strip().lower()

    if value in ["false", "0", "no", "n"]:
        return False

    return True


# ============================================================
# 4. LOAD EXCEL
# ============================================================

print("=" * 70)
print("LOAD GOLDEN DATASET")
print("=" * 70)

print(f"Excel: {excel_path}")

df = pd.read_excel(excel_path)


# ============================================================
# 5. KIỂM TRA CỘT
# ============================================================

required_columns = [
    "id",
    "question",
    "question_type",
    "difficulty",
    "doc_id",
    "chapter",
    "dieu",
    "khoan",
    "diem",
    "answerable",
    "notes",
]

missing_columns = [
    col
    for col in required_columns
    if col not in df.columns
]

if missing_columns:
    raise ValueError(
        "Excel đang thiếu các cột: "
        + ", ".join(missing_columns)
    )


# ============================================================
# 6.FORWARD FILL
# ============================================================

for column in [
    "id",
    "question",
    "question_type",
    "difficulty",
    "answerable",
    "notes",
]:
    df[column] = df[column].ffill()


# ============================================================
# 7. LOẠI DÒNG TRỐNG
# ============================================================

df = df[df["id"].notna()].copy()

df = df.reset_index(drop=True)


# ============================================================
# 8. BUILD DATASET
# ============================================================

golden_dataset = []

grouped = df.groupby("id", sort=True)


for qid, group in grouped:

    query_id = f"q{int(float(qid)):03d}"

    first_row = group.iloc[0]

    question = clean_string(
        first_row["question"]
    )

    question_type = clean_string(
        first_row["question_type"]
    )

    difficulty = clean_string(
        first_row["difficulty"]
    )

    answerable = parse_bool(
        first_row["answerable"]
    )

    notes = clean_string(
        first_row["notes"]
    )


    # ========================================================
    # DANH SÁCH CHUNK ĐÚNG
    # ========================================================

    relevant_chunks = []

    seen_chunk_ids = set()


    # ========================================================
    # DUYỆT TỪNG DÒNG CỦA CÂU HỎI
    # ========================================================

    for _, row in group.iterrows():

        # ----------------------------------------------------
        # DOC ID
        # ----------------------------------------------------

        raw_doc_id = clean_string(
            row["doc_id"]
        )

        if raw_doc_id is None:
            print(
                f"[WARN] {query_id}: "
                f"không có doc_id"
            )
            continue

        doc_id = (
            raw_doc_id
            .replace("/", "_")
        )


        # ----------------------------------------------------
        # CHAPTER / DIEU
        # ----------------------------------------------------

        chapter = parse_int(
            row["chapter"]
        )

        dieu = parse_int(
            row["dieu"]
        )


        # ----------------------------------------------------
        # KHOAN
        # ----------------------------------------------------

        khoan_list = parse_int_list(
            row["khoan"]
        )


        # ----------------------------------------------------
        # DIEM
        # ----------------------------------------------------

        diem_list = parse_int_list(
            row["diem"]
        )


        # ====================================================
        # TẠO QUERY MONGODB
        # ====================================================

        mongo_query = {
            "doc_id": doc_id
        }


        # Chỉ thêm field nếu Excel thực sự chỉ định.
        #
        # KHÔNG làm:
        #
        # hierarchy.dieu = None
        #
        # vì DB có thể không lưu field đó.

        if chapter is not None:
            mongo_query[
                "hierarchy.chapter"
            ] = chapter

        if dieu is not None:
            mongo_query[
                "hierarchy.dieu"
            ] = dieu


        # ====================================================
        # TRƯỜNG HỢP CÓ KHOẢN
        # ====================================================

        if khoan_list:

            for khoan in khoan_list:

                query = dict(mongo_query)

                query[
                    "hierarchy.khoan"
                ] = khoan


                chunk = chunks_col.find_one(
                    query,
                    {
                        "_id": 1,
                        "chunk_id": 1,
                        "doc_id": 1,
                        "content": 1,
                        "hierarchy": 1,
                        "section_title": 1,
                    }
                )


                if chunk is None:

                    print(
                        f"[WARN] Không tìm thấy chunk: "
                        f"{doc_id} | "
                        f"Chapter={chapter} | "
                        f"Điều={dieu} | "
                        f"Khoản={khoan}"
                    )

                    continue


                chunk_id = chunk.get(
                    "chunk_id"
                )


                if not chunk_id:

                    print(
                        f"[WARN] Chunk không có chunk_id: "
                        f"{doc_id} | "
                        f"Điều={dieu} | "
                        f"Khoản={khoan}"
                    )

                    continue


                if chunk_id in seen_chunk_ids:
                    continue


                seen_chunk_ids.add(
                    chunk_id
                )


                relevant_chunks.append({

                    "chunk_id": chunk_id,

                    "doc_id": doc_id,

                    "chapter": chapter,

                    "dieu": dieu,

                    "khoan": [khoan],

                    "diem": diem_list,

                })


        # ====================================================
        # TRƯỜNG HỢP KHÔNG CÓ KHOẢN
        # ====================================================

        else:

            chunk = chunks_col.find_one(
                mongo_query,
                {
                    "_id": 1,
                    "chunk_id": 1,
                    "doc_id": 1,
                    "content": 1,
                    "hierarchy": 1,
                    "section_title": 1,
                }
            )


            if chunk is None:

                print(
                    f"[WARN] Không tìm thấy chunk: "
                    f"{doc_id} | "
                    f"Chapter={chapter} | "
                    f"Điều={dieu} | "
                    f"Không có Khoản"
                )

                continue


            chunk_id = chunk.get(
                "chunk_id"
            )


            if not chunk_id:

                print(
                    f"[WARN] Chunk không có chunk_id: "
                    f"{doc_id}"
                )

                continue


            if chunk_id in seen_chunk_ids:
                continue


            seen_chunk_ids.add(
                chunk_id
            )


            relevant_chunks.append({

                "chunk_id": chunk_id,

                "doc_id": doc_id,

                "chapter": chapter,

                "dieu": dieu,

                "khoan": [],

                "diem": diem_list,

            })


    # ========================================================
    # TẠO SAMPLE
    # ========================================================

    sample = {

        "query_id": query_id,

        "query": question,

        "question_type": question_type,

        "difficulty": difficulty,

        "answerable": answerable,

        "relevant_chunks": relevant_chunks,

    }


    # notes chỉ thêm nếu có
    if notes is not None:
        sample["notes"] = notes


    # ========================================================
    # CẢNH BÁO
    # ========================================================

    if answerable and len(relevant_chunks) == 0:

        print(
            f"[WARNING] {query_id}: "
            f"answerable=True nhưng không có "
            f"relevant_chunks."
        )


    if not answerable:

        print(
            f"[INFO] {query_id}: "
            f"answerable=False"
        )


    golden_dataset.append(
        sample
    )


# ============================================================
# 9. SAVE JSON
# ============================================================

with open(
    output_file,
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        golden_dataset,
        f,
        ensure_ascii=False,
        indent=2
    )


# ============================================================
# 10. THỐNG KÊ
# ============================================================

total = len(golden_dataset)

answerable_count = sum(
    1
    for item in golden_dataset
    if item["answerable"]
)

unanswerable_count = (
    total - answerable_count
)

total_relevant_chunks = sum(
    len(item["relevant_chunks"])
    for item in golden_dataset
)


print()
print("=" * 70)
print("HOÀN TẤT BUILD GOLDEN DATASET")
print("=" * 70)

print(
    f"Tổng số câu hỏi:       {total}"
)

print(
    f"Answerable:             {answerable_count}"
)

print(
    f"Unanswerable:           {unanswerable_count}"
)

print(
    f"Tổng relevant chunks:   {total_relevant_chunks}"
)

print(
    f"Output:                 {output_file}"
)

print("=" * 70)