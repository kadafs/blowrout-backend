"""
scripts/build_ncaa_sdi.py
=========================
Parses Proballers NCAA box scores from data/historical/proballers_ncaa.json,
calculates SDI metrics for all 500+ NCAA teams, and merges them into
data/basketball/team_sdi.json (and Sports Analytics frontend).
"""

import os
import json
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORICAL_FILE = os.path.join(BASE_DIR, "data", "historical", "proballers_ncaa.json")
BACKEND_SDI = os.path.join(BASE_DIR, "data", "basketball", "team_sdi.json")
FRONTEND_SDI = os.path.join(os.path.dirname(BASE_DIR), "Sports Analytics", "public", "data", "basketball", "team_sdi.json")

def clean_player_name(raw_name):
    if not raw_name:
        return "Unknown"
    lines = [line.strip() for line in raw_name.split('\n') if line.strip()]
    if lines:
        return lines[0]
    return raw_name.strip()

def build_ncaa_sdi():
    if not os.path.exists(HISTORICAL_FILE):
        print(f"Error: {HISTORICAL_FILE} not found.")
        return

    with open(HISTORICAL_FILE, "r", encoding="utf-8") as f:
        games = json.load(f)

    print(f"Loaded {len(games)} NCAA games from {HISTORICAL_FILE}.")

    team_data = defaultdict(lambda: {
        "sdi_samples": [],
        "top1_samples": [],
        "top_scorers": defaultdict(int),
        "game_count": 0
    })

    for g in games:
        stats = g.get("stats") or {}
        h_score = g.get("home_score") or 0
        a_score = g.get("away_score") or 0
        h_name = (g.get("home_team") or "").strip()
        a_name = (g.get("away_team") or "").strip()

        # Home team
        h_players = stats.get("home", {}).get("players", [])
        if h_players and h_score > 0 and h_name:
            pts_list = []
            for p in h_players:
                val = p.get("pts")
                try:
                    pts_list.append((clean_player_name(p.get("name")), float(val)))
                except (ValueError, TypeError):
                    pass
            pts_list.sort(key=lambda x: x[1], reverse=True)
            if len(pts_list) >= 2:
                top2 = sum(x[1] for x in pts_list[:2])
                top1 = pts_list[0][1]
                team_data[h_name]["sdi_samples"].append((top2 / h_score) * 100)
                team_data[h_name]["top1_samples"].append((top1 / h_score) * 100)
                team_data[h_name]["game_count"] += 1
                for pname, _ in pts_list[:2]:
                    team_data[h_name]["top_scorers"][pname] += 1

        # Away team
        a_players = stats.get("away", {}).get("players", [])
        if a_players and a_score > 0 and a_name:
            pts_list = []
            for p in a_players:
                val = p.get("pts")
                try:
                    pts_list.append((clean_player_name(p.get("name")), float(val)))
                except (ValueError, TypeError):
                    pass
            pts_list.sort(key=lambda x: x[1], reverse=True)
            if len(pts_list) >= 2:
                top2 = sum(x[1] for x in pts_list[:2])
                top1 = pts_list[0][1]
                team_data[a_name]["sdi_samples"].append((top2 / a_score) * 100)
                team_data[a_name]["top1_samples"].append((top1 / a_score) * 100)
                team_data[a_name]["game_count"] += 1
                for pname, _ in pts_list[:2]:
                    team_data[a_name]["top_scorers"][pname] += 1

    print(f"Processed {len(team_data)} unique NCAA teams.")

    # Load existing team_sdi.json
    existing = {"teams": []}
    if os.path.exists(BACKEND_SDI):
        with open(BACKEND_SDI, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_teams = {t["team"].lower(): t for t in existing.get("teams", [])}
    print(f"Existing teams in SDI database before merge: {len(existing_teams)}")

    # Format NCAA teams
    added_count = 0
    updated_count = 0

    for t_name, d in team_data.items():
        if not d["sdi_samples"]:
            continue
        avg_sdi = round(sum(d["sdi_samples"]) / len(d["sdi_samples"]), 1)
        avg_top1 = round(sum(d["top1_samples"]) / len(d["top1_samples"]), 1)
        
        if avg_sdi >= 55.0:
            risk = "RED"
            label = "HIGH DEPENDENCY"
        elif avg_sdi >= 40.0:
            risk = "AMBER"
            label = "MODERATE"
        else:
            risk = "GREEN"
            label = "BALANCED"

        sorted_scorers = sorted(d["top_scorers"].items(), key=lambda x: x[1], reverse=True)[:3]
        top_players = [{"name": p[0], "times_top2": p[1]} for p in sorted_scorers]

        record = {
            "team": t_name,
            "games_tracked": d["game_count"],
            "avg_sdi": avg_sdi,
            "avg_top1_pct": avg_top1,
            "max_sdi": round(max(d["sdi_samples"]), 1),
            "min_sdi": round(min(d["sdi_samples"]), 1),
            "risk": risk,
            "risk_label": label,
            "top_players": top_players,
            "source": "proballers_ncaa"
        }

        # Also register normalized college nickname aliases (e.g., "Alabama" for "Alabama Crimson Tide")
        # if the first word/token is distinct
        t_lower = t_name.lower()
        if t_lower in existing_teams:
            existing_teams[t_lower].update(record)
            updated_count += 1
        else:
            existing_teams[t_lower] = record
            added_count += 1

    merged_list = list(existing_teams.values())
    red_total = sum(1 for t in merged_list if t.get("risk") == "RED")
    amber_total = sum(1 for t in merged_list if t.get("risk") == "AMBER")
    green_total = sum(1 for t in merged_list if t.get("risk") == "GREEN")

    merged_output = {
        "generated_at": datetime.now().isoformat(),
        "total_teams": len(merged_list),
        "source": "api-sports + proballers_ncaa",
        "summary": {
            "red_high_dependency": red_total,
            "amber_moderate": amber_total,
            "green_balanced": green_total
        },
        "teams": merged_list
    }

    # Save to backend
    with open(BACKEND_SDI, "w", encoding="utf-8") as f:
        json.dump(merged_output, f, indent=2, ensure_ascii=False)
    print(f"Saved merged SDI to {BACKEND_SDI}")

    # Save to frontend if exists
    if os.path.exists(os.path.dirname(FRONTEND_SDI)):
        with open(FRONTEND_SDI, "w", encoding="utf-8") as f:
            json.dump(merged_output, f, indent=2, ensure_ascii=False)
        print(f"Saved merged SDI to {FRONTEND_SDI}")

    print(f"\nMerge Complete:")
    print(f"  Added NCAA teams:   {added_count}")
    print(f"  Updated teams:      {updated_count}")
    print(f"  New Total Teams:    {len(merged_list)}")
    print(f"  Risk Breakdown:     RED={red_total} | AMBER={amber_total} | GREEN={green_total}")

if __name__ == "__main__":
    build_ncaa_sdi()
