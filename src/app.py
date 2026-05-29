import argparse
import json
import sys
from typing import Any, Dict, List, Optional
from mcp_framework.base import BaseMCP, MCPTool
from mcp_framework.errors import BaseMCPException
from mcp_framework.observability import correlation_context, logger

# Import MCP Layers
from state_mcp import (
    StateSystemMCP,
    MongoStateRepository,
    AuditLogger as StateAuditLogger,
    ProgressTracker,
    WorkflowManager,
    TaskManager
)
from document_mcp import (
    DocumentMCP,
    MongoDocumentRepository,
    GoogleDriveClient,
    GeminiOCRService,
    FinancialDocumentClassifier,
    FinancialExtractor,
    FinancialProfileBuilder,
    DocumentAuditService
)
from interaction_mcp import (
    UserInteractionMCP,
    MongoCommunicationRepository,
    GmailClient,
    GoogleCalendarClient,
    NotificationTemplateEngine,
    CommunicationAuditService
)
from shared import GoogleAuthManager, get_database

class TaxAgentApp:
    """
    Main Application Bootstrapper.
    Constructs and registers all controllers, establishing strict Dependency Injection.
    """
    
    def __init__(self):
        # 1. Initialize Shared Resources
        self.auth_manager = GoogleAuthManager()
        self.db = get_database()

        # 2. Dependency Injection - State/System MCP
        self.state_repo = MongoStateRepository(self.db)
        self.state_audit_logger = StateAuditLogger(self.state_repo)
        self.progress_tracker = ProgressTracker(self.state_repo)
        self.workflow_manager = WorkflowManager(self.state_repo, self.state_audit_logger)
        self.task_manager = TaskManager(self.state_repo, self.state_audit_logger, self.progress_tracker)
        
        self.state_mcp = StateSystemMCP(
            repository=self.state_repo,
            workflow_manager=self.workflow_manager,
            task_manager=self.task_manager,
            progress_tracker=self.progress_tracker,
            audit_logger=self.state_audit_logger
        )

        # 3. Dependency Injection - Document MCP
        self.doc_repo = MongoDocumentRepository(self.db)
        self.drive_client = GoogleDriveClient(self.auth_manager)
        self.ocr_service = GeminiOCRService()
        self.doc_classifier = FinancialDocumentClassifier()
        self.financial_extractor = FinancialExtractor()
        self.profile_builder = FinancialProfileBuilder(self.doc_repo)
        self.doc_audit_service = DocumentAuditService(self.doc_repo)

        self.document_mcp = DocumentMCP(
            drive_client=self.drive_client,
            ocr_service=self.ocr_service,
            classifier=self.doc_classifier,
            extractor=self.financial_extractor,
            profile_builder=self.profile_builder,
            repository=self.doc_repo,
            audit_service=self.doc_audit_service
        )

        # 4. Dependency Injection - User Interaction MCP
        self.comm_repo = MongoCommunicationRepository(self.db)
        self.gmail_client = GmailClient(self.auth_manager)
        self.calendar_client = GoogleCalendarClient(self.auth_manager)
        self.template_engine = NotificationTemplateEngine()
        self.comm_audit_service = CommunicationAuditService(self.comm_repo)

        self.interaction_mcp = UserInteractionMCP(
            gmail_client=self.gmail_client,
            calendar_client=self.calendar_client,
            template_engine=self.template_engine,
            repository=self.comm_repo,
            audit_service=self.comm_audit_service
        )

        # 5. Build Registry Map
        self.controllers: List[BaseMCP] = [
            self.state_mcp,
            self.document_mcp,
            self.interaction_mcp
        ]
        self.tool_map: Dict[str, BaseMCP] = {}
        for controller in self.controllers:
            for tool in controller.get_tools():
                self.tool_map[tool.name] = controller

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        Dynamically discovers all tools supported by the registered MCPs.
        """
        all_tools = []
        for controller in self.controllers:
            for tool in controller.get_tools():
                all_tools.append({
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema
                })
        return all_tools

    def execute_tool(self, tool_name: str, arguments: Dict[str, Any], correlation_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes a registered tool by routing to the appropriate MCP controller.
        """
        controller = self.tool_map.get(tool_name)
        if not controller:
            return {
                "status": "error",
                "error": {
                    "code": "TOOL_NOT_FOUND",
                    "message": f"Tool '{tool_name}' is not registered on any MCP controller.",
                    "details": {}
                }
            }
        
        # Route to controller execution
        return controller.execute(tool_name, arguments, correlation_id)

def main():
    parser = argparse.ArgumentParser(description="AI-Native Tax Filing Agent MCP Layer CLI.")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # 1. list-tools sub-command
    subparsers.add_parser("list-tools", help="List all registered MCP tools and their schemas")
    
    # 2. execute sub-command
    exec_parser = subparsers.add_parser("execute", help="Execute an MCP tool")
    exec_parser.add_argument("--tool", required=True, help="Name of the tool to execute")
    exec_parser.add_argument("--args", required=True, help="JSON string representing tool arguments")
    exec_parser.add_argument("--cid", required=False, default=None, help="Correlation ID context")

    args = parser.parse_args()
    
    # Instantiate application
    app = TaxAgentApp()
    
    if args.command == "list-tools" or not args.command:
        # Format output as clean JSON list for standard discovery
        tools = app.list_tools()
        print(json.dumps(tools, indent=2))
        sys.exit(0)
        
    elif args.command == "execute":
        # Parse JSON arguments
        try:
            tool_args = json.loads(args.args)
        except json.JSONDecodeError as e:
            print(json.dumps({
                "status": "error",
                "error": {
                    "code": "INVALID_JSON",
                    "message": f"Failed to parse arguments JSON string: {str(e)}",
                    "details": {}
                }
            }, indent=2))
            sys.exit(1)

        # Run tool and print result
        result = app.execute_tool(args.tool, tool_args, args.cid)
        print(json.dumps(result, indent=2))
        
        # Set exit code based on status
        if result.get("status") == "error":
            sys.exit(1)
        sys.exit(0)

if __name__ == "__main__":
    main()
