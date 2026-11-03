"""
core/mismatch_detector.py
==========================
Automated NCAA & Multi-League Mismatch and Responsible Staking Engine.

Detects non-conference "Buy Games", extreme talent disparities, and high-spread blowouts
before tip-off to protect bettors from high-variance garbage-time totals traps.

Signals Evaluated:
  1. Conference Tier Disparity (Power 5 vs Low-Major / Sub-D1 / Transition)
  2. Baseline SRS / KenPom / Net Rating Gap (ΔSRS >= 20.0)
  3. Market Point Spread (>= 18.0 pts)
  4. Model Projected Spread (>= 15.0 pts)

Outputs:
  - is_mismatch: bool
  - risk_level: 'EXTREME' | 'HIGH' | 'MODERATE' | 'LOW'
  - badge: Human-readable badge text (e.g. 'BUY GAME / HIGH VOLATILITY')
  - short_badge: Compact UI pill (e.g. '⚠️ Buy Game (0.25u)')
  - trigger: Specific reason that triggered the flag
  - recommended_stake: Exact staking advice (e.g. '0.25u or PASS')
  - totals_advice: Totals betting guidance (e.g. 'AVOID FULL-GAME TOTAL')
"""

from __future__ import annotations
import re
from typing import Optional, Dict, Any
from core.ncaa_conference_resolver import lookup_team_conference, is_ncaa_league

# ---------------------------------------------------------------------------
# NCAA Conference Tiers Hierarchy
# ---------------------------------------------------------------------------
NCAA_CONF_TIERS = {
    # Tier 1: High-Major / Power 5 (Heavy resource, top-40 programs)
    "Atlantic Coast": 1,
    "Big 12": 1,
    "Big East": 1,
    "Big Ten": 1,
    "Southeastern": 1,

    # Tier 2: Upper Mid-Major (High-level tournament contenders)
    "Mountain West": 2,
    "West Coast": 2,
    "Atlantic 10": 2,
    "American Conference": 2,
    "Missouri Valley": 2,

    # Tier 3: Standard Mid-Major (Single-bid mid conferences)
    "Sun Belt": 3,
    "Mid-American": 3,
    "Conference USA": 3,
    "Big West": 3,
    "Big Sky": 3,
    "Coastal Athletic Association": 3,
    "Horizon League": 3,
    "Southern": 3,
    "Ivy League": 3,
    "Summit League": 3,
    "Western Athletic": 3,
    "Metro Atlantic Athletic": 3,
    "Patriot League": 3,
    "ASUN": 3,
    "Big South": 3,

    # Tier 4: Low-Major / HBCU / Transition / Regional D1
    "Southwestern Athletic": 4,
    "Mid-Eastern Athletic": 4,
    "Northeast": 4,
    "Southland": 4,
    "Ohio Valley": 4,
    "America East": 4,
}

CONF_ABBR = {
    "Atlantic Coast": "ACC",
    "Big 12": "Big 12",
    "Big East": "Big East",
    "Big Ten": "Big Ten",
    "Southeastern": "SEC",
    "Mountain West": "MWC",
    "West Coast": "WCC",
    "Atlantic 10": "A-10",
    "American Conference": "AAC",
    "Missouri Valley": "MVC",
    "Southwestern Athletic": "SWAC",
    "Mid-Eastern Athletic": "MEAC",
    "Northeast": "NEC",
    "Southland": "Southland",
    "Ohio Valley": "OVC",
    "America East": "AmEast",
    "Mid-American": "MAC",
    "Sun Belt": "Sun Belt",
}

def detect_mismatch(
    home_team: str,
    away_team: str,
    home_id: Optional[int] = None,
    away_id: Optional[int] = None,
    league_id: Optional[int] = None,
    projected_spread: float = 0.0,
    market_spread: Optional[float] = None,
    srs_h: Optional[float] = None,
    srs_a: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Evaluates matchup parameters to identify talent mismatches and blowout risk.
    """
    is_ncaa = is_ncaa_league(league_id) if league_id is not None else False
    if not is_ncaa and league_id is not None:
        lid_int = int(league_id)
        if lid_int in (116, 423) or (11600 <= lid_int <= 11699) or (42300 <= lid_int <= 42399):
            is_ncaa = True

    abs_proj_spr = abs(float(projected_spread or 0.0))
    abs_mkt_spr = abs(float(market_spread)) if market_spread is not None else None

    # Baseline rating gap
    rating_gap = 0.0
    if srs_h is not None and srs_a is not None:
        rating_gap = abs(float(srs_h) - float(srs_a))

    # Effective spread indicator (prefers market if available, else projected)
    effective_spread = abs_mkt_spr if abs_mkt_spr is not None else abs_proj_spr

    # Non-NCAA / Generic Basketball League Logic
    if not is_ncaa:
        if (abs_mkt_spr and abs_mkt_spr >= 22.0) or abs_proj_spr >= 20.0 or rating_gap >= 25.0:
            return {
                "is_mismatch": True,
                "risk_level": "EXTREME",
                "badge": "EXTREME SPREAD MISMATCH",
                "short_badge": "⚠️ Blowout Risk (0.25u)",
                "trigger": f"Projected/Market Spread ({effective_spread:.1f} pts) indicates high blowout variance",
                "recommended_stake": "0.25u or PASS",
                "recommended_units": 0.25,
                "totals_advice": "AVOID FULL-GAME TOTAL (High garbage-time variance)",
                "home_conf": None, "away_conf": None, "home_tier": None, "away_tier": None,
                "tier_gap": 0, "spread": effective_spread, "rating_gap": rating_gap
            }
        elif (abs_mkt_spr and abs_mkt_spr >= 15.0) or abs_proj_spr >= 15.0 or rating_gap >= 18.0:
            return {
                "is_mismatch": True,
                "risk_level": "HIGH",
                "badge": "HIGH SPREAD MISMATCH",
                "short_badge": "⚠️ Mismatch (0.5u)",
                "trigger": f"Spread ({effective_spread:.1f} pts) indicates wide margin",
                "recommended_stake": "0.50u",
                "recommended_units": 0.50,
                "totals_advice": "LEAN FAVORITE TEAM TOTAL",
                "home_conf": None, "away_conf": None, "home_tier": None, "away_tier": None,
                "tier_gap": 0, "spread": effective_spread, "rating_gap": rating_gap
            }
        elif effective_spread >= 10.0:
            return {
                "is_mismatch": False,
                "risk_level": "MODERATE",
                "badge": "MODERATE SPREAD",
                "short_badge": "Moderate Spread",
                "trigger": f"Moderate spread ({effective_spread:.1f} pts)",
                "recommended_stake": "0.75u",
                "recommended_units": 0.75,
                "totals_advice": "STANDARD BETTING",
                "home_conf": None, "away_conf": None, "home_tier": None, "away_tier": None,
                "tier_gap": 0, "spread": effective_spread, "rating_gap": rating_gap
            }
        else:
            return {
                "is_mismatch": False,
                "risk_level": "LOW",
                "badge": "COMPETITIVE MATCHUP",
                "short_badge": "Competitive",
                "trigger": f"Competitive spread ({effective_spread:.1f} pts)",
                "recommended_stake": "1.00u",
                "recommended_units": 1.00,
                "totals_advice": "HIGH INTEGRITY GAME STATE",
                "home_conf": None, "away_conf": None, "home_tier": None, "away_tier": None,
                "tier_gap": 0, "spread": effective_spread, "rating_gap": rating_gap
            }

    # -----------------------------------------------------------------------
    # NCAA Specific Multi-Pillar Detection
    # -----------------------------------------------------------------------
    hc_name = lookup_team_conference(home_id, home_team)
    ac_name = lookup_team_conference(away_id, away_team)

    # Teams not in directory are non-D1 exhibition opponents (Sub-D1 / NAIA / D2 / D3)
    is_home_non_d1 = (hc_name is None)
    is_away_non_d1 = (ac_name is None)

    h_tier = NCAA_CONF_TIERS.get(hc_name, 4 if is_home_non_d1 else 3)
    a_tier = NCAA_CONF_TIERS.get(ac_name, 4 if is_away_non_d1 else 3)
    tier_gap = abs(h_tier - a_tier)

    hc_abbr = CONF_ABBR.get(hc_name, hc_name or "Non-D1")
    ac_abbr = CONF_ABBR.get(ac_name, ac_name or "Non-D1")

    # PILLAR 1: EXTREME BUY GAME
    # - Tier 1 hosting Tier 4 (Power 5 vs Low-Major, e.g. Big Ten vs NEC, SEC vs SWAC)
    # - Power 5 vs Non-D1 opponent
    # - Market spread >= 22.0 or Projected spread >= 20.0
    # - Baseline rating gap >= 24.0
    is_p5_vs_low_major = (h_tier == 1 and a_tier == 4) or (h_tier == 4 and a_tier == 1)
    is_non_d1_mismatch = (h_tier <= 2 and is_away_non_d1) or (a_tier <= 2 and is_home_non_d1)

    if (
        is_p5_vs_low_major
        or is_non_d1_mismatch
        or tier_gap >= 3
        or (abs_mkt_spr and abs_mkt_spr >= 22.0)
        or abs_proj_spr >= 20.0
        or rating_gap >= 24.0
    ):
        reasons = []
        if is_p5_vs_low_major:
            reasons.append(f"Power 5 vs Low-Major ({hc_abbr} vs {ac_abbr})")
        elif is_non_d1_mismatch:
            reasons.append(f"D1 High-Major vs Non-D1 Exhibition ({hc_abbr} vs {ac_abbr})")
        elif tier_gap >= 3:
            reasons.append(f"Tier {h_tier} vs Tier {a_tier} ({hc_abbr} vs {ac_abbr})")

        if abs_mkt_spr and abs_mkt_spr >= 22.0:
            reasons.append(f"Market Spread {abs_mkt_spr:.1f} pts")
        elif abs_proj_spr >= 20.0:
            reasons.append(f"Projected Spread {abs_proj_spr:.1f} pts")

        if rating_gap >= 24.0:
            reasons.append(f"Rating Gap Δ{rating_gap:.1f}")

        trigger_str = " | ".join(reasons) if reasons else "Severe talent mismatch"

        return {
            "is_mismatch": True,
            "risk_level": "EXTREME",
            "badge": "BUY GAME / HIGH VOLATILITY",
            "short_badge": "⚠️ Buy Game (0.25u)",
            "trigger": trigger_str,
            "recommended_stake": "0.25u or PASS",
            "recommended_units": 0.25,
            "totals_advice": "AVOID FULL-GAME TOTAL (High garbage-time variance)",
            "home_conf": hc_name, "away_conf": ac_name, "home_tier": h_tier, "away_tier": a_tier,
            "tier_gap": tier_gap, "spread": effective_spread, "rating_gap": rating_gap
        }

    # PILLAR 2: HIGH MISMATCH
    # - Tier 1 vs Tier 3 (Power 5 vs Standard Mid-Major, e.g. Big 12 vs WAC/Big Sky)
    # - Tier 2 vs Tier 4 (Upper Mid-Major vs Low-Major)
    # - Spread 15.0 - 21.9 pts
    # - Rating gap 16.0 - 23.9 pts
    is_p5_vs_mid = (h_tier == 1 and a_tier == 3) or (h_tier == 3 and a_tier == 1)
    is_mid_vs_low = (h_tier == 2 and a_tier == 4) or (h_tier == 4 and a_tier == 2)

    if (
        is_p5_vs_mid
        or is_mid_vs_low
        or tier_gap >= 2
        or (abs_mkt_spr and abs_mkt_spr >= 15.0)
        or abs_proj_spr >= 15.0
        or rating_gap >= 16.0
    ):
        reasons = []
        if is_p5_vs_mid:
            reasons.append(f"Power 5 vs Mid-Major ({hc_abbr} vs {ac_abbr})")
        elif is_mid_vs_low:
            reasons.append(f"Upper Mid vs Low-Major ({hc_abbr} vs {ac_abbr})")
        elif tier_gap >= 2:
            reasons.append(f"Tier {h_tier} vs Tier {a_tier} ({hc_abbr} vs {ac_abbr})")

        if effective_spread >= 15.0:
            reasons.append(f"Spread {effective_spread:.1f} pts")
        if rating_gap >= 16.0:
            reasons.append(f"Rating Gap Δ{rating_gap:.1f}")

        trigger_str = " | ".join(reasons) if reasons else "Noticeable talent disparity"

        return {
            "is_mismatch": True,
            "risk_level": "HIGH",
            "badge": "HIGH SPREAD MISMATCH",
            "short_badge": "⚠️ Mismatch (0.5u)",
            "trigger": trigger_str,
            "recommended_stake": "0.50u",
            "recommended_units": 0.50,
            "totals_advice": "LEAN FAVORITE TEAM TOTAL",
            "home_conf": hc_name, "away_conf": ac_name, "home_tier": h_tier, "away_tier": a_tier,
            "tier_gap": tier_gap, "spread": effective_spread, "rating_gap": rating_gap
        }

    # PILLAR 3: MODERATE SPREAD
    if effective_spread >= 10.0 or tier_gap == 1:
        return {
            "is_mismatch": False,
            "risk_level": "MODERATE",
            "badge": "MODERATE SPREAD",
            "short_badge": "Moderate Spread",
            "trigger": f"Moderate spread ({effective_spread:.1f} pts, {hc_abbr} vs {ac_abbr})",
            "recommended_stake": "0.75u",
            "recommended_units": 0.75,
            "totals_advice": "STANDARD BETTING",
            "home_conf": hc_name, "away_conf": ac_name, "home_tier": h_tier, "away_tier": a_tier,
            "tier_gap": tier_gap, "spread": effective_spread, "rating_gap": rating_gap
        }

    # PILLAR 4: LOW / COMPETITIVE
    return {
        "is_mismatch": False,
        "risk_level": "LOW",
        "badge": "COMPETITIVE MATCHUP",
        "short_badge": "Competitive",
        "trigger": f"Even matchup ({effective_spread:.1f} pts, {hc_abbr} vs {ac_abbr})",
        "recommended_stake": "1.00u",
        "recommended_units": 1.00,
        "totals_advice": "HIGH INTEGRITY GAME STATE",
        "home_conf": hc_name, "away_conf": ac_name, "home_tier": h_tier, "away_tier": a_tier,
        "tier_gap": tier_gap, "spread": effective_spread, "rating_gap": rating_gap
    }

