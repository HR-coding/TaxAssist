"""Phase 4 — Vertex AI Agent Engine (Agent Builder) deploy wiring (Vertex mocked)."""
import os
import sys
import types
import unittest
from unittest.mock import MagicMock, patch

from app.orchestrator import agent_engine as ae


def _fake_vertex():
    vertexai = types.ModuleType("vertexai")
    vertexai.init = MagicMock()
    preview = types.ModuleType("vertexai.preview")
    reasoning = types.ModuleType("vertexai.preview.reasoning_engines")
    reasoning.AdkApp = MagicMock(return_value="ADKAPP")
    preview.reasoning_engines = reasoning
    vertexai.preview = preview
    agent_engines = types.ModuleType("vertexai.agent_engines")
    agent_engines.create = MagicMock(return_value=MagicMock(resource_name="projects/x/agentEngines/1"))
    vertexai.agent_engines = agent_engines
    return {
        "vertexai": vertexai,
        "vertexai.preview": preview,
        "vertexai.preview.reasoning_engines": reasoning,
        "vertexai.agent_engines": agent_engines,
    }


class TestAgentEngine(unittest.TestCase):
    def test_get_adk_app_wraps_root_agent(self):
        mods = _fake_vertex()
        with patch.dict(sys.modules, mods):
            app = ae.get_adk_app()
            self.assertEqual(app, "ADKAPP")
            kwargs = mods["vertexai.preview.reasoning_engines"].AdkApp.call_args.kwargs
            from app.orchestrator.agent import root_agent
            self.assertIs(kwargs["agent"], root_agent)
            self.assertTrue(kwargs["enable_tracing"])

    def test_deploy_inits_and_creates(self):
        mods = _fake_vertex()
        env = {"GOOGLE_CLOUD_PROJECT": "p", "GOOGLE_CLOUD_LOCATION": "us-central1",
               "AGENT_ENGINE_STAGING_BUCKET": "gs://b"}
        with patch.dict(sys.modules, mods), patch.dict(os.environ, env):
            ae.deploy(display_name="tax-test")
            mods["vertexai"].init.assert_called_once()
            create = mods["vertexai.agent_engines"].create
            create.assert_called_once()
            kwargs = create.call_args.kwargs
            self.assertEqual(kwargs["display_name"], "tax-test")
            self.assertEqual(kwargs["agent_engine"], "ADKAPP")
            self.assertIn("app", kwargs["extra_packages"])
            self.assertTrue(any("aiplatform" in r for r in kwargs["requirements"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
