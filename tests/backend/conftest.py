from __future__ import annotations

import importlib
import io
from pathlib import Path
import sys
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


class _BootstrapS3Client:
    def put_object(self, **_: object) -> None:
        return None

    def get_object(self, **_: object) -> dict[str, object]:
        return {"Body": io.BytesIO(b"")}


class _BootstrapBedrockClient:
    def invoke_model(self, **_: object) -> dict[str, object]:
        return {"body": io.BytesIO(b'{"content":[{"type":"text","text":"bootstrap"}]}')}


class _BootstrapBoto3(ModuleType):
    def client(self, service_name: str, region_name: str | None = None) -> object:
        if service_name == "s3":
            return _BootstrapS3Client()
        if service_name == "bedrock-runtime":
            return _BootstrapBedrockClient()
        raise ValueError(f"Unsupported service: {service_name}")


class _BootstrapCursor:
    def execute(self, *_: object, **__: object) -> None:
        return None

    def fetchone(self) -> tuple[int]:
        return (1,)

    def __enter__(self) -> "_BootstrapCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _BootstrapConnection:
    def cursor(self) -> _BootstrapCursor:
        return _BootstrapCursor()

    def commit(self) -> None:
        return None

    def __enter__(self) -> "_BootstrapConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class _BootstrapPsycopg(ModuleType):
    def connect(self, **_: object) -> _BootstrapConnection:
        return _BootstrapConnection()


class _BootstrapMangum:
    def __init__(self, app: object) -> None:
        self.app = app


sys.modules["boto3"] = _BootstrapBoto3("boto3")
sys.modules["psycopg"] = _BootstrapPsycopg("psycopg")

mangum_module = ModuleType("mangum")
mangum_module.Mangum = _BootstrapMangum  # type: ignore[attr-defined]
sys.modules["mangum"] = mangum_module


REQUIRED_ENV = {
    "ACCESS_KEYS": "alpha,beta",
    "BEDROCK_MODEL_ID": "bedrock-test-model",
    "S3_BUCKET_NAME": "test-bucket",
    "DB_HOST": "db.example.com",
    "DB_PORT": "5432",
    "DB_NAME": "contribnow",
    "DB_USER": "postgres",
    "DB_PASSWORD": "secret",
}


@pytest.fixture
def load_backend_module(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.delenv("AWS_REGION", raising=False)
    monkeypatch.delenv("DB_SSLMODE", raising=False)

    def _load(module_name: str):
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                sys.modules.pop(name)
        return importlib.import_module(module_name)

    return _load
