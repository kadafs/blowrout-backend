import io
import sys
import os
import json
import numpy as np

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

def analyze_subset(name, subset):
    print(f"\n=======================================================")
    print(f"RESULTS: {name} (N = {len(subset)} games)")
    print(f"=======================================================")
    
    # 1. Model Projection Totals Error (MAE, Bias, Tiers)
    deltas = [p.get('total_delta') for p in subset if p.get('total_delta') is not None]
    signed_deltas = [p.get('signed_delta') for p in subset if p.get('signed_delta') is not None]
    
    mae = np.mean(deltas) if deltas else 0
    bias = np.mean(signed_deltas) if signed_deltas else 0
    
    tiers = {"BULLSEYE": 0, "EXCELLENT": 0, "SOLID": 0, "MISS": 0, "BUST": 0}
    for p in subset:
        t = p.get('accuracy_tier')
        if t in tiers:
            tiers[t] += 1
            
    print(f"* Model Totals MAE:        {mae:.2f} pts")
    print(f"* Signed Bias (Act - Proj): {bias:+.2f} pts ({'Undershooting' if bias > 0 else 'Overshooting'})")
    print(f"* Accuracy Tiers:")
    for t, count in tiers.items():
        pct = (count / len(subset) * 100) if subset else 0
        print(f"    - {t:<10}: {count:2d} ({pct:4.1f}%)")
        
    pinpoint = tiers['BULLSEYE'] + tiers['EXCELLENT']
    solid_plus = pinpoint + tiers['SOLID']
    print(f"* Within 8.5 pts (Pinpoint): {pinpoint}/{len(subset)} ({pinpoint/len(subset)*100:.1f}%)")
    print(f"* Within 14.5 pts (Solid+):  {solid_plus}/{len(subset)} ({solid_plus/len(subset)*100:.1f}%)")
    
    # 2. Market Over/Under Bet Picks
    mkt_plays = []
    for p in subset:
        mkt = p.get('market_total')
        side = p.get('side')
        dec = p.get('decision')
        ahs = p.get('actual_home_score')
        aas = p.get('actual_away_score')
        if mkt is not None and ahs is not None and aas is not None and side in ('OVER', 'UNDER'):
            act_total = ahs + aas
            if act_total == mkt:
                res = 'PUSH'
            elif act_total > mkt:
                res = 'OVER'
            else:
                res = 'UNDER'
            
            is_win = (side == res)
            is_push = (res == 'PUSH')
            mkt_plays.append({
                'matchup': f"{p.get('away_team')} @ {p.get('home_team')}",
                'market': mkt,
                'actual': act_total,
                'model': p.get('model_total'),
                'side': side,
                'decision': dec,
                'result': res,
                'is_win': is_win,
                'is_push': is_push
            })
            
    print(f"\n* Market Over/Under Betting Performance (Sample = {len(mkt_plays)} games with market lines):")
    if mkt_plays:
        wins = sum(1 for m in mkt_plays if m['is_win'])
        pushes = sum(1 for m in mkt_plays if m['is_push'])
        losses = len(mkt_plays) - wins - pushes
        decided = wins + losses
        win_pct = (wins / decided * 100) if decided > 0 else 0
        print(f"    - Total Market O/U Plays: {len(mkt_plays)}")
        print(f"    - Record: {wins} Wins - {losses} Losses - {pushes} Pushes")
        print(f"    - Win Rate: {win_pct:.1f}%")
        
        actionable = [m for m in mkt_plays if 'PLAY' in str(m['decision'])]
        print(f"    - Official 'PLAY' Bets (Edge >= Threshold): {len(actionable)} games")
        if actionable:
            a_wins = sum(1 for m in actionable if m['is_win'])
            a_pushes = sum(1 for m in actionable if m['is_push'])
            a_losses = len(actionable) - a_wins - a_pushes
            a_decided = a_wins + a_losses
            a_win_pct = (a_wins / a_decided * 100) if a_decided > 0 else 0
            print(f"        Record: {a_wins}W - {a_losses}L - {a_pushes}P ({a_win_pct:.1f}%)")
            for m in actionable:
                status = "WIN" if m['is_win'] else ("PUSH" if m['is_push'] else "LOSS")
                print(f"        * {m['matchup']:<32} | Mkt:{m['market']:5.1f} Act:{m['actual']:3d} | Pick:{m['side']:<5} -> {status}")
    else:
        print("    - No market totals found in this subset.")

# Split into Mismatched vs Non-Mismatched
mismatched_games = [p for p in men_games if abs(p['actual_home_score'] - p['actual_away_score']) >= 20]
competitive_games = [p for p in men_games if abs(p['actual_home_score'] - p['actual_away_score']) < 20]

print(f"\nMen Games Breakdown:")
print(f"  * Mismatched Blowouts (Margin >= 20 pts): {len(mismatched_games)}")
print(f"  * Competitive Games   (Margin < 20 pts):  {len(competitive_games)}")

analyze_subset("1. ALL MEN'S NCAA GAMES (With Mismatches)", men_games)
analyze_subset("2. COMPETITIVE GAMES ONLY (Without Mismatches, Margin < 20)", competitive_games)
analyze_subset("3. MISMATCHED BUY GAMES ONLY (Margin >= 20)", mismatched_games)
