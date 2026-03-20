"""Server-Sent Events (SSE) manager for real-time notifications.

This module provides SSE functionality with:
- Multi-tab support (multiple connections per user)
- In-memory subscriber tracking (no Redis required)
- Thread-safe queue management
- Automatic cleanup on disconnect
- Type-safe notification system
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Set, Optional

logger = logging.getLogger(__name__)


class NotificationBase(ABC):
    """Base class for all SSE notifications.

    All notification types must implement get_channel() to support self-routing.
    """

    @abstractmethod
    def get_channel(self) -> str:
        """Return the channel this notification should be routed to.

        Returns:
            Channel identifier string (e.g., "user:123" or "auth:abc")
        """
        pass


@dataclass
class ShareNotification(NotificationBase):
    """Share notification sent to SSE clients."""
    share_id: int
    user_id: int
    submitted_at: int
    level: float
    is_block: bool
    share_hash: Optional[str]
    billable: bool
    shares_consumed: int
    block_target_level: float
    tag: Optional[str] = None

    def get_channel(self) -> str:
        """Get the routing channel for this notification."""
        return f"user:{self.user_id}"


@dataclass
class AuthNotification(NotificationBase):
    """Authentication success notification sent to SSE clients."""
    token: str
    k1: str

    def get_channel(self) -> str:
        """Get the routing channel for this notification."""
        return f"auth:{self.k1}"


@dataclass
class InvoiceNotification(NotificationBase):
    """Lightning invoice payment notification sent to SSE clients."""
    invoice_id: int
    status: str  # "paid" or "expired"

    def get_channel(self) -> str:
        """Get the routing channel for this notification."""
        return f"invoice:{self.invoice_id}"


class SSEManager:
    """Manages SSE connections and dispatches typed notifications.

    Supports multiple notification types (shares, auth, etc.) with type safety.

    Attributes:
        _subscribers: Maps channel (str) to set of asyncio.Queue objects (one per tab/connection)
        _lock: Asyncio lock for thread-safe access to subscribers
    """

    def __init__(self, queue_maxsize: int = 100):
        """Initialize SSE manager.

        Args:
            queue_maxsize: Maximum number of buffered notifications per connection
        """
        self._subscribers: Dict[str, Set[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._queue_maxsize = queue_maxsize

    async def subscribe(self, channel: str) -> asyncio.Queue:
        """Register new SSE connection for channel.

        Args:
            channel: Channel identifier (str) for the connection

        Returns:
            Queue that will receive notification objects
        """
        queue = asyncio.Queue(maxsize=self._queue_maxsize)

        async with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = set()
            self._subscribers[channel].add(queue)

        logger.info(f"SSE subscriber added: channel={channel}, total={len(self._subscribers[channel])}")
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue):
        """Remove SSE connection for channel.

        Args:
            channel: Channel identifier (str) for the connection
            queue: Queue to remove
        """
        async with self._lock:
            if channel in self._subscribers:
                self._subscribers[channel].discard(queue)

                # Cleanup empty channel entries
                if not self._subscribers[channel]:
                    del self._subscribers[channel]

        logger.info(f"SSE subscriber removed: channel={channel}")

    async def notify(self, notification: NotificationBase):
        """Dispatch typed notification to all connections on a channel.

        The notification determines its own routing channel via get_channel().

        Args:
            notification: Notification object that implements NotificationBase
        """
        channel = notification.get_channel()

        async with self._lock:
            if channel not in self._subscribers:
                logger.debug(f"No subscribers for channel {channel}")
                return

            # Copy set to avoid modification during iteration
            queues = self._subscribers[channel].copy()

        logger.info(f"Notifying {len(queues)} SSE connections for channel {channel}")
        for queue in queues:
            try:
                queue.put_nowait(notification)
            except asyncio.QueueFull:
                logger.warning(
                    f"SSE queue full for channel {channel}, dropping notification"
                )

    def get_subscriber_count(self) -> int:
        """Get total number of active SSE connections.

        Returns:
            Total number of active connections across all users
        """
        return sum(len(queues) for queues in self._subscribers.values())
