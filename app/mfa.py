from __future__ import annotations

import hmac
import os
import re

import pyotp
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException


def mfa_cipher() -> Fernet:
    try:
        key = os.getenv("MFA_ENCRYPTION_KEY", "").encode("ascii")
        return Fernet(key)
    except (ValueError, TypeError, UnicodeEncodeError):
        raise HTTPException(status_code=503, detail="Authenticator setup is not configured. Contact your administrator.") from None


def decrypt_mfa_secret(encrypted_secret: str) -> str:
    try:
        return mfa_cipher().decrypt(encrypted_secret.encode("ascii")).decode("ascii")
    except (InvalidToken, ValueError, UnicodeEncodeError, UnicodeDecodeError):
        raise HTTPException(status_code=503, detail="Authenticator is unavailable. Use a recovery code or contact your administrator.") from None


def match_totp_counter(secret: str, code: str, timestamp: float, last_counter: int) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    current_counter = int(timestamp // 30)
    authenticator = pyotp.TOTP(secret)
    for offset in (0, -1, 1):
        counter = current_counter + offset
        if counter > last_counter and counter >= 0 and hmac.compare_digest(authenticator.at(counter * 30), code):
            return counter
    return None