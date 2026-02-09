// Purchases JavaScript - Purchase history and purchase actions

// State management
let isLoading = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadNetworkDifficulty();
    await loadPurchases();
    setupPurchaseButton();
});

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

// Load purchase history
async function loadPurchases() {
    if (isLoading) return;

    isLoading = true;
    showLoading(true);

    try {
        const response = await fetch('/api/users/me/purchases');
        if (!response.ok) throw new Error('Failed to fetch purchases');
        const data = await response.json();

        console.log('Loaded purchases:', data);

        if (data.purchases.length === 0) {
            console.log('No purchases, showing empty state');
            showEmptyState(true);
        } else {
            console.log('Found', data.purchases.length, 'purchases');
            showEmptyState(false);
            renderPurchaseCards(data.purchases);
        }

    } catch (error) {
        console.error('Error loading purchases:', error);
        showError('Failed to load purchases');
        showEmptyState(true);
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Render purchase cards
function renderPurchaseCards(purchases) {
    const container = document.getElementById('purchase-cards-container');
    if (!container) {
        console.error('purchase-cards-container not found');
        return;
    }

    container.innerHTML = '';
    console.log('Rendering', purchases.length, 'purchases');

    purchases.forEach(purchase => {
        const card = document.createElement('div');
        card.className = 'purchase-card';

        const date = formatDate(purchase.created_at);

        card.innerHTML = `
            <div class="purchase-card-header">
                <span class="purchase-date">${date}</span>
                <span class="purchase-amount">${purchase.amount}</span>
            </div>
            <div class="purchase-amount-label">Shares Purchased</div>
        `;

        container.appendChild(card);
    });
}

// Format date
function formatDate(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
    });
}

// Setup purchase button
function setupPurchaseButton() {
    const button = document.getElementById('purchase-btn');
    button.addEventListener('click', async () => {
        // TODO: Implement purchase flow
        alert('Purchase flow coming soon!');
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
    const container = document.getElementById('purchase-cards-container');

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
}
