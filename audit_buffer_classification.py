"""
audit_buffer_classification.py
==============================
Classifies PLAY OVER and PLAY UNDER games across historical predictions
into the various Buffer Floor tiers:
  - [ELITE BUFFER]
  - [STRONG BUFFER]
  - [STRONG]+ (Combined Elite + Strong)
  - [NEUTRAL]
  - [MARGINAL]
  - [AVOID]
"""

import glob
import json
import sys
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

def run():
    files = sorted(glob.glob("data/basketball/universal_predictions_*.json"))
    seen = set()

    over_stats = defaultdict(lambda: {"w": 0, "l": 0, "p": 0, "deltas": [], "edges": []})
    under_stats = defaultdict(lambda: {"w": 0, "l": 0, "p": 0, "deltas": [], "edges": []})
    all_plays_stats = defaultdict(lambda: {"w": 0, "l": 0, "p": 0, "deltas": [], "edges": []})

    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fp:
                d = json.load(fp)
        except Exception:
            continue

        preds = d.get("predictions", []) if isinstance(d, dict) else d
        for p in preds:
            h = p.get("actual_home_score")
            a = p.get("actual_away_score")
            mkt = p.get("market_total")
            mdl = p.get("model_total")
            if h is None or a is None or not mkt or mkt <= 50 or not mdl or mdl <= 50:
                continue

            key = f"{p.get('date')}_{p.get('league_id')}_{p.get('home_team')}_{p.get('away_team')}"
            if key in seen:
                continue
            seen.add(key)

            tier = p.get("buffer_tier")
            if not tier:
                continue

            act = h + a
            edge = mdl - mkt
            abs_edge = abs(edge)
            mbet = p.get("mbet_threshold", 4.0)

            is_over = (edge >= mbet) or (p.get("decision") == "PLAY OVER")
            is_under = (edge <= -mbet) or (p.get("decision") == "PLAY UNDER")

            # Determine bet result
            if act > mkt:
                res_over, res_under = "WIN", "LOSS"
            elif act < mkt:
                res_over, res_under = "LOSS", "WIN"
            else:
                res_over, res_under = "PUSH", "PUSH"

            tiers_to_update = [tier]
            if tier in ("[ELITE BUFFER]", "[STRONG BUFFER]"):
                tiers_to_update.append("[STRONG]+")

            for t in tiers_to_update:
                if is_over:
                    st = over_stats[t]
                    if res_over == "WIN": st["w"] += 1
                    elif res_over == "LOSS": st["l"] += 1
                    else: st["p"] += 1
                    st["deltas"].append(act - mkt)
                    st["edges"].append(edge)

                    # Combined
                    c_st = all_plays_stats[t]
                    if res_over == "WIN": c_st["w"] += 1
                    elif res_over == "LOSS": c_st["l"] += 1
                    else: c_st["p"] += 1

                if is_under:
                    st = under_stats[t]
                    if res_under == "WIN": st["w"] += 1
                    elif res_under == "LOSS": st["l"] += 1
                    else: st["p"] += 1
                    st["deltas"].append(mkt - act)
                    st["edges"].append(abs_edge)

                    # Combined
                    c_st = all_plays_stats[t]
                    if res_under == "WIN": c_st["w"] += 1
                    elif res_under == "LOSS": c_st["l"] += 1
                    else: c_st["p"] += 1

    tiers_display = [
        ("[ELITE BUFFER]", "🏆 Elite Buffer (40+ pts)"),
        ("[STRONG BUFFER]", "🟢 Strong Buffer (28-39 pts)"),
        ("[STRONG]+", "🛡️ Strong+ (Combined 28+)"),
        ("[NEUTRAL]", "🟡 Neutral Floor (16-27 pts)"),
        ("[MARGINAL]", "🟠 Marginal Floor (1-15 pts)"),
        ("[AVOID]", "⛔ Avoid Floor (0 pts)"),
    ]

    def print_table(title, stat_dict, is_over_table=False, is_under_table=False):
        print(f"\n{'='*82}")
        print(f"  {title}")
        print(f"{'='*82}")
        print(f"  {'Buffer Floor Tier':<30} | {'Total':<6} | {'W - L - P':<12} | {'Win Rate':<10} | {'Avg Beat':<10} | {'ROI (-110)':<10}")
        print(f"{'-'*82}")
        for t_key, t_label in tiers_display:
            st = stat_dict[t_key]
            tot = st["w"] + st["l"] + st["p"]
            grd = st["w"] + st["l"]
            win_pct = (st["w"] / grd * 100) if grd > 0 else 0.0
            units = (st["w"] * 0.90909) - (st["l"] * 1.0)
            roi = (units / grd * 100) if grd > 0 else 0.0
            u_str = f"{units:+0.1f}u"
            roi_str = f"{roi:+0.2f}%"
            avg_d = (sum(st["deltas"]) / len(st["deltas"])) if st["deltas"] else 0.0
            avg_str = f"{avg_d:+0.1f} pts"

            print(f"  {t_label:<30} | {tot:<6} | {st['w']}-{st['l']}-{st['p']:<10} | {win_pct:>6.2f}%    | {avg_str:>9} | {roi_str:>8} ({u_str})")

    print_table("🟢 1. PLAY OVER PLAYS BY BUFFER FLOOR", over_stats, is_over_table=True)
    print_table("🔴 2. PLAY UNDER PLAYS BY BUFFER FLOOR", under_stats, is_under_table=True)
    print_table("🎯 3. COMBINED ACTIONABLE PLAYS (OVER + UNDER) BY BUFFER FLOOR", all_plays_stats)
    print(f"{'='*75}\n")

if __name__ == "__main__":
    run()
