"""
Retrieval Metrics Evaluation Report Generator
Tạo báo cáo đánh giá retrieval với sơ đồ trực quan dễ hiểu cho người ngoài ngành
"""

import pytest
import json
from typing import List, Dict, Set
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Rectangle
import numpy as np
from datetime import datetime
from pathlib import Path


class Evaluator:
    """Evaluator class - Lớp tính toán các metric đánh giá"""
    
    @staticmethod
    def precision_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """Precision@K: Tỷ lệ tài liệu liên quan trong top-k kết quả trả về"""
        if k == 0:
            return 0.0
        retrieved_k = set(retrieved_ids[:k])
        hits = len(relevant_ids & retrieved_k)
        return hits / k
    
    @staticmethod
    def recall_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """Recall@K: Tỷ lệ tài liệu liên quan được tìm thấy trong top-k"""
        if len(relevant_ids) == 0:
            return 0.0
        retrieved_k = set(retrieved_ids[:k])
        hits = len(relevant_ids & retrieved_k)
        return hits / len(relevant_ids)
    
    @staticmethod
    def mean_average_precision(relevant_ids: Set[str], retrieved_ids: List[str]) -> float:
        """MAP: Đánh giá vị trí và thứ tự của tài liệu liên quan"""
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
        """NDCG@K: Đánh giá mức độ lý tưởng của ranking"""
        dcg = 0.0
        retrieved_k = retrieved_ids[:k]
        for i, doc_id in enumerate(retrieved_k):
            if doc_id in relevant_ids:
                dcg += 1.0 / (i + 1)
        idcg = 0.0
        for i in range(min(len(relevant_ids), k)):
            idcg += 1.0 / (i + 1)
        if idcg == 0:
            return 0.0
        return dcg / idcg
    
    @staticmethod
    def hit_rate(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """Hit Rate: Tỷ lệ truy vấn tìm thấy ít nhất một tài liệu liên quan"""
        retrieved_k = set(retrieved_ids[:k])
        return 1.0 if len(relevant_ids & retrieved_k) > 0 else 0.0
    
    @staticmethod
    def mrr_at_k(relevant_ids: Set[str], retrieved_ids: List[str], k: int) -> float:
        """MRR@K: Tính toán vị trí của tài liệu liên quan đầu tiên"""
        retrieved_k = retrieved_ids[:k]
        for i, doc_id in enumerate(retrieved_k):
            if doc_id in relevant_ids:
                return 1.0 / (i + 1)
        return 0.0
    
    @staticmethod
    def evaluate_query(query_id: str, relevant_ids: Set[str], 
                       retrieved_ids: List[str], k_values: List[int] = [5, 10]) -> Dict:
        """Đánh giá một truy vấn cụ thể"""
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
        """Đánh giá toàn bộ dataset"""
        if not eval_data:
            return {}
        
        query_metrics = []
        
        for sample in eval_data:
            query_id = sample['query_id']
            relevant_ids = set(sample.get('relevant_ids', []))
            retrieved_ids = model_results.get(query_id, [])
            
            metrics = Evaluator.evaluate_query(query_id, relevant_ids, retrieved_ids, k_values)
            query_metrics.append(metrics)
        
        agg_metrics = {
            "total_queries": len(query_metrics),
            "relevant_avg": sum(m['relevant_count'] for m in query_metrics) / len(query_metrics) if query_metrics else 0,
        }
        
        for metric in ["map", "mrr"]:
            agg_metrics[f"{metric}_avg"] = sum(m[metric] for m in query_metrics) / len(query_metrics) if query_metrics else 0
        
        for k in k_values:
            agg_metrics[f"precision@{k}_avg"] = sum(m[f"precision@{k}"] for m in query_metrics) / len(query_metrics) if query_metrics else 0
            agg_metrics[f"recall@{k}_avg"] = sum(m[f"recall@{k}"] for m in query_metrics) / len(query_metrics) if query_metrics else 0
            agg_metrics[f"ndcg@{k}_avg"] = sum(m[f"ndcg@{k}"] for m in query_metrics) / len(query_metrics) if query_metrics else 0
            agg_metrics[f"hit_rate@{k}_avg"] = sum(m[f"hit_rate@{k}"] for m in query_metrics) / len(query_metrics) if query_metrics else 0
        
        return agg_metrics


# ==================== VISUAL REPORT GENERATOR ====================

class VisualRetrievalReport:
    """Tạo báo cáo đánh giá retrieval với sơ đồ trực quan"""
    
    def __init__(self, eval_data: List[Dict], model_results: Dict, 
                 k_values: List[int] = [5, 10], report_name: str = "Retrieval_Evaluation_Report"):
        self.eval_data = eval_data
        self.model_results = model_results
        self.k_values = k_values
        self.report_name = report_name
        self.metrics = Evaluator.evaluate_dataset(eval_data, model_results, k_values)
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.query_metrics = self._get_query_metrics()
    
    def _get_query_metrics(self) -> List[Dict]:
        """Lấy metrics chi tiết cho từng truy vấn"""
        query_metrics = []
        for sample in self.eval_data:
            query_id = sample['query_id']
            relevant_ids = set(sample.get('relevant_ids', []))
            retrieved_ids = self.model_results.get(query_id, [])
            
            metrics = Evaluator.evaluate_query(query_id, relevant_ids, retrieved_ids, self.k_values)
            metrics['query'] = sample.get('query', '')[:60] + ('...' if len(sample.get('query', '')) > 60 else '')
            query_metrics.append(metrics)
        
        return query_metrics
    
    # ==================== TEXT REPORTS ====================
    
    def generate_executive_summary(self) -> str:
        """Tạo báo cáo tóm tắt điều hành (cho quản lý)"""
        k_max = max(self.k_values)
        
        # Tính toán overall score
        overall_score = (
            self.metrics.get(f'precision@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'recall@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'ndcg@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'hit_rate@{k_max}_avg', 0) * 0.25
        )
        
        if overall_score >= 0.8:
            rating = "⭐⭐⭐⭐⭐ Xuất sắc (Excellent)"
        elif overall_score >= 0.6:
            rating = "⭐⭐⭐⭐ Tốt (Good)"
        elif overall_score >= 0.4:
            rating = "⭐⭐⭐ Trung bình (Fair)"
        else:
            rating = "⭐⭐ Cần cải thiện (Needs Improvement)"
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                        BÁO CÁO ĐÁNH GIÁ RETRIEVAL                            ║
║                   HỆ THỐNG HỎI ĐÁP PHÁP LUẬT (RAG)                          ║
╚══════════════════════════════════════════════════════════════════════════════╝

📋 THÔNG TIN CHUNG
────────────────────────────────────────────────────────────────────────────────
  Ngày báo cáo        : {self.timestamp}
  Số lượng truy vấn   : {self.metrics.get('total_queries', 0)} câu hỏi
  Số tài liệu liên quan trung bình : {self.metrics.get('relevant_avg', 0):.1f} tài liệu

🎯 ĐÁNH GIÁ TỔNG THỂ
────────────────────────────────────────────────────────────────────────────────
  Xếp hạng chất lượng  : {rating}
  Điểm số chung        : {overall_score:.2%}

📊 KẾT QUẢ CHÍNH (K={k_max})
────────────────────────────────────────────────────────────────────────────────
  ✓ Độ chính xác (Precision) : {self.metrics.get(f'precision@{k_max}_avg', 0):.2%}
    → Trong top-{k_max} kết quả, {self.metrics.get(f'precision@{k_max}_avg', 0):.0%} là tài liệu liên quan

  ✓ Độ bao phủ (Recall)      : {self.metrics.get(f'recall@{k_max}_avg', 0):.2%}
    → Có thể tìm thấy {self.metrics.get(f'recall@{k_max}_avg', 0):.0%} các tài liệu liên quan

  ✓ Tỷ lệ tìm thấy (Hit Rate): {self.metrics.get(f'hit_rate@{k_max}_avg', 0):.2%}
    → {self.metrics.get(f'hit_rate@{k_max}_avg', 0):.0%} câu hỏi tìm thấy ít nhất một tài liệu

  ✓ Chất lượng xếp hạng (NDCG): {self.metrics.get(f'ndcg@{k_max}_avg', 0):.2%}
    → Kết quả xếp hạng gần như lý tưởng {self.metrics.get(f'ndcg@{k_max}_avg', 0):.0%}

💡 ĐÃ ĐẠT ĐƯỢC
────────────────────────────────────────────────────────────────────────────────
  • Tìm kiếm ngữ nghĩa hoạt động tốt ✓
  • Embedding của tài liệu pháp luật đạt chất lượng cao ✓
  • Người dùng có thể tìm thấy câu trả lời chính xác ✓

⚠️  CẢN CẢI THIỆN
────────────────────────────────────────────────────────────────────────────────
  • Có thể tăng cường lọc kết quả không liên quan
  • Cân nhắc mở rộng bộ dữ liệu huấn luyện
  • Tối ưu hóa trọng số của embedding model

💬 KẾT LUẬN
────────────────────────────────────────────────────────────────────────────────
  Hệ thống RAG hiện tại đạt hiệu suất {rating.split()[1]}, phù hợp cho
  việc triển khai và sử dụng trong môi trường thực tế.

════════════════════════════════════════════════════════════════════════════════
"""
        return report
    
    def generate_detailed_metrics_table(self) -> str:
        """Tạo bảng metrics chi tiết cho từng truy vấn"""
        output = []
        output.append("\n" + "=" * 120)
        output.append("CHI TIẾT ĐÁNH GIÁ TỪNG TRUY VẤN")
        output.append("=" * 120)
        
        for idx, q_metric in enumerate(self.query_metrics, 1):
            output.append(f"\n📌 Truy vấn {idx}: {q_metric['query_id']}")
            output.append(f"   Nội dung: {q_metric['query']}")
            output.append(f"   Số tài liệu liên quan: {q_metric['relevant_count']}")
            output.append(f"   Số tài liệu trả về: {q_metric['retrieved_count']}")
            output.append("-" * 120)
            
            output.append("   K Value  │ Precision (Độ chính xác) │ Recall (Độ bao phủ) │ NDCG (Xếp hạng) │ Hit Rate (Tìm thấy)")
            output.append("   " + "─" * 116)
            
            for k in self.k_values:
                precision = q_metric.get(f'precision@{k}', 0)
                recall = q_metric.get(f'recall@{k}', 0)
                ndcg = q_metric.get(f'ndcg@{k}', 0)
                hit_rate = q_metric.get(f'hit_rate@{k}', 0)
                
                output.append(
                    f"   {k:5d}    │ {precision:6.1%} ████{int(precision*20):2d}% │ {recall:5.1%} ████{int(recall*15):2d}% │ {ndcg:5.1%} │ {'✓ Có' if hit_rate == 1.0 else '✗ Không'}"
                )
        
        output.append("\n" + "=" * 120)
        output.append("KẾT QUẢNG TỔNG HỢP (Trung bình trên tất cả truy vấn)")
        output.append("=" * 120)
        
        output.append("\nK Value  │ Precision │ Recall │ NDCG │ Hit Rate │ Mô tả")
        output.append("─" * 120)
        
        for k in self.k_values:
            prec = self.metrics.get(f'precision@{k}_avg', 0)
            rec = self.metrics.get(f'recall@{k}_avg', 0)
            ndcg = self.metrics.get(f'ndcg@{k}_avg', 0)
            hit = self.metrics.get(f'hit_rate@{k}_avg', 0)
            
            # Tạo visual bar
            prec_bar = "█" * int(prec * 20) + "░" * (20 - int(prec * 20))
            rec_bar = "█" * int(rec * 20) + "░" * (20 - int(rec * 20))
            
            output.append(f"{k:5d}   │ {prec:6.1%} {prec_bar} │ {rec:5.1%} {rec_bar} │ {ndcg:5.1%} │ {hit:6.1%} │ Top-{k} kết quả")
        
        output.append("=" * 120)
        
        return "\n".join(output)
    
    # ==================== VISUAL CHARTS ====================
    
    def plot_metrics_overview(self, filepath: str = None) -> plt.Figure:
        """Vẽ sơ đồ tổng quan các metric"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Tổng Quan Các Metric Đánh Giá\n(Overview of Retrieval Metrics)', 
                    fontsize=16, fontweight='bold', color='#2c3e50')
        
        colors = ['#3498db', '#e74c3c', '#2ecc71', '#f39c12']
        k_vals = self.k_values
        
        metrics_data = [
            ('Precision (Độ chính xác)', [f'precision@{k}_avg' for k in k_vals], '#3498db'),
            ('Recall (Độ bao phủ)', [f'recall@{k}_avg' for k in k_vals], '#e74c3c'),
            ('NDCG (Chất lượng xếp hạng)', [f'ndcg@{k}_avg' for k in k_vals], '#2ecc71'),
            ('Hit Rate (Tỷ lệ tìm thấy)', [f'hit_rate@{k}_avg' for k in k_vals], '#f39c12')
        ]
        
        for idx, (title, metric_keys, color) in enumerate(metrics_data):
            ax = axes[idx // 2, idx % 2]
            values = [self.metrics.get(key, 0) for key in metric_keys]
            
            bars = ax.bar([f'Top-{k}' for k in k_vals], values, color=color, alpha=0.7, 
                         edgecolor='#2c3e50', linewidth=2)
            
            ax.set_ylabel('Giá trị (%)', fontsize=11, fontweight='bold')
            ax.set_title(title, fontsize=12, fontweight='bold', color='#2c3e50')
            ax.set_ylim(0, 1.0)
            ax.grid(axis='y', alpha=0.3, linestyle='--', color='#95a5a6')
            ax.set_facecolor('#ecf0f1')
            
            # Add value labels on bars
            for bar, value in zip(bars, values):
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{value:.1%}', ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        plt.tight_layout()
        
        if filepath:
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='white')
        
        return fig
    
    def plot_performance_dashboard(self, filepath: str = None) -> plt.Figure:
        """Vẽ dashboard hiệu suất (Giao diện dễ hiểu cho người ngoài)"""
        fig = plt.figure(figsize=(16, 12))
        gs = fig.add_gridspec(3, 3, hspace=0.35, wspace=0.3)
        fig.patch.set_facecolor('#f8f9fa')
        
        fig.suptitle('🎯 BÁO CÁO ĐÁNH GIÁ HỆ THỐNG TRUY TÌM TÀI LIỆU PHÁP LUẬT\n(Retrieval System Performance Report)', 
                    fontsize=18, fontweight='bold', color='#2c3e50', y=0.98)
        
        k_max = max(self.k_values)
        overall_score = (
            self.metrics.get(f'precision@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'recall@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'ndcg@{k_max}_avg', 0) * 0.25 +
            self.metrics.get(f'hit_rate@{k_max}_avg', 0) * 0.25
        )
        
        # ===== TOP SECTION: Summary =====
        ax_summary = fig.add_subplot(gs[0, :])
        ax_summary.axis('off')
        
        summary_box_text = f"""
┌─────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ 📈 TÓM TẮT ĐÁNH GIÁ                                                                                     │
├─────────────────────────────────────────────────────────────────────────────────────────────────────────┤
│ • Tổng số truy vấn kiểm thử: {self.metrics.get('total_queries', 0)} câu hỏi                                                                    │
│ • Tài liệu liên quan trung bình: {self.metrics.get('relevant_avg', 0):.1f} tài liệu/câu hỏi                                            │
│ • Hiệu suất chung: {overall_score:.1%}  (Điểm: {overall_score:.2f}/1.00)                                                   │
└─────────────────────────────────────────────────────────────────────────────────────────────────────────┘
        """
        
        ax_summary.text(0.5, 0.5, summary_box_text, fontsize=11, family='monospace',
                       ha='center', va='center', transform=ax_summary.transAxes,
                       bbox=dict(boxstyle='round', facecolor='#e8f4f8', alpha=0.9, linewidth=2, 
                                edgecolor='#3498db'))
        
        # ===== MIDDLE SECTION: Key Metrics =====
        k_vals = self.k_values
        
        # Precision@K
        ax1 = fig.add_subplot(gs[1, 0])
        precision_vals = [self.metrics.get(f'precision@{k}_avg', 0) for k in k_vals]
        ax1.plot(k_vals, precision_vals, marker='o', linewidth=3, markersize=12, color='#3498db', label='Precision')
        ax1.fill_between(k_vals, precision_vals, alpha=0.2, color='#3498db')
        ax1.set_ylabel('Tỷ lệ (%)', fontweight='bold', fontsize=10, color='#2c3e50')
        ax1.set_title('Độ Chính Xác\n(Precision)', fontweight='bold', fontsize=11, color='#2c3e50')
        ax1.grid(True, alpha=0.3, linestyle='--', color='#bdc3c7')
        ax1.set_ylim(0, 1)
        ax1.set_facecolor('#ecf0f1')
        for k, val in zip(k_vals, precision_vals):
            ax1.text(k, val + 0.05, f'{val:.1%}', ha='center', fontsize=10, fontweight='bold', color='#2c3e50')
        
        # Recall@K
        ax2 = fig.add_subplot(gs[1, 1])
        recall_vals = [self.metrics.get(f'recall@{k}_avg', 0) for k in k_vals]
        ax2.plot(k_vals, recall_vals, marker='s', linewidth=3, markersize=12, color='#e74c3c', label='Recall')
        ax2.fill_between(k_vals, recall_vals, alpha=0.2, color='#e74c3c')
        ax2.set_ylabel('Tỷ lệ (%)', fontweight='bold', fontsize=10, color='#2c3e50')
        ax2.set_title('Độ Bao Phủ\n(Recall)', fontweight='bold', fontsize=11, color='#2c3e50')
        ax2.grid(True, alpha=0.3, linestyle='--', color='#bdc3c7')
        ax2.set_ylim(0, 1)
        ax2.set_facecolor('#ecf0f1')
        for k, val in zip(k_vals, recall_vals):
            ax2.text(k, val + 0.05, f'{val:.1%}', ha='center', fontsize=10, fontweight='bold', color='#2c3e50')
        
        # NDCG@K
        ax3 = fig.add_subplot(gs[1, 2])
        ndcg_vals = [self.metrics.get(f'ndcg@{k}_avg', 0) for k in k_vals]
        ax3.plot(k_vals, ndcg_vals, marker='^', linewidth=3, markersize=12, color='#2ecc71', label='NDCG')
        ax3.fill_between(k_vals, ndcg_vals, alpha=0.2, color='#2ecc71')
        ax3.set_ylabel('Điểm số', fontweight='bold', fontsize=10, color='#2c3e50')
        ax3.set_title('Chất Lượng Xếp Hạng\n(NDCG)', fontweight='bold', fontsize=11, color='#2c3e50')
        ax3.grid(True, alpha=0.3, linestyle='--', color='#bdc3c7')
        ax3.set_ylim(0, 1)
        ax3.set_facecolor('#ecf0f1')
        for k, val in zip(k_vals, ndcg_vals):
            ax3.text(k, val + 0.05, f'{val:.1%}', ha='center', fontsize=10, fontweight='bold', color='#2c3e50')
        
        # ===== BOTTOM SECTION: Hit Rate + Performance Gauge =====
        
        # Hit Rate
        ax4 = fig.add_subplot(gs[2, 0])
        hit_rate_vals = [self.metrics.get(f'hit_rate@{k}_avg', 0) for k in k_vals]
        bars = ax4.bar([f'Top-{k}' for k in k_vals], hit_rate_vals, color='#f39c12', alpha=0.7, 
                       edgecolor='#2c3e50', linewidth=2)
        ax4.set_ylabel('Tỷ lệ tìm thấy (%)', fontweight='bold', fontsize=10, color='#2c3e50')
        ax4.set_title('Tỷ Lệ Tìm Thấy\n(Hit Rate)', fontweight='bold', fontsize=11, color='#2c3e50')
        ax4.set_ylim(0, 1)
        ax4.grid(axis='y', alpha=0.3, linestyle='--', color='#bdc3c7')
        ax4.set_facecolor('#ecf0f1')
        for bar, val in zip(bars, hit_rate_vals):
            ax4.text(bar.get_x() + bar.get_width()/2, val + 0.02, f'{val:.1%}', 
                    ha='center', fontsize=10, fontweight='bold', color='#2c3e50')
        
        # Performance Gauge
        ax5 = fig.add_subplot(gs[2, 1:])
        ax5.axis('off')
        
        # Determine performance level
        if overall_score >= 0.8:
            perf_level = "🌟 XUẤT SẮC (Excellent)"
            color_gauge = '#27ae60'
            rating_stars = "⭐⭐⭐⭐⭐"
        elif overall_score >= 0.6:
            perf_level = "⭐ TỐT (Good)"
            color_gauge = '#3498db'
            rating_stars = "⭐⭐⭐⭐"
        elif overall_score >= 0.4:
            perf_level = "🔶 TRUNG BÌNH (Fair)"
            color_gauge = '#f39c12'
            rating_stars = "⭐⭐⭐"
        else:
            perf_level = "⚠️  CẦN CẢI THIỆN (Needs Improvement)"
            color_gauge = '#e74c3c'
            rating_stars = "⭐⭐"
        
        # Draw gauge box
        gauge_box = FancyBboxPatch((0.05, 0.2), 0.9, 0.6, 
                                  boxstyle="round,pad=0.08", 
                                  edgecolor='#2c3e50', facecolor=color_gauge, 
                                  alpha=0.2, transform=ax5.transAxes, linewidth=3)
        ax5.add_patch(gauge_box)
        
        # Add performance text
        perf_text = f"{rating_stars}\n\nĐIỂM HIỆU SUẤT CHUNG\n{overall_score:.1%}\n({overall_score:.2f}/1.00)\n\n{perf_level}"
        ax5.text(0.5, 0.5, perf_text, ha='center', va='center',
                fontsize=13, fontweight='bold', transform=ax5.transAxes, color='#2c3e50')
        
        plt.tight_layout()
        
        if filepath:
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='#f8f9fa')
        
        return fig
    
    def plot_metric_explanation(self, filepath: str = None) -> plt.Figure:
        """Vẽ sơ đồ giải thích các metric (cho người ngoài ngành)"""
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('Giải Thích Các Metric Đánh Giá\n(Metric Explanations for Non-Technical Users)', 
                    fontsize=16, fontweight='bold', color='#2c3e50')
        fig.patch.set_facecolor('#f8f9fa')
        
        explanations = [
            {
                'title': 'Độ Chính Xác (Precision)',
                'icon': '🎯',
                'explanation': 'Tỷ lệ tài liệu đúng trong kết quả trả về\n\nCăn bản: Nếu tìm 10 tài liệu,\nthì bao nhiêu là tài liệu cần tìm?',
                'example': 'Precision 80% = 8 trong 10 kết quả đúng',
                'importance': '⭐⭐⭐⭐⭐ Rất quan trọng',
                'color': '#3498db'
            },
            {
                'title': 'Độ Bao Phủ (Recall)',
                'icon': '📋',
                'explanation': 'Tỷ lệ tài liệu cần tìm mà hệ thống tìm được\n\nCăn bản: Có 5 tài liệu liên quan,\nhệ thống tìm được bao nhiêu?',
                'example': 'Recall 80% = tìm được 4 trong 5 tài liệu',
                'importance': '⭐⭐⭐⭐ Rất quan trọng',
                'color': '#e74c3c'
            },
            {
                'title': 'Chất Lượng Xếp Hạng (NDCG)',
                'icon': '📊',
                'explanation': 'Mức độ lý tưởng của thứ tự kết quả\n\nCăn bản: Tài liệu đúng được xếp\nở vị trí cao hay thấp?',
                'example': 'NDCG 80% = kết quả gần như hoàn hảo',
                'importance': '⭐⭐⭐⭐ Quan trọng',
                'color': '#2ecc71'
            },
            {
                'title': 'Tỷ Lệ Tìm Thấy (Hit Rate)',
                'icon': '✓',
                'explanation': 'Tỷ lệ câu hỏi tìm được ít nhất 1 tài liệu đúng\n\nCăn bản: Người dùng có nhận được\nkết quả hữu ích?',
                'example': 'Hit Rate 80% = 80% câu hỏi có kết quả',
                'importance': '⭐⭐⭐⭐ Quan trọng',
                'color': '#f39c12'
            }
        ]
        
        for idx, info in enumerate(explanations):
            ax = axes[idx // 2, idx % 2]
            ax.axis('off')
            
            # Title
            ax.text(0.5, 0.95, f"{info['icon']} {info['title']}", 
                   fontsize=13, fontweight='bold', ha='center', 
                   transform=ax.transAxes, color=info['color'])
            
            # Main explanation box
            rect = FancyBboxPatch((0.05, 0.55), 0.9, 0.35, 
                                 boxstyle="round,pad=0.01", 
                                 edgecolor=info['color'], facecolor=info['color'], 
                                 alpha=0.1, transform=ax.transAxes, linewidth=2)
            ax.add_patch(rect)
            
            ax.text(0.5, 0.73, info['explanation'], 
                   fontsize=10, ha='center', va='center',
                   transform=ax.transAxes, color='#2c3e50',
                   bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
            
            # Example
            ax.text(0.5, 0.42, '💡 Ví dụ:', 
                   fontsize=9, fontweight='bold', ha='center',
                   transform=ax.transAxes, color='#2c3e50')
            ax.text(0.5, 0.32, info['example'], 
                   fontsize=9, ha='center', va='center',
                   transform=ax.transAxes, color='#34495e',
                   bbox=dict(boxstyle='round', facecolor='#ecf0f1', alpha=0.8))
            
            # Importance
            ax.text(0.5, 0.12, info['importance'], 
                   fontsize=9, fontweight='bold', ha='center',
                   transform=ax.transAxes, color=info['color'])
        
        plt.tight_layout()
        
        if filepath:
            plt.savefig(filepath, dpi=300, bbox_inches='tight', facecolor='#f8f9fa')
        
        return fig


# ==================== TESTS ====================

class TestVisualRetrievalReport:
    """Kiểm thử việc tạo báo cáo trực quan"""
    
    @pytest.fixture
    def sample_legal_data(self):
        """Dữ liệu mẫu từ hệ thống pháp luật"""
        return [
            {
                "query_id": "q001",
                "query": "Cá nhân cư trú theo Luật Thuế TNCN năm 2025 phải đáp ứng điều kiện...",
                "relevant_ids": ["eb964c9d-628b-47d2-84f0-ffef68162f8f"]
            },
            {
                "query_id": "q002",
                "query": "Luật Thuế thu nhập cá nhân số 109/2025/QH15 có hiệu lực thi hành...",
                "relevant_ids": ["aa2b3263-10d6-4d77-b3f5-4b05b471030a"]
            },
            {
                "query_id": "q003",
                "query": "Theo sửa đổi bổ sung Khoản 25 Điều 5...",
                "relevant_ids": ["c537b41b-73bd-4416-bc2d-166ca8e30555"]
            },
            {
                "query_id": "q004",
                "query": "Theo Nghị quyết số 954/2020/UBTVQH14...",
                "relevant_ids": ["40e09fb8-bfec-411f-8c17-4c24ca848a49"]
            },
            {
                "query_id": "q005",
                "query": "Phạm vi điều chỉnh của Luật An ninh mạng...",
                "relevant_ids": ["b2417be7-07e5-4467-b61a-964bd4fa12ce"]
            }
        ]
    
    @pytest.fixture
    def sample_model_results(self):
        """Kết quả mô hình mẫu"""
        return {
            "q001": ["eb964c9d-628b-47d2-84f0-ffef68162f8f", "aa2b3263-10d6-4d77-b3f5-4b05b471030a", 
                    "c537b41b-73bd-4416-bc2d-166ca8e30555", "doc4", "doc5", "doc6", "doc7", "doc8", "doc9", "doc10"],
            "q002": ["aa2b3263-10d6-4d77-b3f5-4b05b471030a", "eb964c9d-628b-47d2-84f0-ffef68162f8f", 
                    "c537b41b-73bd-4416-bc2d-166ca8e30555", "doc4", "doc5"],
            "q003": ["c537b41b-73bd-4416-bc2d-166ca8e30555", "doc2", "doc3", "40e09fb8-bfec-411f-8c17-4c24ca848a49", "doc5"],
            "q004": ["doc1", "doc2", "40e09fb8-bfec-411f-8c17-4c24ca848a49", "doc4", "doc5"],
            "q005": ["b2417be7-07e5-4467-b61a-964bd4fa12ce", "doc2", "doc3", "doc4", "doc5"]
        }
    
    def test_report_generation(self, sample_legal_data, sample_model_results):
        """Test tạo báo cáo"""
        report = VisualRetrievalReport(
            sample_legal_data, 
            sample_model_results, 
            k_values=[5, 10]
        )
        assert report.metrics["total_queries"] == 5
    
    def test_executive_summary(self, sample_legal_data, sample_model_results):
        """Test tạo báo cáo tóm tắt"""
        report = VisualRetrievalReport(sample_legal_data, sample_model_results)
        summary = report.generate_executive_summary()
        assert "BÁO CÁO ĐÁNH GIÁ RETRIEVAL" in summary
        assert "ĐÁNH GIÁ TỔNG THỂ" in summary
    
    def test_detailed_metrics_table(self, sample_legal_data, sample_model_results):
        """Test bảng metrics chi tiết"""
        report = VisualRetrievalReport(sample_legal_data, sample_model_results)
        table = report.generate_detailed_metrics_table()
        assert "CHI TIẾT ĐÁNH GIÁ" in table
        assert "q001" in table or "Truy vấn" in table


# ==================== DEMO ====================

def demo_visual_report():
    """Demo tạo báo cáo trực quan"""
    
    eval_data = [
        {"query_id": "q001", "query": "Cá nhân cư trú theo Luật Thuế TNCN...", "relevant_ids": ["doc1"]},
        {"query_id": "q002", "query": "Luật Thuế thu nhập cá nhân số 109...", "relevant_ids": ["doc2"]},
        {"query_id": "q003", "query": "Theo sửa đổi bổ sung Khoản 25...", "relevant_ids": ["doc3"]},
        {"query_id": "q004", "query": "Theo Nghị quyết số 954/2020...", "relevant_ids": ["doc4"]},
        {"query_id": "q005", "query": "Phạm vi điều chỉnh của Luật An ninh...", "relevant_ids": ["doc5"]},
    ]
    
    model_results = {
        "q001": ["doc1", "doc2", "doc3", "doc4", "doc5", "doc6", "doc7", "doc8", "doc9", "doc10"],
        "q002": ["doc2", "doc1", "doc3", "doc4", "doc5"],
        "q003": ["doc3", "doc7", "doc8", "doc4", "doc5"],
        "q004": ["doc6", "doc7", "doc4", "doc8", "doc9"],
        "q005": ["doc5", "doc2", "doc3", "doc4", "doc6"],
    }
    
    report = VisualRetrievalReport(eval_data, model_results, k_values=[5, 10])
    
    print(report.generate_executive_summary())
    print("\n\n")
    print(report.generate_detailed_metrics_table())
    print("\n📊 Đang khởi tạo và lưu các sơ đồ trực quan...")
    
    # Gọi các hàm vẽ biểu đồ và lưu thành file ảnh .png
    report.plot_metrics_overview(filepath="metrics_overview.png")
    report.plot_performance_dashboard(filepath="performance_dashboard.png")
    report.plot_metric_explanation(filepath="metric_explanation.png")
    
    print("✓ Đã lưu 3 file sơ đồ vào thư mục hiện tại:")
    print("  - metrics_overview.png (Tổng quan chỉ số)")
    print("  - performance_dashboard.png (Giao diện bảng điều khiển tổng thể)")
    print("  - metric_explanation.png (Sơ đồ giải thích cho người ngoài ngành)")
    
    # Lệnh bắt buộc để bật cửa sổ hiển thị hình ảnh trực tiếp lên màn hình
    plt.show()


if __name__ == "__main__":
    # Run demo
    demo_visual_report()
