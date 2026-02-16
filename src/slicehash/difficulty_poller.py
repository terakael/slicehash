"""Background poller for Bitcoin network difficulty.

This module provides the DifficultyPoller class which:
- Polls Bitcoin Core RPC getdifficulty every 60 seconds
- Converts difficulty to block target hash
- Updates ShareProcessor with new target
- Persists target to database
"""

import asyncio
import logging
from typing import Optional

import asyncpg

from .btc_rpc_client import BitcoinRPCClient
from .config import Config
from .db.manager import DatabaseManager

logger = logging.getLogger(__name__)

# Bitcoin max target (difficulty 1)
# This is the maximum target value in Bitcoin, representing minimum difficulty
MAX_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def difficulty_to_target(difficulty: float) -> str:
    """Convert difficulty to target hash.

    Uses the standard Bitcoin formula:
        target = max_target / difficulty

    Args:
        difficulty: Network difficulty value from getdifficulty RPC

    Returns:
        64-character hexadecimal target hash string (lowercase, no 0x prefix)

    Example:
        >>> difficulty_to_target(1.0)
        '00000000ffff0000000000000000000000000000000000000000000000000000'
        >>> difficulty_to_target(100.0)
        '00000000028f5c28f5c28f5c28f5c28f5c28f5c28f5c28f5c28f5c28f5c28f5'
    """
    if difficulty <= 0:
        logger.error(f"Invalid difficulty value: {difficulty}. Using difficulty=1.")
        difficulty = 1.0

    # Calculate target
    target_int = int(MAX_TARGET / difficulty)

    # Convert to 64-character hex string (32 bytes = 256 bits)
    target_hex = f"{target_int:064x}"

    return target_hex


class DifficultyPoller:
    """Background worker that polls Bitcoin difficulty and updates block target.

    Polls Bitcoin Core RPC every 60 seconds to fetch current network difficulty,
    converts it to a target hash, and updates the system state.
    """

    def __init__(self, config: Config, share_processor):
        """Initialize difficulty poller.

        Args:
            config: Application configuration
            share_processor: ShareProcessor instance to update with new targets
        """
        self.config = config
        self.share_processor = share_processor
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._db_conn: Optional[asyncpg.Connection] = None
        self._db_manager = DatabaseManager(self.config.database_url)
        self._poll_interval = 60  # seconds

    async def start(self):
        """Start background polling task."""
        try:
            # Establish persistent database connection
            self._db_conn = await self._db_manager.get_persistent_connection()
            logger.info("DifficultyPoller: Established persistent database connection")
        except Exception as e:
            logger.error(
                f"DifficultyPoller: Failed to establish database connection: {e}",
                exc_info=True,
            )
            raise

        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("DifficultyPoller started (polling every 60 seconds)")

    async def stop(self):
        """Stop background polling task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        # Close database connection
        if self._db_conn:
            await self._db_manager.close_persistent_connection(self._db_conn)
            self._db_conn = None

        logger.info("DifficultyPoller stopped")

    async def _poll_loop(self):
        """Main polling loop that fetches difficulty every 60 seconds."""
        logger.info("DifficultyPoller: Starting poll loop")

        # Initial poll immediately on startup
        await self._poll_difficulty()

        # Then poll every 60 seconds
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._poll_difficulty()
            except asyncio.CancelledError:
                logger.info("DifficultyPoller: Poll loop cancelled")
                break
            except Exception as e:
                logger.error(
                    f"DifficultyPoller: Unexpected error in poll loop: {e}",
                    exc_info=True,
                )
                # Continue polling even on errors
                await asyncio.sleep(self._poll_interval)

    async def _poll_difficulty(self):
        """Fetch difficulty from Bitcoin Core and update target."""
        logger.debug("DifficultyPoller: Polling Bitcoin Core for difficulty")

        try:
            async with BitcoinRPCClient(
                host=self.config.btc_rpc_host,
                port=self.config.btc_rpc_port,
                user=self.config.btc_rpc_user,
                password=self.config.btc_rpc_password,
                timeout=10.0,
            ) as rpc_client:
                difficulty = await rpc_client.get_difficulty()

                if difficulty is None:
                    logger.warning(
                        "DifficultyPoller: Failed to fetch difficulty from Bitcoin Core"
                    )
                    return

                # Convert difficulty to target
                target = difficulty_to_target(difficulty)

                logger.info(
                    f"DifficultyPoller: Fetched difficulty={difficulty:.2f}, "
                    f"target={target[:16]}..."
                )

                # Update ShareProcessor
                await self._update_target(target)

        except Exception as e:
            logger.error(
                f"DifficultyPoller: Error polling difficulty: {e}", exc_info=True
            )

    async def _update_target(self, new_target: str):
        """Update block target in database and ShareProcessor.

        Args:
            new_target: New block target hash (64-character hex string)
        """
        if not self._db_conn:
            logger.error("DifficultyPoller: Database connection not available")
            return

        try:
            # Check if target actually changed
            if (
                self.share_processor.current_block_target
                and self.share_processor.current_block_target == new_target
            ):
                logger.debug(
                    "DifficultyPoller: Target unchanged, skipping update"
                )
                return

            old_target = self.share_processor.current_block_target
            logger.info(
                f"DifficultyPoller: Block target changed: {old_target} -> {new_target}"
            )

            # Update database
            await self._db_conn.execute(
                """
                INSERT INTO global_state (key, value, updated_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (key) DO UPDATE SET
                    value = EXCLUDED.value,
                    updated_at = EXCLUDED.updated_at
                """,
                "current_block_target",
                new_target,
            )

            # Update ShareProcessor
            self.share_processor.update_block_target(new_target)

            logger.info(
                f"DifficultyPoller: Successfully updated block target to {new_target[:16]}..."
            )

        except Exception as e:
            logger.error(
                f"DifficultyPoller: Failed to update target: {e}", exc_info=True
            )
