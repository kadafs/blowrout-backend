"""
build_basketball_signal_stats.py
───────────────────────────────────
Aggregates all graded basketball matches across data/basketball/universal_predictions_*.json
to compute live, empirical performance benchmarks for:
  1. Multi-Segment Smart Edge (FIBA Core, NBA Men, NCAA Men, NBA G-League)
  2. Clash of the Inefficient (⚡)
  3. Shootout / Glass Cannons (🔥)
  4. Drag-Down Under (⚓)

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
from collections import defaultdict
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

sys.path.append(str(ROOT_DIR))
from run_basketball_daily_v2 import classify_basketball_segment

def compute_segment_stats(games, seg_name):
    total = len(games)
    if total == 0:
        return {
            "name": seg_name,
            "sample": 0,
            "market_sample": 0,
            "under": {"sample": 0, "mkt_sample": 0, "market_under_pct": 0.0, "avg_market_delta": 0.0},
            "over": {"sample": 0, "mkt_sample": 0, "market_over_pct": 0.0, "avg_market_delta": 0.0}
        }

    with_mkt = [g for g in games if g["market_total"] is not None]
    nm = len(with_mkt)

    # Smart Under plays
    u_plays = [g for g in with_mkt if g["is_smart_edge_under"]]
    un = len(u_plays)
    u_hits = sum(1 for g in u_plays if g["actual_total"] < g["market_total"])
    u_pct = round(u_hits / un * 100, 1) if un else 0.0
    u_delta = round(sum(g["actual_total"] - g["market_total"] for g in u_plays) / un, 1) if un else 0.0

    ultra_games = [g for g in u_plays if g.get("smart_edge_tier") == "ULTRA"]
    ultra_hits = sum(1 for g in ultra_games if g["actual_total"] < g["market_total"])
    ultra_pct = round(ultra_hits / len(ultra_games) * 100, 1) if ultra_games else 0.0
    ultra_delta = round(sum(g["actual_total"] - g["market_total"] for g in ultra_games) / len(ultra_games), 1) if ultra_games else 0.0

    elite_games = [g for g in u_plays if g.get("smart_edge_tier") == "ELITE"]
    elite_hits = sum(1 for g in elite_games if g["actual_total"] < g["market_total"])
    elite_pct = round(elite_hits / len(elite_games) * 100, 1) if elite_games else 0.0
    elite_delta = round(sum(g["actual_total"] - g["market_total"] for g in elite_games) / len(elite_games), 1) if elite_games else 0.0

    standard_games = [g for g in u_plays if g.get("smart_edge_tier") == "STANDARD"]
    standard_hits = sum(1 for g in standard_games if g["actual_total"] < g["market_total"])
    standard_pct = round(standard_hits / len(standard_games) * 100, 1) if standard_games else 0.0
    standard_delta = round(sum(g["actual_total"] - g["market_total"] for g in standard_games) / len(standard_games), 1) if standard_games else 0.0

    # Smart Over plays
    o_plays = [g for g in with_mkt if g["is_smart_edge_over"]]
    on = len(o_plays)
    o_hits = sum(1 for g in o_plays if g["actual_total"] > g["market_total"])
    o_pct = round(o_hits / on * 100, 1) if on else 0.0
    o_delta = round(sum(g["actual_total"] - g["market_total"] for g in o_plays) / on, 1) if on else 0.0

    return {
        "name": seg_name,
        "sample": total,
        "market_sample": nm,
        "under": {
            "sample": sum(1 for g in games if g["is_smart_edge_under"]),
            "mkt_sample": un,
            "market_under_pct": u_pct,
            "avg_market_delta": u_delta,
            "ultra": {"mkt_sample": len(ultra_games), "under_mkt_pct": ultra_pct, "avg_market_delta": ultra_delta},
            "elite": {"mkt_sample": len(elite_games), "under_mkt_pct": elite_pct, "avg_market_delta": elite_delta},
            "standard": {"mkt_sample": len(standard_games), "under_mkt_pct": standard_pct, "avg_market_delta": standard_delta},
        },
        "over": {
            "sample": sum(1 for g in games if g["is_smart_edge_over"]),
            "mkt_sample": on,
            "market_over_pct": o_pct,
            "avg_market_delta": o_delta,
        }
    }

def build_signal_stats(save_to_dashboard: bool = True) -> dict:
    date_map = {}
    for f in sorted(DATA_DIR.glob("universal_predictions_2026-*.json")):
        d = f.stem.replace("universal_predictions_", "").replace("_v2", "")
        if "_v2" in f.stem:
            date_map[d] = f
        elif d not in date_map:
            date_map[d] = f
    target_files = [date_map[d] for d in sorted(date_map.keys())]

    all_graded = []

    for fpath in target_files:
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

            # Classify archetype segment
            seg_code, seg_label = classify_basketball_segment(p.get("country"), p.get("league"), p.get("home_team"), p.get("away_team"))

            # Check Drag-Down
            band = str(p.get("confidence_score_band") or p.get("band") or "").strip()
            floor_st = str(p.get("floor_status") or "")
            is_dd = bool(p.get("is_drag_down") or (floor_st.startswith("WEAK") and "[AVOID]" in band))

            # Extract dual model metrics
            adv_tot = p.get("adv_total")
            srs_tot = p.get("srs_total")
            try:
                adv_tot = float(adv_tot) if adv_tot is not None else None
            except (ValueError, TypeError):
                adv_tot = None
            try:
                srs_tot = float(srs_tot) if srs_tot is not None else None
            except (ValueError, TypeError):
                srs_tot = None

            adv_e = p.get("adv_edge")
            srs_e = p.get("srs_edge")
            if mkt is not None:
                if adv_e is None and adv_tot is not None:
                    adv_e = round(adv_tot - mkt, 1)
                if srs_e is None and srs_tot is not None:
                    srs_e = round(srs_tot - mkt, 1)

            div = p.get("model_divergence")
            if div is None and adv_tot is not None and srs_tot is not None:
                div = round(abs(adv_tot - srs_tot), 1)

            agreement = p.get("model_agreement")
            if not agreement and adv_e is not None and srs_e is not None:
                if adv_e < 0 and srs_e < 0:
                    agreement = "CONFIRMED_UNDER"
                elif adv_e > 0 and srs_e > 0:
                    agreement = "CONFIRMED_OVER"
                elif (adv_e > 0 and srs_e < 0) or (adv_e < 0 and srs_e > 0):
                    agreement = "DISCORDANT"

            bt = p.get("buffer_tier")
            bs = p.get("buffer_score")
            cb = band
            if not bt and bs is not None:
                bs_val = float(bs)
                bt = ("[ELITE BUFFER]" if bs_val >= 40 else
                      "[STRONG BUFFER]" if bs_val >= 28 else
                      "[NEUTRAL]" if bs_val >= 16 else
                      "[MARGINAL]" if bs_val > 0 else "[AVOID]")
            is_strong_buf = bt in ("[ELITE BUFFER]", "[STRONG BUFFER]") or (bs is not None and bs >= 28)

            # Segment-specific Smart Edge evaluation:
            se_sig = None
            se_tier = "STANDARD"
            se_trigger = ""

            # Check if game object was already stamped with valid trigger and matching segment
            se = p.get("smart_edge")
            if isinstance(se, dict) and se.get("trigger") and se.get("segment") == seg_code:
                se_sig = se.get("signal")
                se_tier = se.get("tier", "STANDARD")
                se_trigger = se.get("trigger", "")
            else:
                # Dynamic multi-engine evaluation per segment:
                if seg_code == "NBA_MEN":
                    is_smart_over = is_strong_buf and cb in ("[LOW]", "[AVOID]")
                    if is_smart_over or (adv_e is not None and adv_e >= 3.0 and srs_e is not None and srs_e >= 3.0):
                        se_sig = "OVER"
                        se_tier = "ELITE"
                        se_trigger = "NBA_PACE_OVER"

                elif seg_code == "NCAA_MEN":
                    is_adv_o_srs_u = (adv_e is not None and srs_e is not None and adv_e > 0 and srs_e < 0)
                    is_discordant = is_adv_o_srs_u and cb != "[MODERATE]" and ((div is not None and div >= 3.1) or cb == "[SOLID]")
                    is_smart_over = is_strong_buf and cb in ("[LOW]", "[AVOID]")
                    if is_discordant:
                        se_sig = "UNDER"
                        se_tier = "ULTRA"
                        se_trigger = "NCAA_DISCORDANT_UNDER"
                    elif agreement == "CONFIRMED_UNDER" and cb != "[LOW]" and not is_smart_over:
                        se_sig = "UNDER"
                        se_tier = "ELITE"
                        se_trigger = "NCAA_COLLEGE_UNDER"

                elif seg_code == "NBA_GLEAGUE":
                    if mkt is not None and mkt >= 228.0 and (srs_e is None or srs_e <= 0 or adv_e is None or adv_e <= 0):
                        se_sig = "UNDER"
                        se_tier = "ELITE"
                        se_trigger = "GLEAGUE_INFLATED_UNDER"

                elif seg_code == "FIBA_CORE":
                    is_adv_o_srs_u = (adv_e is not None and srs_e is not None and adv_e > 0 and srs_e < 0)
                    is_discordant = is_adv_o_srs_u and cb != "[MODERATE]" and ((div is not None and div >= 3.1) or cb == "[SOLID]")
                    is_smart_over = is_strong_buf and cb in ("[LOW]", "[AVOID]")
                    is_dual_u = agreement == "CONFIRMED_UNDER" and cb != "[LOW]" and not is_smart_over and (cb in ("[SOLID]", "[MODERATE]") or (div is not None and 5.0 <= div <= 10.0))

                    if is_discordant:
                        se_sig = "UNDER"
                        se_tier = "ULTRA"
                        se_trigger = "DISCORDANT_SRS_UNDER"
                    elif is_smart_over:
                        se_sig = "OVER"
                        se_tier = "STANDARD"
                        se_trigger = "BUFFER_SCORING_LEAD"
                    elif is_dual_u:
                        se_sig = "UNDER"
                        se_tier = "ELITE"
                        se_trigger = "DUAL_CONSENSUS_UNDER"

            all_graded.append({
                "date": date_str,
                "league": p.get("league", "Unknown"),
                "country": p.get("country", "Other"),
                "league_id": p.get("league_id"),
                "home": p.get("home_team"),
                "away": p.get("away_team"),
                "segment": seg_code,
                "segment_label": seg_label,
                "actual_total": actual_total,
                "model_total": mt,
                "market_total": mkt,
                "signed_delta": actual_total - mt,
                "is_clash": bool(p.get("is_clash")),
                "clash_trigger": p.get("clash_trigger", ""),
                "is_shootout": bool(p.get("is_shootout")),
                "shootout_trigger": p.get("shootout_trigger", ""),
                "is_drag_down": is_dd,
                "is_smart_edge_under": se_sig == "UNDER",
                "is_smart_edge_over": se_sig == "OVER",
                "smart_edge_tier": se_tier,
                "smart_edge_trigger": se_trigger,
                "winner_hit": bool(pred_winner and actual_winner and pred_winner == actual_winner),
            })

    total = len(all_graded)
    if total == 0:
        print("  [WARN] No graded basketball games found.")
        return {}

    # Partition games by archetype
    fiba_games = [r for r in all_graded if r["segment"] == "FIBA_CORE"]
    nba_games = [r for r in all_graded if r["segment"] == "NBA_MEN"]
    ncaa_games = [r for r in all_graded if r["segment"] == "NCAA_MEN"]
    gleague_games = [r for r in all_graded if r["segment"] == "NBA_GLEAGUE"]

    # Top-level baseline & signals (calibrated to FIBA_CORE for backward compatibility)
    fiba_total = len(fiba_games)
    fiba_mkt = [r for r in fiba_games if r["market_total"] is not None]

    base_under_mod = sum(1 for r in fiba_games if r["actual_total"] < r["model_total"])
    base_delta_mod = sum(r["signed_delta"] for r in fiba_games) / fiba_total if fiba_total else 0.0
    base_ml_hit = sum(1 for r in fiba_games if r["winner_hit"])

    base_under_mkt = sum(1 for r in fiba_mkt if r["actual_total"] < r["market_total"])
    base_delta_mkt = (sum(r["actual_total"] - r["market_total"] for r in fiba_mkt) / len(fiba_mkt)) if fiba_mkt else 0.0

    # Clash of the Inefficient (⚡) on FIBA Core
    clash_games = [r for r in fiba_games if r["is_clash"]]
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

    # Shootout / Glass Cannons (🔥) on FIBA Core
    so_games = [r for r in fiba_games if r["is_shootout"]]
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

        sharp_shootout = [r for r in so_games if r["shootout_trigger"] == "SHARP SHOOTOUT"]
        sso_n = len(sharp_shootout)
        sso_over = sum(1 for r in sharp_shootout if r["actual_total"] > r["model_total"])
        sso_delta = (sum(r["signed_delta"] for r in sharp_shootout) / sso_n) if sso_n else 0.0

        sso_mkt = [r for r in sharp_shootout if r["market_total"] is not None]
        ssom_n = len(sso_mkt)
        ssom_over = sum(1 for r in sso_mkt if r["actual_total"] > r["market_total"])
        ssom_delta = (sum(r["actual_total"] - r["market_total"] for r in sso_mkt) / ssom_n) if ssom_n else 0.0

        reg_shootout = [r for r in so_games if r["shootout_trigger"] != "SHARP SHOOTOUT"]
        rso_n = len(reg_shootout)
        rso_over = sum(1 for r in reg_shootout if r["actual_total"] > r["model_total"])
        rso_delta = (sum(r["signed_delta"] for r in reg_shootout) / rso_n) if rso_n else 0.0

        rso_mkt = [r for r in reg_shootout if r["market_total"] is not None]
        rsom_n = len(rso_mkt)
        rsom_over = sum(1 for r in rso_mkt if r["actual_total"] > r["market_total"])
        rsom_delta = (sum(r["actual_total"] - r["market_total"] for r in rso_mkt) / rsom_n) if rsom_n else 0.0

        shootout_stats = {
            "sample": so_n,
            "over_model_pct": round(so_over_mod / so_n * 100, 1),
            "under_model_pct": round(so_under_mod / so_n * 100, 1),
            "avg_score_delta": round(so_delta_mod, 1),
            "moneyline_pct": round(so_ml / so_n * 100, 1),
            "market_sample": som_n,
            "market_over_pct": round(som_over / som_n * 100, 1) if som_n else 0.0,
            "market_under_pct": round(som_under / som_n * 100, 1) if som_n else 0.0,
            "avg_market_delta": round(som_delta, 1),
            "sharp_shootout": {
                "sample": sso_n,
                "over_model_pct": round(sso_over / sso_n * 100, 1) if sso_n else 0.0,
                "avg_score_delta": round(sso_delta, 1),
                "mkt_sample": ssom_n,
                "over_mkt_pct": round(ssom_over / ssom_n * 100, 1) if ssom_n else 0.0,
                "avg_mkt_delta": round(ssom_delta, 1),
            },
            "regular": {
                "sample": rso_n,
                "over_model_pct": round(rso_over / rso_n * 100, 1) if rso_n else 0.0,
                "avg_score_delta": round(rso_delta, 1),
                "mkt_sample": rsom_n,
                "over_mkt_pct": round(rsom_over / rsom_n * 100, 1) if rsom_n else 0.0,
                "avg_mkt_delta": round(rsom_delta, 1),
            }
        }

    # Drag-Down Under (⚓) on FIBA Core
    dd_games = [r for r in fiba_games if r["is_drag_down"]]
    dd_n = len(dd_games)
    drag_down_stats = {}
    if dd_n > 0:
        dd_under_mod = sum(1 for r in dd_games if r["actual_total"] < r["model_total"])
        dd_over_mod = sum(1 for r in dd_games if r["actual_total"] > r["model_total"])
        dd_delta_mod = sum(r["signed_delta"] for r in dd_games) / dd_n
        dd_ml = sum(1 for r in dd_games if r["winner_hit"])

        dd_mkt = [r for r in dd_games if r["market_total"] is not None]
        ddm_n = len(dd_mkt)
        ddm_under = sum(1 for r in dd_mkt if r["actual_total"] < r["market_total"])
        ddm_over = sum(1 for r in dd_mkt if r["actual_total"] > r["market_total"])
        ddm_delta = (sum(r["actual_total"] - r["market_total"] for r in dd_mkt) / ddm_n) if ddm_n else 0.0

        drag_down_stats = {
            "sample": dd_n,
            "mkt_sample": ddm_n,
            "under_mkt_pct": round(ddm_under / ddm_n * 100, 1) if ddm_n else 0.0,
            "over_mkt_pct": round(ddm_over / ddm_n * 100, 1) if ddm_n else 0.0,
            "avg_market_delta": round(ddm_delta, 1),
            "under_model_pct": round(dd_under_mod / dd_n * 100, 1),
            "over_model_pct": round(dd_over_mod / dd_n * 100, 1),
            "avg_score_delta": round(dd_delta_mod, 1),
            "moneyline_pct": round(dd_ml / dd_n * 100, 1),
        }

    # Segments Breakdown
    fiba_stats = compute_segment_stats(fiba_games, "FIBA Core (40m)")
    nba_stats = compute_segment_stats(nba_games, "NBA Men (48m)")
    ncaa_stats = compute_segment_stats(ncaa_games, "NCAA Men (College)")
    gleague_stats = compute_segment_stats(gleague_games, "NBA G-League")

    # Core FIBA smart edge stats for root backwards compatibility
    smart_edge_stats = {
        "sample": fiba_stats["under"]["sample"] + fiba_stats["over"]["sample"],
        "under": fiba_stats["under"],
        "over": fiba_stats["over"],
    }

    # Automated League Warnings (Dynamic Threshold: 55.0% WR with Sample >= 3)
    league_smart_data = defaultdict(lambda: {
        "country": "", "league": "", "league_id": None, "segment": "",
        "total_smart_plays": 0, "total_smart_hits": 0,
        "under_plays": 0, "under_hits": 0,
        "over_plays": 0, "over_hits": 0,
        "net_units": 0.0
    })

    smart_graded_with_mkt = [r for r in all_graded if r["market_total"] is not None and (r["is_smart_edge_under"] or r["is_smart_edge_over"])]
    for r in smart_graded_with_mkt:
        c = r.get("country", "Other")
        l = r.get("league", "Unknown")
        key = f"{c} — {l}" if c and c != "Other" else l
        entry = league_smart_data[key]
        entry["country"] = c
        entry["league"] = l
        entry["league_id"] = r.get("league_id")
        entry["segment"] = r["segment"]
        entry["total_smart_plays"] += 1

        hit = False
        delta = r["actual_total"] - r["market_total"]
        if r["is_smart_edge_under"]:
            entry["under_plays"] += 1
            if delta < 0:
                hit = True
                entry["under_hits"] += 1
                entry["net_units"] += 0.9091
            elif delta > 0:
                entry["net_units"] -= 1.0
        elif r["is_smart_edge_over"]:
            entry["over_plays"] += 1
            if delta > 0:
                hit = True
                entry["over_hits"] += 1
                entry["net_units"] += 0.9091
            elif delta < 0:
                entry["net_units"] -= 1.0

        if hit:
            entry["total_smart_hits"] += 1

    WARN_THRESHOLD = 55.0
    MIN_SAMPLE = 3
    league_warnings = {}

    for lkey, d in league_smart_data.items():
        n = d["total_smart_plays"]
        if n >= MIN_SAMPLE:
            wr = round(d["total_smart_hits"] / n * 100, 1)
            u_wr = round(d["under_hits"] / d["under_plays"] * 100, 1) if d["under_plays"] else None
            o_wr = round(d["over_hits"] / d["over_plays"] * 100, 1) if d["over_plays"] else None

            if wr < WARN_THRESHOLD:
                if d["over_plays"] >= 2 and o_wr is not None and o_wr < 40.0:
                    reason = f"Pace Hazard: Smart Over hit rate is only {o_wr}% ({d['over_hits']}/{d['over_plays']}). Tactical half-court tempo limits offensive breakouts."
                elif d["under_plays"] >= 2 and u_wr is not None and u_wr < 40.0:
                    reason = f"Volatility Hazard: Smart Under hit rate is only {u_wr}% ({d['under_hits']}/{d['under_plays']}). High second-half pace breaks Under suppression."
                else:
                    reason = f"Below Benchmark: Combined Smart Filter hit rate is {wr}% ({d['total_smart_hits']}/{n} hits) vs. {WARN_THRESHOLD}% threshold."

                warn_obj = {
                    "status": "WARNING",
                    "threshold_pct": WARN_THRESHOLD,
                    "min_sample": MIN_SAMPLE,
                    "sample": n,
                    "hits": d["total_smart_hits"],
                    "win_rate": wr,
                    "under_plays": d["under_plays"],
                    "under_hits": d["under_hits"],
                    "under_wr": u_wr,
                    "over_plays": d["over_plays"],
                    "over_hits": d["over_hits"],
                    "over_wr": o_wr,
                    "net_units": round(d["net_units"], 2),
                    "reason": reason,
                    "country": d["country"],
                    "league": d["league"],
                    "segment": d["segment"]
                }
                league_warnings[lkey] = warn_obj
                # Also index by pure league name for robust frontend matching
                if d["league"] and d["league"] != lkey:
                    league_warnings[d["league"]] = warn_obj

    payload = {
        "updated_at": datetime.now().isoformat(),
        "scope": "MULTI_SEGMENT_CALIBRATED",
        "scope_description": "Empirically audited basketball performance benchmarks partitioned by league archetype",
        "total_graded_games": total,
        "baseline": {
            "moneyline_pct": round(base_ml_hit / fiba_total * 100, 1) if fiba_total else 0.0,
            "under_model_pct": round(base_under_mod / fiba_total * 100, 1) if fiba_total else 0.0,
            "avg_signed_delta": round(base_delta_mod, 1),
            "under_market_pct": round(base_under_mkt / len(fiba_mkt) * 100, 1) if fiba_mkt else 0.0,
            "avg_market_delta": round(base_delta_mkt, 1),
        },
        "clash": clash_stats,
        "shootout": shootout_stats,
        "drag_down": drag_down_stats,
        "smart_edge": smart_edge_stats,
        "league_warnings": league_warnings,
        "segments": {
            "FIBA_CORE": fiba_stats,
            "NBA_MEN": nba_stats,
            "NCAA_MEN": ncaa_stats,
            "NBA_GLEAGUE": gleague_stats,
        }
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
    print("\n🏀 Aggregating Basketball Signal Statistics (Multi-Segment Architecture)...")
    stats = build_signal_stats(save_to_dashboard=True)
    print(f"  Total Graded Games (All): {stats.get('total_graded_games', 0)}")
    segs = stats.get("segments", {})
    for k, s in segs.items():
        u = s.get("under", {})
        o = s.get("over", {})
        print(f"  [{k}] {s.get('name')}: Sample={s.get('sample')} (Mkt={s.get('market_sample')}) | Under={u.get('market_under_pct')}% (N={u.get('mkt_sample')}, {u.get('avg_market_delta')}p) | Over={o.get('market_over_pct')}% (N={o.get('mkt_sample')}, +{o.get('avg_market_delta')}p)")
    
    warns = stats.get("league_warnings", {})
    unique_warns = {v["league"]: v for v in warns.values() if isinstance(v, dict)}
    print(f"  [AUTOMATED LEAGUE WARNINGS] Flagged Leagues (N >= 3, WR < 55.0%): {len(unique_warns)}")
    for l, v in sorted(unique_warns.items(), key=lambda x: x[1]["win_rate"]):
        print(f"    ⚠️  {v['country']} — {v['league']}: {v['win_rate']}% WR ({v['hits']}/{v['sample']}) | {v['reason']}")
    print("Done.\n")
