import { isMobileDevice, buildLightningDeepLink, openLightningWallet, showMobileWalletPrompt } from './lightning-utils.js';
import { LightningQRModal } from './lightning-qr-modal.js';
import { LightningSSEClient } from './lightning-sse.js';

let currentK1 = null;
let currentLnurl = null;
let sseClient = null;
let qrModal = null;

document.addEventListener('DOMContentLoaded', () => {
    // Initialize QR modal
    qrModal = new LightningQRModal({
        title: 'Log In with Lightning',
        instructions: 'Scan with your Lightning wallet',
        helpText: 'New users are created automatically',
        onClose: () => {
            if (sseClient) {
                sseClient.disconnect();
                sseClient = null;
            }
        }
    });
    qrModal.init();

    // Setup login button click handlers
    const floatingBtn = document.getElementById('floating-login-btn');
    const ctaBtn = document.getElementById('cta-login-btn');

    if (floatingBtn) {
        floatingBtn.addEventListener('click', handleLoginClick);
    }

    if (ctaBtn) {
        ctaBtn.addEventListener('click', handleLoginClick);
    }
});

async function handleLoginClick() {
    try {
        // Generate LNURL
        const response = await fetch('/api/auth/lnurl/generate');
        if (!response.ok) throw new Error('Failed to generate LNURL');

        const data = await response.json();
        currentK1 = data.k1;
        currentLnurl = data.lnurl;

        // Start SSE monitoring BEFORE opening wallet/showing QR
        sseClient = new LightningSSEClient(`/api/auth/stream/${currentK1}`, {
            onSuccess: (data) => handleAuthSuccess(data.k1)
        });
        sseClient.connect();

        // Device-aware wallet interaction
        if (isMobileDevice() && currentLnurl) {
            // Mobile: Try to open lightning wallet
            const deepLink = buildLightningDeepLink(currentLnurl);
            const opened = await openLightningWallet(deepLink);

            if (!opened) {
                // Wallet didn't open - show fallback prompt
                showMobileWalletPrompt(
                    'Would you like to see the QR code instead?',
                    () => qrModal.show(`/api/auth/qr/${currentK1}`)
                );
            }
        } else {
            // Desktop: Show QR overlay
            qrModal.show(`/api/auth/qr/${currentK1}`);
        }
    } catch (error) {
        console.error('Error during login:', error);
        showError('Failed to initiate login');
    }
}

async function handleAuthSuccess(k1) {
    try {
        const resp = await fetch('/api/auth/complete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ k1 }),
        });

        if (!resp.ok) {
            showError('Authentication failed. Please try again.');
            return;
        }

        if (qrModal) {
            qrModal.showSuccess('Authentication successful! Redirecting...');
        }

        setTimeout(() => {
            window.location.href = '/dashboard';
        }, 1500);
    } catch (error) {
        console.error('Error completing auth:', error);
        showError('Authentication failed. Please try again.');
    }
}

function showError(message) {
    const errorDiv = document.getElementById('auth-error');
    if (errorDiv) {
        const errorMsg = errorDiv.querySelector('.error-message');
        if (errorMsg) {
            errorMsg.textContent = message;
        }
        errorDiv.style.display = 'block';
    }
}
