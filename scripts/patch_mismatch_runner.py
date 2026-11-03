"""Strips verbose mismatch fields from the runner, keeping only is_mismatch + mismatch_info."""
import sys
sys.stdout.reconfigure(encoding="utf-8")

RUNNERS = [
    r"c:\Users\markk\OneDrive\Desktop\CODE\ncaa-api\run_basketball_daily_v2.py",
    r"c:\Users\markk\OneDrive\Desktop\CODE\ncaa-api\run_basketball_daily.py",
]

OLD_BLOCK = (
    '                    "is_mismatch":      mismatch_info["is_mismatch"],\n'
    '                    "risk_level":       mismatch_info["risk_level"],\n'
    '                    "mismatch_badge":   mismatch_info["short_badge"],\n'
    '                    "mismatch_trigger": mismatch_info["trigger"],\n'
    '                    "recommended_stake": mismatch_info["recommended_stake"],\n'
    '                    "totals_advice":    mismatch_info["totals_advice"],\n'
    '                    "mismatch_info":    mismatch_info,\n'
)

NEW_BLOCK = (
    '                    "is_mismatch":  mismatch_info["is_mismatch"],\n'
    '                    "mismatch_info": mismatch_info,\n'
)

for path in RUNNERS:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    # Normalise CRLF -> LF for matching, then restore
    crlf = "\r\n" in text
    text_lf = text.replace("\r\n", "\n")

    if OLD_BLOCK in text_lf:
        text_lf = text_lf.replace(OLD_BLOCK, NEW_BLOCK, 1)
        out = text_lf.replace("\n", "\r\n") if crlf else text_lf
        with open(path, "w", encoding="utf-8") as f:
            f.write(out)
        print(f"Patched: {path}")
    else:
        print(f"Block not found (may already be patched): {path}")
