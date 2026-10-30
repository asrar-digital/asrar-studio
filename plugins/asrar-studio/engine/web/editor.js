/* ═══ محرر أسرار ستوديو — معاينة حية + تايم لاين + لوحة خصائص ═══ */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;'}[c]));
  const fmt = t => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}.${Math.floor((t % 1) * 10)}`;
  const r1 = v => Math.round(v * 100) / 100;

  /* أنواع العناصر: مصفوفة + حقل البداية/النهاية */
  const KIND = {
    items: {s: 'a', e: 'b', cls: 'it'}, stickers: {s: 'at', e: 'until', cls: 'st'}, hero: {s: 'a', e: 'b', cls: 'el'},
    broll: {s: 'a', e: 'b', cls: 'br'}, strike: {s: 'a', e: 'b', cls: 'el'}, chapters: {s: 'at', e: null, cls: 'ch'},
  };
  const TYPE_AR = {list: 'قائمة', costs: 'تكاليف', compare: 'مقارنة', convert: 'تحويل', bignum: 'رقم كبير', numbers: 'أرقام', quote: 'عبارة', icons: 'أيقونات',
    stickers: 'ملصق', hero: 'عنوان كبير', broll: 'لقطة', strike: 'شطب', chapters: 'فصل', endCard: 'الخاتمة'};
  const NEW = (type, t) => {
    const a = r1(t), b = r1(t + 4);
    return ({
      list: {type, a, b, title: 'العنوان', points: [{text: 'النقطة الأولى', t: r1(t + .6)}, {text: 'النقطة الثانية', t: r1(t + 1.8)}]},
      costs: {type, a, b, title: 'التكاليف', rows: [{label: 'الاشتراك', value: '49 ريال'}, {label: 'الإعلانات', value: '200 ريال'}], total: '249 ريال'},
      compare: {type, a, b, title: '', right: {title: 'الطريقة القديمة', points: ['تعب', 'وقت أطول']}, left: {title: 'الطريقة الجديدة', points: ['أسرع', 'أسهل']}},
      convert: {type, a, b, title: '', from: 'قبل', to: 'بعد'},
      bignum: {type, a, b, value: '300,000', prefix: '', suffix: '', label: 'ريال مبيعات'},
      numbers: {type, a, b, title: '', items: [{value: '978', label: 'طلب'}, {value: '5,371', label: 'زيارة'}]},
      quote: {type, a, b, label: '', text: 'العبارة هنا', hi: 'هنا'},
      icons: {type, a, b, items: [{icon: '📢', label: 'طريقة كلامك'}, {icon: '💻', label: 'الذكاء الاصطناعي'}]},
    })[type];
  };
  const SCHEMA = {
    list: [['title', 'text', 'العنوان'], ['points', 'pts', 'النقاط']],
    costs: [['title', 'text', 'العنوان'], ['rows', 'objs:label=البند,value=المبلغ', 'البنود'], ['total', 'text', 'المجموع (فاضي = بدون)']],
    compare: [['title', 'text', 'العنوان'], ['right.title', 'text', 'العمود الأول (السيئ)'], ['right.points', 'lines', 'نقاطه — كل سطر نقطة'], ['left.title', 'text', 'العمود الثاني (الأفضل)'], ['left.points', 'lines', 'نقاطه — كل سطر نقطة']],
    convert: [['title', 'text', 'العنوان'], ['from', 'text', 'من'], ['to', 'text', 'إلى']],
    bignum: [['value', 'text', 'الرقم (يعدّ تلقائياً)'], ['prefix', 'text', 'قبل الرقم'], ['suffix', 'text', 'بعد الرقم'], ['label', 'text', 'الوصف']],
    numbers: [['title', 'text', 'العنوان'], ['items', 'objs:value=الرقم,label=الوصف', 'الأرقام']],
    quote: [['label', 'text', 'وسم صغير فوق'], ['text', 'area', 'العبارة'], ['hi', 'text', 'الكلمة المميزة (من العبارة)']],
    icons: [['items', 'objs:icon=الأيقونة,label=الاسم', 'الأيقونات']],
    stickers: [['text', 'text', 'النص'], ['color', 'pick:hi=مميز,paper=فاتح,accent=بارز,red=أحمر,ink=داكن', 'اللون']],
    hero: [['emoji', 'text', 'إيموجي'], ['title', 'text', 'العنوان'], ['subtitle', 'text', 'تحت العنوان']],
    broll: [['tag', 'text', 'الوسم']],
    strike: [['items', 'lines', 'المشطوب — كل سطر عنصر']],
    chapters: [['label', 'text', 'اسم الفصل']],
    endCard: [['emoji', 'text', 'إيموجي'], ['title', 'area', 'العنوان'], ['button', 'text', 'الزر'], ['sub', 'text', 'سطر صغير'], ['dur', 'num', 'المدة (ثواني)']],
  };
  const SFX = [['auto', 'تلقائي'], ['whoosh', 'ووش'], ['pop', 'بوب'], ['thud', 'ضربة'], ['ding', 'دينق'], ['tick', 'تك'], ['none', 'بدون']];

  window.openEditor = async function (name) {
    const N = encodeURIComponent(name);
    const api = async (u, o) => { const r = await fetch(u, o); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'خطأ'); return j; };
    const post = (u, b) => api(u, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b || {})});
    let TL = await api(`/api/projects/${N}/pvtl`);
    let DOC = await api(`/api/projects/${N}/doc`);
    const tot = () => TL.total || 1;
    let SEL = null, TAB = 'el', ZOOM = 1, hist = [JSON.stringify(TL)], hpos = 0, saveT = null, firstSave = true, DRAW = null;

    const ed = document.createElement('div'); ed.className = 'ed';
    ed.innerHTML = `
      <div class="ed-top"><button class="ib" id="eBack">→ رجوع</button><span class="nm">${esc(name)}</span>
        <span class="sv" id="eSv">محفوظ</span><button class="ib" id="eUn" title="تراجع">↶</button><button class="ib" id="eRe" title="إعادة">↷</button>
        <button class="ib" id="eWarn">✓ ما فيه تنبيهات</button><button class="btn" id="eExp" style="padding:8px 18px">صدّر المقطع ⬇</button></div>
      <div class="ed-main"><div class="ed-panel"><div class="ed-tabs">
        ${[['el', 'العنصر'], ['look', 'الشكل'], ['cap', 'الكتابة'], ['snd', 'الصوت'], ['ai', 'Claude 🪄']].map(([k, t]) => `<span data-t="${k}">${t}</span>`).join('')}</div><div class="ed-pane" id="ePane"></div></div>
        <div class="ed-stage"><div class="pvbox"><div id="pv"></div><canvas id="eCv" width="1080" height="1920"></canvas></div>
          <div class="drw"><button class="ib" data-d="pen">✏️ قلم</button><button class="ib" data-d="box">▭ مربع</button><button class="ib" data-d="arrow">➜ سهم</button>
            <button class="ib" id="dClr">🗑</button><button class="ib" id="dSend" disabled>📨 أرسل الرسم لـ Claude</button></div></div></div>
      <div class="ed-ins">${['list', 'costs', 'compare', 'convert', 'bignum', 'numbers', 'quote', 'icons'].map(k => `<button class="ib" data-add="${k}">+ ${TYPE_AR[k]}</button>`).join('')}
        <button class="ib" data-add="stickers">+ ملصق</button><button class="ib" data-add="hero">+ عنوان كبير</button><button class="ib" data-add="chapters">+ فصل</button>
        <button class="ib" id="eSplit">✂ اقسم عند المؤشر</button><span class="gap"></span>
        <span class="hint" style="margin:0">تكبير</span><input type="range" class="rng" id="eZm" min="1" max="8" step=".5" value="1" style="width:110px"></div>
      <div class="ed-tl" id="eTl"></div><div class="ed-st" id="eSt"></div>`;
    document.body.append(ed); document.body.style.overflow = 'hidden';

    /* ── المعاينة الحية ── */
    if (!window.AsrarPlayer) await new Promise((ok, bad) => { const s = document.createElement('script'); s.src = '/player.js'; s.onload = ok; s.onerror = bad; document.head.append(s); });
    const asset = p => p.startsWith('fonts/') ? '/fonts/' + p.slice(6) : /^[A-Za-z]:[\\/]|^\//.test(p) ? `/pvabs/${N}?p=${encodeURIComponent(p)}` : `/files/${N}/${p}`;
    AsrarPlayer.mount($('#pv'), TL, asset);
    const P = () => AsrarPlayer.player();
    const now = () => (P() ? P().getCurrentFrame() / 30 : 0);
    const seek = t => P() && P().seekTo(Math.round(Math.max(0, Math.min(tot(), t)) * 30));

    /* ── حفظ تلقائي + تراجع/إعادة ── */
    function changed(redraw = true) {
      AsrarPlayer.update(TL);
      const js = JSON.stringify(TL);
      if (js !== hist[hpos]) { hist = hist.slice(0, hpos + 1); hist.push(js); hpos = hist.length - 1; if (hist.length > 120) { hist.shift(); hpos--; } }
      $('#eSv').textContent = 'يحفظ…'; clearTimeout(saveT);
      saveT = setTimeout(async () => {
        try { await post(`/api/projects/${N}/timeline`, Object.assign({}, TL, {_quiet: !firstSave})); firstSave = false; $('#eSv').textContent = 'محفوظ ✓'; }
        catch (e) { $('#eSv').textContent = '⚠ ما انحفظ'; }
      }, 600);
      undoBtns(); warn();
      if (redraw) { drawTL(); drawPane(); }
    }
    const undoBtns = () => { $('#eUn').disabled = hpos <= 0; $('#eRe').disabled = hpos >= hist.length - 1; };
    function jump(d) { hpos = Math.max(0, Math.min(hist.length - 1, hpos + d)); TL = JSON.parse(hist[hpos]); SEL = null; changed(); }
    $('#eUn').onclick = () => jump(-1); $('#eRe').onclick = () => jump(1);
    document.addEventListener('keydown', kd);
    function kd(e) {
      if (/INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); jump(e.shiftKey ? 1 : -1); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') { e.preventDefault(); jump(1); }
      if ((e.key === 'Delete' || e.key === 'Backspace') && SEL) { e.preventDefault(); delSel(); }
    }

    /* ── العناصر ── */
    function allEls() {
      const out = [];
      Object.entries(KIND).forEach(([k, d]) => (TL[k] || []).forEach((e, i) => {
        const s = e[d.s] ?? 0, en = d.e ? (e[d.e] ?? s + 3) : ((TL[k][i + 1] || {})[d.s] ?? Math.min(tot(), s + 2.5));
        out.push({k, i, e, s, en, cls: d.cls, label: k === 'items' ? TYPE_AR[e.type] + (e.title ? ' · ' + e.title : '') : (e.text || e.title || e.label || e.tag || TYPE_AR[k])});
      }));
      if (TL.endCard) out.push({k: 'endCard', i: 0, e: TL.endCard, s: TL.main_end, en: tot(), cls: 'ec', label: 'الخاتمة'});
      return out;
    }
    const selEl = () => SEL && (SEL.k === 'endCard' ? (TL.endCard && {k: 'endCard', e: TL.endCard}) : (TL[SEL.k] || [])[SEL.i] && {k: SEL.k, e: TL[SEL.k][SEL.i]});
    function setTime(k, e, s, en) {
      if (k === 'endCard') return;
      const d = KIND[k]; s = r1(Math.max(0, Math.min(tot() - .2, s)));
      const shift = s - (e[d.s] ?? 0);
      e[d.s] = s;
      if (d.e && en != null) e[d.e] = r1(Math.max(s + .3, Math.min(tot(), en)));
      if (k === 'items') (e.points || e.rows || e.items || []).forEach(p => { if (p && typeof p === 'object' && p.t != null) p.t = r1(p.t + shift); });
    }
    function addEl(type) {
      const t = now();
      if (['stickers', 'hero', 'chapters'].includes(type)) {
        const e = type === 'stickers' ? {at: r1(t), until: r1(t + 3), text: 'ملصق', x: 140, y: 500, rot: -4, color: 'hi'}
          : type === 'hero' ? {a: r1(t), b: r1(t + 3), emoji: '🔥', title: 'عنوان كبير', subtitle: ''} : {at: r1(t), label: 'فصل جديد'};
        (TL[type] = TL[type] || []).push(e);
        if (type === 'chapters') TL.chapters.sort((x, y) => x.at - y.at);
        SEL = {k: type, i: TL[type].indexOf(e)};
      } else {
        (TL.items = TL.items || []).push(NEW(type, t)); SEL = {k: 'items', i: TL.items.length - 1};
      }
      TAB = 'el'; changed();
    }
    ed.querySelectorAll('[data-add]').forEach(b => b.onclick = () => addEl(b.dataset.add));
    function delSel() {
      const s = selEl(); if (!s) return;
      if (s.k === 'endCard') delete TL.endCard; else TL[s.k].splice(SEL.i, 1);
      SEL = null; changed();
    }
    $('#eSplit').onclick = () => { const t = r1(now()); TL.cuts = [...new Set([...(TL.cuts || []), t])].sort((a, b) => a - b); changed(); toast(`✂ قسمت عند ${fmt(t)}`); };

    /* ── لوحة الخصائص ── */
    ed.querySelectorAll('.ed-tabs span').forEach(s => s.onclick = () => { TAB = s.dataset.t; drawPane(); });
    const get = (o, path) => path.split('.').reduce((a, k) => (a || {})[k], o);
    const put = (o, path, v) => { const ks = path.split('.'); const last = ks.pop(); ks.reduce((a, k) => (a[k] = a[k] || {}), o)[last] = v; };
    function field(o, [path, type, label]) {
      const v = get(o, path), id = 'f' + Math.random().toString(36).slice(2, 8);
      if (type === 'text' || type === 'num') return `<div class="fld"><label>${label}</label><input type="${type === 'num' ? 'number' : 'text'}" step=".1" data-p="${path}" data-ty="${type}" value="${esc(v ?? '')}"></div>`;
      if (type === 'area') return `<div class="fld"><label>${label}</label><textarea data-p="${path}" data-ty="text">${esc(v ?? '')}</textarea></div>`;
      if (type === 'lines') return `<div class="fld"><label>${label}</label><textarea data-p="${path}" data-ty="lines">${esc((v || []).map(x => typeof x === 'string' ? x : x.text).join('\n'))}</textarea></div>`;
      if (type.startsWith('pick:')) return `<div class="fld"><label>${label}</label><div class="seg">${type.slice(5).split(',').map(x => { const [k, t] = x.split('='); return `<span data-p="${path}" data-pk="${k}" class="${v === k ? 'on' : ''}">${t}</span>`; }).join('')}</div></div>`;
      if (type === 'pts') return `<div class="fld"><label>${label}</label>${(v || []).map((p, j) => { p = typeof p === 'string' ? {text: p} : p;
        return `<div class="esub"><div class="hd"><span>${j + 1}</span><b data-rm="${path}" data-j="${j}">حذف</b></div><div class="row2"><input type="text" data-p="${path}.${j}.text" data-ty="text" value="${esc(p.text)}">
          <input type="number" step=".1" data-p="${path}.${j}.t" data-ty="num" value="${p.t ?? ''}" placeholder="الوقت"></div></div>`; }).join('')}<button class="ib" data-addp="${path}">+ نقطة عند المؤشر</button></div>`;
      if (type.startsWith('objs:')) { const keys = type.slice(5).split(',').map(x => x.split('='));
        return `<div class="fld"><label>${label}</label>${(v || []).map((p, j) => `<div class="esub"><div class="hd"><span>${j + 1}</span><b data-rm="${path}" data-j="${j}">حذف</b></div><div class="row2">
          ${keys.map(([k, t]) => `<input type="text" placeholder="${t}" data-p="${path}.${j}.${k}" data-ty="text" value="${esc(p[k] ?? '')}">`).join('')}</div></div>`).join('')}
          <button class="ib" data-addo="${path}" data-keys="${keys.map(k => k[0]).join(',')}">+ إضافة</button></div>`; }
      return '';
    }
    function bind(o) {
      const pane = $('#ePane');
      pane.querySelectorAll('[data-p][data-ty]').forEach(inp => inp.oninput = () => {
        let v = inp.value;
        if (inp.dataset.ty === 'num') v = v === '' ? undefined : +v;
        if (inp.dataset.ty === 'lines') v = v.split('\n').map(s => s.trim()).filter(Boolean);
        put(o, inp.dataset.p, v); changed(false); drawTL();
      });
      pane.querySelectorAll('[data-pk]').forEach(sp => sp.onclick = () => { put(o, sp.dataset.p, sp.dataset.pk); changed(); });
      pane.querySelectorAll('[data-rm]').forEach(b => b.onclick = () => { get(o, b.dataset.rm).splice(+b.dataset.j, 1); changed(); });
      pane.querySelectorAll('[data-addp]').forEach(b => b.onclick = () => { const arr = get(o, b.dataset.addp) || []; arr.push({text: 'نقطة جديدة', t: r1(now())}); put(o, b.dataset.addp, arr); changed(); });
      pane.querySelectorAll('[data-addo]').forEach(b => b.onclick = () => { const arr = get(o, b.dataset.addo) || []; arr.push(Object.fromEntries(b.dataset.keys.split(',').map(k => [k, '']))); put(o, b.dataset.addo, arr); changed(); });
    }
    const seg = (key, opts, cur) => `<div class="seg">${opts.map(([k, t]) => `<span data-sk="${key}" data-sv="${k}" class="${String(cur) === String(k) ? 'on' : ''}">${t}</span>`).join('')}</div>`;
    const rng = (key, min, max, step, val, label) => `<div class="fld"><label>${label} <b id="v_${key.replace(/\./g, '_')}">${val}</b></label><input class="rng" type="range" data-rk="${key}" min="${min}" max="${max}" step="${step}" value="${val}"></div>`;
    function bindCtl(o) {
      const pane = $('#ePane');
      pane.querySelectorAll('[data-sk]').forEach(sp => sp.onclick = () => { let v = sp.dataset.sv; if (v === 'true') v = true; if (v === 'false') v = false; if (/^-?\d+(\.\d+)?$/.test(v)) v = +v; put(o, sp.dataset.sk, v); changed(); });
      pane.querySelectorAll('[data-rk]').forEach(r => r.oninput = () => { put(o, r.dataset.rk, +r.value); const l = $('#v_' + r.dataset.rk.replace(/\./g, '_')); if (l) l.textContent = r.value; changed(false); });
    }

    function drawPane() {
      ed.querySelectorAll('.ed-tabs span').forEach(s => s.classList.toggle('on', s.dataset.t === TAB));
      const pane = $('#ePane');
      if (TAB === 'el') {
        const s = selEl();
        if (!s) { pane.innerHTML = `<p class="hint">اختر عنصر من التايم لاين، أو أضف رسمة من الشريط تحت (تنضاف عند المؤشر).</p>
          <p class="hint">⌨️ مسافة = تشغيل · Ctrl+Z تراجع · Delete حذف العنصر المحدد · اسحب العنصر بالتايم لاين لتحريكه وأطرافه لتغيير مدته.</p>`; return; }
        const {k, e} = s, d = KIND[k] || {}, type = k === 'items' ? e.type : k;
        pane.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px"><b style="color:var(--gold2)">${TYPE_AR[type]}</b>
            <span><button class="ib" id="eDup">تكرار</button> <button class="ib" id="eDel" style="color:var(--bad)">حذف</button></span></div>
          ${k !== 'endCard' ? `<div class="row2"><div class="fld"><label>يبدأ</label><input type="number" step=".1" id="eS" value="${e[d.s] ?? 0}"></div>
            ${d.e ? `<div class="fld"><label>يخلص</label><input type="number" step=".1" id="eE" value="${e[d.e] ?? ''}"></div>` : '<div></div>'}</div>
            <div class="row2" style="margin:-4px 0 12px"><button class="ib" id="eSN">يبدأ من المؤشر</button>${d.e ? '<button class="ib" id="eEN">يخلص عند المؤشر</button>' : ''}</div>` : ''}
          ${k === 'items' ? `<div class="fld"><label>الوضع</label>${seg('layout', [['full', 'فوق الفيديو'], ['split', 'الشاشة مقسومة']], e.layout || 'full')}</div>
            ${rng('y', 150, 1500, 10, e.y ?? 520, 'المكان عمودي')}${rng('x', -400, 400, 10, e.x ?? 0, 'المكان أفقي')}${rng('scale', .4, 1.6, .05, e.scale ?? 1, 'الحجم')}
            <div class="fld"><label>تعتيم الفيديو وراه</label>${seg('dim', [[true, 'إيه'], [false, 'لا']], e.dim !== false)}</div>` : ''}
          ${k === 'stickers' ? `${rng('x', 0, 900, 10, e.x ?? 140, 'المكان أفقي')}${rng('y', 150, 1500, 10, e.y ?? 500, 'المكان عمودي')}${rng('rot', -15, 15, 1, e.rot ?? -4, 'الميلان')}${rng('size', 30, 90, 2, e.size ?? 52, 'الحجم')}` : ''}
          ${k === 'hero' ? rng('y', 200, 1200, 10, e.y ?? 480, 'المكان عمودي') + rng('size', 60, 180, 5, e.size ?? 120, 'حجم العنوان') : ''}
          <h4 style="margin:14px 0 8px">المحتوى</h4>${(SCHEMA[type] || []).map(f => field(e, f)).join('')}
          ${k !== 'chapters' && k !== 'endCard' ? `<div class="fld"><label>الصوت</label>${seg('sfx', SFX, e.sfx || 'auto')}</div>` : ''}`;
        bind(e); bindCtl(e);
        const sv = () => { setTime(k, e, +$('#eS').value, d.e ? +$('#eE').value : null); changed(false); drawTL(); };
        if ($('#eS')) $('#eS').onchange = sv; if ($('#eE')) $('#eE').onchange = sv;
        if ($('#eSN')) $('#eSN').onclick = () => { const len = d.e ? (e[d.e] - e[d.s]) : 0; setTime(k, e, now(), d.e ? now() + len : null); changed(); };
        if ($('#eEN')) $('#eEN').onclick = () => { setTime(k, e, e[d.s], now()); changed(); };
        $('#eDel').onclick = delSel;
        $('#eDup').onclick = () => { if (k === 'endCard') return; const c = JSON.parse(JSON.stringify(e)); const len = d.e ? e[d.e] - e[d.s] : 2; TL[k].push(c); setTime(k, c, (d.e ? e[d.e] : e[d.s]) + .3, (d.e ? e[d.e] : e[d.s]) + .3 + len); SEL = {k, i: TL[k].length - 1}; changed(); };
      } else if (TAB === 'look') {
        const P_ = AsrarPlayer.PALETTES, cur = TL.palette || TL.style || 'editorial', base = P_[cur] || P_.editorial, cc = TL.colors || {};
        pane.innerHTML = `<div class="fld"><label>الباقة</label><div class="pal">${Object.entries(P_).map(([k, p]) => `<div data-pal="${k}" class="${k === cur ? 'on' : ''}">${p.name}<i>${['ink', 'accent', 'hi', 'paper'].map(c => `<b style="background:${p[c]}"></b>`).join('')}</i></div>`).join('')}</div></div>
          <div class="fld"><label>ألوان خاصة (تقلب الباقة)</label>${[['ink', 'الخلفية'], ['paper', 'النص'], ['hi', 'البارز'], ['accent', 'البارز الثاني'], ['red', 'التنبيه']].map(([k, t]) =>
            `<div class="clr"><span>${t}</span><input type="color" data-c="${k}" value="${cc[k] || base[k]}"><a data-cr="${k}">${cc[k] ? 'تلقائي ↺' : 'تلقائي'}</a></div>`).join('')}</div>
          <div class="fld"><label>الإطار</label>${seg('frame', [['hard', 'حاد (جريء)'], ['soft', 'ناعم (فخم)']], TL.frame || (base.hard ? 'hard' : 'soft'))}</div>
          <div class="fld"><label>طابع الحركة</label>${seg('mood', [['calm', 'هادي'], ['formal', 'رسمي'], ['hype', 'حماسي']], TL.mood || 'formal')}</div>
          ${rng('energy', .3, 1.8, .05, TL.energy ?? 1, 'قوة الحركة')}${rng('dim', 0, 1, .05, TL.dim ?? 1, 'تعتيم الفيديو وقت الرسومات')}
          <div class="fld"><label>حبيبات الفيلم</label>${seg('grain', [[true, 'إيه'], [false, 'لا']], TL.grain !== false)}</div>`;
        pane.querySelectorAll('[data-pal]').forEach(d => d.onclick = () => { TL.palette = d.dataset.pal; TL.style = d.dataset.pal === 'editorial' ? 'editorial' : 'gold'; delete TL.frame; changed(); });
        pane.querySelectorAll('[data-c]').forEach(c => c.oninput = () => { TL.colors = Object.assign({}, TL.colors, {[c.dataset.c]: c.value}); changed(false); });
        pane.querySelectorAll('[data-cr]').forEach(a => a.onclick = () => { if (TL.colors) { delete TL.colors[a.dataset.cr]; } changed(); });
        bindCtl(TL);
      } else if (TAB === 'cap') {
        pane.innerHTML = `<div class="fld"><label>الكابشن</label>${seg('captions', [[true, 'ظاهر'], [false, 'مخفي']], TL.captions !== false)}</div>
          <div class="fld"><label>كلمات بكل سطر</label>${seg('captionWords', [[1, '1'], [2, '2'], [3, '3'], [4, '4'], [5, '5']], TL.captionWords ?? 3)}</div>
          ${rng('captionSize', 44, 110, 2, TL.captionSize ?? 70, 'الحجم')}${rng('captionY', 900, 1700, 10, TL.captionY ?? 1390, 'المكان')}
          <div class="clr"><span>لون النص</span><input type="color" id="cC" value="${TL.captionColor || '#ffffff'}"><a id="cCr">تلقائي</a></div>
          <h4 style="margin:16px 0 8px">النص</h4><p class="hint">تصحيح الكلمات وتمييزها من صفحة المشروع ← تبويب النص (يحتاج إعادة قص).</p>`;
        bindCtl(TL);
        $('#cC').oninput = e => { TL.captionColor = e.target.value; changed(false); };
        $('#cCr').onclick = () => { delete TL.captionColor; changed(); };
      } else if (TAB === 'snd') {
        pane.innerHTML = `<div class="fld"><label>المؤثرات الصوتية (ووش، بوب…)</label>${seg('sfx', [[true, 'شغّالة'], [false, 'مطفية']], TL.sfx !== false)}</div>
          <p class="hint">لكل عنصر تختار صوته من تبويب «العنصر»: تلقائي، مخصص، أو بدون. النقاط الصفراء بالتايم لاين = مكان كل صوت.</p>
          <div class="fld"><label>موسيقى خلفية (تنخفض تلقائياً وقت الكلام)</label><input type="text" id="mU" placeholder="مسار ملف الموسيقى على جهازك" value="${esc(TL.music || '')}" dir="ltr"></div>
          <p class="hint">المؤثرات والموسيقى تنسمع بالفيديو المصدّر.</p>`;
        bindCtl(TL);
        $('#mU').onchange = e => { TL.music = e.target.value.trim() || null; changed(false); };
      } else if (TAB === 'ai') {
        const pend = (DOC.notes || []).filter(n => !n.done);
        pane.innerHTML = `<p class="hint">اكتب لـ Claude وش تبي — أو ارسم على الفيديو (فوق) وأرسله. Claude يعدّل الخطة والمعاينة تتحدث.</p>
          <div class="fld"><textarea id="aiT" placeholder="مثال: عند هالثانية حط قائمة بالخطوات الثلاث اللي يقولها"></textarea></div>
          <div class="row2"><button class="ib" id="aiN">+ ملاحظة عند ${fmt(now())}</button><button class="btn" id="aiGo" style="padding:8px">نفّذ الحين</button></div>
          <h4 style="margin:16px 0 8px">الملاحظات</h4>${(DOC.notes || []).map(n => `<div class="esub" style="${n.done ? 'opacity:.5' : ''}"><div class="hd"><span style="cursor:pointer" data-sk2="${n.t}">${fmt(n.t)}</span>${n.done ? '✅' : ''}</div>${esc(n.text)}</div>`).join('') || '<p class="hint">ما فيه</p>'}
          ${pend.length ? `<button class="btn" id="aiRun" style="width:100%;margin-top:8px">نفّذ ${pend.length} ملاحظات بـ Claude</button>` : ''}`;
        pane.querySelectorAll('[data-sk2]').forEach(s => s.onclick = () => seek(+s.dataset.sk2));
        $('#aiN').onclick = async () => { const t = $('#aiT').value.trim(); if (!t) return; await post(`/api/projects/${N}/note`, {t: now(), text: t}); DOC = await api(`/api/projects/${N}/doc`); drawPane(); };
        $('#aiGo').onclick = async () => { const t = $('#aiT').value.trim(); if (!t) return; await flush(); post(`/api/projects/${N}/ask`, {text: `عند الثانية ${now().toFixed(1)}: ${t}`}).then(watchJob).catch(e => alert(e.message)); };
        if ($('#aiRun')) $('#aiRun').onclick = async () => { await flush(); post(`/api/projects/${N}/notes_run`).then(watchJob).catch(e => alert(e.message)); };
      }
    }

    /* ── التايم لاين ── */
    function sfxEvents() {
      if (TL.sfx === false) return [];
      const ev = [];
      (TL.broll || []).forEach(b => b.sfx !== 'none' && ev.push(b.a)); (TL.stickers || []).forEach(s => s.sfx !== 'none' && ev.push(s.at));
      (TL.hero || []).forEach(h => h.sfx !== 'none' && ev.push(h.a + .1)); (TL.chapters || []).slice(1).forEach(c => ev.push(c.at));
      (TL.items || []).forEach(it => { if (it.sfx === 'none') return; ev.push(it.a); if ((it.sfx || 'auto') === 'auto') (it.points || it.rows || it.items || []).forEach((p, k, arr) => ev.push(p && p.t != null ? p.t : it.a + .5 + k * Math.max(.5, (it.b - it.a - 1) / arr.length))); });
      if (TL.endCard) ev.push(TL.main_end + .2);
      return ev;
    }
    function scenes() { const c = [0, ...(TL.cuts || []).filter(x => x > 0 && x < TL.main_end), TL.main_end]; return c.slice(1).map((e, i) => [c[i], e]); }
    function drawTL() {
      const box = $('#eTl'), W = 100 * ZOOM, pc = t => (t / tot() * 100) + '%', T = tot();
      const ticks = []; const step = T / (8 * ZOOM) > 5 ? 10 : T / (8 * ZOOM) > 2 ? 5 : T / (8 * ZOOM) > 1 ? 2 : 1;
      for (let t = 0; t <= T; t += step) ticks.push(t);
      const ws = TL.words || [], sents = []; let cur = [];
      ws.forEach((w, i) => { cur.push(w); const nx = ws[i + 1]; if (!nx || nx.s - w.e > .45 || cur.length >= 8) { sents.push(cur); cur = []; } });
      const els = allEls();
      /* توزيع العناصر على أسطر عشان ما تتراكب */
      const lanes = []; els.sort((a, b) => a.s - b.s).forEach(x => { let L = lanes.findIndex(end => end <= x.s); if (L < 0) { L = lanes.length; lanes.push(0); } lanes[L] = x.en; x.L = L; });
      const nL = Math.max(1, lanes.length);
      box.innerHTML = `<div class="tli" style="width:${W}%">
        <div class="tlr">${ticks.map(t => `<span style="left:${pc(t)}">${Math.round(t)}s</span>`).join('')}</div>
        <div class="tlt" style="height:${nL * 30 + 8}px"><span class="nm">الرسومات</span>${els.map(x => `<div class="bk ${x.cls} ${SEL && SEL.k === x.k && SEL.i === x.i ? 'sel' : ''}" data-k="${x.k}" data-i="${x.i}"
          style="left:${pc(x.s)};width:max(18px,${pc(Math.max(.2, x.en - x.s))});top:${5 + x.L * 30}px"><span class="h l"></span>${esc(x.label)}<span class="h r"></span></div>`).join('')}</div>
        <div class="tlt"><span class="nm">الكتابة</span>${TL.captions === false ? '' : sents.map(s => `<div class="bk cap" data-seek="${s[0].s}" style="left:${pc(s[0].s)};width:${pc(s[s.length - 1].e - s[0].s)}">${esc(s.map(w => w.t).join(' '))}</div>`).join('')}</div>
        <div class="tlt"><span class="nm">المشاهد</span>${scenes().map(([a, b], i) => `<div class="scn" data-sc="${i}" style="left:${pc(a)};width:${pc(b - a)}">${i + 1}</div>`).join('')}
          ${(TL.cuts || []).map(c => `<span class="cutm" data-cut="${c}" style="left:${pc(c)}" title="شيل التقسيم">✂</span>`).join('')}</div>
        <div class="tlt"><span class="nm">المؤثرات</span>${sfxEvents().map(t => `<span class="dot" style="left:${pc(t)}"></span>`).join('')}</div>
        <div class="tlt"><span class="nm">الفيديو</span>${DOC.tl && DOC.tl.strip ? `<div class="img" style="background-image:url('/files/${N}/${DOC.tl.strip}');width:${pc(TL.main_end)}"></div>` : ''}</div>
        <div class="tlt"><span class="nm">الصوت</span>${DOC.tl && DOC.tl.wave ? `<div class="img" style="background-image:url('/files/${N}/${DOC.tl.wave}');width:${pc(TL.main_end)}"></div>` : ''}</div>
        <div class="ph" id="ePh"></div></div>`;
      const inner = box.querySelector('.tli');
      inner.onmousedown = e => { if (e.target.closest('.bk:not(.cap),.scn,.cutm')) return; const r = inner.getBoundingClientRect(); seek((e.clientX - r.left) / r.width * T); };
      box.querySelectorAll('[data-seek]').forEach(b => b.onclick = () => seek(+b.dataset.seek));
      box.querySelectorAll('.cutm').forEach(c => c.onclick = () => { TL.cuts = (TL.cuts || []).filter(x => x !== +c.dataset.cut); changed(); });
      box.querySelectorAll('.scn').forEach(s => s.onclick = () => {
        const [a, b] = scenes()[+s.dataset.sc]; seek(a);
        if (confirm(`المشهد ${+s.dataset.sc + 1} (${fmt(a)} – ${fmt(b)})\nتبي تحذفه من الفيديو؟ (يحتاج تصدير)`)) post(`/api/projects/${N}/cut`, {a, b}).then(reload).catch(e => alert(e.message));
      });
      /* سحب العناصر: الوسط يحرّك، الأطراف تغيّر المدة */
      box.querySelectorAll('.bk[data-k]').forEach(bk => bk.onmousedown = e => {
        e.preventDefault(); e.stopPropagation();
        const k = bk.dataset.k, i = +bk.dataset.i; SEL = {k, i}; TAB = 'el';
        const el = k === 'endCard' ? null : TL[k][i]; const d = KIND[k];
        const mode = e.target.classList.contains('l') ? 'l' : e.target.classList.contains('r') ? 'r' : 'm';
        const r = inner.getBoundingClientRect(), x0 = e.clientX, s0 = el ? el[d.s] : 0, e0 = el && d.e ? el[d.e] : null;
        let moved = false;
        const mv = ev => {
          if (!el) return; const dt = (ev.clientX - x0) / r.width * T; if (Math.abs(ev.clientX - x0) > 2) moved = true;
          if (mode === 'm') setTime(k, el, s0 + dt, e0 != null ? e0 + dt : null);
          else if (mode === 'l') setTime(k, el, Math.min(s0 + dt, (e0 ?? s0 + 9) - .3), e0);
          else if (d.e) setTime(k, el, s0, Math.max(s0 + .3, e0 + dt));
          drawTL(); AsrarPlayer.update(TL);
        };
        const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); if (!moved) seek(el ? el[d.s] : TL.main_end); changed(); };
        document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
      });
    }
    $('#eZm').oninput = e => { ZOOM = +e.target.value; drawTL(); };
    (function loop() { if (!ed.isConnected) return; const ph = $('#ePh'); if (ph) ph.style.left = (now() / tot() * 100) + '%'; requestAnimationFrame(loop); })();

    /* ── التنبيهات ── */
    function warn() {
      const W = [], els = allEls(), cy = TL.captionY ?? 1390;
      els.forEach(x => { if (x.en > tot() + .05) W.push([x.s, `«${x.label}» يطلع بعد نهاية الفيديو`]); if (x.en - x.s < .6 && x.k !== 'chapters') W.push([x.s, `«${x.label}» قصير جداً (أقل من ثانية)`]); });
      (TL.items || []).forEach(it => { if (it.layout !== 'split' && TL.captions !== false && (it.y ?? 520) + 420 * (it.scale ?? 1) > cy) W.push([it.a, `«${TYPE_AR[it.type]}» ممكن يغطي الكابشن — ارفعه شوي`]); });
      (TL.stickers || []).forEach(s => { if ((s.x ?? 140) > 760) W.push([s.at, `ملصق «${s.text}» ممكن يطلع برا الشاشة`]); });
      const big = els.filter(x => ['items', 'hero', 'broll', 'strike'].includes(x.k)).sort((a, b) => a.s - b.s);
      big.forEach((x, j) => { const y = big[j + 1]; if (y && y.s < x.en - .2) W.push([y.s, `«${x.label}» و«${y.label}» متداخلين`]); });
      const ts = [0, ...els.map(x => x.s), TL.main_end].sort((a, b) => a - b);
      ts.forEach((t, j) => { if (j && t - ts[j - 1] > 8) W.push([ts[j - 1], `${(t - ts[j - 1]).toFixed(0)} ثواني بدون أي حركة — المشاهد ممكن يطلع`]); });
      const b = $('#eWarn'); b.textContent = W.length ? `⚠ ${W.length} تنبيه` : '✓ ما فيه تنبيهات'; b.classList.toggle('warn', !!W.length);
      b.onclick = () => { if (!W.length) return; TAB = 'el'; SEL = null; $('#ePane').innerHTML = `<h4 style="margin:0 0 10px">التنبيهات</h4><div class="wl">${W.map(([t, m]) => `<div data-t="${t}">⚠ ${fmt(t)} — ${esc(m)}</div>`).join('')}</div>`;
        $('#ePane').querySelectorAll('[data-t]').forEach(d => d.onclick = () => seek(+d.dataset.t)); };
    }

    /* ── الرسم على الفيديو → Claude ── */
    const cv = $('#eCv'), cx = cv.getContext('2d'); let shapes = [];
    ed.querySelectorAll('[data-d]').forEach(b => b.onclick = () => { DRAW = DRAW === b.dataset.d ? null : b.dataset.d; ed.querySelectorAll('[data-d]').forEach(x => x.classList.toggle('on', x.dataset.d === DRAW)); cv.classList.toggle('on', !!DRAW); if (DRAW && P()) P().pause(); });
    const pos = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) / r.width * 1080, (e.clientY - r.top) / r.height * 1920]; };
    function paint() {
      cx.clearRect(0, 0, 1080, 1920); cx.strokeStyle = '#ff3b3b'; cx.fillStyle = '#ff3b3b'; cx.lineWidth = 12; cx.lineCap = cx.lineJoin = 'round';
      shapes.forEach(s => {
        if (s.k === 'pen') { cx.beginPath(); s.p.forEach(([x, y], i) => i ? cx.lineTo(x, y) : cx.moveTo(x, y)); cx.stroke(); }
        if (s.k === 'box') cx.strokeRect(s.a[0], s.a[1], s.b[0] - s.a[0], s.b[1] - s.a[1]);
        if (s.k === 'arrow') { const [x1, y1] = s.a, [x2, y2] = s.b, an = Math.atan2(y2 - y1, x2 - x1); cx.beginPath(); cx.moveTo(x1, y1); cx.lineTo(x2, y2); cx.stroke();
          cx.beginPath(); cx.moveTo(x2, y2); cx.lineTo(x2 - 50 * Math.cos(an - .45), y2 - 50 * Math.sin(an - .45)); cx.lineTo(x2 - 50 * Math.cos(an + .45), y2 - 50 * Math.sin(an + .45)); cx.fill(); }
      });
      $('#dSend').disabled = !shapes.length;
    }
    cv.onmousedown = e => {
      if (!DRAW) return; const p = pos(e), s = DRAW === 'pen' ? {k: 'pen', p: [p]} : {k: DRAW, a: p, b: p}; shapes.push(s);
      const mv = ev => { const q = pos(ev); if (s.k === 'pen') s.p.push(q); else s.b = q; paint(); };
      const up = () => { document.removeEventListener('mousemove', mv); document.removeEventListener('mouseup', up); };
      document.addEventListener('mousemove', mv); document.addEventListener('mouseup', up);
    };
    $('#dClr').onclick = () => { shapes = []; paint(); };
    $('#dSend').onclick = async () => {
      const text = prompt('وش تبي Claude يسوي هنا؟', 'عدّل المكان اللي أشّرت عليه'); if (text === null) return;
      await post(`/api/projects/${N}/annotate`, {t: now(), png: cv.toDataURL('image/png'), text});
      shapes = []; paint(); DOC = await api(`/api/projects/${N}/doc`); TAB = 'ai'; drawPane(); toast('📨 انضاف الرسم لملاحظات Claude');
    };

    /* ── التصدير + متابعة الشغل ── */
    const toast = (m, ms = 2500) => { const s = $('#eSt'); s.textContent = m; s.style.display = 'block'; clearTimeout(s._t); if (ms) s._t = setTimeout(() => s.style.display = 'none', ms); };
    async function flush() { if (saveT) { clearTimeout(saveT); await post(`/api/projects/${N}/timeline`, Object.assign({}, TL, {_quiet: !firstSave})); firstSave = false; $('#eSv').textContent = 'محفوظ ✓'; } }
    async function reload() { TL = await api(`/api/projects/${N}/pvtl`); DOC = await api(`/api/projects/${N}/doc`); hist = [JSON.stringify(TL)]; hpos = 0; AsrarPlayer.update(TL); undoBtns(); warn(); drawTL(); drawPane(); }
    function watchJob() {
      $('#eExp').disabled = true;
      const iv = setInterval(async () => {
        const p = await api(`/api/projects/${N}`).catch(() => null); if (!p) return;
        toast('⏳ ' + (p.status.msg || 'يشتغل…'), 0);
        if (!p.running && p.status.state !== 'run') {
          clearInterval(iv); $('#eExp').disabled = false;
          if (p.status.state === 'error') toast('❌ ' + p.status.msg, 6000);
          else { const m = p.outputs.find(o => o.includes('تيك')) || p.outputs[0]; await reload(); toast('✅ جاهز' + (m ? ' — حمّله من صفحة المشروع' : ''), 6000); if (window.coursePop) coursePop('done'); }
        }
      }, 2000);
    }
    $('#eExp').onclick = async () => { await flush(); post(`/api/projects/${N}/rebuild`).then(watchJob).catch(e => alert(e.message)); };
    $('#eBack').onclick = async () => { await flush(); document.removeEventListener('keydown', kd); ed.remove(); document.body.style.overflow = ''; if (window.onEditorClose) onEditorClose(); };

    undoBtns(); warn(); drawTL(); drawPane();
    if (!(TL.words || []).length) toast('المعاينة تحتاج المشروع يخلص القص أول', 5000);
  };
})();
