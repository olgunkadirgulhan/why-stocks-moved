#!/usr/bin/env python3
"""Then vs Now — uzun video (16:9, ~4-6 dk): "{yıl} vs bugün, her fiyat" (2026-10-14).

Bir yıl seçilir; o yılın BLS ortalama fiyatı olan bütün ürünler tek tek fiş fişe karşılaştırılır, sonunda enflasyona göre
sıralama gelir. İki kip: 'prices' (fiyat + enflasyon) ve 'work' (asgari ücretle kaç dakika çalışmak gerekiyordu).
Konu kimliği ['long', yıl, kip] data/tvn/state.json'da Short'larla aynı listede tutulur; tekrar edilmez.

  python tvn_long.py --dry-run [--year 2005] [--mode prices|work]
"""
import json
import random
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

import tvn
from tvn import C, money, adj, latest, PRICES, SHORT, MINWAGE, CPI, font, ease, DISP, MONO, YEL, RED, GREEN, INK, FADED, PAPER, BG, BG2

W, H, FPS = 1920, 1080, 30
DRY = '--dry-run' in sys.argv


def pick(state, rnd, year=None, mode=None):
    done = {json.dumps(d['key']) for d in state.get('done', [])}
    for _ in range(300):
        y0 = year or rnd.choice(range(1995, 2016)); m = mode or rnd.choice(['prices', 'work'])
        key = ['long', y0, m]
        if json.dumps(key) not in done and len(items_for(y0)) >= 10:
            return key
    raise RuntimeError('yeni uzun konu kalmadı')


def items_for(y0):
    return [k for k in PRICES if y0 in PRICES[k]['years'] and latest(k) - y0 >= 8]


def name(k):
    return PRICES[k]['phrase'][0].lower() + PRICES[k]['phrase'][1:]


def build(key, rnd):
    _, y0, mode = key
    its = items_for(y0); rnd.shuffle(its)
    y1 = max(latest(k) for k in its)
    rows = []
    for k in its:
        p0, p1 = PRICES[k]['years'][y0], PRICES[k]['years'][latest(k)]; yk = latest(k)
        inf = adj(p0, y0, yk); pct = (p1 / p0 - 1) * 100; rows.append(dict(k=k, p0=p0, p1=p1, y1=yk, inf=inf, pct=pct, real=(p1 / inf - 1) * 100))
    order = sorted(rows, key=lambda r: -r['real'])
    for r in rows:
        rank = order.index(r) + 1; k = r['k']; nm = name(k)
        s = [C(rnd, f"{nm[0].upper() + nm[1:]}. In {y0}: {money(r['p0'])}. In {r['y1']}: {money(r['p1'])}.",
               f"Next, {nm}. {money(r['p0'])} back then, {money(r['p1'])} now.",
               f"{nm[0].upper() + nm[1:]} went from {money(r['p0'])} to {money(r['p1'])}.")]
        s.append(f"That is {'up' if r['pct'] >= 0 else 'down'} {abs(r['pct']):.0f} percent.")
        if mode == 'work':
            m0, m1 = r['p0'] / MINWAGE[y0] * 60, r['p1'] / MINWAGE[r['y1']] * 60
            s.append(C(rnd, f"At the federal minimum wage, it took {m0:.0f} minutes of work in {y0}, and {m1:.0f} minutes now.",
                       f"In minimum wage work, that is {m0:.0f} minutes then and {m1:.0f} minutes today."))
            r['m'] = (m0, m1)
        if r['p1'] > r['inf']:
            s.append(C(rnd, f"If it had only kept up with inflation, it would cost {money(r['inf'])}, so it rose faster than prices overall.",
                       f"Inflation alone would make it {money(r['inf'])}. It beat that by {money(r['p1'] - r['inf'])}."))
        else:
            s.append(C(rnd, f"Inflation alone would make it {money(r['inf'])}, so in real terms it is cheaper than in {y0}.",
                       f"Adjusted for inflation it should be {money(r['inf'])}. It is {money(r['inf'] - r['p1'])} below that, a real price drop."))
        if rank <= 3: s.append(C(rnd, f"That is number {rank} on today's list for real price increases.", f"Remember this one: it ranks number {rank} for real increases."))
        elif rank > len(rows) - 2: s.append(C(rnd, "That puts it near the bottom of today's list.", "One of the best deals on this list, in real terms."))
        r['say'] = ' '.join(s)
    k100 = adj(100, y0, max(CPI))
    intro = C(rnd, f"Let's go back to {y0}. We will look at {len(rows)} everyday prices from that year, see what they cost now, and check which ones beat inflation.",
              f"{y0} versus today. {len(rows)} everyday items, real prices from the Bureau of Labor Statistics, and one question: which ones got more expensive than they should have?")
    context = (f"First, some context. One hundred dollars in {y0} has the same buying power as {money(k100)} today. "
               f"The federal minimum wage was {money(MINWAGE[y0])} an hour; now it is {money(MINWAGE[max(MINWAGE)])}.")
    top, bot = order[0], order[-1]
    summary = (f"Here is the full ranking, adjusted for inflation. The biggest real increase: {name(top['k'])}, {top['real']:+.0f} percent above inflation. "
               f"The best deal: {name(bot['k'])}, {bot['real']:+.0f} percent compared with inflation.").replace('+', 'plus ').replace('-', 'minus ')
    beat_n = sum(1 for r in rows if r['p1'] > r['inf'])
    summary += f" In total, {beat_n} of {len(rows)} items rose faster than inflation."
    outro = C(rnd, f"What do you remember paying in {y0}? Tell me in the comments, and tell me which year I should check next.",
              f"Which price surprised you most? Comment below, and tell me your year.")
    beats = [intro, context] + [r['say'] for r in rows] + [summary, outro]
    title = (C(rnd, f"Then vs Now: {len(rows)} Everyday Prices, {y0} vs {y1}", f"{y0} Prices vs Today: {len(rows)} Items Compared",
               f"What Everything Cost in {y0} vs Now ({len(rows)} Items)") if mode == 'prices' else
             C(rnd, f"Minutes of Work: {y0} vs {y1}, {len(rows)} Everyday Items", f"How Long You Had to Work for Groceries in {y0} vs Now"))
    desc = (f"{len(rows)} everyday prices, {y0} vs latest year, from the U.S. Bureau of Labor Statistics average price data (U.S. city average, annual averages).\n\n"
            + '\n'.join(f"{PRICES[r['k']]['label'].title()}: {money(r['p0'])} → {money(r['p1'])} ({r['pct']:+.0f}%; inflation-only {money(r['inf'])})" for r in rows)
            + f"\n\n$100 in {y0} = {money(k100)} today (CPI-U). Federal minimum wage {money(MINWAGE[y0])} in {y0}.\n\n{tvn.SOURCE}\nNot financial advice.\n\n#thenvsnow #prices #inflation #nostalgia")
    return dict(key=key, y0=y0, mode=mode, rows=rows, order=order, beats=beats, title=title[:95], desc=desc, k100=k100)


def background():
    img = Image.new('RGB', (W, H), BG); d = ImageDraw.Draw(img)
    for y in range(0, H, 6):
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * y / H) for a, b in zip(BG, BG2)))
    for x in range(0, W, 60): d.line([(x, 0), (x, H)], fill=(22, 62, 70), width=1)
    d.text((W // 2, 60), 'THEN  vs  NOW', font=font(DISP, 72), fill=YEL, anchor='mm')
    d.text((W - 40, H - 24), 'Data: U.S. Bureau of Labor Statistics', font=font(MONO, 22), fill=(150, 185, 190), anchor='rm')
    return img


def frame(base, v, bi, t):
    img = base.copy(); d = ImageDraw.Draw(img); n = len(v['rows'])
    if bi < 2:                                                        # giriş: büyük yıl + bağlam
        a = ease(t / 0.8)
        d.text((W // 2, 380), str(v['y0']), font=font(DISP, int(320 * a) + 1), fill=PAPER, anchor='mm')
        d.text((W // 2, 590), 'vs  TODAY', font=font(DISP, 120), fill=RED, anchor='mm')
        if bi == 1:
            d.text((W // 2, 740), f"$100 IN {v['y0']} = {money(v['k100'])} TODAY", font=font(MONO, 52), fill=YEL, anchor='mm')
            d.text((W // 2, 820), f"MIN WAGE {money(MINWAGE[v['y0']])}/HR  TO  {money(MINWAGE[max(MINWAGE)])}/HR", font=font(MONO, 44), fill=PAPER, anchor='mm')
    elif bi < 2 + n:                                                  # tek ürün: iki fiş yan yana
        r = v['rows'][bi - 2]
        d.text((W // 2, 140), f"{bi - 1} / {n}", font=font(MONO, 34), fill=(150, 185, 190), anchor='mm')
        lines0 = [(SHORT[r['k']], r['p0'], '$')]; lines1 = [(SHORT[r['k']], r['p1'], '$')]
        if v['mode'] == 'work':
            lines0.append(('MIN WAGE/HOUR', MINWAGE[v['y0']], '$')); lines1.append(('MIN WAGE/HOUR', MINWAGE[r['y1']], '$'))
        h = 230 + 110 * len(lines0) + 110
        tot0, tot1, tu = (r['p0'], r['p1'], '$') if v['mode'] == 'prices' else (r['m'][0], r['m'][1], 'min')
        stamp = (f"{r['pct']:+.0f}%", 0.0 if t < 3.0 else min(1.0, (t - 3.0) / 0.35))
        tvn.receipt(img, 120, 190, 800, h, min(1.0, t / 1.6), v['y0'], lines0, tot0, lh=110, fs=48, total_unit=tu)
        tvn.receipt(img, 1000, 190, 800, h, max(0.0, min(1.0, (t - 1.4) / 1.6)), r['y1'], lines1, tot1, stamp=stamp, now=True, lh=110, fs=48, total_unit=tu)
        if t > 4.0:
            beat = r['p1'] > r['inf']
            d.rounded_rectangle([420, 860, 1500, 990], radius=24, fill=(255, 255, 255))
            d.text((960, 895), 'IF IT ONLY FOLLOWED INFLATION', font=font(MONO, 32), fill=FADED, anchor='mm')
            d.text((760, 950), money(r['inf']), font=font(DISP, 76), fill=GREEN, anchor='mm')
            d.text((1210, 950), 'BEAT INFLATION' if beat else 'REAL PRICE DROP', font=font(DISP, 56), fill=RED if beat else GREEN, anchor='mm')
    else:                                                             # sıralama
        o = v['order']; rh = min(56, 820 // len(o)); y0 = 150
        d.text((W // 2, 120), 'REAL CHANGE VS INFLATION', font=font(DISP, 64), fill=PAPER, anchor='mm')
        mx = max(abs(r['real']) for r in o) or 1
        for i, r in enumerate(o):
            k = ease((t - i * 0.12) / 0.5) if bi == 2 + n else 1.0
            y = y0 + 40 + i * rh; w = 640 * abs(r['real']) / mx * k
            d.text((900, y + rh // 2), SHORT[r['k']], font=font(MONO, 30), fill=PAPER, anchor='rm')
            col = RED if r['real'] > 0 else GREEN
            d.rectangle([930, y + 8, 930 + max(w, 3), y + rh - 8], fill=col)
            d.text((1600, y + rh // 2), f"{r['real']:+.0f}%", font=font(MONO, 30), fill=col, anchor='lm')
        if bi == 3 + n:
            d.rounded_rectangle([560, H - 130, 1360, H - 50], radius=40, fill=YEL)
            d.text((W // 2, H - 90), 'WHICH YEAR NEXT?', font=font(DISP, 60), fill=INK, anchor='mm')
    return img


def render(v, mp4):
    tmp = mp4.with_suffix(''); tmp.mkdir(parents=True, exist_ok=True)
    auds, durs = [], []
    for i, b in enumerate(v['beats']):
        a = tmp / f'a{i}.mp3'
        try:
            tvn.tts(b, a)
        except Exception:
            import renderer
            a = tmp / f'a{i}.wav'; renderer.piper_tts(b, a)
        w = tmp / f'w{i}.wav'
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(a), '-af', 'silenceremove=start_periods=1:start_threshold=-45dB,areverse,'
                        'silenceremove=start_periods=1:start_threshold=-45dB,areverse,apad=pad_dur=0.7', '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', str(w)], check=True)
        d = tvn.dur(w)
        if 2 <= i < 2 + len(v['rows']) and d < 5.5:                     # animasyon bitsin
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', str(w), '-af', f'apad=whole_dur=5.5', str(w) + '.p.wav'], check=True)
            Path(str(w) + '.p.wav').replace(w); d = tvn.dur(w)
        auds.append(w); durs.append(d)
    lst = tmp / 'a.txt'; lst.write_text(''.join(f"file '{a}'\n" for a in auds))
    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(lst), '-ar', '44100', '-ac', '2', str(tmp / 'voice.wav')], check=True)
    base = background()
    p = subprocess.Popen(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                          '-i', str(tmp / 'voice.wav'), '-c:v', 'libx264', '-preset', 'medium', '-crf', '21', '-pix_fmt', 'yuv420p',
                          '-c:a', 'aac', '-b:a', '160k', '-shortest', '-movflags', '+faststart', str(mp4)], stdin=subprocess.PIPE)
    n = len(v['rows'])
    for i, dd in enumerate(durs):
        settle = 4.6 if 2 <= i < 2 + n else (0.12 * n + 0.7 if i == 2 + n else 0.9)
        last = None
        for k in range(int(dd * FPS)):
            t = k / FPS
            if t > settle and last is not None:
                p.stdin.write(last); continue
            fr = frame(base, v, i, t).tobytes()
            if t > settle - 0.05: last = fr
            p.stdin.write(fr)
    p.stdin.close(); p.wait()
    if p.returncode: raise RuntimeError('ffmpeg hata')
    return mp4


def main(n=None, slots=None):
    a = sys.argv[1:]
    n = n or (int(a[a.index('--long') + 1]) if '--long' in a else 1)
    year = int(a[a.index('--year') + 1]) if '--year' in a else None
    mode = a[a.index('--mode') + 1] if '--mode' in a else None
    state = json.loads(tvn.STATE.read_text()) if tvn.STATE.exists() else {'done': []}
    rnd = random.Random(); tvn.OUT.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        key = pick(state, rnd, year, mode); v = build(key, rnd)
        tvn.log(f'[tvn-long] {key} → {v["title"]}')
        import datetime
        mp4 = render(v, tvn.OUT / f'long_{datetime.date.today()}_{i}.mp4')
        if DRY:
            tvn.log(f'  [dry-run] {mp4}'); continue
        from daily_viral import publish_time
        vid = tvn.upload(mp4, dict(title=v['title'], desc=v['desc']), publish_time((slots or ['10:00', '20:00'])[i % 2]))
        state['done'].append(dict(fmt='long', key=key, video_id=vid, date=str(datetime.date.today()), title=v['title']))
        tvn.STATE.write_text(json.dumps(state, indent=1))
        tvn.log(f'  yüklendi https://youtu.be/{vid}')


if __name__ == '__main__':
    main()
