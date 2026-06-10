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


# ==========================================
# Load Excel
# ==========================================

BASE_DIR = Path(__file__).resolve().parents[1] # root of the project

excel_path = BASE_DIR / "data" / "eval" / "ques.xlsx"

df = pd.read_excel(excel_path)

# bỏ dòng trống
df = df[df["id"].notna()]

# reset index
df = df.reset_index(drop=True)
df["id"] = df["id"].ffill()
df["question"] = df["question"].ffill()
df["difficulty"] = df["difficulty"].ffill()

# ==========================================
# Build Golden Dataset
# ==========================================

golden_dataset = []

grouped = df.groupby("id")

for qid, group in grouped:

    query_id = f"q{int(qid):03d}"

    question = str(
        group.iloc[0]["question"]
    ).strip()

    relevant_ids = []
    metadata = []

    for _, row in group.iterrows():
        # Kiểm tra nếu dòng đó không có doc_id thì bỏ qua
        if pd.isna(row["doc_id"]):
            continue

        doc_id = (
            str(row["doc_id"])
            .strip()
            .replace("/", "_")
        )
        chapter = None
        if "chapter" in row and pd.notna(row["chapter"]):
            try:
                chapter = int(float(row["chapter"]))
            except (ValueError, TypeError):
                chapter = None
        # XỬ LÝ ĐIỀU: Ép chắc chắn về kiểu int của Python
        dieu = None
        if pd.notna(row["dieu"]):
            try:
                # Ép qua float trước rồi mới về int để tránh lỗi nếu Excel lưu dạng 29.0
                dieu = int(float(row["dieu"]))
            except (ValueError, TypeError):
                dieu = None

        # XỬ LÝ KHOẢN: Tách danh sách khoản và ép về kiểu int
        khoan_list = [None]
        if pd.notna(row["khoan"]):
            khoan_raw = str(row["khoan"]).strip()

            if ";" in khoan_raw:
                khoan_list = []
                for x in khoan_raw.split(";"):
                    try:
                        if x.strip():
                            khoan_list.append(int(float(x.strip())))
                    except (ValueError, TypeError):
                        pass
            else:
                try:
                    khoan_list = [int(float(khoan_raw))]
                except (ValueError, TypeError):
                    khoan_list = [None]

        # Duyệt qua từng khoản để tạo query chính xác lên MongoDB
        for khoan in khoan_list:
            query = {
                "doc_id": doc_id
            }

            # Chỉ đưa vào query nếu trường đó có giá trị cụ thể (không phải None)
            if chapter is not None:
                query["hierarchy.chapter"] = chapter
            else:
                query["hierarchy.chapter"] = None
            if dieu is not None:
                query["hierarchy.dieu"] = dieu
            else:
                query["hierarchy.dieu"] = None

            if khoan is not None:
                query["hierarchy.khoan"] = khoan
            else:
                query["hierarchy.khoan"] = None

            # Bổ sung: Ưu tiên quét các chunk ở tầng nội dung (clause)
            chunk = chunks_col.find_one(query)

            # Dự phòng (Fallback): Nếu trong DB của bạn không lưu hierarchy dạng None 
            # mà bỏ trống trường đó khi không có điều/khoản, hãy xóa điều kiện None đi
            if chunk is None:
                alt_query = {"doc_id": doc_id}
                if chapter is not None:
                    alt_query["hierarchy.chapter"] = chapter
                if dieu is not None:
                    alt_query["hierarchy.dieu"] = dieu
                if khoan is not None:
                    alt_query["hierarchy.khoan"] = khoan
                chunk = chunks_col.find_one(alt_query)

            if chunk is None:
                print(
                    f"[WARN] Không tìm thấy trong DB: "
                    f"{doc_id}, Điều {dieu}, Khoản {khoan}"
                )
                continue

            if "chunk_id" in chunk:
                relevant_ids.append(chunk["chunk_id"])

        metadata.append({
            "doc_id": doc_id,
            "chapter": chapter,
            "dieu": dieu,
            "khoan": [k for k in khoan_list if k is not None]
        })

    # loại bỏ trùng mã chunk_id
    relevant_ids = list(
        set(relevant_ids)
    )

    if len(relevant_ids) == 0:
        print(
            f"[SKIP] {query_id} do không tìm thấy bất kỳ chunk đáp án nào."
        )
        continue

    golden_dataset.append({
        "query_id": query_id,
        "query": question,
        "relevant_ids": relevant_ids,
        "metadata": metadata
    })

# ==========================================
# Save
# ==========================================

output_dir = BASE_DIR / "datasets"
output_dir.mkdir(exist_ok=True)

output_file = output_dir / "golden_dataset.json"

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

print()
print("=" * 60)
print(f"Đã tạo {len(golden_dataset)} samples")
print(f"Lưu tại: {output_file}")
print("=" * 60)