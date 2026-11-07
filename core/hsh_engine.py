"""
core/hsh_engine.py
──────────────────
Highest-Scoring Half (HSH) prediction engine for football.

Methodology (layered):
  1. Team profile layer  — uses stored avg_ht/sh goals scored+conceded per team (min 3 games)
  2. League prior layer  — uses observed league-wide 1H/2H rate (or global prior)
  3. xG split layer      — distributes match xG across halves using team scoring patterns
  4. Poisson layer       — models P(1H goals > 2H goals) etc. via Poisson PMF
  5. Market hurdle layer — evaluates edge against realistic sportsbook breakeven odds
                          (2H hurdle ~48.5%, 1H hurdle ~31.5%)

Output fields added to each prediction:
  hsh_h1_goals    – expected 1H goals
  hsh_h2_goals    – expected 2H goals
  hsh_prob_1h     – probability 1H has more goals (%)
  hsh_prob_2h     – probability 2H has more goals (%)
  hsh_prob_tie    – probability equal goals in both halves (%)
  hsh_decision    – "1H" | "2H" | "PASS"
  hsh_confidence  – "HIGH" | "MODERATE" | "LOW"
  hsh_edge        – prob of decision - market breakeven (%)
  hsh_source      – "team_profile" | "league_prior" | "global_prior"
"""

import json
import math
import os
from functools import lru_cache

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "football")

# Global priors (research-backed: 2H scores ~56% of all goals on average)
GLOBAL_HT_SHARE = 0.44   # fraction of goals in 1H
GLOBAL_SH_SHARE = 0.56   # fraction of goals in 2H
GLOBAL_RATE_1H  = 0.270  # P(1H > 2H) across all leagues
GLOBAL_RATE_2H  = 0.490  # P(2H > 1H) across all leagues
GLOBAL_RATE_TIE = 0.240  # P(TIE)

# Market-calibrated breakeven hurdles (derived from sportsbook odds)
# 2H average odds ~2.05 -> Implied breakeven: 48.8% (hurdle: 48.5%)
# 1H average odds ~3.20 -> Implied breakeven: 31.25% (hurdle: 31.5%)
BREAKEVEN_2H = 0.485
BREAKEVEN_1H = 0.315

# Edge hurdles to trigger active plays
MIN_EDGE_2H       = 0.035  # P(2H) >= 52.0% -> ~54.7% historical win rate, +12.1% ROI
HIGH_CONF_EDGE_2H = 0.055  # P(2H) >= 54.0% -> ~55.2% historical win rate, +13.1% ROI

# 1H is heavily restricted because football mechanics strongly favor 2H (fatigue, subs, stoppage time).
# 1H calls require verified empirical team profile support and significant positive edge.
MIN_EDGE_1H       = 0.085  # P(1H) >= 40.0%
HIGH_CONF_EDGE_1H = 0.115  # P(1H) >= 43.0%

MIN_TEAM_GAMES    = 3      # Lowered from 5 to 3 so teams with 3+ games activate team_profile


# ── Data loading ──────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def _load_team_profiles() -> dict:
    path = os.path.join(DATA_DIR, "hsh_team_profiles.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("teams", {})
    except Exception:
        return {}


@lru_cache(maxsize=1)
def _load_league_profiles() -> dict:
    path = os.path.join(DATA_DIR, "hsh_league_profiles.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        return d.get("leagues", {})
    except Exception:
        return {}


def reload_profiles():
    """Force reload of cached profiles (call after aggregation)."""
    _load_team_profiles.cache_clear()
    _load_league_profiles.cache_clear()


# ── Poisson helpers ───────────────────────────────────────────────────────────

def _poisson_pmf(k: int, lam: float) -> float:
    """P(X = k) for Poisson(lam)."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def _poisson_half_probs(lam_1h: float, lam_2h: float, max_goals: int = 10) -> tuple:
    """
    Compute P(1H > 2H), P(2H > 1H), P(TIE) using independent Poisson distributions.
    Returns (prob_1h, prob_2h, prob_tie).
    """
    prob_1h = prob_2h = prob_tie = 0.0
    for g1 in range(max_goals + 1):
        p1 = _poisson_pmf(g1, lam_1h)
        for g2 in range(max_goals + 1):
            p2 = _poisson_pmf(g2, lam_2h)
            joint = p1 * p2
            if g1 > g2:
                prob_1h += joint
            elif g2 > g1:
                prob_2h += joint
            else:
                prob_tie += joint
    total = prob_1h + prob_2h + prob_tie
    if total > 0:
        prob_1h  /= total
        prob_2h  /= total
        prob_tie /= total
    return round(prob_1h, 4), round(prob_2h, 4), round(prob_tie, 4)


# ── Team profile lookup ───────────────────────────────────────────────────────

def _get_team_profile(team_name: str, league_id) -> dict:
    profiles = _load_team_profiles()
    if not profiles:
        return {}
    key = f"{league_id}__{team_name.lower().strip()}"
    if key in profiles:
        return profiles[key]
    # Fuzzy fallback
    name_lower = team_name.lower().strip()
    for k, v in profiles.items():
        if v.get("league_id") == league_id:
            stored = (v.get("name") or "").lower().strip()
            if stored and (stored in name_lower or name_lower in stored):
                return v
    return {}


def _get_league_profile(league_id) -> dict:
    profiles = _load_league_profiles()
    return profiles.get(str(league_id), {})


# ── Expected goals split ──────────────────────────────────────────────────────

def _estimate_half_goals(xg_home: float, xg_away: float,
                          h_profile: dict, a_profile: dict,
                          league_profile: dict) -> tuple:
    """
    Estimate expected goals in 1H and 2H.
    Returns (lam_1h, lam_2h, source_label).
    """
    xg_total = xg_home + xg_away

    # --- Team-profile method (best) ---
    h_ht_att = h_profile.get("avg_ht_goals_scored")
    h_sh_att = h_profile.get("avg_sh_goals_scored")
    a_ht_att = a_profile.get("avg_ht_goals_scored")
    a_sh_att = a_profile.get("avg_sh_goals_scored")

    h_games = h_profile.get("games", 0)
    a_games = a_profile.get("games", 0)
    if (all(v is not None for v in [h_ht_att, h_sh_att, a_ht_att, a_sh_att])
            and h_games >= MIN_TEAM_GAMES and a_games >= MIN_TEAM_GAMES):
        h_ht_total = h_ht_att + a_profile.get("avg_ht_goals_conceded", h_ht_att)
        h_sh_total = h_sh_att + a_profile.get("avg_sh_goals_conceded", h_sh_att)
        a_ht_total = a_ht_att + h_profile.get("avg_ht_goals_conceded", a_ht_att)
        a_sh_total = a_sh_att + h_profile.get("avg_sh_goals_conceded", a_sh_att)

        team_ht_avg = (h_ht_total + a_ht_total) / 2
        team_sh_avg = (h_sh_total + a_sh_total) / 2
        team_total  = team_ht_avg + team_sh_avg

        if team_total > 0:
            ht_share = team_ht_avg / team_total
            sh_share = team_sh_avg / team_total
            return round(xg_total * ht_share, 3), round(xg_total * sh_share, 3), "team_profile"

    # --- League-profile method (fallback) ---
    ht_share = league_profile.get("ht_goal_share")
    sh_share = league_profile.get("sh_goal_share")
    if ht_share and sh_share:
        return round(xg_total * ht_share, 3), round(xg_total * sh_share, 3), "league_prior"

    # --- Global prior (last resort) ---
    return round(xg_total * GLOBAL_HT_SHARE, 3), round(xg_total * GLOBAL_SH_SHARE, 3), "global_prior"


# ── Rate blending ─────────────────────────────────────────────────────────────

def _blend_rates(poisson_probs: tuple, h_profile: dict, a_profile: dict,
                 league_profile: dict, source: str) -> tuple:
    """
    Blend Poisson probabilities with observed team/league rates for stability.
    Returns (prob_1h, prob_2h, prob_tie).
    """
    p_1h, p_2h, p_tie = poisson_probs

    if source == "team_profile":
        # Weight: 50% Poisson, 30% team observed rate, 20% league prior
        h_r1 = h_profile.get("match_1h_rate", GLOBAL_RATE_1H)
        h_r2 = h_profile.get("match_2h_rate", GLOBAL_RATE_2H)
        h_rt = h_profile.get("match_tie_rate", GLOBAL_RATE_TIE)
        a_r1 = a_profile.get("match_1h_rate", GLOBAL_RATE_1H)
        a_r2 = a_profile.get("match_2h_rate", GLOBAL_RATE_2H)
        a_rt = a_profile.get("match_tie_rate", GLOBAL_RATE_TIE)
        obs_1h = (h_r1 + a_r1) / 2
        obs_2h = (h_r2 + a_r2) / 2
        obs_tie = (h_rt + a_rt) / 2
        l_1h  = league_profile.get("rate_1h", GLOBAL_RATE_1H)
        l_2h  = league_profile.get("rate_2h", GLOBAL_RATE_2H)
        l_tie = league_profile.get("rate_tie", GLOBAL_RATE_TIE)
        f_1h  = 0.50 * p_1h  + 0.30 * obs_1h  + 0.20 * l_1h
        f_2h  = 0.50 * p_2h  + 0.30 * obs_2h  + 0.20 * l_2h
        f_tie = 0.50 * p_tie + 0.30 * obs_tie + 0.20 * l_tie

    elif source == "league_prior":
        # Weight: 60% Poisson, 40% league prior
        l_1h  = league_profile.get("rate_1h", GLOBAL_RATE_1H)
        l_2h  = league_profile.get("rate_2h", GLOBAL_RATE_2H)
        l_tie = league_profile.get("rate_tie", GLOBAL_RATE_TIE)
        f_1h  = 0.60 * p_1h  + 0.40 * l_1h
        f_2h  = 0.60 * p_2h  + 0.40 * l_2h
        f_tie = 0.60 * p_tie + 0.40 * l_tie

    else:
        # Global prior only — blend 50/50
        f_1h  = 0.50 * p_1h  + 0.50 * GLOBAL_RATE_1H
        f_2h  = 0.50 * p_2h  + 0.50 * GLOBAL_RATE_2H
        f_tie = 0.50 * p_tie + 0.50 * GLOBAL_RATE_TIE

    # Normalise
    total = f_1h + f_2h + f_tie
    if total > 0:
        f_1h /= total; f_2h /= total; f_tie /= total

    return round(f_1h, 4), round(f_2h, 4), round(f_tie, 4)


# ── Public API ────────────────────────────────────────────────────────────────

def compute_hsh(prediction: dict) -> dict:
    """
    Compute Highest-Scoring Half prediction for a single match prediction dict.

    Required fields: home_team, away_team, league_id, xg_home, xg_away
    Returns a dict with hsh_* fields to merge into the prediction.
    """
    home_team = prediction.get("home_team", "")
    away_team = prediction.get("away_team", "")
    league_id = prediction.get("league_id")
    xg_home   = prediction.get("xg_home") or 0.0
    xg_away   = prediction.get("xg_away") or 0.0

    if xg_home + xg_away <= 0:
        return {"hsh_decision": "PASS", "hsh_source": "no_xg"}

    h_profile = _get_team_profile(home_team, league_id)
    a_profile = _get_team_profile(away_team, league_id)
    l_profile = _get_league_profile(league_id)

    lam_1h, lam_2h, source = _estimate_half_goals(
        xg_home, xg_away, h_profile, a_profile, l_profile
    )

    poisson_probs = _poisson_half_probs(lam_1h, lam_2h)
    prob_1h, prob_2h, prob_tie = _blend_rates(
        poisson_probs, h_profile, a_profile, l_profile, source
    )

    # Market-calibrated edges over realistic sportsbook breakeven hurdles
    edge_2h = prob_2h - BREAKEVEN_2H
    edge_1h = prob_1h - BREAKEVEN_1H

    # 1H is heavily restricted: only permitted when supported by empirical team profiles
    # with a proven 1H skew, avoiding negative EV traps on global priors.
    allow_1h = (source == "team_profile" and edge_1h >= MIN_EDGE_1H and prob_1h > prob_2h)

    if edge_2h >= MIN_EDGE_2H and prob_2h >= prob_1h:
        decision = "2H"
        edge = edge_2h
        confidence = "HIGH" if edge_2h >= HIGH_CONF_EDGE_2H else "MODERATE"
    elif allow_1h:
        decision = "1H"
        edge = edge_1h
        confidence = "HIGH" if edge_1h >= HIGH_CONF_EDGE_1H else "MODERATE"
    else:
        decision = "PASS"
        edge = max(edge_1h, edge_2h)
        confidence = "LOW"

    h_games = h_profile.get("games", 0)
    a_games = a_profile.get("games", 0)

    return {
        "hsh_h1_goals":   lam_1h,
        "hsh_h2_goals":   lam_2h,
        "hsh_prob_1h":    round(prob_1h * 100, 1),
        "hsh_prob_2h":    round(prob_2h * 100, 1),
        "hsh_prob_tie":   round(prob_tie * 100, 1),
        "hsh_decision":   decision,
        "hsh_confidence": confidence,
        "hsh_edge":       round(edge * 100, 1),
        "hsh_source":     source,
        "hsh_h_games":    h_games,
        "hsh_a_games":    a_games,
        "hsh_breakeven_2h": round(BREAKEVEN_2H * 100, 1),
        "hsh_breakeven_1h": round(BREAKEVEN_1H * 100, 1),
    }
