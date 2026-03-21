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

const isDesktop = window.matchMedia('(min-width: 1024px)').matches;

// Initialize on page load
document.addEventListener('DOMContentLoaded', async () => {
    restoreSavedMode();
    await loadUserData();
    await loadShares();
    setupInfiniteScroll();
    setupToggleButtons();
    initSharedSSE(handleNewShare, null, handleAchievementUnlock);
    startTimestampRefresh();

    if (isDesktop) {
        initDesktopView();
        loadAchievements();
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

    // Global highscores
    updateDesktopHighscoresIfNeeded(share);
}

// ── Desktop View ─────────────────────────────────────────────────────────────

async function initDesktopView() {
    await Promise.all([
        loadDesktopRecent(),
        loadDesktopMyBest(currentMyBestPeriod),
        loadDesktopHighscores(currentHsPeriod),
        updateDesktopDifficulty(),
    ]);
    setupDesktopToggles();
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

// ── Achievements ──────────────────────────────────────────────────────────────

// Mirrors the Python REGISTRY — category → icon shape mapping
const ACHIEVEMENT_CATEGORY_SHAPE = {
    grind:    'square',
    level:    null,     // determined by level tier in registry
    meme:     'circle',
    peak:     'diamond',
    streak:   'hexagon',
    longevity:'square',
    hash:     'diamond',
    seasonal: 'circle',
};

// Rarity → border color (for icon tint)
const RARITY_COLOR = {
    common:    '#888',
    uncommon:  '#56d364',
    rare:      '#58a6ff',
    epic:      '#bc8cff',
    legendary: '#f7931a',
};

// Full client-side registry mirroring achievements.py REGISTRY
const ACHIEVEMENT_REGISTRY = [
    // Grind
    { id: 'grind_purchased_100',   name: 'Proof of Purchase', description: 'Purchase 100 shares total',       category: 'grind',    rarity: 'common',    secret: false },
    { id: 'grind_purchased_1k',    name: 'Stack Builder',     description: 'Purchase 1,000 shares total',    category: 'grind',    rarity: 'uncommon',  secret: false },
    { id: 'grind_purchased_10k',   name: 'Deep Digs',         description: 'Purchase 10,000 shares total',   category: 'grind',    rarity: 'rare',      secret: false },
    { id: 'grind_purchased_100k',  name: 'Whale',             description: 'Purchase 100,000 shares total',  category: 'grind',    rarity: 'epic',      secret: false },
    { id: 'grind_consumed_100',    name: 'In the Pool',       description: 'Consume 100 shares total',       category: 'grind',    rarity: 'common',    secret: false },
    { id: 'grind_consumed_1k',     name: 'Seasoned',          description: 'Consume 1,000 shares total',     category: 'grind',    rarity: 'uncommon',  secret: false },
    { id: 'grind_consumed_10k',    name: 'The Long Haul',     description: 'Consume 10,000 shares total',    category: 'grind',    rarity: 'rare',      secret: false },
    { id: 'grind_consumed_100k',   name: 'Iron Pickaxe',      description: 'Consume 100,000 shares total',   category: 'grind',    rarity: 'epic',      secret: false },
    { id: 'grind_big_batch',       name: 'All In',            description: 'Purchase 1,000+ shares at once', category: 'grind',    rarity: 'uncommon',  secret: false },
    // Level milestones
    { id: 'level_50',   name: 'Spark',               description: 'Reach level 50',   category: 'level', rarity: 'common',    secret: false },
    { id: 'level_60',   name: 'Flame',               description: 'Reach level 60',   category: 'level', rarity: 'common',    secret: false },
    { id: 'level_70',   name: 'Blaze',               description: 'Reach level 70',   category: 'level', rarity: 'uncommon',  secret: false },
    { id: 'level_80',   name: 'Inferno',             description: 'Reach level 80',   category: 'level', rarity: 'uncommon',  secret: false },
    { id: 'level_90',   name: 'Orbital',             description: 'Reach level 90',   category: 'level', rarity: 'uncommon',  secret: false },
    { id: 'level_100',  name: 'To The Moon',         description: 'Reach level 100',  category: 'level', rarity: 'uncommon',  secret: false },
    { id: 'level_110',  name: 'Interplanetary',      description: 'Reach level 110',  category: 'level', rarity: 'rare',      secret: false },
    { id: 'level_120',  name: 'Solar',               description: 'Reach level 120',  category: 'level', rarity: 'rare',      secret: false },
    { id: 'level_130',  name: 'Stellar',             description: 'Reach level 130',  category: 'level', rarity: 'rare',      secret: false },
    { id: 'level_140',  name: 'Galactic',            description: 'Reach level 140',  category: 'level', rarity: 'rare',      secret: false },
    { id: 'level_150',  name: 'Intergalactic',       description: 'Reach level 150',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_160',  name: 'Deep Space',          description: 'Reach level 160',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_170',  name: 'Quartz',              description: 'Reach level 170',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_180',  name: 'Amethyst',            description: 'Reach level 180',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_190',  name: 'Topaz',               description: 'Reach level 190',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_200',  name: 'Sapphire',            description: 'Reach level 200',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_210',  name: 'Ruby',                description: 'Reach level 210',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_220',  name: 'Emerald',             description: 'Reach level 220',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_230',  name: 'Diamond',             description: 'Reach level 230',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_240',  name: 'Starfire',            description: 'Reach level 240',  category: 'level', rarity: 'epic',      secret: false },
    { id: 'level_250',  name: 'Honeycomb',           description: 'Reach level 250',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_260',  name: 'Sacred Geometry',     description: 'Reach level 260',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_270',  name: 'Crystalline',         description: 'Reach level 270',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_280',  name: 'The Pattern',         description: 'Reach level 280',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_290',  name: 'Transcendent',        description: 'Reach level 290',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_300',  name: 'GOD MODE',            description: 'Reach level 300',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_310',  name: 'Omniscient',          description: 'Reach level 310',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_320',  name: 'Absolute',            description: 'Reach level 320',  category: 'level', rarity: 'legendary', secret: false },
    { id: 'level_330',  name: 'The Limit Does Not Exist', description: 'Reach level 330', category: 'level', rarity: 'legendary', secret: false },
    // Meme
    { id: 'meme_42',   name: 'The Answer',      description: 'Hit exactly level 42',  category: 'meme', rarity: 'rare',      secret: false },
    { id: 'meme_69',   name: 'Nice',            description: 'Hit exactly level 69',  category: 'meme', rarity: 'uncommon',  secret: false },
    { id: 'meme_99',   name: 'Max Level',       description: 'Hit exactly level 99',  category: 'meme', rarity: 'rare',      secret: false },
    { id: 'meme_126',  name: 'Barrows Gloves',  description: 'Hit exactly level 126', category: 'meme', rarity: 'epic',      secret: false },
    // Peak
    { id: 'peak_chart_topper',  name: 'Chart Topper',   description: 'Appear in top 5 highscores (24h)',      category: 'peak', rarity: 'epic',      secret: false },
    { id: 'peak_hall_of_fame',  name: 'Hall of Fame',   description: 'Appear in top 5 highscores (all-time)', category: 'peak', rarity: 'epic',      secret: false },
    { id: 'peak_pole_position', name: 'Pole Position',  description: 'Reach #1 position',                     category: 'peak', rarity: 'legendary', secret: false },
    { id: 'peak_fingertips',    name: 'Fingertips',     description: 'Within 5 levels of block target',       category: 'peak', rarity: 'rare',      secret: false },
    { id: 'peak_eureka',        name: 'Eureka',         description: 'Find a block',                          category: 'peak', rarity: 'legendary', secret: false },
    // Streaks
    { id: 'streak_cold_10',         name: 'Cold Streak',      description: '10 consecutive shares below level 30',    category: 'streak', rarity: 'common',    secret: false },
    { id: 'streak_drought_25',      name: 'Drought',           description: '25 consecutive shares below level 30',    category: 'streak', rarity: 'uncommon',  secret: false },
    { id: 'streak_sahara_50',       name: 'Sahara',            description: '50 consecutive shares below level 30',    category: 'streak', rarity: 'rare',      secret: false },
    { id: 'streak_on_fire_5',       name: 'On Fire',           description: '5 consecutive shares above level 50',     category: 'streak', rarity: 'uncommon',  secret: false },
    { id: 'streak_white_hot_10',    name: 'White Hot',         description: '10 consecutive shares above level 50',    category: 'streak', rarity: 'rare',      secret: false },
    { id: 'streak_unstoppable_20',  name: 'Unstoppable',       description: '20 consecutive shares above level 50',    category: 'streak', rarity: 'epic',      secret: false },
    { id: 'streak_solar_flare_5',   name: 'Solar Flare',       description: '5 consecutive shares above level 100',    category: 'streak', rarity: 'rare',      secret: false },
    { id: 'streak_supernova_10',    name: 'Supernova',         description: '10 consecutive shares above level 100',   category: 'streak', rarity: 'epic',      secret: false },
    { id: 'streak_untouchable_20',  name: 'Untouchable',       description: '20 consecutive shares above level 100',   category: 'streak', rarity: 'legendary', secret: false },
    { id: 'streak_feast_or_famine', name: 'Feast or Famine',   description: 'Same day: share below 30 AND above 100',  category: 'streak', rarity: 'uncommon',  secret: false },
    { id: 'streak_hat_trick',       name: 'Hat Trick',         description: 'Same level 3 times in a row',             category: 'streak', rarity: 'uncommon',  secret: false },
    { id: 'streak_like_clockwork',  name: 'Like Clockwork',    description: 'Same level 5 times in a row',             category: 'streak', rarity: 'rare',      secret: false },
    { id: 'streak_broken_record',   name: 'Broken Record',     description: 'Same level 7 times in a row',             category: 'streak', rarity: 'epic',      secret: false },
    // Longevity
    { id: 'longevity_7d',              name: 'Settled In',     description: 'Account is 7 days old',            category: 'longevity', rarity: 'common',    secret: false },
    { id: 'longevity_30d',             name: 'Regular',        description: 'Account is 30 days old',           category: 'longevity', rarity: 'common',    secret: false },
    { id: 'longevity_180d',            name: 'Committed',      description: 'Account is 180 days old',          category: 'longevity', rarity: 'uncommon',  secret: false },
    { id: 'longevity_365d',            name: 'Veteran',        description: 'Account is 365 days old',          category: 'longevity', rarity: 'rare',      secret: false },
    { id: 'longevity_habit_4w',        name: 'Habit',          description: 'Purchased in 4 different weeks',   category: 'longevity', rarity: 'common',    secret: false },
    { id: 'longevity_dedicated_12w',   name: 'Dedicated',      description: 'Purchased in 12 different weeks',  category: 'longevity', rarity: 'uncommon',  secret: false },
    { id: 'longevity_true_believer_52w', name: 'True Believer', description: 'Purchased in 52 different weeks', category: 'longevity', rarity: 'rare',      secret: false },
    { id: 'longevity_solvent_1d',      name: 'Solvent',        description: 'Balance never empty for 1 day',    category: 'longevity', rarity: 'common',    secret: false },
    { id: 'longevity_funded_7d',       name: 'Funded',         description: 'Balance never empty for 7 days',   category: 'longevity', rarity: 'uncommon',  secret: false },
    { id: 'longevity_sustained_30d',   name: 'Sustained',      description: 'Balance never empty for 30 days',  category: 'longevity', rarity: 'rare',      secret: false },
    { id: 'longevity_ironclad_180d',   name: 'Ironclad',       description: 'Balance never empty for 180 days', category: 'longevity', rarity: 'epic',      secret: false },
    // Hash easter eggs
    { id: 'hash_bada55', name: 'Badass',            description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_dead',   name: 'Dead Block',         description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_face',   name: 'Face in the Crowd',  description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_cafe',   name: 'Hash Café',           description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_beef',   name: 'Beefy',               description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_c0de',   name: 'Code Found',          description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_f00d',   name: 'Hash Browns',         description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_600d',   name: 'Good Vibes',          description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_fade',   name: 'Fading Signal',       description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_feed',   name: 'Feed the Machine',    description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_c001',   name: 'Cool Runnings',       description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_deed',   name: 'Done Deed',           description: '???', category: 'hash', rarity: 'rare', secret: true },
    { id: 'hash_abba',   name: 'Dancing Queen',       description: '???', category: 'hash', rarity: 'rare', secret: true },
    // Seasonal
    { id: 'seasonal_genesis',     name: 'Genesis',     description: 'Mine on January 3rd',         category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_white_paper', name: 'White Paper', description: 'Mine on October 31st',        category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_pizza_day',   name: 'Pizza Day',   description: 'Mine on May 22nd',            category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_christmas',   name: 'Christmas',   description: 'Mine on December 25th',       category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_new_year',    name: 'New Year',    description: 'Mine on January 1st',         category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_halving',     name: 'The Halving', description: 'Mine within 24h of a halving', category: 'seasonal', rarity: 'legendary', secret: false },
];

// Get shape for achievement icon based on category (level uses tier shape)
function getAchievementShape(def) {
    if (def.category === 'level') {
        const threshold = parseInt(def.id.split('_')[1], 10);
        const tier = Math.floor((threshold - 10) / 80);
        const shapes = ['square', 'circle', 'diamond', 'hexagon'];
        return shapes[Math.min(tier, 3)];
    }
    return ACHIEVEMENT_CATEGORY_SHAPE[def.category] || 'square';
}

// Load and render the achievements grid
async function loadAchievements() {
    try {
        const response = await fetch('/api/users/me/achievements');
        if (!response.ok) return;
        const data = await response.json();
        renderAchievementGrid(data.achievements || []);
    } catch (error) {
        console.error('Error loading achievements:', error);
    }
}

function renderAchievementGrid(unlockedList) {
    const grid = document.getElementById('achievements-grid');
    const countEl = document.getElementById('achievements-count');
    if (!grid) return;

    const unlockedSet = new Set(unlockedList.map(u => u.id));
    const visibleDefs = ACHIEVEMENT_REGISTRY.filter(def => !def.secret || unlockedSet.has(def.id));

    grid.innerHTML = '';
    visibleDefs.forEach(def => {
        const badge = renderAchievementBadge(def, unlockedSet.has(def.id));
        grid.appendChild(badge);
    });

    if (countEl) {
        const totalVisible = ACHIEVEMENT_REGISTRY.filter(def => !def.secret).length;
        countEl.textContent = `${unlockedSet.size} / ${totalVisible}`;
    }
}

function renderAchievementBadge(def, isUnlocked) {
    const badge = document.createElement('div');
    badge.className = `achievement-badge ${isUnlocked ? 'unlocked' : 'locked'}${def.secret ? ' secret' : ''}`;
    badge.dataset.achievementId = def.id;
    badge.dataset.rarity = def.rarity;
    badge.title = isUnlocked ? `${def.name}: ${def.description}` : (def.secret ? '???' : def.name);

    const shape = getAchievementShape(def);
    const color = isUnlocked ? RARITY_COLOR[def.rarity] : '#444';
    const darkerColor = isUnlocked
        ? color.replace(/^#/, '')
              .match(/.{2}/g)
              .map(c => Math.round(parseInt(c, 16) * 0.6).toString(16).padStart(2, '0'))
              .join('')
        : '222';

    const icon = document.createElement('div');
    icon.className = `achievement-icon hs-badge shape-${shape}`;
    icon.style.backgroundColor = color;
    icon.style.borderColor = `#${darkerColor}`;
    icon.style.color = '#000';
    icon.style.fontSize = '8px';
    icon.textContent = isUnlocked ? '' : (def.secret ? '?' : '');

    const name = document.createElement('div');
    name.className = 'achievement-name';
    name.textContent = def.secret && !isUnlocked ? '???' : def.name;

    badge.appendChild(icon);
    badge.appendChild(name);
    return badge;
}

function handleAchievementUnlock(data) {
    const grid = document.getElementById('achievements-grid');
    if (!grid) return;

    const ach_id = data.achievement_id;

    // Re-render if badge exists (update locked → unlocked)
    const existing = grid.querySelector(`[data-achievement-id="${ach_id}"]`);
    const def = ACHIEVEMENT_REGISTRY.find(d => d.id === ach_id);
    if (!def) return;

    if (existing) {
        const newBadge = renderAchievementBadge(def, true);
        newBadge.classList.add('just-unlocked');
        grid.replaceChild(newBadge, existing);
        setTimeout(() => newBadge.classList.remove('just-unlocked'), 600);
    } else {
        // Secret badge that wasn't shown — add it
        const newBadge = renderAchievementBadge(def, true);
        newBadge.classList.add('just-unlocked');
        grid.appendChild(newBadge);
        setTimeout(() => newBadge.classList.remove('just-unlocked'), 600);
    }

    // Update count
    const countEl = document.getElementById('achievements-count');
    if (countEl) {
        const current = countEl.textContent.match(/(\d+)\s*\/\s*(\d+)/);
        if (current) {
            const newCount = parseInt(current[1]) + 1;
            countEl.textContent = `${newCount} / ${current[2]}`;
        }
    }
}
