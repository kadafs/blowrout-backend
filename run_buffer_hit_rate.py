"""
run_buffer_hit_rate.py
======================
Evaluates basketball fixtures exclusively using the Historical Buffer Hit Rate (-5 pt floor buffer).

The Historical Buffer Hit Rate assesses how reliably both teams hit their projected scoring floor:
    Floor Target = model_total - 5.0 pts

Scoring Engine (0 - 50 points, matching core/confidence_score.py):
    Weighted Hit Rate = (0.6 * lower_team_hit_rate) + (0.4 * higher_team_hit_rate)
    Base Score:
        >= 80%  -> 50 pts (Elite buffer reliability)
        >= 65%  -> 33 pts (Solid reliability)
        >= 50%  -> 16 pts (Neutral / Marginal)
        <  50%  ->  0 pts (Unreliable / Under-shoots buffer)

    Sample Size Guard:
        min_games >= 5 -> 100% of base score
        min_games == 4 -> 80% of base score (max 40)
        min_games == 3 -> 60% of base score (max 30)
        min_games <= 2 -> 30% of base score (capped at 15)
        0 games / no data -> 8 pts (below-neutral penalty)

Usage:
    python run_buffer_hit_rate.py                      # Today's fixtures (min_graded=3)
    python run_buffer_hit_rate.py --date 2026-10-10    # Specific date
    python run_buffer_hit_rate.py --min_hit_rate 0.65  # Only games with weighted hit rate >= 65%
    python run_buffer_hit_rate.py --min_graded 3       # Enforce min graded games (default: 3)
    python run_buffer_hit_rate.py --audit              # Audit actual buffer hit rate on finished games
    python run_buffer_hit_rate.py --csv                # Export to CSV
"""

import json
import os
import sys
import csv
import argparse
import difflib
from datetime import datetime

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# ---------------------------------------------------------------------------
# Paths & Defaults
# ---------------------------------------------------------------------------
PREDICTIONS_DIR  = "data/basketball"
LEADERBOARD_PATH = "data/basketball/basketball_leaderboard.json"
CSV_OUTPUT_DIR   = "data/confidence_reports"

BUFFER_OFFSET    = 5.0  # -5.0 pts buffer floor

# ---------------------------------------------------------------------------
# Leaderboard Loader
# ---------------------------------------------------------------------------

def load_leaderboard() -> dict:
    """Load and index the basketball leaderboard by (name_lower, league_id)."""
    if not os.path.exists(LEADERBOARD_PATH):
        print(f"  [WARN] Leaderboard not found: {LEADERBOARD_PATH}")
        return {}

    with open(LEADERBOARD_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    entries = data.get("leaderboard", [])
    index = {}
    for e in entries:
        name = e.get("name", "").strip()
        lid  = e.get("league_id")
        index[(name.lower(), lid)] = e

    return index


def lookup_team(name: str, league_id: int, index: dict) -> dict | None:
    """Find leaderboard entry within same league_id (exact, fuzzy, substring)."""
    name_lower = name.lower().strip()

    # 1. Exact match
    if (name_lower, league_id) in index:
        return index[(name_lower, league_id)]

    # 2. Fuzzy match within same league
    league_names = [k[0] for k in index if k[1] == league_id]
    if league_names:
        matches = difflib.get_close_matches(name_lower, league_names, n=1, cutoff=0.72)
        if matches:
            return index[(matches[0], league_id)]

        # 3. Substring match
        for lb_name in league_names:
            if name_lower in lb_name or lb_name in name_lower:
                return index[(lb_name, league_id)]

    return None


def get_team_hit_rate(name: str, league_id: int, index: dict) -> tuple:
    """
    Returns (hit_rate, total_games, hits, source).
    hit_rate is float (0.0-1.0) or None if no history.
    """
    entry = lookup_team(name, league_id, index)
    if entry:
        ff_rate  = entry.get("flat_floor_rate")
        ff_total = entry.get("flat_floor_total", 0)
        ff_hits  = entry.get("flat_floor_hits", 0)
        return ff_rate, int(ff_total), int(ff_hits), "leaderboard"
    return None, 0, 0, "defaults"


# ---------------------------------------------------------------------------
# Hit Rate Evaluation Logic
# ---------------------------------------------------------------------------

def score_hit_rate_value(weighted_hit_rate: float) -> int:
    """Base score from weighted hit rate (Max 50)."""
    if weighted_hit_rate >= 0.80:
        return 50
    elif weighted_hit_rate >= 0.65:
        return 33
    elif weighted_hit_rate >= 0.50:
        return 16
    else:
        return 0


def compute_buffer_hit_rate(hr_a: float | None, games_a: int,
                            hr_h: float | None, games_h: int) -> dict:
    """
    Computes the weighted buffer hit rate, hit rate score (0-50),
    and sample size tier.
    """
    if hr_a is None or hr_h is None or games_a == 0 or games_h == 0:
        return {
            "weighted_hit_rate": None,
            "base_score": 0,
            "sample_penalty": "No History (Penalty Applied)",
            "hit_rate_score": 8,  # Below-neutral penalty
            "tier_label": "[UNTRACKED]",
            "min_games": 0,
        }

    lower_hr  = min(hr_a, hr_h)
    higher_hr = max(hr_a, hr_h)
    weighted_hr = (0.6 * lower_hr) + (0.4 * higher_hr)

    base_score = score_hit_rate_value(weighted_hr)
    min_games  = min(games_a, games_h)

    if min_games >= 5:
        score = base_score
        penalty_desc = "None (Full Sample >=5)"
    elif min_games == 4:
        score = int(base_score * 0.8)
        penalty_desc = "80% (Sample = 4)"
    elif min_games == 3:
        score = int(base_score * 0.6)
        penalty_desc = "60% (Sample = 3)"
    else:
        score = min(15, int(base_score * 0.3))
        penalty_desc = "30% Cap (Sample <= 2)"

    if score >= 40:
        tier_label = "[ELITE BUFFER]"
    elif score >= 28:
        tier_label = "[STRONG BUFFER]"
    elif score >= 16:
        tier_label = "[NEUTRAL]"
    elif score > 0:
        tier_label = "[MARGINAL]"
    else:
        tier_label = "[AVOID]"

    return {
        "weighted_hit_rate": round(weighted_hr, 4),
        "base_score": base_score,
        "sample_penalty": penalty_desc,
        "hit_rate_score": score,
        "tier_label": tier_label,
        "min_games": min_games,
    }


# ---------------------------------------------------------------------------
# Report Execution
# ---------------------------------------------------------------------------

def run_buffer_report(date_str: str, min_hit_rate: float = 0.0,
                      min_score: int = 0, min_graded: int = 3,
                      tier_filter: str = None, league_id_filter: int = None,
                      no_playoffs: bool = False, audit_mode: bool = False):

    pred_path = os.path.join(PREDICTIONS_DIR, f"universal_predictions_{date_str}.json")
    if not os.path.exists(pred_path):
        print(f"\n  [ERROR] No predictions file for {date_str}: {pred_path}")
        return []

    with open(pred_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    if not predictions:
        print(f"  No predictions found in {pred_path}")
        return []

    lb_index = load_leaderboard()

    rows = []
    audit_total = 0
    audit_hits  = 0

    for p in predictions:
        league_id   = p.get("league_id")
        league      = p.get("league", "Unknown")
        tier        = p.get("tier", "unknown")
        home        = p.get("home_team", "?")
        away        = p.get("away_team", "?")
        model_total = p.get("model_total", 0.0)

        # Filters
        if tier_filter and tier != tier_filter:
            continue
        if league_id_filter and league_id != league_id_filter:
            continue
        if no_playoffs:
            stage = p.get("stage", "").lower()
            playoff_keywords = ["final", "semi", "quarter", "playoff", "3rd place", "relegation"]
            if any(k in stage for k in playoff_keywords):
                continue

        # Hit rate stats from leaderboard
        hr_h, games_h, hits_h, src_h = get_team_hit_rate(home, league_id, lb_index)
        hr_a, games_a, hits_a, src_a = get_team_hit_rate(away, league_id, lb_index)
        using_defaults = (src_h == "defaults" or src_a == "defaults")

        min_game_count = min(games_h, games_a)

        # Filter by minimum graded games
        if min_game_count < min_graded:
            continue

        res = compute_buffer_hit_rate(hr_a, games_a, hr_h, games_h)
        whr = res["weighted_hit_rate"]
        score = res["hit_rate_score"]

        if whr is not None and whr < min_hit_rate:
            continue
        if score < min_score:
            continue

        buffer_line = round(model_total - BUFFER_OFFSET, 1)

        # Actual score grading (if finished / graded)
        act_h = p.get("actual_home_score")
        act_a = p.get("actual_away_score")
        actual_total = (act_h + act_a) if (act_h is not None and act_a is not None) else None

        buffer_hit = None
        margin = None
        if actual_total is not None:
            buffer_hit = (actual_total >= buffer_line)
            margin = round(actual_total - buffer_line, 1)
            audit_total += 1
            if buffer_hit:
                audit_hits += 1

        rows.append({
            "date": date_str,
            "league": league,
            "league_id": league_id,
            "tier": tier,
            "home": home,
            "away": away,
            "model_total": round(model_total, 1),
            "buffer_line": buffer_line,
            "actual_total": actual_total,
            "buffer_hit": buffer_hit,
            "margin": margin,
            "hr_h": hr_h,
            "games_h": games_h,
            "hits_h": hits_h,
            "hr_a": hr_a,
            "games_a": games_a,
            "hits_a": hits_a,
            "min_graded_games": min_game_count,
            "weighted_hit_rate": whr,
            "base_score": res["base_score"],
            "hit_rate_score": score,
            "tier_label": res["tier_label"],
            "sample_penalty": res["sample_penalty"],
            "using_defaults": using_defaults,
        })

    if not rows:
        print(f"\n  No games matched filters (min_hit_rate={min_hit_rate}, min_score={min_score}, min_graded={min_graded})")
        return []

    # Sort descending by Hit Rate Score, then Weighted Hit Rate
    rows.sort(key=lambda x: (x["hit_rate_score"], x["weighted_hit_rate"] or 0), reverse=True)

    # ---------------------------------------------------------------------------
    # Render Output
    # ---------------------------------------------------------------------------
    print(f"\n{'=' * 125}")
    print(f"  HISTORICAL BUFFER HIT RATE REPORT  |  {date_str}  |  {len(rows)} games (min_graded >= {min_graded})")
    print(f"  Buffer Target = Model Total - {BUFFER_OFFSET} pts")
    print(f"{'=' * 125}")

    header = (
        f"  {'Score':>5}  {'Rating':<16}  {'wHR%':>6}  {'Away HR (Gms)':<16}  "
        f"{'Home HR (Gms)':<16}  {'Model':>6}  {'Floor':>6}  "
    )
    if audit_mode or any(r["actual_total"] is not None for r in rows):
        header += f"{'Actual':>6}  {'Result':<8}  {'Margin':>6}  Matchup"
    else:
        header += f"Matchup"

    print(header)
    print(f"  {'-' * 120}")

    last_league = None
    for r in rows:
        if r["league"] != last_league:
            print(f"\n  -- {r['league']} ({r['tier']}) --")
            last_league = r["league"]

        whr_str = f"{r['weighted_hit_rate']*100:.1f}%" if r['weighted_hit_rate'] is not None else "N/A"
        hr_a_str = f"{r['hr_a']*100:.0f}% ({r['hits_a']}/{r['games_a']})" if r['hr_a'] is not None else "N/A (0)"
        hr_h_str = f"{r['hr_h']*100:.0f}% ({r['hits_h']}/{r['games_h']})" if r['hr_h'] is not None else "N/A (0)"

        matchup = f"{r['away'][:20]} @ {r['home'][:20]}"

        base_line = (
            f"  {r['hit_rate_score']:>2}/50  {r['tier_label']:<16}  {whr_str:>6}  "
            f"{hr_a_str:<16}  {hr_h_str:<16}  {r['model_total']:>6.1f}  {r['buffer_line']:>6.1f}  "
        )

        if audit_mode or any(x["actual_total"] is not None for x in rows):
            act_str = f"{r['actual_total']:>6.0f}" if r['actual_total'] is not None else "   -  "
            if r["buffer_hit"] is True:
                res_str = "[HIT]"
            elif r["buffer_hit"] is False:
                res_str = "[MISS]"
            else:
                res_str = "PENDING"
            mrg_str = f"{r['margin']:>+6.1f}" if r['margin'] is not None else "   -  "
            print(f"{base_line}{act_str}  {res_str:<8}  {mrg_str}  {matchup}")
        else:
            print(f"{base_line}{matchup}")

    print(f"\n{'=' * 125}")

    # Summary
    print("\n  SUMMARY BY BUFFER RATING:")
    from collections import Counter
    counts = Counter(r["tier_label"] for r in rows)
    for lbl in ["[ELITE BUFFER]", "[STRONG BUFFER]", "[NEUTRAL]", "[MARGINAL]", "[AVOID]", "[UNTRACKED]"]:
        if lbl in counts:
            print(f"    {lbl:<18}: {counts[lbl]} game(s)")

    if audit_total > 0:
        emp_rate = (audit_hits / audit_total) * 100
        print(f"\n  AUDIT RESULTS FOR {date_str}:")
        print(f"    Graded Games Evaluated: {audit_total}")
        print(f"    Buffer Hits (>= -5pts): {audit_hits} / {audit_total} ({emp_rate:.1f}%)")

        # Breakdown by tier for audited games
        for lbl in ["[ELITE BUFFER]", "[STRONG BUFFER]", "[NEUTRAL]", "[MARGINAL]", "[AVOID]"]:
            sub = [x for x in rows if x["tier_label"] == lbl and x["actual_total"] is not None]
            if sub:
                sub_hits = sum(1 for x in sub if x["buffer_hit"])
                print(f"      {lbl:<16}: {sub_hits}/{len(sub)} ({sub_hits/len(sub)*100:.1f}%) hit the -5pt buffer")

    print()
    return rows


# ---------------------------------------------------------------------------
# CSV Exporter
# ---------------------------------------------------------------------------

CSV_FIELDS = [
    "date", "hit_rate_score", "tier_label", "weighted_hit_rate",
    "league", "tier", "league_id", "away_team", "home_team",
    "model_total", "buffer_line", "actual_total", "buffer_hit", "margin",
    "away_hit_rate", "away_games", "away_hits",
    "home_hit_rate", "home_games", "home_hits",
    "min_graded_games", "sample_penalty"
]

def export_csv(rows: list, date_str: str) -> str:
    os.makedirs(CSV_OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(CSV_OUTPUT_DIR, f"buffer_hit_rate_{date_str}.csv")
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in rows:
            writer.writerow({
                "date": date_str,
                "hit_rate_score": r["hit_rate_score"],
                "tier_label": r["tier_label"],
                "weighted_hit_rate": r["weighted_hit_rate"],
                "league": r["league"],
                "tier": r["tier"],
                "league_id": r["league_id"],
                "away_team": r["away"],
                "home_team": r["home"],
                "model_total": r["model_total"],
                "buffer_line": r["buffer_line"],
                "actual_total": r["actual_total"],
                "buffer_hit": r["buffer_hit"],
                "margin": r["margin"],
                "away_hit_rate": r["hr_a"],
                "away_games": r["games_a"],
                "away_hits": r["hits_a"],
                "home_hit_rate": r["hr_h"],
                "home_games": r["games_h"],
                "home_hits": r["hits_h"],
                "min_graded_games": r["min_graded_games"],
                "sample_penalty": r["sample_penalty"],
            })
    return out_path


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Historical Buffer Hit Rate Report (-5 pt floor)")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--min_hit_rate", type=float, default=0.0,
                        help="Minimum weighted hit rate (0.0 to 1.0, e.g. 0.65)")
    parser.add_argument("--min_score", type=int, default=0,
                        help="Minimum hit rate score (0 to 50)")
    parser.add_argument("--min_graded", type=int, default=3,
                        help="Minimum graded games required for BOTH teams (default: 3)")
    parser.add_argument("--tier", choices=["elite_pro", "top_domestic", "second_division", "lower"],
                        help="Filter by league tier")
    parser.add_argument("--league_id", type=int, help="Filter to a specific league ID")
    parser.add_argument("--no_playoffs", action="store_true", help="Exclude playoff matches")
    parser.add_argument("--audit", action="store_true", help="Show actual scores and hit/miss grading")
    parser.add_argument("--csv", action="store_true", help="Export output to CSV")
    args = parser.parse_args()

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    rows = run_buffer_report(
        date_str         = date_str,
        min_hit_rate     = args.min_hit_rate,
        min_score        = args.min_score,
        min_graded       = args.min_graded,
        tier_filter      = args.tier,
        league_id_filter = args.league_id,
        no_playoffs      = args.no_playoffs,
        audit_mode       = args.audit,
    )

    if rows and args.csv:
        path = export_csv(rows, date_str)
        print(f"  CSV exported -> {path}\n")


if __name__ == "__main__":
    main()
