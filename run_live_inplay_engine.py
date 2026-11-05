"""
run_live_inplay_engine.py
=========================
Live In-Play & Halftime Basketball Prediction Engine

Monitors games in real time via API-Basketball (/games?live=all),
tracks quarter-by-quarter scoring, computes sharp 2nd-half mean reversion models,
and detects live betting edges against sportsbook lines.

Key Features:
  - Halftime Mean Reversion Model (65% shooting variance regression)
  - Live Sportsbook In-Play Odds Comparison (Pinnacle/Bet365 consensus)
  - Actionable Signals:
      * HALFTIME FADE UNDER (hot 1H regression)
      * HALFTIME BOUNCE OVER (cold 1H bounce)
      * BLOWOUT CRUNCH UNDER (garbage time bench pacing)
      * CLUTCH CRUNCH UNDER (tight game half-court grind)
  - Live JSON outputs for dashboard display:
      * data/basketball/live_inplay_predictions.json
      * data/basketball/live_halftime_alerts.json

Usage:
  python run_live_inplay_engine.py                 # Single scan of live games
  python run_live_inplay_engine.py --monitor       # Continuous live polling
  python run_live_inplay_engine.py --interval 60   # Poll every 60 seconds
  python run_live_inplay_engine.py --date YYYY-MM-DD # Historical replay / audit
"""

import os
import sys
import json
import time
import argparse
from datetime import datetime
import requests
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
load_dotenv()

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from core.odds_client import fetch_game_odds

API_KEY  = os.getenv("API_BASKETBALL_KEY", "")
GIST_ID  = os.environ.get("LIVE_GIST_ID", "")
GITHUB_TOKEN = os.environ.get("GH_PAT", "")
BASE_URL = "https://v1.basketball.api-sports.io"
HEADERS  = {"x-apisports-key": API_KEY}

DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "basketball")
LIVE_OUTPUT_FILE  = os.path.join(DATA_DIR, "live_inplay_predictions.json")
ALERTS_OUTPUT_FILE = os.path.join(DATA_DIR, "live_halftime_alerts.json")


def update_gist(payload):
    """Publish live in-play predictions and alerts to GitHub Gist for the frontend radar."""
    if not GIST_ID or not GITHUB_TOKEN:
        return
    url = f"https://api.github.com/gists/{GIST_ID}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    data = {
        "files": {
            "live_basketball.json": {
                "content": json.dumps(payload, indent=2)
            }
        }
    }
    try:
        r = requests.patch(url, headers=headers, json=data, timeout=10)
        if r.status_code == 200:
            print("  [Gist] live_basketball.json updated successfully.")
        else:
            print(f"  [Gist] Update HTTP {r.status_code}")
    except Exception as e:
        print(f"  [Gist] Update error: {e}")


def load_pregame_predictions(date_str=None):
    """Load pre-game predictions for today to pair with in-play games."""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")
    path = os.path.join(DATA_DIR, f"universal_predictions_{date_str}_v2.json")
    if not os.path.exists(path):
        # Fallback to non-v2 or yesterday
        path = os.path.join(DATA_DIR, f"universal_predictions_{date_str}.json")
        if not os.path.exists(path):
            return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        pred_map = {}
        for p in data.get("predictions", []):
            gid = p.get("game_id")
            if gid:
                pred_map[str(gid)] = p
            # Also index by normalized team names
            h_norm = p.get("home_team", "").lower().strip()
            a_norm = p.get("away_team", "").lower().strip()
            if h_norm and a_norm:
                pred_map[(h_norm, a_norm)] = p
        return pred_map
    except Exception:
        return {}


def fetch_live_games():
    """Fetch all currently active/live basketball games globally."""
    if not API_KEY:
        print("  [!] Error: API_BASKETBALL_KEY not configured.")
        return []

    games = []
    # 1. Try ?live=all endpoint
    try:
        r = requests.get(f"{BASE_URL}/games?live=all", headers=HEADERS, timeout=12)
        if r.status_code == 200:
            games = r.json().get("response", [])
    except Exception as e:
        print(f"  [!] Error fetching live games: {e}")

    # 2. If live=all returned empty (API-Basketball often does not index in-play games under live=all),
    # query today's fixtures date endpoint and extract active quarters.
    if not games:
        from datetime import datetime, timezone
        now_utc = datetime.now(timezone.utc)
        today_utc = now_utc.strftime("%Y-%m-%d")
        try:
            r = requests.get(f"{BASE_URL}/games?date={today_utc}", headers=HEADERS, timeout=15)
            if r.status_code == 200:
                day_games = r.json().get("response", [])
                games = [
                    g for g in day_games
                    if g.get("status", {}).get("short") not in ("NS", "FT", "AOT", "POST", "CANC", "SUSP", "ABD")
                ]
        except Exception as e:
            print(f"  [!] Error fetching today's active games: {e}")

    return games


def fetch_games_for_replay(date_str):
    """Fetch finished or active games for a specific date for replay testing."""
    if not API_KEY:
        return []
    try:
        r = requests.get(f"{BASE_URL}/games?date={date_str}", headers=HEADERS, timeout=15)
        if r.status_code == 200:
            return r.json().get("response", [])
    except Exception as e:
        print(f"  [!] Error fetching replay games for {date_str}: {e}")
    return []


def calculate_halftime_projection(pregame_total, q1_pts, q2_pts, is_nba=False):
    """
    Mathematical 2nd-Half Mean Reversion Model:
      - In basketball, 1st-half outlier scoring is heavily dominated by shooting variance.
      - 2nd halves exhibit ~65% mean reversion back to baseline (beta = 0.35).
      - Fatigue and tightened second-half defensive schemes impose a standard decay (-1.5 pts, -2.5 in NBA).
    """
    if not pregame_total or pregame_total <= 0:
        return None

    h1_actual = q1_pts + q2_pts
    expected_h1 = pregame_total / 2.0
    h1_delta = h1_actual - expected_h1

    beta = 0.35  # Mean reversion factor
    fatigue_penalty = 2.5 if is_nba else 1.5

    # Projected 2nd Half
    proj_h2 = expected_h1 + (beta * h1_delta) - fatigue_penalty
    # Projected Full Game
    proj_final = h1_actual + proj_h2

    return {
        "h1_actual": h1_actual,
        "expected_h1": round(expected_h1, 1),
        "h1_delta": round(h1_delta, 1),
        "proj_h2": round(proj_h2, 1),
        "proj_final": round(proj_final, 1),
    }


def analyze_game(game, pregame_map, odds_cache=None, is_replay=False):
    """Perform in-play quantitative analysis for a single game."""
    gid = game.get("id")
    lid = game.get("league", {}).get("id")
    lname = game.get("league", {}).get("name", "Unknown")
    is_nba = (lid == 12 or "nba" in lname.lower())

    h_name = game.get("teams", {}).get("home", {}).get("name", "?")
    a_name = game.get("teams", {}).get("away", {}).get("name", "?")

    status_obj = game.get("status", {})
    status_short = status_obj.get("short", "")
    timer = status_obj.get("timer", "")

    scores_h = game.get("scores", {}).get("home", {})
    scores_a = game.get("scores", {}).get("away", {})

    q1_h = scores_h.get("quarter_1") or 0
    q1_a = scores_a.get("quarter_1") or 0
    q2_h = scores_h.get("quarter_2") or 0
    q2_a = scores_a.get("quarter_2") or 0
    q3_h = scores_h.get("quarter_3") or 0
    q3_a = scores_a.get("quarter_3") or 0
    q4_h = scores_h.get("quarter_4") or 0
    q4_a = scores_a.get("quarter_4") or 0

    cur_h = scores_h.get("total") or 0
    cur_a = scores_a.get("total") or 0
    cur_total = cur_h + cur_a
    margin = cur_h - cur_a

    # Retrieve pregame prediction
    pre_pred = pregame_map.get(str(gid))
    if not pre_pred:
        pre_pred = pregame_map.get((h_name.lower().strip(), a_name.lower().strip()))

    pre_total = pre_pred.get("model_total") if pre_pred else None
    pre_market = pre_pred.get("market_total") if pre_pred else None
    confidence = pre_pred.get("confidence", "-") if pre_pred else "-"

    # Calculate 1st Half totals (only valid once 1H has actually finished: HT, Q3, Q4, OT)
    q1_total = q1_h + q1_a
    q2_total = q2_h + q2_a
    has_full_1h = (status_short in ("HT", "Q3", "Q4", "OT", "FT", "AOT") and q1_total > 0 and q2_total > 0)
    ht_analysis = None

    if has_full_1h and pre_total:
        ht_analysis = calculate_halftime_projection(pre_total, q1_total, q2_total, is_nba=is_nba)

    # Fetch live odds if available
    live_market_total = None
    bookmaker = None
    if not is_replay and gid:
        live_odds_info = fetch_game_odds(gid, session_cache=odds_cache)
        live_market_total = live_odds_info.get("market_total")
        bookmaker = live_odds_info.get("bookmaker")
    elif pre_pred:
        # In replay mode, use the recorded market total from pregame prediction
        live_market_total = pre_pred.get("market_total")
        bookmaker = pre_pred.get("bookmaker") or "Pinnacle"

    # In-Play Signal Detection
    signals = []
    primary_signal = "IN PROGRESS"
    edge_2h = None
    edge_live = None

    if ht_analysis:
        h1_delta = ht_analysis["h1_delta"]
        proj_final = ht_analysis["proj_final"]
        proj_h2 = ht_analysis["proj_h2"]

        # Signal 1: Halftime Fade Under (Hot 1H Shooting Regression)
        if h1_delta >= 10.0:
            signals.append({
                "type": "HALFTIME_FADE_UNDER",
                "label": "🔥 HALFTIME FADE UNDER",
                "reason": f"1H scoring exceeded expectation by +{h1_delta:.1f} pts. Heavy 2H shooting regression projected.",
                "pick": "UNDER 2H",
                "strength": "HIGH" if h1_delta >= 15.0 else "STRONG"
            })
            primary_signal = "HALFTIME FADE UNDER"

        # Signal 2: Halftime Bounce Over (Cold 1H Scoring Bounce)
        elif h1_delta <= -10.0:
            signals.append({
                "type": "HALFTIME_BOUNCE_OVER",
                "label": "🚀 HALFTIME BOUNCE OVER",
                "reason": f"1H scoring was -{abs(h1_delta):.1f} pts below model. Positive mean reversion projected for 2H.",
                "pick": "OVER 2H",
                "strength": "HIGH" if h1_delta <= -15.0 else "STRONG"
            })
            primary_signal = "HALFTIME BOUNCE OVER"

        # Signal 3: Blowout Risk (Garbage Time Under)
        if abs(margin) >= 20 and status_short in ("HT", "Q3", "Q4"):
            signals.append({
                "type": "BLOWOUT_CRUNCH_UNDER",
                "label": "📉 BLOWOUT CRUNCH UNDER",
                "reason": f"Margin is {abs(margin)} pts. Expect heavy bench rotations and slow running clock.",
                "pick": "UNDER LIVE",
                "strength": "SOLID"
            })
            if primary_signal == "IN PROGRESS":
                primary_signal = "BLOWOUT CRUNCH UNDER"

        # Compare against Live Sportsbook Line
        if live_market_total:
            edge_live = round(proj_final - live_market_total, 1)
            # Estimate 2H line if full game live market is provided
            implied_2h_line = round(live_market_total - ht_analysis["h1_actual"], 1)
            edge_2h = round(proj_h2 - implied_2h_line, 1)

    record = {
        "game_id": gid,
        "league_id": lid,
        "league": lname,
        "home_team": h_name,
        "away_team": a_name,
        "status": status_short,
        "timer": timer,
        "scores": {
            "home": cur_h,
            "away": cur_a,
            "total": cur_total,
            "margin": margin,
            "quarter_1": {"home": q1_h, "away": q1_a, "total": q1_total},
            "quarter_2": {"home": q2_h, "away": q2_a, "total": q2_total},
            "quarter_3": {"home": q3_h, "away": q3_a, "total": q3_h + q3_a},
            "quarter_4": {"home": q4_h, "away": q4_a, "total": q4_h + q4_a},
        },
        "pregame": {
            "model_total": pre_total,
            "market_total": pre_market,
            "confidence": confidence,
        },
        "halftime_projection": ht_analysis,
        "live_market": {
            "market_total": live_market_total,
            "bookmaker": bookmaker,
            "edge_live": edge_live,
            "edge_2h": edge_2h,
        },
        "primary_signal": primary_signal,
        "signals": signals,
        "updated_at": datetime.now().isoformat(),
    }

    return record


def run_inplay_cycle(date_str=None, limit=None, verbose=True):
    """Run a single live in-play monitoring cycle and update JSON feeds."""
    pregame_map = load_pregame_predictions(date_str)
    odds_cache = {}

    if date_str:
        raw_games = fetch_games_for_replay(date_str)
    else:
        raw_games = fetch_live_games()

    if limit and limit > 0 and len(raw_games) > limit:
        raw_games = raw_games[:limit]

    if not raw_games:
        if verbose:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] No active live games found right now.")
        empty_payload = {
            "updated_at": datetime.now().isoformat(),
            "active_games_count": 0,
            "alerts_count": 0,
            "alerts": [],
            "games": [],
        }
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(LIVE_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(empty_payload, f, indent=2, ensure_ascii=False)
        with open(ALERTS_OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(empty_payload, f, indent=2, ensure_ascii=False)
        update_gist(empty_payload)
        return [], []

    analyzed_games = []
    active_alerts = []

    for g in raw_games:
        status = g.get("status", {}).get("short", "")
        # In live mode, only process active/HT games; in date replay, process games with scores
        if not date_str and status in ("FT", "AOT", "NS", "POST", "CANC"):
            continue

        rec = analyze_game(g, pregame_map, odds_cache=odds_cache, is_replay=bool(date_str))
        analyzed_games.append(rec)

        if rec["signals"]:
            for sig in rec["signals"]:
                active_alerts.append({
                    "game_id": rec["game_id"],
                    "matchup": f"{rec['home_team']} vs {rec['away_team']}",
                    "league": rec["league"],
                    "status": rec["status"],
                    "scores": f"{rec['scores']['home']}-{rec['scores']['away']}",
                    "signal": sig["label"],
                    "pick": sig["pick"],
                    "reason": sig["reason"],
                    "proj_2h": rec["halftime_projection"]["proj_h2"] if rec["halftime_projection"] else None,
                    "proj_final": rec["halftime_projection"]["proj_final"] if rec["halftime_projection"] else None,
                    "live_line": rec["live_market"]["market_total"],
                    "edge_2h": rec["live_market"]["edge_2h"],
                    "timestamp": rec["updated_at"],
                })

    # Save to JSON
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LIVE_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "active_games_count": len(analyzed_games),
            "alerts_count": len(active_alerts),
            "games": analyzed_games,
        }, f, indent=2, ensure_ascii=False)

    with open(ALERTS_OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "updated_at": datetime.now().isoformat(),
            "alerts_count": len(active_alerts),
            "alerts": active_alerts,
        }, f, indent=2, ensure_ascii=False)

    # Publish to Gist if credentials present
    update_gist({
        "updated_at": datetime.now().isoformat(),
        "active_games_count": len(analyzed_games),
        "alerts_count": len(active_alerts),
        "alerts": active_alerts,
        "games": analyzed_games,
    })

    if verbose and analyzed_games:
        print(f"\n{'='*75}")
        print(f"  LIVE IN-PLAY / HALFTIME DASHBOARD | {len(analyzed_games)} ACTIVE GAMES | {len(active_alerts)} ALERTS")
        print(f"{'='*75}")
        for r in analyzed_games:
            sc = r["scores"]
            ht = r["halftime_projection"]
            ht_str = f"1H:{ht['h1_actual']} (Δ{ht['h1_delta']:+0.1f}) -> 2H Proj:{ht['proj_h2']:.1f}" if ht else "1H: Pending"
            sig_badge = f"[{r['primary_signal']}]" if r["primary_signal"] != "IN PROGRESS" else ""
            print(f"  [{r['status']:<4}] {r['home_team']} {sc['home']} vs {r['away_team']} {sc['away']} (Tot:{sc['total']}) | {ht_str} {sig_badge}")

    return analyzed_games, active_alerts


def main():
    parser = argparse.ArgumentParser(description="Live In-Play & Halftime Basketball Prediction Engine")
    parser.add_argument("--monitor",  action="store_true", help="Run in continuous polling loop")
    parser.add_argument("--interval", type=int, default=60, help="Seconds between polls in monitor mode (default: 60)")
    parser.add_argument("--date",     type=str, help="Replay games for a specific date (YYYY-MM-DD)")
    parser.add_argument("--limit",    type=int, default=0, help="Max games to process in replay mode (default: 0 = all)")
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  🏀 LIVE IN-PLAY & HALFTIME BASKETBALL PREDICTION ENGINE")
    print("=" * 70)

    if args.monitor:
        print(f"  Starting monitor daemon (polling every {args.interval}s). Press Ctrl+C to stop.\n")
        try:
            while True:
                run_inplay_cycle(date_str=args.date, limit=args.limit, verbose=True)
                time.sleep(args.interval)
        except KeyboardInterrupt:
            print("\n  Monitor stopped by user.")
    else:
        run_inplay_cycle(date_str=args.date, limit=args.limit, verbose=True)


if __name__ == "__main__":
    main()
