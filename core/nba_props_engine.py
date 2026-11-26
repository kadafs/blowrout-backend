"""
core/nba_props_engine.py
========================
Quantitative NBA Player Props Engine powered by API-Basketball.

Features:
1. Ingests and caches player-level boxscores from API-Basketball.
2. Computes rolling player efficiency profiles:
   - Points Per Minute (PPM)
   - Rebounds Per Minute (RPM)
   - Assists Per Minute (APM)
   - Threepoints Per Minute (3PM/M)
   - Starter vs Bench splits & minutes projections
3. Zero-lookahead filtering (max_date parameter prevents future leakage).
4. Dual distribution modeling:
   - Poisson CDF for discrete event counts (Rebounds, Assists, 3PM)
   - Gaussian Normal CDF for high-volume stats (Points, Points+Assists)
5. Multi-pass token & alias player name matching (handles European Last/First order,
   abbreviated names, HTML entities, and hyphens).
6. Expected Value (EV%) and Edge% calculation against live bookmaker lines.
7. Automated grading against official boxscores.
"""

import os
import sys
import json
import math
import html
import re
import requests
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "data", "nba")
BOXSCORES_FILE = os.path.join(CACHE_DIR, "nba_boxscores_cache.json")

def get_api_key():
    key = os.getenv("API_BASKETBALL_KEY")
    if not key:
        env_file = os.path.join(BASE_DIR, ".env")
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    if "API_BASKETBALL_KEY" in line and "=" in line:
                        key = line.split("=", 1)[1].strip()
                        break
    return key

def parse_minutes(min_str):
    """Converts '36:17' to float 36.28 minutes."""
    if not min_str:
        return 0.0
    try:
        if ":" in str(min_str):
            parts = str(min_str).split(":")
            return float(parts[0]) + float(parts[1]) / 60.0
        return float(min_str)
    except Exception:
        return 0.0

def normalize_name(name):
    """Normalizes player names by unescaping entities, stripping punctuation, and lowercasing."""
    if not name:
        return ""
    name = html.unescape(name).lower().strip()
    name = re.sub(r"['\.\-\(\)]", " ", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name

def load_boxscores_cache():
    if os.path.exists(BOXSCORES_FILE):
        try:
            with open(BOXSCORES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_boxscores_cache(cache):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(BOXSCORES_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)

def fetch_game_boxscore(game_id, api_key):
    """Fetches boxscore for a single NBA game from API-Basketball."""
    url = f"https://v1.basketball.api-sports.io/games/statistics/players?id={game_id}"
    headers = {"x-apisports-key": api_key}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            return data.get("response", [])
    except Exception as e:
        print(f"  [!] Error fetching boxscore {game_id}: {e}")
    return []

def build_player_profiles(boxscores_cache, max_date=None):
    """
    Builds rolling per-minute and per-game averages for every player.
    If max_date is specified (e.g. '2026-11-26'), strictly excludes games on or after that date.
    """
    player_logs = {}
    
    for gid, data in boxscores_cache.items():
        player_entries = data.get("players", []) if isinstance(data, dict) else data
        gdate = data.get("meta", {}).get("date") if isinstance(data, dict) else None
        
        # Zero lookahead check
        if max_date and gdate and gdate >= max_date:
            continue
            
        for p in player_entries:
            pinfo = p.get("player", {})
            pid = pinfo.get("id")
            pname = pinfo.get("name")
            if not pid or not pname:
                continue
                
            mins = parse_minutes(p.get("minutes"))
            if mins < 3.0:  # Skip garbage time entries
                continue
                
            pts = float(p.get("points") or 0.0)
            ast = float(p.get("assists") or 0.0)
            reb_dict = p.get("rebounds") or {}
            reb = float(reb_dict.get("total") if isinstance(reb_dict, dict) else reb_dict or 0.0)
            tp_dict = p.get("threepoint_goals") or {}
            tp = float(tp_dict.get("total") if isinstance(tp_dict, dict) else tp_dict or 0.0)
            is_starter = (p.get("type") == "starters")
            
            if pid not in player_logs:
                player_logs[pid] = {
                    "id": pid,
                    "name": pname,
                    "clean_name": normalize_name(pname),
                    "team_id": p.get("team", {}).get("id"),
                    "games": []
                }
                
            player_logs[pid]["games"].append({
                "game_id": gid,
                "date": gdate,
                "minutes": mins,
                "points": pts,
                "rebounds": reb,
                "assists": ast,
                "threes": tp,
                "is_starter": is_starter,
                "ppm": pts / mins if mins > 0 else 0,
                "rpm": reb / mins if mins > 0 else 0,
                "apm": ast / mins if mins > 0 else 0,
                "tpm": tp / mins if mins > 0 else 0,
            })
            
    # Compute aggregate metrics
    profiles = {}
    for pid, data in player_logs.items():
        glist = data["games"]
        n_games = len(glist)
        if n_games < 2:
            continue
            
        recent = glist[-5:]
        tot_mins = sum(g["minutes"] for g in glist)
        tot_pts = sum(g["points"] for g in glist)
        tot_reb = sum(g["rebounds"] for g in glist)
        tot_ast = sum(g["assists"] for g in glist)
        tot_threes = sum(g["threes"] for g in glist)
        
        r_mins = sum(g["minutes"] for g in recent)
        r_pts = sum(g["points"] for g in recent)
        r_reb = sum(g["rebounds"] for g in recent)
        r_ast = sum(g["assists"] for g in recent)
        r_threes = sum(g["threes"] for g in recent)
        
        starter_count = sum(1 for g in glist if g["is_starter"])
        
        profiles[pid] = {
            "id": pid,
            "name": data["name"],
            "clean_name": data["clean_name"],
            "team_id": data["team_id"],
            "games_played": n_games,
            "starter_pct": round(starter_count / n_games * 100.0, 1),
            "season": {
                "avg_minutes": round(tot_mins / n_games, 1),
                "avg_points": round(tot_pts / n_games, 1),
                "avg_rebounds": round(tot_reb / n_games, 1),
                "avg_assists": round(tot_ast / n_games, 1),
                "avg_threes": round(tot_threes / n_games, 1),
                "ppm": round(tot_pts / tot_mins, 4) if tot_mins > 0 else 0,
                "rpm": round(tot_reb / tot_mins, 4) if tot_mins > 0 else 0,
                "apm": round(tot_ast / tot_mins, 4) if tot_mins > 0 else 0,
                "tpm": round(tot_threes / tot_mins, 4) if tot_mins > 0 else 0,
            },
            "recent5": {
                "avg_minutes": round(r_mins / len(recent), 1),
                "avg_points": round(r_pts / len(recent), 1),
                "avg_rebounds": round(r_reb / len(recent), 1),
                "avg_assists": round(r_ast / len(recent), 1),
                "avg_threes": round(r_threes / len(recent), 1),
                "ppm": round(r_pts / r_mins, 4) if r_mins > 0 else 0,
                "rpm": round(r_reb / r_mins, 4) if r_mins > 0 else 0,
                "apm": round(r_ast / r_mins, 4) if r_mins > 0 else 0,
                "tpm": round(r_threes / r_mins, 4) if r_mins > 0 else 0,
            }
        }
        
    return profiles

def match_player_name(query_name, profiles):
    """
    Robust 3-pass player name matcher:
    1. Exact token set match (order-independent, e.g. 'Josh Giddey' == 'Giddey Josh')
    2. Exact reversed 2-word string
    3. Abbreviated single-character initial match (e.g. 'Matas Buzelis' == 'M. Buzelis')
    """
    norm_q = normalize_name(query_name)
    tokens_q = tuple(sorted(norm_q.split()))
    
    # Pass 1: exact token set
    for pid, p in profiles.items():
        tokens_p = tuple(sorted(p["clean_name"].split()))
        if tokens_q == tokens_p:
            return p
            
    # Pass 2: exact reversed
    parts_q = norm_q.split()
    for pid, p in profiles.items():
        parts_p = p["clean_name"].split()
        if len(parts_q) == 2 and len(parts_p) == 2:
            if parts_q[0] == parts_p[1] and parts_q[1] == parts_p[0]:
                return p
                
    # Pass 3: Initial match ONLY when single char initial exists
    if len(parts_q) >= 2:
        q_first, q_last = parts_q[0], parts_q[-1]
        for pid, p in profiles.items():
            parts_p = p["clean_name"].split()
            if len(parts_p) >= 2:
                if len(parts_p[0]) == 1 and parts_p[-1] == q_last:
                    if parts_p[0] == q_first[0]:
                        return p
                elif len(parts_p[-1]) == 1 and parts_p[0] == q_last:
                    if parts_p[-1] == q_first[0]:
                        return p
                        
    return None

def poisson_prob_over(lam, line):
    """Computes exact P(X > line) using Poisson CDF."""
    k_max = int(math.floor(line))
    prob_le = 0.0
    for k in range(0, k_max + 1):
        prob_le += (lam ** k * math.exp(-lam)) / math.factorial(k)
    return max(0.001, min(0.999, 1.0 - prob_le))

def normal_prob_over(mean, std_dev, line):
    """Computes P(X > line) using Gaussian CDF."""
    if std_dev <= 0:
        return 1.0 if mean > line else 0.0
    z = (line - mean) / std_dev
    return 0.5 * (1.0 - math.erf(z / math.sqrt(2.0)))

def evaluate_prop_opportunity(player_profile, prop_type, line, odds, direction="OVER"):
    """
    Evaluates EV and Win Probability for an individual player prop.
    """
    p_rec = player_profile["recent5"]
    p_sea = player_profile["season"]
    
    # Expected minutes projection (65% recent + 35% season)
    proj_mins = 0.65 * p_rec["avg_minutes"] + 0.35 * p_sea["avg_minutes"]
    
    if prop_type in ["POINTS", "PTS"]:
        proj_val = proj_mins * (0.60 * p_rec["ppm"] + 0.40 * p_sea["ppm"])
        std = max(3.5, 0.28 * proj_val + 2.5)
        prob_over = normal_prob_over(proj_val, std, line)
    elif prop_type in ["REBOUNDS", "REB"]:
        proj_val = proj_mins * (0.60 * p_rec["rpm"] + 0.40 * p_sea["rpm"])
        prob_over = poisson_prob_over(max(0.5, proj_val), line)
    elif prop_type in ["ASSISTS", "AST"]:
        proj_val = proj_mins * (0.60 * p_rec["apm"] + 0.40 * p_sea["apm"])
        prob_over = poisson_prob_over(max(0.5, proj_val), line)
    elif prop_type in ["THREES", "3PM"]:
        proj_val = proj_mins * (0.60 * p_rec["tpm"] + 0.40 * p_sea["tpm"])
        prob_over = poisson_prob_over(max(0.5, proj_val), line)
    elif prop_type in ["POINTS_ASSISTS", "PA"]:
        proj_ppm = 0.60 * p_rec["ppm"] + 0.40 * p_sea["ppm"]
        proj_apm = 0.60 * p_rec["apm"] + 0.40 * p_sea["apm"]
        proj_val = proj_mins * (proj_ppm + proj_apm)
        std = max(4.0, 0.28 * proj_val + 3.0)
        prob_over = normal_prob_over(proj_val, std, line)
    else:
        return None
        
    win_prob = prob_over if direction == "OVER" else (1.0 - prob_over)
    implied_prob = 1.0 / odds if odds > 1.0 else 0.5
    edge = win_prob - implied_prob
    ev = (win_prob * odds) - 1.0
    
    return {
        "player_id": player_profile["id"],
        "player": player_profile["name"],
        "prop_type": prop_type,
        "line": line,
        "direction": direction,
        "odds": odds,
        "projected_value": round(proj_val, 1),
        "projected_minutes": round(proj_mins, 1),
        "win_probability": round(win_prob * 100.0, 1),
        "implied_probability": round(implied_prob * 100.0, 1),
        "edge_pct": round(edge * 100.0, 1),
        "ev_pct": round(ev * 100.0, 1),
        "is_value": (edge >= 0.05 and ev >= 0.05),
        "is_high_conviction": (edge >= 0.08 and ev >= 0.10)
    }
