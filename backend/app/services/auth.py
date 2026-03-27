from app.config import ACCESS_KEYS


def verify_key(access_key: str) -> bool:
    return access_key in ACCESS_KEYS