# src/storage/mongo.py
from pymongo import MongoClient

def get_mongo_client(
    uri="mongodb://dungnguyet17012005_db_user:Dungnguyet17012005~@ac-hzf04zl-shard-00-00.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-01.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-02.bzpmnh4.mongodb.net:27017/?ssl=true&replicaSet=atlas-qutlkr-shard-0&authSource=admin&appName=Cluster0",
    db_name="ai_pdf_db"
):
    """
    Trả về collection để lưu PDF pages
    """
    client = MongoClient(uri)
    db = client[db_name]
    collection = db["pdf_pages"]
    return collection
