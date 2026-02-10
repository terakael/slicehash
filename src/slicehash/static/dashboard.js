// Dashboard JavaScript - Mobile-first share cards with infinite scroll

// State management
let isLoading = false;
let hasMore = true;
let currentOffset = 0;
const LIMIT = 20;

// SSE state
let eventSource = null;
let lastEventId = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_DELAY = 30000;
const INITIAL_RECONNECT_DELAY = 1000;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
    initSSE();
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
        const url = `/api/users/me/shares?limit=${LIMIT}&offset=${currentOffset}`;
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

        // Format timestamp
        const timestamp = formatTimestamp(share.submitted_at);

        // Get level styling
        const { color, shape, borderStyle } = getLevelStyle(share.level);

        // Build badges
        let badges = '';
        if (share.billable) {
            badges += '<span class="share-badge billable-badge">Billable</span>';
        }

        // Add priority badge if shares consumed > 1
        if (share.shares_consumed > 1) {
            badges += `<span class="share-badge priority-badge">Priority ${share.shares_consumed}x</span>`;
        }

        const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

        card.innerHTML = `
            <div class="share-card-header">
                <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
                <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                    ${share.level}
                </div>
            </div>
            ${badges ? `<div class="share-card-footer">${badges}</div>` : ''}
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

// SSE Functions

function initSSE() {
    if (eventSource) {
        eventSource.close();
    }

    eventSource = new EventSource('/api/users/me/shares/stream');

    eventSource.addEventListener('connected', (event) => {
        console.log('SSE connected');
        reconnectAttempts = 0;
    });

    eventSource.addEventListener('share', (event) => {
        const share = JSON.parse(event.data);
        lastEventId = event.lastEventId;
        handleNewShare(share);
    });

    eventSource.addEventListener('heartbeat', (event) => {
        console.debug('SSE heartbeat');
    });

    eventSource.onerror = (error) => {
        console.error('SSE error:', error);
        eventSource.close();
        handleSSEDisconnect();
    };
}

async function handleSSEDisconnect() {
    console.log('SSE disconnected, attempting recovery...');

    if (lastEventId) {
        try {
            await recoverMissedShares(lastEventId);
        } catch (error) {
            console.error('Failed to recover:', error);
        }
    }

    reconnectAttempts++;
    const delay = Math.min(
        INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts - 1),
        MAX_RECONNECT_DELAY
    );

    console.log(`Reconnecting in ${delay}ms (attempt ${reconnectAttempts})...`);
    setTimeout(initSSE, delay);
}

async function recoverMissedShares(sinceId) {
    const response = await fetch(`/api/users/me/shares/recovery?since_id=${sinceId}&limit=200`);
    if (!response.ok) throw new Error('Recovery failed');

    const data = await response.json();
    console.log(`Recovered ${data.shares.length} shares`);

    for (const share of data.shares) {
        handleNewShare(share);
        lastEventId = share.share_id;
    }

    if (data.has_more) {
        await recoverMissedShares(lastEventId);
    }
}

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

    // Format timestamp
    const timestamp = formatTimestamp(share.submitted_at);

    // Get level styling
    const { color, shape, borderStyle } = getLevelStyle(share.level);

    // Build badges
    let badges = '';
    if (share.billable) {
        badges += '<span class="share-badge billable-badge">Billable</span>';
    }

    // Add priority badge if shares consumed > 1
    if (share.shares_consumed > 1) {
        badges += `<span class="share-badge priority-badge">Priority ${share.shares_consumed}x</span>`;
    }

    const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

    card.innerHTML = `
        <div class="share-card-header">
            <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
            <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                ${share.level}
            </div>
        </div>
        ${badges ? `<div class="share-card-footer">${badges}</div>` : ''}
    `;

    // Prepend to the beginning with animation
    card.classList.add('share-card-new');
    container.insertBefore(card, container.firstChild);
    observeCard(card);

    // Remove animation class after animation completes
    setTimeout(() => {
        card.classList.remove('share-card-new');
    }, 400);

    currentOffset++;
    loadUserData(); // Update shares remaining counter
}
