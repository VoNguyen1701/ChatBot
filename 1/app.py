# app.py
# Flask app chính, xử lý API chat và giao diện web
from flask import Flask, render_template, request, jsonify
from datetime import datetime

from src.processing.searching import semantic_search
from src.ai.chat import ask_llm

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("chat.html")


@app.route("/api/chat", methods=["POST"])
def chat():
    
    try:
        question = request.json.get("question", "").strip()
        top_k = request.json.get("top_k", 5)
        
        if not question:
            return jsonify({"error": "Question cannot be empty"}), 400
        
        print(f"\n[API] Question: {question}")
        
        # 1. RETRIEVAL: Truy xuất chunks
        results = semantic_search(
            question,
            top_k=top_k
        )
        
        if not results:
            return jsonify({
                "response": "Không tìm thấy tài liệu phù hợp",
                "citations": [],
                "num_retrieved": 0,
                "timestamp": datetime.now().isoformat()
            })
        
        # 2. BUILD CONTEXT
        #context = "\n\n".join(
         #   [doc["content"] for score, doc in results]
        #)
        context = results[0][1]["content"]
        # 3. CALL LLM
        answer = ask_llm(question, context)
        
        # 4. PREPARE CITATIONS
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
        
        # 5. RETURN RESPONSE (format expected by app.js)
        return jsonify({
            "response": answer,  # ✓ app.js expects "response"
            "citations": citations,
            "num_retrieved": len(results),
            "timestamp": datetime.now().isoformat()
        })
        
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True)