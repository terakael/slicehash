"""Server-Sent Events (SSE) utilities for real-time notifications.

This module provides reusable SSE streaming patterns for auth and payment flows.
"""

import json
import logging
from typing import Any, AsyncGenerator, Callable, Optional

from quart import Response, make_response

logger = logging.getLogger(__name__)


async def create_sse_endpoint(
    event_stream_generator: AsyncGenerator[str, None], timeout: bool = False
) -> Response:
    """Create standardized SSE endpoint response.

    Args:
        event_stream_generator: Async generator yielding SSE-formatted event strings
        timeout: Whether to enable timeout (default False for long-lived connections)

    Returns:
        Quart Response configured for SSE streaming
    """
    response = await make_response(
        event_stream_generator,
        {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
    if not timeout:
        response.timeout = None  # Disable timeout for SSE
    return response


def format_sse_event(
    event_type: str, data: dict | str, event_id: Any = None
) -> str:
    """Format data as SSE event string.

    Args:
        event_type: SSE event type (e.g., 'connected', 'authenticated')
        data: Event data (dict will be JSON encoded, str passed through)
        event_id: Optional event ID

    Returns:
        SSE-formatted event string with newlines
    """
    if isinstance(data, dict):
        data_str = json.dumps(data)
    else:
        data_str = data

    lines = [f"event: {event_type}", f"data: {data_str}"]

    if event_id is not None:
        lines.insert(0, f"id: {event_id}")

    return "\n".join(lines) + "\n\n"


async def sse_stream_from_queue(
    queue: Any,
    manager: Any,
    channel: str,
    connected_event_data: dict,
    notification_event_type: str = "notification",
    transform_notification: Optional[Callable] = None,
) -> AsyncGenerator[str, None]:
    """Generic SSE stream pattern with queue subscription and cleanup.

    Args:
        queue: asyncio.Queue for receiving notifications
        manager: SSE manager instance with unsubscribe method
        channel: Channel name for unsubscribing
        connected_event_data: Data to send in initial 'connected' event
        notification_event_type: Event type name for notifications (default 'notification')
        transform_notification: Optional function to transform notification before sending

    Yields:
        SSE-formatted event strings
    """
    try:
        # Send connected event
        yield format_sse_event("connected", connected_event_data)

        # Wait for notification
        notification = await queue.get()

        # Transform if needed
        if transform_notification:
            notification = transform_notification(notification)

        # Send notification event
        yield format_sse_event(notification_event_type, notification)

    except Exception as e:
        logger.error(f"SSE stream error: {e}")
        yield format_sse_event("error", {"error": "Internal error"})
    finally:
        if queue:
            await manager.unsubscribe(channel, queue)
