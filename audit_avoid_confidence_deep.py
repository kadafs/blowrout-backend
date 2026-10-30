"""
audit_avoid_confidence_deep.py
Deep audit of the [AVOID] Buffer Floor paired against all Model Confidence Levels,
with a microscope on the [AVOID] Buffer + [AVOID] Confidence ("Double Avoid") cohort.
"""

import glob
import json
import math
from collections import defaultdict

def run_avoid_audit():
    v1_files = sorted([f for f in glob.glob('data/basketball/universal_predictions_*.json') if '_v2' not in f])
    
    avoid_matches = []
    
    for f in v1_files:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                d = json.load(fp)
        except Exception:
            continue
            
        for p in d.get('predictions', []):
            act_h = p.get('actual_home_score')
            act_a = p.get('actual_away_score')
            model_tot = p.get('model_total')
            if act_h is None or act_a is None or not model_tot or model_tot <= 0:
                continue
                
            bt = p.get('buffer_tier')
            if bt != '[AVOID]':
                continue
                
            act_tot = act_h + act_a
            p['act_tot'] = act_tot
            p['delta_model'] = act_tot - model_tot
            p['hit_5pt'] = (p['delta_model'] >= -5.0)
            p['hit_0pt'] = (p['delta_model'] >= 0.0)
            p['under_model'] = (act_tot < model_tot)
            
            mkt = p.get('market_total')
            if mkt and mkt > 50:
                p['has_mkt'] = True
                p['delta_mkt'] = act_tot - mkt
                p['under_mkt'] = (act_tot < mkt)
                p['over_mkt'] = (act_tot > mkt)
                p['push_mkt'] = (act_tot == mkt)
            else:
                p['has_mkt'] = False
                
            # Confidence Band
            cb = p.get('confidence_score_band')
            if cb:
                cb = cb.strip()
            else:
                cb = '[UNKNOWN]'
            p['cb'] = cb
            
            # Numeric Confidence Score
            p['cs'] = p.get('confidence_score', 0.0)
            
            avoid_matches.append(p)

    print(f"Total [AVOID] Buffer Matches Graded: {len(avoid_matches)}")
    
    # -----------------------------------------------------------------------
    # 1. Performance Across ALL Confidence Bands
    # -----------------------------------------------------------------------
    print("\n" + "="*125)
    print("1. [AVOID] BUFFER FLOOR PAIRED WITH EACH CONFIDENCE LEVEL")
    print("="*125)
    
    bands = ['[ELITE]', '[HIGH]', '[SOLID]', '[MODERATE]', '[LOW]', '[AVOID]']
    
    by_band = defaultdict(lambda: {
        'n': 0, 'hit_5': 0, 'under_model': 0, 'model_deltas': [],
        'mkt_n': 0, 'under_mkt': 0, 'over_mkt': 0, 'push_mkt': 0, 'mkt_deltas': []
    })
    
    for p in avoid_matches:
        cb = p['cb']
        s = by_band[cb]
        s['n'] += 1
        if p['hit_5pt']: s['hit_5'] += 1
        if p['under_model']: s['under_model'] += 1
        s['model_deltas'].append(p['delta_model'])
        
        if p['has_mkt']:
            s['mkt_n'] += 1
            if p['under_mkt']: s['under_mkt'] += 1
            if p['over_mkt']: s['over_mkt'] += 1
            if p['push_mkt']: s['push_mkt'] += 1
            s['mkt_deltas'].append(p['delta_mkt'])

    header = f"{'Confidence Band':<15} | {'N':>5} | {'Under Model %':>14} | {'-5pt Floor%':>12} | {'Avg Mdl Delta':>14} | {'Mkt N':>6} | {'Under Mkt Win%':>15} | {'Under ROI':>11} | {'Over Mkt Win%':>14} | {'Avg Mkt Delta':>14}"
    print(header)
    print("-" * len(header))
    
    for cb in bands:
        s = by_band[cb]
        n = s['n']
        if n == 0: continue
        u_mdl_pct = s['under_model'] / n * 100
        h5_pct = s['hit_5'] / n * 100
        avg_mdl = sum(s['model_deltas']) / n
        
        mn = s['mkt_n']
        if mn > 0:
            u_mkt_pct = s['under_mkt'] / mn * 100
            o_mkt_pct = s['over_mkt'] / mn * 100
            avg_mkt = sum(s['mkt_deltas']) / mn
            profit_u = (s['under_mkt'] * (100/110)) - s['over_mkt']
            roi_u = profit_u / max(1, (s['under_mkt'] + s['over_mkt'])) * 100
            u_str = f"{s['under_mkt']}/{mn} ({u_mkt_pct:5.1f}%)"
            o_str = f"{s['over_mkt']}/{mn} ({o_mkt_pct:5.1f}%)"
            roi_str = f"{roi_u:>+8.2f}%"
            avg_mkt_str = f"{avg_mkt:>+11.2f} pts"
        else:
            u_str = "N/A"
            o_str = "N/A"
            roi_str = "N/A"
            avg_mkt_str = "N/A"
            
        print(f"{cb:<15} | {n:>5} | {s['under_model']:>4}/{n} ({u_mdl_pct:5.1f}%) | {h5_pct:10.1f}% | {avg_mdl:>+11.2f} pts | {mn:>6} | {u_str:>15} | {roi_str:>11} | {o_str:>14} | {avg_mkt_str:>14}")

    # -----------------------------------------------------------------------
    # 2. DEEP DIVE: [AVOID] BUFFER + [AVOID] CONFIDENCE ("Double Avoid")
    # -----------------------------------------------------------------------
    print("\n" + "="*125)
    print("2. DEEP DIVE: [AVOID] BUFFER + [AVOID] CONFIDENCE ('DOUBLE AVOID')")
    print("="*125)
    
    double_avoid = [p for p in avoid_matches if p['cb'] == '[AVOID]']
    n_da = len(double_avoid)
    da_mkt = [p for p in double_avoid if p['has_mkt']]
    n_da_mkt = len(da_mkt)
    
    print(f"Total Double Avoid Matches: {n_da} (with Market Lines: {n_da_mkt})")
    
    u_mdl_da = sum(1 for p in double_avoid if p['under_model'])
    h5_da = sum(1 for p in double_avoid if p['hit_5pt'])
    avg_mdl_da = sum(p['delta_model'] for p in double_avoid) / n_da
    std_mdl_da = math.sqrt(sum((p['delta_model'] - avg_mdl_da)**2 for p in double_avoid) / n_da)
    
    u_mkt_da = sum(1 for p in da_mkt if p['under_mkt'])
    o_mkt_da = sum(1 for p in da_mkt if p['over_mkt'])
    p_mkt_da = sum(1 for p in da_mkt if p['push_mkt'])
    avg_mkt_da = sum(p['delta_mkt'] for p in da_mkt) / n_da_mkt
    std_mkt_da = math.sqrt(sum((p['delta_mkt'] - avg_mkt_da)**2 for p in da_mkt) / n_da_mkt)
    profit_da = (u_mkt_da * (100/110)) - o_mkt_da
    roi_da = profit_da / (u_mkt_da + o_mkt_da) * 100
    
    print(f"\nAggregates for Double Avoid (N = {n_da}):")
    print(f"  • Under Model Total        : {u_mdl_da}/{n_da} ({u_mdl_da/n_da*100:.2f}%)")
    print(f"  • Failed -5pt Floor        : {n_da - h5_da}/{n_da} ({(n_da - h5_da)/n_da*100:.2f}%)  [Only {h5_da/n_da*100:.2f}% Hit Floor]")
    print(f"  • Model Delta (Act - Model): {avg_mdl_da:+.2f} pts (StdDev: {std_mdl_da:.2f} pts)")
    print(f"\nVs Bookmaker Market Line (N = {n_da_mkt}):")
    print(f"  • UNDER Market Line Wins   : {u_mkt_da}/{n_da_mkt} ({u_mkt_da/n_da_mkt*100:.2f}%)")
    print(f"  • OVER Market Line Wins    : {o_mkt_da}/{n_da_mkt} ({o_mkt_da/n_da_mkt*100:.2f}%)")
    print(f"  • Pushes / Exact Ties      : {p_mkt_da}/{n_da_mkt}")
    print(f"  • Market Score Delta       : {avg_mkt_da:+.2f} pts (StdDev: {std_mkt_da:.2f} pts)")
    print(f"  • Flat ROI Betting UNDER   : {roi_da:+.2f}%  (Net Units Won: {profit_da:+.2f} units)")

    # -----------------------------------------------------------------------
    # 3. Dissecting Double Avoid by Decision & Market Direction
    # -----------------------------------------------------------------------
    print("\n" + "="*125)
    print("3. DISSECTING DOUBLE AVOID: DECISION & DIRECTIONAL SPLITS")
    print("="*125)
    
    splits = [
        ("All Double Avoid", lambda p: True),
        ("Decision == 'PASS' (Below MBET)", lambda p: p.get('decision') == 'PASS'),
        ("Decision == 'PLAY OVER' (Model Edge Over)", lambda p: p.get('decision') == 'PLAY OVER'),
        ("Model < Market Line (Model Projects Under)", lambda p: p['model_total'] < p['market_total']),
        ("Model < Market Line by >= 3 pts", lambda p: (p['market_total'] - p['model_total']) >= 3.0),
        ("Model < Market Line by >= 5 pts", lambda p: (p['market_total'] - p['model_total']) >= 5.0),
        ("Model < Market Line by >= 8 pts", lambda p: (p['market_total'] - p['model_total']) >= 8.0),
        ("Model >= Market Line (Model Projects Over)", lambda p: p['model_total'] >= p['market_total']),
        ("Model >= Market Line by >= 3 pts", lambda p: (p['model_total'] - p['market_total']) >= 3.0),
    ]
    
    header_s = f"{'Sub-Segment of Double Avoid':<42} | {'Mkt N':>6} | {'Under Mkt Hits':>15} | {'Under Win%':>11} | {'Avg Mkt Delta':>14} | {'Under ROI ($-110$)':>18}"
    print(header_s)
    print("-" * len(header_s))
    
    for label, cond in splits:
        sub = [p for p in da_mkt if cond(p)]
        sn = len(sub)
        if sn == 0: continue
        u = sum(1 for p in sub if p['under_mkt'])
        o = sum(1 for p in sub if p['over_mkt'])
        avg_d = sum(p['delta_mkt'] for p in sub) / sn
        profit = (u * (100/110)) - o
        roi = profit / max(1, (u + o)) * 100
        print(f"{label:<42} | {sn:>6} | {u:>4}/{sn} ({u/sn*100:5.1f}%) | {u/sn*100:10.1f}% | {avg_d:>+11.2f} pts | {roi:>+16.2f}%")

    # -----------------------------------------------------------------------
    # 4. Top Leagues for Double Avoid Under Performance
    # -----------------------------------------------------------------------
    print("\n" + "="*125)
    print("4. TOP LEAGUES IN DOUBLE AVOID (Min 10 Graded Games)")
    print("="*125)
    
    league_da = defaultdict(lambda: {'n': 0, 'under': 0, 'over': 0, 'deltas': []})
    for p in da_mkt:
        l = p.get('league', 'Unknown')
        league_da[l]['n'] += 1
        if p['under_mkt']: league_da[l]['under'] += 1
        if p['over_mkt']: league_da[l]['over'] += 1
        league_da[l]['deltas'].append(p['delta_mkt'])
        
    qual_leagues = [(l, s) for l, s in league_da.items() if s['n'] >= 10]
    qual_leagues.sort(key=lambda x: (x[1]['under'] / x[1]['n']), reverse=True)
    
    header_l = f"{'League':<35} | {'Mkt N':>6} | {'Under Hits':>12} | {'Under Win%':>11} | {'Avg Mkt Delta':>14} | {'Under ROI':>11}"
    print(header_l)
    print("-" * len(header_l))
    for l, s in qual_leagues[:12]:
        u_pct = s['under'] / s['n'] * 100
        avg_d = sum(s['deltas']) / s['n']
        profit = (s['under'] * (100/110)) - s['over']
        roi = profit / (s['under'] + s['over']) * 100
        print(f"{l[:35]:<35} | {s['n']:>6} | {s['under']:>4}/{s['n']} ({u_pct:5.1f}%) | {u_pct:>10.1f}% | {avg_d:>+11.2f} pts | {roi:>+9.2f}%")

if __name__ == '__main__':
    run_avoid_audit()

