// Shared JavaScript utilities for SliceHash

// Format timestamp as relative time
function formatTimestamp(timestamp) {
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);

    let timeStr;
    if (diffMins < 1) {
        timeStr = 'Just now';
    } else if (diffMins < 60) {
        timeStr = `${diffMins}m ago`;
    } else {
        const diffHours = Math.floor(diffMins / 60);
        if (diffHours < 24) {
            timeStr = `${diffHours}h ago`;
        } else {
            const diffDays = Math.floor(diffHours / 24);
            if (diffDays < 7) {
                timeStr = `${diffDays}d ago`;
            } else {
                timeStr = date.toLocaleDateString();
            }
        }
    }

    return timeStr;
}

// Format timestamp with username on separate lines for highscores
function formatTimestampWithUsername(timestamp, username) {
    const timeStr = formatTimestamp(timestamp);
    const truncatedUsername = truncateUsername(username);
    return { timeStr, username: truncatedUsername };
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
    // Regular timestamps (dashboard)
    const timestampElements = document.querySelectorAll('.share-timestamp[data-timestamp]');
    timestampElements.forEach(element => {
        refreshTimestamp(element);
    });

    // Highscore timestamps with username (wrapper has data attributes)
    const timestampWrappers = document.querySelectorAll('.share-timestamp-wrapper[data-timestamp]');
    timestampWrappers.forEach(wrapper => {
        refreshTimestampWithUser(wrapper);
    });
}

// Refresh a single timestamp element
function refreshTimestamp(element) {
    const originalTimestamp = element.dataset.timestamp;
    const newDisplay = formatTimestamp(originalTimestamp);
    element.textContent = newDisplay;
}

// Refresh timestamp with username (for highscores)
function refreshTimestampWithUser(wrapper) {
    const originalTimestamp = wrapper.dataset.timestamp;
    const username = wrapper.dataset.username;
    const { timeStr, username: truncatedUsername } = formatTimestampWithUsername(originalTimestamp, username);

    const timestampEl = wrapper.querySelector('.share-timestamp');
    const usernameEl = wrapper.querySelector('.share-username');

    if (timestampEl) timestampEl.textContent = timeStr;
    if (usernameEl) usernameEl.textContent = truncatedUsername;
}

// Setup Intersection Observer to refresh timestamps when cards come into view
function setupTimestampObserver() {
    timestampObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                // Check for regular timestamp (dashboard)
                const timestampElement = entry.target.querySelector('.share-timestamp[data-timestamp]');
                if (timestampElement) {
                    refreshTimestamp(timestampElement);
                }

                // Check for highscore timestamp wrapper
                const timestampWrapper = entry.target.querySelector('.share-timestamp-wrapper[data-timestamp]');
                if (timestampWrapper) {
                    refreshTimestampWithUser(timestampWrapper);
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
