"""
calculate_sdi.py
================
Star Dependency Index (SDI) Calculator (API-Powered with Local Boxscore Cache)

Calculates per-team scoring concentration metrics using official player box scores
from API-Basketball (/games/statistics/players).

SDI Formula:
    SDI = avg((Top 2 scorers' pts) / Team total pts) * 100

Risk Tiers:
    GREEN  (< 40%)  - Balanced roster, resilient
    AMBER  (40-54%) - Moderate dependency, monitor key players
    RED    (>= 55%) - High dependency, injury = collapse

Usage:
    python calculate_sdi.py                # Checks last 7 days of games
    python calculate_sdi.py --days 14      # Checks last 14 days of games
    python calculate_sdi.py --verbose      # Prints detailed breakdown
"""

import os
import json
import glob
import time
import argparse
from datetime import datetime, timedelta
from collections import defaultdict
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
DATA_DIR       = os.path.join(BASE_DIR, "data")
BASKETBALL_DIR = os.path.join(DATA_DIR, "basketball")
CACHE_DIR      = os.path.join(DATA_DIR, "cache", "boxscores")
OUTPUT_FILE    = os.path.join(BASKETBALL_DIR, "team_sdi.json")
API_KEY        = os.getenv("API_BASKETBALL_KEY", "")
API_URL        = "https://v1.basketball.api-sports.io"

MIN_GAMES_DEFAULT = 2


def fetch_recent_finished_games(days=7):
    """Fetch finished games from the last N days via API-Basketball."""
    if not API_KEY:
        print("  [!] Warning: API_BASKETBALL_KEY not set. Cannot fetch new games.")
        return []

    headers = {"x-apisports-key": API_KEY}
    today = datetime.today().date()
    all_games = []

    print(f"  Fetching finished games for the last {days} days from API-Basketball...")
    for i in range(1, days + 1):
        target_date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        try:
            r = requests.get(f"{API_URL}/games?date={target_date}", headers=headers, timeout=15)
            if r.status_code == 200:
                resp = r.json().get("response", [])
                finished = [
                    g for g in resp 
                    if g.get("status", {}).get("short") in ("FT", "AOT")
                    and g.get("scores", {}).get("home", {}).get("total") is not None
                    and g.get("scores", {}).get("away", {}).get("total") is not None
                ]
                all_games.extend(finished)
                print(f"    {target_date}: {len(finished)} finished games found.")
            else:
                print(f"    {target_date}: HTTP {r.status_code}")
        except Exception as e:
            print(f"    {target_date}: Error fetching games: {e}")
        time.sleep(0.3)

    return all_games


def load_cached_boxscores():
    """Load all locally cached player box scores."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache = {}
    pattern = os.path.join(CACHE_DIR, "*.json")
    for filepath in glob.glob(pattern):
        try:
            gid = int(os.path.basename(filepath).replace(".json", ""))
            with open(filepath, "r", encoding="utf-8") as f:
                cache[gid] = json.load(f)
        except Exception:
            continue
    return cache


def save_boxscores_to_cache(game_id, player_records):
    """Save player records for a game to local cache."""
    try:
        path = os.path.join(CACHE_DIR, f"{game_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(player_records, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_boxscores_batch(game_ids, headers):
    """Fetch player box scores for up to 20 games in a single call."""
    if not game_ids:
        return {}
    
    ids_str = "-".join(str(gid) for gid in game_ids)
    url = f"{API_URL}/games/statistics/players?ids={ids_str}"
    
    try:
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code == 200:
            resp = r.json().get("response", [])
            by_game = defaultdict(list)
            for p in resp:
                gid = p.get("game", {}).get("id")
                if gid:
                    by_game[gid].append(p)
            return by_game
        else:
            print(f"    [!] Error fetching boxscore batch: HTTP {r.status_code}")
    except Exception as e:
        print(f"    [!] Exception in batch fetch: {e}")
    
    return {}


def get_all_boxscores(games, cached_scores):
    """Ensure all games have boxscores, fetching missing ones via API in batches."""
    headers = {"x-apisports-key": API_KEY}
    missing_gids = [g["id"] for g in games if g["id"] not in cached_scores]
    
    if missing_gids and API_KEY:
        print(f"  Fetching player box scores for {len(missing_gids)} games (batches of 20)...")
        # Chunk into groups of 20
        chunk_size = 20
        chunks = [missing_gids[i:i + chunk_size] for i in range(0, len(missing_gids), chunk_size)]
        
        for idx, chunk in enumerate(chunks, 1):
            batch_data = fetch_boxscores_batch(chunk, headers)
            for gid in chunk:
                players = batch_data.get(gid, [])
                cached_scores[gid] = players
                save_boxscores_to_cache(gid, players)
            
            print(f"    [{idx}/{len(chunks)}] Fetched {len(chunk)} games ({sum(len(v) for v in batch_data.values())} player stats).")
            time.sleep(0.3)
    else:
        print(f"  All {len(games)} games are already present in local boxscore cache.")

    return cached_scores


def compute_sdi_for_players(players, team_score):
    """Calculate SDI, top 1 %, top 2 player names, and Top-1 Playmaker Offensive Share."""
    if not players or not team_score or team_score <= 0:
        return None, None, [], None, None
    
    # Sort players by points descending for standard Top-2 SDI
    sorted_players = sorted(players, key=lambda x: x.get("points") or 0, reverse=True)
    top2 = sorted_players[:2]
    top2_pts = sum(p.get("points") or 0 for p in top2)
    top1_pts = top2[0].get("points") or 0 if top2 else 0

    sdi_pct = (top2_pts / team_score) * 100
    top1_pct = (top1_pts / team_score) * 100
    top2_names = [p.get("player", {}).get("name", "Unknown") for p in top2]

    # Calculate Top-1 Playmaker Offensive Share: (pts + 2.15 * ast) / team_score
    top1_off_share = None
    top_creator_name = None
    has_ast = any(p.get("assists") is not None for p in players)
    if has_ast:
        creator_list = []
        for p in players:
            pts = float(p.get("points") or 0)
            ast = float(p.get("assists") or 0)
            p_name = p.get("player", {}).get("name", "Unknown")
            creator_list.append((p_name, pts + 2.15 * ast))
        if creator_list:
            creator_list.sort(key=lambda x: x[1], reverse=True)
            top_creator_name, top_off_pts = creator_list[0]
            top1_off_share = round((top_off_pts / team_score) * 100.0, 1)

    return round(sdi_pct, 1), round(top1_pct, 1), top2_names, top1_off_share, top_creator_name


def load_previous_sdi():
    """Load existing SDI output to preserve historical teams that haven't played recently."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def main():
    parser = argparse.ArgumentParser(description="Calculate Star Dependency Index (SDI) per team via API.")
    parser.add_argument("--days", type=int, default=7, help="Number of past days to fetch (default: 7)")
    parser.add_argument("--min_games", type=int, default=MIN_GAMES_DEFAULT, help="Minimum games required")
    parser.add_argument("--verbose", action="store_true", help="Print verbose team details")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  STAR DEPENDENCY INDEX (SDI) CALCULATOR (API-POWERED)")
    print("=" * 70)

    # 1. Load cached boxscores
    cached_boxscores = load_cached_boxscores()
    print(f"  Loaded {len(cached_boxscores)} previously cached game box scores.")

    # 2. Fetch recent games from API
    games = fetch_recent_finished_games(days=args.days)
    
    # 3. Fetch missing box scores in batches of 20
    all_boxscores = get_all_boxscores(games, cached_boxscores)

    # 4. Map game details
    game_lookup = {}
    for g in games:
        game_lookup[g["id"]] = {
            "home_id": g["teams"]["home"]["id"],
            "home_name": g["teams"]["home"]["name"],
            "home_score": g["scores"]["home"]["total"] or 0,
            "away_id": g["teams"]["away"]["id"],
            "away_name": g["teams"]["away"]["name"],
            "away_score": g["scores"]["away"]["total"] or 0,
        }

    # 5. Process player stats by team
    team_data = defaultdict(lambda: {
        "sdi_samples": [],
        "top1_samples": [],
        "top_scorers": defaultdict(int),
        "off_share_samples": [],
        "top_creators": defaultdict(int),
        "game_count": 0
    })

    processed_games = 0
    for gid, players in all_boxscores.items():
        if not players:
            continue
        ginfo = game_lookup.get(gid)
        if not ginfo:
            continue
        
        # Group players by team_id
        team_players = defaultdict(list)
        for p in players:
            tid = p.get("team", {}).get("id")
            if tid:
                team_players[tid].append(p)

        # For home team
        h_id = ginfo["home_id"]
        h_name = ginfo["home_name"]
        h_score = ginfo["home_score"]
        if h_id in team_players and h_score > 0:
            sdi, top1, stars, top1_off, creator = compute_sdi_for_players(team_players[h_id], h_score)
            if sdi is not None:
                team_data[h_name]["sdi_samples"].append(sdi)
                team_data[h_name]["top1_samples"].append(top1)
                team_data[h_name]["game_count"] += 1
                for star in stars:
                    team_data[h_name]["top_scorers"][star] += 1
                if top1_off is not None:
                    team_data[h_name]["off_share_samples"].append(top1_off)
                    team_data[h_name]["top_creators"][creator] += 1

        # For away team
        a_id = ginfo["away_id"]
        a_name = ginfo["away_name"]
        a_score = ginfo["away_score"]
        if a_id in team_players and a_score > 0:
            sdi, top1, stars, top1_off, creator = compute_sdi_for_players(team_players[a_id], a_score)
            if sdi is not None:
                team_data[a_name]["sdi_samples"].append(sdi)
                team_data[a_name]["top1_samples"].append(top1)
                team_data[a_name]["game_count"] += 1
                for star in stars:
                    team_data[a_name]["top_scorers"][star] += 1
                if top1_off is not None:
                    team_data[a_name]["off_share_samples"].append(top1_off)
                    team_data[a_name]["top_creators"][creator] += 1

        processed_games += 1

    print(f"  Processed player statistics across {processed_games} games.")

    # 6. Build new team SDI list
    new_team_records = {}
    for team_name, d in team_data.items():
        g = d["game_count"]
        if g < args.min_games:
            continue

        avg_sdi  = round(sum(d["sdi_samples"])  / g, 1)
        avg_top1 = round(sum(d["top1_samples"]) / g, 1)
        max_sdi  = round(max(d["sdi_samples"]),  1)
        min_sdi  = round(min(d["sdi_samples"]),  1)

        top_players = sorted(d["top_scorers"].items(), key=lambda x: x[1], reverse=True)
        top_players_list = [{"name": n, "times_top2": t} for n, t in top_players[:5]]

        if avg_sdi >= 55:
            risk = "RED"
            risk_label = "HIGH DEPENDENCY"
        elif avg_sdi >= 40:
            risk = "AMBER"
            risk_label = "MODERATE"
        else:
            risk = "GREEN"
            risk_label = "BALANCED"

        # Playmaker Dependency calculation
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

        new_team_records[team_name] = {
            "team":               team_name,
            "games_tracked":      g,
            "avg_sdi":            avg_sdi,
            "avg_top1_pct":       avg_top1,
            "max_sdi":            max_sdi,
            "min_sdi":            min_sdi,
            "risk":               risk,
            "risk_label":         risk_label,
            "top_players":        top_players_list,
            "avg_top1_off_share": avg_off_share,
            "playmaker_risk":     playmaker_risk,
            "top_creator":        top_creator_name,
        }

    # 7. Merge with existing previous SDI so we don't drop teams that didn't play in this window
    prev_data = load_previous_sdi()
    merged_teams = {}
    if prev_data and "teams" in prev_data:
        for t in prev_data["teams"]:
            for p in t.get("top_players", []):
                if "name" in p:
                    import re
                    p["name"] = re.sub(r"\s+", " ", p["name"]).strip()
            merged_teams[t["team"]] = t

    # Overwrite / update with fresh records
    for team_name, rec in new_team_records.items():
        merged_teams[team_name] = rec

    results = list(merged_teams.values())
    results.sort(key=lambda x: x.get("avg_sdi", 0), reverse=True)

    red_count   = sum(1 for r in results if r.get("risk") == "RED")
    amber_count = sum(1 for r in results if r.get("risk") == "AMBER")
    green_count = sum(1 for r in results if r.get("risk") == "GREEN")

    output = {
        "generated_at":     datetime.now().isoformat(),
        "total_teams":      len(results),
        "source":           "api-basketball",
        "summary": {
            "red_high_dependency": red_count,
            "amber_moderate":      amber_count,
            "green_balanced":      green_count,
        },
        "teams": results
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Results: {len(results)} teams tracked ({len(new_team_records)} updated from fresh API data).")
    print(f"  Risk breakdown: RED={red_count} | AMBER={amber_count} | GREEN={green_count}")
    print(f"  Output saved -> {OUTPUT_FILE}")

    # Print top 10 most star-dependent teams
    print(f"\n  TOP 10 MOST STAR-DEPENDENT TEAMS:")
    print(f"  {'Team':<35} {'SDI':>6} {'Top1':>5} {'Risk':<8} {'Key Players'}")
    print("  " + "-" * 85)
    for r in results[:10]:
        stars = ", ".join(p["name"] for p in r.get("top_players", [])[:2])
        print(f"  {r['team']:<35} {r.get('avg_sdi', 0):>5}% {r.get('avg_top1_pct', 0):>4}% {r.get('risk_label', ''):<12} {stars}")

    # Also merge all Proballers NCAA and extra league box scores
    try:
        from scripts.build_ncaa_sdi import build_ncaa_sdi
        print("\n" + "=" * 70)
        print("  MERGING PROBALLERS (NCAA & OTHER) BOX SCORES INTO SDI DATABASE")
        print("=" * 70)
        build_ncaa_sdi()
    except Exception as e:
        print(f"  [!] Note: Could not auto-merge Proballers SDI: {e}")


if __name__ == "__main__":
    main()
