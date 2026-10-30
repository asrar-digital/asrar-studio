#!/usr/bin/env python3
"""أسرار ستوديو — السيرفر المحلي (الاستوديو بالمتصفح).

يشتغل على جهاز المستخدم فقط: http://127.0.0.1:8810
- يعرض الواجهة (engine/web)
- يستقبل المقاطع ويشغّل خطوات المونتاج
- يشغّل Claude Code بالخلفية (`claude -p`) باشتراك المستخدم — بدون مفاتيح API
"""
import json, os, re, shutil, subprocess, sys, threading, time, traceback, urllib.parse, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio as S  # noqa: E402

ENGINE = S.ENGINE
WEB = ENGINE / 'web'
PROJ = S.HOME / 'projects'
PORT = int(os.environ.get('ASRAR_STUDIO_PORT', '8810'))
JOBS = {}            # project -> running thread flag
LOCK = threading.Lock()

STAGES = [('upload', 'رفع المقاطع'), ('transcribe', 'تفريغ الكلام'), ('cut', 'قص السكتات'),
          ('plan', 'Claude يخطط المونتاج'), ('preview', 'المعاينة'), ('render', 'تصدير الفيديو'), ('done', 'جاهز')]
STAGE_KEYS = [k for k, _ in STAGES]


# ───────────────────────── project state ─────────────────────────
def pdir(name):
    p = (PROJ / name).resolve()
    if PROJ.resolve() not in p.parents:
        raise ValueError('bad name')
    return p


def rj(p, d=None):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d


def wj(p, data):
    tmp = str(p) + '.tmp'
    json.dump(data, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def status(name):
    return rj(pdir(name) / 'status.json', {'stage': 'upload', 'state': 'idle', 'msg': ''})


TLS = threading.local()          # اسم المشروع للخيط الحالي (لنسبة التقدم)
BASE = {}                        # نص المرحلة الأساسي لكل مشروع


def _progress(kind, frac):
    name = getattr(TLS, 'name', None)
    if not name: return
    st = status(name)
    pct = int(frac * 100)
    if st.get('pct') == pct: return
    st['pct'] = pct; st['msg'] = f"{BASE.get(name) or st.get('msg', '').split(' — ')[0]} — {pct}%"
    wj(pdir(name) / 'status.json', st)


S.PROGRESS = _progress


def set_status(name, stage=None, state=None, msg=None, error=None):
    st = status(name)
    if stage and stage != st.get('stage'): st['since'] = time.time()
    if state == 'run' and st.get('state') != 'run': st['since'] = time.time()
    if msg is not None: BASE[name] = msg; st.pop('pct', None)
    if stage: st['stage'] = stage
    if state: st['state'] = state
    if msg is not None: st['msg'] = msg
    st['error'] = error
    st['t'] = time.time()
    wj(pdir(name) / 'status.json', st)


def log(name, text, who='system'):
    p = pdir(name) / 'log.jsonl'
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps({'t': time.time(), 'who': who, 'text': text}, ensure_ascii=False) + '\n')


def read_log(name, since=0):
    p = pdir(name) / 'log.jsonl'
    if not p.exists():
        return []
    out = []
    for line in open(p, encoding='utf-8'):
        try:
            e = json.loads(line)
            if e['t'] > since: out.append(e)
        except Exception:
            pass
    return out[-300:]


def project_info(name):
    p = pdir(name)
    st = status(name)
    out = sorted([f.name for f in (p / 'out').glob('*.mp4')]) if (p / 'out').exists() else []
    thumb = 'thumb.jpg' if (p / 'thumb.jpg').exists() else None
    return {'name': name, 'status': st, 'brief': rj(p / 'brief.json', {}), 'outputs': out, 'thumb': thumb,
            'preview': 'preview.jpg' if (p / 'preview.jpg').exists() else None,
            'inputs': sorted(f.name for f in (p / 'inputs').glob('*')) if (p / 'inputs').exists() else [],
            'mtime': (p / 'status.json').stat().st_mtime if (p / 'status.json').exists() else p.stat().st_mtime,
            'running': name in JOBS, 'scripts': rj(p / 'scripts.json', []),
            'product': {k: v for k, v in rj(p / 'product.json', {}).items() if k != 'text'}}


# ───────────────────────── الدعوات (تجربة مغلقة) ─────────────────────────
import hashlib


def invited():
    return True   # الأداة مفتوحة للجميع (أُلغيت أكواد الدعوة)


def check_invite(code):
    c = re.sub(r'\s+', '', (code or '').upper())
    h = hashlib.sha256(('asrar-studio:' + c).encode()).hexdigest()
    if h not in rj(ENGINE / 'invites.json', []): return False
    S.HOME.mkdir(parents=True, exist_ok=True); wj(S.HOME / 'invite.json', {'h': h, 't': time.time()})
    return True


# ───────────────────────── Claude (headless) ─────────────────────────
def find_claude():
    for c in ('claude', 'claude.cmd', 'claude.exe'):
        w = shutil.which(c)
        if w: return w
    for c in (Path.home() / '.local' / 'bin' / 'claude.exe', Path.home() / '.local' / 'bin' / 'claude',
              Path(os.environ.get('APPDATA', '')) / 'npm' / 'claude.cmd'):
        if c.exists(): return str(c)
    return None


def snapshot(name):
    """نسخة احتياطية قبل أي تعديل (للتراجع)."""
    p = pdir(name)
    snap = p / '.snapshots' / time.strftime('%Y%m%d-%H%M%S')
    snap.mkdir(parents=True, exist_ok=True)
    for f in ('edit.json', 'timeline.json', 'brief.json', 'notes.json'):
        if (p / f).exists(): shutil.copy(p / f, snap / f)


AUTH = {'t': 0, 'ok': False}


def claude_logged_in(fresh=False):
    """هل Claude Code مسجّل دخول؟ (claude auth status) — مع كاش 15 ثانية."""
    if not fresh and time.time() - AUTH['t'] < 15: return AUTH['ok']
    exe = find_claude(); ok = False
    if exe:
        cmd = ['cmd', '/c', exe, 'auth', 'status'] if exe.lower().endswith(('.cmd', '.bat')) else [exe, 'auth', 'status']
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, encoding='utf-8', errors='replace',
                               creationflags=0x08000000 if os.name == 'nt' else 0)
            ok = bool(json.loads(r.stdout[r.stdout.find('{'):] or '{}').get('loggedIn'))
        except Exception:
            ok = False
    AUTH.update(t=time.time(), ok=ok)
    return ok


def open_login():
    """يفتح نافذة تسجيل دخول Claude (المتصفح + نافذة للصق الكود إذا انطلب)."""
    exe = find_claude()
    if not exe: raise RuntimeError('Claude Code مو مثبت على جهازك')
    AUTH['t'] = 0
    if os.name == 'nt':
        subprocess.Popen(['cmd', '/c', 'start', 'تسجيل دخول Claude', 'cmd', '/k', exe, 'auth', 'login'])
    elif sys.platform == 'darwin':
        subprocess.Popen(['osascript', '-e', f'tell app "Terminal" to do script "{exe} auth login"'])
    else:
        subprocess.Popen([exe, 'auth', 'login'])


def run_claude(name, task):
    """يشغّل Claude Code بدون واجهة داخل مجلد المشروع ويبث رسائله للسجل."""
    exe = find_claude()
    if not exe:
        raise RuntimeError('ما لقيت Claude Code على جهازك')
    if not claude_logged_in(fresh=True):
        raise RuntimeError('Claude مو متصل — اضغط «سجّل دخول Claude» فوق، والشغل يكمل تلقائياً بعد ما تسجّل')
    p = pdir(name)
    snapshot(name)
    cmd = [exe, '-p', 'Follow the task given on stdin. Work only inside the current project folder.',
           '--output-format', 'stream-json', '--verbose', '--permission-mode', 'acceptEdits',
           '--append-system-prompt-file', str(ENGINE / 'AGENT.md'), '--add-dir', str(ENGINE),
           '--allowedTools', 'Bash', 'Read', 'Edit', 'Write', 'Glob', 'Grep']
    if exe.lower().endswith(('.cmd', '.bat')):
        cmd = ['cmd', '/c'] + cmd
    full = (f'مجلد المشروع: {p}\nمحرّك أسرار ستوديو: {ENGINE / "studio.py"}\nبايثون: {sys.executable}\n'
            f'اسم المشروع: {name}\n\nالمطلوب:\n{task}\n')
    kw = {'creationflags': 0x08000000} if os.name == 'nt' else {}
    proc = subprocess.Popen(cmd, cwd=p, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
    proc.stdin.write(full.encode('utf-8')); proc.stdin.close()
    final, tail = None, []
    for raw in proc.stdout:
        line = raw.decode('utf-8', 'replace').strip()
        try:
            ev = json.loads(line)
        except Exception:
            tail = (tail + [line])[-20:]; continue
        if ev.get('type') == 'assistant':
            for b in (ev.get('message') or {}).get('content') or []:
                if b.get('type') == 'text' and b.get('text', '').strip():
                    log(name, b['text'].strip(), 'claude')
                elif b.get('type') == 'tool_use':
                    i = b.get('input') or {}
                    d = i.get('description') or i.get('file_path') or str(i.get('command', ''))[:120]
                    log(name, f'{b.get("name")}: {d}', 'tool')
        elif ev.get('type') == 'result':
            final = ev
    proc.wait()
    if (final and final.get('is_error')) or (proc.returncode not in (0, None) and not final):
        why = str((final or {}).get('result', ''))[:200] or ' '.join(tail)[-200:]
        if re.search(r'authenticat|OAuth|login|401', why, re.I):
            AUTH['t'] = 0
            raise RuntimeError('Claude مو متصل — اضغط «سجّل دخول Claude» فوق، والشغل يكمل تلقائياً بعد ما تسجّل')
        if re.search(r'usage limit|rate limit|quota', why, re.I):
            raise RuntimeError('وصلت حد استخدام اشتراك Claude — انتظر شوي ثم اضغط «أعد المحاولة من هنا»')
        raise RuntimeError('Claude ما كمّل: ' + why)


# ───────────────────────── pipeline ─────────────────────────
class Fail(Exception):
    pass


def guarded(fn, *a):
    try:
        fn(*a)
    except SystemExit:
        raise Fail('توقفت خطوة في المحرّك — شوف السجل')


def pipeline(name, from_stage='transcribe', skip=()):
    p = pdir(name)
    TLS.name = name
    try:
        order = [k for k in STAGE_KEYS[STAGE_KEYS.index(from_stage):] if k not in skip]
        if 'transcribe' in order:
            set_status(name, 'transcribe', 'run', 'أفرّغ كلامك…'); log(name, 'بدأت التفريغ — أول مرة ينزّل نموذج اللغة (~3 قيقا)')
            fast = rj(p / 'brief.json', {}).get('mode') == 'clips'   # الطويل: نموذج سريع للترشيح بس — كل مقطع ينفرّغ بالدقيق بعدين
            guarded(S.transcribe, name, *(['small'] if fast else []))
            log(name, f'✅ التفريغ خلص: {len(rj(p / "words.json", {}).get("words", []))} كلمة')
        if rj(p / 'brief.json', {}).get('mode') == 'clips' and 'transcribe' in order:
            # فيديو طويل → Claude يرشّح أفضل المقاطع ويعطيها درجة، والمستخدم يختار
            set_status(name, 'plan', 'run', 'Claude يدوّر أقوى المقاطع…')
            run_claude(name, clips_task(name))
            n = len(rj(p / 'clips.json', []))
            if not n: raise Fail('Claude ما لقى مقاطع (clips.json)')
            bb = rj(p / 'brief.json', {})
            if bb.get('picker') == 'claude':
                top = [c['id'] for c in rj(p / 'clips.json', [])[:int(bb.get('count') or 5)]]
                log(name, f'✅ لقيت {n} مقاطع — Claude اختار أقوى {len(top)} وبدأ يصنعها')
                set_status(name, 'done', 'ok', f'Claude اختار {len(top)} مقاطع ✂️')
                make_clips(name, top)
            else:
                log(name, f'✅ لقيت {n} مقاطع — اختر اللي تبيها')
                set_status(name, 'done', 'ok', 'اختر المقاطع اللي تبيها ✂️')
            return
        if 'cut' in order:
            set_status(name, 'cut', 'run', 'أقص السكتات…')
            if not (p / 'edit.json').exists(): wj(p / 'edit.json', {})
            guarded(S.cut, name)
            c = rj(p / 'caps.json', {}); log(name, f'✅ القص خلص: صار الفيديو {c.get("total", 0):.1f} ثانية')
        if 'plan' in order and rj(p / 'brief.json', {}).get('editor') == 'self':
            b0 = rj(p / 'brief.json', {})
            if not (p / 'timeline.json').exists():
                st0 = b0.get('style', 'editorial')
                wj(p / 'timeline.json', {'title': b0.get('title') or name, 'style': 'editorial' if st0 == 'editorial' else 'gold', 'palette': st0})
            log(name, '✂️ وضع «أمنتجه بنفسي»: قصّيت السكتات وركّبت الكابشن — كمّل التعديل من الاستوديو')
            order = [k for k in order if k != 'plan']
        if 'plan' in order:
            set_status(name, 'plan', 'run', 'Claude يخطط المونتاج…')
            log(name, 'سلّمت الخطة لـ Claude — تقدر تتابع رسايله هنا')
            run_claude(name, plan_task(name))
            if not (p / 'timeline.json').exists():
                raise Fail('Claude ما كتب خطة المونتاج (timeline.json)')
            log(name, '✅ الخطة جاهزة')
        if 'preview' in order:
            set_status(name, 'preview', 'run', 'أطلّع لقطات المعاينة…')
            tot = rj(p / 'caps.json', {}).get('total', 10)
            guarded(S.preview, name, [f'{tot * k:.1f}' for k in (.08, .3, .55, .8, .97)])
            log(name, '✅ المعاينة جاهزة')
        if 'render' in order:
            set_status(name, 'render', 'run', 'أصدّر الفيديو (أطول خطوة)…')
            guarded(S.render, name)
            extra_aspects(name)
            log(name, '✅ الفيديو جاهز للتحميل')
        (p / '.dirty_cut').unlink(missing_ok=True)
        set_status(name, 'done', 'ok', 'جاهز 🎬')
    except Exception as e:
        msg = str(e) if isinstance(e, (Fail, RuntimeError)) else 'صار خطأ غير متوقع'
        log(name, '❌ ' + msg, 'error')
        log(name, traceback.format_exc()[-600:], 'debug')
        set_status(name, None, 'error', msg, error=msg)
    finally:
        with LOCK:
            JOBS.pop(name, None)


ASPECTS = {'4x5': (1080, 1350, 'إنستقرام 4×5'), '1x1': (1080, 1080, 'مربع 1×1')}


def extra_aspects(name):
    """نسخ بمقاسات ثانية من النسخة الأساسية (قص من المنتصف — الكابشن عند y≈1390 يبقى داخل الإطار)."""
    p = pdir(name)
    out = p / 'out'
    main = next(iter(sorted(out.glob('*تيك توك*.mp4'))), None)
    for k in rj(p / 'brief.json', {}).get('aspects', []):
        if k not in ASPECTS or not main: continue
        w, h, lb = ASPECTS[k]
        y = min(1920 - h, max(0, 1390 + 110 - h + 60))   # الإطار ينزل لين يشمل الكابشن
        vf = f'crop={w}:{h}:0:{y}'
        if h <= 1080:   # المربع يقص كثير → الفيديو كامل بالنص وخلفه نسخة مغبّشة
            vf = (f'split[a][b];[a]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},boxblur=30:2,eq=brightness=-0.12[bg];'
                  f'[b]scale=-2:{h}[fg];[bg][fg]overlay=(W-w)/2:0')
        S.ff('-i', main, '-vf', vf, '-c:v', 'libx264', '-crf', '17', '-preset', 'medium', '-pix_fmt', 'yuv420p',
             '-c:a', 'copy', '-movflags', '+faststart', out / main.name.replace('تيك توك وريلز', lb))
        log(name, f'✅ نسخة {lb}')


def clips_task(name, again=False):
    b = rj(pdir(name) / 'brief.json', {})
    n = int(b.get('count') or 5)
    lo, hi = (b.get('dur') or '20-60').split('-')
    old = rj(pdir(name) / 'clips.json', []) if again else []
    return ('هذا فيديو طويل (بودكاست/بث/شرح). المطلوب: رشّح أقوى ' + str(n) + ' مقاطع قصيرة تصلح تيك توك/ريلز (ورشّح ' + str(n + 2) + ' عشان يكون فيه خيار).\n'
            '١) اقرأ words.json (كلمات + توقيتات بالثواني من الفيديو الأصلي src.mp4).\n'
            f'٢) كل مقطع {lo}-{hi} ثانية، يبدأ بجملة قوية (هوك) وينتهي بفكرة مكتملة — لا تقطع بنص جملة.\n'
            + ('**مقاطع جديدة غير هذي** (لا تكررها ولا تتداخل معها): ' + json.dumps([[c['a'], c['b']] for c in old]) + '\n' if old else '') +
            'لكل مقطع "tags": 2-3 وسوم قصيرة من: «يبدأ بسؤال»، «فيها رقم»، «فيها قصة»، «حماس»، «كلها نصيحة»، «سريع وحماسي».\n'
            '٣) اكتب clips.json بمجلد المشروع: [{"id":1,"a":ثانية_البداية,"b":ثانية_النهاية,"score":0-100,'
            '"title":"عنوان قصير جذاب","hook":"أول جملة","why":"ليش بينتشر بسطر","tags":["…"]}] مرتبة من الأعلى درجة.\n'
            'الدرجة = قوة الهوك + وضوح الفكرة + قابلية المشاركة. كن صارم بالدرجات. لا تسوي أي شي ثاني.')


def pack_task(name):
    return ('اكتب باقة نشر لهذا الفيديو بالعربي (لهجة سعودية) من words.json و brief.json، واحفظها publish.json:\n'
            '{"tiktok":"وصف تيك توك/ريلز","tweet":"تغريدة X","reply":"رد على التغريدة فيه الرابط","telegram":"رسالة قروب التليقرام"}\n'
            'القواعد: وصف تيك توك/إنستقرام **بدون أي روابط** (قل «الرابط في البايو»، والتليقرام بالاسم فقط)، هوك بأول سطر، 3-5 هاشتاقات.\n'
            'التغريدة بدون رابط، والرابط يكون في reply. رسالة التليقرام قصيرة وحماسية. نص عادي بدون علامات ``` أو ماركداون. لا تسوي أي شي ثاني.')


def claude_job(name, msg, task, after=None):
    """يشغّل Claude بالخلفية على المشروع ثم (اختياري) يكمّل خطوة."""
    def job():
        try:
            set_status(name, 'plan', 'run', msg)
            run_claude(name, task)
        except Exception as e:
            log(name, '❌ ' + str(e), 'error'); set_status(name, None, 'error', str(e), error=str(e))
            with LOCK: JOBS.pop(name, None)
            return
        with LOCK: JOBS.pop(name, None)
        if after: after()
        else: set_status(name, 'done', 'ok', 'جاهز 🎬')
    with LOCK:
        if name in JOBS: return False
        JOBS[name] = True
    threading.Thread(target=job, daemon=True).start()
    return True


def make_clips(name, ids):
    """يقص المقاطع المختارة لمشاريع جديدة ويشغّلها ورا بعض."""
    p = pdir(name)
    clips = {c['id']: c for c in rj(p / 'clips.json', [])}
    brief = dict(rj(p / 'brief.json', {}), mode='short')
    made = []
    for i in ids:
        c = clips.get(i)
        if not c: continue
        nm = re.sub(r'[^\w؀-ۿ-]+', '-', f"{name}-{c.get('title') or i}").strip('-')[:50]
        base, k = nm, 2
        while (PROJ / nm).exists(): nm = f'{base}-{k}'; k += 1
        (PROJ / nm / 'inputs').mkdir(parents=True)
        S.ff('-ss', f"{float(c['a']):.2f}", '-to', f"{float(c['b']):.2f}", '-i', p / 'src.mp4', '-c:v', 'libx264', '-crf', '14',
             '-preset', 'fast', '-c:a', 'aac', '-b:a', '256k', PROJ / nm / 'inputs' / '00_clip.mp4')
        wj(PROJ / nm / 'brief.json', dict(brief, title=c.get('title') or nm))
        set_status(nm, 'upload', 'run', 'بالدور…'); log(nm, f'مقطع من «{name}» ({c["a"]:.0f}–{c["b"]:.0f} ث) — درجة {c.get("score")}')
        made.append(nm)

    def runner():
        for nm in made:
            TLS.name = nm
            try:
                build_source(nm)
            except BaseException as e:
                set_status(nm, None, 'error', str(e), error=str(e)); continue
            with LOCK: JOBS[nm] = True
            pipeline(nm, 'transcribe')
    threading.Thread(target=runner, daemon=True).start()
    return made


# ───────────────────────── إعلان من رابط ─────────────────────────
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36',
      'Accept-Language': 'ar,en;q=0.8'}


def fetch(url, limit=4_000_000):
    import urllib.request
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        return r.read(limit), r.headers.get_content_charset() or 'utf-8'


def read_product(name, url):
    """يقرأ صفحة المنتج: الاسم والوصف والسعر والصور → product.json + assets/"""
    import html as H
    p = pdir(name)
    raw, cs = fetch(url)
    s = raw.decode(cs, 'replace')
    def meta(k):
        return (re.search(rf'<meta[^>]+(?:property|name)=["\']{k}["\'][^>]+content=["\']([^"\']+)', s, re.I) or
                re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{k}["\']', s, re.I))
    g = lambda m: H.unescape(m.group(1)).strip() if m else ''
    info = {'url': url, 'title': g(meta('og:title')) or g(re.search(r'<title[^>]*>([^<]+)', s, re.I)),
            'description': g(meta('og:description')) or g(meta('description')), 'price': g(meta('product:price:amount')),
            'currency': g(meta('product:price:currency')), 'images': []}
    imgs = [g(meta('og:image'))]
    for blk in re.findall(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', s, re.S | re.I):   # بيانات المنتج المنظمة
        try:
            d = json.loads(blk.strip())
        except Exception:
            continue
        for o in (d if isinstance(d, list) else d.get('@graph', [d])):
            if not isinstance(o, dict) or 'Product' not in str(o.get('@type')): continue
            info['title'] = o.get('name') or info['title']
            info['description'] = H.unescape(re.sub('<[^>]+>', ' ', str(o.get('description') or ''))).strip() or info['description']
            off = o.get('offers') or {}
            off = off[0] if isinstance(off, list) and off else off
            if isinstance(off, dict):
                info['price'] = str(off.get('price') or off.get('lowPrice') or info['price'])
                info['currency'] = off.get('priceCurrency') or info['currency']
            im = o.get('image') or []
            imgs += [x if isinstance(x, str) else (x or {}).get('url', '') for x in (im if isinstance(im, list) else [im])]
    imgs += re.findall(r'<img[^>]+(?:data-src|src)=["\']([^"\']+\.(?:jpe?g|png|webp)[^"\']*)', s, re.I)
    body = re.sub(r'<(script|style|noscript)[\s\S]*?</\1>', ' ', s, flags=re.I)
    info['text'] = re.sub(r'\s+', ' ', H.unescape(re.sub(r'<[^>]+>', ' ', body)))[:4000]
    (p / 'assets').mkdir(exist_ok=True)
    seen = set()
    for u in imgs:
        if len(info['images']) >= 6: break
        u = urllib.parse.urljoin(url, (u or '').strip())
        if not u.startswith('http') or u in seen or re.search(r'logo|icon|sprite|avatar|payment|badge', u, re.I): continue
        seen.add(u)
        try:
            data, _ = fetch(u, 8_000_000)
            if len(data) < 15_000: continue          # أيقونات وصور صغيرة
            raw_f = p / 'assets' / f'_raw{len(info["images"])}'
            raw_f.write_bytes(data)
            out = p / 'assets' / f'product_{len(info["images"]) + 1}.jpg'
            S.ff('-i', raw_f, '-vf', 'scale=1080:-2', '-q:v', '3', out); raw_f.unlink()
            info['images'].append(f'assets/{out.name}')
        except BaseException:
            continue
    wj(p / 'product.json', info)
    return info


def scripts_task(name):
    return ('هذا منتج المستخدم (product.json — اقرأه، وشوف صوره في assets/). المطلوب: 3 سكربتات إعلان قصيرة يصوّرها المستخدم بنفسه.\n'
            'الزوايا: ١) مشكلة ← حل  ٢) قصة شخصية  ٣) صدمة بالأرقام/النتيجة.\n'
            'كل سكربت: لهجة سعودية طبيعية، 25-40 ثانية قراءة (70-110 كلمة)، أول جملة هوك يوقف التمرير، يذكر السعر إذا موجود، ويختم بدعوة «الرابط في البايو». لا تخترع ولا تقرّب أي رقم أو ادعاء — استخدم أرقام الصفحة حرفياً.\n'
            'اكتب scripts.json بمجلد المشروع: [{"id":1,"angle":"مشكلة ← حل","score":0-100,"hook":"أول جملة","script":"النص كامل جمل قصيرة كل جملة بسطر",'
            '"shots":["وش يصوّر/يعرض في كل جزء"]}] مرتبة من الأعلى درجة. كن صارم بالدرجة (قوة الهوك + الوضوح + الإقناع). لا تسوي أي شي ثاني.')


def timeline_assets(name):
    """صور التايم لاين: موجة الصوت وشريط لقطات من main.mp4 (تتجدد إذا تغيّر)."""
    p = pdir(name); src = p / 'main.mp4'
    if not src.exists(): return {}
    out = {}
    tot = rj(p / 'caps.json', {}).get('total') or S.probe_dur(src) or 1
    aud = p / 'voice.wav' if (p / 'voice.wav').exists() else src
    for f, inp, args in (('wave.png', aud, ['-filter_complex', 'aformat=channel_layouts=mono,showwavespic=s=2000x120:colors=#7bd88f:scale=sqrt', '-frames:v', '1']),
                         ('strip.jpg', src, ['-vf', f'fps=20/{tot:.3f},scale=96:-2,tile=20x1', '-frames:v', '1', '-q:v', '5'])):
        t = p / f
        if not t.exists() or t.stat().st_mtime < src.stat().st_mtime:
            try:
                S.ff('-i', inp, *args, t)
            except BaseException:
                continue
        out[f.split('.')[0]] = f'{f}?v={int(t.stat().st_mtime)}'
    return out


def cut_range(name, a, b):
    """يحذف جزء من الفيديو النهائي (ثواني النهائي) ← مدى بالمصدر بـ edit.json + يزحزح عناصر المونتاج."""
    p = pdir(name); caps = rj(p / 'caps.json', {})
    keep, acc, drops = caps.get('keep') or [], 0.0, []
    for s0, e0 in keep:                       # تحويل وقت النهائي ← وقت المصدر
        ln = e0 - s0
        lo, hi = max(a, acc), min(b, acc + ln)
        if hi > lo: drops.append([round(s0 + lo - acc, 3), round(s0 + hi - acc, 3)])
        acc += ln
    if not drops: raise Fail('ما لقيت هالجزء')
    snapshot(name)
    e = rj(p / 'edit.json', {}); e['drop'] = (e.get('drop') or []) + drops; wj(p / 'edit.json', e)
    d = b - a
    def mv(t):
        return t if t <= a else (a if t < b else round(t - d, 3))
    tl = rj(p / 'timeline.json', {})
    for k in ('stickers', 'hero', 'broll', 'strike', 'chapters', 'fix'):
        keepers = []
        for el in tl.get(k, []):
            for f in ('at', 'until', 'a', 'b'):
                if f in el: el[f] = mv(el[f])
            st, en = el.get('at', el.get('a', 0)), el.get('until', el.get('b', el.get('at', el.get('a', 0)) + 1))
            if en - st > 0.2 or k == 'chapters': keepers.append(el)
        tl[k] = keepers
    if tl.get('cuts'): tl['cuts'] = sorted({mv(t) for t in tl['cuts']})
    wj(p / 'timeline.json', tl)
    (p / '.dirty_cut').touch()
    return d


def preview_tl(name):
    """الخطة للمعاينة الحية: مثل sync بالرندر (الكلمات + المدة) بدون نسخ ملفات."""
    p = pdir(name)
    tl = rj(p / 'timeline.json', {}) or {}
    caps = rj(p / 'caps.json', {})
    tl['main_end'] = caps.get('total', 0)
    tl['total'] = caps.get('total', 0) + (tl.get('endCard') or {}).get('dur', 0)
    tl['words'] = caps.get('words', [])
    if (p / 'main.mp4').exists() and not (p / 'last.png').exists():
        try:
            S.ff('-sseof', '-0.1', '-i', p / 'main.mp4', '-frames:v', '1', p / 'last.png')
        except BaseException:
            pass
    return tl


def plan_task(name):
    b = rj(pdir(name) / 'brief.json', {})
    return (
        'خطّط مونتاج هذا المشروع حسب الدليل (AGENT.md). حط "palette" بالخطة = قيمة style من إجابات المستخدم، واستخدم الرسومات الجديدة (items) لما يناسب الكلام.\n'
        f'إجابات المستخدم من صفحة الأسئلة: {json.dumps(b, ensure_ascii=False)}\n'
        '١) اقرأ words.json و caps.json.\n'
        '٢) اكتب edit.json (تصحيح الكلمات والكلمات المميزة وحذف الإعادات) ثم شغّل cut بالمحرّك.\n'
        '٣) اكتب timeline.json على توقيتات caps.json الجديدة.\n'
        '٤) شغّل preview واقرأ preview.jpg بنفسك وأصلح أي خلل.\n'
        'لا ترندر — السيرفر يرندر بعدك.'
        + ('\n\nهذا **إعلان منتج** (product.json): استخدم صور المنتج من assets/ كـ broll ("file":"assets/product_1.jpg") '
           'على الكلمات اللي تتكلم عنه، حط ملصق السعر لما يذكره، وخاتمة endCard فيها اسم المنتج وزر «اطلب الحين — الرابط في البايو».'
           if (pdir(name) / 'product.json').exists() else '')
    )


def start_job(name, from_stage, skip=()):
    with LOCK:
        if name in JOBS:
            return False
        JOBS[name] = True
    threading.Thread(target=pipeline, args=(name, from_stage, skip), daemon=True).start()
    return True


def build_source(name):
    """يجمع المقاطع المرفوعة بالترتيب في src.mp4 + صورة مصغّرة."""
    p = pdir(name)
    ins = sorted((p / 'inputs').glob('*'))
    if not ins:
        raise Fail('ما رفعت أي مقطع')
    if rj(p / 'brief.json', {}).get('mode') == 'clips':
        # فيديو طويل: ناخذ أطول ملف ولا نحوّله كامل — نفرّغه كما هو، ونحوّل بس المقاطع المختارة (ثواني بدل ساعات)
        longest = max(ins, key=lambda f: S.probe_dur(f))
        if len(ins) > 1: log(name, f'فيديو طويل: استخدمت «{longest.name[3:]}» بس (الأطول)')
        S.ff('-i', longest, '-map', '0:v:0', '-map', '0:a:0', '-c', 'copy', '-movflags', '+faststart', p / 'src.mp4')
    else:
        S.new(name, [str(f) for f in ins], fit=rj(p / 'brief.json', {}).get('frame') == 'fit')
    S.ff('-ss', '1', '-i', p / 'src.mp4', '-frames:v', '1', '-vf', 'scale=360:-2', p / 'thumb.jpg')


# ───────────────────────── HTTP ─────────────────────────
MIME = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
        '.json': 'application/json; charset=utf-8', '.jpg': 'image/jpeg', '.png': 'image/png', '.mp4': 'video/mp4',
        '.svg': 'image/svg+xml', '.ttf': 'font/ttf', '.woff2': 'font/woff2', '.mov': 'video/quicktime'}


class H(BaseHTTPRequestHandler):
    server_version = 'AsrarStudio/0.2'

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code); self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(b))); self.send_header('Cache-Control', 'no-store'); self.end_headers()
        self.wfile.write(b)

    def body_json(self):
        n = int(self.headers.get('Content-Length') or 0)
        return json.loads(self.rfile.read(n) or b'{}') if n else {}

    def send_file(self, f):
        if not f.exists() or not f.is_file():
            return self.send_json({'error': 'not found'}, 404)
        size = f.stat().st_size
        ctype = MIME.get(f.suffix.lower(), 'application/octet-stream')
        rng = self.headers.get('Range')
        start, end = 0, size - 1
        if rng and rng.startswith('bytes='):
            a, _, b = rng[6:].partition('-')
            start = int(a) if a else 0
            end = int(b) if b else size - 1
            self.send_response(206); self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        else:
            self.send_response(200)
        self.send_header('Content-Type', ctype); self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Content-Length', str(end - start + 1)); self.send_header('Cache-Control', 'no-store')
        if f.suffix.lower() == '.mp4' and 'download' in (self.path or ''):
            self.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + urllib.parse.quote(f.name))
        self.end_headers()
        with open(f, 'rb') as fh:
            fh.seek(start); left = end - start + 1
            while left > 0:
                chunk = fh.read(min(1 << 20, left))
                if not chunk: break
                try:
                    self.wfile.write(chunk)
                except (ConnectionResetError, BrokenPipeError):
                    break
                left -= len(chunk)

    # ── routes ──
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); path = urllib.parse.unquote(u.path); q = urllib.parse.parse_qs(u.query)
        try:
            if path in ('/', '/index.html') or path.startswith('/p/'):
                return self.send_file(WEB / 'index.html')
            if path == '/player.js':
                try:
                    S.build_player()
                except BaseException:
                    pass
                return self.send_file(S.WORK / 'player.js')
            if path.startswith('/fonts/'):
                return self.send_file(ENGINE / 'template' / 'public' / 'fonts' / Path(path).name)
            if path.startswith('/web/'):
                return self.send_file(WEB / path[5:])
            if path == '/api/ping':
                return self.send_json({'ok': True, 'app': 'asrar-studio', 'claude': bool(find_claude()), 'loggedIn': claude_logged_in(), 'invited': True})
            if path == '/api/projects':
                PROJ.mkdir(parents=True, exist_ok=True)
                items = [project_info(d.name) for d in PROJ.iterdir() if d.is_dir() and not d.name.startswith('.')]
                return self.send_json(sorted(items, key=lambda x: -x['mtime']))
            m = re.match(r'^/api/projects/([^/]+)(?:/(\w+))?$', path)
            if m:
                name, what = m.group(1), m.group(2)
                if not pdir(name).exists(): return self.send_json({'error': 'no project'}, 404)
                if what is None: return self.send_json(project_info(name))
                if what == 'log': return self.send_json(read_log(name, float((q.get('since') or ['0'])[0])))
                if what == 'stages': return self.send_json(STAGES)
                if what == 'pvtl':
                    return self.send_json(preview_tl(name))
                if what == 'doc':
                    p = pdir(name)
                    return self.send_json({'caps': rj(p / 'caps.json', {}), 'timeline': rj(p / 'timeline.json', {}),
                                           'notes': rj(p / 'notes.json', []), 'edit': rj(p / 'edit.json', {}),
                                           'clips': rj(p / 'clips.json', []), 'publish': rj(p / 'publish.json', None),
                                           'tl': timeline_assets(name),
                                           'dirty':(p / '.dirty_cut').exists() or (p / '.dirty_tl').exists()})
            m = re.match(r'^/pvabs/([^/]+)$', path)
            if m:   # لقطات بمسار كامل بالمعاينة — بس الملفات المذكورة بخطة المشروع
                want = (q.get('p') or [''])[0]
                tl = rj(pdir(m.group(1)) / 'timeline.json', {}) or {}
                if want not in [b.get('file') for b in tl.get('broll', [])]: return self.send_json({'error': 'not allowed'}, 403)
                return self.send_file(Path(want))
            m = re.match(r'^/files/([^/]+)/(.+)$', path)
            if m:
                f = (pdir(m.group(1)) / m.group(2)).resolve()
                if pdir(m.group(1)) not in f.parents: return self.send_json({'error': 'bad path'}, 400)
                return self.send_file(f)
            self.send_json({'error': 'not found'}, 404)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)

    def do_PUT(self):
        """رفع مقطع: PUT /api/projects/<name>/upload?file=<اسم>  (الجسم = الملف)"""
        u = urllib.parse.urlparse(self.path); path = urllib.parse.unquote(u.path); q = urllib.parse.parse_qs(u.query)
        m = re.match(r'^/api/projects/([^/]+)/upload$', path)
        if not m: return self.send_json({'error': 'not found'}, 404)
        name = m.group(1)
        fname = re.sub(r'[\\/:*?"<>|]', '_', (q.get('file') or ['clip.mp4'])[0])
        idx = int((q.get('i') or ['0'])[0])
        d = pdir(name) / 'inputs'; d.mkdir(parents=True, exist_ok=True)
        left = int(self.headers.get('Content-Length') or 0)
        with open(d / f'{idx:02d}_{fname}', 'wb') as fh:
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk: break
                fh.write(chunk); left -= len(chunk)
        self.send_json({'ok': True})

    def do_POST(self):
        path = urllib.parse.unquote(urllib.parse.urlparse(self.path).path)
        try:
            if path == '/api/claude/login':
                try:
                    open_login(); return self.send_json({'ok': True})
                except Exception as e:
                    return self.send_json({'error': str(e)}, 400)
            if path == '/api/invite':
                ok = check_invite(self.body_json().get('code'))
                return self.send_json({'ok': ok} if ok else {'error': 'الكود غير صحيح'}, 200 if ok else 403)
            if not invited():
                return self.send_json({'error': 'فعّل الاستوديو بكود الدعوة أول'}, 403)
            if path == '/api/projects':
                b = self.body_json()
                name = re.sub(r'[^\w؀-ۿ-]+', '-', (b.get('name') or 'مشروع').strip()).strip('-')[:40] or 'مشروع'
                base, k = name, 2
                while (PROJ / name).exists():
                    name = f'{base}-{k}'; k += 1
                (PROJ / name / 'inputs').mkdir(parents=True)
                set_status(name, 'upload', 'idle', 'ارفع مقاطعك')
                log(name, f'مشروع جديد: {name}')
                return self.send_json({'name': name})
            m = re.match(r'^/api/projects/([^/]+)/(\w+)$', path)
            if not m: return self.send_json({'error': 'not found'}, 404)
            name, act = m.group(1), m.group(2)
            p = pdir(name)
            if act == 'brief':
                wj(p / 'brief.json', self.body_json()); log(name, 'انحفظت إجاباتك'); return self.send_json({'ok': True})
            if act == 'start':
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                b = self.body_json()
                frm = b.get('from', 'transcribe')
                if frm == 'transcribe':
                    if not list((p / 'inputs').glob('*')): return self.send_json({'error': 'ارفع مقطع أو حط رابط أول'}, 400)
                    with LOCK:
                        if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                        JOBS[name] = True
                    set_status(name, 'transcribe', 'run', 'أجهّز المقاطع…')
                    def prep():
                        TLS.name = name
                        try:
                            build_source(name)
                        except BaseException as e:
                            msg = str(e) if isinstance(e, Fail) else 'ما قدرت أجهّز المقاطع — تأكد إنها فيديو سليم'
                            log(name, '❌ ' + msg, 'error'); set_status(name, None, 'error', msg, error=msg)
                            with LOCK: JOBS.pop(name, None)
                            return
                        log(name, '✅ المقاطع جاهزة')
                        pipeline(name, 'transcribe')
                    threading.Thread(target=prep, daemon=True).start()
                    return self.send_json({'ok': True})
                start_job(name, frm)
                return self.send_json({'ok': True})
            if act == 'ask':
                """طلب تعديل حر من المستخدم → Claude ينفّذ ثم معاينة ورندر."""
                text = (self.body_json().get('text') or '').strip()
                if not text: return self.send_json({'error': 'اكتب طلبك'}, 400)
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                log(name, text, 'user')
                def job():
                    try:
                        set_status(name, 'plan', 'run', 'Claude ينفّذ طلبك…')
                        run_claude(name, 'طلب تعديل من المستخدم على المونتاج الحالي:\n' + text +
                                   '\nعدّل edit.json/timeline.json حسب الطلب فقط، وإذا عدّلت edit.json شغّل cut. ثم preview وتأكد. لا ترندر.')
                    except Exception as e:
                        log(name, '❌ ' + str(e), 'error'); set_status(name, None, 'error', str(e), error=str(e))
                        with LOCK: JOBS.pop(name, None)
                        return
                    with LOCK: JOBS.pop(name, None)
                    start_job(name, 'preview')
                with LOCK:
                    JOBS[name] = True
                threading.Thread(target=job, daemon=True).start()
                return self.send_json({'ok': True})
            if act == 'note':      # ملاحظة على ثانية
                b = self.body_json(); notes = rj(p / 'notes.json', [])
                if b.get('del'):
                    notes = [n for n in notes if n['id'] != b['del']]
                else:
                    if not (b.get('text') or '').strip(): return self.send_json({'error': 'اكتب الملاحظة'}, 400)
                    notes.append({'id': int(time.time() * 1000), 't': round(float(b.get('t') or 0), 2), 'text': b['text'].strip(), 'done': False})
                wj(p / 'notes.json', sorted(notes, key=lambda n: n['t'])); return self.send_json({'ok': True})
            if act == 'fix':       # تصحيح كلمة بالنص
                b = self.body_json(); snapshot(name)
                e = rj(p / 'edit.json', {}); e.setdefault('fixes', {})[b['from']] = b['to']
                if b.get('hot') is not None:
                    hot = set(e.get('hot', [])); (hot.add if b['hot'] else hot.discard)(b['to']); e['hot'] = sorted(hot)
                wj(p / 'edit.json', e); (p / '.dirty_cut').touch(); return self.send_json({'ok': True})
            if act == 'timeline':  # حفظ الخطة من المحرر (حفظ تلقائي)
                b = self.body_json(); quiet = b.pop('_quiet', False)
                if not quiet: snapshot(name)
                for k in ('words', 'main_end', 'total'): b.pop(k, None)
                wj(p / 'timeline.json', b); (p / '.dirty_tl').touch()
                return self.send_json({'ok': True})
            if act == 'rebuild':   # طبّق التعديلات اليدوية وأعد التصدير (بدون Claude)
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                (p / '.dirty_tl').unlink(missing_ok=True)
                start_job(name, 'cut' if (p / '.dirty_cut').exists() else 'preview', skip=('plan',))
                log(name, 'أطبّق تعديلاتك وأعيد التصدير…'); return self.send_json({'ok': True})
            if act == 'notes_run':  # Claude ينفّذ الملاحظات المعلّقة
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                notes = rj(p / 'notes.json', []); todo = [n for n in notes if not n['done']]
                if not todo: return self.send_json({'error': 'ما فيه ملاحظات جديدة'}, 400)
                lines = '\n'.join(f"- عند الثانية {n['t']:.1f}: {n['text']}" for n in todo)
                log(name, f'سلّمت {len(todo)} ملاحظات لـ Claude', 'user')
                def job():
                    try:
                        set_status(name, 'plan', 'run', 'Claude ينفّذ ملاحظاتك…')
                        run_claude(name, 'ملاحظات المستخدم على الفيديو الحالي (التوقيت بثواني الفيديو النهائي = توقيتات caps.json):\n' + lines +
                                   '\nنفّذ كل ملاحظة بتعديل edit.json/timeline.json. إذا عدّلت edit.json شغّل cut وعدّل توقيتات timeline.json لتطابق caps.json الجديد. ثم preview وتأكد. لا ترندر.')
                        ids = {n['id'] for n in todo}; cur = rj(p / 'notes.json', [])
                        for n in cur:
                            if n['id'] in ids: n['done'] = True
                        wj(p / 'notes.json', cur)
                    except Exception as e:
                        log(name, '❌ ' + str(e), 'error'); set_status(name, None, 'error', str(e), error=str(e))
                        with LOCK: JOBS.pop(name, None)
                        return
                    with LOCK: JOBS.pop(name, None)
                    start_job(name, 'preview')
                with LOCK: JOBS[name] = True
                threading.Thread(target=job, daemon=True).start()
                return self.send_json({'ok': True})
            if act == 'pack':      # باقة النشر
                if not claude_job(name, 'Claude يكتب باقة النشر…', pack_task(name)):
                    return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                log(name, 'طلبت باقة النشر', 'user'); return self.send_json({'ok': True})
            if act == 'grab':      # تنزيل من رابط يوتيوب (أو أي موقع يدعمه yt-dlp)
                url = (self.body_json().get('url') or '').strip()
                if not re.match(r'^https?://', url): return self.send_json({'error': 'حط رابط صحيح'}, 400)
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                with LOCK: JOBS[name] = True
                def dl():
                    try:
                        set_status(name, 'upload', 'run', 'أنزّل الفيديو من الرابط…'); log(name, 'أنزّل: ' + url)
                        (p / 'inputs').mkdir(exist_ok=True)
                        cmd = [sys.executable, '-m', 'yt_dlp', '--js-runtimes', 'node', '-f', 'bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080]/b',
                               '--merge-output-format', 'mp4', '--no-playlist', '--newline', '-o', str(p / 'inputs' / '00_youtube.%(ext)s'), url]
                        kw = {'creationflags': 0x08000000} if os.name == 'nt' else {}
                        pr = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, **kw)
                        last = ''
                        for raw in pr.stdout:
                            ln = raw.decode('utf-8', 'replace').strip()
                            m2 = re.search(r'\[download\]\s+(\d+(?:\.\d)?)%', ln)
                            if m2 and m2.group(1).split('.')[0] != last:
                                last = m2.group(1).split('.')[0]; set_status(name, 'upload', 'run', f'أنزّل الفيديو… {last}%')
                            elif 'ERROR' in ln: log(name, ln[-200:], 'error')
                        pr.wait()
                        if pr.returncode or not list((p / 'inputs').glob('00_youtube.*')):
                            raise Fail('ما قدرت أنزّل الرابط — تأكد إنه عام وشغّال')
                        log(name, '✅ نزل الفيديو'); set_status(name, 'upload', 'idle', 'نزل الفيديو — كمّل الأسئلة واضغط ابدأ')
                    except Exception as e:
                        msg = str(e) if isinstance(e, Fail) else 'فشل التنزيل'
                        log(name, '❌ ' + msg, 'error'); set_status(name, 'upload', 'idle', msg, error=msg)
                    finally:
                        with LOCK: JOBS.pop(name, None)
                threading.Thread(target=dl, daemon=True).start()
                return self.send_json({'ok': True})
            if act == 'product':   # إعلان من رابط: قراءة المنتج + 3 سكربتات
                url = (self.body_json().get('url') or '').strip()
                if not re.match(r'^https?://', url): return self.send_json({'error': 'حط رابط المنتج كامل'}, 400)
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                with LOCK: JOBS[name] = True
                def ad():
                    try:
                        set_status(name, 'upload', 'run', 'أقرأ صفحة المنتج…'); log(name, 'أقرأ: ' + url)
                        info = read_product(name, url)
                        log(name, f'✅ المنتج: {info["title"][:60]} · {info["price"]} {info["currency"]} · {len(info["images"])} صور')
                        set_status(name, 'upload', 'run', 'Claude يكتب 3 سكربتات…')
                        run_claude(name, scripts_task(name))
                        if not rj(p / 'scripts.json'): raise Fail('Claude ما كتب السكربتات')
                        log(name, '✅ السكربتات جاهزة — اختر واحد وصوّر')
                        set_status(name, 'upload', 'idle', 'اختر سكربت وصوّر')
                    except Exception as e:
                        msg = str(e) if isinstance(e, (Fail, RuntimeError)) else 'ما قدرت أقرأ الصفحة — جرّب رابط المنتج نفسه'
                        log(name, '❌ ' + msg, 'error'); log(name, traceback.format_exc()[-500:], 'debug')
                        set_status(name, 'upload', 'idle', msg, error=msg)
                    finally:
                        with LOCK: JOBS.pop(name, None)
                threading.Thread(target=ad, daemon=True).start()
                return self.send_json({'ok': True})
            if act == 'annotate':   # رسم على الفيديو + ملاحظة → Claude يشوفه
                import base64
                b = self.body_json(); tt = round(float(b.get('t') or 0), 2)
                d = p / 'annotations'; d.mkdir(exist_ok=True)
                fn = f'mark_{int(time.time())}.png'
                (d / fn).write_bytes(base64.b64decode((b.get('png') or '').split(',')[-1]))
                fr = d / fn.replace('mark_', 'frame_')
                try:
                    S.ff('-ss', f'{tt}', '-i', p / 'main.mp4', '-i', d / fn, '-filter_complex', '[1]scale=1080:1920[m];[0][m]overlay', '-frames:v', '1', fr)
                except BaseException:
                    pass
                notes = rj(p / 'notes.json', [])
                notes.append({'id': int(time.time() * 1000), 't': tt, 'done': False,
                              'text': (b.get('text') or 'شوف الرسم').strip() + f' (الرسم على اللقطة: annotations/{fr.name} — افتحها وشوف وين أأشّر)'})
                wj(p / 'notes.json', sorted(notes, key=lambda n: n['t']))
                return self.send_json({'ok': True})
            if act == 'cut':        # قص يدوي من التايم لاين
                b = self.body_json(); a0, b0 = sorted([float(b.get('a', 0)), float(b.get('b', 0))])
                if b0 - a0 < 0.1: return self.send_json({'error': 'حدد جزء أطول'}, 400)
                if name in JOBS: return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                d = cut_range(name, a0, b0); log(name, f'✂️ حذفت {d:.1f} ثانية ({a0:.1f}–{b0:.1f}) — اضغط «طبّق وأعد التصدير»', 'user')
                return self.send_json({'ok': True, 'removed': d})
            if act == 'clip_adjust':  # ±ثانيتين لبداية/نهاية مقطع مرشّح
                b = self.body_json(); cl = rj(p / 'clips.json', [])
                for c in cl:
                    if c['id'] == int(b['id']):
                        c['a'] = round(max(0, c['a'] + float(b.get('da', 0))), 2)
                        c['b'] = round(max(c['a'] + 3, c['b'] + float(b.get('db', 0))), 2)
                wj(p / 'clips.json', cl); return self.send_json({'ok': True})
            if act == 'rescan':     # «هات غيرها»
                if not claude_job(name, 'Claude يدوّر مقاطع ثانية…', clips_task(name, again=True)):
                    return self.send_json({'error': 'المشروع شغّال الحين'}, 409)
                return self.send_json({'ok': True})
            if act == 'clips_make':
                ids = [int(i) for i in self.body_json().get('ids', [])]
                if not ids: return self.send_json({'error': 'اختر مقطع واحد على الأقل'}, 400)
                made = make_clips(name, ids); log(name, f'✂️ بديت أصنع {len(made)} مقاطع')
                return self.send_json({'made': made})
            if act == 'undo':
                snaps = sorted((p / '.snapshots').glob('*')) if (p / '.snapshots').exists() else []
                if not snaps: return self.send_json({'error': 'ما فيه نسخة احتياطية'}, 400)
                last = snaps[-1]
                for f in last.iterdir(): shutil.copy(f, p / f.name)
                shutil.rmtree(last); log(name, '↩️ رجّعت آخر نسخة احتياطية')
                return self.send_json({'ok': True})
            if act == 'open':
                target = p / 'out' if (p / 'out').exists() else p
                if os.name == 'nt': os.startfile(target)  # noqa
                else: subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(target)])
                return self.send_json({'ok': True})
            self.send_json({'error': 'unknown action'}, 404)
        except Exception as e:
            self.send_json({'error': str(e)}, 500)


def serve(open_browser=True):
    PROJ.mkdir(parents=True, exist_ok=True)
    try:
        httpd = ThreadingHTTPServer(('127.0.0.1', PORT), H)
    except OSError:
        print(f'الاستوديو شغّال أصلاً: http://127.0.0.1:{PORT}')
        if open_browser: webbrowser.open(f'http://127.0.0.1:{PORT}')
        return
    url = f'http://127.0.0.1:{PORT}'
    print(f'🎬 أسرار ستوديو شغّال: {url}  (سكّر النافذة أو Ctrl+C للإيقاف)', flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    httpd.serve_forever()


if __name__ == '__main__':
    serve(open_browser='--no-open' not in sys.argv)
