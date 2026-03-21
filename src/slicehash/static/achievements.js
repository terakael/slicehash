// Achievements page JavaScript

const ACHIEVEMENT_CATEGORY_SHAPE = {
    grind:    'square',
    level:    null,      // determined by level tier
    meme:     'circle',
    peak:     'diamond',
    streak:   'hexagon',
    longevity:'square',
    hash:     'diamond',
    seasonal: 'circle',
};

const RARITY_COLOR = {
    common:    '#888',
    uncommon:  '#56d364',
    rare:      '#58a6ff',
    epic:      '#bc8cff',
    legendary: '#f7931a',
};

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
    { id: 'seasonal_genesis',     name: 'Genesis',     description: 'Mine on January 3rd',          category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_white_paper', name: 'White Paper', description: 'Mine on October 31st',         category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_pizza_day',   name: 'Pizza Day',   description: 'Mine on May 22nd',             category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_christmas',   name: 'Christmas',   description: 'Mine on December 25th',        category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_new_year',    name: 'New Year',    description: 'Mine on January 1st',          category: 'seasonal', rarity: 'epic',      secret: false },
    { id: 'seasonal_halving',     name: 'The Halving', description: 'Mine within 24h of a halving', category: 'seasonal', rarity: 'legendary', secret: false },
];

function getAchievementShape(def) {
    if (def.category === 'level') {
        const threshold = parseInt(def.id.split('_')[1], 10);
        const tier = Math.floor((threshold - 10) / 80);
        const shapes = ['square', 'circle', 'diamond', 'hexagon'];
        return shapes[Math.min(tier, 3)];
    }
    return ACHIEVEMENT_CATEGORY_SHAPE[def.category] || 'square';
}

function renderAchievementBadge(def, isUnlocked) {
    const badge = document.createElement('div');
    badge.className = `achievement-badge ${isUnlocked ? 'unlocked' : 'locked'}${def.secret ? ' secret' : ''}`;
    badge.dataset.achievementId = def.id;
    badge.dataset.rarity = def.rarity;
    badge.title = isUnlocked ? `${def.name}: ${def.description}` : (def.secret ? '???' : def.description);

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
    icon.style.fontSize = '9px';
    icon.textContent = '';

    const name = document.createElement('div');
    name.className = 'achievement-name';
    name.textContent = def.secret && !isUnlocked ? '???' : def.name;

    badge.appendChild(icon);
    badge.appendChild(name);
    return badge;
}

function renderAchievementGrid(unlockedList) {
    const grid = document.getElementById('achievements-grid');
    const countEl = document.getElementById('achievements-count');
    if (!grid) return;

    const unlockedSet = new Set(unlockedList.map(u => u.id));
    const visibleDefs = ACHIEVEMENT_REGISTRY.filter(def => !def.secret || unlockedSet.has(def.id));

    grid.innerHTML = '';
    visibleDefs.forEach(def => {
        grid.appendChild(renderAchievementBadge(def, unlockedSet.has(def.id)));
    });

    if (countEl) {
        const totalVisible = ACHIEVEMENT_REGISTRY.filter(def => !def.secret).length;
        countEl.textContent = `${unlockedSet.size} / ${totalVisible}`;
    }
}

function handleAchievementUnlock(data) {
    const grid = document.getElementById('achievements-grid');
    if (!grid) return;

    const achId = data.achievement_id;
    const def = ACHIEVEMENT_REGISTRY.find(d => d.id === achId);
    if (!def) return;

    const existing = grid.querySelector(`[data-achievement-id="${achId}"]`);
    const newBadge = renderAchievementBadge(def, true);
    newBadge.classList.add('just-unlocked');

    if (existing) {
        grid.replaceChild(newBadge, existing);
    } else {
        grid.appendChild(newBadge);
    }
    setTimeout(() => newBadge.classList.remove('just-unlocked'), 600);

    const countEl = document.getElementById('achievements-count');
    if (countEl) {
        const match = countEl.textContent.match(/(\d+)\s*\/\s*(\d+)/);
        if (match) {
            countEl.textContent = `${parseInt(match[1]) + 1} / ${match[2]}`;
        }
    }
}

document.addEventListener('DOMContentLoaded', async () => {
    try {
        const response = await fetch('/api/users/me/achievements');
        if (!response.ok) return;
        const data = await response.json();
        renderAchievementGrid(data.achievements || []);
    } catch (error) {
        console.error('Error loading achievements:', error);
    }

    initSharedSSE(null, null, handleAchievementUnlock);
});
