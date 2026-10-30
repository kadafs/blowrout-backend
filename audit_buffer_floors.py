"""
audit_buffer_floors.py
Comprehensive audit of Basketball Buffer Floors across historical graded games.
"""

import glob
import json
import os
import math
from collections import defaultdict

def run_audit():
    v1_files = sorted([f for f in glob.glob('data/basketball/universal_predictions_*.json') if '_v2' not in f])
    v2_files = sorted(glob.glob('data/basketball/universal_predictions_*_v2.json'))

    print(f"Loaded {len(v1_files)} V1 files and {len(v2_files)} V2 files.")

    def audit_file_set(files, label="V1"):
        # Accumulators
        tier_stats = defaultdict(lambda: {
            'count': 0,
            'hit_0': 0,
            'hit_3': 0,
            'hit_5': 0,
            'hit_7': 0,
            'hit_10': 0,
            'hit_15': 0,
            'deltas': [],
            'mkt_count': 0,
            'mkt_hit': 0,
            'mkt_hit_5': 0,
            'mkt_deltas': [],
        })

        # By min_games
        sample_stats = defaultdict(lambda: {
            'count': 0,
            'hit_5': 0,
            'deltas': []
        })

        # By league
        league_stats = defaultdict(lambda: {
            'count': 0,
            'hit_5': 0,
            'elite_strong_count': 0,
            'elite_strong_hit_5': 0,
            'deltas': []
        })

        # Global floor stats across all games regardless of tier
        global_floors = {
            'count': 0,
            'hit_0': 0,
            'hit_3': 0,
            'hit_5': 0,
            'hit_7': 0,
            'hit_10': 0,
            'hit_15': 0,
            'deltas': [],
            'mkt_count': 0,
            'mkt_hit': 0,
            'mkt_hit_5': 0,
            'mkt_deltas': []
        }

        total_games = 0
        total_graded = 0

        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
            except Exception as e:
                continue

            predictions = data.get('predictions', [])
            total_games += len(predictions)

            for p in predictions:
                act_h = p.get('actual_home_score')
                act_a = p.get('actual_away_score')
                model_tot = p.get('model_total')
                if act_h is None or act_a is None or not model_tot or model_tot <= 0:
                    continue

                act_tot = act_h + act_a
                delta = act_tot - model_tot
                total_graded += 1

                # Global
                global_floors['count'] += 1
                global_floors['deltas'].append(delta)
                if delta >= 0.0: global_floors['hit_0'] += 1
                if delta >= -3.0: global_floors['hit_3'] += 1
                if delta >= -5.0: global_floors['hit_5'] += 1
                if delta >= -7.0: global_floors['hit_7'] += 1
                if delta >= -10.0: global_floors['hit_10'] += 1
                if delta >= -15.0: global_floors['hit_15'] += 1

                mkt = p.get('market_total')
                if mkt and mkt > 50:
                    mkt_diff = act_tot - mkt
                    global_floors['mkt_count'] += 1
                    global_floors['mkt_deltas'].append(mkt_diff)
                    if act_tot >= mkt: global_floors['mkt_hit'] += 1
                    if act_tot >= (mkt - 5.0): global_floors['mkt_hit_5'] += 1

                # Tier
                tier = p.get('buffer_tier')
                if not tier:
                    tier = '[UNSTAMPED / PRE-OCT12]'

                s = tier_stats[tier]
                s['count'] += 1
                s['deltas'].append(delta)
                if delta >= 0.0: s['hit_0'] += 1
                if delta >= -3.0: s['hit_3'] += 1
                if delta >= -5.0: s['hit_5'] += 1
                if delta >= -7.0: s['hit_7'] += 1
                if delta >= -10.0: s['hit_10'] += 1
                if delta >= -15.0: s['hit_15'] += 1

                if mkt and mkt > 50:
                    s['mkt_count'] += 1
                    s['mkt_deltas'].append(mkt_diff)
                    if act_tot >= mkt: s['mkt_hit'] += 1
                    if act_tot >= (mkt - 5.0): s['mkt_hit_5'] += 1

                # Min sample size
                gh = p.get('graded_h')
                ga = p.get('graded_a')
                if gh is not None and ga is not None:
                    min_g = min(gh, ga)
                    bucket = f"min_N >= {min_g}" if min_g >= 5 else f"min_N = {min_g}"
                    sample_stats[bucket]['count'] += 1
                    sample_stats[bucket]['deltas'].append(delta)
                    if delta >= -5.0:
                        sample_stats[bucket]['hit_5'] += 1

                # League stats
                l_name = p.get('league', 'Unknown')
                league_stats[l_name]['count'] += 1
                league_stats[l_name]['deltas'].append(delta)
                if delta >= -5.0:
                    league_stats[l_name]['hit_5'] += 1
                if tier in ('[ELITE BUFFER]', '[STRONG BUFFER]'):
                    league_stats[l_name]['elite_strong_count'] += 1
                    if delta >= -5.0:
                        league_stats[l_name]['elite_strong_hit_5'] += 1

        return {
            'label': label,
            'total_games': total_games,
            'total_graded': total_graded,
            'global_floors': global_floors,
            'tier_stats': tier_stats,
            'sample_stats': sample_stats,
            'league_stats': league_stats,
        }

    res_v1 = audit_file_set(v1_files, "V1")
    res_v2 = audit_file_set(v2_files, "V2")

    return res_v1, res_v2

if __name__ == '__main__':
    r1, r2 = run_audit()

    for r in [r1, r2]:
        label = r['label']
        print("=" * 110)
        print(f"AUDIT RESULTS: BASKETBALL BUFFER FLOORS ({label} ARCHITECTURE)")
        print(f"Total Games Analyzed: {r['total_games']} | Total Graded Matchups: {r['total_graded']}")
        print("=" * 110)

        # 1. Global Baseline Floor Distribution
        gf = r['global_floors']
        n = gf['count']
        print("\n--- 1. GLOBAL BASELINE: OVERALL HIT RATE ACROSS DIFFERENT BUFFER OFFSETS ---")
        print(f"All Graded Matches (N = {n}):")
        print(f"  Floor: Model Total -  0.0 pts (Exact Over)   : {gf['hit_0']:>4}/{n} ({gf['hit_0']/n*100:5.2f}%)")
        print(f"  Floor: Model Total -  3.0 pts Buffer Floor   : {gf['hit_3']:>4}/{n} ({gf['hit_3']/n*100:5.2f}%)")
        print(f"  Floor: Model Total -  5.0 pts Buffer Floor   : {gf['hit_5']:>4}/{n} ({gf['hit_5']/n*100:5.2f}%)  <-- Standard System Floor")
        print(f"  Floor: Model Total -  7.0 pts Buffer Floor   : {gf['hit_7']:>4}/{n} ({gf['hit_7']/n*100:5.2f}%)")
        print(f"  Floor: Model Total - 10.0 pts Buffer Floor   : {gf['hit_10']:>4}/{n} ({gf['hit_10']/n*100:5.2f}%)")
        print(f"  Floor: Model Total - 15.0 pts Buffer Floor   : {gf['hit_15']:>4}/{n} ({gf['hit_15']/n*100:5.2f}%)")
        avg_d = sum(gf['deltas']) / n
        std_d = math.sqrt(sum((x - avg_d)**2 for x in gf['deltas']) / n)
        print(f"  Global Score Delta (Actual - Model)          : {avg_d:>+5.2f} pts (StdDev: {std_d:.2f} pts)")
        if gf['mkt_count'] > 0:
            mn = gf['mkt_count']
            print(f"  Vs Market Line: Over Market Line             : {gf['mkt_hit']:>4}/{mn} ({gf['mkt_hit']/mn*100:5.2f}%)")
            print(f"  Vs Market Line: Market Line - 5.0 pts Floor  : {gf['mkt_hit_5']:>4}/{mn} ({gf['mkt_hit_5']/mn*100:5.2f}%)")

        # 2. Tier Breakdown
        print("\n--- 2. EMPIRICAL HIT RATES BY BUFFER FLOOR TIER (FORWARD STAMPED) ---")
        tiers = ['[ELITE BUFFER]', '[STRONG BUFFER]', '[STRONG]+', '[NEUTRAL]', '[MARGINAL]', '[AVOID]', '[UNSTAMPED / PRE-OCT12]']
        
        # Calculate combined [STRONG]+
        ts = r['tier_stats']
        c_elite = ts.get('[ELITE BUFFER]', {})
        c_strong = ts.get('[STRONG BUFFER]', {})
        ts['[STRONG]+'] = {
            'count': c_elite.get('count', 0) + c_strong.get('count', 0),
            'hit_0': c_elite.get('hit_0', 0) + c_strong.get('hit_0', 0),
            'hit_3': c_elite.get('hit_3', 0) + c_strong.get('hit_3', 0),
            'hit_5': c_elite.get('hit_5', 0) + c_strong.get('hit_5', 0),
            'hit_7': c_elite.get('hit_7', 0) + c_strong.get('hit_7', 0),
            'hit_10': c_elite.get('hit_10', 0) + c_strong.get('hit_10', 0),
            'hit_15': c_elite.get('hit_15', 0) + c_strong.get('hit_15', 0),
            'deltas': c_elite.get('deltas', []) + c_strong.get('deltas', []),
            'mkt_count': c_elite.get('mkt_count', 0) + c_strong.get('mkt_count', 0),
            'mkt_hit': c_elite.get('mkt_hit', 0) + c_strong.get('mkt_hit', 0),
            'mkt_hit_5': c_elite.get('mkt_hit_5', 0) + c_strong.get('mkt_hit_5', 0),
            'mkt_deltas': c_elite.get('mkt_deltas', []) + c_strong.get('mkt_deltas', []),
        }

        header = f"{'Buffer Tier':<24} | {'N':>5} | {'-5pt Floor (Std)':>16} | {'-3pt Floor':>12} | {'Exact (0pt)':>12} | {'-10pt Floor':>12} | {'Avg Delta':>10} | {'Over Mkt Line':>15} | {'Mkt -5pt Floor':>15}"
        print(header)
        print("-" * len(header))
        for t in tiers:
            s = ts.get(t)
            if not s or s['count'] == 0:
                continue
            sn = s['count']
            h5 = s['hit_5'] / sn * 100
            h3 = s['hit_3'] / sn * 100
            h0 = s['hit_0'] / sn * 100
            h10 = s['hit_10'] / sn * 100
            ad = sum(s['deltas']) / sn
            if s['mkt_count'] > 0:
                om = f"{s['mkt_hit']}/{s['mkt_count']} ({s['mkt_hit']/s['mkt_count']*100:5.1f}%)"
                om5 = f"{s['mkt_hit_5']}/{s['mkt_count']} ({s['mkt_hit_5']/s['mkt_count']*100:5.1f}%)"
            else:
                om = "N/A"
                om5 = "N/A"
            print(f"{t:<24} | {sn:>5} | {s['hit_5']:>4}/{sn} ({h5:5.1f}%) | {s['hit_3']:>4}/{sn} ({h3:5.1f}%) | {s['hit_0']:>4}/{sn} ({h0:5.1f}%) | {s['hit_10']:>4}/{sn} ({h10:5.1f}%) | {ad:>+9.2f}  | {om:>15} | {om5:>15}")

        # 3. Sample Size Impact
        print("\n--- 3. SAMPLE SIZE (N) IMPACT ON -5PT BUFFER FLOOR HIT RATE ---")
        ss = r['sample_stats']
        sorted_samples = sorted(ss.keys())
        print(f"{'Sample Bucket':<18} | {'N':>5} | {'-5pt Floor Hits':>16} | {'Win Rate':>9} | {'Avg Delta':>10}")
        print("-" * 65)
        for sb in sorted_samples:
            s = ss[sb]
            sn = s['count']
            ad = sum(s['deltas']) / sn if sn > 0 else 0
            pct = s['hit_5'] / sn * 100 if sn > 0 else 0
            print(f"{sb:<18} | {sn:>5} | {s['hit_5']:>4}/{sn:>4}         | {pct:8.2f}% | {ad:>+9.2f}")

        # 4. Top Leagues by Elite/Strong Hit Rate
        print("\n--- 4. TOP LEAGUES PERFORMANCE ON BUFFER FLOORS (Min 25 graded games) ---")
        ls = r['league_stats']
        qualifying = [(l, s) for l, s in ls.items() if s['count'] >= 25]
        qualifying.sort(key=lambda x: (x[1]['hit_5'] / x[1]['count']), reverse=True)

        print(f"{'League':<35} | {'Graded':>6} | {'-5pt Floor Win Rate':>20} | {'Avg Delta':>10} | {'Elite/Strong (Hit/N)':>22}")
        print("-" * 105)
        for l, s in qualifying[:15]:
            pct = s['hit_5'] / s['count'] * 100
            ad = sum(s['deltas']) / s['count']
            es_str = f"{s['elite_strong_hit_5']}/{s['elite_strong_count']} ({(s['elite_strong_hit_5']/s['elite_strong_count']*100):.1f}%)" if s['elite_strong_count'] > 0 else "0/0"
            print(f"{l[:35]:<35} | {s['count']:>6} | {s['hit_5']:>4}/{s['count']} ({pct:5.1f}%)     | {ad:>+9.2f}  | {es_str:>22}")

        print("\n--- BOTTOM 5 LEAGUES (MOST BUFFER LEAKAGE / HIGH VOLATILITY) ---")
        for l, s in qualifying[-5:]:
            pct = s['hit_5'] / s['count'] * 100
            ad = sum(s['deltas']) / s['count']
            es_str = f"{s['elite_strong_hit_5']}/{s['elite_strong_count']} ({(s['elite_strong_hit_5']/s['elite_strong_count']*100):.1f}%)" if s['elite_strong_count'] > 0 else "0/0"
            print(f"{l[:35]:<35} | {s['count']:>6} | {s['hit_5']:>4}/{s['count']} ({pct:5.1f}%)     | {ad:>+9.2f}  | {es_str:>22}")

        print("\n")

