"""Authentication module for LNURL-auth and JWT-based sessions.

This module provides Lightning Network authentication using LNURL-auth (LUD-04)
with JWT token management for session persistence.
"""

import secrets
import time
import jwt
from functools import wraps
from hashlib import sha256
from typing import Optional
from quart import request, jsonify, redirect
from lnurl import encode as lnurl_encode_lib
from lnurl.helpers import lnurlauth_verify


def lnurl_encode(url: str) -> str:
    """Encode a URL as LNURL using the lnurl library.

    Args:
        url: URL to encode

    Returns:
        LNURL bech32 string (lowercase for wallet compatibility)
    """
    lnurl_obj = lnurl_encode_lib(url)
    return lnurl_obj.bech32.lower()


async def generate_k1_challenge(db, config) -> tuple[str, str]:
    """Generate LNURL-auth challenge and store in database.

    Args:
        db: Database manager instance
        config: Application configuration

    Returns:
        Tuple of (k1_hex, lnurl_string)
    """
    k1_bytes = secrets.token_bytes(32)
    k1_hex = k1_bytes.hex()

    created_at = int(time.time())
    expires_at = created_at + config.auth_challenge_expiration_seconds

    await db.execute(
        "INSERT INTO auth_challenges (k1, created_at, expires_at) VALUES ($1, $2, $3)",
        k1_hex, created_at, expires_at
    )

    callback_url = f"{config.lnurl_callback_url}?tag=login&k1={k1_hex}"
    lnurl_string = lnurl_encode(callback_url)

    return k1_hex, lnurl_string


async def verify_lnurl_signature(k1: str, sig: str, key: str) -> bool:
    """Verify LNURL-auth ECDSA signature using the lnurl library.

    Args:
        k1: Challenge hex string
        sig: Signature hex string (DER encoded)
        key: Public key hex string (33-byte compressed format)

    Returns:
        True if signature is valid, False otherwise
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        logger.info(f"Verifying signature: k1={k1[:16]}..., key={key[:16]}...")
        # Use the lnurl library's built-in signature verification
        result = lnurlauth_verify(k1=k1, sig=sig, key=key)
        logger.info(f"Verification result: {result}")
        return result
    except Exception as e:
        logger.error(f"Signature verification failed: {type(e).__name__}: {e}")
        return False


def create_jwt_token(user_id: int, pubkey: str, config) -> str:
    """Create JWT token for authenticated user.

    Args:
        user_id: Database user ID
        pubkey: Lightning public key
        config: Application configuration

    Returns:
        JWT token string
    """
    payload = {
        "user_id": user_id,
        "pubkey": pubkey,
        "exp": int(time.time()) + config.jwt_expiration_seconds,
        "iat": int(time.time())
    }
    return jwt.encode(payload, config.jwt_secret, algorithm="HS256")


def decode_jwt_token(token: str, config) -> Optional[dict]:
    """Decode and validate JWT token.

    Args:
        token: JWT token string
        config: Application configuration

    Returns:
        Decoded payload dict if valid, None otherwise
    """
    try:
        return jwt.decode(token, config.jwt_secret, algorithms=["HS256"])
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError):
        return None


def require_auth(f):
    """Decorator to require JWT authentication on routes.

    Adds request.user_id and request.pubkey attributes for authenticated requests.
    Redirects to landing page for browser requests or returns 401 for API requests.
    """
    @wraps(f)
    async def decorated_function(*args, **kwargs):
        from quart import current_app

        token = request.cookies.get('access_token')

        if not token:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Authentication required"}), 401
            return redirect('/')

        config = current_app.config["SLICEHASH_CONFIG"]
        payload = decode_jwt_token(token, config)

        if not payload:
            if request.path.startswith('/api/'):
                return jsonify({"error": "Invalid or expired token"}), 401
            return redirect('/')

        request.user_id = payload['user_id']
        request.pubkey = payload['pubkey']

        return await f(*args, **kwargs)

    return decorated_function


async def get_or_create_user_by_pubkey(db, pubkey: str) -> int:
    """Get existing user or create new user with Lightning pubkey.

    Args:
        db: Database manager instance
        pubkey: Lightning public key hex string

    Returns:
        User ID
    """
    row = await db.fetchrow(
        "SELECT id as user_id FROM users WHERE lightning_pubkey = $1",
        pubkey
    )

    if row:
        return row['user_id']

    # Create new user with placeholder address
    placeholder_address = f"bc1_update_in_settings_{pubkey[:8]}"

    user_id = await db.fetchval(
        "INSERT INTO users (address, lightning_pubkey) VALUES ($1, $2) RETURNING id",
        placeholder_address, pubkey
    )

    return user_id


async def store_refresh_token(db, user_id: int, config) -> str:
    """Create and store a new refresh token for a user.

    Args:
        db: Database manager instance
        user_id: User ID
        config: Application configuration

    Returns:
        Raw (unhashed) refresh token string
    """
    raw = secrets.token_hex(32)
    token_hash = sha256(raw.encode()).hexdigest()
    now = int(time.time())
    expires_at = now + config.refresh_token_expiration_seconds

    await db.execute(
        "INSERT INTO refresh_tokens (user_id, token_hash, created_at, expires_at) VALUES ($1, $2, $3, $4)",
        user_id, token_hash, now, expires_at
    )
    return raw


async def validate_and_rotate_refresh_token(db, raw_token: str, config) -> Optional[dict]:
    """Validate refresh token and issue a rotated replacement.

    Detects reuse of revoked tokens (theft signal) and nukes all sessions for
    that user if detected.

    Args:
        db: Database manager instance
        raw_token: Raw (unhashed) refresh token from cookie
        config: Application configuration

    Returns:
        Dict with user_id, pubkey, new_refresh_token if valid; None otherwise
    """
    token_hash = sha256(raw_token.encode()).hexdigest()
    row = await db.fetchrow(
        "SELECT id, user_id, revoked_at, expires_at FROM refresh_tokens WHERE token_hash = $1",
        token_hash
    )

    if not row:
        return None

    now = int(time.time())

    if row["revoked_at"] is not None:
        # Revoked token reuse = likely theft — invalidate all sessions for this user
        await db.execute(
            "UPDATE refresh_tokens SET revoked_at = $1 WHERE user_id = $2 AND revoked_at IS NULL",
            now, row["user_id"]
        )
        return None

    if now > row["expires_at"]:
        return None

    user_row = await db.fetchrow(
        "SELECT id, lightning_pubkey FROM users WHERE id = $1",
        row["user_id"]
    )
    if not user_row:
        return None

    # Issue new refresh token
    new_raw = secrets.token_hex(32)
    new_hash = sha256(new_raw.encode()).hexdigest()
    new_expires = now + config.refresh_token_expiration_seconds
    new_id = await db.fetchval(
        "INSERT INTO refresh_tokens (user_id, token_hash, created_at, expires_at) VALUES ($1, $2, $3, $4) RETURNING id",
        row["user_id"], new_hash, now, new_expires
    )

    # Revoke old token, link to replacement
    await db.execute(
        "UPDATE refresh_tokens SET revoked_at = $1, replaced_by = $2 WHERE id = $3",
        now, new_id, row["id"]
    )

    return {
        "user_id": row["user_id"],
        "pubkey": user_row["lightning_pubkey"],
        "new_refresh_token": new_raw,
    }


async def revoke_refresh_token(db, raw_token: str) -> None:
    """Revoke a single refresh token (logout).

    Args:
        db: Database manager instance
        raw_token: Raw (unhashed) refresh token from cookie
    """
    token_hash = sha256(raw_token.encode()).hexdigest()
    now = int(time.time())
    await db.execute(
        "UPDATE refresh_tokens SET revoked_at = $1 WHERE token_hash = $2 AND revoked_at IS NULL",
        now, token_hash
    )


async def cleanup_expired_challenges(db) -> int:
    """Remove expired auth challenges.

    Args:
        db: Database manager instance

    Returns:
        Number of challenges removed
    """
    current_time = int(time.time())
    result = await db.execute(
        "DELETE FROM auth_challenges WHERE expires_at < $1",
        current_time
    )
    # Extract row count from result string (format: "DELETE N")
    return int(result.split()[-1]) if result else 0


async def mark_challenge_used(db, k1: str) -> bool:
    """Mark challenge as used to prevent replay attacks.

    Args:
        db: Database manager instance
        k1: Challenge hex string

    Returns:
        True if challenge was marked (was unused), False if already used
    """
    result = await db.execute(
        "UPDATE auth_challenges SET used = 1 WHERE k1 = $1 AND used = 0",
        k1
    )
    # Extract row count from result string (format: "UPDATE N")
    row_count = int(result.split()[-1]) if result else 0
    return row_count > 0
