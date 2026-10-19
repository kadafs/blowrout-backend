#!/usr/bin/env python3
"""
backfill_shots_stats.py
────────────────────────
Comprehensive historical match statistics backfiller for all professional leagues.
Fetches Total Shots, Shots on Target (SoT), Corners, Booking Points, and xGOT
from API-Sports across the entire season.

Enforces strict daily quota safety checks to preserve API limits.
"""

import os
import sys
import time
import json
import glob
import argparse
import subprocess
import requests
from pathlib import Path
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

load_dotenv()

BASE_URL = "https://v3.football.api-sports.io"
API_KEY = os.getenv("API_BASKETBALL_KEY") or os.getenv("API_FOOTBALL_KEY")
HEADERS = {"x-apisports-key": API_KEY}

ROOT_DIR = Path(__file__).parent
DATA_DIR = ROOT_DIR / "data" / "football"

# Verified leagues with full in-match statistics coverage in API-Sports
COVERED_LEAGUES = {
    # England
    39: "Premier League", 40: "Championship", 41: "League One", 42: "League Two",
    45: "FA Cup", 48: "League Cup", 46: "EFL Trophy", 44: "FA WSL",
    # Spain
    140: "La Liga", 141: "Segunda Division", 143: "Copa del Rey",
    # Germany
    78: "Bundesliga", 79: "2. Bundesliga", 80: "3. Liga", 81: "DFB Pokal", 82: "Frauen Bundesliga",
    # Italy
    135: "Serie A", 136: "Serie B", 137: "Coppa Italia",
    # France
    61: "Ligue 1", 62: "Ligue 2", 66: "Coupe de France", 64: "Feminine Division 1",
    # Netherlands & Belgium
    88: "Eredivisie", 89: "Eerste Divisie", 90: "KNVB Beker",
    144: "Jupiler Pro League", 145: "Challenger Pro League",
    # Portugal & Scotland
    94: "Primeira Liga", 95: "Segunda Liga",
    179: "Premiership", 180: "Championship",
    # Americas
    253: "Major League Soccer", 254: "NWSL Women",
    71: "Serie A (Brazil)", 72: "Serie B (Brazil)", 73: "Copa do Brasil",
    128: "Liga Profesional Argentina", 262: "Liga MX",
    239: "Primera A (Colombia)", 242: "Liga Pro (Ecuador)", 265: "Primera Division (Chile)",
    281: "Primera Division (Peru)", 268: "Primera Division (Uruguay)",
    # European Tournaments & Competitions
    2: "UEFA Champions League", 3: "UEFA Europa League", 848: "UEFA Europa Conference League",
    5: "UEFA Nations League", 13: "CONMEBOL Libertadores", 11: "CONMEBOL Sudamericana",
    17: "AFC Champions League Elite", 18: "AFC Champions League Two",
    # Other Major European & World Leagues
    203: "Super Lig (Turkey)", 204: "1. Lig (Turkey)",
    218: "Bundesliga (Austria)", 219: "2. Liga (Austria)",
    207: "Super League (Switzerland)", 119: "Superliga (Denmark)",
    103: "Eliteserien (Norway)", 113: "Allsvenskan (Sweden)", 114: "Superettan (Sweden)",
    106: "Ekstraklasa (Poland)", 197: "Super League 1 (Greece)", 345: "Czech Liga",
    283: "Liga I (Romania)", 210: "HNL (Croatia)", 271: "NB I (Hungary)",
    235: "Premier League (Russia)", 236: "First League (Russia)", 333: "Premier League (Ukraine)",
    98: "J1 League (Japan)", 292: "K League 1 (South Korea)", 307: "Saudi Pro League",
    188: "A-League (Australia)", 288: "Premier Soccer League (South Africa)"
}


def check_api_quota() -> tuple[int, int, int]:
    """Returns (used, limit, remaining)."""
    try:
        r = requests.get(f"{BASE_URL}/status", headers=HEADERS, timeout=10)
        r.raise_for_status()
        data = r.json().get("response", {})
        req = data.get("requests", {})
        used = req.get("current", 0)
        limit = req.get("limit_day", 7500)
        remaining = max(0, limit - used)
        return used, limit, remaining
    except Exception as e:
        print(f"  [ERROR] Failed to check quota: {e}")
        return 0, 7500, 0


def fetch_fixture_statistics(fixture_id: int, home_team_id: int | None = None) -> dict | None:
    """Fetch and parse fixture statistics from API-Sports."""
    url = f"{BASE_URL}/fixtures/statistics"
    params = {"fixture": fixture_id}
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=10)
        r.raise_for_status()
        resp = r.json().get("response", [])
        if not resp:
            return None

        def parse_stats(stats_list):
            d = {
                "shots_on_goal": 0,
                "total_shots": 0,
                "shots_insidebox": 0,
                "shots_outsidebox": 0,
                "saves": 0,
                "xg": None
            }
            for s in stats_list:
                t = s.get("type")
                val = s.get("value")
                if val is None:
                    continue
                if isinstance(val, str):
                    val = val.replace("%", "").strip()
                try:
                    num = float(val) if "." in str(val) else int(val)
                except Exception:
                    num = 0

                if t == "Shots on Goal": d["shots_on_goal"] = int(num)
                elif t == "Total Shots": d["total_shots"] = int(num)
                elif t == "Shots insidebox": d["shots_insidebox"] = int(num)
                elif t == "Shots outsidebox": d["shots_outsidebox"] = int(num)
                elif t == "Goalkeeper Saves": d["saves"] = int(num)
                elif t == "expected_goals": d["xg"] = float(num)
            return d

        home_stats = parse_stats([])
        away_stats = parse_stats([])

        if len(resp) >= 2:
            t1_id = resp[1].get("team", {}).get("id")
            if home_team_id and t1_id == home_team_id:
                home_stats = parse_stats(resp[1].get("statistics", []))
                away_stats = parse_stats(resp[0].get("statistics", []))
            else:
                home_stats = parse_stats(resp[0].get("statistics", []))
                away_stats = parse_stats(resp[1].get("statistics", []))
        elif len(resp) == 1:
            home_stats = parse_stats(resp[0].get("statistics", []))

        total_corners = 0
        total_booking_pts = 0
        for team_stats in resp:
            for stat in team_stats.get("statistics", []):
                val = stat.get("value")
                if val is None:
                    continue
                if stat.get("type") == "Corner Kicks":
                    try: total_corners += int(val)
                    except: pass
                elif stat.get("type") == "Yellow Cards":
                    try: total_booking_pts += int(val) * 10
                    except: pass
                elif stat.get("type") == "Red Cards":
                    try: total_booking_pts += int(val) * 25
                    except: pass

        return {
            "corners": total_corners,
            "booking_pts": total_booking_pts,
            "home": home_stats,
            "away": away_stats
        }
    except Exception as e:
        return None


def run_backfill(max_calls: int = 2500, safety_buffer: int = 500, delay: float = 0.22):
    print("================================================================================")
    print("  FOOTBALL HISTORICAL STATS BACKFILL ENGINE")
    print("================================================================================")
    
    used, limit, remaining = check_api_quota()
    print(f"  API Quota Status: {used} used / {limit} limit ({remaining} remaining today)")
    
    budget = min(max_calls, max(0, remaining - safety_buffer))
    if budget <= 0:
        print(f"  ❌ Aborting: Insufficient API quota remaining ({remaining} left, safety buffer {safety_buffer}).")
        return

    print(f"  Target Budget: Up to {budget} fixture requests (leaving {remaining - budget} safety reserve).")
    print(f"  Targeting {len(COVERED_LEAGUES)} top covered professional leagues across all dates.\n")

    files = sorted(DATA_DIR.glob("universal_predictions_*.json"), reverse=True)
    total_updated = 0
    total_calls_made = 0

    for file_path in files:
        if total_calls_made >= budget:
            print(f"  🛑 Reached budget limit ({total_calls_made}/{budget} calls). Stopping.")
            break

        date_str = file_path.stem.replace("universal_predictions_", "")
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue

        predictions = d.get("predictions", [])
        file_modified = False
        file_updates = 0

        for g in predictions:
            if total_calls_made >= budget:
                break

            # Must be a finished match
            if g.get("actual_result") is None:
                continue

            # Must be missing shots
            if g.get("actual_shots_total") is not None:
                continue

            # Skip if already attempted and verified empty
            if g.get("actual_shots_fetched"):
                continue

            # Must have fixture_id
            fid = g.get("fixture_id")
            if not fid:
                continue

            # Must belong to our covered professional leagues
            lid = g.get("league_id")
            if lid not in COVERED_LEAGUES:
                continue

            # Fetch statistics
            stats = fetch_fixture_statistics(fid, g.get("home_team_id"))
            total_calls_made += 1
            time.sleep(delay)

            if stats:
                h_st = stats.get("home") or {}
                a_st = stats.get("away") or {}
                h_sh = h_st.get("total_shots")
                a_sh = a_st.get("total_shots")
                h_sot = h_st.get("shots_on_goal")
                a_sot = a_st.get("shots_on_goal")

                g["actual_shots_home"] = h_sh
                g["actual_shots_away"] = a_sh
                g["actual_shots_total"] = (h_sh + a_sh) if (h_sh is not None and a_sh is not None) else None
                g["actual_sot_home"] = h_sot
                g["actual_sot_away"] = a_sot
                g["actual_sot_total"] = (h_sot + a_sot) if (h_sot is not None and a_sot is not None) else None

                if g.get("actual_corners_total") is None and stats.get("corners") is not None:
                    g["actual_corners_total"] = stats["corners"]
                if g.get("actual_booking_pts") is None and stats.get("booking_pts") is not None:
                    g["actual_booking_pts"] = stats["booking_pts"]

                file_modified = True
                file_updates += 1
                total_updated += 1
            else:
                # Mark as fetched with None to prevent redundant re-fetching
                g["actual_shots_total"] = None
                g["actual_shots_fetched"] = True
                file_modified = True

            if total_calls_made % 50 == 0:
                print(f"    [{date_str}] Calls: {total_calls_made}/{budget} | Stats backfilled: {total_updated}")

        if file_modified:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(d, f)
            print(f"  [SAVED] {file_path.name}: {file_updates} matches backfilled.")

    print("\n================================================================================")
    print(f"  BACKFILL COMPLETE: {total_calls_made} API calls made, {total_updated} matches updated.")
    used, limit, remaining = check_api_quota()
    print(f"  Remaining Quota Today: {remaining} requests.")
    print("================================================================================")

    # Automatically re-aggregate leaderboards
    print("\n🔄 Running aggregate_league_stats.py to update leaderboards...")
    subprocess.run([sys.executable, str(ROOT_DIR / "aggregate_league_stats.py")])

    # Push updated data to dashboard
    print("\n🚀 Pushing updated stats to Sports Analytics dashboard...")
    subprocess.run([sys.executable, str(ROOT_DIR / "push_to_dashboard.py"), "--sport", "football"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill football match statistics from API-Sports.")
    parser.add_argument("--max-calls", type=int, default=2500, help="Max API calls to make")
    parser.add_argument("--safety-buffer", type=int, default=500, help="Minimum remaining requests to leave untouched")
    args = parser.parse_args()
    run_backfill(max_calls=args.max_calls, safety_buffer=args.safety_buffer)
