#!/usr/bin/env python3
"""Fetch live sports moneyline prices from Polymarket's public Gamma API.

Returns a list of normalized "games" the arb_engine understands:
    {"game_time": "...", "league": "mlb", "ref": "<slug>",
     "sides": {"Team A": {"buy": 0.55}, "Team B": {"buy": 0.46}}}

No API key required. Self-discovers sports league tags so it keeps working as
Polymarket adds/removes leagues.
"""
import json, sys, time
import urllib.request
import urllib.parse

GAMMA = "https://gamma-api.polymarket.com"
LEAGUE_SLUGS = {"mlb", "nba", "nhl", "nfl", "sports", "epl", "soccer",
                "ncaaf", "ncaab", "wnba", "mls"}
UA = {"User-Agent": "kalshi-poly-arb-scanner/1.0"}


def _get(path, params=None, tries=3):
    url = GAMMA + path
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
    print(f"[polymarket] GET {url} failed: {last}", file=sys.stderr)
    return None


# Per-league slugs queried directly via ?tag_slug=. Daily game moneylines live
# under these tags alongside season futures (which get filtered out below).
LEAGUE_QUERY_SLUGS = ["mlb", "nba", "nhl", "nfl", "epl", "soccer", "mls",
                      "wnba", "ncaaf", "ncaab"]


def _parse_market(m, league):
    """Turn one gamma market into a game dict, or None if not a 2-way moneyline."""
    # Polymarket tags each sports market: moneyline / spread / total / nrfi / ...
    # We only arb the straight game-winner (moneyline) market.
    smt = m.get("sportsMarketType")
    if smt and str(smt).lower() != "moneyline":
        return None
    # Slug/question as a backstop when the type field is missing.
    blob = f"{m.get('slug','')} {m.get('question','')}".lower()
    if any(w in blob for w in ("spread", "total", "over", "under", "handicap",
                                "runline", "run-line", "innings", "nrfi",
                                "first-5", "margin", "alt-", "alternate")):
        return None
    try:
        outcomes = m.get("outcomes")
        prices = m.get("outcomePrices")
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        if isinstance(prices, str):
            prices = json.loads(prices)
    except Exception:
        return None
    if not outcomes or not prices or len(outcomes) != 2 or len(prices) != 2:
        return None
    # Skip Yes/No style and spread/total markets — only team-vs-team moneylines.
    lo = {str(o).strip().lower() for o in outcomes}
    if lo & {"yes", "no", "over", "under", "draw", "tie"}:
        return None
    if any(any(ch.isdigit() for ch in str(o)) for o in outcomes):
        return None
    if m.get("closed") or not m.get("active", True):
        return None
    try:
        p0, p1 = float(prices[0]), float(prices[1])
    except (TypeError, ValueError):
        return None
    if not (0 < p0 < 1 and 0 < p1 < 1):
        return None
    game_time = (m.get("gameStartTime") or m.get("startDate")
                 or m.get("endDate") or m.get("endDateIso"))
    return {
        "game_time": game_time,
        "league": league,
        "ref": m.get("slug") or m.get("conditionId"),
        "sides": {
            str(outcomes[0]): {"buy": round(p0, 4)},
            str(outcomes[1]): {"buy": round(p1, 4)},
        },
    }


def fetch():
    games, seen = [], set()
    for league in LEAGUE_QUERY_SLUGS:
        offset = 0
        for _ in range(8):  # up to ~1600 events per league
            params = {"closed": "false", "active": "true", "limit": 200,
                      "offset": offset, "tag_slug": league,
                      "order": "startDate", "ascending": "false"}
            events = _get("/events", params)
            if not events:
                break
            for ev in events:
                for m in ev.get("markets", []) or []:
                    g = _parse_market(m, league)
                    if not g:
                        continue
                    if g["ref"] in seen:
                        continue
                    seen.add(g["ref"])
                    games.append(g)
            if len(events) < 200:
                break
            offset += 200
    return games


if __name__ == "__main__":
    out = fetch()
    print(f"[polymarket] {len(out)} moneyline games", file=sys.stderr)
    path = sys.argv[1] if len(sys.argv) > 1 else "pm_games.json"
    json.dump(out, open(path, "w"), indent=2)
    print(f"wrote {path}")
