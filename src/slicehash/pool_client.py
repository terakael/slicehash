"""HTTP client for pool API integration.

This module provides an async HTTP client for updating coinbase addresses
on the Stratum V2 pool during rotation events.
"""

import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class PoolClient:
    """Async HTTP client for pool API integration.

    Handles coinbase address updates via POST to pool's /api/coinbase endpoint.
    Implements graceful error handling - logs failures but doesn't raise exceptions.

    Usage:
        async with PoolClient(pool_url="http://pool.example.com", timeout=5.0) as client:
            success = await client.update_coinbase(
                address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
                user_id=123,
                tag="rotation-event"
            )
            if success:
                logger.info("Coinbase address updated successfully")
    """

    def __init__(self, pool_url: str, timeout: float = 10.0):
        """Initialize pool client.

        Args:
            pool_url: Base URL of the pool (e.g., "http://pool.example.com")
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.pool_url = pool_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        """Enter async context manager."""
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def update_coinbase(
        self,
        address: str,
        user_id: int,
        tag: str
    ) -> bool:
        """Update coinbase address on the pool.

        Sends POST request to pool's /api/coinbase endpoint with the new
        address to use for the next mining block.

        Args:
            address: Bitcoin address to receive mining rewards
            user_id: User ID being rotated to
            tag: Event tag for tracking (e.g., "rotation-event")

        Returns:
            True if update succeeded, False on any error

        Note:
            This method never raises exceptions. All errors are logged
            and return False for graceful degradation.
        """
        if not self._client:
            logger.error("PoolClient not initialized. Use async context manager.")
            return False

        endpoint = f"{self.pool_url}/api/coinbase"
        payload = {
            "address": address,
            "user_id": user_id,
            "tag": tag
        }

        try:
            logger.info(
                f"Updating coinbase address on pool: "
                f"user_id={user_id}, address={address[:15]}..., tag={tag}"
            )

            response = await self._client.post(endpoint, json=payload)
            response.raise_for_status()

            logger.info(
                f"Successfully updated coinbase address: "
                f"status={response.status_code}"
            )
            return True

        except httpx.TimeoutException:
            logger.error(
                f"Timeout connecting to pool API at {endpoint} "
                f"(timeout={self.timeout}s)"
            )
            return False

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Pool API returned error: status={e.response.status_code}, "
                f"body={e.response.text}"
            )
            return False

        except httpx.RequestError as e:
            logger.error(
                f"Network error connecting to pool API at {endpoint}: {e}"
            )
            return False

        except Exception as e:
            logger.error(
                f"Unexpected error updating coinbase address: {e}",
                exc_info=True
            )
            return False
