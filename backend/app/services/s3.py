import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import AWS_REGION, S3_BUCKET_NAME, logger


s3_client = boto3.client("s3", region_name=AWS_REGION)


def save_object_to_s3(object_key: str, obj: str) -> bool:
    try:
        s3_client.put_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
            Body=obj.encode("utf-8"),
        )
        return True

    except (ClientError, BotoCoreError) as e:
        logger.error(f"Failed to save object to S3 with key {object_key}: {str(e)}")
        return False


def load_object_from_s3(object_key: str) -> str | None:
    try:
        response = s3_client.get_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
        )
        obj = response["Body"].read().decode("utf-8")
        return obj

    except (ClientError, BotoCoreError) as e:
        logger.error(f"Failed to load object from S3 with key {object_key}: {str(e)}")
        return None


def delete_object_from_s3(object_key: str) -> bool:
    try:
        s3_client.delete_object(
            Bucket=S3_BUCKET_NAME,
            Key=object_key,
        )
        return True

    except (ClientError, BotoCoreError) as e:
        logger.error(f"Failed to delete object from S3 with key {object_key}: {str(e)}")
        return False