"""
core/live_match_center.py
=========================
Live Match Center Client (API-Powered with Offline Fallback)

Restores live API-Basketball standings, H2H, and recent form splits
using the 7,500 daily Pro tier.
"""

import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv

from core.offline_match_center import compile_offline_match_center

load_dotenv()

API_KEY = os.getenv("API_BASKETBALL_KEY", "")
API_URL = "https://v1.basketball.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "cache", "match_center")


def _get_cache(cache_name):
    os.makedirs(CACHE_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(CACHE_DIR, f"{cache_name}_{today_str}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None


def _set_cache(cache_name, data):
    os.makedirs(CACHE_DIR, exist_ok=True)
    today_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(CACHE_DIR, f"{cache_name}_{today_str}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


def fetch_live_standings(league_id, season):
    """Fetch official standings table from API-Basketball for a league and season."""
    if not API_KEY or not league_id or not season:
        return []

    cache_key = f"standings_{league_id}_{season}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{API_URL}/standings"
    try:
        r = requests.get(url, headers=HEADERS, params={"league": league_id, "season": season}, timeout=15)
        if r.status_code == 200:
            resp = r.json().get("response", [])
            if resp:
                _set_cache(cache_key, resp)
                return resp
            # Try single year if split year failed (e.g. '2026' instead of '2026-2027')
            s_short = str(season).split("-")[0]
            if s_short != str(season):
                r2 = requests.get(url, headers=HEADERS, params={"league": league_id, "season": s_short}, timeout=15)
                if r2.status_code == 200:
                    resp2 = r2.json().get("response", [])
                    if resp2:
                        _set_cache(cache_key, resp2)
                        return resp2
    except Exception:
        pass

    return []


def fetch_live_league_games(league_id, season):
    """Fetch all finished games in the season for this league to extract H2H and recent form."""
    if not API_KEY or not league_id or not season:
        return []

    cache_key = f"games_{league_id}_{season}"
    cached = _get_cache(cache_key)
    if cached is not None:
        return cached

    url = f"{API_URL}/games"
    try:
        r = requests.get(url, headers=HEADERS, params={"league": league_id, "season": season}, timeout=20)
        if r.status_code == 200:
            resp = r.json().get("response", [])
            finished = [
                g for g in resp
                if g.get("status", {}).get("short") in ("FT", "AOT")
                and g.get("scores", {}).get("home", {}).get("total") is not None
                and g.get("scores", {}).get("away", {}).get("total") is not None
            ]
            # Sort newest first
            finished.sort(key=lambda x: str(x.get("date", "")), reverse=True)
            _set_cache(cache_key, finished)
            return finished
        # Try short season string
        s_short = str(season).split("-")[0]
        if s_short != str(season):
            r2 = requests.get(url, headers=HEADERS, params={"league": league_id, "season": s_short}, timeout=20)
            if r2.status_code == 200:
                resp2 = r2.json().get("response", [])
                finished2 = [
                    g for g in resp2
                    if g.get("status", {}).get("short") in ("FT", "AOT")
                    and g.get("scores", {}).get("home", {}).get("total") is not None
                    and g.get("scores", {}).get("away", {}).get("total") is not None
                ]
                finished2.sort(key=lambda x: str(x.get("date", "")), reverse=True)
                _set_cache(cache_key, finished2)
                return finished2
    except Exception:
        pass

    return []


def build_live_match_center(league_id, league_name, season, home_team, away_team, home_id=None, away_id=None, ref_date=None):
    """
    Build complete match center (Standings, H2H, and recent form) using live API data.
    Gracefully falls back to offline match center if live data is empty.
    """
    standings = fetch_live_standings(league_id, season)
    league_games = fetch_live_league_games(league_id, season)

    if not standings and not league_games:
        # Fall back completely to offline database
        return compile_offline_match_center(league_id, league_name, home_team, away_team, ref_date=ref_date)

    # 1. H2H Extraction
    h2h = []
    h_lower = home_team.lower().strip()
    a_lower = away_team.lower().strip()

    for g in league_games:
        g_hid = g.get("teams", {}).get("home", {}).get("id")
        g_aid = g.get("teams", {}).get("away", {}).get("id")
        g_hname = g.get("teams", {}).get("home", {}).get("name", "").lower().strip()
        g_aname = g.get("teams", {}).get("away", {}).get("name", "").lower().strip()

        id_match = (home_id and away_id and ((g_hid == home_id and g_aid == away_id) or (g_hid == away_id and g_aid == home_id)))
        name_match = ((g_hname == h_lower and g_aname == a_lower) or (g_hname == a_lower and g_aname == h_lower))

        if id_match or name_match:
            h2h.append({
                "date": g.get("date", "")[:10],
                "teams": {
                    "home": {"name": g.get("teams", {}).get("home", {}).get("name"), "winner": None},
                    "away": {"name": g.get("teams", {}).get("away", {}).get("name"), "winner": None}
                },
                "scores": {
                    "home": {"total": g.get("scores", {}).get("home", {}).get("total")},
                    "away": {"total": g.get("scores", {}).get("away", {}).get("total")}
                }
            })
            if len(h2h) >= 5:
                break

    # 2. Recent Form Extraction
    def extract_recent(target_id, target_name):
        res = []
        t_lower = target_name.lower().strip()
        for g in league_games:
            g_hid = g.get("teams", {}).get("home", {}).get("id")
            g_aid = g.get("teams", {}).get("away", {}).get("id")
            g_hname = g.get("teams", {}).get("home", {}).get("name", "").lower().strip()
            g_aname = g.get("teams", {}).get("away", {}).get("name", "").lower().strip()

            is_home = (target_id and g_hid == target_id) or (target_name and (t_lower == g_hname or t_lower in g_hname))
            is_away = (target_id and g_aid == target_id) or (target_name and (t_lower == g_aname or t_lower in g_aname))

            if is_home or is_away:
                hs = g.get("scores", {}).get("home", {}).get("total", 0)
                as_ = g.get("scores", {}).get("away", {}).get("total", 0)
                h_winner = (hs > as_)
                a_winner = (as_ > hs)
                res.append({
                    "date": g.get("date", "")[:10],
                    "teams": {
                        "home": {"name": g.get("teams", {}).get("home", {}).get("name"), "winner": h_winner},
                        "away": {"name": g.get("teams", {}).get("away", {}).get("name"), "winner": a_winner}
                    },
                    "scores": {
                        "home": {"total": hs},
                        "away": {"total": as_}
                    }
                })
                if len(res) >= 5:
                    break
        return res

    recentH = extract_recent(home_id, home_team)
    recentA = extract_recent(away_id, away_team)

    # If recent form or H2H was empty from current season, blend with offline fallback
    if not recentH or not recentA or not standings:
        offline = compile_offline_match_center(league_id, league_name, home_team, away_team, ref_date=ref_date)
        if not recentH:
            recentH = offline.get("recentH", [])
        if not recentA:
            recentA = offline.get("recentA", [])
        if not h2h:
            h2h = offline.get("h2h", [])
        if not standings:
            standings = offline.get("full_standings", [])

    return {
        "h2h": h2h,
        "recentH": recentH,
        "recentA": recentA,
        "full_standings": standings,
        "statsH": {},
        "statsA": {}
    }
