"""Achievement system for SliceHash.

Tracks and awards achievements based on mining activity, purchases, time, and hash curiosities.
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class AchievementDef:
    id: str
    name: str
    description: str
    category: str   # grind|level|meme|peak|streak|longevity|hash|seasonal
    rarity: str     # common|uncommon|rare|epic|legendary
    secret: bool = False


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, AchievementDef] = {}

def _r(ach: AchievementDef):
    REGISTRY[ach.id] = ach
    return ach

# Grind
_r(AchievementDef('grind_purchased_100',   'Proof of Purchase', 'Purchase 100 shares total',      'grind', 'common'))
_r(AchievementDef('grind_purchased_1k',    'Stack Builder',     'Purchase 1,000 shares total',    'grind', 'uncommon'))
_r(AchievementDef('grind_purchased_10k',   'Deep Digs',         'Purchase 10,000 shares total',   'grind', 'rare'))
_r(AchievementDef('grind_purchased_100k',  'Whale',             'Purchase 100,000 shares total',  'grind', 'epic'))
_r(AchievementDef('grind_consumed_100',    'In the Pool',       'Consume 100 shares total',       'grind', 'common'))
_r(AchievementDef('grind_consumed_1k',     'Seasoned',          'Consume 1,000 shares total',     'grind', 'uncommon'))
_r(AchievementDef('grind_consumed_10k',    'The Long Haul',     'Consume 10,000 shares total',    'grind', 'rare'))
_r(AchievementDef('grind_consumed_100k',   'Iron Pickaxe',      'Consume 100,000 shares total',   'grind', 'epic'))
_r(AchievementDef('grind_big_batch',       'All In',            'Purchase 1,000+ shares at once', 'grind', 'uncommon'))

# Level milestones — Square tier (50–80)
_r(AchievementDef('level_50',   'Spark',    'Reach level 50',    'level', 'common'))
_r(AchievementDef('level_60',   'Flame',    'Reach level 60',    'level', 'common'))
_r(AchievementDef('level_70',   'Blaze',    'Reach level 70',    'level', 'uncommon'))
_r(AchievementDef('level_80',   'Inferno',  'Reach level 80',    'level', 'uncommon'))

# Level milestones — Circle tier (90–160)
_r(AchievementDef('level_90',   'Orbital',       'Reach level 90',   'level', 'uncommon'))
_r(AchievementDef('level_100',  'To The Moon',   'Reach level 100',  'level', 'uncommon'))
_r(AchievementDef('level_110',  'Interplanetary','Reach level 110',  'level', 'rare'))
_r(AchievementDef('level_120',  'Solar',         'Reach level 120',  'level', 'rare'))
_r(AchievementDef('level_130',  'Stellar',       'Reach level 130',  'level', 'rare'))
_r(AchievementDef('level_140',  'Galactic',      'Reach level 140',  'level', 'rare'))
_r(AchievementDef('level_150',  'Intergalactic', 'Reach level 150',  'level', 'epic'))
_r(AchievementDef('level_160',  'Deep Space',    'Reach level 160',  'level', 'epic'))

# Level milestones — Diamond tier (170–240)
_r(AchievementDef('level_170',  'Quartz',    'Reach level 170',  'level', 'epic'))
_r(AchievementDef('level_180',  'Amethyst',  'Reach level 180',  'level', 'epic'))
_r(AchievementDef('level_190',  'Topaz',     'Reach level 190',  'level', 'epic'))
_r(AchievementDef('level_200',  'Sapphire',  'Reach level 200',  'level', 'epic'))
_r(AchievementDef('level_210',  'Ruby',      'Reach level 210',  'level', 'epic'))
_r(AchievementDef('level_220',  'Emerald',   'Reach level 220',  'level', 'epic'))
_r(AchievementDef('level_230',  'Diamond',   'Reach level 230',  'level', 'epic'))
_r(AchievementDef('level_240',  'Starfire',  'Reach level 240',  'level', 'epic'))

# Level milestones — Hex tier (250–320)
_r(AchievementDef('level_250',  'Honeycomb',       'Reach level 250',  'level', 'legendary'))
_r(AchievementDef('level_260',  'Sacred Geometry', 'Reach level 260',  'level', 'legendary'))
_r(AchievementDef('level_270',  'Crystalline',     'Reach level 270',  'level', 'legendary'))
_r(AchievementDef('level_280',  'The Pattern',     'Reach level 280',  'level', 'legendary'))
_r(AchievementDef('level_290',  'Transcendent',    'Reach level 290',  'level', 'legendary'))
_r(AchievementDef('level_300',  'GOD MODE',        'Reach level 300',  'level', 'legendary'))
_r(AchievementDef('level_310',  'Omniscient',      'Reach level 310',  'level', 'legendary'))
_r(AchievementDef('level_320',  'Absolute',        'Reach level 320',  'level', 'legendary'))

# Level milestones — Special
_r(AchievementDef('level_330',  'The Limit Does Not Exist', 'Reach level 330', 'level', 'legendary'))

# Meme levels
_r(AchievementDef('meme_42',   'The Answer',      'Hit exactly level 42',  'meme', 'rare'))
_r(AchievementDef('meme_69',   'Nice',            'Hit exactly level 69',  'meme', 'uncommon'))
_r(AchievementDef('meme_99',   'Max Level',       'Hit exactly level 99',  'meme', 'rare'))
_r(AchievementDef('meme_126',  'Barrows Gloves',  'Hit exactly level 126', 'meme', 'epic'))

# Peak
_r(AchievementDef('peak_chart_topper', 'Chart Topper',  'Appear in top 5 highscores (24h)',      'peak', 'epic'))
_r(AchievementDef('peak_hall_of_fame', 'Hall of Fame',  'Appear in top 5 highscores (all-time)', 'peak', 'epic'))
_r(AchievementDef('peak_pole_position','Pole Position', 'Reach #1 position',                     'peak', 'legendary'))
_r(AchievementDef('peak_fingertips',   'Fingertips',    'Within 5 levels of block target',       'peak', 'rare'))
_r(AchievementDef('peak_eureka',       'Eureka',        'Find a block',                          'peak', 'legendary'))

# Streaks — Dry
_r(AchievementDef('streak_cold_10',     'Cold Streak',   '10 consecutive shares below level 30',  'streak', 'common'))
_r(AchievementDef('streak_drought_25',  'Drought',       '25 consecutive shares below level 30',  'streak', 'uncommon'))
_r(AchievementDef('streak_sahara_50',   'Sahara',        '50 consecutive shares below level 30',  'streak', 'rare'))

# Streaks — Hot
_r(AchievementDef('streak_on_fire_5',    'On Fire',     '5 consecutive shares above level 50',    'streak', 'uncommon'))
_r(AchievementDef('streak_white_hot_10', 'White Hot',   '10 consecutive shares above level 50',   'streak', 'rare'))
_r(AchievementDef('streak_unstoppable_20','Unstoppable','20 consecutive shares above level 50',   'streak', 'epic'))

# Streaks — Elite
_r(AchievementDef('streak_solar_flare_5',  'Solar Flare',  '5 consecutive shares above level 100',  'streak', 'rare'))
_r(AchievementDef('streak_supernova_10',   'Supernova',    '10 consecutive shares above level 100', 'streak', 'epic'))
_r(AchievementDef('streak_untouchable_20', 'Untouchable',  '20 consecutive shares above level 100', 'streak', 'legendary'))

# Streaks — Special
_r(AchievementDef('streak_feast_or_famine', 'Feast or Famine', 'Same day: a share below 30 AND a share above 100', 'streak', 'uncommon'))
_r(AchievementDef('streak_hat_trick',       'Hat Trick',        'Same level 3 times in a row',  'streak', 'uncommon'))
_r(AchievementDef('streak_like_clockwork',  'Like Clockwork',   'Same level 5 times in a row',  'streak', 'rare'))
_r(AchievementDef('streak_broken_record',   'Broken Record',    'Same level 7 times in a row',  'streak', 'epic'))

# Longevity — Account age
_r(AchievementDef('longevity_7d',   'Settled In',  'Account is 7 days old',    'longevity', 'common'))
_r(AchievementDef('longevity_30d',  'Regular',     'Account is 30 days old',   'longevity', 'common'))
_r(AchievementDef('longevity_180d', 'Committed',   'Account is 180 days old',  'longevity', 'uncommon'))
_r(AchievementDef('longevity_365d', 'Veteran',     'Account is 365 days old',  'longevity', 'rare'))

# Longevity — Purchase regularity
_r(AchievementDef('longevity_habit_4w',       'Habit',        'Purchased in 4 different weeks',   'longevity', 'common'))
_r(AchievementDef('longevity_dedicated_12w',  'Dedicated',    'Purchased in 12 different weeks',  'longevity', 'uncommon'))
_r(AchievementDef('longevity_true_believer_52w', 'True Believer', 'Purchased in 52 different weeks', 'longevity', 'rare'))

# Longevity — Never-empty
_r(AchievementDef('longevity_solvent_1d',   'Solvent',    'Balance never empty for 1 day',    'longevity', 'common'))
_r(AchievementDef('longevity_funded_7d',    'Funded',     'Balance never empty for 7 days',   'longevity', 'uncommon'))
_r(AchievementDef('longevity_sustained_30d','Sustained',  'Balance never empty for 30 days',  'longevity', 'rare'))
_r(AchievementDef('longevity_ironclad_180d','Ironclad',   'Balance never empty for 180 days', 'longevity', 'epic'))

# Hash easter eggs (all secret, all rare)
_r(AchievementDef('hash_bada55',  'Badass',             'Hash contains BADA55',  'hash', 'rare', secret=True))
_r(AchievementDef('hash_dead',    'Dead Block',         'Hash contains DEAD',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_face',    'Face in the Crowd',  'Hash contains FACE',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_cafe',    'Hash Café',          'Hash contains CAFE',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_beef',    'Beefy',              'Hash contains BEEF',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_c0de',    'Code Found',         'Hash contains C0DE',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_f00d',    'Hash Browns',        'Hash contains F00D',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_600d',    'Good Vibes',         'Hash contains 600D',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_fade',    'Fading Signal',      'Hash contains FADE',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_feed',    'Feed the Machine',   'Hash contains FEED',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_c001',    'Cool Runnings',      'Hash contains C001',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_deed',    'Done Deed',          'Hash contains DEED',    'hash', 'rare', secret=True))
_r(AchievementDef('hash_abba',    'Dancing Queen',      'Hash contains ABBA',    'hash', 'rare', secret=True))

# Seasonal
_r(AchievementDef('seasonal_genesis',     'Genesis',     'Mine on January 3rd (Bitcoin birthday)',        'seasonal', 'epic'))
_r(AchievementDef('seasonal_white_paper', 'White Paper', 'Mine on October 31st (Bitcoin whitepaper day)', 'seasonal', 'epic'))
_r(AchievementDef('seasonal_pizza_day',   'Pizza Day',   'Mine on May 22nd (Bitcoin Pizza Day)',          'seasonal', 'epic'))
_r(AchievementDef('seasonal_christmas',   'Christmas',   'Mine on December 25th',                        'seasonal', 'epic'))
_r(AchievementDef('seasonal_new_year',    'New Year',    'Mine on January 1st',                          'seasonal', 'epic'))
_r(AchievementDef('seasonal_halving',     'The Halving', 'Mine within 24h of a Bitcoin halving block',   'seasonal', 'legendary'))

# Bitcoin halving block heights (every 210,000 blocks)
_HALVING_HEIGHTS = [210000, 420000, 630000, 840000, 1050000, 1260000]


# ── AchievementManager ────────────────────────────────────────────────────────

class AchievementManager:
    def __init__(self, sse_manager):
        self.sse_manager = sse_manager

    async def on_share(self, db, user_id: int, share: dict) -> None:
        """Check and award achievements triggered by a new share."""
        from .sse_manager import AchievementNotification

        share_id = share.get('share_id')
        level = share.get('level', 0)
        share_hash = share.get('share_hash') or ''
        is_block = share.get('is_block', False)
        ntime = share.get('ntime', 0)
        block_target_level = share.get('block_target_level', 0)

        already_unlocked = await self._get_unlocked(db, user_id)

        # Fetch last 50 billable shares for streak detection
        recent_rows = await db.fetch(
            """
            SELECT level FROM share_events
            WHERE user_id = $1 AND billable = 1
            ORDER BY id DESC LIMIT 50
            """,
            user_id,
        )
        recent_levels = [r['level'] for r in recent_rows]

        # Today's min/max level for feast-or-famine
        share_date = datetime.fromtimestamp(ntime, tz=timezone.utc).date() if ntime else datetime.now(timezone.utc).date()
        day_start = int(datetime(share_date.year, share_date.month, share_date.day, tzinfo=timezone.utc).timestamp())
        day_end = day_start + 86400
        day_rows = await db.fetch(
            "SELECT level FROM share_events WHERE user_id = $1 AND ntime >= $2 AND ntime < $3",
            user_id, day_start, day_end,
        )
        day_levels = [r['level'] for r in day_rows] + [level]

        # Fetch user created_at for longevity checks
        user_row = await db.fetchrow(
            "SELECT created_at FROM users WHERE id = $1", user_id
        )
        created_at = user_row['created_at'] if user_row else None

        to_grant = []

        # Level milestones
        level_int = math.floor(level)
        for threshold in range(50, 331, 10):
            ach_id = f'level_{threshold}'
            if ach_id in REGISTRY and ach_id not in already_unlocked and level_int >= threshold:
                to_grant.append(ach_id)

        # Meme levels
        for meme_val, ach_id in [(42, 'meme_42'), (69, 'meme_69'), (99, 'meme_99'), (126, 'meme_126')]:
            if ach_id not in already_unlocked and level_int == meme_val:
                to_grant.append(ach_id)

        # Hash easter eggs
        hash_upper = share_hash.upper()
        hash_words = [
            ('BADA55', 'hash_bada55'), ('DEAD', 'hash_dead'), ('FACE', 'hash_face'),
            ('CAFE', 'hash_cafe'), ('BEEF', 'hash_beef'), ('C0DE', 'hash_c0de'),
            ('F00D', 'hash_f00d'), ('600D', 'hash_600d'), ('FADE', 'hash_fade'),
            ('FEED', 'hash_feed'), ('C001', 'hash_c001'), ('DEED', 'hash_deed'),
            ('ABBA', 'hash_abba'),
        ]
        for word, ach_id in hash_words:
            if ach_id not in already_unlocked and word in hash_upper:
                to_grant.append(ach_id)

        # Near-miss / block
        if 'peak_fingertips' not in already_unlocked and block_target_level > 0 and abs(level - block_target_level) <= 5:
            to_grant.append('peak_fingertips')
        if 'peak_eureka' not in already_unlocked and is_block:
            to_grant.append('peak_eureka')

        # Seasonal
        share_utc = datetime.fromtimestamp(ntime, tz=timezone.utc) if ntime else datetime.now(timezone.utc)
        month, day = share_utc.month, share_utc.day
        seasonal_map = [
            (1,  3,  'seasonal_genesis'),
            (10, 31, 'seasonal_white_paper'),
            (5,  22, 'seasonal_pizza_day'),
            (12, 25, 'seasonal_christmas'),
            (1,  1,  'seasonal_new_year'),
        ]
        for sm, sd, ach_id in seasonal_map:
            if ach_id not in already_unlocked and month == sm and day == sd:
                to_grant.append(ach_id)

        # Halving (check share block_height against known halving heights)
        block_height = share.get('block_height', 0)
        if 'seasonal_halving' not in already_unlocked and block_height:
            for hh in _HALVING_HEIGHTS:
                if abs(block_height - hh) <= 144:  # ~24h worth of blocks
                    to_grant.append('seasonal_halving')
                    break

        # Streaks — scan recent_levels (includes current share as first element if billable)
        all_levels = [level] + recent_levels if level >= 10 else recent_levels

        # Dry streak (below 30)
        dry_run = 0
        for lv in all_levels:
            if lv < 30:
                dry_run += 1
            else:
                break
        dry_map = [(10, 'streak_cold_10'), (25, 'streak_drought_25'), (50, 'streak_sahara_50')]
        for threshold, ach_id in dry_map:
            if ach_id not in already_unlocked and dry_run >= threshold:
                to_grant.append(ach_id)

        # Hot streak (above 50)
        hot_run = 0
        for lv in all_levels:
            if lv > 50:
                hot_run += 1
            else:
                break
        hot_map = [(5, 'streak_on_fire_5'), (10, 'streak_white_hot_10'), (20, 'streak_unstoppable_20')]
        for threshold, ach_id in hot_map:
            if ach_id not in already_unlocked and hot_run >= threshold:
                to_grant.append(ach_id)

        # Elite streak (above 100)
        elite_run = 0
        for lv in all_levels:
            if lv > 100:
                elite_run += 1
            else:
                break
        elite_map = [(5, 'streak_solar_flare_5'), (10, 'streak_supernova_10'), (20, 'streak_untouchable_20')]
        for threshold, ach_id in elite_map:
            if ach_id not in already_unlocked and elite_run >= threshold:
                to_grant.append(ach_id)

        # Feast or famine
        if 'streak_feast_or_famine' not in already_unlocked:
            if any(lv < 30 for lv in day_levels) and any(lv > 100 for lv in day_levels):
                to_grant.append('streak_feast_or_famine')

        # Same-level streak
        if all_levels:
            same_level_run = 1
            first_floor = math.floor(all_levels[0])
            for lv in all_levels[1:]:
                if math.floor(lv) == first_floor:
                    same_level_run += 1
                else:
                    break
            same_map = [(3, 'streak_hat_trick'), (5, 'streak_like_clockwork'), (7, 'streak_broken_record')]
            for threshold, ach_id in same_map:
                if ach_id not in already_unlocked and same_level_run >= threshold:
                    to_grant.append(ach_id)

        # Account age longevity
        if created_at:
            now_utc = datetime.now(timezone.utc)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = (now_utc - created_at).days
            age_map = [(7, 'longevity_7d'), (30, 'longevity_30d'), (180, 'longevity_180d'), (365, 'longevity_365d')]
            for threshold, ach_id in age_map:
                if ach_id not in already_unlocked and age_days >= threshold:
                    to_grant.append(ach_id)

        # Grant achievements and SSE notify
        for ach_id in to_grant:
            await self._grant(db, user_id, ach_id, share_id)

        # Check never-empty: if balance hits 0, clear never_empty_since
        balance = await db.fetchval(
            """
            SELECT COALESCE(SUM(t.amount), 0) - COALESCE(SUM(se.shares_consumed), 0)
            FROM (SELECT SUM(amount) as amount FROM transactions WHERE user_id = $1) t,
                 (SELECT SUM(shares_consumed) as shares_consumed FROM share_events WHERE user_id = $1 AND billable = 1) se
            """,
            user_id,
        )
        if balance is not None and balance <= 0:
            await db.execute(
                "UPDATE users SET never_empty_since = NULL WHERE id = $1", user_id
            )

    async def on_purchase(self, db, user_id: int, amount: int, prev_balance: int) -> None:
        """Check and award achievements triggered by a purchase."""
        already_unlocked = await self._get_unlocked(db, user_id)

        # Total purchased
        total_purchased = await db.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = $1", user_id
        )
        purchase_map = [
            (100,   'grind_purchased_100'),
            (1000,  'grind_purchased_1k'),
            (10000, 'grind_purchased_10k'),
            (100000,'grind_purchased_100k'),
        ]
        for threshold, ach_id in purchase_map:
            if ach_id not in already_unlocked and total_purchased >= threshold:
                await self._grant(db, user_id, ach_id)

        # Big batch
        if 'grind_big_batch' not in already_unlocked and amount >= 1000:
            await self._grant(db, user_id, 'grind_big_batch')

        # Total consumed
        total_consumed = await db.fetchval(
            "SELECT COALESCE(SUM(shares_consumed), 0) FROM share_events WHERE user_id = $1 AND billable = 1",
            user_id,
        )
        consumed_map = [
            (100,   'grind_consumed_100'),
            (1000,  'grind_consumed_1k'),
            (10000, 'grind_consumed_10k'),
            (100000,'grind_consumed_100k'),
        ]
        for threshold, ach_id in consumed_map:
            if ach_id not in already_unlocked and total_consumed >= threshold:
                await self._grant(db, user_id, ach_id)

        # Regular weeks
        distinct_weeks = await db.fetchval(
            """
            SELECT COUNT(DISTINCT DATE_TRUNC('week', created_at))
            FROM transactions WHERE user_id = $1
            """,
            user_id,
        )
        week_map = [
            (4,  'longevity_habit_4w'),
            (12, 'longevity_dedicated_12w'),
            (52, 'longevity_true_believer_52w'),
        ]
        for threshold, ach_id in week_map:
            if ach_id not in already_unlocked and distinct_weeks >= threshold:
                await self._grant(db, user_id, ach_id)

        # Never-empty: if prev_balance was 0, start the clock
        if prev_balance <= 0:
            await db.execute(
                "UPDATE users SET never_empty_since = NOW() WHERE id = $1 AND never_empty_since IS NULL",
                user_id,
            )

        # Never-empty duration achievements
        never_empty_row = await db.fetchrow(
            "SELECT never_empty_since FROM users WHERE id = $1", user_id
        )
        if never_empty_row and never_empty_row['never_empty_since']:
            nes = never_empty_row['never_empty_since']
            if nes.tzinfo is None:
                nes = nes.replace(tzinfo=timezone.utc)
            elapsed_days = (datetime.now(timezone.utc) - nes).days
            never_empty_map = [
                (1,   'longevity_solvent_1d'),
                (7,   'longevity_funded_7d'),
                (30,  'longevity_sustained_30d'),
                (180, 'longevity_ironclad_180d'),
            ]
            for threshold, ach_id in never_empty_map:
                if ach_id not in already_unlocked and elapsed_days >= threshold:
                    await self._grant(db, user_id, ach_id)

    async def on_achievements_requested(self, db, user_id: int) -> None:
        """Trigger account age and never-empty checks when user views achievements."""
        already_unlocked = await self._get_unlocked(db, user_id)

        user_row = await db.fetchrow(
            "SELECT created_at, never_empty_since FROM users WHERE id = $1", user_id
        )
        if not user_row:
            return

        created_at = user_row['created_at']
        if created_at:
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - created_at).days
            age_map = [(7, 'longevity_7d'), (30, 'longevity_30d'), (180, 'longevity_180d'), (365, 'longevity_365d')]
            for threshold, ach_id in age_map:
                if ach_id not in already_unlocked and age_days >= threshold:
                    await self._grant(db, user_id, ach_id)

        nes = user_row['never_empty_since']
        if nes:
            if nes.tzinfo is None:
                nes = nes.replace(tzinfo=timezone.utc)
            elapsed_days = (datetime.now(timezone.utc) - nes).days
            never_empty_map = [
                (1,   'longevity_solvent_1d'),
                (7,   'longevity_funded_7d'),
                (30,  'longevity_sustained_30d'),
                (180, 'longevity_ironclad_180d'),
            ]
            for threshold, ach_id in never_empty_map:
                if ach_id not in already_unlocked and elapsed_days >= threshold:
                    await self._grant(db, user_id, ach_id)

    async def _get_unlocked(self, db, user_id: int) -> set:
        rows = await db.fetch(
            "SELECT achievement_id FROM user_achievements WHERE user_id = $1", user_id
        )
        return {r['achievement_id'] for r in rows}

    async def _grant(self, db, user_id: int, ach_id: str, share_id: Optional[int] = None) -> bool:
        """Insert achievement if not already present. Returns True if newly inserted."""
        if ach_id not in REGISTRY:
            logger.warning(f"Tried to grant unknown achievement: {ach_id}")
            return False
        result = await db.execute(
            """
            INSERT INTO user_achievements (user_id, achievement_id, share_id)
            VALUES ($1, $2, $3) ON CONFLICT DO NOTHING
            """,
            user_id, ach_id, share_id,
        )
        newly_inserted = result == "INSERT 0 1"
        if newly_inserted:
            from .sse_manager import AchievementNotification
            defn = REGISTRY[ach_id]
            logger.info(f"Achievement unlocked: user={user_id}, ach={ach_id}")
            await self.sse_manager.notify(AchievementNotification(
                user_id=user_id,
                achievement_id=ach_id,
                achievement_name=defn.name,
            ))
        return newly_inserted
