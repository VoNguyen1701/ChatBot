ai_pdf_system/
│
├── ai_env/
│
├── data/
│   ├── raw/
│        ├──law/
│             ├──HC1.pdf
│             ├──NG1.pdf
│        ├──school/
│
├── src/
│   ├── pdf/
│   │   ├── legal_parser.py    #Parse cấu trúc pháp lý + chunking + extract references
│   │   ├── simple_processor.py         #Điều phối toàn bộ pipeline + lưu MongoDB
│   │   ├── embedding.py
│   │   └── read_pdf.py       #Đọc PDF + clean text + metadata extraction
│
│   ├── processing/
│   │   └── chunker.py
│
│   ├── storage/
│   │   ├── mongo.py        # kết nối MongoDB
│   │   └── store.py        # lưu dữ liệu vào Mongo
│
│   ├── retrieval/
│   │   └── search.py
│
│   ├── ai/
│   │   ├── local_ai.py
│   │   └── cloud_ai.py
│
│   └── main.py
├──templates/
|   |--index
├──static/
│
├── requirements.txt
├── sd.md  # sơ đồ thư mục
└── README.md

ai\Scripts\activate 

Nguồn dữ liệu
   ↓
├── Dataset có sẵn (thuế, giáo dục...)
├── Upload PDF
└── Crawl web (optional)
        ↓
   Chunking
        ↓
   Embedding
        ↓
   Vector DB
        ↓
   RAG QA (Local vs Cloud)

   python -m src.processing.Link///  python src/processing/Link.py
   python src/pdf/embbeding.py
