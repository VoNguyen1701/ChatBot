"""
Retrieval Module
Thực hiện tìm kiếm tương tự dựa trên vector embedding đã lưu trữ trong FAISS và MongoDB
Các chức năng chính:
- Tìm kiếm tương tự (similarity search) với một truy vấn
- So sánh kết quả tìm kiếm giữa các model embedding khác nhau
- Truy xuất thông tin chunk từ MongoDB dựa trên chunk_id
- Tìm kiếm và truy xuất kết hợp (search and retrieve) để lấy thông tin chi tiết của các chunk tương tự
- Hỗ trợ tìm kiếm hàng loạt (batch search) cho nhiều truy vấn cùng lúc
"""

from typing import List, Tuple, Dict, Optional
import numpy as np
from .vector_store import VectorStore
from .embedding_models import EmbeddingModelManager


class Retriever:
    """Bộ truy xuất sử dụng vector embedding để tìm kiếm tương tự và truy xuất thông tin chunk"""
    
    def __init__(self, vector_store: VectorStore, model_manager: EmbeddingModelManager):
        """
        Initialize retriever
        
        Args:
            vector_store: VectorStore instance with FAISS indices
            model_manager: EmbeddingModelManager instance with loaded models
        """
        self.vector_store = vector_store
        self.model_manager = model_manager
    
    def search_similar(self, query: str, model_name: str, k: int = 5) -> List[Tuple[str, float]]:
        """
        Tìm kiếm các chunk tương tự với một truy vấn sử dụng model embedding đã load
        
        Args:
            query: Query text
            model_name: Model to use for embedding
            k: số lượng kết quả trả về muốn lấy
            
        Returns:
            List of (chunk_id, similarity_score) tuples
        similarity_score: Giá trị cosine similarity giữa query và chunk.
            Càng gần 1 thì càng giống nhau.
        """
        # lấy embedding của query
        query_embedding = self.model_manager.embed_text(query, model_name, normalize=True)
        query_vec = np.array([query_embedding], dtype=np.float32)
        
        # Kiểm tra nếu chưa có chỉ mục FAISS cho model này thì trả về rỗng
        if model_name not in self.vector_store.faiss_indices:
            print(f"[ERROR] No FAISS index for {model_name}")
            return []
        
        index = self.vector_store.faiss_indices[model_name]
        chunk_ids = self.vector_store.chunk_ids_map[model_name]
        
        # Tìm kiếm tương tự trong FAISS
        distances, indices = index.search(query_vec, k)
        
        results = []
        for dist, idx in zip(distances[0], indices):
            if idx < len(chunk_ids):
                results.append((chunk_ids[idx], float(dist)))
        
        return results
    
    def search_all_models(self, query: str, k: int = 5) -> Dict[str, List[Tuple[str, float]]]:
        """
        Search using all loaded models
        
        Args:
            query: Query text
            k: Number of results per model
            
        Returns:
            Dictionary mapping model names to search results
        """
        results = {}
        for model_name in self.vector_store.faiss_indices:
            results[model_name] = self.search_similar(query, model_name, k)
        return results
    
    def retrieve_chunks(self, chunk_ids: List[str]) -> List[Dict]:
        """
        Lấy nội dung chunk từ MongoDB dựa trên chunk_ids
        
        Args:
            chunk_ids: List of chunk IDs
            
        Returns:
            List of chunk documents
        """
        return self.vector_store.get_chunks(chunk_ids)
    
    def search_and_retrieve(self, query: str, model_name: str, k: int = 5) -> List[Dict]:
        """
        Tìm kiếm tương tự và truy xuất thông tin chunk chi tiết
        
        Args:
            query: Query text
            model_name: Model to use
            k: Number of results
            
        Returns:
            List of full chunk documents with similarity scores
        """
        # Tìm kiếm tương tự để lấy chunk_ids và similarity scores
        search_results = self.search_similar(query, model_name, k)
        
        if not search_results:
            return []
        
        # Truy xuất nội dung chunk từ MongoDB
        chunk_ids = [chunk_id for chunk_id, _ in search_results]
        chunks = self.retrieve_chunks(chunk_ids)
        
        # Gán similarity score vào từng chunk
        score_map = {chunk_id: score for chunk_id, score in search_results}
        
        results = []
        for chunk in chunks:
            chunk['similarity_score'] = score_map.get(chunk['chunk_id'], 0.0)
            results.append(chunk)
        
        # Sắp xếp kết quả theo similarity score giảm dần
        results.sort(key=lambda x: x['similarity_score'], reverse=True)
        
        return results
    
    def compare_models(self, query: str, k: int = 5) -> Dict:
        """
        So sánh kết quả tìm kiếm giữa các model embedding khác nhau
        
        Args:
            query: Query text
            k: Number of results per model
            
        Returns:
            Dictionary with results from each model
        """
        results = {}
        # Tìm kiếm tương tự với tất cả model đã load
        for model_name in self.vector_store.faiss_indices:
            results[model_name] = self.search_and_retrieve(query, model_name, k)
        
        return results
    
    def batch_search(self, queries: List[str], model_name: str, k: int = 5) -> Dict[str, List]:
        """
        Batch search for multiple queries
        
        Args:
            queries: List of query texts
            model_name: Model to use
            k: Number of results per query
            
        Returns:
            Dictionary mapping query -> search results
        """
        results = {}
        for query in queries:
            results[query] = self.search_and_retrieve(query, model_name, k)
        return results


if __name__ == "__main__":
    # Demo usage
    from .vector_store import VectorStore
    from .embedding_models import EmbeddingModelManager
    
    # Initialize
    vector_store = VectorStore()
    model_manager = EmbeddingModelManager()
    model_manager.load_all_models()
    
    retriever = Retriever(vector_store, model_manager)
    
    # 
    query = "Các trường hợp được miễn thuế thu nhập cá nhân"
    results = retriever.search_all_models(query, k=5)
    
    print(f"[INFO] Query: {query}")
    for model_name, search_results in results.items():
        print(f"\n{model_name}:")
        for chunk_id, score in search_results:
            print(f"  - {chunk_id}: {score:.4f}")
