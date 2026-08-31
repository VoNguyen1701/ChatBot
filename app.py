# app.py
# Flask app chính, xử lý API chat, lịch sử, nguồn trích dẫn và admin
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, timedelta
import os

from src.processing.searching import semantic_search
from src.ai.chat import ask_llm
from src.storage.mongo import get_db

app = Flask(__name__)
app.secret_key = "legal-docs-session-key-2026"


def normalize_document(doc):
    metadata = doc.get("metadata") or {}
    is_active = metadata.get("is_active", doc.get("is_active", True))
    uploaded_at = doc.get("updated_at") or doc.get("created_at") or doc.get("upload_date") or datetime.utcnow()
    if hasattr(uploaded_at, "isoformat"):
        uploaded_at_str = uploaded_at.isoformat()
    else:
        uploaded_at_str = str(uploaded_at)

    return {
        "doc_id": str(doc.get("_id") or doc.get("doc_id") or ""),
        "file_name": doc.get("file_name") or doc.get("filename") or doc.get("name") or "Unknown",
        "document_number": metadata.get("document_number") or doc.get("document_number") or "",
        "document_type": metadata.get("document_type") or doc.get("document_type") or doc.get("type") or "",
        "is_active": bool(is_active),
        "uploaded_at": uploaded_at_str,
        "size": int(doc.get("file_size") or doc.get("size") or 0),
        "status": doc.get("processing_status") or metadata.get("processing_status") or doc.get("status") or "success",
        "pdf_path": doc.get("pdf_path") or doc.get("source_path") or "",
        "page_number": int(doc.get("page_number") or metadata.get("page_number") or 1) if str(doc.get("page_number") or metadata.get("page_number") or 1).strip() else 1,
    }


def get_current_history():
    history = session.get("chat_history", [])
    if not isinstance(history, list):
        history = []
    session["chat_history"] = history
    return history


def add_chat_history(entry):
    history = get_current_history()
    history.append(entry)
    session["chat_history"] = history


def group_history_by_time(history):
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)

    groups = {
        "today": [],
        "week": [],
        "month": [],
    }

    for item in history:
        try:
            ts = item.get("timestamp")
            dt = datetime.fromisoformat(ts) if isinstance(ts, str) else datetime.utcnow()
        except Exception:
            dt = datetime.utcnow()

        if dt >= today:
            groups["today"].append(item)
        elif dt >= week_start:
            groups["week"].append(item)
        elif dt >= month_start:
            groups["month"].append(item)

    return {
        "today": {"label": "Hôm nay", "items": groups["today"]},
        "week": {"label": "Tuần trước", "items": groups["week"]},
        "month": {"label": "Tháng trước", "items": groups["month"]},
    }


def safe_source_url(doc_id, page_number=1):
    return f"/source/{doc_id}?page={int(page_number or 1)}"


@app.route("/")
@app.route("/chat")
def home():
    return render_template("chat.html", page="chat")


@app.route("/documents")
def personal_documents():
    return render_template("chat.html", page="documents")


@app.route("/admin")
def admin_page():
    return render_template("chat.html", page="admin")


@app.route("/source/<doc_id>")
def source_view(doc_id):
    db = get_db()
    document = db["documents"].find_one({"_id": doc_id}) or db["documents"].find_one({"doc_id": doc_id})
    page_number = int(request.args.get("page", 1) or 1)
    chunk = db["chunks"].find_one({"doc_id": doc_id})
    source_text = chunk.get("content") if chunk else (document.get("content") if document else "")

    if not document and not chunk:
        return render_template("source_view.html", document=None, error="Không tìm thấy tài liệu", page_number=page_number)

    context = {
        "document": document or {"_id": doc_id, "file_name": doc_id},
        "source_text": source_text,
        "page_number": page_number,
        "pdf_path": document.get("pdf_path") if document else "",
        "meta": (document or {}).get("metadata", {}) if document else {},
    }
    return render_template("source_view.html", **context, error=None)


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        payload = request.get_json(silent=True) or {}
        question = (payload.get("question") or "").strip()
        top_k = int(payload.get("top_k", 5) or 5)

        if not question:
            return jsonify({"error": "Question cannot be empty"}), 400

        results = semantic_search(question, top_k=top_k)
        results = [
            (score, doc) for score, doc in results
            if (doc.get("is_active") is not False) and (doc.get("metadata", {}).get("is_active") is not False)
        ]

        if not results:
            response_payload = {
                "response": "Không tìm thấy thông tin liên quan trong cơ sở tài liệu phù hợp",
                "citations": [],
                "num_retrieved": 0,
                "timestamp": datetime.utcnow().isoformat(),
            }
            add_chat_history({"question": question, "response": response_payload["response"], "citations": [], "timestamp": response_payload["timestamp"]})
            return jsonify(response_payload)

        top1 = float(results[0][0])
        top5 = float(results[min(4, len(results) - 1)][0])
        gap = top1 - top5

        if top1 < 0.60 or gap < 0.05:
            response_payload = {
                "response": "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu.",
                "citations": [],
                "num_retrieved": len(results),
                "timestamp": datetime.utcnow().isoformat(),
            }
            add_chat_history({"question": question, "response": response_payload["response"], "citations": [], "timestamp": response_payload["timestamp"]})
            return jsonify(response_payload)

        context_list = []
        citations = []
        for idx, (score, doc) in enumerate(results[:5], 1):
            content = str(doc.get("content") or "")
            if content:
                context_list.append(content)

            page_number = int(doc.get("page_number") or doc.get("metadata", {}).get("page_number") or 1)
            clause_label = doc.get("section_title") or doc.get("document_type") or "Tài liệu pháp lý"
            citations.append({
                "id": idx,
                "section_title": clause_label,
                "doc_id": str(doc.get("doc_id") or "N/A"),
                "content_preview": content[:200] + ("..." if len(content) > 200 else ""),
                "similarity_score": round(float(score), 4),
                "source_label": f"AI trích xuất từ \"{doc.get('section_title') or 'Điều chưa xác định'}\"",
                "source_url": safe_source_url(str(doc.get("doc_id") or ""), page_number),
                "page_number": page_number,
            })

        context = "\n---\n".join(context_list)
        answer = ask_llm(question, context)
        payload_response = {
            "response": answer,
            "citations": citations,
            "num_retrieved": len(results),
            "timestamp": datetime.utcnow().isoformat(),
        }
        add_chat_history({"question": question, "response": answer, "citations": citations, "timestamp": payload_response["timestamp"]})
        return jsonify(payload_response)

    except Exception as exc:
        print(f"[ERROR /api/chat]: {exc}")
        return jsonify({"error": str(exc)}), 500


@app.route("/api/history", methods=["GET"])
def api_history():
    history = get_current_history()
    return jsonify({
        "history": history,
        "groups": group_history_by_time(history),
    })


@app.route("/api/clear-history", methods=["POST"]) 
def clear_history():
    session["chat_history"] = []
    return jsonify({"status": "ok"})


@app.route("/api/export", methods=["POST"]) 
def export_chat():
    return jsonify({"session_id": session.get("session_id", "guest"), "chats": get_current_history()})


@app.route("/api/admin/dashboard", methods=["GET"]) 
def admin_dashboard_api():
    db = get_db()
    doc_total = db["documents"].count_documents({}) if "documents" in db.list_collection_names() else 0
    chunk_total = db["chunks"].count_documents({}) if "chunks" in db.list_collection_names() else 0
    question_total = sum(1 for _ in get_current_history())

    docs = list(db["documents"].find({}).sort("updated_at", -1)) if "documents" in db.list_collection_names() else []
    table_rows = [normalize_document(doc) for doc in docs]
    active_count = sum(1 for row in table_rows if row.get("is_active") is not False)
    inactive_count = sum(1 for row in table_rows if row.get("is_active") is False)
    success_count = sum(1 for row in table_rows if row.get("status") == "success")
    processing_count = sum(1 for row in table_rows if row.get("status") == "processing")
    error_count = sum(1 for row in table_rows if row.get("status") == "error")

    return jsonify({
        "summary": {
            "question_count": question_total,
            "document_count": doc_total,
            "chunk_count": chunk_total,
            "active_document_count": active_count,
            "inactive_document_count": inactive_count,
            "today_upload_count": sum(1 for row in table_rows if row.get("uploaded_at", "")[:10] == datetime.utcnow().strftime("%Y-%m-%d")),
            "success_count": success_count,
            "processing_count": processing_count,
            "error_count": error_count,
        },
        "documents": table_rows,
    })


@app.route("/api/admin/stats", methods=["GET"])
def get_stats():
    db = get_db()
    doc_total = db["documents"].count_documents({}) if "documents" in db.list_collection_names() else 0
    chunk_total = db["chunks"].count_documents({}) if "chunks" in db.list_collection_names() else 0

    docs = list(db["documents"].find({})) if "documents" in db.list_collection_names() else []
    status_counts = {"success": 0, "processing": 0, "error": 0}
    for doc in docs:
        status = (doc.get("processing_status") or doc.get("status") or "success").lower()
        if status in status_counts:
            status_counts[status] += 1

    return jsonify({
        "total_docs": doc_total,
        "total_chunks": chunk_total,
        "questions_today": 0,
        "avg_latency": 1.05,
        "status_counts": status_counts,
    })


@app.route("/api/admin/documents", methods=["GET"])
def get_documents():
    db = get_db()
    if "documents" not in db.list_collection_names():
        return jsonify({"documents": []})

    search = request.args.get("search", "").strip()
    status = request.args.get("status", "").strip()
    document_type = request.args.get("type", "").strip()

    query = {}
    if search:
        regex = {"$regex": search, "$options": "i"}
        query["$or"] = [
            {"file_name": regex},
            {"filename": regex},
            {"document_number": regex},
            {"metadata.document_number": regex},
            {"metadata.document_type": regex},
            {"document_type": regex},
            {"name": regex},
        ]
    if status == "active":
        query["$and"] = [{"$or": [{"is_active": {"$ne": False}}, {"metadata.is_active": {"$ne": False}}]}]
    elif status == "inactive":
        query["$or"] = [{"is_active": False}, {"metadata.is_active": False}]
    if document_type:
        qtype = {"$regex": document_type, "$options": "i"}
        query["$and"] = query.get("$and", []) + [{"$or": [{"document_type": qtype}, {"metadata.document_type": qtype}, {"type": qtype}]}]

    docs = list(db["documents"].find(query).sort("updated_at", -1))
    return jsonify({"documents": [normalize_document(doc) for doc in docs]})


@app.route("/api/admin/upload", methods=["POST"]) 
def upload_document():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    db = get_db()
    record = {
        "file_name": file.filename,
        "filename": file.filename,
        "name": file.filename,
        "document_type": request.form.get("docType", "Thông tư"),
        "document_number": request.form.get("documentNumber", ""),
        "type": request.form.get("docType", "Thông tư"),
        "processing_status": "processing",
        "status": "processing",
        "is_active": True,
        "metadata": {
            "document_type": request.form.get("docType", "Thông tư"),
            "document_number": request.form.get("documentNumber", ""),
            "is_active": True,
            "processing_status": "processing"
        },
        "upload_date": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow(),
        "size": int(file.content_length or 0),
        "pdf_path": "",
    }
    res = db["documents"].insert_one(record)
    return jsonify({"success": True, "doc_id": str(res.inserted_id), "message": "Document uploaded successfully"}), 201


@app.route("/api/admin/documents/<doc_id>/status", methods=["PATCH"]) 
def update_document_status(doc_id):
    db = get_db()
    payload = request.get_json(silent=True) or {}
    is_active = bool(payload.get("is_active", True))
    update = {
        "$set": {
            "is_active": is_active,
            "metadata.is_active": is_active,
            "updated_at": datetime.utcnow(),
            "processing_status": "success" if is_active else "error",
            "status": "success" if is_active else "error",
        }
    }
    db["documents"].update_many({"_id": doc_id}, update)
    db["chunks"].update_many({"doc_id": doc_id}, {"$set": {"is_active": is_active, "metadata.is_active": is_active}})
    return jsonify({"status": "ok", "doc_id": doc_id, "is_active": is_active})


@app.route("/api/admin/documents/<doc_id>", methods=["DELETE"]) 
def delete_document(doc_id):
    db = get_db()
    db["chunks"].delete_many({"doc_id": doc_id})
    db["documents"].delete_one({"_id": doc_id})
    return jsonify({"status": "ok", "doc_id": doc_id})


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)