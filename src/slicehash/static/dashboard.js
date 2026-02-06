// Dashboard JavaScript - Share list with infinite scroll

// State management
let isLoading = false;
let hasMore = true;
let currentOffset = 0;
const LIMIT = 50;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
});

// Fetch and display user data
async function loadUserData() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) throw new Error('Failed to fetch user data');

        const data = await response.json();

        // Update header stats
        document.getElementById('shares-remaining').textContent = data.shares_remaining;

        // Fetch network difficulty from traffic status
        await loadNetworkDifficulty();

    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
    }
}

// Fetch network difficulty
async function loadNetworkDifficulty() {
    try {
        const response = await fetch('/api/traffic/status');
        if (!response.ok) throw new Error('Failed to fetch traffic status');

        const data = await response.json();
        document.getElementById('network-difficulty').textContent = data.traffic_level;

    } catch (error) {
        console.error('Error loading network difficulty:', error);
        document.getElementById('network-difficulty').textContent = 'Error';
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
            renderShares(data.shares, append);

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

// Render shares in table
function renderShares(shares, append) {
    const tbody = document.getElementById('share-list');

    if (!append) {
        tbody.innerHTML = '';
    }

    shares.forEach(share => {
        const row = document.createElement('tr');

        // Format timestamp
        const timestamp = formatTimestamp(share.submitted_at);

        // Calculate log10 difficulty
        const difficultyLog = Math.log10(share.share_difficulty).toFixed(2);

        // Format billable badge
        const billableBadge = share.billable
            ? '<span class="billable-badge yes">YES</span>'
            : '<span class="billable-badge no">NO</span>';

        row.innerHTML = `
            <td>${timestamp}</td>
            <td>${difficultyLog}</td>
            <td>${billableBadge}</td>
            <td>${share.shares_consumed}</td>
        `;

        tbody.appendChild(row);
    });
}

// Format timestamp as relative time or ISO
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`;

    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`;

    // Fall back to ISO format for older dates
    return date.toLocaleString();
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
    const table = document.querySelector('.share-table');

    if (show) {
        emptyState.style.display = 'block';
        table.style.display = 'none';
    } else {
        emptyState.style.display = 'none';
        table.style.display = 'table';
    }
}

// Show error message
function showError(message) {
    console.error(message);
    // Could add a toast notification here in the future
}
