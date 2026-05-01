# src/pdf/merged_chunking.py
"""
Hợp nhất tốt nhất của cả 2 phương pháp
- Tree-based parsing từ optimized_chunking.py
- Version control từ read_pdf.py
- Document links từ read_pdf.py
"""

import os, sys, re, uuid, hashlib
from tqdm import tqdm
import pdfplumber
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_db


# =========================
# 1. BUILD TREE (from optimized_chunking)
# =========================
def build_document_tree(text):
    """Xây dựng tree structure Điều → Khoản → Điểm"""
    lines = text.split('\n')
    tree = {
        "preamble": "",
        "articles": []
    }
    
    current_article = None
    current_clause = None
    preamble_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # ARTICLE LEVEL
        article_match = re.match(r'Điều\s+(\d+)\.\s*(.*)', line, re.IGNORECASE)
        if article_match:
            if current_article:
                tree["articles"].append(current_article)
            
            current_article = {
                "number": int(article_match.group(1)),
                "title": f"Điều {article_match.group(1)}",
                "preamble": article_match.group(2),
                "clauses": []
            }
            current_clause = None
            continue
        
        # CLAUSE LEVEL
        clause_match = re.match(r'^(\d+)[.\)]\s*(.*)', line)
        if clause_match and current_article:
            clause_num = int(clause_match.group(1))
            content = clause_match.group(2)
            
            if current_clause:
                current_article["clauses"].append(current_clause)
            
            current_clause = {
                "number": clause_num,
                "content": content,
                "points": []
            }
            continue
        
        # POINT LEVEL
        point_match = re.match(r'^([a-z])[.\)]\s*(.*)', line, re.IGNORECASE)
        if point_match and current_clause:
            point_label = point_match.group(1)
            content = point_match.group(2)
            
            current_clause["points"].append({
                "label": point_label,
                "content": content
            })
            continue
        
        # Append to current level
        if not current_article:
            preamble_lines.append(line)
        elif current_clause:
            current_clause["content"] += " " + line
        elif current_article:
            current_article["preamble"] += " " + line
    
    # Save last items
    if current_clause and current_article:
        current_article["clauses"].append(current_clause)
    if current_article:
        tree["articles"].append(current_article)
    
    tree["preamble"] = " ".join(preamble_lines)
    return tree


# =========================
# 2. EXTRACT REFERENCES (from optimized_chunking)
# =========================
def extract_references_from_text(text):
    """Trích xuất tham chiếu với context"""
    doc_types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
    references = []
    
    for doc_type in doc_types:
        pattern = rf"(?:theo\s+|của\s+|sửa đổi\s+|bổ sung\s+)?{doc_type}\s+(?:số\s+)?(\d+[\w\/\-\.]*(?:/\d{4})?)"
        matches = re.finditer(pattern, text, re.IGNORECASE)
        
        for match in matches:
            ref_num = match.group(1)
            start = max(0, match.start() - 30)
            end = min(len(text), match.end() + 30)
            context = text[start:end].strip()
            
            relationship = _determine_relationship(match.group(0))
            
            references.append({
                "doc_type": doc_type,
                "doc_number": ref_num,
                "relationship": relationship,
                "context": context
            })
    
    return references


def _determine_relationship(text):
    """Xác định loại mối quan hệ"""
    text_upper = text.upper()
    if "SỬA ĐỔI" in text_upper and "BỔ SUNG" in text_upper:
        return "sửa_đổi_bổ_sung"
    elif "SỬA ĐỔI" in text_upper:
        return "sửa_đổi"
    elif "BỔ SUNG" in text_upper:
        return "bổ_sung"
    elif "THAY" in text_upper:
        return "thay_thế"
    return "tham_chiếu"


# =========================
# 3. FLATTEN TREE + EXTRACT REFS
# =========================
def flatten_tree_to_chunks(tree, metadata, doc_ref):
    """Flatten tree + extract references mỗi chunk"""
    chunks = []
    
    # Preamble
    if tree["preamble"].strip():
        refs = extract_references_from_text(tree["preamble"])
        chunks.append({
            "_id": str(uuid.uuid4()),
            "dieu": None,
            "khoan": None,
            "diem": None,
            "section_title": "Mở đầu",
            "content": f"{doc_ref} - Mở đầu: {tree['preamble'][:1500]}",
            "full_content": tree["preamble"],
            "location": {"article": None, "clause": None, "point": None},
            "references": refs,
            "level": "preamble"
        })
    
    # Articles, Clauses, Points
    for article in tree["articles"]:
        article_num = article["number"]
        article_title = article["title"]
        
        if not article["clauses"]:
            full_content = article["preamble"]
            refs = extract_references_from_text(full_content)
            
            chunks.append({
                "_id": str(uuid.uuid4()),
                "dieu": article_num,
                "khoan": None,
                "diem": None,
                "section_title": article_title,
                "content": f"{doc_ref} - {article_title}: {full_content}",
                "full_content": full_content,
                "location": {"article": article_num, "clause": None, "point": None},
                "references": refs,
                "level": "article"
            })
        else:
            for clause in article["clauses"]:
                clause_num = clause["number"]
                clause_content = article["preamble"] + " " + clause["content"]
                
                if not clause["points"]:
                    refs = extract_references_from_text(clause_content)
                    
                    chunks.append({
                        "_id": str(uuid.uuid4()),
                        "dieu": article_num,
                        "khoan": clause_num,
                        "diem": None,
                        "section_title": f"{article_title} - Khoản {clause_num}",
                        "content": f"{doc_ref} - {article_title} - Khoản {clause_num}: {clause_content}",
                        "full_content": clause_content,
                        "location": {"article": article_num, "clause": clause_num, "point": None},
                        "references": refs,
                        "level": "clause"
                    })
                else:
                    for point in clause["points"]:
                        point_label = point["label"]
                        full_content = clause_content + " " + point["content"]
                        refs = extract_references_from_text(full_content)
                        
                        chunks.append({
                            "_id": str(uuid.uuid4()),
                            "dieu": article_num,
                            "khoan": clause_num,
                            "diem": point_label,
                            "section_title": f"{article_title} - Khoản {clause_num} - Điểm {point_label}",
                            "content": f"{doc_ref} - {article_title} - Khoản {clause_num} - Điểm {point_label}: {full_content}",
                            "full_content": full_content,
                            "location": {"article": article_num, "clause": clause_num, "point": point_label},
                            "references": refs,
                            "level": "point"
                        })
    
    return chunks


# =========================
# 4. PROCESS WITH VERSION CONTROL (from read_pdf)
# =========================
def process_and_store_merged(base_folder, db):
    """
    MERGED: Tree-based chunking + Version control + Amendment tracking
    """
    from read_pdf import read_pdf_full, extract_metadata
    
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
    total_refs = 0
    
    for cat in categories:
        cat_path = os.path.join(base_folder, cat)
        files = [f for f in os.listdir(cat_path) if f.endswith(".pdf")]
        
        for file_name in tqdm(files, desc=f"Category: {cat}"):
            file_path = os.path.join(cat_path, file_name)
            
            try:
                # READ
                full_text = read_pdf_full(file_path)
                
                # BUILD TREE
                tree = build_document_tree(full_text)
                
                # METADATA
                meta = extract_metadata(full_text)
                
                # VERSION CONTROL (from read_pdf)
                doc_id = meta["doc_id"]
                content_hash = hashlib.md5(full_text.encode()).hexdigest()
                
                existing_doc = doc_col.find_one({"_id": doc_id})
                
                if existing_doc and existing_doc.get("content_hash") == content_hash:
                    print(f"[SKIP] {doc_id} - No changes")
                    continue
                
                version = (existing_doc.get("current_version", 0) if existing_doc else 0) + 1
                version_id = f"{doc_id}_v{version}"
                
                # UPDATE DOCUMENT
                doc_col.update_one(
                    {"_id": doc_id},
                    {"$set": {
                        "_id": doc_id,
                        "metadata": meta,
                        "current_version": version,
                        "content_hash": content_hash,
                        "category": cat,
                        "file_name": file_name,
                        "tree_stats": {
                            "total_articles": len(tree["articles"]),
                            "total_clauses": sum(len(a["clauses"]) for a in tree["articles"]),
                            "total_points": sum(
                                len(p) for a in tree["articles"]
                                for c in a["clauses"]
                                for p in c["points"]
                            )
                        }
                    }},
                    upsert=True
                )
                
                # CLOSE OLD VERSIONS
                version_col.update_many(
                    {"doc_id": doc_id, "is_current": True},
                    {"$set": {"is_current": False}}
                )
                
                # CREATE NEW VERSION
                version_col.insert_one({
                    "_id": version_id,
                    "doc_id": doc_id,
                    "version": version,
                    "effective_date": meta.get("issued_date"),
                    "is_current": True,
                    "created_at": datetime.utcnow()
                })
                
                # FLATTEN TREE → CHUNKS
                doc_ref = f"[{meta['document_type']} {meta['document_number']}]"
                chunks = flatten_tree_to_chunks(tree, meta, doc_ref)
                
                # DELETE OLD
                chunk_col.delete_many({"doc_id": doc_id})
                ref_col.delete_many({"source_doc_id": doc_id})
                
                # INSERT NEW
                chunk_docs = []
                ref_docs = []
                
                for chunk in chunks:
                    chunk_id = chunk["_id"]
                    
                    chunk_docs.append({
                        "_id": chunk_id,
                        "doc_id": doc_id,
                        "version_id": version_id,
                        "hierarchy": {
                            "dieu": chunk["dieu"],
                            "khoan": chunk["khoan"],
                            "diem": chunk["diem"]
                        },
                        "section_title": chunk["section_title"],
                        "content": chunk["content"],
                        "full_content": chunk["full_content"],
                        "location": chunk["location"],
                        "level": chunk["level"],
                        "content_length": len(chunk["full_content"]),
                        "effective_date": meta.get("issued_date")
                    })
                    
                    # References
                    for ref in chunk["references"]:
                        ref_docs.append({
                            "_id": str(uuid.uuid4()),
                            "source_chunk_id": chunk_id,
                            "source_doc_id": doc_id,
                            "source_location": chunk["location"],
                            "source_level": chunk["level"],
                            "referenced_doc_type": ref["doc_type"],
                            "referenced_doc_number": ref["doc_number"],
                            "relationship_type": ref["relationship"],
                            "context": ref["context"]
                        })
                        
                        # UPDATE DOCUMENT LINKS
                        relation_type = "amends" if ref["relationship"] in ["sửa_đổi", "sửa_đổi_bổ_sung", "thay_thế"] else "refers_to"
                        
                        doc_link_col.update_one(
                            {"source_doc": doc_id, "target_doc": ref["doc_number"]},
                            {"$set": {"relation": relation_type, "last_updated": datetime.utcnow()}},
                            upsert=True
                        )
                
                if chunk_docs:
                    chunk_col.insert_many(chunk_docs)
                    total_chunks += len(chunk_docs)
                
                if ref_docs:
                    ref_col.insert_many(ref_docs)
                    total_refs += len(ref_docs)
                
            except Exception as e:
                print(f"[ERROR] {file_name}: {e}")
                import traceback
                traceback.print_exc()
    
    print(f"\n[SUCCESS] Total chunks: {total_chunks}")
    print(f"[SUCCESS] Total references: {total_refs}")
    return total_chunks


if __name__ == "__main__":
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")
    db = get_db()
    process_and_store_merged(DATA_RAW_PATH, db)