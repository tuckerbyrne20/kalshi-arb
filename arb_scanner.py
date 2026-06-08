#!/usr/bin/env python3
"""Kalshi <> Polymarket cross-platform arbitrage scanner (engine)."""
import json, math, sys
CANON = {
 "seattle":"SEA","baltimore":"BAL","boston":"BOS","new york y":"NYY","yankees":"NYY",
 "new york m":"NYM","mets":"NYM","cleveland":"CLE","tampa bay":"TB","rays":"TB",
 "philadelphia":"PHI","phillies":"PHI","toronto":"TOR","blue jays":"TOR",
 "colorado":"COL","rockies":"COL","chicago c":"CHC","cubs":"CHC","chicago ws":"CWS",
 "white sox":"CWS","texas":"TEX","rangers":"TEX","kansas city":"KC","royals":"KC",
 "st. louis":"STL","cardinals":"STL","minnesota":"MIN","twins":"MIN","detroit":"DET",
 "tigers":"DET","arizona":"AZ","diamondbacks":"AZ","miami":"MIA","marlins":"MIA",
 "houston":"HOU","astros":"HOU","los angeles a":"LAA","angels":"LAA",
 "los angeles d":"LAD","dodgers":"LAD","milwaukee":"MIL","brewers":"MIL",
 "a's":"ATH","athletics":"ATH","pittsburgh":"PIT","pirates":"PIT",
 "san diego":"SD","padres":"SD","cincinnati":"CIN","reds":"CIN",
 "washington":"WSH","nationals":"WSH","san francisco":"SF","giants":"SF","atlanta":"ATL","braves":"ATL"}
def canon(name):
    n=(name or "").lower().strip()
    for k,v in CANON.items():
        if k in n: return v
    return n.upper()[:4]
def kalshi_fee(p): return math.ceil(0.07*p*(1-p)*100)/100
def poly_fee(p): return round(0.03*p,4)
def load(p): return json.load(open(p))
def norm_k(games):
    out=[]
    for g in games:
        sides={canon(t):{"buy":i["buy"],"team":t} for t,i in g["sides"].items()}
        out.append({"game_time":g.get("game_time"),"teams":sorted(sides),"sides":sides,"ref":g.get("event")})
    return out
def norm_p(games):
    out=[]
    for g in games:
        if not g.get("sides"): continue
        sides={canon(t):{"buy":i["buy"],"team":t} for t,i in g["sides"].items()}
        out.append({"game_time":g.get("game_time"),"teams":sorted(sides),"sides":sides,"ref":g.get("slug")})
    return out
def gdate(ts): return str(ts)[:10] if ts else None
def match(kg,pg):
    ms=[]
    for k in kg:
        for p in pg:
            if k["teams"]!=p["teams"]: continue
            legs={}; gross=0.0; net=0.0; ok=True
            for t in k["teams"]:
                kb=k["sides"][t]["buy"]; pb=p["sides"][t]["buy"]
                cands=[]
                if kb>0: cands.append(("kalshi",kb,kb+kalshi_fee(kb)))
                if pb>0: cands.append(("poly",pb,pb+poly_fee(pb)))
                if not cands: ok=False; break
                where,price,_=min(cands,key=lambda c:c[1])
                _,_,pnet=min(cands,key=lambda c:c[2])
                legs[t]={"buy_on":where,"price":price,"k":kb,"p":pb}
                gross+=price; net+=pnet
            if not ok: continue
            ms.append({"teams":k["teams"],"k_time":k["game_time"],"p_time":p["game_time"],
                "same_game_date":gdate(k["game_time"])==gdate(p["game_time"]),
                "k_ref":k["ref"],"p_ref":p["ref"],"legs":legs,
                "gross_cost":round(gross,4),"gross_edge":round(1-gross,4),
                "net_cost":round(net,4),"net_edge":round(1-net,4)})
    return ms
if __name__=="__main__":
    base=sys.argv[1] if len(sys.argv)>1 else "."
    kg=norm_k(load(f"{base}/kalshi_games.json")); pg=norm_p(load(f"{base}/pm_games.json"))
    ms=match(kg,pg); json.dump(ms,open(f"{base}/matches.json","w"),indent=2)
    print(f"Kalshi games:{len(kg)} Poly games:{len(pg)} matched:{len(ms)}")
    for m in sorted(ms,key=lambda x:-x["gross_edge"]):
        tag="SAME-DATE" if m["same_game_date"] else "DIFF-DATE/not-exec"
        print(f" {'/'.join(m['teams']):9} grosscost ${m['gross_cost']:.3f} edge {m['gross_edge']*100:+.1f}c net {m['net_edge']*100:+.1f}c {tag}")
        for t,l in m["legs"].items():
            print(f"    {t}: kalshi {l['k']:.2f} | poly {l['p']:.2f} -> buy {l['buy_on']} @ {l['price']:.2f}")
