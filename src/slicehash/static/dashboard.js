// Dashboard JavaScript - hs-row cards with infinite scroll and desktop grid

// State management
let isLoading = false;
let hasMore = true;
let currentOffset = 0;
let currentMode = localStorage.getItem('dashboardMode') || 'recent';
const LIMIT = 20;
let hasLoadedAllShares = false;

// Desktop column state
let currentMyBestPeriod = 'best-24h';
let currentHsPeriod = '24h';
let currentPersonalBestLevel = 0;

const isDesktop = window.matchMedia('(min-width: 1024px)').matches;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    restoreSavedMode();
    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
    setupToggleButtons();
    initSharedSSE(handleNewShare);
    startTimestampRefresh();

    if (isDesktop) {
        initDesktopView();
    }
});

// Restore saved mode from localStorage
function restoreSavedMode() {
    document.querySelectorAll('.toggle-btn[data-mode]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === currentMode);
    });
}

// Fetch and display user data
async function loadUserData() {
    try {
        const response = await fetch('/api/users/me');
        if (!response.ok) throw new Error('Failed to fetch user data');
        const data = await response.json();
        document.getElementById('shares-remaining').textContent = data.shares_remaining;
        await loadNetworkDifficulty();
    } catch (error) {
        console.error('Error loading user data:', error);
        document.getElementById('shares-remaining').textContent = 'Error';
    }
}

// Fetch network difficulty
async function loadNetworkDifficulty() {
    try {
        const response = await fetch('/api/traffic/status');
        if (!response.ok) throw new Error('Failed to fetch traffic status');
        const data = await response.json();
        const dot = document.getElementById('network-difficulty-dot');
        const val = document.getElementById('network-difficulty-value');
        if (dot) {
            dot.classList.remove('warning', 'danger');
            if (data.traffic_level === 'elevated') dot.classList.add('warning');
            else if (data.traffic_level === 'high') dot.classList.add('danger');
        }
        if (val) val.textContent = data.active_user_count;
    } catch (error) {
        console.error('Error loading network difficulty:', error);
    }
}

// Load shares with pagination
async function loadShares(append = false) {
    if (isLoading || (!append && currentOffset > 0)) return;
    if (append && !hasMore) return;

    isLoading = true;
    showLoading(true);

    try {
        const url = `/api/users/me/shares/load?mode=${currentMode}&limit=${LIMIT}&offset=${currentOffset}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error('Failed to fetch shares');
        const data = await response.json();

        if (data.shares.length === 0 && currentOffset === 0) {
            showEmptyState(true);
        } else {
            showEmptyState(false);
            renderShareCards(data.shares, append);
            currentOffset += data.shares.length;
            hasMore = data.has_more;
            hasLoadedAllShares = !data.has_more;
        }
    } catch (error) {
        console.error('Error loading shares:', error);
    } finally {
        isLoading = false;
        showLoading(false);
    }
}

// Refresh dashboard (called by shared.js on refocus)
window.refreshDashboard = async function() {
    currentOffset = 0;
    hasMore = true;
    hasLoadedAllShares = false;
    const container = document.getElementById('share-cards-container');
    if (container) container.innerHTML = '';
    await loadShares(false);
};

// Switch between view modes
function switchMode(mode) {
    if (mode === currentMode || isLoading) return;
    currentMode = mode;
    localStorage.setItem('dashboardMode', mode);
    document.querySelectorAll('.toggle-btn[data-mode]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    currentOffset = 0;
    hasMore = true;
    hasLoadedAllShares = false;
    loadShares(false);
}

// Setup toggle button event listeners (mobile mode buttons only)
function setupToggleButtons() {
    document.querySelectorAll('.toggle-btn[data-mode]').forEach(btn => {
        btn.addEventListener('click', () => switchMode(btn.dataset.mode));
    });
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function truncateHash(hash) {
    if (!hash) return '';
    return '...' + hash.slice(-10);
}

function darkenHex(hex, factor) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return '#' + [r, g, b].map(c => Math.round(c * factor).toString(16).padStart(2, '0')).join('');
}

function isLightColor(hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return (r * 299 + g * 587 + b * 114) / 1000 > 128;
}

function medalClass(rank) {
    if (rank === 1) return 'medal-gold';
    if (rank === 2) return 'medal-silver';
    if (rank === 3) return 'medal-bronze';
    return '';
}

// Build a .hs-row element for a share
function renderHsRow(share, { rank } = {}) {
    const { color, shape, borderStyle } = getLevelStyle(share.level);
    const borderColor = borderStyle
        ? borderStyle.split(' ').pop()
        : darkenHex(color, 0.7);
    const textColor = isLightColor(color) ? '#000' : '#fff';

    const row = document.createElement('div');
    row.className = 'hs-row';
    row.dataset.shareId = share.share_id;
    row.dataset.level = share.level;
    row.dataset.timestamp = share.submitted_at;

    const mc = rank !== undefined ? medalClass(rank) : '';
    const rankHtml = rank !== undefined
        ? `<span class="hs-rank${mc ? ' ' + mc : ''}">#${rank}</span>`
        : '';
    const timestamp = formatTimestamp(share.submitted_at);
    const userDisplay = share.tag
        ? truncateUsername(share.tag)
        : (share.username ? truncateUsername(share.username) : 'me');
    const hashDisplay = truncateHash(share.share_hash);
    const badgeInner = shape === 'diamond'
        ? `<span>${Math.floor(share.level)}</span>`
        : `${Math.floor(share.level)}`;

    row.innerHTML = `
        ${rankHtml}
        <div class="hs-info">
            <div class="hs-top-line">
                <span class="hs-user">${userDisplay}</span>
                <span class="hs-time share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
            </div>
            <div class="hs-hash">${hashDisplay}</div>
        </div>
        <div class="hs-badge shape-${shape}${mc ? ' ' + mc : ''}" style="background-color: ${color}; border-color: ${borderColor}; color: ${textColor};">${badgeInner}</div>
    `;

    row.addEventListener('click', () => {
        window.location.href = `/hash-validator/${share.share_id}`;
    });

    return row;
}

// Build a .share-card banner for personal best (block or non-block styled)
function renderPersonalBest(share) {
    const { color, shape, borderStyle } = getLevelStyle(share.level);
    const borderAttr = borderStyle ? `border: ${borderStyle};` : '';
    const userDisplay = share.tag ? truncateUsername(share.tag) : 'me';
    const timestamp = formatTimestamp(share.submitted_at);
    const cardClass = share.is_block ? 'share-card block' : 'share-card personal-best';
    const subtitle = share.is_block ? 'BLOCK FOUND · ALL TIME HIGH' : 'ALL TIME HIGH';

    const card = document.createElement('div');
    card.className = cardClass;
    card.dataset.shareId = share.share_id;
    card.innerHTML = `
        <div class="share-card-header">
            <div class="share-header-top">
                <span class="share-timestamp" data-timestamp="${share.submitted_at}">${timestamp}</span>
                <span class="share-user-tag">${userDisplay}</span>
                <span class="share-user-tag">${subtitle}</span>
            </div>
            <div class="share-level-badge shape-${shape}" style="background-color: ${color}; ${borderAttr}">
                ${Math.floor(share.level)}
            </div>
        </div>
        <div class="share-card-footer">
            <span class="share-hash">${truncateHash(share.share_hash)}</span>
        </div>
    `;
    card.addEventListener('click', () => {
        window.location.href = `/hash-validator/${share.share_id}`;
    });
    return card;
}

// Render shares as hs-rows into mobile feed
function renderShareCards(shares, append) {
    const container = document.getElementById('share-cards-container');
    if (!append) container.innerHTML = '';
    shares.forEach(share => {
        const row = renderHsRow(share, {});
        container.appendChild(row);
        observeCard(row);
    });
}

// Setup infinite scroll listener
function setupInfiniteScroll() {
    window.addEventListener('scroll', () => {
        const scrollHeight = document.documentElement.scrollHeight;
        const scrollTop = document.documentElement.scrollTop;
        const clientHeight = document.documentElement.clientHeight;
        if (scrollTop + clientHeight >= scrollHeight - 200 && !isLoading && hasMore) {
            loadShares(true);
        }
    });
}

// Show/hide loading indicator (mobile)
function showLoading(show) {
    const indicator = document.getElementById('shares-loading-indicator');
    if (indicator) indicator.style.display = show ? 'block' : 'none';
}

// Show/hide empty state (mobile)
function showEmptyState(show) {
    const emptyState = document.getElementById('shares-empty-state');
    const container = document.getElementById('share-cards-container');
    if (!emptyState || !container) return;
    if (show) {
        let message = 'No shares yet';
        if (currentMode === 'best-24h') message = 'No shares in the last 24 hours';
        emptyState.querySelector('p').textContent = message;
        emptyState.style.display = 'block';
        container.style.display = 'none';
    } else {
        emptyState.style.display = 'none';
        container.style.display = 'flex';
    }
}

// ── FLIP animation helper ─────────────────────────────────────────────────────
// Inserts newRow into container, animating displaced siblings downward
// and fading the new row in.
function animateInsert(container, newRow, insertBefore) {
    const existingRows = [...container.querySelectorAll('.hs-row')];
    const beforeTop = existingRows.map(el => el.getBoundingClientRect().top);

    // Insert invisibly
    newRow.style.opacity = '0';
    if (insertBefore) {
        container.insertBefore(newRow, insertBefore);
    } else {
        container.appendChild(newRow);
    }

    // Force layout recalc
    newRow.offsetHeight;

    // FLIP: animate siblings that shifted
    existingRows.forEach((el, i) => {
        const delta = beforeTop[i] - el.getBoundingClientRect().top;
        if (Math.abs(delta) > 0.5) {
            el.style.transform = `translateY(${delta}px)`;
            el.style.transition = 'none';
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    el.style.transition = 'transform 0.22s ease';
                    el.style.transform = '';
                    el.addEventListener('transitionend', function h() {
                        el.style.transform = '';
                        el.style.transition = '';
                        el.removeEventListener('transitionend', h);
                    });
                });
            });
        }
    });

    // Fade in new row
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            newRow.style.transition = 'opacity 0.25s ease';
            newRow.style.opacity = '1';
            newRow.addEventListener('transitionend', function h() {
                newRow.style.opacity = '';
                newRow.style.transition = '';
                newRow.removeEventListener('transitionend', h);
            });
        });
    });
}

// Re-number rank labels and medal classes after a column changes
function updateColumnRanks(container) {
    container.querySelectorAll('.hs-row').forEach((row, index) => {
        const rank = index + 1;
        const mc = medalClass(rank);
        const rankEl = row.querySelector('.hs-rank');
        if (rankEl) {
            rankEl.textContent = `#${rank}`;
            rankEl.className = 'hs-rank' + (mc ? ` ${mc}` : '');
        }
        const badgeEl = row.querySelector('.hs-badge');
        if (badgeEl) {
            badgeEl.classList.remove('medal-gold', 'medal-silver', 'medal-bronze');
            if (mc) badgeEl.classList.add(mc);
        }
    });
}

// SSE callback for new shares
function handleNewShare(share) {
    console.log(`handleNewShare: share ${share.share_id}, level=${share.level}, mode=${currentMode}`);

    // ── Mobile feed ──────────────────────────────────────────────────────────
    const container = document.getElementById('share-cards-container');
    if (container) {
        let mobileIsDuplicate = false;
        for (const row of container.querySelectorAll('.hs-row')) {
            if (row.dataset.shareId === String(share.share_id)) {
                mobileIsDuplicate = true;
                break;
            }
        }

        if (!mobileIsDuplicate) {
            showEmptyState(false);
            const row = renderHsRow(share, {});
            const existingRows = [...container.querySelectorAll('.hs-row')];

            let insertBefore = null;
            let insertPosition = 0;

            if (currentMode === 'recent') {
                insertBefore = container.firstChild;
            } else {
                for (const existing of existingRows) {
                    const existingLevel = parseFloat(existing.dataset.level);
                    const existingTimestamp = existing.dataset.timestamp;
                    if (share.level > existingLevel ||
                        (share.level === existingLevel && share.submitted_at > existingTimestamp)) {
                        insertBefore = existing;
                        break;
                    }
                    insertPosition++;
                }
            }

            const shouldInsert = currentMode === 'recent' || hasLoadedAllShares || insertPosition < existingRows.length;
            if (!shouldInsert) {
                console.log(`Discarding share ${share.share_id} - ranks below loaded set`);
                lastEventId = share.share_id;
            } else {
                row.classList.add('share-card-new');
                if (insertBefore) {
                    container.insertBefore(row, insertBefore);
                } else {
                    container.appendChild(row);
                }
                observeCard(row);
                setTimeout(() => row.classList.remove('share-card-new'), 400);
                currentOffset++;
            }
        }
    }

    // ── Desktop updates ──────────────────────────────────────────────────────
    if (!isDesktop) return;

    // Recent column
    const recentCol = document.getElementById('desktop-recent-col');
    if (recentCol) {
        let isDup = false;
        for (const row of recentCol.querySelectorAll('.hs-row')) {
            if (row.dataset.shareId === String(share.share_id)) { isDup = true; break; }
        }
        if (!isDup) {
            const row = renderHsRow(share, {});
            animateInsert(recentCol, row, recentCol.firstChild);
            observeCard(row);
        }
    }

    // My Best column
    updateDesktopMyBest(share);

    // Personal best banner
    if (share.level > currentPersonalBestLevel) {
        currentPersonalBestLevel = share.level;
        const pbContainer = document.getElementById('desktop-personal-best');
        if (pbContainer) {
            pbContainer.innerHTML = '';
            const card = renderPersonalBest(share);
            pbContainer.appendChild(card);
            observeCard(card);
        }
    }

    // Global highscores
    updateDesktopHighscoresIfNeeded(share);
}

// ── Desktop View ─────────────────────────────────────────────────────────────

async function initDesktopView() {
    await Promise.all([
        loadDesktopPersonalBest(),
        loadDesktopRecent(),
        loadDesktopMyBest(currentMyBestPeriod),
        loadDesktopHighscores(currentHsPeriod),
        updateDesktopDifficulty(),
    ]);
    setupDesktopToggles();
}

async function loadDesktopPersonalBest() {
    try {
        const response = await fetch('/api/users/me/shares/load?mode=best-all-time&limit=1');
        if (!response.ok) return;
        const data = await response.json();
        const container = document.getElementById('desktop-personal-best');
        if (!container) return;
        container.innerHTML = '';
        if (data.shares.length > 0) {
            currentPersonalBestLevel = data.shares[0].level;
            const card = renderPersonalBest(data.shares[0]);
            container.appendChild(card);
            observeCard(card);
        }
    } catch (error) {
        console.error('Error loading desktop personal best:', error);
    }
}

async function loadDesktopRecent() {
    try {
        const response = await fetch('/api/users/me/shares/load?mode=recent&limit=20');
        if (!response.ok) return;
        const data = await response.json();
        const container = document.getElementById('desktop-recent-col');
        if (!container) return;
        container.innerHTML = '';
        data.shares.forEach(share => {
            const row = renderHsRow(share, {});
            container.appendChild(row);
            observeCard(row);
        });
    } catch (error) {
        console.error('Error loading desktop recent:', error);
    }
}

async function loadDesktopMyBest(period) {
    try {
        const response = await fetch(`/api/users/me/shares/load?mode=${period}&limit=20`);
        if (!response.ok) return;
        const data = await response.json();
        const container = document.getElementById('desktop-mybest-col');
        if (!container) return;
        container.innerHTML = '';
        data.shares.forEach((share, index) => {
            const row = renderHsRow(share, { rank: index + 1 });
            container.appendChild(row);
            observeCard(row);
        });
    } catch (error) {
        console.error('Error loading desktop my best:', error);
    }
}

async function loadDesktopHighscores(period) {
    try {
        const endpoint = period === '24h' ? '/api/highscores/24h' : '/api/highscores/all-time';
        const response = await fetch(endpoint);
        if (!response.ok) return;
        const data = await response.json();
        const container = document.getElementById('desktop-highscores-col');
        if (!container) return;
        container.innerHTML = '';
        data.shares.forEach((share, index) => {
            const row = renderHsRow(share, { rank: index + 1 });
            container.appendChild(row);
            observeCard(row);
        });
    } catch (error) {
        console.error('Error loading desktop highscores:', error);
    }
}

// Insert a new share into the my-best column at the right rank position
function updateDesktopMyBest(share) {
    const container = document.getElementById('desktop-mybest-col');
    if (!container) return;

    // For 24h period, check recency
    if (currentMyBestPeriod === 'best-24h') {
        const now = Math.floor(Date.now() / 1000);
        if (share.submitted_at < now - 86400) return;
    }

    // Dedup
    for (const row of container.querySelectorAll('.hs-row')) {
        if (row.dataset.shareId === String(share.share_id)) return;
    }

    const existingRows = [...container.querySelectorAll('.hs-row')];
    let insertBefore = null;
    let insertPosition = 0;

    for (const existing of existingRows) {
        const existingLevel = parseFloat(existing.dataset.level);
        const existingTimestamp = existing.dataset.timestamp;
        if (share.level > existingLevel ||
            (share.level === existingLevel && share.submitted_at > existingTimestamp)) {
            insertBefore = existing;
            break;
        }
        insertPosition++;
    }

    // Don't push beyond the display limit
    if (insertPosition >= 20) return;

    const row = renderHsRow(share, { rank: insertPosition + 1 });
    animateInsert(container, row, insertBefore);
    observeCard(row);
    updateColumnRanks(container);
}

// Reload global highscores if the new share might rank
function updateDesktopHighscoresIfNeeded(share) {
    const container = document.getElementById('desktop-highscores-col');
    if (!container) return;

    // For 24h period, check recency
    if (currentHsPeriod === '24h') {
        const now = Math.floor(Date.now() / 1000);
        if (share.submitted_at < now - 86400) return;
    }

    const existingRows = [...container.querySelectorAll('.hs-row')];
    let wouldRank = existingRows.length < 5;
    if (!wouldRank) {
        const lowestLevel = parseFloat(existingRows[existingRows.length - 1].dataset.level || '0');
        if (share.level >= lowestLevel) wouldRank = true;
    }

    if (wouldRank) {
        loadDesktopHighscores(currentHsPeriod);
    }
}

function setupDesktopToggles() {
    document.querySelectorAll('[data-mybest-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-mybest-period]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentMyBestPeriod = btn.dataset.mybestPeriod;
            loadDesktopMyBest(currentMyBestPeriod);
        });
    });

    document.querySelectorAll('[data-hs-period]').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('[data-hs-period]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentHsPeriod = btn.dataset.hsPeriod;
            loadDesktopHighscores(currentHsPeriod);
        });
    });
}

async function updateDesktopDifficulty() {
    try {
        const response = await fetch('/api/traffic/status');
        if (!response.ok) return;
        const data = await response.json();
        const badge = document.getElementById('desktop-difficulty-badge');
        const text = document.getElementById('desktop-difficulty-text');
        if (!badge || !text) return;
        if (!data.traffic_level || data.traffic_level === 'normal' || data.traffic_level === 'low') {
            badge.style.display = 'none';
        } else {
            badge.style.display = 'flex';
            text.textContent = data.traffic_level === 'elevated' ? 'Difficulty Elevated' : 'Difficulty High';
        }
    } catch (error) {
        console.error('Error loading desktop difficulty:', error);
    }
}
