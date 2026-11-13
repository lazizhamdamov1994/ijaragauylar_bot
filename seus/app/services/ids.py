import secrets
import string

_ALPHABET = string.ascii_letters + string.digits  # 62 belgi


def generate_public_id(length: int = 10) -> str:
    """Taxmin qilib bo'lmaydigan qisqa ID (62^10 ≈ 8·10^17 variant), kriptografik tasodifiy."""
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))


def is_valid_public_id(value: str) -> bool:
    return 4 <= len(value) <= 16 and all(c in _ALPHABET for c in value)
