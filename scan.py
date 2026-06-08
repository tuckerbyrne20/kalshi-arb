#!/usr/bin/env python3
"""Live arbitrage scan: fetch -> match -> publish.

Run by the GitHub Action on a schedule (and runnable locally):

    python3 scan.py

It fetches live Kalshi + Polymarket sports prices, runs the engine, and
writes a self-contained webpage to docs/index.html plus docs/data.json.
If any *executable* (same-game, positive net edge) arb is found it writes
alert.txt and sets the GitHub Actions output `has_arb=true` so the workflow
can email you.
"""
import json, os, sys, datetime, html, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")
os.makedirs(DOCS, exist_ok=True)

import arb_engine
import fetch_kalshi
import fetch_polymarket


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def gather():
    """Fetch live data; fall back to last good snapshot, then to samples."""
    errors = []
    try:
        kalshi = fetch_kalshi.fetch()
    except Exception as e:
        errors.append(f"kalshi fetch: {e}")
        kalshi = []
    try:
        poly = fetch_polymarket.fetch()
    except Exception as e:
        errors.append(f"polymarket fetch: {e}")
        poly = []

    prev = _load_json(os.path.join(DOCS, "data.json"), {})
    if not kalshi:
        kalshi = prev.get("raw_kalshi") or _load_json(os.path.join(HERE, "kalshi_games.json"), [])
        if kalshi:
            errors.append("kalshi: used cached/sample data")
    if not poly:
        poly = prev.get("raw_poly") or _load_json(os.path.join(HERE, "pm_games.json"), [])
        if poly:
            errors.append("polymarket: used cached/sample data")
    return kalshi, poly, errors


def build_payload():
    kalshi, poly, errors = gather()
    result = arb_engine.scan(kalshi, poly)
    now = datetime.datetime.now(datetime.timezone.utc)
    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M UTC"),
        "generated_ts": now.isoformat(),
        "kpis": result["kpis"],
        "matches": result["matches"],
        "executable": result["executable"],
        "errors": errors,
        "raw_kalshi": kalshi,
        "raw_poly": poly,
    }


# --------------------------------------------------------------------------
# HTML rendering
# --------------------------------------------------------------------------
def _match_card(m):
    exec_ok = m["same_game_date"] and m["net_edge"] > 0
    if exec_ok:
        badge = '<span class="ok">EXECUTABLE — same game</span>'
    elif m["same_game_date"]:
        badge = '<span class="warn">SAME DATE — edge too thin</span>'
    else:
        badge = '<span class="warn">DIFFERENT GAME DATE — not executable</span>'
    legs = ""
    for t, l in m["legs"].items():
        label = html.escape(l.get("k_team") or l.get("p_team") or t)
        legs += (f"<tr><td>{label} wins</td><td>{l['k']:.2f}</td>"
                 f"<td>{l['p']:.2f}</td><td><b>buy {l['buy_on']} @ {l['price']:.2f}</b></td></tr>")
    cls_g = "pos" if m["gross_edge"] >= 0 else "neg"
    cls_n = "pos" if m["net_edge"] >= 0 else "neg"
    return f"""<div class="match">
  <div class="mhead"><span class="teams">{html.escape('/'.join(m['teams']))}</span> {badge}</div>
  <div class="meta">Kalshi: {html.escape(str(m['k_time']))} &middot; Polymarket: {html.escape(str(m['p_time']))}</div>
  <table class="legs"><tr><th>Outcome</th><th>Kalshi ask</th><th>Polymarket ask</th><th>Cheapest side</th></tr>{legs}</table>
  <div class="edge">Buy-both cost: <b>${m['gross_cost']:.3f}</b> &nbsp;|&nbsp;
    Gross edge: <span class="{cls_g}">{m['gross_edge']*100:+.1f}&cent;</span> &nbsp;|&nbsp;
    Net of est. fees: <span class="{cls_n}">{m['net_edge']*100:+.1f}&cent;</span></div>
</div>"""


def render_html(p):
    k = p["kpis"]
    execs = p["executable"]
    matches = p["matches"]
    err = ""
    if p["errors"]:
        err = ('<div class="note" style="border-color:rgba(251,191,36,.4)">'
               '<b>Run notes:</b> ' + html.escape("; ".join(p["errors"])) + "</div>")
    if execs:
        bottom = (f'<div class="note" style="border-color:var(--pos)"><b>{len(execs)} executable '
                  f'arb(s) right now</b> — same game on both books with positive fee-adjusted edge. '
                  f'Verify live prices and resolution rules before acting.</div>')
    else:
        bottom = ('<div class="note"><b>No risk-free arb executable in this snapshot.</b> '
                  'Any matches below are on different game dates or have edges thinner than fees.</div>')
    match_html = "".join(_match_card(m) for m in matches) or \
        '<div class="note">No same-teams matches between the two books right now.</div>'

    exec_count_color = "var(--pos)" if k["executable"] else "var(--warn)"
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Live Arb Scanner — Kalshi &harr; Polymarket</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--mut:#8b93a7;--line:#262b36;--pos:#34d399;--neg:#f87171;--warn:#fbbf24;--accent:#60a5fa;}}
*{{box-sizing:border-box}}
body{{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:#e6e9ef;padding:28px;}}
.wrap{{max-width:960px;margin:0 auto}}
h1{{font-size:24px;margin:0 0 2px}} h2{{font-size:16px;margin:30px 0 10px;color:#cdd3df;border-bottom:1px solid var(--line);padding-bottom:6px}}
.sub{{color:var(--mut);font-size:13px;margin-bottom:20px}}
.cards{{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;flex:1;min-width:140px}}
.kpi .n{{font-size:26px;font-weight:700}} .kpi .l{{color:var(--mut);font-size:12px;margin-top:2px}}
.match{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}}
.mhead{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}}
.teams{{font-size:17px;font-weight:700}}
.meta{{color:var(--mut);font-size:12px;margin:6px 0 10px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
.legs th,.legs td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}}
.legs th{{color:var(--mut);font-weight:500}}
.edge{{margin-top:10px;font-size:14px}}
.pos{{color:var(--pos);font-weight:700}} .neg{{color:var(--neg);font-weight:700}}
.ok{{background:rgba(52,211,153,.15);color:var(--pos);padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}}
.warn{{background:rgba(251,191,36,.15);color:var(--warn);padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}}
.note{{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.3);border-radius:10px;padding:12px 16px;font-size:13px;margin:10px 0}}
.foot{{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);padding-top:12px}}
.dot{{height:8px;width:8px;border-radius:50%;background:var(--pos);display:inline-block;margin-right:6px;animation:pulse 2s infinite}}
@keyframes pulse{{0%{{opacity:1}}50%{{opacity:.3}}100%{{opacity:1}}}}
</style></head><body><div class="wrap">

<h1><span class="dot"></span>Live Arbitrage Scanner</h1>
<div class="sub">Kalshi &harr; Polymarket &middot; all sports &middot; updated <b>{html.escape(p['generated_at'])}</b> &middot; auto-refreshes every 5 min</div>

<div class="cards">
  <div class="kpi"><div class="n">{k['kalshi']}</div><div class="l">Kalshi games priced</div></div>
  <div class="kpi"><div class="n">{k['poly']}</div><div class="l">Polymarket games priced</div></div>
  <div class="kpi"><div class="n">{k['matches']}</div><div class="l">Same-teams matches</div></div>
  <div class="kpi"><div class="n" style="color:{exec_count_color}">{k['executable']}</div><div class="l">Executable arbs now</div></div>
</div>

{err}
{bottom}

<h2>Matched markets</h2>
{match_html}

<h2>Method &amp; fee model</h2>
<div class="note">A real arb needs the <b>same game</b> on both books (same teams, same date, same resolution). Buy each outcome wherever it's cheaper; if the two asks sum under $1.00 the gap is the gross edge. Net edge subtracts estimated fees — Kalshi taker &asymp; 0.07&middot;p&middot;(1&minus;p), Polymarket &asymp; 0.03&middot;p. Order-book depth, slippage, USD&harr;USDC, withdrawal time and locked capital are <b>not</b> modeled.</div>

<div class="foot">Analytical tool, not financial advice. Prices are point-in-time snapshots and move continuously — confirm live before acting. Data: api.elections.kalshi.com &middot; gamma-api.polymarket.com</div>
</div></body></html>"""


def main():
    p = build_payload()
    with open(os.path.join(DOCS, "data.json"), "w") as f:
        json.dump(p, f, indent=2)
    with open(os.path.join(DOCS, "index.html"), "w") as f:
        f.write(render_html(p))
    # GitHub Pages: don't run Jekyll on these files.
    open(os.path.join(DOCS, ".nojekyll"), "w").close()

    execs = p["executable"]
    k = p["kpis"]
    print(f"scan: kalshi={k['kalshi']} poly={k['poly']} matches={k['matches']} executable={k['executable']}")
    for e in p["errors"]:
        print("  note:", e)

    # Alert plumbing for the workflow.
    has_arb = bool(execs)
    if has_arb:
        lines = ["Executable arbitrage opportunities detected:\n"]
        for m in execs:
            lines.append(f"- {'/'.join(m['teams'])} | net edge {m['net_edge']*100:+.1f}c "
                         f"| gross {m['gross_edge']*100:+.1f}c | {m['k_time']}")
            for t, l in m["legs"].items():
                lines.append(f"    {t}: buy {l['buy_on']} @ {l['price']:.2f}")
        lines.append("\nVerify live prices and resolution rules before acting.")
        with open(os.path.join(HERE, "alert.txt"), "w") as f:
            f.write("\n".join(lines))

    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f:
            f.write(f"has_arb={'true' if has_arb else 'false'}\n")
            f.write(f"summary=kalshi {k['kalshi']} / poly {k['poly']} / "
                    f"{k['matches']} matches / {k['executable']} executable\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        traceback.print_exc()
        sys.exit(1)
