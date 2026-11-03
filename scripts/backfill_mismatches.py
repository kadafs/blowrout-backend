import sys, os, glob, json
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
sys.path.append(os.path.abspath('.'))

from core.mismatch_detector import detect_mismatch

files = glob.glob('data/basketball/universal_predictions_*.json')
print(f"Found {len(files)} basketball prediction files to backfill.")

total_updated = 0
total_mismatches = 0

for fpath in files:
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception as e:
        print(f"  Error reading {fpath}: {e}")
        continue

    preds = data.get('predictions', [])
    updated_file = False

    for p in preds:
        ht = p.get('home_team')
        at = p.get('away_team')
        hid = p.get('home_id')
        aid = p.get('away_id')
        lid = p.get('league_id')
        xpts_h = p.get('xpts_h') or 0
        xpts_a = p.get('xpts_a') or 0
        spread = abs(xpts_h - xpts_a)
        mkt_spr = p.get('market_spread')
        
        # Check stats in match_center
        mc = p.get('match_center', {})
        sH = mc.get('statsH', {})
        sA = mc.get('statsA', {})
        srs_h = sH.get('srs_rating')
        srs_a = sA.get('srs_rating')

        info = detect_mismatch(
            home_team=ht,
            away_team=at,
            home_id=hid,
            away_id=aid,
            league_id=lid,
            projected_spread=spread,
            market_spread=mkt_spr,
            srs_h=srs_h,
            srs_a=srs_a
        )

        p['is_mismatch'] = info['is_mismatch']
        p['mismatch_info'] = info
        for _stale in ('risk_level', 'mismatch_badge', 'mismatch_trigger', 'recommended_stake', 'totals_advice'):
            p.pop(_stale, None)

        if info['is_mismatch']:
            total_mismatches += 1
        total_updated += 1
        updated_file = True

    if updated_file:
        with open(fpath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        print(f"  Saved {fpath} ({len(preds)} predictions).")

print(f"\nFinished backfilling! Updated {total_updated} prediction records ({total_mismatches} flagged as mismatches).")

