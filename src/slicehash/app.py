"""Quart web application for SliceHash mining backend.

This module provides the HTTP server with:
- Fast webhook endpoint for receiving share events from pool (<10ms response)
- Background share processing with rotation logic
- Health check endpoint
"""

import asyncio
import logging
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator, ValidationError
from quart import Quart, request, jsonify, render_template

from .config import load_config, Config
from .db.manager import DatabaseManager
from .quota import calculate_shares_remaining, get_active_users
from .priority import calculate_traffic_level, TrafficLevel
from .share_processor import ShareProcessor

logger = logging.getLogger(__name__)

# Global references (initialized in create_app)
share_queue: Optional[asyncio.Queue] = None
share_processor: Optional[ShareProcessor] = None
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

    @field_validator('address')
    @classmethod
    def validate_bitcoin_address(cls, v: str | None) -> str | None:
        """Validate Bitcoin address format.

        Accepts:
        - Bech32: bc1 + 39-87 alphanumeric characters
        - Legacy P2PKH: 1 + 25-34 base58 characters
        - Legacy P2SH: 3 + 25-34 base58 characters

        POC-level validation: format check only (no checksum verification).
        """
        if v is None:
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
    app = Quart(__name__)

    # Load configuration
    config = load_config(config_path)
    app.config["SLICEHASH_CONFIG"] = config

    # Initialize share queue (in-memory, unbounded)
    global share_queue, share_processor
    share_queue = asyncio.Queue()

    # Initialize share processor (will start background task)
    share_processor = ShareProcessor(config, share_queue)

    @app.before_serving
    async def startup():
        """Start background share processor and load block target."""
        global current_block_target

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
        logger.info("SliceHash application started")

    @app.after_serving
    async def shutdown():
        """Stop background share processor."""
        await share_processor.stop()
        logger.info("SliceHash application stopped")

    @app.post("/api/shares/webhook")
    async def webhook_handler():
        """Receive share events from pool.

        Must respond <10ms - immediately queue and return 200.

        Expected JSON payload:
        {
            "user_id": str,
            "nonce": int,
            "ntime": int,
            "version": int,
            "coinbase_address": str,
            "coinbase_prefix_tag": str,
            "share_hash": str (optional),
            "is_block": bool,
            "block_target": str (optional),
            "job_id": int (optional),
            "timestamp_secs": int (optional)
        }

        Required fields: all except job_id and timestamp_secs

        Returns:
            JSON response with status and 200 OK, or error with 400/500
        """
        try:
            data = await request.get_json()

            # Minimal validation (just check required fields exist)
            required = ["user_id", "nonce", "ntime", "version", "coinbase_address",
                       "coinbase_prefix_tag", "is_block"]
            if not all(k in data for k in required):
                return jsonify({"error": "Missing required fields"}), 400

            # Queue for background processing (non-blocking)
            share_queue.put_nowait(data)

            # Immediate response (target <10ms)
            return jsonify({"status": "queued"}), 200

        except Exception as e:
            # Log but don't block (fast failure)
            logger.error(f"Webhook error: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/health")
    async def health_check():
        """Health check endpoint.

        Returns:
            JSON with status and queue size
        """
        return jsonify({
            "status": "healthy",
            "queue_size": share_queue.qsize() if share_queue else 0
        })

    @app.get("/api/users/me")
    async def get_current_user():
        """Return current user's data including quota and traffic level.

        POC: Defaults to user_id=1 (no auth system yet).

        Returns:
            200: User data JSON
            404: User not found
            500: Internal error
        """
        try:
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Fetch user record
                cursor = await db.execute(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                    (1,)
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
    async def update_user():
        """Update current user's address and/or tag.

        POC: Updates user_id=1 (no auth system yet).

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
                params.append(1)  # user_id
                await db.execute(
                    f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                    tuple(params)
                )
                await db.commit()

                # Return updated user data (reuse GET logic)
                cursor = await db.execute(
                    "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                    (1,)
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
    async def get_share_history():
        """Return paginated share history for current user.

        POC: Returns history for user_id=1 (no auth system yet).

        Query parameters:
            limit: Results per page (default 50, max 100)
            offset: Number of results to skip (default 0)

        Returns:
            200: Paginated share history
            400: Invalid query parameters
            500: Internal error
        """
        try:
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
                    (1,)
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
                    (1, limit, offset)
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
    async def get_purchase_history():
        """Return purchase history (transactions) for current user.

        POC: Returns history for user_id=1 (no auth system yet).

        Returns:
            200: List of transactions
            500: Internal error
        """
        try:
            async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
                # Get all transactions for user (newest first)
                cursor = await db.execute(
                    """
                    SELECT transaction_id, amount, created_at
                    FROM transactions
                    WHERE user_id = ?
                    ORDER BY created_at DESC
                    """,
                    (1,)
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

    @app.get("/")
    async def dashboard():
        """Render dashboard page showing share activity and stats.

        Returns:
            HTML template for main dashboard
        """
        return await render_template("dashboard.html")

    @app.get("/settings")
    async def settings_page():
        """Render settings page for user configuration.

        Returns:
            HTML template for settings page
        """
        return await render_template("settings.html")

    @app.get("/purchases")
    async def purchases_page():
        """Render purchases page for viewing purchase history.

        Returns:
            HTML template for purchases page
        """
        return await render_template("purchases.html")

    @app.get("/highscores")
    async def highscores_page():
        """Render highscores page showing top shares.

        Returns:
            HTML template for highscores page
        """
        return await render_template("highscores.html")

    return app


# For running with hypercorn/uvicorn
app = create_app()
