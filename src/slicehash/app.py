"""Quart web application for SliceHash mining backend.

This module provides the HTTP server with:
- Fast webhook endpoint for receiving share events from pool (<10ms response)
- Background share processing with rotation logic
- Health check endpoint
"""

import asyncio
import logging
from typing import Optional

from quart import Quart, request, jsonify

from .config import load_config, Config
from .share_processor import ShareProcessor

logger = logging.getLogger(__name__)

# Global references (initialized in create_app)
share_queue: Optional[asyncio.Queue] = None
share_processor: Optional[ShareProcessor] = None


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
        """Start background share processor."""
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
            "user_id": int,
            "share_difficulty": float,
            "channel_id": str,
            "sequence_number": int,
            "submitted_at": str  # ISO timestamp
        }

        Returns:
            JSON response with status and 200 OK, or error with 400/500
        """
        try:
            data = await request.get_json()

            # Minimal validation (just check required fields exist)
            required = ["user_id", "share_difficulty", "channel_id", "sequence_number"]
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

    return app


# For running with hypercorn/uvicorn
app = create_app()
