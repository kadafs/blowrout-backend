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
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath("."))
from scrape_proballers import get_proballers_session, scrape_match

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
    parser.add_argument("--team", type=str, default=None, help="Filter matches for a specific team (e.g. 'Virginia')")
    parser.add_argument("--url", type=str, default=None, help="Direct schedule URL (league or team schedule)")
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

    # Build fast lookup sets:
    # 1. Existing matchups that ALREADY have assists
    existing_with_ast = set()
    for g in games:
        if has_assists(g):
            h = (g.get('home_team') or '').strip().lower()
            a = (g.get('away_team') or '').strip().lower()
            existing_with_ast.add((h, a))

    # Build signature lookup: (date, home_team, away_team) AND (home_team, away_team) fallback
    sig_map = {}
    team_pair_map = {}
    for idx, g in enumerate(games):
        h = (g.get('home_team') or '').strip().lower()
        a = (g.get('away_team') or '').strip().lower()
        d = (g.get('date') or '').strip()
        sig = f"{d} {h} {a}"
        sig_map[sig] = idx
        if (h, a) not in team_pair_map:
            team_pair_map[(h, a)] = []
        team_pair_map[(h, a)].append(idx)

    # 3. Fetch schedule page and parse table rows
    target_url = args.url or NCAA_URL
    print(f"\nFetching schedule from: {target_url} ...")
    try:
        resp = sess.get(target_url, timeout=20)
        if resp.status_code == 403 or "Just a moment..." in resp.text:
            print("\n[!] Cloudflare challenge encountered (HTTP 403).")
            print("[!] Please run: python refresh_proballers_session.py on your desktop, then retry.\n")
            return
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"[!] Failed to fetch schedule: {e}")
        return

    # Extract all game rows and pre-filter
    to_scrape = []
    already_have_count = 0

    for tr in soup.find_all("tr"):
        game_link = tr.find("a", href=lambda h: h and "/basketball/game/" in h)
        if not game_link:
            continue
        team_entries = tr.find_all("a", class_="list-team-entry")
        if len(team_entries) >= 2:
            h_title = team_entries[0].find("span", class_="title")
            a_title = team_entries[1].find("span", class_="title")
            h_name = (h_title.text if h_title else team_entries[0].text).strip()
            a_name = (a_title.text if a_title else team_entries[1].text).strip()
            href = game_link["href"]
            full_url = "https://www.proballers.com" + href if not href.startswith("http") else href
            
            # Check team filter if user specified --team
            if args.team:
                t_lower = args.team.lower()
                if t_lower not in h_name.lower() and t_lower not in a_name.lower():
                    continue

            # Check if this matchup ALREADY has assists
            pair = (h_name.lower(), a_name.lower())
            if pair in existing_with_ast:
                already_have_count += 1
                continue

            to_scrape.append((h_name, a_name, full_url))

    print(f"\nSchedule Table Scan Complete:")
    print(f"  - Total matches on schedule:  {already_have_count + len(to_scrape)}")
    print(f"  - Already have assists:        {already_have_count} (SKIPPED instantly - 0 requests)")
    print(f"  - Genuinely need backfill:     {len(to_scrape)}")

    if not to_scrape:
        print("\n[✓] All target matches already have player assists! Nothing to scrape.")
        return

    if args.max:
        to_scrape = to_scrape[:args.max]
        print(f"Capped to first {len(to_scrape)} links via --max {args.max}.")

    # 4. Process each match link that genuinely needs assists
    updated_count = 0
    new_count = 0

    print(f"\nStarting backfill scrape for {len(to_scrape)} matches...")
    for idx, (h_sched, a_sched, link) in enumerate(to_scrape, 1):
        slug = link.rstrip("/").split("/")[-1]
        print(f"  [{idx}/{len(to_scrape)}] Scraping {slug} ...")

        try:
            m_data = scrape_match(link, session=sess)
        except Exception as e:
            print(f"      [!] Error fetching {slug}: {e}")
            continue

        if not m_data:
            print("      [!] Empty data or Cloudflare block. Pausing.")
            continue

        h = (m_data.get('home_team') or '').strip().lower()
        a = (m_data.get('away_team') or '').strip().lower()
        d = (m_data.get('date') or '').strip()
        sig = f"{d} {h} {a}"

        existing_idx = None
        if sig in sig_map:
            existing_idx = sig_map[sig]
        elif (h, a) in team_pair_map:
            for cand_idx in team_pair_map[(h, a)]:
                cand_d = (games[cand_idx].get('date') or '').strip()
                if cand_d == "Unknown" or cand_d == d:
                    existing_idx = cand_idx
                    break

        if existing_idx is not None:
            games[existing_idx] = m_data
            updated_count += 1
            print(f"      [+] Backfilled assists: {m_data.get('home_team')} vs {m_data.get('away_team')}")
        else:
            games.append(m_data)
            sig_map[sig] = len(games) - 1
            new_count += 1
            print(f"      [+] Added new match with assists: {m_data.get('home_team')} vs {m_data.get('away_team')}")

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
    print(f"  Skipped (had ast):    {already_have_count}")
    print(f"  Saved to:             {DATA_FILE}")
    print("=" * 70)

if __name__ == "__main__":
    main()
