"""
scripts/run_nba_props_daily.py
==============================
Daily NBA Player Props Modeling, Evaluation & Grading Pipeline.

Usage:
  python scripts/run_nba_props_daily.py --date 2026-11-26
  python scripts/run_nba_props_daily.py --backfill 50
"""

import os
import sys
import json
import time
import argparse
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.nba_props_engine import (
    get_api_key,
    load_boxscores_cache,
    save_boxscores_cache,
    fetch_game_boxscore,
    build_player_profiles,
    match_player_name,
    evaluate_prop_opportunity,
    parse_minutes
)

PROPS_OUTPUT_DIR = os.path.join(BASE_DIR, "data", "basketball")

def parse_prop_selection(bet_name, val_dict):
    """
    Parses complex selection strings from API-Basketball bookmakers:
      - 'Josh Giddey - Over 22.5' -> ('Josh Giddey', 'POINTS_ASSISTS', 22.5, 'OVER', 1.85)
      - 'Moussa Diabate - Over 10.5' -> ('Moussa Diabate', 'REBOUNDS', 10.5, 'OVER', 1.87)
      - 'Isaac Okoro - 15' -> ('Isaac Okoro', 'POINTS', 14.5, 'OVER', 4.50)
    """
    val_str = val_dict.get("value", "").strip()
    odd = float(val_dict.get("odd") or 0.0)
    if odd <= 1.0 or not val_str:
        return None
        
    bname_lower = bet_name.lower()
    
    if " - " in val_str:
        parts = val_str.rsplit(" - ", 1)
        player_name = parts[0].strip()
        tail = parts[1].strip()
        
        # 1. Player Points and Assists (PA)
        if "points and assists" in bname_lower:
            if tail.startswith("Over "):
                line = float(tail.replace("Over ", "").strip())
                return player_name, "POINTS_ASSISTS", line, "OVER", odd
            elif tail.startswith("Under "):
                line = float(tail.replace("Under ", "").strip())
                return player_name, "POINTS_ASSISTS", line, "UNDER", odd
                
        # 2. Player Runs (Rebounds)
        elif "runs" in bname_lower or "rebound" in bname_lower:
            if tail.startswith("Over "):
                line = float(tail.replace("Over ", "").strip())
                return player_name, "REBOUNDS", line, "OVER", odd
            elif tail.startswith("Under "):
                line = float(tail.replace("Under ", "").strip())
                return player_name, "REBOUNDS", line, "UNDER", odd
                
        # 3. Player Points Milestones
        elif "milestone" in bname_lower or "point" in bname_lower:
            try:
                line_val = float(tail)
                return player_name, "POINTS", line_val - 0.5, "OVER", odd
            except ValueError:
                if tail.startswith("Over "):
                    line = float(tail.replace("Over ", "").strip())
                    return player_name, "POINTS", line, "OVER", odd
                elif tail.startswith("Under "):
                    line = float(tail.replace("Under ", "").strip())
                    return player_name, "POINTS", line, "UNDER", odd

    return None

def backfill_recent_boxscores(api_key, max_games=50):
    """Fetches missing finished NBA game boxscores to build up the player database."""
    print(f"\nChecking recent NBA finished games in local cache...")
    boxscores = load_boxscores_cache()
    
    url = "https://v1.basketball.api-sports.io/games?league=12&season=2026-2027"
    headers = {"x-apisports-key": api_key}
    r = requests.get(url, headers=headers, timeout=20).json()
    all_games = r.get("response", [])
    
    finished = [g for g in all_games if g.get("status", {}).get("short") == "FT"]
    print(f"Total finished NBA games this season: {len(finished)}")
    
    finished.reverse()
    
    added = 0
    for g in finished:
        gid = str(g["id"])
        if gid not in boxscores:
            dt = g.get("date", "")[:10]
            h = g["teams"]["home"]["name"]
            a = g["teams"]["away"]["name"]
            print(f"  Fetching [{len(boxscores)+1}] Boxscore {gid} ({dt}): {h} vs {a}...")
            bdata = fetch_game_boxscore(gid, api_key)
            if bdata:
                boxscores[gid] = {
                    "meta": {
                        "date": dt,
                        "home": h,
                        "away": a,
                        "home_score": g.get("scores", {}).get("home", {}).get("total"),
                        "away_score": g.get("scores", {}).get("away", {}).get("total"),
                    },
                    "players": bdata
                }
                added += 1
            time.sleep(0.25)
            if added >= max_games:
                break
                
    if added > 0:
        save_boxscores_cache(boxscores)
        print(f"[✓] Added {added} new game boxscores to local cache. Total cached: {len(boxscores)}")
    else:
        print(f"[✓] Cache already up to date ({len(boxscores)} games cached).")
        
    return boxscores

def run():
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parser = argparse.ArgumentParser(description="NBA Player Props Model Runner")
    parser.add_argument("--date", type=str, default=today_str, help="Target date YYYY-MM-DD")
    parser.add_argument("--backfill", type=int, default=20, help="Max games to backfill")
    args = parser.parse_args()
    
    api_key = get_api_key()
    if not api_key:
        print("[!] Error: API_BASKETBALL_KEY not found.")
        return
        
    print("=" * 85)
    print(f"  NBA QUANTITATIVE PLAYER PROPS ENGINE — TARGET DATE: {args.date}")
    print("=" * 85)
    
    # 1. Backfill and load boxscores
    boxscores = backfill_recent_boxscores(api_key, max_games=args.backfill)
    
    # 2. Build player rolling profiles strictly using games before target date
    print(f"\nBuilding rolling player efficiency profiles (zero-lookahead prior to {args.date})...")
    profiles = build_player_profiles(boxscores, max_date=args.date)
    print(f"[✓] Successfully built profiles for {len(profiles)} active NBA players.")
    
    # 3. Fetch games for target date
    url = f"https://v1.basketball.api-sports.io/games?league=12&season=2026-2027&date={args.date}"
    headers = {"x-apisports-key": api_key}
    r = requests.get(url, headers=headers, timeout=20).json()
    games = r.get("response", [])
    print(f"\nFound {len(games)} NBA games on {args.date}:")
    
    all_evaluated_props = []
    
    for g in games:
        gid = g["id"]
        h_name = g["teams"]["home"]["name"]
        a_name = g["teams"]["away"]["name"]
        status = g.get("status", {}).get("short", "")
        print(f"\nProcessing Game {gid}: {h_name} vs {a_name} (Status: {status})")
        
        # Pull odds
        odds_url = f"https://v1.basketball.api-sports.io/odds?game={gid}"
        r_odds = requests.get(odds_url, headers=headers, timeout=20).json()
        odds_resp = r_odds.get("response", [])
        if not odds_resp:
            print("  [~] No odds currently published for this game.")
            continue
            
        bms = odds_resp[0].get("bookmakers", [])
        game_props = []
        
        for bm in bms:
            bm_name = bm.get("name")
            for b in bm.get("bets", []):
                bet_name = b.get("name")
                for val in b.get("values", []):
                    parsed = parse_prop_selection(bet_name, val)
                    if not parsed:
                        continue
                    pname, ptype, line, direction, odd = parsed
                    
                    matched_profile = match_player_name(pname, profiles)
                    if not matched_profile:
                        continue
                        
                    res = evaluate_prop_opportunity(matched_profile, ptype, line, odd, direction)
                    if res:
                        res["game_id"] = str(gid)
                        res["game"] = f"{h_name} vs {a_name}"
                        res["bookmaker"] = bm_name
                        res["status"] = status
                        game_props.append(res)
                        
        print(f"  -> Evaluated {len(game_props)} player prop opportunities.")
        all_evaluated_props.extend(game_props)
        time.sleep(0.2)
        
    print("\n" + "=" * 85)
    print(f"  TOTAL PLAYER PROP OPPORTUNITIES EVALUATED: {len(all_evaluated_props)}")
    print("=" * 85)
    
    # Deduplicate redundant lines for same player & prop type (take best odds)
    best_props_map = {}
    for p in all_evaluated_props:
        bk = f"{p['player_id']}_{p['prop_type']}_{p['line']}_{p['direction']}"
        if bk not in best_props_map or p["odds"] > best_props_map[bk]["odds"]:
            best_props_map[bk] = p
    unique_props = list(best_props_map.values())
    
    # Filter Value Plays
    value_plays = [p for p in unique_props if p["is_value"]]
    std_value = [p for p in value_plays if 1.60 <= p["odds"] <= 2.30]
    alt_value = [p for p in value_plays if p["odds"] > 2.30]
    
    print(f"\nIdentified {len(value_plays)} Total Value Plays:")
    print(f"  - Standard 2-Way Lines (Odds 1.60-2.30): {len(std_value)} plays")
    print(f"  - Alt / Milestone Plus-Money Lines (Odds > 2.30): {len(alt_value)} plays")
    
    # Grade if games are finished
    all_ft = all(g.get("status", {}).get("short") == "FT" for g in games)
    if all_ft:
        print("\n" + "=" * 85)
        print("  ALL GAMES COMPLETED — GRADING MODEL PROPS AGAINST OFFICIAL FINAL BOXSCORES")
        print("=" * 85)
        
        graded_std = []
        for p in std_value:
            gid = p["game_id"]
            pid = p["player_id"]
            game_box = boxscores.get(gid)
            if not game_box:
                continue
            player_entries = game_box.get("players", []) if isinstance(game_box, dict) else game_box
            
            actual_entry = next((pe for pe in player_entries if pe.get("player", {}).get("id") == pid), None)
            if not actual_entry:
                continue
                
            actual_pts = float(actual_entry.get("points") or 0.0)
            actual_ast = float(actual_entry.get("assists") or 0.0)
            reb_dict = actual_entry.get("rebounds") or {}
            actual_reb = float(reb_dict.get("total") if isinstance(reb_dict, dict) else reb_dict or 0.0)
            
            ptype = p["prop_type"]
            val = actual_pts if ptype == "POINTS" else (actual_reb if ptype == "REBOUNDS" else (actual_pts + actual_ast))
            
            won = (val > p["line"]) if p["direction"] == "OVER" else (val < p["line"])
            push = (val == p["line"])
            profit = (p["odds"] - 1.0) if won else (0.0 if push else -1.0)
            
            p["actual_value"] = val
            p["won"] = won
            p["push"] = push
            p["profit"] = profit
            graded_std.append(p)
            
        wins = sum(1 for p in graded_std if p["won"])
        losses = sum(1 for p in graded_std if not p["won"] and not p["push"])
        pushes = sum(1 for p in graded_std if p["push"])
        n = wins + losses
        wr = (wins / n * 100.0) if n > 0 else 0.0
        tot_prof = sum(p["profit"] for p in graded_std)
        roi = (tot_prof / len(graded_std) * 100.0) if graded_std else 0.0
        
        print(f"\n[STANDARD 2-WAY PROPS FINAL SCORECARD]:")
        print(f"  Bets: {len(graded_std)} | Record: {wins}-{losses}-{pushes} | Win Rate: {wr:.1f}% | Profit: {tot_prof:+.2f}u | ROI: {roi:+.2f}%")
        
    # Print Top Standard Value Plays
    std_value.sort(key=lambda x: x["ev_pct"], reverse=True)
    print("\n" + "=" * 115)
    print(f"  TOP RECOMMENDED STANDARD 2-WAY VALUE PLAYS (ODDS 1.60 - 2.30):")
    print("=" * 115)
    print(f"{'#':<3} {'Player':<20} {'Matchup':<26} {'Prop':<14} {'Line':<12} {'Proj':>5} {'Odds':>5} {'Win%':>6} {'Edge%':>6} {'EV%':>6}")
    print("-" * 115)
    
    for idx, vp in enumerate(std_value[:20], 1):
        line_str = f"{vp['direction']} {vp['line']}"
        print(f"{idx:<3} {vp['player']:<20} {vp['game']:<26} {vp['prop_type']:<14} {line_str:<12} {vp['projected_value']:>5.1f} {vp['odds']:>5.2f} {vp['win_probability']:>5.1f}% {vp['edge_pct']:>+5.1f}% {vp['ev_pct']:>+5.1f}%")
        
    # Save output to JSON
    os.makedirs(PROPS_OUTPUT_DIR, exist_ok=True)
    out_file = os.path.join(PROPS_OUTPUT_DIR, f"nba_player_props_{args.date}.json")
    latest_file = os.path.join(PROPS_OUTPUT_DIR, "nba_player_props_latest.json")
    
    payload = {
        "date": args.date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_evaluated": len(all_evaluated_props),
        "unique_props_count": len(unique_props),
        "standard_value_count": len(std_value),
        "alt_value_count": len(alt_value),
        "standard_value_plays": std_value,
        "alt_value_plays": alt_value
    }
    
    with open(out_file, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)
    with open(latest_file, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2, ensure_ascii=False)
        
    print(f"\n[✓] Results successfully exported to:\n  - {out_file}\n  - {latest_file}")

if __name__ == "__main__":
    run()
