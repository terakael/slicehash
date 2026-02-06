"""Manual test for rotation logic and fairness algorithm.

Tests:
1. Never-served users get highest priority
2. Weighted wait time affects selection order
3. Rotation interval scales with user count
4. should_rotate respects time and share requirements
"""

import asyncio
import os
from datetime import datetime, timedelta
from slicehash.rotation import (
    RotationState,
    select_next_user,
    should_rotate,
    calculate_rotation_interval
)
from slicehash.db.manager import (
    DatabaseManager,
    init_database,
    get_or_create_user,
    add_transaction
)


async def test_rotation():
    """Test rotation logic with realistic scenarios."""
    # Use temporary database
    test_db = "test_rotation.db"
    if os.path.exists(test_db):
        os.remove(test_db)

    print("=== Rotation Logic Test ===\n")

    # Initialize test database
    await init_database(test_db)

    async with DatabaseManager(test_db) as db:
        print("1. Creating test users with transactions...")
        user1 = await get_or_create_user(db, "bc1user1", "user1")
        user2 = await get_or_create_user(db, "bc1user2", "user2")
        user3 = await get_or_create_user(db, "bc1user3", "user3")

        # All users get 1000 shares
        await add_transaction(db, user1, 1000)
        await add_transaction(db, user2, 1000)
        await add_transaction(db, user3, 1000)

        print(f"   Created users: {user1}, {user2}, {user3}")

        print("\n2. Setting user priorities...")
        # user1: default priority 1
        # user2: priority 5 (highest, pays most during congestion)
        # user3: default priority 1
        await db.execute(
            "UPDATE users SET priority_multiplier = 5 WHERE user_id = ?",
            (user2,)
        )
        await db.commit()
        print(f"   user1: priority 1, user2: priority 5, user3: priority 1")

        print("\n3. Testing never-served priority...")
        # All users have last_served_at = NULL
        next_user = await select_next_user(db)
        print(f"   Selected user: {next_user}")
        assert next_user in [user1, user2, user3], "Should select one of the never-served users"
        print("   ✓ Never-served user selected")

        print("\n4. Simulating service history...")
        # Mark user1 as served 5 minutes ago
        await db.execute(
            "UPDATE users SET last_served_at = datetime('now', '-5 minutes') WHERE user_id = ?",
            (user1,)
        )
        # Mark user3 as served just now
        await db.execute(
            "UPDATE users SET last_served_at = datetime('now') WHERE user_id = ?",
            (user3,)
        )
        await db.commit()
        print("   user1: served 5 minutes ago")
        print("   user2: never served (NULL)")
        print("   user3: served just now")

        print("\n5. Testing fairness algorithm...")
        # Should select user2 (never served) despite high priority
        next_user = await select_next_user(db)
        print(f"   Selected user: {next_user}")
        assert next_user == user2, f"Should select never-served user2, got {next_user}"
        print("   ✓ Never-served user2 selected despite high priority multiplier")

        print("\n6. Testing weighted wait time after all served...")
        # Mark user2 as served now
        await db.execute(
            "UPDATE users SET last_served_at = datetime('now') WHERE user_id = ?",
            (user2,)
        )
        await db.commit()
        print("   user1: served 5 minutes ago, priority 1")
        print("   user2: served just now, priority 5")
        print("   user3: served just now, priority 1")

        # Should select user1 (longest wait time)
        next_user = await select_next_user(db)
        print(f"   Selected user: {next_user}")
        assert next_user == user1, f"Should select user1 (longest wait), got {next_user}"
        print("   ✓ User with longest wait time selected")

        print("\n7. Testing exclude_user_id parameter...")
        # Exclude user1, should get user3 (both served recently, but user3 has lower priority)
        next_user = await select_next_user(db, exclude_user_id=user1)
        print(f"   Selected user (excluding {user1}): {next_user}")
        assert next_user in [user2, user3], f"Should select user2 or user3, got {next_user}"
        print("   ✓ Exclusion works correctly")

        print("\n8. Testing with user who has no remaining shares...")
        # Create user4 with 0 shares
        user4 = await get_or_create_user(db, "bc1user4", "user4")
        # Don't add any transactions - no quota
        print(f"   Created user4 ({user4}) with 0 shares")

        # Should not select user4 (not in active users)
        next_user = await select_next_user(db)
        assert next_user != user4, f"Should not select user4 (no quota), got {next_user}"
        print("   ✓ User with no remaining shares not selected")

    # Test rotation interval calculation
    print("\n9. Testing rotation interval calculation...")
    intervals = [
        (5, 12.0),
        (10, 6.0),
        (20, 3.0),
        (30, 2.0),
        (60, 1.0),
        (100, 1.0),  # Minimum 1.0 second
    ]
    for user_count, expected in intervals:
        interval = calculate_rotation_interval(user_count)
        assert interval == expected, f"Expected {expected}s for {user_count} users, got {interval}s"
        print(f"   {user_count} users: {interval}s interval ✓")

    # Test should_rotate logic
    print("\n10. Testing should_rotate conditions...")
    now = datetime.now()

    # Test case: enough time + shares
    state = RotationState(
        current_user_id=1,
        shares_this_turn=1,
        rotation_started_at=now - timedelta(seconds=10),
        last_rotation_at=now - timedelta(seconds=15)
    )
    assert should_rotate(state, 5.0, now) is True, "Should rotate (10s > 5s, 1+ shares)"
    print("   ✓ Rotation triggered with sufficient time and shares")

    # Test case: not enough time
    state = RotationState(
        current_user_id=1,
        shares_this_turn=1,
        rotation_started_at=now - timedelta(seconds=10),
        last_rotation_at=now - timedelta(seconds=15)
    )
    assert should_rotate(state, 15.0, now) is False, "Should not rotate (10s < 15s)"
    print("   ✓ No rotation when time insufficient")

    # Test case: no shares yet
    state_no_shares = RotationState(
        current_user_id=1,
        shares_this_turn=0,
        rotation_started_at=now - timedelta(seconds=10),
        last_rotation_at=now - timedelta(seconds=15)
    )
    assert should_rotate(state_no_shares, 5.0, now) is False, "Should not rotate (0 shares)"
    print("   ✓ No rotation when no shares found")

    # Test case: no current user
    state_no_user = RotationState(
        current_user_id=None,
        shares_this_turn=5,
        rotation_started_at=now - timedelta(seconds=10)
    )
    assert should_rotate(state_no_user, 5.0, now) is False, "Should not rotate (no user)"
    print("   ✓ No rotation when no user assigned")

    # Test case: no start time
    state_no_start = RotationState(
        current_user_id=1,
        shares_this_turn=1,
        rotation_started_at=None
    )
    assert should_rotate(state_no_start, 5.0, now) is False, "Should not rotate (no start time)"
    print("   ✓ No rotation when rotation_started_at is None")

    print("\n=== All rotation tests passed! ===")

    # Cleanup
    os.remove(test_db)


if __name__ == "__main__":
    asyncio.run(test_rotation())
