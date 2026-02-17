/**
 * Lightning QR code modal component.
 * Reusable modal for displaying QR codes during auth and payment flows.
 */

export class LightningQRModal {
    /**
     * Create a Lightning QR modal.
     * @param {Object} config - Modal configuration
     * @param {string} config.title - Modal title
     * @param {string} config.instructions - Instructions text below QR
     * @param {string} config.helpText - Help text below instructions
     * @param {Function} config.onClose - Callback when modal closes
     */
    constructor(config) {
        this.config = {
            title: config.title || 'Lightning Payment',
            instructions: config.instructions || 'Scan with your Lightning wallet',
            helpText: config.helpText || '',
            onClose: config.onClose || (() => {}),
        };

        this.overlay = null;
        this.placeholder = null;
    }

    /**
     * Initialize modal by adding HTML to page.
     * Call this once during page setup.
     */
    init() {
        // Create overlay HTML
        const overlayHTML = `
            <div id="lightning-qr-overlay" class="qr-overlay" style="display: none;">
                <div class="qr-overlay-content">
                    <button class="qr-close-btn" id="lightning-qr-close-btn">×</button>
                    <h2 class="qr-overlay-title">${this.config.title}</h2>
                    <div class="qr-container-overlay">
                        <div id="lightning-qr-placeholder" class="qr-placeholder">
                            <div class="loading-spinner"></div>
                            <p>Generating QR code...</p>
                        </div>
                    </div>
                    <p class="qr-overlay-instructions">${this.config.instructions}</p>
                    ${this.config.helpText ? `<p class="qr-overlay-help">${this.config.helpText}</p>` : ''}

                    <div id="lightning-status" class="auth-status" style="display: none;">
                        <div class="status-icon">✓</div>
                        <p id="lightning-status-message">Success!</p>
                    </div>

                    <div id="lightning-error" class="auth-error" style="display: none;">
                        <p class="error-message" id="lightning-error-message"></p>
                        <button onclick="location.reload()" class="btn-retry">Try Again</button>
                    </div>
                </div>
            </div>
        `;

        // Add to page
        document.body.insertAdjacentHTML('beforeend', overlayHTML);

        // Store references
        this.overlay = document.getElementById('lightning-qr-overlay');
        this.placeholder = document.getElementById('lightning-qr-placeholder');

        // Setup event listeners
        const closeBtn = document.getElementById('lightning-qr-close-btn');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => this.hide());
        }

        // Close when clicking outside
        if (this.overlay) {
            this.overlay.addEventListener('click', (e) => {
                if (e.target === this.overlay) {
                    this.hide();
                }
            });
        }
    }

    /**
     * Display modal with QR code.
     * @param {string} qrImageUrl - URL to QR code image
     */
    show(qrImageUrl) {
        if (!this.overlay || !this.placeholder) {
            console.error('Modal not initialized. Call init() first.');
            return;
        }

        // Reset state
        document.getElementById('lightning-status').style.display = 'none';
        document.getElementById('lightning-error').style.display = 'none';

        // Show loading state
        this.placeholder.innerHTML = '<div class="loading-spinner"></div><p>Generating QR code...</p>';

        // Display overlay
        this.overlay.style.display = 'flex';

        // Load and display QR code
        const img = document.createElement('img');
        img.src = qrImageUrl;
        img.alt = 'Lightning QR Code';
        img.className = 'qr-code-img';

        img.onload = () => {
            this.placeholder.innerHTML = '';
            this.placeholder.appendChild(img);
        };

        img.onerror = () => {
            this.showError('Failed to load QR code');
        };
    }

    /**
     * Hide modal and trigger onClose callback.
     */
    hide() {
        if (this.overlay) {
            this.overlay.style.display = 'none';
        }
        this.config.onClose();
    }

    /**
     * Show success state in modal.
     * @param {string} message - Success message to display
     */
    showSuccess(message) {
        const statusDiv = document.getElementById('lightning-status');
        const statusMsg = document.getElementById('lightning-status-message');

        if (statusDiv && statusMsg) {
            statusMsg.textContent = message;
            statusDiv.style.display = 'block';
        }
    }

    /**
     * Show error state in modal.
     * @param {string} message - Error message to display
     */
    showError(message) {
        const errorDiv = document.getElementById('lightning-error');
        const errorMsg = document.getElementById('lightning-error-message');

        if (errorDiv && errorMsg) {
            errorMsg.textContent = message;
            errorDiv.style.display = 'block';
        }
    }
}
