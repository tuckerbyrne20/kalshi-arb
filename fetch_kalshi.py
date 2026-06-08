#!/usr/bin/env python3
"""Fetch live sports moneyline prices from Kalshi's public market API.

Returns a list of normalized "games" the arb_engine understands:
    {"game_time": "...", "league": "sports", "ref": "<event_ticker>",
     "sides": {"Team A": {"buy": 0.55}, "Team B": {"buy": 0.47}}}

Uses the public (read-only) trade-api v2 endpoints — no API key required.
Pages through open events and keeps the ones in the "Sports" category that
look like two-team games.
"""
import json, sys, time
import urllib.request
import urllib.parse

BASE = "https://api.elections.kalshi.com/trade-api/v2"
UA = {"User-Agent": "kalshi-poly-arb-scanner/1.0"}
SPORTS_CATEGORIES = {"sports"}


def _get(path, params=None, tries=3):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa
            last = e
            time.sleep(1.5 * (i + 1))
    print(f"[kalshi] GET {url} failed: {last}", file=sys.stderr)
    return None


def _ask(market, side):
    """Best ask in dollars to BUY the given side ('yes'/'no'), or None."""
    v = market.get(f"{side}_ask_dollars")
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    # Kalshi reports ask of 0.00 / 1.00 when there's no real liquidity.
    return v if 0 < v < 1 else None


def _event_to_game(ev):
    """Build a game dict from a Kalshi sports event, merging its markets."""
    sides = {}
    game_time = None
    for m in ev.get("markets", []) or []:
        if m.get("status") not in (None, "active", "open"):
            continue
        yt = (m.get("yes_sub_title") or "").strip()
        nt = (m.get("no_sub_title") or "").strip()
        ya = _ask(m, "yes")
        na = _ask(m, "no")
        if yt and ya is not None:
            sides.setdefault(yt, {"buy": ya})
        if nt and na is not None:
            sides.setdefault(nt, {"buy": na})
        game_time = game_time or m.get("close_time") or m.get("expected_expiration_time")
    if len(sides) < 2:
        return None
    return {
        "game_time": game_time,
        "league": "sports",
        "ref": ev.get("event_ticker"),
        "sides": sides,
    }


def fetch():
    games, cursor = [], None
    for _ in range(60):  # up to 60 * 200 = 12k events
        params = {"limit": 200, "status": "open", "with_nested_markets": "true"}
        if cursor:
            params["cursor"] = cursor
        data = _get("/events", params)
        if not data:
            break
        for ev in data.get("events", []):
            cat = (ev.get("category") or "").strip().lower()
            if cat not in SPORTS_CATEGORIES:
                continue
            g = _event_to_game(ev)
            if g:
                games.append(g)
        cursor = data.get("cursor")
        if not cursor:
            break
    return games


if __name__ == "__main__":
    out = fetch()
    print(f"[kalshi] {len(out)} sports games", file=sys.stderr)
    path = sys.argv[1] if len(sys.argv) > 1 else "kalshi_games.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"wrote {path}")
