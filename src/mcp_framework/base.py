from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List
from .errors import BaseMCPException

@dataclass
class MCPTool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]

class BaseMCP(ABC):
    """
    Abstract base class for all Model Context Protocol (MCP) controllers.
    """
    
    @abstractmethod
    def get_tools(self) -> List[MCPTool]:
        """
        Returns the list of tools exposed by this MCP.
        """
        pass

    def validate_input(self, tool_name: str, arguments: Dict[str, Any]) -> None:
        """
        Validates the arguments against the input schema of the requested tool.
        Raises BaseMCPException if validation fails.
        """
        tools = self.get_tools()
        tool = next((t for t in tools if t.name == tool_name), None)
        if not tool:
            raise BaseMCPException(
                error_code="TOOL_NOT_FOUND",
                message=f"Tool '{tool_name}' is not supported by {self.__class__.__name__}.",
                details={"tool_name": tool_name}
            )

        schema = tool.input_schema
        if not isinstance(arguments, dict):
            raise BaseMCPException(
                error_code="INVALID_ARGUMENTS_FORMAT",
                message="Arguments must be a JSON object (dict).",
                details={"received_type": type(arguments).__name__}
            )

        # Check required fields
        required_fields = schema.get("required", [])
        missing_fields = [field for field in required_fields if field not in arguments]
        if missing_fields:
            raise BaseMCPException(
                error_code="MISSING_REQUIRED_ARGUMENTS",
                message=f"Missing required arguments for tool '{tool_name}': {', '.join(missing_fields)}",
                details={"missing": missing_fields, "tool_name": tool_name}
            )

        # Check properties types
        properties = schema.get("properties", {})
        for key, val in arguments.items():
            if key not in properties:
                # Accept unexpected fields or raise? Usually, in strict environments, we might warn or ignore.
                continue
            
            prop_schema = properties[key]
            expected_type = prop_schema.get("type")
            if not expected_type:
                continue

            # Validate type
            is_valid = True
            if expected_type == "string" and not isinstance(val, str):
                is_valid = False
            elif expected_type == "integer" and (isinstance(val, bool) or not isinstance(val, int)):
                is_valid = False
            elif expected_type == "number" and (isinstance(val, bool) or not isinstance(val, (int, float))):
                is_valid = False
            elif expected_type == "boolean" and not isinstance(val, bool):
                is_valid = False
            elif expected_type == "array" and not isinstance(val, list):
                is_valid = False
            elif expected_type == "object" and not isinstance(val, dict):
                is_valid = False

            if not is_valid:
                raise BaseMCPException(
                    error_code="INVALID_ARGUMENT_TYPE",
                    message=f"Argument '{key}' in tool '{tool_name}' must be of type '{expected_type}'. Received: '{type(val).__name__}'",
                    details={"argument": key, "expected_type": expected_type, "received_type": type(val).__name__}
                )

    @abstractmethod
    def execute(self, tool_name: str, arguments: Dict[str, Any], correlation_id: str = None) -> Dict[str, Any]:
        """
        Executes the requested tool with the provided arguments.
        Subclasses should validate inputs before performing the action.
        """
        pass
