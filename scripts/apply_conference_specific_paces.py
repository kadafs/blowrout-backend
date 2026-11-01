"""
scripts/apply_conference_specific_paces.py
=========================================
Applies conference-specific empirical pace pivots to all NCAA Men (116, 11600-11631)
and NCAA Women (423, 42300-42331) configs.

- Men's conferences use empirical adjusted tempos from Barttorvik (66.1 - 69.6 possessions).
- Women's conferences use empirical conference tempos derived from game scoring distributions
  anchored to collegiate women's offensive rating (96.0 pts/100 poss).
"""

import sys
import json
import os
import re

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
from collections import defaultdict

BT_NAME_MAP = {
    'Non-Conference': 'ALL',
    'ASUN': 'ASun',
    'America East': 'AE',
    'American Conference': 'Amer',
    'Atlantic 10': 'A10',
    'Atlantic Coast': 'ACC',
    'Big 12': 'B12',
    'Big East': 'BE',
    'Big Sky': 'BSky',
    'Big South': 'BSth',
    'Big Ten': 'B10',
    'Big West': 'BW',
    'Coastal Athletic': 'CAA',
    'Coastal Athletic Association': 'CAA',
    'Conference USA': 'CUSA',
    'Horizon League': 'Horz',
    'Ivy League': 'Ivy',
    'Metro Atlantic Athletic': 'MAAC',
    'Mid-American': 'MAC',
    'Mid-Eastern Athletic': 'MEAC',
    'Missouri Valley': 'MVC',
    'Mountain West': 'MWC',
    'Northeast': 'NEC',
    'Ohio Valley': 'OVC',
    'Patriot League': 'Pat',
    'Southeastern': 'SEC',
    'Southern': 'SC',
    'Southland': 'Slnd',
    'Southwestern Athletic': 'SWAC',
    'Sun Belt': 'SB',
    'Summit League': 'Sum',
    'Western Athletic': 'WAC',
    'West Coast': 'WCC'
}

def load_men_conference_paces():
    with open('data/barttorvik_stats.json', 'r', encoding='utf-8') as f:
        bt_data = json.load(f)

    conf_paces = defaultdict(list)
    for team, stats in bt_data.items():
        c = stats.get('conf')
        t = stats.get('adj_t')
        if c and t:
            conf_paces[c].append(t)

    all_paces = [t for paces in conf_paces.values() for t in paces]
    national_avg_pace = round(sum(all_paces) / len(all_paces), 1)

    men_paces_by_name = {}
    for conf_name, bt_code in BT_NAME_MAP.items():
        if bt_code == 'ALL':
            men_paces_by_name[conf_name] = national_avg_pace
        else:
            paces = conf_paces.get(bt_code, [])
            men_paces_by_name[conf_name] = round(sum(paces) / len(paces), 1) if paces else national_avg_pace

    return men_paces_by_name, national_avg_pace


def update_ncaa_configs():
    with open('configs/ncaa_conferences.json', 'r', encoding='utf-8') as f:
        conf_data = json.load(f)

    men_paces_by_name, national_men_pace = load_men_conference_paces()
    cid_map = conf_data["conference_id_map"]

    directories = ["configs/leagues_v2", "configs/leagues"]

    print("Updating NCAA Men's Conference Configs...")
    for conf_name, info in cid_map.items():
        cid = info["id"]
        pace = men_paces_by_name.get(conf_name, national_men_pace)
        for d in directories:
            p = os.path.join(d, f"{cid}.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as fp:
                    cfg = json.load(fp)
                avg_t = cfg.get("_avg_total", 145.0)
                eff = round((avg_t * 100.0) / (2.0 * pace), 1)
                cfg["pace_pivot"] = pace
                cfg["eff_pivot"] = eff
                with open(p, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, indent=2)

    # Parent 116
    for d in directories:
        p = os.path.join(d, "116.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
            avg_t = cfg.get("_avg_total", 148.5)
            eff = round((avg_t * 100.0) / (2.0 * national_men_pace), 1)
            cfg["pace_pivot"] = national_men_pace
            cfg["eff_pivot"] = eff
            with open(p, "w", encoding="utf-8") as fp:
                json.dump(cfg, fp, indent=2)

    print("Updating NCAA Women's Conference Configs...")
    for cid in range(42300, 42332):
        for d in directories:
            p = os.path.join(d, f"{cid}.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as fp:
                    cfg = json.load(fp)
                avg_t = cfg.get("_avg_total", 130.0)
                # Collegiate Women baseline offensive efficiency is 96.0 pts/100 poss
                pace = round((avg_t * 100.0) / (2.0 * 96.0), 1)
                eff = round((avg_t * 100.0) / (2.0 * pace), 1)
                cfg["pace_pivot"] = pace
                cfg["eff_pivot"] = eff
                with open(p, "w", encoding="utf-8") as fp:
                    json.dump(cfg, fp, indent=2)

    # Parent 423
    for d in directories:
        p = os.path.join(d, "423.json")
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as fp:
                cfg = json.load(fp)
            avg_t = cfg.get("_avg_total", 132.8)
            pace = round((avg_t * 100.0) / (2.0 * 96.0), 1)
            eff = round((avg_t * 100.0) / (2.0 * pace), 1)
            cfg["pace_pivot"] = pace
            cfg["eff_pivot"] = eff
            with open(p, "w", encoding="utf-8") as fp:
                json.dump(cfg, fp, indent=2)

    print("✅ All 66 NCAA league configs successfully updated with conference-specific pace pivots!")

if __name__ == "__main__":
    update_ncaa_configs()
