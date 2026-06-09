"""
Maps OCR extraction output (TaxDocumentExtraction) to the correct ITR ledger fields.

Field path rules (from schemas.jsonc):
- Scalar NumericField paths  → set the .value sub-key
- Array paths                → append a new item dict to the list
"""
import logging
from datetime import datetime
from app.services.itr_service import get_itr, update_itr

logger = logging.getLogger("itr_mapper")

# Fields that are arrays of items (value + source_doc_id + optional metadata)
# Any field path starting with these prefixes should append, not overwrite.
_ARRAY_FIELD_PREFIXES = {
    "other_sources.savings_interest",
    "other_sources.deposit_interest",
    "other_sources.dividend_income",
    "other_sources.others",
    "deductions.sec_80c",
    "deductions.sec_80ccc",
    "deductions.sec_80ccd1",
    "deductions.sec_80ccd1b",
    "deductions.sec_80ccd2",
    "deductions.sec_80d",
    "deductions.sec_80dd",
    "deductions.sec_80ddb",
    "deductions.sec_80e",
    "deductions.sec_80ee",
    "deductions.sec_80eea",
    "deductions.sec_80eeb",
    "deductions.sec_80g",
    "deductions.sec_80gg",
    "deductions.sec_80gga",
    "deductions.sec_80ggc",
    "deductions.sec_80u",
    "taxes_paid.advance_tax",
    "taxes_paid.self_assessment_tax",
    "taxes_paid.tds_on_salary",
    "taxes_paid.tds_other_than_salary",
    "taxes_paid.tcs",
    # ITR-2 equivalents
    "schedule_salary",
    "schedule_house_property",
    "schedule_capital_gains.short_term_gains",
    "schedule_capital_gains.long_term_gains",
    "schedule_other_sources.savings_interest",
    "schedule_other_sources.fd_interest",
    "schedule_other_sources.dividend_income_domestic",
    "schedule_other_sources.dividend_income_foreign",
    "schedule_via_deductions.sec_80c",
    "schedule_via_deductions.sec_80d",
    "schedule_vda.transactions",
}


def apply_extraction_to_itr(user_id: str, extraction_result: dict) -> dict:
    """
    Takes one TaxDocumentExtraction result dict and applies all extractions
    to the user's ITR record in MongoDB.

    Args:
        user_id: The target taxpayer.
        extraction_result: Dict from ocr_extractor.extract_financial_data()["extraction"].
                           Must have: document_type, financial_year, extractions list.

    Returns:
        Summary dict of what was applied.
    """
    doc_type = extraction_result.get("document_type", "UNKNOWN")
    source_doc_id = f"{doc_type}_{extraction_result.get('financial_year', 'UNK')}"
    extractions = extraction_result.get("extractions", [])

    applied = []
    array_pushes = {}    # field_path -> list of items to $push
    scalar_sets = {}     # field_path.value -> float

    for ext in extractions:
        field_path = ext.get("target_itr_field", "")
        value = float(ext.get("extracted_numerical_value", 0) or 0)

        if not field_path:
            continue

        if _is_array_field(field_path):
            # Build an item dict appropriate for this array type
            item = _build_array_item(field_path, value, source_doc_id)
            array_pushes.setdefault(field_path, []).append(item)
            applied.append({"field": field_path, "action": "append", "value": value})
        else:
            # NumericField scalar: set .value and .source_doc_id
            scalar_sets[f"{field_path}.value"] = value
            scalar_sets[f"{field_path}.source_doc_id"] = source_doc_id
            applied.append({"field": field_path, "action": "set", "value": value})

    # Apply scalar updates in one call (triggers live recalc)
    if scalar_sets:
        update_itr(user_id, scalar_sets)

    # Apply array appends
    if array_pushes:
        push_ops = {k: {"$each": v} for k, v in array_pushes.items()}
        from app.services.db import db
        from app.services.field_calculator import compute_calculated_fields
        db.itr_records.update_one(
            {"user_id": user_id},
            {"$push": push_ops, "$set": {"modified_at": datetime.utcnow()}}
        )
        # Trigger recalc after push
        full_doc = db.itr_records.find_one({"user_id": user_id}, {"_id": 0})
        if full_doc:
            calc = compute_calculated_fields(full_doc)
            if calc:
                db.itr_records.update_one({"user_id": user_id}, {"$set": calc})

    logger.info(f"[{user_id}] Applied {len(applied)} extractions from {doc_type}")
    return {
        "user_id": user_id,
        "document_type": doc_type,
        "fields_applied": len(applied),
        "detail": applied
    }


def map_document_to_itr(document_data: dict, source_doc_id: str = "UNKNOWN") -> dict:
    """
    Legacy compatibility mapper: converts a flat document_data dict (e.g. from
    an API payload) to an ITR-1 partial update dict.
    The top-level orchestrator calls this when document_data is provided manually.
    """
    from app.models.tax_ledger import ITR1Ledger
    itr = ITR1Ledger().model_dump(by_alias=True)
    itr["itr_type"] = "ITR1"
    itr["filing_status"] = "DRAFT"

    pi = itr["personal_info"]
    pi["pan"] = document_data.get("pan_number", "")
    name = document_data.get("employee_name", "")
    if name:
        parts = name.strip().split()
        pi["first_name"] = parts[0]
        if len(parts) > 1:
            pi["last_name"] = " ".join(parts[1:])

    itr["salary_income"]["gross_salary"]["value"] = float(document_data.get("gross_salary", 0) or 0)
    itr["salary_income"]["gross_salary"]["source_doc_id"] = source_doc_id

    # Other sources
    if document_data.get("savings_interest"):
        itr["other_sources"]["savings_interest"].append({
            "value": float(document_data["savings_interest"]),
            "source_doc_id": source_doc_id,
            "description": "Savings interest"
        })
    if document_data.get("fd_interest"):
        itr["other_sources"]["deposit_interest"].append({
            "value": float(document_data["fd_interest"]),
            "source_doc_id": source_doc_id,
            "description": "FD interest"
        })
    if document_data.get("dividend_income"):
        itr["other_sources"]["dividend_income"].append({
            "value": float(document_data["dividend_income"]),
            "source_doc_id": source_doc_id,
            "description": "Dividend income"
        })

    # Deductions
    if document_data.get("deduction_80c"):
        itr["deductions"]["sec_80c"].append({
            "value": float(document_data["deduction_80c"]),
            "source_doc_id": source_doc_id,
            "category": ""
        })
    if document_data.get("deduction_80d"):
        itr["deductions"]["sec_80d"].append({
            "value": float(document_data["deduction_80d"]),
            "source_doc_id": source_doc_id,
            "category": "SELF"
        })
    if document_data.get("deduction_80ccd1b"):
        itr["deductions"]["sec_80ccd1b"].append({
            "value": float(document_data["deduction_80ccd1b"]),
            "source_doc_id": source_doc_id
        })

    # Taxes paid
    if document_data.get("tds_salary"):
        itr["taxes_paid"]["tds_on_salary"].append({
            "value": float(document_data["tds_salary"]),
            "source_doc_id": source_doc_id,
            "deductor_tan": ""
        })

    return itr


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _is_array_field(field_path: str) -> bool:
    return any(field_path.startswith(p) for p in _ARRAY_FIELD_PREFIXES)


def _build_array_item(field_path: str, value: float, source_doc_id: str) -> dict:
    """Build the appropriate item dict for a given array field."""
    base = {"value": value, "source_doc_id": source_doc_id}
    if "sec_80c" in field_path:
        base["category"] = ""
    elif "sec_80d" in field_path:
        base["category"] = "SELF"
    elif "sec_80g" in field_path:
        base["donee_name"] = ""
    elif "tds_on_salary" in field_path or "tds_other_than_salary" in field_path:
        base.pop("value", None)
        base = {"value": value, "source_doc_id": source_doc_id, "deductor_tan": ""}
    elif "advance_tax" in field_path or "self_assessment_tax" in field_path:
        base.update({"bsr_code": "", "challan_no": "", "date": None})
    elif "savings_interest" in field_path or "deposit_interest" in field_path or "dividend_income" in field_path:
        base["description"] = ""
    return base
