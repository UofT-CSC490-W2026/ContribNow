import unittest
from unittest.mock import patch

from app.backend.agent.loop import (
    BedrockAgentConfig,
    _build_return_control_result,
    build_agent_prompt,
    invoke_bedrock_agent,
)


class _FakeRuntimeClient:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.calls = []

    def invoke_agent(self, **kwargs):
        self.calls.append(kwargs)
        return next(self._responses)


class TestAgentLoop(unittest.TestCase):
    def test_build_agent_prompt_includes_history_and_repo_slug(self) -> None:
        prompt = build_agent_prompt(
            question="How do I run tests?",
            conversation_history=[
                {"role": "user", "content": "What is this repo?"},
                {"role": "assistant", "content": "A Python app."},
            ],
        )

        self.assertIn("repoSlug `default`", prompt)
        self.assertIn("user: What is this repo?", prompt)
        self.assertIn("assistant: A Python app.", prompt)
        self.assertIn("How do I run tests?", prompt)

    def test_build_return_control_result_dispatches_tool(self) -> None:
        payload = {
            "invocationId": "inv-1",
            "invocationInputs": [
                {
                    "functionInvocationInput": {
                        "actionGroup": "LocalRepoTools",
                        "function": "searchRepoText",
                        "parameters": [
                            {"name": "repoSlug", "value": "default"},
                            {"name": "query", "value": "needle"},
                        ],
                    }
                }
            ],
        }

        with patch(
            "app.backend.agent.loop.run_local_tool",
            return_value="pkg.py:1: needle = 1",
        ) as mock_run_local_tool:
            result = _build_return_control_result(payload)

        mock_run_local_tool.assert_called_once_with(
            "searchRepoText",
            {"repoSlug": "default", "query": "needle"},
        )
        self.assertEqual(result["invocationId"], "inv-1")

    def test_invoke_bedrock_agent_handles_return_control_loop(self) -> None:
        responses = [
            {
                "completion": [
                    {
                        "returnControl": {
                            "invocationId": "inv-1",
                            "invocationInputs": [
                                {
                                    "functionInvocationInput": {
                                        "actionGroup": "LocalRepoTools",
                                        "function": "listRepoFiles",
                                        "parameters": [
                                            {"name": "repoSlug", "value": "default"},
                                            {"name": "path", "value": "."},
                                        ],
                                    }
                                }
                            ],
                        }
                    }
                ]
            },
            {
                "completion": [
                    {"chunk": {"bytes": b"Use pytest from the repository root."}}
                ]
            },
        ]
        fake_client = _FakeRuntimeClient(responses)

        with (
            patch(
                "app.backend.agent.loop.boto3.client",
                return_value=fake_client,
            ),
            patch(
                "app.backend.agent.loop.run_local_tool",
                return_value="README.md\ntests",
            ),
        ):
            answer = invoke_bedrock_agent(
                prompt="How do I run tests?",
                session_id="run-123",
                config=BedrockAgentConfig(
                    agent_id="agent-1",
                    agent_alias_id="alias-1",
                    region="ca-central-1",
                ),
            )

        self.assertEqual(answer, "Use pytest from the repository root.")
        self.assertEqual(len(fake_client.calls), 2)
        self.assertEqual(fake_client.calls[0]["sessionId"], "run-123")
        self.assertIn("sessionState", fake_client.calls[1])
