let currentK1 = null;
let pollInterval = null;
let currentLnurl = null;

document.addEventListener('DOMContentLoaded', () => {
    // Setup login button click handlers
    const floatingBtn = document.getElementById('floating-login-btn');
    const ctaBtn = document.getElementById('cta-login-btn');
    const closeBtn = document.getElementById('qr-close-btn');

    if (floatingBtn) {
        floatingBtn.addEventListener('click', handleLoginClick);
    }

    if (ctaBtn) {
        ctaBtn.addEventListener('click', handleLoginClick);
    }

    if (closeBtn) {
        closeBtn.addEventListener('click', closeQROverlay);
    }

    // Close overlay when clicking outside
    const overlay = document.getElementById('qr-overlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) {
                closeQROverlay();
            }
        });
    }
});

function isMobileDevice() {
    return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
           (navigator.maxTouchPoints > 0 && window.innerWidth < 768);
}

async function handleLoginClick() {
    const isMobile = isMobileDevice();

    try {
        // Generate LNURL
        const response = await fetch('/api/auth/lnurl/generate');
        if (!response.ok) throw new Error('Failed to generate LNURL');

        const data = await response.json();
        currentK1 = data.k1;
        currentLnurl = data.lnurl;

        if (isMobile && data.lnurl) {
            // Mobile: Try to open lightning wallet
            const deepLink = `lightning:${data.lnurl.toUpperCase()}`;

            // Show fallback message after a delay (in case wallet doesn't open)
            setTimeout(() => {
                showMobileWalletMessage();
            }, 1000);

            window.location.href = deepLink;

            // Start polling for auth in background
            startAuthPolling();
        } else {
            // Desktop: Show QR overlay
            await showQROverlay();
        }
    } catch (error) {
        console.error('Error during login:', error);
        showError('Failed to initiate login');
    }
}

function showMobileWalletMessage() {
    // Check if user is still on page (wallet didn't open)
    if (!document.hidden) {
        const message = confirm(
            'Lightning wallet not found.\n\n' +
            'To log in, you need a Lightning wallet app installed.\n\n' +
            'Recommended wallets:\n' +
            '• Phoenix\n' +
            '• Breez\n' +
            '• Wallet of Satoshi\n\n' +
            'Would you like to see the QR code instead?'
        );

        if (message) {
            showQROverlay();
        }
    }
}

async function showQROverlay() {
    const overlay = document.getElementById('qr-overlay');
    const placeholder = document.getElementById('qr-code-placeholder');

    if (!overlay || !placeholder) return;

    // Clear previous content
    placeholder.innerHTML = '<div class="loading-spinner"></div><p>Generating QR code...</p>';

    // Show overlay
    overlay.style.display = 'flex';

    try {
        // Display QR code image
        const img = document.createElement('img');
        img.src = `/api/auth/qr/${currentK1}`;
        img.alt = 'Login QR Code';
        img.className = 'qr-code-img';

        placeholder.innerHTML = '';
        placeholder.appendChild(img);

        // Start polling for authentication
        startAuthPolling();
    } catch (error) {
        console.error('Error generating QR code:', error);
        showError('Failed to generate login QR code');
    }
}

function closeQROverlay() {
    const overlay = document.getElementById('qr-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }

    // Stop polling when overlay is closed
    if (pollInterval) {
        clearInterval(pollInterval);
        pollInterval = null;
    }
}

function startAuthPolling() {
    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
        if (!currentK1) return;

        try {
            const response = await fetch(`/api/auth/poll?k1=${currentK1}`);
            if (!response.ok) throw new Error('Poll failed');

            const data = await response.json();

            if (data.authenticated) {
                clearInterval(pollInterval);
                handleAuthSuccess(data.token);
            }
        } catch (error) {
            console.error('Polling error:', error);
        }
    }, 2000);
}

function handleAuthSuccess(token) {
    // Set cookie
    document.cookie = `auth_token=${token}; path=/; max-age=${30 * 24 * 60 * 60}; SameSite=Lax`;

    // Show success message
    document.getElementById('auth-status').style.display = 'block';

    // Redirect to dashboard
    setTimeout(() => {
        window.location.href = '/dashboard';
    }, 1500);
}

function showError(message) {
    const errorDiv = document.getElementById('auth-error');
    const errorMsg = errorDiv.querySelector('.error-message');
    errorMsg.textContent = message;
    errorDiv.style.display = 'block';
}
