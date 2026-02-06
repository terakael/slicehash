#!/usr/bin/env python3
"""Manual test for priority system implementation.

Tests traffic level thresholds and share consumption rules.
"""

from src.slicehash.priority import (
    TrafficLevel,
    calculate_traffic_level,
    calculate_shares_consumed
)


def test_traffic_level_thresholds():
    """Test that traffic levels are correctly determined from user counts."""
    print("Testing traffic level thresholds...")

    # GREEN: < 10 active users
    assert calculate_traffic_level(0) == TrafficLevel.GREEN
    assert calculate_traffic_level(5) == TrafficLevel.GREEN
    assert calculate_traffic_level(9) == TrafficLevel.GREEN

    # ORANGE: 10-25 active users
    assert calculate_traffic_level(10) == TrafficLevel.ORANGE
    assert calculate_traffic_level(15) == TrafficLevel.ORANGE
    assert calculate_traffic_level(25) == TrafficLevel.ORANGE

    # RED: > 25 active users
    assert calculate_traffic_level(26) == TrafficLevel.RED
    assert calculate_traffic_level(50) == TrafficLevel.RED
    assert calculate_traffic_level(100) == TrafficLevel.RED

    print("✓ Traffic level thresholds correct")


def test_green_traffic_consumption():
    """Test that green traffic always consumes 1 share regardless of priority."""
    print("Testing green traffic share consumption...")

    for priority in range(1, 6):
        shares = calculate_shares_consumed(priority, TrafficLevel.GREEN)
        assert shares == 1, f"Priority {priority} should consume 1 share during green traffic, got {shares}"

    print("✓ Green traffic always consumes 1 share")


def test_orange_red_traffic_consumption():
    """Test that orange/red traffic applies priority multiplier."""
    print("Testing orange/red traffic share consumption...")

    # Test ORANGE traffic
    for priority in range(1, 6):
        shares = calculate_shares_consumed(priority, TrafficLevel.ORANGE)
        assert shares == priority, f"Priority {priority} should consume {priority} shares during orange traffic, got {shares}"

    # Test RED traffic
    for priority in range(1, 6):
        shares = calculate_shares_consumed(priority, TrafficLevel.RED)
        assert shares == priority, f"Priority {priority} should consume {priority} shares during red traffic, got {shares}"

    print("✓ Orange/red traffic applies priority multiplier")


def test_invalid_priority():
    """Test that invalid priority values are rejected."""
    print("Testing invalid priority validation...")

    invalid_priorities = [0, -1, 6, 10, 100]

    for priority in invalid_priorities:
        try:
            calculate_shares_consumed(priority, TrafficLevel.GREEN)
            assert False, f"Priority {priority} should have raised ValueError"
        except ValueError as e:
            assert "Invalid priority" in str(e)
            assert "must be between 1 and 5" in str(e)

    print("✓ Invalid priority values rejected")


def test_consumption_examples():
    """Test concrete examples from the specification."""
    print("Testing concrete examples...")

    # Green traffic - everyone pays 1
    assert calculate_shares_consumed(1, TrafficLevel.GREEN) == 1
    assert calculate_shares_consumed(3, TrafficLevel.GREEN) == 1
    assert calculate_shares_consumed(5, TrafficLevel.GREEN) == 1

    # Orange traffic - priority multiplier
    assert calculate_shares_consumed(1, TrafficLevel.ORANGE) == 1
    assert calculate_shares_consumed(3, TrafficLevel.ORANGE) == 3
    assert calculate_shares_consumed(5, TrafficLevel.ORANGE) == 5

    # Red traffic - priority multiplier
    assert calculate_shares_consumed(1, TrafficLevel.RED) == 1
    assert calculate_shares_consumed(3, TrafficLevel.RED) == 3
    assert calculate_shares_consumed(5, TrafficLevel.RED) == 5

    print("✓ Concrete examples pass")


def main():
    """Run all manual tests."""
    print("=" * 60)
    print("Priority System Manual Test")
    print("=" * 60)
    print()

    test_traffic_level_thresholds()
    test_green_traffic_consumption()
    test_orange_red_traffic_consumption()
    test_invalid_priority()
    test_consumption_examples()

    print()
    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
