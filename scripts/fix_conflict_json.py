"""
Fix git merge conflict markers in a JSON file.
Keeps the HEAD (ours) section and discards the incoming (theirs) section.
"""
import sys, re, json
sys.stdout.reconfigure(encoding="utf-8")

path = r"data/basketball/universal_predictions_2026-11-03_v2.json"

with open(path, encoding="utf-8") as f:
    text = f.read()

# Remove all conflict blocks, keeping only the HEAD (<<<< ... =======) side
conflict_pattern = re.compile(
    r'<<<<<<< HEAD\n(.*?)=======\n.*?>>>>>>> [^\n]+\n',
    re.DOTALL
)

fixed, count = conflict_pattern.subn(r'\1', text)
print(f"Resolved {count} conflict block(s)")

# Validate JSON
try:
    json.loads(fixed)
    print("JSON valid after fix")
    with open(path, "w", encoding="utf-8") as f:
        f.write(fixed)
    print(f"Saved {path}")
except json.JSONDecodeError as e:
    print(f"Still invalid JSON: {e}")
    # Show context around the error
    lines = fixed.splitlines()
    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 3)
    for i, l in enumerate(lines[start:end], start=start+1):
        print(f"  {i}: {repr(l)}")

