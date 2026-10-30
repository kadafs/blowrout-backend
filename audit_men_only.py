"""
audit_men_only.py
Comprehensive audit comparing Men's Basketball vs Women's Basketball vs All
across Buffer Floors, Buffer Tiers, Confidence Pairings, and Double Avoid.
"""

import glob
import json
import re
import math
from collections import defaultdict

def is_womens_match(p):
    l = (p.get('league') or '').lower()
    h = (p.get('home_team') or '').lower()
    a = (p.get('away_team') or '').lower()
    if 'women' in l or 'woman' in l or 'ladies' in l or 'wnba' in l:
        return True
    if re.search(r'\b(w|women)\b', l) or l.endswith(' w'):
        return True
    if h.endswith(' w') or a.endswith(' w') or h.endswith(' (w)') or a.endswith(' (w)'):
        return True
    return False

def run_audit():
    files = sorted([f for f in glob.glob('data/basketball/universal_predictions_*.json') if '_v2' not in f])
    
    all_games = []
    
    for f in files:
        with open(f, 'r', encoding='utf-8') as fp:
            d = json.load(fp)
        for p in d.get('predictions', []):
            act_h = p.get('actual_home_score')
            act_a = p.get('actual_away_score')
            model_tot = p.get('model_total')
            if act_h is None or act_a is None or not model_tot or model_tot <= 0:
                continue
            
            p['act_tot'] = act_h + act_a
            p['delta_model'] = p['act_tot'] - model_tot
            p['is_women'] = is_womens_match(p)
            
            mkt = p.get('market_total')
            if mkt and mkt > 50:
                p['has_mkt'] = True
                p['delta_mkt'] = p['act_tot'] - mkt
                p['over_mkt'] = (p['act_tot'] > mkt)
                p['under_mkt'] = (p['act_tot'] < mkt)
                p['push_mkt'] = (p['act_tot'] == mkt)
                p['mkt_hit_5'] = (p['act_tot'] >= mkt - 5.0)
            else:
                p['has_mkt'] = False
                
            p['bt'] = p.get('buffer_tier') or '[UNSTAMPED]'
            p['cb'] = (p.get('confidence_score_band') or '[UNKNOWN]').strip()
            p['ec'] = str(p.get('confidence') or 'NONE').strip()
            p['cs'] = p.get('confidence_score', 0.0)
            all_games.append(p)
            
    print(f"Total Graded: {len(all_games)}")
    men_games = [p for p in all_games if not p['is_women']]
    women_games = [p for p in all_games if p['is_women']]
    print(f"Men Graded: {len(men_games)} ({len(men_games)/len(all_games)*100:.1f}%)")
    print(f"Women Graded: {len(women_games)} ({len(women_games)/len(all_games)*100:.1f}%)")

    # -----------------------------------------------------------------------
    # 1. Global Baseline: Men vs Women vs All
    # -----------------------------------------------------------------------
    print("\n" + "="*115)
    print("1. GLOBAL BASELINE COMPARISON: MEN ONLY vs WOMEN ONLY vs ALL")
    print("="*115)
    
    header1 = f"{'Cohort':<14} | {'Graded N':>8} | {'Exact (0pt)':>12} | {'-3pt Floor':>12} | {'-5pt Floor (Std)':>16} | {'-10pt Floor':>12} | {'Avg Model Delta':>16} | {'Over Mkt Win%':>14} | {'Mkt -5pt Floor':>15}"
    print(header1)
    print("-" * len(header1))
    
    for label, cohort in [("ALL BASKETBALL", all_games), ("MEN ONLY", men_games), ("WOMEN ONLY", women_games)]:
        n = len(cohort)
        h0 = sum(1 for p in cohort if p['delta_model'] >= 0.0)
        h3 = sum(1 for p in cohort if p['delta_model'] >= -3.0)
        h5 = sum(1 for p in cohort if p['delta_model'] >= -5.0)
        h10 = sum(1 for p in cohort if p['delta_model'] >= -10.0)
        avg_d = sum(p['delta_model'] for p in cohort) / n
        
        mkt_p = [p for p in cohort if p['has_mkt']]
        mn = len(mkt_p)
        if mn > 0:
            mo = sum(1 for p in mkt_p if p['over_mkt'])
            mo5 = sum(1 for p in mkt_p if p['mkt_hit_5'])
            mo_str = f"{mo}/{mn} ({mo/mn*100:5.1f}%)"
            mo5_str = f"{mo5}/{mn} ({mo5/mn*100:5.1f}%)"
        else:
            mo_str = "N/A"
            mo5_str = "N/A"
            
        print(f"{label:<14} | {n:>8} | {h0:>4}/{n} ({h0/n*100:4.1f}%) | {h3:>4}/{n} ({h3/n*100:4.1f}%) | {h5:>4}/{n} ({h5/n*100:5.1f}%) | {h10:>4}/{n} ({h10/n*100:5.1f}%) | {avg_d:>+13.2f} pts | {mo_str:>14} | {mo5_str:>15}")

    # -----------------------------------------------------------------------
    # 2. Buffer Floor Tiers (MEN ONLY vs ALL)
    # -----------------------------------------------------------------------
    print("\n" + "="*115)
    print("2. BUFFER TIER PERFORMANCE: MEN ONLY (vs ALL)")
    print("="*115)
    
    tiers = ['[ELITE BUFFER]', '[STRONG BUFFER]', '[STRONG]+', '[NEUTRAL]', '[MARGINAL]', '[AVOID]']
    
    header2 = f"{'Buffer Tier':<18} | {'Men N':>6} | {'Men -5pt Hit%':>14} | {'(All -5pt Hit%)':>16} | {'Avg Model Delta':>16} | {'Men Mkt N':>9} | {'Over Mkt Win%':>14} | {'Over ROI':>10}"
    print(header2)
    print("-" * len(header2))
    
    for bt in tiers:
        if bt == '[STRONG]+':
            men_sub = [p for p in men_games if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]')]
            all_sub = [p for p in all_games if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]')]
        else:
            men_sub = [p for p in men_games if p['bt'] == bt]
            all_sub = [p for p in all_games if p['bt'] == bt]
            
        n_men = len(men_sub)
        n_all = len(all_sub)
        if n_men == 0: continue
        
        h5_men = sum(1 for p in men_sub if p['delta_model'] >= -5.0)
        h5_all = sum(1 for p in all_sub if p['delta_model'] >= -5.0)
        avg_d_men = sum(p['delta_model'] for p in men_sub) / n_men
        
        mkt_men = [p for p in men_sub if p['has_mkt']]
        mn_men = len(mkt_men)
        if mn_men > 0:
            mo_men = sum(1 for p in mkt_men if p['over_mkt'])
            mo_men_pct = mo_men / mn_men * 100
            profit = (mo_men * (100/110)) - (mn_men - mo_men)
            roi = profit / mn_men * 100
            mo_str = f"{mo_men}/{mn_men} ({mo_men_pct:5.1f}%)"
            roi_str = f"{roi:>+7.2f}%"
        else:
            mo_str = "N/A"
            roi_str = "N/A"
            
        print(f"{bt:<18} | {n_men:>6} | {h5_men:>3}/{n_men} ({h5_men/n_men*100:5.1f}%) | {h5_all:>4}/{n_all} ({h5_all/n_all*100:5.1f}%) | {avg_d_men:>+13.2f} pts | {mn_men:>9} | {mo_str:>14} | {roi_str:>10}")

    # -----------------------------------------------------------------------
    # 3. [STRONG]+ paired with MBET Edge (MEN ONLY)
    # -----------------------------------------------------------------------
    print("\n" + "="*115)
    print("3. [STRONG]+ BUFFER PAIRED WITH MBET EDGE (MEN ONLY)")
    print("="*115)
    
    strong_men = [p for p in men_games if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]')]
    
    for ec_label, cond in [
        ("HIGH Edge Confidence", lambda p: p['ec'] == 'HIGH'),
        ("SOLID Edge Confidence", lambda p: p['ec'] == 'SOLID'),
        ("HIGH or SOLID Edge (Clears MBET)", lambda p: p['ec'] in ('HIGH', 'SOLID')),
        ("MBET FILTER (Below Edge Threshold)", lambda p: p['ec'] == 'MBET FILTER'),
    ]:
        sub = [p for p in strong_men if cond(p)]
        n = len(sub)
        if n == 0: continue
        h5 = sum(1 for p in sub if p['delta_model'] >= -5.0)
        mkt_sub = [p for p in sub if p['has_mkt']]
        mn = len(mkt_sub)
        mo = sum(1 for p in mkt_sub if p['over_mkt'])
        profit = (mo * 100/110) - (mn - mo) if mn > 0 else 0
        roi = profit / mn * 100 if mn > 0 else 0
        print(f"  {ec_label:<38} | N={n:>3} | -5pt Floor: {h5:>3}/{n} ({h5/n*100:5.1f}%) | Mkt N={mn:>3} | Over Mkt: {mo:>3}/{mn} ({mo/max(1,mn)*100:5.1f}%) | Over ROI: {roi:>+6.2f}%")

    # -----------------------------------------------------------------------
    # 4. Double Avoid (MEN ONLY)
    # -----------------------------------------------------------------------
    print("\n" + "="*115)
    print("4. 'DOUBLE AVOID' ([AVOID] BUFFER + [AVOID] CONFIDENCE) -- MEN ONLY")
    print("="*115)
    
    da_men = [p for p in men_games if p['bt'] == '[AVOID]' and p['cb'] == '[AVOID]']
    n_da = len(da_men)
    da_mkt = [p for p in da_men if p['has_mkt']]
    mn_da = len(da_mkt)
    
    u_mdl = sum(1 for p in da_men if p['delta_model'] < 0.0)
    h5 = sum(1 for p in da_men if p['delta_model'] >= -5.0)
    avg_mdl = sum(p['delta_model'] for p in da_men) / n_da
    
    u_mkt = sum(1 for p in da_mkt if p['under_mkt'])
    o_mkt = sum(1 for p in da_mkt if p['over_mkt'])
    avg_mkt = sum(p['delta_mkt'] for p in da_mkt) / mn_da
    profit_u = (u_mkt * 100/110) - o_mkt
    roi_u = profit_u / (u_mkt + o_mkt) * 100
    
    print(f"Men Only Double Avoid: Total N = {n_da} (with Market: {mn_da})")
    print(f"  • Under Model Total        : {u_mdl}/{n_da} ({u_mdl/n_da*100:.2f}%)")
    print(f"  • Failed -5pt Floor        : {n_da - h5}/{n_da} ({(n_da - h5)/n_da*100:.2f}%)")
    print(f"  • Avg Model Delta          : {avg_mdl:+.2f} pts")
    print(f"  • Under Market Line Wins   : {u_mkt}/{mn_da} ({u_mkt/mn_da*100:.2f}%)")
    print(f"  • Over Market Line Wins    : {o_mkt}/{mn_da} ({o_mkt/mn_da*100:.2f}%)")
    print(f"  • Avg Market Delta         : {avg_mkt:+.2f} pts")
    print(f"  • Under Flat ROI ($-110$)  : {roi_u:+.2f}% (Net Units Won: {profit_u:+.2f} units)")
    
    print("\n  Sub-Segment Directional Splits (Men Only Double Avoid):")
    for s_name, cond in [
        ("Decision == 'PASS' (Below MBET)", lambda p: p.get('decision') == 'PASS'),
        ("Decision == 'PLAY OVER' (Model Edge Over)", lambda p: p.get('decision') == 'PLAY OVER'),
        ("Model < Market Line (Projects Under)", lambda p: p['model_total'] < p['market_total']),
        ("Model < Market Line by >= 3 pts", lambda p: (p['market_total'] - p['model_total']) >= 3.0),
        ("Model < Market Line by >= 5 pts", lambda p: (p['market_total'] - p['model_total']) >= 5.0),
        ("Model < Market Line by >= 8 pts", lambda p: (p['market_total'] - p['model_total']) >= 8.0),
    ]:
        sub = [p for p in da_mkt if cond(p)]
        sn = len(sub)
        if sn == 0: continue
        u = sum(1 for p in sub if p['under_mkt'])
        o = sum(1 for p in sub if p['over_mkt'])
        avg_d = sum(p['delta_mkt'] for p in sub) / sn
        profit = (u * 100/110) - o
        roi = profit / max(1, (u + o)) * 100
        print(f"    {s_name:<40} | N={sn:>4} | Under: {u:>3}/{sn} ({u/sn*100:5.1f}%) | Avg Delta: {avg_d:>+5.2f} pts | Under ROI: {roi:>+6.2f}%")

if __name__ == '__main__':
    run_audit()
