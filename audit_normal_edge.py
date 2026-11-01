"""
audit_normal_edge.py
====================
Audits basketball Over/Under betting performance based on NORMAL (RAW) EDGE:
    Raw Edge = Model Projection - Market Line
    Pick = OVER if Edge > 0 else UNDER

Tests:
  1. Performance by Edge Buckets: [0-2], [2-4], [4-6], [6-8], [8-10], [10-15], [15+]
  2. Performance by Minimum Edge Cutoffs: >=0, >=1, >=2, >=3, >=4, >=5, >=6, >=7, >=8, >=10, >=12, >=15
  3. Split by Pick Side (OVER vs UNDER)
  4. Comparison between Raw Normal Edge vs MBET Dynamic Filtering

Evaluates on:
  - Part A: Yesterday's Real Bookmaker Lines (2026-10-31, Pinnacle/Bet365 consensus)
  - Part B: Full Multi-Month Graded Historical Database (5,155 graded matches)
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

def audit_dataset(matches, title="DATASET"):
    print("\n" + "="*88)
    print(f"  {title}")
    print("="*88)
    
    valid = [m for m in matches if m.get('actual') is not None and m.get('market') is not None and m.get('edge') != 0]
    
    # Check outcomes
    for m in valid:
        m['abs_edge'] = round(abs(m['edge']), 1)
        m['side'] = "OVER" if m['edge'] > 0 else "UNDER"
        if m['side'] == "OVER":
            m['hit'] = (m['actual'] > m['market'])
            m['push'] = (m['actual'] == m['market'])
        else:
            m['hit'] = (m['actual'] < m['market'])
            m['push'] = (m['actual'] == m['market'])
            
    graded = [m for m in valid if not m['push']]
    pushes = sum(1 for m in valid if m['push'])
    
    total_wins = sum(1 for m in graded if m['hit'])
    total_games = len(graded)
    total_wr = (total_wins / total_games * 100) if total_games else 0
    total_roi = calculate_roi(total_wins, total_games)
    
    print(f"Total Graded Games: {total_games} (Pushes: {pushes})")
    print(f"Baseline (Any Raw Edge > 0): {total_wins}/{total_games} ({total_wr:.2f}%) | Net ROI: {total_roi:+.2f}%\n")
    
    # 1. MINIMUM EDGE THRESHOLDS
    print("-" * 88)
    print("1. PERFORMANCE BY MINIMUM NORMAL EDGE THRESHOLD (|Model - Market| >= X)")
    print("-" * 88)
    print(f"{'Min Edge':<12} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Units (+/-)':<10}")
    print("-" * 88)
    
    cutoffs = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 12.0, 15.0]
    for c in cutoffs:
        subset = [m for m in graded if m['abs_edge'] >= c]
        if not subset:
            continue
        w = sum(1 for m in subset if m['hit'])
        t = len(subset)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"Edge >= {c:<5.1f} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")
        
    # 2. EDGE BRACKETS / BUCKETS
    print("\n" + "-" * 88)
    print("2. PERFORMANCE BY EDGE BUCKET RANGES")
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
        subset = [m for m in graded if low < m['abs_edge'] <= high]
        if not subset:
            continue
        w = sum(1 for m in subset if m['hit'])
        t = len(subset)
        wr = w / t * 100
        roi = calculate_roi(w, t)
        units = (w * 1.91) - t
        print(f"{label:<16} | {t:<8} | {w:<8} | {wr:>6.2f}%    | {roi:>+7.2f}%     | {units:>+8.1f}u")
        
    # 3. OVER VS UNDER BREAKDOWN BY NORMAL EDGE
    print("\n" + "-" * 88)
    print("3. OVER VS UNDER ASYMMETRY (NORMAL RAW EDGE)")
    print("-" * 88)
    print(f"{'Side':<6} | {'Min Edge':<10} | {'Bets':<8} | {'Wins':<8} | {'Win Rate':<10} | {'ROI (@1.91)':<12} | {'Units (+/-)':<10}")
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

def run():
    # -------------------------------------------------------------
    # 1. LOAD YESTERDAY'S REAL BOOKMAKER LINES (2026-10-31)
    # -------------------------------------------------------------
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

    with open('data/basketball/universal_predictions_2026-10-31_v2.json', 'r', encoding='utf-8') as f:
        data_yesterday = json.load(f)
        
    matches_yesterday_real = []
    for p in data_yesterday.get('predictions', []):
        h = p.get('home_team', '').lower().strip()
        a = p.get('away_team', '').lower().strip()
        gid = str(p.get('game_id', ''))
        act = actual_scores.get(gid) or actual_scores.get((h, a))
        mkt = p.get('market_total')
        src = p.get('odds_source')
        edge = p.get('edge')
        if act and mkt and src not in [None, 'BASELINE', 'AVERAGE'] and edge is not None:
            matches_yesterday_real.append({
                'match': f"{p.get('home_team')} vs {p.get('away_team')}",
                'market': mkt,
                'actual': act,
                'edge': edge
            })
            
    # -------------------------------------------------------------
    # 2. LOAD FULL HISTORICAL GRADED DATABASE (5,155 MATCHES)
    # -------------------------------------------------------------
    matches_historical = []
    pred_files = sorted(glob.glob("data/basketball/universal_predictions_*_v2.json"))
    if not pred_files:
        pred_files = sorted(glob.glob("data/basketball/universal_predictions_*.json"))

    seen_matches = set()
    for pf in pred_files:
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                p_data = json.load(f)
            preds = p_data.get('predictions', []) if isinstance(p_data, dict) else p_data
            for p in preds:
                act_h = p.get("actual_home_score")
                act_a = p.get("actual_away_score")
                model_tot = p.get("model_total")
                mkt_tot = p.get("market_total")

                if act_h is None or act_a is None:
                    continue
                if mkt_tot is None or mkt_tot <= 50:
                    continue
                if model_tot is None or model_tot <= 50:
                    continue

                match_key = f"{p.get('date')}_{p.get('league_id')}_{p.get('home_team')}_{p.get('away_team')}"
                if match_key in seen_matches:
                    continue
                seen_matches.add(match_key)

                act_tot = act_h + act_a
                edge = model_tot - mkt_tot

                matches_historical.append({
                    'match': f"{p.get('home_team')} vs {p.get('away_team')}",
                    'market': mkt_tot,
                    'actual': act_tot,
                    'edge': edge
                })
        except Exception:
            pass

    # RUN AUDITS
    audit_dataset(matches_yesterday_real, "PART A: REAL BOOKMAKER CLOSING LINES AUDIT (2026-10-31, Pinnacle/Bet365)")
    audit_dataset(matches_historical, f"PART B: FULL HISTORICAL GRADED DATABASE AUDIT ({len(matches_historical)} Total Games)")

if __name__ == "__main__":
    run()
