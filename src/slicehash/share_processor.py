"""Background share processing with rotation logic integration.

This module provides the ShareProcessor class which:
- Consumes share events from webhook queue
- Classifies shares as billable based on difficulty threshold
- Calculates shares consumed using priority and traffic level
- Stores share events in database
- Manages rotation state in memory
- Triggers rotation when conditions met
- Updates pool coinbase address on rotation
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from .config import Config
from .db.manager import DatabaseManager
from .quota import classify_share_billable, calculate_shares_remaining, get_active_users
from .priority import calculate_traffic_level, calculate_shares_consumed
from .pool_client import PoolClient
from .rotation import RotationState, select_next_user, should_rotate, calculate_rotation_interval

logger = logging.getLogger(__name__)


class ShareProcessor:
    """Background worker processing share events and managing rotation.

    Integrates quota calculation, priority system, and rotation logic.
    """

    def __init__(self, config: Config, share_queue: asyncio.Queue):
        """Initialize share processor.

        Args:
            config: Application configuration
            share_queue: Queue of incoming share events from webhook
        """
        self.config = config
        self.share_queue = share_queue
        self.rotation_state = RotationState()
        self._task: Optional[asyncio.Task] = None
        self._running = False

    async def start(self):
        """Start background processing task."""
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
        logger.info("Share processor stopped")

    async def _process_loop(self):
        """Main processing loop - runs continuously."""
        while self._running:
            try:
                # Get next share from queue (with timeout for responsiveness)
                share_data = await asyncio.wait_for(
                    self.share_queue.get(),
                    timeout=1.0
                )

                # Process share with all business logic
                await self._process_share(share_data)

            except asyncio.TimeoutError:
                # No shares in queue, continue loop
                continue
            except Exception as e:
                logger.error(f"Error processing share: {e}", exc_info=True)
                # Continue processing despite errors

    async def _process_share(self, share_data: dict):
        """Process single share event.

        Steps:
        1. Classify billable based on difficulty threshold
        2. Calculate traffic level and shares consumed
        3. Store share event in database
        4. Update rotation state
        5. Check if rotation needed
        6. If yes: select next user and update pool

        Args:
            share_data: Share event from webhook
        """
        user_id = share_data["user_id"]
        share_difficulty = share_data["share_difficulty"]

        async with DatabaseManager(self.config.database_path) as db:
            # Step 1: Classify billable
            billable = classify_share_billable(
                share_difficulty,
                self.config.billable_difficulty_threshold
            )

            # Step 2: Calculate shares consumed (if billable)
            # Note: shares_consumed is always >= 1 due to schema constraint
            # For non-billable shares, we set it to 1 but it doesn't affect quota
            # (only billable=1 shares count toward consumption)
            shares_consumed = 1  # Default for non-billable
            if billable:
                # Get traffic level
                active_users = await get_active_users(db)
                traffic_level = calculate_traffic_level(len(active_users))

                # Get user's priority multiplier
                cursor = await db.execute(
                    "SELECT priority_multiplier FROM users WHERE user_id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
                priority = row[0] if row else 1

                shares_consumed = calculate_shares_consumed(priority, traffic_level)

            # Step 3: Store share event
            await db.execute(
                """
                INSERT INTO share_events
                (user_id, share_difficulty, billable, shares_consumed,
                 channel_id, sequence_number, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    share_difficulty,
                    1 if billable else 0,
                    shares_consumed,
                    share_data.get("channel_id"),
                    share_data.get("sequence_number"),
                    share_data.get("submitted_at", datetime.now().isoformat())
                )
            )
            await db.commit()

            logger.info(
                f"Stored share: user={user_id}, difficulty={share_difficulty}, "
                f"billable={billable}, consumed={shares_consumed}"
            )

            # Step 4: Update rotation state
            if self.rotation_state.current_user_id == user_id:
                self.rotation_state.shares_this_turn += 1
            elif self.rotation_state.current_user_id is None:
                # First user to mine
                self.rotation_state.current_user_id = user_id
                self.rotation_state.shares_this_turn = 1
                self.rotation_state.rotation_started_at = datetime.now()

            # Step 5: Check rotation
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
        next_user_id = await select_next_user(db, exclude_user_id=self.rotation_state.current_user_id)

        if next_user_id is None:
            logger.warning("No active users available for rotation")
            return

        # Get user details
        cursor = await db.execute(
            "SELECT address, tag FROM users WHERE user_id = ?",
            (next_user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            logger.error(f"User {next_user_id} not found")
            return

        address, tag = row

        # Update pool's coinbase address
        async with PoolClient(str(self.config.pool_url)) as pool:
            success = await pool.update_coinbase(address, next_user_id, tag)

        if success:
            # Update user's last_served_at
            await db.execute(
                "UPDATE users SET last_served_at = ? WHERE user_id = ?",
                (datetime.now().isoformat(), next_user_id)
            )
            await db.commit()

            # Update rotation state
            old_user = self.rotation_state.current_user_id
            self.rotation_state.current_user_id = next_user_id
            self.rotation_state.shares_this_turn = 0
            self.rotation_state.rotation_started_at = datetime.now()
            self.rotation_state.last_rotation_at = datetime.now()

            logger.info(f"Rotated from user {old_user} to user {next_user_id}")
        else:
            logger.error("Failed to update pool coinbase address")
