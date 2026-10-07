#!/usr/bin/env python3
"""daily_viral.py — youtube-agent-skill + claude-content-skills → tam otomatik günlük pipeline.

    python daily_viral.py --videos 2              # normal günlük çalışma (Görev Zamanlayıcı bunu çağırır)
    python daily_viral.py --videos 1 --dry-run    # her şeyi üret + render et, YouTube'a yükleme
    python daily_viral.py --fallback-only --dry-run   # sadece güvenli formatı (piyasa özeti) dene
"""
import csv, datetime, glob, json, os, re, sys, traceback
from zoneinfo import ZoneInfo

import requests

import renderer
from common import (DATA, OUT, STATE, BRAIN, PY, BASE, YTS, OOT, TODAY, CONTENT_LANG, llm, lines, log, retry, sh,
                    skill, context, tg, tg_social, yt_creds, have_yt_creds, is_quota_error)
from scoring import check_title, score_hooks

HOOK_MIN = int(os.environ.get("HOOK_MIN", 60))
TITLE_MIN = int(os.environ.get("TITLE_MIN", 85))
OUTLIER_MIN = float(os.environ.get("OUTLIER_MIN", 3.0))
MAX_TRIES, MAX_OSD_WORDS = 3, 7
TR = CONTENT_LANG == "tr"
TZ = ZoneInfo(os.environ.get("PUBLISH_TZ", "Europe/Istanbul" if TR else "America/New_York"))
# yerel saat=hedef — going-viral rotasyonu (SHARE öğlen, SAVE akşam, 3. slot FOLLOW).
# EN varsayılanı crypto-shorts-factory'nin 09/14/19 UTC slotlarıyla çakışmaz (12:30 ET=16:30Z, 19:00 ET=23:00Z).
# 6 slot (günlük 10.000 kota: 6 × 1.600 yükleme + ~350 okuma/liste). İlk n slot kullanılır.
SLOTS = [(s.split("=")[0], s.split("=")[1]) for s in os.environ.get(
    "SLOTS", "14:00=SHARE,20:00=SAVE,11:00=FOLLOW" if TR else
    "07:00=SAVE,09:30=SHARE,12:30=SHARE,15:00=FOLLOW,17:30=SAVE,20:00=SHARE").split(",")]
DISCLAIMER = "Yatırım Tavsiyesi Değildir" if TR else "Not financial advice"
DRY = "--dry-run" in sys.argv


def publish_time(hhmm):
    """Slot saatini RFC3339 UTC'ye çevirir; saat geçtiyse 20 dk sonrasına kaydırır (publishAt gelecekte olmalı)."""
    h, m = map(int, hhmm.split(":"))
    now = datetime.datetime.now(TZ)
    t = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if t < now + datetime.timedelta(minutes=15):
        t = now + datetime.timedelta(minutes=20)
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------- 0. PİYASA VERİSİ (yfinance) ----------------
def market_snapshot():
    snap = json.loads(sh([PY, BASE / "market_snapshot.py"], timeout=300))
    (DATA / f"market_{TODAY}.json").write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
    return snap


def market_brief(snap):
    """LLM'e giden hali: seri yok, sadece rakamlar (token tasarrufu)."""
    out = {k: {x: v.get(x) for x in ("name", "price", "change_pct", "change_5d_pct", "as_of", "news")}
           for k, v in snap["tickers"].items()}
    for v in out.values():                          # "on Friday" diyebilmek için kapanış günü adı
        if v.get("as_of"):
            v["as_of_day"] = datetime.date.fromisoformat(v["as_of"]).strftime("%A")
    return out


FACT_RULES = """FACT RULES (a finance channel lives or dies on this):
- Every number comes from the market data above. Never round a number into a different claim.
- A CAUSE ("why it moved") may only come from the "news" headlines/summaries of that asset or of the indexes.
  Attribute it ("according to today's headlines", "reports say"). If no headline explains the move, do not
  invent one: say the cause isn't clear yet and focus on what the move means for the viewer.
- Never claim fund flows, trading volume, institutional buying, insider activity, analyst actions or
  predictions unless a headline in the data says exactly that. No price targets, no buy/sell advice."""


STALE_RE = re.compile(r"\b(today|tonight|this morning|right now)\b|\bbugün\b", re.I)


def covered_moves(days=10):
    """Son günlerde video yapılmış (varlık, kapanış günü) çiftleri: aynı hareket ikinci kez anlatılmaz.
    Hafta sonu ve Pazartesi sabahı veri hâlâ Cuma kapanışı; eskiden Cuma'nın hareketi 3 gün üst üste yükleniyordu."""
    out = set()
    since = datetime.date.today() - datetime.timedelta(days=days)
    for f in glob.glob(str(DATA / "job_*.json")):
        try:
            day = datetime.date.fromisoformat(os.path.basename(f)[4:14])
            if day < since:
                continue
            job = json.loads(open(f, encoding="utf-8").read())
            t = job.get("idea", {}).get("ticker")
            as_of = job.get("as_of")
            if not as_of:                              # eski kayıtlar: o günün piyasa dosyasından
                mf = DATA / f"market_{day.isoformat()}.json"
                if mf.exists():
                    as_of = json.loads(mf.read_text(encoding="utf-8"))["tickers"].get(t, {}).get("as_of")
            if t and as_of:
                out.add((t, as_of))
        except (ValueError, KeyError, json.JSONDecodeError):
            continue
    return out


# ---------------- 1. TALEP (agent-reach → Reddit) ----------------
def demand():
    out = []
    for sub in lines(STATE / "subreddits.txt"):
        try:
            j = requests.get(f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=15",
                             headers={"User-Agent": "viral-pipeline/1.0"}, timeout=20).json()
            out += [{"sub": sub, "title": c["data"]["title"], "score": c["data"]["score"],
                     "comments": c["data"]["num_comments"]} for c in j["data"]["children"]]
        except Exception as e:
            log(f"reddit atlandı {sub}: {e}")        # 429 vb. → o gün talep adımı eksik kalır, devam
    out.sort(key=lambda x: -(x["score"] + 3 * x["comments"]))
    return out[:20]


# ---------------- 2. KEŞİF (/yt-viral) ----------------
def _iso_seconds(d):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else None


def collect_api(url, api):
    """YouTube Data API ile kanalın son 30 videosu (~3 kota birimi). GitHub IP'lerinde yt-dlp bot engeline takılır."""
    m = re.search(r"youtube\.com/(@[\w.\-]+|channel/(UC[\w\-]+))", url)
    if not m:
        raise ValueError(f"tanınmayan kanal URL'si: {url}")
    q = {"id": m.group(2)} if m.group(2) else {"forHandle": m.group(1)}
    items = api.channels().list(part="contentDetails,snippet", **q).execute().get("items", [])
    if not items:
        raise ValueError("kanal bulunamadı")
    ch = items[0]["snippet"]["title"]
    uploads = items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    pl = api.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=30).execute()
    ids = [i["contentDetails"]["videoId"] for i in pl.get("items", [])]
    rows = []
    for v in api.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids)).execute().get("items", []):
        dur = _iso_seconds(v["contentDetails"].get("duration"))
        if dur and dur <= 180 and v["statistics"].get("viewCount"):    # sadece Shorts uzunluğu
            rows.append({"channel": ch, "title": v["snippet"]["title"], "views": int(v["statistics"]["viewCount"]),
                         "duration": dur, "url": f"https://www.youtube.com/shorts/{v['id']}"})
    return rows


def discover():
    rows = []
    api = None
    if have_yt_creds():
        from googleapiclient.discovery import build
        api = build("youtube", "v3", credentials=yt_creds(), cache_discovery=False)
    if api is None:                                                 # yt-dlp ile kazıma yok (YouTube şartları)
        log("YouTube API yok, keşif atlandı")
        return []
    for url in lines(STATE / "channels.txt"):
        try:
            rows += collect_api(url, api)
        except Exception as e:
            log(f"kanal atlandı {url}: {str(e)[:200]}")
    p = DATA / f"collected_{TODAY}.json"
    p.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    res = {"outliers": []}
    for lo in (OUTLIER_MIN, 2.0):                                   # eşik düşürme yedeği
        res = json.loads(sh([PY, YTS / "yt-viral" / "swipe.py", p, "--min", str(lo), "--json"]))
        if res["outliers"]:
            break
    if not res["outliers"]:                                         # son 7 günün outlier'ları
        for f in sorted(glob.glob(str(DATA / "outliers_*.json")))[-7:]:
            res["outliers"] += json.loads(open(f, encoding="utf-8").read())["outliers"][:5]
        res["outliers"].sort(key=lambda r: -r["multiple"])
    else:
        (DATA / f"outliers_{TODAY}.json").write_text(json.dumps(res, indent=1, ensure_ascii=False), encoding="utf-8")
    log(f"keşif: {len(rows)} video, {len(res['outliers'])} outlier")
    return res["outliers"]


# ---------------- 3. İNCELEME (reel-analyzer + agent-reach video) ----------------
def teardown(outlier):
    return llm(skill("oot", "reel-analyzer") + "\n\n" + context(),
               f"""Reel to model: "{outlier['title']}" ({outlier['multiple']}x its channel median, formula: {outlier['formula']}).
No transcript is used (we never download other creators' videos or captions): work from title + formula only.
Return JSON: {{"hook":"...","hook_why":"...","beats":[{{"t":"0-3s","said":"...","shown":"..."}}],
"pacing":"...","visual_technique":"...","reusable_moves":["...","..."],"remake_plan":"..."}}
Model the general TECHNIQUE only (pacing, hook type). Never reproduce the creator's words, title wording,
story, or visual style: our video must not feel interchangeable with theirs.""")


# ---------------- 4. HOOK MADENCİLİĞİ (hook-mining) ----------------
def mine(outliers):
    p = DATA / f"hooks_{TODAY}.csv"
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["hook", "score"])
        for o in outliers:
            w.writerow([o["title"], o["multiple"]])                 # performans = kendi medyanına göre multiple
    sh([PY, OOT / "hook-mining" / "mine_hooks.py", p, "--top", "40"])
    return json.loads((DATA / f"hooks_{TODAY}.mined.json").read_text(encoding="utf-8"))


# ---------------- 5. SEÇİM + STRATEJİ (going-viral) ----------------
def pick_ideas(outliers, td, dem, market, goals):
    r = llm(skill("oot", "going-viral") + "\n\n" + skill("yt", "yt-viral") + "\n\n" + context(),
            f"""Top outliers: {json.dumps(outliers[:5], ensure_ascii=False)}
Teardown of #1: {json.dumps(td, ensure_ascii=False)}
What people ask today (Reddit): {json.dumps(dem[:10], ensure_ascii=False)}
Today's REAL market data (only these numbers, never invent): {json.dumps(market, ensure_ascii=False)}
Make {len(goals)} ideas. Idea i has goal = {goals}[i]. Each reuses a proven STRUCTURE on today's data,
answers a real audience question where possible, and states the emotion that drives its goal.
"ticker" must be one of the market data keys and is the asset the video is about.
Every idea must fit "What this channel covers" in the voice profile; never pick a topic it excludes.
Prefer moves that today's "news" headlines actually explain: the channel promises the WHY.
{FACT_RULES}
JSON: {{"ideas":[{{"idea":"...","goal":"SHARE|SAVE|FOLLOW","emotion":"...","formula":"...","ticker":"...",
"structure_from":"<outlier url>","payoff_withheld_until_end":"...","data_points":["..."]}}]}}""")
    return [i for i in r.get("ideas", []) if isinstance(i, dict) and i.get("idea")][:len(goals)]


# ---------------- 6. HOOK (viral-hook-writer + hook-mining remix) → hookscore kapısı ----------------
HOOK_RUBRIC = """HOW EVERY HOOK IS SCORED (hookscore.py; each property 0-100, verdict = 60% mean + 40% the WEAKEST
property, so a single weak property sinks the hook; the gate is {min}):
- SPECIFICITY: a concrete figure (12%, $4,350, 5 days) and a named company/asset; no hype adjectives
  (amazing, insane, huge, massive, secret, ultimate, best, crazy).
- ADDRESS: "you"/"your" inside the first six words, ideally twice in the line.
- STAKES: name the cost with words like lose, lost, cost, waste, risk, before, stop, never, broke, fail.
- CURIOSITY: open a gap with why / how / what / which / until / but / nobody / almost; a closing "?" helps;
  never resolve it (no "because", "so that", "which means").
- BREVITY: 9 to 24 spoken words.
Aim for EVERY property >= 60. A hook that is strong on four and dead on one fails."""

TITLE_RUBRIC = """HOW EVERY TITLE+COVER PAIR IS CHECKED (title.py; ANY issue fails the gate, score must be >= {min}):
- length: the title is AT MOST 40 characters INCLUDING spaces (count them; the mobile feed cuts at 40).
- no-number: the title contains a digit (a %, a price, a date).
- front-load: the first three words are not all filler (the, a, how, why, what, this, your...).
- shouting: at most two ALL-CAPS words.
- vague: none of amazing, incredible, insane, crazy, huge, massive, ultimate, best, powerful, secret, epic, perfect.
- duplicate: the cover text shares NO meaningful word with the title (the cover says what the title does not).
- thumb-length: cover text is 1-3 words."""


def _hook_feedback(scored):
    lines = []
    for r in scored[:3]:
        weak = min(r["properties"], key=r["properties"].get)
        props = ", ".join(f"{k} {v}" for k, v in r["properties"].items())
        lines.append(f'- "{r["hook"]}" → {r["verdict"]} ({props}); weakest {weak}: {hs_fix(weak)}')
    return "\n".join(lines)


def hs_fix(prop):
    from scoring import hs
    return hs.FIX.get(prop, "")


def best_hook(idea, mined):
    buckets = {k: [h["hook"] for h in v[:3]] for k, v in mined.get("buckets", {}).items()}
    feedback, best = "", None
    for attempt in range(MAX_TRIES):
        retry_note = (f"\nYOUR PREVIOUS ATTEMPT'S BEST HOOKS DID NOT PASS. Scores:\n{feedback}\n"
                      "Rewrite them: fix each one's weakest property while keeping what already scored well.\n"
                      if feedback else "")
        hooks = llm(skill("oot", "viral-hook-writer") + "\n\n" + skill("oot", "hook-mining") + "\n\n"
                    + skill("yt", "yt-script") + "\n\n" + context(),
                    f"""Idea: {json.dumps(idea, ensure_ascii=False)}
Proven hook skeletons in our niche (by pattern): {json.dumps(buckets, ensure_ascii=False)}
Power words earning their keep: {mined.get('power_word_frequency', [])[:15]}
{HOOK_RUBRIC.format(min=HOOK_MIN)}
{retry_note}
Write 10 hooks (spoken). At least 5 are REMIXES: keep a proven skeleton, swap ONLY power words, never
verbatim. Use real numbers from the idea only. Each has a 3-5 word on-screen version.
The numbers are from the last market close, not from today: never write "today", "tonight", "this morning"
or "right now"; name the day (e.g. "on Friday") or say "this week".
JSON: {{"hooks":[{{"line":"...","on_screen":"...","pattern":"..."}}]}}""", creative=True).get("hooks", [])
        hooks = [h for h in hooks if isinstance(h, dict) and h.get("line")
                 and not STALE_RE.search(h["line"] + " " + (h.get("on_screen") or ""))]   # eski veri: "today" yok
        if not hooks:
            continue
        by_line = {h["line"].replace("\n", " ").strip(): h for h in hooks}
        scored = score_hooks(list(by_line))
        top = scored[0]
        log(f"  hook {top['verdict']} (deneme {attempt + 1}): {top['hook'][:70]}")
        if not best or top["verdict"] > best["verdict"]:
            best = {**top, "on_screen": by_line.get(top["hook"], {}).get("on_screen", "")}
        if top["verdict"] >= HOOK_MIN:
            return best
        feedback = _hook_feedback(scored)
    return None


# ---------------- 7-8. SCRIPT + EKRAN YAZISI (reel-scripter/builder, yt-shorts, on-screen-text) ----------------
def write_script(idea, hook, td, market):
    s = llm(skill("oot", "reel-scripter") + "\n\n" + skill("oot", "reel-builder")[:3000] + "\n\n"
            + skill("yt", "yt-shorts") + "\n\n" + skill("oot", "on-screen-text-writer") + "\n\n" + context(),
            f"""Idea: {json.dumps(idea, ensure_ascii=False)}
Market data (only numbers you may use): {json.dumps(market, ensure_ascii=False)}
Winning hook (first spoken line, verbatim): {hook['hook']}   On-screen at frame 0: {hook['on_screen']}
Structure to model (NOT words): {json.dumps(td.get('beats', []), ensure_ascii=False)} · pacing: {td.get('pacing', '')}
Write a 25-32s vertical Short (60-85 words), 4-6 beats. No filler: every sentence carries a number from the market data or a concrete cause from the news; cut generic lines like 'investors are watching closely'. Frame 0 = moving chart. Claim lands ~1.5s.
Re-hook at ~9s and ~15s. Tease the payoff in the hook, deliver it in the LAST beat.
Every beat: spoken line + on-screen text (headline, <=7 words, one EMPHASIS word that appears in it) +
visual for the renderer: chart (price line of "ticker"), counter (big animated number from the osd),
list (asset tiles), compare (5-day bars of "ticker" vs "compare_with"), text.
"ticker"/"compare_with" must be market data keys. Use "counter" ONLY when that beat's osd contains the number.
Last line loops into the first. One CTA. Final beat on-screen: "{DISCLAIMER}".
Plain text only: no markdown, no asterisks; put the emphasis word in "emphasis" instead.
{FACT_RULES}
JSON: {{"beats":[{{"say":"...","osd":"...","emphasis":"...","visual":"chart|counter|list|compare|text","ticker":"..."}}],"word_count":0}}""",
            creative=True)
    beats = [b for b in s.get("beats", []) if isinstance(b, dict) and (b.get("say") or "").strip()]
    for b in beats:                                   # model markdown yazarsa: **kelime** → vurgu, yıldızlar ekrana çıkmasın
        bold = re.findall(r"\*\*(.+?)\*\*", b.get("osd") or "")
        if bold and not b.get("emphasis"):
            b["emphasis"] = bold[0]
        for k in ("osd", "say", "emphasis"):
            b[k] = re.sub(r"[*_`#]+", "", b.get(k) or "").strip()
    beats[0:1] = [{**beats[0], "say": hook["hook"]}] if beats else []   # hook birebir ilk cümle
    s["beats"] = beats
    words = sum(len(b["say"].split()) for b in beats)
    s["word_count"] = words
    s["mute_pass"] = bool(beats) and all(b.get("osd") and len(b["osd"].split()) <= MAX_OSD_WORDS for b in beats)
    s["length_pass"] = 45 <= words <= 95                 # ~32 sn üstü Shorts izlenme süresini düşürür
    return s


# ---------------- 9. PAKET (yt-package + cover-thumbnail-brief) → title.py kapısı ----------------
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def invented_numbers(text, market):
    """Başlıkta olup piyasa verisinde olmayan sayılar (ör. 'Nasdaq up 22%' gibi uydurma/yanlış oranlar)."""
    def norm(x):
        x = x.replace(",", "")
        try:
            v = float(x)
        except ValueError:
            return set()
        return {f"{v:g}", f"{round(v):g}", f"{round(v, 1):g}", f"{round(v, 2):g}"}
    allowed = set()
    for m in NUM_RE.findall(json.dumps(market)):
        allowed |= norm(m)
        try: allowed |= norm(str(abs(float(m.replace(",", "")))))
        except ValueError: pass
    bad = []
    for m in NUM_RE.findall(text):
        v = float(m.replace(",", ""))
        if v <= 12 or 2020 <= v <= 2035:          # "3 sectors", "5 days", yıllar
            continue
        if not (norm(m) & allowed):
            bad.append(m)
    return bad


def published_titles():
    """Kanalda daha önce kullanılan tüm başlıklar (küçük harf)."""
    out = set()
    for f in glob.glob(str(BRAIN / "20*.md")):
        first = open(f, encoding="utf-8").readline()
        if " — " in first:
            out.add(first.rsplit(" — ", 1)[-1].strip().lower())
    return out


def recent_titles(n=8):
    """Kanaldaki son video başlıkları (state/brain notlarından), başlık kalıbı tekrarını önlemek için."""
    out = []
    for f in sorted(glob.glob(str(BRAIN / "20*.md")))[-n:]:
        first = open(f, encoding="utf-8").readline()
        if " — " in first:
            out.append(first.rsplit(" — ", 1)[-1].strip())
    return "; ".join(out) or "(none yet)"


def package(idea, script, market=None):
    feedback = ""
    for attempt in range(MAX_TRIES):
        retry_note = (f"\nYOUR PREVIOUS PAIRS FAILED THE CHECK:\n{feedback}\nFix exactly those issues.\n"
                      if feedback else "")
        cand = llm(skill("yt", "yt-package") + "\n\n" + skill("oot", "cover-thumbnail-brief") + "\n\n" + context(),
                   f"""Idea: {idea['idea']}  Hook: {script['beats'][0]['say']}
{TITLE_RUBRIC.format(min=TITLE_MIN)}
{retry_note}
TEN title+cover pairs. The title carries a number/name/date from the idea, subject in the first three words.
OUR LAST TITLES (do NOT reuse their sentence structure; a channel where every title reads "<Company> jumped X% today"
looks templated to YouTube): {recent_titles()}
Mix angles across the ten pairs: a question, a contrast, what it means for the viewer's money, a "why" angle.
Cover text is legible at 150px and clear of the top 12% / bottom 20%.
JSON: {{"pairs":[{{"title":"...","thumb":"...","visual_brief":"..."}}]}}""").get("pairs", [])
        results = []
        used = published_titles()
        for c in cand:
            if isinstance(c, dict) and c.get("title"):
                if c["title"].strip().lower() in used:                  # aynı başlık = tekrar içerik (hafta sonu aynı veri)
                    continue
                if market is not None and invented_numbers(c["title"], market):   # başlıktaki her sayı veride olmalı
                    log(f"  başlık reddedildi (veride olmayan sayı {invented_numbers(c['title'], market)}): {c['title']}")
                    continue
                r = check_title(c["title"], c.get("thumb"))
                results.append({**r, "thumb": c.get("thumb", ""), "visual_brief": c.get("visual_brief", "")})
        if not results:
            continue
        results.sort(key=lambda r: (bool(r["issues"]), -r["score"]))   # önce sorunsuz olanlar
        best = results[0]
        log(f"  title {best['score']} (deneme {attempt + 1}): {best['title']}  issues={[i[0] for i in best['issues']]}")
        if best["score"] >= TITLE_MIN and not best["issues"]:
            return best
        feedback = "\n".join(f'- "{r["title"]}" ({r["chars"]} chars) + cover "{r["thumb"]}": '
                             + "; ".join(f"{k}: {m}" for k, m in r["issues"]) for r in results[:3])
    return None


# ---------------- 10. SEO (yt-seo) ----------------
def _seo_fallback(idea, pkg, script):
    """LLM'siz SEO: kapıları geçmiş bir video SEO adımı yüzünden asla kaybolmasın."""
    first = script["beats"][1]["say"] if len(script["beats"]) > 1 else script["beats"][0]["say"]
    name = (idea.get("ticker") or "").lstrip("^")
    return {"queries": [], "description": f"{pkg['title']}. {first}",
            "tags": [t for t in [name, "stock market", "stocks", "investing", "market news", "why stocks moved"] if t]}


def seo(idea, pkg, script):
    yt = None
    for _ in range(2):
        try:
            s = llm(skill("yt", "yt-seo") + "\n\n" + context(),
                    f"""Title: {pkg['title']}  Idea: {idea['idea']}  Goal: {idea['goal']}
Script: {json.dumps(script['beats'], ensure_ascii=False)}
Return EXACTLY this JSON shape (the outer "youtube" key is required):
{{"youtube": {{"queries":["q1","q2","q3"],"description":"2 lines = what viewer gets, then '{DISCLAIMER}', then #shorts","tags":["<=15 tags"]}}}}""")
            cand = s.get("youtube", s) if isinstance(s, dict) else {}     # model sarmalayıcıyı unutabiliyor
            if isinstance(cand, dict) and isinstance(cand.get("description"), str) and cand["description"].strip():
                yt = cand
                break
        except Exception as e:
            log(f"  seo denemesi başarısız: {str(e)[:120]}")
    if not yt:
        log("  seo: LLM çıktısı kullanılamadı, veriden oluşturuldu")
        yt = _seo_fallback(idea, pkg, script)
    s = {"youtube": yt}
    yt["tags"] = [t for t in yt.get("tags", []) if isinstance(t, str)][:15]
    if DISCLAIMER.lower() not in yt["description"].lower():
        yt["description"] += f"\n{DISCLAIMER}."
    if "#shorts" not in yt["description"].lower():
        yt["description"] += "\n#shorts"
    head = (pkg["title"] + " " + yt["description"][:200]).lower()
    yt["query_test_pass"] = any(all(w in head for w in q.lower().split()[:2]) for q in yt.get("queries", []))
    return s


# ---------------- RENDER + YÜKLEME ----------------
def render(job, i, snap):
    props = OUT / f"{TODAY}_{i}.json"
    props.write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")
    return renderer.render(job["script"]["beats"], snap, OUT / f"{TODAY}_{i}.mp4", job["idea"].get("ticker"))


def upload_youtube(mp4, pkg, yt, publish_at):
    if DRY:
        log(f"  [dry-run] yükleme atlandı: {mp4.name} → {publish_at}")
        return "DRYRUN"
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    api = build("youtube", "v3", credentials=yt_creds(), cache_discovery=False)
    # YouTube < ve > içeren başlık/açıklama/etiketi reddeder (invalidDescription), yükleme komple düşer
    clean = lambda s: str(s).replace("->", "→").replace("<", "").replace(">", "")
    body = {"snippet": {"title": clean(pkg["title"])[:100], "description": clean(yt["description"])[:4900],
                        "tags": [clean(t) for t in yt["tags"]], "categoryId": "25",
                        "defaultLanguage": CONTENT_LANG, "defaultAudioLanguage": CONTENT_LANG},
            "status": {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}}
    mode = os.environ.get("YOUTUBE_PRIVACY", "unlisted")      # scheduled = slot saatinde herkese açık
    if mode == "scheduled":
        body["status"].update(privacyStatus="private", publishAt=publish_at)
    else:
        body["status"]["privacyStatus"] = mode                # unlisted / private: önce elle izle
    vid = api.videos().insert(part="snippet,status", body=body,
                              media_body=MediaFileUpload(str(mp4), resumable=True)).execute()["id"]
    log(f"  yüklendi https://youtu.be/{vid} (yayın {publish_at})")
    return vid


def add_to_playlist(video_id, ticker=None, key=None):
    """state/playlists.json (brand/setup_playlists.py) → videoyu konusunun listesine ekle. Hata yüklemeyi bozmaz."""
    f = STATE / "playlists.json"
    if DRY or not f.exists():
        return
    pl = json.loads(f.read_text(encoding="utf-8"))
    pid = pl["by_key"].get(key) if key else pl["by_ticker"].get(ticker)
    if not pid:
        return
    try:
        from googleapiclient.discovery import build
        build("youtube", "v3", credentials=yt_creds(), cache_discovery=False).playlistItems().insert(
            part="snippet", body={"snippet": {"playlistId": pid,
                                              "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        log(f"  listeye eklendi: {pid}")
    except Exception as e:
        log(f"  listeye eklenemedi: {str(e)[:150]}")


# ---------------- 11. HAFIZA (ai-brain) ----------------
def brain_save(job):
    slug = re.sub(r"[^a-z0-9]+", "-", job["package"]["title"].lower())[:40].strip("-") or "video"
    name = f"{TODAY}-{slug}"
    (BRAIN / f"{name}.md").write_text(f"""# Video — {TODAY} — {job['package']['title']}
#ai-brain #video #{job['idea']['goal'].lower()} #{job['hook']['formula'].lower().replace(' ', '-')}
Related:: [[MOC]]
## Decisions
- Goal {job['idea']['goal']} / emotion {job['idea'].get('emotion', '')} — structure from {job['idea'].get('structure_from', '')}
- Hook ({job['hook']['verdict']}): {job['hook']['hook']}
- Title ({job['package']['score']}): {job['package']['title']} · cover "{job['package']['thumb']}"
## Built
- youtu.be/{job.get('video_id', '')}
## Open
- [ ] Pazar retention sonucu → lessons.md
""", encoding="utf-8")
    with open(BRAIN / "MOC.md", "a", encoding="utf-8") as f:
        f.write(f"- [[{name}]] — {job['idea']['goal']} · hook {job['hook']['verdict']}\n")


# ---------------- ÜRETİM + YEDEK ----------------
def produce(idea, mined, td, market):
    hook = best_hook(idea, mined)
    if not hook:
        return None, f"hook kapısı (<{HOOK_MIN})"
    script = write_script(idea, hook, td, market)
    if not script["length_pass"]:                   # bir kez daha, kısaltma notuyla (fikir boşa gitmesin)
        log(f"  script {script['word_count']} kelime → kısaltılarak yeniden yazılıyor")
        script = write_script({**idea, "rewrite_note": f"Previous draft had {script['word_count']} words; "
                                                     "stay within 60-85 words, 4-6 beats."}, hook, td, market)
    if not script["mute_pass"]:
        return None, "mute kapısı (ekran yazısı)"
    if not script["length_pass"]:
        return None, f"script uzunluğu ({script['word_count']} kelime)"
    pkg = package(idea, script, market)
    if not pkg:
        return None, f"başlık kapısı (<{TITLE_MIN})"
    spoken = " ".join([hook["hook"], pkg["title"], pkg.get("thumb", "")] + [b["say"] + " " + (b.get("osd") or "")
                                                                         for b in script["beats"]])
    if STALE_RE.search(spoken):                     # veri önceki kapanış: "today" yanıltıcı olur
        return None, "eski veri için 'today' dendi"
    return {"idea": idea, "hook": hook, "script": script, "package": pkg,
            "as_of": (market.get(idea.get("ticker")) or {}).get("as_of"),
            "platforms": {"youtube": seo(idea, pkg, script)["youtube"]}, "teardown": td}, ""


def fallback_recap(snap, i, publish_at):
    """Güvenli format: günün piyasa özeti — LLM'e ve puan kapılarına bağlı değil, slot asla boş kalmaz."""
    beats, star = renderer.recap_beats(snap)
    mp4 = renderer.render(beats, snap, OUT / f"{TODAY}_fallback_{i}.mp4", star)
    m = snap["tickers"][star]
    names = ", ".join(v["name"] for v in snap["tickers"].values())
    if TR:
        title = f"{m['name']} {renderer.pct_str(m['change_pct'], 2)} · Piyasa Özeti {datetime.date.today():%d.%m.%Y}"
        yt = {"description": f"Günün piyasa özeti: {names}.\n{DISCLAIMER}. Veriler gecikmelidir.\n#shorts",
              "tags": ["borsa", "piyasa", "kripto", "bitcoin", "altın", "dolar", "bist100", "piyasa özeti"]}
    else:
        title = f"{m['name']} {renderer.pct_str(m['change_pct'], 2)} · Market Recap {datetime.date.fromisoformat(m['as_of']):%b %d}"
        yt = {"description": f"Market recap for the {m['as_of']} close: {names}.\n{DISCLAIMER}. Data may be delayed.\n#shorts",
              "tags": ["stock market", "market recap", "bitcoin", "crypto", "stocks", "investing", "nasdaq", "gold"]}
    vid = upload_youtube(mp4, {"title": title}, yt, publish_at)
    add_to_playlist(vid, key="recap")
    if not DRY:                                      # aynı gün başka bir çalışma ikinci özet yüklemesin
        (DATA / f"recap_{TODAY}.json").write_text(json.dumps({"video_id": vid, "publish_at": publish_at,
                                                              "as_of": snap["tickers"][star].get("as_of")}),
                                                   encoding="utf-8")
    return vid, mp4, title


def main():
    n = int(sys.argv[sys.argv.index("--videos") + 1]) if "--videos" in sys.argv else 2
    slots = SLOTS[:n]
    log(f"=== daily_viral {TODAY} · {n} video{' · DRY-RUN' if DRY else ''} ===")
    snap = retry(market_snapshot)
    market = market_brief(snap)
    report = []
    global FACT_RULES
    FACT_RULES += ('\n- DATES: each asset\'s numbers are from its last close ("as_of", weekday in "as_of_day"); '
                   'the video is published later and markets are closed on weekends. Never write "today", '
                   '"tonight", "this morning" or "right now". Name the day instead, e.g. "on Friday", '
                   'or "this week" for 5-day moves.')
    covered = covered_moves()
    fresh = {k: v for k, v in market.items() if (k, v.get("as_of")) not in covered}
    log(f"taze hareket: {len(fresh)}/{len(market)} (daha önce anlatılanlar: "
        f"{sorted(k for k in market if k not in fresh)})")
    if len(fresh) < n:
        report.append(f"ℹ️ son kapanışlardan anlatılmamış {len(fresh)} varlık kaldı → {len(fresh)} video")
        slots = slots[:len(fresh)]
    pool, mined, td = [], {"buckets": {}, "power_word_frequency": []}, {}
    if "--fallback-only" not in sys.argv:
        try:
            dem = retry(demand)
            outliers = retry(discover)
            if outliers:
                td = retry(teardown, outliers[0])
                mined = mine(outliers)
                goals = [g for _, g in slots]
                # slot başına 3 aday fikir (1 asıl + 2 yedek)
                pool = retry(pick_ideas, outliers, td, dem, fresh, goals * 3) if goals else []
                pool = [x for x in pool if x.get("ticker") in fresh]   # anlatılmış hareket tekrar edilmez
                log(f"fikir havuzu: {len(pool)}")
            else:
                report.append("⚠️ Hiç outlier yok (channels.txt boş ya da erişilemedi) → güvenli format")
        except Exception as e:
            log(traceback.format_exc())
            report.append(f"⚠️ keşif/seçim hatası: {str(e)[:200]} → güvenli format")
    used, tickers_today, quota_hit = set(), set(), False
    social_sent = False
    # aynı kapanışın özeti ikinci kez yüklenmez (hafta sonu da Cuma verisi gelir)
    star_as_of = (snap["tickers"].get(renderer.recap_beats(snap)[1]) or {}).get("as_of")
    recap_done = (DATA / f"recap_{TODAY}.json").exists() or any(
        json.loads(open(f, encoding="utf-8").read()).get("as_of") == star_as_of
        for f in glob.glob(str(DATA / "recap_*.json")))
    for i, (hhmm, goal) in enumerate(slots):
        if quota_hit:
            report.append(f"⏸ [{goal}] {hhmm} atlandı — günlük YouTube kotası doldu, yarın devam")
            continue
        publish_at = publish_time(hhmm)
        done = False
        free = [x for x in pool if id(x) not in used]
        # aynı hedefteki fikirler önce; aynı gün aynı hisse tekrar etmesin
        free.sort(key=lambda x: (x.get("goal") != goal, x.get("ticker") in tickers_today))
        for idea in free[:3]:
            used.add(id(idea))
            log(f"[{goal}] {idea['idea'][:80]}")
            try:
                job, why = produce(idea, mined, td, market)
                if not job:
                    report.append(f"↻ {idea['idea'][:40]} — {why}, yedeğe geçildi")
                    continue
                mp4 = retry(render, job, i, snap)
                job["video_id"] = retry(upload_youtube, mp4, job["package"], job["platforms"]["youtube"], publish_at)
                job["publish_at"] = publish_at
                add_to_playlist(job["video_id"], ticker=job["idea"].get("ticker"))
                tickers_today.add(job["idea"].get("ticker"))
                if not DRY:                                 # test çalışmaları hafızayı / weekly verisini kirletmesin
                    (DATA / f"job_{TODAY}_{i}.json").write_text(json.dumps(job, ensure_ascii=False, indent=1),
                                                                encoding="utf-8")
                    brain_save(job)
                if not social_sent and not DRY:             # Telegram'a günde tek video (TikTok/Instagram için)
                    social_sent = True
                    tg_social(mp4, job["package"]["title"], f"https://youtu.be/{job['video_id']}",
                              job["idea"].get("ticker"))
                report.append(f"✅ [{goal}] {job['package']['title']}\n   hook {job['hook']['verdict']} · title "
                              f"{job['package']['score']} · {publish_at}\n   https://youtu.be/{job['video_id']}")
                done = True
                break
            except Exception as e:
                log(traceback.format_exc())
                if is_quota_error(e):
                    quota_hit = True
                    report.append(f"⏸ [{goal}] günlük YouTube kotası doldu, kalan slotlar yarına")
                    break
                report.append(f"↻ {idea['idea'][:40]} — hata: {str(e)[:150]}")
        if not done and recap_done:                                 # aynı özet 2. kez = tekrarlayan içerik
            report.append(f"⏭ [{goal}] {hhmm} boş bırakıldı — bugünün piyasa özeti zaten yüklendi")
        elif not done and not quota_hit:                            # slot boş kalmasın: günde bir özet
            recap_done = True
            try:
                vid, mp4, title = retry(fallback_recap, snap, i, publish_at)
                if not social_sent and not DRY:
                    social_sent = True
                    tg_social(mp4, title, f"https://youtu.be/{vid}")
                report.append(f"🛟 [{goal}] güvenli format (piyasa özeti) → https://youtu.be/{vid}")
            except Exception as e:
                log(traceback.format_exc())
                if is_quota_error(e):
                    quota_hit = True
                report.append(f"❌ [{goal}] güvenli format da başarısız: {str(e)[:200]}")
    msg = f"🎬 {TODAY} günlük viral (bilgi amaçlı, işlem gerekmez)\n\n" + "\n\n".join(report)
    log(msg)
    tg(msg)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(traceback.format_exc())
        tg(f"❌ daily_viral {TODAY} çöktü: {str(e)[:500]}")
        sys.exit(1)
