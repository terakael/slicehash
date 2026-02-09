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

        // Display QR code image from server
        const placeholder = document.getElementById('qr-code-placeholder');
        const img = document.createElement('img');
        img.src = `/api/auth/qr/${data.k1}`;
        img.alt = 'Login QR Code';
        img.className = 'qr-code-img';

        placeholder.innerHTML = '';
        placeholder.appendChild(img);

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
