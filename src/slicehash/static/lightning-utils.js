/**
 * Lightning wallet interaction utilities.
 * Provides device detection, deep linking, and wallet opening functionality.
 */

/**
 * Detect if user is on a mobile device.
 * @returns {boolean} True if mobile device detected
 */
export function isMobileDevice() {
    return (
        /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent) ||
        (navigator.maxTouchPoints > 0 && window.innerWidth < 768)
    );
}

/**
 * Build Lightning deep link URI for wallet apps.
 * @param {string} lnurlOrInvoice - LNURL or Lightning invoice string
 * @returns {string} Deep link URI (lightning:LNURL...)
 */
export function buildLightningDeepLink(lnurlOrInvoice) {
    return `lightning:${lnurlOrInvoice.toUpperCase()}`;
}

/**
 * Attempt to open Lightning wallet app via deep link.
 * @param {string} lightningUri - Lightning deep link URI
 * @returns {Promise<boolean>} Promise that resolves to true if wallet likely opened
 */
export async function openLightningWallet(lightningUri) {
    return new Promise((resolve) => {
        // Track if page becomes hidden (wallet opened)
        let walletOpened = false;

        const visibilityHandler = () => {
            if (document.hidden) {
                walletOpened = true;
            }
        };

        document.addEventListener('visibilitychange', visibilityHandler);

        // Attempt to open wallet
        window.location.href = lightningUri;

        // Check after delay if wallet opened
        setTimeout(() => {
            document.removeEventListener('visibilitychange', visibilityHandler);
            resolve(walletOpened);
        }, 1000);
    });
}

/**
 * Show user-friendly prompt when wallet doesn't open.
 * @param {string} message - Message to display to user
 * @param {Function} qrFallback - Callback to invoke if user wants QR code
 */
export function showMobileWalletPrompt(message, qrFallback) {
    const showQR = confirm(
        message + '\n\n' +
        'Lightning wallet not found.\n\n' +
        'To continue, you need a Lightning wallet app installed.\n\n' +
        'Recommended wallets:\n' +
        '• Phoenix\n' +
        '• Breez\n' +
        '• Wallet of Satoshi\n\n' +
        'Would you like to see the QR code instead?'
    );

    if (showQR && qrFallback) {
        qrFallback();
    }
}
