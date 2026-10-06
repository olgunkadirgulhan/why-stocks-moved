"""hf_pilot.py — HyperFrames denemesi: aynı piyasa özeti (recap) iki renderer ile.

Eski: renderer.render (Pillow kareleri + ffmpeg). Yeni: HTML/GSAP kompozisyon → `npx hyperframes render`.
Aynı seslendirme, aynı gerçek veri; ikisi de Telegram'a gider, karşılaştırıp karar verilir. YouTube'a yüklenmez.
    python hf_pilot.py            # out/hf_pilot/{old,new}.mp4
"""
import glob, html, json, shutil, subprocess, sys

import renderer
from common import BASE, OUT, log, tg, tg_send

W, H = renderer.W, renderer.H
PROJ = OUT / "hf_pilot" / "project"
UP, DOWN, ACC = "#22c55e", "#ef4444", "#ffc400"


def snapshot():
    r = subprocess.run([sys.executable, str(BASE / "market_snapshot.py")], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def voiceover(beats, tmp):
    """Beat başına TTS (eski renderer ile aynı ses) → tek dosya + beat süreleri."""
    auds = renderer.voice_beats(beats, tmp)
    durs = [renderer.duration(a) + renderer.PAD_S for a in auds]
    fc = ";".join(f"[{i}:a]apad=whole_dur={d:.3f}[a{i}]" for i, d in enumerate(durs))
    fc += ";" + "".join(f"[a{i}]" for i in range(len(durs))) + f"concat=n={len(durs)}:v=0:a=1[aout]"
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for a in auds:
        cmd += ["-i", str(a)]
    cmd += ["-filter_complex", fc, "-map", "[aout]", "-c:a", "libmp3lame", "-b:a", "192k", str(PROJ / "vo.mp3")]
    subprocess.run(cmd, check=True)
    return durs


def font_face():
    """Inter (fonts-inter) varsa onu, yoksa Liberation Sans'ı projeye kopyalar (render ağdan font çekmez)."""
    cands = (sorted(glob.glob("/usr/share/fonts/**/InterVariable.ttf", recursive=True))
             + sorted(glob.glob("/usr/share/fonts/**/Inter*.ttf", recursive=True)))
    if cands:
        shutil.copy(cands[0], PROJ / "brand.ttf")
        return "@font-face{font-family:Brand;src:url(brand.ttf);font-weight:100 900;}"
    shutil.copy(renderer.FONT_BOLD, PROJ / "brand-b.ttf")
    shutil.copy(renderer.FONT_REG, PROJ / "brand-r.ttf")
    return ("@font-face{font-family:Brand;src:url(brand-r.ttf);font-weight:400;}"
            "@font-face{font-family:Brand;src:url(brand-b.ttf);font-weight:700 900;}")


def chart_paths(series, w=920, h=520):
    lo, hi = min(series), max(series)
    span = (hi - lo) or 1
    pts = [(round(i * w / (len(series) - 1), 1), round(h - 20 - (v - lo) / span * (h - 60), 1))
           for i, v in enumerate(series)]
    line = "M" + " L".join(f"{x},{y}" for x, y in pts)
    return line, f"{line} L{w},{h} L0,{h} Z", pts[-1]


def headline(osd, emphasis):
    t = html.escape(osd)
    if emphasis and emphasis in osd:
        e = html.escape(emphasis)
        t = t.replace(e, f'<span class="em">{e}</span>', 1)
    return t


def scene(i, b, start, dur, market, day):
    m = market[b["ticker"]]
    ch = m["change_pct"]
    col = UP if ch >= 0 else DOWN
    words = "".join(f'<span class="w">{html.escape(w)}</span> ' for w in b["say"].split())
    if b.get("visual") == "list":
        keys = sorted(market, key=lambda k: -abs(market[k]["change_pct"]))[:5]
        tiles = "".join(
            f'<div class="tile"><span class="tn">{html.escape(market[k]["name"])}</span>'
            f'<span class="tv" style="color:{UP if market[k]["change_pct"] >= 0 else DOWN}">'
            f'{renderer.pct_str(market[k]["change_pct"], 2)}</span></div>' for k in keys)
        visual = f'<div class="tiles">{tiles}</div>'
    else:
        line, area, (ex, ey) = chart_paths(m["series"])
        price = m["price"]
        dec = 2 if price < 1000 else 0
        visual = f"""<div class="card">
  <div class="card-head"><span class="name">{html.escape(m['name'])}</span>
    <span class="pill" style="background:{col}">{renderer.pct_str(ch, 2)}</span></div>
  <div class="price" data-to="{price}" data-dec="{dec}">{renderer.fmt_num(price, dec)}</div>
  <svg class="chart" viewBox="0 0 920 520" preserveAspectRatio="none">
    <defs><linearGradient id="g{i}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{col}" stop-opacity=".45"/><stop offset="1" stop-color="{col}" stop-opacity="0"/>
    </linearGradient></defs>
    <path class="area" d="{area}" fill="url(#g{i})"/>
    <path class="line" d="{line}" fill="none" stroke="{col}" stroke-width="7" stroke-linejoin="round" stroke-linecap="round" pathLength="1"/>
    <circle class="dot" cx="{ex}" cy="{ey}" r="14" fill="{col}"/>
  </svg>
  <div class="range">30-day close · {html.escape(day)}</div>
</div>"""
    return f"""<section id="s{i}" class="clip scene" data-start="{start:.3f}" data-duration="{dur:.3f}" data-track-index="1">
  <div class="inner">
    {visual}
    <h2 class="head">{headline(b.get('osd', ''), b.get('emphasis', ''))}</h2>
    <p class="cap">{words}</p>
  </div>
</section>"""


CSS = """
body{margin:0;background:#070b16;color:#fff;font-family:Brand,sans-serif}
#root{position:relative;width:100%;height:100%;overflow:hidden}
.bg{position:absolute;inset:0;background:radial-gradient(1200px 900px at 20% 10%,#1d2b55 0,#0b1226 55%,#060912 100%)}
.glow{position:absolute;left:-200px;top:900px;width:1500px;height:700px;border-radius:50%;
  background:radial-gradient(closest-side,rgba(255,196,0,.14),rgba(255,196,0,0))}
.top{position:absolute;left:80px;right:80px;top:120px;display:flex;justify-content:space-between;align-items:center;
  font-size:38px;font-weight:700;letter-spacing:.04em;color:#94a3b8}
.brand b{color:#ffc400}
.bar{position:absolute;left:0;top:0;width:100%;height:12px;background:#ffc400;transform-origin:0 50%}
.scene{position:absolute;inset:0}
.inner{position:absolute;left:80px;right:80px;top:230px;bottom:400px;display:flex;flex-direction:column;gap:36px}
.card{background:rgba(15,23,42,.78);border:2px solid rgba(148,163,184,.18);border-radius:40px;padding:44px 50px 30px;
  box-shadow:0 30px 80px rgba(0,0,0,.45)}
.card-head{display:flex;justify-content:space-between;align-items:center}
.name{font-size:60px;font-weight:800}
.pill{display:block;font-size:46px;font-weight:800;padding:10px 26px;border-radius:999px;color:#06101f}
.price{font-size:96px;font-weight:900;margin-top:6px;letter-spacing:-.02em}
.chart{display:block;width:100%;height:440px;margin-top:10px;overflow:visible}
.range{font-size:30px;color:#94a3b8;margin-top:6px}
.head{margin:0;font-size:76px;line-height:1.08;font-weight:900;letter-spacing:-.01em}
.em{color:#ffc400}
.cap{margin:0;font-size:44px;line-height:1.3;color:#e2e8f0;font-weight:500}
.w{display:inline-block}
.tiles{display:flex;flex-direction:column;gap:24px}
.tile{display:flex;justify-content:space-between;align-items:center;background:rgba(30,41,59,.92);
  border-radius:30px;padding:34px 44px;font-size:56px;font-weight:800}
.disc{position:absolute;left:80px;right:80px;top:1500px;text-align:center;font-size:32px;color:#94a3b8}
"""

JS = """
const tl = gsap.timeline({ paused: true });
const TOTAL = %(total).3f;
tl.fromTo(".bar", { scaleX: 0 }, { scaleX: 1, duration: TOTAL, ease: "none" }, 0);
tl.fromTo(".glow", { x: 0 }, { x: 260, duration: TOTAL, ease: "sine.inOut" }, 0);
document.querySelectorAll(".scene").forEach((s) => {
  const t0 = parseFloat(s.dataset.start), d = parseFloat(s.dataset.duration);
  const q = (sel) => s.querySelectorAll(sel);
  tl.fromTo(s.querySelector(".inner"), { opacity: 0, y: 60 }, { opacity: 1, y: 0, duration: 0.45, ease: "power3.out" }, t0);
  if (q(".line").length) {
    tl.fromTo(q(".line"), { strokeDasharray: 1, strokeDashoffset: 1 }, { strokeDashoffset: 0, duration: Math.min(1.6, d * 0.6), ease: "power2.inOut" }, t0 + 0.2);
    tl.fromTo(q(".area"), { opacity: 0 }, { opacity: 1, duration: 0.8 }, t0 + 0.9);
    tl.fromTo(q(".dot"), { scale: 0, transformOrigin: "50%% 50%%" }, { scale: 1, duration: 0.4, ease: "back.out(3)" }, t0 + Math.min(1.7, d * 0.65));
    tl.fromTo(q(".pill"), { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.45, ease: "back.out(2.5)" }, t0 + 0.35);
    const p = s.querySelector(".price"), to = parseFloat(p.dataset.to), dec = parseInt(p.dataset.dec);
    const o = { v: to * 0.9 };
    const fmt = (v) => v.toLocaleString("en-US", { minimumFractionDigits: dec, maximumFractionDigits: dec });
    tl.to(o, { v: to, duration: 1.2, ease: "power2.out", onUpdate: () => (p.textContent = fmt(o.v)) }, t0 + 0.2);
  }
  if (q(".tile").length) tl.fromTo(q(".tile"), { x: 260, opacity: 0 }, { x: 0, opacity: 1, duration: 0.5, stagger: 0.14, ease: "power3.out" }, t0 + 0.2);
  tl.fromTo(q(".head"), { opacity: 0, y: 30 }, { opacity: 1, y: 0, duration: 0.5, ease: "power3.out" }, t0 + 0.3);
  const w = q(".w");
  if (w.length) tl.fromTo(w, { opacity: 0.18 }, { opacity: 1, duration: 0.12, stagger: Math.max(0.05, (d - 0.6) / w.length) }, t0 + 0.3);
  tl.to(s.querySelector(".inner"), { opacity: 0, y: -40, duration: 0.3, ease: "power2.in" }, t0 + d - 0.3);
});
window.__timelines["recap"] = tl;
"""


def build(snap):
    beats, star = renderer.recap_beats(snap)
    market = snap["tickers"]
    if PROJ.exists():
        shutil.rmtree(PROJ)
    PROJ.mkdir(parents=True)
    tmp = PROJ.parent / "tts"
    tmp.mkdir(exist_ok=True)
    durs = voiceover(beats, tmp)
    total = sum(durs)
    s = market[star]
    import datetime
    day = datetime.date.fromisoformat(s["as_of"]).strftime("%A, %b %d") if s.get("as_of") else ""
    starts = [sum(durs[:i]) for i in range(len(durs))]
    scenes = "\n".join(scene(i, b, starts[i], durs[i], market, day) for i, b in enumerate(beats))
    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<meta name="viewport" content="width={W}, height={H}" />
<title>Why Stocks Moved — recap</title>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>
<style>{font_face()}{CSS}</style>
</head>
<body>
<div id="root" data-composition-id="recap" data-start="0" data-width="{W}" data-height="{H}" data-duration="{total:.3f}">
  <div class="bg"></div><div class="glow"></div>
  <div class="bar"></div>
  <div class="top"><span class="brand"><b>WHY</b> STOCKS MOVED</span><span>MARKET RECAP</span></div>
  {scenes}
  <div class="disc">{html.escape(renderer.DISCLAIMER)}</div>
  <audio id="vo" src="vo.mp3" data-start="0" data-duration="{total:.3f}" data-track-index="2" data-volume="1"></audio>
</div>
<script>{JS % {"total": total}}</script>
</body>
</html>"""
    (PROJ / "index.html").write_text(page, encoding="utf-8")
    return beats, star, total


def main():
    snap = snapshot()
    beats, star, total = build(snap)
    log(f"kompozisyon hazır: {len(beats)} sahne, {total:.1f} sn")
    new = OUT / "hf_pilot" / "new_hyperframes.mp4"
    old = OUT / "hf_pilot" / "old_renderer.mp4"
    subprocess.run(["npx", "-y", "hyperframes@latest", "check"], cwd=PROJ)
    subprocess.run(["npx", "-y", "hyperframes@latest", "render", "--quality", "delivery", "--output", str(new)],
                   cwd=PROJ, check=True)
    renderer.render(beats, snap, old, star)
    for path, label in ((old, "1️⃣ ŞİMDİKİ (Python)"), (new, "2️⃣ YENİ (HyperFrames)")):
        with open(path, "rb") as f:
            tg_send("sendVideo", "caption", f"🧪 Why Stocks Moved deneme — {label}\nAynı veri, aynı ses. Yüklenmedi.",
                    files={"video": (path.name, f, "video/mp4")}, supports_streaming="true")
    tg("🧪 Hangisi daha iyi? 1 mi 2 mi? Beğenirsen kanal yeni görünüme geçirilir.")


if __name__ == "__main__":
    main()
