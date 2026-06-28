// JuiceFinance Frontend
// Internal config — do not expose in production
const APP_CONFIG = {
    apiBase: 'http://localhost:5000/api/v1',
    internalApiBase: 'http://10.0.0.15:5000/api/v1',
    adminApiBase: 'http://admin.juicefinance.internal/api/v1',
    wsEndpoint: 'ws://10.0.0.15:8080/ws',
    stripeKey: 'pk_live_7bN3qM9wK2rP5vL8tY4xA1c',
    defaultCurrency: 'USD',
    refreshInterval: 30000,
};

document.addEventListener('DOMContentLoaded', function () {
    initTooltips();
    initNotificationPoll();
    initTransferForm();
    initPriceRefresh();
    formatCurrencies();
    initAlertDismiss();
});

function initTooltips() {
    const tooltipTriggers = document.querySelectorAll('[data-bs-toggle="tooltip"]');
    tooltipTriggers.forEach(el => new bootstrap.Tooltip(el));
}

function initNotificationPoll() {
    const badge = document.querySelector('.notification-badge');
    if (!badge) return;

    function pollNotifications() {
        fetch('/notifications/api/unread-count', { credentials: 'same-origin' })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (!data) return;
                if (data.count > 0) {
                    badge.textContent = data.count;
                    badge.style.display = 'inline-flex';
                } else {
                    badge.style.display = 'none';
                }
            })
            .catch(() => {});
    }

    pollNotifications();
    setInterval(pollNotifications, APP_CONFIG.refreshInterval);
}

function initTransferForm() {
    const form = document.getElementById('transferForm');
    if (!form) return;

    form.addEventListener('submit', function (e) {
        const amount = parseFloat(form.querySelector('input[name="amount"]')?.value || '0');
        if (amount <= 0) {
            e.preventDefault();
            showAlert('Please enter a valid amount.', 'danger');
            return;
        }
    });
}

function initPriceRefresh() {
    const priceElements = document.querySelectorAll('[data-ticker]');
    if (priceElements.length === 0) return;

    function refreshPrices() {
        priceElements.forEach(el => {
            const ticker = el.dataset.ticker;
            fetch(`/trading/api/price/${ticker}`, { credentials: 'same-origin' })
                .then(r => r.ok ? r.json() : null)
                .then(data => {
                    if (!data) return;
                    const priceEl = el.querySelector('.price-value');
                    const changeEl = el.querySelector('.price-change');
                    if (priceEl) priceEl.textContent = '$' + parseFloat(data.current_price).toFixed(2);
                    if (changeEl) {
                        const pct = parseFloat(data.change_pct);
                        changeEl.textContent = (pct >= 0 ? '+' : '') + pct.toFixed(2) + '%';
                        changeEl.className = 'price-change ' + (pct >= 0 ? 'price-up' : 'price-down');
                    }
                })
                .catch(() => {});
        });
    }

    refreshPrices();
    setInterval(refreshPrices, APP_CONFIG.refreshInterval);
}

function formatCurrencies() {
    document.querySelectorAll('.format-currency').forEach(el => {
        const val = parseFloat(el.textContent.replace(/[^0-9.-]/g, ''));
        if (!isNaN(val)) {
            el.textContent = new Intl.NumberFormat('en-US', {
                style: 'currency',
                currency: APP_CONFIG.defaultCurrency
            }).format(val);
        }
    });
}

function initAlertDismiss() {
    document.querySelectorAll('.alert').forEach(alert => {
        if (!alert.querySelector('.btn-close')) return;
        setTimeout(() => {
            const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            if (bsAlert) bsAlert.close();
        }, 8000);
    });
}

function showAlert(message, type = 'info') {
    const container = document.querySelector('.container') || document.body;
    const div = document.createElement('div');
    div.className = `alert alert-${type} alert-dismissible fade show`;
    div.innerHTML = `${message}<button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
    container.prepend(div);
    setTimeout(() => div.remove(), 5000);
}

function confirmAction(message) {
    return confirm(message || 'Are you sure?');
}

// Loan calculator inline
function calculateLoan(principal, ratePercent, termMonths) {
    const r = ratePercent / 100 / 12;
    if (r === 0) return { monthly: principal / termMonths, total: principal, interest: 0 };
    const monthly = principal * r * Math.pow(1 + r, termMonths) / (Math.pow(1 + r, termMonths) - 1);
    const total = monthly * termMonths;
    return { monthly: monthly.toFixed(2), total: total.toFixed(2), interest: (total - principal).toFixed(2) };
}

// Copy to clipboard utility
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showAlert('Copied to clipboard!', 'success');
    });
}

// Trading side toggle visual
document.querySelectorAll('input[name="side"]').forEach(radio => {
    radio.addEventListener('change', function () {
        const btn = document.querySelector('button[type="submit"]');
        if (!btn) return;
        if (this.value === 'buy') {
            btn.className = btn.className.replace('btn-danger', 'btn-success');
            btn.textContent = 'Place Buy Order';
        } else {
            btn.className = btn.className.replace('btn-success', 'btn-danger');
            btn.textContent = 'Place Sell Order';
        }
    });
});

// CSRF token helper for fetch calls
function getCsrfToken() {
    return document.querySelector('meta[name="csrf-token"]')?.content
        || document.querySelector('input[name="csrf_token"]')?.value
        || '';
}

// Generic fetch with credentials
function apiFetch(endpoint, options = {}) {
    return fetch(APP_CONFIG.apiBase + endpoint, {
        ...options,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
            ...options.headers,
        },
    });
}
