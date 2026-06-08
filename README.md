# Live Kalshi ↔ Polymarket Arbitrage Scanner

An always-on website that scans Kalshi and Polymarket for cross-platform
sports arbitrage and emails you when a real, executable opportunity appears.

It runs entirely on **GitHub Actions + GitHub Pages** — no server to manage,
no hosting bill. A scheduled job fetches live prices every ~10 minutes,
matches the two order books, regenerates the public webpage, and sends an
email if it finds a same-game bet that pays out no matter who wins.

## How it works

```
GitHub Actions (cron every 10 min)
        │
        ├─ fetch_kalshi.py      → live sports moneylines from Kalshi
        ├─ fetch_polymarket.py  → live sports moneylines from Polymarket
        ├─ arb_engine.py        → match same games, compute fee-adjusted edge
        └─ scan.py              → write docs/index.html + docs/data.json
                                  → email you if an executable arb exists
```

- **docs/index.html** is the live page GitHub Pages serves. It auto-refreshes
  every 5 minutes in the browser.
- A real ("executable") arb means the **same game** is listed on both books and
  buying each side on the cheaper platform costs under $1 even after estimated
  fees. Anything on mismatched dates is flagged, never counted.

## One-time setup (≈5 minutes)

### 1. Create the GitHub repo and push

These files are already a local git repo. Create an empty repo on GitHub
(no README), then run the commands GitHub shows you — they look like:

```bash
git remote add origin https://github.com/<you>/kalshi-arb.git
git branch -M main
git push -u origin main
```

### 2. Turn on GitHub Pages

Repo **Settings → Pages → Build and deployment**:
- Source: **Deploy from a branch**
- Branch: **main**, folder: **/docs** → Save.

Your site goes live at `https://<you>.github.io/kalshi-arb/` within a minute
of the first scan. (The first scan also creates the page, so trigger one now:
**Actions → Arb scan → Run workflow**.)

### 3. Turn on the schedule

The workflow already runs every 10 minutes. GitHub disables scheduled
workflows on a repo with no activity for 60 days — just push any commit or hit
**Run workflow** to keep it alive.

### 4. Enable email alerts (optional but recommended)

The Action emails you via Gmail SMTP using an **App Password** (not your normal
password):

1. At [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   create an app password (requires 2-Step Verification on the account).
2. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
   Add three secrets:
   - `MAIL_USERNAME` → your Gmail address (e.g. `tttb2005@gmail.com`)
   - `MAIL_PASSWORD` → the 16-character app password
   - `MAIL_TO`       → where to send alerts (your email)

If you skip this, everything else still works — you just won't get emails, and
the webpage will still show any opportunities.

## Run it locally

```bash
python3 scan.py            # fetches live data, regenerates docs/index.html
open docs/index.html       # view the page

# individual pieces
python3 fetch_kalshi.py    # writes kalshi_games.json
python3 fetch_polymarket.py# writes pm_games.json
python3 arb_engine.py .    # match the two JSON files and print results
```

There's also `server.py` — a small local web app where you can paste two
slates by hand and scan them, handy for testing.

## Tuning

- **Scan frequency:** edit the `cron` line in `.github/workflows/scan.yml`.
  GitHub's minimum is every 5 minutes and runs can be delayed under load.
- **Alert threshold:** in `scan.py`, the "executable" filter is
  `same_game_date and net_edge > 0`. Raise the `0` to require a fatter cushion
  (e.g. `> 0.01` for ≥1¢ after fees).
- **Leagues / team names:** `arb_engine.py` has the team-name map. Add aliases
  there if a league's names aren't matching across the two platforms.
- **Fee model:** `kalshi_fee` / `poly_fee` in `arb_engine.py` are estimates —
  update them if the platforms change their fee schedules.

## Caveats

This is an analytical tool, **not financial advice**. The scanner uses last/mid
prices, not full order-book depth, so a flagged edge may shrink or vanish once
you account for slippage, available size, USD↔USDC conversion, withdrawal time,
locked capital, and platform eligibility. Always confirm live prices and each
market's resolution rules before placing any trade.
