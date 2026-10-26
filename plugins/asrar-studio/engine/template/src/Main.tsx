import React from 'react';
import {AbsoluteFill, OffthreadVideo, Img, Sequence, staticFile, useCurrentFrame, continueRender, delayRender, interpolate, Easing} from 'remotion';
import tlRaw from './timeline.json';

/* ═══ أسرار ستوديو — قالب يقرأ كل شي من timeline.json ═══ */
const TL: any = tlRaw;
const FPS = 30;
const F = (s: number) => Math.round(s * FPS);
const C = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
const ev = (f: number, a: number, b: number, o0 = 0, o1 = 1) => interpolate(f, [a, b], [o0, o1], {...C, easing: Easing.bezier(0.22, 1, 0.36, 1)});
const spring = (f: number, at: number, damp = 10) => {
  const t = Math.max(0, f - at) / FPS; if (f < at) return 0;
  const w = 16, z = damp / 20;
  return 1 - Math.exp(-z * w * t) * Math.cos(w * Math.sqrt(1 - z * z) * t);
};

/* local fonts */
const h = delayRender('fonts');
const st = document.createElement('style');
st.textContent = `@font-face{font-family:'TJ';font-weight:800;src:url('${staticFile('fonts/Tajawal-ExtraBold.ttf')}')}
@font-face{font-family:'TJ';font-weight:900;src:url('${staticFile('fonts/Tajawal-Black.ttf')}')}
@font-face{font-family:'IN';font-weight:100 900;src:url('${staticFile('fonts/Inter.ttf')}')}`;
document.head.appendChild(st);
Promise.all([document.fonts.load('800 40px TJ', 'أب'), document.fonts.load('900 40px TJ', 'أب'), document.fonts.load('900 40px IN')]).then(() => continueRender(h), () => continueRender(h));

/* ── themes ── */
const THEMES: Record<string, any> = {
  editorial: {ink: '#0E0E0E', accent: '#FF6B1A', hi: '#D7FF3A', paper: '#F4EFE6', red: '#FF3B3B', radius: 0,
    box: (shadow: string, off = 10) => ({border: '6px solid #0E0E0E', boxShadow: `${off}px ${off}px 0 ${shadow}`})},
  gold: {ink: '#070707', accent: '#D4A84B', hi: '#F3D28C', paper: '#F7F1E4', red: '#FF4D6D', radius: 22,
    box: (shadow: string) => ({border: '2px solid #D4A84B', borderRadius: 22, boxShadow: `0 0 0 1px rgba(0,0,0,.4), 0 18px 50px rgba(0,0,0,.45), 0 0 40px ${shadow}33`})},
};
const T = {...THEMES[TL.style || 'editorial'], ...(TL.brand?.colors || {})};
const COLOR = (c?: string) => ({lime: T.hi, hi: T.hi, cream: T.paper, paper: T.paper, red: T.red, accent: T.accent, ink: T.ink} as any)[c || 'paper'] || c;
const AR = "'TJ', sans-serif", EN = "'IN', sans-serif";
const isLatin = (s: string) => /^[\x00-\x7F]+$/.test(s);

type P = {f: number; t: number};
const MAIN_END: number = TL.main_end;

/* ── captions: 3-word chunks, hot word on highlighter ── */
type W = {t: string; s: number; e: number; hot: boolean};
const CHUNKS: W[][] = [];
{
  const ws: W[] = TL.words || [];
  let cur: W[] = [];
  ws.forEach((w, i) => {
    cur.push(w);
    const gap = i + 1 < ws.length ? ws[i + 1].s - w.e : 9;
    if (cur.length >= 3 || gap > 0.45) { CHUNKS.push(cur); cur = []; }
  });
  if (cur.length) CHUNKS.push(cur);
}
const Captions: React.FC<P> = ({f, t}) => {
  if (TL.captions === false || t > MAIN_END) return null;
  const idx = CHUNKS.findIndex((c, i) => t >= c[0].s - 0.05 && (i === CHUNKS.length - 1 || t < CHUNKS[i + 1][0].s - 0.05));
  if (idx < 0) return null;
  const c = CHUNKS[idx];
  if (t > c[c.length - 1].e + 0.45) return null;
  return (
    <div style={{position: 'absolute', top: TL.captionY ?? 1390, left: 60, right: 60, display: 'flex', justifyContent: 'center'}}>
      <div style={{direction: 'rtl', display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'center'}}>
        {c.map((w, i) => {
          const at = F(w.s - 0.05), k = spring(f, at, 9), said = f >= at, bar = ev(f, at, at + 6);
          return (
            <span key={i} style={{position: 'relative', fontFamily: isLatin(w.t) ? EN : AR, fontWeight: 900, fontSize: 70, lineHeight: 1.15, whiteSpace: 'nowrap',
              display: 'inline-block', opacity: said ? 1 : 0, transform: `translateY(${(1 - k) * 30}px) scale(${0.7 + 0.3 * k})`}}>
              {w.hot && <span style={{position: 'absolute', left: -12, right: -12, top: 6, bottom: 2, background: T.hi, border: `4px solid ${T.ink}`,
                borderRadius: T.radius / 2, transform: `scaleX(${bar}) skewX(-10deg)`, transformOrigin: 'right'}} />}
              <span style={{position: 'relative', color: w.hot ? T.ink : T.paper,
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

/* ── B-roll window ── */
const BRoll: React.FC<P> = ({f, t}) => {
  const list: any[] = TL.broll || [];
  const i = list.findIndex((b) => t >= b.a && t < b.b);
  if (i < 0) return null;
  const b = list[i], s = F(b.a), e = F(b.b);
  const kin = ev(f, s, s + 9), kout = ev(f, e - 6, e), dir = i % 2 ? -1 : 1;
  const tilt = (i % 2 ? 2.5 : -2.5) + Math.sin((f - s) / 30) * .6;
  const blur = (1 - kin + kout) * 30;
  const W_ = b.landscape ? 960 : 700, H_ = b.landscape ? 560 : 1000;
  return (
    <div style={{position: 'absolute', left: 0, right: 0, top: b.landscape ? 520 : 360, display: 'flex', justifyContent: 'center'}}>
      <div style={{position: 'relative', transform: `translateX(${(1 - kin) * 1200 * dir - kout * 1200 * dir}px) rotate(${tilt}deg)`, filter: blur > .5 ? `blur(${blur}px)` : undefined}}>
        <div style={{width: W_, height: H_, overflow: 'hidden', background: '#000', ...T.box(T.accent, 14)}}>
          <Sequence from={s} durationInFrames={e - s + 2}><OffthreadVideo src={staticFile(b.src)} muted style={{width: '100%', height: '100%', objectFit: 'cover'}} /></Sequence>
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
  /* footage dims & blurs smoothly behind B-roll / hero / strike windows */
  const wins = [...(TL.broll || []), ...(TL.hero || []), ...(TL.strike || [])];
  const dimK = wins.reduce((a: number, w: any) => Math.max(a, interpolate(t, [w.a - .25, w.a, w.b, w.b + .25], [0, 1, 1, 0], C)), 0);
  /* fix mistakes: zoom into frame during given windows */
  const fix = (TL.fix || []).reduce((a: number, z: any) => Math.max(a, interpolate(t, [z.a - .3, z.a, z.b, z.b + .3], [0, 1, 1, 0], C) * (z.zoom ?? .14)), 0);
  /* punch on cuts & shake on stickers */
  const cuts: number[] = TL.cuts || [];
  const last = [...cuts].reverse().find((c) => t >= c);
  const punch = last !== undefined ? interpolate(t - last, [0, .35], [1.08, 1], {...C, easing: Easing.out(Easing.cubic)}) : 1;
  const shake = (TL.stickers || []).reduce((a: number, s: any) => a + (f >= F(s.at) && f < F(s.at) + 8 ? Math.sin((f - F(s.at)) * 3) * 10 * (1 - (f - F(s.at)) / 8) : 0), 0);
  return (
    <AbsoluteFill style={{background: T.ink}}>
      <AbsoluteFill style={{transform: `translateX(${shake}px) scale(${punch * (1 + fix) * (1 + dimK * .12)})`, transformOrigin: '50% 35%',
        filter: dimK ? `blur(${dimK * 16}px) brightness(${1 - dimK * .45}) saturate(${1 - dimK * .5})` : undefined}}>
        <Sequence durationInFrames={F(MAIN_END)}><OffthreadVideo src={staticFile('main.mp4')} muted style={{width: 1080, height: 1920}} /></Sequence>
        {t >= MAIN_END && <Img src={staticFile('last.png')} style={{width: 1080, height: 1920}} />}
      </AbsoluteFill>
      <Stickers f={f} t={t} />
      <Hero f={f} t={t} />
      <BRoll f={f} t={t} />
      <Strike f={f} t={t} />
      <Chapter f={f} t={t} />
      <Captions f={f} t={t} />
      <EndCard f={f} t={t} />
      <svg style={{position: 'absolute', inset: 0, mixBlendMode: 'overlay', opacity: .1, pointerEvents: 'none'}} width={1080} height={1920}>
        <filter id="g"><feTurbulence type="fractalNoise" baseFrequency="0.85" seed={f % 7} /></filter><rect width={1080} height={1920} filter="url(#g)" /></svg>
    </AbsoluteFill>
  );
};
