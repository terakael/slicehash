// Highscores JavaScript - Top 5 shares by level

// State management
let currentPeriod = '24h';
let isLoading = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadHighscores(currentPeriod);
    setupToggleButtons();
    initSharedSSE(null, handlePageRefocus);
    startTimestampRefresh();
});

// Fetch and display user data
async function loadUserData() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) throw new Error('Failed to fetch user data');
        const data = await response.json();
        document.getElementById('shares-remaining').textContent = data.shares_remaining;
    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
    }
}

// Load highscores for given period
async function loadHighscores(period) {
    if (isLoading) return;

    isLoading = true;
    showLoading(true);

    try {
        const endpoint = period === '24h' ? '/api/highscores/24h' : '/api/highscores/all-time';
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Failed to fetch highscores');
        const data = await response.json();

        if (data.shares.length === 0) {
            showEmptyState(true, period);
        } else {
            showEmptyState(false, period);
            renderShareCards(data.shares);
        }
    } catch (error) {
        console.error('Error loading highscores:', error);
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Switch between periods
function switchPeriod(period) {
    if (period === currentPeriod || isLoading) return;
    currentPeriod = period;
    document.querySelectorAll('.toggle-btn[data-period]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.period === period);
    });
    loadHighscores(period);
}

// Setup toggle button event listeners
function setupToggleButtons() {
    document.querySelectorAll('.toggle-btn[data-period]').forEach(btn => {
        btn.addEventListener('click', () => switchPeriod(btn.dataset.period));
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function truncateHash(hash) {
    if (!hash) return '';
    return '...' + hash.slice(-10);
}

function darkenHex(hex, factor) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return '#' + [r, g, b].map(c => Math.round(c * factor).toString(16).padStart(2, '0')).join('');
}

function isLightColor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 128;
}

function medalClass(rank) {
    if (rank === 1) return 'medal-gold';
    if (rank === 2) return 'medal-silver';
    if (rank === 3) return 'medal-bronze';
    return '';
}

// Build a .hs-row element for a highscore entry
function renderHsRow(share, { rank } = {}) {
    const { color, shape, borderStyle } = getLevelStyle(share.level);
    const borderColor = borderStyle
        ? borderStyle.split(' ').pop()
        : darkenHex(color, 0.7);
    const textColor = '#fff';

    const row = document.createElement('div');
    row.className = 'hs-row';
    row.dataset.level = share.level;

    const mc = rank !== undefined ? medalClass(rank) : '';
    const rankHtml = rank !== undefined
        ? `<span class="hs-rank${mc ? ' ' + mc : ''}">#${rank}</span>`
        : '';
    const timestamp = formatTimestamp(share.submitted_at);
    const userDisplay = share.tag
        ? truncateUsername(share.tag)
        : truncateUsername(share.username || share.address || 'Unknown');
    const hashDisplay = truncateHash(share.share_hash);
    const badgeInner = shape === 'diamond'
        ? `<span>${Math.floor(share.level)}</span>`
        : `${Math.floor(share.level)}`;

    row.innerHTML = `
        ${rankHtml}
        <div class="hs-info">
            <div class="hs-top-line">
                <span class="hs-user">${userDisplay}</span>
                <span class="hs-time share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
            </div>
            <div class="hs-hash">${hashDisplay}</div>
        </div>
        <div class="hs-badge shape-${shape}${mc ? ' ' + mc : ''}" style="background-color: ${color}; border-color: ${borderColor}; color: ${textColor};">${badgeInner}</div>
    `;

    return row;
}

// Render shares as hs-rows (ranked)
function renderShareCards(shares) {
    const container = document.getElementById('highscore-cards-container');
    container.innerHTML = '';
    shares.forEach((share, index) => {
        const row = renderHsRow(share, { rank: index + 1 });
        container.appendChild(row);
        observeCard(row);
    });
}

// Show/hide loading indicator
function showLoading(show) {
    const indicator = document.getElementById('loading-indicator');
    if (indicator) indicator.style.display = show ? 'block' : 'none';
}

// Show/hide empty state
function showEmptyState(show, period) {
    const emptyState = document.getElementById('empty-state');
    const container = document.getElementById('highscore-cards-container');

    if (show) {
        const message = period === '24h' ? 'No shares in the last 24 hours' : 'No shares recorded';
        emptyState.querySelector('p').textContent = message;
        emptyState.style.display = 'block';
        container.style.display = 'none';
    } else {
        emptyState.style.display = 'none';
        container.style.display = 'flex';
    }
}

// Handle page refocus - reload if new shares arrived while away
async function handlePageRefocus(missedSharesCount) {
    if (missedSharesCount > 0) {
        console.log(`Checking for new highscores after ${missedSharesCount} shares`);
        await loadHighscores(currentPeriod);
    }
}
