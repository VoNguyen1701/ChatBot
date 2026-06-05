ai_pdf_system/
│
├── ai_env/
│
├── data/
│   ├── raw/
│        ├──Thue/
│             ├──HC1.pdf
│             ├──NG1.pdf
│
│
├── datasets/
│     ├── build.py    
│     ├── chunk.py         
│     ├── build.json
│     └── golden_dataset.json       
│
├── src/
│   ├── pdf/
│   │   ├── legal_parser.py    #Parse cấu trúc pháp lý + chunking + extract references
│   │   ├── simple_processor.py         #Điều phối toàn bộ pipeline + lưu MongoDB
│   │   └── read_pdf.py       #Đọc PDF + clean text + metadata extraction
│   
│   ├── processing/
│   │   ├── embedding.py    #embedding lại tất cả chunks trong DB
│   │   ├── prompt.py         #Chức năng xây dựng prompt cho LLM dựa trên kết quả semantic search
│   │   └── rearching.py       #Tính cosine similarity giữa query và chunks đã embedding, trả về top_k
│
│   ├── embedding/ # MỤC NÀY TẠM THỜI ĐỂ ĐÓ KO DÙNG
│       ├── embedding_models.py   # Load model + tạo embedding
│       ├── vector_store.py        # Lưu MongoDB + FAISS
│       ├── retrieval.py           # Tìm kiếm và truy xuất
│       ├── evaluation.py         # Đánh giá kết quả: Precision, Recall, MRR, NDCG
│       ├── benchmark.py           #Chạy benchmark
│
│   ├── storage/
│   │   ├── mongo.py        # kết nối MongoDB
│   │   └── 
│
├──templates/
|   ├──chat.html
├──static/
|   ├──css/
|        ├──style.css
|   ├──js/
|        ├──app.js
│
├── requirements.txt
├── app.py     #Flask app chính, xử lý API chat và giao diện web
├── app_chat_ui.py     #Giao diện web
├── sd.md  # sơ đồ thư mục
└── README.md

ai\Scripts\activate 
python src/pdf/simple_processor.py    
python -m src.processing.embedding   
python reset_embedding.py
