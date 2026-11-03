import io
import sys
import os
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

files = [
    'data/basketball/universal_predictions_2026-11-01_v2.json',
    'data/basketball/universal_predictions_2026-11-02_v2.json',
    'data/basketball/universal_predictions_2026-11-03_v2.json'
]

men_games = []
for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    preds = data.get('predictions', [])
    for p in preds:
        lid = p.get('league_id', 0)
        is_men_ncaa = ('116' in str(lid)) and ('423' not in str(lid)) and (' W' not in p.get('home_team', ''))
        if is_men_ncaa and p.get('actual_result') and not p.get('awarded_match') and not p.get('incomplete_feed'):
            men_games.append(p)

print(f"Total Men NCAA graded games: {len(men_games)}")

# Let's inspect all 22 mismatched games (actual margin >= 20) and their projected spreads
mismatches = []
for p in men_games:
    ahs = p['actual_home_score']
    aas = p['actual_away_score']
    actual_margin = abs(ahs - aas)
    proj_spr = abs((p.get('xpts_h') or 0) - (p.get('xpts_a') or 0))
    mkt_spread = p.get('market_spread')  # if exists
    mismatches.append((p, actual_margin, proj_spr))

# Filter to actual_margin >= 20
blowouts = [m for m in mismatches if m[1] >= 20]

print(f"\nTotal Men's Blowouts (Actual Margin >= 20 pts): {len(blowouts)}")

low_spread_blowouts = [m for m in blowouts if m[2] < 15.0]
high_spread_blowouts = [m for m in blowouts if m[2] >= 15.0]

print(f"  • Blowouts with Projected Spread < 15.0 pts:  {len(low_spread_blowouts)} games (SURPRISE BLOWOUTS)")
print(f"  • Blowouts with Projected Spread >= 15.0 pts: {len(high_spread_blowouts)} games (EXPECTED MISMATCHES)")

print("\n" + "=" * 120)
print(f"{'Date':<10} | {'Matchup':<38} | {'Proj Spread':<11} | {'Actual Score':<12} | {'Actual Margin':<13} | {'Pick':<4} | {'Res':<4} | {'Status'}")
print("=" * 120)

for p, am, ps in sorted(low_spread_blowouts, key=lambda x: x[2]):
    ht = p['home_team']
    at = p['away_team']
    matchup = f"{at} @ {ht}"
    score = f"{p['actual_home_score']}-{p['actual_away_score']}"
    pick = p.get('predicted_result')
    res = p.get('actual_result')
    win = 'WIN' if pick == res else 'LOSS'
    print(f"{p['date']:<10} | {matchup:<38} | {ps:<11.1f} | {score:<12} | +{am:<12} | {pick:<4} | {res:<4} | {win}")

print("=" * 120)

