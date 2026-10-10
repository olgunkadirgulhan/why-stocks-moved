#!/usr/bin/env python3
"""invest_vs.py — "1 yıl önce iki varlığa 1.000 $ koysaydın" kıyas formatı (LLM'siz, yalnız yfinance kapanışları).
2026-10-10: kanalın 'neden hareket etti' videoları medyan 26 izlenmede kaldı; kıyas formatı (Bloop'ta Normal vs Psycho)
en çok izlenen yapı. Her rakam gerçek kapanıştan hesaplanır; geçmiş getiri gelecek getiri değildir uyarısı her videoda.

  python invest_vs.py --dry-run     # sıradaki çifti render eder, yüklemez
"""
import datetime
import json
import sys
from pathlib import Path

import yfinance as yf

import renderer

HERE = Path(__file__).resolve().parent
STATE = HERE / "data" / "invest_vs.json"
NAMES = {"NVDA": "Nvidia", "AAPL": "Apple", "MSFT": "Microsoft", "TSLA": "Tesla", "AMZN": "Amazon", "META": "Meta",
         "GOOGL": "Google", "^GSPC": "S&P 500", "GC=F": "Gold", "NFLX": "Netflix", "COST": "Costco",
         "WMT": "Walmart", "KO": "Coca-Cola", "MCD": "McDonald's", "DIS": "Disney", "NKE": "Nike"}
# İzleyicinin merak edeceği eşleşmeler: rakip markalar, "tek hisse vs endeks", "hisse vs altın"
PAIRS = [("NVDA", "AAPL"), ("TSLA", "^GSPC"), ("MSFT", "GOOGL"), ("AMZN", "WMT"), ("META", "NFLX"),
         ("GC=F", "^GSPC"), ("KO", "MCD"), ("NKE", "COST"), ("AAPL", "MSFT"), ("NVDA", "GC=F"),
         ("DIS", "NFLX"), ("TSLA", "NVDA"), ("GOOGL", "META"), ("COST", "WMT"), ("AAPL", "^GSPC"),
         ("AMZN", "GOOGL"), ("MCD", "COST"), ("KO", "GC=F"), ("META", "MSFT"), ("TSLA", "AAPL")]
STAKE = 1000


def money(v):
    return f"${v:,.0f}"


def history(sym):
    h = yf.Ticker(sym).history(period="1y", interval="1d")["Close"].dropna()
    if len(h) < 200:
        raise RuntimeError(f"{sym}: 1 yıllık veri yok ({len(h)})")
    return h


def next_pair():
    done = json.loads(STATE.read_text()) if STATE.exists() else []
    recent = {tuple(d["pair"]) for d in done[-len(PAIRS) + 2:]}
    return next((p for p in PAIRS if p not in recent), PAIRS[len(done) % len(PAIRS)]), done


def build():
    (a, b), done = next_pair()
    tickers = {}
    for sym in (a, b):
        h = history(sym)
        vals = [STAKE * float(x) / float(h.iloc[0]) for x in h]
        series = [round(v, 2) for v in vals[::5]] + ([round(vals[-1], 2)] if (len(vals) - 1) % 5 else [])
        pct = (vals[-1] / STAKE - 1) * 100
        tickers[sym] = {"name": NAMES[sym], "price": round(vals[-1], 2), "change_pct": round(pct, 2),
                        "change_5d_pct": round(pct, 2), "series": series, "as_of": str(h.index[-1].date()),
                        "start": str(h.index[0].date())}
    A, B = tickers[a], tickers[b]
    win, lose = (A, B) if A["price"] >= B["price"] else (B, A)
    diff = win["price"] - lose["price"]
    since = datetime.date.fromisoformat(A["start"]).strftime("%B %Y")
    pc = lambda v: f"{'up' if v >= 0 else 'down'} {abs(v):.1f} percent"
    beats = [
        {"say": f"{since}. You put {money(STAKE)} in {A['name']}. Your friend put {money(STAKE)} in {B['name']}. "
                f"Who has more now?",
         "osd": f"{A['name']} vs {B['name']}", "emphasis": "vs", "visual": "text", "ticker": a},
        {"say": f"Your {A['name']} money is now {money(A['price'])}, {pc(A['change_pct'])}.",
         "osd": f"{A['name']}: {money(A['price'])}", "emphasis": A["name"].split()[0], "visual": "chart", "ticker": a},
        {"say": f"Your friend's {B['name']} money is now {money(B['price'])}, {pc(B['change_pct'])}.",
         "osd": f"{B['name']}: {money(B['price'])}", "emphasis": B["name"].split()[0], "visual": "chart", "ticker": b},
        {"say": f"{win['name']} wins by {money(diff)}. Same money, same day, very different year.",
         "osd": f"{win['name']} wins by {money(diff)}", "emphasis": "wins", "visual": "compare",
         "ticker": a, "compare_with": b},
        {"say": "Past returns never promise future ones. Which two should we test next? Tell us in the comments.",
         "osd": "Which pair next?", "emphasis": "next", "visual": "list", "ticker": win is A and a or b},
    ]
    title = f"$1,000 in {A['name']} vs {B['name']}: 1 year later"
    if len(title) > 60:
        title = f"$1,000: {A['name']} vs {B['name']}"
    desc = (f"{money(STAKE)} in {A['name']} vs {money(STAKE)} in {B['name']}, from the {A['start']} close to the "
            f"{A['as_of']} close.\n{A['name']}: {money(A['price'])} ({A['change_pct']:+.1f}%)\n"
            f"{B['name']}: {money(B['price'])} ({B['change_pct']:+.1f}%)\n\n"
            "Price change only (dividends, fees and taxes not included). Data: Yahoo Finance closing prices.\n"
            f"Past performance does not predict future results. Not financial advice.\n\n"
            "#shorts #stocks #investing")
    tags = ["if you invested 1000", f"{A['name'].lower()} vs {B['name'].lower()}", f"{A['name'].lower()} stock",
            f"{B['name'].lower()} stock", "stock comparison", "investing", "stock market"]
    return {"pair": [a, b], "snapshot": {"tickers": tickers}, "beats": beats, "title": title,
            "yt": {"description": desc, "tags": tags}, "winner": win["name"], "done": done}


def record(job, video_id):
    job["done"].append({"pair": job["pair"], "date": datetime.date.today().isoformat(), "video_id": video_id})
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(job["done"], indent=1))


if __name__ == "__main__":
    j = build()
    out = HERE / "out" / f"invest_vs_test.mp4"
    out.parent.mkdir(exist_ok=True)
    print(j["title"]); print(json.dumps(j["beats"], indent=1))
    if "--no-render" not in sys.argv:
        print(renderer.render_pillow(j["beats"], j["snapshot"], out, j["pair"][0]))
