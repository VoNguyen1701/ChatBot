"""
Benchmark Runner
Chạy toàn bộ pipeline benchmark cho 3 model embedding tiếng Việt
"""

import json
import os
from typing import List, Dict
from pathlib import Path
import numpy as np
from tqdm import tqdm

from .embedding_models import EmbeddingModelManager
from .vector_store import VectorStore
from .retrieval import Retriever
from .evaluation import Evaluator


class BenchmarkRunner:
    """Orchestrates model benchmarking"""
    
    def __init__(self, results_dir: str = "./results", data_dir: str = "./datasets"):
        """
        Initialize benchmark runner
        
        Args:
            results_dir: Directory to save results
            data_dir: Directory containing datasets
        """
        self.results_dir = Path(results_dir)
        self.data_dir = Path(data_dir)
        self.results_dir.mkdir(exist_ok=True)
        self.data_dir.mkdir(exist_ok=True)

        self.model_manager = EmbeddingModelManager()
        self.vector_store = VectorStore()
        self.retriever = None
        self.evaluator = Evaluator()
        
        print(f"[INFO] Benchmark runner initialized") 
        print(f"       Results dir: {self.results_dir}")
        print(f"       Data dir: {self.data_dir}")
    
    def load_dataset(self, filename: str) -> List[Dict]:
        """Đọc dữ liệu từ file JSON trong data_dir"""
        filepath = self.data_dir / filename
        
        if not filepath.exists():
            print(f"[WARN] Không tìm thấy: {filepath}")
            return []
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"[INFO] Đã load {len(data)} item từ {filename}")
        return data
    
    def prepare_embeddings(self, chunks: List[Dict]):
        """
        Sinh embeddings cho tất cả chunks với tất cả model, lưu vào MongoDB và xây dựng FAISS index
        """
        print(f"\n[INFO] Preparing embeddings for {len(chunks)} chunks...")
        
        # Load all models
        self.model_manager.load_all_models(verbose=True)
        
        chunk_ids = [chunk['chunk_id'] for chunk in chunks]
        chunk_contents = [chunk['content'] for chunk in chunks]
        
        embeddings_data = {}
        successful_models = []
        
        # Embed sử dụng từng model và lưu kết quả
        for model_name in self.model_manager.MODELS_TO_TEST:

            try:

                print(f"\n[INFO] Embedding with {model_name}...")

                embeddings_list = self.model_manager.embed_batch(
                    chunk_contents,
                    model_name,
                    normalize=True,
                    batch_size=32,
                    show_progress=True
                )

                embeddings_data[model_name] = {
                    chunk_id: emb
                    for chunk_id, emb in zip(chunk_ids, embeddings_list)
                }

                embeddings_np = np.array(
                    embeddings_list,
                    dtype=np.float32
                )

                self.vector_store.build_faiss_index(
                    model_name,
                    embeddings_np,
                    chunk_ids
                )

                successful_models.append(model_name)

            except Exception as e:

                print(
                    f"[ERROR] {model_name} failed: {e}"
                )
        
        # Lưu embeddings vào MongoDB
        self.vector_store.store_embeddings(embeddings_data)
        
        # Khởi tạo retriever với vector store và model manager đã chuẩn bị
        self.retriever = Retriever(self.vector_store, self.model_manager)
        
        print(f"\n[INFO] ✅ Embeddings prepared successfully")
    
    def run_evaluation(self, eval_data: List[Dict]) -> Dict:
        """
        Run evaluation on all models
        """
        if not self.retriever:
            print("[ERROR] Retriever chưa được khởi tạo. Run prepare_embeddings .") 
            return {}
        
        print(f"\n[INFO] Running evaluation on {len(eval_data)} queries...")
        
        results = {}
        
        for model_name in self.model_manager.MODELS_TO_TEST:
            print(f"\n[INFO] Evaluating {model_name}...")
            
            model_results = {}
            
            # Duyệt qua từng query
            for sample in tqdm(eval_data, desc=model_name):
                query_id = sample['query_id']
                query_text = sample['query']
                
                # Search
                search_results = self.retriever.search_similar(
                    query_text,
                    model_name,
                    k=10
                )
                
                # Lấy chunk_id của các kết quả tìm được
                retrieved_ids = [chunk_id for chunk_id, _ in search_results]
                model_results[query_id] = retrieved_ids
            
            # Đánh giá kết quả
            metrics = self.evaluator.evaluate_dataset(eval_data, model_results, k_values=[5, 10])
            results[model_name] = {
                "metrics": metrics,
                "query_results": model_results
            }
            
            print(f"[INFO] ✅ {model_name} evaluation complete")
            print(self.evaluator.format_metrics(metrics))
        
        return results
    
    def compare_models(self, results: Dict) -> Dict:
        """
        So sánh kết quả giữa các model và in ra bảng so sánh
        """
        print(f"\n{'='*80}")
        print(f"{'MODEL COMPARISON SUMMARY':^80}")
        print(f"{'='*80}\n")
        
        comparison = {}
        
        # Tổng hợp kết quả cho từng model
        for model_name, data in results.items():
            metrics = data['metrics']
            comparison[model_name] = {
                "map": metrics.get('map_avg', 0),
                "recall@5": metrics.get('recall@5_avg', 0),
                "recall@10": metrics.get('recall@10_avg', 0),
                "ndcg@5": metrics.get('ndcg@5_avg', 0),
                "ndcg@10": metrics.get('ndcg@10_avg', 0),
                "hit_rate@5": metrics.get('hit_rate@5_avg', 0),
            }
        
        # Xác định model tốt nhất cho từng metric
        metrics_keys = list(comparison[list(comparison.keys())[0]].keys())
        best_models = {}
        
        for metric in metrics_keys:
            best_model = max(
                comparison.items(),
                key=lambda x: x[1][metric]
            )[0]
            best_models[metric] = best_model
        
        # In bảng so sánh
        print(f"{'Metric':<15} | {' | '.join(f'{name:^15}' for name in comparison.keys())} | {'BEST':^15}")
        print("-" * (15 + 3 + 18*len(comparison) + 3 + 15))
        
        for metric in metrics_keys:
            scores = [f"{comparison[name][metric]:.4f}" for name in comparison.keys()]
            best = best_models[metric]
            print(f"{metric:<15} | {' | '.join(f'{s:^15}' for s in scores)} | {best:^15}")
        
        return {
            "comparison": comparison,
            "best_models": best_models
        }
    
    def save_results(self, results: Dict, comparison: Dict, filename_prefix: str = "benchmark"):
        """
        Save results to JSON files
        """
        # Save detailed results
        detailed_file = self.results_dir / f"{filename_prefix}_detailed.json"
        with open(detailed_file, 'w', encoding='utf-8') as f:
            # Sử dụng default=str để handle các object không serializable (nếu có)
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        # Save comparison summary
        summary_file = self.results_dir / f"{filename_prefix}_summary.json"
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False)
        
        print(f"\n[INFO] ✅ Results saved:")
        print(f"       - {detailed_file}")
        print(f"       - {summary_file}")
    
    def run_full_benchmark(self, chunks_file: str = "chunks.json", 
                          eval_file: str = "golden_dataset.json") -> Dict:
        """
        Run full benchmark pipeline
        """
        print(f"\n{'='*80}")
        print(f"{'STARTING EMBEDDING MODEL BENCHMARK':^80}")
        print(f"{'='*80}\n")
        
        # Load datasets
        chunks = self.load_dataset(chunks_file)
        eval_data = self.load_dataset(eval_file)
        
        if not chunks:
            print("[ERROR] No chunks loaded")
            return {}
        
        if not eval_data:
            print("[ERROR] No evaluation data loaded")
            return {}
        
        # Store chunks
        self.vector_store.store_chunks(chunks)
        
        # Prepare embeddings
        self.prepare_embeddings(chunks)
        
        # Run evaluation
        results = self.run_evaluation(eval_data)
        
        # Compare models
        comparison = self.compare_models(results)
        
        # Save results
        self.save_results(results, comparison)
        
        print(f"\n{'='*80}")
        print(f"{'BENCHMARK COMPLETE':^80}")
        print(f"{'='*80}\n")
        
        return {
            "results": results,
            "comparison": comparison
        }


if __name__ == "__main__":
    # Demo usage
    runner = BenchmarkRunner(
        results_dir="./results",
        data_dir="./datasets"
    )
    
    # Run full benchmark
    runner.run_full_benchmark(
         chunks_file="chunks.json",
         eval_file="golden_dataset.json"
     )
    
    print("[INFO] BenchmarkRunner initialized and ready to use")
