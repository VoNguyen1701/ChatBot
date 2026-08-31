# datasets/chunk.py
from pymongo import MongoClient
import json

client = MongoClient("mongodb://dungnguyet17012005_db_user:Dungnguyet17012005~@ac-hzf04zl-shard-00-00.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-01.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-02.bzpmnh4.mongodb.net:27017/?ssl=true&replicaSet=atlas-qutlkr-shard-0&authSource=admin&appName=Cluster0")
db = client["ai1_db"]

chunks = list(
    db.chunks.find(
        {},
        {
            "_id": 0
        }
    )
)

with open(
    "datasets/chunks.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        chunks,
        f,
        ensure_ascii=False,
        indent=2,
        default=str
    )