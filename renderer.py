"""renderer.py — dikey Shorts render'ı: edge-tts seslendirme + Pillow kareleri → ffmpeg (H.264/AAC, 1080x1920).

md'deki Remotion `FinanceShort` / `DailyRecap` composition'larının yerini tutar ve aynı props'u okur:
script.beats[].say / osd / emphasis / visual (+ opsiyonel ticker). Node/Chrome gerektirmez.
Frame 0 her zaman hareketli grafik; "Yatırım Tavsiyesi Değildir" her karede sabit.
"""
import datetime
import asyncio, os, re, shutil, subprocess

from PIL import Image, ImageDraw, ImageFont

from common import CONTENT_LANG, OUT, log

W, H, FPS = 1080, 1920, 30
TR = CONTENT_LANG == "tr"
VOICE = os.environ.get("TTS_VOICE", "tr-TR-AhmetNeural" if TR else "en-US-AndrewMultilingualNeural")
RATE = os.environ.get("TTS_RATE", "+8%" if TR else "+5%")
def _first(*paths):
    return next((p for p in paths if p and os.path.exists(p)), paths[-1])


# Windows: Arial · GitHub Actions (Ubuntu): Liberation Sans (Arial metrikli) / DejaVu
FONT_BOLD = _first(os.environ.get("FONT_BOLD"), r"C:\Windows\Fonts\arialbd.ttf",
                   "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                   "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
FONT_REG = _first(os.environ.get("FONT_REG"), r"C:\Windows\Fonts\arial.ttf",
                  "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                  "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
CHANNEL = os.environ.get("CHANNEL_NAME", "")
DISCLAIMER = "Yatırım Tavsiyesi Değildir · veriler gecikmeli" if TR else "Not financial advice · data may be delayed"
FG, ACC, UP, DOWN, MUTED = (255, 255, 255), (255, 196, 0), (34, 197, 94), (239, 68, 68), (148, 163, 184)
PAD_S = 0.3                      # beat sonu nefes payı

# Shorts arayüzü alt ~%20'yi ve sağ kenarı kapatır; her şey bu kutunun içinde kalır
VIS = (80, 250, 1000, 980)       # grafik / sayaç / kart alanı
HEAD_Y, CAP_Y, DISC_Y = 1030, 1330, 1530          # 3 satır altyazı uyarıya değmez; 1536 altı Shorts UI

_fonts = {}


def font(size, bold=True):
    k = (size, bold)
    if k not in _fonts:
        _fonts[k] = ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    return _fonts[k]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


# ---------------- ses ----------------
def tts(text, mp3):
    import edge_tts

    async def go():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(mp3))
    asyncio.run(go())


PIPER_VOICE = os.environ.get("PIPER_VOICE", "tr_TR-fahrettin-medium" if TR else "en_US-ryan-medium")
PIPER_DIR = os.environ.get("PIPER_VOICE_DIR", os.path.join(os.path.expanduser("~"), ".cache", "piper-voices"))


def piper_tts(text, wav):
    """Yedek ses: Piper — çevrimdışı, ücretsiz, anahtar yok. Ses modeli ilk kullanımda indirilir (~60 MB)."""
    import sys
    model = os.path.join(PIPER_DIR, PIPER_VOICE + ".onnx")
    if not os.path.exists(model):
        os.makedirs(PIPER_DIR, exist_ok=True)
        subprocess.run([sys.executable, "-m", "piper.download_voices", PIPER_VOICE, "--data-dir", PIPER_DIR],
                       check=True, capture_output=True)
    subprocess.run([sys.executable, "-m", "piper", "-m", model, "-f", str(wav)], input=text, text=True,
                   encoding="utf-8", check=True, capture_output=True)


def voice_beats(beats, tmp):
    """Tüm beat'ler edge-tts (doğal ses); biri bile başarısızsa video baştan sona Piper ile (ses karışmasın)."""
    try:
        out = []
        for i, b in enumerate(beats):
            a = tmp / f"a{i}.mp3"
            for k in range(3):
                try:
                    tts(b["say"], a)
                    if a.exists() and a.stat().st_size > 1000:
                        break
                except Exception:
                    if k == 2:
                        raise
            else:
                raise RuntimeError("edge-tts boş ses döndürdü")
            out.append(a)
        return out
    except Exception as e:
        log(f"  edge-tts çalışmadı ({str(e)[:100]}) → Piper yedek sesi")
        out = []
        for i, b in enumerate(beats):
            w = tmp / f"p{i}.wav"
            piper_tts(b["say"], w)
            out.append(w)
        return out


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


# ---------------- çizim parçaları ----------------
def _background():
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img)
    for y in range(H):
        k = y / H
        d.line([(0, y), (W, y)], fill=(int(8 + 14 * k), int(12 + 20 * k), int(26 + 36 * k)))
    return img


def wrap(d, text, fnt, max_w):
    out, cur = [], ""
    for w in text.split():
        t = (cur + " " + w).strip()
        if d.textlength(t, font=fnt) <= max_w or not cur:
            cur = t
        else:
            out.append(cur)
            cur = w
    return out + ([cur] if cur else [])


def fmt_num(v, dec):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") if TR else s   # TR 12.345,67 · EN 12,345.67


def pct_str(v, dec, plus=True):
    sign = "+" if v > 0 and plus else "-" if v < 0 else ""
    return sign + "%" + fmt_num(abs(v), dec) if TR else sign + fmt_num(abs(v), dec) + "%"


def draw_chart(d, series, progress, box, alpha=255, label=None, up=None):
    x0, y0, x1, y1 = box
    if not series or len(series) < 2:
        return
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1
    n = len(series)
    pts = [(x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * (v - lo) / span) for i, v in enumerate(series)]
    k = max(2, int(round(n * ease(progress))))
    vis = pts[:k]
    col = UP if (up if up is not None else series[-1] >= series[0]) else DOWN   # renk = anlatılan günlük yön
    d.polygon(vis + [(vis[-1][0], y1), (vis[0][0], y1)], fill=col + (int(alpha * 0.18),))
    d.line(vis, fill=col + (alpha,), width=9, joint="curve")
    if alpha > 200:
        cx, cy = vis[-1]
        for r, a in ((34, 50), (22, 90), (12, 255)):
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (a,))
        if label and progress > 0.6:
            f = font(46)
            tw = d.textlength(label, font=f)
            lx = min(max(x0, cx - tw / 2), x1 - tw)
            ly = cy - 90 if cy - 90 > y0 else cy + 40
            d.rounded_rectangle([lx - 18, ly - 10, lx + tw + 18, ly + 58], 16, fill=(15, 23, 42, 230))
            d.text((lx, ly), label, font=f, fill=FG)


def draw_headline(d, osd, emphasis, t_in):
    """Başlık her zaman büyük harf ve en fazla 2 satır: sığmazsa küçülür. Dönen: alt kenarın y'si."""
    if not osd:
        return HEAD_Y
    key = lambda w: (w.strip(".,!?:;%()").replace("I", "ı").replace("İ", "i") if TR else w.strip(".,!?:;%()")).lower()
    em = {key(w) for w in (emphasis or "").split()}
    osd = (osd.replace("i", "İ").replace("ı", "I") if TR else osd).upper()   # TR büyük harf kuralı
    base = 92
    while base > 52 and len(wrap(d, osd, font(base), W - 160)) > 2:
        base -= 6
    size = int(base * (0.82 + 0.18 * ease(t_in / 0.25)))
    f = font(size)
    y = HEAD_Y
    for line in wrap(d, osd, f, W - 160):
        ws = line.split()
        widths = [d.textlength(w + " ", font=f) for w in ws]
        x = (W - sum(widths)) / 2
        for w, wd in zip(ws, widths):
            hit = key(w) in em
            d.text((x + 4, y + 5), w, font=f, fill=(0, 0, 0, 160))
            d.text((x, y), w, font=f, fill=ACC if hit else FG)
            x += wd
        y += int(size * 1.12)
    return y


def draw_caption(d, say, top=CAP_Y):
    f = font(44, bold=False)
    y = max(CAP_Y, top + 24)                         # başlık uzunsa altyazı aşağı kayar, üst üste binmez
    for line in wrap(d, say, f, W - 200)[:3]:
        d.text(((W - d.textlength(line, font=f)) / 2, y), line, font=f, fill=(226, 232, 240))
        y += 56


def parse_num(raw):
    """'12.345,67' / '12,345.67' / '3,5' / '1.250' → (değer, ondalık hane)."""
    raw = raw.lstrip("+")
    if "," in raw and "." in raw:
        dsep = "," if raw.rfind(",") > raw.rfind(".") else "."
    elif "," in raw or "." in raw:
        sep = "," if "," in raw else "."
        dsep = sep if raw.count(sep) == 1 and len(raw.rsplit(sep, 1)[1]) <= 2 else None
    else:
        dsep = None
    tsep = {",": ".", ".": ","}.get(dsep, ",.")
    clean = "".join(c for c in raw if c not in tsep)
    if dsep:
        clean = clean.replace(dsep, ".")
    dec = len(clean.split(".")[1]) if "." in clean else 0
    return float(clean), dec


def draw_counter(d, target_text, progress):
    m = re.search(r"([-+]?%)?\s?([-+]?\d[\d.,]*\d|\d)\s*(%|x|k|bin|milyon|milyar|tl|\$)?", target_text or "", re.I)
    if not m:
        return False
    val, dec = parse_num(m.group(2))
    if (m.group(1) or "").startswith("-"):
        val = -val
    unit = "%" if m.group(1) else (m.group(3) or "")
    cur = val * ease(progress / 0.8)
    txt = pct_str(cur, dec, plus=False) if unit == "%" else fmt_num(cur, dec) + (" " + unit if unit else "")
    f = font(210)
    col = DOWN if val < 0 else ACC
    cx, cy = (VIS[0] + VIS[2]) / 2, (VIS[1] + VIS[3]) / 2
    d.text((cx - d.textlength(txt, font=f) / 2, cy - 120), txt, font=f, fill=col)
    return True


def draw_tiles(d, market, keys, progress):
    keys = keys[:4]
    th = (VIS[3] - VIS[1] - 30 * (len(keys) - 1)) / max(1, len(keys))
    for i, k in enumerate(keys):
        m = market[k]
        p = ease((progress - i * 0.12) / 0.35)
        if p <= 0:
            continue
        y = VIS[1] + i * (th + 30)
        x = VIS[0] + (1 - p) * 300
        d.rounded_rectangle([x, y, x + VIS[2] - VIS[0], y + th], 28, fill=(30, 41, 59, int(235 * p)))
        ch = m["change_pct"]
        col = UP if ch >= 0 else DOWN
        d.text((x + 40, y + th / 2 - 34), m["name"], font=font(58), fill=FG + (int(255 * p),))
        s = pct_str(ch, 2)
        d.text((x + VIS[2] - VIS[0] - 40 - d.textlength(s, font=font(62)), y + th / 2 - 36), s, font=font(62), fill=col + (int(255 * p),))


def draw_compare(d, market, keys, progress):
    keys = keys[:2]
    if len(keys) < 2:
        return draw_tiles(d, market, keys, progress)
    vals = [market[k]["change_5d_pct"] for k in keys]
    top = max(abs(v) for v in vals) or 1
    bw = 300
    base = VIS[3] - 80
    for i, (k, v) in enumerate(zip(keys, vals)):
        cx = VIS[0] + (VIS[2] - VIS[0]) * (0.28 + 0.44 * i)
        h = (base - VIS[1] - 120) * abs(v) / top * ease(progress / 0.7)
        col = UP if v >= 0 else DOWN
        d.rounded_rectangle([cx - bw / 2, base - h, cx + bw / 2, base], 20, fill=col + (235,))
        lab = pct_str(v, 1)
        d.text((cx - d.textlength(lab, font=font(64)) / 2, base - h - 84), lab, font=font(64), fill=FG)
        nm = market[k]["name"]
        d.text((cx - d.textlength(nm, font=font(46)) / 2, base + 16), nm, font=font(46), fill=MUTED)


def _ticker_label(m):
    p = m["price"]
    return fmt_num(p, 2 if p < 1000 else 0)


def frame(bg, beat, market, ticker, t_beat, dur_beat, t_total, dur_total):
    img = bg.copy()
    d = ImageDraw.Draw(img, "RGBA")
    prog = t_beat / max(dur_beat, 0.01)
    keys = list(market)
    tk = beat.get("ticker") if beat.get("ticker") in market else ticker
    series = market[tk]["series"]
    visual = beat.get("visual", "text")

    d.rectangle([0, 0, W * t_total / dur_total, 12], fill=ACC)          # ilerleme çubuğu
    if CHANNEL:
        d.text((80, 140), CHANNEL, font=font(40), fill=MUTED)
    d.text((W - 80 - d.textlength(market[tk]["name"], font=font(40)), 140), market[tk]["name"], font=font(40), fill=MUTED)

    if visual == "counter" and not re.search(r"\d", beat.get("osd", "")):
        visual = "chart"                             # sayaç yalnızca ekran yazısında rakam varsa: alakasız sayı gösterme
    if visual == "chart":
        draw_chart(d, series, min(1, prog / 0.7), VIS, 255, _ticker_label(market[tk]), market[tk]["change_pct"] >= 0)
    else:
        draw_chart(d, series, 1, VIS, 55, up=market[tk]["change_pct"] >= 0)   # arkada soluk grafik
        if visual == "list":
            draw_tiles(d, market, [tk] + [k for k in keys if k != tk], prog)
        elif visual == "compare":
            other = beat.get("compare_with") if beat.get("compare_with") in market else next(k for k in keys if k != tk)
            draw_compare(d, market, [tk, other], prog)
        elif visual == "counter":
            draw_counter(d, beat.get("osd", ""), prog)

    bottom = draw_headline(d, beat.get("osd", ""), beat.get("emphasis", ""), t_beat)
    draw_caption(d, beat.get("say", ""), bottom)
    f = font(34, bold=False)
    d.text(((W - d.textlength(DISCLAIMER, font=f)) / 2, DISC_Y), DISCLAIMER, font=f, fill=MUTED)
    return img


# ---------------- ana giriş ----------------
def render(beats, market_snapshot, out_mp4, ticker=None):
    """beats: [{"say","osd","emphasis","visual","ticker"?}], market_snapshot: market_snapshot.py çıktısı."""
    market = market_snapshot["tickers"]
    ticker = ticker if ticker in market else next(iter(market))
    beats = [dict(b) for b in beats if (b.get("say") or "").strip()]
    if not beats:
        raise ValueError("render: boş script")
    beats[0]["visual"] = "chart"                                         # frame 0 = hareketli grafik
    tmp = OUT / (out_mp4.stem + "_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    try:
        auds = voice_beats(beats, tmp)
        durs = [duration(a) + PAD_S for a in auds]
        total = sum(durs)
        fc = ";".join(f"[{i + 1}:a]apad=whole_dur={dd:.3f}[a{i}]" for i, dd in enumerate(durs))
        fc += ";" + "".join(f"[a{i}]" for i in range(len(durs))) + f"concat=n={len(durs)}:v=0:a=1[aout]"
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-"]
        for a in auds:
            cmd += ["-i", str(a)]
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast",
                "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.3f}",
                "-movflags", "+faststart", str(out_mp4)]
        errf = open(tmp / "ffmpeg.log", "w")
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
        bg = _background()
        starts = [sum(durs[:i]) for i in range(len(durs))]
        nframes = int(total * FPS) + 1
        bi = 0
        for fi in range(nframes):
            t = fi / FPS
            while bi + 1 < len(beats) and t >= starts[bi + 1]:
                bi += 1
            img = frame(bg, beats[bi], market, ticker, t - starts[bi], durs[bi], t, total)
            p.stdin.write(img.tobytes())
        p.stdin.close()
        rc = p.wait()
        errf.close()
        if rc:
            raise RuntimeError("ffmpeg: " + (tmp / "ffmpeg.log").read_text(errors="ignore")[-600:])
        log(f"render ok {out_mp4.name} ({total:.1f} sn, {len(beats)} beat)")
        return out_mp4
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def recap_beats(market_snapshot):
    """Güvenli format (DailyRecap): LLM'siz, sadece gerçek veriden günün piyasa özeti."""
    m = market_snapshot["tickers"]
    keys = sorted(m, key=lambda k: -abs(m[k]["change_pct"]))
    star = keys[0]

    s, v0 = m[star], m[star]["change_pct"]
    first = s["name"].split()[0]
    if TR:
        yon = lambda v: "yükseldi" if v >= 0 else "düştü"
        pct = lambda v: "yüzde " + fmt_num(abs(v), 2)
        beats = [{"say": f"Günün piyasa özeti. En sert hareket {s['name']} tarafında: {pct(v0)} {yon(v0)}.",
                  "osd": f"{s['name']} günün yıldızı", "emphasis": first, "visual": "chart", "ticker": star}]
        line = lambda v: f"{v['name']} {pct(v['change_pct'])} {yon(v['change_pct'])}, haftalık bazda {pct(v['change_5d_pct'])} {yon(v['change_5d_pct'])}."
        outro = {"say": "Hepsi bir arada. Yarın yine buradayız, takipte kal.", "osd": "Günün tablosu", "emphasis": "tablosu"}
    else:
        yon = lambda v: "up" if v >= 0 else "down"
        pct = lambda v: fmt_num(abs(v), 2) + " percent"
        # veri bir önceki işlem gününün kapanışı (hafta sonu = Cuma): "today" denmez, gün adı söylenir
        day = datetime.date.fromisoformat(s["as_of"]).strftime("%A") if s.get("as_of") else "the last session"
        beats = [{"say": f"Your market recap. The biggest mover on {day} was {s['name']}, {yon(v0)} {pct(v0)}.",
                  "osd": f"{s['name']} led {day}", "emphasis": first, "visual": "chart", "ticker": star}]
        line = lambda v: f"{v['name']} was {yon(v['change_pct'])} {pct(v['change_pct'])} on {day}, and {yon(v['change_5d_pct'])} {pct(v['change_5d_pct'])} on the week."
        outro = {"say": "That's the whole board. Follow so you catch the next recap.", "osd": f"{day}'s board", "emphasis": "board"}
    for k in keys[1:5]:
        v = m[k]
        beats.append({"say": line(v), "osd": f"{v['name']} {pct_str(v['change_pct'], 2)}",
                      "emphasis": v["name"].split()[0], "visual": "chart", "ticker": k})
    beats.append({**outro, "visual": "list", "ticker": star})
    return beats, star
