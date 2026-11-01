"""
core/ncaa_conference_resolver.py
================================
Resolves NCAA Division 1 matchups to their specific individual conference
(e.g., Big East, Big Ten, SEC, ACC) or to NCAA - Non-Conference when teams
from different conferences face each other.
"""

import json
import os
import re

_NCAA_CONFERENCES_CACHE = None

def _load_conferences_cache():
    global _NCAA_CONFERENCES_CACHE
    if _NCAA_CONFERENCES_CACHE is not None:
        return _NCAA_CONFERENCES_CACHE

    conf_path = os.path.join(os.path.dirname(__file__), "..", "configs", "ncaa_conferences.json")
    if not os.path.exists(conf_path):
        conf_path = "configs/ncaa_conferences.json"

    if os.path.exists(conf_path):
        try:
            with open(conf_path, "r", encoding="utf-8") as f:
                _NCAA_CONFERENCES_CACHE = json.load(f)
                return _NCAA_CONFERENCES_CACHE
        except Exception as e:
            print(f"[NCAA Resolver] Warning: Failed to load {conf_path}: {e}")

    _NCAA_CONFERENCES_CACHE = {"conferences": {}, "team_to_conf": {}, "conference_id_map": {}}
    return _NCAA_CONFERENCES_CACHE


def _normalize_name(name):
    if not name:
        return ""
    # remove accents, periods, lowercase
    cleaned = re.sub(r'[^a-zA-Z0-9\s]', '', name).lower().strip()
    return cleaned


def lookup_team_conference(team_id=None, team_name=None):
    """
    Find conference name for a given NCAA team.
    Returns conference name (e.g. 'Big East') or None if not found.
    """
    cache = _load_conferences_cache()
    conferences = cache.get("conferences", {})
    team_to_conf = cache.get("team_to_conf", {})

    # 1. Match by numeric ID first (most reliable)
    if team_id:
        try:
            tid_int = int(team_id)
            for conf, team_list in conferences.items():
                for t in team_list:
                    if t.get("id") == tid_int:
                        return conf
        except (ValueError, TypeError):
            pass

    # 2. Match by exact team name
    if team_name:
        if team_name in team_to_conf:
            return team_to_conf[team_name]

        norm_target = _normalize_name(team_name)
        for t_key, conf in team_to_conf.items():
            if _normalize_name(t_key) == norm_target:
                return conf

        # 3. Match by token / substring
        target_tokens = set(norm_target.split())
        for t_key, conf in team_to_conf.items():
            k_tokens = set(_normalize_name(t_key).split())
            if target_tokens and k_tokens and (target_tokens == k_tokens or target_tokens.issubset(k_tokens) or k_tokens.issubset(target_tokens)):
                return conf

    return None


def resolve_ncaa_conference(home_id, home_name, away_id, away_name):
    """
    Given NCAA home and away teams, determine whether this is an intra-conference matchup
    (e.g., Villanova vs UConn -> NCAA - Big East, league_id 11607)
    or a non-conference matchup (e.g., Villanova vs Notre Dame -> NCAA - Non-Conference, league_id 11600).

    Returns:
        (league_id: int, league_name: str, league_code: str)
    """
    cache = _load_conferences_cache()
    conf_id_map = cache.get("conference_id_map", {})

    home_conf = lookup_team_conference(home_id, home_name)
    away_conf = lookup_team_conference(away_id, away_name)

    # Both teams confirmed in the same conference
    if home_conf and away_conf and home_conf == away_conf:
        conf_info = conf_id_map.get(home_conf)
        if conf_info:
            return conf_info["id"], conf_info["name"], conf_info.get("code", f"NCAA-{home_conf[:4].upper()}")

    # Non-Conference game (cross-conference or one/both unmapped)
    nc_info = conf_id_map.get("Non-Conference", {
        "id": 11600,
        "name": "NCAA - Non-Conference",
        "code": "NCAA-NC"
    })
    return nc_info["id"], nc_info["name"], nc_info["code"]


def get_api_league_id(league_id):
    """
    Converts individual NCAA conference IDs (11600-11631) back to API-Basketball's
    parent NCAA league ID (116) for upstream API calls.
    """
    try:
        lid = int(league_id)
        if 11600 <= lid <= 11699:
            return 116
        if 42300 <= lid <= 42399:
            return 423
        return lid
    except (ValueError, TypeError):
        return league_id


def is_ncaa_league(league_id):
    """Check whether a league ID represents NCAA or an NCAA conference."""
    try:
        lid = int(league_id)
        return lid == 116 or (11600 <= lid <= 11699)
    except (ValueError, TypeError):
        return False

