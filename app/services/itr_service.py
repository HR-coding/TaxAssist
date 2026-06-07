from app.services.db import db

from app.models.itr1_schema import (
    ITR1_SCHEMA
)


def create_itr(user_id):

    itr = ITR1_SCHEMA.copy()

    itr["user_id"] = user_id

    db.itr_records.insert_one(
        itr
    )

    return itr


def get_itr(user_id):

    return db.itr_records.find_one(
        {"user_id": user_id},
        {"_id": 0}
    )


def update_itr(
    user_id,
    updates
):

    db.itr_records.update_one(
        {"user_id": user_id},
        {"$set": updates}
    )
