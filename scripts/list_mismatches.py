import json

files = [
    'data/basketball/universal_predictions_2026-11-01_v2.json',
    'data/basketball/universal_predictions_2026-11-02_v2.json',
    'data/basketball/universal_predictions_2026-11-03_v2.json'
]

all_ncaa = []
for fpath in files:
    with open(fpath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    preds = data.get('predictions', [])
    for p in preds:
        lid = p.get('league_id', 0)
        is_ncaa = ('116' in str(lid) or '423' in str(lid))
        if is_ncaa and p.get('actual_result') and not p.get('awarded_match') and not p.get('incomplete_feed'):
            all_ncaa.append(p)

print(f"Total graded NCAA games: {len(all_ncaa)}")

mismatches = []
for p in all_ncaa:
    ahs = p.get('actual_home_score', 0)
    aas = p.get('actual_away_score', 0)
    actual_margin = abs(ahs - aas)
    proj_margin = abs((p.get('xpts_h') or 0) - (p.get('xpts_a') or 0))
    # A game is considered a mismatch if actual margin >= 20 or projected margin >= 15
    if actual_margin >= 20 or proj_margin >= 15:
        mismatches.append((p, actual_margin, proj_margin))

print(f"Found {len(mismatches)} mismatched games:")
# Sort by actual margin descending
mismatches.sort(key=lambda x: x[1], reverse=True)

header = f"{'Date':<10} | {'Gen':<5} | {'Matchup':<42} | {'Act Score':<11} | {'Margin':<6} | {'Model Tot':<9} | {'Act Tot':<7} | {'Delta':<5} | {'Tier':<9} | {'Pick':<4} | {'Res':<4} | {'Status'}"
print("=" * len(header))
print(header)
print("=" * len(header))

for p, am, pm in mismatches:
    gender = 'Women' if '423' in str(p.get('league_id')) or ' W' in p.get('home_team', '') else 'Men'
    ht = p.get('home_team')
    at = p.get('away_team')
    matchup = f"{at} @ {ht}"
    ahs = p.get('actual_home_score')
    aas = p.get('actual_away_score')
    score_str = f"{ahs}-{aas}"
    mt = p.get('model_total') or 0
    tot = ahs + aas
    delta = p.get('total_delta') or abs(tot - mt)
    pick = p.get('predicted_result')
    res = p.get('actual_result')
    win = 'WIN' if pick == res else 'LOSS'
    tier = p.get('accuracy_tier', '')
    print(f"{p.get('date'):<10} | {gender:<5} | {matchup:<42} | {score_str:<11} | {am:<6} | {mt:<9.1f} | {tot:<7} | {delta:<5.1f} | {tier:<9} | {pick:<4} | {res:<4} | {win}")

print("=" * len(header))

