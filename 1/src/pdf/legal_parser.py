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
# CLASS 3: REFERENCE RELATIONSHIP EXTRACTOR (Enhanced)
# =============================================================================
class ReferenceRelationshipExtractor:
    """
    Enhanced reference extractor với hỗ trợ 3 loại tham chiếu:
    
    1. RELATIVE (Tham chiếu tương đối - cùng Điều)
       - "Khoản 3 Điều này"
       - "Khoản 1, 2 Điều này"
       - Tham chiếu trong cùng một điều
    
    2. ABSOLUTE (Tham chiếu tuyệt đối - cùng văn bản)
       - "Khoản 1 Điều 7"
       - "Điều 3"
       - Tham chiếu trong cùng tài liệu nhưng khác điều
    
    3. CROSS_REFERENCE (Tham chiếu chéo - văn bản khác)
       - "Điều 3 của Luật Thuế thu nhập cá nhân"
       - "Điều 7 Nghị định số 126/2020/NĐ-CP"
       - Tham chiếu tới tài liệu pháp luật khác
    """
    
    RELATIONSHIP_TYPES = {
        "RELATIVE": "Tham chiếu tương đối (cùng Điều)",
        "ABSOLUTE": "Tham chiếu tuyệt đối (cùng văn bản)",
        "CROSS_REFERENCE": "Tham chiếu chéo (văn bản khác)"
    }
    
    def __init__(self, text: str, current_article: Optional[int] = None):
        """
        Initialize reference extractor
        
        Args:
            text (str): Full text để extract references
            current_article (int): Current article number (dùng để detect relative refs)
        """
        self.text = text
        self.current_article = current_article
        self.doc_types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
    
    def extract_all(self) -> Dict[str, List[Dict]]:
        """
        Extract all reference types
        
        Returns:
            Dict with keys: relative, absolute, cross_reference
        """
        return {
            "relative": self._extract_relative_references(),
            "absolute": self._extract_absolute_references(),
            "cross_reference": self._extract_cross_references(),
            "all": self._extract_all_merged()
        }
    
    def _extract_relative_references(self) -> List[Dict]:
        """
        Extract RELATIVE references - "Khoản X Điều này"
        
        Patterns:
        - Khoản 3 Điều này
        - Khoản 1, 2 Điều này
        - Khoản 1 và 3 Điều này
        """
        relative_refs = []
        
        # Flexible pattern: match Khoản followed by numbers, then optional text, then Điều này
        # This handles: "Khoản 3 Điều này", "theo Khoản 3 Điều này", etc.
        pattern = r'[Kk]hoan\s+([\d,\s&và]+)\s+[Dd]ieu\s+nay'
        
        # Also try with Vietnamese characters directly
        for attempt_pattern in [

            # Khoản 2 Điều này
            r'khoản\s+(\d+)\s+điều\s+này',

            # Khoản 1, khoản 2 Điều này
            r'((?:khoản\s+\d+\s*,?\s*)+)điều\s+này',

            # Khoản 1 và khoản 2 Điều này
            r'((?:khoản\s+\d+\s*(?:và\s+)?)+)điều\s+này',

            # Điểm b khoản 2 Điều này
            r'(?:điểm\s+[a-z]\s+)?khoản\s+(\d+)\s+điều\s+này',

            # Các điểm a,b,c khoản 1 và khoản 2 Điều này
            r'(?:các\s+điểm\s+[a-z,\s]+)?((?:khoản\s+\d+\s*(?:,|và)?\s*)+)điều\s+này',
        ]:

            matches = re.finditer(
                attempt_pattern,
                self.text,
                re.IGNORECASE | re.UNICODE
            )
            
            for match in matches:
                clauses_str = match.group(1).strip()
                
                # Parse clause numbers (handle "1, 2" or "1 và 2" or "1, 2, 3")
                clause_nums = sorted(
                list(
                    set(
                        int(x)
                        for x in re.findall(r'\d+', clauses_str)
                    )
                )
            )
                
                start = max(0, match.start() - 60)
                end = min(len(self.text), match.end() + 60)
                context = self.text[start:end].strip()
                
                # Check if already added
                if not any(ref.get("text") == match.group(0) for ref in relative_refs):
                    relative_refs.append({
                        "type": "RELATIVE",
                        "description": self.RELATIONSHIP_TYPES["RELATIVE"],
                        "clause_numbers": clause_nums,
                        "article_number": self.current_article,
                        "text": match.group(0),
                        "context": context,
                        "location": {"article": self.current_article, "clauses": clause_nums}
                    })
        
        return relative_refs
    
    def _extract_absolute_references(self) -> List[Dict]:
        """
        Extract ABSOLUTE references - "Khoản X Điều Y" hoặc "Điều Y"
        
        Patterns:
        - Khoản 1 Điều 7
        - Khoản 1, 2 Điều 5
        - Điều 7
        - Điều 1 đến Điều 5
        """
        absolute_refs = []
        seen_refs = set()  # Track to avoid duplicates
        
        # Pattern 1: "Khoản X Điều Y" - explicit clause + article
        patterns_abs1 = [
            r'[Kk]ho[àa]n\s+([\d,\s&và]+)\s+[Đđ]i[ều]u\s+(\d+)',
            r'Khoản\s+([\d,\s&và]+)\s+Điều\s+(\d+)',
        ]
        
        for pattern in patterns_abs1:
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            
            for match in matches:
                clauses_str = match.group(1).strip()
                article_num = int(match.group(2))
                
                # Skip if it's the current article (it's relative, not absolute)
                if article_num == self.current_article:
                    continue
                
                ref_key = (article_num, tuple(self._parse_numbers(clauses_str)))
                if ref_key in seen_refs:
                    continue
                seen_refs.add(ref_key)
                
                clause_nums = self._parse_numbers(clauses_str)
                start = max(0, match.start() - 60)
                end = min(len(self.text), match.end() + 60)
                context = self.text[start:end].strip()
                
                absolute_refs.append({
                    "type": "ABSOLUTE",
                    "description": self.RELATIONSHIP_TYPES["ABSOLUTE"],
                    "clause_numbers": clause_nums,
                    "article_number": article_num,
                    "text": match.group(0),
                    "context": context,
                    "location": {"article": article_num, "clauses": clause_nums}
                })
        
        # Pattern 2: "Điều X" - article only
        patterns_abs2 = [
            r'[Đđ]i[ều]u\s+(\d+)(?:\s+(?:đến|tới|đ[ến])\s+[Đđ]i[ều]u\s+(\d+))?',
            r'Điều\s+(\d+)(?:\s+(?:đến|tới|đến)\s+Điều\s+(\d+))?',
        ]
        
        for pattern in patterns_abs2:
            matches = re.finditer(pattern, self.text, re.IGNORECASE)
            
            for match in matches:
                article_start = int(match.group(1))
                article_end = int(match.group(2)) if match.group(2) else article_start
                
                # Skip if it's the current article only
                if article_start == self.current_article and not match.group(2):
                    continue
                
                ref_key = (article_start, article_end)
                if ref_key in seen_refs:
                    continue
                seen_refs.add(ref_key)
                
                start = max(0, match.start() - 60)
                end = min(len(self.text), match.end() + 60)
                context = self.text[start:end].strip()
                
                absolute_refs.append({
                    "type": "ABSOLUTE",
                    "description": self.RELATIONSHIP_TYPES["ABSOLUTE"],
                    "clause_numbers": None,
                    "article_number": article_start,
                    "article_range": (article_start, article_end) if article_end != article_start else None,
                    "text": match.group(0),
                    "context": context,
                    "location": {"article": article_start, "article_to": article_end if article_end != article_start else None}
                })
        
        return absolute_refs
    
    def _extract_cross_references(self) -> List[Dict]:
        """
        Extract CROSS-REFERENCES - tham chiếu chéo đến văn bản khác
        
        Patterns:
        - "Điều 3 của Luật Thuế thu nhập cá nhân"
        - "Điều 7 Nghị định số 126/2020/NĐ-CP"
        - "Luật số 10/2014"
        - "Theo Nghị định 126/2020/NĐ-CP"
        """
        cross_refs = []
        
        # Pattern 1: "Điều X của/trong {doc_type} {doc_number}"
        for doc_type in self.doc_types:
            pattern = (
                rf'[Đđ]i[ều]u\s+(\d+)\s+(?:của|trong)\s+{doc_type}\s+'
                rf'(?:số\s+)?(\d+[\w\/\-]*(?:/\d{{4}})?)'
            )
            matches = re.finditer(pattern, self.text, re.IGNORECASE | re.UNICODE)
            
            for match in matches:
                article_num = int(match.group(1))
                doc_number = match.group(2).rstrip('.,;:')  # Remove trailing punctuation
                
                start = max(0, match.start() - 60)
                end = min(len(self.text), match.end() + 60)
                context = self.text[start:end].strip()
                
                cross_refs.append({
                    "type": "CROSS_REFERENCE",
                    "description": self.RELATIONSHIP_TYPES["CROSS_REFERENCE"],
                    "doc_type": doc_type,
                    "doc_number": doc_number,
                    "article_number": article_num,
                    "text": match.group(0),
                    "context": context,
                    "location": {"doc_type": doc_type, "doc_number": doc_number, "article": article_num}
                })
        
        # Pattern 2: "{doc_type} số {doc_number}" or similar
        pattern_doc = rf"(?:theo\s+)?({'|'.join(self.doc_types)})\s+(?:số\s+)?(\d+[\w\/\-]*(?:/\d{{4}})?)"
        matches_doc = re.finditer(pattern_doc, self.text, re.IGNORECASE | re.UNICODE)
        
        for match in matches_doc:
            doc_type = match.group(1)
            doc_number = match.group(2).rstrip('.,;:')  # Remove trailing punctuation
            
            # Check if this is already captured with article number
            if any(ref.get("doc_number") == doc_number for ref in cross_refs):
                continue
            
            start = max(0, match.start() - 60)
            end = min(len(self.text), match.end() + 60)
            context = self.text[start:end].strip()
            
            cross_refs.append({
                "type": "CROSS_REFERENCE",
                "description": self.RELATIONSHIP_TYPES["CROSS_REFERENCE"],
                "doc_type": doc_type,
                "doc_number": doc_number,
                "article_number": None,
                "text": match.group(0),
                "context": context,
                "location": {"doc_type": doc_type, "doc_number": doc_number}
            })
        
        return cross_refs
    
    def _parse_numbers(self, text: str) -> List[int]:
        """
        Parse clause/article numbers from text like "1, 2, 3" or "1 và 2" or "1&2"
        
        Args:
            text (str): Text containing numbers
            
        Returns:
            List[int]: Extracted numbers
        """
        # Remove common separators and split
        text = re.sub(r'(?:và|\s+|,|&)+', ' ', text)
        numbers = []
        for word in text.split():
            try:
                numbers.append(int(word.strip()))
            except:
                pass
        return numbers
    
    def _extract_all_merged(self) -> List[Dict]:
        """Merge all references into single list"""
        all_refs = (
            self._extract_relative_references() +
            self._extract_absolute_references() +
            self._extract_cross_references()
        )
        return all_refs


# =============================================================================
# CLASS 4: SIMPLE REFERENCE EXTRACTOR (Legacy - kept for backward compatibility)
# =============================================================================
class SimpleReferenceExtractor:
    """
    Legacy reference extractor - extract simple document references only
    Use ReferenceRelationshipExtractor for comprehensive relationship detection
    """
    
    def __init__(self, text: str):
        self.text = text
        self.doc_types = ["Luật", "Nghị định", "Thông tư", "Quyết định", "Nghị quyết"]
    
    def extract(self) -> List[Dict]:
        """
        Extract simple document references (backward compatibility)
        
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
                    "type": "CROSS_REFERENCE",
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
    
    # Extract references - NEW: Comprehensive relationship extraction
    print("\n" + "="*70)
    print("🔗 REFERENCE RELATIONSHIP EXTRACTION")
    print("="*70)
    
    # Example 1: Extract relationships for a specific article
    extractor = ReferenceRelationshipExtractor(full_text, current_article=7)
    all_relationships = extractor.extract_all()
    
    print(f"\n📍 Relative References (cùng Điều): {len(all_relationships['relative'])}")
    for ref in all_relationships['relative'][:3]:
        print(f"   - {ref['text']} → Khoản {ref['clause_numbers']}")
    
    print(f"\n📍 Absolute References (cùng văn bản): {len(all_relationships['absolute'])}")
    for ref in all_relationships['absolute'][:3]:
        print(f"   - {ref['text']} → Điều {ref['article_number']}")
    
    print(f"\n📍 Cross-References (văn bản khác): {len(all_relationships['cross_reference'])}")
    for ref in all_relationships['cross_reference'][:3]:
        print(f"   - {ref['text']} → {ref['doc_type']} số {ref['doc_number']}")
    
    # Example 2: Legacy simple extraction (backward compatibility)
    print("\n" + "="*70)
    simple_refs = SimpleReferenceExtractor(full_text).extract()
    print(f"🔗 Simple References (legacy): {len(simple_refs)}")