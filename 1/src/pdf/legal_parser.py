# src/pdf/legal_parser.py
"""
LEGAL DOCUMENT PARSER
    _add_article_chunks: COMBINE all points into one clause chunk -> có điều quá dài -> có thể vượt quá token limit??
    Vấn đề "\n" trong content: Giữ nguyên để preserve format, không thay thế bằng space??
    SimpleReferenceExtractor: Chỉ trích xuất reference tài liệu khác, không cố gắng phân biệt amendment vs refers_to, cũng không detect nested references (ví dụ "Điều 9 → Điều 7" quá phức tạp)

"""

import re
import uuid
from typing import List, Dict, Optional


# =============================================================================
# CLASS 1: DOCUMENT TREE BUILDER
# =============================================================================
class DocumentTreeBuilder:
    
    def __init__(self, text: str):
        """
        Initialize tree builder
        
        Args:
            text (str): Full text của tài liệu (sau khi clean_text)
        """
        self.text = text
        self.tree = {
            "preamble": "",
            "chapters": [],
            "articles": []
        }
    
    def build(self) -> Dict:

        # ===== NORMALIZE TEXT =====
        text = re.sub(r"\n+", "\n", self.text).strip() #

        # ===== CHECK FOR CHAPTERS =====
        chapter_pattern = r'(?:^|\n)\s*Chương\s+[IVXivx\d]+\b'
        has_chapters = bool(re.search(chapter_pattern, text))
        
        if has_chapters:
            self._parse_with_chapters(text)
        else:
            self._parse_without_chapters(text)

        return self.tree
    
    def _parse_with_chapters(self, text: str):
        """Split văn bản thành chương → điều → khoản → điểm"""
        
        # ===== SPLIT BY CHAPTERS =====
        chapter_blocks = re.split(
            r'(?=(?:^|\n)\s*Chương\s+[IVXivx\d]+\b)',
            text
        )
        
        # ===== PREAMBLE (before first chapter) =====
        self.tree["preamble"] = chapter_blocks[0].strip()
        
        # ===== PROCESS CHAPTERS =====
        for chapter_block in chapter_blocks[1:]:
            chapter_block = chapter_block.strip()
            if not chapter_block:
                continue
            
            # Extract chapter header: "Chương 1 NHỮNG QUY ĐỊNH CHUNG"
            chapter_match = re.search(
                r'Chương\s+([IVXivx\d]+)\s*\n+([^\n]+)',
                chapter_block,
                re.IGNORECASE
            )
            
            if not chapter_match:
                continue
            
            chapter_num_str = chapter_match.group(1)
            chapter_name = chapter_match.group(2).strip()
            
            # Convert Roman/Arabic to number
            try:
                chapter_num = self._convert_to_number(chapter_num_str)
            except:
                chapter_num = len(self.tree["chapters"]) + 1
            
            # Extract chapter body (after header)
            chapter_body = re.sub(
                r'^Chương\s+[IVXivx\d]+\s*\n+[^\n]+\n*',
                '',
                chapter_block,
                flags=re.IGNORECASE
            ).strip()
            
            chapter = {
                "number": chapter_num,
                "title": f"Chương {chapter_num_str}",
                "name": chapter_name,
                "articles": []
            }
            
            # ===== PARSE ARTICLES WITHIN CHAPTER =====
            article_blocks = re.split(
                r'(?=(?:^|\n|\s)Điều\s+\d+\.)',
                chapter_body
            )
            
            for article_block in article_blocks:
                article_block = article_block.strip()
                if not article_block:
                    continue
                
                article = self._parse_article(article_block)
                if article:
                    chapter["articles"].append(article)
            
            self.tree["chapters"].append(chapter)
    
    def _parse_without_chapters(self, text: str):
        """Parse document without Chương structure"""
        
        # ===== SPLIT BY ARTICLES =====
        article_blocks = re.split(
            r'(?=(?:^|\n|\s)Điều\s+\d+\.)',
            text
        )
        
        # ===== PREAMBLE =====
        self.tree["preamble"] = article_blocks[0].strip()
        
        # ===== PROCESS ARTICLES =====
        for article_block in article_blocks[1:]:
            article_block = article_block.strip()
            if not article_block:
                continue
            
            article = self._parse_article(article_block)
            if article:
                self.tree["articles"].append(article)
    
    def _parse_article(self, article_block: str) -> Optional[Dict]:
        """Parse single article block into articles dict with clauses and points"""
        
        # ===== ARTICLE HEADER =====
        article_match = re.search(
            r'Điều\s+(\d+)\.\s*([^\n]*)',
            article_block,
            re.IGNORECASE
        )
        
        if not article_match:
            return None
        
        article_num = int(article_match.group(1))
        article_title_suffix = article_match.group(2).strip()
        
        # ===== REMOVE ARTICLE HEADER =====
        body = re.sub(
            r'^Điều\s+\d+\.\s*',
            '',
            article_block,
            flags=re.DOTALL
        ).strip()
        
        article = {
            "number": article_num,
            "title": f"Điều {article_num}",
            "preamble": article_title_suffix if article_title_suffix and not re.match(r'^\d+[\.\)]', article_title_suffix) else "",
            "clauses": []
        }
        
        # ===== FIND ALL CLAUSES =====
        clause_pattern = r'(\d+)[\.\)]\s*([^\n]*(?:\n(?!^\d+[\.\)]).*)*)'
        clause_matches = list(re.finditer(clause_pattern, body, re.MULTILINE))
        if not clause_matches:
            article["clauses"].append({
                "number": 1,
                "content": body,
                "points": []
            })
            return article
        
        for clause_match in clause_matches:
            clause_num = int(clause_match.group(1))
            clause_content_raw = clause_match.group(2).strip()
            
            # ===== EXTRACT POINTS FROM CLAUSE =====
            points = []
            point_pattern = (
                r'^\s*([a-zđ])[\.\)]\s*(.*?)'
                r'(?=^\s*[a-zđ][\.\)]|\Z)'
            )
            point_matches = list(re.finditer( point_pattern, clause_content_raw, re.IGNORECASE | re.MULTILINE | re.DOTALL))
            
            # Remove points from clause content
            clause_content = clause_content_raw
            if point_matches:
                # Keep only content before first point
                first_point_start = point_matches[0].start()
                clause_content = clause_content_raw[:first_point_start].strip()
                
                # Extract all points
                for point_match in point_matches:
                    points.append({
                        "label": point_match.group(1).lower(),
                        "content": point_match.group(2).strip()
                    })
            
            clause = {
                "number": clause_num,
                "content": clause_content if clause_content else clause_content_raw,
                "points": points
            }
            
            article["clauses"].append(clause)
        
        return article
    
    def _convert_to_number(self, s: str) -> int:
        """Convert Roman or Arabic numerals to int"""
        s = s.strip()
        
        # Try Arabic first
        try:
            return int(s)
        except:
            pass
        
        # Try Roman
        roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        s = s.upper()
        result = 0
        prev = 0
        
        for char in reversed(s):
            val = roman_map.get(char, 0)
            if val < prev:
                result -= val
            else:
                result += val
            prev = val
        
        return result if result > 0 else 1


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
    
    def _normalize_text(self, text: str) -> str:
        """Chuẩn hóa: Gộp nhiều dòng thừa, nhưng GIỮ LẠI cấu trúc xuống dòng đơn giản (không gộp tất cả thành một dòng)"""
        text = re.sub(r'\n+', '\n ', text) # Giữ lại newlines nhưng thêm space sau newline để tránh dính chữ
        text = re.sub(r' +', ' ', text) # Gộp nhiều space thành 1
        return text.strip()
    
    def build(self) -> List[Dict]:
        """
        Build chunks from tree structure
        
        Handles both structures:
        - With chapters: preamble → chapters[].articles[]
        - Without chapters: preamble → articles[]
        
        Returns:
            List[Dict]: List of chunks
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
                "content": f"{self.doc_ref} - {self._normalize_text(preamble_text)}",
                "location": {"chapter": None, "article": None, "clause": None, "point": None},
                "level": "preamble"
            })
        
        # ===== 2. CHAPTERS (if exist) =====
        if self.tree.get("chapters"):
            for chapter in self.tree["chapters"]:
                chapter_num = chapter["number"]
                chapter_title = chapter["title"]
                chapter_name = chapter.get("name", "")
                
                # Chapter name chunk
                if chapter_name:
                    self.chunks.append({
                        "_id": str(uuid.uuid4()),
                        "dieu": None,
                        "khoan": None,
                        "diem": None,
                        "section_title": f"{chapter_title}: {chapter_name}",
                        "content": f"{self.doc_ref} - {chapter_title}: {self._normalize_text(chapter_name)}",
                        "location": {"chapter": chapter_num, "article": None, "clause": None, "point": None},
                        "level": "chapter"
                    })
                
                # Articles within chapter
                for article in chapter.get("articles", []):
                    self._add_article_chunks(article, chapter_num=chapter_num)
        
        # ===== 3. ARTICLES (if no chapters) =====
        else:
            for article in self.tree.get("articles", []):
                self._add_article_chunks(article, chapter_num=None)
        
        return self.chunks
    
    def _add_article_chunks(self, article: Dict, chapter_num: Optional[int] = None):
        """Add chunks for single article - COMBINE all points into one clause chunk"""
        
        article_num = article["number"]
        article_title = article["title"]
        
        # Article preamble
        if article.get("preamble", "").strip():
            self.chunks.append({
                "_id": str(uuid.uuid4()),
                "dieu": article_num,
                "khoan": None,
                "diem": None,
                "section_title": f"{article_title} - {article['preamble'][:60]}...",
                "content": f"{self.doc_ref} - {article_title}: {self._normalize_text(article['preamble'])}",
                "location": {"chapter": chapter_num, "article": article_num, "clause": None, "point": None},
                "level": "article"
            })
        
        # Clauses - COMBINE all points into single clause chunk
        for clause in article.get("clauses", []):
            clause_num = clause["number"]
            clause_content = clause.get("content", "")
            points = clause.get("points", [])
            
            # Build combined content: clause + all points together
            combined_parts = [clause_content]
            if points:
                for point in points:
                    combined_parts.append(f"{point['label']}) {point['content']}")
            
            full_text = " ".join(combined_parts)  # Use space instead of newline
            section_title = f"{article_title} - Khoản {clause_num}"
            
            self.chunks.append({
                "_id": str(uuid.uuid4()),
                "dieu": article_num,
                "khoan": clause_num,
                "diem": None,
                "section_title": section_title,
                "content": f"{self.doc_ref} - {section_title} {self._normalize_text(full_text)}",
                "location": {"chapter": chapter_num, "article": article_num, "clause": clause_num, "point": None},
                "level": "clause"
            })


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
