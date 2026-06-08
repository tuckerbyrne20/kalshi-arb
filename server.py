#!/usr/bin/env python3
"""Zero-dependency web app wrapping arb_scanner.py.

Run:  python3 server.py   ->  http://localhost:8000
Uses only the Python standard library, so no pip install is needed.
It imports the matching engine from arb_scanner.py directly (the engine
file is not modified).
"""
import json, os, importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))

# --- import the engine (arb_scanner.py) without running its __main__ block ---
spec = importlib.util.spec_from_file_location("arb_scanner", os.path.join(HERE, "arb_scanner.py"))
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


def run_scan(kalshi_games, pm_games):
    """Normalize + match using the engine, plus build display-friendly slates."""
    kg = engine.norm_k(kalshi_games)
    pg = engine.norm_p(pm_games)
    matches = engine.match(kg, pg)
    matches.sort(key=lambda m: -m["gross_edge"])

    def slate(games):
        rows = []
        for g in sorted(games, key=lambda x: str(x.get("game_time"))):
            sides = g.get("sides") or {}
            prices = " / ".join(f"{t} {i['buy']:.2f}" for t, i in sides.items() if i.get("buy", 0) > 0)
            if prices:
                rows.append({"time": g.get("game_time"), "prices": prices})
        return rows

    executable = [m for m in matches if m["same_game_date"] and m["gross_edge"] > 0]
    return {
        "kpis": {
            "kalshi": len(kg),
            "poly": len(pg),
            "matches": len(matches),
            "executable": len(executable),
        },
        "matches": matches,
        "kalshi_slate": slate(kalshi_games),
        "poly_slate": slate(pm_games),
    }


def load_sample():
    with open(os.path.join(HERE, "kalshi_games.json")) as f:
        kg = json.load(f)
    with open(os.path.join(HERE, "pm_games.json")) as f:
        pg = json.load(f)
    return kg, pg


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # quieter console
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, INDEX_HTML, "text/html; charset=utf-8")
        elif self.path == "/api/sample":
            kg, pg = load_sample()
            self._send(200, json.dumps({"kalshi": kg, "poly": pg}))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        if self.path != "/api/scan":
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            kg = payload.get("kalshi") or []
            pg = payload.get("poly") or []
            if not isinstance(kg, list) or not isinstance(pg, list):
                raise ValueError("Both 'kalshi' and 'poly' must be JSON arrays of games.")
            self._send(200, json.dumps(run_scan(kg, pg)))
        except Exception as e:
            self._send(400, json.dumps({"error": str(e)}))


INDEX_HTML = r"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Kalshi &harr; Polymarket Arb Scanner</title>
<style>
:root{--bg:#0f1115;--card:#181b22;--mut:#8b93a7;--line:#262b36;--pos:#34d399;--neg:#f87171;--warn:#fbbf24;--accent:#60a5fa;}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:#e6e9ef;padding:28px;}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:24px;margin:0 0 2px} h2{font-size:16px;margin:30px 0 10px;color:#cdd3df;border-bottom:1px solid var(--line);padding-bottom:6px}
.sub{color:var(--mut);font-size:13px;margin-bottom:20px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 18px;flex:1;min-width:140px}
.kpi .n{font-size:26px;font-weight:700} .kpi .l{color:var(--mut);font-size:12px;margin-top:2px}
.match{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:12px 0}
.mhead{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px}
.teams{font-size:17px;font-weight:700}
.meta{color:var(--mut);font-size:12px;margin:6px 0 10px}
table{width:100%;border-collapse:collapse;font-size:13px}
.legs th,.legs td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
.legs th{color:var(--mut);font-weight:500}
.edge{margin-top:10px;font-size:14px}
.pos{color:var(--pos);font-weight:700} .neg{color:var(--neg);font-weight:700}
.ok{background:rgba(52,211,153,.15);color:var(--pos);padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}
.warn{background:rgba(251,191,36,.15);color:var(--warn);padding:3px 9px;border-radius:20px;font-size:12px;font-weight:600}
.slate{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:8px 14px;margin:10px 0}
.slate table td{padding:5px 8px;border-bottom:1px solid var(--line);color:#cdd3df}
.note{background:rgba(96,165,250,.08);border:1px solid rgba(96,165,250,.3);border-radius:10px;padding:12px 16px;font-size:13px;margin:10px 0}
.foot{color:var(--mut);font-size:12px;margin-top:24px;border-top:1px solid var(--line);padding-top:12px}
.panel{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}
.grid{display:flex;gap:14px;flex-wrap:wrap}
.col{flex:1;min-width:280px}
label{display:block;font-size:12px;color:var(--mut);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
textarea{width:100%;height:150px;background:#0b0d11;color:#e6e9ef;border:1px solid var(--line);border-radius:8px;padding:10px;font:12px/1.45 ui-monospace,Menlo,monospace;resize:vertical}
.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px;align-items:center}
button{background:var(--accent);color:#0b0d11;border:0;border-radius:8px;padding:9px 16px;font-size:14px;font-weight:700;cursor:pointer}
button.ghost{background:transparent;color:var(--accent);border:1px solid var(--line)}
button:hover{opacity:.9}
input[type=file]{display:none}
.filerow{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}
.tag{font-size:11px;color:var(--mut)}
.err{color:var(--neg);font-size:13px;margin-top:8px}
code{background:#0b0d11;padding:1px 5px;border-radius:4px;font-size:12px}
.hidden{display:none}
</style></head><body><div class="wrap">

<h1>Kalshi &harr; Polymarket Arbitrage Scanner</h1>
<div class="sub">Paste or upload the two slates, hit <b>Scan</b>. Cross-platform same-game matches and fee-adjusted edges are computed by <code>arb_scanner.py</code>.</div>

<div class="panel">
  <div class="grid">
    <div class="col">
      <label>Kalshi games JSON</label>
      <textarea id="kalshi" placeholder='[{"game_time":"...","sides":{"Seattle":{"buy":0.55}}}]'></textarea>
      <div class="filerow">
        <button class="ghost" onclick="document.getElementById('kf').click()">Upload kalshi_games.json</button>
        <input type="file" id="kf" accept=".json" onchange="loadFile(this,'kalshi')">
      </div>
    </div>
    <div class="col">
      <label>Polymarket games JSON</label>
      <textarea id="poly" placeholder='[{"game_time":"...","sides":{"Seattle Mariners":{"buy":0.53}}}]'></textarea>
      <div class="filerow">
        <button class="ghost" onclick="document.getElementById('pf').click()">Upload pm_games.json</button>
        <input type="file" id="pf" accept=".json" onchange="loadFile(this,'poly')">
      </div>
    </div>
  </div>
  <div class="btns">
    <button onclick="scan()">Scan for arbs</button>
    <button class="ghost" onclick="loadSample()">Load sample data</button>
    <button class="ghost" onclick="clearAll()">Clear</button>
    <span class="tag" id="status"></span>
  </div>
  <div class="err" id="err"></div>
</div>

<div id="results" class="hidden">
  <div class="cards" id="cards"></div>
  <div class="note" id="bottomline"></div>
  <h2>Matched markets</h2>
  <div id="matches"></div>
  <h2>Kalshi slate</h2>
  <div class="slate"><table id="kslate"></table></div>
  <h2>Polymarket slate</h2>
  <div class="slate"><table id="pslate"></table></div>
</div>

<h2>Method &amp; fee model</h2>
<ul>
<li><b>Match key:</b> normalized team pair. A real arb requires the <b>same game date</b> on both legs &mdash; mismatched dates are flagged, not traded.</li>
<li><b>Edge:</b> buy each outcome on whichever platform is cheaper; if the two prices sum under $1.00 the difference is the gross edge (guaranteed $1 payout).</li>
<li><b>Fees:</b> Kalshi taker &asymp; <code>0.07&middot;p&middot;(1&minus;p)</code>; Polymarket &asymp; <code>0.03&middot;p</code>. Net edge subtracts these.</li>
<li><b>Not modeled:</b> book depth/slippage, USD&harr;USDC, withdrawal time, locked capital, eligibility.</li>
</ul>

<div class="foot">Analytical tool, not financial advice. Prices are point-in-time snapshots and move continuously &mdash; confirm resolution rules and live fees before acting.</div>
</div>

<script>
const $=id=>document.getElementById(id);
function loadFile(inp,target){const f=inp.files[0];if(!f)return;const r=new FileReader();r.onload=e=>{$(target).value=e.target.result;$('status').textContent=f.name+' loaded into '+target;};r.readAsText(f);}
async function loadSample(){const r=await fetch('/api/sample');const d=await r.json();$('kalshi').value=JSON.stringify(d.kalshi,null,2);$('poly').value=JSON.stringify(d.poly,null,2);$('status').textContent='Sample data loaded';$('err').textContent='';}
function clearAll(){$('kalshi').value='';$('poly').value='';$('results').classList.add('hidden');$('status').textContent='';$('err').textContent='';}
function parse(id){const v=$(id).value.trim();if(!v)return [];return JSON.parse(v);}
async function scan(){
  $('err').textContent='';
  let kalshi,poly;
  try{kalshi=parse('kalshi');poly=parse('poly');}
  catch(e){$('err').textContent='Invalid JSON: '+e.message;return;}
  $('status').textContent='Scanning...';
  const r=await fetch('/api/scan',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kalshi,poly})});
  const d=await r.json();
  if(!r.ok){$('err').textContent=d.error||'Scan failed';$('status').textContent='';return;}
  render(d);$('status').textContent='Done';
}
function c(v){return (v>=0?'pos':'neg');}
function render(d){
  $('results').classList.remove('hidden');
  const k=d.kpis;
  $('cards').innerHTML=`
    <div class="kpi"><div class="n">${k.kalshi}</div><div class="l">Kalshi games priced</div></div>
    <div class="kpi"><div class="n">${k.poly}</div><div class="l">Polymarket games priced</div></div>
    <div class="kpi"><div class="n">${k.matches}</div><div class="l">Same-teams matches</div></div>
    <div class="kpi"><div class="n" style="color:${k.executable?'var(--pos)':'var(--warn)'}">${k.executable}</div><div class="l">Executable arbs now</div></div>`;
  $('bottomline').innerHTML = k.executable
    ? `<b>Bottom line:</b> ${k.executable} executable same-game arb(s) found &mdash; both legs settle on the identical game with a positive fee-adjusted edge. Verify live before acting.`
    : `<b>Bottom line:</b> No risk-free arbitrage executable in this snapshot. Apparent edges below are on <b>different game dates</b> &mdash; the matching trap to avoid.`;
  $('matches').innerHTML = d.matches.length ? d.matches.map(m=>{
    const exec = m.same_game_date;
    const badge = exec && m.gross_edge>0
      ? `<span class="ok">EXECUTABLE &mdash; same game</span>`
      : `<span class="warn">${exec?'SAME DATE':'DIFFERENT GAME DATE'} &mdash; ${exec?'check edge':'not executable'}</span>`;
    const legs = Object.entries(m.legs).map(([t,l])=>
      `<tr><td>${t} wins</td><td>${l.k.toFixed(2)}</td><td>${l.p.toFixed(2)}</td><td><b>buy ${l.buy_on} @ ${l.price.toFixed(2)}</b></td></tr>`).join('');
    return `<div class="match">
      <div class="mhead"><span class="teams">${m.teams.join('/')}</span> ${badge}</div>
      <div class="meta">Kalshi game: ${m.k_time||'?'} &nbsp;&middot;&nbsp; Polymarket game: ${m.p_time||'?'}</div>
      <table class="legs"><tr><th>Outcome</th><th>Kalshi ask</th><th>Polymarket ask</th><th>Cheapest side</th></tr>${legs}</table>
      <div class="edge">Buy-both cost: <b>$${m.gross_cost.toFixed(3)}</b> &nbsp;|&nbsp;
      Gross edge: <span class="${c(m.gross_edge)}">${(m.gross_edge*100>=0?'+':'')}${(m.gross_edge*100).toFixed(1)}&cent;</span> &nbsp;|&nbsp;
      Net of est. fees: <span class="${c(m.net_edge)}">${(m.net_edge*100>=0?'+':'')}${(m.net_edge*100).toFixed(1)}&cent;</span></div>
    </div>`;
  }).join('') : '<div class="note">No same-teams matches between the two slates.</div>';
  const slate=(rows)=>'<tr><td><b>Game time</b></td><td><b>Prices</b></td></tr>'+rows.map(r=>`<tr><td>${r.time}</td><td>${r.prices}</td></tr>`).join('');
  $('kslate').innerHTML=slate(d.kalshi_slate);
  $('pslate').innerHTML=slate(d.poly_slate);
  $('results').scrollIntoView({behavior:'smooth'});
}
</script>
</body></html>"""


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Arb scanner web app -> http://localhost:{port}  (Ctrl-C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
