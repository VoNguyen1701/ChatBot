# src/pdf/unified_document_processor.py
"""
UNIFIED DOCUMENT PROCESSOR
Kết hợp:
1. merged_chunking.py (Tree-based + Version control)
2. nested_reference_handler.py (Nested reference analysis)
→ 1 module duy nhất, 1 lần parse, tối ưu 100%
"""

import os, sys, re, uuid, hashlib
from tqdm import tqdm
import pdfplumber
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from storage.mongo import get_db


# =========================
# 1. TREE BUILDER (from merged_chunking)
# =========================
class DocumentTreeBuilder:
    """Xây dựng cây cấu trúc Điều → Khoản → Điểm"""
    
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split('\n')
        self.tree = {
            "preamble": "",
            "articles": []
        }
    
    def build(self) -> Dict:
        """Build tree structure"""
        current_article = None
        current_clause = None
        preamble_lines = []
        
        for line in self.lines:
            line = line.strip()
            if not line:
                continue
            
            # ARTICLE LEVEL: "Điều X."
            article_match = re.match(r'Điều\s+(\d+)\.\s*(.*)', line, re.IGNORECASE)
            if article_match:
                if current_article:
                    self.tree["articles"].append(current_article)
                
                current_article = {
                    "number": int(article_match.group(1)),
                    "title": f"Điều {article_match.group(1)}",
                    "preamble": article_match.group(2),
                    "clauses": [],
                    "references": []  # 🔥 NEW: Store references at article level
                }
                current_clause = None
                continue
            
            # CLAUSE LEVEL: "1." hoặc "1)"
            clause_match = re.match(r'^(\d+)[.\)]\s*(.*)', line)
            if clause_match and current_article:
                clause_num = int(clause_match.group(1))
                content = clause_match.group(2)
                
                if current_clause:
                    current_article["clauses"].append(current_clause)
                
                current_clause = {
                    "number": clause_num,
                    "content": content,
                    "points": [],
                    "references": []  # 🔥 NEW
                }
                continue
            
            # POINT LEVEL: "a)" hoặc "a."
            point_match = re.match(r'^([a-z])[.\)]\s*(.*)', line, re.IGNORECASE)
            if point_match and current_clause:
                point_label = point_match.group(1)
                content = point_match.group(2)
                
                current_clause["points"].append({
                    "label": point_label,
                    "content": content,
                    "references": []  # 🔥 NEW
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
            self.tree["articles"].append(current_article)
        
        self.tree["preamble"] = " ".join(preamble_lines)
        return self.tree


# =========================
# 2. REFERENCE EXTRACTOR (merged: simple + nested)
# =========================
class ReferenceExtractor:
    """
    Trích xuất cả 2 loại reference:
    - Simple: Luật 10/2014
    - Nested: Điều 9 ND này → Điều 7 Luật Phí
    """
    
    def __init__(self, text: str):
        self.text = text
        self.doc_types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
    
    def extract_simple_references(self) -> List[Dict]:
        """
        Extract simple references: "Luật 10/2014", "Nghị định 15/2023"
        
        Returns:
        [
            {
                "doc_type": "Luật",
                "doc_number": "10/2014",
                "relationship": "tham_chiếu",
                "context": "...",
                "type": "simple"
            }
        ]
        """
        references = []
        
        for doc_type in self.doc_types:
            pattern = rf"(?:theo\s+|của\s+|sửa đổi\s+|bổ sung\s+)?{doc_type}\s+(?:số\s+)?(\d+[\w\/\-\.]*(?:/\d{4})?)"
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            
            for match in matches:
                ref_num = match.group(1)
                start = max(0, match.start() - 30)
                end = min(len(self.text), match.end() + 30)
                context = self.text[start:end].strip()
                
                relationship = self._determine_relationship(match.group(0))
                
                references.append({
                    "doc_type": doc_type,
                    "doc_number": ref_num,
                    "relationship": relationship,
                    "context": context,
                    "type": "simple",  # 🔥 Mark as simple
                    "confidence": 0.90
                })
        
        return references
    
    def extract_nested_references(self) -> List[Dict]:
        """
        Extract nested references: "Điều 9 ND này → Điều 7 Luật Phí"
        
        Returns:
        [
            {
                "primary": {"type": "Điều", "number": 9, "document": "Nghị định này"},
                "nested": {"type": "Điều", "number": 7, "document": "Luật Phí"},
                "relationship": "equates_to",
                "type": "nested"
            }
        ]
        """
        nested_refs = []
        
        # Pattern: "Điều X [Nghị định/Luật] này ... [Điều/Khoản] Y [Luật/Nghị định]"
        patterns = [
            # Ví dụ: "Điều 9 Nghị định này ... Điều 7 Luật Phí"
            r'Điều\s+(\d+)\s+([Nn]ghị định này|[Ll]uật này|[Tt]hông tư này|[Qq]uyết định này)\s+.*?(?:là|tương ứng|quy định)\s+(?:tại\s+)?([Đđ]iều|[Kk]hoản)\s+(\d+)\s+([A-Za-z0-9\s\u0100-\ỿ,\-\.]+?)(?:[,;]|\n)',
            
            # Ví dụ: "Điều 9 Khoản 1 ND này ... Điều 7 Khoản 2 Luật Phí"
            r'Điều\s+(\d+)\s+[Kk]hoản\s+(\d+)\s+([Nn]ghị định này|[Ll]uật này)\s+.*?(?:là|tương ứng|quy định)\s+(?:tại\s+)?([Đđ]iều|[Kk]hoản)\s+(\d+)\s+(?:[Kk]hoản\s+(\d+)\s+)?([A-Za-z0-9\s\u0100-\ỿ,\-\.]+?)(?:[,;]|\n)',
        ]
        
        for pattern in patterns:
            matches = re.finditer(pattern, self.text, re.IGNORECASE | re.MULTILINE)
            
            for match in matches:
                groups = match.groups()
                
                if len(groups) >= 4:
                    primary_article = int(groups[0])
                    primary_doc = groups[1]
                    nested_article = int(groups[len(groups) - 2])
                    nested_doc = groups[len(groups) - 1].strip()
                    
                    context = self.text[max(0, match.start() - 30):min(len(self.text), match.end() + 30)].strip()
                    
                    relationship = self._determine_nested_relationship(context)
                    
                    nested_refs.append({
                        "primary": {
                            "type": "Điều",
                            "number": primary_article,
                            "document": primary_doc,
                            "is_self": "này" in primary_doc.lower()
                        },
                        "nested": {
                            "type": "Điều",
                            "number": nested_article,
                            "document": nested_doc
                        },
                        "context": context,
                        "relationship": relationship,
                        "type": "nested",  # 🔥 Mark as nested
                        "confidence": 0.85
                    })
        
        return nested_refs
    
    def extract_all(self) -> Tuple[List[Dict], List[Dict]]:
        """Extract both simple and nested references"""
        simple_refs = self.extract_simple_references()
        nested_refs = self.extract_nested_references()
        return simple_refs, nested_refs
    
    def _determine_relationship(self, text: str) -> str:
        """Xác định loại mối quan hệ (simple)"""
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
    
    def _determine_nested_relationship(self, text: str) -> str:
        """Xác định loại mối quan hệ (nested)"""
        text_upper = text.upper()
        
        if any(word in text_upper for word in ["TƯƠNG ĐƯƠNG", "CÙNG", "HỒI TƯƠNG"]):
            return "equates_to"
        elif any(word in text_upper for word in ["THỰC HIỆN", "TRIỂN KHAI", "HƯỚNG DẪN"]):
            return "implements"
        elif any(word in text_upper for word in ["NGOẠI LỆ", "KHÔNG ÁP DỤNG"]):
            return "exempts"
        elif any(word in text_upper for word in ["QUY ĐỊNH CHI TIẾT", "LÀM RÕ"]):
            return "clarifies"
        else:
            return "references"


# =========================
# 3. CHUNK BUILDER (merged: flatten tree + attach refs)
# =========================
class ChunkBuilder:
    """
    Chuyển tree + references thành chunks
    Mỗi chunk chứa:
    - Content
    - Simple references
    - Nested references
    """
    
    def __init__(self, tree: Dict, metadata: Dict, doc_ref: str):
        self.tree = tree
        self.metadata = metadata
        self.doc_ref = doc_ref
        self.chunks = []
    
    def build(self, simple_refs: List[Dict], nested_refs: List[Dict]) -> List[Dict]:
        """Build chunks with references"""
        
        # Build simple refs index for fast lookup
        refs_by_context = self._index_references(simple_refs + nested_refs)
        
        # Preamble chunk
        if self.tree["preamble"].strip():
            refs = self._get_refs_for_text(self.tree["preamble"], refs_by_context)
            
            self.chunks.append({
                "_id": str(uuid.uuid4()),
                "dieu": None,
                "khoan": None,
                "diem": None,
                "section_title": "Mở đầu",
                "content": f"{self.doc_ref} - Mở đầu: {self.tree['preamble'][:1500]}",
                "full_content": self.tree["preamble"],
                "location": {"article": None, "clause": None, "point": None},
                "references": refs,
                "level": "preamble"
            })
        
        # Article chunks
        for article in self.tree["articles"]:
            article_num = article["number"]
            article_title = article["title"]
            article_full_text = article["preamble"]
            
            if not article["clauses"]:
                # No clauses → 1 chunk per article
                refs = self._get_refs_for_text(article_full_text, refs_by_context)
                
                self.chunks.append({
                    "_id": str(uuid.uuid4()),
                    "dieu": article_num,
                    "khoan": None,
                    "diem": None,
                    "section_title": article_title,
                    "content": f"{self.doc_ref} - {article_title}: {article_full_text}",
                    "full_content": article_full_text,
                    "location": {"article": article_num, "clause": None, "point": None},
                    "references": refs,
                    "level": "article"
                })
            else:
                # Has clauses → 1 chunk per clause/point
                for clause in article["clauses"]:
                    clause_num = clause["number"]
                    clause_text = article["preamble"] + " " + clause["content"]
                    
                    if not clause["points"]:
                        # No points → 1 chunk for clause
                        refs = self._get_refs_for_text(clause_text, refs_by_context)
                        
                        self.chunks.append({
                            "_id": str(uuid.uuid4()),
                            "dieu": article_num,
                            "khoan": clause_num,
                            "diem": None,
                            "section_title": f"{article_title} - Khoản {clause_num}",
                            "content": f"{self.doc_ref} - {article_title} - Khoản {clause_num}: {clause_text}",
                            "full_content": clause_text,
                            "location": {"article": article_num, "clause": clause_num, "point": None},
                            "references": refs,
                            "level": "clause"
                        })
                    else:
                        # Has points → 1 chunk per point
                        for point in clause["points"]:
                            point_label = point["label"]
                            point_text = clause_text + " " + point["content"]
                            refs = self._get_refs_for_text(point_text, refs_by_context)
                            
                            self.chunks.append({
                                "_id": str(uuid.uuid4()),
                                "dieu": article_num,
                                "khoan": clause_num,
                                "diem": point_label,
                                "section_title": f"{article_title} - Khoản {clause_num} - Điểm {point_label}",
                                "content": f"{self.doc_ref} - {article_title} - Khoản {clause_num} - Điểm {point_label}: {point_text}",
                                "full_content": point_text,
                                "location": {"article": article_num, "clause": clause_num, "point": point_label},
                                "references": refs,
                                "level": "point"
                            })
        
        return self.chunks
    
    def _index_references(self, references: List[Dict]) -> Dict:
        """Index references by first 50 chars for quick lookup"""
        index = {}
        for ref in references:
            context_key = ref.get("context", "")[:50]
            if context_key not in index:
                index[context_key] = []
            index[context_key].append(ref)
        return index
    
    def _get_refs_for_text(self, text: str, refs_index: Dict) -> List[Dict]:
        """Get references relevant to this text chunk"""
        matching_refs = []
        
        for context_key, refs in refs_index.items():
            if context_key.lower() in text.lower():
                matching_refs.extend(refs)
        
        # Remove duplicates
        seen = set()
        unique_refs = []
        for ref in matching_refs:
            key = (ref.get("doc_type"), ref.get("doc_number"), ref.get("type"))
            if key not in seen:
                seen.add(key)
                unique_refs.append(ref)
        
        return unique_refs


# =========================
# 4. REFERENCE GRAPH BUILDER (nested reference analysis)
# =========================
class ReferenceGraphBuilder:
    """Build reference graph for nested references"""
    
    def __init__(self, nested_refs: List[Dict]):
        self.nested_refs = nested_refs
        self.graph = {
            "nodes": {},
            "edges": [],
            "article_mappings": {}
        }
    
    def build(self) -> Dict:
        """Build reference graph"""
        seen_edges = set()
        
        for ref in self.nested_refs:
            primary = ref["primary"]
            nested = ref["nested"]
            
            primary_id = self._normalize_id(primary["document"])
            nested_id = self._normalize_id(nested["document"])
            
            # Add nodes
            if primary_id not in self.graph["nodes"]:
                self.graph["nodes"][primary_id] = {
                    "type": self._extract_type(primary["document"]),
                    "label": primary["document"],
                    "articles": {}
                }
            
            if nested_id not in self.graph["nodes"]:
                self.graph["nodes"][nested_id] = {
                    "type": self._extract_type(nested["document"]),
                    "label": nested["document"],
                    "articles": {}
                }
            
            # Store articles
            self.graph["nodes"][primary_id]["articles"][primary["number"]] = {
                "title": f"Điều {primary['number']}"
            }
            self.graph["nodes"][nested_id]["articles"][nested["number"]] = {
                "title": f"Điều {nested['number']}"
            }
            
            # Add edges
            edge_id = f"{primary_id}:Điều_{primary['number']}->{nested_id}:Điều_{nested['number']}"
            
            if edge_id not in seen_edges:
                self.graph["edges"].append({
                    "source": f"{primary_id}:Điều_{primary['number']}",
                    "target": f"{nested_id}:Điều_{nested['number']}",
                    "type": ref["relationship"],
                    "confidence": ref["confidence"]
                })
                seen_edges.add(edge_id)
                
                # Store mapping
                mapping_key = f"{primary_id}:Điều_{primary['number']}"
                if mapping_key not in self.graph["article_mappings"]:
                    self.graph["article_mappings"][mapping_key] = []
                
                self.graph["article_mappings"][mapping_key].append({
                    "nested_doc": nested_id,
                    "nested_article": nested["number"],
                    "relationship": ref["relationship"]
                })
        
        return self.graph
    
    def _normalize_id(self, doc_name: str) -> str:
        if "này" in doc_name.lower():
            return "self"
        normalized = doc_name.lower()
        normalized = re.sub(r'[^\w\s]', '', normalized)
        return "_".join(normalized.split())[:30]
    
    def _extract_type(self, doc_name: str) -> str:
        types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
        for doc_type in types:
            if doc_type.lower() in doc_name.lower():
                return doc_type
        return "Unknown"


# =========================
# 5. UNIFIED PROCESSOR (main integration)
# =========================
class UnifiedDocumentProcessor:
    """
    UNIFIED PROCESSOR: 1 module, 1 pass, tối ưu 100%
    
    Flow:
    1. Read PDF
    2. Extract metadata
    3. Build tree
    4. Extract all references (simple + nested) - 1 pass only
    5. Build chunks with references
    6. Build reference graph
    7. Store everything in MongoDB
    """
    
    def __init__(self, db):
        self.db = db
        self.stats = {
            "total_documents": 0,
            "total_chunks": 0,
            "total_simple_refs": 0,
            "total_nested_refs": 0,
            "total_graph_nodes": 0,
            "total_graph_edges": 0
        }
    
    def process_document(self, file_path: str) -> Dict:
        """Process single document"""
        from read_pdf import read_pdf_full, extract_metadata, clean_text
        
        try:
            # 1. READ PDF
            full_text = read_pdf_full(file_path)
            
            # 2. EXTRACT METADATA
            metadata = extract_metadata(full_text)
            doc_id = metadata["doc_id"]
            doc_ref = f"[{metadata['document_type']} {metadata['document_number']}]"
            
            # 3. VERSION CONTROL
            content_hash = hashlib.md5(full_text.encode()).hexdigest()
            existing_doc = self.db["documents"].find_one({"_id": doc_id})
            
            if existing_doc and existing_doc.get("content_hash") == content_hash:
                return {"status": "skipped", "reason": "no_changes"}
            
            version = (existing_doc.get("current_version", 0) if existing_doc else 0) + 1
            version_id = f"{doc_id}_v{version}"
            
            # 4. BUILD TREE
            builder = DocumentTreeBuilder(full_text)
            tree = builder.build()
            
            # 5. EXTRACT ALL REFERENCES (1 pass only!)
            extractor = ReferenceExtractor(full_text)
            simple_refs, nested_refs = extractor.extract_all()
            
            # 6. BUILD CHUNKS WITH REFERENCES
            chunk_builder = ChunkBuilder(tree, metadata, doc_ref)
            chunks = chunk_builder.build(simple_refs, nested_refs)
            
            # 7. BUILD REFERENCE GRAPH
            graph_builder = ReferenceGraphBuilder(nested_refs)
            graph = graph_builder.build()
            
            # 8. STORE IN MONGODB
            self._store_to_db(
                doc_id, version, version_id, metadata, content_hash, 
                tree, chunks, simple_refs, nested_refs, graph
            )
            
            # 9. UPDATE STATS
            self.stats["total_documents"] += 1
            self.stats["total_chunks"] += len(chunks)
            self.stats["total_simple_refs"] += len(simple_refs)
            self.stats["total_nested_refs"] += len(nested_refs)
            self.stats["total_graph_nodes"] += len(graph["nodes"])
            self.stats["total_graph_edges"] += len(graph["edges"])
            
            return {
                "status": "success",
                "doc_id": doc_id,
                "version": version,
                "chunks": len(chunks),
                "simple_refs": len(simple_refs),
                "nested_refs": len(nested_refs)
            }
        
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _store_to_db(self, doc_id, version, version_id, metadata, content_hash,
                     tree, chunks, simple_refs, nested_refs, graph):
        """Store all data to MongoDB"""
        
        doc_col = self.db["documents"]
        chunk_col = self.db["chunks"]
        ref_col = self.db["references"]
        graph_col = self.db["reference_graphs"]
        mapping_col = self.db["article_mappings"]
        version_col = self.db["document_versions"]
        
        # 1. UPDATE DOCUMENT
        doc_col.update_one(
            {"_id": doc_id},
            {"$set": {
                "_id": doc_id,
                "metadata": metadata,
                "current_version": version,
                "content_hash": content_hash,
                "tree_stats": {
                    "total_articles": len(tree["articles"]),
                    "total_clauses": sum(len(a["clauses"]) for a in tree["articles"]),
                    "total_points": sum(
                        len(p) for a in tree["articles"]
                        for c in a["clauses"]
                        for p in c["points"]
                    )
                },
                "reference_stats": {
                    "simple_refs": len(simple_refs),
                    "nested_refs": len(nested_refs),
                    "graph_nodes": len(graph["nodes"]),
                    "graph_edges": len(graph["edges"])
                }
            }},
            upsert=True
        )
        
        # 2. CLOSE OLD VERSIONS
        version_col.update_many(
            {"doc_id": doc_id, "is_current": True},
            {"$set": {"is_current": False}}
        )
        
        # 3. CREATE NEW VERSION
        version_col.insert_one({
            "_id": version_id,
            "doc_id": doc_id,
            "version": version,
            "effective_date": metadata.get("issued_date"),
            "is_current": True,
            "created_at": datetime.utcnow()
        })
        
        # 4. DELETE OLD DATA
        chunk_col.delete_many({"doc_id": doc_id})
        ref_col.delete_many({"source_doc_id": doc_id})
        graph_col.delete_many({"source_doc_id": doc_id})
        mapping_col.delete_many({"source_doc_id": doc_id})
        
        # 5. INSERT CHUNKS + REFERENCES
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
                "effective_date": metadata.get("issued_date"),
                "references_count": len(chunk.get("references", []))
            })
            
            # References from this chunk
            for ref in chunk.get("references", []):
                ref_docs.append({
                    "_id": str(uuid.uuid4()),
                    "source_chunk_id": chunk_id,
                    "source_doc_id": doc_id,
                    "source_location": chunk["location"],
                    "source_level": chunk["level"],
                    "reference": ref,
                    "type": ref.get("type", "simple")
                })
        
        # 6. INSERT GRAPH
        if graph["edges"]:
            graph_col.insert_one({
                "_id": f"graph_{doc_id}",
                "source_doc_id": doc_id,
                "nodes": graph["nodes"],
                "edges": graph["edges"],
                "created_at": datetime.utcnow()
            })
        
        # 7. INSERT MAPPINGS
        for mapping_key, mappings in graph["article_mappings"].items():
            mapping_col.insert_one({
                "_id": mapping_key,
                "source_doc_id": doc_id,
                "mappings": mappings,
                "created_at": datetime.utcnow()
            })
        
        # Bulk insert
        if chunk_docs:
            chunk_col.insert_many(chunk_docs)
        
        if ref_docs:
            ref_col.insert_many(ref_docs)
    
    def process_batch(self, base_folder: str):
        """Process all PDFs in folder"""
        categories = [
            f for f in os.listdir(base_folder)
            if os.path.isdir(os.path.join(base_folder, f))
        ]
        
        for cat in categories:
            cat_path = os.path.join(base_folder, cat)
            files = [f for f in os.listdir(cat_path) if f.endswith(".pdf")]
            
            for file_name in tqdm(files, desc=f"Category: {cat}"):
                file_path = os.path.join(cat_path, file_name)
                result = self.process_document(file_path)
                
                if result["status"] == "error":
                    print(f"[ERROR] {file_name}: {result['error']}")
                else:
                    print(f"[{result['status'].upper()}] {file_name}")
        
        self._print_stats()
    
    def _print_stats(self):
        """Print processing statistics"""
        print("\n" + "=" * 60)
        print("PROCESSING STATISTICS")
        print("=" * 60)
        for key, value in self.stats.items():
            print(f"{key:.<40} {value:>15,}")
        print("=" * 60)


# =========================
# 6. MAIN
# =========================
if __name__ == "__main__":
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    DATA_RAW_PATH = os.path.join(BASE_DIR, "data", "raw")
    
    db = get_db()
    
    processor = UnifiedDocumentProcessor(db)
    processor.process_batch(DATA_RAW_PATH)