"""
core/shots_confidence.py
─────────────────────────
Composite Confidence Scoring Engine for Football Total Shots and Shots on Target (SoT).

Evaluates match-level shot predictions across a 100-point scale:
1. Empirical Floor Hit Rate      (40 pts): Historical frequency of matches exceeding target line.
2. Model Margin / Clearance       (25 pts): Difference between expected shots and market line.
3. League Pace & Shot Climate     (20 pts): Environmental volume tier (ELITE_PACE, HIGH_PACE, LOW_EVENT).
4. Model Calibration & Stability  (15 pts): Historical prediction MAE and directional bias.

Confidence Bands:
  [ELITE SHOTS]  (80 - 100 pts)
  [STRONG SHOTS] (65 - 79 pts)
  [SOLID SHOTS]  (50 - 64 pts)
  [MODERATE]     (38 - 49 pts)
  [AVOID / TRAP] (0 - 37 pts)
"""

import json
import os
import difflib
from typing import Dict, Any, Optional, Tuple

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "football")
LEAGUE_LB_PATH = os.path.join(DATA_DIR, "league_leaderboard.json")
TEAM_LB_PATH = os.path.join(DATA_DIR, "football_leaderboard.json")

# Global prior defaults when empirical sample size is small
GLOBAL_SHOTS_BASELINE = 25.0
GLOBAL_OVER_24_5_RATE = 54.0
GLOBAL_SOT_ACCURACY   = 33.5


def load_shots_leaderboards(data_dir: str = DATA_DIR) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Load and index league and team historical leaderboards.
    Returns:
        (league_index, team_index)
    """
    l_path = os.path.join(data_dir, "league_leaderboard.json")
    t_path = os.path.join(data_dir, "football_leaderboard.json")

    league_index = {}
    if os.path.exists(l_path):
        try:
            with open(l_path, "r", encoding="utf-8") as f:
                ldata = json.load(f)
            for row in ldata.get("leaderboard", []):
                lid = row.get("league_id")
                name = row.get("name", "").strip().lower()
                if lid is not None:
                    league_index[str(lid)] = row
                if name:
                    league_index[name] = row
        except Exception as e:
            print(f"  [WARN] Failed to load {l_path}: {e}")

    team_index = {}
    if os.path.exists(t_path):
        try:
            with open(t_path, "r", encoding="utf-8") as f:
                tdata = json.load(f)
            for row in tdata.get("leaderboard", []):
                name = row.get("name", "").strip().lower()
                lid = row.get("league_id")
                if name:
                    if lid is not None:
                        team_index[(name, str(lid))] = row
                    if name not in team_index:
                        team_index[name] = row
        except Exception as e:
            print(f"  [WARN] Failed to load {t_path}: {e}")

    return league_index, team_index


def lookup_league_stats(league_id: Optional[int], league_name: str, country: str, league_index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find leaderboard entry for a league."""
    if not league_index:
        return None
    if league_id is not None and str(league_id) in league_index:
        return league_index[str(league_id)]
    
    clean_name = league_name.strip().lower()
    if country:
        full_key = f"{country.strip().lower()} — {clean_name}"
        if full_key in league_index:
            return league_index[full_key]
    if clean_name in league_index:
        return league_index[clean_name]

    # Fuzzy match on keys
    for k, v in league_index.items():
        if clean_name in k or k in clean_name:
            return v
    return None


def lookup_team_stats(team_name: str, league_id: Optional[int], team_index: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Find leaderboard entry for a team."""
    if not team_index or not team_name:
        return None
    name_clean = team_name.strip().lower()
    if league_id is not None:
        key = (name_clean, str(league_id))
        if key in team_index:
            return team_index[key]
    
    if name_clean in team_index:
        return team_index[name_clean]
    
    # Substring match
    for k, v in team_index.items():
        if isinstance(k, str) and (name_clean in k or k in name_clean):
            return v
    return None


def compute_shots_confidence(
    exp_total_shots: float,
    shots_call: str,
    shots_call_line: str,
    home_team: str,
    away_team: str,
    league_id: Optional[int] = None,
    league_name: str = "",
    country: str = "",
    pre_xg_total: Optional[float] = None,
    conversion_rating: str = "BALANCED",
    league_index: Optional[Dict[str, Any]] = None,
    team_index: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compute a 100-point composite confidence score for Total Shots.
    """
    if shots_call == "PASS" or not shots_call_line:
        return {
            "score": 0.0,
            "tier": "[PASS]",
            "floor_rate_pts": 0.0,
            "margin_pts": 0.0,
            "pace_pts": 0.0,
            "calibration_pts": 0.0,
            "empirical_floor_rate": None,
            "margin": 0.0,
            "shots_tier": "UNVERIFIED"
        }

    # Resolve line value
    try:
        line_val = float(shots_call_line.split()[-1])
    except (ValueError, IndexError):
        line_val = 24.5

    is_over = "OVER" in shots_call_line.upper()

    # Lookups
    l_stats = lookup_league_stats(league_id, league_name, country, league_index or {}) or {}
    h_stats = lookup_team_stats(home_team, league_id, team_index or {}) or {}
    a_stats = lookup_team_stats(away_team, league_id, team_index or {}) or {}

    # -------------------------------------------------------------
    # 1. Empirical Floor Hit Rate (Max 40 Pts)
    # -------------------------------------------------------------
    # Choose appropriate target rate
    if line_val >= 26.0:
        l_rate = l_stats.get("shots_over_26_5_pct")
    elif line_val >= 24.0:
        l_rate = l_stats.get("shots_over_24_5_pct")
    else:
        l_rate = l_stats.get("shots_over_22_5_pct")

    # Fallback to general over 24.5 or global baseline
    if l_rate is None:
        l_rate = GLOBAL_OVER_24_5_RATE

    # Calculate blended empirical rate
    # If betting UNDER, target rate is (100 - over_rate)
    target_league_rate = l_rate if is_over else (100.0 - l_rate)

    # Blend team rates if they have at least 3 games
    team_rates = []
    if h_stats.get("actual_shots_games", 0) >= 3:
        h_ov = h_stats.get("shots_over_24_5_pct", l_rate)
        team_rates.append(h_ov if is_over else (100.0 - h_ov))
    if a_stats.get("actual_shots_games", 0) >= 3:
        a_ov = a_stats.get("shots_over_24_5_pct", l_rate)
        team_rates.append(a_ov if is_over else (100.0 - a_ov))

    if team_rates:
        team_avg = sum(team_rates) / len(team_rates)
        blended_floor_rate = round(0.60 * team_avg + 0.40 * target_league_rate, 1)
    else:
        # Shrinkage to global prior
        l_games = l_stats.get("actual_shots_games", 0)
        weight = min(1.0, l_games / 15.0)
        prior = GLOBAL_OVER_24_5_RATE if is_over else (100.0 - GLOBAL_OVER_24_5_RATE)
        blended_floor_rate = round(weight * target_league_rate + (1.0 - weight) * prior, 1)

    # Points mapping (out of 40)
    if blended_floor_rate >= 75.0:
        floor_rate_pts = 40.0
    elif blended_floor_rate >= 70.0:
        floor_rate_pts = 35.0
    elif blended_floor_rate >= 65.0:
        floor_rate_pts = 30.0
    elif blended_floor_rate >= 60.0:
        floor_rate_pts = 24.0
    elif blended_floor_rate >= 55.0:
        floor_rate_pts = 18.0
    elif blended_floor_rate >= 50.0:
        floor_rate_pts = 12.0
    else:
        floor_rate_pts = 4.0

    # -------------------------------------------------------------
    # 2. Model Margin / Clearance (Max 25 Pts)
    # -------------------------------------------------------------
    if is_over:
        margin = round(exp_total_shots - line_val, 1)
    else:
        margin = round(line_val - exp_total_shots, 1)

    if margin >= 3.5:
        margin_pts = 25.0
    elif margin >= 2.5:
        margin_pts = 20.0
    elif margin >= 1.5:
        margin_pts = 15.0
    elif margin >= 0.8:
        margin_pts = 10.0
    elif margin > 0.0:
        margin_pts = 5.0
    else:
        margin_pts = 0.0

    # -------------------------------------------------------------
    # 3. League Pace & Environmental Climate (Max 20 Pts)
    # -------------------------------------------------------------
    pace_tier = l_stats.get("shots_tier", "BALANCED")
    if is_over:
        if pace_tier == "ELITE_PACE":
            pace_pts = 20.0
        elif pace_tier == "HIGH_PACE":
            pace_pts = 16.0
        elif pace_tier == "BALANCED":
            pace_pts = 11.0
        elif pace_tier == "UNVERIFIED":
            pace_pts = 10.0
        else:  # LOW_EVENT
            pace_pts = 2.0  # Heavy penalty for betting OVER in low-event leagues
    else:
        # For UNDER calls, low event leagues get high points
        if pace_tier == "LOW_EVENT":
            pace_pts = 20.0
        elif pace_tier == "BALANCED":
            pace_pts = 14.0
        elif pace_tier == "UNVERIFIED":
            pace_pts = 10.0
        else:
            pace_pts = 3.0  # Dangerous to bet UNDER in ELITE_PACE leagues

    # -------------------------------------------------------------
    # 4. Model Calibration & Stability (Max 15 Pts)
    # -------------------------------------------------------------
    mae = l_stats.get("shots_mae")
    bias = l_stats.get("shots_bias")

    if mae is not None:
        if mae <= 4.0:
            cal_pts = 15.0
        elif mae <= 5.0:
            cal_pts = 11.0
        elif mae <= 6.5:
            cal_pts = 7.0
        else:
            cal_pts = 3.0
    else:
        cal_pts = 8.0  # neutral

    # Directional bias penalty
    if bias is not None:
        if is_over and bias > 2.0:
            cal_pts = max(0.0, cal_pts - 4.0)  # Model tends to project too high
        elif not is_over and bias < -2.0:
            cal_pts = max(0.0, cal_pts - 4.0)  # Model tends to project too low

    total_score = round(floor_rate_pts + margin_pts + pace_pts + cal_pts, 1)

    # Determine Confidence Band
    if total_score >= 80.0:
        tier = "[ELITE SHOTS]"
    elif total_score >= 65.0:
        tier = "[STRONG SHOTS]"
    elif total_score >= 50.0:
        tier = "[SOLID SHOTS]"
    elif total_score >= 38.0:
        tier = "[MODERATE]"
    else:
        tier = "[AVOID / TRAP]"

    return {
        "score": total_score,
        "tier": tier,
        "floor_rate_pts": floor_rate_pts,
        "margin_pts": margin_pts,
        "pace_pts": pace_pts,
        "calibration_pts": cal_pts,
        "empirical_floor_rate": blended_floor_rate,
        "margin": margin,
        "shots_tier": pace_tier
    }


def compute_sot_confidence(
    exp_total_sot: float,
    sot_call: str,
    sot_call_line: str,
    shots_confidence_score: float,
    conversion_rating: str,
    home_team: str,
    away_team: str,
    league_id: Optional[int] = None,
    league_name: str = "",
    country: str = "",
    league_index: Optional[Dict[str, Any]] = None,
    team_index: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compute confidence and guardrail checks for Shots on Target (SoT).
    Requires both volume foundation and empirical shooting accuracy.
    """
    if sot_call == "PASS" or not sot_call_line:
        return {
            "score": 0.0,
            "tier": "[PASS]",
            "sot_accuracy": None,
            "margin": 0.0
        }

    try:
        line_val = float(sot_call_line.split()[-1])
    except (ValueError, IndexError):
        line_val = 8.5

    is_over = "OVER" in sot_call_line.upper()

    l_stats = lookup_league_stats(league_id, league_name, country, league_index or {}) or {}
    h_stats = lookup_team_stats(home_team, league_id, team_index or {}) or {}
    a_stats = lookup_team_stats(away_team, league_id, team_index or {}) or {}

    # Empirical accuracy from teams or league
    l_acc = l_stats.get("sot_conversion_rate") or GLOBAL_SOT_ACCURACY
    team_accs = []
    if h_stats.get("team_sot_accuracy"):
        team_accs.append(h_stats["team_sot_accuracy"])
    if a_stats.get("team_sot_accuracy"):
        team_accs.append(a_stats["team_sot_accuracy"])

    if team_accs:
        blended_acc = round(0.55 * (sum(team_accs) / len(team_accs)) + 0.45 * l_acc, 1)
    else:
        blended_acc = round(float(l_acc), 1)

    margin = round(exp_total_sot - line_val, 1) if is_over else round(line_val - exp_total_sot, 1)

    # 1. Base score derived from Shots volume foundation (Max 40)
    vol_base = (shots_confidence_score / 100.0) * 40.0

    # 2. Accuracy Score (Max 35)
    if is_over:
        if blended_acc >= 36.5:
            acc_pts = 35.0
        elif blended_acc >= 34.0:
            acc_pts = 28.0
        elif blended_acc >= 31.0:
            acc_pts = 18.0
        elif blended_acc >= 28.0:
            acc_pts = 8.0
        else:
            acc_pts = 0.0  # Long-distance pot-shooters, < 28% on target
    else:
        # For UNDER calls, low accuracy is favorable
        if blended_acc <= 28.5:
            acc_pts = 35.0
        elif blended_acc <= 31.5:
            acc_pts = 28.0
        elif blended_acc <= 34.0:
            acc_pts = 18.0
        else:
            acc_pts = 6.0

    # 3. SoT Margin (Max 25)
    if margin >= 2.0:
        mar_pts = 25.0
    elif margin >= 1.2:
        mar_pts = 18.0
    elif margin >= 0.6:
        mar_pts = 12.0
    elif margin > 0.0:
        mar_pts = 6.0
    else:
        mar_pts = 0.0

    total_sot_score = round(vol_base + acc_pts + mar_pts, 1)

    # Hard guardrails
    if is_over:
        if conversion_rating == "LOW_CONVERSION_RISK":
            total_sot_score = min(total_sot_score, 32.0)
        if blended_acc < 29.0:
            total_sot_score = min(total_sot_score, 34.0)

    if total_sot_score >= 80.0:
        tier = "[ELITE SOT]"
    elif total_sot_score >= 65.0:
        tier = "[STRONG SOT]"
    elif total_sot_score >= 50.0:
        tier = "[SOLID SOT]"
    elif total_sot_score >= 38.0:
        tier = "[MODERATE]"
    else:
        tier = "[AVOID / TRAP]"

    return {
        "score": total_sot_score,
        "tier": tier,
        "sot_accuracy": blended_acc,
        "margin": margin,
        "conversion_rating": conversion_rating
    }
