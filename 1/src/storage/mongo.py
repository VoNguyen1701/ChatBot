# src/storage/mongo.py
from pymongo import MongoClient

def get_db(
    uri="mongodb://dungnguyet17012005_db_user:Dungnguyet17012005~@ac-hzf04zl-shard-00-00.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-01.bzpmnh4.mongodb.net:27017,ac-hzf04zl-shard-00-02.bzpmnh4.mongodb.net:27017/?ssl=true&replicaSet=atlas-qutlkr-shard-0&authSource=admin&appName=Cluster0",
    db_name="legal_rag_db"
):
    client = MongoClient(uri)
    return client[db_name]