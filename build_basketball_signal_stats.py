"""
build_basketball_signal_stats.py
───────────────────────────────
Aggregates all graded basketball matches across data/basketball/universal_predictions_*.json
to compute live, empirical performance benchmarks for:
  1. Clash of the Inefficient (⚡)
  2. Shootout / Glass Cannons (🔥)

Outputs:
  - data/basketball/basketball_signal_stats.json
  - (and copies to Sports Analytics/public/data/basketball/basketball_signal_stats.json)

Can be executed standalone or imported into daily grading scripts.
"""

import glob
import json
import os
import sys
import shutil
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "data" / "basketball"
OUTPUT_FILE = DATA_DIR / "basketball_signal_stats.json"
DASHBOARD_DIR = ROOT_DIR.parent / "Sports Analytics" / "public" / "data" / "basketball"
if not DASHBOARD_DIR.parent.parent.exists() and (ROOT_DIR.parent / "sports-analytics").exists():
    DASHBOARD_DIR = ROOT_DIR.parent / "sports-analytics" / "public" / "data" / "basketball"

def build_signal_stats(save_to_dashboard: bool = True) -> dict:
    files = sorted(DATA_DIR.glob("universal_predictions_2026-*.json"))
    # Use production V1 files (non-v2) for primary benchmark
    v1_files = [f for f in files if not f.name.endswith("_v2.json")]

    all_graded = []

    for fpath in v1_files:
        date_str = fpath.stem.replace("universal_predictions_", "")
        try:
            with open(fpath, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except Exception:
            continue

        preds = data.get("predictions", []) if isinstance(data, dict) else data
        for p in preds:
            h_score = p.get("home_score") if p.get("home_score") is not None else p.get("actual_home_score")
            a_score = p.get("away_score") if p.get("away_score") is not None else p.get("actual_away_score")

            if h_score is None or a_score is None:
                continue

            actual_total = float(h_score + a_score)
            mt = p.get("model_total")
            if mt is None and isinstance(p.get("model"), dict):
                mt = p.get("model", {}).get("total")
            if mt is None:
                continue
            mt = float(mt)

            mkt = p.get("market_total")
            if mkt in (145.5, 230.0, None, 0):
                mkt = None
            else:
                try:
                    mkt = float(mkt)
                except (ValueError, TypeError):
                    mkt = None

            pred_winner = p.get("predicted_result")
            actual_winner = p.get("actual_result")
            if not actual_winner:
                actual_winner = "HOME" if h_score > a_score else ("AWAY" if a_score > h_score else "DRAW")

            all_graded.append({
                "date": date_str,
                "league": p.get("league", "Unknown"),
                "home": p.get("home_team"),
                "away": p.get("away_team"),
                "actual_total": actual_total,
                "model_total": mt,
                "market_total": mkt,
                "signed_delta": actual_total - mt,
                "is_clash": bool(p.get("is_clash")),
                "clash_trigger": p.get("clash_trigger", ""),
                "is_shootout": bool(p.get("is_shootout")),
                "shootout_trigger": p.get("shootout_trigger", ""),
                "winner_hit": bool(pred_winner and actual_winner and pred_winner == actual_winner),
            })

    total = len(all_graded)
    if total == 0:
        print("  [WARN] No graded basketball games found.")
        return {}

    # 1. Baseline
    base_under_mod = sum(1 for r in all_graded if r["actual_total"] < r["model_total"])
    base_delta_mod = sum(r["signed_delta"] for r in all_graded) / total
    base_ml_hit = sum(1 for r in all_graded if r["winner_hit"])

    with_mkt = [r for r in all_graded if r["market_total"] is not None]
    base_under_mkt = sum(1 for r in with_mkt if r["actual_total"] < r["market_total"])
    base_delta_mkt = (sum(r["actual_total"] - r["market_total"] for r in with_mkt) / len(with_mkt)) if with_mkt else 0.0

    # 2. Clash of the Inefficient (⚡)
    clash_games = [r for r in all_graded if r["is_clash"]]
    c_n = len(clash_games)
    clash_stats = {}
    if c_n > 0:
        c_under = sum(1 for r in clash_games if r["actual_total"] < r["model_total"])
        c_over = sum(1 for r in clash_games if r["actual_total"] > r["model_total"])
        c_delta = sum(r["signed_delta"] for r in clash_games) / c_n
        c_ml = sum(1 for r in clash_games if r["winner_hit"])

        sharp_clash = [r for r in clash_games if r["clash_trigger"] == "SHARP OVER"]
        sc_n = len(sharp_clash)
        sc_under = sum(1 for r in sharp_clash if r["actual_total"] < r["model_total"])
        sc_delta = (sum(r["signed_delta"] for r in sharp_clash) / sc_n) if sc_n else 0.0

        sc_mkt = [r for r in sharp_clash if r["market_total"] is not None]
        sc_mkt_n = len(sc_mkt)
        sc_mkt_under = sum(1 for r in sc_mkt if r["actual_total"] < r["market_total"])
        sc_mkt_delta = (sum(r["actual_total"] - r["market_total"] for r in sc_mkt) / sc_mkt_n) if sc_mkt_n else 0.0

        reg_clash = [r for r in clash_games if r["clash_trigger"] != "SHARP OVER"]
        rc_n = len(reg_clash)
        rc_under = sum(1 for r in reg_clash if r["actual_total"] < r["model_total"])
        rc_delta = (sum(r["signed_delta"] for r in reg_clash) / rc_n) if rc_n else 0.0

        rc_mkt = [r for r in reg_clash if r["market_total"] is not None]
        rc_mkt_n = len(rc_mkt)
        rc_mkt_under = sum(1 for r in rc_mkt if r["actual_total"] < r["market_total"])
        rc_mkt_delta = (sum(r["actual_total"] - r["market_total"] for r in rc_mkt) / rc_mkt_n) if rc_mkt_n else 0.0

        c_mkt = [r for r in clash_games if r["market_total"] is not None]
        cm_n = len(c_mkt)
        cm_under = sum(1 for r in c_mkt if r["actual_total"] < r["market_total"])
        cm_delta = (sum(r["actual_total"] - r["market_total"] for r in c_mkt) / cm_n) if cm_n else 0.0

        clash_stats = {
            "sample": c_n,
            "under_model_pct": round(c_under / c_n * 100, 1),
            "over_model_pct": round(c_over / c_n * 100, 1),
            "avg_score_delta": round(c_delta, 1),
            "moneyline_pct": round(c_ml / c_n * 100, 1),
            "sharp_over": {
                "sample": sc_n,
                "under_model_pct": round(sc_under / sc_n * 100, 1) if sc_n else 0.0,
                "avg_score_delta": round(sc_delta, 1),
                "mkt_sample": sc_mkt_n,
                "under_mkt_pct": round(sc_mkt_under / sc_mkt_n * 100, 1) if sc_mkt_n else 0.0,
                "avg_mkt_delta": round(sc_mkt_delta, 1),
            },
            "regular": {
                "sample": rc_n,
                "under_model_pct": round(rc_under / rc_n * 100, 1) if rc_n else 0.0,
                "avg_score_delta": round(rc_delta, 1),
                "mkt_sample": rc_mkt_n,
                "under_mkt_pct": round(rc_mkt_under / rc_mkt_n * 100, 1) if rc_mkt_n else 0.0,
                "avg_mkt_delta": round(rc_mkt_delta, 1),
            },
            "market_overall": {
                "sample": cm_n,
                "under_mkt_pct": round(cm_under / cm_n * 100, 1) if cm_n else 0.0,
                "avg_mkt_delta": round(cm_delta, 1),
            }
        }

    # 3. Shootout / Glass Cannons (🔥)
    so_games = [r for r in all_graded if r["is_shootout"]]
    so_n = len(so_games)
    shootout_stats = {}
    if so_n > 0:
        so_over_mod = sum(1 for r in so_games if r["actual_total"] > r["model_total"])
        so_under_mod = sum(1 for r in so_games if r["actual_total"] < r["model_total"])
        so_delta_mod = sum(r["signed_delta"] for r in so_games) / so_n
        so_ml = sum(1 for r in so_games if r["winner_hit"])

        so_mkt = [r for r in so_games if r["market_total"] is not None]
        som_n = len(so_mkt)
        som_over = sum(1 for r in so_mkt if r["actual_total"] > r["market_total"])
        som_under = sum(1 for r in so_mkt if r["actual_total"] < r["market_total"])
        som_delta = (sum(r["actual_total"] - r["market_total"] for r in so_mkt) / som_n) if som_n else 0.0

        sharp_so = [r for r in so_games if r["shootout_trigger"] == "SHARP SHOOTOUT"]
        sso_n = len(sharp_so)
        sso_mkt = [r for r in sharp_so if r["market_total"] is not None]
        sso_mkt_n = len(sso_mkt)
        sso_mkt_over = sum(1 for r in sso_mkt if r["actual_total"] > r["market_total"])
        sso_mkt_delta = (sum(r["actual_total"] - r["market_total"] for r in sso_mkt) / sso_mkt_n) if sso_mkt_n else 0.0

        shootout_stats = {
            "sample": so_n,
            "mkt_sample": som_n,
            "market_over_pct": round(som_over / som_n * 100, 1) if som_n else 0.0,
            "market_under_pct": round(som_under / som_n * 100, 1) if som_n else 0.0,
            "avg_market_delta": round(som_delta, 1),
            "model_over_pct": round(so_over_mod / so_n * 100, 1),
            "model_under_pct": round(so_under_mod / so_n * 100, 1),
            "avg_score_delta": round(so_delta_mod, 1),
            "moneyline_pct": round(so_ml / so_n * 100, 1),
            "sharp_shootout": {
                "sample": sso_n,
                "mkt_sample": sso_mkt_n,
                "market_over_pct": round(sso_mkt_over / sso_mkt_n * 100, 1) if sso_mkt_n else 0.0,
                "avg_market_delta": round(sso_mkt_delta, 1),
            }
        }

    payload = {
        "updated_at": datetime.now().isoformat(),
        "total_graded_games": total,
        "baseline": {
            "moneyline_pct": round(base_ml_hit / total * 100, 1),
            "under_model_pct": round(base_under_mod / total * 100, 1),
            "avg_signed_delta": round(base_delta_mod, 1),
            "under_market_pct": round(base_under_mkt / len(with_mkt) * 100, 1) if with_mkt else 0.0,
            "avg_market_delta": round(base_delta_mkt, 1),
        },
        "clash": clash_stats,
        "shootout": shootout_stats,
    }

    # Save to ncaa-api
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as wf:
        json.dump(payload, wf, indent=2, ensure_ascii=False)
    print(f"  [OK] Saved signal stats -> {OUTPUT_FILE}")

    # Copy to Sports Analytics dashboard if available
    if save_to_dashboard and DASHBOARD_DIR.exists():
        dash_dest = DASHBOARD_DIR / "basketball_signal_stats.json"
        try:
            with open(dash_dest, "w", encoding="utf-8") as wf:
                json.dump(payload, wf, separators=(",", ":"))
            print(f"  [OK] Copied minified to dashboard -> {dash_dest}")
        except Exception as e:
            print(f"  [WARN] Failed to copy to dashboard: {e}")

    return payload

if __name__ == "__main__":
    print("\n🏀 Aggregating Basketball Clash & Shootout Signal Statistics...")
    stats = build_signal_stats(save_to_dashboard=True)
    print(f"  Total Graded Games: {stats.get('total_graded_games', 0)}")
    print(f"  Clash Sample: {stats.get('clash', {}).get('sample', 0)} | Under Model: {stats.get('clash', {}).get('under_model_pct', 0)}%")
    print(f"  Shootout Sample: {stats.get('shootout', {}).get('sample', 0)} | Over Market: {stats.get('shootout', {}).get('market_over_pct', 0)}%")
    print("Done.\n")
