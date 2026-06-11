"""
Google Cloud Agent Builder — Vertex AI Agent Engine deployment.

This is what runs our agent on Agent Builder's MANAGED runtime (Agent Engine),
not just the ADK framework locally. It wraps the ADK `root_agent` as an
`AdkApp` (Agent Builder's app object) and provides the deploy entrypoint.

Vertex imports are lazy so importing this module never requires the Vertex SDK
(keeps the test suite and local tooling light). To deploy:

    pip install "google-cloud-aiplatform[adk,agent_engines]"
    export GOOGLE_CLOUD_PROJECT=<project>
    export GOOGLE_CLOUD_LOCATION=us-central1
    export AGENT_ENGINE_STAGING_BUCKET=gs://<bucket>
    python -m app.orchestrator.agent_engine        # deploys to Agent Engine
"""
import os
from app.orchestrator.agent import root_agent


def get_adk_app(enable_tracing: bool = True):
    """
    Wrap the ADK agent as an Agent Engine app. Usable locally
    (`app.query(...)`) and as the artifact deployed to the managed runtime.
    """
    from vertexai.preview import reasoning_engines
    return reasoning_engines.AdkApp(agent=root_agent, enable_tracing=enable_tracing)


def deploy(display_name: str = "tax-orchestrator"):
    """Deploy the agent to Vertex AI Agent Engine (Agent Builder's runtime)."""
    import vertexai
    from vertexai import agent_engines

    vertexai.init(
        project=os.environ["GOOGLE_CLOUD_PROJECT"],
        location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
        staging_bucket=os.environ["AGENT_ENGINE_STAGING_BUCKET"],
    )

    remote_app = agent_engines.create(
        agent_engine=get_adk_app(),
        display_name=display_name,
        # Runtime deps the managed environment must install for the agent + tools.
        requirements=[
            "google-cloud-aiplatform[adk,agent_engines]",
            "google-genai",
            "google-api-python-client",
            "google-auth-oauthlib",
            "pymongo",
            "pdfplumber",
            "pydantic",
        ],
        extra_packages=["app"],  # ship our package (tools, guards, services)
    )
    print(f"Deployed to Agent Engine: {remote_app.resource_name}")
    return remote_app


if __name__ == "__main__":
    deploy()
