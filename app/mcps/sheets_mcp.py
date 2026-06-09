from app.mcps.tools.sheets_client import (
    read_unvouched_transactions,
    write_unvouched_transaction,
    update_verified_transaction,
)


def read_unvouched_transactions_mcp(spreadsheet_id: str = None) -> dict:
    """
    MCP adapter: fetches all unvouched transaction entries from Google Sheets.
    Returns transactions list for the agent to review and reconcile.
    """
    return read_unvouched_transactions(spreadsheet_id=spreadsheet_id)


def write_unvouched_transaction_mcp(
    transaction_type: str,
    description: str,
    amount: float,
    date: str,
    source: str = "agent",
    spreadsheet_id: str = None
) -> dict:
    """
    MCP adapter: appends a new unvouched transaction (real estate, gold, etc.) to the Sheet.
    """
    return write_unvouched_transaction(
        transaction_type=transaction_type,
        description=description,
        amount=amount,
        date=date,
        source=source,
        spreadsheet_id=spreadsheet_id
    )


def update_verified_transaction_mcp(
    row_index: int,
    verified_amount: float,
    spreadsheet_id: str = None
) -> dict:
    """
    MCP adapter: marks a transaction row as verified with the confirmed amount.
    """
    return update_verified_transaction(
        row_index=row_index,
        verified_amount=verified_amount,
        spreadsheet_id=spreadsheet_id
    )
