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
# 3. EXTRACT METADATA & EFFECTIVE DATE
# =========================
def extract_metadata(text):
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    header_full = "\n".join(lines[:30])
    
    metadata = {
        "doc_id": "UNKNOWN",
        "document_number": None,
        "issued_date": None,       # Ngày ban hành
        "effective_date": None,    # Ngày có hiệu lực
        "expiry_date": None,       # Ngày hết hiệu lực
        "status": "dang_co_hieu_luc", # dang_co_hieu_luc | het_hieu_luc
        "issuer": None,
        "document_type": None,
        "title": None
    }

    # 1️⃣ EXTRACT: Số hiệu & ID
    num_match = re.search(r"(\d{1,3}/\d{4}/[\w\-]+)", header_full)
    if num_match:
        num = num_match.group(1)
        metadata["document_number"] = num
        metadata["doc_id"] = num.replace("/", "_")

    # 2️⃣ EXTRACT: Ngày ban hành
    date_match = re.search(
        r"ngày\s*(\d{1,2})\s*(?:/|tháng\s*)(\d{1,2})\s*(?:/|năm\s*)(\d{4})", 
        header_full, 
        re.IGNORECASE
    )
    if date_match:
        day, month, year = date_match.groups()
        metadata["issued_date"] = f"{year}-{int(month):02d}-{int(day):02d}" # Chuẩn hóa YYYY-MM-DD

    # 3️⃣ EXTRACT: Ngày có hiệu lực từ các điều khoản thi hành (Quét từ dưới lên)
    footer_text = "\n".join(lines[-40:]) # Lấy 40 dòng cuối văn bản
    eff_match = re.search(
        r"(?:có hiệu lực|hiệu lực thi hành)\s+(?:kể\s+từ|từ)\s+ngày\s*(\d{1,2})\s*(?:/|tháng\s*)(\d{1,2})\s*(?:/|năm\s*)(\d{4})",
        footer_text,
        re.IGNORECASE
    )
    if eff_match:
        day, month, year = eff_match.groups()
        metadata["effective_date"] = f"{year}-{int(month):02d}-{int(day):02d}"
    else:
        # Fallback: Nếu không tìm thấy, mặc định sau ngày ban hành 45 ngày (hoặc bằng ngày ban hành tùy cấu hình)
        metadata["effective_date"] = metadata["issued_date"]

    # 4️⃣ EXTRACT: Issuer (Cơ quan ban hành)
    if lines:
        issuer_raw = lines[0].split("---")[0].strip()
        metadata["issuer"] = issuer_raw.title() if issuer_raw else "UNKNOWN"

    # 5️⃣ EXTRACT: Loại văn bản & Tiêu đề
    type_map = {
        "LUẬT": "Luật",
        "NGHỊ ĐỊNH": "Nghị định",
        "THÔNG TƯ": "Thông tư",
        "QUYẾT ĐỊNH": "Quyết định",
        "NGHỊ QUYẾT": "Nghị quyết"
    }

    for i, line in enumerate(lines[:30]):
        line_up = line.upper()
        for key, value in type_map.items():
            if re.search(rf"^{key}\b", line_up):
                metadata["document_type"] = value
                title_parts = []
                for j in range(i + 1, min(i + 5, len(lines[:30]))):
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
# 4. PROCESS AND STORE WITH CASCADE UPDATE
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
                full_text = read_pdf_full(file_path)
                meta = extract_metadata(full_text)
                doc_id = meta["doc_id"] if meta["doc_id"] != "UNKNOWN" else str(uuid.uuid4())

                content_hash = hashlib.md5(full_text.encode()).hexdigest()
                existing_doc = doc_col.find_one({"_id": doc_id})

                if existing_doc:
                    old_hash = existing_doc.get("content_hash")
                    if old_hash == content_hash:
                        print(f"[SKIP NO CHANGE] {doc_id}")
                        continue
                    version = existing_doc.get("current_version", 1) + 1
                else:
                    version = 1

                version_id = f"{doc_id}_v{version}"

                # Update Document hiện tại
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

                # Đóng version cấu trúc nội bộ cũ
                version_col.update_many(
                    {"doc_id": doc_id, "is_current": True},
                    {"$set": {"is_current": False, "valid_to": meta.get("effective_date")}}
                )

                version_col.insert_one({
                    "_id": version_id,
                    "doc_id": doc_id,
                    "version": version,
                    "effective_date": meta.get("effective_date"),
                    "valid_from": meta.get("effective_date") or "1900-01-01",
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
                        "status": meta["status"],  # Thừa hưởng trạng thái "dang_co_hieu_luc" từ meta văn bản
                        "valid_from": meta.get("effective_date") or "1900-01-01",
                        "valid_to": None,
                    }
                    chunk_docs.append(chunk_doc)

                    # Trích xuất tham chiếu và xử lý mối liên kết lan truyền
                    ref_extractor = SimpleReferenceExtractor()
                    refs = ref_extractor.extract_references(content)

                    for ref in refs:
                        ref_id = str(uuid.uuid4())
                        target_doc_number = ref["doc_number"]

                        ref_docs.append({
                            "_id": ref_id,
                            "source_chunk_id": chunk_id,
                            "source_doc_id": doc_id,
                            "reference": {
                                "doc_type": ref["doc_type"],
                                "doc_number": target_doc_number
                            },
                            "context": ref["context"],
                            "type": "legal_reference"
                        })

                        # 🌟 CƠ CHẾ CASCADE UPDATE: KHAI TỬ HIỆU LỰC VĂN BẢN BỊ THAY THẾ
                        if re.search(r"(thay thế|bãi bỏ|hủy bỏ)", content, re.IGNORECASE):
                            # Tìm kiếm văn bản cũ trong hệ thống qua số hiệu văn bản
                            old_doc = doc_col.find_one({"metadata.document_number": target_doc_number})
                            
                            if old_doc:
                                target_doc_id = old_doc["_id"]
                                
                                # 1. Cập nhật trạng thái của văn bản cũ trong bảng documents
                                doc_col.update_one(
                                    {"_id": target_doc_id},
                                    {"$set": {
                                        "metadata.status": "het_hieu_luc",
                                        "metadata.expiry_date": meta.get("effective_date")
                                    }}
                                )
                                
                                # 2. Cập nhật lan truyền tất cả các Chunks cũ sang "het_hieu_luc"
                                chunk_col.update_many(
                                    {"doc_id": target_doc_id},
                                    {"$set": {
                                        "status": "het_hieu_luc",
                                        "valid_to": meta.get("effective_date")
                                    }}
                                )
                                
                                # 3. Lưu mối quan hệ thay thế cấu trúc
                                doc_link_col.update_one(
                                    {"source_doc": doc_id, "target_doc": target_doc_id},
                                    {"$set": {"relation": "replaces"}},
                                    upsert=True
                                )
                        
                        elif re.search(r"(sửa đổi|bổ sung)", content, re.IGNORECASE):
                            # Nếu chỉ sửa đổi bổ sung, lưu mối quan hệ liên kết thông thường
                            old_doc = doc_col.find_one({"metadata.document_number": target_doc_number})
                            if old_doc:
                                doc_link_col.update_one(
                                    {"source_doc": doc_id, "target_doc": old_doc["_id"]},
                                    {"$set": {"relation": "amends"}},
                                    upsert=True
                                )

                        # Mặc định tạo quan hệ tham chiếu chung
                        old_doc = doc_col.find_one({"metadata.document_number": target_doc_number})
                        target_id = old_doc["_id"] if old_doc else "EXTERNAL_REF"
                        doc_link_col.update_one(
                            {"source_doc": doc_id, "target_doc": target_id},
                            {"$set": {"relation": "refers_to"}},
                            upsert=True
                        )

                if chunk_docs:
                    chunk_col.insert_many(chunk_docs)
                    total_chunks += len(chunk_docs)

                if ref_docs:
                    ref_col.insert_many(ref_docs)

            except Exception as e:
                print(f"[ERROR] {file_name}: {e}")

    print(f"\n[SUCCESS] Total chunks: {total_chunks}")
    return total_chunks


if __name__ == "__main__":
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")
    db = get_db()
    process_and_store(DATA_RAW_PATH, db)