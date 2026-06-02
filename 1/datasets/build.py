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

db = client["ai1_db"]
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

        doc_id = (
            str(row["doc_id"])
            .strip()
            .replace("/", "_")
        )

        dieu = None

        if pd.notna(row["dieu"]):
            dieu = int(row["dieu"])

        # xử lý khoản
        khoan_list = [None]

        if pd.notna(row["khoan"]):

            khoan_raw = str(row["khoan"]).strip()

            if ";" in khoan_raw:

                khoan_list = [
                    int(x.strip())
                    for x in khoan_raw.split(";")
                ]

            else:

                khoan_list = [
                    int(khoan_raw)
                ]

        for khoan in khoan_list:

            query = {
                "doc_id": doc_id
            }

            if dieu is not None:
                query["hierarchy.dieu"] = dieu

            if khoan is not None:
                query["hierarchy.khoan"] = khoan

            chunk = chunks_col.find_one(query)

            if chunk is None:

                print(
                    f"[WARN] Không tìm thấy: "
                    f"{doc_id}, Điều {dieu}, Khoản {khoan}"
                )

                continue

            relevant_ids.append(
                chunk["chunk_id"]
            )

        metadata.append({
            "doc_id": doc_id,
            "dieu": dieu,
            "khoan": khoan_list
        })

    # loại bỏ trùng
    relevant_ids = list(
        set(relevant_ids)
    )

    if len(relevant_ids) == 0:

        print(
            f"[SKIP] {query_id}"
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