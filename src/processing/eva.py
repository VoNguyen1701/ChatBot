# =========================================================
# CONFIDENCE GATE
# =========================================================
#
# MỤC ĐÍCH:
#   Đánh giá mức độ tin cậy của kết quả Hybrid Retrieval
#   trước khi đưa dữ liệu cho LLM (Ollama) sinh câu trả lời.
#
# NHIỆM VỤ:
#   1. Lấy điểm Hybrid cao nhất (Top-1)
#   2. Lấy điểm Hybrid Top-2
#   3. Tính khoảng cách giữa Top-1 và Top-2
#   4. Phân loại kết quả thành:
#        - HIGH
#        - MEDIUM
#        - LOW
#        - REJECT
#   5. Quyết định có cho phép gọi LLM hay không.
#
# LƯU Ý:
#   Hybrid score hiện tại là điểm xếp hạng tương đối,
#   KHÔNG phải xác suất Top-1 đúng.
#
#   Vì vậy không được hiểu:
#       score = 0.90  → 90% chắc chắn đúng
#
#   Các ngưỡng bên dưới là ngưỡng BAN ĐẦU để tích hợp
#   và kiểm thử. Sau khi có thêm tập đánh giá sẽ hiệu chỉnh.
# =========================================================


# =========================================================
# CẤU HÌNH NGƯỠNG
# =========================================================

# Mức HIGH:
# Kết quả truy hồi có điểm rất cao.
HIGH_THRESHOLD = 0.90

# Mức MEDIUM:
# Có thể vẫn đủ thông tin để LLM xử lý,
# nhưng độ tin cậy thấp hơn HIGH.
MEDIUM_THRESHOLD = 0.75

# Mức LOW:
# Có kết quả nhưng chưa đủ tin cậy để tự động sinh câu trả lời.
LOW_THRESHOLD = 0.60


# =========================================================
# HÀM ĐÁNH GIÁ CONFIDENCE
# =========================================================

def evaluate_confidence(results):
    """
    Đánh giá mức độ tin cậy của kết quả Hybrid Retrieval.

    Parameters
    ----------
    results : list
        Danh sách kết quả Hybrid Retrieval:

        [
            (score, doc),
            (score, doc),
            ...
        ]

        Trong đó:
            score : Hybrid score
            doc   : thông tin chunk/document

    Returns
    -------
    dict
        Ví dụ:

        {
            "level": "HIGH",
            "allow_llm": True,
            "top1_score": 0.95,
            "top2_score": 0.60,
            "gap_top2": 0.35
        }
    """

    # -----------------------------------------------------
    # TRƯỜNG HỢP KHÔNG CÓ KẾT QUẢ
    # -----------------------------------------------------

    if not results:
        return {
            "level": "REJECT",
            "allow_llm": False,
            "top1_score": 0.0,
            "top2_score": 0.0,
            "gap_top2": 0.0
        }

    # -----------------------------------------------------
    # LẤY TOP-1
    # -----------------------------------------------------

    top1_score = float(results[0][0])

    # -----------------------------------------------------
    # LẤY TOP-2
    # -----------------------------------------------------

    if len(results) >= 2:
        top2_score = float(results[1][0])
    else:
        top2_score = 0.0

    # -----------------------------------------------------
    # TÍNH KHOẢNG CÁCH TOP-1 VÀ TOP-2
    # -----------------------------------------------------

    gap_top2 = top1_score - top2_score

    # -----------------------------------------------------
    # PHÂN LOẠI CONFIDENCE
    # -----------------------------------------------------

    if top1_score >= HIGH_THRESHOLD:

        level = "HIGH"
        allow_llm = True

    elif top1_score >= MEDIUM_THRESHOLD:

        level = "MEDIUM"
        allow_llm = True

    elif top1_score >= LOW_THRESHOLD:

        level = "LOW"
        allow_llm = False

    else:

        level = "REJECT"
        allow_llm = False

    # -----------------------------------------------------
    # TRẢ KẾT QUẢ
    # -----------------------------------------------------

    return {
        "level": level,
        "allow_llm": allow_llm,
        "top1_score": top1_score,
        "top2_score": top2_score,
        "gap_top2": gap_top2
    }


# =========================================================
# HÀM IN KẾT QUẢ
# =========================================================

def print_confidence(result):
    """
    In kết quả Confidence Gate ra terminal.
    """

    print("=" * 70)
    print("CONFIDENCE GATE")
    print("=" * 70)

    print(f"Level       : {result['level']}")
    print(f"Allow LLM   : {result['allow_llm']}")
    print(f"Top1 score  : {result['top1_score']:.4f}")
    print(f"Top2 score  : {result['top2_score']:.4f}")
    print(f"Gap Top2    : {result['gap_top2']:.4f}")

    print("=" * 70)


# =========================================================
# TEST MODULE
# =========================================================

if __name__ == "__main__":

    print()
    print("TEST 1 - HIGH")
    print("-" * 70)

    test_results_high = [
        (0.95, {"chunk_id": "A"}),
        (0.60, {"chunk_id": "B"}),
        (0.40, {"chunk_id": "C"})
    ]

    result = evaluate_confidence(test_results_high)
    print_confidence(result)


    print()
    print("TEST 2 - MEDIUM")
    print("-" * 70)

    test_results_medium = [
        (0.80, {"chunk_id": "A"}),
        (0.75, {"chunk_id": "B"}),
        (0.60, {"chunk_id": "C"})
    ]

    result = evaluate_confidence(test_results_medium)
    print_confidence(result)


    print()
    print("TEST 3 - LOW")
    print("-" * 70)

    test_results_low = [
        (0.65, {"chunk_id": "A"}),
        (0.60, {"chunk_id": "B"}),
        (0.55, {"chunk_id": "C"})
    ]

    result = evaluate_confidence(test_results_low)
    print_confidence(result)


    print()
    print("TEST 4 - REJECT")
    print("-" * 70)

    test_results_reject = [
        (0.45, {"chunk_id": "A"}),
        (0.40, {"chunk_id": "B"}),
        (0.35, {"chunk_id": "C"})
    ]

    result = evaluate_confidence(test_results_reject)
    print_confidence(result)


    print()
    print("TEST 5 - KHÔNG CÓ KẾT QUẢ")
    print("-" * 70)

    result = evaluate_confidence([])
    print_confidence(result)