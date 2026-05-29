import asyncio
import os
import sys
from app import TaxAgentApp
from orchestrator import OrchestratorRunner, create_orchestrator_agent

async def main():
    print("=" * 60)
    print("AI TAX FILING AGENT - ORCHESTRATOR VERIFICATION SCRIPT")
    print("=" * 60)
    
    # 1. Initialize MCP application container
    print("[1/3] Initializing TaxAgentApp MCP Container...")
    app = TaxAgentApp()
    tools = app.list_tools()
    print(f"      Found {len(tools)} tools in MCP registry.")
    
    # 2. Instantiate Orchestrator Agent and inspect bridged tools
    print("[2/3] Bridging tools to Google ADK Agent...")
    try:
        agent = create_orchestrator_agent(app)
        print(f"      Orchestrator Agent '{agent.name}' created successfully.")
        print(f"      Bridged tools count: {len(agent.tools)}")
        print("      Bridged tools list:")
        for t in agent.tools:
            print(f"        - {t.__name__}: {t.__doc__.splitlines()[0] if t.__doc__ else 'No docstring'}")
    except Exception as e:
        print(f"      [ERROR] Agent compilation failed: {e}")
        sys.exit(1)
        
    # 3. Running Runner verification
    print("[3/3] Checking Gemini API key authentication...")
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("\n[WARNING] GEMINI_API_KEY environment variable is NOT set.")
        print("          Orchestration runtime will fail if executed.")
        print("          Set GEMINI_API_KEY in your shell or env to test dialogue flow.")
        print("\n          Compilation and tool bridging VERIFICATION: SUCCESS")
        print("=" * 60)
        sys.exit(0)
        
    print("      GEMINI_API_KEY detected. Starting a live session test...")
    try:
        runner = OrchestratorRunner(app)
        user_id = "verifier_user_1"
        session_id = "verifier_session_1"
        
        # We seed some checklist tasks manually in state repository so the agent has work to do
        print("      Seeding mock checklist task...")
        app.execute_tool("create_task", {
            "user_id": user_id,
            "task": {
                "title": "Review ITR-2 Profile",
                "description": "Please double check the salary schedule total wages."
            }
        })
        
        prompt = "Hello! Check my state, list my open tasks, and tell me what I should do."
        print(f"      Sending prompt: '{prompt}'")
        print("      Awaiting agent response...")
        
        result = await runner.chat(user_message=prompt, user_id=user_id, session_id=session_id)
        
        if result["status"] == "success":
            print("\n      [RESPONSE RECEIVED]")
            print(result["data"]["response"])
            print("\n      [AGENT EVENTS LOG]")
            for ev in result["data"]["events"]:
                # Print only relevant parts to avoid flooding
                if "action" in ev or "tool" in ev or "LlmResponse" in ev:
                    print(f"        * {ev[:120]}...")
            print("\n      Live session dialogue VERIFICATION: SUCCESS")
        else:
            print(f"\n      [ERROR] Agent chat failed: {result['error']['message']}")
            sys.exit(1)
            
    except Exception as e:
        print(f"\n      [ERROR] Runtime execution failed: {e}")
        sys.exit(1)
        
    print("=" * 60)

if __name__ == "__main__":
    # Ensure src directory is in path
    src_dir = os.path.dirname(os.path.abspath(__file__))
    if src_dir not in sys.path:
        sys.path.append(src_dir)
    asyncio.run(main())
