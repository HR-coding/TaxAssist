from datetime import datetime
from app.mcps.services.db import db
from app.mcps.models.tax_ledger import ITR1Ledger, ITR2Ledger
from app.mcps.services.field_calculator import compute_calculated_fields


def create_itr(user_id: str, itr_type: str = "ITR1") -> dict:
    """Creates a blank ITR record (ITR-1 or ITR-2) with correct schema defaults."""
    if itr_type in ("ITR2", "ITR-2"):
        obj = ITR2Ledger(user_id=user_id)
    else:
        obj = ITR1Ledger(user_id=user_id)

    doc = obj.model_dump(by_alias=True)
    doc["modified_at"] = datetime.utcnow()
    db.itr_records.insert_one(doc)
    doc.pop("_id", None)
    return doc


def get_itr(user_id: str) -> dict:
    return db.itr_records.find_one({"user_id": user_id}, {"_id": 0})


def update_itr(user_id: str, updates: dict):
    """
    Applies a partial update to the ITR record, then immediately recomputes
    all CALCULATED_FIELDs (live recalc on every field update).
    """
    updates["modified_at"] = datetime.utcnow()
    db.itr_records.update_one(
        {"user_id": user_id},
        {"$set": updates},
        upsert=True
    )

    # Live recalc — fetch full doc and compute all derived fields
    full_doc = db.itr_records.find_one({"user_id": user_id}, {"_id": 0})
    if full_doc:
        calc_updates = compute_calculated_fields(full_doc)
        if calc_updates:
            db.itr_records.update_one(
                {"user_id": user_id},
                {"$set": calc_updates}
            )
