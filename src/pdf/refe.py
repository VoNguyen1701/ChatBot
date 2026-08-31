# src/pdf/reference_resolver.py
"""
INTERNAL REFERENCE RESOLVER

Mục đích: Khi LLM nhận một chunk có chứa tham chiếu nội bộ như:
  - "Khoản 3 Điều này"          → tìm chunk cùng Điều, Khoản 3
  - "Điều 5 Luật này"           → tìm chunk Điều 5, cùng doc_id
  - "Điều 3 của Luật TNCN"      → tìm doc khớp tên → tìm chunk Điều 3
  - "Khoản 1, 2 Điều 7"         → tìm nhiều khoản
  - "các điểm a, b khoản 3..."  → tìm chunk khoản 3 (điểm được gộp vào chunk khoản)

USAGE:
    from reference_resolver import ReferenceResolver

    resolver = ReferenceResolver(db)

    # Giải tham chiếu từ một chunk
    results = resolver.resolve_from_chunk(chunk_doc)

    # Giải tham chiếu từ text tự do (LLM gọi sau khi nhận chunk)
    results = resolver.resolve(
        text="Theo khoản 3 Điều này, ...",
        source_chunk=chunk_doc
    )
"""

import re
from typing import List, Dict, Optional, Tuple


# =============================================================================
# PATTERNS
# =============================================================================

# Tên văn bản xuất hiện trong tham chiếu
DOC_NAME_ALIASES = {
    "luật thuế thu nhập cá nhân": ["TNCN", "thuế thu nhập cá nhân", "Luật TNCN"],
    "luật doanh nghiệp":          ["Luật DN"],
    "luật đầu tư":                ["Luật ĐT"],
    "bộ luật dân sự":             ["BLDS"],
    "bộ luật hình sự":            ["BLHS"],
    "luật hành chính":            ["hành chính"],
}

# Pattern nhận diện tham chiếu nội bộ (trong cùng tài liệu)
INTERNAL_PATTERNS = [
    # "Khoản 3 Điều này" / "Khoản 2, 3 Điều này"
    (
        "khoan_dieu_nay",
        re.compile(
            r"[Kk]ho[aả]n\s+([\d,\s]+)\s+[Đđ]i[eề]u\s+n[àa]y",
            re.IGNORECASE
        )
    ),
    # "Điều này"
    (
        "dieu_nay",
        re.compile(r"\b[Đđ]i[eề]u\s+n[àa]y\b", re.IGNORECASE)
    ),
    # "Khoản này"
    (
        "khoan_nay",
        re.compile(r"\b[Kk]ho[aả]n\s+n[àa]y\b", re.IGNORECASE)
    ),
    # "Điều 5 Luật này" / "Điều 5, 6 Luật này"
    (
        "dieu_luat_nay",
        re.compile(
            r"[Đđ]i[eề]u\s+([\d,\s]+)\s+(?:[Ll]u[aậ]t|[Nn]gh[ịi]\s+[Đđ][ịi]nh|[Tt]h[ôo]ng\s+t[ưư])\s+n[àa]y",
            re.IGNORECASE
        )
    ),
    # "Khoản 2 Điều 7" / "Khoản 1, 2 Điều 7"
    (
        "khoan_dieu_so",
        re.compile(
            r"[Kk]ho[aả]n\s+([\d,\s]+)\s+[Đđ]i[eề]u\s+(\d+)",
            re.IGNORECASE
        )
    ),
    # "Điều 7" (standalone, không có "Luật/Nghị định ... số ...")
    (
        "dieu_so",
        re.compile(
            r"(?<![/\d])\b[Đđ]i[eề]u\s+(\d+)(?!\s*(?:của\s+)?(?:[Ll]u[aậ]t|[Nn]gh[ịi]\s+[Đđ][ịi]nh|[Tt]h[ôo]ng\s+t[ưư])\s+(?:s[ốo]\s+)?[\d/]+)",
            re.IGNORECASE
        )
    ),
    # "điểm a, b khoản 3 Điều này"
    (
        "diem_khoan_dieu_nay",
        re.compile(
            r"[Đđ]i[eể]m\s+([a-zđ,\s]+)\s+[Kk]ho[aả]n\s+([\d,\s]+)\s+[Đđ]i[eề]u\s+n[àa]y",
            re.IGNORECASE
        )
    ),
    # "điểm a, b khoản 3 Điều 7"
    (
        "diem_khoan_dieu_so",
        re.compile(
            r"[Đđ]i[eể]m\s+([a-zđ,\s]+)\s+[Kk]ho[aả]n\s+([\d,\s]+)\s+[Đđ]i[eề]u\s+(\d+)",
            re.IGNORECASE
        )
    ),
]

# Pattern tham chiếu NGOẠI (sang văn bản khác theo số hiệu)
EXTERNAL_PATTERN = re.compile(
    r"[Đđ]i[eề]u\s+(\d+)\s+(?:của\s+)?([Ll]u[aậ]t|[Nn]gh[ịi]\s+[Đđ][ịi]nh|[Tt]h[ôo]ng\s+t[ưư]|[Qq]uy[eế]t\s+[Đđ][ịi]nh)\s+(?:s[ốo]\s+)?([\d/\w\-]+)",
    re.IGNORECASE
)


# =============================================================================
# HELPERS
# =============================================================================

def _parse_number_list(raw: str) -> List[int]:
    """Parse "1, 2, 3" hoặc "1" thành [1, 2, 3]"""
    nums = []
    for part in re.split(r"[,\s]+", raw.strip()):
        part = part.strip()
        if part.isdigit():
            nums.append(int(part))
    return nums


def _normalize_doc_number(raw: str) -> str:
    """Chuẩn hóa số văn bản: bỏ khoảng trắng, lowercase để so sánh"""
    return raw.strip().lower().replace(" ", "")


# =============================================================================
# MAIN CLASS
# =============================================================================

class ReferenceResolver:
    """
    Giải tham chiếu nội bộ và ngoại trong văn bản pháp luật.

    Flow:
      1. Phát hiện pattern tham chiếu trong content của chunk
      2. Phân loại: nội bộ (same doc) hay ngoại (doc khác)
      3. Query MongoDB chunks collection để lấy chunk(s) phù hợp
      4. Trả về danh sách chunk đã resolve, kèm loại tham chiếu

    Args:
        db: MongoDB database connection
    """

    def __init__(self, db):
        self.db        = db
        self.chunks    = db["chunks"]
        self.documents = db["documents"]
        self.chunk_refs = db["chunk_references"]

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def resolve(
        self,
        text: str,
        source_chunk: Dict
    ) -> List[Dict]:
        """
        Phân tích `text` và tìm các chunk liên quan.

        Args:
            text (str): Nội dung cần phân tích (thường là chunk["content"])
            source_chunk (Dict): Chunk gốc (cần có doc_id, hierarchy)

        Returns:
            List[Dict]: Danh sách kết quả, mỗi item:
            {
                "ref_type":    "internal" | "external",
                "pattern":     tên pattern khớp,
                "matched_text": chuỗi khớp trong văn bản,
                "query":       dict mô tả query đã dùng,
                "chunks":      [chunk_doc, ...]   ← các chunk tìm được
            }
        """
        results = []

        doc_id    = source_chunk.get("doc_id")
        hierarchy = source_chunk.get("hierarchy", {})
        src_dieu  = hierarchy.get("dieu")
        src_khoan = hierarchy.get("khoan")

        # ── 1. EXTERNAL references (cross-document) ──────────────────────────
        for ext_match in EXTERNAL_PATTERN.finditer(text):
            dieu_num   = int(ext_match.group(1))
            doc_type   = ext_match.group(2).strip()
            doc_number = ext_match.group(3).strip()

            target_doc_id = self._find_doc_id(doc_type, doc_number)

            query = {
                "doc_id": target_doc_id,
                "hierarchy.dieu": dieu_num
            }
            found = self._query_chunks(query, target_doc_id)

            results.append({
                "ref_type":     "external",
                "pattern":      "dieu_doc_ngoai",
                "matched_text": ext_match.group(0),
                "query": {
                    "doc_type":   doc_type,
                    "doc_number": doc_number,
                    "dieu":       dieu_num,
                    "resolved_doc_id": target_doc_id
                },
                "chunks": found
            })

        # ── 2. INTERNAL references ────────────────────────────────────────────
        for pattern_name, pattern in INTERNAL_PATTERNS:
            for m in pattern.finditer(text):

                # Bỏ qua nếu đoạn này đã được EXTERNAL_PATTERN bắt
                if self._overlaps_external(text, m.start(), m.end()):
                    continue

                ref_result = self._resolve_internal(
                    pattern_name=pattern_name,
                    match=m,
                    doc_id=doc_id,
                    src_dieu=src_dieu,
                    src_khoan=src_khoan,
                )
                if ref_result:
                    results.append(ref_result)

        return results

    def resolve_by_graph(self, source_chunk_id: str) -> List[Dict]:
        """
        Resolve tham chiếu bằng cách đọc chunk_references đã lưu lúc ingest.
        O(1) thay vì O(text) — không parse lại regex.

        Args:
            source_chunk_id: chunk_id của chunk đang được LLM xử lý

        Returns:
            List[Dict]: mỗi item gồm edge metadata + chunk content đã fetch
            {
                "ref_type":        "RELATIVE" | "ABSOLUTE" | "CROSS_REFERENCE",
                "text":            chuỗi tham chiếu gốc,
                "context":         đoạn văn xung quanh,
                "resolved":        True/False,
                "target_chunk_id": str | None,
                "chunk":           chunk_doc | None   ← nội dung thực
            }
        """
        edges = list(self.chunk_refs.find(
            {"source_chunk_id": source_chunk_id},
            {"_id": 0}
        ))

        if not edges:
            return []

        # ── Fetch tất cả internal chunks một lần (bulk) ──────────────────────
        internal_ids = [
            e["target_chunk_id"]
            for e in edges
            if e.get("target_chunk_id")
        ]

        chunk_map: Dict[str, Dict] = {}
        if internal_ids:
            for c in self.chunks.find(
                {"chunk_id": {"$in": internal_ids}},
                {"_id": 0, "chunk_id": 1, "section_title": 1,
                 "content": 1, "hierarchy": 1, "doc_id": 1}
            ):
                chunk_map[c["chunk_id"]] = c

        # ── Resolve CROSS_REFERENCE chunks ───────────────────────────────────
        results = []
        for edge in edges:
            target_cid = edge.get("target_chunk_id")

            if edge["ref_type"] == "CROSS_REFERENCE" and not target_cid:
                # Thử tìm doc trong documents collection rồi fetch chunk
                target_doc_id = self._find_doc_id(
                    edge.get("target_doc_type", ""),
                    edge.get("target_doc_number", "")
                )
                fetched_chunks = []
                if target_doc_id and edge.get("target_dieu"):
                    fetched_chunks = self._query_chunks(
                        {"doc_id": target_doc_id,
                         "hierarchy.dieu": edge["target_dieu"]},
                        target_doc_id
                    )
                results.append({
                    "ref_type":        edge["ref_type"],
                    "text":            edge.get("text", ""),
                    "context":         edge.get("context", ""),
                    "resolved":        len(fetched_chunks) > 0,
                    "target_chunk_id": None,
                    "chunks":          fetched_chunks
                })
            else:
                chunk = chunk_map.get(target_cid) if target_cid else None
                results.append({
                    "ref_type":        edge["ref_type"],
                    "text":            edge.get("text", ""),
                    "context":         edge.get("context", ""),
                    "resolved":        chunk is not None,
                    "target_chunk_id": target_cid,
                    "chunks":          [chunk] if chunk else []
                })

        return results

    def resolve_from_chunk(self, chunk_doc: Dict) -> List[Dict]:
        """
        Graph-first: đọc chunk_references đã index lúc ingest (O(1)).
        Fallback về regex scan nếu chưa có data (doc chưa re-ingest sau khi
        thêm ReferenceRelationshipExtractor).
        """
        results = self.resolve_by_graph(chunk_doc.get("chunk_id", ""))

        if not results:
            # Fallback: parse lại text — dùng khi chunk_references chưa có
            results = self.resolve(
                text=chunk_doc.get("content", ""),
                source_chunk=chunk_doc
            )

        return results

    # -------------------------------------------------------------------------
    # INTERNAL REFERENCE HANDLERS
    # -------------------------------------------------------------------------

    def _resolve_internal(
        self,
        pattern_name: str,
        match: re.Match,
        doc_id: str,
        src_dieu: Optional[int],
        src_khoan: Optional[int],
    ) -> Optional[Dict]:
        """Dispatch sang handler tương ứng với pattern_name"""

        handlers = {
            "khoan_dieu_nay":     self._h_khoan_dieu_nay,
            "dieu_nay":           self._h_dieu_nay,
            "khoan_nay":          self._h_khoan_nay,
            "dieu_luat_nay":      self._h_dieu_luat_nay,
            "khoan_dieu_so":      self._h_khoan_dieu_so,
            "dieu_so":            self._h_dieu_so,
            "diem_khoan_dieu_nay": self._h_diem_khoan_dieu_nay,
            "diem_khoan_dieu_so":  self._h_diem_khoan_dieu_so,
        }

        handler = handlers.get(pattern_name)
        if not handler:
            return None

        return handler(match, doc_id, src_dieu, src_khoan)

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _h_khoan_dieu_nay(self, m, doc_id, src_dieu, src_khoan):
        """'Khoản 3 Điều này' → Điều hiện tại, Khoản 3"""
        if src_dieu is None:
            return None
        khoan_list = _parse_number_list(m.group(1))
        query = {"doc_id": doc_id, "hierarchy.dieu": src_dieu,
                 "hierarchy.khoan": {"$in": khoan_list}}
        return {
            "ref_type": "internal", "pattern": "khoan_dieu_nay",
            "matched_text": m.group(0),
            "query": {"dieu": src_dieu, "khoan": khoan_list},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_dieu_nay(self, m, doc_id, src_dieu, src_khoan):
        """'Điều này' → toàn bộ chunks của Điều hiện tại"""
        if src_dieu is None:
            return None
        query = {"doc_id": doc_id, "hierarchy.dieu": src_dieu}
        return {
            "ref_type": "internal", "pattern": "dieu_nay",
            "matched_text": m.group(0),
            "query": {"dieu": src_dieu},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_khoan_nay(self, m, doc_id, src_dieu, src_khoan):
        """'Khoản này' → chunk của Khoản hiện tại"""
        if src_dieu is None or src_khoan is None:
            return None
        query = {"doc_id": doc_id, "hierarchy.dieu": src_dieu,
                 "hierarchy.khoan": src_khoan}
        return {
            "ref_type": "internal", "pattern": "khoan_nay",
            "matched_text": m.group(0),
            "query": {"dieu": src_dieu, "khoan": src_khoan},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_dieu_luat_nay(self, m, doc_id, src_dieu, src_khoan):
        """'Điều 5 Luật này' → Điều 5 trong cùng doc"""
        dieu_list = _parse_number_list(m.group(1))
        query = {"doc_id": doc_id, "hierarchy.dieu": {"$in": dieu_list}}
        return {
            "ref_type": "internal", "pattern": "dieu_luat_nay",
            "matched_text": m.group(0),
            "query": {"dieu": dieu_list},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_khoan_dieu_so(self, m, doc_id, src_dieu, src_khoan):
        """'Khoản 1 Điều 7' → Khoản 1 của Điều 7, cùng doc"""
        khoan_list = _parse_number_list(m.group(1))
        dieu_num   = int(m.group(2))
        query = {"doc_id": doc_id, "hierarchy.dieu": dieu_num,
                 "hierarchy.khoan": {"$in": khoan_list}}
        return {
            "ref_type": "internal", "pattern": "khoan_dieu_so",
            "matched_text": m.group(0),
            "query": {"dieu": dieu_num, "khoan": khoan_list},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_dieu_so(self, m, doc_id, src_dieu, src_khoan):
        """'Điều 7' (standalone) → tất cả chunks của Điều 7, cùng doc"""
        dieu_num = int(m.group(1))
        query = {"doc_id": doc_id, "hierarchy.dieu": dieu_num}
        return {
            "ref_type": "internal", "pattern": "dieu_so",
            "matched_text": m.group(0),
            "query": {"dieu": dieu_num},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_diem_khoan_dieu_nay(self, m, doc_id, src_dieu, src_khoan):
        """'điểm a, b khoản 3 Điều này' → Khoản 3 Điều hiện tại"""
        if src_dieu is None:
            return None
        khoan_list = _parse_number_list(m.group(2))
        # Điểm được gộp vào chunk khoản → chỉ cần tìm chunk khoản
        query = {"doc_id": doc_id, "hierarchy.dieu": src_dieu,
                 "hierarchy.khoan": {"$in": khoan_list}}
        return {
            "ref_type": "internal", "pattern": "diem_khoan_dieu_nay",
            "matched_text": m.group(0),
            "query": {"dieu": src_dieu, "khoan": khoan_list,
                      "note": "diem included in clause chunk"},
            "chunks": self._query_chunks(query, doc_id)
        }

    def _h_diem_khoan_dieu_so(self, m, doc_id, src_dieu, src_khoan):
        """'điểm a, b khoản 3 Điều 7' → Khoản 3 Điều 7"""
        khoan_list = _parse_number_list(m.group(2))
        dieu_num   = int(m.group(3))
        query = {"doc_id": doc_id, "hierarchy.dieu": dieu_num,
                 "hierarchy.khoan": {"$in": khoan_list}}
        return {
            "ref_type": "internal", "pattern": "diem_khoan_dieu_so",
            "matched_text": m.group(0),
            "query": {"dieu": dieu_num, "khoan": khoan_list,
                      "note": "diem included in clause chunk"},
            "chunks": self._query_chunks(query, doc_id)
        }

    # -------------------------------------------------------------------------
    # DOCUMENT LOOKUP (cross-doc)
    # -------------------------------------------------------------------------

    def _find_doc_id(self, doc_type: str, doc_number: str) -> Optional[str]:
        """
        Tìm doc_id trong MongoDB theo số hiệu văn bản.
        Thử khớp chuỗi số hiệu (flexible).

        Args:
            doc_type (str): "Luật", "Nghị định", ...
            doc_number (str): "10/2014/QH13"

        Returns:
            str | None: doc_id nếu tìm thấy
        """
        # Bước 1: khớp chính xác metadata.document_number
        doc = self.documents.find_one(
            {"metadata.document_number": {"$regex": re.escape(doc_number), "$options": "i"}}
        )
        if doc:
            return doc["_id"]

        # Bước 2: fallback khớp _id
        candidate_id = doc_number.replace("/", "_")
        doc = self.documents.find_one({"_id": {"$regex": candidate_id, "$options": "i"}})
        if doc:
            return doc["_id"]

        # Bước 3: chưa tìm thấy → trả về None, caller xử lý
        return None

    # -------------------------------------------------------------------------
    # CHUNK QUERY
    # -------------------------------------------------------------------------

    def _query_chunks(self, query: Dict, doc_id: Optional[str]) -> List[Dict]:
        """
        Query chunks collection, trả về danh sách chunk đơn giản.
        Giới hạn 20 chunk để tránh overload context LLM.
        """
        if doc_id is None:
            # Không tìm thấy doc ngoại → trả rỗng
            return []

        cursor = self.chunks.find(query, {
            "_id": 0,
            "chunk_id": 1,
            "doc_id": 1,
            "version_id": 1,
            "hierarchy": 1,
            "section_title": 1,
            "content": 1,
            "level": 1
        }).limit(20)

        return list(cursor)

    # -------------------------------------------------------------------------
    # UTILITY
    # -------------------------------------------------------------------------

    def _overlaps_external(self, text: str, start: int, end: int) -> bool:
        """Kiểm tra vị trí [start, end] có nằm trong một external match không"""
        for ext_m in EXTERNAL_PATTERN.finditer(text):
            if ext_m.start() <= start and ext_m.end() >= end:
                return True
        return False


# =============================================================================
# LLM INTEGRATION HELPER
# =============================================================================

def format_resolved_refs_for_llm(resolved: List[Dict]) -> str:
    """
    Format kết quả resolve thành context string để inject vào LLM prompt.

    Args:
        resolved: output của ReferenceResolver.resolve()

    Returns:
        str: Context block để thêm vào system/user prompt
    """
    if not resolved:
        return ""

    lines = ["\n--- THAM CHIẾU LIÊN QUAN ---"]

    for ref in resolved:
        matched = ref["matched_text"]
        chunks  = ref["chunks"]

        if not chunks:
            lines.append(f'\n⚠ Tham chiếu "{matched}" — không tìm thấy chunk phù hợp.')
            continue

        lines.append(f'\n📌 Tham chiếu: "{matched}"')
        for chunk in chunks:
            lines.append(
                f"  [{chunk.get('section_title', '?')}] "
                f"{chunk.get('content', '')[:300]}"
                + ("..." if len(chunk.get("content", "")) > 300 else "")
            )

    lines.append("--- KẾT THÚC THAM CHIẾU ---\n")
    return "\n".join(lines)


# =============================================================================
# USAGE EXAMPLE
# =============================================================================
if __name__ == "__main__":
    """
    Chạy thử với MongoDB thật:
        python src/pdf/reference_resolver.py
    """
    from storage.mongo import get_db

    db = get_db()
    resolver = ReferenceResolver(db)

    # Giả lập chunk đang được LLM xử lý
    test_chunk = {
        "doc_id":   "108_2025_QH15",
        "chunk_id": "6b044d52-dace-4dee-a186-f60955caaa1f",
        "hierarchy": {"chapter": 1, "dieu": 4, "khoan": 1, "diem": None},
        "section_title": "Điều 4 - Khoản 1",
        "content": (
            "[Luật 108/2025/QH15] - Điều 4 - Khoản 1 "
            "Thuế là khoản phải nộp ngân sách nhà nước theo quy định của các luật thuế. "
            "Xem thêm Khoản 3 Điều này và Điều 5 Luật này để biết miễn giảm."
        )
    }

    resolved = resolver.resolve_from_chunk(test_chunk)

    print(f"Tìm thấy {len(resolved)} tham chiếu:\n")
    for r in resolved:
        print(f"  pattern : {r['pattern']}")
        print(f"  matched : {r['matched_text']}")
        print(f"  chunks  : {len(r['chunks'])} chunk(s) found")
        for c in r["chunks"]:
            print(f"    - {c['section_title']}: {c['content'][:80]}...")
        print()

    # Format để inject vào LLM
    context = format_resolved_refs_for_llm(resolved)
    print(context)