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
│   │   └── read_pdf.py
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