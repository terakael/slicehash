"""Quart web application for SliceHash mining backend.

This module provides the HTTP server with:
- Fast webhook endpoint for receiving share events from pool (<10ms response)
- Background share processing with rotation logic
- Health check endpoint
"""

import asyncio
import json
import logging
import re
import time
import io
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, validator, ValidationError
from quart import Quart, request, jsonify, render_template, Response, send_file, redirect, current_app
import qrcode
from PIL import Image

from .config import load_config, Config
from .db.manager import DatabaseManager, init_database
from .quota import calculate_shares_remaining, get_active_users
from .priority import calculate_traffic_level, TrafficLevel
from .share_processor import ShareProcessor
from .sse_manager import SSEManager, ShareNotification
from .redis_consumer import RedisStreamConsumer
from .auth import (
    generate_k1_challenge,
    verify_lnurl_signature,
    create_jwt_token,
    decode_jwt_token,
    require_auth,
    get_or_create_user_by_pubkey,
    cleanup_expired_challenges,
    mark_challenge_used,
    lnurl_encode,
)

logger = logging.getLogger(__name__)

# Global references (initialized in create_app)
share_queue: Optional[asyncio.Queue] = None
share_processor: Optional[ShareProcessor] = None
redis_consumer: Optional[RedisStreamConsumer] = None
sse_manager: Optional[SSEManager] = None
current_block_target: Optional[str] = None


def calculate_level(hash_str: str) -> int:
    """Calculate the level of a hash (number of leading zeros minus 5).

    Args:
        hash_str: Hexadecimal hash string

    Returns:
        Level value (leading zeros - 5), minimum 0
    """
    if not hash_str:
        return 0

    leading_zeros = 0
    for char in hash_str:
        if char == '0':
            leading_zeros += 1
        else:
            break

    return max(0, leading_zeros - 5)


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

    @validator('address')
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
        if v.startswith('bc1_update_in_settings_'):
            return v

        pattern = r'^(bc1[a-z0-9]{39,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Bitcoin address format')
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
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    app = Quart(__name__)

    # Load configuration
    config = load_config(config_path)
    app.config["SLICEHASH_CONFIG"] = config

    # Initialize share queue (in-memory, unbounded)
    global share_queue, share_processor, redis_consumer, sse_manager
    share_queue = asyncio.Queue()

    # Initialize SSE manager
    sse_manager = SSEManager()

    # Initialize share processor (will start background task)
    share_processor = ShareProcessor(config, share_queue, sse_manager)

    # Initialize Redis stream consumer
    redis_consumer = RedisStreamConsumer(config, share_queue)

    @app.before_serving
    async def startup():
        """Start background share processor, Redis consumer, and load block target."""
        global current_block_target

        # Initialize database if it doesn't exist
        db_path = Path(config.database_path)
        if not db_path.exists():
            logger.info(f"Database not found at {config.database_path}. Initializing...")
            await init_database(config.database_path)
            logger.info("Database initialized successfully")

        # Load current block target from database
        async with DatabaseManager(config.database_path) as db:
            cursor = await db.execute(
                "SELECT value FROM global_state WHERE key = 'current_block_target'"
            )
            row = await cursor.fetchone()
            if row:
                current_block_target = row[0]
                logger.info(f"Loaded block target: {current_block_target}")

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

        return jsonify({
            "status": "healthy",
            "queue_size": share_queue.qsize() if share_queue else 0,
            "sse_connections": sse_manager.get_subscriber_count() if sse_manager else 0,
            "redis_connected": redis_connected
        })

    @app.get("/")
    async def landing_page():
        """Landing page with LNURL-auth QR code."""
        # Check if already authenticated
        token = request.cookies.get('auth_token')
        if token:
            config_obj = app.config["SLICEHASH_CONFIG"]
            payload = decode_jwt_token(token, config_obj)
            if payload:
                return redirect('/dashboard')

        return await render_template("landing.html")

    @app.get("/api/auth/lnurl/generate")
    async def generate_lnurl():
        """Generate new LNURL-auth challenge."""
        try:
            config_obj = app.config["SLICEHASH_CONFIG"]
            async with DatabaseManager(config_obj.database_path) as db:
                await cleanup_expired_challenges(db)
                k1, lnurl_string = await generate_k1_challenge(db, config_obj)

                logger.info(f"Generated LNURL - k1: {k1[:16]}..., lnurl: {lnurl_string[:50]}...")

                return jsonify({
                    "lnurl": lnurl_string,
                    "k1": k1
                }), 200
        except Exception as e:
            logger.error(f"Failed to generate LNURL: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/auth/qr/<k1>")
    async def get_qr_code(k1: str):
        """Generate QR code image for LNURL-auth."""
        try:
            config_obj = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(config_obj.database_path) as db:
                cursor = await db.execute(
                    "SELECT expires_at FROM auth_challenges WHERE k1 = ?",
                    (k1,)
                )
                row = await cursor.fetchone()

                if not row or int(time.time()) > row[0]:
                    return jsonify({"error": "Invalid or expired challenge"}), 404

            callback_url = f"{config_obj.lnurl_callback_url}?tag=login&k1={k1}&action=login"
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
            img = img.convert('RGB')  # Convert to RGB for logo overlay

            # Load and embed logo in center
            logo_path = Path(current_app.static_folder) / "favicon-32x32.png"
            if logo_path.exists():
                logo = Image.open(logo_path)

                # Calculate logo size (20% of QR code size)
                qr_width, qr_height = img.size
                logo_size = int(min(qr_width, qr_height) * 0.2)
                logo = logo.resize((logo_size, logo_size), Image.Resampling.LANCZOS)

                # Add white background to logo if it has transparency
                if logo.mode in ('RGBA', 'LA'):
                    background = Image.new('RGB', logo.size, (255, 255, 255))
                    if logo.mode == 'RGBA':
                        background.paste(logo, mask=logo.split()[3])
                    else:
                        background.paste(logo, mask=logo.split()[1])
                    logo = background

                # Calculate center position and paste logo
                logo_pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
                img.paste(logo, logo_pos)

            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)

            return await send_file(img_io, mimetype='image/png')
        except Exception as e:
            logger.error(f"QR code generation error: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/auth/lnurl/callback")
    async def lnurl_callback():
        """LNURL-auth callback endpoint (called by Lightning wallets)."""
        try:
            tag = request.args.get('tag')
            k1 = request.args.get('k1')
            sig = request.args.get('sig')
            key = request.args.get('key')

            if tag != 'login' or not all([k1, sig, key]):
                return jsonify({"status": "ERROR", "reason": "Invalid parameters"}), 400

            config_obj = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(config_obj.database_path) as db:
                # Verify challenge exists and is valid
                cursor = await db.execute(
                    "SELECT used, expires_at FROM auth_challenges WHERE k1 = ?",
                    (k1,)
                )
                row = await cursor.fetchone()

                if not row:
                    return jsonify({"status": "ERROR", "reason": "Invalid challenge"}), 400

                used, expires_at = row

                if used:
                    return jsonify({"status": "ERROR", "reason": "Challenge already used"}), 400

                if int(time.time()) > expires_at:
                    return jsonify({"status": "ERROR", "reason": "Challenge expired"}), 400

                # Verify signature
                if not await verify_lnurl_signature(k1, sig, key):
                    return jsonify({"status": "ERROR", "reason": "Invalid signature"}), 400

                # Mark challenge as used
                await mark_challenge_used(db, k1)

                # Get or create user
                user_id = await get_or_create_user_by_pubkey(db, key)

                # Generate JWT token
                token = create_jwt_token(user_id, key, config_obj)

                # Store token temporarily for polling
                await db.execute(
                    "INSERT INTO auth_tokens (k1, user_id, token, created_at) VALUES (?, ?, ?, ?)",
                    (k1, user_id, token, int(time.time()))
                )
                await db.commit()

                return jsonify({"status": "OK"}), 200
        except Exception as e:
            logger.error(f"LNURL callback error: {e}")
            return jsonify({"status": "ERROR", "reason": "Internal error"}), 500

    @app.get("/api/auth/poll")
    async def poll_auth_status():
        """Poll for authentication status (called by browser)."""
        try:
            k1 = request.args.get('k1')
            if not k1:
                return jsonify({"error": "Missing k1 parameter"}), 400

            config_obj = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(config_obj.database_path) as db:
                cursor = await db.execute(
                    "SELECT token FROM auth_tokens WHERE k1 = ?",
                    (k1,)
                )
                row = await cursor.fetchone()

                if row:
                    token = row[0]

                    # Clean up token from database
                    await db.execute("DELETE FROM auth_tokens WHERE k1 = ?", (k1,))
                    await db.commit()

                    return jsonify({"authenticated": True, "token": token}), 200
                else:
                    return jsonify({"authenticated": False}), 200
        except Exception as e:
            logger.error(f"Poll auth error: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/auth/logout")
    async def logout():
        """Log out current user."""
        response = redirect('/')
        response.delete_cookie('auth_token')
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
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Fetch user record
                cursor = await db.execute(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()

                if not row:
                    return jsonify({"error": "User not found"}), 404

                user_id, address, tag, priority = row

                # Calculate derived fields using existing business logic
                shares_remaining = await calculate_shares_remaining(db, user_id)
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify({
                    "user_id": user_id,
                    "address": address,
                    "tag": tag,
                    "priority_multiplier": priority,
                    "shares_remaining": shares_remaining,
                    "traffic_level": traffic_level.value
                }), 200

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

            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Build dynamic UPDATE query (only include non-None fields)
                updates = []
                params = []

                if update_req.address is not None:
                    updates.append("address = ?")
                    params.append(update_req.address)

                if update_req.tag is not None:
                    updates.append("tag = ?")
                    params.append(update_req.tag)

                if not updates:
                    return jsonify({"error": "No fields to update"}), 400

                # Execute update
                params.append(user_id)
                await db.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                    tuple(params)
                )
                await db.commit()

                # Return updated user data (reuse GET logic)
                cursor = await db.execute(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return jsonify({"error": "User not found"}), 404

                user_id, address, tag, priority = row
                shares_remaining = await calculate_shares_remaining(db, user_id)
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify({
                    "user_id": user_id,
                    "address": address,
                    "tag": tag,
                    "priority_multiplier": priority,
                    "shares_remaining": shares_remaining,
                    "traffic_level": traffic_level.value
                }), 200

        except ValidationError as e:
            # Pydantic validation failed
            return jsonify({
                "error": "Validation failed",
                "details": [{"field": err["loc"][0] if err["loc"] else "unknown", "message": err["msg"]} for err in e.errors()]
            }), 400
        except ValueError as e:
            # Field validator raised ValueError
            return jsonify({
                "error": "Validation failed",
                "details": str(e)
            }), 400
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
            limit = int(request.args.get('limit', 50))
            offset = int(request.args.get('offset', 0))

            # Clamp to reasonable values
            limit = min(max(limit, 1), 100)
            offset = max(offset, 0)

            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Get total count
                cursor = await db.execute(
                    "SELECT COUNT(*) FROM share_events WHERE user_id = ?",
                    (user_id,)
                )
                total = (await cursor.fetchone())[0]

                # Get paginated results (newest first)
                cursor = await db.execute(
                    """
                    SELECT submitted_at, level, is_block, share_hash, billable, shares_consumed
                    FROM share_events
                    WHERE user_id = ?
                    ORDER BY submitted_at DESC
                    LIMIT ? OFFSET ?
                    """,
                    (user_id, limit, offset)
                )
                rows = await cursor.fetchall()

                shares = [
                    {
                        "submitted_at": row[0],
                        "level": row[1],
                        "is_block": bool(row[2]),
                        "share_hash": row[3],
                        "billable": bool(row[4]),
                        "shares_consumed": row[5]
                    }
                    for row in rows
                ]

                return jsonify({
                    "shares": shares,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total
                }), 200

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
                queue = await sse_manager.subscribe(user_id)
                yield f"event: connected\ndata: {json.dumps({'user_id': user_id})}\n\n"

                while True:
                    try:
                        notification = await asyncio.wait_for(queue.get(), timeout=30.0)
                        event_data = {
                            "share_id": notification.share_id,
                            "submitted_at": notification.submitted_at,
                            "level": notification.level,
                            "is_block": notification.is_block,
                            "share_hash": notification.share_hash,
                            "billable": notification.billable,
                            "shares_consumed": notification.shares_consumed
                        }
                        yield f"id: {notification.share_id}\nevent: share\ndata: {json.dumps(event_data)}\n\n"
                    except asyncio.TimeoutError:
                        # Heartbeat every 30s
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.now().isoformat()})}\n\n"
            finally:
                if queue:
                    await sse_manager.unsubscribe(user_id, queue)

        return Response(event_stream(), mimetype="text/event-stream", headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        })

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
        since_id = request.args.get('since_id', type=int)
        since_time = request.args.get('since_time', type=str)
        limit = min(int(request.args.get('limit', 50)), 200)

        if not since_id and not since_time:
            return jsonify({"error": "Must provide since_id or since_time"}), 400

        try:
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                if since_id:
                    query = """
                        SELECT id, submitted_at, level, is_block, share_hash, billable, shares_consumed
                        FROM share_events
                        WHERE user_id = ? AND id > ?
                        ORDER BY id ASC
                        LIMIT ?
                    """
                    cursor = await db.execute(query, (user_id, since_id, limit))
                else:
                    query = """
                        SELECT id, submitted_at, level, is_block, share_hash, billable, shares_consumed
                        FROM share_events
                        WHERE user_id = ? AND submitted_at > ?
                        ORDER BY id ASC
                        LIMIT ?
                    """
                    cursor = await db.execute(query, (user_id, since_time, limit))

                rows = await cursor.fetchall()
                shares = [
                    {
                        "share_id": row[0],
                        "submitted_at": row[1],
                        "level": row[2],
                        "is_block": bool(row[3]),
                        "share_hash": row[4],
                        "billable": bool(row[5]),
                        "shares_consumed": row[6]
                    }
                    for row in rows
                ]

                return jsonify({"shares": shares, "count": len(shares), "has_more": len(shares) == limit})

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
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                return jsonify({
                    "traffic_level": traffic_level.value,
                    "active_user_count": len(active_users)
                }), 200

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
            global current_block_target

            # If not in memory, try loading from database
            if current_block_target is None:
                async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                    cursor = await db.execute(
                        "SELECT value FROM global_state WHERE key = 'current_block_target'"
                    )
                    row = await cursor.fetchone()
                    if row:
                        current_block_target = row[0]

            # Calculate level for the target
            level = calculate_level(current_block_target) if current_block_target else 0

            return jsonify({
                "block_target": current_block_target,
                "level": level
            }), 200

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
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Get all transactions for user (newest first)
                cursor = await db.execute(
                    """
                    SELECT transaction_id, amount, created_at
                    FROM transactions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (user_id,)
                )
                rows = await cursor.fetchall()

                purchases = [
                    {
                        "transaction_id": row[0],
                        "amount": row[1],
                        "created_at": row[2]
                    }
                    for row in rows
                ]

                return jsonify({
                    "purchases": purchases,
                    "total": len(purchases)
                }), 200

        except Exception as e:
            logger.error(f"Failed to fetch purchase history: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/highscores/24h")
    async def get_highscores_24h():
        """Return top 5 shares from last 24 hours by level.

        Returns:
            200: List of top 5 shares with user info
            500: Internal error
        """
        try:
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                cursor = await db.execute(
                    """
                    SELECT
                        se.submitted_at, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        COALESCE(u.tag, u.address) as username
                    FROM share_events se
                    LEFT JOIN users u ON CAST(se.user_id AS INTEGER) = u.user_id
                    WHERE datetime(se.submitted_at) >= datetime('now', '-24 hours')
                    ORDER BY se.level DESC, se.submitted_at DESC
                    LIMIT 5
                    """
                )
                rows = await cursor.fetchall()

                shares = [
                    {
                        "submitted_at": row[0],
                        "level": row[1],
                        "is_block": bool(row[2]),
                        "share_hash": row[3],
                        "billable": bool(row[4]),
                        "shares_consumed": row[5],
                        "user_id": row[6],
                        "username": row[7]
                    }
                    for row in rows
                ]

                return jsonify({
                    "shares": shares
                }), 200

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
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                cursor = await db.execute(
                    """
                    SELECT
                        se.submitted_at, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        COALESCE(u.tag, u.address) as username
                    FROM share_events se
                    LEFT JOIN users u ON CAST(se.user_id AS INTEGER) = u.user_id
                    ORDER BY se.level DESC, se.submitted_at DESC
                    LIMIT 5
                    """
                )
                rows = await cursor.fetchall()

                shares = [
                    {
                        "submitted_at": row[0],
                        "level": row[1],
                        "is_block": bool(row[2]),
                        "share_hash": row[3],
                        "billable": bool(row[4]),
                        "shares_consumed": row[5],
                        "user_id": row[6],
                        "username": row[7]
                    }
                    for row in rows
                ]

                return jsonify({
                    "shares": shares
                }), 200

        except Exception as e:
            logger.error(f"Failed to fetch all-time highscores: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/dashboard")
    @require_auth
    async def dashboard():
        """Render dashboard page showing share activity and stats.

        Returns:
            HTML template for main dashboard
        """
        return await render_template("dashboard.html")

    @app.get("/settings")
    @require_auth
    async def settings_page():
        """Render settings page for user configuration.

        Returns:
            HTML template for settings page
        """
        return await render_template("settings.html")

    @app.get("/purchases")
    @require_auth
    async def purchases_page():
        """Render purchases page for viewing purchase history.

        Returns:
            HTML template for purchases page
        """
        return await render_template("purchases.html")

    @app.get("/highscores")
    @require_auth
    async def highscores_page():
        """Render highscores page showing top shares.

        Returns:
            HTML template for highscores page
        """
        return await render_template("highscores.html")

    return app


# For running with hypercorn/uvicorn
app = create_app()
