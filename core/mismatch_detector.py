"""
core/mismatch_detector.py
==========================
NCAA Conference Tier Mismatch Detector.

Rules:
  - Only fires for NCAA games (college basketball).
  - A mismatch is flagged ONLY when the two teams' conferences are separated
    by >= 2 tiers (e.g. Power 5 / Tier-1 vs Low-Major / Tier-4).
  - Non-NCAA leagues ALWAYS return is_mismatch = False.
  - SRS ratings, Vegas spread, and model projected spread are NOT used.
"""

from __future__ import annotations
from typing import Optional, Dict, Any
from core.ncaa_conference_resolver import lookup_team_conference, is_ncaa_league

# ---------------------------------------------------------------------------
# NCAA Conference Tier Hierarchy
# ---------------------------------------------------------------------------
NCAA_CONF_TIERS: Dict[str, int] = {
    # Tier 1 — High-Major / Power Conferences
    "Atlantic Coast":   1,
    "Big 12":           1,
    "Big East":         1,
    "Big Ten":          1,
    "Southeastern":     1,

    # Tier 2 — Upper Mid-Major (strong tournament contenders)
    "Mountain West":    2,
    "West Coast":       2,
    "Atlantic 10":      2,
    "American Conference": 2,
    "Missouri Valley":  2,

    # Tier 3 — Standard Mid-Major (single-bid conferences)
    "Sun Belt":         3,
    "Mid-American":     3,
    "Conference USA":   3,
    "Big West":         3,
    "Big Sky":          3,
    "Coastal Athletic Association": 3,
    "Horizon League":   3,
    "Southern":         3,
    "Ivy League":       3,
    "Summit League":    3,
    "Western Athletic": 3,
    "Metro Atlantic Athletic": 3,
    "Patriot League":   3,
    "ASUN":             3,
    "Big South":        3,

    # Tier 4 — Low-Major / HBCU / Regional D1
    "Southwestern Athletic": 4,
    "Mid-Eastern Athletic":  4,
    "Northeast":             4,
    "Southland":             4,
    "Ohio Valley":           4,
    "America East":          4,
}


def _is_ncaa(league_id: Optional[int]) -> bool:
    """Return True if league_id identifies an NCAA college basketball league."""
    if league_id is None:
        return False
    if is_ncaa_league(league_id):
        return True
    lid = int(league_id)
    return lid in (116, 423) or (11600 <= lid <= 11699) or (42300 <= lid <= 42399)


def detect_mismatch(
    home_team: str,
    away_team: str,
    home_id: Optional[int] = None,
    away_id: Optional[int] = None,
    league_id: Optional[int] = None,
    # kept for call-site compatibility — not used
    projected_spread: float = 0.0,
    market_spread: Optional[float] = None,
    srs_h: Optional[float] = None,
    srs_a: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Detect a conference tier mismatch for NCAA games only.

    Returns a dict with:
      is_mismatch (bool)  — True only for NCAA games where tier_gap >= 2
      home_conf / away_conf (str | None)
      home_tier / away_tier (int | None)
      tier_gap (int)
    """
    # ── Non-NCAA: always no mismatch ────────────────────────────────────────
    if not _is_ncaa(league_id):
        return {
            "is_mismatch": False,
            "home_conf": None, "away_conf": None,
            "home_tier": None, "away_tier": None,
            "tier_gap": 0,
        }

    # ── NCAA: resolve conferences ────────────────────────────────────────────
    hc_name = lookup_team_conference(home_id, home_team)
    ac_name = lookup_team_conference(away_id, away_team)

    # Teams absent from the directory are Non-D1 (NAIA / D2 / D3 exhibitions)
    h_tier = NCAA_CONF_TIERS.get(hc_name, 4 if hc_name is None else 3)
    a_tier = NCAA_CONF_TIERS.get(ac_name, 4 if ac_name is None else 3)
    tier_gap = abs(h_tier - a_tier)

    return {
        "is_mismatch": tier_gap >= 2,
        "home_conf": hc_name,
        "away_conf": ac_name,
        "home_tier": h_tier,
        "away_tier": a_tier,
        "tier_gap": tier_gap,
    }
