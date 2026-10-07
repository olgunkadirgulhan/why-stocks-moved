"""hf_pilot.py — HyperFrames denemesi: aynı piyasa özeti (recap) iki renderer ile.

Eski: renderer.render (Pillow kareleri + ffmpeg). Yeni: HTML/GSAP kompozisyon → `npx hyperframes render`.
Aynı seslendirme, aynı gerçek veri; ikisi de Telegram'a gider, karşılaştırıp karar verilir. YouTube'a yüklenmez.
    python hf_pilot.py            # out/hf_pilot/{old,new}.mp4
"""
import glob, html, json, shutil, subprocess, sys

import renderer
from common import BASE, OUT, log, tg, tg_send

import hf_render


def snapshot():
    r = subprocess.run([sys.executable, str(BASE / "market_snapshot.py")], capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def main():
    snap = snapshot()
    beats, star = renderer.recap_beats(snap)
    new = OUT / "hf_pilot" / "new_hyperframes.mp4"
    old = OUT / "hf_pilot" / "old_renderer.mp4"
    new.parent.mkdir(parents=True, exist_ok=True)
    hf_render.render(beats, snap, new, star, label="MARKET RECAP")
    renderer.render_pillow(beats, snap, old, star)
    for path, label in ((old, "1️⃣ ŞİMDİKİ (Python)"), (new, "2️⃣ YENİ (HyperFrames)")):
        with open(path, "rb") as f:
            tg_send("sendVideo", "caption", f"🧪 Why Stocks Moved deneme — {label}\nAynı veri, aynı ses. Yüklenmedi.",
                    files={"video": (path.name, f, "video/mp4")}, supports_streaming="true")
    tg("🧪 Hangisi daha iyi? 1 mi 2 mi? Beğenirsen kanal yeni görünüme geçirilir.")
    # fenek-shorts telegram-relay için (bu repoda Telegram secret'ı olmasa da Fenek botuyla gelir)
    soc = BASE / "social"
    soc.mkdir(exist_ok=True)
    vids = []
    for path, label in ((old, "1️⃣ ŞİMDİKİ (Python)"), (new, "2️⃣ YENİ (HyperFrames)")):
        shutil.copy(path, soc / path.name)
        vids.append({"file": path.name, "caption": f"🧪 Why Stocks Moved deneme — {label}\nAynı veri, aynı ses. Yüklenmedi."})
    (soc / "post.json").write_text(json.dumps({"videos": vids, "note": "🧪 Hangisi daha iyi? 1 mi 2 mi? "
                                               "Beğenirsen kanal yeni görünüme geçirilir."}, ensure_ascii=False),
                                   encoding="utf-8")


if __name__ == "__main__":
    main()
