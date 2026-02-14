// Dashboard JavaScript - Mobile-first share cards with infinite scroll

// State management
let isLoading = false;
let hasMore = true;
let currentOffset = 0;
let currentMode = localStorage.getItem('dashboardMode') || 'recent';
const LIMIT = 20;
let hasLoadedAllShares = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Restore saved mode and set active button
    restoreSavedMode();

    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
    setupToggleButtons();
    initSharedSSE(handleNewShare);
    startTimestampRefresh();
});

// Restore saved mode from localStorage
function restoreSavedMode() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        if (btn.dataset.mode === currentMode) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
}

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
        const url = `/api/users/me/shares/load?mode=${currentMode}&limit=${LIMIT}&offset=${currentOffset}`;
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
            hasLoadedAllShares = !data.has_more;
        }

    } catch (error) {
        console.error('Error loading shares:', error);
        showError('Failed to load shares');
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Refresh dashboard - reset state and reload (called by shared.js on refocus)
window.refreshDashboard = async function() {
    console.log('Refreshing dashboard - resetting state and reloading shares');
    currentOffset = 0;
    hasMore = true;
    hasLoadedAllShares = false;

    // Clear existing shares
    const container = document.getElementById('share-cards-container');
    if (container) {
        container.innerHTML = '';
    }

    await loadShares(false);
};

// Switch between view modes
function switchMode(mode) {
    if (mode === currentMode || isLoading) return;

    currentMode = mode;

    // Save preference to localStorage
    localStorage.setItem('dashboardMode', mode);

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
    hasLoadedAllShares = false;
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

        // Format timestamp
        const timestamp = formatTimestamp(share.submitted_at);

        // Get level styling
        const { color, shape, borderStyle } = getLevelStyle(share.level);
        const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

        // Display tag if available (use immutable tag from share)
        const tagDisplay = share.tag ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>` : '';

        card.innerHTML = `
            <a href="/hash-validator/${share.share_id}" class="share-validator-link" title="Validate this hash">🔍</a>
            <div class="share-card-header">
                <div class="share-header-top">
                    <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
                    ${tagDisplay}
                </div>
                <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                    ${Math.floor(share.level)}
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
        // Update message based on mode
        let message = 'No shares yet';
        if (currentMode === 'best-24h') {
            message = 'No shares in the last 24 hours';
        }
        emptyState.querySelector('p').textContent = message;
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
    console.log(`handleNewShare called for share ${share.share_id}, level=${share.level}, mode=${currentMode}`);

    const container = document.getElementById('share-cards-container');

    // Duplicate detection using share_id
    const existingCards = container.querySelectorAll('.share-card');
    for (const card of existingCards) {
        const cardShareId = card.dataset.shareId;
        if (cardShareId === String(share.share_id)) {
            console.log(`Duplicate share ${share.share_id} detected, skipping`);
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

    // Format timestamp
    const timestamp = formatTimestamp(share.submitted_at);

    // Get level styling
    const { color, shape, borderStyle } = getLevelStyle(share.level);
    const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

    // Display tag if available (use immutable tag from share)
    const tagDisplay = share.tag ? `<span class="share-user-tag">${truncateUsername(share.tag)}</span>` : '';

    card.innerHTML = `
        <a href="/hash-validator/${share.share_id}" class="share-validator-link" title="Validate this hash">🔍</a>
        <div class="share-card-header">
            <div class="share-header-top">
                <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
                ${tagDisplay}
            </div>
            <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                ${Math.floor(share.level)}
            </div>
        </div>
        <div class="share-card-footer">
            <span class="share-hash">${share.share_hash}</span>
        </div>
    `;

    // Determine insertion position based on mode
    let insertBefore = null;
    let insertPosition = 0;

    if (currentMode === 'recent') {
        // Recent mode: always prepend to top (newest first)
        insertBefore = container.firstChild;
    } else {
        // Best modes: insert by level ranking (all your shares, ranked)
        // Find first card with lower level (or same level but older timestamp)
        for (const existingCard of existingCards) {
            const existingLevel = parseFloat(existingCard.dataset.level);
            const existingTimestamp = existingCard.dataset.timestamp;

            if (share.level > existingLevel) {
                insertBefore = existingCard;
                break;
            } else if (share.level === existingLevel && share.submitted_at > existingTimestamp) {
                insertBefore = existingCard;
                break;
            }
            insertPosition++;
        }
    }

    // Discard if would insert beyond loaded shares (unless we have complete dataset)
    if (!hasLoadedAllShares && insertPosition >= existingCards.length && currentMode !== 'recent') {
        console.log(`Discarding share ${share.share_id} - ranks below loaded set (hasLoadedAllShares=${hasLoadedAllShares}, insertPosition=${insertPosition}, existingCards.length=${existingCards.length})`);
        lastEventId = share.share_id;  // Still update for catch-up tracking
        return;
    }

    console.log(`Inserting share ${share.share_id} at position ${insertPosition} (mode=${currentMode}, hasLoadedAllShares=${hasLoadedAllShares})`);

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
