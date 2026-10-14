#!/usr/bin/env python3
"""tvn_brand.py — kanalın "Then vs Now" kimliği (2026-10-14): banner, profil, filigran, açıklama, eski videoları gizleme.

    python brand/tvn_brand.py --make                 # sadece görselleri üret (brand/tvn_*.png)
    python brand/tvn_brand.py --apply [--hide-old]   # YouTube'a uygula (CI: brand.yml)

--hide-old: Then vs Now'dan önceki (borsa) videoları SİLMEZ, gizli yapar; id'ler data/tvn/hidden_old.json'a yazılır,
tools/set_privacy.py ile geri açılabilir. Kanal adı/handle API ile değişmez → Studio'dan elle.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import tvn  # noqa: E402  renkler, fontlar, gerçek fiyat verisi
from PIL import Image, ImageDraw  # noqa: E402

HERE = ROOT / 'brand'
F = tvn.font
DESCRIPTION = """What did things cost back then, and what do they cost now?

Each Short puts two receipts side by side: the same groceries, gas or electricity in an earlier year and today, using official U.S. city-average prices from the Bureau of Labor Statistics. Then we show what the price would be if it had only followed inflation (CPI-U), how long it took to earn it at the federal minimum wage, and which everyday item got pricier the fastest.

Real numbers only. The data source is in every description.

New Shorts every day.

Not financial advice. For education and information only."""
KEYWORDS = ['then vs now', 'prices then and now', 'then and now prices', 'inflation', 'cost of living', 'grocery prices',
            'egg prices', 'gas prices', 'price history', 'how much did it cost', 'minimum wage', 'cpi', '90s prices',
            '2000s prices', 'inflation explained', 'purchasing power', 'old prices', 'grocery receipt']


def mini_receipt(year, label, price, now, w=420, h=300):
    p = Image.new('RGBA', (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(p)
    zig = [(i * 30, 0 if i % 2 == 0 else 14) for i in range(w // 30 + 2)]
    d.polygon([(0, 14)] + zig + [(w, h - 14)] + [(w - i * 30, h - (0 if i % 2 == 0 else 14)) for i in range(w // 30 + 2)]
              + [(0, h - 14)], fill=tvn.PAPER)
    d.text((w // 2, 70), str(year), font=F(tvn.DISP, 96), fill=tvn.RED if now else tvn.INK, anchor='mm')
    d.line([(26, 124), (w - 26, 124)], fill=tvn.FADED, width=3)
    d.text((28, 160), label, font=F(tvn.MONO, 34), fill=tvn.INK)
    d.text((w - 28, 214), tvn.money(price), font=F(tvn.MONO, 58), fill=tvn.RED if now else tvn.INK, anchor='ra')
    return p


def banner():
    W, H = 2560, 1440
    img = Image.new('RGB', (W, H), tvn.BG); d = ImageDraw.Draw(img)
    for y in range(0, H, 4):
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * y / H) for a, b in zip(tvn.BG, tvn.BG2)))
    for x in range(0, W, 64): d.line([(x, 0), (x, H)], fill=(22, 62, 70), width=1)
    eg = tvn.PRICES['eggs']['years']; y0, y1 = 1995, max(eg)              # gerçek BLS yumurta fiyatları
    r0 = mini_receipt(y0, 'EGGS / DOZEN', eg[y0], False, w=340).rotate(4, expand=True, resample=Image.BICUBIC)
    r1 = mini_receipt(y1, 'EGGS / DOZEN', eg[y1], True, w=340).rotate(-4, expand=True, resample=Image.BICUBIC)
    cy = H // 2                                                           # güvenli alan: ortadaki 1546×423
    img.paste(r0, (W // 2 - 770, cy - r0.height // 2), r0)
    img.paste(r1, (W // 2 + 770 - r1.width, cy - r1.height // 2), r1)
    d.text((W // 2, cy - 50), 'THEN vs NOW', font=F(tvn.DISP, 170), fill=tvn.YEL, anchor='mm')
    d.text((W // 2, cy + 85), 'REAL PRICES · OFFICIAL DATA', font=F(tvn.MONO, 40), fill=(226, 236, 236), anchor='mm')
    d.text((W // 2, cy + 140), 'NEW SHORTS DAILY', font=F(tvn.MONO, 34), fill=tvn.YEL, anchor='mm')
    img.save(HERE / 'tvn_banner_2560x1440.png')


def icon(size=800, transparent=False):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0) if transparent else tvn.BG + (255,)); d = ImageDraw.Draw(img)
    s = size / 800
    w, h = int(520 * s), int(560 * s); x, y = (size - w) // 2, (size - h) // 2
    rec = mini_receipt('THEN', '', 0, False, w=520, h=560).resize((w, h))
    d2 = ImageDraw.Draw(rec)
    d2.rectangle([0, int(110 * s), w, h - int(20 * s)], fill=tvn.PAPER)
    d2.text((w // 2, int(70 * s)), 'THEN', font=F(tvn.DISP, int(96 * s)), fill=tvn.INK, anchor='mm')
    d2.line([(int(26 * s), int(124 * s)), (w - int(26 * s), int(124 * s))], fill=tvn.FADED, width=max(2, int(3 * s)))
    d2.text((w // 2, int(250 * s)), 'vs', font=F(tvn.MONO, int(80 * s)), fill=tvn.FADED, anchor='mm')
    d2.text((w // 2, int(400 * s)), 'NOW', font=F(tvn.DISP, int(200 * s)), fill=tvn.RED, anchor='mm')
    img.paste(rec, (x, y), rec)
    return img


def make():
    banner()
    icon().convert('RGB').save(HERE / 'tvn_profile_800x800.png')
    icon(150, transparent=True).save(HERE / 'tvn_watermark_150x150.png')
    print('✓ brand/tvn_banner_2560x1440.png, tvn_profile_800x800.png, tvn_watermark_150x150.png')


def apply(hide_old):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    from common import yt_creds
    import apply_branding
    yt = build('youtube', 'v3', credentials=yt_creds(), cache_discovery=False)
    ch = yt.channels().list(part='snippet,brandingSettings,contentDetails', mine=True).execute()['items'][0]
    if ch['snippet']['title'] not in ('Why Stocks Moved', 'Then vs Now'):
        sys.exit(f"Beklenmeyen kanal: {ch['snippet']['title']}")
    url = yt.channelBanners().insert(media_body=MediaFileUpload(str(HERE / 'tvn_banner_2560x1440.png'),
                                                                mimetype='image/png')).execute()['url']
    b = ch.get('brandingSettings', {}); b.setdefault('channel', {})
    b['channel']['description'] = DESCRIPTION
    b['channel']['keywords'] = ' '.join(f'"{k}"' if ' ' in k else k for k in KEYWORDS)
    b.setdefault('image', {})['bannerExternalUrl'] = url
    b.pop('hints', None)
    yt.channels().update(part='brandingSettings', body={'id': ch['id'], 'brandingSettings': b}).execute()
    print('✓ banner + açıklama + anahtar kelimeler')
    apply_branding.HERE = HERE
    (HERE / 'watermark_150x150.png').write_bytes((HERE / 'tvn_watermark_150x150.png').read_bytes())
    try:
        apply_branding.set_watermark(ch['id']); print('✓ filigran')
    except Exception as e:
        print(f'• filigran atlandı ({str(e)[:120]})')
    if not hide_old:
        return
    keep = {d.get('video_id') for d in json.loads(tvn.STATE.read_text()).get('done', [])} if tvn.STATE.exists() else set()
    up = ch['contentDetails']['relatedPlaylists']['uploads']; ids, tok = [], None
    while True:
        r = yt.playlistItems().list(part='contentDetails', playlistId=up, maxResults=50, pageToken=tok).execute()
        ids += [i['contentDetails']['videoId'] for i in r['items']]; tok = r.get('nextPageToken')
        if not tok: break
    hidden_f = tvn.DATA / 'hidden_old.json'
    hidden = json.loads(hidden_f.read_text()) if hidden_f.exists() else []
    for i in range(0, len(ids), 50):
        for v in yt.videos().list(part='status,snippet', id=','.join(ids[i:i + 50])).execute()['items']:
            if v['id'] in keep or v['status']['privacyStatus'] == 'private':
                continue
            st = v['status']; st['privacyStatus'] = 'private'; st.pop('publishAt', None)
            yt.videos().update(part='status', body={'id': v['id'], 'status': st}).execute()
            hidden.append({'id': v['id'], 'was': v['status'].get('privacyStatus'), 'title': v['snippet']['title']})
            print(f"  gizlendi: {v['id']} | {v['snippet']['title'][:60]}")
    hidden_f.write_text(json.dumps(hidden, indent=1, ensure_ascii=False))
    print(f'✓ {len(hidden)} eski video gizli (geri almak için: data/tvn/hidden_old.json)')


if __name__ == '__main__':
    if '--make' in sys.argv or not (HERE / 'tvn_banner_2560x1440.png').exists():
        make()
    if '--apply' in sys.argv:
        sys.path.insert(0, str(HERE)); apply('--hide-old' in sys.argv)
