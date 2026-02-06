"""Manual test for pool client graceful error handling.

Tests that PoolClient handles network errors without raising exceptions.
"""

import asyncio
import logging

from src.slicehash.pool_client import PoolClient

# Configure logging to see error messages
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)


async def test_unreachable_pool():
    """Test graceful error handling with unreachable pool."""
    print("\n=== Testing Pool Client Error Handling ===\n")

    # Test 1: Connection refused (invalid host)
    print("Test 1: Connection to unreachable pool...")
    async with PoolClient(pool_url="http://localhost:9999", timeout=2.0) as client:
        result = await client.update_coinbase(
            address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            user_id=123,
            tag="test-rotation"
        )
        print(f"Result: {result}")
        assert result is False, "Expected False for unreachable pool"
        print("✓ Test 1 passed: Connection error handled gracefully\n")

    # Test 2: Invalid domain (DNS resolution failure)
    print("Test 2: Connection to invalid domain...")
    async with PoolClient(pool_url="http://invalid.example.localhost", timeout=2.0) as client:
        result = await client.update_coinbase(
            address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            user_id=456,
            tag="test-rotation"
        )
        print(f"Result: {result}")
        assert result is False, "Expected False for invalid domain"
        print("✓ Test 2 passed: DNS error handled gracefully\n")

    # Test 3: Timeout (extremely short timeout)
    print("Test 3: Timeout with valid domain but unreachable...")
    async with PoolClient(pool_url="http://example.com:9999", timeout=0.1) as client:
        result = await client.update_coinbase(
            address="bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh",
            user_id=789,
            tag="test-rotation"
        )
        print(f"Result: {result}")
        assert result is False, "Expected False for timeout"
        print("✓ Test 3 passed: Timeout handled gracefully\n")

    print("=== All Tests Passed ===")
    print("✓ PoolClient handles network errors gracefully")
    print("✓ No exceptions raised")
    print("✓ Returns False on all error conditions")
    print("✓ Logging provides observability")


if __name__ == "__main__":
    try:
        asyncio.run(test_unreachable_pool())
        print("\n✓ Manual test completed successfully")
    except Exception as e:
        print(f"\n✗ Test failed with exception: {e}")
        raise
