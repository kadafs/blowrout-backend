"""
backtest_mbet_filter.py
=======================
Backtests the MBET (Minimum Betting Edge Threshold) filter against the
full historical dataset of graded basketball predictions.

Evaluates:
  1. Plays that Clear MBET (Actionable Bets: PLAY OVER / PLAY UNDER)
  2. Plays Below MBET (Filtered Out / PASS)
  3. Win Rate, Net Profit/Loss, and ROI at standard -110 (1.909) odds
  4. Performance breakdowns by:
     - Side (Over vs Under)
     - Edge Size Brackets (Below MBET, +0-3 pts over MBET, +3-6 pts, +6+ pts)
     - Model Architecture ([ADVANCED] vs [SRS])
     - Men vs Women competitions
"""

import glob
import json
import math
import sys
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run_backtest():
    # Load all prediction files (focus on V2 files first, or all unique predictions)
    files = sorted(glob.glob("data/basketball/universal_predictions_*_v2.json"))
    if not files:
        files = sorted(glob.glob("data/basketball/universal_predictions_*.json"))

    print(f"Loading prediction archives across {len(files)} files...")

    # Load league edge thresholds config as fallback
    mbet_matrix = {}
    try:
        with open("configs/league_edge_thresholds.json", "r", encoding="utf-8") as f:
            mbet_matrix = json.load(f)
    except Exception:
        pass

    seen_matches = set()
    records = []

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = json.load(f)
        except Exception:
            continue

        preds = content.get("predictions", []) if isinstance(content, dict) else content
        for p in preds:
            act_h = p.get("actual_home_score")
            act_a = p.get("actual_away_score")
            model_tot = p.get("model_total")
            mkt_tot = p.get("market_total")

            # Must be graded and have a valid market total
            if act_h is None or act_a is None:
                continue
            if mkt_tot is None or mkt_tot <= 50:
                continue
            if model_tot is None or model_tot <= 50:
                continue

            # Deduplicate by match identifier
            match_key = f"{p.get('date')}_{p.get('league_id')}_{p.get('home_team')}_{p.get('away_team')}"
            if match_key in seen_matches:
                continue
            seen_matches.add(match_key)

            act_tot = act_h + act_a
            edge = model_tot - mkt_tot
            abs_edge = abs(edge)

            lid = str(p.get("league_id", ""))
            mbet = p.get("mbet_threshold")
            if not mbet:
                mbet = mbet_matrix.get(lid, {}).get("recommended_minimum_edge", 12.0)

            clears_mbet = (abs_edge >= mbet)

            # Determine side: if model > market -> OVER, else -> UNDER
            projected_side = "OVER" if edge > 0 else "UNDER"

            # Result against market
            if act_tot > mkt_tot:
                market_outcome = "OVER"
            elif act_tot < mkt_tot:
                market_outcome = "UNDER"
            else:
                market_outcome = "PUSH"

            # Grade the bet
            if market_outcome == "PUSH":
                bet_result = "PUSH"
            elif market_outcome == projected_side:
                bet_result = "WIN"
            else:
                bet_result = "LOSS"

            arch = p.get("model_architecture", "[  SRS   ]")
            league = p.get("league", "")
            is_women = ("women" in league.lower() or " w" in league.lower() or "ladies" in league.lower())

            records.append({
                "match": match_key,
                "league": league,
                "is_women": is_women,
                "arch": "[ADVANCED]" if "ADV" in arch else "[  SRS   ]",
                "model_tot": model_tot,
                "mkt_tot": mkt_tot,
                "act_tot": act_tot,
                "edge": edge,
                "abs_edge": abs_edge,
                "mbet": mbet,
                "clears_mbet": clears_mbet,
                "projected_side": projected_side,
                "bet_result": bet_result,
                "market_outcome": market_outcome
            })

    total_games = len(records)
    print(f"\n==========================================================================")
    print(f"  HISTORICAL MBET BACKTEST RESULTS ({total_games:,} UNIQUE GRADED MATCHES)")
    print(f"==========================================================================")

    def compute_stats(subset, name="Subset"):
        w = sum(1 for r in subset if r["bet_result"] == "WIN")
        l = sum(1 for r in subset if r["bet_result"] == "LOSS")
        p = sum(1 for r in subset if r["bet_result"] == "PUSH")
        graded = w + l
        win_pct = (w / graded * 100) if graded > 0 else 0.0

        # Calculate standard betting profit assuming flat 1 unit bets at -110 (win 0.909 units)
        units = (w * 0.90909) - (l * 1.0)
        roi = (units / graded * 100) if graded > 0 else 0.0

        return {
            "name": name,
            "total": len(subset),
            "w": w,
            "l": l,
            "p": p,
            "win_pct": win_pct,
            "units": units,
            "roi": roi
        }

    # 1. Main Comparison: Cleared MBET vs Below MBET
    cleared = [r for r in records if r["clears_mbet"]]
    below = [r for r in records if not r["clears_mbet"]]

    st_cleared = compute_stats(cleared, "🎯 PLAYS (CLEARS MBET)")
    st_below = compute_stats(below, "⚪ BELOW MBET (PASS)")
    st_all = compute_stats(records, "📊 ALL GRADED GAMES")

    print("\n1. PRIMARY FILTER EVALUATION:")
    print("--------------------------------------------------------------------------")
    print(f"  {'Category':<26} | {'Total':<6} | {'W - L - P':<14} | {'Win Rate':<10} | {'ROI (-110)':<10}")
    print("--------------------------------------------------------------------------")
    for s in [st_cleared, st_below, st_all]:
        u_str = f"{s['units']:+0.1f}u"
        roi_str = f"{s['roi']:+0.2f}%"
        print(f"  {s['name']:<26} | {s['total']:<6} | {s['w']}-{s['l']}-{s['p']:<10} | {s['win_pct']:>6.2f}%    | {roi_str:>8} ({u_str})")

    # 2. Breakdown of Cleared MBET: OVER vs UNDER
    cleared_over = [r for r in cleared if r["projected_side"] == "OVER"]
    cleared_under = [r for r in cleared if r["projected_side"] == "UNDER"]

    st_over = compute_stats(cleared_over, "🟢 PLAY OVER (Clears MBET)")
    st_under = compute_stats(cleared_under, "🔴 PLAY UNDER (Clears MBET)")

    print("\n2. DIRECTIONAL SPLIT (FOR CLEARED MBET PLAYS):")
    print("--------------------------------------------------------------------------")
    print(f"  {'Category':<26} | {'Total':<6} | {'W - L - P':<14} | {'Win Rate':<10} | {'ROI (-110)':<10}")
    print("--------------------------------------------------------------------------")
    for s in [st_over, st_under]:
        u_str = f"{s['units']:+0.1f}u"
        roi_str = f"{s['roi']:+0.2f}%"
        print(f"  {s['name']:<26} | {s['total']:<6} | {s['w']}-{s['l']}-{s['p']:<10} | {s['win_pct']:>6.2f}%    | {roi_str:>8} ({u_str})")

    # 3. Edge Magnitude Tiers
    # Tier 1: Below MBET (< MBET)
    # Tier 2: Solid (MBET <= Edge < MBET + 3.0)
    # Tier 3: High (MBET + 3.0 <= Edge < MBET + 6.0)
    # Tier 4: Extreme (Edge >= MBET + 6.0)
    t_below = [r for r in records if r["abs_edge"] < r["mbet"]]
    t_solid = [r for r in records if r["mbet"] <= r["abs_edge"] < r["mbet"] + 3.0]
    t_high = [r for r in records if r["mbet"] + 3.0 <= r["abs_edge"] < r["mbet"] + 6.0]
    t_extreme = [r for r in records if r["abs_edge"] >= r["mbet"] + 6.0]

    st_t_below = compute_stats(t_below, "Below MBET (< Threshold)")
    st_t_solid = compute_stats(t_solid, "Solid Edge (MBET + 0-3 pts)")
    st_t_high = compute_stats(t_high, "High Edge  (MBET + 3-6 pts)")
    st_t_extreme = compute_stats(t_extreme, "Extreme Edge (MBET + 6+ pts)")

    print("\n3. EDGE SIZE PROGRESSION:")
    print("--------------------------------------------------------------------------")
    print(f"  {'Edge Tier':<28} | {'Total':<6} | {'W - L - P':<14} | {'Win Rate':<10} | {'ROI (-110)':<10}")
    print("--------------------------------------------------------------------------")
    for s in [st_t_below, st_t_solid, st_t_high, st_t_extreme]:
        u_str = f"{s['units']:+0.1f}u"
        roi_str = f"{s['roi']:+0.2f}%"
        print(f"  {s['name']:<28} | {s['total']:<6} | {s['w']}-{s['l']}-{s['p']:<10} | {s['win_pct']:>6.2f}%    | {roi_str:>8} ({u_str})")

    # 4. Model Architecture Breakdown
    cleared_adv = [r for r in cleared if r["arch"] == "[ADVANCED]"]
    cleared_srs = [r for r in cleared if r["arch"] == "[  SRS   ]"]

    st_adv = compute_stats(cleared_adv, "[ADVANCED] Four Factors")
    st_srs = compute_stats(cleared_srs, "[  SRS   ] Iterative SRS")

    print("\n4. MODEL ARCHITECTURE (CLEARS MBET):")
    print("--------------------------------------------------------------------------")
    print(f"  {'Architecture':<26} | {'Total':<6} | {'W - L - P':<14} | {'Win Rate':<10} | {'ROI (-110)':<10}")
    print("--------------------------------------------------------------------------")
    for s in [st_adv, st_srs]:
        u_str = f"{s['units']:+0.1f}u"
        roi_str = f"{s['roi']:+0.2f}%"
        print(f"  {s['name']:<26} | {s['total']:<6} | {s['w']}-{s['l']}-{s['p']:<10} | {s['win_pct']:>6.2f}%    | {roi_str:>8} ({u_str})")

    # 5. Men vs Women Breakdown
    cleared_men = [r for r in cleared if not r["is_women"]]
    cleared_women = [r for r in cleared if r["is_women"]]

    st_men = compute_stats(cleared_men, "Men's Competitions")
    st_women = compute_stats(cleared_women, "Women's Competitions")

    print("\n5. COMPETITION GENDER (CLEARS MBET):")
    print("--------------------------------------------------------------------------")
    print(f"  {'Gender Category':<26} | {'Total':<6} | {'W - L - P':<14} | {'Win Rate':<10} | {'ROI (-110)':<10}")
    print("--------------------------------------------------------------------------")
    for s in [st_men, st_women]:
        u_str = f"{s['units']:+0.1f}u"
        roi_str = f"{s['roi']:+0.2f}%"
        print(f"  {s['name']:<26} | {s['total']:<6} | {s['w']}-{s['l']}-{s['p']:<10} | {s['win_pct']:>6.2f}%    | {roi_str:>8} ({u_str})")

    print("==========================================================================\n")

if __name__ == "__main__":
    run_backtest()
