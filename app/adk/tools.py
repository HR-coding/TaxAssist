from mcps.document_mcp import process_document_mcp
from mcps.tax_rules_mcp import retrieve_tax_rules_mcp
from mcps.workflow_mcp import update_workflow_mcp

from tools.tax_calculator import calculate_tax


def process_document_tool(document_text: str):

    return process_document_mcp(document_text)


def retrieve_tax_rules_tool():

    return retrieve_tax_rules_mcp()


def calculate_tax_tool(gross_salary: int):

    return calculate_tax(gross_salary)


def update_workflow_tool(user_id: str, status: str):

    return update_workflow_mcp(
        user_id,
        status
    )