# app.py
# Flask app chính, xử lý API chat và giao diện web
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, session, url_for
from datetime import datetime
import os
import uuid
from werkzeug.security import check_password_hash, generate_password_hash

from src.processing.searching import semantic_search
from src.ai.chat import ask_llm
from src.storage.mongo import get_db

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-secret-key")


def current_user():
    return session.get("user")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Authentication required"}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user().get("role") != "admin":
            return jsonify({"error": "Admin access required"}), 403
        return view(*args, **kwargs)
    return wrapped


def configured_users():
    return {
        os.environ.get("APP_USER_USERNAME", "user"): {
            "password": os.environ.get("APP_USER_PASSWORD", "user"),
            "role": "user"
        },
        os.environ.get("APP_ADMIN_USERNAME", "admin"): {
            "password": os.environ.get("APP_ADMIN_PASSWORD", "admin"),
            "role": "admin"
        }
    }


def find_registered_user(username):
    try:
        return get_db()["users"].find_one({"username": username})
    except Exception as error:
        print(f"[WARN] Could not read users: {error}")
        return None


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        username = data.get("username", "").strip()
        password = data.get("password", "")
        account = configured_users().get(username)
        registered_account = None if account else find_registered_user(username)
        valid_password = (
            account and account["password"] == password
        ) or (
            registered_account and check_password_hash(
                registered_account["password_hash"], password
            )
        )
        if not valid_password:
            return jsonify({"error": "Tên đăng nhập hoặc mật khẩu không đúng"}), 401
        role = account["role"] if account else registered_account.get("role", "user")
        session["user"] = {"username": username, "role": role}
        session.setdefault("conversation_id", str(uuid.uuid4()))
        return jsonify({"user": session["user"]})
    if current_user():
        return redirect(url_for("home"))
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form
        username = data.get("username", "").strip()
        password = data.get("password", "")
        confirm_password = data.get("confirm_password", "")

        if len(username) < 3:
            return jsonify({"error": "Tên đăng nhập phải có ít nhất 3 ký tự"}), 400
        if len(password) < 6:
            return jsonify({"error": "Mật khẩu phải có ít nhất 6 ký tự"}), 400
        if password != confirm_password:
            return jsonify({"error": "Mật khẩu xác nhận không khớp"}), 400
        if username in configured_users() or find_registered_user(username):
            return jsonify({"error": "Tên đăng nhập đã tồn tại"}), 409

        try:
            get_db()["users"].insert_one({
                "username": username,
                "password_hash": generate_password_hash(password),
                "role": "user",
                "created_at": datetime.now().isoformat()
            })
        except Exception as error:
            print(f"[ERROR /register]: {error}")
            return jsonify({"error": "Không thể tạo tài khoản lúc này"}), 500

        return jsonify({"success": True, "message": "Đăng ký thành công"}), 201

    if current_user():
        return redirect(url_for("home"))
    return render_template("login.html", register_mode=True)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/me")
def me():
    user = current_user()
    if not user:
        return jsonify({"user": None}), 401
    return jsonify({"user": user})


def ensure_conversation():
    if "conversation_id" not in session:
        session["conversation_id"] = str(uuid.uuid4())
    return session["conversation_id"]


def save_chat_result(question, result):
    result["question"] = question
    result["conversation_id"] = ensure_conversation()
    result["user_id"] = current_user()["username"]
    try:
        get_db()["chat_history"].insert_one(dict(result))
    except Exception as error:
        print(f"[WARN] Could not save chat history: {error}")


@app.route("/")
@app.route("/chat")
@login_required
def home():
    return render_template("chat.html", page="chat")

@app.route("/documents")
@login_required
def personal_documents():
    return render_template("chat.html", page="documents")


@app.route("/admin")
@admin_required
def admin_page():
    return render_template("chat.html", page="admin")


@app.route("/api/chat", methods=["POST"])
@login_required
def chat():
    try:
        data = request.get_json(silent=True) or {}
        question = data.get("question", "").strip()
        top_k = data.get("top_k", 5)

        if not question:
            return jsonify({"error": "Question cannot be empty"}), 400

        print(f"\n[API] Question: {question}")

        results = semantic_search(question, top_k=top_k)

        if not results:
            result = {
                "response": "Không tìm thấy thông tin liên quan trong cơ sở tài liệu phù hợp",
                "citations": [],
                "num_retrieved": 0,
                "timestamp": datetime.now().isoformat()
            }
            save_chat_result(question, result)
            return jsonify(result)

        top1 = float(results[0][0])
        top5 = float(results[min(4, len(results) - 1)][0])
        gap = top1 - top5

        print(f"[DEBUG] top1={top1:.4f}, gap={gap:.4f}")

        retrieval_ok = False

        # Top 1 rất cao
        if top1 >= 0.70:
            retrieval_ok = True

        # Top 1 trung bình -> cần gap
        elif top1 >= 0.60 and gap >= 0.05:
            retrieval_ok = True

        if not retrieval_ok:
            print(
                "[RETRIEVAL] Confidence thấp -> không gọi LLM"
            )

            result = {
                "response": "Tôi không tìm thấy thông tin phù hợp trong cơ sở dữ liệu.",
                "citations": [],
                "num_retrieved": len(results),
                "timestamp": datetime.now().isoformat()
            }
            save_chat_result(question, result)
            return jsonify(result)

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

        result = {
            "response": answer,
            "citations": citations,
            "num_retrieved": len(results),
            "timestamp": datetime.now().isoformat()
        }
        save_chat_result(question, result)
        return jsonify(result)

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/history", methods=["GET"])
@login_required
def chat_history():
    conversation_id = request.args.get("conversation_id") or ensure_conversation()
    try:
        documents = get_db()["chat_history"].find(
            {
                "user_id": current_user()["username"],
                "conversation_id": conversation_id
            },
            {"_id": 0}
        ).sort("timestamp", 1)
        return jsonify({"history": list(documents), "conversation_id": conversation_id})
    except Exception as error:
        return jsonify({"history": [], "conversation_id": conversation_id, "error": str(error)})


@app.route("/api/conversations", methods=["GET"])
@login_required
def conversations():
    try:
        rows = get_db()["chat_history"].find(
            {"user_id": current_user()["username"]},
            {"_id": 0, "conversation_id": 1, "question": 1, "timestamp": 1}
        ).sort("timestamp", -1)
        result = []
        seen = set()
        for row in rows:
            conversation_id = row.get("conversation_id")
            if conversation_id and conversation_id not in seen:
                seen.add(conversation_id)
                result.append(row)
        return jsonify({"conversations": result})
    except Exception as error:
        return jsonify({"conversations": [], "error": str(error)})


@app.route("/api/conversations/new", methods=["POST"])
@login_required
def new_conversation():
    session["conversation_id"] = str(uuid.uuid4())
    return jsonify({"conversation_id": session["conversation_id"], "history": []})


@app.route("/api/export", methods=["POST"])
@login_required
def export_history():
    response = chat_history().json
    return jsonify({
        "conversation_id": response["conversation_id"],
        "export_time": datetime.now().isoformat(),
        "num_chats": len(response["history"]),
        "chats": response["history"]
    })


# ═════════════════════════════════════════════════════════════════════════════
# ADMIN ROUTES
# ═════════════════════════════════════════════════════════════════════════════

@app.route("/admin/documents")
@admin_required
def admin_documents():
    return render_template("admin_documents.html")


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    return render_template("admin_dashboard.html")


@app.route("/admin/settings")
@admin_required
def admin_settings():
    return render_template("admin_settings.html")


@app.route("/api/admin/stats", methods=["GET"])
@admin_required
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
@admin_required
def get_documents():
    try:
        db = get_db()

        if "documents" not in db.list_collection_names():
            return jsonify({"documents": []})

        documents = []

        for doc in db["documents"].find({}):

            metadata = doc.get("metadata", {}) or {}

            doc_id = (
                metadata.get("doc_id")
                or doc.get("_id")
                or ""
            )

            file_name = doc.get("file_name", "")

            document_number = metadata.get(
                "document_number", ""
            )

            document_type = metadata.get(
                "document_type", ""
            )

            title = metadata.get(
                "title", ""
            )

            issuer = metadata.get(
                "issuer", ""
            )

            issued_date = metadata.get(
                "issued_date", ""
            )

            category = doc.get(
                "category", ""
            )

            created_at = doc.get("created_at")

            if isinstance(created_at, datetime):
                uploaded_at = created_at.isoformat()
            else:
                uploaded_at = str(created_at or "")

            # Document cũ chưa có is_active
            # => mặc định là true
            is_active = doc.get("is_active", True)

            size = doc.get("size", 0) or 0

            documents.append({
                "doc_id": str(doc_id),
                "file_name": file_name,
                "document_number": document_number,
                "document_type": document_type,
                "title": title,
                "issuer": issuer,
                "issued_date": issued_date,
                "category": category,
                "uploaded_at": uploaded_at,
                "size": size,
                "is_active": bool(is_active)
            })
        search = request.args.get(
            "search",
            ""
        ).strip().lower()

        category_filter = request.args.get(
            "category",
            ""
        ).strip()

        type_filter = request.args.get(
            "type",
            ""
        ).strip()
        if search:
            documents = [
                doc
                for doc in documents
                if search in
                str(
                    doc["document_number"]
                ).lower()
            ]
        if category_filter:
            documents = [
                doc
                for doc in documents
                if doc["category"] ==
                category_filter
            ]
        if type_filter:
            documents = [
                doc
                for doc in documents
                if doc["document_type"] ==
                type_filter
            ]

        return jsonify({
            "documents": documents
        })

    except Exception as e:
        print("ERROR /api/admin/documents:", e)

        return jsonify({
            "error": str(e),
            "documents": []
        }), 500
@app.route("/api/admin/documents/<doc_id>/status", methods=["PATCH"])
@admin_required
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
@admin_required
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
@admin_required
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

@app.route("/api/admin/dashboard", methods=["GET"])
@admin_required
def admin_dashboard_api():
    try:
        db = get_db()

        if "documents" not in db.list_collection_names():
            return jsonify({
                "summary": {
                    "document_count": 0,
                    "category_count": 0,
                    "today_upload_count": 0
                }
            })

        collection = db["documents"]

        total = collection.count_documents({})

        categories = collection.distinct("category")

        category_count = len([
            category
            for category in categories
            if category and str(category).strip()
        ])

        today = datetime.now().date()

        today_upload_count = 0

        for doc in collection.find({}):

            created_at = doc.get("created_at")

            if isinstance(created_at, datetime):
                if created_at.date() == today:
                    today_upload_count += 1

        return jsonify({
            "summary": {
                "document_count": total,
                "category_count": category_count,
                "today_upload_count": today_upload_count
            }
        })

    except Exception as e:
        print("ERROR /api/admin/dashboard:", e)

        return jsonify({
            "error": str(e)
        }), 500

if __name__ == "__main__":
    app.run(debug=True)

