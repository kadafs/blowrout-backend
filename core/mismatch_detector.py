"""
core/mismatch_detector.py
==========================
NCAA Conference Tier Mismatch Detector.

Flags NCAA matchups where a structural talent disparity exists due to a
Conference Tier Gap >= 2 (e.g. Power 5 host vs Low-Major / Non-D1 visitor).

This is the only signal used. SRS, market spread, and projected spread are
NOT used as mismatch triggers — conference tier gap alone is the indicator.

Outputs:
  - is_mismatch: bool  (True only when NCAA tier_gap >= 2)
  - home_conf / away_conf: conference names
  - home_tier / away_tier: 1-4 tier classification
  - tier_gap: absolute tier difference
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
    Detects NCAA conference tier mismatches.

    A mismatch is flagged ONLY when the two teams belong to conferences that
    are separated by >= 2 tiers (e.g. Power 5/Tier-1 vs Low-Major/Tier-4,
    or Tier 1 vs Tier 3, or Tier 2 vs Tier 4).

    SRS rating differential, Vegas market spread, and model projected spread
    are NOT used as mismatch signals — conference tier gap is the sole trigger.

    Non-NCAA leagues are never flagged as mismatches.
    """
    # ── Resolve NCAA status ──────────────────────────────────────────────────
    is_ncaa = is_ncaa_league(league_id) if league_id is not None else False
    if not is_ncaa and league_id is not None:
        lid_int = int(league_id)
        if lid_int in (116, 423) or (11600 <= lid_int <= 11699) or (42300 <= lid_int <= 42399):
            is_ncaa = True

    # Non-NCAA: never a mismatch
    if not is_ncaa:
        return {
            "is_mismatch": False,
            "home_conf": None, "away_conf": None,
            "home_tier": None, "away_tier": None,
            "tier_gap": 0
        }

    # ── NCAA: conference tier lookup ─────────────────────────────────────────
    hc_name = lookup_team_conference(home_id, home_team)
    ac_name = lookup_team_conference(away_id, away_team)

    # Teams not in directory are non-D1 / exhibition opponents (NAIA / D2 / D3)
    is_home_non_d1 = (hc_name is None)
    is_away_non_d1 = (ac_name is None)

    h_tier = NCAA_CONF_TIERS.get(hc_name, 4 if is_home_non_d1 else 3)
    a_tier = NCAA_CONF_TIERS.get(ac_name, 4 if is_away_non_d1 else 3)
    tier_gap = abs(h_tier - a_tier)

    # ── Flag: tier gap >= 2 is the ONLY mismatch trigger ────────────────────
    is_mismatch = tier_gap >= 2

    return {
        "is_mismatch": is_mismatch,
        "home_conf": hc_name,
        "away_conf": ac_name,
        "home_tier": h_tier,
        "away_tier": a_tier,
        "tier_gap": tier_gap
    }

