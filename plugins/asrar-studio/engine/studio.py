#!/usr/bin/env python3
"""أسرار ستوديو — محرّك المونتاج.

الأوامر:
  doctor                         يفحص الأدوات المطلوبة
  new <project> <clip>...        مشروع جديد من مقطع أو أكثر (بالترتيب)
  transcribe <project>           تفريغ بتوقيت كل كلمة → words.json
  cut <project>                  يقص السكتات + يطبّق edit.json → main.mp4 + caps.json
  setup                          يجهّز محرّك الرسم (مرة وحدة، ~500 ميقا)
  preview <project> <t1> <t2>…   لقطات معاينة → preview.jpg
  render <project>               الرندر النهائي + الصوت + نسخ المنصات
  path <project>                 يطبع مسار مجلد المشروع
"""
import json, os, shutil, subprocess, sys, math, re, wave, struct
from pathlib import Path

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8'); sys.stderr.reconfigure(encoding='utf-8')

ENGINE = Path(__file__).resolve().parent
HOME = Path(os.environ.get('ASRAR_STUDIO_HOME', Path.home() / 'Documents' / 'AsrarStudio'))
WORK = HOME / '.engine'          # Remotion workspace (node_modules lives here)
FPS = 30
REMOTION = '4.0.529'


def die(msg):
    print('❌ ' + msg); sys.exit(1)


def run(cmd, **kw):
    r = subprocess.run([str(c) for c in cmd], **kw)
    if r.returncode != 0:
        die('فشل الأمر: ' + ' '.join(map(str, cmd[:3])) + ' …')
    return r


def ff(*args):
    run(['ffmpeg', '-v', 'error', '-y', *args])


def probe_dur(p):
    out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', str(p)],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def proj(name):
    p = HOME / 'projects' / name
    if not p.exists():
        die(f'ما لقيت المشروع: {name}')
    return p


# ───────────────────────── doctor ─────────────────────────
def doctor():
    ok = True
    def chk(label, good, fix):
        nonlocal ok
        print(('✅ ' if good else '❌ ') + label + ('' if good else f'  ← {fix}'))
        ok &= good
    has = lambda b: shutil.which(b) is not None
    chk('ffmpeg', has('ffmpeg') and has('ffprobe'), 'winget install Gyan.FFmpeg  |  brew install ffmpeg')
    node = subprocess.run(['node', '--version'], capture_output=True, text=True).stdout.strip() if has('node') else ''
    chk(f'Node.js {node or ""}', bool(node) and int(node.lstrip('v').split('.')[0]) >= 18, 'winget install OpenJS.NodeJS.LTS  |  brew install node')
    chk('npm', has('npm') or has('npm.cmd'), 'يجي مع Node.js')
    try:
        import faster_whisper  # noqa
        fw = True
    except Exception:
        fw = False
    chk('faster-whisper (التفريغ)', fw, 'pip install faster-whisper')
    try:
        import numpy  # noqa
        npk = True
    except Exception:
        npk = False
    chk('numpy', npk, 'pip install numpy')
    chk('محرّك الرسم (Remotion)', (WORK / 'node_modules' / 'remotion').exists(), 'python studio.py setup')
    free = shutil.disk_usage(HOME.anchor if HOME.exists() else Path.home().anchor).free / 1e9
    chk(f'مساحة القرص ({free:.0f} قيقا متاحة)', free > 5, 'فضّي مساحة (يحتاج 5 قيقا على الأقل)')
    print('\n' + ('كل شي جاهز 🎬' if ok else 'فيه أدوات ناقصة — ركّبها ثم أعد الفحص'))
    sys.exit(0 if ok else 1)


# ───────────────────────── new ─────────────────────────
def new(name, clips, fit=False):
    p = HOME / 'projects' / name
    p.mkdir(parents=True, exist_ok=True)
    ins, fc, L = [], '', ''
    for i, c in enumerate(clips):
        if not Path(c).exists():
            die(f'ما لقيت الملف: {c}')
        ins += ['-i', c]
        vf = ('split[x][y];[x]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:2,eq=brightness=-0.15[bg];'
              '[y]scale=1080:-2[fg];[bg][fg]overlay=0:(H-h)/2,') if fit else 'scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,'
        fc += (f'[{i}:v]{vf}fps={FPS},setsar=1[v{i}];'
               f'[{i}:a]aresample=48000,aformat=channel_layouts=stereo[a{i}];')
        L += f'[v{i}][a{i}]'
    fc += f'{L}concat=n={len(clips)}:v=1:a=1[v][a]'
    ff(*ins, '-filter_complex', fc, '-map', '[v]', '-map', '[a]', '-c:v', 'libx264', '-crf', '14', '-preset', 'fast',
       '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '256k', p / 'src.mp4')
    print(f'✅ المشروع جاهز: {p}\n   المدة: {probe_dur(p / "src.mp4"):.1f} ثانية')


# ───────────────────────── transcribe ─────────────────────────
def transcribe(name, model='large-v3'):
    p = proj(name)
    wav = p / 'a16k.wav'
    ff('-i', p / 'src.mp4', '-vn', '-ac', '1', '-ar', '16000', wav)
    from faster_whisper import WhisperModel
    m = None
    for dev, ct in (('cuda', 'float16'), ('cpu', 'int8')):
        try:
            m = WhisperModel(model, device=dev, compute_type=ct)
            segs, _ = m.transcribe(str(wav), language='ar', word_timestamps=True, vad_filter=True)
            segs = list(segs)
            break
        except Exception as e:  # GPU missing / out of memory → CPU
            print(f'… {dev} ما نفع ({str(e)[:60]}) — أجرّب المعالج')
    words = [{'w': w.word.strip(), 's': round(w.start, 3), 'e': round(w.end, 3)} for s in segs for w in s.words]
    sents = [{'s': round(s.start, 2), 'e': round(s.end, 2), 't': s.text.strip()} for s in segs]
    json.dump({'words': words, 'sentences': sents}, open(p / 'words.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
    print(f'✅ التفريغ: {len(words)} كلمة')
    for s in sents:
        print(f'  [{s["s"]:6.2f}] {s["t"]}')


# ───────────────────────── cut ─────────────────────────
def silences(src, db=-38, mind=0.35):
    r = subprocess.run(['ffmpeg', '-hide_banner', '-i', str(src), '-af', f'silencedetect=n={db}dB:d={mind}', '-f', 'null', '-'],
                       capture_output=True, text=True, encoding='utf-8', errors='ignore')
    st = [float(x) for x in re.findall(r'silence_start: ([\d.]+)', r.stderr)]
    en = [float(x) for x in re.findall(r'silence_end: ([\d.]+)', r.stderr)]
    return list(zip(st, en + [probe_dur(src)] * (len(st) - len(en))))


def cut(name):
    """edit.json (اختياري): {"fixes": {"غلط":"صح"}, "hot": [...], "drop": [[a,b],...], "pad": 0.12}"""
    p = proj(name)
    ed = json.load(open(p / 'edit.json', encoding='utf-8')) if (p / 'edit.json').exists() else {}
    pad = ed.get('pad', 0.12)
    dur = probe_dur(p / 'src.mp4')
    gaps = [(a, b) for a, b in silences(p / 'src.mp4')] + [tuple(x) for x in ed.get('drop', [])]
    gaps.sort()
    keep, cur = [], 0.0
    for a, b in gaps:
        a2 = a + pad if a > 0 else 0
        b2 = max(b - pad, a2)
        if a2 > cur + 0.05:
            keep.append((cur, a2))
        cur = max(cur, b2)
    if cur < dur - 0.1:
        keep.append((cur, dur))
    def mp(t):
        acc = 0.0
        for a, b in keep:
            if t < a: return acc
            if t <= b: return acc + t - a
            acc += b - a
        return acc
    W = json.load(open(p / 'words.json', encoding='utf-8'))['words']
    fixes, hot = ed.get('fixes', {}), set(ed.get('hot', []))
    caps = []
    for w in W:
        mid = (w['s'] + w['e']) / 2
        if not any(a <= mid <= b for a, b in keep):
            continue
        t = fixes.get(w['w'], w['w'])
        if not t:
            continue
        caps.append({'t': t, 's': round(mp(w['s']), 3), 'e': round(mp(w['e']), 3), 'hot': t in hot})
    total = sum(b - a for a, b in keep)
    fc, L = '', ''
    for i, (a, b) in enumerate(keep):
        fc += (f'[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS[v{i}];'
               f'[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.015,afade=t=out:st={max(0, b - a - 0.02):.3f}:d=0.02[a{i}];')
        L += f'[v{i}][a{i}]'
    fc += f'{L}concat=n={len(keep)}:v=1:a=1[v][a]'
    ff('-i', p / 'src.mp4', '-filter_complex', fc, '-map', '[v]', '-c:v', 'libx264', '-crf', '12', '-preset', 'fast', '-pix_fmt', 'yuv420p',
       p / 'main.mp4', '-map', '[a]', '-c:a', 'pcm_s16le', '-ar', '48000', '-ac', '2', p / 'voice.wav')
    json.dump({'total': round(total, 3), 'words': caps, 'keep': keep}, open(p / 'caps.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(f'✅ القص: {dur:.1f} ث → {total:.1f} ث (شلت {dur - total:.1f} ث سكوت)')
    line = ''
    for c in caps:
        line += f'{c["t"]}@{c["s"]:.2f} '
        if len(line) > 110:
            print('  ' + line); line = ''
    if line: print('  ' + line)


# ───────────────────────── sfx (generated, no copyright) ─────────────────────────
def make_sfx():
    import numpy as np
    sr = 48000
    def save(n, x):
        x = np.clip(x, -1, 1); y = (np.stack([x, x], 1) * 32767).astype('<i2')
        w = wave.open(str(ENGINE / 'sfx' / n), 'wb'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(sr); w.writeframes(y.tobytes()); w.close()
    (ENGINE / 'sfx').mkdir(exist_ok=True)
    t = np.arange(int(sr * .5)) / sr
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(len(t))
    soft = np.convolve(noise, np.ones(40) / 40, 'same') * 4
    save('whoosh.wav', .3 * soft * np.sin(np.pi * np.clip(t / .45, 0, 1)) ** 2)
    save('thud.wav', .8 * np.sin(2 * np.pi * 70 * t) * np.exp(-t * 14) + .2 * noise * np.exp(-t * 40))
    tp = t[:int(sr * .14)]
    save('pop.wav', .35 * np.sin(2 * np.pi * (500 + 900 * tp) * tp) * np.exp(-tp * 30))
    td = t[:int(sr * .45)]
    save('ding.wav', .25 * (np.sin(2 * np.pi * 1320 * td) + .5 * np.sin(2 * np.pi * 1980 * td)) * np.exp(-td * 7))
    tt = t[:int(sr * .06)]
    save('tick.wav', .25 * np.sin(2 * np.pi * 1600 * tt) * np.exp(-tt * 60))


# ───────────────────────── setup (Remotion workspace) ─────────────────────────
def setup():
    WORK.mkdir(parents=True, exist_ok=True)
    pkg = {'name': 'asrar-studio-engine', 'private': True,
           'dependencies': {'@remotion/cli': REMOTION, 'remotion': REMOTION, 'react': '18.3.1', 'react-dom': '18.3.1'}}
    json.dump(pkg, open(WORK / 'package.json', 'w'), indent=1)
    npm = shutil.which('npm') or shutil.which('npm.cmd') or 'npm'
    print('… أحمّل محرّك الرسم (مرة وحدة، ~500 ميقا)')
    run([npm, 'install', '--no-audit', '--no-fund', '--loglevel=error'], cwd=WORK, shell=os.name == 'nt')
    make_sfx()
    print('✅ المحرّك جاهز')


def sync(name):
    """ينسخ القالب + ملفات المشروع لمساحة الرسم."""
    p = proj(name)
    if not (WORK / 'node_modules' / 'remotion').exists():
        die('المحرّك مو جاهز — شغّل: setup')
    for d in ('src', 'public'):
        shutil.rmtree(WORK / d, ignore_errors=True)
    shutil.copytree(ENGINE / 'template' / 'src', WORK / 'src')
    shutil.copytree(ENGINE / 'template' / 'public', WORK / 'public')
    for f in ('remotion.config.ts', 'tsconfig.json'):
        shutil.copy(ENGINE / 'template' / f, WORK / f)
    tl = json.load(open(p / 'timeline.json', encoding='utf-8')) if (p / 'timeline.json').exists() else {}
    caps = json.load(open(p / 'caps.json', encoding='utf-8'))
    tl.setdefault('total', caps['total'] + tl.get('endCard', {}).get('dur', 0))
    tl['main_end'] = caps['total']
    tl['words'] = caps['words']
    brand_p = HOME / 'brand.json'
    if brand_p.exists():
        tl['brand'] = {**json.load(open(brand_p, encoding='utf-8')), **tl.get('brand', {})}
    shutil.copy(p / 'main.mp4', WORK / 'public' / 'main.mp4')
    ff('-sseof', '-0.1', '-i', p / 'main.mp4', '-frames:v', '1', WORK / 'public' / 'last.png')
    for i, b in enumerate(tl.get('broll', [])):     # B-roll clips → public
        src = Path(b['file'])
        if not src.is_absolute(): src = p / src
        dst = f'broll_{i}.mp4'
        args = ['-ss', str(b.get('from', 0)), '-t', str(b['b'] - b['a'] + 0.3), '-i', src, '-an']
        vf = [f"crop={b['crop']}"] if b.get('crop') else []
        if b.get('blur'):  # [x,y,w,h] privacy blur
            x, y, w, h = b['blur']
            vf = [f'split[m][c];[c]crop={w}:{h}:{x}:{y},boxblur=18:4[bl];[m][bl]overlay={x}:{y}' + (',' + vf[0] if vf else '')]
        vf.append('scale=1080:-2:flags=lanczos')
        ff(*args, '-vf', ','.join(vf), '-c:v', 'libx264', '-crf', '14', WORK / 'public' / dst)
        b['src'] = dst
    json.dump(tl, open(WORK / 'src' / 'timeline.json', 'w', encoding='utf-8'), ensure_ascii=False)
    return p, tl


def npx():
    return shutil.which('npx') or shutil.which('npx.cmd') or 'npx'


def preview(name, times):
    p, tl = sync(name)
    outs = []
    for t in times:
        o = WORK / 'out' / f'p_{t}.png'
        run([npx(), 'remotion', 'still', 'src/index.ts', 'Main', str(o), f'--frame={int(float(t) * FPS)}', '--scale=0.35', '--log=error'],
            cwd=WORK, shell=os.name == 'nt')
        outs.append(o)
    args = sum([['-i', o] for o in outs], [])
    ff(*args, '-filter_complex', f'hstack={len(outs)}' if len(outs) > 1 else 'null', p / 'preview.jpg')
    print(f'✅ المعاينة: {p / "preview.jpg"}')


def mix_audio(p, tl):
    total = tl['total']
    ev = []
    for b in tl.get('broll', []): ev.append(('whoosh', b['a']))
    for s in tl.get('stickers', []): ev.append(('thud', s['at']))
    for h in tl.get('hero', []): ev.append(('ding', h['a'] + .1))
    for c in tl.get('chapters', [])[1:]: ev.append(('whoosh', c['at']))
    if tl.get('endCard'): ev.append(('ding', tl['main_end'] + .2))
    ev = [e for e in ev if 0 <= e[1] < total]
    ins, fc, L = ['-i', p / 'voice.wav'], '', ''
    for i, (k, t) in enumerate(ev, 1):
        ins += ['-i', ENGINE / 'sfx' / f'{k}.wav']
        ms = int(t * 1000); fc += f'[{i}]adelay={ms}|{ms}[e{i}];'; L += f'[e{i}]'
    music = tl.get('music')
    if music:
        ins += ['-stream_loop', '-1', '-i', music]
    mi = len(ev) + 1
    g = f'[0]apad=whole_dur={total},asplit=2[v][sc];'
    parts = '[v]'
    n = 1
    if ev:
        g += fc + f'{L}amix=inputs={len(ev)}:normalize=0,volume=0.8[fx];'; parts += '[fx]'; n += 1
    if music:
        g += f'[{mi}]atrim=0:{total},afade=t=out:st={max(0, total - 1.5)}:d=1.5[mu];[mu][sc]sidechaincompress=threshold=0.03:ratio=8:release=300,volume=-14dB[m];'
        parts += '[m]'; n += 1
    else:
        g = g.replace('asplit=2[v][sc]', 'anull[v]')
    g += f'{parts}amix=inputs={n}:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[o]'
    ff(*ins, '-filter_complex', g, '-map', '[o]', '-ar', '48000', p / 'mix.wav')


def render(name):
    p, tl = sync(name)
    silent = WORK / 'out' / 'silent.mp4'
    run([npx(), 'remotion', 'render', 'src/index.ts', 'Main', str(silent), '--codec=h264', '--crf=12', '--concurrency=4', '--log=error'],
        cwd=WORK, shell=os.name == 'nt')
    mix_audio(p, tl)
    out = p / 'out'; out.mkdir(exist_ok=True)
    base = tl.get('title', name)
    enc = ['-c:v', 'libx264', '-profile:v', 'high', '-preset', 'slow', '-pix_fmt', 'yuv420p', '-r', str(FPS), '-g', '60',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', '-shortest']
    ff('-i', silent, '-i', p / 'mix.wav', '-map', '0:v', '-map', '1:a', *enc, '-b:v', '12M', '-maxrate', '15M', '-bufsize', '24M',
       '-c:a', 'aac', '-b:a', '256k', out / f'{base}-تيك توك وريلز.mp4')
    ff('-i', silent, '-i', p / 'mix.wav', '-map', '0:v', '-map', '1:a', *enc, '-b:v', '8M', '-maxrate', '8M', '-bufsize', '16M',
       '-c:a', 'aac', '-b:a', '128k', '-ar', '44100', out / f'{base}-X.mp4')
    ff('-i', out / f'{base}-تيك توك وريلز.mp4', '-vf', 'scale=720:-2', '-c:v', 'libx264', '-crf', '25', '-preset', 'fast',
       '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', out / f'{base}-معاينة.mp4')
    print(f'✅ جاهز: {out}')
    for f in sorted(out.iterdir()):
        print(f'   {f.name}  ({f.stat().st_size / 1e6:.0f} ميقا)')


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(0)
    c = a[0]
    if c == 'doctor': doctor()
    elif c == 'new': new(a[1], a[2:])
    elif c == 'transcribe': transcribe(a[1], *(a[2:3]))
    elif c == 'cut': cut(a[1])
    elif c == 'setup': setup()
    elif c == 'preview': preview(a[1], a[2:])
    elif c == 'render': render(a[1])
    elif c == 'path': print(HOME / 'projects' / a[1])
    elif c == 'serve':
        import server; server.serve(open_browser='--no-open' not in a)
    else: print(__doc__)
