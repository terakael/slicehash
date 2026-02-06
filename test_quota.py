#!/usr/bin/env python3
"""Manual verification script for quota calculation logic.

Demonstrates:
1. Quota calculation with transactions and share consumption
2. Active user identification filtering zero/negative balance
3. Billable classification based on threshold
"""

import asyncio
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from slicehash.db import DatabaseManager, init_database, get_or_create_user, add_transaction
from slicehash.quota import calculate_shares_remaining, get_active_users, classify_share_billable


async def main():
    """Run quota calculation tests."""
    db_path = "test_quota.db"

    # Clean slate
    Path(db_path).unlink(missing_ok=True)

    print("=== SliceHash Quota Calculation Verification ===\n")

    # Initialize database
    print("1. Initializing test database...")
    await init_database(db_path)
    print("   ✓ Database initialized\n")

    async with DatabaseManager(db_path) as db:
        # Create test users
        print("2. Creating test users...")
        alice_id = await get_or_create_user(db, "alice_address", "Alice")
        bob_id = await get_or_create_user(db, "bob_address", "Bob")
        charlie_id = await get_or_create_user(db, "charlie_address", "Charlie")
        print(f"   ✓ Alice: user_id={alice_id}")
        print(f"   ✓ Bob: user_id={bob_id}")
        print(f"   ✓ Charlie: user_id={charlie_id}\n")

        # Add transactions (share purchases)
        print("3. Recording share purchases...")
        await add_transaction(db, alice_id, 1000)
        await add_transaction(db, bob_id, 500)
        await add_transaction(db, charlie_id, 2000)
        print("   ✓ Alice purchased 1000 shares")
        print("   ✓ Bob purchased 500 shares")
        print("   ✓ Charlie purchased 2000 shares\n")

        # Test classify_share_billable
        print("4. Testing billable classification...")
        threshold = 1000000.0
        test_cases = [
            (1500000.0, True, "high difficulty"),
            (1000000.0, True, "exact threshold"),
            (999999.9, False, "below threshold"),
            (500000.0, False, "low difficulty"),
        ]
        for difficulty, expected, desc in test_cases:
            result = classify_share_billable(difficulty, threshold)
            status = "✓" if result == expected else "✗"
            print(f"   {status} {desc}: {difficulty} → billable={result}")
        print()

        # Add share events (mining activity)
        # Note: Each share_event consumes 1-5 shares based on priority multiplier
        # To consume many shares, we need multiple events
        print("5. Recording share events...")

        # Alice: Submit 50 billable shares (50 events × 5 shares = 250 total consumed)
        for i in range(50):
            await db.execute(
                """
                INSERT INTO share_events
                (submitted_at, user_id, share_difficulty, billable, shares_consumed)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"2026-02-06T09:00:{i:02d}Z", alice_id, 1500000.0, 1, 5)
            )
        print(f"   ✓ Alice: 50 billable share events (50 × 5 = 250 shares consumed)")

        # Bob: Submit 300 billable shares (300 events × 2 shares = 600 total consumed)
        # This will cause overconsumption since Bob only has 500 shares
        for i in range(300):
            await db.execute(
                """
                INSERT INTO share_events
                (submitted_at, user_id, share_difficulty, billable, shares_consumed)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"2026-02-06T09:05:{i%60:02d}Z", bob_id, 2000000.0, 1, 2)
            )
        print(f"   ✓ Bob: 300 billable share events (300 × 2 = 600 shares consumed, overconsumption!)")

        # Charlie: Submit 50 non-billable shares (shouldn't count toward quota)
        for i in range(50):
            await db.execute(
                """
                INSERT INTO share_events
                (submitted_at, user_id, share_difficulty, billable, shares_consumed)
                VALUES (?, ?, ?, ?, ?)
                """,
                (f"2026-02-06T09:10:{i:02d}Z", charlie_id, 500000.0, 0, 2)
            )
        print(f"   ✓ Charlie: 50 non-billable share events (low difficulty, doesn't affect quota)")

        await db.commit()
        print()

        # Calculate shares remaining
        print("6. Calculating shares remaining...")
        alice_remaining = await calculate_shares_remaining(db, alice_id)
        bob_remaining = await calculate_shares_remaining(db, bob_id)
        charlie_remaining = await calculate_shares_remaining(db, charlie_id)

        print(f"   Alice: 1000 purchased - 250 consumed = {alice_remaining} remaining")
        print(f"   Bob: 500 purchased - 600 consumed = {bob_remaining} remaining (negative!)")
        print(f"   Charlie: 2000 purchased - 0 consumed = {charlie_remaining} remaining")
        print()

        # Verify calculations
        assert alice_remaining == 750, f"Expected 750, got {alice_remaining}"
        assert bob_remaining == -100, f"Expected -100, got {bob_remaining}"
        assert charlie_remaining == 2000, f"Expected 2000, got {charlie_remaining}"
        print("   ✓ All calculations correct\n")

        # Get active users
        print("7. Identifying active users...")
        active = await get_active_users(db)
        print(f"   Active users (shares_remaining > 0): {active}")
        print(f"   ✓ Alice (user_id={alice_id}): {alice_id in active} (750 remaining)")
        print(f"   ✓ Bob (user_id={bob_id}): {bob_id in active} (-100 remaining, excluded)")
        print(f"   ✓ Charlie (user_id={charlie_id}): {charlie_id in active} (2000 remaining)")
        print()

        # Verify active user filtering
        assert alice_id in active, "Alice should be active"
        assert bob_id not in active, "Bob should not be active (negative balance)"
        assert charlie_id in active, "Charlie should be active"
        print("   ✓ Active user filtering correct\n")

    print("=== All Tests Passed ===")
    print("\nQuota calculation logic verified:")
    print("  • Shares remaining = purchased - consumed (billable only)")
    print("  • Active users = users with shares_remaining > 0")
    print("  • Billable classification based on difficulty threshold")

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


if __name__ == "__main__":
    asyncio.run(main())
