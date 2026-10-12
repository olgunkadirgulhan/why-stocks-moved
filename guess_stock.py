#!/usr/bin/env python3
"""guess_stock.py — "Guess the Stock" oyunu: adı gizli gerçek 1 yıllık grafik + 3 ipucu + cevap (LLM'siz, yfinance).
2026-10-12: kanal medyanı 27 izlenme; etkileşimli tahmin oyunu izleyiciyi yorum yazmaya ve sonuna kadar izlemeye iter.
Yatırım tavsiyesi yok: şirket tanıtım ipuçları + geçmiş fiyat; her videoda uyarı.

  python guess_stock.py            # sıradaki hisseyi render eder (out/guess_test.mp4)
"""
import datetime
import json
import sys
from pathlib import Path

import yfinance as yf

import renderer

HERE = Path(__file__).resolve().parent
STATE = HERE / "data" / "guess_stock.json"
MYSTERY = "MYSTERY"
# sembol: (ad, sektör ipucu, ürün ipucu, harf ipucu) — herkesin tanıdığı markalar, sadece genel bilgi
POOL = {
    "AAPL": ("Apple", "It makes phones and computers", "Its logo is a fruit with a bite", "It starts with A"),
    "NVDA": ("Nvidia", "It designs computer chips", "Gamers and AI labs love its graphics cards", "It starts with N"),
    "TSLA": ("Tesla", "It makes electric cars", "It also sells home batteries", "It starts with T"),
    "AMZN": ("Amazon", "It is an online store", "It also runs a huge cloud business", "It starts with A"),
    "MSFT": ("Microsoft", "It is a software company", "It makes Windows and Xbox", "It starts with M"),
    "GOOGL": ("Google", "It is an internet company", "Most people use its search engine every day", "It starts with G"),
    "META": ("Meta", "It runs social media apps", "It owns Instagram and WhatsApp", "It starts with M"),
    "NFLX": ("Netflix", "It is a streaming service", "It made Stranger Things", "It starts with N"),
    "DIS": ("Disney", "It is an entertainment company", "It has theme parks and a famous mouse", "It starts with D"),
    "NKE": ("Nike", "It sells sportswear", "Its logo is a swoosh", "It starts with N"),
    "KO": ("Coca-Cola", "It sells drinks", "Its classic bottle is red", "It starts with C"),
    "MCD": ("McDonald's", "It is a restaurant chain", "Its logo is golden arches", "It starts with M"),
    "SBUX": ("Starbucks", "It sells coffee", "Its logo is a green mermaid", "It starts with S"),
    "COST": ("Costco", "It is a warehouse store", "Members love its hot dog deal", "It starts with C"),
    "WMT": ("Walmart", "It is a giant retailer", "It has thousands of supercenters", "It starts with W"),
    "UBER": ("Uber", "It is a ride app", "It also delivers food", "It starts with U"),
    "SPOT": ("Spotify", "It is a music app", "It makes yearly listening recaps", "It starts with S"),
    "ABNB": ("Airbnb", "It is a travel app", "You can book someone's home", "It starts with A"),
    "AMD": ("AMD", "It designs computer chips", "Its chips power game consoles", "It starts with A"),
    "BA": ("Boeing", "It builds airplanes", "It makes the 737", "It starts with B"),
    "PEP": ("PepsiCo", "It sells drinks and snacks", "It owns Lay's chips", "It starts with P"),
    "CMG": ("Chipotle", "It is a restaurant chain", "It is famous for burritos", "It starts with C"),
    "F": ("Ford", "It makes cars", "It makes the Mustang", "It starts with F"),
    "GME": ("GameStop", "It is a video game retailer", "It became a famous meme stock", "It starts with G"),
}


def pct_text(v):
    return f"{'up' if v >= 0 else 'down'} {abs(v):.0f} percent"


def next_symbol():
    done = json.loads(STATE.read_text()) if STATE.exists() else []
    recent = {d["symbol"] for d in done[-(len(POOL) - 4):]}
    fresh = [s for s in POOL if s not in recent]
    return (fresh[len(done) % len(fresh)] if fresh else list(POOL)[len(done) % len(POOL)]), done


def build():
    sym, done = next_symbol()
    name, h1, h2, h3 = POOL[sym]
    h = yf.Ticker(sym).history(period="1y", interval="1d")["Close"].dropna()
    if len(h) < 200:
        raise RuntimeError(f"{sym}: 1 yıllık veri yok ({len(h)})")
    vals = [float(x) for x in h]
    series = [round(v, 2) for v in vals[::5]] + ([round(vals[-1], 2)] if (len(vals) - 1) % 5 else [])
    pct = (vals[-1] / vals[0] - 1) * 100
    base = {"price": round(vals[-1], 2), "change_pct": round(pct, 2), "change_5d_pct": round(pct, 2), "series": series,
            "as_of": str(h.index[-1].date()), "start": str(h.index[0].date())}
    tickers = {MYSTERY: dict(base, name="???"), sym: dict(base, name=name)}
    beats = [
        {"say": "Guess the stock! This is one real year of its price. You get three hints.",
         "osd": "GUESS THE STOCK", "emphasis": "GUESS", "visual": "chart", "ticker": MYSTERY},
        {"say": f"Hint one: {h1}.", "osd": f"Hint 1: {h1}", "emphasis": "Hint", "visual": "chart", "ticker": MYSTERY},
        {"say": f"Hint two: {h2}.", "osd": f"Hint 2: {h2}", "emphasis": "Hint", "visual": "chart", "ticker": MYSTERY},
        {"say": f"Last hint: {h3}. Comment your guess now!", "osd": f"Hint 3: {h3}", "emphasis": "Hint",
         "visual": "chart", "ticker": MYSTERY},
        {"say": f"It is {name}! {pct_text(pct)} over the past year. Did you get it?", "osd": f"It's {name}!",
         "emphasis": name.split()[0], "visual": "chart", "ticker": sym},
        {"say": "How many hints did you need? Tell us below. This is not financial advice.",
         "osd": "1, 2 or 3 hints?", "emphasis": "hints", "visual": "text", "ticker": sym},
    ]
    sector = h1.replace("It is ", "").replace("It ", "").rstrip(".")
    titles = [f"Guess the Stock From Its Chart 🤔 ({sector})", "Can You Guess This Stock in 3 Hints? 📈",
              f"Name This Stock! Hint: {sector} 🤔", "Guess the Company From One Year of Its Chart 📉📈"]
    title = titles[len(done) % len(titles)][:95]
    desc = (f"Guess the stock from one year of its real chart, then 3 hints. Answer: {name} ({sym}), "
            f"{pct:+.1f}% from the {base['start']} close to the {base['as_of']} close.\n\n"
            "How many hints did you need? Comment below 👇\n\n"
            "Price data: Yahoo Finance closing prices. For entertainment and education only, not financial advice.\n\n"
            "#shorts #stocks #guessthestock")
    tags = ["guess the stock", "stock quiz", "stock chart", f"{name.lower()} stock", "stock market", "investing",
            "finance quiz"]
    return {"symbol": sym, "snapshot": {"tickers": tickers}, "beats": beats, "title": title,
            "yt": {"description": desc, "tags": tags}, "done": done}


def record(job, video_id):
    job["done"].append({"symbol": job["symbol"], "date": datetime.date.today().isoformat(), "video_id": video_id})
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(job["done"], indent=1))


if __name__ == "__main__":
    j = build()
    out = HERE / "out" / "guess_test.mp4"
    out.parent.mkdir(exist_ok=True)
    print(j["title"]); print(json.dumps(j["beats"], indent=1))
    if "--no-render" not in sys.argv:
        print(renderer.render_pillow(j["beats"], j["snapshot"], out, MYSTERY))
