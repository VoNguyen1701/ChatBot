#!/usr/bin/env python
# -*- coding: utf-8 -*-
# app_chat_ui.py
# giao diện web
"""
╔═══════════════════════════════════════════════════════════════════════════════╗
║         LEGAL DOCUMENT CHAT UI - HỆ THỐNG TRUY VẤN TÀI LIỆU PHÁP LỤC           ║
║                      (Flask Web Application)                                  ║
║                                                                               ║
║  Ứng dụng web để tương tác với hệ thống truy xuất và trả lời các câu hỏi     ║
║  về tài liệu pháp lý bằng cách kết hợp retrieval vector + LLM (Qwen)         ║
║                                                                               ║
║  Các tính năng:                                                              ║
║  ✓ Chat interface thân thiện                                                 ║
║  ✓ Hiển thị kết quả retrieval + citation                                     ║
║  ✓ Streaming response từ Qwen                                                ║
║  ✓ Quản lý lịch sử chat                                                      ║
║  ✓ Export kết quả                                                            ║
╚═══════════════════════════════════════════════════════════════════════════════╝
"""

from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime
import uuid

# Setup path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from src.embedding.retrieval import Retriever
    from src.embedding.vector_store import VectorStore
    from src.embedding.embedding_models import EmbeddingModelManager
    from src.processing.prompt import build_prompt
    from src.ai.qwen import ask_qwen
    from src.storage.mongo import get_db
except ImportError as e:
    print(f"❌ Import error: {e}")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════
# FLASK INITIALIZATION
# ════════════════════════════════════════════════════════════════════════════

app = Flask(__name__)
app.secret_key = 'legal-document-retrieval-system-2024'
CORS(app)

# Global retrieval system
retrieval_system = None


def init_retrieval_system():
    """Khởi tạo hệ thống retrieval"""
    global retrieval_system
    
    print("[INIT] Đang khởi tạo hệ thống retrieval...")
    
    try:
        db = get_db()
        vector_store = VectorStore()
        model_manager = EmbeddingModelManager()
        model_manager.load_all_models()
        retriever = Retriever(vector_store, model_manager)
        
        retrieval_system = {
            "db": db,
            "retriever": retriever,
            "vector_store": vector_store,
            "chat_history": {}
        }
        
        print("✓ Hệ thống retrieval sẵn sàng")
        return True
        
    except Exception as e:
        print(f"❌ Lỗi khởi tạo: {e}")
        return False


# ════════════════════════════════════════════════════════════════════════════
# API ROUTES
# ════════════════════════════════════════════════════════════════════════════

@app.route('/')
def index():
    """Trang chủ - Chat interface"""
    return render_template('chat.html')


@app.route('/api/health', methods=['GET'])
def health_check():
    """Kiểm tra trạng thái hệ thống"""
    return jsonify({
        "status": "ok" if retrieval_system else "error",
        "message": "System is running" if retrieval_system else "System initialization failed"
    })


@app.route('/api/chat', methods=['POST'])
def chat():
    """
    ═══════════════════════════════════════════════════════════════
    ENDPOINT: POST /api/chat
    
    Xử lý câu hỏi người dùng:
    1. Truy xuất các chunk liên quan
    2. Xây dựng prompt với citation
    3. Gọi Qwen để trả lời
    4. Trả về kết quả với metadata
    ═══════════════════════════════════════════════════════════════
    """
    try:
        data = request.json
        question = data.get('question', '').strip()
        model_name = data.get('model', list(retrieval_system['vector_store'].faiss_indices.keys())[0])
        top_k = data.get('top_k', 5)
        
        if not question:
            return jsonify({"error": "Câu hỏi không được để trống"}), 400
        
        print(f"\n[QUERY] {question}")
        print(f"[MODEL] {model_name} | [TOP-K] {top_k}")
        
        # 1. RETRIEVAL: Truy xuất chunks liên quan
        retriever = retrieval_system['retriever']
        search_results = retriever.search_and_retrieve(question, model_name, k=top_k)
        
        # 2. PREPARE CITATIONS: Chuẩn bị citation data
        citations = []
        for i, chunk in enumerate(search_results, 1):
            citations.append({
                "id": i,
                "chunk_id": chunk.get('chunk_id', ''),
                "doc_id": chunk.get('doc_id', ''),
                "section_title": chunk.get('section_title', ''),
                "similarity_score": round(chunk.get('similarity_score', 0), 4),
                "content_preview": chunk.get('content', '')[:200] + "..."
            })
        
        # 3. BUILD PROMPT: Xây dựng prompt với context
        prompt = build_prompt(question)
        
        # 4. GET RESPONSE: Gọi Qwen để trả lời
        try:
            response = ask_qwen(prompt)
        except Exception as e:
            print(f"⚠️  Qwen error: {e}")
            response = "Xin lỗi, không thể kết nối tới Qwen LLM."
        
        # 5. PREPARE RESPONSE
        chat_id = str(uuid.uuid4())
        result = {
            "chat_id": chat_id,
            "question": question,
            "response": response,
            "model": model_name,
            "top_k": top_k,
            "citations": citations,
            "num_retrieved": len(search_results),
            "timestamp": datetime.now().isoformat()
        }
        
        # Store in chat history
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        
        session_id = session['session_id']
        if session_id not in retrieval_system['chat_history']:
            retrieval_system['chat_history'][session_id] = []
        
        retrieval_system['chat_history'][session_id].append(result)
        
        print(f"✓ Retrieved {len(search_results)} chunks")
        print(f"✓ Response ready")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/api/models', methods=['GET'])
def get_models():
    """Lấy danh sách các model embedding có sẵn"""
    try:
        models = list(retrieval_system['vector_store'].faiss_indices.keys())
        return jsonify({"models": models})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/history', methods=['GET'])
def get_history():
    """Lấy lịch sử chat của session hiện tại"""
    try:
        if 'session_id' not in session:
            return jsonify({"history": []})
        
        session_id = session['session_id']
        history = retrieval_system['chat_history'].get(session_id, [])
        
        return jsonify({"history": history})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/export', methods=['POST'])
def export_chat():
    """Export lịch sử chat thành JSON"""
    try:
        if 'session_id' not in session:
            return jsonify({"error": "No chat history"}), 400
        
        session_id = session['session_id']
        history = retrieval_system['chat_history'].get(session_id, [])
        
        export_data = {
            "session_id": session_id,
            "export_time": datetime.now().isoformat(),
            "num_chats": len(history),
            "chats": history
        }
        
        return jsonify(export_data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/clear-history', methods=['POST'])
def clear_history():
    """Xóa lịch sử chat"""
    try:
        if 'session_id' not in session:
            session['session_id'] = str(uuid.uuid4())
        
        session_id = session['session_id']
        if session_id in retrieval_system['chat_history']:
            retrieval_system['chat_history'][session_id] = []
        
        return jsonify({"status": "ok", "message": "Chat history cleared"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════════════════════
# ERROR HANDLERS
# ════════════════════════════════════════════════════════════════════════════

@app.errorhandler(404)
def not_found(error):
    """404 handler"""
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(error):
    """500 handler"""
    return jsonify({"error": "Server error"}), 500


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    """Entry point"""
    print("\n" + "╔" + "="*78 + "╗")
    print("║" + " "*20 + "LEGAL DOCUMENT CHAT UI" + " "*36 + "║")
    print("╚" + "="*78 + "╝\n")
    
    # Initialize retrieval system
    if not init_retrieval_system():
        print("❌ Initialization failed")
        sys.exit(1)
    
    print("\n" + "="*80)
    print("🚀 STARTING FLASK SERVER")
    print("="*80)
    print(f"📍 URL: http://localhost:5000")
    print(f"📍 API: http://localhost:5000/api")
    print("="*80 + "\n")
    
    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False
    )


if __name__ == '__main__':
    main()
