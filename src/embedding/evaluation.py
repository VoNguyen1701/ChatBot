"""
Model Evaluation Module
Đánh giá hiệu suất của các model embedding sử dụng các metric chuẩn trong Information Retrieval (IR)
"""

from typing import List, Dict, Set
from collections import defaultdict


class Evaluator:
    """Evaluator class cung cấp các phương thức để tính toán các metric đánh giá hiệu suất của hệ thống retrieval dựa trên embedding."""
    
    @staticmethod
    def precision_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """
        Tính toán Precision@k            
        Returns:
            Precision@k score (0-1)
        """
        if k == 0:
            return 0.0
        
        retrieved_k = set(retrieved_ids[:k])
        hits = len(relevant_ids & retrieved_k)
        
        return hits / k
    
    @staticmethod
    def recall_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """
        Calculate Recall@k: Tỷ lệ tài liệu liên quan được tìm thấy trong top-k kết quả trả về
        Returns:
            Recall@k score (0-1)
        """
        if len(relevant_ids) == 0:
            return 0.0
        
        retrieved_k = set(retrieved_ids[:k])
        hits = len(relevant_ids & retrieved_k)
        
        return hits / len(relevant_ids)
    
    @staticmethod
    def mean_average_precision(relevant_ids: Set[str], retrieved_ids: List[str]) -> float:
        """
        Calculate Mean Average Precision (MAP):
        Đánh giá thời gian và thứ tự của các tài liệu liên quan trong kết quả trả về.

        Công thức tính MAP:
MAP = (1/Q) * Σ (AP(q_i)) với Q là tổng số truy vấn và AP(q_i) là Average Precision của truy vấn q_i.
Average Precision (AP) được tính bằng công thức:
AP = (1/R) * Σ (P(k) * rel(k)) với R là số tài liệu liên quan, P(k) là Precision tại vị trí k, và rel(k) là 1 nếu tài liệu tại vị trí k là liên quan, ngược lại là 0.
        """
        if len(relevant_ids) == 0:
            return 0.0
        
        ap = 0.0
        hits = 0
        
        for i, doc_id in enumerate(retrieved_ids):
            if doc_id in relevant_ids:
                hits += 1
                ap += hits / (i + 1)
        
        return ap / len(relevant_ids)
    
    @staticmethod
    def ndcg_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """
        Calculate Normalized Discounted Cumulative Gain (NDCG@k):
            NDCG đánh giá chất lượng của kết quả trả về dựa trên vị trí của các tài liệu liên quan. 
            Tài liệu liên quan xuất hiện càng cao trong danh sách trả về thì điểm số càng cao.
        """
        # Calculate DCG
        dcg = 0.0
        retrieved_k = retrieved_ids[:k]
        
        for i, doc_id in enumerate(retrieved_k):
            if doc_id in relevant_ids:
                dcg += 1.0 / (i + 1)
        
        # Calculate IDCG (ideal DCG)
        idcg = 0.0
        for i in range(min(len(relevant_ids), k)):
            idcg += 1.0 / (i + 1)
        
        if idcg == 0:
            return 0.0
        
        return dcg / idcg
    
    @staticmethod
    def hit_rate(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """
        Calculate Hit Rate (nơi nào đó trong top-k có ít nhất một tài liệu liên quan được tìm thấy):
            Đánh giá xem người dùng có tìm thấy ít nhất một tài liệu liên quan trong top-k kết quả trả về hay không.
        """
        retrieved_k = set(retrieved_ids[:k])
        return 1.0 if len(relevant_ids & retrieved_k) > 0 else 0.0
    
    @staticmethod
    def mrr_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """
        Calculate Mean Reciprocal Rank (MRR@k):
            MRR đánh giá vị trí của tài liệu liên quan đầu tiên xuất hiện trong kết quả trả về. 
        """
        retrieved_k = retrieved_ids[:k]
        
        for i, doc_id in enumerate(retrieved_k):
            if doc_id in relevant_ids:
                return 1.0 / (i + 1)
        
        return 0.0
    
    @staticmethod
    def evaluate_query(query_id: str, relevant_ids: Set[str], 
                       retrieved_ids: List[str], k_values: List[int] = [5, 10]) -> Dict:
        """
        Đánh giá một truy vấn cụ thể với các metric đã định nghĩa
        """
        metrics = {
            "query_id": query_id,
            "relevant_count": len(relevant_ids),
            "retrieved_count": len(retrieved_ids),
            "map": Evaluator.mean_average_precision(relevant_ids, retrieved_ids),
            "mrr": Evaluator.mrr_at_k(relevant_ids, retrieved_ids, len(retrieved_ids)),
        }
        
        for k in k_values:
            metrics[f"precision@{k}"] = Evaluator.precision_at_k(relevant_ids, retrieved_ids, k)
            metrics[f"recall@{k}"] = Evaluator.recall_at_k(relevant_ids, retrieved_ids, k)
            metrics[f"ndcg@{k}"] = Evaluator.ndcg_at_k(relevant_ids, retrieved_ids, k)
            metrics[f"hit_rate@{k}"] = Evaluator.hit_rate(relevant_ids, retrieved_ids, k)
        
        return metrics
    
    @staticmethod
    def evaluate_dataset(eval_data: List[Dict], model_results: Dict, 
                        k_values: List[int] = [5, 10]) -> Dict:
        """
        Đánh giá toàn bộ dataset với các truy vấn và kết quả trả về từ model
        """
        if not eval_data:
            return {}
        
        query_metrics = []
        
        for sample in eval_data:
            query_id = sample['query_id']
            relevant_ids = set(sample.get('relevant_ids', []))
            retrieved_ids = model_results.get(query_id, [])
            
            metrics = Evaluator.evaluate_query(query_id, relevant_ids, retrieved_ids, k_values)
            query_metrics.append(metrics)
        
        # Tính toán các metric tổng hợp trung bình trên toàn bộ dataset
        agg_metrics = {
            "total_queries": len(query_metrics),
            "relevant_avg": sum(m['relevant_count'] for m in query_metrics) / len(query_metrics),
        }
        
        for metric in ["map", "mrr"]:
            agg_metrics[f"{metric}_avg"] = sum(m[metric] for m in query_metrics) / len(query_metrics)
        
        for k in k_values:
            agg_metrics[f"precision@{k}_avg"] = sum(m[f"precision@{k}"] for m in query_metrics) / len(query_metrics)
            agg_metrics[f"recall@{k}_avg"] = sum(m[f"recall@{k}"] for m in query_metrics) / len(query_metrics)
            agg_metrics[f"ndcg@{k}_avg"] = sum(m[f"ndcg@{k}"] for m in query_metrics) / len(query_metrics)
            agg_metrics[f"hit_rate@{k}_avg"] = sum(m[f"hit_rate@{k}"] for m in query_metrics) / len(query_metrics)
        
        return agg_metrics
    
    @staticmethod
    def format_metrics(metrics: Dict) -> str:
        """Chuyển đổi dict metrics thành chuỗi định dạng đẹp để hiển thị"""
        output = []
        for key, value in metrics.items():
            if isinstance(value, float):
                output.append(f"{key}: {value:.4f}")
            else:
                output.append(f"{key}: {value}")
        return "\n".join(output)


if __name__ == "__main__":
    # Demo usage
    relevant_ids = {"doc1", "doc2", "doc3"}
    retrieved_ids = ["doc1", "doc4", "doc2", "doc5", "doc6"]
    
    metrics = Evaluator.evaluate_query(
        "q1",
        relevant_ids,
        retrieved_ids,
        k_values=[5, 10]
    )
    
    print("Evaluation Metrics:")
    print(Evaluator.format_metrics(metrics))
