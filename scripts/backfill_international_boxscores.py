"""
scripts/backfill_international_boxscores.py
===========================================
Batch-fetches missing player boxscores from API-Basketball for finished games
in international and professional leagues, caching them into data/cache/boxscores/
so that calculate_sdi.py can compute Top-1 Playmaker Dependency / Creator Index
for all non-NCAA teams.
"""

import os
import glob
import json
import time
import argparse
from datetime import datetime
from collections import defaultdict
import requests
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache", "boxscores")
MC_DIR = os.path.join(DATA_DIR, "cache", "match_center")
API_KEY = os.getenv("API_BASKETBALL_KEY", "")
API_URL = "https://v1.basketball.api-sports.io"

def fetch_boxscores_batch(game_ids, headers):
    if not game_ids:
        return {}
    ids_str = "-".join(str(gid) for gid in game_ids)
    url = f"{API_URL}/games/statistics/players?ids={ids_str}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code == 200:
            resp = r.json().get("response", [])
            by_game = defaultdict(list)
            for p in resp:
                gid = p.get("game", {}).get("id")
                if gid:
                    by_game[gid].append(p)
            return by_game
        else:
            print(f"    [!] Error HTTP {r.status_code}: {r.text[:100]}")
    except Exception as e:
        print(f"    [!] Exception in batch fetch: {e}")
    return {}

def main():
    parser = argparse.ArgumentParser(description="Backfill missing boxscores for international leagues.")
    parser.add_argument("--max_games", type=int, default=600, help="Max games to fetch (default: 600)")
    parser.add_argument("--all_leagues", action="store_true", help="Fetch across all leagues, not just today's active leagues")
    args = parser.parse_args()

    if not API_KEY:
        print("[!] Error: API_BASKETBALL_KEY not set in .env")
        return

    os.makedirs(CACHE_DIR, exist_ok=True)

    # 1. Check existing boxscore cache
    existing_box = {int(os.path.basename(f).replace(".json", "")) for f in glob.glob(os.path.join(CACHE_DIR, "*.json"))}
    print(f"Existing boxscores in local cache: {len(existing_box)}")

    # 2. Identify target leagues (today's active leagues from universal predictions or match_center)
    target_lids = set()
    today_preds_file = os.path.join(os.path.dirname(BASE_DIR), "Sports Analytics", "public", "data", "basketball", f"universal_predictions_{datetime.now().strftime('%Y-%m-%d')}_v2.json")
    if not os.path.exists(today_preds_file):
        # Fallback to any recent predictions file
        cand_files = sorted(glob.glob(os.path.join(os.path.dirname(BASE_DIR), "Sports Analytics", "public", "data", "basketball", "universal_predictions_*_v2.json")))
        if cand_files:
            today_preds_file = cand_files[-1]

    if os.path.exists(today_preds_file) and not args.all_leagues:
        try:
            with open(today_preds_file, "r", encoding="utf-8") as fp:
                pdata = json.load(fp)
                for p in pdata.get("predictions", []):
                    lid = p.get("league_id")
                    if lid:
                        target_lids.add(int(lid))
            print(f"Targeting {len(target_lids)} leagues playing today from {os.path.basename(today_preds_file)}: {sorted(target_lids)}")
        except Exception as e:
            print(f"Error reading today's predictions: {e}")

    # 3. Scan match_center for finished games
    missing_games = []
    league_names = {}
    for mf in glob.glob(os.path.join(MC_DIR, "games_*.json")):
        try:
            with open(mf, "r", encoding="utf-8") as fp:
                data = json.load(fp)
                glist = data if isinstance(data, list) else data.get("response", [])
                for g in glist:
                    gid = g.get("id")
                    status = g.get("status", {}).get("short")
                    lid = g.get("league", {}).get("id")
                    lname = g.get("league", {}).get("name", "Unknown")
                    if lid:
                        league_names[lid] = lname
                    if gid and status in ("FT", "AOT") and gid not in existing_box:
                        if args.all_leagues or (not target_lids) or (lid in target_lids):
                            missing_games.append((gid, lid, lname))
        except Exception:
            pass

    # Deduplicate by gid
    unique_missing = {}
    for gid, lid, lname in missing_games:
        if gid not in unique_missing:
            unique_missing[gid] = (lid, lname)

    missing_list = list(unique_missing.keys())
    print(f"Total missing finished games in target leagues: {len(missing_list)}")
    if not missing_list:
        print("All target games are already present in boxscore cache!")
        return

    if args.max_games and len(missing_list) > args.max_games:
        missing_list = missing_list[:args.max_games]
        print(f"Limiting fetch to {args.max_games} games.")

    chunk_size = 20
    chunks = [missing_list[i:i + chunk_size] for i in range(0, len(missing_list), chunk_size)]
    headers = {"x-apisports-key": API_KEY}

    print(f"\nStarting batch fetch: {len(chunks)} API requests for {len(missing_list)} games...")
    fetched_games_count = 0
    fetched_player_records = 0

    for idx, chunk in enumerate(chunks, 1):
        batch_data = fetch_boxscores_batch(chunk, headers)
        for gid in chunk:
            players = batch_data.get(gid, [])
            path = os.path.join(CACHE_DIR, f"{gid}.json")
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(players, fp, ensure_ascii=False)
            if players:
                fetched_games_count += 1
                fetched_player_records += len(players)

        print(f"  [{idx}/{len(chunks)}] Fetched {len(chunk)} games -> {sum(len(v) for v in batch_data.values())} player stats.")
        time.sleep(0.3)

    print(f"\n[+] Batch backfill complete!")
    print(f"  Games saved with player stats: {fetched_games_count} / {len(missing_list)}")
    print(f"  Total player stat records: {fetched_player_records}")

if __name__ == "__main__":
    main()
