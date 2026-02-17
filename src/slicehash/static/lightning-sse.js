/**
 * Lightning SSE client for real-time auth and payment notifications.
 * Wraps EventSource with Lightning-specific event handling.
 */

export class LightningSSEClient {
    /**
     * Create Lightning SSE client.
     * @param {string} endpoint - SSE endpoint URL
     * @param {Object} handlers - Event handlers
     * @param {Function} handlers.onConnected - Called when SSE connects (optional)
     * @param {Function} handlers.onSuccess - Called on success event (authenticated/paid)
     * @param {Function} handlers.onError - Called on error (optional)
     */
    constructor(endpoint, handlers) {
        this.endpoint = endpoint;
        this.handlers = {
            onConnected: handlers.onConnected || (() => {}),
            onSuccess: handlers.onSuccess || (() => {}),
            onError: handlers.onError || ((error) => console.error('SSE error:', error)),
        };
        this.eventSource = null;
    }

    /**
     * Start SSE connection and begin listening for events.
     */
    connect() {
        // Close existing connection if any
        if (this.eventSource) {
            this.eventSource.close();
        }

        // Open new connection
        this.eventSource = new EventSource(this.endpoint);

        // Connected event
        this.eventSource.addEventListener('connected', (e) => {
            console.log('Lightning SSE connected:', e.data);
            try {
                const data = JSON.parse(e.data);
                this.handlers.onConnected(data);
            } catch (err) {
                console.error('Error parsing connected event:', err);
            }
        });

        // Success events (authenticated or paid)
        this.eventSource.addEventListener('authenticated', (e) => {
            this._handleSuccess(e);
        });

        this.eventSource.addEventListener('paid', (e) => {
            this._handleSuccess(e);
        });

        // Error event
        this.eventSource.addEventListener('error', (e) => {
            console.error('Lightning SSE error:', e);
            this.handlers.onError(e);
            this.disconnect();
        });
    }

    /**
     * Handle success event (authenticated or paid).
     * @private
     */
    _handleSuccess(event) {
        try {
            const data = JSON.parse(event.data);
            this.disconnect();
            this.handlers.onSuccess(data);
        } catch (err) {
            console.error('Error parsing success event:', err);
            this.handlers.onError(err);
        }
    }

    /**
     * Close SSE connection.
     */
    disconnect() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
    }

    /**
     * Check if SSE connection is active.
     * @returns {boolean} True if connected
     */
    isConnected() {
        return this.eventSource !== null && this.eventSource.readyState === EventSource.OPEN;
    }
}
