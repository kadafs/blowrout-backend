"""
scripts/enrich_predictions_sdi.py
=================================
Refreshes sdiH and sdiA in daily prediction payloads using the latest team_sdi.json,
ensuring all non-NCAA teams display updated SDI, Creator Dependency, and Playmaker Risk
without touching or altering any predicted lines or model edges.

Also tags high-altitude NCAA home venues with:
  - is_altitude_venue: True
  - altitude_ft: <elevation>
  - altitude_tag: "AVOID - ALTITUDE" or "ALTITUDE - OVER ONLY" (market <= 145.5)
"""

import os
import sys
import glob
import json
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.sdi_lookup import load_sdi_index, get_sdi_record
BACKEND_DIR = os.path.join(BASE_DIR, "data", "basketball")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "Sports Analytics", "public", "data", "basketball")
FRONTEND_DIR_ACTIONS = os.path.join(BASE_DIR, "sports-analytics", "public", "data", "basketball")

# High-altitude NCAA venues (≥ 4,000 ft). Key = lowercase team name fragment.
# Elevation in feet. Any home team matching a key gets tagged.
ALTITUDE_VENUES = {
    "wyoming":          7220,
    "air force":        6621,
    "southern utah":    5800,
    "colorado":         5360,   # Univ of Colorado (Boulder)
    "denver":           5280,
    "new mexico":       5100,
    "colorado state":   5004,
    "montana state":    4800,
    "utah state":       4778,
    "northern colorado":4650,
    "utah":             4657,
    "byu":              4551,
    "brigham young":    4551,
    "nevada":           4505,
    "utah valley":      4500,
    "idaho state":      4500,
    "weber state":      4300,
}

def get_altitude(team_name: str):
    """Return (is_altitude, elevation_ft) for a home team. Checks substring match."""
    if not team_name:
        return False, 0
    lower = team_name.lower()
    for key, elev in ALTITUDE_VENUES.items():
        if key in lower:
            return True, elev
    return False, 0

def enrich_file(filepath):
    if not os.path.exists(filepath):
        return 0, 0, 0
    with open(filepath, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    preds = data.get("predictions", []) if isinstance(data, dict) else data
    if not isinstance(preds, list):
        return 0, 0, 0

    sdi_index = load_sdi_index()
    enriched_sdi = 0
    enriched_creator = 0
    altitude_count = 0

    for p in preds:
        h_name = p.get("home_team")
        a_name = p.get("away_team")
        mc = p.setdefault("match_center", {})

        # ── Altitude tagging ──────────────────────────────────────────────────
        is_alt, alt_ft = get_altitude(h_name)
        if is_alt:
            market_total = p.get("market_total")
            p["is_altitude_venue"] = True
            p["altitude_ft"] = alt_ft
            # Master rule: BET OVER only when market total <= 145.5; else AVOID
            if market_total and market_total <= 145.5:
                p["altitude_tag"] = "ALTITUDE - OVER ONLY"
            else:
                p["altitude_tag"] = "AVOID - ALTITUDE"
            altitude_count += 1
        else:
            # Clear any stale altitude tag if venue changed
            p.pop("is_altitude_venue", None)
            p.pop("altitude_ft", None)
            p.pop("altitude_tag", None)

        sdi_h = get_sdi_record(h_name, sdi_index)
        sdi_a = get_sdi_record(a_name, sdi_index)

        if sdi_h:
            mc["sdiH"] = {
                "avg_sdi": sdi_h.get("avg_sdi"),
                "top1_pct": sdi_h.get("avg_top1_pct"),
                "risk": sdi_h.get("risk"),
                "risk_label": sdi_h.get("risk_label"),
                "top_players": sdi_h.get("top_players", []),
                "avg_off_share": sdi_h.get("avg_top1_off_share"),
                "playmaker_risk": sdi_h.get("playmaker_risk"),
                "top_creator": sdi_h.get("top_creator"),
            }
            enriched_sdi += 1
            if sdi_h.get("avg_top1_off_share") is not None:
                enriched_creator += 1

        if sdi_a:
            mc["sdiA"] = {
                "avg_sdi": sdi_a.get("avg_sdi"),
                "top1_pct": sdi_a.get("avg_top1_pct"),
                "risk": sdi_a.get("risk"),
                "risk_label": sdi_a.get("risk_label"),
                "top_players": sdi_a.get("top_players", []),
                "avg_off_share": sdi_a.get("avg_top1_off_share"),
                "playmaker_risk": sdi_a.get("playmaker_risk"),
                "top_creator": sdi_a.get("top_creator"),
            }
            enriched_sdi += 1
            if sdi_a.get("avg_top1_off_share") is not None:
                enriched_creator += 1

    tmp_path = filepath + ".tmp"
    for attempt in range(3):
        try:
            with open(tmp_path, "w", encoding="utf-8") as fp:
                json.dump(data, fp, indent=2, ensure_ascii=False)
            os.replace(tmp_path, filepath)
            break
        except Exception as e:
            if attempt == 2:
                print(f"      [!] Warning: Could not write {filepath}: {e}")
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:
                        pass
            time.sleep(0.5)

    return enriched_sdi, enriched_creator, altitude_count

def main():
    target_files = glob.glob(os.path.join(BACKEND_DIR, "universal_predictions_*_v2.json"))
    target_files += glob.glob(os.path.join(FRONTEND_DIR, "universal_predictions_*_v2.json"))
    target_files += glob.glob(os.path.join(FRONTEND_DIR_ACTIONS, "universal_predictions_*_v2.json"))
    target_files = sorted(list(set(target_files)))

    print(f"Refreshing SDI, Creator, and Altitude tags across {len(target_files)} prediction files...")
    for tf in target_files:
        sdi_count, creator_count, alt_count = enrich_file(tf)
        print(f"  {os.path.basename(tf)} -> SDI: {sdi_count}, Creator: {creator_count}, Altitude-tagged: {alt_count}")

if __name__ == "__main__":
    main()
