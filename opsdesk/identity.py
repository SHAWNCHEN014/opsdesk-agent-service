import hashlib
import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select

from opsdesk.storage import AccessGrant, Identity, timestamp


def encode_password(value):
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1)
    return salt + ":" + key.hex()


def matches_password(value, encoded):
    salt, expected = encoded.split(":", 1)
    actual = hashlib.scrypt(value.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


class Authentication:
    def __init__(self, database, config):
        self.database, self.config = database, config

    def sign_in(self, username, password):
        with self.database.session.begin() as db:
            account = db.scalar(select(Identity).where(Identity.username == username))
            if account is None or not matches_password(password, account.password):
                raise HTTPException(401, "Invalid demonstration credentials")
            token = secrets.token_urlsafe(32)
            db.add(AccessGrant(token_digest=hashlib.sha256(token.encode()).hexdigest(), identity_id=account.id, expires=timestamp() + timedelta(hours=12)))
            return token, {"id": account.id, "username": account.username, "role": account.role}

    def resolve(self, cookies, authorization=""):
        with self.database.session() as db:
            if authorization.startswith("Bearer ") and hmac.compare_digest(authorization[7:], self.config.mcp_token):
                return db.scalar(select(Identity).where(Identity.username == "employee"))
            token = cookies.get("opsdesk_session", "")
            grant = db.get(AccessGrant, hashlib.sha256(token.encode()).hexdigest()) if token else None
            if grant is not None and grant.expires > timestamp():
                return db.get(Identity, grant.identity_id)
        raise HTTPException(401, "Sign in first")

    def revoke(self, token):
        with self.database.session.begin() as db:
            grant = db.get(AccessGrant, hashlib.sha256(token.encode()).hexdigest())
            if grant is not None:
                db.delete(grant)
