let currentK1 = null;
let pollInterval = null;

document.addEventListener('DOMContentLoaded', async () => {
    await generateQRCode();
    startAuthPolling();
});

async function generateQRCode() {
    try {
        const response = await fetch('/api/auth/lnurl/generate');
        if (!response.ok) throw new Error('Failed to generate LNURL');

        const data = await response.json();
        currentK1 = data.k1;

        const placeholder = document.getElementById('qr-code-placeholder');
        placeholder.innerHTML = '';

        // Check if on narrow screen (likely mobile)
        const isNarrowScreen = window.innerWidth < 768;

        if (isNarrowScreen && data.lnurl) {
            // Show button first for mobile users
            const deepLink = `lightning:${data.lnurl.toUpperCase()}`;
            const linkBtn = document.createElement('a');
            linkBtn.href = deepLink;
            linkBtn.className = 'wallet-open-btn';
            linkBtn.textContent = 'Open Lightning Wallet';

            const hint = document.createElement('p');
            hint.className = 'mobile-hint';
            hint.textContent = 'Tap to authenticate with your Lightning wallet';

            placeholder.appendChild(linkBtn);
            placeholder.appendChild(hint);

            // Also show QR code below for alternative scanning
            const orDivider = document.createElement('p');
            orDivider.className = 'mobile-hint';
            orDivider.style.marginTop = '24px';
            orDivider.textContent = '— or scan with another device —';

            const img = document.createElement('img');
            img.src = `/api/auth/qr/${data.k1}`;
            img.alt = 'Login QR Code';
            img.className = 'qr-code-img';
            img.style.marginTop = '16px';

            placeholder.appendChild(orDivider);
            placeholder.appendChild(img);
        } else {
            // Display QR code for desktop users
            const img = document.createElement('img');
            img.src = `/api/auth/qr/${data.k1}`;
            img.alt = 'Login QR Code';
            img.className = 'qr-code-img';
            placeholder.appendChild(img);
        }

    } catch (error) {
        console.error('Error generating QR code:', error);
        showError('Failed to generate login QR code');
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
