import os
import json
import glob
from collections import defaultdict
from datetime import datetime

# Season cutoff logic matching generate_advanced_metrics.py (TEAM STATS)
SUMMER_LEAGUE_IDS = {"13", "66", "76", "222", "207", "208", "209", "210", "211", "212", "213", "214", "215", "216"}

def get_season_cutoff(league_id, ref_date=None):
    """
    Exact same season cutoff logic used by TEAM STATS in generate_advanced_metrics.py:
    - Summer leagues (WNBA, NBL1, CEBL): runs Jan 1 - Dec 31 of current year.
    - Global winter leagues: runs Aug 1 to May/June across year boundary.
      If current month >= 8 (Aug-Dec), season started Aug 1 of this year.
      If current month < 8 (Jan-Jul), season started Aug 1 of previous year.
    """
    if ref_date is None:
        ref_date = datetime.now()
    elif isinstance(ref_date, str):
        try:
            ref_date = datetime.strptime(ref_date[:10], "%Y-%m-%d")
        except Exception:
            ref_date = datetime.now()
            
    cur_year = ref_date.year
    cur_month = ref_date.month
    
    if str(league_id) in SUMMER_LEAGUE_IDS:
        return f"{cur_year}-01-01"
    if cur_month >= 8:
        return f"{cur_year}-08-01"
    return f"{cur_year - 1}-08-01"


def _parse_match_date(date_str, ref_year=None):
    """
    Robustly parse a match date string into a comparable ISO string (YYYY-MM-DD).
    Handles:
      - ISO format:   '2026-03-21'
      - Proballers:   'Feb 6, 2026', 'Oct 7, 2025'
      - Flashscore:   '28.09.2026 14:00', '28.09. 14:00'
    Returns the ISO string, or '' on failure.
    """
    if not date_str:
        return ''
    s = str(date_str).strip()
    # Already ISO
    if len(s) >= 10 and s[4] == '-' and s[7] == '-':
        return s[:10]
    # Try human-readable formats used by Proballers / standard
    for fmt in ('%b %d, %Y', '%B %d, %Y', '%d %b %Y', '%d/%m/%Y', '%m/%d/%Y', '%d.%m.%Y', '%d.%m.%Y %H:%M'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    # Flashscore 'DD.MM. HH:MM' or 'DD.MM.'
    if '.' in s:
        parts = s.split()[0].rstrip('.').split('.')
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            day, month = int(parts[0]), int(parts[1])
            year = ref_year or datetime.now().year
            try:
                candidate = datetime(year, month, day)
                now_midnight = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                if candidate >= now_midnight:
                    candidate = datetime(year - 1, month, day)
                return candidate.strftime('%Y-%m-%d')
            except Exception:
                pass
    return ''

def _find_league_files(league_id, league_name=None):
    """
    Identifies all localized JSON databases for a league, 
    borrowing the robust slug-mapping logic from generate_advanced_metrics.py
    """
    map_file = "data/league_slug_map.json"
    target_slug = None
    
    if os.path.exists(map_file):
        with open(map_file, encoding="utf-8") as f:
            slug_map = json.load(f)
            # Reverse lookup the slug based on league_id
            for slug, l_id in slug_map.items():
                if int(l_id) == int(league_id):
                    target_slug = slug
                    break
                    
    files_to_check = []
    if target_slug:
        files_to_check.append(f"data/historical/proballers_{target_slug}.json")
        files_to_check.append(f"data/historical/flashscore_{target_slug}.json")
        files_to_check.append(f"data/historical/proballers_{target_slug.replace('_', '-')}.json")
        files_to_check.append(f"data/historical/flashscore_{target_slug.replace('_', '-')}.json")
        
    # Also check the raw API backup files
    files_to_check.append(f"data/historical/api_basketball_{league_id}.json")
    
    existing = []
    for f in dict.fromkeys(files_to_check):
        if os.path.exists(f):
            existing.append(f)
            
    return existing

def _find_league_file(league_id, league_name=None):
    """Backwards-compatible single file lookup."""
    files = _find_league_files(league_id, league_name)
    return files[0] if files else None

def _load_matches(file_path):
    try:
        with open(file_path, encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            if "games" in data: return data["games"]
            if "matches" in data: return data["matches"]
            if "response" in data: return data["response"]
    except Exception:
        pass
    return []

def get_h2h(matches, team1, team2):
    """ Extract historical Head-to-Head from offline chronological arrays """
    h2h = []
    t1 = str(team1).lower()
    t2 = str(team2).lower()
    
    for m in matches:
        ht = str(m.get('home_team', '')).lower()
        at = str(m.get('away_team', '')).lower()
        
        match_t1_h = (t1 in ht) or (ht in t1 and len(ht) >= 4)
        match_t1_a = (t1 in at) or (at in t1 and len(at) >= 4)
        match_t2_h = (t2 in ht) or (ht in t2 and len(ht) >= 4)
        match_t2_a = (t2 in at) or (at in t2 and len(at) >= 4)
        
        if (match_t1_h and match_t2_a) or (match_t2_h and match_t1_a):
            h2h.append({
                "date": m.get("date", ""),
                "teams": {
                    "home": {"name": m.get("home_team")},
                    "away": {"name": m.get("away_team")}
                },
                "scores": {
                    "home": {"total": m.get("home_score")},
                    "away": {"total": m.get("away_score")}
                }
            })
            if len(h2h) >= 5:
                break
    return h2h

def get_recent_form(matches, team):
    """ Extract Recent Form for a specific team """
    recent = []
    t = str(team).lower()
    
    for m in matches:
        ht = str(m.get('home_team', '')).lower()
        at = str(m.get('away_team', '')).lower()
        
        match_h = (t in ht) or (ht in t and len(ht) >= 4)
        match_a = (t in at) or (at in t and len(at) >= 4)
        
        if match_h or match_a:
            is_home = match_h
            hs = m.get("home_score", 0)
            as_ = m.get("away_score", 0)
            
            h_winner = True if hs > as_ else False if hs < as_ else None
            a_winner = True if as_ > hs else False if as_ < hs else None
            
            recent.append({
                "date": m.get("date", ""),
                "teams": {
                    "home": {"name": m.get("home_team"), "winner": h_winner},
                    "away": {"name": m.get("away_team"), "winner": a_winner}
                },
                "scores": {
                    "home": {"total": hs},
                    "away": {"total": as_}
                }
            })
            if len(recent) >= 5:
                break
    return recent

def calculate_standings(matches, league_id=None, ref_date=None):
    """
    Calculate a standings table based on W-L tallies.
    Filtered to the current season cutoff (same logic as TEAM STATS in generate_advanced_metrics.py)
    so that the P/W/L columns do not include previous-season games.
    """
    season_cutoff = ''
    if league_id is not None:
        season_cutoff = get_season_cutoff(league_id, ref_date)

    def _tally(match_list):
        standings = {}
        for m in match_list:
            ht = m.get('home_team')
            at = m.get('away_team')
            hs = m.get('home_score', 0)
            as_ = m.get('away_score', 0)
            if not ht or not at:
                continue
            
            for t in [ht, at]:
                if t not in standings:
                    standings[t] = {'w': 0, 'l': 0, 'pf': 0, 'pa': 0, 'form': []}
                    
            if hs > as_:
                standings[ht]['w'] += 1
                standings[at]['l'] += 1
                if len(standings[ht]['form']) < 5: standings[ht]['form'].append('W')
                if len(standings[at]['form']) < 5: standings[at]['form'].append('L')
            elif as_ > hs:
                standings[at]['w'] += 1
                standings[ht]['l'] += 1
                if len(standings[ht]['form']) < 5: standings[ht]['form'].append('L')
                if len(standings[at]['form']) < 5: standings[at]['form'].append('W')
                
            standings[ht]['pf'] += hs
            standings[ht]['pa'] += as_
            standings[at]['pf'] += as_
            standings[at]['pa'] += hs
        return standings

    # First attempt: filter by current season cutoff
    if season_cutoff:
        filtered = [
            m for m in matches
            if _parse_match_date(m.get('date', '')) >= season_cutoff
        ]
    else:
        filtered = matches

    standings = _tally(filtered)

    # Fallback: if league has not tipped off yet in current season (0 games),
    # fallback to all matches so standings tab doesn't show completely blank
    if not standings and season_cutoff and matches:
        standings = _tally(matches)

    s_list = []
    for team_name, st in standings.items():
        played = st['w'] + st['l']
        if played == 0:
            continue
        win_pct = st['w'] / played
        s_list.append({
            "team_name": team_name,
            "played": played,
            "w": st['w'],
            "l": st['l'],
            "win_pct": win_pct,
            "pf": st['pf'],
            "pa": st['pa'],
            "form": "".join(st['form'])
        })
    s_list.sort(key=lambda x: (x['win_pct'], x['w'], x['pf'] - x['pa']), reverse=True)

    formatted = []
    for i, st in enumerate(s_list):
        formatted.append({
            "position": i + 1,
            "team": {"name": st["team_name"], "logo": ""},
            "games": {
                "played": st["played"],
                "win": {"total": st["w"], "percentage": f"{st['win_pct']:.3f}"},
                "lose": {"total": st["l"]}
            },
            "points": {
                "for": st["pf"],
                "against": st["pa"]
            },
            "form": st["form"]
        })
    return [formatted] if formatted else []

def compile_offline_match_center(league_id, league_name, home_team, away_team, ref_date=None):
    """ Entry point for run_basketball_daily.py to execute the zero-cost build """
    file_paths = _find_league_files(league_id, league_name)
    all_raw_matches = []
    for fp in file_paths:
        all_raw_matches.extend(_load_matches(fp))

    # Also ingest recent completed games from daily cache files (data/api_basketball_today_*.json)
    d_files = sorted(glob.glob("data/api_basketball_today_*.json"), reverse=True)
    for df in d_files:
        try:
            with open(df, encoding="utf-8") as fp:
                day_data = json.load(fp)
            for entry in day_data.get("leagues_summary", []):
                if entry.get("league_id") == league_id:
                    for g in entry.get("games", []):
                        hs = g.get("home_score")
                        as_ = g.get("away_score")
                        if hs is not None and as_ is not None and hs != "" and as_ != "":
                            all_raw_matches.append({
                                "date": str(g.get("time", "") or day_data.get("date", ""))[:10],
                                "home_team": g.get("home", ""),
                                "away_team": g.get("away", ""),
                                "home_score": int(hs),
                                "away_score": int(as_),
                            })
        except Exception:
            pass

    if not all_raw_matches:
        return {"h2h": [], "recentH": [], "recentA": [], "full_standings": [], "statsH": {}, "statsA": {}}

    # Semantic deduplication & date parsing
    deduped = {}
    for m in all_raw_matches:
        ht = m.get("home_team")
        at = m.get("away_team")
        hs = m.get("home_score")
        as_ = m.get("away_score")
        if not ht or not at or hs is None or as_ is None:
            continue
        try:
            hs = int(hs)
            as_ = int(as_)
        except (ValueError, TypeError):
            continue
        iso_date = _parse_match_date(m.get("date", ""))
        key = (iso_date or m.get("date", ""), str(ht).lower().strip(), str(at).lower().strip())
        m_clean = dict(m)
        m_clean["_iso_date"] = iso_date
        m_clean["home_score"] = hs
        m_clean["away_score"] = as_
        if key not in deduped:
            deduped[key] = m_clean

    matches = list(deduped.values())
    # Sort descending by date so recent form and H2H get newest matches first!
    matches.sort(key=lambda x: str(x.get("_iso_date", "")), reverse=True)

    return {
        "h2h": get_h2h(matches, home_team, away_team),
        "recentH": get_recent_form(matches, home_team),
        "recentA": get_recent_form(matches, away_team),
        "full_standings": calculate_standings(matches, league_id=league_id, ref_date=ref_date),
        "statsH": {}, 
        "statsA": {}
    }
