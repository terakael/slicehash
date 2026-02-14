"""Background share processing with rotation logic integration.

This module provides the ShareProcessor class which:
- Consumes share events from webhook queue
- Classifies shares as billable based on difficulty threshold
- Calculates shares consumed using priority and traffic level
- Stores share events in database
- Manages rotation state in memory
- Triggers rotation when conditions met
- Updates pool coinbase address on rotation
- Tracks and updates block target changes
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .config import Config
from .db.manager import DatabaseManager
from .hash_utils import calculate_level
from .pool_client import PoolClient
from .priority import calculate_shares_consumed, calculate_traffic_level
from .quota import calculate_shares_remaining, classify_share_billable, get_active_users
from .rotation import (
    RotationState,
    calculate_rotation_interval,
    select_next_user,
    should_rotate,
)
from .sse_manager import ShareNotification, SSEManager

logger = logging.getLogger(__name__)


class ShareProcessor:
    """Background worker processing share events and managing rotation.

    Integrates quota calculation, priority system, and rotation logic.
    """

    def __init__(
        self,
        config: Config,
        share_queue: asyncio.Queue,
        sse_manager: SSEManager,
        highscores_cache=None,
    ):
        """Initialize share processor.

        Args:
            config: Application configuration
            share_queue: Queue of incoming share events from webhook
            sse_manager: SSE manager for real-time notifications
            highscores_cache: Optional highscores cache to invalidate on new shares
        """
        self.config = config
        self.share_queue = share_queue
        self.sse_manager = sse_manager
        self.highscores_cache = highscores_cache
        self.rotation_state = RotationState()
        self.current_block_target: Optional[str] = None
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._db_conn = None
        self._db_manager = DatabaseManager(self.config.database_url)

    async def start(self):
        """Start background processing task and load block target."""
        try:
            # Establish persistent database connection
            self._db_conn = await self._db_manager.get_persistent_connection()
            logger.info("Established persistent database connection")

            # Load current block target from database
            row = await self._db_conn.fetchrow(
                "SELECT value FROM global_state WHERE key = $1", "current_block_target"
            )
            if row:
                self.current_block_target = row["value"]
                logger.info(f"Loaded block target: {self.current_block_target}")
        except Exception as e:
            # Clean up connection on failure
            if self._db_conn:
                await self._db_manager.close_persistent_connection(self._db_conn)
                self._db_conn = None
            logger.error(f"Failed to start share processor: {e}", exc_info=True)
            raise

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Share processor started")

    async def stop(self):
        """Stop background processing task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        # Close persistent database connection
        if self._db_conn:
            await self._db_manager.close_persistent_connection(self._db_conn)
            self._db_conn = None
            logger.info("Closed persistent database connection")

        logger.info("Share processor stopped")

    async def _process_loop(self):
        """Main processing loop - runs continuously."""
        while self._running:
            try:
                # Get next share from queue (with timeout for responsiveness)
                share_data = await asyncio.wait_for(self.share_queue.get(), timeout=1.0)

                # Process share with all business logic
                await self._process_share(share_data)

            except asyncio.TimeoutError:
                # No shares in queue, continue loop
                continue
            except (asyncpg.PostgresError, ConnectionError) as e:
                # Database or connection errors - attempt reconnection
                logger.error(f"Database error processing share: {e}", exc_info=True)
                logger.warning("Attempting to reconnect to database")
                try:
                    if self._db_conn:
                        await self._db_manager.close_persistent_connection(
                            self._db_conn
                        )
                    self._db_conn = await self._db_manager.get_persistent_connection()
                    logger.info("Successfully reconnected to database")
                except Exception as reconnect_error:
                    logger.error(
                        f"Failed to reconnect to database: {reconnect_error}",
                        exc_info=True,
                    )
            except Exception as e:
                # Other errors - log but continue processing
                logger.error(f"Unexpected error processing share: {e}", exc_info=True)

    async def _process_share(self, share_data: dict):
        """Process single share event.

        Steps:
        1. Check and update block target if changed
        2. Calculate level from share hash
        3. Classify billable based on level or other criteria
        4. Calculate traffic level and shares consumed
        5. Store share event in database (share_events, share_validation, share_merkle_path)
        6. Update rotation state
        7. Check if rotation needed
        8. If yes: select next user and update pool

        Args:
            share_data: Share event from webhook
        """
        # Convert string fields to integers for PostgreSQL strict typing
        user_id = int(share_data["user_id"])
        nonce = int(share_data["nonce"])
        ntime = int(share_data["ntime"])
        version = int(share_data["version"])
        coinbase_address = share_data["coinbase_address"]
        coinbase_prefix_tag = share_data["coinbase_prefix_tag"]
        share_hash = share_data.get("share_hash")
        is_block = share_data["is_block"]
        block_target = share_data.get("block_target")

        # Hash verification fields
        prev_block_hash = share_data.get("prev_block_hash")
        bits = share_data.get("bits")
        merkle_path = share_data.get("merkle_path")  # JSON string or parsed list
        block_height = share_data.get("block_height")
        extranonce = share_data.get("extranonce")
        coinbase_value = share_data.get("coinbase_value")
        witness_commitment = share_data.get("witness_commitment")

        db = self._db_conn

        # Step 1: Check and update block target if changed
        if block_target and block_target != self.current_block_target:
            logger.info(
                f"Block target changed: {self.current_block_target} -> {block_target}"
            )
            self.current_block_target = block_target

            # Update database
            await db.execute(
                """
                INSERT INTO global_state (key, value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                "current_block_target",
                str(block_target),
            )

        # Step 2: Calculate level from share hash
        level = calculate_level(share_hash) if share_hash else 0

        # Step 2b: Apply test network logic
        if self.config.is_test_network:
            is_block = level >= self.config.test_network_block_level

        # Calculate block target level
        block_target_level = (
            calculate_level(self.current_block_target)
            if self.current_block_target
            else 0
        )

        # Step 3: Classify billable (for now, use level >= 10 as billable)
        # TODO: Replace with proper difficulty threshold when available
        billable = level >= 10

        # Step 4: Calculate shares consumed (if billable)
        shares_consumed = 1  # Default for non-billable
        if billable:
            # Get traffic level
            active_users = await get_active_users(db)
            traffic_level = calculate_traffic_level(len(active_users))

            # Get user's priority multiplier
            row = await db.fetchrow(
                "SELECT priority_multiplier FROM users WHERE user_id = $1", user_id
            )
            priority = row["priority_multiplier"] if row else 1

            shares_consumed = calculate_shares_consumed(priority, traffic_level)

        # Step 5: Store share event (normalized across three tables)
        # Convert Unix timestamp to UTC datetime, then make it naive for database storage
        submitted_at_dt = datetime.fromtimestamp(ntime, tz=timezone.utc).replace(
            tzinfo=None
        )

        # Insert into main share_events table (lean, for listing)
        share_id = await db.fetchval(
            """
            INSERT INTO share_events
            (user_id, share_hash, is_block, level, billable, shares_consumed,
             coinbase_prefix_tag, block_height, submitted_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING id
            """,
            user_id,
            share_hash,
            1 if is_block else 0,
            level,
            1 if billable else 0,
            shares_consumed,
            coinbase_prefix_tag,
            block_height,
            submitted_at_dt,
        )

        # Insert into share_validation table (detailed mining parameters)
        await db.execute(
            """
            INSERT INTO share_validation
            (share_id, nonce, ntime, version, coinbase_address,
             prev_block_hash, bits, extranonce, coinbase_value, witness_commitment)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            share_id,
            nonce,
            ntime,
            version,
            coinbase_address,
            prev_block_hash,
            bits,
            extranonce,
            coinbase_value,
            witness_commitment,
        )

        # Insert merkle path hashes if present
        if merkle_path:
            # Parse merkle_path if it's a JSON string
            if isinstance(merkle_path, str):
                try:
                    merkle_hashes = json.loads(merkle_path)
                except json.JSONDecodeError:
                    logger.warning(f"Failed to parse merkle_path JSON: {merkle_path}")
                    merkle_hashes = []
            else:
                merkle_hashes = merkle_path

            # Insert each merkle hash with its position
            if merkle_hashes:
                for position, merkle_hash in enumerate(merkle_hashes):
                    await db.execute(
                        """
                        INSERT INTO share_merkle_path
                        (share_id, position, merkle_hash)
                        VALUES ($1, $2, $3)
                        """,
                        share_id,
                        position,
                        merkle_hash,
                    )

        logger.info(
            f"Stored share: user={user_id}, level={level}, "
            f"is_block={is_block}, billable={billable}, consumed={shares_consumed}"
        )

        # Notify SSE subscribers
        notification = ShareNotification(
            share_id=share_id,
            user_id=user_id,
            submitted_at=int(submitted_at_dt.timestamp()),
            level=level,
            is_block=is_block,
            share_hash=share_hash,
            billable=billable,
            shares_consumed=shares_consumed,
            block_target_level=block_target_level,
            tag=coinbase_prefix_tag,
        )
        await self.sse_manager.notify(notification)

        # Invalidate highscores cache (new share might be a highscore)
        if self.highscores_cache:
            await self.highscores_cache.invalidate()

        # Step 6: Update rotation state
        if self.rotation_state.current_user_id == user_id:
            self.rotation_state.shares_this_turn += 1
        elif self.rotation_state.current_user_id is None:
            # First user to mine
            self.rotation_state.current_user_id = user_id
            self.rotation_state.shares_this_turn = 1
            self.rotation_state.rotation_started_at = datetime.now()

        # Step 7: Check rotation
        active_users = await get_active_users(db)
        rotation_interval = calculate_rotation_interval(len(active_users))

        if should_rotate(self.rotation_state, rotation_interval, datetime.now()):
            await self._rotate_user(db, active_users)

    async def _rotate_user(self, db, active_users: list[int]):
        """Perform user rotation.

        Args:
            db: Active database connection
            active_users: List of active user IDs
        """
        # Select next user
        next_user_id = await select_next_user(db)

        if next_user_id is None:
            logger.warning("No active users available for rotation")
            return

        # Get user details
        row = await db.fetchrow(
            "SELECT address, tag FROM users WHERE user_id = $1", next_user_id
        )
        if not row:
            logger.error(f"User {next_user_id} not found")
            return

        address, tag = row["address"], row["tag"]

        # Update pool's coinbase address
        async with PoolClient(str(self.config.pool_url)) as pool:
            success = await pool.update_coinbase(address, next_user_id, tag)

        if success:
            # Update user's last_served_at (store as naive UTC for consistency)
            await db.execute(
                "UPDATE users SET last_served_at = $1 WHERE user_id = $2",
                datetime.now(timezone.utc).replace(tzinfo=None),
                next_user_id,
            )

            # Update rotation state
            old_user = self.rotation_state.current_user_id
            self.rotation_state.current_user_id = next_user_id
            self.rotation_state.shares_this_turn = 0
            self.rotation_state.rotation_started_at = datetime.now()
            self.rotation_state.last_rotation_at = datetime.now()

            logger.info(f"Rotated from user {old_user} to user {next_user_id}")
        else:
            logger.error("Failed to update pool coinbase address")
