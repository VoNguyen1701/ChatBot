# src/pdf/legal_parser.py
"""
LEGAL DOCUMENT PARSER

Chuyên trách: Xây dựng cấu trúc + chunking cho tài liệu pháp lý Vietnamese

SCOPE:
✅ Build hierarchical tree: Điều → Khoản → Điểm (Article > Clause > Point)
✅ Create chunks cho embedding/retrieval
⏸️ Advanced extraction (legal_basis, amendments, timeline) - xem advanced_extraction.py

USAGE:
    from legal_parser import DocumentTreeBuilder, ChunkBuilder
    
    builder = DocumentTreeBuilder(text)
    tree = builder.build()
    
    chunks = ChunkBuilder(tree, metadata).build()
"""

import re
import uuid
from typing import List, Dict, Optional


# =============================================================================
# CLASS 1: DOCUMENT TREE BUILDER
# =============================================================================
class DocumentTreeBuilder:
    """
    Xây dựng cây cấu trúc phân cấp của tài liệu pháp lý Vietnamese.
    
    HIERARCHY:
    ├─ preamble          (Mở đầu, CĂN CỨ, QUYẾT ĐỊNH, etc)
    └─ articles[]
       ├─ number        (1, 2, 3, ...)
       ├─ title         ("Điều 1")
       ├─ preamble      (Mô tả Điều)
       └─ clauses[]     (Khoản)
          ├─ number     (1, 2, 3, ...)
          ├─ content    (Nội dung Khoản)
          └─ points[]   (Điểm)
             ├─ label   ("a", "b", "c", ...)
             └─ content (Nội dung Điểm)
    """
    
    def __init__(self, text: str):
        """
        Initialize tree builder
        
        Args:
            text (str): Full text của tài liệu (sau khi clean_text)
        """
        self.text = text
        self.lines = text.split('\n')
        self.tree = {
            "preamble": "",
            "articles": []
        }
    
    def build(self) -> Dict:

        # ===== NORMALIZE TEXT =====
        text = re.sub(r"\n+", "\n", self.text).strip()

        # ===== SPLIT ARTICLES =====
        article_blocks = re.split(
            r'(?=(?:^|\n|\s)Điều\s+\d+\.)',
            text
        )

        # ===== PREAMBLE =====
        self.tree["preamble"] = article_blocks[0].strip()

        # ===== PROCESS ARTICLES =====
        for block in article_blocks[1:]:

            block = block.strip()

            if not block:
                continue

            # ===== ARTICLE HEADER =====
            article_match = re.search(
                r'Điều\s+(\d+)\.\s*(.*)',
                block
            )

            if not article_match:
                continue

            article_num = int(article_match.group(1))

            # ===== REMOVE ARTICLE HEADER =====
            body = re.sub(
                r'^Điều\s+\d+\.\s*',
                '',
                block
            ).strip()

            article = {
                "number": article_num,
                "title": f"Điều {article_num}",
                "preamble": "",
                "clauses": []
            }

            # ===== SPLIT CLAUSES DIRECTLY FROM BODY =====
            clause_parts = re.split(
                r'(?=(?:^|\s)\d{1,2}[\.\)])',
                body
            )

            for part in clause_parts:

                part = part.strip()

                if not part:
                    continue

                clause_match = re.match(
                    r'^(\d+)[\.\)]\s*(.*)',
                    part,
                    re.DOTALL
                )

                if clause_match:

                    clause_num = int(clause_match.group(1))
                    clause_content = clause_match.group(2).strip()

                    clause = {
                        "number": clause_num,
                        "content": clause_content,
                        "points": []
                    }

                    # ===== SPLIT POINTS =====
                    point_parts = re.split(
                        r'(?=(?:^|\s)[a-z][\.\)])',
                        clause_content
                    )

                    cleaned_content = []

                    for pp in point_parts:

                        pp = pp.strip()

                        if not pp:
                            continue

                        point_match = re.match(
                            r'^([a-z])[\.\)]\s*(.*)',
                            pp,
                            re.IGNORECASE | re.DOTALL
                        )

                        if point_match:

                            clause["points"].append({
                                "label": point_match.group(1),
                                "content": point_match.group(2).strip()
                            })

                        else:
                            cleaned_content.append(pp)

                    clause["content"] = " ".join(cleaned_content)

                    article["clauses"].append(clause)

                else:
                    article["preamble"] += " " + part
            
            # ===== SAVE ARTICLE =====
            self.tree["articles"].append(article)

        return self.tree


# =============================================================================
# CLASS 2: CHUNK BUILDER (SIMPLIFIED)
# =============================================================================
class ChunkBuilder:
    
    def __init__(self, tree: Dict, metadata: Dict, doc_ref: str = None):
        """
        Initialize chunk builder
        
        Args:
            tree (Dict): Output từ DocumentTreeBuilder.build()
            metadata (Dict): Document metadata (từ extract_metadata)
            doc_ref (str): Document reference string, e.g. "[TT 21/2026]"
        """
        self.tree = tree
        self.metadata = metadata
        self.doc_ref = doc_ref or f"[{metadata.get('document_type', 'DOC')} {metadata.get('document_number', 'UNKNOWN')}]"
        self.chunks = []
        self.max_size = 800  # characters per chunk
    
    def build(self) -> List[Dict]:
        """
        Build chunks from tree structure
        
        Returns:
            List[Dict]: List of chunks (xem OUTPUT trên)
        """
        
        # ===== 1. PREAMBLE CHUNK =====
        if self.tree["preamble"].strip():
            preamble_text = self.tree["preamble"]
            self.chunks.append({
                "_id": str(uuid.uuid4()),
                "dieu": None,
                "khoan": None,
                "diem": None,
                "section_title": "Mở đầu",
                "content": f"{self.doc_ref} - {preamble_text[:self.max_size]}",
                "location": {"article": None, "clause": None, "point": None},
                "level": "preamble"
            })
        
        # ===== 2. ARTICLE + CLAUSE + POINT CHUNKS =====
        for article in self.tree["articles"]:
            article_num = article["number"]
            article_title = article["title"]
            
            # Article preamble
            if article["preamble"].strip():
                self.chunks.append({
                    "_id": str(uuid.uuid4()),
                    "dieu": article_num,
                    "khoan": None,
                    "diem": None,
                    "section_title": f"{article_title} - {article['preamble'][:60]}...",
                    "content": f"{self.doc_ref} - {article_title}: {article['preamble'][:self.max_size]}",
                    "location": {"article": article_num, "clause": None, "point": None},
                    "level": "article"
                })
            
            # Clauses
            for clause in article["clauses"]:
                clause_num = clause["number"]
                clause_content = clause["content"]
                
                # If has points → create point-level chunks
                if clause["points"]:
                    for point in clause["points"]:
                        point_label = point["label"]
                        point_content = point["content"]
                        
                        section_title = f"{article_title} - Khoản {clause_num}{point_label}"
                        
                        # Combine clause + point content
                        full_text = f"{clause_content}\n{point_content}"
                        
                        self.chunks.append({
                            "_id": str(uuid.uuid4()),
                            "dieu": article_num,
                            "khoan": clause_num,
                            "diem": point_label,
                            "section_title": section_title,
                            "content": f"{self.doc_ref} - {section_title}\n{full_text[:self.max_size]}",
                            "location": {"article": article_num, "clause": clause_num, "point": point_label},
                            "level": "point"
                        })
                else:
                    # No points → clause-level chunk
                    section_title = f"{article_title} - Khoản {clause_num}"
                    
                    self.chunks.append({
                        "_id": str(uuid.uuid4()),
                        "dieu": article_num,
                        "khoan": clause_num,
                        "diem": None,
                        "section_title": section_title,
                        "content": f"{self.doc_ref} - {section_title}\n{clause_content[:self.max_size]}",
                        "location": {"article": article_num, "clause": clause_num, "point": None},
                        "level": "clause"
                    })
        
        return self.chunks


# =============================================================================
# SIMPLE REFERENCE EXTRACTOR (không phức tạp)
# =============================================================================
class SimpleReferenceExtractor:
    """
    Trích xuất references đơn giản (KHÔNG nested)
    
    Chỉ detect:
    - "Luật 10/2014"
    - "Nghị định 15/2023"
    - "Thông tư 20/2025"
    
    Không detect:
    - "Điều 9 → Điều 7" (quá phức tạp)
    - Amendment vs refers_to distinction (quá nâng cao)
    
    Use case:
    - Tìm các reference tài liệu khác
    - Xây dựng knowledge graph cơ bản
    """
    
    def __init__(self, text: str):
        self.text = text
        self.doc_types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
    
    def extract(self) -> List[Dict]:
        """
        Extract simple document references
        
        Returns:
            List[Dict]: List of references
            [
                {
                    "doc_type": "Luật",
                    "doc_number": "10/2014",
                    "context": "...(50 chars before/after)..."
                },
                ...
            ]
        """
        references = []
        
        for doc_type in self.doc_types:
            # Regex: "Luật 10/2014" hoặc "Luật số 10/2014"
            pattern = rf"(?:theo\s+)?{doc_type}\s+(?:số\s+)?(\d+[\w\/\-\.]*(?:/\d{{4}})?)"
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            
            for match in matches:
                ref_num = match.group(1)
                
                # Get context (50 chars before/after)
                start = max(0, match.start() - 50)
                end = min(len(self.text), match.end() + 50)
                context = self.text[start:end].strip()
                
                references.append({
                    "doc_type": doc_type,
                    "doc_number": ref_num,
                    "context": context
                })
        
        return references


# =============================================================================
# USAGE EXAMPLE
# =============================================================================
if __name__ == "__main__":
    from pdf.read_pdf import read_pdf_full, extract_metadata, clean_text
    
    # Read
    file_path = "data/raw/law/HC1.pdf"
    full_text = read_pdf_full(file_path)
    
    # Extract metadata
    metadata = extract_metadata(full_text)
    print(f"📄 {metadata['document_type']} {metadata['document_number']}")
    
    # Build tree
    builder = DocumentTreeBuilder(full_text)
    tree = builder.build()
    print(f"📚 Articles: {len(tree['articles'])}")
    
    # Create chunks
    chunks = ChunkBuilder(tree, metadata).build()
    print(f"📦 Chunks: {len(chunks)}")
    
    # Extract simple references
    refs = SimpleReferenceExtractor(full_text).extract()
    print(f"🔗 References: {len(refs)}")
