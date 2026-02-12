"""Quart web application for SliceHash mining backend.

This module provides the HTTP server with:
- Fast webhook endpoint for receiving share events from pool (<10ms response)
- Background share processing with rotation logic
- Health check endpoint
"""

import asyncio
import io
import json
import logging
import re
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import qrcode
from PIL import Image
from pydantic import BaseModel, Field, ValidationError, validator
from quart import (
    Quart,
    Response,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
)

from .auth import (
    cleanup_expired_challenges,
    create_jwt_token,
    decode_jwt_token,
    generate_k1_challenge,
    get_or_create_user_by_pubkey,
    lnurl_encode,
    mark_challenge_used,
    require_auth,
    verify_lnurl_signature,
)
from .config import Config, load_config
from .db.manager import DatabaseManager, init_database
from .hash_utils import calculate_level
from .priority import TrafficLevel, calculate_traffic_level
from .quota import calculate_shares_remaining, get_active_users
from .redis_consumer import RedisStreamConsumer
from .share_processor import ShareProcessor
from .sse_manager import AuthNotification, ShareNotification, SSEManager

logger = logging.getLogger(__name__)

# Global references (initialized in create_app)
share_queue: Optional[asyncio.Queue] = None
share_processor: Optional[ShareProcessor] = None
redis_consumer: Optional[RedisStreamConsumer] = None
sse_manager: SSEManager


# Highscores cache
class HighscoresCache:
    """Simple in-memory cache for highscores."""

    def __init__(self):
        self._cache = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str):
        async with self._lock:
            return self._cache.get(key)

    async def set(self, key: str, value):
        async with self._lock:
            self._cache[key] = value

    async def invalidate(self):
        async with self._lock:
            self._cache.clear()
            logger.info("Highscores cache invalidated")


highscores_cache: Optional[HighscoresCache] = None


# Pydantic models for API request/response validation
class UserResponse(BaseModel):
    """Response model for user data."""

    user_id: int
    address: str
    tag: str | None
    priority_multiplier: int
    shares_remaining: int
    traffic_level: str


class UserUpdateRequest(BaseModel):
    """Request model for updating user profile."""

    address: str | None = None
    tag: str | None = Field(None, max_length=50)

    @validator("address")
    @classmethod
    def validate_bitcoin_address(cls, v: str | None) -> str | None:
        """Validate Bitcoin address format.

        Accepts:
        - Bech32: bc1 + 39-87 alphanumeric characters
        - Legacy P2PKH: 1 + 25-34 base58 characters
        - Legacy P2SH: 3 + 25-34 base58 characters
        - Placeholder addresses (bc1_update_in_settings_...)

        POC-level validation: format check only (no checksum verification).
        """
        if v is None:
            return v

        # Allow placeholder addresses for users created via LNURL-auth
        if v.startswith("bc1_update_in_settings_"):
            return v

        pattern = r"^(bc1[a-z0-9]{39,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$"
        if not re.match(pattern, v):
            raise ValueError("Invalid Bitcoin address format")
        return v


class ShareHistoryResponse(BaseModel):
    """Response model for paginated share history."""

    shares: list[dict]
    total: int
    limit: int
    offset: int
    has_more: bool


class TrafficStatusResponse(BaseModel):
    """Response model for traffic status."""

    traffic_level: str
    active_user_count: int


def create_app(config_path: str = "config.yaml") -> Quart:
    """Create and configure Quart application.

    Args:
        config_path: Path to configuration YAML file

    Returns:
        Configured Quart app instance
    """
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    app = Quart(__name__)

    # Load configuration
    config = load_config(config_path)
    app.config["SLICEHASH_CONFIG"] = config

    # Initialize share queue (in-memory, unbounded)
    global share_queue, share_processor, redis_consumer, sse_manager, highscores_cache
    share_queue = asyncio.Queue()

    # Initialize SSE manager
    sse_manager = SSEManager()

    # Initialize highscores cache
    highscores_cache = HighscoresCache()

    # Initialize share processor (will start background task)
    share_processor = ShareProcessor(config, share_queue, sse_manager, highscores_cache)

    # Initialize Redis stream consumer
    redis_consumer = RedisStreamConsumer(config, share_queue)

    @app.before_serving
    async def startup():
        """Start background share processor and Redis consumer."""
        # Initialize database if it doesn't exist
        db_path = Path(config.database_url)
        if not db_path.exists():
            logger.info(f"Database not found at {config.database_url}. Initializing...")
            await init_database(config.database_url)
            logger.info("Database initialized successfully")

        # Start background services (share processor loads block target on startup)
        await share_processor.start()
        await redis_consumer.start()
        logger.info("SliceHash application started")

    @app.after_serving
    async def shutdown():
        """Stop background share processor and Redis consumer."""
        await redis_consumer.stop()
        await share_processor.stop()
        logger.info("SliceHash application stopped")

    @app.get("/health")
    async def health_check():
        """Health check endpoint.

        Returns:
            JSON with status, queue size, SSE connections, and Redis connection status
        """
        redis_connected = False
        if redis_consumer:
            redis_connected = await redis_consumer.is_connected()

        return jsonify(
            {
                "status": "healthy",
                "queue_size": share_queue.qsize() if share_queue else 0,
                "sse_connections": sse_manager.get_subscriber_count(),
                "redis_connected": redis_connected,
            }
        )

    @app.get("/")
    async def landing_page():
        """Landing page with LNURL-auth QR code."""
        # Check if already authenticated
        token = request.cookies.get("auth_token")
        if token:
            config_obj = app.config["SLICEHASH_CONFIG"]
            payload = decode_jwt_token(token, config_obj)
            if payload:
                return redirect("/dashboard")

        return await render_template("landing.html")

    @app.get("/api/auth/lnurl/generate")
    async def generate_lnurl():
        """Generate new LNURL-auth challenge."""
        try:
            config_obj = app.config["SLICEHASH_CONFIG"]
            async with DatabaseManager(config_obj.database_url) as db:
                await cleanup_expired_challenges(db)
                k1, lnurl_string = await generate_k1_challenge(db, config_obj)

                logger.info(
                    f"Generated LNURL - k1: {k1[:16]}..., lnurl: {lnurl_string[:50]}..."
                )

                return jsonify({"lnurl": lnurl_string, "k1": k1}), 200
        except Exception as e:
            logger.error(f"Failed to generate LNURL: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/auth/qr/<k1>")
    async def get_qr_code(k1: str):
        """Generate QR code image for LNURL-auth."""
        try:
            config_obj = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(config_obj.database_url) as db:
                row = await db.fetchrow(
                    "SELECT expires_at FROM auth_challenges WHERE k1 = $1", k1
                )

                if not row or int(time.time()) > row["expires_at"]:
                    return jsonify({"error": "Invalid or expired challenge"}), 404

            callback_url = (
                f"{config_obj.lnurl_callback_url}?tag=login&k1={k1}&action=login"
            )
            lnurl_string = lnurl_encode(callback_url)

            qr = qrcode.QRCode(
                version=None,  # Auto-select version based on data
                error_correction=qrcode.constants.ERROR_CORRECT_H,  # High error correction for logo overlay
                box_size=8,
                border=2,
            )
            qr.add_data(lnurl_string)
            qr.make(fit=True)

            img = qr.make_image(fill_color="black", back_color="white")
            img = img.convert("RGB")  # Convert to RGB for logo overlay

            # Load and embed logo in center
            logo_path = Path(current_app.static_folder) / "favicon-32x32.png"
            if logo_path.exists():
                logo = Image.open(logo_path)

                # Calculate logo size (20% of QR code size)
                qr_width, qr_height = img.size
                logo_size = int(min(qr_width, qr_height) * 0.2)
                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

                # Add white background to logo if it has transparency
                if logo.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", logo.size, (255, 255, 255))
                    if logo.mode == "RGBA":
                        background.paste(logo, mask=logo.split()[3])
                    else:
                        background.paste(logo, mask=logo.split()[1])
                    logo = background

                # Calculate center position and paste logo
                logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                img.paste(logo, logo_pos)

            img_io = io.BytesIO()
            img.save(img_io, "PNG")
            img_io.seek(0)

            return await send_file(img_io, mimetype="image/png")
        except Exception as e:
            logger.error(f"QR code generation error: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/auth/lnurl/callback")
    async def lnurl_callback():
        """LNURL-auth callback endpoint (called by Lightning wallets)."""
        try:
            tag = request.args.get("tag")
            k1 = request.args.get("k1")
            sig = request.args.get("sig")
            key = request.args.get("key")

            if tag != "login" or not all([k1, sig, key]):
                return jsonify({"status": "ERROR", "reason": "Invalid parameters"}), 400

            config_obj = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(config_obj.database_url) as db:
                # Verify challenge exists and is valid
                row = await db.fetchrow(
                    "SELECT used, expires_at FROM auth_challenges WHERE k1 = $1", k1
                )

                if not row:
                    return jsonify(
                        {"status": "ERROR", "reason": "Invalid challenge"}
                    ), 400

                used, expires_at = row["used"], row["expires_at"]

                if used:
                    return jsonify(
                        {"status": "ERROR", "reason": "Challenge already used"}
                    ), 400

                if int(time.time()) > expires_at:
                    return jsonify(
                        {"status": "ERROR", "reason": "Challenge expired"}
                    ), 400

                # Verify signature
                if not await verify_lnurl_signature(k1, sig, key):
                    return jsonify(
                        {"status": "ERROR", "reason": "Invalid signature"}
                    ), 400

                # Mark challenge as used
                await mark_challenge_used(db, k1)

                # Get or create user
                user_id = await get_or_create_user_by_pubkey(db, key)

                # Generate JWT token
                token = create_jwt_token(user_id, key, config_obj)

            # Notify via SSE (instant push to waiting browsers)
            notification = AuthNotification(token=token, k1=k1)
            await sse_manager.notify(notification)

            return jsonify({"status": "OK"}), 200
        except Exception as e:
            logger.error(f"LNURL callback error: {e}")
            return jsonify({"status": "ERROR", "reason": "Internal error"}), 500

    @app.get("/api/auth/stream/<k1>")
    async def stream_auth_status(k1: str):
        """SSE endpoint for real-time authentication status updates.

        Args:
            k1: Challenge identifier

        Returns:
            Server-Sent Events stream with:
            - connected: Initial connection event
            - authenticated: Auth success with token
        """
        async def event_stream():
            queue = None
            try:
                # Subscribe using k1 as channel identifier
                queue = await sse_manager.subscribe(f"auth:{k1}")
                yield f"event: connected\ndata: {json.dumps({'k1': k1})}\n\n"

                # Wait for auth success notification (no timeout, browser will handle)
                notification = await queue.get()  # Receives AuthNotification object
                yield f"event: authenticated\ndata: {json.dumps(asdict(notification))}\n\n"

            except Exception as e:
                logger.error(f"Auth SSE error: {e}")
                yield f"event: error\ndata: {json.dumps({'error': 'Internal error'})}\n\n"
            finally:
                if queue:
                    await sse_manager.unsubscribe(f"auth:{k1}", queue)

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/auth/logout")
    async def logout():
        """Log out current user."""
        response = redirect("/")
        response.delete_cookie("auth_token")
        return response

    @app.get("/api/users/me")
    @require_auth
    async def get_current_user():
        """Return current user's data including quota and traffic level.

        Returns:
            200: User data JSON
            404: User not found
            500: Internal error
        """
        try:
            user_id = request.user_id
            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Fetch user record
                row = await db.fetchrow(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = $1",
                    user_id,
                )

                if not row:
                    return jsonify({"error": "User not found"}), 404

                user_id, address, tag, priority = (
                    row["user_id"],
                    row["address"],
                    row["tag"],
                    row["priority_multiplier"],
                )

                # Calculate derived fields using existing business logic
                shares_remaining = await calculate_shares_remaining(db, user_id)
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify(
                    {
                        "user_id": user_id,
                        "address": address,
                        "tag": tag,
                        "priority_multiplier": priority,
                        "shares_remaining": shares_remaining,
                        "traffic_level": traffic_level.value,
                    }
                ), 200

        except Exception as e:
            logger.error(f"Failed to fetch user: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.patch("/api/users/me")
    @require_auth
    async def update_user():
        """Update current user's address and/or tag.

        Request body:
            {
                "address": "bc1...",  # optional, validated
                "tag": "my-label"     # optional, max 50 chars
            }

        Returns:
            200: Updated user data
            400: Validation error or no fields to update
            500: Internal error
        """
        try:
            user_id = request.user_id
            data = await request.get_json()

            # Validate request with Pydantic
            update_req = UserUpdateRequest(**data)

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Build dynamic UPDATE query (only include non-None fields)
                updates = []
                params = []
                param_num = 1

                if update_req.address is not None:
                    updates.append(f"address = ${param_num}")
                    params.append(update_req.address)
                    param_num += 1

                if update_req.tag is not None:
                    updates.append(f"tag = ${param_num}")
                    params.append(update_req.tag)
                    param_num += 1

                if not updates:
                    return jsonify({"error": "No fields to update"}), 400

                # Execute update
                params.append(user_id)
                await db.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = ${param_num}",
                    *params,
                )

                # Return updated user data (reuse GET logic)
                row = await db.fetchrow(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = $1",
                    user_id,
                )
                if not row:
                    return jsonify({"error": "User not found"}), 404

                user_id, address, tag, priority = (
                    row["user_id"],
                    row["address"],
                    row["tag"],
                    row["priority_multiplier"],
                )
                shares_remaining = await calculate_shares_remaining(db, user_id)
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify(
                    {
                        "user_id": user_id,
                        "address": address,
                        "tag": tag,
                        "priority_multiplier": priority,
                        "shares_remaining": shares_remaining,
                        "traffic_level": traffic_level.value,
                    }
                ), 200

        except ValidationError as e:
            # Pydantic validation failed
            return jsonify(
                {
                    "error": "Validation failed",
                    "details": [
                        {
                            "field": err["loc"][0] if err["loc"] else "unknown",
                            "message": err["msg"],
                        }
                        for err in e.errors()
                    ],
                }
            ), 400
        except ValueError as e:
            # Field validator raised ValueError
            return jsonify({"error": "Validation failed", "details": str(e)}), 400
        except Exception as e:
            logger.error(f"Failed to update user: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/users/me/shares")
    @require_auth
    async def get_share_history():
        """Return paginated share history for current user.

        Query parameters:
            limit: Results per page (default 50, max 100)
            offset: Number of results to skip (default 0)

        Returns:
            200: Paginated share history
            400: Invalid query parameters
            500: Internal error
        """
        try:
            user_id = request.user_id
            # Parse and validate query params
            limit = int(request.args.get("limit", 50))
            offset = int(request.args.get("offset", 0))

            # Clamp to reasonable values
            limit = min(max(limit, 1), 100)
            offset = max(offset, 0)

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Get total count
                total = await db.fetchval(
                    "SELECT COUNT(*) FROM share_events WHERE user_id = $1", user_id
                )

                # Get paginated results (newest first)
                rows = await db.fetch(
                    """
                    SELECT submitted_at, level, is_block, share_hash, billable, shares_consumed, coinbase_prefix_tag
                    FROM share_events
                    WHERE user_id = $1
                    ORDER BY submitted_at DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )

                shares = [
                    {
                        "submitted_at": row["submitted_at"].isoformat()
                        if row["submitted_at"]
                        else None,
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["coinbase_prefix_tag"],
                    }
                    for row in rows
                ]

                return jsonify(
                    {
                        "shares": shares,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < total,
                    }
                ), 200

        except ValueError:
            return jsonify({"error": "Invalid limit or offset parameter"}), 400
        except Exception as e:
            logger.error(f"Failed to fetch share history: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/users/me/shares/stream")
    @require_auth
    async def stream_shares():
        """SSE endpoint for real-time share notifications.

        Returns:
            Server-Sent Events stream with:
            - connected: Initial connection event
            - share: New share notification
            - heartbeat: Keep-alive every 30s
        """
        user_id = request.user_id

        async def event_stream():
            queue = None
            try:
                queue = await sse_manager.subscribe(f"user:{user_id}")
                yield f"event: connected\ndata: {json.dumps({'user_id': user_id})}\n\n"

                while True:
                    try:
                        notification = await asyncio.wait_for(queue.get(), timeout=30.0)
                        event_data = {
                            "share_id": notification.share_id,
                            "submitted_at": notification.submitted_at.isoformat()
                            if hasattr(notification.submitted_at, "isoformat")
                            else notification.submitted_at,
                            "level": notification.level,
                            "is_block": notification.is_block,
                            "share_hash": notification.share_hash,
                            "billable": notification.billable,
                            "shares_consumed": notification.shares_consumed,
                            "block_target_level": notification.block_target_level,
                            "tag": notification.tag,
                        }
                        yield f"id: {notification.share_id}\nevent: share\ndata: {json.dumps(event_data)}\n\n"
                    except asyncio.TimeoutError:
                        # Heartbeat every 30s
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.now().isoformat()})}\n\n"
            finally:
                if queue:
                    await sse_manager.unsubscribe(f"user:{user_id}", queue)

        return Response(
            event_stream(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.get("/api/users/me/shares/recovery")
    @require_auth
    async def recover_missed_shares():
        """Fetch shares missed during disconnect.

        Query parameters:
            since_id: Last share ID received (preferred for reliability)
            since_time: Last timestamp received (fallback)
            limit: Maximum shares to return (default 50, max 200)

        Returns:
            200: List of missed shares with pagination info
            400: Missing required parameters
            500: Internal error
        """
        user_id = request.user_id
        since_id = request.args.get("since_id", type=int)
        since_time = request.args.get("since_time", type=str)
        limit = min(int(request.args.get("limit", 50)), 200)

        if not since_id and not since_time:
            return jsonify({"error": "Must provide since_id or since_time"}), 400

        try:
            # Get current block target level from cached value (updated by share processor)
            block_target_level = 0
            if share_processor and share_processor.current_block_target:
                block_target_level = calculate_level(
                    share_processor.current_block_target
                )

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                if since_id:
                    query = """
                        SELECT id, submitted_at, level, is_block, share_hash, billable, shares_consumed, coinbase_prefix_tag
                        FROM share_events
                        WHERE user_id = $1 AND id > $2
                        ORDER BY id ASC
                        LIMIT $3
                    """
                    rows = await db.fetch(query, user_id, since_id, limit)
                else:
                    query = """
                        SELECT id, submitted_at, level, is_block, share_hash, billable, shares_consumed, coinbase_prefix_tag
                        FROM share_events
                        WHERE user_id = $1 AND submitted_at > $2
                        ORDER BY id ASC
                        LIMIT $3
                    """
                    rows = await db.fetch(query, user_id, since_time, limit)

                shares = [
                    {
                        "share_id": row["id"],
                        "submitted_at": row["submitted_at"].isoformat()
                        if row["submitted_at"]
                        else None,
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["coinbase_prefix_tag"],
                        "block_target_level": int(block_target_level),
                    }
                    for row in rows
                ]

                return jsonify(
                    {
                        "shares": shares,
                        "count": len(shares),
                        "has_more": len(shares) == limit,
                    }
                )

        except Exception as e:
            logger.error(f"Failed to recover missed shares: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/traffic/status")
    async def get_traffic_status():
        """Return current traffic level and active user count.

        Returns:
            200: Traffic status data
            500: Internal error
        """
        try:
            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify(
                    {
                        "traffic_level": traffic_level.value,
                        "active_user_count": len(active_users),
                    }
                ), 200

        except Exception as e:
            logger.error(f"Failed to fetch traffic status: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/block-target")
    async def get_block_target():
        """Return current block target and its level.

        Returns:
            200: Block target data with target hash and level
            500: Internal error
        """
        try:
            # Get current block target from cached value (updated by share processor)
            block_target = None
            if share_processor and share_processor.current_block_target:
                block_target = share_processor.current_block_target

            # Calculate level for the target
            level = calculate_level(block_target) if block_target else 0

            return jsonify({"block_target": block_target, "level": level}), 200

        except Exception as e:
            logger.error(f"Failed to fetch block target: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/users/me/purchases")
    @require_auth
    async def get_purchase_history():
        """Return purchase history (transactions) for current user.

        Returns:
            200: List of transactions
            500: Internal error
        """
        try:
            user_id = request.user_id
            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Get all transactions for user (newest first)
                rows = await db.fetch(
                    """
                    SELECT transaction_id, amount, created_at
                    FROM transactions
                    WHERE user_id = $1
                    ORDER BY created_at DESC
                    """,
                    user_id,
                )

                purchases = [
                    {
                        "transaction_id": row["transaction_id"],
                        "amount": row["amount"],
                        "created_at": row["created_at"],
                    }
                    for row in rows
                ]

                return jsonify({"purchases": purchases, "total": len(purchases)}), 200

        except Exception as e:
            logger.error(f"Failed to fetch purchase history: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.post("/api/users/me/purchases")
    @require_auth
    async def create_purchase():
        """Create a new purchase transaction for the current user.

        Request body:
            {
                "amount": int  # Number of shares to purchase (must be positive)
            }

        Returns:
            201: Purchase created successfully
            400: Invalid request (missing/invalid amount, or BTC address not set)
            500: Internal error
        """
        try:
            user_id = request.user_id
            data = await request.get_json()

            if not data or "amount" not in data:
                return jsonify({"error": "Missing 'amount' field"}), 400

            amount = data["amount"]

            # Validate amount
            if not isinstance(amount, int) or amount <= 0:
                return jsonify({"error": "Amount must be a positive integer"}), 400

            # Check if user has set a valid Bitcoin address
            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                user = await db.fetchrow(
                    "SELECT address FROM users WHERE user_id = $1", user_id
                )

                if not user:
                    return jsonify({"error": "User not found"}), 404

                # Check if address is a placeholder
                if user["address"].startswith("bc1_update_in_settings_"):
                    return jsonify(
                        {
                            "error": "Please set your Bitcoin address in Settings before purchasing shares"
                        }
                    ), 400

                # Create transaction
                row = await db.fetchrow(
                    """
                    INSERT INTO transactions (user_id, amount, created_at)
                    VALUES ($1, $2, NOW())
                    RETURNING transaction_id, amount, created_at
                    """,
                    user_id,
                    amount,
                )

                return jsonify(
                    {
                        "transaction_id": row["transaction_id"],
                        "amount": row["amount"],
                        "created_at": row["created_at"],
                    }
                ), 201

        except Exception as e:
            logger.error(f"Failed to create purchase: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/highscores/24h")
    async def get_highscores_24h():
        """Return top 5 shares from last 24 hours by level.

        Returns:
            200: List of top 5 shares with user info
            500: Internal error
        """
        try:
            # Check cache first
            cached = await highscores_cache.get("24h")
            if cached:
                logger.debug("Returning cached 24h highscores")
                return jsonify(cached), 200

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                rows = await db.fetch(
                    """
                    SELECT
                        se.submitted_at, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        se.coinbase_prefix_tag, se.coinbase_address,
                        COALESCE(se.coinbase_prefix_tag, se.coinbase_address) as username
                    FROM share_events se
                    WHERE se.submitted_at >= NOW() - INTERVAL '24 hours'
                    ORDER BY se.level DESC, se.submitted_at DESC
                    LIMIT 5
                    """
                )

                shares = [
                    {
                        "submitted_at": row["submitted_at"].isoformat()
                        if row["submitted_at"]
                        else None,
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "user_id": row["user_id"],
                        "tag": row["coinbase_prefix_tag"],
                        "address": row["coinbase_address"],
                        "username": row["username"],
                    }
                    for row in rows
                ]

                result = {"shares": shares}

                # Cache the result
                await highscores_cache.set("24h", result)
                logger.debug("Cached 24h highscores")

                return jsonify(result), 200

        except Exception as e:
            logger.error(f"Failed to fetch 24h highscores: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/highscores/all-time")
    async def get_highscores_all_time():
        """Return top 5 shares of all time by level.

        Returns:
            200: List of top 5 shares with user info
            500: Internal error
        """
        try:
            # Check cache first
            cached = await highscores_cache.get("all-time")
            if cached:
                logger.debug("Returning cached all-time highscores")
                return jsonify(cached), 200

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                rows = await db.fetch(
                    """
                    SELECT
                        se.submitted_at, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        se.coinbase_prefix_tag, se.coinbase_address,
                        COALESCE(se.coinbase_prefix_tag, se.coinbase_address) as username
                    FROM share_events se
                    ORDER BY se.level DESC, se.submitted_at DESC
                    LIMIT 5
                    """
                )

                shares = [
                    {
                        "submitted_at": row["submitted_at"].isoformat()
                        if row["submitted_at"]
                        else None,
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "user_id": row["user_id"],
                        "tag": row["coinbase_prefix_tag"],
                        "address": row["coinbase_address"],
                        "username": row["username"],
                    }
                    for row in rows
                ]

                result = {"shares": shares}

                # Cache the result
                await highscores_cache.set("all-time", result)
                logger.debug("Cached all-time highscores")

                return jsonify(result), 200

        except Exception as e:
            logger.error(f"Failed to fetch all-time highscores: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/shares")
    @require_auth
    async def get_shares():
        """Return current user's shares with pagination, supporting multiple view modes.

        Query parameters:
            mode: View mode - 'recent', 'best-24h', 'best-all-time' (default: 'recent')
            limit: Results per page (default 20, max 100)
            offset: Number of results to skip (default 0)

        Returns:
            200: Paginated shares for current user
            400: Invalid parameters
            500: Internal error
        """
        try:
            user_id = request.user_id
            mode = request.args.get("mode", "recent")
            limit = int(request.args.get("limit", 20))
            offset = int(request.args.get("offset", 0))

            limit = min(max(limit, 1), 100)
            offset = max(offset, 0)

            # Configure query based on mode
            if mode == "recent":
                where_clause = "WHERE user_id = $1"
                order_by = "ORDER BY submitted_at DESC"
            elif mode == "best-24h":
                where_clause = (
                    "WHERE user_id = $1 AND submitted_at >= NOW() - INTERVAL '24 hours'"
                )
                order_by = "ORDER BY level DESC, submitted_at DESC"
            elif mode == "best-all-time":
                where_clause = "WHERE user_id = $1"
                order_by = "ORDER BY level DESC, submitted_at DESC"
            else:
                return jsonify(
                    {
                        "error": "Invalid mode. Must be 'recent', 'best-24h', or 'best-all-time'"
                    }
                ), 400

            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Get total count
                count_query = f"SELECT COUNT(*) FROM share_events {where_clause}"
                total = await db.fetchval(count_query, user_id)

                # Get paginated results
                query = f"""
                    SELECT
                        id, submitted_at, level, is_block, share_hash,
                        billable, shares_consumed, coinbase_prefix_tag
                    FROM share_events
                    {where_clause}
                    {order_by}
                    LIMIT $2 OFFSET $3
                """
                rows = await db.fetch(query, user_id, limit, offset)

                shares = [
                    {
                        "share_id": row["id"],
                        "submitted_at": row["submitted_at"].isoformat()
                        if row["submitted_at"]
                        else None,
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["coinbase_prefix_tag"],
                    }
                    for row in rows
                ]

                return jsonify(
                    {
                        "shares": shares,
                        "total": total,
                        "limit": limit,
                        "offset": offset,
                        "has_more": offset + limit < total,
                    }
                ), 200

        except ValueError:
            return jsonify({"error": "Invalid limit or offset parameter"}), 400
        except Exception as e:
            logger.error(f"Failed to fetch shares: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/dashboard")
    @require_auth
    async def dashboard():
        """Render dashboard page showing share activity and stats.

        Returns:
            HTML template for main dashboard
        """
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            shares_remaining = await calculate_shares_remaining(db, request.user_id)

        # Get current block target level from cached value (updated by share processor)
        block_target_level = 0
        if share_processor and share_processor.current_block_target:
            block_target_level = calculate_level(share_processor.current_block_target)

        return await render_template(
            "dashboard.html",
            shares_remaining=shares_remaining,
            block_target_level=int(block_target_level),
        )

    @app.get("/settings")
    @require_auth
    async def settings_page():
        """Render settings page for user configuration.

        Returns:
            HTML template for settings page
        """
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            shares_remaining = await calculate_shares_remaining(db, request.user_id)

        # Get current block target level from cached value (updated by share processor)
        block_target_level = 0
        if share_processor and share_processor.current_block_target:
            block_target_level = calculate_level(share_processor.current_block_target)

        return await render_template(
            "settings.html",
            shares_remaining=shares_remaining,
            block_target_level=int(block_target_level),
        )

    @app.get("/purchases")
    @require_auth
    async def purchases_page():
        """Render purchases page for viewing purchase history.

        Returns:
            HTML template for purchases page
        """
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            shares_remaining = await calculate_shares_remaining(db, request.user_id)

        # Get current block target level from cached value (updated by share processor)
        block_target_level = 0
        if share_processor and share_processor.current_block_target:
            block_target_level = calculate_level(share_processor.current_block_target)

        return await render_template(
            "purchases.html",
            shares_remaining=shares_remaining,
            block_target_level=int(block_target_level),
        )

    @app.get("/highscores")
    @require_auth
    async def highscores_page():
        """Render highscores page showing top shares.

        Returns:
            HTML template for highscores page
        """
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            shares_remaining = await calculate_shares_remaining(db, request.user_id)

        # Get current block target level from cached value (updated by share processor)
        block_target_level = 0
        if share_processor and share_processor.current_block_target:
            block_target_level = calculate_level(share_processor.current_block_target)

        return await render_template(
            "highscores.html",
            shares_remaining=shares_remaining,
            block_target_level=int(block_target_level),
        )

    return app


# For running with hypercorn/uvicorn
app = create_app()
