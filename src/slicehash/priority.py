"""Priority system with traffic-based share consumption multipliers.

This module implements SliceHash's fairness mechanism during congestion:
- During LOW traffic (green): Everyone pays equally (1 share per submission)
- During MEDIUM/HIGH traffic (orange/red): Priority determines cost multiplier

Rationale:
When the pool has capacity, all users get equal treatment regardless of priority.
During congestion, users with higher priority pay proportionally more shares to
maintain their position, implementing a fair market-based queuing mechanism.

Traffic levels are determined by active user count:
- GREEN: < 10 active users (low traffic)
- ORANGE: 10-25 active users (medium traffic)
- RED: > 25 active users (high traffic)

Priority multipliers range from 1x to 5x, where:
- Priority 1: 1x multiplier (lowest priority, cheapest during congestion)
- Priority 5: 5x multiplier (highest priority, most expensive during congestion)
"""

from enum import Enum


class TrafficLevel(Enum):
    """Traffic level based on active user count.

    Attributes:
        GREEN: Low traffic, no congestion (<10 active users)
        ORANGE: Medium traffic, moderate congestion (10-25 active users)
        RED: High traffic, severe congestion (>25 active users)
    """
    GREEN = "green"
    ORANGE = "orange"
    RED = "red"


def calculate_traffic_level(active_user_count: int) -> TrafficLevel:
    """Calculate current traffic level based on active user count.

    Traffic thresholds:
    - GREEN: < 10 active users
    - ORANGE: 10-25 active users
    - RED: > 25 active users

    Args:
        active_user_count: Number of currently active users in the pool.

    Returns:
        TrafficLevel enum indicating current congestion level.

    Example:
        >>> calculate_traffic_level(5)
        TrafficLevel.GREEN
        >>> calculate_traffic_level(15)
        TrafficLevel.ORANGE
        >>> calculate_traffic_level(30)
        TrafficLevel.RED
    """
    if active_user_count < 10:
        return TrafficLevel.GREEN
    elif active_user_count <= 25:
        return TrafficLevel.ORANGE
    else:
        return TrafficLevel.RED


def calculate_shares_consumed(priority: int, traffic_level: TrafficLevel) -> int:
    """Calculate shares consumed based on priority and traffic level.

    During GREEN traffic: Always returns 1 (no priority multiplier applied)
    During ORANGE/RED traffic: Returns priority value (1-5x multiplier)

    This implements the fairness mechanism where:
    - Everyone pays equally during low traffic
    - Higher priority users pay proportionally more during congestion

    Args:
        priority: User priority level (1-5), where 1 is lowest and 5 is highest.
        traffic_level: Current traffic congestion level.

    Returns:
        Number of shares consumed for this submission.

    Raises:
        ValueError: If priority is not in the valid range (1-5).

    Example:
        >>> calculate_shares_consumed(3, TrafficLevel.GREEN)
        1
        >>> calculate_shares_consumed(3, TrafficLevel.ORANGE)
        3
        >>> calculate_shares_consumed(5, TrafficLevel.RED)
        5
    """
    if not (1 <= priority <= 5):
        raise ValueError(
            f"Invalid priority {priority}. Priority must be between 1 and 5 inclusive."
        )

    if traffic_level == TrafficLevel.GREEN:
        # During low traffic, everyone pays 1 share regardless of priority
        return 1
    else:
        # During congestion (ORANGE or RED), apply priority multiplier
        return priority
