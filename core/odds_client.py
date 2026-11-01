"""
core/odds_client.py
===================
Live Sportsbook Odds Client & Market Consensus Extractor

Fetches real-time sports betting odds from API-Basketball (/odds?game={game_id})
and extracts the sharpest consensus total (Over/Under) line.

Supports Pinnacle, Bet365, Betfair, 1xBet, Marathon Bet, Betano, WilliamHill, etc.
"""

import os
import re
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_BASKETBALL_KEY", "")
API_URL = "https://v1.basketball.api-sports.io"

PREFERRED_BOOKS = [
    "Pinnacle",
    "Bet365",
    "Betfair",
    "1xBet",
    "Marathon Bet",
    "Betano",
    "WilliamHill",
    "BetVictor",
    "SBO",
]


def extract_main_total_from_bet(bet):
    """
    Given an Over/Under bet structure from API-Basketball, find the primary
    total line where Over and Under odds are closest to balanced (1.91 standard vig).
    """
    values = bet.get("values", [])
    lines = {}
    for v in values:
        val_str = v.get("value", "")
        odd_str = v.get("odd", "")
        m = re.match(r"(Over|Under)\s+([0-9]+(?:\.[0-9]+)?)", val_str, re.IGNORECASE)
        if m and odd_str:
            side = m.group(1).capitalize()
            line = float(m.group(2))
            try:
                odd = float(odd_str)
                lines.setdefault(line, {})[side] = odd
            except ValueError:
                continue

    candidates = []
    for line, odds in lines.items():
        if "Over" in odds and "Under" in odds:
            diff = abs(odds["Over"] - odds["Under"])
            dist_191 = abs(odds["Over"] - 1.91) + abs(odds["Under"] - 1.91)
            score = dist_191 + (diff * 2)
            candidates.append((score, line, odds["Over"], odds["Under"]))

    if candidates:
        candidates.sort(key=lambda x: x[0])
        best = candidates[0]
        return best[1], best[2], best[3]
    return None, None, None


def fetch_game_odds(game_id, session_cache=None):
    """
    Fetch live odds for a single game and return the sharpest available market line.
    
    Returns:
        dict: {
            "market_total": float or None,
            "bookmaker": str or None,
            "odds_over": float or None,
            "odds_under": float or None,
            "has_live_odds": bool
        }
    """
    if not API_KEY:
        return {
            "market_total": None,
            "bookmaker": None,
            "odds_over": None,
            "odds_under": None,
            "has_live_odds": False,
        }

    if session_cache is not None and game_id in session_cache:
        return session_cache[game_id]

    headers = {"x-apisports-key": API_KEY}
    url = f"{API_URL}/odds?game={game_id}"
    
    empty_result = {
        "market_total": None,
        "bookmaker": None,
        "odds_over": None,
        "odds_under": None,
        "has_live_odds": False,
    }

    try:
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code != 200:
            if session_cache is not None:
                session_cache[game_id] = empty_result
            return empty_result

        data = r.json()
        resp = data.get("response", [])
        if not resp:
            if session_cache is not None:
                session_cache[game_id] = empty_result
            return empty_result

        bookmakers = resp[0].get("bookmakers", [])
        if not bookmakers:
            if session_cache is not None:
                session_cache[game_id] = empty_result
            return empty_result

        # Sort bookmakers by priority
        def book_priority(b):
            name = b.get("name", "")
            if name in PREFERRED_BOOKS:
                return PREFERRED_BOOKS.index(name)
            return 999

        sorted_books = sorted(bookmakers, key=book_priority)
        for b in sorted_books:
            b_name = b.get("name")
            bets = b.get("bets", [])
            ou_bet = next((bet for bet in bets if bet.get("name") == "Over/Under"), None)
            if ou_bet:
                line, o_odd, u_odd = extract_main_total_from_bet(ou_bet)
                if line is not None:
                    res = {
                        "market_total": line,
                        "bookmaker": b_name,
                        "odds_over": o_odd,
                        "odds_under": u_odd,
                        "has_live_odds": True,
                    }
                    if session_cache is not None:
                        session_cache[game_id] = res
                    return res

    except Exception:
        pass

    if session_cache is not None:
        session_cache[game_id] = empty_result
    return empty_result

