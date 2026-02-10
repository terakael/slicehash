"""Redis Stream consumer for ingesting share events.

This module provides a Redis Streams consumer that:
- Reads share events from a Redis stream
- Validates and parses message data
- Queues messages to the existing ShareProcessor
- Provides reliable at-least-once delivery via consumer groups
"""

import asyncio
import json
import logging
from typing import Optional

import redis.asyncio as redis

from .config import Config

logger = logging.getLogger(__name__)


class RedisStreamConsumer:
    """Consumer for Redis Streams that ingests share events.

    Uses Redis consumer groups for reliable delivery and reads messages
    in a blocking loop. Messages are validated and queued to the existing
    share processing queue.

    Attributes:
        config: SliceHash configuration with Redis connection details.
        share_queue: Asyncio queue for processed messages.
        redis_client: Redis async client connection.
        consumer_task: Background task for consuming messages.
        running: Flag indicating if consumer is active.
    """

    def __init__(self, config: Config, share_queue: asyncio.Queue):
        """Initialize Redis Stream consumer.

        Args:
            config: SliceHash configuration with Redis settings.
            share_queue: Queue to push validated messages to.
        """
        self.config = config
        self.share_queue = share_queue
        self.redis_client: Optional[redis.Redis] = None
        self.consumer_task: Optional[asyncio.Task] = None
        self.running = False

    async def start(self) -> None:
        """Start the Redis consumer.

        Establishes connection, creates consumer group if needed,
        and starts the consumption loop.
        """
        if self.running:
            logger.warning("Redis consumer already running")
            return

        logger.info(
            f"Starting Redis consumer: {self.config.redis_host}:{self.config.redis_port} "
            f"stream={self.config.redis_stream_key} "
            f"group={self.config.redis_consumer_group} "
            f"consumer={self.config.redis_consumer_name}"
        )

        # Create Redis connection
        self.redis_client = redis.Redis(
            host=self.config.redis_host,
            port=self.config.redis_port,
            password=self.config.redis_password,
            decode_responses=True,
            socket_keepalive=True,
            socket_connect_timeout=5,
            retry_on_timeout=True,
        )

        # Test connection
        try:
            await self.redis_client.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Create consumer group (idempotent - ignores if exists)
        try:
            await self.redis_client.xgroup_create(
                name=self.config.redis_stream_key,
                groupname=self.config.redis_consumer_group,
                id="0",
                mkstream=True,
            )
            logger.info(f"Created consumer group: {self.config.redis_consumer_group}")
        except redis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group already exists: {self.config.redis_consumer_group}")
            else:
                logger.error(f"Failed to create consumer group: {e}")
                raise

        # Start consumption loop
        self.running = True
        self.consumer_task = asyncio.create_task(self._consume_loop())
        logger.info("Redis consumer started")

    async def stop(self) -> None:
        """Stop the Redis consumer.

        Gracefully shuts down the consumption loop and closes the connection.
        """
        if not self.running:
            logger.warning("Redis consumer not running")
            return

        logger.info("Stopping Redis consumer")
        self.running = False

        # Cancel consumer task
        if self.consumer_task:
            self.consumer_task.cancel()
            try:
                await self.consumer_task
            except asyncio.CancelledError:
                pass

        # Close Redis connection
        if self.redis_client:
            await self.redis_client.close()
            await self.redis_client.connection_pool.disconnect()

        logger.info("Redis consumer stopped")

    async def _consume_loop(self) -> None:
        """Main consumption loop.

        Continuously reads messages from Redis stream using XREADGROUP,
        processes them, and acknowledges successful processing.
        """
        while self.running:
            try:
                # Read messages from stream (block for 5 seconds)
                # Start from '>' to get only new undelivered messages
                messages = await self.redis_client.xreadgroup(
                    groupname=self.config.redis_consumer_group,
                    consumername=self.config.redis_consumer_name,
                    streams={self.config.redis_stream_key: ">"},
                    count=10,  # Read up to 10 messages at once
                    block=5000,  # Block for 5 seconds
                )

                # Process each message
                for stream_name, message_list in messages:
                    for message_id, message_data in message_list:
                        try:
                            await self._process_message(message_id, message_data)

                            # Acknowledge successful processing
                            await self.redis_client.xack(
                                self.config.redis_stream_key,
                                self.config.redis_consumer_group,
                                message_id,
                            )
                        except Exception as e:
                            logger.error(
                                f"Failed to process message {message_id}: {e}",
                                exc_info=True,
                            )
                            # Don't acknowledge - message will be redelivered

            except asyncio.CancelledError:
                logger.info("Consumer loop cancelled")
                break
            except redis.ConnectionError as e:
                logger.error(f"Redis connection error: {e}")
                await asyncio.sleep(5)  # Wait before reconnecting
                try:
                    await self.redis_client.ping()
                    logger.info("Redis connection restored")
                except Exception:
                    logger.error("Failed to restore Redis connection")
            except Exception as e:
                logger.error(f"Unexpected error in consumer loop: {e}", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight loop on errors

    async def _process_message(self, message_id: str, message_data: dict) -> None:
        """Process a single message from the stream.

        Validates message structure, converts types, and queues to ShareProcessor.

        Args:
            message_id: Redis message ID.
            message_data: Message field-value pairs from stream.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        # Validate required fields
        required = [
            "user_id",
            "nonce",
            "ntime",
            "version",
            "coinbase_address",
            "coinbase_prefix_tag",
            "is_block",
        ]
        missing = [field for field in required if field not in message_data]
        if missing:
            raise ValueError(f"Missing required fields: {missing}")

        # Convert types (Redis stores everything as strings)
        try:
            processed_data = {
                "user_id": message_data["user_id"],
                "nonce": int(message_data["nonce"]),
                "ntime": int(message_data["ntime"]),
                "version": int(message_data["version"]),
                "coinbase_address": message_data["coinbase_address"],
                "coinbase_prefix_tag": message_data["coinbase_prefix_tag"],
                "is_block": message_data["is_block"].lower() in ("true", "1", "yes"),
            }

            # Optional fields
            if "share_hash" in message_data:
                processed_data["share_hash"] = message_data["share_hash"]
            if "block_target" in message_data:
                processed_data["block_target"] = message_data["block_target"]
            if "job_id" in message_data:
                processed_data["job_id"] = int(message_data["job_id"])
            if "timestamp_secs" in message_data:
                processed_data["timestamp_secs"] = int(message_data["timestamp_secs"])

        except (ValueError, KeyError) as e:
            raise ValueError(f"Invalid message data: {e}") from e

        # Queue for processing (non-blocking)
        self.share_queue.put_nowait(processed_data)
        logger.debug(f"Queued message {message_id} from Redis stream")

    async def is_connected(self) -> bool:
        """Check if Redis connection is active.

        Returns:
            True if connected and responsive, False otherwise.
        """
        if not self.redis_client:
            return False

        try:
            await self.redis_client.ping()
            return True
        except Exception:
            return False
