"""
core/confidence_score.py
=========================
Model Confidence Score (No Edge) — 75-point composite system normalized to 100.

Four Core Pillars (75 pts total → normalized 0 to 100):
    Volatility (Game Variance Ceiling): 27 pts (36%)
    MAE (Model Error Margin):           20 pts (27%)
    Directional Bias (Systematic Drift):20 pts (27%)
    Projected Spread (Blowout Risk):     8 pts (11%)

Optional / Auxiliary Diagnostic:
    Historical Buffer Floor Hit Rate (0.0 - 1.0) and Floor Status Badge ("ELITE", "OK", "WEAK")
    Tracked as an optional Over-floor metric, not incorporated into the primary confidence score.

Inputs per game:
    vol_a, vol_b     — std_dev_totals for home and away team
    mae_a, mae_b     — per-team historical MAE (model vs actual)
    bias_a, bias_b   — per-team historical bias (model − actual, signed)
    spread           — projected point spread (abs value)
    hit_rate_a, hit_rate_b (optional) — flat floor hit rates (0.0 - 1.0)
    hit_rate_games_a, hit_rate_games_b (optional) — graded games count

Output:
    confidence_score — 0.0 to 100.0 (calibrated 4-pillar score)
    raw_score        — 0 to 75
    band             — confidence tier label & description
    weighted_hit_rate— optional auxiliary floor hit rate
    floor_status     — optional auxiliary badge ("ELITE", "OK", "MARGINAL", "WEAK", "LOW_N", "N/A")
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Scoring rubrics
# ---------------------------------------------------------------------------

def score_volatility(max_vol: float) -> int:
    """
    Evaluates the volatility of the game based on the MAX (worst) std_dev_totals
    of the two teams. Volatility acts as a strict ceiling on confidence — chaotic
    teams make totals betting dangerous.

    Scoring (Max 27):
        ≤ 13.0 pts → 27 (Highly stable)
        ≤ 16.0 pts → 20 (Moderate variance)
        ≤ 18.0 pts → 13 (Noticeable variance)
        ≤ 20.0 pts →  6 (Volatile)
         > 20.0 pts →  0 (Chaotic — avoid)
    """
    if max_vol <= 13.0:
        return 27
    elif max_vol <= 16.0:
        return 20
    elif max_vol <= 18.0:
        return 13
    elif max_vol <= 20.0:
        return 6
    else:
        return 0


def score_mae(max_mae: float) -> int:
    """
    Evaluates the model's absolute error margin for the teams involved.
    Uses MAX (worst) MAE to ensure neither team represents a predictive blind spot.

    Scoring (Max 20):
        ≤ 10.5 pts → 20 (Excellent model grip)
        ≤ 12.0 pts → 15 (Good)
        ≤ 15.0 pts → 10 (Average)
        ≤ 18.0 pts →  5 (Weak grip)
         > 18.0 pts →  0 (Blind guess)
    """
    if max_mae <= 10.5:
        return 20
    elif max_mae <= 12.0:
        return 15
    elif max_mae <= 15.0:
        return 10
    elif max_mae <= 18.0:
        return 5
    else:
        return 0


def score_bias(avg_bias_abs: float) -> int:
    """
    Evaluates the directional error (model vs actual) of the game.
    Uses the AVERAGE bias across both teams since opposing biases (+ and -) naturally
    cancel out in totals betting.

    Scoring (Max 20):
        ≤ 2.5 pts → 20 (Clean projection)
        ≤ 5.0 pts → 15 (Slight drift)
        ≤ 8.0 pts → 10 (Moderate bias)
        ≤ 12.0 pts →  5 (Heavy bias)
         > 12.0 pts →  0 (Extreme drift)
    """
    if avg_bias_abs <= 2.5:
        return 20
    elif avg_bias_abs <= 5.0:
        return 15
    elif avg_bias_abs <= 8.0:
        return 10
    elif avg_bias_abs <= 12.0:
        return 5
    else:
        return 0


def score_spread(spread: float) -> int:
    """
    Spread scoring (max 8 points) — acts as a secondary filter, not a co-primary signal.

    Scoring rationale:
        < 2  pts →  2  Coin-flip game — foul-fest / OT trap, model unreliable
        2-5  pts →  5  Close, competitive game — both teams engaged, good scoring
        5-11 pts →  8  Sweet spot — one team clearly better, model most accurate
        11-15    →  2  Surprise performance drop — heavily penalised
        > 15 pts →  5  Blowout recovery
    """
    if spread < 2:
        return 2    # Coin-flip — foul-fest / OT trap
    elif spread <= 5:
        return 5    # Close, competitive — both teams motivated
    elif spread <= 11:
        return 8    # Sweet spot — model is most accurate here
    elif spread <= 15:
        return 2    # Surprise drop — penalise
    else:
        return 5    # Blowout recovery


def score_hit_rate(weighted_hit_rate: float | None) -> int:
    """
    Auxiliary buffer hit rate scoring (0-50 pts).
    Optional diagnostic for floor/buffer analysis (not added to primary confidence score).
    """
    if weighted_hit_rate is None:
        return 0
    if weighted_hit_rate >= 0.80:
        return 50
    elif weighted_hit_rate >= 0.65:
        return 33
    elif weighted_hit_rate >= 0.50:
        return 16
    else:
        return 0


def get_floor_status(weighted_hit_rate: float | None, min_games: int) -> str:
    """
    Auxiliary floor status badge for Over floor reliability.
    """
    if weighted_hit_rate is None or min_games == 0:
        return "N/A"
    if min_games < 3:
        return f"LOW_N({min_games})"
    if weighted_hit_rate >= 0.80:
        return "ELITE"
    elif weighted_hit_rate >= 0.65:
        return "OK"
    elif weighted_hit_rate >= 0.50:
        return "MARGINAL"
    else:
        return "WEAK"


# ---------------------------------------------------------------------------
# Confidence bands
# ---------------------------------------------------------------------------

CONFIDENCE_BANDS = [
    (90, "[ELITE]   ", "Model is firing on all cylinders -- very high trust"),
    (75, "[HIGH]    ", "Strong confidence -- play with conviction"),
    (60, "[SOLID]   ", "Above-average confidence -- worth monitoring"),
    (45, "[MODERATE]", "Model is uncertain on at least one dimension"),
    (30, "[LOW]     ", "Multiple red flags -- proceed with caution"),
    (0,  "[AVOID]   ", "Model confidence too low -- skip this game"),
]


def get_confidence_band(score: float) -> dict:
    """Return the label and description for a given confidence score."""
    for threshold, label, description in CONFIDENCE_BANDS:
        if score >= threshold:
            return {"label": label, "description": description}
    return {"label": "🔴 AVOID", "description": "Model confidence too low — skip this game"}


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def compute_confidence(game: dict) -> dict:
    """
    Compute the Model Confidence Score for a single game.

    Parameters
    ----------
    game : dict
        {
            "vol_a": float,      # std_dev_totals for home team
            "vol_b": float,      # std_dev_totals for away team
            "mae_a": float,      # historical MAE for home team
            "mae_b": float,      # historical MAE for away team
            "bias_a": float,     # historical signed bias for home team (model - actual)
            "bias_b": float,     # historical signed bias for away team (model - actual)
            "spread": float,     # projected absolute spread (always positive)
            "hit_rate_a": float, # (optional) flat floor hit rate for home team (0.0-1.0, or None)
            "hit_rate_b": float, # (optional) flat floor hit rate for away team (0.0-1.0, or None)
            "hit_rate_games_a": int, # (optional) graded games used for hit_rate_a
            "hit_rate_games_b": int, # (optional) graded games used for hit_rate_b
        }

    Returns
    -------
    dict with:
        max_vol          — maximum volatility used in scoring
        max_mae          — maximum MAE used in scoring
        avg_bias_abs     — absolute average bias used in scoring
        spread           — projected point spread
        vol_score        — points from volatility   (0-27)
        mae_score        — points from MAE           (0-20)
        bias_score       — points from bias          (0-20)
        spread_score     — points from spread        (2-8)
        raw_score        — total 4-pillar points     (0-75)
        confidence_score — normalized 0-100 score
        band             — confidence band label + description
        weighted_hit_rate— (optional) 60/40 blend of hit rates
        floor_status     — (optional) "ELITE", "OK", "MARGINAL", "WEAK", "LOW_N", "N/A"
        hit_rate_score   — (optional) auxiliary buffer score
        min_hit_games    — (optional) smallest sample size between the two teams
    """
    max_vol      = max(game["vol_a"], game["vol_b"])
    max_mae      = max(game["mae_a"], game["mae_b"])
    avg_bias_abs = abs((game["bias_a"] + game["bias_b"]) / 2)
    spread       = abs(game.get("spread", 0))

    # Core 4-Pillar Scoring (Max 75 raw points)
    vol_score    = score_volatility(max_vol)
    mae_score    = score_mae(max_mae)
    bias_score   = score_bias(avg_bias_abs)
    spread_score = score_spread(spread)

    raw_score        = vol_score + mae_score + bias_score + spread_score
    confidence_score = round((raw_score / 75.0) * 100.0, 1)

    # Optional / Auxiliary Floor & Hit-Rate Evaluation
    hit_a       = game.get("hit_rate_a")
    hit_b       = game.get("hit_rate_b")
    games_a     = game.get("hit_rate_games_a", 0) or 0
    games_b     = game.get("hit_rate_games_b", 0) or 0
    min_games   = min(games_a, games_b) if (games_a and games_b) else 0

    if hit_a is not None and hit_b is not None and min_games > 0:
        lower_hr = min(hit_a, hit_b)
        higher_hr = max(hit_a, hit_b)
        weighted_hit_rate = round((0.6 * lower_hr) + (0.4 * higher_hr), 4)

        base_hit_score = score_hit_rate(weighted_hit_rate)
        if min_games >= 5:
            hit_rate_score = base_hit_score
        elif min_games == 4:
            hit_rate_score = int(base_hit_score * 0.8)
        elif min_games == 3:
            hit_rate_score = int(base_hit_score * 0.6)
        else:
            hit_rate_score = min(15, int(base_hit_score * 0.3))
    else:
        weighted_hit_rate = None
        hit_rate_score = 0

    floor_status = get_floor_status(weighted_hit_rate, min_games)

    return {
        # Diagnostics
        "max_vol":          round(max_vol, 2),
        "max_mae":          round(max_mae, 2),
        "avg_bias_abs":     round(avg_bias_abs, 2),
        "spread":           round(spread, 2),
        # 4-Pillar Component scores
        "vol_score":        vol_score,
        "mae_score":        mae_score,
        "bias_score":       bias_score,
        "spread_score":     spread_score,
        "raw_score":        raw_score,
        # Normalized Confidence
        "confidence_score": confidence_score,
        "band":             get_confidence_band(confidence_score),
        # Auxiliary Floor Diagnostics (Optional)
        "weighted_hit_rate": weighted_hit_rate,
        "floor_status":      floor_status,
        "hit_rate_score":    hit_rate_score,
        "min_hit_games":     min_games,
    }


# ---------------------------------------------------------------------------
# Convenience: score a batch of games
# ---------------------------------------------------------------------------

def score_games(games: list[dict]) -> list[dict]:
    """
    Score a list of game dicts. Each game should include all 7 required keys
    plus optional metadata keys (home_team, away_team, league, etc.) which
    are passed through unchanged.

    Returns the same list with confidence results merged in.
    """
    results = []
    for g in games:
        conf = compute_confidence(g)
        results.append({**g, **conf})
    return results


# ---------------------------------------------------------------------------
# CLI demo / smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_cases = [
        {
            "label": "Elite Game (low vol, low MAE, unbiased, close spread, high HR)",
            "game": {"vol_a": 12.1, "vol_b": 12.8, "mae_a": 6.2, "mae_b": 7.1,
                     "bias_a": 0.5, "bias_b": -1.2, "spread": 7.0,
                     "hit_rate_a": 0.85, "hit_rate_b": 0.80, "hit_rate_games_a": 6, "hit_rate_games_b": 5},
        },
        {
            "label": "Solid Game (solid HR, good model grip)",
            "game": {"vol_a": 15.0, "vol_b": 15.5, "mae_a": 8.5, "mae_b": 9.0,
                     "bias_a": 2.5, "bias_b": 3.0, "spread": 7.0,
                     "hit_rate_a": 0.70, "hit_rate_b": 0.65, "hit_rate_games_a": 5, "hit_rate_games_b": 5},
        },
        {
            "label": "Moderate Confidence (small sample HR, average grip)",
            "game": {"vol_a": 17.5, "vol_b": 18.0, "mae_a": 10.5, "mae_b": 11.0,
                     "bias_a": 4.5, "bias_b": 5.5, "spread": 11.0,
                     "hit_rate_a": 0.55, "hit_rate_b": 0.60, "hit_rate_games_a": 3, "hit_rate_games_b": 3},
        },
        {
            "label": "Low Confidence (high vol, high MAE, biased, failing HR)",
            "game": {"vol_a": 22.0, "vol_b": 23.5, "mae_a": 14.0, "mae_b": 15.0,
                     "bias_a": 8.0, "bias_b": 9.5, "spread": 18.0,
                     "hit_rate_a": 0.35, "hit_rate_b": 0.40, "hit_rate_games_a": 6, "hit_rate_games_b": 6},
        },
    ]

    header = f"{'Label':<55} {'Vol':>5} {'MAE':>5} {'Bias':>5} {'Sprd':>5} {'Raw':>4} {'Score':>6} {'Band':<12} {'Floor'}"
    print("\n" + "=" * 120)
    print("  MODEL CONFIDENCE SCORE — SMOKE TEST (4 Pillars + Floor Diagnostic)")
    print("=" * 120)
    print(header)
    print("-" * 120)

    for tc in test_cases:
        r = compute_confidence(tc["game"])
        print(
            f"{tc['label']:<55} "
            f"{r['max_vol']:>5.1f} "
            f"{r['max_mae']:>5.1f} "
            f"{r['avg_bias_abs']:>5.1f} "
            f"{tc['game']['spread']:>5.1f} "
            f"{r['raw_score']:>4} "
            f"{r['confidence_score']:>6.1f} "
            f"{r['band']['label']:<12} "
            f"[{r['floor_status']}] (wHR: {r['weighted_hit_rate']})"
        )
    print("=" * 120)
