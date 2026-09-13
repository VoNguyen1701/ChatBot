from src.storage.mongo import get_db


db = get_db()
chunk_col = db["chunks"]


print("========================================")
print("KIỂM TRA MONGODB CHUNKS")
print("========================================")


docs = list(
    chunk_col.find(
        {},
        {
            "_id": 1,
            "doc_id": 1,
            "parent_doc_id": 1,
            "section_title": 1
        }
    ).limit(10)
)


print(f"[INFO] Lấy được {len(docs)} documents\n")


for i, doc in enumerate(docs, start=1):

    print(f"--- DOCUMENT {i} ---")

    print(
        "_id:",
        doc.get("_id")
    )

    print(
        "_id type:",
        type(doc.get("_id"))
    )

    print(
        "doc_id:",
        doc.get("doc_id")
    )

    print(
        "parent_doc_id:",
        doc.get("parent_doc_id")
    )

    print(
        "section_title:",
        doc.get("section_title")
    )

    print()