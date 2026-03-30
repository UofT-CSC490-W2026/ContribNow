import json
import boto3

from app.config import AWS_REGION, BEDROCK_MODEL_ID
from app.config import logger


def generate_document(prompt: str, repo_url: str) -> str:
    client = boto3.client("bedrock-runtime", region_name=AWS_REGION)

    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2200,
        "temperature": 0.2,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ]
    }

    logger.info("Invoking Bedrock with prompt:")
    logger.info(prompt)

    response = client.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(body),
        contentType="application/json",
        accept="application/json",
    )

    response_body = json.loads(response["body"].read())

    text_parts = []
    for item in response_body.get("content", []):
        if item.get("type") == "text":
            text_parts.append(item.get("text", ""))

    final_text = "".join(text_parts).strip()

    if not final_text:
        raise ValueError("Bedrock returned an empty response")

    return final_text
