# src/pdf/simple_processor.py
"""
UNIFIED DOCUMENT PROCESSOR (SIMPLIFIED)

Mục đích: Xử lý PDF → Trích metadata → Build tree → Create chunks → Store MongoDB
USAGE:
    from simple_processor import UnifiedDocumentProcessor
    
    processor = UnifiedDocumentProcessor(db)
    processor.process_batch("data/raw")
"""

import os
import sys
import hashlib
from pathlib import Path
from datetime import datetime
from tqdm import tqdm
from typing import Dict, List

# Setup path
BASE_DIR = Path(__file__).parent.parent.parent
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from pdf.read_pdf import read_pdf_full, extract_metadata, clean_text
from pdf.legal_parser import DocumentTreeBuilder, ChunkBuilder, SimpleReferenceExtractor
from storage.mongo import get_db


# =============================================================================
# CLASS: UNIFIED DOCUMENT PROCESSOR
# =============================================================================
class UnifiedDocumentProcessor:
    """
    Xử lý PDF documents end-to-end
    
    Flow:
    1. Read PDF
    2. Extract metadata
    3. Build document tree
    4. Create chunks
    5. Extract simple references
    6. Store to MongoDB
    
    MongoDB Collections:
    - documents: Main document record
    - chunks: Content chunks for embedding/retrieval
    - references: Simple document references
    - document_versions: Version history
    
    TODO (Future):
    - reference_graphs: Document relationship graph
    - article_mappings: Điều mapping for nested references
    """
    
    def __init__(self, db):
        """
        Initialize processor
        
        Args:
            db: MongoDB database connection (from get_db())
        """
        self.db = db
        self.stats = {
            "total_documents": 0,
            "total_chunks": 0,
            "total_references": 0,
            "errors": 0
        }
        self.create_indexes()
    def create_indexes(self):
        """
        Create MongoDB indexes
        """

        chunk_col = self.db["chunks"]

        chunk_col.create_index("doc_id")

        chunk_col.create_index("version_id")

        chunk_col.create_index("document_type")

        chunk_col.create_index("level")

        chunk_col.create_index([
            ("hierarchy.dieu", 1),
            ("hierarchy.khoan", 1),
            ("hierarchy.diem", 1)
        ])
    
    def process_document(self, file_path: str, category: str = None) -> Dict:
        """
        Process single PDF document
        
        Args:
            file_path (str): Path to PDF file
            category (str): Category/folder name (e.g., "law", "school")
        
        Returns:
            Dict: Processing result
            {
                "status": "success|skipped|error",
                "doc_id": "TT_21_2026",
                "chunks": 45,
                "references": 12,
                "error": "..." (if error)
            }
        """
        try:
            # ===== STEP 1: Read PDF =====
            full_text = read_pdf_full(file_path)
            if not full_text:
                return {"status": "error", "error": "Empty PDF"}
            
            # ===== STEP 2: Extract Metadata =====
            metadata = extract_metadata(full_text)
            doc_id = metadata["doc_id"]
            
            # ===== STEP 3: Version Control =====
            content_hash = hashlib.md5(full_text.encode()).hexdigest()
            existing_doc = self.db["documents"].find_one({"_id": doc_id})
            
            if existing_doc and existing_doc.get("content_hash") == content_hash:
                return {"status": "skipped", "reason": "no_changes"}
            
            version = (existing_doc.get("current_version", 0) if existing_doc else 0) + 1
            version_id = f"{doc_id}_v{version}"
            
            # ===== STEP 4: Build Tree =====
            builder = DocumentTreeBuilder(full_text)
            tree = builder.build()
            
            # ===== STEP 5: Create Chunks =====
            doc_ref = f"[{metadata['document_type']} {metadata['document_number']}]"
            chunk_builder = ChunkBuilder(tree, metadata, doc_ref)
            chunks = chunk_builder.build()
            
            # ===== STEP 6: Extract Simple References =====
            extractor = SimpleReferenceExtractor(full_text)
            simple_refs = extractor.extract()
            
            # ===== STEP 7: Store to MongoDB =====
            self._store_to_db(
                doc_id, version, version_id, metadata, content_hash,
                tree, chunks, simple_refs, category, file_name=Path(file_path).name
            )
            
            # ===== Update Stats =====
            self.stats["total_documents"] += 1
            self.stats["total_chunks"] += len(chunks)
            self.stats["total_references"] += len(simple_refs)
            
            return {
                "status": "success",
                "doc_id": doc_id,
                "version": version,
                "chunks": len(chunks),
                "references": len(simple_refs)
            }
        
        except Exception as e:
            self.stats["errors"] += 1
            return {"status": "error", "error": str(e)}
    
    def _store_to_db(self, doc_id, version, version_id, metadata, content_hash,
                     tree, chunks, simple_refs, category=None, file_name=None):
        """
        Store processed document to MongoDB
        
        Collections:
        1. documents: Main document metadata
        2. chunks: Content chunks
        3. references: Simple references
        4. document_versions: Version history
        
        Args:
            doc_id (str): Document ID
            version (int): Version number
            version_id (str): Version ID
            metadata (dict): Document metadata
            content_hash (str): MD5 hash of content
            tree (dict): Document tree structure
            chunks (list): Chunks
            simple_refs (list): Simple references
        """
        
        doc_col = self.db["documents"]
        chunk_col = self.db["chunks"]
        ref_col = self.db["references"]
        version_col = self.db["document_versions"]
        
        # ===== 1. Update Document =====
        doc_col.update_one(
            {"_id": doc_id},
            {"$set": {
                "_id": doc_id,
                "metadata": metadata,
                "category": category,
                "file_name": file_name,
                "current_version": version,
                "content_hash": content_hash,
                "tree_stats": {
                    "total_chapters": len(tree.get("chapters", [])),
                    "total_articles": (
                        sum(len(ch["articles"]) for ch in tree.get("chapters", []))
                        if tree.get("chapters") else len(tree.get("articles", []))
                    ),
                    "total_clauses": (
                        sum(
                            len(a["clauses"])
                            for ch in tree.get("chapters", [])
                            for a in ch["articles"]
                        )
                        if tree.get("chapters") else
                        sum(len(a["clauses"]) for a in tree.get("articles", []))
                    ),
                    "total_points": (
                        sum(
                            len(c["points"])
                            for ch in tree.get("chapters", [])
                            for a in ch["articles"]
                            for c in a["clauses"]
                        )
                        if tree.get("chapters") else
                        sum(len(c["points"]) for a in tree.get("articles", []) for c in a["clauses"])
                    )
                },
                "reference_count": len(simple_refs),
                "chunk_count": len(chunks),
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow()
            }
            },
            upsert=True
        )
        
        # ===== 2. Close Old Versions =====
        version_col.update_many(
            {"doc_id": doc_id, "is_current": True},
            {"$set": {"is_current": False}}
        )
        
        # ===== 3. Create New Version =====
        version_col.insert_one({
            "_id": version_id,
            "doc_id": doc_id,
            "version": version,
            "issued_date": metadata.get("issued_date"),
            "is_current": True,
            "created_at": datetime.utcnow()
        })
        
        # ===== 4. Delete Old Data =====
        chunk_col.delete_many({"doc_id": doc_id})
        ref_col.delete_many({"source_doc_id": doc_id})
        
        # ===== 5. Insert Chunks =====
        chunk_docs = []
        for chunk in chunks:
            chunk_docs.append({
                "_id": chunk["_id"],
                "doc_id": doc_id,
                "version_id": version_id,
                "document_type": metadata.get("document_type"),
                "effective_date": metadata.get("effective_date"),
                "hierarchy": {
                    "chapter": chunk["location"].get("chapter"),
                    "dieu": chunk["location"].get("article"),
                    "khoan": chunk["location"].get("clause"),
                    "diem": chunk["location"].get("point")
                },
                "section_title": chunk["section_title"],
                "content": chunk["content"],
                "level": chunk["level"],
                "content_length": len(chunk["content"]),
                "created_at": datetime.utcnow()
            })
        
        # ===== 6. Insert References =====
        ref_docs = []
        for ref in simple_refs:
            ref_docs.append({
                "source_doc_id": doc_id,
                "reference": {
                    "doc_type": ref["doc_type"],
                    "doc_number": ref["doc_number"]
                },
                "context": ref.get("context", ""),
                "created_at": datetime.utcnow()
            })
        
        # Bulk insert
        if chunk_docs:
            chunk_col.insert_many(chunk_docs)
        
        if ref_docs:
            ref_col.insert_many(ref_docs)
    
    def process_batch(self, base_folder: str):
        base_path = Path(base_folder)
        
        if not base_path.exists():
            print(f"❌ Folder not found: {base_folder}")
            return
        
        # Get all categories (subfolders)
        categories = [
            d for d in base_path.iterdir()
            if d.is_dir()
        ]
        
        print(f"\n📂 Processing PDFs in: {base_folder}")
        print(f"📊 Found {len(categories)} categories\n")
        
        for cat_path in categories:
            category_name = cat_path.name
            
            # Get all PDFs in this category
            pdf_files = list(cat_path.glob("*.pdf"))
            
            if not pdf_files:
                continue
            
            print(f"📁 {category_name}: {len(pdf_files)} files")
            
            for pdf_file in tqdm(pdf_files, desc=f"  {category_name}", leave=True):
                result = self.process_document(
                    str(pdf_file),
                    category_name
                )
                
                status_symbol = {
                    "success": "✅",
                    "skipped": "⏭️",
                    "error": "❌"
                }.get(result["status"], "?")
                
                print(f"    {status_symbol} {pdf_file.name}: {result['status']}")
        
        self._print_stats()
    
    def _print_stats(self):
        """
        Print processing statistics
        """
        print("\n" + "=" * 60)
        print("PROCESSING STATISTICS")
        print("=" * 60)
        
        for key, value in self.stats.items():
            print(f"{key:.<40} {value:>15,}")
        
        print("=" * 60)


# =============================================================================
# MAIN
# =============================================================================
if __name__ == "__main__":
    """
    Usage:
        cd D:\Code\.vscode\TT\1
        .\ai\Scripts\Activate.ps1
        python src/pdf/simple_processor.py
    """
    
    print("""
    ╔════════════════════════════════════════════════════════════════════╗
    ║         🚀 LEGAL DOCUMENT PROCESSOR (SIMPLIFIED)                  ║
    ╚════════════════════════════════════════════════════════════════════╝
    """)
    
    # Get database connection
    print("🔌 Connecting to MongoDB...")
    try:
        db = get_db()
        print("✅ Connected")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        exit(1)
    
    # Process batch
    processor = UnifiedDocumentProcessor(db)
    
    data_path = BASE_DIR / "data" / "raw"
    processor.process_batch(str(data_path))
    
    print("\n✨ Done!")
