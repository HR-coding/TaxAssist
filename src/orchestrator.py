import inspect
import os
import sys
import logging
from typing import Any, Dict, List, Callable, Optional
from google.adk import Agent
from google.adk.runners import InMemoryRunner

# Set up logging matching the application context
logger = logging.getLogger("TaxAgentMCP.orchestrator")

class MCPToolBridger:
    """
    Utility class that bridges generic MCP tools (defined via JSON Schemas)
    into standard Python functions that can be ingested by the Google ADK.
    """
    
    @staticmethod
    def bridge_tools(tools_metadata: List[Dict[str, Any]], execute_callback: Callable[[str, Dict[str, Any]], Any]) -> List[Callable]:
        """
        Dynamically compiles Python function definitions for each tool metadata dictionary.
        Returns a list of callable Python functions with proper annotations and docstrings.
        """
        bridged_functions = []
        type_map = {
            "string": "str",
            "integer": "int",
            "number": "float",
            "boolean": "bool",
            "array": "list",
            "object": "dict"
        }
        
        for tool in tools_metadata:
            name = tool["name"]
            description = tool["description"]
            input_schema = tool["input_schema"] or {}
            
            properties = input_schema.get("properties", {})
            required = input_schema.get("required", [])
            
            # To construct a valid Python signature, required params (no default value)
            # must precede optional params (default value = None).
            sorted_params = []
            for p_name in properties:
                if p_name in required:
                    sorted_params.append((p_name, True))
                else:
                    sorted_params.append((p_name, False))
            
            # Sort so that required is True (which sorts after False) is not done,
            # we want required=True first.
            sorted_params.sort(key=lambda x: 0 if x[1] else 1)
            
            # Build parameter lists for signature and body
            param_def_parts = []
            args_collect_parts = []
            doc_args_parts = []
            
            for p_name, is_req in sorted_params:
                p_schema = properties[p_name]
                schema_type = p_schema.get("type", "string")
                py_type_str = type_map.get(schema_type, "str")
                p_desc = p_schema.get("description", "")
                
                # Signature part
                if is_req:
                    param_def_parts.append(f"{p_name}: {py_type_str}")
                else:
                    param_def_parts.append(f"{p_name}: {py_type_str} = None")
                
                # Body argument collection
                args_collect_parts.append(f"'{p_name}': {p_name}")
                
                # Docstring part
                doc_args_parts.append(f"        {p_name}: {p_desc}")
                
            sig_str = ", ".join(param_def_parts)
            args_dict_str = ", ".join(args_collect_parts)
            doc_args_str = "\n".join(doc_args_parts)
            
            # Construct Python source code for the wrapper function
            func_source = f"""
def {name}({sig_str}):
    \"\"\"{description}

    Args:
{doc_args_str}
    \"\"\"
    args = {{{args_dict_str}}}
    # Remove None values to clean up args payload, or keep them if they are optional
    cleaned_args = {{k: v for k, v in args.items() if v is not None}}
    return execute_callback("{name}", cleaned_args)
"""
            # Compile the function source within a local namespace
            namespace = {"execute_callback": execute_callback}
            try:
                exec(func_source, namespace)
                compiled_func = namespace[name]
                bridged_functions.append(compiled_func)
                logger.debug(f"Successfully compiled bridged function for tool '{name}'")
            except Exception as e:
                logger.error(f"Failed to compile bridged tool function for '{name}': {str(e)}")
                raise
                
        return bridged_functions


def create_orchestrator_agent(app: Any) -> Agent:
    """
    Factory function that creates the Gemini ADK Orchestrator Agent.
    Discovers all tools registered in TaxAgentApp, wraps them dynamically,
    and returns a fully configured Agent.
    """
    # 1. Discover all tools
    raw_tools = app.list_tools()
    
    # 2. Define callback to bridge execution back to App
    def execute_callback(tool_name: str, arguments: Dict[str, Any]) -> Any:
        logger.info(f"Orchestrator executing tool '{tool_name}' with args: {arguments}")
        result = app.execute_tool(tool_name, arguments)
        logger.debug(f"Tool '{tool_name}' execution result: {result}")
        return result

    # 3. Create bridged functions
    bridged_tools = MCPToolBridger.bridge_tools(raw_tools, execute_callback)
    
    # 4. System Instruction guiding the agent reasoning
    system_instruction = (
        "You are an AI-Native Tax Filing Orchestrator agent built to assist users with their Indian Income Tax Filing (ITR-1 and ITR-2).\n"
        "Your task is to orchestrate the workflow step-by-step using your available tools.\n\n"
        "Workflow Guidelines:\n"
        "1. Check the user's filing state (`get_state`) first to understand where they are in the process.\n"
        "2. Retrieve any pending checklist tasks (`get_open_tasks`) to see what actions need to be performed (e.g. upload W-2, retrieve salary schedule).\n"
        "3. If a W-2 or document upload is required, and you have a Google Drive file ID, run `process_document` to retrieve OCR data, classify it, extract financial parameters, and update the financial profile.\n"
        "4. Create reminders (`create_reminder`) on the calendar and send notification emails (`send_email`, `request_document`, `send_clarification`) to request documents or explain discrepancies.\n"
        "5. Once a task is completed, make sure to resolve it (`resolve_task`) and update the workflow step status (`update_state`).\n"
        "6. Always fetch and summarize the updated tax profile (`get_financial_profile`) to keep the user informed.\n\n"
        "Operate professionally, logically, and systematically. Explain what tools you are using to complete the user's request."
    )

    # 5. Build ADK Agent
    agent = Agent(
        name="tax_orchestrator",
        description="Dynamic orchestrator coordinating tax document OCR, checklist tasks, and calendar/email communications.",
        model="gemini-2.5-flash",
        instruction=system_instruction,
        tools=bridged_tools
    )
    
    return agent


class OrchestratorRunner:
    """
    Manages the session runner and handles text-based dialogue with the Gemini Agent.
    """
    def __init__(self, app: Any):
        self.app = app
        self.agent = create_orchestrator_agent(app)
        self.runner = InMemoryRunner(self.agent)
        
        # Verify API Key
        if "GEMINI_API_KEY" not in os.environ:
            logger.warning(
                "GEMINI_API_KEY environment variable is not set. "
                "Agent executions will fail unless a valid key is provided in the environment."
            )

    async def chat(self, user_message: str, user_id: str = "default_user", session_id: str = "default_session") -> Dict[str, Any]:
        """
        Sends a message to the agent and executes the event loop (handling tool calls).
        Returns a dictionary containing the final assistant text response and tool execution events.
        """
        if "GEMINI_API_KEY" not in os.environ:
            return {
                "status": "error",
                "error": {
                    "code": "MISSING_CREDENTIALS",
                    "message": "GEMINI_API_KEY environment variable is not set. Please set it to run the orchestrator.",
                    "details": {}
                }
            }

        # 1. Ensure the session is pre-created asynchronously in InMemorySessionService
        try:
            await self.runner.session_service.get_session(
                app_name=self.runner.app_name,
                user_id=user_id,
                session_id=session_id
            )
        except Exception:
            # Session not found, create a new one
            await self.runner.session_service.create_session(
                app_name=self.runner.app_name,
                user_id=user_id,
                session_id=session_id
            )

        # 2. Package the text message into google.genai.types.Content object
        from google.genai import types
        message_content = types.Content(
            role="user",
            parts=[types.Part(text=user_message)]
        )

        response_text = ""
        events_log = []
        
        try:
            # InMemoryRunner.run_async yields events as they occur
            async for event in self.runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message_content
            ):
                events_log.append(event)
                
                # Check for output content events
                if hasattr(event, "content") and event.content:
                    if hasattr(event.content, "parts") and event.content.parts:
                        for part in event.content.parts:
                            if hasattr(part, "text") and part.text:
                                response_text += part.text
                    elif isinstance(event.content, str):
                        response_text += event.content
                elif hasattr(event, "output") and isinstance(event.output, str):
                    response_text += event.output
            
            return {
                "status": "success",
                "data": {
                    "response": response_text,
                    "events": [str(e) for e in events_log]
                }
            }
            
        except Exception as e:
            logger.error(f"Error during orchestrator agent chat turn: {str(e)}")
            return {
                "status": "error",
                "error": {
                    "code": "AGENT_EXECUTION_FAILED",
                    "message": f"An error occurred while running the agent: {str(e)}",
                    "details": {}
                }
            }

