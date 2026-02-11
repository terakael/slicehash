// Dashboard JavaScript - Mobile-first share cards with infinite scroll

// State management
let isLoading = false;
let hasMore = true;
let currentOffset = 0;
let currentMode = 'recent';
const LIMIT = 20;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
    setupToggleButtons();
    initSharedSSE(handleNewShare, handlePageRefocus);
    startTimestampRefresh();
});

// Fetch and display user data
async function loadUserData() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) throw new Error('Failed to fetch user data');

        const data = await response.json();

        // Update shares remaining display
        document.getElementById('shares-remaining').textContent = data.shares_remaining;

        // Fetch network difficulty from traffic status
        await loadNetworkDifficulty();

    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
    }
}

// Fetch network difficulty (active user count)
async function loadNetworkDifficulty() {
    try {
        const response = await fetch('/api/traffic/status');
        if (!response.ok) throw new Error('Failed to fetch traffic status');

        const data = await response.json();
        document.getElementById('network-difficulty-value').textContent = data.active_user_count;

    } catch (error) {
        console.error('Error loading network difficulty:', error);
        document.getElementById('network-difficulty-value').textContent = '?';
    }
}

// Load shares with pagination
async function loadShares(append = false) {
    if (isLoading || (!append && currentOffset > 0)) return;
    if (append && !hasMore) return;

    isLoading = true;
    showLoading(true);

    try {
        const url = `/api/shares?mode=${currentMode}&limit=${LIMIT}&offset=${currentOffset}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch shares');

        const data = await response.json();

        if (data.shares.length === 0 && currentOffset === 0) {
            showEmptyState(true);
        } else {
            showEmptyState(false);
            renderShareCards(data.shares, append);

            // Update pagination state
            currentOffset += data.shares.length;
            hasMore = data.has_more;
        }

    } catch (error) {
        console.error('Error loading shares:', error);
        showError('Failed to load shares');
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Switch between view modes
function switchMode(mode) {
    if (mode === currentMode || isLoading) return;

    currentMode = mode;

    // Update button active states
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        if (btn.dataset.mode === mode) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Reset pagination state and reload
    currentOffset = 0;
    hasMore = true;
    loadShares(false);
}

// Setup toggle button event listeners
function setupToggleButtons() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchMode(btn.dataset.mode);
        });
    });
}

// Render shares as cards
function renderShareCards(shares, append) {
    const container = document.getElementById('share-cards-container');

    if (!append) {
        container.innerHTML = '';
    }

    shares.forEach(share => {
        const card = document.createElement('div');
        card.className = `share-card${share.is_block ? ' block' : ''}`;
        card.dataset.shareId = share.share_id;
        card.dataset.level = share.level;
        card.dataset.timestamp = share.submitted_at;

        // Format timestamp with username for global views
        let timestampDisplay, userDisplay;

        if (currentMode === 'recent') {
            // Recent mode: show just timestamp and tag (current user's shares)
            timestampDisplay = formatTimestamp(share.submitted_at);
            userDisplay = share.tag ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>` : '';
        } else {
            // Best modes: show timestamp with username (all users' shares)
            const { timeStr, username } = formatTimestampWithUsername(share.submitted_at, share.username);
            timestampDisplay = timeStr;
            userDisplay = share.tag
                ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>`
                : `<span class="share-username">${username}</span>`;
        }

        // Get level styling
        const { color, shape, borderStyle } = getLevelStyle(share.level);
        const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

        card.innerHTML = `
            <div class="share-card-header">
                <div class="share-header-top">
                    <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestampDisplay}</span>
                    ${userDisplay}
                </div>
                <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                    ${share.level}
                </div>
            </div>
            <div class="share-card-footer">
                <span class="share-hash">${share.share_hash}</span>
            </div>
        `;

        container.appendChild(card);
        observeCard(card);
    });
}

// Setup infinite scroll listener
function setupInfiniteScroll() {
    window.addEventListener('scroll', () => {
        const scrollHeight = document.documentElement.scrollHeight;
        const scrollTop = document.documentElement.scrollTop;
        const clientHeight = document.documentElement.clientHeight;

        // Trigger load when within 200px of bottom
        if (scrollTop + clientHeight >= scrollHeight - 200) {
            if (!isLoading && hasMore) {
                loadShares(true);
            }
        }
    });
}

// Show/hide loading indicator
function showLoading(show) {
    const indicator = document.getElementById('loading-indicator');
    indicator.style.display = show ? 'block' : 'none';
}

// Show/hide empty state
function showEmptyState(show) {
    const emptyState = document.getElementById('empty-state');
    const container = document.getElementById('share-cards-container');

    if (show) {
        emptyState.style.display = 'block';
        container.style.display = 'none';
    } else {
        emptyState.style.display = 'none';
        container.style.display = 'flex';
    }
}

// Show error message
function showError(message) {
    console.error(message);
    // Could add a toast notification here in the future
}

// SSE callback for handling new shares (adds card to dashboard)
function handleNewShare(share) {
    const container = document.getElementById('share-cards-container');

    // Duplicate detection using share_id
    const existingCards = container.querySelectorAll('.share-card');
    for (const card of existingCards) {
        const cardShareId = card.dataset.shareId;
        if (cardShareId === String(share.share_id)) {
            return; // Duplicate, skip
        }
    }

    showEmptyState(false);

    // Create new card element
    const card = document.createElement('div');
    card.className = `share-card${share.is_block ? ' block' : ''}`;
    card.dataset.shareId = share.share_id;
    card.dataset.level = share.level;
    card.dataset.timestamp = share.submitted_at;

    // Format display based on mode
    let timestampDisplay, userDisplay;

    if (currentMode === 'recent') {
        timestampDisplay = formatTimestamp(share.submitted_at);
        userDisplay = share.tag ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>` : '';
    } else {
        // For best modes, we need username info - use what's available from SSE
        timestampDisplay = formatTimestamp(share.submitted_at);
        userDisplay = share.tag
            ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>`
            : `<span class="share-username">${truncateUsername(share.address || 'Unknown')}</span>`;
    }

    // Get level styling
    const { color, shape, borderStyle } = getLevelStyle(share.level);
    const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

    card.innerHTML = `
        <div class="share-card-header">
            <div class="share-header-top">
                <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestampDisplay}</span>
                ${userDisplay}
            </div>
            <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                ${share.level}
            </div>
        </div>
        <div class="share-card-footer">
            <span class="share-hash">${share.share_hash}</span>
        </div>
    `;

    // Determine insertion position based on mode
    let insertBefore = null;

    if (currentMode === 'recent') {
        // Recent mode: always prepend to top (newest first)
        insertBefore = container.firstChild;
    } else {
        // Best modes: insert by level ranking
        // Find first card with lower level (or same level but older timestamp)
        for (const existingCard of existingCards) {
            const existingLevel = parseInt(existingCard.dataset.level);
            const existingTimestamp = existingCard.dataset.timestamp;

            if (share.level > existingLevel) {
                insertBefore = existingCard;
                break;
            } else if (share.level === existingLevel && share.submitted_at > existingTimestamp) {
                insertBefore = existingCard;
                break;
            }
        }
    }

    // Insert with animation
    card.classList.add('share-card-new');
    if (insertBefore) {
        container.insertBefore(card, insertBefore);
    } else {
        container.appendChild(card);
    }
    observeCard(card);

    // Remove animation class after animation completes
    setTimeout(() => {
        card.classList.remove('share-card-new');
    }, 400);

    currentOffset++;
}

// Handle page refocus - reload shares if more than 10 received while away
async function handlePageRefocus(missedSharesCount) {
    if (currentMode === 'recent') {
        // Recent mode: handle missed user shares
        if (missedSharesCount > 10) {
            console.log(`Reloading dashboard with latest shares (${missedSharesCount} missed)`);

            // Reset state
            currentOffset = 0;
            hasMore = true;

            // Reload fresh shares from the top
            await loadShares(false);
        } else if (missedSharesCount > 0) {
            console.log(`Fetching ${missedSharesCount} missed shares`);

            // Fetch the missed shares and prepend them
            try {
                const response = await fetch(`/api/users/me/shares?limit=${missedSharesCount}&offset=0`);
                if (!response.ok) throw new Error('Failed to fetch missed shares');

                const data = await response.json();

                // Prepend shares in reverse order (oldest first) so newest ends up on top
                for (let i = data.shares.length - 1; i >= 0; i--) {
                    handleNewShare(data.shares[i]);
                }
            } catch (error) {
                console.error('Error fetching missed shares:', error);
                // Fall back to full reload
                currentOffset = 0;
                hasMore = true;
                await loadShares(false);
            }
        }
    } else {
        // Best modes: reload if any shares were missed (rankings may have changed)
        if (missedSharesCount > 0) {
            console.log(`Reloading ${currentMode} view after ${missedSharesCount} new shares`);
            currentOffset = 0;
            hasMore = true;
            await loadShares(false);
        }
    }
}
