"""Quota calculation logic for tracking user share balances.

This module provides functions for:
- Calculating remaining shares (purchased minus consumed)
- Identifying active users eligible for mining rotation
- Classifying shares as billable based on difficulty threshold

These functions form the core business logic of the SliceHash fairness
algorithm, determining which users are eligible to mine based on their
remaining quota.
"""

import aiosqlite
from cachetools import TTLCache

# Global cache for active users with 1-second TTL
# This reduces redundant database queries during high-frequency share processing
_active_users_cache = TTLCache(maxsize=100, ttl=1.0)


def classify_share_billable(share_difficulty: float, threshold: float) -> bool:
    """Determine if a share is billable based on difficulty threshold.

    A share is considered billable if its difficulty meets or exceeds
    the configured threshold. Billable shares consume quota, while
    non-billable shares (e.g., from learning/testing) do not.

    Args:
        share_difficulty: The difficulty value of the submitted share
        threshold: Minimum difficulty for a share to be billable

    Returns:
        True if share_difficulty >= threshold, False otherwise

    Example:
        >>> classify_share_billable(1500000.0, 1000000.0)
        True
        >>> classify_share_billable(500000.0, 1000000.0)
        False
    """
    return share_difficulty >= threshold


async def calculate_shares_remaining(
    db: aiosqlite.Connection,
    user_id: int
) -> int:
    """Calculate remaining share balance for a user.

    Computes: SUM(transactions.amount) - SUM(share_events.shares_consumed WHERE billable=1)

    This represents the user's current quota: shares they've purchased minus
    shares they've consumed through billable mining activity.

    Args:
        db: Active database connection
        user_id: ID of the user to calculate balance for

    Returns:
        Integer representing shares remaining (can be 0 or negative if overconsumed)

    Raises:
        aiosqlite.Error: If database query fails

    Example:
        >>> # User purchased 1000 shares, consumed 250 billable shares
        >>> await calculate_shares_remaining(db, user_id=42)
        750
    """
    # Get total shares purchased
    cursor = await db.execute(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ?",
        (user_id,)
    )
    row = await cursor.fetchone()
    purchased = row[0] if row else 0

    # Get total billable shares consumed
    cursor = await db.execute(
        """
        SELECT COALESCE(SUM(shares_consumed), 0)
        FROM share_events
        WHERE user_id = ? AND billable = 1
        """,
        (user_id,)
    )
    row = await cursor.fetchone()
    consumed = row[0] if row else 0

    return purchased - consumed


async def get_active_users(db: aiosqlite.Connection) -> list[int]:
    """Get list of user IDs with positive share balance.

    Returns all users who have shares remaining (shares_remaining > 0),
    making them eligible for the mining rotation queue.

    This function uses a 1-second cache to reduce redundant database queries
    during high-frequency share processing. The cache is acceptable because
    the active users list doesn't need to be perfectly real-time.

    Args:
        db: Active database connection

    Returns:
        List of user_ids with positive share balance, sorted by user_id

    Raises:
        aiosqlite.Error: If database query fails

    Example:
        >>> # Returns users with quota remaining
        >>> await get_active_users(db)
        [1, 3, 5, 7]
    """
    # Check cache first
    cache_key = "active_users"
    if cache_key in _active_users_cache:
        return _active_users_cache[cache_key]

    # Single aggregate query to get users with positive share balance
    # Replicates the logic from calculate_shares_remaining:
    # - purchased = SUM(transactions.amount) for the user
    # - consumed = SUM(share_events.shares_consumed) WHERE billable=1 for the user
    # - active = purchased > consumed
    cursor = await db.execute(
        """
        SELECT u.user_id
        FROM users u
        LEFT JOIN (
            SELECT user_id, COALESCE(SUM(amount), 0) AS purchased
            FROM transactions
            GROUP BY user_id
        ) t ON u.user_id = t.user_id
        LEFT JOIN (
            SELECT user_id, COALESCE(SUM(shares_consumed), 0) AS consumed
            FROM share_events
            WHERE billable = 1
            GROUP BY user_id
        ) se ON u.user_id = se.user_id
        WHERE COALESCE(t.purchased, 0) > COALESCE(se.consumed, 0)
        ORDER BY u.user_id
        """
    )
    rows = await cursor.fetchall()
    result = [row[0] for row in rows]

    # Cache the result with 1-second TTL
    _active_users_cache[cache_key] = result

    return result


def invalidate_active_users_cache():
    """Invalidate the active users cache.

    Call this function when user transactions or share events are modified
    outside of the normal share processing flow (e.g., manual adjustments,
    bulk imports) to ensure the cache doesn't serve stale data.

    This is optional - the cache will automatically expire after 1 second.
    This function is provided for cases where immediate cache invalidation
    is desired.
    """
    _active_users_cache.pop("active_users", None)
