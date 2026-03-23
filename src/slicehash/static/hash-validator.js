// Hash Validator JavaScript - Bitcoin mining share verification

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadShareData();
    setupEventListeners();
});

// Update floating result panel
function updateFloatingPanel(level, hash, isValid) {
    const levelBadge = document.getElementById('floating-level-badge');
    const hashValue = document.getElementById('floating-hash-value');
    const floatingPanel = document.getElementById('floating-result');

    // Show panel if hidden
    if (floatingPanel.style.display === 'none') {
        floatingPanel.style.display = 'block';
    }

    // Update level with styling
    if (level !== null && level !== undefined) {
        const { color, shape, borderStyle } = getLevelStyle(level);
        levelBadge.textContent = Math.floor(level);
        levelBadge.style.backgroundColor = color;

        // Apply shape class
        levelBadge.className = 'floating-level-badge shape-' + shape;

        if (borderStyle) {
            levelBadge.style.border = borderStyle;
        } else {
            levelBadge.style.border = `3px solid ${color}`;
            levelBadge.style.borderRightColor = adjustBrightness(color, -30);
            levelBadge.style.borderBottomColor = adjustBrightness(color, -30);
        }
    } else {
        levelBadge.textContent = '-';
        levelBadge.style.backgroundColor = '#f7931a';
        levelBadge.style.border = '3px solid #c46700';
    }

    // Update hash
    hashValue.textContent = hash || 'Calculating...';

    // Add validation styling to hash
    if (isValid === true) {
        hashValue.style.borderColor = '#4ec9b0';
    } else if (isValid === false) {
        hashValue.style.borderColor = '#f48771';
    } else {
        hashValue.style.borderColor = '#000000';
    }
}

// Helper to adjust color brightness
function adjustBrightness(color, percent) {
    const num = parseInt(color.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 + (R < 255 ? R < 1 ? 0 : R : 255) * 0x10000 +
        (G < 255 ? G < 1 ? 0 : G : 255) * 0x100 +
        (B < 255 ? B < 1 ? 0 : B : 255))
        .toString(16).slice(1);
}

// Fetch share data from API
async function loadShareData() {
    try {
        const response = await fetch(`/api/shares/${window.shareId}/validator-data`);
        if (!response.ok) {
            throw new Error('Failed to fetch share data');
        }

        const data = await response.json();

        // Populate form fields
        document.getElementById('version').value = data.version;
        document.getElementById('prevBlockHash').value = data.prev_block_hash;
        document.getElementById('timestamp').value = data.timestamp;
        document.getElementById('bits').value = data.bits;
        document.getElementById('nonce').value = data.nonce;
        document.getElementById('blockHeight').value = data.block_height;
        document.getElementById('poolTag').value = data.pool_tag;
        document.getElementById('minerTag').value = data.miner_tag;
        document.getElementById('extranonce').value = data.extranonce;
        document.getElementById('coinbaseAddress').value = data.coinbase_address;
        document.getElementById('coinbaseValue').value = data.coinbase_value;
        document.getElementById('sequence').value = data.sequence;
        document.getElementById('locktime').value = data.locktime;
        document.getElementById('witnessCommitment').value = data.witness_commitment || '';
        document.getElementById('merklePath').value = data.merkle_path.join('\n');

        // Store expected hash for comparison
        window.expectedHash = data.share_hash;
        window.expectedLevel = data.level;

        // Hide loading state and show form
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('validator-form').style.display = 'block';

        // Show floating panel
        document.getElementById('floating-result').style.display = 'block';

        // Auto-calculate on load
        await calculateHash();

    } catch (error) {
        console.error('Error loading share data:', error);
        document.getElementById('loading-state').innerHTML = `
            <p style="color: var(--error-color);">Failed to load share data: ${error.message}</p>
        `;
    }
}

// Setup event listeners
function setupEventListeners() {
    document.getElementById('calculate-btn').addEventListener('click', calculateHash);
    document.getElementById('floating-calculate-btn').addEventListener('click', calculateHash);

    // Optional: Auto-recalculate on input change
    document.querySelectorAll('.validator-input').forEach(input => {
        input.addEventListener('change', () => {
            // Clear results when inputs change
            document.getElementById('results').innerHTML = '';
            // Update floating panel to show pending state
            updateFloatingPanel(null, 'Pending...', null);
        });
    });
}

// ============================================================================
// BECH32 DECODER (Native implementation)
// ============================================================================

const BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';

function bech32Polymod(values) {
    const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];
    let chk = 1;
    for (const value of values) {
        const top = chk >> 25;
        chk = (chk & 0x1ffffff) << 5 ^ value;
        for (let i = 0; i < 5; i++) {
            if ((top >> i) & 1) {
                chk ^= GEN[i];
            }
        }
    }
    return chk;
}

function bech32HrpExpand(hrp) {
    const result = [];
    for (let i = 0; i < hrp.length; i++) {
        result.push(hrp.charCodeAt(i) >> 5);
    }
    result.push(0);
    for (let i = 0; i < hrp.length; i++) {
        result.push(hrp.charCodeAt(i) & 31);
    }
    return result;
}

function bech32VerifyChecksum(hrp, data) {
    const polymod = bech32Polymod([...bech32HrpExpand(hrp), ...data]);
    return polymod === 1 || polymod === 0x2bc830a3;
}

function bech32Decode(bechString) {
    if (bechString.length < 8 || bechString.length > 90) {
        throw new Error('Invalid bech32 string length');
    }

    const lower = bechString.toLowerCase();
    const upper = bechString.toUpperCase();
    if (bechString !== lower && bechString !== upper) {
        throw new Error('Mixed case bech32 string');
    }

    const pos = bechString.lastIndexOf('1');
    if (pos < 1 || pos + 7 > bechString.length) {
        throw new Error('Invalid bech32 separator position');
    }

    const hrp = lower.slice(0, pos);
    const data = [];

    for (let i = pos + 1; i < lower.length; i++) {
        const d = BECH32_CHARSET.indexOf(lower[i]);
        if (d === -1) {
            throw new Error('Invalid bech32 character');
        }
        data.push(d);
    }

    if (!bech32VerifyChecksum(hrp, data)) {
        throw new Error('Invalid bech32 checksum');
    }

    return { hrp, data: data.slice(0, -6) };
}

function bech32FromWords(words) {
    let value = 0;
    let bits = 0;
    const maxV = (1 << 8) - 1;
    const result = [];

    for (const word of words) {
        value = (value << 5) | word;
        bits += 5;

        while (bits >= 8) {
            bits -= 8;
            result.push((value >> bits) & maxV);
        }
    }

    if (bits >= 5 || ((value << (8 - bits)) & maxV)) {
        throw new Error('Invalid bech32 padding');
    }

    return new Uint8Array(result);
}

// ============================================================================
// CRYPTO HELPERS (Browser-compatible)
// ============================================================================

async function doubleSha256(buffer) {
    const hash1 = await crypto.subtle.digest('SHA-256', buffer);
    const hash2 = await crypto.subtle.digest('SHA-256', hash1);
    return new Uint8Array(hash2);
}

function reverseBuffer(buffer) {
    return new Uint8Array(buffer).reverse();
}

function uint32LE(value) {
    const buf = new Uint8Array(4);
    const view = new DataView(buf.buffer);
    view.setUint32(0, value, true);
    return buf;
}

function encodeVarInt(n) {
    if (n < 0xfd) {
        return new Uint8Array([n]);
    } else if (n <= 0xffff) {
        const buf = new Uint8Array(3);
        buf[0] = 0xfd;
        new DataView(buf.buffer).setUint16(1, n, true);
        return buf;
    } else if (n <= 0xffffffff) {
        const buf = new Uint8Array(5);
        buf[0] = 0xfe;
        new DataView(buf.buffer).setUint32(1, n, true);
        return buf;
    } else {
        const buf = new Uint8Array(9);
        buf[0] = 0xff;
        new DataView(buf.buffer).setBigUint64(1, BigInt(n), true);
        return buf;
    }
}

function encodeBlockHeight(height) {
    if (height <= 0x7f) {
        return new Uint8Array([0x01, height]);
    } else if (height <= 0x7fff) {
        return new Uint8Array([0x02, height & 0xff, (height >> 8) & 0xff]);
    } else if (height <= 0x7fffff) {
        return new Uint8Array([0x03, height & 0xff, (height >> 8) & 0xff, (height >> 16) & 0xff]);
    } else {
        return new Uint8Array([
            0x04,
            height & 0xff,
            (height >> 8) & 0xff,
            (height >> 16) & 0xff,
            (height >> 24) & 0xff
        ]);
    }
}

// Base58 decoding for legacy addresses
function base58Decode(address) {
    const ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz';
    const BASE = 58;

    let decoded = 0n;
    for (let i = 0; i < address.length; i++) {
        const char = address[i];
        const value = ALPHABET.indexOf(char);
        if (value === -1) throw new Error(`Invalid base58 character: ${char}`);
        decoded = decoded * BigInt(BASE) + BigInt(value);
    }

    // Convert to bytes
    const hex = decoded.toString(16);
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
        bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }

    // Add leading zeros
    let leadingZeros = 0;
    for (let i = 0; i < address.length && address[i] === '1'; i++) {
        leadingZeros++;
    }

    if (leadingZeros > 0) {
        const result = new Uint8Array(leadingZeros + bytes.length);
        result.set(bytes, leadingZeros);
        return result;
    }

    return bytes;
}

function addressToScriptPubKey(address) {
    // Bech32 addresses (native SegWit v0/v1): bc1, tb1, bcrt1
    if (address.startsWith('bc1') || address.startsWith('tb1') || address.startsWith('bcrt1')) {
        try {
            const decoded = bech32Decode(address);
            const witnessVersion = decoded.data[0];
            const witnessProgram = bech32FromWords(decoded.data.slice(1));

            // P2WPKH (bc1q/tb1q/bcrt1q): OP_0 <20-byte-hash>
            if (witnessVersion === 0 && witnessProgram.length === 20) {
                const scriptPubKey = new Uint8Array(22);
                scriptPubKey[0] = 0x00; // OP_0
                scriptPubKey[1] = 0x14; // 20 bytes
                scriptPubKey.set(witnessProgram, 2);
                return scriptPubKey;
            }
            // P2WSH (bc1q with 32 bytes): OP_0 <32-byte-hash>
            else if (witnessVersion === 0 && witnessProgram.length === 32) {
                const scriptPubKey = new Uint8Array(34);
                scriptPubKey[0] = 0x00; // OP_0
                scriptPubKey[1] = 0x20; // 32 bytes
                scriptPubKey.set(witnessProgram, 2);
                return scriptPubKey;
            }
            // P2TR (bc1p/tb1p/bcrt1p): OP_1 <32-byte-pubkey>
            else if (witnessVersion === 1 && witnessProgram.length === 32) {
                const scriptPubKey = new Uint8Array(34);
                scriptPubKey[0] = 0x51; // OP_1
                scriptPubKey[1] = 0x20; // 32 bytes
                scriptPubKey.set(witnessProgram, 2);
                return scriptPubKey;
            } else {
                throw new Error(`Unsupported witness version ${witnessVersion} or program length ${witnessProgram.length}`);
            }
        } catch (e) {
            throw new Error(`Failed to decode bech32 address: ${e.message}`);
        }
    }
    // P2SH addresses (wrapped SegWit): starts with '3'
    else if (address.startsWith('3') || address.startsWith('2')) { // '2' for testnet P2SH
        try {
            const decoded = base58Decode(address);
            // decoded = [version_byte, 20_byte_hash, 4_byte_checksum]
            if (decoded.length !== 25) {
                throw new Error(`Invalid P2SH address length: ${decoded.length}`);
            }

            // Extract the 20-byte script hash (skip version byte, exclude checksum)
            const scriptHash = decoded.slice(1, 21);

            // P2SH scriptPubKey: OP_HASH160 <20-byte-script-hash> OP_EQUAL
            const scriptPubKey = new Uint8Array(23);
            scriptPubKey[0] = 0xa9; // OP_HASH160
            scriptPubKey[1] = 0x14; // 20 bytes
            scriptPubKey.set(scriptHash, 2);
            scriptPubKey[22] = 0x87; // OP_EQUAL
            return scriptPubKey;
        } catch (e) {
            throw new Error(`Failed to decode P2SH address: ${e.message}`);
        }
    }
    // P2PKH addresses (legacy): starts with '1' or 'm'/'n' for testnet
    else if (address.startsWith('1') || address.startsWith('m') || address.startsWith('n')) {
        try {
            const decoded = base58Decode(address);
            if (decoded.length !== 25) {
                throw new Error(`Invalid P2PKH address length: ${decoded.length}`);
            }

            // Extract the 20-byte pubkey hash
            const pubkeyHash = decoded.slice(1, 21);

            // P2PKH scriptPubKey: OP_DUP OP_HASH160 <20-byte-pubkey-hash> OP_EQUALVERIFY OP_CHECKSIG
            const scriptPubKey = new Uint8Array(25);
            scriptPubKey[0] = 0x76; // OP_DUP
            scriptPubKey[1] = 0xa9; // OP_HASH160
            scriptPubKey[2] = 0x14; // 20 bytes
            scriptPubKey.set(pubkeyHash, 3);
            scriptPubKey[23] = 0x88; // OP_EQUALVERIFY
            scriptPubKey[24] = 0xac; // OP_CHECKSIG
            return scriptPubKey;
        } catch (e) {
            throw new Error(`Failed to decode P2PKH address: ${e.message}`);
        }
    } else {
        throw new Error(`Unsupported address format: ${address}`);
    }
}

function hexToBytes(hex) {
    hex = hex.replace(/^0x/, '');
    const bytes = new Uint8Array(hex.length / 2);
    for (let i = 0; i < bytes.length; i++) {
        bytes[i] = parseInt(hex.substr(i * 2, 2), 16);
    }
    return bytes;
}

function bytesToHex(bytes) {
    return Array.from(bytes).map(b => b.toString(16).padStart(2, '0')).join('');
}

function concatBuffers(...buffers) {
    const totalLength = buffers.reduce((sum, buf) => sum + buf.length, 0);
    const result = new Uint8Array(totalLength);
    let offset = 0;
    for (const buf of buffers) {
        result.set(buf, offset);
        offset += buf.length;
    }
    return result;
}

function countLeadingZeroBits(hash) {
    let count = 0;
    for (let i = hash.length - 1; i >= 0; i--) {
        const byte = hash[i];
        if (byte === 0) {
            count += 8;
        } else {
            let mask = 0x80;
            while ((byte & mask) === 0 && mask > 0) {
                count++;
                mask >>= 1;
            }
            break;
        }
    }
    return count;
}

function bitsToTarget(bits) {
    const exponent = bits >>> 24;
    const mantissa = bits & 0x00ffffff;

    const target = new Uint8Array(32);
    if (exponent <= 3) {
        const val = mantissa >>> (8 * (3 - exponent));
        const view = new DataView(target.buffer);
        for (let i = 0; i < Math.min(exponent, 3); i++) {
            view.setUint8(i, (val >>> (8 * i)) & 0xff);
        }
    } else {
        const offset = exponent - 3;
        target[offset] = mantissa & 0xff;
        target[offset + 1] = (mantissa >>> 8) & 0xff;
        target[offset + 2] = (mantissa >>> 16) & 0xff;
    }

    return target;
}

// ============================================================================
// LEVEL CALCULATION (matches Python hash_utils.calculate_level)
// ============================================================================

function calculateLevel(hashHex) {
    // Must match BASE_ZEROS / SCALE in Python hash_utils.calculate_level.
    const BASE_ZEROS = 11.7;
    const SCALE = 30.0;

    // Normalize to 64 hex chars (display/reversed format with leading zeros)
    const hex = hashHex.toLowerCase().padStart(64, '0');
    const hashInt = BigInt('0x' + hex);

    if (hashInt === 0n) return 1.0 + SCALE * Math.log2(1 + 64 - BASE_ZEROS);

    // Count leading zero hex digits
    let leadingZeroHex = 0;
    for (let i = 0; i < 64; i++) {
        if (hex[i] === '0') leadingZeroHex++;
        else break;
    }

    const sigHexLen = 64 - leadingZeroHex;
    if (sigHexLen === 0) return 1.0 + SCALE * Math.log2(1 + 64 - BASE_ZEROS);

    // frac = 1 - hash_int / 16^sigHexLen
    // Approximate with top 13 significant hex digits (52 bits, safe for double)
    const TOP = 13;
    const topHex = hex.slice(leadingZeroHex, leadingZeroHex + TOP).padEnd(TOP, '0');
    const topInt = Number(BigInt('0x' + topHex)); // safe: max 2^52 - 1 < 2^53
    const mantissa = topInt / Math.pow(16, TOP);
    const frac = 1 - mantissa;

    if (leadingZeroHex < 11) return 0;
    const effective = Math.max(0.0, leadingZeroHex + frac - BASE_ZEROS);
    return 1.0 + SCALE * Math.log2(1 + effective);
}

// ============================================================================
// COINBASE TX WITNESS STRIPPING (for correct TXID computation)
// ============================================================================

function readVarInt(bytes, offset) {
    const first = bytes[offset];
    if (first < 0xfd) return { value: first, size: 1 };
    if (first === 0xfd) return { value: bytes[offset + 1] | (bytes[offset + 2] << 8), size: 3 };
    const view = new DataView(bytes.buffer, bytes.byteOffset);
    return { value: view.getUint32(offset + 1, true), size: 5 };
}

// Strip segwit marker/flag and witness data to get non-witness tx for TXID
function stripWitnessForTxid(txBytes) {
    if (txBytes[4] !== 0x00) return txBytes; // not segwit

    let offset = 6; // skip version(4) + marker(1) + flag(1)

    const inputCountVi = readVarInt(txBytes, offset); offset += inputCountVi.size;
    for (let i = 0; i < inputCountVi.value; i++) {
        offset += 36; // prev hash(32) + index(4)
        const scriptLenVi = readVarInt(txBytes, offset); offset += scriptLenVi.size;
        offset += scriptLenVi.value; // scriptSig
        offset += 4; // sequence
    }

    const outputCountVi = readVarInt(txBytes, offset); offset += outputCountVi.size;
    for (let i = 0; i < outputCountVi.value; i++) {
        offset += 8; // value
        const scriptLenVi = readVarInt(txBytes, offset); offset += scriptLenVi.size;
        offset += scriptLenVi.value; // scriptPubKey
    }

    // offset now points to witness data; everything after is witness + locktime(4)
    return concatBuffers(
        txBytes.slice(0, 4),                    // version
        txBytes.slice(6, offset),               // inputs + outputs (skip marker+flag)
        txBytes.slice(txBytes.length - 4)       // locktime
    );
}

// ============================================================================
// MAIN HASH CALCULATION
// ============================================================================

async function calculateHash() {
    try {
        // Read inputs
        const inputs = {
            version: parseInt(document.getElementById('version').value),
            prevBlockHash: document.getElementById('prevBlockHash').value.replace(/^0x/, ''),
            timestamp: parseInt(document.getElementById('timestamp').value),
            bits: parseInt(document.getElementById('bits').value, 16),
            nonce: parseInt(document.getElementById('nonce').value),
            blockHeight: parseInt(document.getElementById('blockHeight').value),
            poolTag: document.getElementById('poolTag').value,
            minerTag: document.getElementById('minerTag').value,
            extranonce: document.getElementById('extranonce').value.replace(/^0x/, ''),
            coinbaseAddress: document.getElementById('coinbaseAddress').value,
            coinbaseValue: parseInt(document.getElementById('coinbaseValue').value),
            sequence: parseInt(document.getElementById('sequence').value),
            locktime: parseInt(document.getElementById('locktime').value),
            witnessCommitment: document.getElementById('witnessCommitment').value.replace(/^0x/, ''),
            merklePath: document.getElementById('merklePath').value.split('\n').filter(s => s.trim()).map(s => s.trim().replace(/^0x/, ''))
        };

        let output = '<div class="validator-output">';

        // STEP 1: Build Coinbase Transaction from form fields
        output += '<h3>STEP 1: Build Coinbase Transaction</h3>';

        // ScriptSig: BIP34 height + OP_0 + [tagLen] + "/pool/miner/" + [extranonceLen] + extranonce
        const heightBytes = encodeBlockHeight(inputs.blockHeight);
        const tag = `/${inputs.poolTag}/${inputs.minerTag}/`;
        const tagBytes = new TextEncoder().encode(tag);
        const extranonceBytes = hexToBytes(inputs.extranonce);

        const scriptSig = concatBuffers(
            heightBytes,
            new Uint8Array([0x00]),                    // OP_0 from coinbase_prefix
            new Uint8Array([tagBytes.length]),          // push tag
            tagBytes,
            new Uint8Array([extranonceBytes.length]),   // push extranonce
            extranonceBytes
        );
        output += `<div class="output-item"><span class="output-label">ScriptSig:</span> <span class="output-value hash-display">${bytesToHex(scriptSig)}</span></div>`;
        output += `<div class="output-item"><span class="output-label">ScriptSig length:</span> ${scriptSig.length} bytes</div>`;

        // Output 1: coinbase payout
        const scriptPubKey = addressToScriptPubKey(inputs.coinbaseAddress);
        const valueBuf = new Uint8Array(8);
        new DataView(valueBuf.buffer).setBigUint64(0, BigInt(inputs.coinbaseValue), true);

        // Output 2: OP_RETURN witness commitment
        const magic = hexToBytes('aa21a9ed');
        const commitment = hexToBytes(inputs.witnessCommitment);
        const opReturnData = concatBuffers(magic, commitment);
        const opReturnScript = concatBuffers(
            new Uint8Array([0x6a]),
            new Uint8Array([opReturnData.length]),
            opReturnData
        );

        // Full segwit coinbase TX
        const coinbaseTxBytes = concatBuffers(
            uint32LE(2),                                        // version = 2 (coinbase tx)
            new Uint8Array([0x00, 0x01]),                       // segwit marker + flag
            new Uint8Array([0x01]),                             // input count
            new Uint8Array(32),                                 // prev hash (all zeros)
            new Uint8Array([0xff, 0xff, 0xff, 0xff]),           // prev index
            encodeVarInt(scriptSig.length),                     // scriptSig length
            scriptSig,                                          // scriptSig
            uint32LE(inputs.sequence),                          // sequence
            new Uint8Array([0x02]),                             // output count
            valueBuf,                                           // output 1 value
            encodeVarInt(scriptPubKey.length),                  // output 1 script len
            scriptPubKey,                                       // output 1 script
            new Uint8Array(8),                                  // output 2 value (0)
            encodeVarInt(opReturnScript.length),                // output 2 script len
            opReturnScript,                                     // output 2 script
            new Uint8Array([0x01, 0x20]),                       // witness: 1 item, 32 bytes
            new Uint8Array(32),                                 // witness: 32 zero bytes
            uint32LE(inputs.locktime)                           // locktime
        );
        output += `<div class="output-item"><span class="output-label">Coinbase TX:</span> <span class="output-value hash-display">${bytesToHex(coinbaseTxBytes)}</span></div>`;
        output += `<div class="output-item"><span class="output-label">Size:</span> ${coinbaseTxBytes.length} bytes</div>`;

        // STEP 2: Calculate Coinbase TXID
        output += '<h3>STEP 2: Calculate Coinbase TXID</h3>';

        const nonWitnessTx = stripWitnessForTxid(coinbaseTxBytes);
        output += `<div class="output-item"><span class="output-label">Non-witness TX:</span> <span class="output-value hash-display">${bytesToHex(nonWitnessTx)}</span></div>`;

        const coinbaseTxid = await doubleSha256(nonWitnessTx);
        output += `<div class="output-item"><span class="output-label">TXID (display):</span> <span class="output-value hash-display">${bytesToHex(reverseBuffer(coinbaseTxid))}</span></div>`;

        // STEP 3: Calculate Merkle Root
        output += '<h3>STEP 3: Calculate Merkle Root</h3>';

        let merkleRoot = coinbaseTxid;

        if (inputs.merklePath.length === 0) {
            output += '<div class="output-item">Merkle path is empty - coinbase TXID is the merkle root</div>';
        } else {
            output += `<div class="output-item">Combining with ${inputs.merklePath.length} sibling hashes:</div>`;

            for (let i = 0; i < inputs.merklePath.length; i++) {
                const siblingHash = hexToBytes(inputs.merklePath[i]);
                const combined = concatBuffers(merkleRoot, siblingHash);
                merkleRoot = await doubleSha256(combined);

                output += `<div class="output-item">Step ${i + 1}: ${bytesToHex(merkleRoot).substring(0, 16)}...</div>`;
            }
        }

        output += `<div class="output-item"><span class="output-label">Merkle Root (display):</span> <span class="output-value hash-display">${bytesToHex(reverseBuffer(merkleRoot))}</span></div>`;

        // STEP 4: Build Block Header
        output += '<h3>STEP 4: Build Block Header (80 bytes)</h3>';

        const headerParts = [];
        headerParts.push(uint32LE(inputs.version));

        const prevHashBuf = hexToBytes(inputs.prevBlockHash);
        headerParts.push(reverseBuffer(prevHashBuf));

        headerParts.push(merkleRoot);
        headerParts.push(uint32LE(inputs.timestamp));
        headerParts.push(uint32LE(inputs.bits));
        headerParts.push(uint32LE(inputs.nonce));

        const blockHeader = concatBuffers(...headerParts);
        output += `<div class="output-item"><span class="output-label">Block Header:</span> <span class="output-value hash-display">${bytesToHex(blockHeader)}</span></div>`;

        // STEP 5: Calculate Block Hash
        output += '<h3>STEP 5: Calculate Block Hash</h3>';

        const blockHash = await doubleSha256(blockHeader);
        const blockHashDisplay = bytesToHex(reverseBuffer(blockHash));
        output += `<div class="output-item"><span class="output-label">Block Hash:</span> <span class="output-value hash-display">${blockHashDisplay}</span></div>`;

        // STEP 6: Verify Difficulty
        output += '<h3>STEP 6: Verify Difficulty</h3>';

        const leadingZeros = countLeadingZeroBits(blockHash);
        const target = bitsToTarget(inputs.bits);
        const requiredZeros = countLeadingZeroBits(target);

        output += `<div class="output-item"><span class="output-label">Leading zero bits:</span> ${leadingZeros}</div>`;
        output += `<div class="output-item"><span class="output-label">Required zero bits:</span> ${requiredZeros}</div>`;

        const hashBigInt = BigInt('0x' + bytesToHex(blockHash));
        const targetBigInt = BigInt('0x' + bytesToHex(target));
        const isValid = hashBigInt <= targetBigInt;

        output += `<div class="output-item"><span class="output-label">Hash meets target:</span> <span class="output-${isValid ? 'success' : 'error'}">${isValid ? '✓ YES' : '✗ NO'}</span></div>`;

        output += '</div>';

        // Summary with comparison to expected hash
        const hashMatches = window.expectedHash && blockHashDisplay === window.expectedHash;
        const summary = `
            <div class="validator-summary ${hashMatches && isValid ? '' : 'invalid'}">
                <h3>${hashMatches && isValid ? '✓ VALID SHARE' : '⚠ VALIDATION RESULT'}</h3>
                <div class="summary-item">
                    <span class="summary-label">Calculated Hash:</span>
                    <span class="summary-value hash-display">${blockHashDisplay}</span>
                </div>
                ${window.expectedHash ? `
                <div class="summary-item">
                    <span class="summary-label">Expected Hash:</span>
                    <span class="summary-value hash-display">${window.expectedHash}</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">Hash Match:</span>
                    <span class="summary-value ${hashMatches ? 'text-success' : 'text-error'}">${hashMatches ? '✓ Match' : '✗ Mismatch'}</span>
                </div>
                ` : ''}
                <div class="summary-item">
                    <span class="summary-label">Leading Zeros:</span>
                    <span class="summary-value">${leadingZeros} bits</span>
                </div>
                <div class="summary-item">
                    <span class="summary-label">Target Valid:</span>
                    <span class="summary-value ${isValid ? 'text-success' : 'text-error'}">${isValid ? '✓ Yes' : '✗ No'}</span>
                </div>
            </div>
        `;

        document.getElementById('results').innerHTML = summary + output;

        // Update floating panel with results
        const calculatedLevel = calculateLevel(blockHashDisplay);
        updateFloatingPanel(calculatedLevel, blockHashDisplay, hashMatches && isValid);

    } catch (error) {
        document.getElementById('results').innerHTML = `
            <div class="validator-summary invalid">
                <h3>❌ Error</h3>
                <p>${error.message}</p>
            </div>
        `;
        console.error('Hash calculation error:', error);

        // Update floating panel with error state
        updateFloatingPanel(null, error.message, false);
    }
}
