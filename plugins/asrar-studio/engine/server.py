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


def set_status(name, stage=None, state=None, msg=None, error=None):
    st = status(name)
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
            'running': name in JOBS}


# ───────────────────────── Claude (headless) ─────────────────────────
def find_claude():
    for c in ('claude', 'claude.cmd', 'claude.exe'):
        w = shutil.which(c)
        if w: return w
    for c in (Path.home() / '.local' / 'bin' / 'claude.exe', Path.home() / '.local' / 'bin' / 'claude',
              Path(os.environ.get('APPDATA', '')) / 'npm' / 'claude.cmd'):
        if c.exists(): return str(c)
    return None


def run_claude(name, task):
    """يشغّل Claude Code بدون واجهة داخل مجلد المشروع ويبث رسائله للسجل."""
    exe = find_claude()
    if not exe:
        raise RuntimeError('ما لقيت Claude Code على جهازك')
    p = pdir(name)
    snap = p / '.snapshots' / time.strftime('%Y%m%d-%H%M%S')    # نسخة احتياطية قبل أي تعديل
    snap.mkdir(parents=True, exist_ok=True)
    for f in ('edit.json', 'timeline.json', 'brief.json'):
        if (p / f).exists(): shutil.copy(p / f, snap / f)
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
        raise RuntimeError('Claude ما كمّل: ' + (str((final or {}).get('result', ''))[:200] or ' '.join(tail)[-200:]))


# ───────────────────────── pipeline ─────────────────────────
class Fail(Exception):
    pass


def guarded(fn, *a):
    try:
        fn(*a)
    except SystemExit:
        raise Fail('توقفت خطوة في المحرّك — شوف السجل')


def pipeline(name, from_stage='transcribe'):
    p = pdir(name)
    try:
        order = STAGE_KEYS[STAGE_KEYS.index(from_stage):]
        if 'transcribe' in order:
            set_status(name, 'transcribe', 'run', 'أفرّغ كلامك…'); log(name, 'بدأت التفريغ — أول مرة ينزّل نموذج اللغة (~3 قيقا)')
            guarded(S.transcribe, name)
            log(name, f'✅ التفريغ خلص: {len(rj(p / "words.json", {}).get("words", []))} كلمة')
        if 'cut' in order:
            set_status(name, 'cut', 'run', 'أقص السكتات…')
            if not (p / 'edit.json').exists(): wj(p / 'edit.json', {})
            guarded(S.cut, name)
            c = rj(p / 'caps.json', {}); log(name, f'✅ القص خلص: صار الفيديو {c.get("total", 0):.1f} ثانية')
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
            log(name, '✅ الفيديو جاهز للتحميل')
        set_status(name, 'done', 'ok', 'جاهز 🎬')
    except Exception as e:
        msg = str(e) if isinstance(e, (Fail, RuntimeError)) else 'صار خطأ غير متوقع'
        log(name, '❌ ' + msg, 'error')
        log(name, traceback.format_exc()[-600:], 'debug')
        set_status(name, None, 'error', msg, error=msg)
    finally:
        with LOCK:
            JOBS.pop(name, None)


def plan_task(name):
    b = rj(pdir(name) / 'brief.json', {})
    return (
        'خطّط مونتاج هذا المشروع حسب الدليل (AGENT.md).\n'
        f'إجابات المستخدم من صفحة الأسئلة: {json.dumps(b, ensure_ascii=False)}\n'
        '١) اقرأ words.json و caps.json.\n'
        '٢) اكتب edit.json (تصحيح الكلمات والكلمات المميزة وحذف الإعادات) ثم شغّل cut بالمحرّك.\n'
        '٣) اكتب timeline.json على توقيتات caps.json الجديدة.\n'
        '٤) شغّل preview واقرأ preview.jpg بنفسك وأصلح أي خلل.\n'
        'لا ترندر — السيرفر يرندر بعدك.'
    )


def start_job(name, from_stage):
    with LOCK:
        if name in JOBS:
            return False
        JOBS[name] = True
    threading.Thread(target=pipeline, args=(name, from_stage), daemon=True).start()
    return True


def build_source(name):
    """يجمع المقاطع المرفوعة بالترتيب في src.mp4 + صورة مصغّرة."""
    p = pdir(name)
    ins = sorted((p / 'inputs').glob('*'))
    if not ins:
        raise Fail('ما رفعت أي مقطع')
    S.new(name, [str(f) for f in ins])
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
            if path.startswith('/fonts/'):
                return self.send_file(ENGINE / 'template' / 'public' / 'fonts' / Path(path).name)
            if path.startswith('/web/'):
                return self.send_file(WEB / path[5:])
            if path == '/api/ping':
                return self.send_json({'ok': True, 'app': 'asrar-studio', 'claude': bool(find_claude())})
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
                    set_status(name, 'upload', 'run', 'أجهّز المقاطع…')
                    try:
                        build_source(name)
                    except BaseException as e:
                        set_status(name, None, 'error', str(e), error=str(e)); return self.send_json({'error': str(e)}, 400)
                    log(name, '✅ المقاطع جاهزة')
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
