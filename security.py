from argon2 import PasswordHasher
from argon2.exceptions import (
    VerifyMismatchError,
    VerificationError
)

password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=2
)


def hash_password(password):
    return password_hasher.hash(password)


def verify_password(password_hash, password):
    try:
        return password_hasher.verify(
            password_hash,
            password
        )
    except (VerifyMismatchError, VerificationError):
        return False
