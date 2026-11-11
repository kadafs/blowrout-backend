import sys
import os
import json
import time
from datetime import datetime
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

try:
    from playwright_stealth import Stealth
    HAS_STEALTH = True
except ImportError:
    print("Warning: playwright_stealth not installed. Cloudflare may block execution.")
    HAS_STEALTH = False

SESSION_FILE = "data/proballers_session.json"

def get_proballers_session(cf_clearance=None, user_agent=None):
    if not cf_clearance:
        cf_clearance = os.getenv("PROBALLERS_CF_CLEARANCE")
    if not user_agent:
        user_agent = os.getenv("PROBALLERS_USER_AGENT")

    if (not cf_clearance or not user_agent) and os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if not cf_clearance:
                    cf_clearance = data.get("cf_clearance")
                if not user_agent:
                    user_agent = data.get("user_agent")
        except Exception:
            pass

    if not user_agent:
        user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/154.0.0.0 Safari/537.36"

    if cf_clearance:
        try:
            from curl_cffi import requests
            s = requests.Session(impersonate="chrome131")
            s.headers.update({
                "user-agent": user_agent,
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                "accept-language": "en-US,en;q=0.9",
                "referer": "https://www.proballers.com/",
            })
            s.cookies.set("cf_clearance", cf_clearance, domain=".proballers.com")
            return s
        except ImportError:
            print("  [!] curl_cffi not installed. Falling back to Playwright.")
            return None
    return None

def parse_boxscore(html):
    """
    Parses the raw Proballers Box Score HTML and extracts Four Factors and player stats.
    Supports both the modern 6-table layout and the legacy 3-table layout.
    Returns: {"date": ..., "home_team": ..., "away_team": ..., "home_score": ..., "away_score": ..., "stats": {...}}
    """
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all('table')
    if len(tables) < 3:
        return None

    title = soup.find('title').text if soup.find('title') else ""
    date_str = title.split(' - ')[1] if ' - ' in title else "Unknown"

    # --- Modern Layout (6+ tables): [0] Quarters, [1] Team Totals, [4] Home Players, [5] Away Players ---
    if len(tables) >= 6:
        q_rows = tables[0].find_all('tr')
        h_name = q_rows[1].find_all(['td', 'th'])[0].text.strip() if len(q_rows) >= 3 else "Home"
        a_name = q_rows[2].find_all(['td', 'th'])[0].text.strip() if len(q_rows) >= 3 else "Away"

        t1_rows = tables[1].find_all('tr')
        if len(t1_rows) >= 3:
            t1_headers = [c.text.strip().upper() for c in t1_rows[0].find_all(['td', 'th'])]
            
            def parse_team_modern(row, team_name, player_table):
                cells = [c.text.strip() for c in row.find_all(['td', 'th'])]
                h_map = {h: cells[i] for i, h in enumerate(t1_headers) if i < len(cells)}
                
                def get_int(key, default=0):
                    val = h_map.get(key, "").replace("%", "").strip()
                    try:
                        return int(val)
                    except ValueError:
                        return default

                active_players = []
                p_rows = player_table.find_all('tr')
                for pr in p_rows[1:-1]:
                    p_cells = [c.text.strip() for c in pr.find_all(['td', 'th'])]
                    if len(p_cells) < 5: continue
                    p_name = p_cells[0]
                    if not p_name or p_name.lower() in ["totals", "team", team_name.lower()]: continue
                    pts_str = p_cells[1]
                    try:
                        pts = int(pts_str)
                    except (ValueError, TypeError):
                        pts = 0
                    min_str = p_cells[4].upper()
                    if min_str not in ["", "DNP", "00:00", "0", "0:00"] or pts > 0:
                        active_players.append({"name": p_name, "pts": pts})

                return {
                    "team_name": team_name,
                    "players": active_players,
                    "points": get_int("PTS"),
                    "FGA": get_int("FGA"),
                    "FTA": get_int("FTA"),
                    "ORB": get_int("OR"),
                    "DRB": get_int("DR"),
                    "TRB": get_int("REB"),
                    "AST": get_int("AST"),
                    "TOV": get_int("TO"),
                    "STL": get_int("STL"),
                    "BLK": get_int("BLK")
                }

            h_data = parse_team_modern(t1_rows[1], h_name, tables[4])
            a_data = parse_team_modern(t1_rows[2], a_name, tables[5])

            if h_data and a_data:
                return {
                    "date": date_str,
                    "home_team": h_data["team_name"],
                    "away_team": a_data["team_name"],
                    "home_score": h_data["points"],
                    "away_score": a_data["points"],
                    "stats": {
                        "home": h_data,
                        "away": a_data
                    }
                }

    # --- Legacy Layout (3 tables): [0] Quarters, [1] Home Team, [2] Away Team ---
    def safe_int(val, default=0):
        """Safely converts a cell value to int, returning default for '-', '', or non-numeric."""
        v = str(val).strip().replace('%', '')
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    def extract_team_totals(table):
        rows = table.find_all('tr')
        if len(rows) < 2: return None
        
        active_players = []
        for r in rows[1:-1]:
            player_cells = r.find_all('td')
            if len(player_cells) < 18: continue
            
            name = player_cells[0].text.strip()
            if not name or name.lower() == "totals" or name.lower() == "team": continue
            
            pts_str = player_cells[1].text.strip()
            pts = safe_int(pts_str)
            
            min_str = player_cells[2].text.strip().upper()
            if min_str not in ["", "DNP", "00:00", "0", "0:00"] or pts > 0:
                active_players.append({"name": name, "pts": pts})
        
        totals_row = rows[-1]
        cells = [td.text.strip() for td in totals_row.find_all('td')]
        if len(cells) < 18: return None
        
        # FGA = made+attempted for 2s + 3s; guard against '-' cells
        twos = cells[5].split('-')
        threes = cells[6].split('-')
        fga = (safe_int(twos[1]) + safe_int(threes[1])) if (len(twos) == 2 and len(threes) == 2) else 0
        
        fts = cells[8].split('-')
        fta = safe_int(fts[1]) if len(fts) == 2 else 0
        
        return {
            "team_name": cells[0],
            "players": active_players,
            "points": safe_int(cells[1]),
            "FGA": fga,
            "FTA": fta,
            "ORB": safe_int(cells[10]),
            "DRB": safe_int(cells[11]),
            "TRB": safe_int(cells[12]),
            "AST": safe_int(cells[13]),
            "TOV": safe_int(cells[14]),
            "STL": safe_int(cells[15]),
            "BLK": safe_int(cells[16])
        }
        
    h_data = extract_team_totals(tables[1])
    a_data = extract_team_totals(tables[2])
    
    if not h_data or not a_data:
        return None
        
    return {
        "date": date_str,
        "home_team": h_data["team_name"],
        "away_team": a_data["team_name"],
        "home_score": h_data["points"],
        "away_score": a_data["points"],
        "stats": {
            "home": h_data,
            "away": a_data
        }
    }

def extract_league_schedule(url, context=None, session=None):
    """
    Extracts all box score URLs from a parent Proballers League/Team Schedule page.
    Uses fast curl_cffi session if available, falls back to Playwright context.
    """
    box_urls = []
    if session:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 403 or "Just a moment..." in resp.text:
                print("  [!] Cloudflare verification challenge encountered (HTTP 403 / Turnstile).")
                print("  [!] Stored session in data/proballers_session.json has expired.")
                print("  [!] Please run: python scrape_proballers.py --refresh to solve the challenge in a browser window.")
                return []
            soup = BeautifulSoup(resp.text, 'html.parser')
            for a in soup.find_all('a', href=True):
                href = a['href']
                if '/basketball/game/' in href:
                    full_url = "https://www.proballers.com" + href if not href.startswith("http") else href
                    if full_url not in box_urls:
                        box_urls.append(full_url)
        except Exception as e:
            print(f"  [X] Failed fetching schedule with session: {e}")
            return []
    elif context:
        page = context.new_page()
        if HAS_STEALTH: Stealth().apply_stealth_sync(page)
        time.sleep(2)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(4000)
        except Exception:
            print(f"  -> Cloudflare telemetry timeout bypassed natively.")
            
        links = page.locator('a').all()
        for l in links:
            href = l.get_attribute('href')
            if href and '/basketball/game/' in href:
                full_url = "https://www.proballers.com" + href if not href.startswith("http") else href
                if full_url not in box_urls:
                    box_urls.append(full_url)
        page.close()

    box_urls.reverse()
    return box_urls

def scrape_match(url, context=None, session=None):
    if session:
        try:
            resp = session.get(url, timeout=15)
            if resp.status_code == 403 or "Just a moment..." in resp.text:
                print("      [!] Cloudflare challenge encountered during match fetch (HTTP 403).")
                return {}
            return parse_boxscore(resp.text) or {}
        except Exception as e:
            print(f"      [!] Skipping game (HTTP error): {e}")
            return {}
    elif context:
        page = context.new_page()
        if HAS_STEALTH: Stealth().apply_stealth_sync(page)
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except:
            pass
        try:
            html = page.content()
            data = parse_boxscore(html)
        except Exception as e:
            print(f"      [!] Skipping game (DOM locked/navigating): {e}")
            data = {}
        page.close()
        return data
    return {}

import argparse
import random

def run_proballers_scraper(target_url, max_games=None, cutoff_date=None, session=None):
    import re
    # Normalize URL: if pointing to root league page, append /schedule
    target_clean = target_url.strip().rstrip('/')
    if not target_clean.endswith('/schedule'):
        target_clean = f"{target_clean}/schedule"
    target_url = target_clean

    # Robust slug extraction: /league/221/g-league/schedule -> g-league
    m = re.search(r'/league/\d+/([^/]+)', target_url)
    if m:
        domain_slug = m.group(1)
    else:
        parts = target_url.strip('/').split('/')
        domain_slug = parts[-2] if parts[-1] == "schedule" and len(parts) >= 2 else parts[-1]

    out_file = f"data/historical/proballers_{domain_slug}.json"
    
    existing_data = []
    seen_sigs = set()
    has_gaps = False
    
    # Intelligent resume logic: Load existing data to append strictly new games
    if os.path.exists(out_file) and os.path.getsize(out_file) > 1024:
        try:
            with open(out_file, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
                no_player_count = 0
                for item in raw_data:
                    sig = f"{item.get('date')} {item.get('home_team')} {item.get('away_team')}"
                    seen_sigs.add(sig)
                    existing_data.append(item)
                    has_players = bool(item.get("stats", {}).get("home", {}).get("players"))
                    if not has_players:
                        no_player_count += 1
                        has_gaps = True

            print(f"  [~] Loaded {len(existing_data)} historical records ({no_player_count} without player stats — retained for score history, skipped by SDI).")
        except Exception as e:
            print(f"  [!] Failed to load existing payload: {str(e)}. Starting fresh.")

    print(f"\n===========================================================")
    print(f"  STARTING PROBALLERS SCRAPER -> {domain_slug.upper()}")
    print(f"===========================================================")

    def execute_harvest(context=None, sess=None):
        nonlocal existing_data, seen_sigs, has_gaps
        matches = extract_league_schedule(target_url, context=context, session=sess)
        print(f"  -> Extracted {len(matches)} historical payload links from DOM.")
        
        if max_games and len(matches) > max_games:
            matches = matches[:max_games]
            
        new_matches_added = 0
        import re
        for i, match_url in enumerate(matches):
            print(f"      [{i+1}/{len(matches)}] Harvesting advanced stats: {match_url.split('/')[-1]}")
            
            # Fast-path URL date check
            if cutoff_date:
                match_dt_match = re.search(r'-(\d{4}-\d{2}-\d{2})/?$', match_url)
                if match_dt_match:
                    try:
                        url_date = datetime.strptime(match_dt_match.group(1), "%Y-%m-%d").date()
                        cutoff_dt = datetime.strptime(cutoff_date, "%Y-%m-%d").date()
                        if url_date < cutoff_dt:
                            print(f"        -> [!] URL date {url_date} is older than cutoff {cutoff_date}. Stopping extraction.")
                            break
                    except Exception:
                        pass

            m_data = scrape_match(match_url, context=context, session=sess)
            if m_data:
                game_date_str = m_data.get('date', 'Unknown')
                if cutoff_date and game_date_str != "Unknown":
                    try:
                        game_dt = datetime.strptime(game_date_str.strip(), "%b %d, %Y").date()
                        cutoff_dt = datetime.strptime(cutoff_date, "%Y-%m-%d").date()
                        if game_dt < cutoff_dt:
                            print(f"        -> [!] Game date {game_date_str} is older than cutoff {cutoff_date}. Stopping extraction.")
                            break
                    except Exception:
                        pass

                sig = f"{m_data.get('date')} {m_data.get('home_team')} {m_data.get('away_team')}"
                if sig not in seen_sigs:
                    existing_data.append(m_data)
                    seen_sigs.add(sig)
                    new_matches_added += 1
                    print(f"        -> [+] Appended new data!")
                else:
                    print(f"        -> [~] Match already exists in dataset: {sig}")
                    if has_gaps:
                        print(f"        -> [!] Gap detected in historical data. Continuing scan...")
                        continue
                    else:
                        print(f"        -> [!] League up to date. Skipping remaining historical matches.")
                        break
            
            # Rate limit
            time.sleep(random.uniform(1.0, 2.5) if sess else random.uniform(2.1, 4.3))
                
        print(f"\n  [+] Mapped Mathematical Payloads (New: {new_matches_added})")
        
        if existing_data:
            os.makedirs("data/historical", exist_ok=True)
            with open(out_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, indent=2, ensure_ascii=False)
            print(f"  [+] SUCCESS: Historical [ADVANCED] payload locked -> {out_file}")
            
        return True

    if session:
        print("  [*] Utilizing fast stealth session (curl_cffi with cf_clearance).")
        return execute_harvest(sess=session)
    else:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=['--disable-blink-features=AutomationControlled']
            )
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            res = execute_harvest(context=context)
            browser.close()
            return res

def fetch_api_basketball_directly(date_str):
    """
    Standalone function to fetch ALL daily fixtures from api-basketball.com
    without touching the prediction engine logic.
    """
    from dotenv import load_dotenv
    import requests
    load_dotenv()
    
    api_key = os.getenv("API_BASKETBALL_KEY")
    if not api_key:
        print("  [X] API_BASKETBALL_KEY missing from .env")
        return []
        
    fixtures_file = f"data/api_basketball_today_{date_str}.json"
    print(f"  Fetching all raw fixtures for {date_str} directly from api-basketball.com...")
    
    try:
        r = requests.get(
            "https://v1.basketball.api-sports.io/games",
            headers={"x-apisports-key": api_key},
            params={"date": date_str},
            timeout=15,
        )
        api_data = r.json()
        
        if api_data.get("errors"):
            print(f"  [X] API Error: {api_data.get('errors')}. Will not cache empty results.")
            return []
            
        all_games = api_data.get("response", [])
        total = api_data.get("results", 0)
        
        from collections import defaultdict
        by_league = defaultdict(list)
        for game in all_games:
            league = game.get("league", {})
            lid = league.get("id")
            lname = league.get("name", "Unknown")
            country = game.get("country", {}).get("name", "")
            by_league[(lid, lname, country)].append(game)

        leagues_summary = []
        for (lid, lname, country), games in by_league.items():
            leagues_summary.append({
                "league_id": lid, 
                "league_name": lname,
                "country": country,
                "game_count": len(games)
            })

        out = {"date": date_str, "total_games": total, "leagues_summary": leagues_summary}
        os.makedirs("data", exist_ok=True)
        with open(fixtures_file, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
            
        print(f"  -> Saved {total} raw games across {len(leagues_summary)} leagues.")
        return leagues_summary
    except Exception as e:
        print(f"  [X] Direct fetch failed: {e}")
        return []

def get_daily_urls(date_str):
    """
    Reads all daily fixtures JSON to find which leagues are actively playing today.
    Only active leagues will be scraped.
    No dependency on prediction engines.
    """
    if date_str == "today" or not date_str:
        from datetime import timezone, datetime
        ET_TZ = timezone.utc
        date_str = datetime.now(ET_TZ).strftime("%Y-%m-%d")
        
    fixtures_file = f"data/api_basketball_today_{date_str}.json"
    
    if not os.path.exists(fixtures_file):
        print(f"  [!] Fixtures file not found: {fixtures_file}")
        leagues_list = fetch_api_basketball_directly(date_str)
    else:
        try:
            with open(fixtures_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                leagues_list = data.get("leagues_summary", [])
        except Exception as e:
            print(f"  [X] Failed reading fixtures file: {e}")
            leagues_list = []
            
    if not leagues_list:
        return []
        
    valid_leagues = leagues_list
    
    leagues_today = [str(l.get("league_id")) for l in valid_leagues if l.get("league_id")]
    
    urls = []
    
    # 1. Lookup via configs/leagues folder
    for lid in leagues_today:
        cfg_path = f"configs/leagues/{lid}.json"
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as cf:
                    cfg = json.load(cf)
                    url = cfg.get("proballers_url")
                    if url and url not in urls:
                        urls.append(url)
            except Exception:
                pass
                
    # 2. Legacy Method: Lookup via league_slug_map + proballers_schedule_links
    map_file = "data/league_slug_map.json"
    txt_files = ["proballers_schedule_links.txt", "proballers_priority_links.txt"]
    
    if os.path.exists(map_file):
        try:
            with open(map_file, "r", encoding="utf-8") as mf:
                slug_map = json.load(mf)
                
            for tfile in txt_files:
                if os.path.exists(tfile):
                    with open(tfile, "r", encoding="utf-8") as tf:
                        for line in tf:
                            url = line.strip()
                            if not url or url.startswith("#"): continue
                            
                            parts = url.strip("/").split("/")
                            if len(parts) >= 2:
                                slug = parts[-2]
                                api_id = slug_map.get(slug)
                                if not api_id:
                                    api_id = slug_map.get(slug.replace("-", "_"))
                                    
                                if api_id and str(api_id) in leagues_today:
                                    if url not in urls:
                                        urls.append(url)
        except Exception as e:
            print(f"  [X] Failed parsing legacy mapping: {e}")

    return urls

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proballers Advanced Metrics Mass Scraper")
    parser.add_argument("--url", type=str, help="Single schedule URL to scrape")
    parser.add_argument("--file", type=str, help="Text file containing multiple schedule URLs to batch process")
    parser.add_argument("--daily", type=str, nargs="?", const="today", help="Scrape only leagues playing on this date (YYYY-MM-DD or 'today')")
    parser.add_argument("--max", type=int, default=200, help="Max games to scrape per league (prevent timeout during sync)")
    parser.add_argument("--cutoff_date", type=str, help="Do not scrape games older than this date (YYYY-MM-DD)")
    parser.add_argument("--refresh", action="store_true", help="Launch interactive Chrome window to solve Cloudflare and refresh cf_clearance")
    parser.add_argument("--cf_clearance", type=str, help="Cloudflare clearance cookie override")
    parser.add_argument("--user_agent", type=str, help="User-Agent string override")
    
    args = parser.parse_args()

    if args.refresh:
        from refresh_proballers_session import refresh_session
        if not refresh_session():
            print("[-] Session refresh failed or was cancelled. Exiting.")
            sys.exit(1)

    session = get_proballers_session(args.cf_clearance, args.user_agent)
    
    target_urls = []
    
    if args.daily:
        print(f"\n[DAILY OPTIMIZATION] Identifying active leagues for date: {args.daily}")
        target_urls = get_daily_urls(args.daily)
        print(f"-> Found {len(target_urls)} active Proballers leagues scheduled for {args.daily if args.daily != 'today' else 'today'}\n")
        
        if not args.cutoff_date:
            from datetime import timedelta, timezone
            if args.daily == "today" or args.daily == "":
                d_obj = datetime.now(timezone.utc)
            else:
                d_obj = datetime.strptime(args.daily, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            args.cutoff_date = (d_obj - timedelta(days=14)).strftime("%Y-%m-%d")
            print(f"-> Set automatic cutoff_date to {args.cutoff_date} for daily mode.\n")
    elif args.file:
        if not os.path.exists(args.file):
            print(f"Error: File {args.file} not found.")
            sys.exit(1)
        with open(args.file, "r") as f:
            target_urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
        print(f"Found {len(target_urls)} leagues in target manifest. Commencing Mass Extraction Sequence.")
    elif args.url:
        target_urls = [args.url]
    else:
        parser.print_help()
        sys.exit(0)
        
    for idx, url in enumerate(target_urls):
        print(f"\n[BATCH ROUTINE] Extracting League {idx+1} of {len(target_urls)}: {url.split('/')[-2] if '/' in url else url}")
        run_proballers_scraper(url, max_games=args.max, cutoff_date=args.cutoff_date, session=session)
        
        if idx < len(target_urls) - 1:
            cooldown = random.uniform(3.0, 6.0) if session else random.uniform(8.5, 14.5)
            print(f"  -> Cooldown for {cooldown:.1f}s before next league...")
            time.sleep(cooldown)
