import json
import glob
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Load historical actual scores
hist_files = glob.glob('data/historical/api_basketball_*.json')
actual_scores = {}
for hf in hist_files:
    try:
        with open(hf, 'r', encoding='utf-8') as f:
            games = json.load(f)
        for g in games:
            if g.get('date') == '2026-10-31':
                h = g.get('home_team', '').lower().strip()
                a = g.get('away_team', '').lower().strip()
                gid = g.get('game_id')
                hs = g.get('home_score')
                as_score = g.get('away_score')
                if hs is not None and as_score is not None:
                    tot = hs + as_score
                    if (h, a) not in actual_scores:
                        actual_scores[(h, a)] = tot
                    if gid:
                        actual_scores[str(gid)] = tot
    except Exception:
        pass

# Load updated predictions
with open('data/basketball/universal_predictions_2026-10-31_v2.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
preds = data.get('predictions', [])

real_odds_graded = []
for p in preds:
    h = p.get('home_team', '').lower().strip()
    a = p.get('away_team', '').lower().strip()
    gid = str(p.get('game_id', ''))
    
    actual = actual_scores.get(gid) or actual_scores.get((h, a))
    mkt = p.get('market_total')
    dec = p.get('decision')
    side = p.get('side')
    src = p.get('odds_source')
    
    if actual and mkt and src not in [None, 'BASELINE', 'AVERAGE']:
        is_hit = False
        if side == 'OVER' and actual > mkt:
            is_hit = True
        elif side == 'UNDER' and actual < mkt:
            is_hit = True
        elif actual == mkt:
            is_hit = None # Push
            
        real_odds_graded.append({
            'match': f"{p.get('home_team')} vs {p.get('away_team')}",
            'bookmaker': src,
            'real_line': mkt,
            'actual': actual,
            'side': side,
            'edge': p.get('edge'),
            'decision': dec,
            'is_hit': is_hit
        })

cleared = [g for g in real_odds_graded if 'PLAY' in str(g['decision']) and g['is_hit'] is not None]
below = [g for g in real_odds_graded if 'PASS' in str(g['decision']) and g['is_hit'] is not None]

print("="*75)
print(f"  BACKFILL 2026-10-31 REAL MARKET LINE PERFORMANCE AUDIT")
print("="*75)
print(f"Total Matches Graded on REAL Bookmaker Lines: {len(real_odds_graded)}")
if cleared:
    c_wins = sum(1 for g in cleared if g['is_hit'])
    roi = ((c_wins * 1.91) - len(cleared)) / len(cleared) * 100
    print(f"\n🎯 CLEARED MBET (High Conviction Plays): {c_wins}/{len(cleared)} ({c_wins/len(cleared)*100:.1f}%) | ROI: {roi:+.1f}%")
if below:
    b_wins = sum(1 for g in below if g['is_hit'])
    roi = ((b_wins * 1.91) - len(below)) / len(below) * 100
    print(f"⚪ BELOW MBET (Filtered Out / Passes):   {b_wins}/{len(below)} ({b_wins/len(below)*100:.1f}%) | ROI: {roi:+.1f}%")

print("\nDetailed Breakdown of Cleared MBET Plays (Real Lines):")
for g in cleared:
    status = "WIN  ✅" if g['is_hit'] else "LOSS ❌"
    print(f"  {g['match']:<42} | Line: {g['real_line']:>5.1f} [{g['bookmaker']:<8}] | {g['side']:<5} (Edge {g['edge']:>+5.1f}) | Final: {g['actual']:>3} -> {status}")

print("="*75)
