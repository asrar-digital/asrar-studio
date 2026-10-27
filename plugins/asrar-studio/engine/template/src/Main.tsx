import React from 'react';
import {AbsoluteFill, OffthreadVideo, Img, Audio, Sequence, staticFile, useCurrentFrame, continueRender, delayRender, interpolate, Easing} from 'remotion';
import tlRaw from './timeline.json';

/* ═══ أسرار ستوديو — قالب يقرأ كل شي من timeline.json ═══
   نفس القالب يشتغل بالرندر (Remotion) وبالمعاينة الحية بالمتصفح (@remotion/player). */
let TL: any = tlRaw;
const FPS = 30;
const F = (s: number) => Math.round(s * FPS);
const C = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const ev = (f: number, a: number, b: number, o0 = 0, o1 = 1) => interpolate(f, [a, b], [o0, o1], {...C, easing: Easing.bezier(0.22, 1, 0.36, 1)});
let DAMP = 10, ENERGY = 1;
const spring = (f: number, at: number, damp = DAMP) => {
  const t = Math.max(0, f - at) / FPS; if (f < at) return 0;
  const w = 16, z = Math.min(.95, damp / 20);
  return 1 - Math.exp(-z * w * t) * Math.cos(w * Math.sqrt(1 - z * z) * t);
};

/* الملفات: بالرندر staticFile، وبالمعاينة الحية السيرفر المحلي */
const asset = (p: string) => ((globalThis as any).__ASRAR_ASSET ? (globalThis as any).__ASRAR_ASSET(p) : staticFile(p));

/* local fonts */
const h = delayRender('fonts');
const st = document.createElement('style');
st.textContent = `@font-face{font-family:'TJ';font-weight:800;src:url('${asset('fonts/Tajawal-ExtraBold.ttf')}')}
@font-face{font-family:'TJ';font-weight:900;src:url('${asset('fonts/Tajawal-Black.ttf')}')}
@font-face{font-family:'IN';font-weight:100 900;src:url('${asset('fonts/Inter.ttf')}')}`;
document.head.appendChild(st);
Promise.all([document.fonts.load('800 40px TJ', 'أب'), document.fonts.load('900 40px TJ', 'أب'), document.fonts.load('900 40px IN')]).then(() => continueRender(h), () => continueRender(h));

/* ── الأشكال (الإطار) + باقات الألوان ── */
const HARD = (ink: string) => (shadow: string, off = 10) => ({border: `6px solid ${ink}`, boxShadow: `${off}px ${off}px 0 ${shadow}`});
const SOFT = (edge: string) => (shadow: string) => ({border: `2px solid ${edge}`, borderRadius: 22, boxShadow: `0 0 0 1px rgba(0,0,0,.4), 0 18px 50px rgba(0,0,0,.45), 0 0 40px ${shadow}33`});
export const PALETTES: Record<string, any> = {
  editorial: {name: 'إديتوريال', ink: '#0E0E0E', accent: '#FF6B1A', hi: '#D7FF3A', paper: '#F4EFE6', red: '#FF3B3B', hard: true},
  gold:      {name: 'ذهبي فاخر', ink: '#070707', accent: '#D4A84B', hi: '#F3D28C', paper: '#F7F1E4', red: '#FF4D6D'},
  amber:     {name: 'ليلي كهرماني', ink: '#0B1020', accent: '#7C5CFF', hi: '#FFB547', paper: '#F5F1E8', red: '#FF4D6D'},
  teal:      {name: 'بحر فيروزي', ink: '#04161C', accent: '#1E90FF', hi: '#2EE6D6', paper: '#EAFBFB', red: '#FF5A5F'},
  sunset:    {name: 'غروب', ink: '#1A0B12', accent: '#FF2E63', hi: '#FF9F45', paper: '#FFF1E6', red: '#FF2E63'},
  neon:      {name: 'أسود ونيون', ink: '#050505', accent: '#00E5FF', hi: '#39FF14', paper: '#F2F2F2', red: '#FF2079'},
  mono:      {name: 'أسود وأبيض', ink: '#0A0A0A', accent: '#8A8A8A', hi: '#FFFFFF', paper: '#FFFFFF', red: '#FF3B3B'},
};
let T: any = {};
const COLOR = (c?: string) => ({lime: T.hi, hi: T.hi, cream: T.paper, paper: T.paper, red: T.red, accent: T.accent, ink: T.ink} as any)[c || 'paper'] || c;
const AR = "'TJ', sans-serif", EN = "'IN', sans-serif";
const isLatin = (s: string) => /^[\x00-\x7F]+$/.test(String(s));

type P = {f: number; t: number};
let MAIN_END = 0;

/* ── captions: 3-word chunks, hot word on highlighter ── */
type W = {t: string; s: number; e: number; hot: boolean};
let CHUNKS: W[][] = [];

/* يجهّز كل شي من الخطة — يتنادى مرة بالرندر، وكل ما تتغيّر الخطة بالمعاينة الحية */
export function init(tl: any) {
  TL = tl || {};
  const base = PALETTES[TL.palette] || PALETTES[TL.style] || PALETTES.editorial;
  const c = {...base, ...(TL.brand?.colors || {}), ...(TL.colors || {})};
  const hard = (TL.frame || (base.hard ? 'hard' : 'soft')) === 'hard';
  T = {...c, radius: hard ? 0 : 22, box: hard ? HARD(c.ink) : SOFT(c.accent)};
  const mood = TL.mood || 'formal';
  ENERGY = (TL.energy ?? 1) * (mood === 'hype' ? 1.35 : mood === 'calm' ? .6 : 1);
  DAMP = mood === 'hype' ? 7 : mood === 'calm' ? 16 : 10;
  MAIN_END = TL.main_end ?? TL.total ?? 0;
  CHUNKS = [];
  const ws: W[] = TL.words || [];
  const per = TL.captionWords ?? 3;
  let cur: W[] = [];
  ws.forEach((w, i) => {
    cur.push(w);
    const gap = i + 1 < ws.length ? ws[i + 1].s - w.e : 9;
    if (cur.length >= per || gap > 0.45) { CHUNKS.push(cur); cur = []; }
  });
  if (cur.length) CHUNKS.push(cur);
}
init(tlRaw);

const Captions: React.FC<P> = ({f, t}) => {
  if (TL.captions === false || t > MAIN_END) return null;
  const idx = CHUNKS.findIndex((c, i) => t >= c[0].s - 0.05 && (i === CHUNKS.length - 1 || t < CHUNKS[i + 1][0].s - 0.05));
  if (idx < 0) return null;
  const c = CHUNKS[idx];
  if (t > c[c.length - 1].e + 0.45) return null;
  const size = TL.captionSize ?? 70;
  return (
    <div style={{position: 'absolute', top: TL.captionY ?? 1390, left: 60, right: 60, display: 'flex', justifyContent: 'center'}}>
      <div style={{direction: 'rtl', display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'center'}}>
        {c.map((w, i) => {
          const at = F(w.s - 0.05), k = spring(f, at, 9), said = f >= at, bar = ev(f, at, at + 6);
          return (
            <span key={i} style={{position: 'relative', fontFamily: isLatin(w.t) ? EN : AR, fontWeight: 900, fontSize: size, lineHeight: 1.15, whiteSpace: 'nowrap',
              display: 'inline-block', opacity: said ? 1 : 0, transform: `translateY(${(1 - k) * 30 * ENERGY}px) scale(${0.7 + 0.3 * k})`}}>
              {w.hot && <span style={{position: 'absolute', left: -12, right: -12, top: 6, bottom: 2, background: T.hi, border: `4px solid ${T.ink}`,
                borderRadius: T.radius / 2, transform: `scaleX(${bar}) skewX(-10deg)`, transformOrigin: 'right'}} />}
              <span style={{position: 'relative', color: w.hot ? T.ink : (TL.captionColor || T.paper),
                textShadow: w.hot ? 'none' : `4px 4px 0 ${T.ink}, -2px -2px 0 ${T.ink}, 2px -2px 0 ${T.ink}, -2px 2px 0 ${T.ink}`}}>{w.t}</span>
            </span>);
        })}
      </div>
    </div>
  );
};

/* ── chapter label ── */
const Chapter: React.FC<P> = ({f, t}) => {
  const ch: any[] = TL.chapters || [];
  if (!ch.length || t >= MAIN_END) return null;
  let i = -1; ch.forEach((c, k) => { if (t >= c.at) i = k; });
  if (i < 0) return null;
  const c = ch[i], k = spring(f, F(c.at) + 2);
  return (
    <div style={{position: 'absolute', top: 260, right: 60, display: 'flex', direction: 'rtl', transform: `translateX(${(1 - k) * 300}px)`, ...T.box(T.accent, 8), overflow: 'hidden'}}>
      <div style={{background: T.ink, color: T.hi, fontFamily: EN, fontWeight: 900, fontSize: 40, padding: '6px 16px'}}>{c.n || String(i + 1).padStart(2, '0')}</div>
      <div style={{background: T.paper, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 40, padding: '6px 22px'}}>{c.label}</div>
    </div>
  );
};

/* ── stickers ── */
const Stickers: React.FC<P> = ({f, t}) => (
  <>{(TL.stickers || []).map((s: any, i: number) => {
    const until = s.until ?? Infinity;
    if (t < s.at || t > until + 0.4) return null;
    const bg = COLOR(s.color), dark = [T.red, T.accent, T.ink].includes(bg);
    return <div key={i} style={{position: 'absolute', left: s.x ?? 140, top: s.y ?? 500, transform: `rotate(${s.rot ?? -4}deg) scale(${spring(f, F(s.at))})`,
      opacity: 1 - ev(f, F(until), F(until + .35)), fontFamily: AR, fontWeight: 900, fontSize: s.size ?? 52, color: dark ? '#fff' : T.ink, background: bg,
      padding: '10px 26px', whiteSpace: 'nowrap', direction: 'rtl', ...T.box(T.ink, 8)}}>{s.text}</div>;
  })}</>
);

/* ── B-roll window (فيديو أو صورة) ── */
const isImg = (p: string) => /\.(jpe?g|png|webp)$/i.test(p || '');
const BRoll: React.FC<P> = ({f, t}) => {
  const list: any[] = TL.broll || [];
  const i = list.findIndex((b) => t >= b.a && t < b.b);
  if (i < 0) return null;
  const b = list[i], s = F(b.a), e = F(b.b);
  const kin = ev(f, s, s + 9), kout = ev(f, e - 6, e), dir = i % 2 ? -1 : 1;
  const tilt = (i % 2 ? 2.5 : -2.5) + Math.sin((f - s) / 30) * .6;
  const blur = (1 - kin + kout) * 30;
  const W_ = b.landscape ? 960 : 700, H_ = b.landscape ? 560 : 1000;
  const src = b.src || b.file;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: b.landscape ? 520 : 360, display: 'flex', justifyContent: 'center'}}>
      <div style={{position: 'relative', transform: `translateX(${(1 - kin) * 1200 * dir - kout * 1200 * dir}px) rotate(${tilt}deg)`, filter: blur > .5 ? `blur(${blur}px)` : undefined}}>
        <div style={{width: W_, height: H_, overflow: 'hidden', background: '#000', ...T.box(T.accent, 14)}}>
          {isImg(src) ? <Img src={asset(src)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
            : <Sequence from={s} durationInFrames={e - s + 2}><OffthreadVideo src={asset(src)} startFrom={b.src ? 0 : F(b.from || 0)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} /></Sequence>}
        </div>
        {b.tag && <div style={{position: 'absolute', top: -50, left: 16, display: 'flex', direction: 'rtl', transformOrigin: 'left', transform: `rotate(${-tilt * 1.4}deg) scale(${spring(f, s + 6)})`, ...T.box(T.ink, 6), overflow: 'hidden'}}>
          <div style={{background: T.hi, color: T.ink, fontFamily: EN, fontWeight: 900, fontSize: 34, padding: '6px 14px'}}>{b.n || String(i + 1).padStart(2, '0')}</div>
          <div style={{background: T.paper, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 32, padding: '6px 18px', whiteSpace: 'nowrap'}}>{b.tag}</div>
        </div>}
      </div>
    </div>
  );
};

/* ── hero reveal (big title over blurred footage) ── */
const Hero: React.FC<P> = ({f, t}) => (
  <>{(TL.hero || []).map((hh: any, i: number) => {
    if (t < hh.a - .1 || t > hh.b + .1) return null;
    const k = spring(f, F(hh.a)), out = ev(f, F(hh.b) - 8, F(hh.b));
    return (
      <div key={i} style={{position: 'absolute', left: 0, right: 0, top: hh.y ?? 480, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24, opacity: 1 - out,
        transform: `scale(${.6 + .4 * k + out * .3})`}}>
        {hh.emoji && <div style={{width: 220, height: 220, borderRadius: 999, background: T.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 130, ...T.box(T.ink, 12), borderRadius: 999}}>{hh.emoji}</div>}
        <div style={{fontFamily: isLatin(hh.title) ? EN : AR, fontWeight: 900, fontSize: hh.size ?? 120, color: T.paper, letterSpacing: isLatin(hh.title) ? -4 : 0, textShadow: `8px 8px 0 ${T.ink}`, textAlign: 'center', direction: 'rtl'}}>{hh.title}</div>
        {hh.subtitle && <div style={{background: T.hi, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 46, padding: '8px 26px', transform: 'rotate(-2deg)', direction: 'rtl', ...T.box(T.ink, 8)}}>{hh.subtitle}</div>}
      </div>);
  })}</>
);

/* ── strike list (old ways crossed out) ── */
const Strike: React.FC<P> = ({f, t}) => (
  <>{(TL.strike || []).map((sl: any, i: number) => {
    if (t < sl.a || t > sl.b + .3) return null;
    const out = ev(f, F(sl.b), F(sl.b) + 8);
    return (
      <div key={i} style={{position: 'absolute', left: 0, right: 0, top: sl.y ?? 400, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 22, opacity: 1 - out}}>
        {sl.items.map((it: string, j: number) => {
          const at = F(sl.a + .3) + j * 5, x = ev(f, F(sl.a + 1.4) + j * 3, F(sl.a + 1.8) + j * 3);
          return <div key={j} style={{position: 'relative', fontFamily: isLatin(it) ? EN : AR, fontWeight: 900, fontSize: 52, color: T.ink, background: T.paper, padding: '10px 30px',
            direction: isLatin(it) ? 'ltr' : 'rtl', transform: `scale(${spring(f, at)}) rotate(${(j % 2 ? 1 : -1) * 3}deg)`, ...T.box(T.red, 8)}}>{it}
            <div style={{position: 'absolute', left: -12, right: -12, top: '46%', height: 12, background: T.red, transform: `scaleX(${x}) rotate(-3deg)`}} /></div>;
        })}
      </div>);
  })}</>
);

/* ═════════ الرسومات الجديدة (items) — كل وحدة لها وقت ومكان وحجم ووضع ═════════
   {type, a, b, layout:'full'|'split', x, y, scale, sfx, ...المحتوى} */
const num = (v: any) => Number(String(v ?? '').replace(/[^\d.]/g, '')) || 0;
const countUp = (f: number, at: number, v: any) => {
  const n = num(v), k = ev(f, at, at + 22);
  if (!n) return String(v ?? '');
  const shown = n * k, dec = String(v).includes('.') ? 1 : 0;
  return String(v).replace(/[\d.,]+/, shown.toLocaleString('en-US', {maximumFractionDigits: dec, minimumFractionDigits: dec}));
};
const Card: React.FC<{children: any; w?: number; pad?: number}> = ({children, w = 920, pad = 40}) => (
  <div style={{width: w, background: T.ink + 'EE', padding: pad, direction: 'rtl', ...T.box(T.accent, 12), borderRadius: T.radius}}>{children}</div>
);
const Title: React.FC<{text?: string; f: number; at: number}> = ({text, f, at}) => !text ? null : (
  <div style={{display: 'inline-block', background: T.hi, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 52, padding: '6px 26px', marginBottom: 26,
    borderRadius: T.radius / 2, transform: `scale(${spring(f, at)}) rotate(-1.5deg)`, transformOrigin: 'right'}}>{text}</div>
);
const pointAt = (it: any, j: number, key = 'points') => it[key]?.[j]?.t ?? (it.a + .5 + j * Math.max(.5, (it.b - it.a - 1) / Math.max(1, (it[key]?.length || 1))));
const txt = (p: any) => (typeof p === 'string' ? p : p?.text ?? '');

const ITEM: Record<string, React.FC<{it: any; f: number}>> = {
  list: ({it, f}) => (
    <Card><Title text={it.title} f={f} at={F(it.a)} />
      {(it.points || []).map((p: any, j: number) => {
        const at = F(pointAt(it, j)), k = spring(f, at);
        return <div key={j} style={{display: 'flex', alignItems: 'center', gap: 22, margin: '16px 0', opacity: f >= at ? 1 : 0, transform: `translateX(${(1 - k) * -80 * ENERGY}px)`}}>
          <div style={{minWidth: 70, height: 70, borderRadius: 999, background: T.accent, color: T.paper, fontFamily: EN, fontWeight: 900, fontSize: 38, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{j + 1}</div>
          <div style={{fontFamily: AR, fontWeight: 900, fontSize: 54, color: T.paper}}>{txt(p)}</div></div>;
      })}</Card>),
  costs: ({it, f}) => (
    <Card><Title text={it.title || 'التكاليف'} f={f} at={F(it.a)} />
      {(it.rows || []).map((r: any, j: number) => {
        const at = F(pointAt(it, j, 'rows'));
        return <div key={j} style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 0', borderBottom: `2px dashed ${T.paper}33`, opacity: f >= at ? 1 : 0}}>
          <span style={{fontFamily: AR, fontWeight: 800, fontSize: 48, color: T.paper}}>{r.label}</span>
          <span style={{fontFamily: EN, fontWeight: 900, fontSize: 52, color: T.hi, direction: 'ltr'}}>{countUp(f, at, r.value)}</span></div>;
      })}
      {it.total != null && (() => { const at = F(it.b - Math.min(1.2, (it.b - it.a) / 3)); return (
        <div style={{display: 'flex', justifyContent: 'space-between', marginTop: 22, background: T.hi, color: T.ink, padding: '14px 24px', borderRadius: T.radius / 2, transform: `scale(${spring(f, at)})`}}>
          <span style={{fontFamily: AR, fontWeight: 900, fontSize: 52}}>المجموع</span><span style={{fontFamily: EN, fontWeight: 900, fontSize: 60, direction: 'ltr'}}>{countUp(f, at, it.total)}</span></div>); })()}
    </Card>),
  compare: ({it, f}) => {
    const side = (s: any, k: number, good: boolean) => {
      const at = F(it.a + .2 + k * .5), sp = spring(f, at);
      return <div style={{flex: 1, background: good ? T.hi : T.paper + '14', color: good ? T.ink : T.paper, padding: 26, borderRadius: T.radius, transform: `translateY(${(1 - sp) * 120}px)`, opacity: Math.min(1, sp * 2)}}>
        <div style={{fontFamily: AR, fontWeight: 900, fontSize: 50, marginBottom: 14}}>{s?.title}</div>
        {(s?.points || []).map((p: any, j: number) => <div key={j} style={{fontFamily: AR, fontWeight: 800, fontSize: 40, margin: '10px 0', opacity: f >= at + 8 + j * 6 ? 1 : 0}}>{good ? '✔ ' : '✖ '}{txt(p)}</div>)}
      </div>;
    };
    return <Card w={980}><Title text={it.title} f={f} at={F(it.a)} />
      <div style={{display: 'flex', gap: 22, alignItems: 'stretch', position: 'relative'}}>{side(it.right, 0, false)}{side(it.left, 1, true)}
        <div style={{position: 'absolute', left: '50%', top: '40%', transform: `translate(-50%,-50%) scale(${spring(f, F(it.a + .6))})`, background: T.red, color: '#fff', fontFamily: EN, fontWeight: 900, fontSize: 40, width: 90, height: 90, borderRadius: 999, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>VS</div></div></Card>;
  },
  convert: ({it, f}) => {
    const mid = F(it.mid ?? (it.a + (it.b - it.a) * .45)), a = spring(f, F(it.a)), b = spring(f, mid), arrow = ev(f, mid - 8, mid);
    const box = (v: string, on: boolean, k: number) => <div style={{background: on ? T.hi : T.paper + '18', color: on ? T.ink : T.paper, fontFamily: isLatin(v) ? EN : AR, fontWeight: 900, fontSize: 60,
      padding: '26px 34px', borderRadius: T.radius, transform: `scale(${k})`, textDecoration: !on && f > mid ? `line-through ${T.red} 6px` : 'none'}}>{v}</div>;
    return <Card><Title text={it.title} f={f} at={F(it.a)} />
      <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 26}}>{box(it.from, false, a)}
        <div style={{fontSize: 80, color: T.accent, transform: `scaleX(${arrow})`, transformOrigin: 'right'}}>⟵</div>{box(it.to, true, b)}</div></Card>;
  },
  bignum: ({it, f}) => {
    const at = F(it.a), k = spring(f, at);
    return <div style={{display: 'flex', flexDirection: 'column', alignItems: 'center', transform: `scale(${.5 + .5 * k})`}}>
      <div style={{fontFamily: EN, fontWeight: 900, fontSize: it.size ?? 260, color: T.hi, lineHeight: 1, textShadow: `10px 10px 0 ${T.ink}`, direction: 'ltr', letterSpacing: -8}}>
        {it.prefix || ''}{countUp(f, at, it.value)}{it.suffix || ''}</div>
      {it.label && <div style={{marginTop: 20, background: T.paper, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 56, padding: '8px 30px', borderRadius: T.radius / 2, ...T.box(T.ink, 8)}}>{it.label}</div>}
    </div>;
  },
  numbers: ({it, f}) => (
    <Card w={980}><Title text={it.title} f={f} at={F(it.a)} />
      <div style={{display: 'flex', flexWrap: 'wrap', gap: 20, justifyContent: 'center'}}>{(it.items || []).map((x: any, j: number) => {
        const at = F(pointAt(it, j, 'items')), k = spring(f, at);
        return <div key={j} style={{width: 280, background: T.paper + '12', borderRadius: T.radius, padding: '22px 10px', textAlign: 'center', transform: `scale(${k})`}}>
          <div style={{fontFamily: EN, fontWeight: 900, fontSize: 84, color: T.hi, direction: 'ltr'}}>{countUp(f, at, x.value)}</div>
          <div style={{fontFamily: AR, fontWeight: 800, fontSize: 36, color: T.paper}}>{x.label}</div></div>;
      })}</div></Card>),
  quote: ({it, f}) => {
    const at = F(it.a), words = String(it.text || '').split(/\s+/);
    return <div style={{maxWidth: 940, textAlign: 'center', direction: 'rtl', lineHeight: 1.35}}>
      {it.label && <div style={{display: 'inline-block', marginBottom: 18, background: T.accent, color: T.paper, fontFamily: AR, fontWeight: 900, fontSize: 40, padding: '4px 22px', borderRadius: 99}}>{it.label}</div>}<div>
      {words.map((w, j) => { const wa = at + j * 3, on = (it.hi || '').split(/\s+/).includes(w);
        return <span key={j} style={{display: 'inline-block', margin: '0 10px', fontFamily: AR, fontWeight: 900, fontSize: it.size ?? 96, color: on ? T.ink : T.paper, opacity: f >= wa ? 1 : 0,
          background: on ? T.hi : 'transparent', padding: on ? '0 16px' : 0, borderRadius: T.radius / 2, transform: `translateY(${(1 - spring(f, wa)) * 40}px)`,
          textShadow: on ? 'none' : `6px 6px 0 ${T.ink}`}}>{w}</span>; })}</div></div>;
  },
  icons: ({it, f}) => (
    <div style={{display: 'flex', gap: 40, justifyContent: 'center', flexWrap: 'wrap', maxWidth: 1000}}>{(it.items || []).map((x: any, j: number) => {
      const at = F(pointAt(it, j, 'items')), k = spring(f, at);
      return <div key={j} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16, transform: `scale(${k}) translateY(${Math.sin((f - at) / 12) * 6}px)`}}>
        <div style={{width: 230, height: 230, borderRadius: 50, background: T.paper + '14', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 140, ...T.box(T.accent, 8)}}>{x.icon}</div>
        <div style={{background: T.paper, color: T.ink, fontFamily: AR, fontWeight: 900, fontSize: 44, padding: '6px 22px', borderRadius: 99}}>{x.label}</div></div>;
    })}</div>),
};
export const ITEM_TYPES = Object.keys(ITEM);

const Items: React.FC<P> = ({f, t}) => (
  <>{(TL.items || []).map((it: any, i: number) => {
    if (t < it.a - .05 || t > it.b + .3 || !ITEM[it.type]) return null;
    const out = ev(f, F(it.b), F(it.b) + 9), k = spring(f, F(it.a));
    const split = it.layout === 'split';
    const R = ITEM[it.type];
    return <div key={i} style={{position: 'absolute', left: 0, right: 0, top: split ? 1000 : (it.y ?? 520), display: 'flex', justifyContent: 'center',
      transform: `translateX(${(it.x ?? 0)}px) scale(${(it.scale ?? 1) * (.85 + .15 * k)})`, transformOrigin: '50% 0', opacity: (1 - out) * Math.min(1, k * 1.6)}}>
      <R it={it} f={f} /></div>;
  })}</>
);

/* ── end card ── */
const EndCard: React.FC<P> = ({f, t}) => {
  const ec = TL.endCard; if (!ec || t < MAIN_END - .1) return null;
  const s = F(MAIN_END);
  return (
    <AbsoluteFill style={{background: T.accent, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 34, clipPath: `circle(${ev(f, s - 3, s + 12) * 150}% at 50% 50%)`}}>
      <div style={{position: 'absolute', inset: 0, backgroundImage: 'repeating-linear-gradient(45deg, rgba(0,0,0,.06) 0 4px, transparent 4px 26px)'}} />
      {ec.emoji && <div style={{fontSize: 150, transform: `scale(${spring(f, s + 4)}) rotate(${Math.sin(f / 8) * 6}deg)`}}>{ec.emoji}</div>}
      <div style={{fontFamily: AR, fontWeight: 900, fontSize: 76, color: T.ink, textAlign: 'center', lineHeight: 1.25, whiteSpace: 'pre-line', transform: `scale(${spring(f, s + 7)})`}}>{ec.title}</div>
      {ec.button && <div style={{background: T.ink, color: T.hi, fontFamily: AR, fontWeight: 900, fontSize: 52, padding: '14px 40px', borderRadius: T.radius, transform: `scale(${spring(f, s + 14)}) rotate(-2deg)`, boxShadow: `10px 10px 0 ${T.paper}`}}>{ec.button}</div>}
      {ec.sub && <div style={{fontFamily: AR, fontWeight: 800, fontSize: 36, color: T.ink, opacity: ev(f, s + 20, s + 30)}}>{ec.sub}</div>}
    </AbsoluteFill>
  );
};

export const Main: React.FC = () => {
  const f = useCurrentFrame(), t = f / FPS;
  /* footage dims & blurs smoothly behind windows (B-roll / hero / strike / full items) */
  const items: any[] = TL.items || [];
  const wins = [...(TL.broll || []), ...(TL.hero || []), ...(TL.strike || []), ...items.filter((x) => x.layout !== 'split' && x.dim !== false)];
  const dimK = wins.reduce((a: number, w: any) => Math.max(a, interpolate(t, [w.a - .25, w.a, w.b, w.b + .25], [0, 1, 1, 0], C)), 0) * (TL.dim ?? 1);
  /* الشاشة المقسومة: الفيديو يطلع فوق والرسمة تحت */
  const splitK = items.filter((x) => x.layout === 'split').reduce((a: number, w: any) => Math.max(a, interpolate(t, [w.a - .3, w.a, w.b, w.b + .3], [0, 1, 1, 0], C)), 0);
  /* fix mistakes: zoom into frame during given windows */
  const fix = (TL.fix || []).reduce((a: number, z: any) => Math.max(a, interpolate(t, [z.a - .3, z.a, z.b, z.b + .3], [0, 1, 1, 0], C) * (z.zoom ?? .14)), 0);
  /* punch on cuts & shake on stickers */
  const cuts: number[] = TL.cuts || [];
  const last = [...cuts].reverse().find((c) => t >= c);
  const punch = last !== undefined ? interpolate(t - last, [0, .35], [1 + .08 * ENERGY, 1], {...C, easing: Easing.out(Easing.cubic)}) : 1;
  const shake = (TL.stickers || []).reduce((a: number, s: any) => a + (f >= F(s.at) && f < F(s.at) + 8 ? Math.sin((f - F(s.at)) * 3) * 10 * ENERGY * (1 - (f - F(s.at)) / 8) : 0), 0);
  return (
    <AbsoluteFill style={{background: T.ink}}>
      <AbsoluteFill style={{transform: `translateY(${-splitK * 420}px) translateX(${shake}px) scale(${punch * (1 + fix) * (1 + dimK * .12)})`, transformOrigin: '50% 35%',
        clipPath: splitK ? `inset(0 0 ${splitK * 46}% 0 round ${splitK * 40}px)` : undefined,
        filter: dimK ? `blur(${dimK * 16}px) brightness(${1 - dimK * .45}) saturate(${1 - dimK * .5})` : undefined}}>
        <Sequence durationInFrames={F(MAIN_END)}><OffthreadVideo src={asset('main.mp4')} muted style={{width: 1080, height: 1920}} /></Sequence>
        {t >= MAIN_END && <Img src={asset('last.png')} style={{width: 1080, height: 1920}} />}
      </AbsoluteFill>
      {(globalThis as any).__ASRAR_ASSET && <Audio src={asset('voice.wav')} />}
      <Stickers f={f} t={t} />
      <Hero f={f} t={t} />
      <BRoll f={f} t={t} />
      <Strike f={f} t={t} />
      <Items f={f} t={t} />
      <Chapter f={f} t={t} />
      <Captions f={f} t={t} />
      <EndCard f={f} t={t} />
      {TL.grain !== false && !(globalThis as any).__ASRAR_ASSET && <svg style={{position: 'absolute', inset: 0, mixBlendMode: 'overlay', opacity: .1, pointerEvents: 'none'}} width={1080} height={1920}>
        <filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" seed={f % 7} /></filter><rect width={1080} height={1920} filter="url(#g)" /></svg>}
    </AbsoluteFill>
  );
};
