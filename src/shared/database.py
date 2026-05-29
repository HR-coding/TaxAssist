import os
from typing import Any, Dict, Generator, Optional
import pymongo
from pymongo.errors import PyMongoError
from mcp_framework.errors import RepositoryException
from mcp_framework.observability import logger

_db_client: Optional[Any] = None

class MockMongoCollection:
    """
    An in-memory mock of a MongoDB collection to allow the system
    to run without requiring a live MongoDB server.
    """
    def __init__(self, name: str):
        self.name = name
        self.data: Dict[str, Dict[str, Any]] = {}

    def find_one(self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        # Simple exact matches for demo/testing
        for item in self.data.values():
            match = True
            for k, v in filter.items():
                if k == "_id" and item.get("_id") != v:
                    match = False
                    break
                elif k != "_id" and item.get(k) != v:
                    match = False
                    break
            if match:
                return dict(item)
        return None

    def find(self, filter: Dict[str, Any], projection: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        results = []
        for item in self.data.values():
            match = True
            for k, v in filter.items():
                if k == "_id" and item.get("_id") != v:
                    match = False
                    break
                elif k != "_id" and item.get(k) != v:
                    match = False
                    break
            if match:
                results.append(dict(item))
        return results

    def insert_one(self, document: Dict[str, Any]) -> Any:
        doc = dict(document)
        if "_id" not in doc:
            import uuid
            doc["_id"] = str(uuid.uuid4())
        doc_id = doc["_id"]
        self.data[doc_id] = doc
        
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        return InsertOneResult(doc_id)

    def update_one(self, filter: Dict[str, Any], update: Dict[str, Any], upsert: bool = False) -> Any:
        doc = self.find_one(filter)
        if not doc:
            if upsert:
                # Basic upsert
                new_doc = {}
                # Set initial filter properties
                for k, v in filter.items():
                    if k != "_id":
                        new_doc[k] = v
                
                # Apply update operators
                if "$set" in update:
                    new_doc.update(update["$set"])
                if "$setOnInsert" in update:
                    new_doc.update(update["$setOnInsert"])
                
                self.insert_one(new_doc)
                class UpdateResultUpsert:
                    matched_count = 0
                    modified_count = 1
                    upserted_id = new_doc.get("_id")
                return UpdateResultUpsert()
            else:
                class UpdateResultNoMatch:
                    matched_count = 0
                    modified_count = 0
                    upserted_id = None
                return UpdateResultNoMatch()

        # Update matching doc
        if "$set" in update:
            doc.update(update["$set"])
        if "$unset" in update:
            for k in update["$unset"]:
                doc.pop(k, None)
        if "$push" in update:
            for k, v in update["$push"].items():
                if k not in doc:
                    doc[k] = []
                if isinstance(doc[k], list):
                    doc[k].append(v)
                    
        self.data[doc["_id"]] = doc
        class UpdateResultSuccess:
            matched_count = 1
            modified_count = 1
            upserted_id = None
        return UpdateResultSuccess()

    def delete_one(self, filter: Dict[str, Any]) -> Any:
        doc = self.find_one(filter)
        if doc:
            self.data.pop(doc["_id"], None)
            class DeleteResultSuccess:
                deleted_count = 1
            return DeleteResultSuccess()
        class DeleteResultFail:
            deleted_count = 0
        return DeleteResultFail()

    def count_documents(self, filter: Dict[str, Any]) -> int:
        return len(self.find(filter))


class MockMongoClient:
    """
    In-memory MongoDB client mock.
    """
    def __init__(self):
        self.db = MockMongoDatabase(self)
        
    def __getitem__(self, name: str) -> Any:
        return self.db

    def close(self):
        pass


class MockMongoDatabase:
    """
    In-memory MongoDB database mock.
    """
    def __init__(self, client):
        self.client = client
        self.collections: Dict[str, MockMongoCollection] = {}

    def __getitem__(self, name: str) -> MockMongoCollection:
        if name not in self.collections:
            self.collections[name] = MockMongoCollection(name)
        return self.collections[name]

    def get_collection(self, name: str) -> MockMongoCollection:
        return self[name]


def get_db_client() -> Any:
    """
    Returns a connection pool client to MongoDB.
    Gracefully falls back to MockMongoClient if MONGO_URI is missing or connections fail.
    """
    global _db_client
    if _db_client is not None:
        return _db_client

    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        logger.info("MONGO_URI environment variable not detected. Falling back to MockMongoClient.")
        _db_client = MockMongoClient()
        return _db_client

    try:
        # Standard PyMongo Client setup
        _db_client = pymongo.MongoClient(
            mongo_uri, 
            serverSelectionTimeoutMS=2000,
            uuidRepresentation="standard"
        )
        # Test connection
        _db_client.server_info()
        logger.info("Connected to MongoDB successfully.")
    except PyMongoError as e:
        logger.warning(f"Failed to connect to MongoDB at {mongo_uri}. Error: {str(e)}. Falling back to MockMongoClient.")
        _db_client = MockMongoClient()

    return _db_client


def get_database(name: Optional[str] = None) -> Any:
    """
    Helper function to get a specific database.
    """
    client = get_db_client()
    db_name = name or os.getenv("MONGO_DATABASE", "tax_filing_agent")
    return client[db_name]
