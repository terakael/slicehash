// Purchases page — Lightning invoice payment flow

import { LightningQRModal } from './lightning-qr-modal.js';
import { LightningSSEClient } from './lightning-sse.js';
import { isMobileDevice, buildLightningDeepLink, openLightningWallet } from './lightning-utils.js';

// State
let isLoading = false;
let isPurchasing = false;
let invoiceModal = null;
let invoiceSSEClient = null;
let countdownInterval = null;
let currentBolt11 = null;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    await loadUserData();
    await loadPurchases();
    setupPurchaseForm();
    window.initSharedSSE();

    invoiceModal = new LightningQRModal({
        title: 'Pay with Lightning',
        instructions: 'Scan with your Lightning wallet',
        onClose: () => cleanupInvoice(),
    });
    invoiceModal.init();
    addInvoiceExtras();
});

// Inject amount, countdown, and wallet-button elements into the modal
function addInvoiceExtras() {
    const content = document.querySelector('.qr-overlay-content');
    if (!content) return;

    const instructions = content.querySelector('.qr-overlay-instructions');
    if (!instructions) return;

    // Amount line (e.g. "1,000 sats · 1 share")
    const amountEl = document.createElement('p');
    amountEl.id = 'invoice-amount';
    amountEl.className = 'invoice-amount';
    amountEl.style.display = 'none';
    instructions.insertAdjacentElement('afterend', amountEl);

    // Countdown timer
    const countdownEl = document.createElement('p');
    countdownEl.id = 'invoice-countdown';
    countdownEl.className = 'invoice-countdown';
    countdownEl.style.display = 'none';
    amountEl.insertAdjacentElement('afterend', countdownEl);

    // Open-in-wallet button (shown on mobile)
    const walletBtn = document.createElement('button');
    walletBtn.id = 'open-wallet-btn';
    walletBtn.className = 'btn-open-wallet';
    walletBtn.textContent = 'Open in Wallet';
    walletBtn.style.display = 'none';
    walletBtn.addEventListener('click', () => {
        if (currentBolt11) {
            openLightningWallet(buildLightningDeepLink(currentBolt11));
        }
    });
    countdownEl.insertAdjacentElement('afterend', walletBtn);
}

// Fetch and display user data (shares remaining, BTC address warning)
async function loadUserData() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) throw new Error('Failed to fetch user data');
        const data = await response.json();

        document.getElementById('shares-remaining').textContent = data.shares_remaining;

        if (data.address && data.address.startsWith('bc1_update_in_settings_')) {
            showBtcAddressWarning();
        }
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

        if (data.purchases.length === 0) {
            showEmptyState(true);
        } else {
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
    if (!container) return;

    container.innerHTML = '';
    purchases.forEach(purchase => {
        const card = document.createElement('div');
        card.className = 'purchase-card';
        card.innerHTML = `
            <div class="purchase-card-header">
                <span class="purchase-date">${formatDate(purchase.created_at)}</span>
                <span class="purchase-amount">${purchase.amount}</span>
            </div>
            <div class="purchase-amount-label">Shares Purchased</div>
        `;
        container.appendChild(card);
    });
}

function formatDate(timestamp) {
    const ts = typeof timestamp === 'string' ? Number(timestamp) : timestamp;
    return new Date(ts * 1000).toLocaleDateString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
    });
}

// Setup purchase form
function setupPurchaseForm() {
    const input = document.getElementById('purchase-amount');
    const button = document.getElementById('purchase-submit-btn');

    button.addEventListener('click', async () => { await handlePurchase(); });
    input.addEventListener('keypress', async (e) => {
        if (e.key === 'Enter') await handlePurchase();
    });
}

// Handle purchase: create invoice then show payment modal
async function handlePurchase() {
    if (isPurchasing) return;

    const input = document.getElementById('purchase-amount');
    const button = document.getElementById('purchase-submit-btn');
    const amount = parseInt(input.value);

    if (!amount || amount <= 0) {
        showError('Please enter a valid amount');
        return;
    }

    isPurchasing = true;
    button.disabled = true;
    button.textContent = 'Generating invoice...';

    try {
        const response = await fetch('/api/users/me/purchases/invoice', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount }),
        });

        if (!response.ok) {
            const err = await response.json();
            throw new Error(err.error || 'Failed to create invoice');
        }

        const data = await response.json();
        input.value = '';
        showInvoiceModal(data, amount);

    } catch (error) {
        console.error('Error creating invoice:', error);
        const msg = error.message || 'Failed to create invoice';
        if (msg.includes('Bitcoin address')) {
            showError(msg + ' <a href="/settings" style="color: #007bff; text-decoration: underline;">Go to Settings</a>');
        } else {
            showError(msg);
        }
    } finally {
        isPurchasing = false;
        button.disabled = false;
        button.textContent = 'Purchase';
    }
}

// Show invoice modal and start SSE listener
function showInvoiceModal({ invoice_id, bolt11, amount_sats, expires_at }, numShares) {
    currentBolt11 = bolt11;

    // Show QR (server generates QR from stored BOLT11)
    invoiceModal.show(`/api/users/me/purchases/invoice/${invoice_id}/qr`);

    // Update amount line
    const amountEl = document.getElementById('invoice-amount');
    if (amountEl) {
        amountEl.textContent = `${amount_sats.toLocaleString()} sats · ${numShares} share${numShares !== 1 ? 's' : ''}`;
        amountEl.style.display = 'block';
    }

    // Mobile: show "Open in Wallet" button
    const walletBtn = document.getElementById('open-wallet-btn');
    if (walletBtn) {
        walletBtn.style.display = isMobileDevice() ? 'block' : 'none';
    }

    // Start countdown
    startCountdown(expires_at);

    // Connect SSE stream for payment confirmation
    cleanupInvoiceSSE();
    invoiceSSEClient = new LightningSSEClient(
        `/api/users/me/purchases/invoice/${invoice_id}/stream`,
        {
            onSuccess: () => {
                stopCountdown();
                invoiceModal.showSuccess('Payment received! Shares added to your account.');
                setTimeout(async () => {
                    invoiceModal.hide();
                    await loadUserData();
                    await loadPurchases();
                }, 2000);
            },
            onExpired: () => {
                stopCountdown();
                invoiceModal.showError('Invoice expired. Please close and try again.');
            },
            onError: (e) => {
                console.error('Invoice SSE error:', e);
            },
        }
    );
    invoiceSSEClient.connect();
}

// Countdown timer
function startCountdown(expiresAt) {
    const el = document.getElementById('invoice-countdown');
    if (!el) return;

    el.style.display = 'block';
    stopCountdown();

    countdownInterval = setInterval(() => {
        const remaining = Math.max(0, expiresAt - Math.floor(Date.now() / 1000));
        const mins = Math.floor(remaining / 60);
        const secs = remaining % 60;
        el.textContent = `Expires in ${mins}:${secs.toString().padStart(2, '0')}`;

        if (remaining === 0) {
            stopCountdown();
            el.textContent = 'Expired';
        }
    }, 1000);
}

function stopCountdown() {
    if (countdownInterval) {
        clearInterval(countdownInterval);
        countdownInterval = null;
    }
}

// Cleanup SSE connection (called on modal close)
function cleanupInvoiceSSE() {
    if (invoiceSSEClient) {
        invoiceSSEClient.disconnect();
        invoiceSSEClient = null;
    }
}

function cleanupInvoice() {
    cleanupInvoiceSSE();
    stopCountdown();
    currentBolt11 = null;

    const amountEl = document.getElementById('invoice-amount');
    if (amountEl) amountEl.style.display = 'none';

    const countdownEl = document.getElementById('invoice-countdown');
    if (countdownEl) countdownEl.style.display = 'none';

    const walletBtn = document.getElementById('open-wallet-btn');
    if (walletBtn) walletBtn.style.display = 'none';
}

// UI helpers
function showLoading(show) {
    document.getElementById('loading-indicator').style.display = show ? 'block' : 'none';
}

function showEmptyState(show) {
    const emptyState = document.getElementById('empty-state');
    const container = document.getElementById('purchase-cards-container');
    emptyState.style.display = show ? 'block' : 'none';
    container.style.display = show ? 'none' : 'flex';
}

function showError(message) {
    let errorAlert = document.getElementById('purchase-error-alert');
    if (!errorAlert) {
        errorAlert = document.createElement('div');
        errorAlert.id = 'purchase-error-alert';
        errorAlert.className = 'alert alert-danger';
        errorAlert.style.marginTop = '1rem';
        const form = document.querySelector('.purchase-form');
        form.parentNode.insertBefore(errorAlert, form.nextSibling);
    }

    errorAlert.innerHTML = message;
    errorAlert.style.display = 'block';

    if (!message.includes('<a')) {
        setTimeout(() => { errorAlert.style.display = 'none'; }, 5000);
    }
}

function showBtcAddressWarning() {
    if (document.getElementById('btc-address-warning')) return;

    const warning = document.createElement('div');
    warning.id = 'btc-address-warning';
    warning.className = 'alert alert-warning';
    warning.style.marginBottom = '1.5rem';
    warning.innerHTML = `
        <strong>⚠️ Action Required:</strong> You must set your Bitcoin address before purchasing shares.
        <a href="/settings" style="color: #856404; text-decoration: underline; font-weight: bold;">Go to Settings →</a>
    `;

    const mainContent = document.querySelector('main') || document.querySelector('.container');
    if (mainContent && mainContent.firstChild) {
        mainContent.insertBefore(warning, mainContent.firstChild);
    }
}
