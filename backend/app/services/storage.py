import boto3

from app.config import AWS_REGION, S3_BUCKET_NAME


s3_client = boto3.client("s3", region_name=AWS_REGION)


def save_document(document: str, repo_id: str, version: int) -> str:
    object_key = f"outputs/{repo_id}/v{version}.md"

    s3_client.put_object(
        Bucket=S3_BUCKET_NAME,
        Key=object_key,
        Body=document.encode("utf-8"),
        ContentType="text/markdown; charset=utf-8",
    )

    return object_key


def load_document(storage_key: str) -> str:
    response = s3_client.get_object(
        Bucket=S3_BUCKET_NAME,
        Key=storage_key,
    )

    return response["Body"].read().decode("utf-8")