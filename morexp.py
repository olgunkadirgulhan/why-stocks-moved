"""Which Cost More? Shorts (2026-11-08; Then vs Now kanalının yeni konsepti — kanal dağıtımı çöktü: medyan 10).
Trend taraması: "which is more expensive" son 30 gün Shorts medyanı 347K, 44 kanal 100K+.
Gerçek veri: data/tvn/prices.json (BLS ortalama perakende fiyatları, ABD şehir ortalaması, yıllık). Uydurma yok.
Her video 5 tur: iki ürün (yıl + emoji + "a dozen eggs"), 3 sn düşün, sonra iki fiyat ve kazanan. Seri numarası #N.
    python morexp.py --dry-run | --auto
"""
import json, os, random, sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import ImageDraw
import shortkit as K

HERE = Path(__file__).resolve().parent
PRICES = json.loads((HERE / 'data' / 'tvn' / 'prices.json').read_text())
LOG = HERE / 'data' / 'tvn' / 'morexp_published.csv'
OUT = HERE / 'out' / 'morexp'
DRY = '--dry-run' in sys.argv
N_R, THINK, SHOW = 5, 3.0, 2.2
INTRO, OUTRO = 1.4, 3.0
RED, BLUE, GOLD = (235, 80, 70), (60, 130, 235), (255, 215, 60)


def latest_year(k): return max(PRICES[k]['years'])


def side(k, y):
    p = PRICES[k]['years'][y]
    return dict(k=k, y=y, p=p, em=PRICES[k]['emoji'], phrase=PRICES[k]['phrase'])


def make_round(rnd):
    """Bugün vs bugün ya da geçmiş vs bugün; fiyatlar en az %8 farklı olmalı (tartışmalı eşitlik yok)."""
    for _ in range(200):
        a, b = rnd.sample(list(PRICES), 2)
        ya = latest_year(a) if rnd.random() < 0.6 else rnd.choice([y for y in PRICES[a]['years'] if int(y) <= 2010])
        yb = latest_year(b)
        A, B = side(a, ya), side(b, yb)
        if abs(A['p'] - B['p']) / max(A['p'], B['p']) >= 0.08:
            return [A, B] if rnd.random() < 0.5 else [B, A]
    raise SystemExit('tur bulunamadı')


def frame_fn(p):
    rs = p['rounds']; seg = THINK + SHOW; total = INTRO + N_R * seg + OUTRO

    def f(T):
        img = K.gradient((20, 45, 40), (8, 20, 18), False).copy(); d = ImageDraw.Draw(img)
        if T < INTRO:
            u = K.ease(T / 0.5)
            K.text(d, (K.W / 2, 760), 'WHICH COST', int(130 * u) + 1)
            K.text(d, (K.W / 2, 900), 'MORE?', int(170 * u) + 1, fill=GOLD)
            K.text(d, (K.W / 2, 1070), f"5 ROUNDS · #{p['n']}", int(64 * u) + 1)
            return img
        if T >= INTRO + N_R * seg:
            u = K.ease((T - INTRO - N_R * seg) / 0.5)
            K.text(d, (K.W / 2, 720), 'HOW MANY', int(110 * u) + 1)
            K.text(d, (K.W / 2, 850), 'DID YOU GET?', int(110 * u) + 1, fill=GOLD)
            K.text(d, (K.W / 2, 1010), 'COMMENT YOUR SCORE', int(70 * u) + 1)
            K.text(d, (K.W / 2, 1160), f"NEXT: ROUND SET #{p['n'] + 1}", int(60 * u) + 1)
            return img
        i = int((T - INTRO) // seg); lt = T - INTRO - i * seg; A, B = rs[i]; pop = K.ease(lt / 0.35)
        show = lt >= THINK; win = 0 if A['p'] > B['p'] else 1
        K.text(d, (K.W / 2, 150), f'ROUND {i + 1}/{N_R}', 60)
        for j, (S, col, cy) in enumerate(((A, RED, 640), (B, BLUE, 1300))):
            hi = show and j == win
            d.rounded_rectangle([60, cy - 300, K.W - 60, cy + 300], radius=48, fill=(col if not show or hi else (90, 95, 100)) + (255,),
                                outline=GOLD if hi else None, width=14 if hi else 0)
            e = K.emoji_img(S['em'], int(200 * pop) + 1); img.alpha_composite(e, (int(K.W / 2 - e.width / 2), int(cy - (200 if j == 0 else 140) - e.height / 2)))
            K.text_block(d, K.W / 2, cy - 10, S['phrase'].upper(), 70, K.W - 200, max_lines=2)
            K.text(d, (K.W / 2, cy + 110), f"IN {S['y']}" if S['y'] != latest_year(S['k']) else 'TODAY', 64, fill=GOLD)
            if show:
                K.text(d, (K.W / 2, cy + 215), f"${S['p']:,.2f}", 110, fill=(255, 255, 255))
        d.ellipse([K.W / 2 - 90, 880, K.W / 2 + 90, 1060], fill=GOLD)
        K.text(d, (K.W / 2, 970), 'OR', 72, fill=(20, 45, 40), stroke=(255, 255, 255))
        if not show:
            frac = max(0.0, 1 - lt / THINK)
            d.rounded_rectangle([90, 1690, K.W - 90, 1736], radius=23, fill=(255, 255, 255, 120))
            d.rounded_rectangle([90, 1690, 90 + max(46, (K.W - 180) * frac), 1736], radius=23, fill=GOLD)
        return img
    events = [(INTRO + i * seg, 'new') for i in range(N_R)] + [(INTRO + i * seg + s, 'tick') for i in range(N_R) for s in (1, 2)]
    events += [(INTRO + i * seg + THINK, 'ding') for i in range(N_R)] + [(INTRO + N_R * seg, 'end')]
    return f, total, events


TITLES = ['Which Cost More? {a} or {b} 💸 #{n}', 'Guess Which Is More Expensive: {a} vs {b} #{n}', '{a} or {b}: Which Cost More? 🤔 (Round Set #{n})',
          'Price Battle: {a} vs {b} 💰 #{n}', 'Can You Guess the Pricier One? {a} {b} #{n}']


def main():
    a = sys.argv[1:]
    if '--auto' in a and K.today_count(LOG) >= int(os.environ.get('PER_DAY') or 3):
        print('bugünkü sayı doldu'); return
    rnd = random.Random(); seen_keys = {r['topic_id'] for r in K.rows(LOG)}
    for _ in range(50):
        rounds = [make_round(rnd) for _ in range(N_R)]
        tid = 'mx:' + '|'.join(f"{A['k']}{A['y']}-{B['k']}{B['y']}" for A, B in rounds)
        if tid not in seen_keys: break
    n = len(K.rows(LOG)) + 1
    p = dict(rounds=rounds, n=n, seed=rnd.randrange(10 ** 6))
    A0, B0 = rounds[0]
    seen = {K.tkey(r['title']) for r in K.rows(LOG)}
    opts = [t.format(a=A0['em'], b=B0['em'], n=n) for t in TITLES]; rnd.shuffle(opts)
    title = next(o for o in opts if K.tkey(o) not in seen)
    desc = ('Which cost more? Guess before the prices appear!\n\n'
            + '\n'.join(f"{i + 1}. {A['phrase']} ({'today' if A['y'] == latest_year(A['k']) else A['y']}): ${A['p']:,.2f}  vs  "
                        f"{B['phrase']} ({'today' if B['y'] == latest_year(B['k']) else B['y']}): ${B['p']:,.2f}" for i, (A, B) in enumerate(rounds))
            + '\n\nPrices: U.S. city average retail prices, Bureau of Labor Statistics (annual averages; "today" = latest full year).\n'
            'Comment your score! New rounds every day 👇\n\nEmoji: Noto Color Emoji by Google (SIL OFL).\n\n#shorts #prices #guessthepirce #quiz #money')
    desc = desc.replace('#guessthepirce', '#guesstheprice')
    tags = ['which is more expensive', 'guess the price', 'price quiz', 'prices then and now', 'quiz', 'money', 'shorts']
    f, total, events = frame_fn(p)
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%d_%H%M%S')
    print(f'[morexp] #{n} {title}', flush=True)
    mp4 = K.render(f, total, events, p['seed'], OUT / f'mx_{stamp}.mp4')
    if DRY: print('  [dry-run]', mp4); return
    pa = K.publish_at(['16:00', '19:00', '21:30'], K.today_count(LOG))
    vid = K.upload(mp4, title + ' #shorts', desc, tags, pa, category='27')
    K.record(LOG, tid, vid, title, pa)
    print(f'  ✓ https://youtu.be/{vid} ({pa})')


if __name__ == '__main__':
    main()
