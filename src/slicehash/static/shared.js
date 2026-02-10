// Shared JavaScript utilities for SliceHash

// Format timestamp as current time in user's timezone and format (with optional username)
function formatTimestamp(timestamp, username = null) {
    const now = new Date();
    const timeStr = now.toLocaleString();

    if (username) {
        const truncatedUsername = truncateUsername(username);
        return `${timeStr} by ${truncatedUsername}`;
    }

    return timeStr;
}

// Truncate username if longer than 20 characters
function truncateUsername(username) {
    if (!username) return 'Unknown';
    if (username.length > 20) {
        return username.substring(0, 17) + '...';
    }
    return username;
}

// Get level styling (color, shape, border)
function getLevelStyle(level) {
    // Color palette cycling every 8 levels
    const colorPalette = [
        '#58a6ff', // Blue
        '#56d364', // Green
        '#f78166', // Orange
        '#d29922', // Gold
        '#bc8cff', // Purple
        '#ff7b72', // Red
        '#79c0ff', // Light Blue
        '#ffa657', // Bright Orange
    ];

    // Shape tiers (every 8 levels)
    const tier = Math.floor((level - 1) / 8);
    const colorIndex = (level - 1) % 8;
    const color = colorPalette[colorIndex];

    let shape, borderStyle = '';

    if (tier === 0) {
        // Levels 1-8: Square
        shape = 'square';
    } else if (tier === 1) {
        // Levels 9-16: Circle
        shape = 'circle';
    } else if (tier === 2) {
        // Levels 17-24: Diamond
        shape = 'diamond';
    } else if (tier === 3) {
        // Levels 25-32: Hexagon
        shape = 'hexagon';
    } else {
        // Levels 33+: Hexagon with special borders
        shape = 'hexagon';
        const borderColors = ['#f85149', '#ffa657', '#e3b341', '#ff7b72'];
        const borderColor = borderColors[tier % borderColors.length];
        borderStyle = `3px solid ${borderColor}`;
    }

    return { color, shape, borderStyle };
}

// Timestamp refresh functionality
let timestampObserver = null;

// Refresh all visible timestamps
function refreshTimestamps() {
    const timestampElements = document.querySelectorAll('.share-timestamp[data-timestamp]');
    timestampElements.forEach(element => {
        refreshTimestamp(element);
    });
}

// Refresh a single timestamp element
function refreshTimestamp(element) {
    const username = element.dataset.username || null;
    const newDisplay = formatTimestamp(null, username);
    element.textContent = newDisplay;
}

// Setup Intersection Observer to refresh timestamps when cards come into view
function setupTimestampObserver() {
    timestampObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const timestampElement = entry.target.querySelector('.share-timestamp[data-timestamp]');
                if (timestampElement) {
                    refreshTimestamp(timestampElement);
                }
            }
        });
    }, {
        rootMargin: '50px'
    });
}

// Observe a card for timestamp refresh
function observeCard(card) {
    if (timestampObserver) {
        timestampObserver.observe(card);
    }
}

// Start periodic timestamp refresh (every 30 seconds)
function startTimestampRefresh() {
    setupTimestampObserver();
    setInterval(refreshTimestamps, 30000);
}
