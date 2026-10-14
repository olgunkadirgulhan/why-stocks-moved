#!/usr/bin/env python3
"""Then vs Now — "eskiden ne kadardı, şimdi ne kadar" (2026-10-14, Why Stocks Moved kanalının yeni konsepti).

Her rakam ABD Çalışma İstatistikleri Bürosu'ndan (BLS): ortalama fiyat serileri (APU…, ABD şehir ortalaması, yıllık
ortalama) ve tüketici fiyat endeksi (CPI-U, CUUR0000SA0). Uydurma rakam yok; kaynak her açıklamada yazar.
Görsel kimlik (diğer kanallara benzemesin): koyu petrol zemin, kâğıt fişler, Courier Prime + Bebas Neue, kırmızı damga.

  python tvn.py --dry-run [--videos 2] [--format item|dollar|basket|wage|race]
"""
import asyncio
import datetime
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DATA = HERE / 'data' / 'tvn'
OUT = HERE / 'out' / 'tvn'
STATE = DATA / 'state.json'
W, H, FPS = 1080, 1920, 30
BG, BG2 = (16, 54, 62), (10, 38, 46)
PAPER, INK, FADED, RED, YEL, GREEN = (250, 245, 230), (35, 32, 30), (120, 112, 100), (205, 40, 40), (255, 205, 60), (60, 160, 90)
MONO = str(HERE / 'fonts' / 'tvn' / 'CourierPrime-Bold.ttf')
DISP = str(HERE / 'fonts' / 'tvn' / 'BebasNeue-Regular.ttf')
VOICE = os.environ.get('TVN_VOICE', 'en-US-ChristopherNeural')   # bu kanalın kendi sesi
DRY = '--dry-run' in sys.argv
CPI = {int(k): v for k, v in json.loads((DATA / 'cpi_annual.json').read_text()).items()}
PRICES = json.loads((DATA / 'prices.json').read_text())
for _v in PRICES.values():
    _v['years'] = {int(k): x for k, x in _v['years'].items()}
# Federal asgari ücret (yılın büyük bölümünde geçerli olan; ABD Çalışma Bakanlığı)
MINWAGE = {**{y: 4.25 for y in range(1991, 1997)}, 1997: 4.75, **{y: 5.15 for y in range(1998, 2008)}, 2008: 5.85, 2009: 6.55,
           **{y: 7.25 for y in range(2010, 2027)}}
SHORT = {'eggs': 'EGGS / DOZEN', 'milk': 'MILK / GALLON', 'bread': 'WHITE BREAD/LB', 'gas': 'GAS / GALLON',
         'coffee': 'COFFEE / LB', 'bananas': 'BANANAS / LB', 'beef': 'GROUND BEEF/LB', 'chicken': 'CHICKEN / LB',
         'oranges': 'ORANGES / LB', 'tomatoes': 'TOMATOES / LB', 'sugar': 'SUGAR / LB', 'electricity': 'POWER/100 KWH',
         'cheese': 'CHEDDAR / LB', 'rice': 'RICE / LB', 'bacon': 'BACON / LB'}
SOURCE = ('Source: U.S. Bureau of Labor Statistics — Average Price Data (U.S. city average) and Consumer Price Index '
          '(CPI-U), annual averages.')


def log(m): print(m, flush=True)


def money(v):
    return f'${v:,.2f}' if v < 100 else f'${v:,.0f}'


def latest(item):
    return max(PRICES[item]['years'])


def adj(v, y0, y1):
    """y0 dolarını y1 dolarına çevir (CPI-U yıllık ortalama)."""
    return v * CPI[y1] / CPI[y0]


# ---------------------------------------------------------------- konu seçimi
def pick(state, rnd, fmt=None):
    done = {json.dumps(d['key']) for d in state.get('done', [])}
    last_fmts = [d['fmt'] for d in state.get('done', [])][-3:]
    fmts = ['item', 'item', 'dollar', 'basket', 'wage', 'race']
    for _ in range(400):
        f = fmt or rnd.choice([x for x in fmts if last_fmts.count(x) < 2] or fmts)
        if f == 'item':
            it = rnd.choice(list(PRICES)); y0 = rnd.choice([y for y in PRICES[it]['years'] if y <= latest(it) - 10])
            key = ['item', it, y0]
        elif f == 'dollar':
            y0 = rnd.choice(list(range(1920, 2016, 5))); key = ['dollar', y0]
        elif f == 'basket':
            y0 = rnd.choice(list(range(1996, 2016))); key = ['basket', y0]
        elif f == 'wage':
            it = rnd.choice([k for k in PRICES if k != 'electricity']); y0 = rnd.choice([y for y in PRICES[it]['years'] if y in MINWAGE and y <= 2008])
            key = ['wage', it, y0]
        else:
            a, b = rnd.sample(list(PRICES), 2); y0 = rnd.choice([y for y in range(1996, 2011) if y in PRICES[a]['years'] and y in PRICES[b]['years']])
            key = ['race', a, b, y0]
        if json.dumps(key) not in done:
            return f, key
    raise RuntimeError('yeni konu kalmadı')


# ---------------------------------------------------------------- senaryo (beat = söylenen + ekran)
def build(f, key):
    if f == 'item':
        _, it, y0 = key; P = PRICES[it]; y1 = latest(it); p0, p1 = P['years'][y0], P['years'][y1]
        inf = adj(p0, y0, y1); pct = (p1 / p0 - 1) * 100; faster = p1 > inf
        beats = [dict(say=f"{P['phrase']} in {y0} cost {money(p0)}. Guess what it costs now.", show='then'),
                 dict(say=f"In {y1}? {money(p1)}.", show='now'),
                 dict(say=f"That's {pct:.0f} percent more.", show='stamp'),
                 dict(say=f"If it had only followed inflation, it would cost {money(inf)}. "
                          + ("So it went up faster than everything else." if faster else "So it actually got cheaper in real terms."), show='inflation'),
                 dict(say=f"What did you pay last time? Tell me below.", show='cta')]
        rec = dict(lines=[(SHORT[it], p0, p1)], y0=y0, y1=y1, inf=[inf], pct=pct)
        title = f"{P['phrase'].replace('A ', '').replace('a ', '').capitalize()}: {y0} Price vs {y1} {P['emoji']}"
        if len(title) > 70: title = f"{P['label'].title()}: {y0} vs {y1} {P['emoji']}"
        desc = (f"{P['phrase']} cost {money(p0)} in {y0} and {money(p1)} in {y1} (+{pct:.0f}%). Adjusted only for "
                f"inflation it would be {money(inf)}.\n\nSeries: {P['series']} (BLS average price, U.S. city average).")
    elif f == 'dollar':
        _, y0 = key; y1 = max(CPI); v = adj(100, y0, y1); k = v / 100
        beats = [dict(say=f"Here is what one hundred dollars from {y0} is worth today.", show='then'),
                 dict(say=f"In {y1} money, it's {money(v)}.", show='now'),
                 dict(say=f"Prices are about {k:.1f} times higher than in {y0}.", show='stamp'),
                 dict(say=f"Same bill, same paper. It just buys {100 / k:.0f} percent of what it used to.", show='inflation'),
                 dict(say="Which year do you want to see next? Comment below.", show='cta')]
        rec = dict(lines=[('$100 BILL', 100, v)], y0=y0, y1=y1, inf=[None], pct=(k - 1) * 100)
        title = f"$100 in {y0} Is Worth This Today 💵"
        desc = f"$100 in {y0} has the same buying power as {money(v)} in {y1} (CPI-U annual averages, {CPI[y0]} → {CPI[y1]})."
    elif f == 'basket':
        _, y0 = key; items = [k for k in random.Random(y0).sample(['eggs', 'milk', 'bread', 'beef', 'coffee', 'bananas', 'chicken', 'cheese'], 4) if y0 in PRICES[k]['years']]
        y1 = min(latest(k) for k in items)
        lines = [(SHORT[k], PRICES[k]['years'][y0], PRICES[k]['years'][y1]) for k in items]
        t0, t1 = sum(a for _, a, _ in lines), sum(b for _, _, b in lines); pct = (t1 / t0 - 1) * 100; inf = adj(t0, y0, y1)
        beats = [dict(say=f"The same grocery run, {y0} versus {y1}. In {y0}, these {len(items)} items cost {money(t0)}.", show='then'),
                 dict(say=f"Today the same cart costs {money(t1)}.", show='now'),
                 dict(say=f"Up {pct:.0f} percent.", show='stamp'),
                 dict(say=f"With plain inflation it would be {money(inf)}. "
                          + ("Groceries outran inflation." if t1 > inf else "Groceries actually trailed inflation."), show='inflation'),
                 dict(say="What would this cart cost where you live? Comment below.", show='cta')]
        rec = dict(lines=lines, y0=y0, y1=y1, inf=[inf], pct=pct, total=(t0, t1))
        title = f"The Same Grocery Run: {y0} vs {y1} 🛒"
        desc = f"Basket: {', '.join(PRICES[k]['label'].lower() for k in items)}. {y0}: {money(t0)} · {y1}: {money(t1)} (+{pct:.0f}%)."
    elif f == 'wage':
        _, it, y0 = key; P = PRICES[it]; y1 = latest(it); p0, p1 = P['years'][y0], P['years'][y1]
        m0, m1 = p0 / MINWAGE[y0] * 60, p1 / MINWAGE[y1] * 60
        beats = [dict(say=f"How long did you have to work for {P['phrase'].lower()}? In {y0}, at the federal minimum wage of "
                          f"{money(MINWAGE[y0])}, about {m0:.0f} minutes.", show='then'),
                 dict(say=f"In {y1}, at {money(MINWAGE[y1])} an hour, it takes {m1:.0f} minutes.", show='now'),
                 dict(say=("That's longer than before." if m1 > m0 else "That's actually shorter than before."), show='stamp'),
                 dict(say=f"The price went from {money(p0)} to {money(p1)}, while the federal minimum only went from "
                          f"{money(MINWAGE[y0])} to {money(MINWAGE[y1])}. Many states pay more than the federal minimum.", show='inflation'),
                 dict(say="How many minutes would it take you? Comment below.", show='cta')]
        rec = dict(lines=[(SHORT[it], p0, p1)], y0=y0, y1=y1, inf=[None], pct=(m1 / m0 - 1) * 100, minutes=(m0, m1))
        title = f"Minutes of Work to Buy {P['label'].split(',')[0].title()}: {y0} vs {y1} ⏱️"
        desc = (f"Federal minimum wage: {money(MINWAGE[y0])} ({y0}) vs {money(MINWAGE[y1])} ({y1}). Price: {money(p0)} vs "
                f"{money(p1)}. Minutes of work: {m0:.0f} vs {m1:.0f}. Many states set a higher minimum.\n\nSeries: {P['series']}.")
    else:
        _, a, b, y0 = key; A, B = PRICES[a], PRICES[b]; y1 = min(latest(a), latest(b))
        pa, pb = (A['years'][y1] / A['years'][y0] - 1) * 100, (B['years'][y1] / B['years'][y0] - 1) * 100
        win = A if pa > pb else B
        beats = [dict(say=f"Since {y0}, what got more expensive: {A['label'].split(',')[0].lower()} or {B['label'].split(',')[0].lower()}? Guess now.", show='then'),
                 dict(say=f"{A['label'].split(',')[0].title()}: from {money(A['years'][y0])} to {money(A['years'][y1])}. "
                          f"{B['label'].split(',')[0].title()}: from {money(B['years'][y0])} to {money(B['years'][y1])}.", show='now'),
                 dict(say=f"{win['label'].split(',')[0].title()} wins, up {max(pa, pb):.0f} percent.", show='stamp'),
                 dict(say=f"The other one rose {min(pa, pb):.0f} percent. Did you guess right?", show='inflation'),
                 dict(say="Which two should I compare next? Comment below.", show='cta')]
        rec = dict(lines=[(SHORT[a], A['years'][y0], A['years'][y1]), (SHORT[b], B['years'][y0], B['years'][y1])],
                   y0=y0, y1=y1, inf=[None, None], pct=max(pa, pb), race=(pa, pb))
        title = f"{A['label'].split(',')[0].title()} vs {B['label'].split(',')[0].title()}: What Got Pricier Since {y0}?"
        desc = (f"{A['label']}: {money(A['years'][y0])} → {money(A['years'][y1])} (+{pa:.0f}%). {B['label']}: "
                f"{money(B['years'][y0])} → {money(B['years'][y1])} (+{pb:.0f}%). Series: {A['series']}, {B['series']}.")
    return dict(fmt=f, key=key, beats=beats, rec=rec, title=title[:95],
                desc=desc + f"\n\n{SOURCE}\nNot financial advice.\n\n#thenvsnow #prices #inflation #nostalgia #shorts")


# ---------------------------------------------------------------- çizim
_FC = {}


def font(path, sz):
    k = (path, sz)
    if k not in _FC: _FC[k] = ImageFont.truetype(path, sz)
    return _FC[k]


def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


def back(x):
    x = max(0.0, min(1.0, x)); c = 1.7; v = x - 1
    return 1 + (c + 1) * v ** 3 + c * v ** 2


def background():
    img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)
    for y in range(0, H, 6):
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * y / H) for a, b in zip(BG, BG2)))
    for x in range(0, W, 60): d.line([(x, 0), (x, H)], fill=(255, 255, 255, 8) if False else (22, 62, 70), width=1)
    d.text((W // 2, 120), 'THEN  vs  NOW', font=font(DISP, 120), fill=YEL, anchor='mm')
    d.text((W // 2, 1830), 'Data: U.S. Bureau of Labor Statistics', font=font(MONO, 30), fill=(150, 185, 190), anchor='mm')
    return img


def fmtv(v, unit):
    return f'{v:.0f} MIN' if unit == 'min' else money(v)


def receipt(img, x, y, w, h, prog, year, lines, total, stamp=None, now=False, lh=74, fs=50, total_unit='$', hy=0):
    """Kâğıt fiş: prog 0→1 yazıcıdan çıkış + satırların daktiloyla yazılması. lines: [(etiket, değer, birim)]."""
    hh = int(h * ease(prog * 1.6))
    if hh < 10: return
    paper = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(paper)
    zig = [(i * 30, 0 if i % 2 == 0 else 16) for i in range(w // 30 + 2)]
    d.polygon([(0, 16)] + zig + [(w, h - 16)] + [(w - i * 30, h - (0 if i % 2 == 0 else 16)) for i in range(w // 30 + 2)] + [(0, h - 16)], fill=PAPER)
    d.text((w // 2, 92 - hy // 2), str(year), font=font(DISP, 130 - hy), fill=RED if now else INK, anchor='mm')
    d.line([(36, 160 - hy), (w - 36, 160 - hy)], fill=FADED, width=3)
    rows = [f'{lab[:15]:<15}{fmtv(val, unit):>9}' for lab, val, unit in lines]
    total_chars = sum(len(r) for r in rows)
    nchars = int(max(0.0, prog - 0.15) / 0.55 * total_chars)
    yy = 190 - hy; shown = 0; f = font(MONO, fs)
    for r in rows:
        d.text((36, yy), r[:max(0, nchars - shown)], font=f, fill=INK); shown += len(r); yy += lh
    if nchars >= total_chars:
        d.line([(30, yy + 4), (w - 30, yy + 4)], fill=FADED, width=3)
        d.text((36, yy + 22), 'WORK TIME' if total_unit == 'min' else 'TOTAL', font=font(MONO, fs + 10), fill=INK)
        d.text((w - 36, yy + 22), fmtv(total, total_unit), font=font(MONO, fs + 16), fill=RED if now else INK, anchor='ra')
    img.paste(paper.crop((0, 0, w, hh)), (x, y), paper.crop((0, 0, w, hh)))
    if stamp and stamp[1] > 0:
        txt, sp = stamp
        s = 1.7 - 0.7 * back(sp)
        st = Image.new('RGBA', (760, 260), (0, 0, 0, 0)); sd = ImageDraw.Draw(st)
        sd.rounded_rectangle([10, 10, 750, 250], radius=30, outline=RED + (235,), width=16)
        sd.text((380, 134), txt, font=font(DISP, 190), fill=RED + (235,), anchor='mm')
        st = st.rotate(-10, expand=True, resample=Image.BICUBIC); st = st.resize((int(st.width * s), int(st.height * s)))
        img.paste(st, (x + w - st.width + 40, y + h - st.height // 3), st)


def frame(base, v, beat_i, t, kind):
    img = base.copy(); d = ImageDraw.Draw(img)
    rec = v['rec']; y0, y1 = rec['y0'], rec['y1']; wage = v['fmt'] == 'wage'
    l0 = [(l, a, '$') for l, a, _ in rec['lines']]; l1 = [(l, b, '$') for l, _, b in rec['lines']]
    if wage:
        tot0, tot1, tu = rec['minutes'][0], rec['minutes'][1], 'min'
        l0.append(('MIN WAGE/HOUR', MINWAGE[y0], '$')); l1.append(('MIN WAGE/HOUR', MINWAGE[y1], '$'))
    else:
        tot0, tot1, tu = sum(a for _, a, _ in l0), sum(b for _, b, _ in l1), '$'
    n = len(l0); lh, fs = (110, 60) if n <= 2 else (80, 52) if n <= 3 else (58, 46)
    hy = 40 if n >= 4 else 0
    h = 230 - hy + lh * n + 110
    has_inf = rec['inf'][0] is not None
    need = 2 * h + 50 + 200 + (190 if has_inf else 0) + 160
    top = 200 + max(0, (1620 - need) // 2)
    p_then = 1.0 if beat_i > 0 else min(1.0, t / 2.2)
    p_now = 0.0 if beat_i < 1 else (1.0 if beat_i > 1 else min(1.0, t / 2.0))
    stamp_txt = (f"+{rec['pct']:.0f}%" if rec['pct'] >= 0 else f"{rec['pct']:.0f}%")
    if v['fmt'] == 'dollar': stamp_txt = f"x{1 + rec['pct'] / 100:.1f}"
    if wage: stamp_txt = f"{'+' if rec['pct'] >= 0 else ''}{rec['pct']:.0f}% TIME"
    sp = 0.0 if beat_i < 2 else (1.0 if beat_i > 2 else min(1.0, t / 0.35))
    receipt(img, 60, top, 960, h, p_then, y0, l0, tot0, lh=lh, fs=fs, total_unit=tu, hy=hy)
    receipt(img, 60, top + h + 50, 960, h, p_now, y1, l1, tot1, stamp=(stamp_txt, sp), now=True, lh=lh, fs=fs, total_unit=tu, hy=hy)
    by = top + 2 * h + 50 + 200
    if beat_i >= 3 and rec['inf'][0] is not None:
        a = ease(t / 0.6) if beat_i == 3 else 1.0
        d.rounded_rectangle([60, by - 80, 1020, by + 80], radius=24, fill=(255, 255, 255))
        d.text((540, by - 30), 'IF IT ONLY FOLLOWED INFLATION', font=font(MONO, 38), fill=FADED, anchor='mm')
        d.text((540, by + 32), money(rec['inf'][0] * a), font=font(DISP, 96), fill=GREEN, anchor='mm')
    if beat_i == 4:
        cy = by + (190 if has_inf else 0)
        cta = {'dollar': 'WHICH YEAR NEXT?', 'race': 'DID YOU GUESS RIGHT?', 'wage': 'HOW LONG FOR YOU?'}.get(v['fmt'], 'WHAT DID YOU PAY?')
        d.rounded_rectangle([90, cy - 70, 990, cy + 70], radius=34, fill=YEL)
        d.text((540, cy), cta, font=font(DISP, 100), fill=INK, anchor='mm')
    return img


# ---------------------------------------------------------------- ses + video
def tts(text, path):
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, VOICE, rate='+6%').save(str(path))
    asyncio.run(go())


def dur(p):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)], capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def render(v, mp4):
    tmp = mp4.with_suffix(''); tmp.mkdir(parents=True, exist_ok=True)
    auds, durs = [], []
    for i, b in enumerate(v['beats']):
        a = tmp / f'a{i}.mp3'
        try:
            tts(b['say'], a)
        except Exception:
            import renderer
            a = tmp / f'a{i}.wav'; renderer.piper_tts(b['say'], a)
        auds.append(a); durs.append(dur(a) + 0.35)
    lst = tmp / 'a.txt'; lst.write_text(''.join(f"file '{a}'\nfile '{tmp / 'gap.wav'}'\n" for a in auds))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'lavfi', '-i', 'anullsrc=r=24000:cl=mono', '-t', '0.35', str(tmp / 'gap.wav')], check=True)
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-ar', '44100', '-ac', '2', str(tmp / 'voice.wav')], check=True)
    base = background()
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                          '-i', str(tmp / 'voice.wav'), '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
                          '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', str(mp4)], stdin=subprocess.PIPE)
    for i, dd in enumerate(durs):
        for k in range(int(dd * FPS)):
            p.stdin.write(frame(base, v, i, k / FPS, v['fmt']).tobytes())
    p.stdin.close(); p.wait()
    return mp4


# ---------------------------------------------------------------- yükleme (kategori: Eğitim)
def upload(mp4, v, publish_at):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from common import yt_creds
    body = {"snippet": {"title": v['title'], "description": v['desc'], "categoryId": "27", "defaultLanguage": "en",
                        "defaultAudioLanguage": "en", "tags": ['then vs now', 'prices then and now', 'inflation', 'cost of living',
                                                              'nostalgia', 'grocery prices', 'how much things cost']},
            "status": {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": False}}
    mode = os.environ.get("YOUTUBE_PRIVACY", "unlisted")
    if mode == "scheduled":
        body["status"].update(privacyStatus="private", publishAt=publish_at)
    else:
        body["status"]["privacyStatus"] = mode
    api = build("youtube", "v3", credentials=yt_creds(), cache_discovery=False)
    return api.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(mp4), resumable=True)).execute()["id"]


# ---------------------------------------------------------------- ana akış
def main():
    n = int(sys.argv[sys.argv.index('--videos') + 1]) if '--videos' in sys.argv else 1
    fmt = sys.argv[sys.argv.index('--format') + 1] if '--format' in sys.argv else None
    state = json.loads(STATE.read_text()) if STATE.exists() else {'done': []}
    rnd = random.Random()
    OUT.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        f, key = pick(state, rnd, fmt)
        v = build(f, key)
        log(f'[tvn] {f} {key} → {v["title"]}')
        mp4 = render(v, OUT / f'{datetime.date.today()}_{i}.mp4')
        if DRY:
            log(f'  [dry-run] {mp4}'); continue
        from daily_viral import publish_time, SLOTS
        vid = upload(mp4, v, publish_time(SLOTS[i % len(SLOTS)][0]))
        state['done'].append(dict(fmt=f, key=key, video_id=vid, date=str(datetime.date.today()), title=v['title']))
        STATE.write_text(json.dumps(state, indent=1))
        log(f'  yüklendi https://youtu.be/{vid}')


if __name__ == '__main__':
    main()
