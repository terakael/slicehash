// Hash Validator JavaScript - Bitcoin mining share verification

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadShareData();
    setupEventListeners();
});

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
        document.getElementById('witnessCommitment').value = data.witness_commitment || '';
        document.getElementById('merklePath').value = data.merkle_path.join('\n');

        // Store expected hash for comparison
        window.expectedHash = data.share_hash;
        window.expectedLevel = data.level;

        // Hide loading state and show form
        document.getElementById('loading-state').style.display = 'none';
        document.getElementById('validator-form').style.display = 'block';

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

    // Optional: Auto-recalculate on input change
    document.querySelectorAll('.validator-input').forEach(input => {
        input.addEventListener('change', () => {
            // Clear results when inputs change
            document.getElementById('results').innerHTML = '';
        });
    });
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

function addressToScriptPubKey(address) {
    if (address.startsWith('bc1q')) {
        const decoded = bech32.bech32.decode(address);
        const witness = new Uint8Array(bech32.bech32.fromWords(decoded.words.slice(1)));

        const scriptPubKey = new Uint8Array(22);
        scriptPubKey[0] = 0x00; // OP_0
        scriptPubKey[1] = 0x14; // 20 bytes
        scriptPubKey.set(witness, 2);
        return scriptPubKey;
    } else {
        throw new Error('Only bc1q (P2WPKH) addresses supported');
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
// MAIN HASH CALCULATION
// ============================================================================

async function calculateHash() {
    try {
        // Read inputs
        const inputs = {
            version: parseInt(document.getElementById('version').value),
            prevBlockHash: document.getElementById('prevBlockHash').value.replace(/^0x/, ''),
            timestamp: parseInt(document.getElementById('timestamp').value),
            bits: parseInt(document.getElementById('bits').value),
            nonce: parseInt(document.getElementById('nonce').value),
            blockHeight: parseInt(document.getElementById('blockHeight').value),
            poolTag: document.getElementById('poolTag').value,
            minerTag: document.getElementById('minerTag').value,
            extranonce: document.getElementById('extranonce').value.replace(/^0x/, ''),
            coinbaseAddress: document.getElementById('coinbaseAddress').value,
            coinbaseValue: parseInt(document.getElementById('coinbaseValue').value),
            witnessCommitment: document.getElementById('witnessCommitment').value.replace(/^0x/, ''),
            merklePath: document.getElementById('merklePath').value.split('\n').filter(s => s.trim()).map(s => s.trim().replace(/^0x/, ''))
        };

        let output = '<div class="validator-output">';

        // STEP 1: Build Coinbase Transaction
        output += '<h3>STEP 1: Build Coinbase Transaction</h3>';

        const coinbaseParts = [];
        coinbaseParts.push(uint32LE(2)); // Version 2
        coinbaseParts.push(new Uint8Array([0x00, 0x01])); // SegWit marker and flag
        coinbaseParts.push(encodeVarInt(1)); // Input count
        coinbaseParts.push(new Uint8Array(32).fill(0)); // Null hash
        coinbaseParts.push(new Uint8Array([0xff, 0xff, 0xff, 0xff])); // Index 0xffffffff

        // ScriptSig
        const scriptSigParts = [];
        scriptSigParts.push(encodeBlockHeight(inputs.blockHeight));

        const tagString = `/${inputs.poolTag}/${inputs.minerTag}//`;
        const tagBytes = new TextEncoder().encode(tagString);
        scriptSigParts.push(new Uint8Array([tagBytes.length]));
        scriptSigParts.push(tagBytes);

        const extranonceBytes = hexToBytes(inputs.extranonce);
        scriptSigParts.push(new Uint8Array([extranonceBytes.length]));
        scriptSigParts.push(extranonceBytes);

        const scriptSig = concatBuffers(...scriptSigParts);
        coinbaseParts.push(encodeVarInt(scriptSig.length));
        coinbaseParts.push(scriptSig);
        coinbaseParts.push(new Uint8Array([0xff, 0xff, 0xff, 0xff])); // Sequence

        // Outputs
        const hasWitness = inputs.witnessCommitment && inputs.witnessCommitment.length > 0;
        coinbaseParts.push(encodeVarInt(hasWitness ? 2 : 1));

        const valueBuf = new Uint8Array(8);
        new DataView(valueBuf.buffer).setBigUint64(0, BigInt(inputs.coinbaseValue), true);
        coinbaseParts.push(valueBuf);

        const scriptPubKey = addressToScriptPubKey(inputs.coinbaseAddress);
        coinbaseParts.push(encodeVarInt(scriptPubKey.length));
        coinbaseParts.push(scriptPubKey);

        if (hasWitness) {
            const witnessValue = new Uint8Array(8).fill(0);
            coinbaseParts.push(witnessValue);

            const commitmentBytes = hexToBytes(inputs.witnessCommitment);
            const witnessScript = concatBuffers(
                new Uint8Array([0x6a]), // OP_RETURN
                new Uint8Array([0x24]), // 36 bytes
                new Uint8Array([0xaa, 0x21, 0xa9, 0xed]),
                commitmentBytes
            );
            coinbaseParts.push(encodeVarInt(witnessScript.length));
            coinbaseParts.push(witnessScript);
        }

        coinbaseParts.push(new Uint8Array([0x00])); // Witness data
        coinbaseParts.push(uint32LE(0)); // Locktime

        const coinbaseTx = concatBuffers(...coinbaseParts);
        output += `<div class="output-item"><span class="output-label">Coinbase TX:</span> <span class="output-value hash-display">${bytesToHex(coinbaseTx)}</span></div>`;
        output += `<div class="output-item"><span class="output-label">Size:</span> ${coinbaseTx.length} bytes</div>`;

        // STEP 2: Calculate Coinbase TXID
        output += '<h3>STEP 2: Calculate Coinbase TXID</h3>';

        const coinbaseTxForTxid = concatBuffers(
            coinbaseParts[0],
            ...coinbaseParts.slice(3, -2),
            coinbaseParts[coinbaseParts.length - 1]
        );

        const coinbaseTxid = await doubleSha256(coinbaseTxForTxid);
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

    } catch (error) {
        document.getElementById('results').innerHTML = `
            <div class="validator-summary invalid">
                <h3>❌ Error</h3>
                <p>${error.message}</p>
            </div>
        `;
        console.error('Hash calculation error:', error);
    }
}
