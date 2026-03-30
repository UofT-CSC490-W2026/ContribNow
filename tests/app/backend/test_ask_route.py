import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.backend.models import AskRequest
from app.backend.routes.ask import ask


class TestAskRoute(unittest.IsolatedAsyncioTestCase):
    async def test_ask_returns_agent_answer(self) -> None:
        request = AskRequest(
            runId="run-123",
            repoSlug="default",
            question="How do I run tests?",
        )

        with (
            patch(
                "app.backend.routes.ask.load_bedrock_agent_config",
                return_value=object(),
            ),
            patch(
                "app.backend.routes.ask.invoke_bedrock_agent",
                return_value="Use pytest from the repository root.",
            ),
        ):
            response = await ask(request)

        self.assertEqual(response.answer, "Use pytest from the repository root.")
        self.assertEqual(response.citations, [])

    async def test_ask_maps_runtime_error_to_http_502(self) -> None:
        request = AskRequest(
            runId="run-123",
            repoSlug="default",
            question="How do I run tests?",
        )

        with (
            patch(
                "app.backend.routes.ask.load_bedrock_agent_config",
                return_value=object(),
            ),
            patch(
                "app.backend.routes.ask.invoke_bedrock_agent",
                side_effect=RuntimeError("Bedrock agent exceeded max_turns=8."),
            ),
        ):
            with self.assertRaises(HTTPException) as exc_info:
                await ask(request)

        self.assertEqual(exc_info.exception.status_code, 502)
