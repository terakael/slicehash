// Settings page JavaScript

// Bitcoin address validation regex
const BITCOIN_ADDRESS_REGEX = /^(bc1[a-z0-9]{39,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$/;

// DOM elements
let form;
let addressInput;
let tagInput;
let saveButton;
let successMessage;
let errorMessage;

// State
let isLoading = false;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    // Get DOM elements
    form = document.getElementById('settings-form');
    addressInput = document.getElementById('address');
    tagInput = document.getElementById('tag');
    saveButton = document.getElementById('save-button');
    successMessage = document.getElementById('success-message');
    errorMessage = document.getElementById('error-message');

    // Load current user data
    await loadCurrentSettings();

    // Setup form submission handler
    form.addEventListener('submit', handleFormSubmit);

    // Initialize SSE connection
    initSharedSSE();
});

// Load current user settings from API
async function loadCurrentSettings() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) {
            throw new Error('Failed to load settings');
        }

        const data = await response.json();

        // Populate form fields
        addressInput.value = data.address || '';
        tagInput.value = data.tag || '';

        // Update shares remaining display
        document.getElementById('shares-remaining').textContent = data.shares_remaining;

    } catch (error) {
        console.error('Error loading settings:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
        showError('Failed to load current settings. Please refresh the page.');
    }
}

// Handle form submission
async function handleFormSubmit(event) {
    event.preventDefault();

    // Clear previous messages
    hideMessages();

    // Get form values
    const address = addressInput.value.trim();
    const tag = tagInput.value.trim();

    // Client-side validation
    if (address && !BITCOIN_ADDRESS_REGEX.test(address)) {
        showError('Invalid Bitcoin address format. Please use bech32 (bc1...) or legacy (1... or 3...) format.');
        addressInput.classList.add('error');
        return;
    }

    if (tag && tag.length > 50) {
        showError('Custom tag must be 50 characters or less.');
        tagInput.classList.add('error');
        return;
    }

    // Remove error styling
    addressInput.classList.remove('error');
    tagInput.classList.remove('error');

    // Build request payload (only include non-empty fields)
    const payload = {};
    if (address) payload.address = address;
    if (tag) payload.tag = tag;

    // Check if there's anything to update
    if (Object.keys(payload).length === 0) {
        showError('Please enter at least one field to update.');
        return;
    }

    // Disable form during submission
    setLoading(true);

    try {
        const response = await fetch('/api/users/me', {
            method: 'PATCH',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const data = await response.json();
            
            // Update form with returned values
            addressInput.value = data.address || '';
            tagInput.value = data.tag || '';
            
            // Show success message
            showSuccess('Settings saved successfully!');
        } else {
            // Handle error response
            const errorData = await response.json();
            
            if (response.status === 400) {
                // Validation error
                if (errorData.details) {
                    if (Array.isArray(errorData.details)) {
                        const messages = errorData.details.map(d => d.message).join(', ');
                        showError(`Validation error: ${messages}`);
                    } else {
                        showError(`Validation error: ${errorData.details}`);
                    }
                } else {
                    showError(errorData.error || 'Invalid input');
                }
            } else {
                // Server error
                showError('Failed to save settings. Please try again.');
            }
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        showError('Network error. Please check your connection and try again.');
    } finally {
        setLoading(false);
    }
}

// Show success message
function showSuccess(message) {
    hideMessages();
    successMessage.textContent = message;
    successMessage.style.display = 'block';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        successMessage.style.display = 'none';
    }, 5000);
}

// Show error message
function showError(message) {
    hideMessages();
    errorMessage.textContent = message;
    errorMessage.style.display = 'block';
    
    // Auto-hide after 5 seconds
    setTimeout(() => {
        errorMessage.style.display = 'none';
    }, 5000);
}

// Hide all messages
function hideMessages() {
    successMessage.style.display = 'none';
    errorMessage.style.display = 'none';
}

// Set loading state
function setLoading(loading) {
    isLoading = loading;
    saveButton.disabled = loading;
    saveButton.textContent = loading ? 'Saving...' : 'Save Changes';
}
