import os
from app.mcps.utils.google_auth import get_sheets_service


def read_unvouched_transactions(spreadsheet_id: str = None, range_name: str = "UnvouchedTransactions!A1:Z") -> dict:
    """
    Reads unvouched transaction values (real estate, gold, unlisted shares, etc.)
    from the configured Google Sheet.

    The sheet must have a header row followed by data rows.
    Each row: [transaction_type, description, amount, date, source]

    Returns a list of transaction dicts for the agent to process.
    """
    spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_ID", "")
    if not spreadsheet_id:
        return {"status": "error", "message": "GOOGLE_SHEETS_ID not configured", "transactions": []}

    service = get_sheets_service()
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )

    rows = result.get("values", [])
    if not rows:
        return {"status": "empty", "transactions": []}

    headers = [h.strip().lower().replace(" ", "_") for h in rows[0]]
    transactions = []
    for row in rows[1:]:
        # Pad short rows to header length
        padded = row + [""] * (len(headers) - len(row))
        transactions.append(dict(zip(headers, padded)))

    return {"status": "ok", "transactions": transactions, "count": len(transactions)}


def write_unvouched_transaction(
    transaction_type: str,
    description: str,
    amount: float,
    date: str,
    source: str = "agent",
    spreadsheet_id: str = None,
    range_name: str = "UnvouchedTransactions!A1"
) -> dict:
    """
    Appends a new unvouched transaction row to the Google Sheet.
    Used by the agent to record real estate, gold, or other manually-declared values.
    """
    spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_ID", "")
    if not spreadsheet_id:
        return {"status": "error", "message": "GOOGLE_SHEETS_ID not configured"}

    service = get_sheets_service()
    body = {"values": [[transaction_type, description, str(amount), date, source]]}

    service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range=range_name,
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body=body
    ).execute()

    return {"status": "appended", "transaction_type": transaction_type, "amount": amount}


def update_verified_transaction(
    row_index: int,
    verified_amount: float,
    spreadsheet_id: str = None,
    sheet_name: str = "UnvouchedTransactions"
) -> dict:
    """
    Updates the amount in a specific row after agent verification.
    Row index is 1-based (row 1 = header, row 2 = first data row).
    """
    spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_ID", "")
    if not spreadsheet_id:
        return {"status": "error", "message": "GOOGLE_SHEETS_ID not configured"}

    service = get_sheets_service()
    # Column C (index 3) holds the amount
    cell_range = f"{sheet_name}!C{row_index}"
    body = {"values": [[str(verified_amount)]]}

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=cell_range,
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()

    return {"status": "updated", "row": row_index, "verified_amount": verified_amount}
