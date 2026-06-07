from pymongo import MongoClient
from dotenv import load_dotenv
import certifi
import os

load_dotenv()

client = MongoClient(
    os.getenv("MONGO_URI"),
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000
)

try:
    print(client.list_database_names())
    print("CONNECTED TO MONGODB")
except Exception as e:
    print("ERROR:")
    print(e)
