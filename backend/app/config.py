import os, logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("app")
logger.setLevel(logging.INFO)

ACCESS_KEYS = os.getenv("ACCESS_KEYS")
if not ACCESS_KEYS:
    raise ValueError("ACCESS_KEYS environment variable is not set")
ACCESS_KEYS = [
    key.strip()
    for key in ACCESS_KEYS.split(",")
    if key.strip()
]


AWS_REGION = os.getenv("AWS_REGION", "ca-central-1")

BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID")
if not BEDROCK_MODEL_ID:
    raise ValueError("BEDROCK_MODEL_ID environment variable is not set")

S3_BUCKET_NAME = os.getenv("S3_BUCKET_NAME")
if not S3_BUCKET_NAME:
    raise ValueError("S3_BUCKET_NAME environment variable is not set")

DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SSLMODE = os.getenv("DB_SSLMODE", "require")
if not all([DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD]):
    raise ValueError("RDS database environment variables are not fully set")