"""Rotation logic with fairness algorithm for selecting next mining user.

This module implements SliceHash's core rotation mechanics:
- RotationState tracks current user and turn progress
- Fairness algorithm selects least recently served user
- Weighted wait time accounts for both time elapsed and priority multiplier
- Adaptive rotation interval scales with active user count

Fairness Algorithm:
The select_next_user function implements a weighted fairness model:
1. Never-served users get highest priority (bootstraps fair distribution)
2. Among previously-served users, calculate: weighted_wait = time_since / priority_multiplier
3. Higher priority users (who pay more during congestion) wait "less long" in queue
4. Lower priority users (who pay less) get more frequent turns during low traffic

Rotation Decision:
should_rotate triggers rotation when BOTH conditions met:
- Time elapsed >= adaptive interval (scales with user count)
- Current user found at least 1 share (ensures minimum productivity)

This ensures every user gets a turn while preventing instant rotation on first share.
"""

import asyncpg
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from .quota import get_active_users


@dataclass
class RotationState:
    """Current rotation state (in-memory tracking).

    Tracks which user is currently mining and their progress during this turn.
    This state is ephemeral (not persisted to database) and resets on service restart.

    Attributes:
        current_user_id: User currently assigned mining slot (None if no active users)
        shares_this_turn: How many shares current user has found this turn
        rotation_started_at: When current user's turn began (for time threshold)
        last_rotation_at: When we last rotated (for interval calculation)

    Example:
        >>> state = RotationState(
        ...     current_user_id=42,
        ...     shares_this_turn=3,
        ...     rotation_started_at=datetime.now() - timedelta(seconds=15),
        ...     last_rotation_at=datetime.now() - timedelta(seconds=20)
        ... )
    """
    current_user_id: Optional[int] = None
    shares_this_turn: int = 0
    rotation_started_at: Optional[datetime] = None
    last_rotation_at: Optional[datetime] = None


def calculate_rotation_interval(active_user_count: int) -> float:
    """Calculate adaptive rotation interval based on active user count.

    Implements the formula: 60 seconds / active_user_count
    This ensures all users get approximately equal time over a 60-second window.

    More users = shorter intervals = faster rotation = more frequent turns for everyone
    Fewer users = longer intervals = more time per turn = more shares per rotation

    Args:
        active_user_count: Number of users currently eligible for mining rotation

    Returns:
        Rotation interval in seconds (minimum 1.0 second)

    Example:
        >>> calculate_rotation_interval(5)
        12.0
        >>> calculate_rotation_interval(20)
        3.0
        >>> calculate_rotation_interval(60)
        1.0
        >>> calculate_rotation_interval(100)
        1.0
    """
    if active_user_count <= 0:
        return 60.0  # Default to full minute if no users

    interval = 60.0 / active_user_count
    return max(interval, 1.0)  # Minimum 1 second to prevent thrashing


def should_rotate(
    state: RotationState,
    rotation_interval: float,
    now: datetime
) -> bool:
    """Determine if rotation should occur based on time and share criteria.

    Rotation triggers when ALL conditions are met:
    1. Current user exists (current_user_id is not None)
    2. Current user found at least 1 share this turn
    3. Time elapsed since rotation_started_at >= rotation_interval

    The 1-share minimum ensures users get productive turns before rotation.
    The time threshold ensures fair distribution of mining time.

    Args:
        state: Current rotation state
        rotation_interval: Time threshold in seconds (from calculate_rotation_interval)
        now: Current timestamp for elapsed time calculation

    Returns:
        True if rotation should occur, False otherwise

    Example:
        >>> now = datetime.now()
        >>> state = RotationState(
        ...     current_user_id=1,
        ...     shares_this_turn=1,
        ...     rotation_started_at=now - timedelta(seconds=10)
        ... )
        >>> should_rotate(state, 5.0, now)
        True
        >>> should_rotate(state, 15.0, now)
        False
        >>> state_no_shares = RotationState(
        ...     current_user_id=1,
        ...     shares_this_turn=0,
        ...     rotation_started_at=now - timedelta(seconds=10)
        ... )
        >>> should_rotate(state_no_shares, 5.0, now)
        False
    """
    # No rotation if no one is mining
    if state.current_user_id is None:
        return False

    # Need at least 1 share before rotation
    if state.shares_this_turn == 0:
        return False

    # Safety check: can't calculate elapsed time without start time
    if state.rotation_started_at is None:
        return False

    # Check if enough time has elapsed
    elapsed = (now - state.rotation_started_at).total_seconds()
    return elapsed >= rotation_interval


async def select_next_user(db: asyncpg.Connection) -> Optional[int]:
    """Select next user for mining based on fairness algorithm.

    Implements weighted fairness algorithm:
    1. Get all active users (positive share balance)
    2. Prioritize never-served users (last_served_at IS NULL)
    3. Among served users, calculate weighted_wait = time_since / priority_multiplier
    4. Select user with maximum weighted_wait

    Weighted Wait Time Rationale:
    - User with priority 1 who waited 10 min: weighted_wait = 600s / 1 = 600s
    - User with priority 5 who waited 10 min: weighted_wait = 600s / 5 = 120s
    - Priority 1 user gets selected (fairer since they pay less during congestion)

    This ensures:
    - High priority users (pay more) don't monopolize the queue
    - Low priority users (pay less) get fair turns based on wait time
    - Everyone eventually gets served proportional to their patience
    - Users who were just served have low weighted_wait and are naturally deprioritized

    Args:
        db: Active database connection

    Returns:
        user_id of selected user, or None if no eligible users

    Raises:
        asyncpg.PostgresError: If database queries fail

    Example:
        >>> # Select initial user
        >>> next_user = await select_next_user(db)
        >>> # Later, select fairest user (naturally rotates due to last_served_at)
        >>> next_user = await select_next_user(db)
    """
    # Get all users with positive share balance
    active_users = await get_active_users(db)

    # No eligible users
    if not active_users:
        return None

    # Build SQL to fetch user data for fairness calculation
    # Query: last_served_at and priority_multiplier for all active users
    user_data = await db.fetch(
        """
        SELECT user_id, last_served_at, priority_multiplier
        FROM users
        WHERE user_id = ANY($1::int[])
        """,
        active_users
    )

    # Apply fairness algorithm
    # Priority 1: Never-served users (last_served_at IS NULL)
    # Priority 2: Users with maximum weighted_wait_time

    never_served = []
    previously_served = []

    for row in user_data:
        user_id = row['user_id']
        last_served_at = row['last_served_at']
        priority_multiplier = row['priority_multiplier']

        if last_served_at is None:
            never_served.append(user_id)
        else:
            previously_served.append((user_id, last_served_at, priority_multiplier))

    # Never-served users get highest priority
    if never_served:
        # Return first never-served user (arbitrary but deterministic)
        return never_served[0]

    # Calculate weighted wait time for previously-served users
    if not previously_served:
        return None

    # Use Python datetime (timezone-naive) for consistency with stored timestamps
    # Use UTC for consistency (database stores naive UTC timestamps)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    best_user_id = None
    max_weighted_wait = -1

    for user_id, last_served_at, priority_multiplier in previously_served:
        # Calculate seconds since last served
        time_since_seconds = (now - last_served_at).total_seconds()
        time_since = int(time_since_seconds)

        # Weighted wait time = time_since / priority_multiplier
        # Higher priority users have shorter "effective" wait time
        weighted_wait = time_since / priority_multiplier

        if weighted_wait > max_weighted_wait:
            max_weighted_wait = weighted_wait
            best_user_id = user_id

    return best_user_id
