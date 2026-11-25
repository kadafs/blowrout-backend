"""
scripts/enrich_predictions_sdi.py
=================================
Refreshes sdiH and sdiA in daily prediction payloads using the latest team_sdi.json,
ensuring all non-NCAA teams display updated SDI, Creator Dependency, and Playmaker Risk
without touching or altering any predicted lines or model edges.
"""

import os
import sys
import glob
import json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from core.sdi_lookup import load_sdi_index, get_sdi_record
BACKEND_DIR = os.path.join(BASE_DIR, "data", "basketball")
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "Sports Analytics", "public", "data", "basketball")

def enrich_file(filepath):
    if not os.path.exists(filepath):
        return 0, 0
    with open(filepath, "r", encoding="utf-8") as fp:
        data = json.load(fp)

    preds = data.get("predictions", []) if isinstance(data, dict) else data
    if not isinstance(preds, list):
        return 0, 0

    sdi_index = load_sdi_index()
    enriched_sdi = 0
    enriched_creator = 0

    for p in preds:
        h_name = p.get("home_team")
        a_name = p.get("away_team")
        mc = p.setdefault("match_center", {})

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

    with open(filepath, "w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2, ensure_ascii=False)

    return enriched_sdi, enriched_creator

def main():
    target_files = glob.glob(os.path.join(BACKEND_DIR, "universal_predictions_*_v2.json"))
    target_files += glob.glob(os.path.join(FRONTEND_DIR, "universal_predictions_*_v2.json"))
    target_files = sorted(list(set(target_files)))

    print(f"Refreshing SDI and Creator Index across {len(target_files)} prediction files...")
    for tf in target_files:
        sdi_count, creator_count = enrich_file(tf)
        print(f"  {os.path.basename(tf)} -> enriched {sdi_count} SDI records, {creator_count} Creator records.")

if __name__ == "__main__":
    main()
