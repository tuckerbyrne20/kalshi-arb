#!/usr/bin/env python3
"""Cross-platform arbitrage engine: Kalshi <> Polymarket.

Pure, dependency-free matching + edge math. Fetchers hand this module two
lists of normalized "games" and it returns matched markets with fee-adjusted
edges. Designed for all major US sports leagues (MLB, NBA, NHL, NFL) plus a
generic fallback for anything else.

A "game" dict looks like:
    {
      "game_time": "2026-06-11T01:35",      # ISO-ish string (date is what matters)
      "league":    "mlb",                    # optional hint
      "ref":       "sea-bal-jun11",          # platform-native id/slug/ticker
      "sides":     {"Seattle Mariners": {"buy": 0.55}, ...}   # team -> ask price
    }
"""
import json, math, re, sys

# ---------------------------------------------------------------------------
# Team-name canonicalization, in two layers because the two platforms label
# teams differently: Kalshi often uses the CITY only ("Seattle"), Polymarket
# uses the full name ("Seattle Mariners"). Both must map to the same code.
#
#   1. NICK  — distinctive nickname / full-name substrings. Unique enough to
#              resolve a team regardless of league. Checked first.
#   2. CITY  — bare city -> code, defaulting to the MLB team for that city.
#              Used only when no nickname matched (i.e. a city-only string).
#
# Keys are lowercase substrings; first hit wins, so list more-specific keys
# first. Codes are arbitrary but stable; cross-league teams get a league suffix
# so e.g. Boston (MLB) and the Celtics never collide.
# ---------------------------------------------------------------------------
NICK = {
    # MLB nicknames
    "diamondbacks": "AZ", "braves": "ATL", "orioles": "BAL", "red sox": "BOS",
    "cubs": "CHC", "white sox": "CWS", "reds": "CIN", "guardians": "CLE",
    "rockies": "COL", "tigers": "DET", "astros": "HOU", "royals": "KC",
    "angels": "LAA", "dodgers": "LAD", "marlins": "MIA", "brewers": "MIL",
    "twins": "MIN", "mets": "NYM", "yankees": "NYY", "athletics": "ATH",
    "a's": "ATH", "phillies": "PHI", "pirates": "PIT", "padres": "SD",
    "giants": "SF", "mariners": "SEA", "cardinals": "STL", "rays": "TB",
    "rangers": "TEX", "blue jays": "TOR", "nationals": "WSH",
    # NBA
    "hawks": "ATL-NBA", "celtics": "BOS-NBA", "nets": "BKN", "hornets": "CHA",
    "bulls": "CHI-NBA", "cavaliers": "CLE-NBA", "mavericks": "DAL-NBA",
    "nuggets": "DEN-NBA", "pistons": "DET-NBA", "warriors": "GSW",
    "rockets": "HOU-NBA", "pacers": "IND-NBA", "clippers": "LAC-NBA",
    "lakers": "LAL", "grizzlies": "MEM", "heat": "MIA-NBA", "bucks": "MIL-NBA",
    "timberwolves": "MIN-NBA", "pelicans": "NOP", "knicks": "NYK",
    "thunder": "OKC", "magic": "ORL", "76ers": "PHI-NBA", "sixers": "PHI-NBA",
    "suns": "PHX", "trail blazers": "POR", "blazers": "POR", "spurs": "SAS",
    "raptors": "TOR-NBA", "jazz": "UTA", "wizards": "WAS-NBA",
    "sacramento kings": "SAC",
    # NHL
    "ducks": "ANA", "bruins": "BOS-NHL", "sabres": "BUF", "flames": "CGY",
    "hurricanes": "CAR-NHL", "blackhawks": "CHI-NHL", "avalanche": "COL-NHL",
    "blue jackets": "CBJ", "stars": "DAL-NHL", "red wings": "DET-NHL",
    "oilers": "EDM", "panthers": "FLA", "los angeles kings": "LAK",
    "la kings": "LAK", "wild": "MIN-NHL", "canadiens": "MTL", "predators": "NSH",
    "devils": "NJD", "islanders": "NYI", "new york rangers": "NYR",
    "senators": "OTT", "flyers": "PHI-NHL", "penguins": "PIT-NHL",
    "sharks": "SJS", "kraken": "SEA-NHL", "blues": "STL-NHL", "lightning": "TBL",
    "maple leafs": "TOR-NHL", "canucks": "VAN", "golden knights": "VGK",
    "capitals": "WSH-NHL", "winnipeg jets": "WPG", "jets": "WPG",
    # NFL
    "falcons": "ATL-NFL", "ravens": "BAL-NFL", "bills": "BUF-NFL",
    "bears": "CHI-NFL", "bengals": "CIN-NFL", "browns": "CLE-NFL",
    "cowboys": "DAL-NFL", "broncos": "DEN-NFL", "lions": "DET-NFL",
    "packers": "GB", "texans": "HOU-NFL", "colts": "IND-NFL", "jaguars": "JAX",
    "chiefs": "KC-NFL", "raiders": "LV", "chargers": "LAC-NFL", "rams": "LAR",
    "dolphins": "MIA-NFL", "vikings": "MIN-NFL", "patriots": "NE", "saints": "NO",
    "new york giants": "NYG", "new york jets": "NYJ", "eagles": "PHI-NFL",
    "steelers": "PIT-NFL", "49ers": "SF-NFL", "niners": "SF-NFL",
    "seahawks": "SEA-NFL", "buccaneers": "TB-NFL", "bucs": "TB-NFL",
    "titans": "TEN", "commanders": "WAS-NFL", "arizona cardinals": "ARI-NFL",
}

# Bare-city -> MLB code. Multi-word/ambiguous cities listed with a hint suffix
# (e.g. "chicago c") and the bare city left out where it's truly ambiguous.
CITY = {
    "arizona": "AZ", "atlanta": "ATL", "baltimore": "BAL", "boston": "BOS",
    "chicago c": "CHC", "chicago w": "CWS", "cincinnati": "CIN",
    "cleveland": "CLE", "colorado": "COL", "detroit": "DET", "houston": "HOU",
    "kansas city": "KC", "los angeles a": "LAA", "los angeles d": "LAD",
    "la angels": "LAA", "la dodgers": "LAD", "miami": "MIA", "milwaukee": "MIL",
    "minnesota": "MIN", "new york m": "NYM", "new york y": "NYY", "oakland": "ATH",
    "philadelphia": "PHI", "pittsburgh": "PIT", "san diego": "SD",
    "san francisco": "SF", "seattle": "SEA", "st. louis": "STL",
    "st louis": "STL", "tampa bay": "TB", "texas": "TEX", "toronto": "TOR",
    "washington": "WSH",
}


def canon(name: str) -> str:
    """Map a raw team string to a stable short code (nickname first, then city)."""
    n = (name or "").lower().strip()
    for key, code in NICK.items():
        if key in n:
            return code
    for key, code in CITY.items():
        if key in n:
            return code
    # Generic fallback: strip punctuation, take a compact uppercase token.
    cleaned = re.sub(r"[^a-z ]", "", n).strip()
    if not cleaned:
        return "?"
    return cleaned.split()[-1].upper()[:5]


# --- fee models (estimates; verify live before trading) -------------------
def kalshi_fee(p: float) -> float:
    """Kalshi taker fee ~ 0.07 * p * (1-p), rounded up to the cent."""
    return math.ceil(0.07 * p * (1 - p) * 100) / 100


def poly_fee(p: float) -> float:
    """Polymarket taker fee ~ 0.03 * p (sports), per share."""
    return round(0.03 * p, 4)


def gdate(ts) -> str:
    return str(ts)[:10] if ts else None


def normalize(games, platform):
    """Turn a raw games list into engine form: teams sorted, sides keyed by code."""
    out = []
    for g in games or []:
        sides_raw = g.get("sides") or {}
        if not sides_raw:
            continue
        sides = {}
        for team, info in sides_raw.items():
            buy = (info or {}).get("buy")
            if buy is None:
                continue
            sides[canon(team)] = {"buy": float(buy), "team": team}
        if len(sides) < 2:
            continue
        out.append({
            "platform": platform,
            "game_time": g.get("game_time"),
            "league": g.get("league"),
            "teams": sorted(sides),
            "sides": sides,
            "ref": g.get("ref") or g.get("event") or g.get("slug"),
        })
    return out


def match(kg, pg):
    """Match Kalshi games to Polymarket games on identical team pair."""
    ms = []
    for k in kg:
        for p in pg:
            if k["teams"] != p["teams"]:
                continue
            legs, gross, net, ok = {}, 0.0, 0.0, True
            for t in k["teams"]:
                kb = k["sides"][t]["buy"]
                pb = p["sides"][t]["buy"]
                cands = []
                if kb > 0:
                    cands.append(("kalshi", kb, kb + kalshi_fee(kb)))
                if pb > 0:
                    cands.append(("poly", pb, pb + poly_fee(pb)))
                if not cands:
                    ok = False
                    break
                where, price, _ = min(cands, key=lambda c: c[1])
                _, _, pnet = min(cands, key=lambda c: c[2])
                legs[t] = {"buy_on": where, "price": price, "k": kb, "p": pb,
                           "k_team": k["sides"][t]["team"], "p_team": p["sides"][t]["team"]}
                gross += price
                net += pnet
            if not ok:
                continue
            ms.append({
                "teams": k["teams"],
                "league": k.get("league") or p.get("league"),
                "k_time": k["game_time"], "p_time": p["game_time"],
                "same_game_date": gdate(k["game_time"]) == gdate(p["game_time"]),
                "k_ref": k["ref"], "p_ref": p["ref"],
                "legs": legs,
                "gross_cost": round(gross, 4), "gross_edge": round(1 - gross, 4),
                "net_cost": round(net, 4), "net_edge": round(1 - net, 4),
            })
    ms.sort(key=lambda m: -m["gross_edge"])
    return ms


def scan(kalshi_games, poly_games):
    """High-level: normalize both slates, match, and summarize."""
    kg = normalize(kalshi_games, "kalshi")
    pg = normalize(poly_games, "poly")
    matches = match(kg, pg)
    executable = [m for m in matches if m["same_game_date"] and m["net_edge"] > 0]
    return {
        "kpis": {
            "kalshi": len(kg), "poly": len(pg),
            "matches": len(matches), "executable": len(executable),
        },
        "matches": matches,
        "executable": executable,
    }


# Back-compat aliases for the older server.py
norm_k = lambda games: normalize(games, "kalshi")
norm_p = lambda games: normalize(games, "poly")


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "."
    kg = json.load(open(f"{base}/kalshi_games.json"))
    pg = json.load(open(f"{base}/pm_games.json"))
    result = scan(kg, pg)
    k = result["kpis"]
    print(f"Kalshi:{k['kalshi']} Poly:{k['poly']} matched:{k['matches']} executable:{k['executable']}")
    for m in result["matches"]:
        tag = "EXECUTABLE" if (m["same_game_date"] and m["net_edge"] > 0) else \
              ("same-date" if m["same_game_date"] else "DIFF-DATE/not-exec")
        print(f" {'/'.join(m['teams']):14} gross {m['gross_edge']*100:+.1f}c "
              f"net {m['net_edge']*100:+.1f}c  {tag}")
