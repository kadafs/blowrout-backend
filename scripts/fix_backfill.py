"""Patch backfill_mismatches.py to use the simplified mismatch detector output."""
with open('scripts/backfill_mismatches.py', 'rb') as f:
    raw = f.read()

old = (
    b"        p['is_mismatch'] = info['is_mismatch']\r\n"
    b"        p['risk_level'] = info['risk_level']\r\n"
    b"        p['mismatch_badge'] = info['short_badge']\r\n"
    b"        p['mismatch_trigger'] = info['trigger']\r\n"
    b"        p['recommended_stake'] = info['recommended_stake']\r\n"
    b"        p['totals_advice'] = info['totals_advice']\r\n"
    b"        p['mismatch_info'] = info\r\n"
)
new = (
    b"        p['is_mismatch'] = info['is_mismatch']\r\n"
    b"        p['mismatch_info'] = info\r\n"
    b"        for _stale in ('risk_level', 'mismatch_badge', 'mismatch_trigger', 'recommended_stake', 'totals_advice'):\r\n"
    b"            p.pop(_stale, None)\r\n"
)
assert old in raw, 'Block not found'
raw = raw.replace(old, new, 1)
with open('scripts/backfill_mismatches.py', 'wb') as f:
    f.write(raw)
print('Patched OK')
