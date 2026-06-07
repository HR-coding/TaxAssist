from google.adk import Agent

from .tools import (
    process_document_tool,
    retrieve_tax_rules_tool,
    calculate_tax_tool,
    update_workflow_tool
)

root_agent = Agent(
    name="tax_orchestrator",
    model="gemini-2.0-flash",
    instruction="""
    You are a Tax Filing Orchestrator Agent.

    Your responsibilities:
    1. Process uploaded tax documents
    2. Retrieve tax rules
    3. Calculate tax
    4. Update workflow state

    Use the available tools whenever needed.
    """,
    tools=[
        process_document_tool,
        retrieve_tax_rules_tool,
        calculate_tax_tool,
        update_workflow_tool
    ]
)

print("Agent Created Successfully")
