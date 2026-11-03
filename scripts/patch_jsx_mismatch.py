"""Simplify mismatch UI in BasketballRow.jsx:
- Keep only isMismatch, remove riskLevel/mismatchBadge/mismatchTrigger/recommendedStake/totalsAdvice
- Replace complex badge pill with a clean 'Mismatch' label
- Remove the advisory callout card inside BY THE NUMBERS
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

JSX_PATH = r"c:\Users\markk\OneDrive\Desktop\CODE\Sports Analytics\src\components\BasketballRow.jsx"

with open(JSX_PATH, "r", encoding="utf-8") as f:
    text = f.read()

# --- 1. Slim down the variable block ---
OLD_VARS = (
    "  // Mismatch & Responsible Staking Badge\n"
    "  const isMismatch = Boolean(primary.is_mismatch ?? consolidatedGame?.is_mismatch)\n"
    "  const riskLevel = primary.risk_level || consolidatedGame?.risk_level || 'LOW'\n"
    "  const mismatchBadge = primary.mismatch_badge || consolidatedGame?.mismatch_badge || ''\n"
    "  const mismatchTrigger = primary.mismatch_trigger || consolidatedGame?.mismatch_trigger || ''\n"
    "  const recommendedStake = primary.recommended_stake || consolidatedGame?.recommended_stake || '1.00u'\n"
    "  const totalsAdvice = primary.totals_advice || consolidatedGame?.totals_advice || ''\n"
)
NEW_VARS = (
    "  // Conference Tier Mismatch indicator\n"
    "  const isMismatch = Boolean(primary.is_mismatch ?? consolidatedGame?.is_mismatch)\n"
)

# --- 2. Replace complex badge pill with clean label ---
OLD_BADGE = (
    "            {isMismatch && (\n"
    "              <span\n"
    "                style={{\n"
    "                  fontSize: '9.5px',\n"
    "                  lineHeight: 1,\n"
    "                  fontWeight: 800,\n"
    "                  background: riskLevel === 'EXTREME' ? 'rgba(239, 68, 68, 0.15)' : 'rgba(245, 158, 11, 0.15)',\n"
    "                  color: riskLevel === 'EXTREME' ? '#ef4444' : '#f59e0b',\n"
    "                  border: riskLevel === 'EXTREME' ? '1px solid rgba(239, 68, 68, 0.35)' : '1px solid rgba(245, 158, 11, 0.35)',\n"
    "                  borderRadius: '3px',\n"
    "                  padding: '1px 4px',\n"
    "                  cursor: 'help'\n"
    "                }}\n"
    "                title={`${mismatchBadge || 'Buy Game Mismatch'}: ${mismatchTrigger || 'High blowout variance'}. Recommended Stake: ${recommendedStake}. Advice: ${totalsAdvice}`}\n"
    "              >\n"
    "                {mismatchBadge || (riskLevel === 'EXTREME' ? '⚠️ Buy Game (0.25u)' : '⚠️ Mismatch (0.5u)')}\n"
    "              </span>\n"
    "            )}\n"
)
NEW_BADGE = (
    "            {isMismatch && (\n"
    "              <span\n"
    "                style={{\n"
    "                  fontSize: '9.5px',\n"
    "                  lineHeight: 1,\n"
    "                  fontWeight: 700,\n"
    "                  background: 'rgba(245, 158, 11, 0.12)',\n"
    "                  color: '#f59e0b',\n"
    "                  border: '1px solid rgba(245, 158, 11, 0.3)',\n"
    "                  borderRadius: '3px',\n"
    "                  padding: '1px 4px',\n"
    "                }}\n"
    "              >\n"
    "                Mismatch\n"
    "              </span>\n"
    "            )}\n"
)

# --- 3. Remove advisory callout card from BY THE NUMBERS ---
OLD_CARD = (
    "                {isMismatch && (\n"
    "                  <div style={{\n"
    "                    margin: '8px 0 12px',\n"
    "                    padding: '8px 12px',\n"
    "                    background: riskLevel === 'EXTREME' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(245, 158, 11, 0.1)',\n"
    "                    borderLeft: `4px solid ${riskLevel === 'EXTREME' ? '#ef4444' : '#f59e0b'}`,\n"
    "                    borderRadius: '4px',\n"
    "                    fontSize: '12px'\n"
    "                  }}>\n"
    "                    <div style={{ fontWeight: 800, color: riskLevel === 'EXTREME' ? '#ef4444' : '#f59e0b', display: 'flex', alignItems: 'center', gap: '6px' }}>\n"
    "                      <span>⚠️</span>\n"
    "                      <span>{riskLevel === 'EXTREME' ? 'BUY GAME / EXTREME MISMATCH' : 'HIGH SPREAD MISMATCH'}</span>\n"
    "                      <span style={{ marginLeft: 'auto', background: riskLevel === 'EXTREME' ? '#ef4444' : '#f59e0b', color: '#fff', padding: '1px 6px', borderRadius: '3px', fontSize: '10px' }}>\n"
    "                        STAKE: {recommendedStake}\n"
    "                      </span>\n"
    "                    </div>\n"
    "                    <div style={{ color: '#cbd5e1', marginTop: '4px', fontSize: '11px' }}>\n"
    "                      <strong>Trigger:</strong> {mismatchTrigger}\n"
    "                    </div>\n"
    "                    <div style={{ color: '#94a3b8', marginTop: '2px', fontSize: '10.5px' }}>\n"
    "                      <strong>Totals Advice:</strong> {totalsAdvice || 'Full-game totals have high variance in blowout conditions. Lean Team Totals or PASS.'}\n"
    "                    </div>\n"
    "                  </div>\n"
    "                )}\n"
)
NEW_CARD = ""  # remove entirely

changes = 0
for old, new, label in [
    (OLD_VARS, NEW_VARS, "variable block"),
    (OLD_BADGE, NEW_BADGE, "badge pill"),
    (OLD_CARD, NEW_CARD, "advisory card"),
]:
    normalized = text.replace("\r\n", "\n")
    if old in normalized:
        normalized = normalized.replace(old, new, 1)
        text = normalized.replace("\n", "\r\n")
        print(f"  Patched: {label}")
        changes += 1
    else:
        print(f"  NOT FOUND (may already be patched): {label}")

if changes:
    with open(JSX_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"\nSaved {JSX_PATH} ({changes} change(s))")
else:
    print("No changes made.")

