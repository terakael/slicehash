"""Bitcoin Core RPC client for difficulty polling.

This module provides an async HTTP client for calling Bitcoin Core JSON-RPC
methods, specifically for fetching network difficulty.
"""

import base64
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class BitcoinRPCClient:
    """Async HTTP client for Bitcoin Core RPC integration.

    Handles JSON-RPC calls to Bitcoin Core daemon with HTTP Basic Auth.
    Implements graceful error handling - logs failures but doesn't raise exceptions.

    Usage:
        async with BitcoinRPCClient(
            host="127.0.0.1",
            port=8332,
            user="rpcuser",
            password="rpcpass",
            timeout=10.0
        ) as client:
            difficulty = await client.get_difficulty()
            if difficulty is not None:
                logger.info(f"Current difficulty: {difficulty}")
    """

    def __init__(
        self,
        host: str,
        port: int,
        user: str,
        password: str,
        timeout: float = 10.0,
    ):
        """Initialize Bitcoin RPC client.

        Args:
            host: Bitcoin Core RPC host (e.g., "127.0.0.1")
            port: Bitcoin Core RPC port (default: 8332 for mainnet)
            user: RPC username
            password: RPC password
            timeout: Request timeout in seconds (default: 10.0)
        """
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._request_id = 0

        # Build RPC URL
        self.rpc_url = f"http://{host}:{port}"

        # Build Basic Auth header
        credentials = f"{user}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        self._auth_header = f"Basic {encoded}"

    async def __aenter__(self):
        """Enter async context manager."""
        headers = {
            "Authorization": self._auth_header,
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(timeout=self.timeout, headers=headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit async context manager."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _call_rpc(self, method: str, params: list = None) -> Optional[Any]:
        """Call a Bitcoin Core RPC method.

        Args:
            method: RPC method name (e.g., "getdifficulty")
            params: List of parameters (default: empty list)

        Returns:
            Result from RPC call, or None on error

        Note:
            This method never raises exceptions. All errors are logged
            and return None for graceful degradation.
        """
        if not self._client:
            logger.error("BitcoinRPCClient not initialized. Use async context manager.")
            return None

        if params is None:
            params = []

        self._request_id += 1
        payload = {
            "jsonrpc": "1.0",
            "id": self._request_id,
            "method": method,
            "params": params,
        }

        try:
            logger.debug(f"Calling Bitcoin RPC method: {method}")

            response = await self._client.post(self.rpc_url, json=payload)
            response.raise_for_status()

            data = response.json()

            # Check for RPC error
            if "error" in data and data["error"] is not None:
                logger.error(
                    f"Bitcoin RPC error for method '{method}': {data['error']}"
                )
                return None

            result = data.get("result")
            logger.debug(f"Bitcoin RPC {method} returned: {result}")
            return result

        except httpx.TimeoutException:
            logger.error(
                f"Timeout connecting to Bitcoin RPC at {self.rpc_url} "
                f"(timeout={self.timeout}s)"
            )
            return None

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Bitcoin RPC returned HTTP error: status={e.response.status_code}, "
                f"body={e.response.text}"
            )
            return None

        except httpx.RequestError as e:
            logger.error(
                f"Network error connecting to Bitcoin RPC at {self.rpc_url}: {e}"
            )
            return None

        except Exception as e:
            logger.error(
                f"Unexpected error calling Bitcoin RPC method '{method}': {e}",
                exc_info=True,
            )
            return None

    async def get_difficulty(self) -> Optional[float]:
        """Get current network difficulty.

        Calls the 'getdifficulty' RPC method which returns the
        proof-of-work difficulty as a multiple of the minimum difficulty.

        Returns:
            Current network difficulty as a float, or None on error

        Example:
            >>> difficulty = await client.get_difficulty()
            >>> if difficulty:
            ...     print(f"Network difficulty: {difficulty}")
            Network difficulty: 73197634206448.98
        """
        result = await self._call_rpc("getdifficulty")

        if result is None:
            return None

        try:
            return float(result)
        except (ValueError, TypeError) as e:
            logger.error(f"Failed to convert difficulty to float: {result}, error: {e}")
            return None
