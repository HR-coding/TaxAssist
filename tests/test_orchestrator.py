import inspect
import pytest
from src.orchestrator import MCPToolBridger, create_orchestrator_agent
from src.app import TaxAgentApp

def test_tool_bridger_compiles_functions():
    # Define a mock tool schema resembling typical MCP schemas
    mock_tools_metadata = [
        {
            "name": "mock_tool_1",
            "description": "Mock tool descriptions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "Unique user identifier."
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of records."
                    },
                    "flag": {
                        "type": "boolean",
                        "description": "Enable flag."
                    }
                },
                "required": ["user_id"]
            },
            "output_schema": {}
        }
    ]
    
    invoked_args = {}
    
    def mock_executor(tool_name: str, arguments: dict):
        invoked_args[tool_name] = arguments
        return {"status": "success", "data": "mocked"}
        
    bridged_funcs = MCPToolBridger.bridge_tools(mock_tools_metadata, mock_executor)
    
    assert len(bridged_funcs) == 1
    func = bridged_funcs[0]
    
    # 1. Verify function name
    assert func.__name__ == "mock_tool_1"
    
    # 2. Verify docstring is populated
    assert "Mock tool descriptions." in func.__doc__
    assert "user_id" in func.__doc__
    assert "count" in func.__doc__
    assert "flag" in func.__doc__
    
    # 3. Verify signature
    sig = inspect.signature(func)
    params = sig.parameters
    assert "user_id" in params
    assert "count" in params
    assert "flag" in params
    
    # Required parameter has no default value, optional ones default to None
    assert params["user_id"].default is inspect.Parameter.empty
    assert params["count"].default is None
    assert params["flag"].default is None
    
    # 4. Verify execution bridges correctly
    res = func(user_id="user_abc", count=42)
    assert res["status"] == "success"
    assert "mock_tool_1" in invoked_args
    assert invoked_args["mock_tool_1"] == {"user_id": "user_abc", "count": 42}

def test_create_orchestrator_agent():
    # Instantiate the container app
    app = TaxAgentApp()
    
    # Create the agent
    agent = create_orchestrator_agent(app)
    
    # Verify agent attributes
    assert agent.name == "tax_orchestrator"
    assert "gemini-2.5-flash" in agent.model
    assert len(agent.tools) > 0
    
    # Locate one of the tools, e.g. get_state
    tool_names = [t.__name__ for t in agent.tools]
    assert "get_state" in tool_names
    assert "process_document" in tool_names
    assert "send_email" in tool_names
