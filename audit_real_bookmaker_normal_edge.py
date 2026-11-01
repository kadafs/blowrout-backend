"""
audit_real_bookmaker_normal_edge.py
===================================
Audits basketball Over/Under betting performance based EXCLUSIVELY on
REAL BOOKMAKER LINES (Pinnacle, Bet365, 1xBet, Marathon Bet, etc.)
evaluating NORMAL (RAW) EDGE:
    Raw Edge = Model Projection - Real Market Line
    Pick = OVER if Edge > 0 else UNDER
"""

import os
import sys
import glob
import json

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def calculate_roi(wins, total, odds=1.91):
    if total == 0:
        return 0.0
    return ((wins * odds) - total) / total * 100

def run_real_odds_audit():
    # 1. Load actual scores from historical databases
    print("Loading actual game scores from historical database...")
    hist_files = glob.glob('data/historical/api_basketball_*.json')
    actual_scores = {}
    for hf in hist_files:
        try:
            with open(hf, 'r', encoding='utf-8') as f:
                games = json.load(f)
            for g in games:
                dt = g.get('date')
                if dt in ['2026-10-29', '2026-10-30', '2026-10-31']:
                    h = g.get('home_team', '').lower().strip()
                    a = g.get('away_team', '').lower().strip()
                    gid = str(g.get('game_id', ''))
                    hs = g.get('home_score')
                    as_score = g.get('away_score')
                    if hs is not None and as_score is not None:
                        tot = hs + as_score
                        if (dt, h, a) not in actual_scores:
                            actual_scores[(dt, h, a)] = tot
                        if gid:
                            actual_scores[gid] = tot
        except Exception:
            pass

    # 2. Extract all predictions with REAL bookmaker lines
    target_dates = ['2026-10-29', '2026-10-30', '2026-10-31']
    real_matches = []
    
    for dt in target_dates:
        pred_path = f"data/basketball/universal_predictions_{dt}_v2.json"
        if not os.path.exists(pred_path):
            continue
        try:
            with open(pred_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for p in data.get('predictions', []):
                h = p.get('home_team', '').lower().strip()
                a = p.get('away_team', '').lower().strip()
                gid = str(p.get('game_id', ''))
                src = p.get('odds_source')
                book = p.get('bookmaker') or src
                mkt = p.get('market_total')
                model_tot = p.get('model_total')
                
                # STRICT FILTER: MUST BE REAL BOOKMAKER LINE
                if src in [None, '', 'BASELINE', 'AVERAGE', 'None']:
                    continue
                if mkt is None or mkt <= 50 or model_tot is None:
                    continue
                
                act = actual_scores.get(gid) or actual_scores.get((dt, h, a))
                if act is None:
                    continue
                
                edge = round(model_tot - mkt, 1)
                abs_edge = round(abs(edge), 1)
                if abs_edge == 0:
                    continue
                
                side = "OVER" if edge > 0 else "UNDER"
                hit = False
                push = False
                if act == mkt:
                    push = True
                elif side == "OVER" and act > mkt:
                    hit = True
                elif side == "UNDER" and act < mkt:
                    hit = True
                    
                real_matches.append({
                    'date': dt,
                    'match': f"{p.get('home_team')} vs {p.get('away_team')}",
                    'bookmaker': book,
                    'real_line': mkt,
                    'model_tot': model_tot,
                    'edge': edge,
                    'abs_edge': abs_edge,
                    'side': side,
                    'actual': act,
                    'hit': hit,
                    'push': push
                })
        except Exception as e:
            print(f"Error reading {dt}: {e}")

    graded = [m for m in real_matches if not m['push']]
    pushes = sum(1 for m in real_matches if m['push'])
    
    total_bets = len(graded)
    total_wins = sum(1 for m in graded if m['hit'])
    total_wr = (total_wins / total_bets * 100) if total_bets else 0.0
    total_roi = calculate_roi(total_wins, total_bets)
    total_units = (total_wins * 1.91) - total_bets

    print("\n" + "="*88)
    print("  AUDIT: NORMAL (RAW) EDGE ON REAL BOOKMAKER LINES (Pinnacle/Bet365/1xBet)")
    print("="*88)
    print(f"Total Matches with Real Lines Graded: {total_bets} (Pushes: {pushes})")
    print(f"Baseline Performance (Any Normal Edge > 0): {total_wins}/{total_bets} ({total_wr:.2f}%) | ROI: {total_roi:+.2f}% | Net Units: {total_units:+.1f}u\n")

    # 1. MINIMUM NORMAL EDGE THRESHOLDS
    print("-" * 88)
    print("1. PERFORMANCE BY MINIMUM NORMAL EDGE CUTOFF (|Model - Real Line| >= X)")
    print("-" * 88)
    print(f"{'Min Edge':<12} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Net Units':<10}")
    print("-" * 88)
    cutoffs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0]
    for c in cutoffs:
        sub = [m for m in graded if m['abs_edge'] >= c]
        if not sub:
            continue
        w = sum(1 for m in sub if m['hit'])
        t = len(sub)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"Edge >= {c:<5.1f} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")

    # 2. EDGE BUCKET RANGES
    print("\n" + "-" * 88)
    print("2. PERFORMANCE BY ISOLATED EDGE BUCKETS (Where do the profits lie?)")
    print("-" * 88)
    print(f"{'Edge Bucket':<16} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Net Units':<10}")
    print("-" * 88)
    buckets = [
        ("0.1 to 2.0 pts", 0.0, 2.0),
        ("2.1 to 4.0 pts", 2.0, 4.0),
        ("4.1 to 6.0 pts", 4.0, 6.0),
        ("6.1 to 8.0 pts", 6.0, 8.0),
        ("8.1 to 10.0 pts", 8.0, 10.0),
        ("10.1 to 15.0 pts", 10.0, 15.0),
        ("15.1+ pts", 15.0, 999.0)
    ]
    for label, low, high in buckets:
        sub = [m for m in graded if low < m['abs_edge'] <= high]
        if not sub:
            continue
        w = sum(1 for m in sub if m['hit'])
        t = len(sub)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"{label:<16} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")

    # 3. OVER VS UNDER ASYMMETRY ON REAL LINES
    print("\n" + "-" * 88)
    print("3. OVER VS UNDER ASYMMETRY (NORMAL EDGE ON REAL LINES)")
    print("-" * 88)
    print(f"{'Side':<6} | {'Min Edge':<10} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Net Units':<10}")
    print("-" * 88)
    for side in ["OVER", "UNDER"]:
        side_matches = [m for m in graded if m['side'] == side]
        for c in [0.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0]:
            sub = [m for m in side_matches if m['abs_edge'] >= c]
            if not sub:
                continue
            w = sum(1 for m in sub if m['hit'])
            t = len(sub)
            wr = w / t * 100
            roi = calculate_roi(w, t)
            units = (w * 1.91) - t
            print(f"{side:<6} | Edge >= {c:<4.1f} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")
        print("-" * 88)

    # 4. BREAKDOWN BY BOOKMAKER
    print("\n" + "-" * 88)
    print("4. BREAKDOWN BY BOOKMAKER PROVIDER")
    print("-" * 88)
    print(f"{'Bookmaker':<16} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Net Units':<10}")
    print("-" * 88)
    books = set(m['bookmaker'] for m in graded)
    for b in sorted(books):
        sub = [m for m in graded if m['bookmaker'] == b]
        w = sum(1 for m in sub if m['hit'])
        t = len(sub)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"{b:<16} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")

    # 5. DATE CONSISTENCY
    print("\n" + "-" * 88)
    print("5. DAY-BY-DAY PERFORMANCE CONSISTENCY (REAL LINES)")
    print("-" * 88)
    print(f"{'Date':<12} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Net Units':<10}")
    print("-" * 88)
    for dt in target_dates:
        sub = [m for m in graded if m['date'] == dt]
        if not sub:
            continue
        w = sum(1 for m in sub if m['hit'])
        t = len(sub)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"{dt:<12} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")
    print("="*88)

if __name__ == "__main__":
    run_real_odds_audit()
