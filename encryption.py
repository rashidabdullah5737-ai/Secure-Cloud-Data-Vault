import os
import base64

from dotenv import load_dotenv
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

load_dotenv()

encoded_key = os.getenv("ENCRYPTION_KEY")

if not encoded_key:
    raise RuntimeError("ENCRYPTION_KEY missing from .env")

KEY = base64.urlsafe_b64decode(encoded_key)

if len(KEY) != 32:
    raise RuntimeError("Invalid AES-256 key length")


def encrypt_data(plaintext, aad=None):
    aes = AESGCM(KEY)
    nonce = os.urandom(12)

    ciphertext = aes.encrypt(
        nonce,
        plaintext.encode("utf-8"),
        aad
    )

    return ciphertext, nonce


def decrypt_data(ciphertext, nonce, aad=None):
    aes = AESGCM(KEY)

    plaintext = aes.decrypt(
        nonce,
        ciphertext,
        aad
    )

    return plaintext.decode("utf-8")
