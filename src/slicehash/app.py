"""Quart web application for SliceHash mining backend.

This module provides the HTTP server with:
- Fast webhook endpoint for receiving share events from pool (<10ms response)
- Background share processing with rotation logic
- Health check endpoint
"""

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, ValidationError, validator
from quart import (
    Quart,
    Response,
    current_app,
    jsonify,
    make_response,
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
from .cln_client import CLNClient
from .coinbase_parser import parse_coinbase_transaction
from .config import Config, load_config
from .db.manager import DatabaseManager, init_database
from .difficulty_poller import DifficultyPoller
from .hash_utils import calculate_level
from .priority import TrafficLevel, calculate_traffic_level
from .qr_utils import serve_qr_image
from .quota import calculate_shares_remaining, get_active_users
from .redis_consumer import RedisStreamConsumer
from .share_processor import ShareProcessor
from .sse_manager import AuthNotification, InvoiceNotification, ShareNotification, SSEManager
from .sse_utils import create_sse_endpoint, format_sse_event

logger = logging.getLogger(__name__)

# Global references (initialized in create_app)
share_queue: Optional[asyncio.Queue] = None
share_processor: Optional[ShareProcessor] = None
redis_consumer: Optional[RedisStreamConsumer] = None
difficulty_poller: Optional[DifficultyPoller] = None
sse_manager: SSEManager
cln_client: Optional[CLNClient] = None


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
            logger.debug("Highscores cache invalidated")


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
        - Bech32 (SegWit/Taproot): bc1/tb1/bcrt1 + 39-87 alphanumeric
        - Legacy P2PKH: 1/m/n + 25-34 base58 characters
        - Legacy P2SH: 3/2 + 25-34 base58 characters
        - Placeholder addresses (bc1_update_in_settings_...)

        POC-level validation: format check only (no checksum verification).
        """
        if v is None:
            return v

        # Allow placeholder addresses for users created via LNURL-auth
        if v.startswith("bc1_update_in_settings_"):
            return v

        # Support mainnet, testnet, and regtest addresses
        pattern = (
            r"^((bc1|tb1|bcrt1)[a-z0-9]{39,87}|[13mn2][a-km-zA-HJ-NP-Z1-9]{25,34})$"
        )
        if not re.match(pattern, v):
            raise ValueError(
                "Invalid Bitcoin address format. Supported: bc1/tb1/bcrt1 (bech32), 1/3/m/n/2 (legacy)"
            )
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


async def _await_payment_task(
    invoice_id: int,
    user_id: int,
    amount_shares: int,
    label: str,
    expires_at: datetime,
    client: CLNClient,
    db_url: str,
    sse_mgr: SSEManager,
) -> None:
    """Background task: wait for a CLN invoice to be paid or expire.

    Calls CLN's waitinvoice (blocking) then updates the DB and emits an SSE
    notification to any browser tabs waiting on this invoice.
    """
    try:
        now = datetime.now(tz=timezone.utc)
        timeout = max((expires_at - now).total_seconds() + 60.0, 120.0)
        result = await client.wait_invoice(label, timeout=timeout)

        if result.status == "paid":
            async with DatabaseManager(db_url) as db:
                await db.execute(
                    "UPDATE lightning_invoices SET status = 'paid', paid_at = $1 WHERE id = $2",
                    result.paid_at.replace(tzinfo=None) if result.paid_at else None,
                    invoice_id,
                )
                await db.execute(
                    "INSERT INTO transactions (user_id, amount, created_at) VALUES ($1, $2, NOW())",
                    user_id,
                    amount_shares,
                )
            logger.info(
                f"Invoice {invoice_id} paid — {amount_shares} shares added for user {user_id}"
            )
            await sse_mgr.notify(InvoiceNotification(invoice_id=invoice_id, status="paid"))
        else:
            async with DatabaseManager(db_url) as db:
                await db.execute(
                    "UPDATE lightning_invoices SET status = 'expired' WHERE id = $1",
                    invoice_id,
                )
            logger.info(f"Invoice {invoice_id} expired")
            await sse_mgr.notify(InvoiceNotification(invoice_id=invoice_id, status="expired"))

    except Exception as e:
        logger.error(f"Error waiting for invoice {invoice_id}: {e}")
        # Mark expired so the user can retry
        try:
            async with DatabaseManager(db_url) as db:
                await db.execute(
                    "UPDATE lightning_invoices SET status = 'expired' WHERE id = $1 AND status = 'pending'",
                    invoice_id,
                )
            await sse_mgr.notify(InvoiceNotification(invoice_id=invoice_id, status="expired"))
        except Exception:
            pass


async def _recover_pending_invoices(
    config: Config, client: CLNClient, sse_mgr: SSEManager
) -> None:
    """On startup, resolve any invoices that were pending when the app last shut down.

    For each pending invoice:
    - If already paid on the node: create the transaction and mark paid.
    - If already expired on the node: mark expired.
    - If still pending and not yet expired: restart the wait task.
    - If expired by timestamp but unknown to node: mark expired.
    """
    try:
        async with DatabaseManager(config.database_url) as db:
            rows = await db.fetch(
                """
                SELECT id, user_id, amount_shares, label, payment_hash, expires_at
                FROM lightning_invoices
                WHERE status = 'pending'
                """
            )

        if not rows:
            return

        logger.info(f"Recovering {len(rows)} pending invoices")

        for row in rows:
            invoice_id = row["id"]
            try:
                status = await client.get_invoice_status(row["payment_hash"])
                now = datetime.now(tz=timezone.utc)
                expires_at = row["expires_at"].replace(tzinfo=timezone.utc)

                if status and status.status == "paid":
                    async with DatabaseManager(config.database_url) as db:
                        await db.execute(
                            "UPDATE lightning_invoices SET status='paid', paid_at=$1 WHERE id=$2",
                            status.paid_at.replace(tzinfo=None) if status.paid_at else None,
                            invoice_id,
                        )
                        await db.execute(
                            "INSERT INTO transactions (user_id, amount, created_at) VALUES ($1, $2, NOW())",
                            row["user_id"],
                            row["amount_shares"],
                        )
                    logger.info(f"Recovery: invoice {invoice_id} was already paid")
                elif status is None or status.status == "expired" or now >= expires_at:
                    async with DatabaseManager(config.database_url) as db:
                        await db.execute(
                            "UPDATE lightning_invoices SET status='expired' WHERE id=$1",
                            invoice_id,
                        )
                    logger.info(f"Recovery: invoice {invoice_id} marked expired")
                else:
                    # Still pending — restart the wait task
                    asyncio.create_task(
                        _await_payment_task(
                            invoice_id=invoice_id,
                            user_id=row["user_id"],
                            amount_shares=row["amount_shares"],
                            label=row["label"],
                            expires_at=expires_at,
                            client=client,
                            db_url=config.database_url,
                            sse_mgr=sse_mgr,
                        )
                    )
                    logger.info(f"Recovery: restarted wait task for invoice {invoice_id}")
            except Exception as e:
                logger.error(f"Recovery failed for invoice {invoice_id}: {e}")
    except Exception as e:
        logger.error(f"Invoice recovery failed: {e}")


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
    global \
        share_queue, \
        share_processor, \
        redis_consumer, \
        difficulty_poller, \
        sse_manager, \
        highscores_cache, \
        cln_client
    share_queue = asyncio.Queue()

    # Initialize SSE manager
    sse_manager = SSEManager()

    # Initialize highscores cache
    highscores_cache = HighscoresCache()

    # Initialize share processor (will start background task)
    share_processor = ShareProcessor(config, share_queue, sse_manager, highscores_cache)

    # Initialize Redis stream consumer
    redis_consumer = RedisStreamConsumer(config, share_queue)

    # Initialize difficulty poller (will start background task)
    difficulty_poller = DifficultyPoller(config, share_processor)

    # Initialize CLN client if configured
    if config.lightning_node_url and config.lightning_rune:
        cln_client = CLNClient(
            base_url=config.lightning_node_url,
            rune=config.lightning_rune,
            ca_cert=config.lightning_ca_cert,
        )
        logger.info(f"CLN client initialized: {config.lightning_node_url}")
    else:
        cln_client = None
        logger.info("CLN not configured — Lightning payments disabled")

    @app.before_serving
    async def startup():
        """Start background share processor and Redis consumer."""
        # Ensure schema exists (init_database uses CREATE TABLE/INDEX IF NOT EXISTS)
        await init_database(config.database_url)

        # Start background services (share processor loads block target on startup)
        await share_processor.start()
        await redis_consumer.start()
        await difficulty_poller.start()

        # Recover any pending Lightning invoices from before last shutdown
        if cln_client:
            await _recover_pending_invoices(config, cln_client, sse_manager)

        logger.info("SliceHash application started")

    @app.after_serving
    async def shutdown():
        """Stop background services."""
        await difficulty_poller.stop()
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

            # Validate k1 challenge
            async with DatabaseManager(config_obj.database_url) as db:
                row = await db.fetchrow(
                    "SELECT expires_at FROM auth_challenges WHERE k1 = $1", k1
                )

                if not row or int(time.time()) > row["expires_at"]:
                    return jsonify({"error": "Invalid or expired challenge"}), 404

            # Generate LNURL for callback
            callback_url = (
                f"{config_obj.lnurl_callback_url}?tag=login&k1={k1}&action=login"
            )
            lnurl_string = lnurl_encode(callback_url)

            # Generate and serve QR code (no logo - keeps QR version lower for better scannability)
            return await serve_qr_image(lnurl_string, logo_filename=None)

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

                # Send connected event
                yield format_sse_event("connected", {"k1": k1})

                # Wait for auth success notification (no timeout, browser will handle)
                notification = await queue.get()  # Receives AuthNotification object
                yield format_sse_event("authenticated", asdict(notification))

            except Exception as e:
                logger.error(f"Auth SSE error: {e}")
                yield format_sse_event("error", {"error": "Internal error"})
            finally:
                if queue:
                    await sse_manager.unsubscribe(f"auth:{k1}", queue)

        return await create_sse_endpoint(event_stream())

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
                    "SELECT id as user_id, address, tag, priority_multiplier FROM users WHERE id = $1",
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
                    f"UPDATE users SET {', '.join(updates)} WHERE id = ${param_num}",
                    *params,
                )

                # Return updated user data (reuse GET logic)
                row = await db.fetchrow(
                    "SELECT id as user_id, address, tag, priority_multiplier FROM users WHERE id = $1",
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
                    SELECT id as share_id, ntime, level, is_block, share_hash, billable, shares_consumed, miner_tag
                    FROM share_events
                    WHERE user_id = $1
                    ORDER BY ntime DESC
                    LIMIT $2 OFFSET $3
                    """,
                    user_id,
                    limit,
                    offset,
                )

                shares = [
                    {
                        "share_id": row["share_id"],
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["miner_tag"],
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
            connection_start = time.time()
            try:
                queue = await sse_manager.subscribe(f"user:{user_id}")
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
                            "shares_consumed": notification.shares_consumed,
                            "block_target_level": notification.block_target_level,
                            "tag": notification.tag,
                        }
                        yield f"id: {notification.share_id}\nevent: share\ndata: {json.dumps(event_data)}\n\n"
                    except asyncio.TimeoutError:
                        # Heartbeat every 30s with padding to defeat TCP/proxy buffering
                        yield f"event: heartbeat\ndata: {json.dumps({'timestamp': datetime.now().isoformat()})}\n\n"
                        yield ": ping\n\n"  # SSE comment for keepalive
                    except Exception as e:
                        logger.error(
                            f"Error in SSE event loop for user {user_id}: {e}",
                            exc_info=True,
                        )
                        raise
            except asyncio.CancelledError:
                connection_duration = time.time() - connection_start
                logger.warning(
                    f"SSE connection cancelled for user {user_id} after {connection_duration:.2f}s"
                )
                raise
            except Exception as e:
                connection_duration = time.time() - connection_start
                logger.error(
                    f"SSE connection error for user {user_id} after {connection_duration:.2f}s: {e}",
                    exc_info=True,
                )
                raise
            finally:
                connection_duration = time.time() - connection_start
                logger.info(
                    f"SSE connection closed for user {user_id} after {connection_duration:.2f}s"
                )
                if queue:
                    await sse_manager.unsubscribe(f"user:{user_id}", queue)

        response = await make_response(
            event_stream(),
            {
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
        response.timeout = None  # Disable timeout for SSE
        return response

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
                        SELECT id as share_id, ntime, level, is_block, share_hash, billable, shares_consumed, miner_tag
                        FROM share_events
                        WHERE user_id = $1 AND id > $2
                        ORDER BY id ASC
                        LIMIT $3
                    """
                    rows = await db.fetch(query, user_id, since_id, limit)
                else:
                    query = """
                        SELECT id as share_id, ntime, level, is_block, share_hash, billable, shares_consumed, miner_tag
                        FROM share_events
                        WHERE user_id = $1 AND ntime > $2
                        ORDER BY id ASC
                        LIMIT $3
                    """
                    rows = await db.fetch(query, user_id, int(since_time), limit)

                shares = [
                    {
                        "share_id": row["share_id"],
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["miner_tag"],
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

    @app.get("/api/users/me/shares/load")
    @require_auth
    async def load_shares():
        """Load shares page with mode support (initial load and pagination).

        Query parameters:
            mode: 'recent', 'best-24h', 'best-all-time' (default: 'recent')
            offset: Number of results to skip (default: 0)
            limit: Results per page (default: 20, max: 100)

        Returns:
            {"shares": [...], "has_more": bool}
        """
        user_id = request.user_id
        mode = request.args.get("mode", "recent")
        offset = max(int(request.args.get("offset", 0)), 0)
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)

        logger.info(
            f"Load shares request: user_id={user_id}, mode={mode}, offset={offset}, limit={limit}"
        )

        # Configure query based on mode
        if mode == "recent":
            where_clause = "WHERE user_id = $1"
            order_by = "ORDER BY ntime DESC"
        elif mode == "best-24h":
            where_clause = "WHERE user_id = $1 AND ntime >= EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::INTEGER"
            order_by = "ORDER BY level DESC, ntime DESC"
        elif mode == "best-all-time":
            where_clause = "WHERE user_id = $1"
            order_by = "ORDER BY level DESC, ntime DESC"
        else:
            return jsonify({"error": "Invalid mode"}), 400

        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            # Get total count for has_more
            count_query = f"SELECT COUNT(*) FROM share_events {where_clause}"
            total = await db.fetchval(count_query, user_id)

            # Get paginated results
            query = f"""
                SELECT id as share_id, ntime, level, is_block, share_hash,
                       billable, shares_consumed, miner_tag
                FROM share_events
                {where_clause}
                {order_by}
                LIMIT $2 OFFSET $3
            """
            rows = await db.fetch(query, user_id, limit, offset)

            shares = [
                {
                    "share_id": row["share_id"],
                    "submitted_at": row["ntime"],
                    "level": row["level"],
                    "is_block": bool(row["is_block"]),
                    "share_hash": row["share_hash"],
                    "billable": bool(row["billable"]),
                    "shares_consumed": row["shares_consumed"],
                    "tag": row["miner_tag"],
                }
                for row in rows
            ]

            logger.info(
                f"Load shares response: returned {len(shares)} shares, has_more={offset + len(rows) < total}, total={total}"
            )

            return jsonify(
                {"shares": shares, "has_more": offset + len(rows) < total}
            ), 200

    @app.get("/api/users/me/shares/refresh")
    @require_auth
    async def refresh_shares():
        """Refocus catch-up: incremental or full refresh based on staleness.

        Query parameters:
            since_id: Last share ID received (REQUIRED)
            mode: View mode (default: 'recent')
            limit: Check window size (default: 20, max: 100)

        Returns:
            Incremental: {"type": "incremental", "shares": [...]}
            Full refresh: {"type": "full_refresh", "shares": [...], "has_more": bool}
        """
        user_id = request.user_id
        since_id = request.args.get("since_id")
        mode = request.args.get("mode", "recent")
        limit = min(max(int(request.args.get("limit", 20)), 1), 100)

        logger.info(
            f"Refresh shares request: user_id={user_id}, since_id={since_id}, mode={mode}, limit={limit}"
        )

        if not since_id:
            logger.warning(f"Refresh shares: missing since_id")
            return jsonify({"error": "since_id is required"}), 400

        try:
            since_id = int(since_id)
        except ValueError:
            logger.warning(f"Refresh shares: invalid since_id={since_id}")
            return jsonify({"error": "Invalid since_id"}), 400

        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            # Single query: fetch latest N by time
            check_query = """
                SELECT id as share_id, ntime, level, is_block, share_hash,
                       billable, shares_consumed, miner_tag
                FROM share_events
                WHERE user_id = $1
                ORDER BY ntime DESC
                LIMIT $2
            """
            rows = await db.fetch(check_query, user_id, limit)

            if not rows:
                logger.info(
                    f"Refresh shares: no shares found, returning empty full_refresh"
                )
                return jsonify(
                    {"type": "full_refresh", "shares": [], "has_more": False}
                ), 200

            share_ids = [row["share_id"] for row in rows]
            logger.info(
                f"Refresh shares: fetched {len(rows)} recent shares, checking if since_id={since_id} is in list"
            )

            if since_id in share_ids:
                # INCREMENTAL: Trim to shares before since_id
                since_index = share_ids.index(since_id)
                new_rows = rows[:since_index]

                logger.info(
                    f"Refresh shares: INCREMENTAL - found since_id at index {since_index}, returning {len(new_rows)} new shares"
                )

                shares = [
                    {
                        "share_id": row["share_id"],
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["miner_tag"],
                    }
                    for row in new_rows
                ]

                return jsonify({"type": "incremental", "shares": shares}), 200

            else:
                # FULL REFRESH: User is >limit shares stale
                logger.info(
                    f"Refresh shares: FULL REFRESH - since_id not in recent {limit} shares, user is stale"
                )
                if mode == "recent":
                    # Reuse rows (already DESC by time) - 1 query total
                    logger.info(
                        f"Refresh shares: FULL REFRESH (recent mode) - reusing fetched rows"
                    )
                    shares = [
                        {
                            "share_id": row["share_id"],
                            "submitted_at": row["ntime"],
                            "level": row["level"],
                            "is_block": bool(row["is_block"]),
                            "share_hash": row["share_hash"],
                            "billable": bool(row["billable"]),
                            "shares_consumed": row["shares_consumed"],
                            "tag": row["miner_tag"],
                        }
                        for row in rows
                    ]

                    # Check if more exists
                    count_query = "SELECT COUNT(*) FROM share_events WHERE user_id = $1"
                    total = await db.fetchval(count_query, user_id)

                    logger.info(
                        f"Refresh shares: FULL REFRESH response - {len(shares)} shares, has_more={len(rows) < total}, total={total}"
                    )

                    return jsonify(
                        {
                            "type": "full_refresh",
                            "shares": shares,
                            "has_more": len(rows) < total,
                        }
                    ), 200

                else:
                    # Best modes: fetch by level - 2 queries total
                    logger.info(
                        f"Refresh shares: FULL REFRESH (best mode={mode}) - fetching by level"
                    )
                    if mode == "best-24h":
                        where_clause = "WHERE user_id = $1 AND ntime >= EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::INTEGER"
                    else:  # best-all-time
                        where_clause = "WHERE user_id = $1"

                    # Get total count
                    count_query = f"SELECT COUNT(*) FROM share_events {where_clause}"
                    total = await db.fetchval(count_query, user_id)

                    # Get by level
                    best_query = f"""
                        SELECT id as share_id, ntime, level, is_block, share_hash,
                               billable, shares_consumed, miner_tag
                        FROM share_events
                        {where_clause}
                        ORDER BY level DESC, ntime DESC
                        LIMIT $2
                    """
                    rows = await db.fetch(best_query, user_id, limit)

                    shares = [
                        {
                            "share_id": row["share_id"],
                            "submitted_at": row["ntime"],
                            "level": row["level"],
                            "is_block": bool(row["is_block"]),
                            "share_hash": row["share_hash"],
                            "billable": bool(row["billable"]),
                            "shares_consumed": row["shares_consumed"],
                            "tag": row["miner_tag"],
                        }
                        for row in rows
                    ]

                    logger.info(
                        f"Refresh shares: FULL REFRESH response - {len(shares)} shares, has_more={len(rows) < total}, total={total}"
                    )

                    return jsonify(
                        {
                            "type": "full_refresh",
                            "shares": shares,
                            "has_more": len(rows) < total,
                        }
                    ), 200

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
                    SELECT id as transaction_id, amount, created_at
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
                        "created_at": int(
                            row["created_at"].replace(tzinfo=timezone.utc).timestamp()
                        )
                        if row["created_at"]
                        else None,
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
                    "SELECT address FROM users WHERE id = $1", user_id
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
                    RETURNING id as transaction_id, amount, created_at
                    """,
                    user_id,
                    amount,
                )

                return jsonify(
                    {
                        "transaction_id": row["transaction_id"],
                        "amount": row["amount"],
                        "created_at": int(
                            row["created_at"].replace(tzinfo=timezone.utc).timestamp()
                        )
                        if row["created_at"]
                        else None,
                    }
                ), 201

        except Exception as e:
            logger.error(f"Failed to create purchase: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.post("/api/users/me/purchases/invoice")
    @require_auth
    async def create_invoice():
        """Create a Lightning invoice for a share purchase.

        Request body:
            {
                "amount": int  # Number of shares to purchase (must be positive)
            }

        Returns:
            201: Invoice created — {invoice_id, bolt11, amount_sats, expires_at}
            400: Invalid request or BTC address not set
            503: Lightning payments not configured
            500: Internal error
        """
        if not cln_client:
            return jsonify({"error": "Lightning payments are not configured"}), 503

        try:
            user_id = request.user_id
            data = await request.get_json()

            if not data or "amount" not in data:
                return jsonify({"error": "Missing 'amount' field"}), 400

            amount = data["amount"]
            if not isinstance(amount, int) or amount <= 0:
                return jsonify({"error": "Amount must be a positive integer"}), 400

            cfg = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(cfg.database_url) as db:
                user = await db.fetchrow(
                    "SELECT address FROM users WHERE id = $1", user_id
                )

                if not user:
                    return jsonify({"error": "User not found"}), 404

                if user["address"].startswith("bc1_update_in_settings_"):
                    return jsonify(
                        {
                            "error": "Please set your Bitcoin address in Settings before purchasing shares"
                        }
                    ), 400

            amount_sats = amount * cfg.sats_per_share
            amount_msat = amount_sats * 1000
            label = f"slicehash_{user_id}_{uuid.uuid4().hex}"
            description = f"SliceHash: {amount} share{'s' if amount != 1 else ''}"

            invoice = await cln_client.create_invoice(
                amount_msat=amount_msat,
                label=label,
                description=description,
                expiry=cfg.invoice_expiry_seconds,
            )

            async with DatabaseManager(cfg.database_url) as db:
                row = await db.fetchrow(
                    """
                    INSERT INTO lightning_invoices
                        (user_id, payment_hash, label, payment_request, amount_shares, amount_sats, expires_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id
                    """,
                    user_id,
                    invoice.payment_hash,
                    label,
                    invoice.bolt11,
                    amount,
                    amount_sats,
                    invoice.expires_at.replace(tzinfo=None),  # store as naive UTC (matches existing TIMESTAMP columns)
                )

            invoice_id = row["id"]

            asyncio.create_task(
                _await_payment_task(
                    invoice_id=invoice_id,
                    user_id=user_id,
                    amount_shares=amount,
                    label=label,
                    expires_at=invoice.expires_at,
                    client=cln_client,
                    db_url=cfg.database_url,
                    sse_mgr=sse_manager,
                )
            )

            return jsonify(
                {
                    "invoice_id": invoice_id,
                    "bolt11": invoice.bolt11,
                    "amount_sats": amount_sats,
                    "expires_at": int(invoice.expires_at.timestamp()),
                }
            ), 201

        except Exception as e:
            logger.error(f"Failed to create invoice: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/users/me/purchases/invoice/<int:invoice_id>/qr")
    @require_auth
    async def get_invoice_qr(invoice_id: int):
        """Generate QR code image for a Lightning invoice.

        Returns:
            200: PNG QR code image
            404: Invoice not found or doesn't belong to current user
            500: Internal error
        """
        try:
            user_id = request.user_id
            cfg = app.config["SLICEHASH_CONFIG"]

            async with DatabaseManager(cfg.database_url) as db:
                row = await db.fetchrow(
                    "SELECT payment_request FROM lightning_invoices WHERE id = $1 AND user_id = $2",
                    invoice_id,
                    user_id,
                )

            if not row:
                return jsonify({"error": "Invoice not found"}), 404

            # Uppercase BOLT11 for alphanumeric QR encoding (smaller, faster to scan)
            bolt11_upper = row["payment_request"].upper()
            return await serve_qr_image(bolt11_upper, logo_filename=None)

        except Exception as e:
            logger.error(f"Failed to generate invoice QR: {e}")
            return jsonify({"error": "Internal error"}), 500

    @app.get("/api/users/me/purchases/invoice/<int:invoice_id>/stream")
    @require_auth
    async def invoice_payment_stream(invoice_id: int):
        """SSE stream for Lightning invoice payment status.

        Emits:
            connected: Initial connection event
            paid:      Invoice was paid, shares have been added
            expired:   Invoice expired without payment
        """
        try:
            user_id = request.user_id
            cfg = app.config["SLICEHASH_CONFIG"]

            # Verify invoice belongs to current user
            async with DatabaseManager(cfg.database_url) as db:
                row = await db.fetchrow(
                    "SELECT status FROM lightning_invoices WHERE id = $1 AND user_id = $2",
                    invoice_id,
                    user_id,
                )

            if not row:
                return jsonify({"error": "Invoice not found"}), 404

            # If already resolved, respond immediately without subscribing
            if row["status"] == "paid":
                async def immediate_paid():
                    yield format_sse_event("connected", {"invoice_id": invoice_id})
                    yield format_sse_event("paid", {"invoice_id": invoice_id})
                return await create_sse_endpoint(immediate_paid())

            if row["status"] == "expired":
                async def immediate_expired():
                    yield format_sse_event("connected", {"invoice_id": invoice_id})
                    yield format_sse_event("expired", {"invoice_id": invoice_id})
                return await create_sse_endpoint(immediate_expired())

        except Exception as e:
            logger.error(f"Invoice stream setup failed: {e}")
            return jsonify({"error": "Internal error"}), 500

        channel = f"invoice:{invoice_id}"

        async def event_stream():
            queue = None
            try:
                queue = await sse_manager.subscribe(channel)
                yield format_sse_event("connected", {"invoice_id": invoice_id})

                notification = await queue.get()  # Receives InvoiceNotification
                yield format_sse_event(notification.status, {"invoice_id": invoice_id})

            except Exception as e:
                logger.error(f"Invoice SSE stream error: {e}")
                yield format_sse_event("error", {"error": "Internal error"})
            finally:
                if queue:
                    await sse_manager.unsubscribe(channel, queue)

        return await create_sse_endpoint(event_stream())

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
                        se.ntime, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        se.miner_tag,
                        u.address as coinbase_address,
                        COALESCE(se.miner_tag, u.address) as username
                    FROM share_events se
                    LEFT JOIN users u ON se.user_id = u.id
                    WHERE se.ntime >= EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::INTEGER
                    ORDER BY se.level DESC, se.ntime DESC
                    LIMIT 5
                    """
                )

                shares = [
                    {
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "user_id": row["user_id"],
                        "tag": row["miner_tag"],
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
                        se.ntime, se.level, se.is_block, se.share_hash,
                        se.billable, se.shares_consumed, se.user_id,
                        se.miner_tag,
                        u.address as coinbase_address,
                        COALESCE(se.miner_tag, u.address) as username
                    FROM share_events se
                    LEFT JOIN users u ON se.user_id = u.id
                    ORDER BY se.level DESC, se.ntime DESC
                    LIMIT 5
                    """
                )

                shares = [
                    {
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "user_id": row["user_id"],
                        "tag": row["miner_tag"],
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
                order_by = "ORDER BY ntime DESC"
            elif mode == "best-24h":
                where_clause = "WHERE user_id = $1 AND ntime >= EXTRACT(EPOCH FROM NOW() - INTERVAL '24 hours')::INTEGER"
                order_by = "ORDER BY level DESC, ntime DESC"
            elif mode == "best-all-time":
                where_clause = "WHERE user_id = $1"
                order_by = "ORDER BY level DESC, ntime DESC"
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
                        share_id, ntime, level, is_block, share_hash,
                        billable, shares_consumed, miner_tag
                    FROM share_events
                    {where_clause}
                    {order_by}
                    LIMIT $2 OFFSET $3
                """
                rows = await db.fetch(query, user_id, limit, offset)

                shares = [
                    {
                        "share_id": row["share_id"],
                        "submitted_at": row["ntime"],
                        "level": row["level"],
                        "is_block": bool(row["is_block"]),
                        "share_hash": row["share_hash"],
                        "billable": bool(row["billable"]),
                        "shares_consumed": row["shares_consumed"],
                        "tag": row["miner_tag"],
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

    @app.get("/hash-validator/<int:share_id>")
    @require_auth
    async def hash_validator_page(share_id: int):
        """Render hash validator page for a specific share.

        Args:
            share_id: ID of the share to validate

        Returns:
            HTML template for hash validator page
        """
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_url) as db:
            shares_remaining = await calculate_shares_remaining(db, request.user_id)

        # Get current block target level from cached value (updated by share processor)
        block_target_level = 0
        if share_processor and share_processor.current_block_target:
            block_target_level = calculate_level(share_processor.current_block_target)

        return await render_template(
            "hash-validator.html",
            shares_remaining=shares_remaining,
            block_target_level=int(block_target_level),
            share_id=share_id,
        )

    @app.get("/api/shares/<int:share_id>/validator-data")
    @require_auth
    async def get_validator_data(share_id: int):
        """Get all data needed for hash validation.

        Args:
            share_id: ID of the share

        Returns:
            JSON with all hash validation fields
        """
        try:
            async with DatabaseManager(
                app.config["SLICEHASH_CONFIG"].database_url
            ) as db:
                # Fetch share data from both tables with a JOIN
                query = """
                    SELECT
                        se.id as share_id, se.user_id, se.share_hash, se.ntime,
                        se.level, se.is_block, se.miner_tag, se.block_height,
                        sv.coinbase_tx, sv.prev_block_hash, sv.bits, sv.nonce,
                        sv.version, sv.merkle_path
                    FROM share_events se
                    JOIN share_verification sv ON se.id = sv.share_id
                    WHERE se.id = $1 AND se.user_id = $2
                """
                row = await db.fetchrow(query, share_id, request.user_id)

                if not row:
                    return jsonify({"error": "Share not found"}), 404

                # Parse coinbase transaction to extract all fields
                coinbase_data = parse_coinbase_transaction(row["coinbase_tx"])

                # Parse merkle_path from JSONB
                merkle_path = []
                if row["merkle_path"]:
                    import json

                    merkle_path = json.loads(row["merkle_path"])

                # Prepare response data
                data = {
                    # Share metadata
                    "share_id": row["share_id"],
                    "share_hash": row["share_hash"],
                    "level": row["level"],
                    "is_block": bool(row["is_block"]),
                    # Block header fields
                    "version": hex(row["version"]),
                    "timestamp": row["ntime"],
                    "bits": row["bits"],
                    "nonce": row["nonce"],
                    "prev_block_hash": row["prev_block_hash"],
                    # Coinbase transaction fields (parsed)
                    "coinbase_address": coinbase_data.get("coinbase_address", ""),
                    "pool_tag": coinbase_data.get("pool_tag", "SliceHash"),
                    "miner_tag": coinbase_data.get("miner_tag", row["miner_tag"] or ""),
                    "extranonce": coinbase_data.get("extranonce", ""),
                    "coinbase_value": coinbase_data.get("coinbase_value", 0),
                    "witness_commitment": coinbase_data.get("witness_commitment", ""),
                    "sequence": coinbase_data.get("sequence", 0xffffffff),
                    "locktime": coinbase_data.get("locktime", 0),
                    # Other fields
                    "block_height": row["block_height"],
                    "merkle_path": merkle_path,
                }

                return jsonify(data), 200

        except Exception as e:
            logger.error(f"Failed to fetch validator data: {e}", exc_info=True)
            return jsonify({"error": "Internal error"}), 500

    return app


# For running with hypercorn/uvicorn
app = create_app(config_path=os.environ.get("CONFIG_PATH", "config.yaml"))
