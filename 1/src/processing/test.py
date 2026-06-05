import os
import sys
import json
from pathlib import Path
import matplotlib.pyplot as plt

# 1. Thiết lập Path để import được các module từ thư mục src
BASE_DIR = Path(__file__).parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Import hàm tìm kiếm thực tế của bạn và class vẽ báo cáo
from src.processing.searching import semantic_search
from src.processing.test_eval import VisualRetrievalReport
# Giả sử class VisualRetrievalReport của bạn nằm trong file báo cáo, bạn sửa lại đường dẫn import cho đúng:
# from src.evaluation.visual_report import VisualRetrievalReport 

# =============================================================================
# CHẠY ĐÁNH GIÁ THỰC TẾ
# =============================================================================
def run_real_evaluation():
    # Thử tìm file golden_dataset.json
    golden_data_path = BASE_DIR / "../../datasets/golden_dataset.json"
    if not golden_data_path.exists():
        print(f"❌ Không tìm thấy file dữ liệu chuẩn tại: {golden_data_path}")
        return

    print("📖 Đang đọc tập dữ liệu chuẩn golden_dataset.json...")
    with open(golden_data_path, "r", encoding="utf-8") as f:
        golden_data = json.load(f)
    
    print(f"✓ Đã nạp thành công {len(golden_data)} câu hỏi kiểm thử.")
    
    # Khởi tạo dictionary chứa kết quả tìm kiếm thực tế từ RAG
    real_model_results = {}
    
    print("\n🚀 Đang chạy thử nghiệm hệ thống Retrieval trên cơ sở dữ liệu thật...")
    # Lặp qua từng câu hỏi trong bộ dữ liệu chuẩn
    for item in golden_data:
        q_id = item["query_id"]
        query_text = item["query"]
        print(f"🔍 Đang truy vấn [{q_id}]: {query_text[:50]}...")
        # 1. Gọi hàm tìm kiếm thực tế của bạn
        search_results = semantic_search(query_text, top_k=10)
        
        # 2. Trích xuất CHÍNH XÁC trường chunk_id và chuẩn hóa chuỗi
        retrieved_ids = []
        for score, doc in search_results:
            # Lấy trường định danh tương ứng với trường được lưu trong relevant_ids của file Golden
            # Thông thường là chunk_id dạng UUID
            c_id = doc.get("chunk_id") or doc.get("_id") 
            
            if c_id:
                # Ép kiểu về chuỗi, xóa khoảng trắng thừa và đưa về dạng chữ thường (lowercase)
                retrieved_ids.append(str(c_id).strip().lower())
        
        # Lưu vào danh sách kết quả thực tế của mô hình
        real_model_results[q_id] = retrieved_ids

    # Chuẩn hóa luôn cả relevant_ids trong dữ liệu golden_data trước khi truyền vào Evaluator
    for item in golden_data:
        item["relevant_ids"] = [str(rid).strip().lower() for rid in item["relevant_ids"]]

    print("\n✅ Quá trình truy xuất hoàn tất. Đang tính toán chỉ số và dựng sơ đồ...")

    # 2. Đưa dữ liệu thật vào class báo cáo trực quan
    # Bạn cần đảm bảo class VisualRetrievalReport đã được import ở trên
    try:
        report = VisualRetrievalReport(
            eval_data=golden_data, 
            model_results=real_model_results, 
            k_values=[5, 10]
        )
        
        # In báo cáo văn bản ra terminal
        print("\n" + "="*80)
        print(" BÁO CÁO NĂNG LỰC RETRIEVAL THỰC TẾ")
        print("="*80)
        print(report.generate_executive_summary())
        print("\n")
        print(report.generate_detailed_metrics_table())
        
        # Vẽ và lưu biểu đồ thật
        print("\n📊 Đang vẽ đồ thị trực quan thực tế...")
        report.plot_performance_dashboard(filepath="rag_real_performance.png")
        report.plot_metrics_overview(filepath="rag_real_overview.png")
        
        print("✓ Đã xuất các file sơ đồ thực tế:")
        print("  - rag_real_performance.png")
        print("  - rag_real_overview.png")
        
        # Hiển thị biểu đồ lên màn hình
        plt.show()

    except NameError:
        print("⚠️ Lưu ý: Bạn cần copy class 'VisualRetrievalReport' vào file này hoặc import nó từ file báo cáo của bạn để vẽ được sơ đồ.")
        # Backup: Ghi kết quả thật ra file json để kiểm tra nếu chưa có class vẽ đồ thị
        with open("real_model_results.json", "w", encoding="utf-8") as out_f:
            json.dump(real_model_results, out_f, ensure_ascii=False, indent=2)
        print("✓ Đã tạm thời lưu kết quả chạy thật ra file 'real_model_results.json'")

if __name__ == "__main__":
    run_real_evaluation()