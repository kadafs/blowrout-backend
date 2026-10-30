"""
audit_buffer_confidence_pair.py
Audits the pairing of Basketball Buffer Floors with Confidence Levels.
Evaluates both:
1. Model Confidence Score / Bands (0-100 4-pillar score)
2. Market Edge Confidence (HIGH, SOLID, MBET FILTER)
"""

import glob
import json
from collections import defaultdict

def run_pairing_audit():
    files = sorted([f for f in glob.glob('data/basketball/universal_predictions_*.json') if '_v2' not in f])

    matches = []
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
            p['hit_5pt'] = (p['delta_model'] >= -5.0)
            p['hit_0pt'] = (p['delta_model'] >= 0.0)
            p['hit_10pt'] = (p['delta_model'] >= -10.0)
            
            mkt = p.get('market_total')
            if mkt and mkt > 50:
                p['has_mkt'] = True
                p['delta_mkt'] = p['act_tot'] - mkt
                p['mkt_over'] = (p['act_tot'] > mkt)
                p['mkt_under'] = (p['act_tot'] < mkt)
                p['mkt_hit_5'] = (p['act_tot'] >= mkt - 5.0)
            else:
                p['has_mkt'] = False

            # Normalize buffer tier
            bt = p.get('buffer_tier')
            if not bt:
                bt = '[UNSTAMPED]'
            p['bt'] = bt

            # Normalize confidence band
            cb = p.get('confidence_score_band')
            if cb:
                cb = cb.strip()
            else:
                cb = '[UNKNOWN]'
            p['cb'] = cb

            # Numeric confidence score
            cs = p.get('confidence_score', 0.0)
            p['cs'] = cs

            # Market edge confidence
            c_edge = p.get('confidence')
            p['c_edge'] = str(c_edge).strip() if c_edge else 'NONE'

            matches.append(p)

    print(f"Loaded {len(matches)} graded matches.")

    # -------------------------------------------------------------
    # 1. 2D Matrix: Buffer Tier x Confidence Score Band
    # -------------------------------------------------------------
    print("\n" + "="*115)
    print("1. MATRIX: BUFFER TIER  x  CONFIDENCE SCORE BAND (4-Pillar Model Confidence)")
    print("Metric: -5pt Floor Hit Rate (Hits / N)  and  [Vs Market Line Over Hit Rate]")
    print("="*115)

    buffer_tiers = ['[ELITE BUFFER]', '[STRONG BUFFER]', '[STRONG]+', '[NEUTRAL]', '[MARGINAL]', '[AVOID]']
    conf_bands = ['[HIGH]+', '[SOLID]', '[MODERATE]', '[LOW]', '[AVOID]']

    # Helper to bucket conf band
    def get_conf_group(cb):
        if cb in ('[ELITE]', '[HIGH]'):
            return '[HIGH]+'
        elif cb == '[SOLID]':
            return '[SOLID]'
        elif cb == '[MODERATE]':
            return '[MODERATE]'
        elif cb == '[LOW]':
            return '[LOW]'
        elif cb == '[AVOID]':
            return '[AVOID]'
        return '[OTHER]'

    matrix_5pt = defaultdict(lambda: {'n': 0, 'hit_5': 0, 'mkt_n': 0, 'mkt_over': 0, 'mkt_under': 0, 'deltas': [], 'mkt_deltas': []})

    for p in matches:
        cg = get_conf_group(p['cb'])
        bt = p['bt']
        
        # Individual
        matrix_5pt[(bt, cg)]['n'] += 1
        if p['hit_5pt']: matrix_5pt[(bt, cg)]['hit_5'] += 1
        matrix_5pt[(bt, cg)]['deltas'].append(p['delta_model'])
        if p['has_mkt']:
            matrix_5pt[(bt, cg)]['mkt_n'] += 1
            if p['mkt_over']: matrix_5pt[(bt, cg)]['mkt_over'] += 1
            if p['mkt_under']: matrix_5pt[(bt, cg)]['mkt_under'] += 1
            matrix_5pt[(bt, cg)]['mkt_deltas'].append(p['delta_mkt'])

        # Combined [STRONG]+
        if bt in ('[ELITE BUFFER]', '[STRONG BUFFER]'):
            matrix_5pt[('[STRONG]+', cg)]['n'] += 1
            if p['hit_5pt']: matrix_5pt[('[STRONG]+', cg)]['hit_5'] += 1
            matrix_5pt[('[STRONG]+', cg)]['deltas'].append(p['delta_model'])
            if p['has_mkt']:
                matrix_5pt[('[STRONG]+', cg)]['mkt_n'] += 1
                if p['mkt_over']: matrix_5pt[('[STRONG]+', cg)]['mkt_over'] += 1
                if p['mkt_under']: matrix_5pt[('[STRONG]+', cg)]['mkt_under'] += 1
                matrix_5pt[('[STRONG]+', cg)]['mkt_deltas'].append(p['delta_mkt'])

    # Print Table
    header = f"{'Buffer Tier':<18} | {'Conf Band':<12} | {'Graded':>6} | {'-5pt Floor Win%':>16} | {'Avg Model Delta':>16} | {'Market N':>8} | {'Over Mkt Win%':>14} | {'Over ROI':>10}"
    print(header)
    print("-" * len(header))

    for bt in buffer_tiers:
        for cg in conf_bands:
            cell = matrix_5pt[(bt, cg)]
            n = cell['n']
            if n == 0:
                continue
            h5_pct = cell['hit_5'] / n * 100
            avg_d = sum(cell['deltas']) / n
            mn = cell['mkt_n']
            if mn > 0:
                m_over_pct = cell['mkt_over'] / mn * 100
                profit = (cell['mkt_over'] * (100/110)) - (mn - cell['mkt_over'])
                roi = profit / mn * 100
                m_str = f"{cell['mkt_over']}/{mn} ({m_over_pct:5.1f}%)"
                roi_str = f"{roi:>+7.2f}%"
            else:
                m_str = "N/A"
                roi_str = "N/A"
            print(f"{bt:<18} | {cg:<12} | {n:>6} | {cell['hit_5']:>3}/{n} ({h5_pct:5.1f}%) | {avg_d:>+13.2f} pts | {mn:>8} | {m_str:>14} | {roi_str:>10}")
        print("-" * len(header))

    # -------------------------------------------------------------
    # 2. High Confidence vs Low Confidence Comparison for [STRONG]+
    # -------------------------------------------------------------
    print("\n" + "="*115)
    print("2. DOES HIGH CONFIDENCE (Score >= 50 vs < 50) BOOST [STRONG]+ BUFFER PERFORMANCE?")
    print("="*115)

    for threshold in [40, 50, 60]:
        hi = [p for p in matches if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]') and p['cs'] >= threshold]
        lo = [p for p in matches if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]') and p['cs'] < threshold]
        
        n_hi = len(hi)
        n_lo = len(lo)
        
        h5_hi = sum(1 for p in hi if p['hit_5pt'])
        h5_lo = sum(1 for p in lo if p['hit_5pt'])
        
        m_hi = [p for p in hi if p['has_mkt']]
        m_lo = [p for p in lo if p['has_mkt']]
        
        mo_hi = sum(1 for p in m_hi if p['mkt_over'])
        mo_lo = sum(1 for p in m_lo if p['mkt_over'])
        
        roi_hi = ((mo_hi * 100/110) - (len(m_hi) - mo_hi)) / max(1, len(m_hi)) * 100 if m_hi else 0
        roi_lo = ((mo_lo * 100/110) - (len(m_lo) - mo_lo)) / max(1, len(m_lo)) * 100 if m_lo else 0

        print(f"Threshold: Confidence Score >= {threshold}")
        print(f"  [STRONG]+ WITH Score >= {threshold}: N={n_hi:>3} | -5pt Floor: {h5_hi:>3}/{n_hi} ({h5_hi/max(1,n_hi)*100:5.1f}%) | Over Mkt: {mo_hi:>3}/{len(m_hi)} ({mo_hi/max(1,len(m_hi))*100:5.1f}%) | Over ROI: {roi_hi:>+6.2f}%")
        print(f"  [STRONG]+ WITH Score <  {threshold}: N={n_lo:>3} | -5pt Floor: {h5_lo:>3}/{n_lo} ({h5_lo/max(1,n_lo)*100:5.1f}%) | Over Mkt: {mo_lo:>3}/{len(m_lo)} ({mo_lo/max(1,len(m_lo))*100:5.1f}%) | Over ROI: {roi_lo:>+6.2f}%")
        print()

    # -------------------------------------------------------------
    # 3. Buffer Tier paired with Market Edge Confidence (HIGH / SOLID / MBET)
    # -------------------------------------------------------------
    print("\n" + "="*115)
    print("3. BUFFER TIER PAIRED WITH MARKET EDGE CONFIDENCE (HIGH vs SOLID vs MBET FILTER)")
    print("="*115)

    edge_matrix = defaultdict(lambda: {'n': 0, 'hit_5': 0, 'mkt_n': 0, 'mkt_over': 0, 'mkt_under': 0})
    for p in matches:
        if p['bt'] in ('[ELITE BUFFER]', '[STRONG BUFFER]', '[STRONG]+', '[AVOID]'):
            ec = p['c_edge']
            bt = p['bt']
            # Individual
            edge_matrix[(bt, ec)]['n'] += 1
            if p['hit_5pt']: edge_matrix[(bt, ec)]['hit_5'] += 1
            if p['has_mkt']:
                edge_matrix[(bt, ec)]['mkt_n'] += 1
                if p['mkt_over']: edge_matrix[(bt, ec)]['mkt_over'] += 1
                if p['mkt_under']: edge_matrix[(bt, ec)]['mkt_under'] += 1

            if bt in ('[ELITE BUFFER]', '[STRONG BUFFER]'):
                edge_matrix[('[STRONG]+', ec)]['n'] += 1
                if p['hit_5pt']: edge_matrix[('[STRONG]+', ec)]['hit_5'] += 1
                if p['has_mkt']:
                    edge_matrix[('[STRONG]+', ec)]['mkt_n'] += 1
                    if p['mkt_over']: edge_matrix[('[STRONG]+', ec)]['mkt_over'] += 1
                    if p['mkt_under']: edge_matrix[('[STRONG]+', ec)]['mkt_under'] += 1

    header_edge = f"{'Buffer Tier':<18} | {'Edge Conf':<14} | {'N':>5} | {'-5pt Floor Win%':>16} | {'Mkt N':>6} | {'Over Mkt Win%':>14} | {'Over ROI':>10}"
    print(header_edge)
    print("-" * len(header_edge))
    for bt in ['[STRONG]+', '[ELITE BUFFER]', '[STRONG BUFFER]', '[AVOID]']:
        for ec in ['HIGH', 'SOLID', 'MBET FILTER']:
            c = edge_matrix[(bt, ec)]
            if c['n'] == 0: continue
            h5_pct = c['hit_5'] / c['n'] * 100
            mn = c['mkt_n']
            if mn > 0:
                om_pct = c['mkt_over'] / mn * 100
                profit = (c['mkt_over'] * (100/110)) - (mn - c['mkt_over'])
                roi = profit / mn * 100
                om_str = f"{c['mkt_over']}/{mn} ({om_pct:5.1f}%)"
                roi_str = f"{roi:>+7.2f}%"
            else:
                om_str = "N/A"
                roi_str = "N/A"
            print(f"{bt:<18} | {ec:<14} | {c['n']:>5} | {c['hit_5']:>3}/{c['n']} ({h5_pct:5.1f}%) | {mn:>6} | {om_str:>14} | {roi_str:>10}")
        print("-" * len(header_edge))

    # -------------------------------------------------------------
    # 4. Under Pairing: [AVOID] paired with Confidence
    # -------------------------------------------------------------
    print("\n" + "="*115)
    print("4. UNDER PAIRING: [AVOID] BUFFER PAIRED WITH CONFIDENCE BANDS (Betting UNDER vs Market)")
    print("="*115)

    avoid_conf = defaultdict(lambda: {'n': 0, 'under': 0, 'over': 0, 'push': 0, 'deltas': []})
    for p in matches:
        if p['bt'] == '[AVOID]' and p['has_mkt']:
            cg = get_conf_group(p['cb'])
            s = avoid_conf[cg]
            s['n'] += 1
            if p['mkt_under']: s['under'] += 1
            elif p['mkt_over']: s['over'] += 1
            else: s['push'] += 1
            s['deltas'].append(p['delta_mkt'])

    header_u = f"{'Buffer Tier':<10} | {'Conf Band':<12} | {'Mkt N':>6} | {'Under Hits':>11} | {'Under Win%':>11} | {'Avg Delta':>10} | {'Under ROI':>10}"
    print(header_u)
    print("-" * len(header_u))
    for cg in ['[HIGH]+', '[SOLID]', '[MODERATE]', '[LOW]', '[AVOID]']:
        s = avoid_conf[cg]
        if s['n'] == 0: continue
        u_pct = s['under'] / s['n'] * 100
        avg_d = sum(s['deltas']) / s['n']
        profit = (s['under'] * (100/110)) - s['over']
        roi = profit / (s['under'] + s['over']) * 100
        print(f"{'[AVOID]':<10} | {cg:<12} | {s['n']:>6} | {s['under']:>11} | {u_pct:>10.1f}% | {avg_d:>+9.2f}  | {roi:>+9.2f}%")

if __name__ == '__main__':
    run_pairing_audit()
