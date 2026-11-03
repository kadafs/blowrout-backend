"""
scripts/audit_graded_ncaa.py
===========================
Comprehensive audit of all graded NCAA basketball games across both
Men's (116, 11600-11631) and Women's (423, 42300-42331) conferences.
"""

import glob
import json
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

def is_ncaa_game(pred):
    lid = pred.get("league_id", 0)
    lname = str(pred.get("league", "")).lower()
    if lid in (116, 423):
        return True
    if 11600 <= lid <= 11699 or 42300 <= lid <= 42399:
        return True
    if "ncaa" in lname:
        return True
    return False

def get_gender(pred):
    lid = pred.get("league_id", 0)
    lname = str(pred.get("league", "")).lower()
    h = str(pred.get("home_team", ""))
    a = str(pred.get("away_team", ""))
    if lid == 423 or (42300 <= lid <= 42399) or "women" in lname or h.endswith(" W") or a.endswith(" W"):
        return "Women"
    return "Men"

def audit():
    files = sorted(glob.glob("data/basketball/universal_predictions_*_v2.json"))
    if not files:
        files = sorted(glob.glob("data/basketball/universal_predictions_*.json"))

    all_ncaa = []
    by_date = {}

    for fpath in files:
        date_str = os.path.basename(fpath).replace("universal_predictions_", "").replace("_v2.json", "").replace(".json", "")
        with open(fpath, "r", encoding="utf-8") as fp:
            d = json.load(fp)
        
        preds = d.get("predictions", [])
        ncaa_preds = [p for p in preds if is_ncaa_game(p)]
        if ncaa_preds:
            by_date[date_str] = ncaa_preds
            all_ncaa.extend(ncaa_preds)

    print("=" * 110)
    print("                      OFFICIAL NCAA GRADED PREDICTIONS AUDIT")
    print("=" * 110)
    print(f"Total NCAA Predictions Indexed Across All Dates: {len(all_ncaa)}")
    
    graded_games = [p for p in all_ncaa if p.get("actual_result") is not None]
    ungraded_games = [p for p in all_ncaa if p.get("actual_result") is None]
    print(f"Total NCAA Graded Games: {len(graded_games)}")
    print(f"Total NCAA Pending/Ungraded Games: {len(ungraded_games)}")
    print("-" * 110)

    # Breakdown by Date
    print("\n📅 BREAKDOWN BY DATE:")
    for dt in sorted(by_date.keys()):
        games = by_date[dt]
        gr = [p for p in games if p.get("actual_result") is not None]
        print(f"  • {dt}: {len(games):2d} total NCAA games | {len(gr):2d} graded | {len(games)-len(gr):2d} pending")

    # Breakdown by Gender
    men_graded = [p for p in graded_games if get_gender(p) == "Men"]
    women_graded = [p for p in graded_games if get_gender(p) == "Women"]

    print("\n👥 BREAKDOWN BY GENDER:")
    print(f"  • Men's NCAA Graded:   {len(men_graded)}")
    print(f"  • Women's NCAA Graded: {len(women_graded)}")

    # Accuracy Metrics
    def calc_metrics(games, label):
        if not games:
            print(f"\n--- {label}: No graded games ---")
            return
        
        wins = sum(1 for p in games if p.get("predicted_result") == p.get("actual_result"))
        tot = len(games)
        win_pct = (wins / tot) * 100

        deltas = [p.get("total_delta") for p in games if p.get("total_delta") is not None]
        signed = [p.get("signed_delta") for p in games if p.get("signed_delta") is not None]
        
        mae = sum(deltas) / len(deltas) if deltas else 0.0
        bias = sum(signed) / len(signed) if signed else 0.0

        # Tiers
        from collections import Counter
        tiers = Counter(p.get("accuracy_tier") for p in games if p.get("accuracy_tier"))

        print(f"\n📊 {label} (Sample = {tot} games):")
        print(f"  • Straight-Up Win Rate:   {wins}/{tot} ({win_pct:.1f}%)")
        print(f"  • Totals MAE:             {mae:.2f} pts")
        print(f"  • Totals Bias (Signed):   {bias:+.2f} pts {'(Overshooting)' if bias < 0 else '(Undershooting)' if bias > 0 else ''}")
        print(f"  • Accuracy Tiers:")
        for t in ["BULLSEYE", "EXCELLENT", "SOLID", "MISS", "BUST", "OT WARP"]:
            if tiers[t]:
                pct = (tiers[t] / tot) * 100
                print(f"      - {t:10s}: {tiers[t]:2d} ({pct:4.1f}%)")

    calc_metrics(graded_games, "ALL NCAA COMBINED")
    calc_metrics(men_graded, "NCAA MEN'S DIVISION 1")
    calc_metrics(women_graded, "NCAA WOMEN'S DIVISION 1")

    # Detailed Game Log
    print("\n" + "=" * 125)
    print(f"{'Date':<10} {'Gender':<6} {'League / Conf':<30} {'Matchup':<40} {'Model':<7} {'Actual':<8} {'Delta':<7} {'Tier':<10} {'Pick':<5} {'Res':<5} {'Status'}")
    print("=" * 125)
    
    for p in sorted(graded_games, key=lambda x: (x.get("date", ""), get_gender(x), x.get("time", ""))):
        dt = p.get("date", "")
        gnd = get_gender(p)
        lname = p.get("league", "NCAA")
        if len(lname) > 28:
            lname = lname[:28] + ".."
        h = p.get("home_team", "")
        a = p.get("away_team", "")
        matchup = f"{a} @ {h}"
        if len(matchup) > 38:
            matchup = matchup[:38] + ".."
        
        m_tot = p.get("model_total", 0.0)
        hs = p.get("actual_home_score", 0)
        as_ = p.get("actual_away_score", 0)
        act_tot = hs + as_
        act_score = f"{hs}-{as_}"
        
        delta = p.get("total_delta")
        delta_str = f"{delta:4.1f}" if delta is not None else "N/A"
        tier = p.get("accuracy_tier", "")
        
        pick = p.get("predicted_result", "")[:4]
        res = p.get("actual_result", "")[:4]
        is_win = (p.get("predicted_result") == p.get("actual_result"))
        stat_str = "WIN" if is_win else "LOSS"

        print(f"{dt:<10} {gnd:<6} {lname:<30} {matchup:<40} {m_tot:<7.1f} {act_score:<8} {delta_str:<7} {tier:<10} {pick:<5} {res:<5} {stat_str}")

    print("=" * 125)

if __name__ == "__main__":
    audit()

