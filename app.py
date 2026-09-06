# app.py
# Flask app chính, xử lý API chat và giao diện web
from flask import Flask, render_template, request, jsonify
from datetime import datetime
import os

from src.processing.searching import semantic_search
from src.ai.chat import ask_llm
from src.storage.mongo import get_db

app = Flask(__name__)


@app.route("/")
@app.route("/chat")
def home():
    return render_template("chat.html", page="chat")

# ĐANG LỖI CHỖ ADMIN NÀY
@app.route("/documents")
def personal_documents():
    return render_template("chat.html", page="documents")


@app.route("/admin")
def admin_page():
    return render_template("chat.html", page="admin")


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        question = request.json.get("question", "").strip()
        top_k = request.json.get("top_k", 5)

        if not question:
            return jsonify({"error": "Question cannot be empty"}), 400

        print(f"\n[API] Question: {question}")

        results = semantic_search(question, top_k=top_k)

        if not results:
            return jsonify({
                "response": "Không tìm thấy thông tin liên quan trong cơ sở tài liệu phù hợp",
                "citations": [],
                "num_retrieved": 0,
                "timestamp": datetime.now().isoformat()
            })

        top1 = float(results[0][0])
        top5 = float(results[min(4, len(results) - 1)][0])
        gap = top1 - top5

        print(f"[DEBUG] top1={top1:.4f}, gap={gap:.4f}")

        if top1 < 0.60 or gap < 0.05:
            return jsonify({
                "response": "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu.",
                "citations": [],
                "num_retrieved": len(results),
                "timestamp": datetime.now().isoformat()
            })

        context_list = []
        for score, doc in results:
            context_list.append(doc["content"])

        context = "\n---\n".join(context_list)
        answer = ask_llm(question, context)

        citations = []
        for i, (score, doc) in enumerate(results, 1):
            citations.append({
                "id": i,
                "section_title": doc.get("section_title", "N/A"),
                "doc_id": doc.get("doc_id", "N/A"),
                "content_preview": doc.get("content", "")[:200] + "...",
                "similarity_score": round(float(score), 4)
            })

        print(f"[API] Retrieved {len(results)} documents")
        print(f"[API] Created {len(citations)} citations")
        print(f"[API] Answer length: {len(answer)} chars")

        return jsonify({
            "response": answer,
            "citations": citations,
            "num_retrieved": len(results),
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/admin/documents")
def admin_documents():
    return render_template("admin_documents.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    return render_template("admin_dashboard.html")


@app.route("/admin/settings")
def admin_settings():
    return render_template("admin_settings.html")


@app.route("/api/admin/stats", methods=["GET"])
def get_stats():
    """Lấy thống kê thực tế từ CSDL MongoDB"""
    try:
        db = get_db()

        total_docs = db["documents"].count_documents({}) if "documents" in db.list_collection_names() else 0
        total_chunks = db["chunks"].count_documents({}) if "chunks" in db.list_collection_names() else 0

        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        questions_today = 0
        if "chat_history" in db.list_collection_names():
            questions_today = db["chat_history"].count_documents({
                "timestamp": {"$gte": today_start.isoformat()}
            })

        return jsonify({
            "total_docs": total_docs,
            "total_chunks": total_chunks,
            "questions_today": questions_today,
            "avg_latency": 1.05
        })
    except Exception as e:
        print(f"[ERROR /api/admin/stats]: {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/admin/documents", methods=["GET"])
def get_documents():
    """Lấy danh sách các tài liệu thực tế từ MongoDB"""
    try:
        db = get_db()
        if "documents" not in db.list_collection_names():
            return jsonify({"documents": []})

        documents = []
        for doc in db["documents"].find({}):
            if "_id" in doc:
                doc["_id"] = str(doc["_id"])
            documents.append(doc)

        return jsonify({"documents": documents})
    except Exception as e:
        print(f"[ERROR /api/admin/documents]: {str(e)}")
        return jsonify({"error": str(e)}), 500
@app.route("/api/admin/documents/<doc_id>/status", methods=["PATCH"])
def update_document_status(doc_id):
    try:
        data = request.get_json() or {}

        is_active = data.get("is_active")

        if not isinstance(is_active, bool):
            return jsonify({
                "error": "is_active phải là true hoặc false"
            }), 400

        db = get_db()

        result = db["documents"].update_one(
            {"_id": doc_id},
            {
                "$set": {
                    "is_active": is_active,
                    "updated_at": datetime.now()
                }
            }
        )

        if result.matched_count == 0:
            return jsonify({
                "error": "Không tìm thấy tài liệu"
            }), 404

        return jsonify({
            "success": True,
            "is_active": is_active
        })

    except Exception as e:
        print(f"[ERROR /api/admin/documents/status]: {str(e)}")
        return jsonify({"error": str(e)}), 500
@app.route("/api/admin/documents/<doc_id>", methods=["DELETE"])
def delete_document(doc_id):
    try:
        db = get_db()

        result = db["documents"].delete_one({
            "_id": doc_id
        })

        if result.deleted_count == 0:
            return jsonify({
                "error": "Không tìm thấy tài liệu"
            }), 404

        return jsonify({
            "success": True,
            "message": "Đã xóa tài liệu"
        })

    except Exception as e:
        print(f"[ERROR /api/admin/documents/delete]: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/upload", methods=["POST"])
def upload_document():
    """Xử lý upload tài liệu và lưu metadata vào MongoDB"""
    try:
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        doc_name = request.form.get('docName', file.filename)
        doc_type = request.form.get('docType', 'Unknown')
        issue_date = request.form.get('issueDate', '')

        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        db = get_db()
        doc_metadata = {
            "name": doc_name,
            "filename": file.filename,
            "type": doc_type,
            "issue_date": issue_date,
            "upload_date": datetime.now().isoformat(),
            "size": file.content_length or 0,
            "status": "processing"
        }

        result = db["documents"].insert_one(doc_metadata)
        print(f"[INFO] Document uploaded: {doc_name} (ID: {result.inserted_id})")

        return jsonify({
            "success": True,
            "message": "Document uploaded successfully",
            "doc_id": str(result.inserted_id)
        }), 201
    except Exception as e:
        print(f"[ERROR /api/admin/upload]: {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)