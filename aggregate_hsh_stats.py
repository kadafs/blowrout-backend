"""
aggregate_hsh_stats.py
──────────────────────
Builds team-level Highest-Scoring Half (HSH) profiles from graded football
predictions. Reads all universal_predictions_*.json files in data/football/,
extracts games with halftime scores, and outputs:

    data/football/hsh_team_profiles.json   – per-team 1H/2H stats
    data/football/hsh_league_profiles.json – per-league 1H/2H tendencies

Usage:
    python3 aggregate_hsh_stats.py
    python3 aggregate_hsh_stats.py --min_games 5
"""

import argparse
import glob
import json
import os
from collections import defaultdict
from datetime import datetime

DATA_DIR    = os.path.join(os.path.dirname(__file__), "data", "football")
OUT_TEAMS   = os.path.join(DATA_DIR, "hsh_team_profiles.json")
OUT_LEAGUES = os.path.join(DATA_DIR, "hsh_league_profiles.json")


def load_all_graded_predictions() -> list:
    """Return all graded football predictions that have halftime score data."""
    all_preds = []
    pattern = os.path.join(DATA_DIR, "universal_predictions_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        print("  [!] No universal_predictions_*.json files found in data/football/")
        return []
    for fp in files:
        try:
            with open(fp, encoding="utf-8") as f:
                data = json.load(f)
            preds = data.get("predictions", []) if isinstance(data, dict) else data
            for p in preds:
                if (
                    p.get("actual_result") is not None
                    and p.get("actual_ht_home") is not None
                    and p.get("actual_ht_away") is not None
                ):
                    all_preds.append(p)
        except Exception as e:
            print(f"  [!] Error reading {os.path.basename(fp)}: {e}")
    print(f"  Loaded {len(all_preds)} graded predictions with HT scores across {len(files)} files.")
    return all_preds


def aggregate_team_profiles(predictions: list) -> dict:
    """Per-team 1H/2H goal split statistics, keyed by league_id__team_name_lower."""
    teams = defaultdict(lambda: {
        "name": "", "league_id": None, "league": "", "games": 0,
        "ht_goals_scored": 0, "ht_goals_conceded": 0,
        "sh_goals_scored": 0, "sh_goals_conceded": 0,
        "result_1h": 0, "result_2h": 0, "result_tie": 0,
        "team_1h_higher": 0, "team_2h_higher": 0, "team_half_tie": 0,
    })

    for p in predictions:
        league_id = p.get("league_id")
        league    = p.get("league", "")
        h_team    = p.get("home_team", "")
        a_team    = p.get("away_team", "")
        ht_home   = p["actual_ht_home"]
        ht_away   = p["actual_ht_away"]
        ft_home   = p["actual_home_goals"]
        ft_away   = p["actual_away_goals"]
        sh_home   = ft_home - ht_home
        sh_away   = ft_away - ht_away
        hsh_res   = p.get("actual_hsh_result", "")

        def update(key, name, scored_ht, scored_sh, conceded_ht, conceded_sh):
            t = teams[key]
            t["name"] = name; t["league_id"] = league_id; t["league"] = league
            t["games"] += 1
            t["ht_goals_scored"]   += scored_ht
            t["ht_goals_conceded"] += conceded_ht
            t["sh_goals_scored"]   += scored_sh
            t["sh_goals_conceded"] += conceded_sh
            if hsh_res == "1H":   t["result_1h"]  += 1
            elif hsh_res == "2H": t["result_2h"]  += 1
            else:                 t["result_tie"] += 1
            if scored_ht > scored_sh:   t["team_1h_higher"] += 1
            elif scored_sh > scored_ht: t["team_2h_higher"] += 1
            else:                       t["team_half_tie"]  += 1

        update(f"{league_id}__{h_team.lower().strip()}", h_team, ht_home, sh_home, ht_away, sh_away)
        update(f"{league_id}__{a_team.lower().strip()}", a_team, ht_away, sh_away, ht_home, sh_home)

    output = {}
    for key, t in teams.items():
        g = t["games"]
        if g == 0: continue
        output[key] = {
            "name": t["name"], "league_id": t["league_id"], "league": t["league"], "games": g,
            "avg_ht_goals_scored":    round(t["ht_goals_scored"]   / g, 3),
            "avg_ht_goals_conceded":  round(t["ht_goals_conceded"] / g, 3),
            "avg_sh_goals_scored":    round(t["sh_goals_scored"]   / g, 3),
            "avg_sh_goals_conceded":  round(t["sh_goals_conceded"] / g, 3),
            "match_1h_rate":          round(t["result_1h"]  / g, 4),
            "match_2h_rate":          round(t["result_2h"]  / g, 4),
            "match_tie_rate":         round(t["result_tie"] / g, 4),
            "team_1h_higher_rate":    round(t["team_1h_higher"] / g, 4),
            "team_2h_higher_rate":    round(t["team_2h_higher"] / g, 4),
            "team_half_tie_rate":     round(t["team_half_tie"]  / g, 4),
        }
    return output


def aggregate_league_profiles(predictions: list) -> dict:
    """Per-league 1H/2H goal split and outcome rate statistics."""
    leagues = defaultdict(lambda: {
        "league": "", "league_id": None, "games": 0,
        "total_ht_goals": 0, "total_sh_goals": 0,
        "result_1h": 0, "result_2h": 0, "result_tie": 0,
    })

    for p in predictions:
        lid = p.get("league_id")
        key = str(lid)
        l = leagues[key]
        l["league"] = p.get("league", ""); l["league_id"] = lid; l["games"] += 1
        l["total_ht_goals"] += p.get("actual_ht_goals", 0)
        l["total_sh_goals"] += p.get("actual_sh_goals", 0)
        res = p.get("actual_hsh_result", "")
        if res == "1H":   l["result_1h"]  += 1
        elif res == "2H": l["result_2h"]  += 1
        else:             l["result_tie"] += 1

    output = {}
    for key, l in leagues.items():
        g = l["games"]
        if g == 0: continue
        total_goals = l["total_ht_goals"] + l["total_sh_goals"]
        output[key] = {
            "league": l["league"], "league_id": l["league_id"], "games": g,
            "avg_ht_goals":  round(l["total_ht_goals"] / g, 3),
            "avg_sh_goals":  round(l["total_sh_goals"] / g, 3),
            "ht_goal_share": round(l["total_ht_goals"] / total_goals, 4) if total_goals else 0.44,
            "sh_goal_share": round(l["total_sh_goals"] / total_goals, 4) if total_goals else 0.56,
            "rate_1h":       round(l["result_1h"]  / g, 4),
            "rate_2h":       round(l["result_2h"]  / g, 4),
            "rate_tie":      round(l["result_tie"] / g, 4),
        }
    return output


def save_json(path: str, data: dict, label: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved {label} ({len(data.get('teams', data.get('leagues', data)))} entries) -> {os.path.basename(path)}")


def print_summary(team_profiles: dict, league_profiles: dict, min_games: int) -> None:
    qualified = {k: v for k, v in team_profiles.items() if v["games"] >= min_games}
    print(f"\n{'─'*60}")
    print(f"  HSH Team Profiles   : {len(team_profiles)} total | {len(qualified)} with >= {min_games} games")
    print(f"  HSH League Profiles : {len(league_profiles)}")
    sorted_leagues = sorted(league_profiles.values(), key=lambda x: x["rate_2h"], reverse=True)
    total_graded = sum(l["games"] for l in league_profiles.values())
    print(f"\n  Top 5 Most 2H-Heavy Leagues (from {total_graded} graded games):")
    for l in sorted_leagues[:5]:
        print(f"    {l['league']:<40}  2H: {l['rate_2h']*100:.1f}%  1H: {l['rate_1h']*100:.1f}%  TIE: {l['rate_tie']*100:.1f}%  (n={l['games']})")
    print(f"{'─'*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Aggregate HSH team/league profiles from graded football predictions")
    parser.add_argument("--min_games", type=int, default=3, help="Min games for summary display (default: 3)")
    args = parser.parse_args()

    print("\n=== Aggregating Highest-Scoring Half (HSH) Profiles ===\n")
    predictions = load_all_graded_predictions()

    if not predictions:
        print("\n  [!] No graded predictions with HT data yet.")
        print("  [i] HT scores are captured automatically when grade_football.py runs.")
        print("  [i] Re-run this script after grading a few days of results.\n")
        return

    team_profiles   = aggregate_team_profiles(predictions)
    league_profiles = aggregate_league_profiles(predictions)

    save_json(OUT_TEAMS,   {"generated_at": datetime.utcnow().isoformat()+"Z", "total_games": len(predictions), "teams": team_profiles},   "team profiles")
    save_json(OUT_LEAGUES, {"generated_at": datetime.utcnow().isoformat()+"Z", "total_games": len(predictions), "leagues": league_profiles}, "league profiles")
    print_summary(team_profiles, league_profiles, args.min_games)


if __name__ == "__main__":
    main()
