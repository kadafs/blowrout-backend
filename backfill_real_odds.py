"""
backfill_real_odds.py
=====================
Backfills real sportsbook market lines (Pinnacle/Bet365/William Hill consensus)
into historical prediction files, replacing baseline averages.

Usage:
    python backfill_real_odds.py --date 2026-10-31
"""

import os
import sys
import glob
import json
import time
import argparse
from datetime import datetime
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.odds_client import fetch_game_odds

def backfill_date(target_date="2026-10-31"):
    print(f"\n{'='*75}")
    print(f"  BACKFILLING REAL MARKET ODDS FOR DATE: {target_date}")
    print(f"{'='*75}")

    pred_v2_path = f"data/basketball/universal_predictions_{target_date}_v2.json"
    pred_v1_path = f"data/basketball/universal_predictions_{target_date}.json"

    if not os.path.exists(pred_v2_path):
        print(f"Error: {pred_v2_path} does not exist.")
        return

    with open(pred_v2_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    predictions = data.get("predictions", [])
    print(f"Found {len(predictions)} predictions for {target_date}.")

    # Build game_id mapping from historical files
    print("Building game_id lookup from historical databases...")
    historical_files = glob.glob("data/historical/api_basketball_*.json")
    game_id_map = {}

    for hf in historical_files:
        try:
            with open(hf, "r", encoding="utf-8") as f:
                games = json.load(f)
        except Exception:
            continue
        for g in games:
            if g.get("date") == target_date:
                h = g.get("home_team", "").lower().strip()
                a = g.get("away_team", "").lower().strip()
                gid = g.get("game_id")
                if h and a and gid:
                    game_id_map[(h, a)] = gid

    print(f"Mapped {len(game_id_map)} game IDs for {target_date}.")

    # Load persistent odds cache
    cache_dir = "data/cache/odds"
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"odds_{target_date}.json")
    odds_cache = {}
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                odds_cache = json.load(f)
        except Exception:
            odds_cache = {}

    # Load MBET threshold matrix
    mbet_matrix = {}
    try:
        with open("configs/league_edge_thresholds.json", "r", encoding="utf-8") as f:
            mbet_matrix = json.load(f)
    except Exception:
        pass

    updated_count = 0
    checked_count = 0
    no_odds_count = 0

    for i, p in enumerate(predictions):
        h = p.get("home_team", "").lower().strip()
        a = p.get("away_team", "").lower().strip()
        lid = str(p.get("league_id", ""))

        gid = p.get("game_id") or game_id_map.get((h, a))
        if not gid:
            # Fuzzy match attempt
            for (kh, ka), map_gid in game_id_map.items():
                if (h in kh or kh in h) and (a in ka or ka in a):
                    gid = map_gid
                    break

        if not gid:
            continue

        p["game_id"] = gid
        checked_count += 1

        # Fetch odds
        gid_str = str(gid)
        if gid_str in odds_cache:
            odds_info = odds_cache[gid_str]
        else:
            odds_info = fetch_game_odds(gid)
            odds_cache[gid_str] = odds_info
            time.sleep(0.05)  # slight pause for API pacing

        if odds_info.get("has_live_odds") and odds_info.get("market_total"):
            real_mkt = odds_info["market_total"]
            model_tot = p.get("model_total", 0.0)
            edge = round(model_tot - real_mkt, 1)
            side = "OVER" if edge > 0 else "UNDER"
            abs_edge = abs(edge)

            mbet = p.get("mbet_threshold")
            if not mbet:
                mbet = mbet_matrix.get(lid, {}).get("recommended_minimum_edge", 6.5)

            if abs_edge >= (mbet + 1.5):
                decision = f"PLAY {side}"
                confidence = "HIGH"
            elif abs_edge >= mbet:
                decision = "PASS"
                confidence = "SOLID"
            else:
                decision = "PASS"
                confidence = "MBET FILTER"

            # Update prediction fields
            p["market_total"] = real_mkt
            p["edge"] = edge
            p["side"] = side
            p["decision"] = decision
            p["confidence"] = confidence
            p["odds_source"] = odds_info.get("bookmaker") or "BOOKMAKER"
            p["bookmaker"] = odds_info.get("bookmaker")
            p["odds_over"] = odds_info.get("odds_over")
            p["odds_under"] = odds_info.get("odds_under")
            p["baseline_total"] = None

            updated_count += 1
            if updated_count % 10 == 0 or updated_count <= 5:
                print(f"  [{updated_count:>3}] {p.get('home_team')} vs {p.get('away_team')} -> Real Line: {real_mkt} [{odds_info.get('bookmaker')}] | Edge: {edge:+.1f} {decision}")
        else:
            no_odds_count += 1

    # Save persistent cache
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(odds_cache, f, indent=2)

    # Save updated prediction files
    with open(pred_v2_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    if os.path.exists(pred_v1_path):
        with open(pred_v1_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    print(f"\n{'='*75}")
    print(f"  BACKFILL COMPLETE FOR {target_date}")
    print(f"  Total Predictions: {len(predictions)}")
    print(f"  Games Checked:     {checked_count}")
    print(f"  Updated with Real Lines: {updated_count}")
    print(f"  No Bookmaker Lines Found: {no_odds_count}")
    print(f"  Saved to: {pred_v2_path}")
    print(f"{'='*75}\n")

    # Sync to Sports Analytics frontend if directory exists
    frontend_dir = "../Sports Analytics/public/data/basketball"
    if os.path.exists(frontend_dir):
        frontend_v2 = os.path.join(frontend_dir, f"universal_predictions_{target_date}_v2.json")
        frontend_v1 = os.path.join(frontend_dir, f"universal_predictions_{target_date}.json")
        with open(frontend_v2, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        with open(frontend_v1, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"  Successfully synced updated predictions to frontend: {frontend_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill real sportsbook lines into historical predictions.")
    parser.add_argument("--date", type=str, default="2026-10-31", help="Target date YYYY-MM-DD")
    args = parser.parse_args()
    backfill_date(args.date)

