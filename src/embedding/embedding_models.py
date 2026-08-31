"""
Quản lý các model embedding

Hoạt động: Load, quản lý và thực hiện embedding với 3 model tiếng Việt

"""

import os
import json
from typing import Dict, List
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


class EmbeddingModelManager:
    """Quản lý các model embedding, hỗ trợ load, embed, và thông tin model"""
    
    MODELS_TO_TEST = {
        "phobert-base":"VoVanPhuc/sup-SimCSE-VietNamese-phobert-base",
        "vietnamese-sbert": "keepitreal/vietnamese-sbert"
    }
    
    def __init__(self):
        """Initialize model manager"""
        self.models = {}
        self.model_info = {}
        
    def load_model(self, model_name: str, verbose: bool = True) -> SentenceTransformer:
        """
        Kiểm tra và load model nếu chưa có
        Args:
            model_name: Tên model để load
            verbose: In thông tin loading
        Returns:
            Instance của SentenceTransformer

        """
        if model_name not in self.MODELS_TO_TEST: # chỉ cho phép load các model trong danh sách so sánh
            raise ValueError(f"Model {model_name} không thuộc MODELS_TO_TEST")
        
        if model_name in self.models: # đã load rồi thì trả về luôn
            if verbose:
                print(f"[INFO] Model {model_name} đã được load")
            return self.models[model_name]
        
        model_path = self.MODELS_TO_TEST[model_name] # lấy đường dẫn model từ danh sách
        if verbose:
            print(f"[INFO] Loading {model_name}: {model_path}...")
        
        try:
            model = SentenceTransformer(model_path) # load model từ Hugging Face
            self.models[model_name] = model
            
            # Store model info
            self.model_info[model_name] = {
                "path": model_path,
                "embedding_dim": model.get_sentence_embedding_dimension(),  # lấy kích thước embedding từ model
                "max_seq_length": model.max_seq_length, # lấy chiều dài tối đa của câu mà model hỗ trợ (chunk quá dài sẽ bị cắt)
            }
            
            if verbose:
                print(f"[INFO] ✅ {model_name} load thành công")
                print(f"       - Embedding dimension: {self.model_info[model_name]['embedding_dim']}")
                print(f"       - Max sequence length: {self.model_info[model_name]['max_seq_length']}")
            
            return model
        except Exception as e:
            print(f"[ERROR] Không load được {model_name}: {e}")
            raise
    
    def load_all_models(self, verbose: bool = True) -> Dict[str, SentenceTransformer]:
        """
        Load tất cả các model trong MODELS_TO_TEST
        Args:
            verbose: In thông tin loading
        Returns:
            Bản đồ model_name -> model instance
        """
        print("[INFO] Đang load toàn bộ model...")
        for model_name in self.MODELS_TO_TEST:
            self.load_model(model_name, verbose=verbose)
        print(f"[INFO] ✅ Đã load {len(self.models)} thành công\n")
        return self.models
    
    def embed_text(self, text: str, model_name: str, normalize: bool = True) -> List[float]:
        """
        Chuyển đổi một văn bản thành embedding vector sử dụng model đã load
        
        Args:
            text: Văn bản cần chuyển đổi
            model_name: Tên model để sử dụng
            normalize: Có chuẩn hóa embedding hay không (mặc định True)          
        Returns:
            Embedding vector dưới dạng list float
        """
        # Kiểm tra nếu model chưa được load thì load trước
        if model_name not in self.models:
            self.load_model(model_name)
        
        model = self.models[model_name]
        embedding = model.encode(text, normalize_embeddings=normalize) # trả về numpy array, convert sang list để dễ lưu vào MongoDB sau này
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str], model_name: str, normalize: bool = True, 
                   batch_size: int = 32, show_progress: bool = True) -> List[List[float]]:
        """
        Embbeding hàng loạt cho một danh sách văn bản
        
        Args:
            texts: Danh sách văn bản cần chuyển đổi
            model_name: Tên model để sử dụng        
            normalize: Có chuẩn hóa embedding hay không (mặc định True)
            batch_size: Kích thước batch khi embedding (mặc định 32)
            show_progress: Hiển thị thanh tiến trình hay không (mặc định True)
            
        Returns:
            List các embedding vector dưới dạng list float
        """
        if model_name not in self.models:
            self.load_model(model_name)
        
        model = self.models[model_name]
        
        if show_progress:
            embeddings = model.encode(
                texts, 
                normalize_embeddings=normalize,
                batch_size=batch_size,
                show_progress_bar=True
            )
        else:
            embeddings = model.encode(
                texts,
                normalize_embeddings=normalize,
                batch_size=batch_size,
                show_progress_bar=False
            )
        
        return [emb.tolist() for emb in embeddings]
    
    def embed_all_models(self, text: str) -> Dict[str, List[float]]:
        """
        Embed cùng một văn bản với tất cả các model đã load, trả về dictionary mapping model_name -> embedding vector
        
        Args:
            text: Text to embed
            
        Returns:
            Dictionary mapping model names to embeddings
        """
        embeddings = {}
        for model_name in self.models:
            embeddings[model_name] = self.embed_text(text, model_name)
        return embeddings
    
    def get_model_info(self) -> Dict:
        """Lấy thông tin về tất cả các model đã load, bao gồm đường dẫn, kích thước embedding, và max sequence length"""
        return {
            "models": list(self.models.keys()),
            "details": self.model_info
        }
    
    def unload_model(self, model_name: str):
        """Xóa 1 model khỏi bộ nhớ (nếu cần) giải phóng CPU"""
        if model_name in self.models:
            del self.models[model_name]
            print(f"[INFO] Model {model_name} unloaded")
    
    def unload_all(self):
        """Xóa tất cả model khỏi bộ nhớ, giải phóng CPU"""
        self.models.clear()
        print("[INFO] All models unloaded")


if __name__ == "__main__":
    # Demo usage
    manager = EmbeddingModelManager()
    
    # Load all models
    models = manager.load_all_models()
    
    # Test embedding
    test_text = "Thuế cá nhân của công dân Việt Nam"
    embeddings = manager.embed_all_models(test_text)
    
    print(f"\n[INFO] Test text: {test_text}")
    print(f"[INFO] Kích thước của Embedding:")
    for model_name, emb in embeddings.items():
        print(f"  - {model_name}: {len(emb)} dimensions")
    
    # In thông tin model
    info = manager.get_model_info()
    print(f"\n[INFO] Model info:")
    print(json.dumps(info, indent=2, ensure_ascii=False))
