"""
scripts/build_ncaa_sdi.py
=========================
Parses Proballers NCAA box scores from data/historical/proballers_ncaa.json,
calculates SDI metrics for all 500+ NCAA teams, and merges them into
data/basketball/team_sdi.json (and Sports Analytics frontend).
"""

import os
import glob
import json
from collections import defaultdict
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORICAL_DIR = os.path.join(BASE_DIR, "data", "historical")
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
    # Scan all Proballers historical files (proballers_ncaa.json and other proballers_*.json)
    pattern = os.path.join(HISTORICAL_DIR, "proballers_*.json")
    files = glob.glob(pattern)
    if not files:
        print(f"Warning: No proballers_*.json files found in {HISTORICAL_DIR}.")
        return

    all_games = []
    for fpath in files:
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                games = json.load(f)
                if isinstance(games, list):
                    all_games.extend(games)
                    print(f"Loaded {len(games)} games from {os.path.basename(fpath)}.")
        except Exception as e:
            print(f"Error reading {fpath}: {e}")

    if not all_games:
        print("No Proballers games found to process.")
        return

    print(f"Total Proballers games to process: {len(all_games)}")

    team_data = defaultdict(lambda: {
        "sdi_samples": [],
        "top1_samples": [],
        "top_scorers": defaultdict(int),
        "off_share_samples": [],
        "top_creators": defaultdict(int),
        "game_count": 0
    })

    for g in all_games:
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

            # Check for assists to calculate Top-1 Playmaker Offensive Share
            has_ast = any("ast" in p or "assists" in p for p in h_players)
            if has_ast:
                creator_list = []
                for p in h_players:
                    pts = float(p.get("pts") or 0)
                    ast = float(p.get("ast", p.get("assists", 0)) or 0)
                    creator_list.append((clean_player_name(p.get("name")), pts + 2.15 * ast))
                if creator_list:
                    creator_list.sort(key=lambda x: x[1], reverse=True)
                    top_creator_name, top_off_pts = creator_list[0]
                    off_share = (top_off_pts / h_score) * 100.0
                    team_data[h_name]["off_share_samples"].append(off_share)
                    team_data[h_name]["top_creators"][top_creator_name] += 1

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

            # Check for assists to calculate Top-1 Playmaker Offensive Share
            has_ast = any("ast" in p or "assists" in p for p in a_players)
            if has_ast:
                creator_list = []
                for p in a_players:
                    pts = float(p.get("pts") or 0)
                    ast = float(p.get("ast", p.get("assists", 0)) or 0)
                    creator_list.append((clean_player_name(p.get("name")), pts + 2.15 * ast))
                if creator_list:
                    creator_list.sort(key=lambda x: x[1], reverse=True)
                    top_creator_name, top_off_pts = creator_list[0]
                    off_share = (top_off_pts / a_score) * 100.0
                    team_data[a_name]["off_share_samples"].append(off_share)
                    team_data[a_name]["top_creators"][top_creator_name] += 1

    print(f"Processed {len(team_data)} unique Proballers teams.")

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

        avg_off_share = round(sum(d["off_share_samples"]) / len(d["off_share_samples"]), 1) if d["off_share_samples"] else None
        if avg_off_share is not None:
            if avg_off_share >= 38.8:
                playmaker_risk = "HIGH"
            elif avg_off_share <= 31.5:
                playmaker_risk = "LOW"
            else:
                playmaker_risk = "MODERATE"
            top_creator_sorted = sorted(d["top_creators"].items(), key=lambda x: x[1], reverse=True)
            top_creator_name = top_creator_sorted[0][0] if top_creator_sorted else None
        else:
            playmaker_risk = None
            top_creator_name = None

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
            "avg_top1_off_share": avg_off_share,
            "playmaker_risk": playmaker_risk,
            "top_creator": top_creator_name,
            "source": "proballers_ncaa"
        }

        # Also register normalized college nickname aliases (e.g., "Alabama" for "Alabama Crimson Tide")
        # if the first word/token is distinct
        t_lower = t_name.lower()
        if t_lower in existing_teams:
            # Preserve existing creator metrics if current proballers record lacks assist data
            if record.get("avg_top1_off_share") is None and existing_teams[t_lower].get("avg_top1_off_share") is not None:
                record["avg_top1_off_share"] = existing_teams[t_lower]["avg_top1_off_share"]
                record["playmaker_risk"] = existing_teams[t_lower]["playmaker_risk"]
                record["top_creator"] = existing_teams[t_lower]["top_creator"]
            existing_teams[t_lower].update(record)
            updated_count += 1
        else:
            existing_teams[t_lower] = record
            added_count += 1

    merged_list = list(existing_teams.values())
    red_total = sum(1 for t in merged_list if t.get("risk") == "RED")
    amber_total = sum(1 for t in merged_list if t.get("risk") == "AMBER")
    green_total = sum(1 for t in merged_list if t.get("risk") == "GREEN")
    high_playmaker_total = sum(1 for t in merged_list if t.get("playmaker_risk") == "HIGH")
    low_playmaker_total = sum(1 for t in merged_list if t.get("playmaker_risk") == "LOW")

    merged_output = {
        "generated_at": datetime.now().isoformat(),
        "total_teams": len(merged_list),
        "source": "api-sports + proballers_ncaa",
        "summary": {
            "red_high_dependency": red_total,
            "amber_moderate": amber_total,
            "green_balanced": green_total,
            "high_playmaker_risk": high_playmaker_total,
            "low_playmaker_risk": low_playmaker_total
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
