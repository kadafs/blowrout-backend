"""
core/shots_engine.py
────────────────────
Total Shots & Shots on Target (SoT) Prediction and Guardrail Engine.

Predicts:
- Expected Home / Away / Total Shots
- Expected Home / Away / Total Shots on Target (SoT)
- Market line probabilities (Over 22.5, 24.5, 26.5 Shots; Over 7.5, 8.5, 9.5 SoT)
- Actionable calls: OVER/UNDER/PASS
- Shot conversion efficiency classification (CLINICAL, BALANCED, LOW_CONVERSION_RISK)
- High Over 2.5 conversion risk warning flag
"""

import math
from typing import Dict, Any, Optional

# Default baseline parameters for modern professional football
DEFAULT_MATCH_SHOTS = 24.0
DEFAULT_TEAM_SHOTS_HOME = 13.2
DEFAULT_TEAM_SHOTS_AWAY = 10.8
DEFAULT_SOT_RATIO = 0.345  # ~34.5% of total shots are on target across top leagues

# Standard betting lines
SHOTS_LINE_PRIMARY = 24.5
SHOTS_LINE_HIGH    = 26.5
SHOTS_LINE_LOW     = 22.5

SOT_LINE_PRIMARY   = 8.5
SOT_LINE_HIGH      = 9.5
SOT_LINE_LOW       = 7.5

# Minimum confidence required to emit a betting call
CALL_CONFIDENCE_THRESHOLD = 62.5


def poisson_cdf(lam: float, k: int) -> float:
    """Calculate P(X <= k) for Poisson distribution with mean lam."""
    if lam <= 0:
        return 1.0
    total = 0.0
    for i in range(k + 1):
        total += (math.e ** -lam) * (lam ** i) / math.factorial(i)
    return min(1.0, max(0.0, total))


def prob_over(exp_val: float, line: float) -> float:
    """Calculate P(X > line) as percentage."""
    k = int(math.floor(line))
    p_le_k = poisson_cdf(exp_val, k)
    return round((1.0 - p_le_k) * 100.0, 1)


def prob_under(exp_val: float, line: float) -> float:
    """Calculate P(X < line) as percentage."""
    k = int(math.floor(line))
    return round(poisson_cdf(exp_val, k) * 100.0, 1)


# Women's league keywords — shots baselines are calibrated on men's data only
# Women's games average ~35-40 shots vs ~24 for men, causing systematic UNDER bias
WOMENS_LEAGUE_KEYWORDS = (
    " w ", " women", "frauen", "femenil", "feminin", "feminine",
    "damen", "mulher", "donne", "vrouwen", "kvinde", "kvinner",
    "naiset", "naisten", "nők", "womens", "woman",
)


def _is_womens_league(league: str, country: str = "") -> bool:
    """Return True if the league name indicates a women's competition."""
    combined = (league + " " + country).lower()
    return any(kw in combined for kw in WOMENS_LEAGUE_KEYWORDS)


from core.shots_confidence import (
    compute_shots_confidence,
    compute_sot_confidence,
    lookup_league_stats,
    lookup_team_stats
)


def calculate_shots_prediction(
    home_profile: Optional[Dict[str, Any]],
    away_profile: Optional[Dict[str, Any]],
    pre_xg_home: Optional[float] = None,
    pre_xg_away: Optional[float] = None,
    country: str = "",
    league: str = "",
    home_team: str = "",
    away_team: str = "",
    league_id: Optional[int] = None,
    league_index: Optional[Dict[str, Any]] = None,
    team_index: Optional[Dict[str, Any]] = None
) -> Optional[Dict[str, Any]]:
    """
    Generate match-level Total Shots and Shots on Target (SoT) projections,
    confidence levels, and betting signals from team profiles and pre-match context.
    """
    h_prof = home_profile or {}
    a_prof = away_profile or {}

    # Skip women's leagues — baselines calibrated on men's data only.
    # Women's games average ~35-40 total shots vs ~24 for men, causing large UNDER bias.
    if _is_womens_league(league, country):
        return None

    # Check if teams are quarantined
    if h_prof.get("quarantined") or a_prof.get("quarantined"):
        return None

    # Look up league empirical stats if available
    l_stats = lookup_league_stats(league_id, league, country, league_index or {}) or {}
    if l_stats.get("sot_conversion_rate"):
        league_sot_ratio = min(0.48, max(0.20, l_stats["sot_conversion_rate"] / 100.0))
    else:
        league_sot_ratio = DEFAULT_SOT_RATIO

    # 1. Resolve Home Team Expected Shots
    # Blend home team shots generated with away team shots conceded
    h_shots_for = h_prof.get("home_shots_for") or h_prof.get("avg_shots_for") or h_prof.get("avg_shots_total")
    a_shots_ag  = a_prof.get("away_shots_against") or a_prof.get("avg_shots_against")

    # 2. Resolve Away Team Expected Shots
    a_shots_for = a_prof.get("away_shots_for") or a_prof.get("avg_shots_for") or a_prof.get("avg_shots_total")
    h_shots_ag  = h_prof.get("home_shots_against") or h_prof.get("avg_shots_against")

    # Fallback to pre-match xG heuristics if team profile historical shots are missing
    # In professional football, ~0.11 xG is generated per shot (i.e. ~9 shots per 1.0 xG)
    if not h_shots_for or not a_shots_for:
        if pre_xg_home is not None and pre_xg_away is not None:
            exp_home_shots = round(min(25.0, max(6.0, float(pre_xg_home) * 8.5)), 1)
            exp_away_shots = round(min(22.0, max(5.0, float(pre_xg_away) * 8.5)), 1)
        else:
            exp_home_shots = DEFAULT_TEAM_SHOTS_HOME
            exp_away_shots = DEFAULT_TEAM_SHOTS_AWAY
    else:
        # Expected home shots = (Home Shots For + Away Shots Allowed) / 2
        if a_shots_ag:
            exp_home_shots = round(min(25.0, max(5.0, (float(h_shots_for) + float(a_shots_ag)) / 2.0)), 1)
        else:
            exp_home_shots = round(min(25.0, max(5.0, float(h_shots_for))), 1)

        # Expected away shots = (Away Shots For + Home Shots Allowed) / 2
        if h_shots_ag:
            exp_away_shots = round(min(22.0, max(4.0, (float(a_shots_for) + float(h_shots_ag)) / 2.0)), 1)
        else:
            exp_away_shots = round(min(22.0, max(4.0, float(a_shots_for))), 1)

    exp_total_shots = round(min(38.0, exp_home_shots + exp_away_shots), 1)

    # 3. Resolve Shots on Target (SoT) Accuracy Ratios
    # Accuracy ratio = SoT / Total Shots (baseline ~ 34.5% or league empirical)
    h_sot_ratio = h_prof.get("sot_accuracy_ratio")
    if not h_sot_ratio:
        h_sot_for = h_prof.get("home_sot_for") or h_prof.get("avg_sot_for")
        if h_sot_for and h_shots_for and h_shots_for > 0:
            h_sot_ratio = min(0.50, max(0.20, float(h_sot_for) / float(h_shots_for)))
        else:
            # Check team leaderboard empirical accuracy
            h_team_stats = lookup_team_stats(home_team, league_id, team_index or {}) or {}
            if h_team_stats.get("team_sot_accuracy"):
                h_sot_ratio = min(0.50, max(0.20, h_team_stats["team_sot_accuracy"] / 100.0))
            else:
                h_sot_ratio = league_sot_ratio
    else:
        h_sot_ratio = min(0.50, max(0.20, float(h_sot_ratio)))

    a_sot_ratio = a_prof.get("sot_accuracy_ratio")
    if not a_sot_ratio:
        a_sot_for = a_prof.get("away_sot_for") or a_prof.get("avg_sot_for")
        if a_sot_for and a_shots_for and a_shots_for > 0:
            a_sot_ratio = min(0.50, max(0.20, float(a_sot_for) / float(a_shots_for)))
        else:
            # Check team leaderboard empirical accuracy
            a_team_stats = lookup_team_stats(away_team, league_id, team_index or {}) or {}
            if a_team_stats.get("team_sot_accuracy"):
                a_sot_ratio = min(0.50, max(0.20, a_team_stats["team_sot_accuracy"] / 100.0))
            else:
                a_sot_ratio = league_sot_ratio
    else:
        a_sot_ratio = min(0.50, max(0.20, float(a_sot_ratio)))

    # Compute Expected SoT per team
    exp_home_sot = round(exp_home_shots * h_sot_ratio, 1)
    exp_away_sot = round(exp_away_shots * a_sot_ratio, 1)
    exp_total_sot = round(exp_home_sot + exp_away_sot, 1)

    # Overall blended match accuracy
    match_sot_accuracy = round((exp_total_sot / exp_total_shots) * 100.0, 1) if exp_total_shots > 0 else 34.5

    # 4. Conversion Efficiency Rating
    # Identifies matches where high shot volume does NOT translate to dangerous chances
    if match_sot_accuracy >= 37.0:
        conversion_rating = "CLINICAL"
    elif match_sot_accuracy <= 30.5:
        conversion_rating = "LOW_CONVERSION_RISK"
    else:
        conversion_rating = "BALANCED"

    # 5. Poisson Line Probabilities
    # Total Shots lines
    prob_over_22_5_shots = prob_over(exp_total_shots, SHOTS_LINE_LOW)
    prob_over_24_5_shots = prob_over(exp_total_shots, SHOTS_LINE_PRIMARY)
    prob_over_26_5_shots = prob_over(exp_total_shots, SHOTS_LINE_HIGH)

    # Shots on Target lines
    prob_over_7_5_sot = prob_over(exp_total_sot, SOT_LINE_LOW)
    prob_over_8_5_sot = prob_over(exp_total_sot, SOT_LINE_PRIMARY)
    prob_over_9_5_sot = prob_over(exp_total_sot, SOT_LINE_HIGH)

    # 6. Actionable Market Calls
    # Guard: suppress all calls when exp_total_shots is suspiciously low.
    DATA_QUALITY_FLOOR = 18.0

    # Shots Call
    shots_call = "PASS"
    shots_call_line = ""
    if exp_total_shots >= DATA_QUALITY_FLOOR:
        if prob_over_26_5_shots >= CALL_CONFIDENCE_THRESHOLD:
            shots_call = "OVER 26.5"
            shots_call_line = "OVER 26.5"
        elif prob_over_24_5_shots >= CALL_CONFIDENCE_THRESHOLD:
            shots_call = "OVER 24.5"
            shots_call_line = "OVER 24.5"
        elif (100.0 - prob_over_22_5_shots) >= CALL_CONFIDENCE_THRESHOLD:
            shots_call = "UNDER 22.5"
            shots_call_line = "UNDER 22.5"

    # SoT Call
    sot_call = "PASS"
    sot_call_line = ""
    if exp_total_shots >= DATA_QUALITY_FLOOR:
        if prob_over_9_5_sot >= CALL_CONFIDENCE_THRESHOLD:
            sot_call = "OVER 9.5"
            sot_call_line = "OVER 9.5"
        elif prob_over_8_5_sot >= CALL_CONFIDENCE_THRESHOLD:
            sot_call = "OVER 8.5"
            sot_call_line = "OVER 8.5"
        elif (100.0 - prob_over_7_5_sot) >= CALL_CONFIDENCE_THRESHOLD:
            sot_call = "UNDER 7.5"
            sot_call_line = "UNDER 7.5"

    # 7. Compute Confidence Scores
    shots_conf = compute_shots_confidence(
        exp_total_shots=exp_total_shots,
        shots_call=shots_call,
        shots_call_line=shots_call_line,
        home_team=home_team,
        away_team=away_team,
        league_id=league_id,
        league_name=league,
        country=country,
        pre_xg_total=(pre_xg_home or 0.0) + (pre_xg_away or 0.0),
        conversion_rating=conversion_rating,
        league_index=league_index,
        team_index=team_index
    )

    sot_conf = compute_sot_confidence(
        exp_total_sot=exp_total_sot,
        sot_call=sot_call,
        sot_call_line=sot_call_line,
        shots_confidence_score=shots_conf.get("score", 0.0),
        conversion_rating=conversion_rating,
        home_team=home_team,
        away_team=away_team,
        league_id=league_id,
        league_name=league,
        country=country,
        league_index=league_index,
        team_index=team_index
    )

    return {
        "exp_home_shots": exp_home_shots,
        "exp_away_shots": exp_away_shots,
        "exp_total_shots": exp_total_shots,
        "exp_home_sot": exp_home_sot,
        "exp_away_sot": exp_away_sot,
        "exp_total_sot": exp_total_sot,
        "sot_accuracy_pct": match_sot_accuracy,
        "conversion_rating": conversion_rating,
        "over_22_5_shots_prob": prob_over_22_5_shots,
        "over_24_5_shots_prob": prob_over_24_5_shots,
        "over_26_5_shots_prob": prob_over_26_5_shots,
        "over_7_5_sot_prob": prob_over_7_5_sot,
        "over_8_5_sot_prob": prob_over_8_5_sot,
        "over_9_5_sot_prob": prob_over_9_5_sot,
        "shots_call": shots_call,
        "shots_call_line": shots_call_line,
        "shots_confidence_score": shots_conf.get("score", 0.0),
        "shots_confidence_tier": shots_conf.get("tier", "[PASS]"),
        "shots_margin": shots_conf.get("margin", 0.0),
        "shots_pace_tier": shots_conf.get("shots_tier", "UNVERIFIED"),
        "sot_call": sot_call,
        "sot_call_line": sot_call_line,
        "sot_confidence_score": sot_conf.get("score", 0.0),
        "sot_confidence_tier": sot_conf.get("tier", "[PASS]"),
        "sot_margin": sot_conf.get("margin", 0.0)
    }

