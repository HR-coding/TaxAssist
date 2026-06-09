import logging
from app.mcps.services.db import db

logger = logging.getLogger("db_initializer")


def initialize_database():
    """
    Creates MongoDB indexes for all collections.
    Safe to call on every startup (create_index is idempotent).
    """
    logger.info("Initialising database indexes...")
    try:
        # document_registry
        db.document_registry.create_index("user_id")
        db.document_registry.create_index("source_id", unique=True)
        db.document_registry.create_index("document_id")

        # state_tracker
        db.state_tracker.create_index("user_id", unique=True)
        db.state_tracker.create_index([("user_id", 1), ("tax_year", 1)], unique=True)

        # itr_records
        db.itr_records.create_index("user_id", unique=True)
        db.itr_records.create_index([("user_id", 1), ("tax_year", 1)], unique=True)

        logger.info("Database initialisation successful.")
        return True
    except Exception as e:
        logger.error(f"Database initialisation failed: {e}")
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    initialize_database()
