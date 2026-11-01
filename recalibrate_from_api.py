"""
recalibrate_from_api.py
=======================
Official API League Calibrator for API-Sports (Pro Tier).
Fetches historical finished game logs directly from API-Basketball,
derives pace pivots, efficiency benchmarks, HCA, and baseline totals,
and saves standardized configs to configs/leagues/ and configs/leagues_v2/.
"""

import os
import sys
import time
import json
import math
import glob
import argparse
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

load_dotenv()

API_KEY = os.getenv("API_BASKETBALL_KEY")
BASE_URL = "https://v1.basketball.api-sports.io"
HEADERS = {"x-apisports-key": API_KEY}
ET_TZ = ZoneInfo("America/New_York")

TIER_TEMPLATES = {
    "elite_pro": {
        "_tier": "elite_pro",
        "_tier_desc": "Top professional leagues (NBA, EuroLeague, ACB)",
        "game_duration_mins": 40,
        "pace_pivot": 98.0,
        "eff_pivot": 113.0,
        "regression_factor": 0.96,
        "hca_total_bump": 2.5,
        "pace_delta_weight": 1.4,
        "eff_delta_weight": 0.75,
        "situational": {
            "b2b_penalty_single": -1.5,
            "b2b_penalty_double": -3.0,
            "fatigue_impact_cap": -4.0
        },
        "thresholds": {"mode_a": 8.0, "mode_b": 4.5, "min_edge": 0.0},
    },
    "top_domestic": {
        "_tier": "top_domestic",
        "_tier_desc": "Competitive domestic leagues (BBL, B League, CBA, BNXT)",
        "game_duration_mins": 40,
        "pace_pivot": 78.0,
        "eff_pivot": 108.0,
        "regression_factor": 0.90,
        "hca_total_bump": 3.5,
        "pace_delta_weight": 1.1,
        "eff_delta_weight": 0.7,
        "situational": {
            "b2b_penalty_single": -1.5,
            "b2b_penalty_double": -3.0,
            "fatigue_impact_cap": -4.0
        },
        "thresholds": {"mode_a": 7.0, "mode_b": 4.0, "min_edge": 0.0},
    },
    "second_division": {
        "_tier": "second_division",
        "_tier_desc": "Second-tier domestic leagues",
        "game_duration_mins": 40,
        "pace_pivot": 74.0,
        "eff_pivot": 105.0,
        "regression_factor": 0.88,
        "hca_total_bump": 4.5,
        "pace_delta_weight": 0.9,
        "eff_delta_weight": 0.65,
        "situational": {
            "b2b_penalty_single": -1.0,
            "b2b_penalty_double": -2.0,
            "fatigue_impact_cap": -3.0
        },
        "thresholds": {"mode_a": 7.5, "mode_b": 4.0, "min_edge": 0.0},
    },
    "lower": {
        "_tier": "lower",
        "_tier_desc": "National / regional leagues",
        "game_duration_mins": 40,
        "pace_pivot": 70.0,
        "eff_pivot": 103.0,
        "regression_factor": 0.82,
        "hca_total_bump": 5.5,
        "pace_delta_weight": 0.7,
        "eff_delta_weight": 0.6,
        "situational": {
            "b2b_penalty_single": -1.0,
            "b2b_penalty_double": -2.0,
            "fatigue_impact_cap": -3.0
        },
        "thresholds": {"mode_a": 9.0, "mode_b": 5.0, "min_edge": 0.0},
    },
}

KNOWN_TIER_MAP = {
    12:  "elite_pro",   # NBA
    117: "elite_pro",   # ACB Spain
    120: "elite_pro",   # Euroleague
    40:  "top_domestic",  # BBL Germany
    56:  "top_domestic",  # B League Japan
    31:  "top_domestic",  # CBA China
    368: "top_domestic",  # BNXT League
    45:  "top_domestic",  # Basket League Greece
    104: "top_domestic",  # Super Ligi Turkey
    198: "top_domestic",  # ABA League
    82:  "top_domestic",  # VTB United League
    72:  "top_domestic",  # Energa Basket Liga Poland
    407: "second_division",
    96:  "second_division",
    34:  "second_division",
    99:  "second_division",
    68:  "second_division",
    251: "lower",
    275: "lower",
    388: "lower",
}

def get_league_info(league_id):
    """Fetch league metadata and available season strings."""
    try:
        r = requests.get(f"{BASE_URL}/leagues", headers=HEADERS, params={"id": league_id}, timeout=12)
        resp = r.json().get("response", [])
        if not resp:
            return None, "Unknown", []
        l_obj = resp[0]
        name = l_obj.get("name", "Unknown")
        seasons = [s.get("season") for s in l_obj.get("seasons", []) if s.get("season")]
        return l_obj, name, seasons
    except Exception as e:
        print(f"  [API Error] fetching league {league_id}: {e}")
        return None, "Unknown", []

def fetch_finished_games_for_seasons(league_id, seasons_to_fetch):
    """Fetch finished games across specified season strings."""
    finished = []
    seen_ids = set()

    for s_str in seasons_to_fetch:
        try:
            r = requests.get(
                f"{BASE_URL}/games",
                headers=HEADERS,
                params={"league": league_id, "season": str(s_str)},
                timeout=15,
            )
            data = r.json().get("response", [])
            for g in data:
                gid = g.get("id")
                if gid in seen_ids:
                    continue
                status = g.get("status", {}).get("short", "")
                if status not in ("FT", "AOT"):
                    continue
                hs = g.get("scores", {}).get("home", {}).get("total")
                as_ = g.get("scores", {}).get("away", {}).get("total")
                if hs is None or as_ is None:
                    continue
                try:
                    hs = int(hs)
                    as_ = int(as_)
                except (ValueError, TypeError):
                    continue

                seen_ids.add(gid)
                finished.append({
                    "id": gid,
                    "date": g.get("date", "")[:10],
                    "home": g.get("teams", {}).get("home", {}).get("name"),
                    "away": g.get("teams", {}).get("away", {}).get("name"),
                    "home_score": hs,
                    "away_score": as_,
                    "total": hs + as_,
                    "margin": hs - as_
                })
        except Exception as e:
            print(f"  [Error] Season {s_str} for league {league_id}: {e}")

    return finished

def derive_parameters(games, league_id, league_name, tier_name):
    """Derive mathematical parameters from actual finished games."""
    n = len(games)
    if n < 8:
        return None

    totals = [g["total"] for g in games]
    margins = [g["margin"] for g in games]

    avg_total = sum(totals) / n
    std_total = math.sqrt(sum((t - avg_total) ** 2 for t in totals) / n)

    hca = sum(margins) / n
    hca = max(0.5, min(7.5, hca))

    tier_pace = TIER_TEMPLATES[tier_name]["pace_pivot"]
    eff_pivot = (avg_total * 100.0) / (2.0 * tier_pace)
    eff_pivot = max(88.0, min(140.0, eff_pivot))

    regression_factor = min(0.90, 0.50 + 0.40 * (min(n, 120) / 120.0))

    return {
        "n_games": n,
        "avg_total": round(avg_total, 1),
        "std_total": round(std_total, 1),
        "hca": round(hca, 2),
        "pace_pivot": round(tier_pace, 1),
        "eff_pivot": round(eff_pivot, 1),
        "regression_factor": round(regression_factor, 3),
    }

def calibrate_league(league_id, force_tier=None, verbose=True):
    """Calibrate a single league and save to configs/leagues/ and configs/leagues_v2/."""
    try:
        lid_int = int(league_id)
        if lid_int == 116 or (11600 <= lid_int <= 11699):
            from calibrate_all_ncaa_from_api import calibrate_all_ncaa
            calibrate_all_ncaa()
            return True
    except (ValueError, TypeError):
        pass

    l_obj, name, seasons = get_league_info(league_id)
    if not seasons:
        if verbose:
            print(f"  [Skip] League {league_id}: No seasons available.")
        return False

    # Pick the 2 most recent seasons for a rich sample
    seasons_sorted = sorted(seasons, key=lambda s: str(s))
    recent_seasons = seasons_sorted[-2:] if len(seasons_sorted) >= 2 else seasons_sorted

    if verbose:
        print(f"\n[{league_id}] {name} | Seasons: {recent_seasons}")

    tier_name = force_tier or KNOWN_TIER_MAP.get(league_id, "top_domestic")
    games = fetch_finished_games_for_seasons(league_id, recent_seasons)

    derived = derive_parameters(games, league_id, name, tier_name)

    template = dict(TIER_TEMPLATES[tier_name])
    cfg = {
        "name": name,
        "_league_id": league_id,
        "_calibrated_at": datetime.now(ET_TZ).strftime("%Y-%m-%d"),
        "_tier": tier_name,
        "_source": "api-recalibrated" if derived else "tier-template",
    }
    for k, v in template.items():
        if not k.startswith("_"):
            cfg[k] = v

    if derived:
        cfg["hca_total_bump"] = derived["hca"]
        cfg["pace_pivot"] = derived["pace_pivot"]
        cfg["eff_pivot"] = derived["eff_pivot"]
        cfg["regression_factor"] = derived["regression_factor"]
        cfg["_n_games"] = derived["n_games"]
        cfg["_avg_total"] = derived["avg_total"]
        cfg["_std_total"] = derived["std_total"]
        if verbose:
            print(f"  ✅ Derived: Games={derived['n_games']} | AvgTotal={derived['avg_total']} | Pace={derived['pace_pivot']} | Eff={derived['eff_pivot']} | HCA={derived['hca']:+.2f}")
    else:
        if verbose:
            print(f"  ⚠️ Thin Data ({len(games)} games) — using {tier_name} defaults.")

    # Save to both v1 and v2 directories
    out_paths = [
        f"configs/leagues/{league_id}.json",
        f"configs/leagues_v2/{league_id}.json"
    ]
    for p in out_paths:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as fp:
            json.dump(cfg, fp, indent=2)

    return True

def main():
    parser = argparse.ArgumentParser(description="Official API League Calibrator")
    parser.add_argument("--league_id", type=int, help="Single league ID to calibrate")
    parser.add_argument("--ncaa", action="store_true", help="Calibrate all 31 NCAA conferences + Non-Conference + Women's NCAA")
    parser.add_argument("--active", action="store_true", help="Calibrate all leagues active in today's predictions")
    parser.add_argument("--limit", type=int, default=0, help="Max leagues to calibrate (default: 0 = all)")
    args = parser.parse_args()

    print("=" * 70)
    print("  OFFICIAL API LEAGUE RE-CALIBRATOR (7,500 Plan Active)")
    print("=" * 70)

    if args.ncaa:
        from calibrate_all_ncaa_from_api import calibrate_all_ncaa
        calibrate_all_ncaa()
        return

    if args.league_id:
        calibrate_league(args.league_id)
        return

    # Find target league IDs
    target_ids = []
    if args.active:
        # Find all leagues appearing in today's or recent prediction files
        pred_files = sorted(glob.glob("data/basketball/universal_predictions_*.json"))
        seen = set()
        for pf in pred_files[-3:]:
            try:
                d = json.load(open(pf, "r", encoding="utf-8"))
                for p in d.get("predictions", []):
                    lid = p.get("league_id")
                    if lid and lid not in seen:
                        seen.add(lid)
                        target_ids.append(lid)
            except Exception:
                pass
        print(f"Found {len(target_ids)} active leagues from recent predictions.")
    else:
        # Load all existing config IDs
        existing = glob.glob("configs/leagues/*.json")
        for f in existing:
            base = os.path.basename(f).replace(".json", "")
            if base.isdigit():
                target_ids.append(int(base))
        print(f"Found {len(target_ids)} total league configs in repository.")

    if args.limit and args.limit > 0 and len(target_ids) > args.limit:
        target_ids = target_ids[:args.limit]
        print(f"Batching down to top {args.limit} leagues.")

    success = 0
    for idx, lid in enumerate(target_ids, 1):
        print(f"[{idx}/{len(target_ids)}]", end=" ")
        if calibrate_league(lid, verbose=True):
            success += 1
        time.sleep(0.5)  # safe throttle (well under 60 req/min)

    print(f"\n🎉 Successfully calibrated {success}/{len(target_ids)} leagues directly from API.")

if __name__ == "__main__":
    main()
