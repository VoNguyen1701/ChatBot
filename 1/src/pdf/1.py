# src/pdf/read_pdf.py
import os, sys, re, uuid, hashlib
from tqdm import tqdm
import pdfplumber

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
# 3. METADAT
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

    # 1. Số hiệu & ID
    num_match = re.search(r"Số[:\s]*([\w\/\-]+)", header_full, re.IGNORECASE)
    if num_match:
        num = num_match.group(1)
        metadata["document_number"] = num
        metadata["doc_id"] = num.replace("/", "_")

    # 2. Ngày ban hành
    date_match = re.search(r"ngày\s*(\d{1,2})\s*(?:/|tháng\s*)(\d{1,2})\s*(?:/|năm\s*)(\d{4})", header_full, re.IGNORECASE)
    if date_match:
        metadata["issued_date"] = f"{date_match.group(1)}/{date_match.group(2)}/{date_match.group(3)}"

    # 3. Issuer (Cơ quan ban hành) - Lấy dòng ngắn đầu tiên bên trái
    if lines:
        # Thường là dòng 0 hoặc 1 (Ví dụ: QUỐC HỘI hoặc CHÍNH PHỦ)
        metadata["issuer"] = lines[0].split("---")[0].strip().title()

    # 4. Loại văn bản & Tiêu đề
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
            if re.search(rf"^{key}\b", line_up):  # Tìm dòng bắt đầu bằng từ khóa loại văn bản
                metadata["document_type"] = value
                
                # Tiêu đề là các dòng tiếp theo cho đến khi gặp "CĂN CỨ"
                title_parts = []
                for j in range(i + 1, i + 5):
                    if j < len(lines) and "CĂN CỨ" not in lines[j].upper():
                        title_parts.append(lines[j])
                    else:
                        break
                metadata["title"] = " ".join(title_parts).strip()
                break
        if metadata["document_type"]: break

    return metadata
def extract_references(text):
    patterns = [
        r"(Nghị định\s+số\s*\d+\/\d+\/[A-Z\-]+)",
        r"(Luật\s+[^\n,\.]+?\d{4})",
        r"(Thông tư\s+số\s*\d+\/\d+\/[A-Z\-]+)"
    ]

    refs = []
    for p in patterns:
        matches = re.findall(p, text, re.IGNORECASE)
        refs.extend(matches)

    return list(set(refs))
# =========================
# 4. SMART CHUNKING
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
        block = block.strip()

        # 🔥 bỏ block rác
        if not block or len(block) < 10:
            continue

        lines = block.split("\n")
        title = lines[0].strip()

        # 🔥 bỏ title lỗi
        if not title:
            continue

        dieu_match = re.search(r"Điều\s+(\d+)", title)
        if not dieu_match:
            continue

        dieu_number = int(dieu_match.group(1))
        body = " ".join(lines[1:]).strip()
        # =========================
        # Nếu Điều dài → tách khoản
        # =========================
        if len(body) > max_child_size:

            khoan_parts = re.split(r"(?=(?:^|\n|\s)\d+\.\s)", body)  #r"(?=\n\d+\.\s)"

            for kp in khoan_parts:
                kp = kp.strip()
                if not kp:
                    continue

                # extract số khoản
                khoan_match = re.search(r"^(\d+)\.", kp)
                khoan_number = int(khoan_match.group(1)) if khoan_match else None

                # clean content cho embedding (bỏ "Điều X.")
                clean_kp = re.sub(r"Điều\s+\d+\.\s*", "", kp)

                chunks.append({
                    "dieu": dieu_number,
                    "khoan": khoan_number,
                    "section_title": f"{title} - Khoản {khoan_number}",
                    "content": f"{doc_ref} - {title} - {clean_kp}"
                })

        else:
            chunks.append({
                "dieu": dieu_number,
                "khoan": None,
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
                chunks = split_into_smart_chunks(full_text, meta)

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
                            "dieu": chunk.get("dieu"),
                            "khoan": chunk.get("khoan"),
                            #"diem": chunk.get("diem")   # (tạm thời có thể None)
                        },
                        "item_path": build_item_path(
                            chunk.get("dieu"),
                            chunk.get("khoan"),
                            #chunk.get("diem")
                        ),

                        "section_title": chunk["section_title"],
                        "content": content,
                        "content_length": len(content),
                        "valid_from": meta.get("issued_date") or "1900-01-01",
                        "valid_to": None,
                    }

                    chunk_docs.append(chunk_doc)

                    # ===== 2. EXTRACT REFERENCES =====
                    refs = extract_references(content)

                    for ref in refs:
                        ref_id = str(uuid.uuid4())

                        # lưu reference
                        ref_docs.append({
                            "_id": ref_id,
                            "source_chunk_id": chunk_id,
                            "source_doc_id": doc_id,
                            "reference_text": ref,
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