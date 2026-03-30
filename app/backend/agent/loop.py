from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import boto3

from .agent import run_local_tool


@dataclass(frozen=True)
class BedrockAgentConfig:
    agent_id: str
    agent_alias_id: str
    region: str


def _require_env(value: str | None, label: str) -> str:
    if not value:
        raise ValueError(f"Missing {label}.")
    return value


def load_bedrock_agent_config() -> BedrockAgentConfig:
    return BedrockAgentConfig(
        agent_id=_require_env(os.getenv("BEDROCK_AGENT_ID"), "BEDROCK_AGENT_ID"),
        agent_alias_id=_require_env(
            os.getenv("BEDROCK_AGENT_ALIAS_ID"),
            "BEDROCK_AGENT_ALIAS_ID",
        ),
        region=os.getenv("AWS_REGION", "ca-central-1"),
    )


def build_agent_prompt(
    *,
    question: str,
    conversation_history: list[dict[str, Any]] | None,
    repo_slug: str = "default",
) -> str:
    if not question.strip():
        raise ValueError("Question must be non-empty.")

    lines = [
        "You are answering questions about a local repository.",
        f"Use repoSlug `{repo_slug}` when calling tools.",
    ]
    if conversation_history:
        lines.append("Conversation history:")
        for message in conversation_history[-10:]:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "user")).strip() or "user"
            content = str(message.get("content", "")).strip()
            if not content:
                continue
            lines.append(f"{role}: {content}")
    lines.extend(["Current user question:", question.strip()])
    return "\n".join(lines)


def _parse_agent_response(
    response: dict[str, Any],
) -> tuple[str, dict[str, Any] | None]:
    text_parts: list[str] = []
    return_control: dict[str, Any] | None = None

    for event in response.get("completion", []):
        if not isinstance(event, dict):
            continue
        chunk = event.get("chunk")
        if isinstance(chunk, dict):
            data = chunk.get("bytes", b"")
            if isinstance(data, bytes):
                text_parts.append(data.decode("utf-8"))
            elif isinstance(data, str):
                text_parts.append(data)
        maybe_return_control = event.get("returnControl")
        if isinstance(maybe_return_control, dict):
            return_control = maybe_return_control

    return "".join(text_parts).strip(), return_control


def _params_to_dict(function_input: dict[str, Any]) -> dict[str, str]:
    params: dict[str, str] = {}
    for item in function_input.get("parameters", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and isinstance(value, str):
            params[name] = value
    return params


def _build_return_control_result(
    return_control: dict[str, Any],
) -> dict[str, Any]:
    invocation_id = str(return_control["invocationId"])
    invocation_inputs = return_control.get("invocationInputs", [])
    if not invocation_inputs:
        raise ValueError("Missing invocation inputs in returnControl payload.")

    first_input = invocation_inputs[0]
    if not isinstance(first_input, dict):
        raise ValueError("Invalid invocation input payload.")
    function_input = first_input.get("functionInvocationInput")
    if not isinstance(function_input, dict):
        raise ValueError("Missing functionInvocationInput in returnControl payload.")

    action_group = str(function_input["actionGroup"])
    function_name = str(function_input["function"])
    params = _params_to_dict(function_input)
    output = run_local_tool(function_name, params)

    return {
        "invocationId": invocation_id,
        "returnControlInvocationResults": [
            {
                "functionResult": {
                    "actionGroup": action_group,
                    "function": function_name,
                    "responseBody": {
                        "TEXT": {
                            "body": output,
                        }
                    },
                }
            }
        ],
    }


def _invoke_agent_once(
    client: Any,
    *,
    config: BedrockAgentConfig,
    session_id: str,
    prompt: str | None = None,
    session_state: dict[str, Any] | None = None,
    end_session: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    request_payload: dict[str, Any] = {
        "agentId": config.agent_id,
        "agentAliasId": config.agent_alias_id,
        "sessionId": session_id,
        "endSession": end_session,
    }
    if prompt is not None:
        request_payload["inputText"] = prompt
    if session_state is not None:
        request_payload["sessionState"] = session_state

    response = client.invoke_agent(**request_payload)
    return _parse_agent_response(response)


def invoke_bedrock_agent(
    *,
    prompt: str,
    session_id: str,
    config: BedrockAgentConfig,
    end_session: bool = False,
    max_turns: int = 8,
) -> str:
    if not prompt.strip():
        raise ValueError("Prompt must be non-empty.")
    if not session_id.strip():
        raise ValueError("session_id must be non-empty.")
    if max_turns <= 0:
        raise ValueError("max_turns must be positive.")

    client = boto3.client("bedrock-agent-runtime", region_name=config.region)
    current_prompt: str | None = prompt
    current_session_state: dict[str, Any] | None = None
    last_text = ""

    for _ in range(max_turns):
        text, return_control = _invoke_agent_once(
            client,
            config=config,
            session_id=session_id,
            prompt=current_prompt,
            session_state=current_session_state,
            end_session=end_session,
        )
        if text:
            last_text = text
        if return_control is None:
            if last_text:
                return last_text
            raise ValueError("Bedrock agent returned an empty response.")

        current_prompt = None
        current_session_state = _build_return_control_result(return_control)
        print("debug: ", current_session_state)

    raise RuntimeError(f"Bedrock agent exceeded max_turns={max_turns}.")
