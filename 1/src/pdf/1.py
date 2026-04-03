# src/pdf/read_pdf.py
import os, sys, re, uuid
from tqdm import tqdm
import pdfplumber

# =========================
# SETUP PATH
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_mongo_client


# =========================
# 1. CLEAN TEXT
# =========================
def clean_text(text):
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"Trang\s*\d+", "", text, flags=re.IGNORECASE)
    return text.strip()


# =========================
# 2. READ PDF
# =========================
def read_pdf_full(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Không tìm thấy file: {file_path}")

    full_text = ""
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            content = page.extract_text()
            if content:
                full_text += content + "\n"

    return clean_text(full_text)


# =========================
# 3. METADAT
# =========================
def extract_metadata(text):
    header = text[:1500].replace("\n", " ")
    up = header.upper()

    metadata = {
        "doc_id": "UNKNOWN",
        "document_number": None,
        "issued_date": None,
        "issuer": None,
        "document_type": None,
        "title": None
    }

    # document number
    match = re.search(r"Số[:\s]*([\w\/\-]+)", header, re.IGNORECASE)
    if match:
        num = match.group(1)
        metadata["document_number"] = num
        metadata["doc_id"] = num.replace("/", "_")

    # date
    match = re.search(
        r"ngày\s*(\d{1,2})\s*(?:/|tháng\s*)(\d{1,2})\s*(?:/|năm\s*)(\d{4})",
        header,
        re.IGNORECASE,
    )
    if match:
        metadata["issued_date"] = f"{match.group(1)}/{match.group(2)}/{match.group(3)}"

    # type
    if "NGHỊ ĐỊNH" in up:
        metadata["document_type"] = "Nghị định"
    elif "THÔNG TƯ" in up:
        metadata["document_type"] = "Thông tư"
    elif "QUYẾT ĐỊNH" in up:
        metadata["document_type"] = "Quyết định"
    elif "LUẬT" in up:
        metadata["document_type"] = "Luật"

    # issuer
    match = re.search(r"(BỘ\s+[A-Z\s]+|UBND\s+[A-Z\s]+)", up)
    if match:
        metadata["issuer"] = match.group(1).title()

    # title
    lines = text.split("\n")[:20]
    titles = [l.strip() for l in lines if len(l) > 20]
    if titles:
        metadata["title"] = titles[0]

    return metadata


# =========================
# 4. SMART CHUNKING (CODE 1 + IMPROVE)
# =========================
def split_into_smart_chunks(text, metadata, max_child_size=800):
    text = re.sub(r"\n+", "\n", text).strip()

    doc_ref = f"[{metadata['document_type']} {metadata['document_number']}]"

    # =========================
    # 1. Split theo Điều chuẩn
    # =========================
    dieu_blocks = re.split(r"(?=\n?Điều\s+\d+\.)", text)
    chunks = []

    # =========================
    # 2. Xử lý mở đầu
    # =========================
    intro = dieu_blocks[0].strip()
    if intro:
        chunks.append({
            "section_title": "Mở đầu",
            "content": f"{doc_ref} {intro[:1200]}"
        })

    # =========================
    # 3. Xử lý từng Điều
    # =========================
    for block in dieu_blocks[1:]:
        lines = block.strip().split("\n")

        title = lines[0].strip()
        body = " ".join(lines[1:]).strip()

        # =========================
        # Nếu Điều dài → tách khoản
        # =========================
        if len(body) > max_child_size:

            khoan_parts = re.split(r"(?=\d+\.\s)", body)

            for kp in khoan_parts:
                kp = kp.strip()
                if not kp:
                    continue

                chunks.append({
                    "section_title": f"{title} - khoản",
                    "content": f"{doc_ref} - {title} - {kp}"
                })

        else:
            chunks.append({
                "section_title": title,
                "content": f"{doc_ref} - {title}: {body}"
            })

    return chunks


# =========================
# 5. STORE
# =========================
def process_and_store(base_folder, db):
    doc_col = db["documents"]
    chunk_col = db["chunks"]

    categories = [
        f for f in os.listdir(base_folder)
        if os.path.isdir(os.path.join(base_folder, f))
    ]

    total_chunks = 0

    for cat in categories:
        cat_path = os.path.join(base_folder, cat)
        files = [f for f in os.listdir(cat_path) if f.endswith(".pdf")]

        for file_name in tqdm(files, desc=f"Category: {cat}"):
            file_path = os.path.join(cat_path, file_name)

            try:
                # READ
                full_text = read_pdf_full(file_path)

                # METADATA
                meta = extract_metadata(full_text)

                # DOC ID
                doc_id = meta["doc_id"] if meta["doc_id"] != "UNKNOWN" else str(uuid.uuid4())

                # SAVE DOCUMENT (UPSERT)
                doc_col.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "_id": doc_id,
                        "metadata": meta,
                        "category": cat,
                        "file_name": file_name,
                        "raw_length": len(full_text)
                    }},
                    upsert=True
                )

                # DELETE OLD CHUNKS
                chunk_col.delete_many({"parent_doc_id": doc_id})

                # CHUNKING
                chunks = split_into_smart_chunks(full_text, meta)

                chunk_docs = []
                for chunk in chunks:
                    chunk_docs.append({
                        "_id": str(uuid.uuid4()),
                        "parent_doc_id": doc_id,
                        "section_title": chunk["section_title"],
                        "content": chunk["content"],
                        "content_length": len(chunk["content"])
                    })

                if chunk_docs:
                    chunk_col.insert_many(chunk_docs)
                    total_chunks += len(chunk_docs)

            except Exception as e:
                print(f"[ERROR] {file_name}: {e}")

    print(f"\n[SUCCESS] Total chunks: {total_chunks}")
    return total_chunks


# =========================
# 6. MAIN
# =========================
if __name__ == "__main__":
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")

    client = get_mongo_client()
    db = client["legal_rag_db"]

    process_and_store(DATA_RAW_PATH, db)