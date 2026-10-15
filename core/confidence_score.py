"""
core/confidence_score.py
=========================
Model Confidence Score (No Edge) — 100-point composite system.

Components (100 pts total):
    Historical Buffer Hit Rate: 50 pts
    MAE (Model Accuracy):        15 pts
    Directional Bias:            15 pts
    Volatility (Variance):       12 pts
    Projected Spread:             8 pts

Inputs per game:
    vol_a, vol_b     — std_dev_totals for home and away team
    mae_a, mae_b     — per-team historical MAE (model vs actual)
    bias_a, bias_b   — per-team historical bias (model − actual, signed)
    spread           — projected point spread (abs value)
    hit_rate_a, hit_rate_b — flat floor hit rates (0.0 - 1.0)
    hit_rate_games_a, hit_rate_games_b — graded games count

Output:
    confidence_score — 0.0 to 100.0 (higher = more predictable game)
    raw_score        — 0 to 100
    band             — confidence tier label & description
"""


# ---------------------------------------------------------------------------
# Scoring rubrics
# ---------------------------------------------------------------------------

def score_volatility(max_vol: float) -> int:
    """
    Evaluates the volatility of the game based on the MAX (worst) std_dev_totals
    of the two teams. Volatility acts as a strict ceiling on confidence — chaotic
    teams make totals betting dangerous.

    Scoring (Max 12):
        ≤ 13.0 pts → 12 (Highly stable)
        ≤ 16.0 pts →  8 (Moderate variance)
        ≤ 20.0 pts →  4 (Volatile)
         > 20.0 pts →  0 (Chaotic — avoid)
    """
    if max_vol <= 13.0:
        return 12
    elif max_vol <= 16.0:
        return 8
    elif max_vol <= 20.0:
        return 4
    else:
        return 0


def score_mae(max_mae: float) -> int:
    """
    Evaluates the model's absolute error margin for the teams involved.
    Uses MAX (worst) MAE to ensure neither team represents a predictive blind spot.

    Scoring (Max 15):
        ≤ 10.5 pts → 15 (Excellent model grip)
        ≤ 12.0 pts → 11 (Good)
        ≤ 15.0 pts →  7 (Average)
        ≤ 18.0 pts →  3 (Weak grip)
         > 18.0 pts →  0 (Blind guess)
    """
    if max_mae <= 10.5:
        return 15
    elif max_mae <= 12.0:
        return 11
    elif max_mae <= 15.0:
        return 7
    elif max_mae <= 18.0:
        return 3
    else:
        return 0


def score_bias(avg_bias_abs: float) -> int:
    """
    Evaluates the directional error (model vs actual) of the game.
    Uses the AVERAGE bias across both teams since opposing biases (+ and -) naturally
    cancel out in totals betting.

    Scoring (Max 15):
        ≤ 2.5 pts → 15 (Clean projection)
        ≤ 5.0 pts → 11 (Slight drift)
        ≤ 8.0 pts →  7 (Moderate bias)
        ≤ 12.0 pts →  3 (Heavy bias)
         > 12.0 pts →  0 (Extreme drift)
    """
    if avg_bias_abs <= 2.5:
        return 15
    elif avg_bias_abs <= 5.0:
        return 11
    elif avg_bias_abs <= 8.0:
        return 7
    elif avg_bias_abs <= 12.0:
        return 3
    else:
        return 0


def score_spread(spread: float) -> int:
    """
    Spread scoring (max 8 points) — acts as a secondary filter, not a co-primary signal.

    Scoring rationale:
        < 2  pts →  3  Coin-flip game — foul-fest / OT trap, model unreliable
        2-5  pts →  6  Close, competitive game — both teams engaged, good scoring
        5-11 pts →  8  Sweet spot — one team clearly better, model most accurate
        11-15    →  2  Surprise performance drop — heavily penalised
        > 15 pts →  3  Blowout — starters pulled early, garbage time distorts total
    """
    if spread < 2:
        return 3    # Coin-flip — foul-fest / OT trap
    elif spread <= 5:
        return 6    # Close, competitive — both teams motivated
    elif spread <= 11:
        return 8    # Sweet spot — model is most accurate here
    elif spread <= 15:
        return 2    # Surprise drop — penalise
    else:
        return 3    # Blowout — garbage time distorts total


def score_hit_rate(weighted_hit_rate: float) -> int:
    """
    PRIMARY scoring dimension (Max 50 points). Rewards games where BOTH teams have empirically
    proven they hit the model's -5 pt buffer floor in historical results.

    Uses a weighted blend: (0.6 * worst_hit_rate) + (0.4 * best_hit_rate).
    This ensures the weaker team heavily drags the score down, but allows a
    highly reliable opponent to offer slight buoyancy.

    Thresholds (weighted -5pt buffer hit rate, 0.0-1.0):
        >= 0.80 → 50  (very reliable — both teams consistently hit the buffer)
        >= 0.65 → 33
        >= 0.50 → 16
         < 0.50 →  0  (automatic fail — game undershoots more often than not)
    """
    if weighted_hit_rate >= 0.80:
        return 50
    elif weighted_hit_rate >= 0.65:
        return 33
    elif weighted_hit_rate >= 0.50:
        return 16
    else:
        return 0


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
            "hit_rate_a": float, # flat floor hit rate for home team (0.0-1.0, or None)
            "hit_rate_b": float, # flat floor hit rate for away team (0.0-1.0, or None)
            "hit_rate_games_a": int, # graded games used for hit_rate_a (for sample size guard)
            "hit_rate_games_b": int, # graded games used for hit_rate_b
        }

    Returns
    -------
    dict with:
        max_vol          — maximum volatility used in scoring
        max_mae          — maximum MAE used in scoring
        avg_bias_abs     — absolute average bias used in scoring
        weighted_hit_rate— 60/40 blend of the two teams' hit rates
        vol_score        — points from volatility   (0-12)
        mae_score        — points from MAE           (0-15)
        bias_score       — points from bias          (0-15)
        spread_score     — points from spread        (2-8)
        hit_rate_score   — points from empirical hit rate (0-50)
        raw_score        — total raw points           (0-100)
        confidence_score — identical to raw_score
        band             — confidence band label + description
    """
    max_vol      = max(game["vol_a"], game["vol_b"])
    max_mae      = max(game["mae_a"], game["mae_b"])
    avg_bias_abs = abs((game["bias_a"] + game["bias_b"]) / 2)
    spread       = abs(game.get("spread", 0))

    # Determine empirical hit rate score
    hit_a       = game.get("hit_rate_a")
    hit_b       = game.get("hit_rate_b")
    games_a     = game.get("hit_rate_games_a", 0)
    games_b     = game.get("hit_rate_games_b", 0)

    if hit_a is None or hit_b is None or games_a == 0 or games_b == 0:
        # No empirical hit-rate data — apply a below-neutral penalty.
        weighted_hit_rate = None
        hit_rate_score = 8
    else:
        lower_hr = min(hit_a, hit_b)
        higher_hr = max(hit_a, hit_b)
        weighted_hit_rate = (0.6 * lower_hr) + (0.4 * higher_hr)
        
        base_hit_score = score_hit_rate(weighted_hit_rate)
        
        # Sliding scale sample size penalty based on the WEAKEST sample size
        # Ensures teams with tiny sample sizes cannot achieve elite scores
        min_games = min(games_a, games_b)
        if min_games >= 5:
            hit_rate_score = base_hit_score
        elif min_games == 4:
            hit_rate_score = int(base_hit_score * 0.8) # max 40
        elif min_games == 3:
            hit_rate_score = int(base_hit_score * 0.6) # max 30
        else: # 1-2 games
            hit_rate_score = min(15, int(base_hit_score * 0.3)) # neutral cap

    vol_score    = score_volatility(max_vol)
    mae_score    = score_mae(max_mae)
    bias_score   = score_bias(avg_bias_abs)
    spread_score = score_spread(spread)

    raw_score        = vol_score + mae_score + bias_score + spread_score + hit_rate_score
    confidence_score = float(raw_score)  # Max is exactly 100 now

    return {
        # Diagnostics
        "max_vol":          round(max_vol, 2),
        "max_mae":          round(max_mae, 2),
        "avg_bias_abs":     round(avg_bias_abs, 2),
        "weighted_hit_rate": round(weighted_hit_rate, 4) if weighted_hit_rate is not None else None,
        # Component scores
        "vol_score":        vol_score,
        "mae_score":        mae_score,
        "bias_score":       bias_score,
        "spread_score":     spread_score,
        "hit_rate_score":   hit_rate_score,
        # Overall
        "raw_score":        raw_score,
        "confidence_score": confidence_score,
        "band":             get_confidence_band(confidence_score),
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

    header = f"{'Label':<60} {'Vol':>5} {'MAE':>5} {'Bias':>5} {'Sprd':>5} {'HR':>4} {'Raw':>4} {'Score':>6} Band"
    print("\n" + "=" * 120)
    print("  MODEL CONFIDENCE SCORE — SMOKE TEST")
    print("=" * 120)
    print(header)
    print("-" * 120)

    for tc in test_cases:
        r = compute_confidence(tc["game"])
        print(
            f"{tc['label']:<60} "
            f"{r['max_vol']:>5.1f} "
            f"{r['max_mae']:>5.1f} "
            f"{r['avg_bias_abs']:>5.1f} "
            f"{tc['game']['spread']:>5.1f} "
            f"{r['hit_rate_score']:>4} "
            f"{r['raw_score']:>4} "
            f"{r['confidence_score']:>6.1f} "
            f"{r['band']['label']}"
        )
    print("=" * 120)
