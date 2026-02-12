"""Hash utility functions for SliceHash.

This module provides hash-related utilities including level calculation
with fractional precision for accurate ranking.
"""

import math


def calculate_level(hash_str: str) -> float:
    """Calculate the level of a hash with fractional precision.

    Uses a logarithmic approach to provide precise ranking beyond just leading zeros.
    The integer part is (leading_zeros - 5), and the fractional part is based on
    the first non-zero hex digit (smaller digit = higher level).

    This allows for more accurate ranking: hashes with the same number of leading
    zeros can now be differentiated based on their subsequent digits.

    Examples:
        "00000000001..." (10 zeros, then '1') -> level 59.4
        "0000000000f..." (10 zeros, then 'f') -> level 50.3
        "000000000001..." (11 zeros, then '1') -> level 69.4

    Mathematical approach:
        Instead of counting leading zeros in a string, we convert the hash to
        base 10 and use logarithms:
        - log16(hash_int) gives us the position of the most significant hex digit
        - leading_zeros = 63 - floor(log16(hash_int))
        - The fractional part comes from: 1 - 16^(log_frac - 1)
          where log_frac is the fractional part of log16(hash_int)

    Args:
        hash_str: Hexadecimal hash string (64 characters)

    Returns:
        Level value with fractional precision, minimum 0.0
    """
    if not hash_str:
        return 0.0

    # Convert hash to integer
    hash_int = int(hash_str, 16)
    if hash_int == 0:
        return 590.0  # All zeros: (64 - 5) * 10

    # Calculate logarithm base 16
    log_val = math.log(hash_int, 16)
    log_floor = math.floor(log_val)
    log_frac = log_val - log_floor

    # Integer level from leading zeros
    # Number of significant hex digits = floor(log16(n)) + 1
    # Leading zeros = 64 - significant_digits = 63 - floor(log16(n))
    leading_zeros_int = 63 - log_floor
    level_int = max(0, leading_zeros_int - 5)

    # Fractional part: smaller first non-zero digit = higher fractional value
    # This is derived from: frac = (16 - first_digit) / 16
    # Which can be computed as: frac = 1 - 16^(log_frac - 1)
    frac = 1 - (16 ** (log_frac - 1))

    level = (level_int + frac) * 10
    return level
