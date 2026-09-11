"""
Vector Store Manager
Lưu trữ và quản lý vector embedding với MongoDB và FAISS
Mục tiêu:
- MongoDB:
    + Lưu nội dung chunk
    + Lưu embedding vector
    + Lưu metadata phục vụ truy xuất và đánh giá

- FAISS:
    + Xây dựng chỉ mục vector
    + Tìm kiếm semantic similarity tốc độ cao
    + Hỗ trợ retrieval trong hệ thống RAG

Pipeline tổng quát:
PDF -> Chunking -> Embedding -> MongoDB + FAISS -> Semantic Retrieval

Ý tưởng:
- MongoDB dùng để lưu dữ liệu gốc và metadata
- FAISS chỉ dùng để search vector nhanh
- Khi retrieve:
    Query -> embedding -> search FAISS -> lấy chunk_id
    -> truy MongoDB để lấy nội dung chunk

"""

import json
import os
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import numpy as np
from pymongo import MongoClient
import faiss


class VectorStore:
    """Quản lý vector embedding với MongoDB và FAISS"""
    
    def __init__(self, db_name: str = "legal_rag_db", mongo_uri: str = None):
        """
        Khởi tạo vector store, kết nối MongoDB và chuẩn bị cấu trúc lưu trữ
        
        Args:
            db_name: MongoDB database name
            mongo_uri: Uri kết nối MongoDB (nếu None sẽ dùng mặc định)
        """
        self.db_name = db_name
        self.mongo_uri = mongo_uri or "mongodb://dungnguyet17012005_db_user:Dungnguyet17012005~@ac-hzf04zl-shard-00-00.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-01.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-02.bzpmnh4.mongodb.net:27017/?ssl=true&replicaSet=atlas-qutlkr-shard-0&authSource=admin&appName=Cluster0"
        
        # Khởi tạo kết nối MongoDB
        try:
            self.client = MongoClient(self.mongo_uri)
            self.db = self.client[db_name]
            self.chunks_col = self.db["chunks"]
            self.embeddings_col = self.db["embeddings"]
            print(f"[INFO] ✅ Kết nối MongoDB: {db_name}")
        except Exception as e:
            print(f"[ERROR] Không kết nối được MongoDB: {e}")
            raise
        
        # FAISS indices for each model
        self.faiss_indices = {} # Lưu trữ các chỉ mục FAISS theo model name
        self.chunk_ids_map = {}  # Lưu trữ mapping chunk_id <-> index trong FAISS
    
    def store_chunks(self, chunks: List[Dict]) -> int:
        """
        Lưu trữ chunks vào MongoDB
        
        Args:
            chunks: Danh sách chunk, mỗi chunk là dict có ít nhất "chunk_id", "text", "metadata"
            
        Returns:
            Số lượng chunks đã lưu trữ
        """
        if not chunks:
            print("[WARN] Không có chunk để lưu")
            return 0
        
        try:
            """
            insert_many:
            - Chèn nhiều document cùng lúc
            - ordered=False:
                nếu 1 document lỗi
                vẫn tiếp tục insert document khác
            """
            # Lưu hoặc cập nhật chunk (dựa trên chunk_id)
            result = self.chunks_col.insert_many(chunks, ordered=False)
            print(f"[INFO] Đã lưu {len(result.inserted_ids)} chunks vào MongoDB")
            return len(result.inserted_ids)
        except Exception as e:
            print(f"[ERROR] Lỗi khi lưu chunks: {e}")
            raise
    
    def get_chunks(self, chunk_ids: Optional[List[str]] = None) -> List[Dict]:
        """
        Lấy chunks từ MongoDB

        Args:
            chunk_ids:
                Danh sách chunk_id cần lấy

                Nếu None:
                    lấy toàn bộ chunks

        Returns:
            Danh sách chunks
        """
        if chunk_ids: # Lấy chunks theo chunk_ids nếu được cung cấp
            chunks = list(self.chunks_col.find({"chunk_id": {"$in": chunk_ids}}))
        else: # Lấy tất cả chunks nếu không cung cấp chunk_ids
            chunks = list(self.chunks_col.find())
        return chunks
    
    def store_embeddings(self, embeddings_data: Dict[str, List]) -> int:
        """
            Lưu embeddings vào MongoDB
            Cấu trúc embeddings_data:
            {
                "model_name": {
                    "chunk_id": [vector embedding],
                    ...
                }
            }
            Returns: Tổng số embeddings đã lưu trữ
        """
        count = 0
        timestamp = datetime.now() # Dùng timestamp hiện tại cho created_at và updated_at
        
        # Duyêt qua từng model và chunk để lưu embedding vào MongoDB
        for model_name, embeddings in embeddings_data.items(): 
            for chunk_id, embedding in embeddings.items():
                # Chuẩn bị document để lưu vào MongoDB
                doc = {
                    "chunk_id": chunk_id,
                    "model_name": model_name,
                    "embedding": embedding,
                    "embedding_dim": len(embedding),
                    "created_at": timestamp,
                    "updated_at": timestamp
                }
                
                # Lưu hoặc cập nhật embedding (dựa trên chunk_id và model_name)
                """
                update_one + upsert=True
                Điều kiện unique:
                    chunk_id + model_name
                """
                self.embeddings_col.update_one(
                    {"chunk_id": chunk_id, "model_name": model_name},
                    {"$set": doc},
                    upsert=True
                )
                count += 1
        
        print(f"[INFO] Đã lưu {count} embeddings vào MongoDB")
        return count
    
    def build_faiss_index(self, model_name: str, embeddings: np.ndarray, 
                         chunk_ids: List[str]) -> faiss.Index:
        """
       Xây dựng FAISS index để semantic search

        Args:
            model_name:Tên embedding model

            embeddings:
                Ma trận embedding
                Shape:(num_vectors, embedding_dim)

            chunk_ids: Danh sách chunk_id tương ứng

        Returns: FAISS index
        """
        # Kiểm tra tính hợp lệ của dữ liệu
        if embeddings.shape[0] != len(chunk_ids):
            raise ValueError("Số embeddings và chunk_ids không khớp")
        
        embedding_dim = embeddings.shape[1] # Lấy kích thước embedding từ shape của ma trận embeddings
        
        # Tạo FAISS index
        index = faiss.IndexFlatIP(embedding_dim)  
        index.add(embeddings.astype(np.float32)) # Thêm embedding vào index (chuyển sang float32 để tương thích với FAISS)
        
        self.faiss_indices[model_name] = index # Lưu index vào dictionary theo model_name
        self.chunk_ids_map[model_name] = chunk_ids # Lưu mapping chunk_id <-> index trong FAISS
        
        print(f"[INFO] Built FAISS index for {model_name}")
        print(f"       - Dimension: {embedding_dim}")
        print(f"       - Vectors: {index.ntotal}")
        
        return index
    
    def save_faiss_index(self, model_name: str, save_dir: str = "./indices"):
        """Save FAISS vào disk"""
        os.makedirs(save_dir, exist_ok=True)
        
        if model_name not in self.faiss_indices:
            print(f"[WARN] Không tồn tại index cho {model_name}")
            return
        
        index_path = os.path.join(save_dir, f"{model_name}.index")
        id_map_path = os.path.join(save_dir, f"{model_name}_ids.json")
        
        faiss.write_index(self.faiss_indices[model_name], index_path)
        
        with open(id_map_path, 'w') as f:
            json.dump(self.chunk_ids_map[model_name], f)
        
        print(f"[INFO] Đã lưu FAISS index {index_path}")
    
    def load_faiss_index(self, model_name: str, load_dir: str = "./indices"):
        """Load FAISS index from disk"""
        index_path = os.path.join(load_dir, f"{model_name}.index")
        id_map_path = os.path.join(load_dir, f"{model_name}_ids.json")
        
        if not os.path.exists(index_path):
            print(f"[WARN] Index not found: {index_path}")
            return None
        
        self.faiss_indices[model_name] = faiss.read_index(index_path)
        
        with open(id_map_path, 'r') as f:
            self.chunk_ids_map[model_name] = json.load(f)
        
        print(f"[INFO] Không tìm thấy index {index_path}")
        return self.faiss_indices[model_name]
    
    def get_index_stats(self, model_name: str) -> Dict:
        """Lấy thống kê về index FAISS cho một model cụ thể"""
        if model_name not in self.faiss_indices:
            return {"status": "not_loaded"}
        
        index = self.faiss_indices[model_name]
        return {
            "model_name": model_name,
            "vector_count": index.ntotal,
            "dimension": index.d,
            "index_type": str(type(index).__name__)
        }
    
    def get_all_indices_stats(self) -> Dict:
        """Lấy thống kê về tất cả các index FAISS đã load"""
        stats = {}
        for model_name in self.faiss_indices:
            stats[model_name] = self.get_index_stats(model_name)
        return stats


if __name__ == "__main__":
    # Demo usage
    store = VectorStore()
    print(f"Vector store initialized: {store.db_name}")
