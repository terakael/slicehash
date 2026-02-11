// Purchases JavaScript - Purchase history and purchase actions

// State management
let isLoading = false;
let isPurchasing = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadPurchases();
    setupPurchaseForm();
    initSharedSSE();
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

// Setup purchase form
function setupPurchaseForm() {
    const form = document.querySelector('.purchase-form');
    const input = document.getElementById('purchase-amount');
    const button = document.getElementById('purchase-submit-btn');

    button.addEventListener('click', async () => {
        await handlePurchase();
    });

    input.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') {
            await handlePurchase();
        }
    });
}

// Handle purchase submission
async function handlePurchase() {
    if (isPurchasing) return;

    const input = document.getElementById('purchase-amount');
    const button = document.getElementById('purchase-submit-btn');
    const amount = parseInt(input.value);

    // Validate input
    if (!amount || amount <= 0) {
        showError('Please enter a valid amount');
        return;
    }

    isPurchasing = true;
    button.disabled = true;
    button.textContent = 'Purchasing...';

    try {
        const response = await fetch('/api/users/me/purchases', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ amount })
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Failed to create purchase');
        }

        // Clear input
        input.value = '';

        // Reload data
        await loadUserData();
        await loadPurchases();

        console.log('Purchase successful');

    } catch (error) {
        console.error('Error creating purchase:', error);
        showError(error.message || 'Failed to create purchase');
    } finally {
        isPurchasing = false;
        button.disabled = false;
        button.textContent = 'Purchase';
    }
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
