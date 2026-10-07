"""common.py — tüm pipeline'ın paylaştığı ayarlar ve yardımcılar (yollar, LLM, retry, OAuth, Telegram, log)."""
import datetime, glob, json, os, pathlib, re, subprocess, sys, time

import requests

BASE = pathlib.Path(__file__).resolve().parent


def _load_env():
    f = BASE / ".env"
    if not f.exists():
        return
    for ln in f.read_text(encoding="utf-8").splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1)
            v = re.split(r"\s+#", v, maxsplit=1)[0].strip().strip('"').strip("'")   # satır sonu yorumu
            if v:
                os.environ.setdefault(k.strip(), v)


_load_env()

PY = sys.executable
YTS = pathlib.Path(os.environ.get("YTS") or BASE / "vendor/youtube-agent-skill/skills")
OOT = pathlib.Path(os.environ.get("OOT") or BASE / "vendor/claude-content-skills/skills")
DATA, OUT, STATE, LOGS = BASE / "data", BASE / "out", BASE / "state", BASE / "logs"
BRAIN = STATE / "brain"
for _d in (DATA, OUT, STATE, LOGS, BRAIN):
    _d.mkdir(parents=True, exist_ok=True)

CONTENT_LANG = os.environ.get("CONTENT_LANG", "en")
# Sırayla denenir; anahtarı olmayan atlanır, hata/limit verende sıradakine geçilir.
# gemini (ücretsiz) → groq (ücretsiz) → anthropic (ücretli, opsiyonel) → ollama (yerel GPU)
LLM_BACKEND = os.environ.get("LLM_BACKEND", "gemini,groq,anthropic")
LLM_CREATIVE_BACKEND = os.environ.get("LLM_CREATIVE_BACKEND", LLM_BACKEND)  # hook + script adımı (§8.7)
# Yoğunluk (503) / zaman aşımında sıradaki model. Adlar 2026-09-23'te tools/llm_probe.py ile doğrulandı.
# Farklı nesil/boyutlar ayrı kapasite havuzlarında: flash'lar birlikte 503 verse de lite/gemma genelde açık.
GEMINI_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODEL", ",".join([
    "gemini-flash-latest", "gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.7-flash", "gemini-3-flash-preview",
    "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
    "gemma-4-31b-it", "gemma-4-26b-a4b-it"])).split(",")]
GEMINI_ROUND_PAUSE = int(os.environ.get("GEMINI_ROUND_PAUSE", "90"))   # tüm modeller meşgulse bekle, 1 tur daha
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
LLM_MIN_INTERVAL = float(os.environ.get("LLM_MIN_INTERVAL", "7"))   # ücretsiz katman dakika limiti için
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1:8b")
OLLAMA_NUM_CTX = int(os.environ.get("OLLAMA_NUM_CTX", "16384"))
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5")
TG_TOKEN, TG_CHAT = os.environ.get("TG_TOKEN"), os.environ.get("TG_CHAT")
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
             "https://www.googleapis.com/auth/youtube",              # kanal ayarları: banner, açıklama, filigran
             "https://www.googleapis.com/auth/youtube.readonly",
             "https://www.googleapis.com/auth/yt-analytics.readonly"]

TODAY = datetime.date.today().isoformat()
_LOG = LOGS / f"{TODAY}.log"

# Alt süreçteki python araçları Windows'ta cp1254/cp1252 ile değil UTF-8 ile okuyup yazsın
_CHILD_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}


def log(msg):
    line = f"[{datetime.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def sh(cmd, cwd=None, timeout=None):
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=cwd, timeout=timeout, env=_CHILD_ENV)
    if r.returncode:
        raise RuntimeError(f"{pathlib.Path(str(cmd[0])).name} {r.returncode}: {r.stderr.strip()[-600:]}")
    return r.stdout


def lines(path):
    """Yorum (#) ve boş satırları atlayarak bir liste dosyası oku."""
    p = pathlib.Path(path)
    if not p.exists():
        return []
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.strip().startswith("#")]


def skill(repo, name):
    root = YTS if repo == "yt" else OOT
    return (root / name / "SKILL.md").read_text(encoding="utf-8")


def context():
    voice = (STATE / "voice.md").read_text(encoding="utf-8")
    lessons = (STATE / "lessons.md").read_text(encoding="utf-8") if (STATE / "lessons.md").exists() else ""
    notes = sorted(glob.glob(str(BRAIN / "20*.md")))[-10:]            # ai-brain: sadece son 10 not
    brain = "\n---\n".join(pathlib.Path(n).read_text(encoding="utf-8")[:600] for n in notes)
    lang = {"tr": "Turkish", "en": "English"}.get(CONTENT_LANG, CONTENT_LANG)
    return (f"OUTPUT LANGUAGE: every audience-facing string (hooks, script, on-screen text, titles, "
            f"description, tags) is written in {lang}. JSON keys stay in English.\n\n"
            f"VOICE PROFILE:\n{voice}\n\nLESSONS (our retention data):\n{lessons}\n\nPAST WINNERS (ai-brain):\n{brain}")


def _json_from(txt):
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt.strip())
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        a, b = txt.find("{"), txt.rfind("}")
        return json.loads(txt[a:b + 1])


def _ollama(system, prompt, as_json):
    r = requests.post(OLLAMA_URL, json={
        "model": OLLAMA_MODEL, "system": system, "prompt": prompt, "stream": False,
        **({"format": "json"} if as_json else {}),
        "options": {"temperature": 0.8, "num_ctx": OLLAMA_NUM_CTX}}, timeout=900)
    r.raise_for_status()
    return r.json()["response"]


def _anthropic(system, prompt, as_json):
    import anthropic
    client = anthropic.Anthropic()
    if as_json:
        prompt += "\n\nReply with ONLY the JSON object, no prose, no code fences."
    resp = client.messages.create(model=ANTHROPIC_MODEL, max_tokens=16000, system=system,
                                  messages=[{"role": "user", "content": prompt}])
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude isteği reddetti (refusal)")
    return "".join(b.text for b in resp.content if b.type == "text")


_gemini_ok = [0]


def gemini_request(model, system, prompt, as_json):
    """Tek model çağrısı. Gemma'da sistem talimatı ve JSON modu yok: talimat prompt'un başına eklenir."""
    gemma = model.startswith("gemma")
    body = {"contents": [{"role": "user", "parts": [{"text": f"{system}\n\n{prompt}" if gemma else prompt}]}],
            "generationConfig": {"temperature": 0.8, "maxOutputTokens": 8192,
                                 **({"responseMimeType": "application/json"} if as_json and not gemma else {})}}
    if not gemma:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                         params={"key": os.environ["GEMINI_API_KEY"]}, timeout=(10, 75), json=body)


def _gemini(system, prompt, as_json):
    """Google Gemini API, ücretsiz katman (aistudio.google.com anahtarı, kart gerekmez)."""
    last, n = None, len(GEMINI_MODELS)
    for rnd in range(2):
        if rnd:
            log(f"  gemini: tüm modeller meşgul, {GEMINI_ROUND_PAUSE}s sonra bir tur daha")
            time.sleep(GEMINI_ROUND_PAUSE)
        for k in range(n):                           # son çalışan modelden başla, hepsini dolaş
            idx = (_gemini_ok[0] + k) % n
            model = GEMINI_MODELS[idx]
            try:
                r = gemini_request(model, system, prompt, as_json)
            except requests.RequestException as e:
                last = f"{model}: {type(e).__name__}"
                continue
            if r.ok:
                cands = r.json().get("candidates") or []
                parts = cands[0].get("content", {}).get("parts", []) if cands else []
                txt = "".join(p.get("text", "") for p in parts if not p.get("thought"))
                if txt.strip():
                    if idx != _gemini_ok[0]:
                        log(f"  gemini modeli: {model}")
                    _gemini_ok[0] = idx
                    return txt
                last = f"{model}: boş yanıt ({cands[0].get('finishReason') if cands else 'no candidates'})"
            else:
                last = f"{model}: {r.status_code} {r.text[:200]}"
    _gemini_ok[0] = 0                                # hepsi düştüyse sonraki çağrıda baştan dene
    raise RuntimeError(f"gemini: {last}")


def _groq(system, prompt, as_json):
    """Groq, ücretsiz katman (console.groq.com anahtarı, kart gerekmez). Dakikada 8K token sınırı var."""
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=300,
                      headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}, json={
                          "model": GROQ_MODEL, "temperature": 0.8, "max_tokens": 4096,
                          **({"response_format": {"type": "json_object"}} if as_json else {}),
                          "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
    if not r.ok:
        raise RuntimeError(f"groq: {r.status_code} {r.text[:200]}")
    return r.json()["choices"][0]["message"]["content"]


_BACKENDS = {"gemini": (_gemini, "GEMINI_API_KEY"), "groq": (_groq, "GROQ_API_KEY"),
             "anthropic": (_anthropic, "ANTHROPIC_API_KEY"), "ollama": (_ollama, None)}
_last_call = [0.0]


def llm(system, prompt, as_json=True, creative=False):
    """Zincirdeki ilk çalışan servisi kullanır; limit/hata/bozuk JSON'da sıradakine geçer."""
    chain = [b.strip() for b in (LLM_CREATIVE_BACKEND if creative else LLM_BACKEND).split(",") if b.strip()]
    errors = []
    for name in chain:
        fn, key = _BACKENDS[name]
        if key and not os.environ.get(key):
            continue
        wait = LLM_MIN_INTERVAL - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
        try:
            txt = fn(system, prompt, as_json)
            return _json_from(txt) if as_json else txt
        except Exception as e:
            errors.append(f"{name}: {str(e)[:160]}")
            log(f"  llm {name} başarısız, sıradaki deneniyor: {str(e)[:120]}")
    raise RuntimeError("hiçbir LLM servisi yanıt vermedi — " + (" | ".join(errors) or "API anahtarı yok"))


def is_quota_error(e):
    return "quotaExceeded" in str(e) or "dailyLimitExceeded" in str(e)


def retry(fn, *a, tries=3, waits=(30, 120, 300), **kw):
    for k in range(tries):
        try:
            return fn(*a, **kw)
        except Exception as e:
            if k == tries - 1 or is_quota_error(e):     # kota bitti: tekrar denemek kotayı daha da yer
                raise
            log(f"retry {fn.__name__} ({str(e)[:200]}) {waits[k]}s sonra")
            time.sleep(waits[k])


def have_yt_creds():
    return bool(os.environ.get("YOUTUBE_REFRESH_TOKEN")) or (STATE / "token.json").exists()


def yt_creds():
    """GitHub Actions: YOUTUBE_CLIENT_ID/SECRET/REFRESH_TOKEN secret'larından. Yerelde: state/token.json."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if os.environ.get("YOUTUBE_REFRESH_TOKEN"):
        creds = Credentials(None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
                            token_uri="https://oauth2.googleapis.com/token",
                            client_id=os.environ["YOUTUBE_CLIENT_ID"],
                            client_secret=os.environ["YOUTUBE_CLIENT_SECRET"])
        creds.refresh(Request())                              # her çalışmada taze access token
        return creds
    tok = STATE / "token.json"
    if not tok.exists():
        raise RuntimeError("YouTube yetkisi yok — `python auth_youtube.py` çalıştır, çıkan değerleri GitHub secret yap")
    creds = Credentials.from_authorized_user_file(str(tok), YT_SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        tok.write_text(creds.to_json(), encoding="utf-8")   # otomatik yenile + kaydet
    return creds


def tg(msg):
    if not (TG_TOKEN and TG_CHAT):
        return
    try:
        requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                      json={"chat_id": TG_CHAT, "text": msg[:4000]}, timeout=20)
    except Exception as e:
        log(f"telegram gönderilemedi: {e}")


def tg_send(method, text_field, text, files=None, **extra):
    if not (TG_TOKEN and TG_CHAT):
        return False
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{method}",
                          data={"chat_id": TG_CHAT, text_field: text, **extra}, files=files, timeout=180)
        r.raise_for_status()
        return True
    except Exception as e:
        log(f"telegram gönderilemedi: {e}")
        return False


def tg_social(mp4, title, url, ticker=None):
    """Günün tek videosu: orijinal dosya (TikTok/Instagram'a kaliteli yükleme) + dokununca kopyalanan açıklamalar.
    Ayrıca social/ klasörüne yazılır: fenek-shorts'taki telegram-relay onu (artifact 'social-<run>') Fenek botuyla yollar."""
    tag = re.sub(r"[^A-Za-z0-9]", "", (ticker or "").upper())
    tag = f" #{tag}" if tag and not tag[0].isdigit() else ""
    note = "Not financial advice. Education only. Data may be delayed."
    captions = {
        "🎵 TikTok açıklaması (kutuya dokun → kopyalanır):":
            f"{title}\n\n{note}\n\n#stocks #stockmarket{tag} #investing #finance #learnontiktok #fyp",
        "📸 Instagram açıklaması (kutuya dokun → kopyalanır):":
            f"{title}\n\nFollow for one market move explained every day 📈\n{note}\n\n"
            f"#stocks #stockmarket #investing{tag} #finance{'' if tag else ' #money'}",  # Instagram: en fazla 5
    }
    import shutil
    soc = BASE / "social"
    soc.mkdir(exist_ok=True)
    shutil.copy(mp4, soc / "video.mp4")
    labels = list(captions.values())
    (soc / "post.json").write_text(json.dumps({"channel": "Why Stocks Moved", "title": title, "url": url,
                                               "tiktok": labels[0], "instagram": labels[1]},
                                              ensure_ascii=False, indent=1), encoding="utf-8")
    if not (TG_TOKEN and TG_CHAT) or os.path.getsize(mp4) > 49 * 1024 * 1024:
        return
    with open(mp4, "rb") as f:
        tg_send("sendDocument", "caption", f"🎬 Why Stocks Moved — günün videosu (TikTok/Instagram için)\n{title}\n{url}",
                files={"document": (os.path.basename(str(mp4)), f, "video/mp4")})
    for label, text in captions.items():
        esc = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        tg_send("sendMessage", "text", f"{label}\n<pre>{esc}</pre>", parse_mode="HTML")
