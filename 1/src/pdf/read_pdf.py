# src/pdf/read_pdf.py
import os, sys, re, uuid, hashlib
from tqdm import tqdm
import pdfplumber
from pdf.legal_parser import DocumentTreeBuilder, ChunkBuilder
from pdf.legal_parser import SimpleReferenceExtractor
# =========================
# SETUP PATH
# =========================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_db


# =========================
# 1. CLEAN TEXT
# =========================
def clean_text(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    text = re.sub(r"Trang\s*\d+", "", text, flags=re.IGNORECASE)
    return text.strip()
def build_item_path(dieu, khoan):
    parts = []
    if dieu:
        parts.append(f"Điều {dieu}")
    if khoan:
        parts.append(f"Khoản {khoan}")
    return " > ".join(parts)
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
# 3. EXTRACT METADATA (BASIC)
# =========================
def extract_metadata(text):
    # Lấy 30 dòng đầu, làm sạch khoảng trắng
    lines = [l.strip() for l in text.split('\n')[:30] if l.strip()]
    header_full = "\n".join(lines)
    up = header_full.upper()

    metadata = {
        "doc_id": "UNKNOWN",
        "document_number": None,
        "issued_date": None,
        "issuer": None,
        "document_type": None,
        "title": None
    }

    # 1️⃣ EXTRACT: Số hiệu & ID
    # Regex: Tìm pattern "Số: XXX/2026" hoặc "Số XXX/2026"
    num_match = re.search(r"Số[:\s]*([\w\/\-]+)", header_full, re.IGNORECASE)
    if num_match:
        num = num_match.group(1)
        metadata["document_number"] = num
        metadata["doc_id"] = num.replace("/", "_")

    # 2️⃣ EXTRACT: Ngày ban hành
    # Regex: Tìm pattern "ngày 25 / tháng 12 / năm 2025"
    # Hoặc: "ngày 25/12/2025"
    date_match = re.search(
        r"ngày\s*(\d{1,2})\s*(?:/|tháng\s*)(\d{1,2})\s*(?:/|năm\s*)(\d{4})", 
        header_full, 
        re.IGNORECASE
    )
    if date_match:
        day, month, year = date_match.groups()
        metadata["issued_date"] = f"{day}/{month}/{year}"

    # 3️⃣ EXTRACT: Issuer (Cơ quan ban hành)
    # Lấy dòng đầu tiên (thường là QUỐC HỘI, CHÍNH PHỦ, BỘ...)
    if lines:
        issuer_raw = lines[0].split("---")[0].strip()
        metadata["issuer"] = issuer_raw.title() if issuer_raw else "UNKNOWN"

    # 4️⃣ EXTRACT: Loại văn bản & Tiêu đề
    type_map = {
        "LUẬT": "Luật",
        "NGHỊ ĐỊNH": "Nghị định",
        "THÔNG TƯ": "Thông tư",
        "QUYẾT ĐỊNH": "Quyết định",
        "NGHỊ QUYẾT": "Nghị quyết"
    }

    for i, line in enumerate(lines):
        line_up = line.upper()
        for key, value in type_map.items():
            # Match: Line bắt đầu bằng loại văn bản
            if re.search(rf"^{key}\b", line_up):
                metadata["document_type"] = value
                
                # Tiêu đề = 3-4 dòng sau đó (cho đến khi gặp "CĂN CỨ")
                title_parts = []
                for j in range(i + 1, min(i + 5, len(lines))):
                    if "CĂN CỨ" not in lines[j].upper():
                        title_parts.append(lines[j])
                    else:
                        break
                metadata["title"] = " ".join(title_parts).strip()
                break
        
        if metadata["document_type"]:
            break

    return metadata
# =========================
# 5. STORE
# =========================
def process_and_store(base_folder, db):
    doc_col = db["documents"]
    chunk_col = db["chunks"]
    ref_col = db["references"]
    doc_link_col = db["document_links"]
    version_col = db["document_versions"]

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

                # ===== TẠO HASH NỘI DUNG =====
                content_hash = hashlib.md5(full_text.encode()).hexdigest()

                # ===== CHECK DOCUMENT CŨ =====
                existing_doc = doc_col.find_one({"_id": doc_id})

                if existing_doc:
                    old_hash = existing_doc.get("content_hash")

                    # ❌ KHÔNG ĐỔI → SKIP
                    if old_hash == content_hash:
                        print(f"[SKIP NO CHANGE] {doc_id}")
                        continue

                    # ✅ CÓ ĐỔI → tăng version
                    version = existing_doc.get("current_version", 1) + 1
                else:
                    # ✅ DOCUMENT MỚI
                    version = 1

                version_id = f"{doc_id}_v{version}"

                # ===== UPDATE DOCUMENT TRƯỚC =====
                doc_col.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "_id": doc_id,
                        "metadata": meta,
                        "current_version": version,
                        "content_hash": content_hash,
                        "category": cat,
                        "file_name": file_name,
                        "raw_length": len(full_text)
                    }},
                    upsert=True
                )

                # ===== ĐÓNG VERSION CŨ =====
                version_col.update_many(
                    {
                        "doc_id": doc_id,
                        "is_current": True
                    },
                    {
                        "$set": {
                            "is_current": False,
                            "valid_to": meta.get("issued_date")
                        }
                    }
                )

                # ===== TẠO VERSION MỚI =====
                version_col.insert_one({
                    "_id": version_id,
                    "doc_id": doc_id,
                    "version": version,
                    "effective_date": meta.get("issued_date"),
                    "valid_from": meta.get("issued_date") or "1900-01-01",
                    "valid_to": None,
                    "is_current": True
                })

                # CHUNKING
                tree_builder = DocumentTreeBuilder(full_text)
                doc_tree = tree_builder.build()

                chunk_builder = ChunkBuilder(doc_tree, meta)
                chunks = chunk_builder.build()

                chunk_docs = []
                ref_docs = []

                for chunk in chunks:
                    chunk_id = str(uuid.uuid4())

                    content = chunk["content"]

                    # ===== 1. SAVE CHUNK =====
                    chunk_doc = {
                        "_id": chunk_id,
                        "doc_id": doc_id,
                        "version_id": version_id,
                        "hierarchy": {
                            "chapter": chunk["location"].get("chapter"),
                            "dieu": chunk["location"].get("article"),
                            "khoan": chunk["location"].get("clause"),
                            "diem": chunk["location"].get("point")
                        },
                        "item_path": build_item_path(
                            chunk["location"].get("article"),
                            chunk["location"].get("clause")
                        ),
                        "section_title": chunk["section_title"],
                        "content": content,
                        "content_length": len(content),
                        "level": chunk["level"],
                        "valid_from": meta.get("issued_date") or "1900-01-01",
                        "valid_to": None,
                    }

                    chunk_docs.append(chunk_doc)

                    # ===== 2. EXTRACT REFERENCES =====
                    ref_extractor = SimpleReferenceExtractor()
                    refs = ref_extractor.extract_references(content)

                    for ref in refs:
                        ref_id = str(uuid.uuid4())

                        # lưu reference
                        ref_docs.append({
                            "_id": ref_id,
                            "source_chunk_id": chunk_id,
                            "source_doc_id": doc_id,
                            "reference": {
                                "doc_type": ref["doc_type"],
                                "doc_number": ref["doc_number"]
                            },
                            "context": ref["context"],
                            "type": "legal_reference"
                        })

                        
                        # detect sửa đổi
                        if re.search(r"(sửa đổi|bổ sung|thay thế)", content, re.IGNORECASE):
                            doc_link_col.update_one(
                                {
                                    "source_doc": doc_id,
                                    "target_doc": ref
                                },
                                {
                                    "$set": {
                                        "relation": "amends"
                                    }
                                },
                                upsert=True
                            )
                        # ===== 3. BUILD DOCUMENT LINK =====
                        doc_link_col.update_one(
                            {
                                "source_doc": doc_id,
                                "target_doc": ref
                            },
                            {
                                "$set": {
                                    "relation": "refers_to"
                                }
                            },
                            upsert=True
                        )

                # ===== INSERT DB =====
                if chunk_docs:
                    chunk_col.insert_many(chunk_docs)
                    total_chunks += len(chunk_docs)

                if ref_docs:
                    ref_col.insert_many(ref_docs)

            except Exception as e:
                print(f"[ERROR] {file_name}: {e}")

    print(f"\n[SUCCESS] Total chunks: {total_chunks}")
    return total_chunks


# =========================
# 6. MAIN
# =========================
if __name__ == "__main__":
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")

    db = get_db()

    process_and_store(DATA_RAW_PATH, db)