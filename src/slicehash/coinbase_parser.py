"""Coinbase transaction parser for extracting verification fields.

This module provides utilities to parse Bitcoin coinbase transactions and extract
fields needed for share verification and display.
"""

import hashlib
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
_BECH32M_CONST = 0x2bc830a3
_BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def _bech32_polymod(values: list) -> int:
    gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    chk = 1
    for v in values:
        b = chk >> 25
        chk = (chk & 0x1ffffff) << 5 ^ v
        for i in range(5):
            chk ^= gen[i] if ((b >> i) & 1) else 0
    return chk


def _bech32_hrp_expand(hrp: str) -> list:
    return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]


def _bech32_create_checksum(hrp: str, data: list, bech32m: bool) -> list:
    const = _BECH32M_CONST if bech32m else 1
    values = _bech32_hrp_expand(hrp) + list(data)
    polymod = _bech32_polymod(values + [0, 0, 0, 0, 0, 0]) ^ const
    return [(polymod >> 5 * (5 - i)) & 31 for i in range(6)]


def _convertbits(data: bytes, frombits: int, tobits: int, pad: bool = True) -> Optional[list]:
    acc, bits, ret = 0, 0, []
    maxv = (1 << tobits) - 1
    max_acc = (1 << (frombits + tobits - 1)) - 1
    for value in data:
        if value < 0 or (value >> frombits):
            return None
        acc = ((acc << frombits) | value) & max_acc
        bits += frombits
        while bits >= tobits:
            bits -= tobits
            ret.append((acc >> bits) & maxv)
    if pad:
        if bits:
            ret.append((acc << (tobits - bits)) & maxv)
    elif bits >= frombits or ((acc << (tobits - bits)) & maxv):
        return None
    return ret


def _bech32_encode(hrp: str, witver: int, witprog: bytes) -> Optional[str]:
    """Encode a segwit address using bech32 (v0) or bech32m (v1+)."""
    data = _convertbits(witprog, 8, 5)
    if data is None:
        return None
    bech32m = witver != 0
    combined = [witver] + data
    checksum = _bech32_create_checksum(hrp, combined, bech32m)
    return hrp + '1' + ''.join([_BECH32_CHARSET[d] for d in combined + checksum])


def _base58check_encode(payload: bytes) -> str:
    """Encode bytes as Base58Check (for P2PKH and P2SH addresses)."""
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    data = payload + checksum
    count = 0
    for byte in data:
        if byte != 0:
            break
        count += 1
    n = int.from_bytes(data, 'big')
    result = []
    while n:
        n, remainder = divmod(n, 58)
        result.append(_BASE58_ALPHABET[remainder])
    result.extend([_BASE58_ALPHABET[0]] * count)
    return ''.join(reversed(result))


def parse_coinbase_script(script_hex: str) -> dict:
    """Parse SV2 coinbase scriptSig to extract embedded data.

    SV2 coinbase scriptSig format:
    - BIP34 block height: [len_byte] + height_bytes (little-endian)
    - OP_0 (0x00): pushed by coinbase_prefix
    - Pool/miner tag: [len_byte] + b"/pool/miner/"
    - Extranonce: [len_byte] + extranonce_bytes

    Args:
        script_hex: Hexadecimal coinbase script

    Returns:
        Dictionary with extracted fields (block_height, pool_tag, miner_tag, extranonce)
    """
    result = {
        "block_height": 0,
        "pool_tag": "",
        "miner_tag": "",
        "extranonce": "",
    }

    try:
        script_bytes = bytes.fromhex(script_hex)
        offset = 0

        # BIP34 block height: first byte is push length, then height LE
        if len(script_bytes) < 1:
            return result
        height_len = script_bytes[0]
        if 1 <= height_len <= 4:
            height_bytes = script_bytes[1:1 + height_len]
            if height_bytes:
                result["block_height"] = int.from_bytes(height_bytes, byteorder='little')
            offset = 1 + height_len
        else:
            offset = 1

        # OP_0 (0x00) byte appended to coinbase_prefix in SV2
        if offset < len(script_bytes) and script_bytes[offset] == 0x00:
            offset += 1

        # Pool/miner tag: [len_byte] + "/pool/miner/"
        if offset < len(script_bytes):
            tag_len = script_bytes[offset]
            offset += 1
            if offset + tag_len <= len(script_bytes):
                tag_bytes = script_bytes[offset:offset + tag_len]
                offset += tag_len
                try:
                    tag_str = tag_bytes.decode('ascii')
                    parts = tag_str.strip('/').split('/')
                    if len(parts) >= 1 and parts[0]:
                        result["pool_tag"] = parts[0]
                    if len(parts) >= 2 and parts[1]:
                        result["miner_tag"] = parts[1]
                except Exception:
                    pass

        # Extranonce: [len_byte] + extranonce_bytes
        if offset < len(script_bytes):
            extranonce_len = script_bytes[offset]
            offset += 1
            if offset + extranonce_len <= len(script_bytes):
                result["extranonce"] = script_bytes[offset:offset + extranonce_len].hex()

    except Exception as e:
        logger.warning(f"Failed to parse coinbase script: {e}")

    return result


def parse_coinbase_transaction(coinbase_tx_hex: str) -> dict:
    """Parse a coinbase transaction to extract all verification fields.

    Args:
        coinbase_tx_hex: Full coinbase transaction in hexadecimal

    Returns:
        Dictionary with extracted fields:
        - block_height: Block height (from BIP34 in coinbase script)
        - coinbase_address: The payout address
        - pool_tag: Pool identifier
        - miner_tag: Miner identifier
        - extranonce: Extra nonce value
        - witness_commitment: Witness commitment (SegWit)
        - coinbase_value: Output value in satoshis
    """
    result = {
        "block_height": 0,
        "coinbase_address": "",
        "pool_tag": "",
        "miner_tag": "",
        "extranonce": "",
        "witness_commitment": "",
        "coinbase_value": 0,
        "sequence": 0xffffffff,
        "locktime": 0,
    }

    try:
        # Parse transaction structure (simplified parser)
        tx_bytes = bytes.fromhex(coinbase_tx_hex)
        offset = 0

        # Version (4 bytes)
        if len(tx_bytes) < offset + 4:
            return result
        offset += 4

        # Check for witness flag (0x00 0x01)
        has_witness = False
        if len(tx_bytes) >= offset + 2 and tx_bytes[offset] == 0x00 and tx_bytes[offset + 1] == 0x01:
            has_witness = True
            offset += 2

        # Input count (varint - simplified: assume 1 byte = 1 input for coinbase)
        if len(tx_bytes) < offset + 1:
            return result
        offset += 1

        # Previous output (32 bytes hash + 4 bytes index = 36 bytes, all zeros for coinbase)
        if len(tx_bytes) < offset + 36:
            return result
        offset += 36

        # Script length (varint)
        if len(tx_bytes) < offset + 1:
            return result
        script_len = tx_bytes[offset]
        if script_len >= 0xfd:  # Multi-byte varint
            return result  # Simplified: don't handle multi-byte varints
        offset += 1

        # Coinbase script
        if len(tx_bytes) < offset + script_len:
            return result
        coinbase_script = tx_bytes[offset:offset + script_len]
        offset += script_len

        # Parse coinbase script for tags and extranonce
        script_data = parse_coinbase_script(coinbase_script.hex())
        result.update(script_data)

        # Sequence (4 bytes)
        if len(tx_bytes) < offset + 4:
            return result
        result["sequence"] = int.from_bytes(tx_bytes[offset:offset + 4], 'little')
        offset += 4

        # Output count (varint)
        if len(tx_bytes) < offset + 1:
            return result
        output_count = tx_bytes[offset]
        offset += 1

        # Parse first output for address and value
        if output_count >= 1:
            # Value (8 bytes, little-endian)
            if len(tx_bytes) < offset + 8:
                return result
            value_bytes = tx_bytes[offset:offset + 8]
            result["coinbase_value"] = int.from_bytes(value_bytes, byteorder='little')
            offset += 8

            # Script length (varint)
            if len(tx_bytes) < offset + 1:
                return result
            out_script_len = tx_bytes[offset]
            if out_script_len >= 0xfd:
                return result
            offset += 1

            # Output script (contains address)
            if len(tx_bytes) < offset + out_script_len:
                return result
            out_script = tx_bytes[offset:offset + out_script_len]

            # Extract address from output script (simplified)
            # P2WPKH: OP_0 <20-byte-hash>
            # P2WSH: OP_0 <32-byte-hash>
            # P2PKH: OP_DUP OP_HASH160 <20-byte-hash> OP_EQUALVERIFY OP_CHECKSIG
            # P2SH: OP_HASH160 <20-byte-hash> OP_EQUAL

            if len(out_script) == 22 and out_script[0] == 0x00 and out_script[1] == 0x14:
                # P2WPKH (SegWit v0, 20 bytes)
                addr = _bech32_encode('bc', 0, out_script[2:22])
                if addr:
                    result["coinbase_address"] = addr
            elif len(out_script) == 34 and out_script[0] == 0x00 and out_script[1] == 0x20:
                # P2WSH (SegWit v0, 32 bytes)
                addr = _bech32_encode('bc', 0, out_script[2:34])
                if addr:
                    result["coinbase_address"] = addr
            elif len(out_script) == 34 and out_script[0] == 0x51 and out_script[1] == 0x20:
                # P2TR (Taproot, SegWit v1, 32 bytes)
                addr = _bech32_encode('bc', 1, out_script[2:34])
                if addr:
                    result["coinbase_address"] = addr
            elif len(out_script) == 25 and out_script[0] == 0x76 and out_script[1] == 0xa9:
                # P2PKH
                result["coinbase_address"] = _base58check_encode(bytes([0x00]) + out_script[3:23])
            elif len(out_script) == 23 and out_script[0] == 0xa9:
                # P2SH
                result["coinbase_address"] = _base58check_encode(bytes([0x05]) + out_script[2:22])

            offset += out_script_len

        # Check for witness commitment in subsequent outputs
        # Witness commitment is in an OP_RETURN output
        for _ in range(1, output_count):
            if len(tx_bytes) < offset + 8:
                break
            offset += 8  # Value

            if len(tx_bytes) < offset + 1:
                break
            out_script_len = tx_bytes[offset]
            offset += 1

            if len(tx_bytes) < offset + out_script_len:
                break
            out_script = tx_bytes[offset:offset + out_script_len]

            # Check for witness commitment: OP_RETURN (0x6a) followed by data
            if len(out_script) >= 38 and out_script[0] == 0x6a and out_script[1] == 0x24:
                # Witness commitment magic: 0xaa21a9ed
                if out_script[2:6].hex() == "aa21a9ed":
                    result["witness_commitment"] = out_script[6:38].hex()

            offset += out_script_len

        # Locktime: last 4 bytes of the transaction
        if len(tx_bytes) >= 4:
            result["locktime"] = int.from_bytes(tx_bytes[-4:], 'little')

    except Exception as e:
        logger.error(f"Failed to parse coinbase transaction: {e}", exc_info=True)

    return result


def extract_miner_tag(coinbase_tx_hex: str) -> str:
    """Extract miner tag from coinbase transaction.

    This is a convenience function for the common case of just needing the miner tag.

    Args:
        coinbase_tx_hex: Full coinbase transaction in hexadecimal

    Returns:
        Miner tag string (empty if not found)
    """
    parsed = parse_coinbase_transaction(coinbase_tx_hex)
    return parsed.get("miner_tag", "")


def extract_coinbase_address(coinbase_tx_hex: str) -> str:
    """Extract coinbase payout address from transaction.

    This is a convenience function for the common case of just needing the address.

    Args:
        coinbase_tx_hex: Full coinbase transaction in hexadecimal

    Returns:
        Bitcoin address string (empty if not found)
    """
    parsed = parse_coinbase_transaction(coinbase_tx_hex)
    return parsed.get("coinbase_address", "")
