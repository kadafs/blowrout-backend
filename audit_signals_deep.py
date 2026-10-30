import glob
import json
import os
import sys
from collections import defaultdict

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

files = sorted(glob.glob("data/basketball/universal_predictions_2026-*.json"))
v1_files = [f for f in files if not f.endswith("_v2.json")]

all_graded = []
clash_matches = []
shootout_matches = []

for f in v1_files:
    try:
        with open(f, "r", encoding="utf-8") as fp:
            d = json.load(fp)
    except Exception:
        continue
    preds = d.get("predictions", []) if isinstance(d, dict) else d
    for p in preds:
        h_score = p.get("home_score") if p.get("home_score") is not None else p.get("actual_home_score")
        a_score = p.get("away_score") if p.get("away_score") is not None else p.get("actual_away_score")
        if h_score is None or a_score is None:
            continue
        try:
            h_score, a_score = float(h_score), float(a_score)
        except (ValueError, TypeError):
            continue
        actual_total = h_score + a_score

        mt = p.get("model_total")
        if mt is None and isinstance(p.get("model"), dict):
            mt = p.get("model", {}).get("total")
        if mt is None:
            continue
        try:
            mt = float(mt)
        except (ValueError, TypeError):
            continue

        mkt = p.get("market_total")
        if mkt in (145.5, 230.0, None, 0, "None", ""):
            mkt = None
        else:
            try:
                mkt = float(mkt)
            except (ValueError, TypeError):
                mkt = None

        row = {
            "date": p.get("date") or os.path.basename(f).replace("universal_predictions_", "").replace(".json", ""),
            "league": p.get("league", "Unknown"),
            "home": p.get("home_team"),
            "away": p.get("away_team"),
            "actual_total": actual_total,
            "model_total": mt,
            "market_total": mkt,
            "model_delta": actual_total - mt,
            "market_delta": (actual_total - mkt) if mkt is not None else None,
            "is_clash": bool(p.get("is_clash")),
            "clash_trigger": p.get("clash_trigger", ""),
            "is_shootout": bool(p.get("is_shootout")),
            "shootout_trigger": p.get("shootout_trigger", ""),
        }
        all_graded.append(row)
        if row["is_clash"]:
            clash_matches.append(row)
        if row["is_shootout"]:
            shootout_matches.append(row)

total_all = len(all_graded)
with_mkt_all = [r for r in all_graded if r["market_total"] is not None]

base_under_mod = sum(1 for r in all_graded if r["actual_total"] < r["model_total"])
base_over_mod = sum(1 for r in all_graded if r["actual_total"] > r["model_total"])
base_under_mkt = sum(1 for r in with_mkt_all if r["actual_total"] < r["market_total"])
base_over_mkt = sum(1 for r in with_mkt_all if r["actual_total"] > r["market_total"])

print("=" * 80)
print(f"BASKETBALL SIGNAL RE-AUDIT REPORT (Total Graded Games: {total_all})")
print("=" * 80)
print(f"Baseline (All {total_all} Games):")
print(f"  Under Model: {base_under_mod}/{total_all} ({base_under_mod/total_all*100:.1f}%) | Avg Delta: {sum(r['model_delta'] for r in all_graded)/total_all:+.1f} pts")
print(f"  Under Market ({len(with_mkt_all)} Games with lines): {base_under_mkt}/{len(with_mkt_all)} ({base_under_mkt/len(with_mkt_all)*100:.1f}%) | Over Market: {base_over_mkt}/{len(with_mkt_all)} ({base_over_mkt/len(with_mkt_all)*100:.1f}%) | Avg Delta: {sum(r['market_delta'] for r in with_mkt_all)/len(with_mkt_all):+.1f} pts")

print("\n" + "#" * 80)
print("1. CLASH OF THE INEFFICIENT (⚡) AUDIT")
print("#" * 80)

c_n = len(clash_matches)
c_under_mod = sum(1 for r in clash_matches if r["actual_total"] < r["model_total"])
c_over_mod = sum(1 for r in clash_matches if r["actual_total"] > r["model_total"])
c_delta_mod = sum(r["model_delta"] for r in clash_matches) / c_n if c_n else 0

c_mkt = [r for r in clash_matches if r["market_total"] is not None]
cm_n = len(c_mkt)
c_under_mkt = sum(1 for r in c_mkt if r["actual_total"] < r["market_total"])
c_over_mkt = sum(1 for r in c_mkt if r["actual_total"] > r["market_total"])
c_delta_mkt = sum(r["market_delta"] for r in c_mkt) / cm_n if cm_n else 0

print(f"Overall Clash Sample: N = {c_n}")
print(f"  vs Model Total:")
print(f"    UNDER Model: {c_under_mod}/{c_n} ({c_under_mod/c_n*100:.1f}%)")
print(f"    OVER Model:  {c_over_mod}/{c_n} ({c_over_mod/c_n*100:.1f}%)")
print(f"    Avg Delta (Actual - Model): {c_delta_mod:+.1f} pts")
print(f"  vs Market Line (N = {cm_n} with market line):")
print(f"    UNDER Market: {c_under_mkt}/{cm_n} ({c_under_mkt/cm_n*100:.1f}%)")
print(f"    OVER Market:  {c_over_mkt}/{cm_n} ({c_over_mkt/cm_n*100:.1f}%)")
print(f"    Avg Delta (Actual - Market): {c_delta_mkt:+.1f} pts")

# Split by trigger
sc = [r for r in clash_matches if r["clash_trigger"] == "SHARP OVER"]
rc = [r for r in clash_matches if r["clash_trigger"] != "SHARP OVER"]

print("\n  -- Sub-segment: SHARP OVER Clash (Model projected >= 7 pts above market) --")
sc_n = len(sc)
sc_under_mod = sum(1 for r in sc if r["actual_total"] < r["model_total"])
sc_delta_mod = sum(r["model_delta"] for r in sc) / sc_n if sc_n else 0
sc_mkt = [r for r in sc if r["market_total"] is not None]
scm_n = len(sc_mkt)
sc_under_mkt = sum(1 for r in sc_mkt if r["actual_total"] < r["market_total"])
sc_over_mkt = sum(1 for r in sc_mkt if r["actual_total"] > r["market_total"])
sc_delta_mkt = sum(r["market_delta"] for r in sc_mkt) / scm_n if scm_n else 0

print(f"    Sample: N = {sc_n}")
print(f"    UNDER Model: {sc_under_mod}/{sc_n} ({sc_under_mod/sc_n*100:.1f}%) | Avg Delta: {sc_delta_mod:+.1f} pts")
print(f"    UNDER Market: {sc_under_mkt}/{scm_n} ({sc_under_mkt/scm_n*100:.1f}%) | OVER Market: {sc_over_mkt}/{scm_n} ({sc_over_mkt/scm_n*100:.1f}%) | Avg Delta: {sc_delta_mkt:+.1f} pts")

print("\n  -- Sub-segment: REGULAR CLASH (Market within 7 pts of model, or no market line) --")
rc_n = len(rc)
rc_under_mod = sum(1 for r in rc if r["actual_total"] < r["model_total"])
rc_delta_mod = sum(r["model_delta"] for r in rc) / rc_n if rc_n else 0
rc_mkt = [r for r in rc if r["market_total"] is not None]
rcm_n = len(rc_mkt)
rc_under_mkt = sum(1 for r in rc_mkt if r["actual_total"] < r["market_total"])
rc_over_mkt = sum(1 for r in rc_mkt if r["actual_total"] > r["market_total"])
rc_delta_mkt = sum(r["market_delta"] for r in rc_mkt) / rcm_n if rcm_n else 0

print(f"    Sample: N = {rc_n}")
print(f"    UNDER Model: {rc_under_mod}/{rc_n} ({rc_under_mod/rc_n*100:.1f}%) | Avg Delta: {rc_delta_mod:+.1f} pts")
print(f"    UNDER Market: {rc_under_mkt}/{rcm_n} ({rc_under_mkt/rcm_n*100:.1f}%) | OVER Market: {rc_over_mkt}/{rcm_n} ({rc_over_mkt/rcm_n*100:.1f}%) | Avg Delta: {rc_delta_mkt:+.1f} pts")

# Monthly trend for Clash
print("\n  -- Clash Monthly Breakdown --")
clash_by_month = defaultdict(list)
for r in clash_matches:
    m = r["date"][:7] if r["date"] else "Unknown"
    clash_by_month[m].append(r)

for m in sorted(clash_by_month.keys()):
    items = clash_by_month[m]
    k_n = len(items)
    u_mod = sum(1 for r in items if r["actual_total"] < r["model_total"])
    m_items = [r for r in items if r["market_total"] is not None]
    u_mkt = sum(1 for r in m_items if r["actual_total"] < r["market_total"])
    print(f"    {m}: N = {k_n:3d} | Under Model: {u_mod}/{k_n} ({u_mod/k_n*100:.1f}%) | Under Mkt: {u_mkt}/{len(m_items)} ({u_mkt/len(m_items)*100:.1f}% if len(m_items)>0 else 0)")

print("\n" + "#" * 80)
print("2. SHOOTOUT / GLASS CANNONS (🔥) AUDIT")
print("#" * 80)

so_n = len(shootout_matches)
so_over_mod = sum(1 for r in shootout_matches if r["actual_total"] > r["model_total"])
so_under_mod = sum(1 for r in shootout_matches if r["actual_total"] < r["model_total"])
so_delta_mod = sum(r["model_delta"] for r in shootout_matches) / so_n if so_n else 0

so_mkt = [r for r in shootout_matches if r["market_total"] is not None]
som_n = len(so_mkt)
so_over_mkt = sum(1 for r in so_mkt if r["actual_total"] > r["market_total"])
so_under_mkt = sum(1 for r in so_mkt if r["actual_total"] < r["market_total"])
so_delta_mkt = sum(r["market_delta"] for r in so_mkt) / som_n if som_n else 0

print(f"Overall Shootout Sample: N = {so_n}")
print(f"  vs Market Line (N = {som_n} with market line):")
print(f"    OVER Market:  {so_over_mkt}/{som_n} ({so_over_mkt/som_n*100:.1f}%)")
print(f"    UNDER Market: {so_under_mkt}/{som_n} ({so_under_mkt/som_n*100:.1f}%)")
print(f"    Avg Delta (Actual - Market): {so_delta_mkt:+.1f} pts")
print(f"  vs Model Total:")
print(f"    OVER Model:  {so_over_mod}/{so_n} ({so_over_mod/so_n*100:.1f}%)")
print(f"    UNDER Model: {so_under_mod}/{so_n} ({so_under_mod/so_n*100:.1f}%)")
print(f"    Avg Delta (Actual - Model): {so_delta_mod:+.1f} pts")

# Split by trigger
sso = [r for r in shootout_matches if r["shootout_trigger"] == "SHARP SHOOTOUT"]
rso = [r for r in shootout_matches if r["shootout_trigger"] != "SHARP SHOOTOUT"]

print("\n  -- Sub-segment: SHARP SHOOTOUT (Model projected >= 5 pts above market) --")
sso_n = len(sso)
sso_over_mod = sum(1 for r in sso if r["actual_total"] > r["model_total"])
sso_delta_mod = sum(r["model_delta"] for r in sso) / sso_n if sso_n else 0
sso_mkt = [r for r in sso if r["market_total"] is not None]
ssom_n = len(sso_mkt)
sso_over_mkt = sum(1 for r in sso_mkt if r["actual_total"] > r["market_total"])
sso_under_mkt = sum(1 for r in sso_mkt if r["actual_total"] < r["market_total"])
sso_delta_mkt = sum(r["market_delta"] for r in sso_mkt) / ssom_n if ssom_n else 0

print(f"    Sample: N = {sso_n} (with Mkt: {ssom_n})")
print(f"    OVER Market:  {sso_over_mkt}/{ssom_n} ({sso_over_mkt/ssom_n*100:.1f}%) | Avg Market Delta: {sso_delta_mkt:+.1f} pts")
print(f"    OVER Model:   {sso_over_mod}/{sso_n} ({sso_over_mod/sso_n*100:.1f}%) | Avg Model Delta: {sso_delta_mod:+.1f} pts")

print("\n  -- Sub-segment: REGULAR SHOOTOUT (Market within 5 pts or no market line) --")
rso_n = len(rso)
rso_over_mod = sum(1 for r in rso if r["actual_total"] > r["model_total"])
rso_delta_mod = sum(r["model_delta"] for r in rso) / rso_n if rso_n else 0
rso_mkt = [r for r in rso if r["market_total"] is not None]
rsom_n = len(rso_mkt)
rso_over_mkt = sum(1 for r in rso_mkt if r["actual_total"] > r["market_total"])
rso_delta_mkt = sum(r["market_delta"] for r in rso_mkt) / rsom_n if rsom_n else 0

print(f"    Sample: N = {rso_n} (with Mkt: {rsom_n})")
if rsom_n:
    print(f"    OVER Market:  {rso_over_mkt}/{rsom_n} ({rso_over_mkt/rsom_n*100:.1f}%) | Avg Market Delta: {rso_delta_mkt:+.1f} pts")
print(f"    OVER Model:   {rso_over_mod}/{rso_n} ({rso_over_mod/rso_n*100:.1f}%) | Avg Model Delta: {rso_delta_mod:+.1f} pts")

# Monthly trend for Shootout
print("\n  -- Shootout Monthly Breakdown --")
so_by_month = defaultdict(list)
for r in shootout_matches:
    m = r["date"][:7] if r["date"] else "Unknown"
    so_by_month[m].append(r)

for m in sorted(so_by_month.keys()):
    items = so_by_month[m]
    k_n = len(items)
    m_items = [r for r in items if r["market_total"] is not None]
    o_mkt = sum(1 for r in m_items if r["actual_total"] > r["market_total"])
    o_mod = sum(1 for r in items if r["actual_total"] > r["model_total"])
    pct_mkt = (o_mkt / len(m_items) * 100) if m_items else 0
    pct_mod = (o_mod / k_n * 100) if k_n else 0
    print(f"    {m}: N = {k_n:2d} (Mkt N={len(m_items):2d}) | OVER Mkt: {o_mkt}/{len(m_items)} ({pct_mkt:.1f}%) | OVER Mod: {o_mod}/{k_n} ({pct_mod:.1f}%)")

