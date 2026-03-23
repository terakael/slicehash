"""Hash utility functions for SliceHash.

This module provides hash-related utilities including level calculation
with fractional precision for accurate ranking.
"""

import math


def bits_to_target(bits_hex: str) -> int:
    """Convert compact bits representation to target value.

    The bits field in Bitcoin uses a compact representation where:
    - First byte: exponent (number of bytes)
    - Next 3 bytes: mantissa (coefficient)

    Formula: target = mantissa * 256^(exponent - 3)

    Args:
        bits_hex: Compact bits representation (e.g., "0x17034219")

    Returns:
        Target value as integer
    """
    # Remove 0x prefix if present
    if bits_hex.startswith("0x") or bits_hex.startswith("0X"):
        bits_hex = bits_hex[2:]

    # Parse as big-endian integer
    bits_int = int(bits_hex, 16)

    # Extract exponent and mantissa
    exponent = bits_int >> 24
    mantissa = bits_int & 0xFFFFFF

    # Calculate target
    if exponent <= 3:
        target = mantissa >> (8 * (3 - exponent))
    else:
        target = mantissa << (8 * (exponent - 3))

    return target


def is_valid_block(share_hash: str, bits: str) -> bool:
    """Check if a share hash meets the block difficulty target.

    Args:
        share_hash: Hexadecimal hash string
        bits: Compact bits representation (e.g., "0x17034219")

    Returns:
        True if share_hash <= target, False otherwise
    """
    if not share_hash or not bits:
        return False

    try:
        target = bits_to_target(bits)
        hash_int = int(share_hash, 16)
        return hash_int <= target
    except (ValueError, ZeroDivisionError):
        return False


def calculate_level(hash_str: str) -> float:
    """Calculate the level of a hash with fractional precision.

    Levels reflect rarity relative to the proxy's minimum accepted hash.
    Shares barely above the threshold score near 0; the level rises steeply
    for moderately rare shares and flattens progressively for the very rare.

    The effective score is the continuous leading-zero count above BASE_ZEROS,
    which is tuned to the actual proxy threshold (not just an integer boundary).
    Applying log2(1 + effective) gives the desired curve shape: steep initial
    climb that decelerates as rarity increases.

    Formula:
        leading_zeros = 63 - floor(log16(hash_int))
        frac          = 1 - 16^(log_frac - 1)   (smaller first digit = higher)
        effective     = max(0, leading_zeros + frac - BASE_ZEROS)
        level         = SCALE * log2(1 + effective)

    Reference points (BASE_ZEROS=11.7, SCALE=30):
        at proxy threshold              ->  ~0
        11 leading zeros, best fraction ->  ~9
        12 leading zeros, avg fraction  ->  ~24
        13 leading zeros, avg fraction  ->  ~39
        14 leading zeros, avg fraction  ->  ~50
        16 leading zeros, avg fraction  ->  ~65

    BASE_ZEROS tuning: set to the effective score of the minimum proxy hash.
    Adjust if observed minimum shares drift significantly from level ~0.

    Args:
        hash_str: Hexadecimal hash string (64 characters)

    Returns:
        Level value with fractional precision, minimum 1.0
    """
    # Tuned to align effective=0 with the actual proxy threshold hash.
    # Increase if minimum observed shares are too high; decrease if too low.
    BASE_ZEROS = 11.7
    SCALE = 30.0

    if not hash_str:
        return 0.0

    # Convert hash to integer
    hash_int = int(hash_str, 16)
    if hash_int == 0:
        return 1.0 + SCALE * math.log2(1 + 64 - BASE_ZEROS)  # All zeros: maximum possible

    # Calculate logarithm base 16
    log_val = math.log(hash_int, 16)
    log_floor = math.floor(log_val)
    log_frac = log_val - log_floor

    # Continuous leading-zero count
    # Number of significant hex digits = floor(log16(n)) + 1
    # Leading zeros = 64 - significant_digits = 63 - floor(log16(n))
    leading_zeros_int = 63 - log_floor

    # Fractional part: smaller first non-zero digit = higher fractional value
    # frac = 1 - 16^(log_frac - 1)
    frac = 1 - (16 ** (log_frac - 1))

    # Hashes below the proxy's minimum leading-zero count score 0.
    # BASE_ZEROS calibrates level magnitude within accepted shares and may
    # differ from this integer boundary.
    if leading_zeros_int < 11:
        return 0.0

    effective = max(0.0, leading_zeros_int + frac - BASE_ZEROS)
    return 1.0 + SCALE * math.log2(1 + effective)
