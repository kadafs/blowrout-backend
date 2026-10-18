"""
run_shots_report.py
───────────────────
Daily Total Shots & Shots on Target (SoT) Confidence and Leaderboard Report.

Data sources:
  - data/football/universal_predictions_{date}.json  (Daily fixture shots predictions)
  - data/football/league_leaderboard.json            (League shot pace & over hit rates)
  - data/football/football_leaderboard.json          (Team empirical shot stats & accuracy)

Usage:
  python run_shots_report.py                         # today's shots report
  python run_shots_report.py --date 2026-10-17       # specific date
  python run_shots_report.py --min_score 65          # only show score >= 65
  python run_shots_report.py --tier elite            # only [ELITE SHOTS]
  python run_shots_report.py --tier strong           # [ELITE] + [STRONG]
  python run_shots_report.py --sot_only              # only games with active SoT call
  python run_shots_report.py --over_only             # only OVER calls
  python run_shots_report.py --league_id 40          # specific league
"""

import os
import sys
import json
import argparse
from datetime import datetime, timezone
from typing import Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "football")

TIER_ORDER = {
    "[ELITE SHOTS]": 1,
    "[STRONG SHOTS]": 2,
    "[SOLID SHOTS]": 3,
    "[MODERATE]": 4,
    "[AVOID / TRAP]": 5,
    "[PASS]": 6
}


def load_predictions(date_str: str) -> List[Dict[str, Any]]:
    path = os.path.join(DATA_DIR, f"universal_predictions_{date_str}.json")
    if not os.path.exists(path):
        print(f"  [ERROR] Prediction file not found: {path}")
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("predictions", [])
    except Exception as e:
        print(f"  [ERROR] Failed to read {path}: {e}")
        return []


def main():
    parser = argparse.ArgumentParser(description="Daily Football Total Shots & SoT Confidence Report")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--min_score", type=float, default=0.0, help="Minimum shots confidence score (0-100)")
    parser.add_argument("--tier", choices=["elite", "strong", "solid", "all"], default="all", help="Filter by confidence tier")
    parser.add_argument("--over_only", action="store_true", help="Only show OVER calls")
    parser.add_argument("--sot_only", action="store_true", help="Only show matches with an active SoT call")
    parser.add_argument("--league_id", type=int, help="Filter by API League ID")
    parser.add_argument("--limit", type=int, default=50, help="Max rows to display")
    args = parser.parse_args()

    date_str = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    predictions = load_predictions(date_str)

    if not predictions:
        print(f"No predictions found for {date_str}.")
        return

    from core.shots_confidence import load_shots_leaderboards, compute_shots_confidence, compute_sot_confidence
    l_idx, t_idx = load_shots_leaderboards()

    # Extract and filter games with shots calls
    rows = []
    for p in predictions:
        shots = p.get("shots") or {}
        sh_call = shots.get("shots_call")
        sot_call = shots.get("sot_call")

        # Skip if no call at all
        if (not sh_call or sh_call == "PASS") and (not sot_call or sot_call == "PASS"):
            continue

        if args.league_id and p.get("league_id") != args.league_id:
            continue

        if args.over_only and sh_call and "OVER" not in sh_call:
            continue

        if args.sot_only and (not sot_call or sot_call == "PASS"):
            continue

        sh_score = shots.get("shots_confidence_score")
        sh_tier  = shots.get("shots_confidence_tier")
        sot_score = shots.get("sot_confidence_score")
        sot_tier  = shots.get("sot_confidence_tier")

        if sh_score is None or sh_tier is None:
            sh_conf = compute_shots_confidence(
                exp_total_shots=shots.get("exp_total_shots", 24.0),
                shots_call=sh_call or "PASS",
                shots_call_line=shots.get("shots_call_line", ""),
                home_team=p.get("home_team", ""),
                away_team=p.get("away_team", ""),
                league_id=p.get("league_id"),
                league_name=p.get("league", ""),
                country=p.get("country", ""),
                pre_xg_total=p.get("xg_total"),
                conversion_rating=shots.get("conversion_rating", "BALANCED"),
                league_index=l_idx,
                team_index=t_idx
            )
            sh_score = sh_conf["score"]
            sh_tier = sh_conf["tier"]
            shots["shots_margin"] = sh_conf["margin"]
            shots["shots_pace_tier"] = sh_conf["shots_tier"]

            sot_conf = compute_sot_confidence(
                exp_total_sot=shots.get("exp_total_sot", 8.0),
                sot_call=sot_call or "PASS",
                sot_call_line=shots.get("sot_call_line", ""),
                shots_confidence_score=sh_score,
                conversion_rating=shots.get("conversion_rating", "BALANCED"),
                home_team=p.get("home_team", ""),
                away_team=p.get("away_team", ""),
                league_id=p.get("league_id"),
                league_name=p.get("league", ""),
                country=p.get("country", ""),
                league_index=l_idx,
                team_index=t_idx
            )
            sot_score = sot_conf["score"]
            sot_tier = sot_conf["tier"]

        if sh_score < args.min_score:
            continue

        if args.tier == "elite" and sh_tier != "[ELITE SHOTS]":
            continue
        elif args.tier == "strong" and sh_tier not in ("[ELITE SHOTS]", "[STRONG SHOTS]"):
            continue
        elif args.tier == "solid" and sh_tier not in ("[ELITE SHOTS]", "[STRONG SHOTS]", "[SOLID SHOTS]"):
            continue

        rows.append({
            "fixture_id": p.get("fixture_id"),
            "league_id": p.get("league_id"),
            "league": p.get("league", "Unknown"),
            "country": p.get("country", ""),
            "home_team": p.get("home_team", "Unknown"),
            "away_team": p.get("away_team", "Unknown"),
            "kickoff": p.get("kickoff", ""),
            "exp_shots": shots.get("exp_total_shots", 0.0),
            "shots_call": sh_call or "PASS",
            "shots_line": shots.get("shots_call_line", ""),
            "shots_score": sh_score,
            "shots_tier": sh_tier,
            "shots_margin": shots.get("shots_margin", 0.0),
            "pace_tier": shots.get("shots_pace_tier", "UNVERIFIED"),
            "exp_sot": shots.get("exp_total_sot", 0.0),
            "sot_call": sot_call or "PASS",
            "sot_line": shots.get("sot_call_line", ""),
            "sot_score": sot_score,
            "sot_tier": sot_tier,
            "conversion_rating": shots.get("conversion_rating", "BALANCED")
        })

    # Sort primarily by Shots Confidence Score descending
    rows.sort(key=lambda x: (x["shots_score"], x["exp_shots"]), reverse=True)

    print("\n" + "=" * 115)
    print(f"  FOOTBALL SHOTS & SOT CONFIDENCE REPORT | {date_str} | {len(rows)} QUALIFIED MATCHES")
    print("=" * 115)
    print(f"{'MATCHUP':<32} | {'LEAGUE':<22} | {'EXP SH':<6} | {'CALL':<10} | {'SCORE':<5} | {'TIER':<14} | {'EXP SOT':<7} | {'SOT CALL':<10}")
    print("-" * 115)

    displayed = rows[:args.limit]
    for r in displayed:
        match_str = f"{r['home_team']} vs {r['away_team']}"[:31]
        comp_str = f"{r['country'][:3].upper()} - {r['league']}"[:21]
        call_str = r['shots_call'] if r['shots_call'] != 'PASS' else '-'
        sot_str = f"{r['sot_call']} {r['sot_tier']}" if r['sot_call'] != 'PASS' else '-'
        
        print(f"{match_str:<32} | {comp_str:<22} | {r['exp_shots']:<6.1f} | {call_str:<10} | {r['shots_score']:<5.1f} | {r['shots_tier']:<14} | {r['exp_sot']:<7.1f} | {sot_str}")

    print("-" * 115)
    # Summary breakdowns
    elite_cnt  = sum(1 for r in rows if r["shots_tier"] == "[ELITE SHOTS]")
    strong_cnt = sum(1 for r in rows if r["shots_tier"] == "[STRONG SHOTS]")
    solid_cnt  = sum(1 for r in rows if r["shots_tier"] == "[SOLID SHOTS]")
    mod_cnt    = sum(1 for r in rows if r["shots_tier"] == "[MODERATE]")
    avoid_cnt  = sum(1 for r in rows if r["shots_tier"] == "[AVOID / TRAP]")
    sot_elite  = sum(1 for r in rows if r["sot_tier"] == "[ELITE SOT]")
    sot_strong = sum(1 for r in rows if r["sot_tier"] == "[STRONG SOT]")

    print(f" SUMMARY: Total: {len(rows)} | [ELITE]: {elite_cnt} | [STRONG]: {strong_cnt} | [SOLID]: {solid_cnt} | [MODERATE]: {mod_cnt} | [AVOID]: {avoid_cnt}")
    print(f" SOT PLAYS: [ELITE SOT]: {sot_elite} | [STRONG SOT]: {sot_strong}")
    print("=" * 115 + "\n")


if __name__ == "__main__":
    main()
