"""Server-Sent Events (SSE) manager for real-time share notifications.

This module provides SSE functionality with:
- Multi-tab support (multiple connections per user)
- In-memory subscriber tracking (no Redis required)
- Thread-safe queue management
- Automatic cleanup on disconnect
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)


@dataclass
class ShareNotification:
    """Share notification sent to SSE clients."""
    share_id: int
    user_id: int
    submitted_at: str
    level: int
    is_block: bool
    share_hash: Optional[str]
    billable: bool
    shares_consumed: int


class SSEManager:
    """Manages SSE connections and dispatches share notifications.

    Attributes:
        _subscribers: Maps user_id to set of asyncio.Queue objects (one per tab/connection)
        _lock: Asyncio lock for thread-safe access to subscribers
    """

    def __init__(self, queue_maxsize: int = 100):
        """Initialize SSE manager.

        Args:
            queue_maxsize: Maximum number of buffered notifications per connection
        """
        self._subscribers: Dict[int, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize

    async def subscribe(self, user_id: int) -> asyncio.Queue:
        """Register new SSE connection for user.

        Args:
            user_id: User ID for the connection

        Returns:
            Queue that will receive ShareNotification objects
        """
        queue = asyncio.Queue(maxsize=self._queue_maxsize)

        async with self._lock:
            if user_id not in self._subscribers:
                self._subscribers[user_id] = set()
            self._subscribers[user_id].add(queue)

        logger.info(f"SSE subscriber added: user_id={user_id}, total={len(self._subscribers[user_id])}")
        return queue

    async def unsubscribe(self, user_id: int, queue: asyncio.Queue):
        """Remove SSE connection for user.

        Args:
            user_id: User ID for the connection
            queue: Queue to remove
        """
        async with self._lock:
            if user_id in self._subscribers:
                self._subscribers[user_id].discard(queue)

                # Cleanup empty user entries
                if not self._subscribers[user_id]:
                    del self._subscribers[user_id]

        logger.info(f"SSE subscriber removed: user_id={user_id}")

    async def notify_share(self, notification: ShareNotification):
        """Dispatch share notification to all user's connections.

        Args:
            notification: Share notification to send
        """
        async with self._lock:
            if notification.user_id not in self._subscribers:
                return

            # Copy set to avoid modification during iteration
            queues = self._subscribers[notification.user_id].copy()

        for queue in queues:
            try:
                queue.put_nowait(notification)
            except asyncio.QueueFull:
                logger.warning(
                    f"SSE queue full for user {notification.user_id}, "
                    f"dropping notification (share_id={notification.share_id})"
                )

    def get_subscriber_count(self) -> int:
        """Get total number of active SSE connections.

        Returns:
            Total number of active connections across all users
        """
        return sum(len(queues) for queues in self._subscribers.values())
