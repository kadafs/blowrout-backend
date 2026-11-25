"""
scripts/rescrape_ncaa_assists.py
================================
Backfills player assists for older historical NCAA games in data/historical/proballers_ncaa.json.

Workflow:
1. Checks if stored Proballers session is active.
   If expired, instructs user to run: python refresh_proballers_session.py
2. Fetches NCAA league schedule match links.
3. Scrapes each box score with the updated parser (capturing points + assists).
4. Updates existing records in proballers_ncaa.json where assists were missing.
5. Saves progress incrementally every 25 games.

Usage:
    python scripts/rescrape_ncaa_assists.py
    python scripts/rescrape_ncaa_assists.py --max 100
"""

import sys
import os
import json
import time
import random
import argparse

sys.path.insert(0, os.path.abspath("."))
from scrape_proballers import get_proballers_session, extract_league_schedule, scrape_match

NCAA_URL = "https://www.proballers.com/basketball/league/5/ncaa/schedule"
DATA_FILE = "data/historical/proballers_ncaa.json"

def has_assists(game):
    """Check if a game already has player assists recorded."""
    st = game.get("stats", {})
    for side in ["home", "away"]:
        for p in st.get(side, {}).get("players", []):
            if "ast" in p or "assists" in p:
                return True
    return False

def main():
    parser = argparse.ArgumentParser(description="Backfill assists for older NCAA games.")
    parser.add_argument("--max", type=int, default=None, help="Maximum games to scrape in this run")
    parser.add_argument("--delay_min", type=float, default=1.2, help="Min delay between requests (s)")
    parser.add_argument("--delay_max", type=float, default=2.5, help="Max delay between requests (s)")
    args = parser.parse_args()

    print("=" * 70)
    print("  NCAA BOXSCORE ASSIST BACKFILL TOOL")
    print("=" * 70)

    # 1. Check session
    sess = get_proballers_session()
    if not sess:
        print("\n[!] Cloudflare session not found or curl_cffi missing.")
        print("[!] Please run: python refresh_proballers_session.py to log in.\n")
        return

    # 2. Load existing dataset
    if not os.path.exists(DATA_FILE):
        print(f"[!] {DATA_FILE} not found. Cannot backfill.")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as fp:
        games = json.load(fp)

    total_games = len(games)
    games_with_ast = sum(1 for g in games if has_assists(g))
    games_needing_ast = total_games - games_with_ast

    print(f"Loaded {total_games} total NCAA games from {DATA_FILE}:")
    print(f"  - Already have assists: {games_with_ast}")
    print(f"  - Need assists:         {games_needing_ast}")

    if games_needing_ast == 0:
        print("\n[✓] All historical NCAA games already have player assists recorded!")
        return

    # Build signature lookup: (date, home_team, away_team) -> index in games
    sig_map = {}
    for idx, g in enumerate(games):
        sig = f"{g.get('date')} {g.get('home_team')} {g.get('away_team')}"
        sig_map[sig] = idx

    # 3. Extract schedule URLs
    print(f"\nFetching schedule links from Proballers NCAA: {NCAA_URL} ...")
    try:
        match_links = extract_league_schedule(NCAA_URL, session=sess)
    except Exception as e:
        print(f"[!] Failed to fetch schedule: {e}")
        return

    if not match_links:
        print("\n[!] 0 match links found. Cloudflare session has expired.")
        print("[!] Please run: python refresh_proballers_session.py on your desktop, then retry.\n")
        return

    print(f"Found {len(match_links)} game links on Proballers schedule.")
    if args.max:
        match_links = match_links[:args.max]
        print(f"Capped to first {len(match_links)} links via --max {args.max}.")

    # 4. Process each match link
    updated_count = 0
    new_count = 0
    skipped_count = 0

    print("\nStarting backfill scrape...")
    for idx, link in enumerate(match_links, 1):
        slug = link.rstrip("/").split("/")[-1]
        print(f"  [{idx}/{len(match_links)}] Scraping {slug} ...")

        try:
            m_data = scrape_match(link, session=sess)
        except Exception as e:
            print(f"      [!] Error fetching {slug}: {e}")
            continue

        if not m_data:
            print("      [!] Empty data or Cloudflare block. Pausing.")
            continue

        sig = f"{m_data.get('date')} {m_data.get('home_team')} {m_data.get('away_team')}"
        if sig in sig_map:
            existing_idx = sig_map[sig]
            if not has_assists(games[existing_idx]):
                games[existing_idx] = m_data
                updated_count += 1
                print(f"      [+] Backfilled assists for: {sig}")
            else:
                skipped_count += 1
                print(f"      [~] Game already has assists: {sig}")
        else:
            games.append(m_data)
            sig_map[sig] = len(games) - 1
            new_count += 1
            print(f"      [+] Added new match with assists: {sig}")

        # Auto-save every 25 updates
        if (updated_count + new_count) > 0 and (updated_count + new_count) % 25 == 0:
            with open(DATA_FILE, "w", encoding="utf-8") as fp:
                json.dump(games, fp, indent=2, ensure_ascii=False)
            print(f"      [*] Checkpoint saved ({updated_count} updated, {new_count} new).")

        time.sleep(random.uniform(args.delay_min, args.delay_max))

    # Final save
    with open(DATA_FILE, "w", encoding="utf-8") as fp:
        json.dump(games, fp, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("  BACKFILL COMPLETE")
    print(f"  Updated with assists: {updated_count}")
    print(f"  New games added:      {new_count}")
    print(f"  Skipped (had ast):    {skipped_count}")
    print(f"  Saved to:             {DATA_FILE}")
    print("=" * 70)

if __name__ == "__main__":
    main()
