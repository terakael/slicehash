// Highscores JavaScript - Top 5 shares by level

// State management
let currentPeriod = '24h';
let isLoading = false;

// Cache management
const highscoresCache = {
    '24h': { data: null, timestamp: 0 },
    'all-time': { data: null, timestamp: 0 }
};
const CACHE_DURATION = 60000; // 1 minute in milliseconds

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

        // Update shares remaining display
        document.getElementById('shares-remaining').textContent = data.shares_remaining;

    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
    }
}

// Load highscores for given period
async function loadHighscores(period, forceRefresh = false) {
    if (isLoading) return;

    // Check cache first (unless forced refresh)
    if (!forceRefresh) {
        const cached = highscoresCache[period];
        const now = Date.now();
        if (cached.data && (now - cached.timestamp < CACHE_DURATION)) {
            console.log(`Using cached highscores for ${period}`);
            if (cached.data.shares.length === 0) {
                showEmptyState(true, period);
            } else {
                showEmptyState(false, period);
                renderShareCards(cached.data.shares);
            }
            return;
        }
    }

    isLoading = true;
    showLoading(true);

    try {
        const endpoint = period === '24h' ? '/api/highscores/24h' : '/api/highscores/all-time';
        const response = await fetch(endpoint);
        if (!response.ok) throw new Error('Failed to fetch highscores');

        const data = await response.json();

        // Update cache
        highscoresCache[period] = {
            data: data,
            timestamp: Date.now()
        };

        if (data.shares.length === 0) {
            showEmptyState(true, period);
        } else {
            showEmptyState(false, period);
            renderShareCards(data.shares);
        }

    } catch (error) {
        console.error('Error loading highscores:', error);
        showError('Failed to load highscores');
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Switch between periods
function switchPeriod(period) {
    if (period === currentPeriod || isLoading) return;

    currentPeriod = period;

    // Update button active states
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        if (btn.dataset.period === period) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });

    // Load data for new period
    loadHighscores(period);
}

// Setup toggle button event listeners
function setupToggleButtons() {
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchPeriod(btn.dataset.period);
        });
    });
}

// Render shares as cards
function renderShareCards(shares) {
    const container = document.getElementById('highscore-cards-container');
    container.innerHTML = '';

    shares.forEach((share, index) => {
        const card = document.createElement('div');
        card.className = `share-card highscore-card${share.is_block ? ' block' : ''}`;

        // Format timestamp with username
        const { timeStr, username } = formatTimestampWithUsername(share.submitted_at, share.username);

        // Get level styling
        const { color, shape, borderStyle } = getLevelStyle(share.level);

        const borderAttr = borderStyle ? `border: ${borderStyle};` : '';

        card.innerHTML = `
            <div class="share-card-header">
                <div class="share-timestamp-wrapper" data-timestamp="${share.submitted_at}" data-username="${share.username}">
                    <span class="share-timestamp">${timeStr}</span>
                    <span class="share-username">${username}</span>
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

// Show/hide loading indicator
function showLoading(show) {
    const indicator = document.getElementById('loading-indicator');
    indicator.style.display = show ? 'block' : 'none';
}

// Show/hide empty state
function showEmptyState(show, period) {
    const emptyState = document.getElementById('empty-state');
    const container = document.getElementById('highscore-cards-container');

    if (show) {
        // Update message based on period
        const message = period === '24h' ? 'No shares in the last 24 hours' : 'No shares recorded';
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

// Handle page refocus - check for new highscores if any shares arrived
async function handlePageRefocus(missedSharesCount) {
    if (missedSharesCount > 0) {
        console.log(`Checking for new highscores after ${missedSharesCount} shares`);
        // Force refresh to get latest highscores
        await loadHighscores(currentPeriod, true);
    }
}
