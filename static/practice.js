/* Öva (genererade övningar) och Övningsportfölj (pappershandel). Använder hjälpare från app.js (esc, nf, pct, cls, api, dialog, toast ...). */

const PR = { mode: null, kind: 'all', sess: { n: 0, ok: 0 }, horizon: 120, ticker: null };
const PCOL = { price: '#5aa0ff', sma50: '#e8b34a', sma200: '#b07cf0', bench: '#9aa4b2', future: '#2fc07a' };

/* ------------------------------------------------------------------ SVG-diagram */
function svgPanel(panel, o = {}) {
  const W = 720, H = panel.small ? 120 : 240, L = 46, R = 12, T = 10, B = 16;
  const fut = o.future || null;
  const hist = panel.series[0].y.length;
  const n = hist + (fut ? fut.length : 0);
  const vals = [];
  panel.series.forEach(s => s.y.forEach(v => v != null && vals.push(v)));
  if (fut) fut.forEach(v => v != null && vals.push(v));
  (panel.hlines || []).forEach(h => vals.push(h.y));
  if (o.hline != null) vals.push(o.hline);
  let lo = panel.ymin != null ? panel.ymin : Math.min(...vals), hi = panel.ymax != null ? panel.ymax : Math.max(...vals);
  if (o.range) { lo = Math.min(lo, o.range[0]); hi = Math.max(hi, o.range[1]); }
  if (panel.ymin == null) { const p = (hi - lo) * 0.06 || 1; lo -= p; hi += p; }
  const X = i => L + (i / Math.max(n - 1, 1)) * (W - L - R);
  const Y = v => T + (1 - (v - lo) / ((hi - lo) || 1)) * (H - T - B);
  const path = (ys, off = 0) => { let d = '', pen = false; ys.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + X(i + off).toFixed(1) + ',' + Y(v).toFixed(1); pen = true; }); return d; };
  const dec = (hi - lo) < 12 ? 1 : 0;
  let g = '';
  for (let k = 0; k <= 4; k++) {
    const v = lo + (hi - lo) * k / 4, y = Y(v);
    g += `<line x1="${L}" x2="${W - R}" y1="${y.toFixed(1)}" y2="${y.toFixed(1)}" stroke="#243044" stroke-width="1"/><text x="${L - 6}" y="${(y + 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#8995a8">${nf(v, dec)}</text>`;
  }
  (panel.hlines || []).forEach(h => { g += `<line x1="${L}" x2="${W - R}" y1="${Y(h.y).toFixed(1)}" y2="${Y(h.y).toFixed(1)}" stroke="#e8b34a" stroke-dasharray="5 4" stroke-width="1.2"/><text x="${W - R - 4}" y="${(Y(h.y) - 4).toFixed(1)}" text-anchor="end" font-size="11" fill="#e8b34a">${esc(h.label)}</text>`; });
  panel.series.forEach(s => { g += `<path d="${path(s.y)}" fill="none" stroke="${PCOL[s.cls] || '#5aa0ff'}" stroke-width="${s.cls === 'price' ? 1.8 : 1.4}" ${s.dash ? 'stroke-dasharray="4 3"' : ''}/>`; });
  if (fut) {
    const x0 = X(hist - 1);
    g += `<line x1="${x0.toFixed(1)}" x2="${x0.toFixed(1)}" y1="${T}" y2="${H - B}" stroke="#5d6a7f" stroke-dasharray="3 3"/><text x="${(x0 + 5).toFixed(1)}" y="${T + 10}" font-size="11" fill="#8995a8">här köper du</text>`;
    g += `<path d="${path([panel.series[0].y[hist - 1]].concat(fut), hist - 1)}" fill="none" stroke="${PCOL.future}" stroke-width="1.8"/>`;
    if (o.exit) g += `<circle cx="${X(hist - 1 + o.exit.day).toFixed(1)}" cy="${Y(o.exit.price).toFixed(1)}" r="5" fill="#f0605d" stroke="#0c1016" stroke-width="1.5"/>`;
  }
  if (o.hline != null) g += `<line x1="${L}" x2="${W - R}" y1="${Y(o.hline).toFixed(1)}" y2="${Y(o.hline).toFixed(1)}" stroke="#f0605d" stroke-dasharray="6 4" stroke-width="1.6"/><text x="${L + 4}" y="${(Y(o.hline) - 5).toFixed(1)}" font-size="11.5" fill="#f0605d">${esc(o.hlineLabel || '')}</text>`;
  const leg = panel.series.length > 1 ? `<div class="svg-leg">${panel.series.map(s => `<span><i style="background:${PCOL[s.cls] || '#5aa0ff'}"></i>${esc(s.name)}</span>`).join('')}</div>` : '';
  return `<div class="svgwrap">${panel.title ? `<div class="svg-title">${esc(panel.title)}</div>` : ''}<svg class="svgchart" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>${leg}</div>`;
}
function panelsHTML(chart, extra = {}) {
  const shared = {};
  chart.panels.forEach(p => {
    if (p.shared) {
      const v = p.series.flatMap(s => s.y.filter(x => x != null));
      const r = shared[p.shared] || [Infinity, -Infinity];
      shared[p.shared] = [Math.min(r[0], ...v), Math.max(r[1], ...v)];
    }
  });
  return chart.panels.map((p, i) => svgPanel(p, { ...(i === 0 ? extra : {}), range: p.shared ? shared[p.shared] : null })).join('');
}

/* ------------------------------------------------------------------ Öva: nav */
const PR_MODES = [
  ['chart', '📈', 'Läs diagrammet', 'Frågor om riktiga diagram med dolda namn: medelvärden, RSI, nedgång, volatilitet, toppar och relativ styrka.', 'chart'],
  ['risk', '🧮', 'Riskräknaren', 'Räkna positionsstorlek, R-multiplar och förväntat värde. Nya tal varje gång.', 'risk'],
  ['flaw', '🔍', 'Hitta felet', 'Granska en fiktiv portfölj och peka ut största risken. Ibland är rätt svar att det inte finns något fel.', 'flaw'],
  ['stopex', '🛑', 'Stoppövning', 'Placera stoppet själv på ett diagram och se vad som hände efteråt. Bedöms på hur du placerar det, inte på tur.', 'stopex'],
  ['stopsim', '🧪', 'Stoppsimulator', 'Jämför stopptyper över hundratals historiska affärer i en aktie i stället för ett enda utfall.', 'stopsim'],
  ['cards', '🗂', 'Repetitionskort', 'Repetera begreppen i Ordlistan med växande mellanrum. Det du missar kommer tillbaka oftare.', 'card'],
  ['stress', '🌪', 'Stresstest', 'Räkna ut vad en kraftig nedgång, ett gap genom stoppen eller ett risktak betyder för en portfölj. Nya tal varje gång.', 'stress'],
  ['spur', '🔗', 'Samband eller slump', 'Hittar man samband mellan bolag av ren slump? Gissa hur starka de bästa sambanden blir när allt är slumpat, och hur många som ser ut att vara äkta.', 'spur'],
  ['luck', '🎲', 'Tur eller skicklighet', 'Hur mycket kan slumpen ge? Serier av vinster och förluster som ser ut som skicklighet, och hur långa förlustserier som är normala.', 'luck'],
  ['bias', '🧠', 'Beteendefällor', 'Korta scenarier där du pekar ut tankevurpan: förlustaversion, FOMO, bekräftelsebias och fler. Varje svar ger ett motmedel.', 'bias'],
];
const PR_TOOLS = [
  ['playbook', '📕', 'Spelbok', 'Dina skriftliga regler: vad du letar efter, när du köper och säljer, hur stor du får vara och när du inte handlar. Skrivs i lugn och ro för de tillfällen när känslan säger något annat.', 'playbook'],
  ['monthly', '🗓', 'Månadsgranskning', 'Titta tillbaka på månaden: siffror hämtas automatiskt ur din övningsportfölj, du skriver vad som gick bra, sämre och vad du ändrar.', 'monthly'],
  ['riskpanel', '🛡', 'Riskpanel', 'Stresstesta dina övningsportföljer mot dina egna gränser och se om du hållit dem de senaste 60 handelsdagarna.', 'riskpanel'],
  ['stats', '📊', 'Handelsstatistik', 'Snitt i R, träffandel, längsta förlustserie och mer, alltid med osäkerhetsintervall. Jämför två strategier.', 'stats'],
  ['rules', '🔬', 'Regeltest', 'Skriv en hypotes, sätt ihop en regel och testa den mot historiken: mot slumpen, mot halva perioden och mot hur många regler du redan provat.', 'rules'],
  ['profile', '🪪', 'Handlarprofil', 'Hela bilden samlad: statistik, process, risk, Spelbok och lärdomar, plus ett ärligt utlåtande om du har en påvisbar fördel.', 'profile'],
];
const ALL_PR = () => [...PR_MODES, ...PR_TOOLS];
const glossKeys = () => Object.keys(GLOSSARY).filter(k => !GLOSSARY[k].plan);
const sessLine = () => PR.sess.n ? `<span class="mut small">Den här omgången: ${PR.sess.ok} av ${PR.sess.n} rätt</span>` : '';

async function viewPractice(v, rid) {
  const st = await api('/practice/stats');
  if (stale(rid)) return;
  if (!PR.mode) {
    let due = null;
    try { due = await api('/practice/cards/due', { method: 'POST', body: { keys: glossKeys() } }); } catch (e) { /* ok */ }
    let tr = null;
    try { const [pb, mo] = await Promise.all([api('/trader/playbook'), api('/trader/monthly')]); tr = { playbook: pb, months: mo.months, older: mo.older }; } catch (e) { /* ok */ }
    if (stale(rid)) return;
    const line = (k) => {
      const s = st[k];
      if (k === 'card') return due ? `${due.stats.due + due.new.length} att repetera nu · ${due.stats.mastered} av ${due.stats.total} begrepp bemästrade` : `${s.n} repetitioner gjorda`;
      if (k === 'stopsim') return `${s.n} ${s.n === 1 ? 'körning' : 'körningar'}`;
      if (k === 'stopex') return `${s.n} gjorda`;
      if (k === 'playbook') return tr && tr.playbook.complete ? 'Alla sex avsnitt skrivna' : `${tr ? tr.playbook.sections.filter(x => x.ok).length : 0} av 6 avsnitt skrivna`;
      if (k === 'monthly') return tr ? (n => n + (n === 1 ? ' månad granskad' : ' månader granskade'))(tr.months.filter(m => m.done).length + tr.older.length) : '';
      if (['riskpanel', 'stats', 'rules', 'profile'].includes(k)) return '';
      return s.n ? `${s.n} gjorda · ${s.recent_n ? nf(s.recent_correct / s.recent_n * 100, 0) + ' % rätt senaste ' + s.recent_n : ''}` : 'Inte påbörjad';
    };
    const cardH = ([k, ic, t, d, sk]) => `<div class="card pr-card" data-m="${k}"><div class="pr-ic">${ic}</div><h4>${esc(t)}</h4><div class="mut small">${esc(d)}</div><div class="pr-stat">${esc(line(sk))}</div><button class="btn primary sm">${PR_TOOLS.some(x => x[0] === k) ? 'Öppna' : 'Starta'}</button></div>`;
    v.innerHTML = guide('practice') + `<h3 class="sec-h">Övningar</h3><div class="pr-grid">${PR_MODES.map(cardH).join('')}</div>
      <h3 class="sec-h">Handlarens verktyg</h3><div class="pr-grid">${PR_TOOLS.map(cardH).join('')}
      <div class="card pr-card" data-m="__paper"><div class="pr-ic">🧾</div><h4>Övningsportfölj</h4><div class="mut small">Handla med låtsaspengar till riktiga kurser. Varje köp kräver tes, stopp och rätt storlek. Du får processpoäng, inte vinstpoäng.</div><div class="pr-stat">Egen flik</div><button class="btn primary sm">Öppna</button></div></div>
      <div class="disclaimer">Övningarna är utbildning, inte råd. Poäng i spelläget ges för att du övar och för objektiva facit, aldrig för vinst på enskilda kursrörelser.</div>`;
    bindGuides();
    $$('.pr-card').forEach(c => c.onclick = () => { if (c.dataset.m === '__paper') { S.tab = 'paper'; renderTabs(); renderView(); return; } PR.mode = c.dataset.m; PR.sess = { n: 0, ok: 0 }; renderView(); });
    return;
  }
  const mode = ALL_PR().find(m => m[0] === PR.mode);
  v.innerHTML = `<div class="panel"><div class="panel-head"><div><button class="btn sm" id="pr-back">← Alla övningar</button> <b style="margin-left:10px">${mode[1]} ${esc(mode[2])}</b></div><div id="pr-sess">${sessLine()}</div></div><div id="pr-body"></div></div>`;
  $('#pr-back').onclick = () => { PR.mode = null; renderView(); };
  const fn = { chart: modeChart, risk: modeRisk, flaw: modeFlaw, stopex: modeStopex, stopsim: modeStopsim, cards: modeCards, bias: modeBias, stress: modeStress, luck: modeLuck, spur: modeSpur, playbook: modePlaybook, monthly: modeMonthly, riskpanel: modeRiskpanel, stats: modeStats, rules: modeRules, profile: modeProfile }[PR.mode];
  await fn($('#pr-body'), rid);
}
function sessUpdate(ok) {
  PR.sess.n++;
  if (ok) PR.sess.ok++;
  const e = $('#pr-sess');
  if (e) e.innerHTML = sessLine();
  if (typeof gameCheck === 'function') gameCheck();
}
const fbHTML = (ok, text, extra = '') => `<div class="fb ${ok ? 'good' : 'bad'}"><b>${ok ? 'Rätt.' : 'Inte riktigt.'}</b> ${text}${extra}</div><div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="pr-next">Nästa uppgift</button></div>`;

/* ------------------------------------------------------------------ Läs diagrammet */
async function modeChart(body, rid) {
  const kinds = [['all', 'Alla blandat'], ['sma_cross', 'Medelvärden'], ['drawdown', 'Nedgång'], ['rsi', 'RSI'], ['volatility', 'Volatilitet'], ['breakout', 'Toppar'], ['rs', 'Relativ styrka']];
  body.innerHTML = `<div class="seg" id="pr-kinds" style="margin-bottom:12px">${kinds.map(([k, l]) => `<button data-k="${k}" class="${PR.kind === k ? 'on' : ''}">${l}</button>`).join('')}</div><div id="pr-ex"></div>`;
  $$('#pr-kinds button').forEach(b => b.onclick = () => { PR.kind = b.dataset.k; $$('#pr-kinds button').forEach(x => x.classList.toggle('on', x === b)); load(); });
  const load = async () => {
    const ex = $('#pr-ex');
    ex.innerHTML = '<div class="loading">Hämtar uppgift…</div>';
    let q;
    try { q = await api('/practice/chart' + (PR.kind !== 'all' ? '?kind=' + PR.kind : '')); } catch (e) { ex.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    ex.innerHTML = `<p class="q-text"><b>${esc(q.title)}${/[?.!]$/.test(q.title) ? '' : '.'}</b> ${esc(q.q)}</p>${panelsHTML(q.chart)}<div class="q-opts">${q.options.map(o => `<button class="q-opt" data-i="${o.i}">${esc(o.text)}</button>`).join('')}</div><div id="pr-fb"></div>`;
    $$('.q-opt', ex).forEach(b => b.onclick = async () => {
      $$('.q-opt', ex).forEach(x => x.disabled = true);
      try {
        const a = await api('/practice/chart/answer', { method: 'POST', body: { token: q.token, choice: +b.dataset.i } });
        $$('.q-opt', ex).forEach(x => { if (+x.dataset.i === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
        $('#pr-fb').innerHTML = fbHTML(a.correct, esc(a.why), `<div class="small mut" style="margin-top:6px">Det här var ${esc(a.reveal.name)} (${esc(a.reveal.ticker)}), ${esc(a.reveal.date)}.</div>`);
        $('#pr-next').onclick = load;
        sessUpdate(a.correct);
      } catch (e) { toast(e.message, true); }
    });
  };
  await load();
}

/* ------------------------------------------------------------------ Riskräknaren */
async function modeRisk(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar uppgift…</div>';
    const q = await api('/practice/risk');
    body.innerHTML = `<p class="q-text">${esc(q.q)}</p><div class="row-add"><input id="rk-in" inputmode="decimal" placeholder="Ditt svar" autocomplete="off" style="max-width:180px"> <span class="mut" style="align-self:center">${esc(q.unit)}</span> <button class="btn primary" id="rk-go">Svara</button></div><div id="pr-fb"></div>
      <div class="small mut">Tips: räkna ut det på papper först. ${q.unit === 'aktier' ? 'Avrunda nedåt: du kan inte köpa en halv aktie.' : ''}</div>`;
    const inp = $('#rk-in');
    inp.focus();
    const go = async () => {
      const val = parseFloat(inp.value.replace(/\s/g, '').replace(',', '.'));
      if (isNaN(val)) { toast('Skriv ett tal', true); return; }
      $('#rk-go').disabled = true; inp.disabled = true;
      const a = await api('/practice/risk/answer', { method: 'POST', body: { token: q.token, value: val } });
      $('#pr-fb').innerHTML = fbHTML(a.correct, esc(a.why), `<div class="small" style="margin-top:6px">Rätt svar: <b>${nf(a.answer, a.decimals)} ${esc(a.unit)}</b>${a.correct ? '' : ` (du skrev ${nf(val, a.decimals)})`}</div>`);
      $('#pr-next').onclick = load;
      sessUpdate(a.correct);
    };
    $('#rk-go').onclick = go;
    inp.onkeydown = e => { if (e.key === 'Enter') go(); };
  };
  await load();
}

/* ------------------------------------------------------------------ Hitta felet */
async function modeFlaw(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar portfölj…</div>';
    const q = await api('/practice/flaw');
    body.innerHTML = `<p class="q-text">${esc(q.q)}</p>
      <div class="tbl-scroll"><table><thead><tr><th class="l">Innehav</th><th class="l">Bransch</th><th>Valuta</th><th>Vikt</th><th class="l">Anmärkning</th></tr></thead><tbody>
      ${q.rows.map(r => `<tr><td class="l">${esc(r.name)}</td><td class="l">${esc(r.sector)}</td><td>${esc(r.cur)}</td><td>${nf(r.w, 1)} %</td><td class="l mut small">${esc(r.extra || '')}</td></tr>`).join('')}
      ${q.note ? `<tr><td class="l mut" colspan="5">${esc(q.note)}</td></tr>` : ''}</tbody></table></div>
      <div class="q-opts" style="margin-top:12px">${q.options.map(o => `<button class="q-opt" data-k="${o.key}">${esc(o.text)}</button>`).join('')}</div><div id="pr-fb"></div>`;
    $$('.q-opt', body).forEach(b => b.onclick = async () => {
      $$('.q-opt', body).forEach(x => x.disabled = true);
      const a = await api('/practice/flaw/answer', { method: 'POST', body: { token: q.token, choice: b.dataset.k } });
      $$('.q-opt', body).forEach(x => { if (x.dataset.k === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
      $('#pr-fb').innerHTML = fbHTML(a.correct, `Svaret var: <b>${esc(a.answer_text)}.</b> ${esc(a.why)}`);
      $('#pr-next').onclick = load;
      sessUpdate(a.correct);
    });
  };
  await load();
}

/* ------------------------------------------------------------------ Stoppövning */
async function modeStopex(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar diagram…</div>';
    let q;
    try { q = await api('/practice/stopex'); } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    const panel = q.chart.panels[0];
    body.innerHTML = `<p class="q-text">Du köper vid sista kursen i diagrammet (<b>${nf(q.entry, 2)}</b>). Var lägger du stoppet? Dra i reglaget. Det vanliga dagsbruset (ATR${info('atr')}) är <b>${nf(q.atr_pct, 1)} %</b> av kursen.</p>
      <div id="sx-chart"></div>
      <div class="row-add" style="align-items:center"><input type="range" id="sx-r" min="0.5" max="25" step="0.5" value="6" style="flex:1;min-width:200px"><button class="btn primary" id="sx-go">Lås stoppet</button></div>
      <div id="sx-info" class="small"></div><div id="pr-fb"></div>`;
    const draw = (p, extra = {}) => { $('#sx-chart').innerHTML = svgPanel(panel, { hline: q.entry * (1 - p / 100), hlineLabel: 'Ditt stopp', ...extra }); };
    const info1 = () => {
      const p = +$('#sx-r').value, stop = q.entry * (1 - p / 100), mult = (q.entry * p / 100) / q.atr;
      const pos = 1 / p * 100;
      draw(p);
      $('#sx-info').innerHTML = `Stopp <b>${nf(stop, 2)}</b> (−${nf(p, 1)} %) · <b>${nf(mult, 1)} ATR</b> från ingången · riskerar du 1 % av portföljen blir positionen <b class="${pos > 25 ? 'neg' : ''}">${nf(pos, 0)} %</b> av portföljen${pos > 25 ? ' (över 25 %-gränsen)' : ''}`;
    };
    $('#sx-r').oninput = info1;
    info1();
    $('#sx-go').onclick = async () => {
      const p = +$('#sx-r').value;
      $('#sx-go').disabled = true; $('#sx-r').disabled = true;
      const a = await api('/practice/stopex/answer', { method: 'POST', body: { token: q.token, stop_pct: p } });
      draw(p, { future: a.future.series[0].y, exit: a.stopped ? { day: a.exit_day, price: a.exit_price } : null });
      const out = a.stopped
        ? `Stoppet löste ut dag ${a.exit_day} och du fick ${nf(a.exit_price, 2)} (<b class="${cls(a.result_pct)}">${pct(a.result_pct)}</b>)${a.gap ? '. Aktien öppnade under stoppet, så du fick öppningskursen: det kallas gap' : ''}.${a.whipsaw ? ' Kursen gick sedan över din ingångskurs: du blev utskakad.' : ''}`
        : `Stoppet löste inte ut under de 60 dagarna. Resultat efter 60 dagar: <b class="${cls(a.result_pct)}">${pct(a.result_pct)}</b>.`;
      $('#pr-fb').innerHTML = `<div class="fb ${a.verdict === 'ok' ? 'good' : 'warn'}"><b>${a.verdict === 'ok' ? 'Bra placerat.' : a.verdict === 'inside' ? 'Nära bruset.' : 'Långt bort.'}</b> ${esc(a.verdict_text)}</div>
        <p>${out}</p><p class="small">Lägsta kurs under perioden var ${pct(a.mae_pct)} från ingången. Ett ATR-stopp (3 × ATR, ${nf(a.atr_stop, 2)}) hade ${a.atr_stop_hit ? 'löst ut' : 'inte löst ut'}. Det var <b>${esc(a.reveal.name)}</b> (${esc(a.reveal.ticker)}), ${esc(a.reveal.date)}.</p>
        <div class="disclaimer">${esc(a.disclaimer)}</div><div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="pr-next">Nästa uppgift</button></div>`;
      $('#pr-next').onclick = load;
      sessUpdate(a.verdict === 'ok');
    };
  };
  await load();
}

/* ------------------------------------------------------------------ Stoppsimulator */
async function modeStopsim(body) {
  let pool;
  try { pool = (await api('/practice/pool')).tickers; } catch (e) { body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (!pool.length) { body.innerHTML = '<div class="empty">För lite kursdata. Tryck Uppdatera först.</div>'; return; }
  if (!PR.ticker || !pool.find(p => p.ticker === PR.ticker)) PR.ticker = pool[0].ticker;
  body.innerHTML = `<p class="q-text">Välj en aktie och hur länge varje affär hålls. Appen går in på hundratals olika dagar i historien och testar alla stopptyper på exakt samma affärer.</p>
    <div class="row-add"><select id="ss-t" style="max-width:280px">${pool.map(p => `<option value="${esc(p.ticker)}" ${p.ticker === PR.ticker ? 'selected' : ''}>${esc(p.ticker)} – ${esc(p.name)}</option>`).join('')}</select>
    <div class="seg" id="ss-h">${[[60, '60 dagar'], [120, '120 dagar'], [250, '1 år']].map(([k, l]) => `<button data-v="${k}" class="${PR.horizon === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <button class="btn primary" id="ss-go">Kör simuleringen</button></div><div id="ss-out"></div>`;
  $$('#ss-h button').forEach(b => b.onclick = () => { PR.horizon = +b.dataset.v; $$('#ss-h button').forEach(x => x.classList.toggle('on', x === b)); });
  $('#ss-t').onchange = e => { PR.ticker = e.target.value; };
  $('#ss-go').onclick = async () => {
    const out = $('#ss-out');
    out.innerHTML = '<div class="loading">Simulerar…</div>';
    let r;
    try { r = await api(`/practice/stopsim?ticker=${encodeURIComponent(PR.ticker)}&horizon=${PR.horizon}`); } catch (e) { out.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (typeof gameCheck === 'function') gameCheck();
    const f = (v, d = 1) => v == null ? '–' : nf(v, d) + ' %';
    out.innerHTML = `<div class="small mut" style="margin:6px 0">${esc(r.name)} · ${esc(r.from)} till ${esc(r.to)} · varje affär hålls högst ${r.horizon} dagar · ungefär ${nf(r.n_eff, 0)} oberoende affärer</div>
      <div class="tbl-scroll"><table><thead><tr><th class="l">Regel</th><th>Snitt</th><th>Median</th><th>Vinnare</th><th>Utlöst</th><th>Utskakad${info('whipsaw')}</th><th>Sämsta 10 %</th><th>Sämsta</th><th>Gap${info('gapfill')}</th></tr></thead><tbody>
      ${r.rules.map(x => `<tr><td class="l">${esc(x.label)}</td><td class="${cls(x.mean)}">${f(x.mean)}</td><td class="${cls(x.median)}">${f(x.median)}</td><td>${f(x.win, 0)}</td><td>${x.rule === 'none' ? '–' : f(x.stopped, 0)}</td><td>${f(x.whipsaw, 0)}</td><td class="${cls(x.tail10)}">${f(x.tail10)}</td><td class="${cls(x.worst)}">${f(x.worst)}</td><td>${x.rule === 'none' ? '–' : x.gaps}</td></tr>`).join('')}</tbody></table></div>
      <div class="hint">Utskakad = andel av de utlösta affärerna där aktien ändå slutade högre efter ${r.horizon} dagar än där stoppet sålde. Sämsta 10 % = snittet av de 10 % sämsta affärerna.</div>
      <ul class="plain">${r.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul>
      <div class="invalid" style="margin-top:10px"><b>Förbehåll:</b><ul class="plain" style="margin:6px 0 0">${r.caveats.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>`;
  };
}

/* ------------------------------------------------------------------ Repetitionskort */
async function modeCards(body) {
  const keys = glossKeys();
  const d = await api('/practice/cards/due', { method: 'POST', body: { keys } });
  const queue = [...d.due, ...d.new];
  const total = queue.length, st = d.stats;
  const head = `<div class="small mut" style="margin-bottom:10px">${st.known} kort påbörjade · ${st.mastered} bemästrade (box 4 eller högre) · ${st.unseen} nya kvar att lära${info('spaced')}</div>`;
  if (!total) {
    body.innerHTML = head + '<div class="fb good"><b>Klart för idag.</b> Inga kort att repetera just nu. Kom tillbaka imorgon: det är spridningen över dagar som gör att kunskapen fastnar.</div>';
    return;
  }
  let done = 0, seenBack = false;
  const show = () => {
    if (!queue.length) { body.innerHTML = head + `<div class="fb good"><b>Bra jobbat.</b> Du repeterade ${done} kort. Korten du missade kommer tillbaka snart.</div>`; if (typeof gameCheck === 'function') gameCheck(); return; }
    const k = queue[0], g = GLOSSARY[k];
    seenBack = false;
    body.innerHTML = head + `<div class="flash"><div class="small mut">Kort ${Math.min(done + 1, total)} av ${total}${queue.length + done > total ? ' (inklusive omtag)' : ''} · ${esc(g.cat)}</div><h3 class="flash-t">${esc(g.t)}</h3><div class="mut">Förklara begreppet för dig själv med egna ord. Vänd sedan kortet.</div>
      <div id="fc-back" hidden><div class="g-short" style="margin-top:12px"><b>I korthet:</b> ${esc(g.s)}</div><p>${esc(g.what)}</p>${g.ex ? `<p class="g-ex">${esc(g.ex)}</p>` : ''}${g.watch ? `<p class="small"><b>Tänk på:</b> ${esc(g.watch)}</p>` : ''}</div>
      <div class="dlg-actions" id="fc-act"><span></span><button class="btn primary" id="fc-flip">Visa svaret</button></div></div>`;
    $('#fc-flip').onclick = () => {
      $('#fc-back').hidden = false;
      if (typeof track === 'function') track('gloss', k);
      $('#fc-act').innerHTML = `<button class="btn" data-g="again">Kunde inte</button><button class="btn" data-g="hard">Osäker</button><button class="btn primary" data-g="good">Kunde</button>`;
      $$('#fc-act button').forEach(b => b.onclick = async () => {
        const grade = b.dataset.g;
        $$('#fc-act button').forEach(x => x.disabled = true);
        try { await api('/practice/cards/answer', { method: 'POST', body: { key: k, grade } }); } catch (e) { toast(e.message, true); }
        queue.shift();
        if (grade === 'again') queue.push(k); else done++;
        show();
      });
    };
  };
  show();
}

/* ------------------------------------------------------------------ Beteendefällor */
async function modeBias(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar scenario…</div>';
    const q = await api('/practice/bias');
    body.innerHTML = `<p class="q-text">${esc(q.q)}</p><div class="small mut" style="margin-bottom:8px">Vilken tankevurpa är det här?</div>
      <div class="q-opts">${q.options.map(o => `<button class="q-opt" data-k="${o.key}"><b>${esc(o.text)}</b><div class="small mut">${esc(o.hint)}</div></button>`).join('')}</div><div id="pr-fb"></div>`;
    $$('.q-opt', body).forEach(b => b.onclick = async () => {
      $$('.q-opt', body).forEach(x => x.disabled = true);
      const a = await api('/practice/bias/answer', { method: 'POST', body: { token: q.token, choice: b.dataset.k } });
      $$('.q-opt', body).forEach(x => { if (x.dataset.k === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
      $('#pr-fb').innerHTML = fbHTML(a.correct, `Det här är <b>${esc(a.answer_text)}</b>. ${esc(a.why)}`, `<div class="g-ex" style="margin-top:8px"><b>Motmedel:</b> ${esc(a.antidote)}</div>`);
      $('#pr-next').onclick = load;
      sessUpdate(a.correct);
    });
  };
  await load();
}

/* ------------------------------------------------------------------ Spelbok */
async function modePlaybook(body) {
  const d = await api('/trader/playbook');
  const done = d.sections.filter(x => x.ok).length;
  body.innerHTML = `<p class="q-text">Skriv dina regler <b>nu, i lugn och ro</b>. Det är de du följer när marknaden stormar och känslorna säger något annat. Minst ${d.min_len} tecken per avsnitt.${info('playbook')}</p>
    <div class="small mut" id="pb-prog" style="margin-bottom:10px">${done} av ${d.sections.length} avsnitt klara</div>
    ${d.sections.map(x => `<label class="fld"><span><b>${esc(x.title)}</b> <span class="pbok ${x.ok ? 'pos' : 'mut'}" data-ok="${x.key}">${x.ok ? '✓ klar' : ''}</span></span><textarea rows="3" data-k="${x.key}" placeholder="${esc(x.hint)}">${esc(x.text)}</textarea></label>`).join('')}
    <h4 style="margin:16px 0 6px">Dina gränser</h4><div class="fld2">${Object.entries(d.limits).map(([k, l]) => `<label class="fld"><span>${esc(l.label)} (${l.min}–${l.max})</span><input data-l="${k}" inputmode="decimal" value="${String(l.value).replace('.', ',')}"></label>`).join('')}</div>
    <div class="hint">Gränserna används av nivå 8 och framåt. Satt realistiskt: för tajt och du bryter dem direkt, för löst och de skyddar dig inte.</div>
    <div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="pb-save">Spara Spelboken</button></div>${d.updated ? `<div class="small mut">Senast sparad ${esc(d.updated.slice(0, 10))}</div>` : ''}`;
  const refresh = () => { let n = 0; $$('textarea[data-k]', body).forEach(t => { const ok = t.value.trim().length >= d.min_len; if (ok) n++; const m = $(`[data-ok="${t.dataset.k}"]`, body); m.textContent = ok ? '✓ klar' : ''; m.className = 'pbok ' + (ok ? 'pos' : 'mut'); }); $('#pb-prog').textContent = `${n} av ${d.sections.length} avsnitt klara`; };
  $$('textarea[data-k]', body).forEach(t => t.oninput = refresh);
  $('#pb-save').onclick = async () => {
    const sections = {}, limits = {};
    $$('textarea[data-k]', body).forEach(t => sections[t.dataset.k] = t.value);
    $$('input[data-l]', body).forEach(i => limits[i.dataset.l] = parseFloat(i.value.replace(',', '.')));
    try { await api('/trader/playbook', { method: 'PUT', body: { sections, limits } }); toast('Spelboken sparad'); gameCheck(); } catch (e) { toast(e.message, true); }
  };
}

/* ------------------------------------------------------------------ Månadsgranskning */
async function modeMonthly(body) {
  const d = await api('/trader/monthly');
  const f = (v, dd = 1) => v == null ? '–' : nf(v, dd);
  body.innerHTML = `<p class="q-text">Gå igenom månaden: siffrorna kommer från din övningsportfölj, du skriver vad som gick bra, sämre och vad du ändrar.${info('monthly')}</p>
    <div class="hint">Du kan granska den här månaden och de tre föregående, när du har minst ${d.need} stängda övningsaffärer under månaden.</div>
    ${d.months.map(m => `<div class="panel" style="margin-bottom:12px"><div class="panel-head"><b style="text-transform:capitalize">${esc(m.label)}</b>
      <span class="small mut">${m.stats.closed_n} stängda affärer · ${m.stats.journal_n} journalposter · ${m.stats.practice_n} övningar</span></div>
      ${m.stats.closed_n ? `<div class="small" style="margin-bottom:8px">Träffandel ${f(m.stats.hit_rate, 0)} % · snitt ${f(m.stats.avg_pnl_pct)} % per affär · snitt ${f(m.stats.avg_r)} R · processpoäng ${f(m.stats.process_avg, 0)}</div>` : ''}
      ${m.done ? `<div class="g-ex"><b>Gick bra:</b> ${esc(m.review.good)}<br><b>Gick sämre:</b> ${esc(m.review.bad)}<br><b>Ändrar:</b> ${esc(m.review.change)}</div><button class="btn sm" data-edit="${m.month}" style="margin-top:8px">Ändra</button>`
        : m.eligible ? `<button class="btn primary sm" data-edit="${m.month}">Skriv granskning</button>` : `<div class="small mut">Kräver minst ${d.need} stängda övningsaffärer (har ${m.stats.closed_n}).</div>`}
      <div class="mform" data-form="${m.month}" hidden>
        <label class="fld"><span>Vad gick bra i processen? (minst 30 tecken)</span><textarea rows="2" data-f="good">${m.review ? esc(m.review.good) : ''}</textarea></label>
        <label class="fld"><span>Vad gick sämre, och varför? Bedöm processen, inte bara utfallet.</span><textarea rows="2" data-f="bad">${m.review ? esc(m.review.bad) : ''}</textarea></label>
        <label class="fld"><span>En sak jag ändrar nästa månad</span><textarea rows="2" data-f="change">${m.review ? esc(m.review.change) : ''}</textarea></label>
        <div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" data-save="${m.month}">Spara</button></div></div></div>`).join('')}
    ${d.older.length ? `<h4 style="margin:14px 0 6px">Tidigare granskningar</h4>${d.older.map(m => `<div class="g-ex" style="margin-bottom:8px"><b style="text-transform:capitalize">${esc(m.label)}</b><br><b>Gick bra:</b> ${esc(m.review.good)}<br><b>Gick sämre:</b> ${esc(m.review.bad)}<br><b>Ändrar:</b> ${esc(m.review.change)}</div>`).join('')}` : ''}`;
  $$('[data-edit]', body).forEach(b => b.onclick = () => { const fm = $(`[data-form="${b.dataset.edit}"]`, body); fm.hidden = !fm.hidden; });
  $$('[data-save]', body).forEach(b => b.onclick = async () => {
    const fm = $(`[data-form="${b.dataset.save}"]`, body), v = k => $(`[data-f="${k}"]`, fm).value;
    try { await api('/trader/monthly/' + b.dataset.save, { method: 'PUT', body: { good: v('good'), bad: v('bad'), change: v('change') } }); toast('Månadsgranskning sparad'); gameCheck(); renderView(); } catch (e) { toast(e.message, true); }
  });
}

/* ------------------------------------------------------------------ Nivå 8–10: hjälpare */
const z0 = (v, d) => Math.abs(v) < 0.5 * Math.pow(10, -d) ? 0 : v;
const sgn = (v, d = 2) => v == null ? '–' : (v > 0 ? '+' : '') + nf(v, d);
function ciBar(lo, mean, hi, o = {}) {
  if (lo == null || hi == null) return '';
  const W = 360, H = 46, pad = 14, y = 16;
  const a = Math.min(lo, o.min != null ? o.min : -0.5, mean), b = Math.max(hi, o.max != null ? o.max : 0.5, mean);
  const x = v => pad + (v - a) / (b - a) * (W - 2 * pad);
  const col = lo > 0 ? '#2fc07a' : hi < 0 ? '#f0605d' : '#e8b34a';
  const lab = (v, anchor = 'middle') => `<text x="${x(v)}" y="${H - 4}" text-anchor="${anchor}" fill="#8995a8" font-size="10">${nf(v, 2)}</text>`;
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" class="cibar" role="img" aria-label="Intervall ${nf(lo, 2)} till ${nf(hi, 2)}">
    <line x1="${x(0)}" x2="${x(0)}" y1="3" y2="${y + 10}" stroke="#8995a8" stroke-dasharray="3 3"/>
    <line x1="${x(lo)}" x2="${x(hi)}" y1="${y}" y2="${y}" stroke="${col}" stroke-width="6" stroke-linecap="round" opacity=".85"/>
    <circle cx="${x(mean)}" cy="${y}" r="5" fill="#e8ecf3"/>
    <text x="${x(0)}" y="${H - 4}" text-anchor="middle" fill="#8995a8" font-size="10">0</text>
    ${lab(lo, 'end')}${lab(hi, 'start')}</svg>`;
}
function rCurve(ys) {
  if (!ys || ys.length < 2) return '';
  const W = 640, H = 120, L = 6, R = 6, T = 8, B = 8;
  const pts = [0, ...ys];
  const lo = Math.min(...pts), hi = Math.max(...pts), sp = (hi - lo) || 1;
  const X = i => L + i / (pts.length - 1) * (W - L - R), Y = v => T + (1 - (v - lo) / sp) * (H - T - B);
  return `<svg viewBox="0 0 ${W} ${H}" class="svgchart" style="width:100%;max-width:${W}px"><line x1="${L}" x2="${W - R}" y1="${Y(0)}" y2="${Y(0)}" stroke="#5d6a7f" stroke-dasharray="3 3"/>
    <polyline fill="none" stroke="#5aa0ff" stroke-width="2" points="${pts.map((v, i) => X(i).toFixed(1) + ',' + Y(v).toFixed(1)).join(' ')}"/></svg>`;
}
const stat = (label, val, sub = '') => `<div class="card statc"><div class="mut small">${label}</div><div class="big">${val}</div>${sub ? `<div class="small mut">${sub}</div>` : ''}</div>`;

/* ------------------------------------------------------------------ Stresstest (övning) */
async function modeStress(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar uppgift…</div>';
    const q = await api('/practice/stress');
    const cell = r => q.kind === 'beta' ? [nf(r.w, 0) + ' %', nf(r.beta, 1)] : q.kind === 'gap' ? [nf(r.w, 0) + ' %', nf(r.stop, 0) + ' %'] : [nf(r.w, 0) + ' %', nf(r.risk, 1) + ' %'];
    body.innerHTML = `<p class="q-text">${esc(q.q)}${info('stresstest')}</p>
      <div class="tbl-scroll"><table><thead><tr>${q.cols.map((c, i) => `<th class="${i ? '' : 'l'}">${esc(c)}</th>`).join('')}</tr></thead><tbody>
      ${q.rows.map(r => `<tr><td class="l">${esc(r.name)}</td>${cell(r).map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}
      ${q.cash ? `<tr><td class="l mut">Kontanter</td><td>${nf(q.cash, 0)} %</td><td class="mut">–</td></tr>` : ''}</tbody></table></div>
      <div class="row-add" style="margin-top:12px"><input id="rk-in" inputmode="decimal" placeholder="Ditt svar" autocomplete="off" style="max-width:180px"> <span class="mut" style="align-self:center">${esc(q.unit)}</span> <button class="btn primary" id="rk-go">Svara</button></div><div id="pr-fb"></div>
      <div class="small mut">Tips: räkna på papper. Svaret godkänns inom en liten marginal.</div>`;
    const inp = $('#rk-in'); inp.focus();
    const go = async () => {
      const val = parseFloat(inp.value.replace(/\s/g, '').replace(',', '.'));
      if (isNaN(val)) { toast('Skriv ett tal', true); return; }
      $('#rk-go').disabled = true; inp.disabled = true;
      const a = await api('/practice/stress/answer', { method: 'POST', body: { token: q.token, value: val } });
      $('#pr-fb').innerHTML = fbHTML(a.correct, esc(a.why), `<div class="small" style="margin-top:6px">Rätt svar: <b>${nf(a.answer, a.decimals)} ${esc(a.unit)}</b>${a.correct ? '' : ` (du skrev ${nf(val, a.decimals)})`}</div>`);
      $('#pr-next').onclick = load; sessUpdate(a.correct);
    };
    $('#rk-go').onclick = go; inp.onkeydown = e => { if (e.key === 'Enter') go(); };
  };
  await load();
}

/* ------------------------------------------------------------------ Tur eller skicklighet (övning) */
async function modeLuck(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar uppgift…</div>';
    const q = await api('/practice/luck');
    body.innerHTML = `<p class="q-text">${esc(q.q)}${info('losingstreak')}</p><div class="small mut" style="margin-bottom:8px">Gissa först, räkna sedan på svaret.</div>
      <div class="q-opts">${q.options.map(o => `<button class="q-opt" data-k="${o.key}">${esc(o.text)}</button>`).join('')}</div><div id="pr-fb"></div>`;
    $$('.q-opt', body).forEach(b => b.onclick = async () => {
      $$('.q-opt', body).forEach(x => x.disabled = true);
      const a = await api('/practice/luck/answer', { method: 'POST', body: { token: q.token, choice: b.dataset.k } });
      $$('.q-opt', body).forEach(x => { if (x.dataset.k === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
      $('#pr-fb').innerHTML = fbHTML(a.correct, `Rätt svar: <b>${esc(a.answer_text)}</b>. ${esc(a.why)}`);
      $('#pr-next').onclick = load; sessUpdate(a.correct);
    });
  };
  await load();
}

/* ------------------------------------------------------------------ Samband eller slump (övning) */
async function modeSpur(body) {
  const load = async () => {
    body.innerHTML = '<div class="loading">Hämtar uppgift…</div>';
    const q = await api('/practice/spur');
    body.innerHTML = `<p class="q-text">${esc(q.q)}${info('multiple')}</p><div class="small mut" style="margin-bottom:8px">Gissa först, räkna sedan på svaret.</div>
      <div class="q-opts">${q.options.map(o => `<button class="q-opt" data-k="${o.key}">${esc(o.text)}</button>`).join('')}</div><div id="pr-fb"></div>`;
    $$('.q-opt', body).forEach(b => b.onclick = async () => {
      $$('.q-opt', body).forEach(x => x.disabled = true);
      const a = await api('/practice/spur/answer', { method: 'POST', body: { token: q.token, choice: b.dataset.k } });
      $$('.q-opt', body).forEach(x => { if (x.dataset.k === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
      $('#pr-fb').innerHTML = fbHTML(a.correct, `Rätt svar: <b>${esc(a.answer_text)}</b>. ${esc(a.why)}`);
      $('#pr-next').onclick = load; sessUpdate(a.correct);
    });
  };
  await load();
}

/* ------------------------------------------------------------------ Riskpanel */
async function modeRiskpanel(body) {
  const [pl, rp] = await Promise.all([api('/paper'), api('/pro/riskpanel')]);
  const h = rp.history, ports = pl.portfolios;
  const pct = v => v == null ? '–' : nf(v, 1) + ' %';
  body.innerHTML = `<p class="q-text">Här ser du vad dina övningsportföljer klarar när det går fel, och om du har hållit dina egna gränser. Gränserna sätter du i Spelboken (nu: samlad öppen risk högst <b>${nf(h.limits.max_open_risk, 1)} %</b>, nedgång högst <b>${nf(h.limits.max_dd, 1)} %</b>).${info('stresstest')}</p>
    <h4 style="margin:12px 0 6px">1. Stresstesta en portfölj</h4>
    ${ports.length ? `<div class="seg" id="rp-pick">${ports.map(p => `<button data-id="${p.id}">${esc(p.name)} <span class="mut small">(${p.open_n} öppna)</span></button>`).join('')}</div><div id="rp-out" style="margin-top:12px"><div class="mut small">Välj en portfölj. Stresstestet kräver minst tre öppna positioner för att räknas i spelläget.</div></div>` : '<div class="mut">Du har ingen övningsportfölj ännu. Skapa en under Övningsportfölj.</div>'}
    <h4 style="margin:20px 0 6px">2. Har du hållit dina gränser de senaste 60 handelsdagarna?${info('risklimits')}</h4>
    <div class="hint">Godkänt kräver att öppen risk och nedgång låg inom dina gränser hela perioden och att du hade positioner minst 30 av 60 dagar. Vinst eller förlust spelar ingen roll. Öppen risk räknas bakåt med stoppet som gällde vid köp om stoppet flyttats senare, vilket kan överskatta risken lite.</div>
    <div class="tbl-scroll"><table><thead><tr><th class="l">Portfölj</th><th>Dagar sedan start</th><th>Dagar med positioner</th><th>Högsta öppna risk</th><th>Största nedgång</th><th class="l">Status</th></tr></thead><tbody>
    ${h.portfolios.map(p => `<tr><td class="l">${esc(p.name)}</td><td>${p.days}</td><td>${p.window_days ? p.invested_days + '/60' : '–'}</td><td>${pct(p.max_risk)}</td><td>${p.dd == null ? '–' : pct(-p.dd)}</td><td class="l ${p.ok ? 'pos' : 'mut'}" style="white-space:normal;min-width:240px">${p.ok ? '✓ ' : ''}${esc(p.why)}</td></tr>`).join('') || '<tr><td colspan="6" class="mut">Inga portföljer.</td></tr>'}</tbody></table></div>`;
  $$('#rp-pick button').forEach(b => b.onclick = async () => {
    $$('#rp-pick button').forEach(x => x.classList.toggle('on', x === b));
    const out = $('#rp-out'); out.innerHTML = '<div class="loading">Räknar…</div>';
    const d = await api('/pro/stress/' + b.dataset.id);
    gameCheck();
    out.innerHTML = d.n_open === 0 ? '<div class="mut">Portföljen har inga öppna positioner att stresstesta.</div>' : `
      <div class="small mut" style="margin-bottom:8px">Portföljbeta ${nf(z0(d.portfolio_beta, 2), 2)} · kontanter ${nf(d.cash_pct, 0)} % · ${d.n_open} öppna positioner${d.n_open < 3 ? ' (tre krävs för spelläget)' : ''}. Beta mäts mot index över senaste året.</div>
      <div class="tbl-scroll"><table><thead><tr><th class="l">Scenario</th><th>Förlust, % av portföljen</th><th>Förlust, kr</th><th class="l">Mot dina gränser</th></tr></thead><tbody>
      ${d.scenarios.map(s => `<tr><td class="l">${esc(s.label)}</td><td>${nf(z0(s.loss_pct, 1), 1)} %</td><td>${nf(z0(s.loss_pct / 100 * d.equity, 0), 0)} kr</td><td class="l ${s.over ? 'neg' : 'pos'}">${s.over ? 'Över gränsen' : 'Inom gränsen'}</td></tr>`).join('')}</tbody></table></div>
      <div class="tbl-scroll" style="margin-top:12px"><table><thead><tr><th class="l">Innehav</th><th>Vikt</th><th>Beta</th><th>Stoppavstånd</th><th>Risk vid stopp</th></tr></thead><tbody>
      ${d.positions.map(x => `<tr><td class="l">${esc(x.ticker)} <span class="mut small">${esc(x.name)}</span></td><td>${nf(x.w, 1)} %</td><td>${nf(z0(x.beta, 2), 2)}</td><td>${nf(x.stop_dist, 1)} %</td><td>${nf(x.risk_pct, 2)} %</td></tr>`).join('')}</tbody></table></div>
      <div class="hint" style="margin-top:8px">Scenarierna är grova: beta är ett historiskt snitt och faller sällan lika snällt i en riktig kris. Använd dem för att se storleksordningen och om något scenario passerar din gräns.</div>`;
  });
}

/* ------------------------------------------------------------------ Handelsstatistik */
async function modeStats(body) {
  const d = await api('/pro/stats');
  gameCheck();
  const t = d.total;
  const v = d.verdict;
  const pl = await api('/paper');
  const elig = pl.portfolios;
  body.innerHTML = `<p class="q-text">Dina stängda övningsaffärer, mätta som <b>R-multiplar</b>${info('expectancy')} (resultat delat med risken du tog vid köp). Varje siffra visas med ett <b>osäkerhetsintervall</b>${info('ci')}: det är intervallet som säger hur mycket du kan lita på snittet.</p>
    <div class="g-ex" style="margin-bottom:12px"><b>${esc(v.title)}.</b> ${esc(v.text)}</div>
    ${t.n ? `<div class="cards">
      ${stat('Stängda affärer', t.n, `${t.wins} vinster`)}
      ${stat('Träffandel', nf(t.win_rate, 0) + ' %', `intervall ${nf(t.win_lo, 0)}–${nf(t.win_hi, 0)} %`)}
      ${stat('Snitt per affär', sgn(t.mean_r) + ' R', `intervall ${sgn(t.r_lo)} till ${sgn(t.r_hi)}`)}
      ${stat('Snittvinst / snittförlust', t.payoff ? nf(t.payoff, 2) : '–', `${sgn(t.avg_win_r)} R / ${sgn(t.avg_loss_r)} R`)}
      ${stat('Träffandel som krävs', t.breakeven_win ? nf(t.breakeven_win, 0) + ' %' : '–', 'för att gå runt med din vinst/förlust-kvot')}
      ${stat('Längsta förlustserie', t.longest_losing + ' st', `normalt ca ${t.typical_losing}, ibland ${t.p95_losing}+ vid din träffandel`)}
      ${stat('Största nedgång', nf(t.max_dd_r, 1) + ' R', 'i ackumulerad R')}
      ${stat('Affärer för ±0,25 R', t.need_n || '–', 'ungefär, med din spridning')}
    </div>
    <h4 style="margin:12px 0 6px">Snitt-R med intervall ${info('ci')}</h4><div>${ciBar(t.r_lo, t.mean_r, t.r_hi)}<div class="small mut">Den streckade linjen är noll. Ligger hela intervallet på ena sidan har du något att tolka, annars inte.</div></div>
    <h4 style="margin:12px 0 6px">Ackumulerad R över tid</h4>${rCurve(t.curve_r)}
    ${t.gap_stops ? `<div class="small mut" style="margin-top:6px">${t.gap_stops} affärer stoppades med gap och blev större förluster än planerat.</div>` : ''}
    <h4 style="margin:16px 0 6px">Per portfölj</h4>
    <div class="tbl-scroll"><table><thead><tr><th class="l">Portfölj</th><th>Affärer</th><th>Träffandel</th><th>Snitt R</th><th>Intervall</th><th>Längsta förlustserie</th></tr></thead><tbody>
    ${d.portfolios.map(p => `<tr><td class="l">${esc(p.name)}</td><td>${p.n}</td><td>${p.n ? nf(p.win_rate, 0) + ' %' : '–'}</td><td>${p.n ? sgn(p.mean_r) : '–'}</td><td>${p.n >= 2 ? `${sgn(p.r_lo)} till ${sgn(p.r_hi)}` : '–'}</td><td>${p.n ? p.longest_losing : '–'}</td></tr>`).join('')}</tbody></table></div>`
      : '<div class="mut">Du har inga stängda övningsaffärer ännu. Statistiken fylls på när du stänger affärer i Övningsportföljen.</div>'}
    <h4 style="margin:20px 0 6px">Jämför två strategier${info('ci')}</h4>
    ${elig.length >= 2 ? `<div class="hint">Skillnaden mellan två portföljer är nästan alltid mindre säker än man tror. Jämförelsen visar om den går att skilja från slump.</div>
    <div class="row-add"><select id="cp-a">${elig.map(p => `<option value="${p.id}">${esc(p.name)} (${p.closed_n})</option>`).join('')}</select> <span style="align-self:center" class="mut">mot</span> <select id="cp-b">${elig.map((p, i) => `<option value="${p.id}" ${i === 1 ? 'selected' : ''}>${esc(p.name)} (${p.closed_n})</option>`).join('')}</select> <button class="btn primary" id="cp-go">Jämför</button></div><div id="cp-out" style="margin-top:12px"></div>`
      : '<div class="mut">Du behöver två övningsportföljer med stängda affärer för att jämföra.</div>'}
    <div class="disclaimer" style="margin-top:14px">${esc(d.note)}</div>`;
  const go = $('#cp-go');
  if (go) go.onclick = async () => {
    const out = $('#cp-out');
    try {
      const r = await api(`/pro/compare?a=${$('#cp-a').value}&b=${$('#cp-b').value}`);
      gameCheck();
      out.innerHTML = `<div class="g-ex"><b>${esc(r.a.name)}</b>: ${sgn(r.a.mean_r)} R (${r.a.n} affärer, intervall ${sgn(r.a.r_lo)} till ${sgn(r.a.r_hi)})<br>${ciBar(r.a.r_lo, r.a.mean_r, r.a.r_hi)}<br>
        <b>${esc(r.b.name)}</b>: ${sgn(r.b.mean_r)} R (${r.b.n} affärer, intervall ${sgn(r.b.r_lo)} till ${sgn(r.b.r_hi)})<br>${ciBar(r.b.r_lo, r.b.mean_r, r.b.r_hi)}<br>
        <b>Skillnad:</b> ${sgn(r.diff)} R, intervall ${sgn(r.lo)} till ${sgn(r.hi)}. ${esc(r.text)}</div>
        ${Math.min(r.a.n, r.b.n) < 10 ? '<div class="small mut" style="margin-top:6px">Spelläget kräver minst tio stängda affärer i båda portföljerna.</div>' : ''}`;
    } catch (e) { out.innerHTML = `<div class="fb bad">${esc(e.message)}</div>`; }
  };
}

/* ------------------------------------------------------------------ Regeltest */
async function modeRules(body) {
  const d = await api('/pro/rules');
  const sel = new Set(['trend_up']);
  const draw = () => {
    body.innerHTML = `<p class="q-text">Testa en regel mot historiken i dina listor. <b>Skriv hypotesen först</b>: det du tror kommer hända och varför. Sedan jämförs regeln med vad som hände i allmänhet och med båda halvorna av perioden.${info('ruletest')}</p>
      <label class="fld"><span><b>Min hypotes</b> (minst 30 tecken)</span><textarea id="rt-h" rows="2" placeholder="T.ex.: Aktier som dragit sig tillbaka mot SMA50 i en stark uppåttrend fortsätter upp oftare än slumpen, eftersom trenden brukar hålla."></textarea></label>
      <div class="fld"><span><b>Köp när alla dessa stämmer</b></span><div class="chips" id="rt-c">${d.conds.map(c => `<button class="chip ${sel.has(c.key) ? 'on' : ''}" data-k="${c.key}" title="${esc(c.hint)}">${esc(c.label)}</button>`).join('')}</div></div>
      <div class="fld2"><label class="fld"><span>Stopp, antal ATR under kursen (1–6)</span><input id="rt-s" inputmode="decimal" value="3"></label><label class="fld"><span>Håll högst (handelsdagar, 10–120)</span><input id="rt-d" inputmode="numeric" value="40"></label></div>
      <div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="rt-go">Kör testet</button></div>
      <div id="rt-out"></div>
      ${d.history.length ? `<h4 style="margin:18px 0 6px">Dina tidigare tester (${d.history.length})</h4><div class="tbl-scroll"><table><thead><tr><th class="l">Datum</th><th class="l">Regel</th><th class="l">Hypotes</th><th>Affärer</th><th>Snitt R</th><th>Jämförelse</th></tr></thead><tbody>${d.history.map(h => `<tr><td class="l">${esc(h.ts)}</td><td class="l small">${esc(h.label)}</td><td class="l small">${esc(h.hypothesis)}</td><td>${h.n}</td><td>${sgn(h.mean_r)}</td><td>${sgn(h.base_r)}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
    $$('#rt-c .chip').forEach(c => c.onclick = () => { sel.has(c.dataset.k) ? sel.delete(c.dataset.k) : sel.add(c.dataset.k); c.classList.toggle('on'); });
    $('#rt-go').onclick = async () => {
      const out = $('#rt-out'); out.innerHTML = '<div class="loading">Testar mot historiken…</div>';
      try {
        const r = await api('/pro/rules', { method: 'POST', body: { conds: [...sel], stop_atr: parseFloat($('#rt-s').value.replace(',', '.')) || 3, horizon: parseInt($('#rt-d').value) || 40, hypothesis: $('#rt-h').value } });
        gameCheck();
        const x = r.result;
        out.innerHTML = `<div class="panel" style="margin-top:12px"><div class="panel-head"><b>Resultat</b><span class="small mut">${x.n} affärer i ${x.tickers} bolag, ${x.months} månader</span></div>
          <div class="cards">
            ${stat('Snitt per affär', sgn(x.mean_r) + ' R', `intervall ${sgn(x.r_lo)} till ${sgn(x.r_hi)}`)}
            ${stat('Jämförelse: alla dagar', sgn(x.base_r) + ' R', `${x.base_n} affärer med samma stopp och tid`)}
            ${stat('Skillnad mot jämförelsen', sgn(x.ahead_r) + ' R', x.better_than_chance ? 'intervallet ligger över jämförelsen' : 'går inte att skilja från jämförelsen')}
            ${stat('Träffandel', nf(x.win_rate, 0) + ' %', `intervall ${nf(x.win_lo, 0)}–${nf(x.win_hi, 0)} %`)}
            ${stat('Första / andra halvan', `${sgn(x.first_half_r)} / ${sgn(x.second_half_r)}`, `delat vid ${esc(x.split_date)}`)}
            ${stat('Utstoppade', nf(x.stopped_pct, 0) + ' %', 'av affärerna')}
          </div>${ciBar(x.r_lo, x.mean_r, x.r_hi)}
          <div class="g-ex" style="margin-top:10px"><b>Läs ärligt:</b><ul style="margin:6px 0 0 18px">${x.notes.map(n => `<li>${esc(n)}</li>`).join('')}</ul></div>
          <div class="small mut" style="margin-top:8px">Du har nu gjort ${r.prev_tests} regeltest. Det här är utbildning, inget råd, och historiken säger inte vad som händer härnäst.</div></div>`;
      } catch (e) { out.innerHTML = `<div class="fb bad" style="margin-top:10px">${esc(e.message)}</div>`; }
    };
  };
  draw();
}

/* ------------------------------------------------------------------ Handlarprofil */
async function modeProfile(body) {
  const d = await api('/pro/profile');
  gameCheck();
  const s = d.stats, v = d.verdict;
  const lim = d.playbook.limits;
  body.innerHTML = `<div class="profhead"><div><div class="mut small">Status</div><div class="big">${esc(d.label)}</div></div>
      <div class="mut small" style="max-width:520px">${esc(d.disclaimer)}</div></div>
    <h4 style="margin:14px 0 6px">Krav för <i>Visad professionell process</i>${info('profile')}</h4>
    <div class="tbl-scroll"><table><tbody>${d.reqs.map(r => `<tr><td class="l">${r.ok ? '✅' : '⬜'} ${esc(r.label)}</td><td class="${r.ok ? 'pos' : 'mut'}">${esc(r.have)}</td></tr>`).join('')}</tbody></table></div>
    <div class="hint" style="margin-top:6px">Inget av kraven handlar om att tjäna pengar. Kraven är tid, antal, process, risk och ärlighet.</div>
    <h4 style="margin:16px 0 6px">Siffrorna</h4>
    ${s.n ? `<div class="cards">${stat('Affärer', s.n, `${d.months_with_trades} månader med stängda affärer`)}${stat('Snitt per affär', sgn(s.mean_r) + ' R', `intervall ${sgn(s.r_lo)} till ${sgn(s.r_hi)}`)}${stat('Träffandel', nf(s.win_rate, 0) + ' %', `intervall ${nf(s.win_lo, 0)}–${nf(s.win_hi, 0)} %`)}${stat('Processsnitt, senaste 30', d.process_last30 == null ? '–' : nf(d.process_last30, 0), 'av 100')}${stat('Längsta förlustserie', s.longest_losing + ' st', `normalt ca ${s.typical_losing}`)}${stat('Spelbok och granskning', `${d.monthly_n} granskningar`, d.playbook.complete ? 'Spelbok komplett' : 'Spelbok saknas')}</div>
      <div>${ciBar(s.r_lo, s.mean_r, s.r_hi)}</div>` : '<div class="mut">Inga stängda affärer ännu.</div>'}
    <div class="g-ex" style="margin:12px 0"><b>Ärligt utlåtande: ${esc(v.title)}.</b> ${esc(v.text)}</div>
    <h4 style="margin:16px 0 6px">Risk</h4>
    <div class="small">Dina gränser: samlad öppen risk högst ${nf(lim.max_open_risk, 1)} %, nedgång högst ${nf(lim.max_dd, 1)} %. ${d.risk.ok ? '<span class="pos">Hållna i 60 handelsdagar i minst en portfölj.</span>' : '<span class="mut">Ännu inte hållna i 60 handelsdagar.</span>'}</div>
    ${d.bias.n ? `<div class="small mut" style="margin-top:4px">Beteendefällor: ${d.bias.n} besvarade${d.bias.pct != null ? `, ${nf(d.bias.pct, 0)} % rätt på de senaste` : ''}. Regeltester gjorda: ${d.rule_tests}.</div>` : ''}
    <h4 style="margin:16px 0 6px">Min Spelbok</h4>
    ${d.playbook.complete ? d.playbook.sections.map(x => `<div class="small" style="margin-bottom:6px"><b>${esc(x.title)}</b><br>${esc(x.text)}</div>`).join('') : '<div class="mut small">Spelboken är inte komplett. Skriv den under Handlarens verktyg → Spelbok.</div>'}
    <h4 style="margin:16px 0 6px">Lärdomar från mina affärer</h4>
    ${d.lessons.length ? `<ul class="small" style="margin:0 0 0 18px">${d.lessons.map(l => `<li><b>${esc(l.ticker)}</b> (${esc(l.date)}${l.r != null ? ', ' + sgn(l.r, 1) + ' R' : ''}): ${esc(l.text)}</li>`).join('')}</ul>` : '<div class="mut small">Skriv lärdomar när du granskar stängda affärer.</div>'}
    <h4 style="margin:18px 0 6px">Ditt beslut</h4>
    ${d.decision ? `<div class="g-ex"><b>${esc(d.decision.ts)}:</b> ${esc(d.decision.label)}<br><span class="small">${esc(d.decision.reflection)}</span><div class="small mut" style="margin-top:4px">Skrevs efter ${d.decision.n} affärer med utlåtandet ”${esc(d.decision.verdict)}”.</div></div>` : ''}
    <div class="hint">${s.n >= 30 ? 'Utifrån din egen statistik: vad gör du härnäst? Vilket du väljer spelar ingen roll för nivån, men motiveringen måste vara ärlig.' : 'Beslutet blir möjligt när du har minst 30 stängda övningsaffärer.'}</div>
    ${s.n >= 30 ? `<div class="chips" id="pf-d" style="flex-direction:column;align-items:stretch;gap:6px">${Object.entries(d.decisions).map(([k, t]) => `<label class="chip" style="text-align:left;display:block"><input type="radio" name="pfd" value="${k}" ${d.decision && d.decision.decision === k ? 'checked' : ''}> ${esc(t)}</label>`).join('')}</div>
      <label class="fld" style="margin-top:10px"><span>Din motivering (minst ${d.min_reflect} tecken): vad visar siffrorna, vad är du osäker på och vad skulle få dig att ändra dig?</span><textarea id="pf-r" rows="4">${d.decision ? esc(d.decision.reflection) : ''}</textarea></label>
      <div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="pf-save">Spara beslut</button></div>` : ''}`;
  const sv = $('#pf-save');
  if (sv) sv.onclick = async () => {
    const dec = (document.querySelector('input[name=pfd]:checked') || {}).value;
    try { await api('/pro/decision', { method: 'PUT', body: { decision: dec || '', reflection: $('#pf-r').value } }); toast('Beslut sparat'); gameCheck(); modeProfile(body); } catch (e) { toast(e.message, true); }
  };
}

/* ================================================================== ÖVNINGSPORTFÖLJ */
const PAPER = { pid: null };
const procTip = p => `Plan ${p.parts.plan}/20 · Risk ${p.parts.risk}/30 · Storlek ${p.parts.size}/20 · Granskning ${p.parts.review}/30`;
const REASON_SV = { target: 'Målet nåddes', thesis: 'Tesen höll inte', time: 'Tiden gick ut', other: 'Annat skäl', stop: 'Stoppet löste ut', stop_gap: 'Stoppet löste ut (gap)' };

async function viewPaper(v, rid) {
  if (PAPER.pid) return paperDetail(v, rid);
  const d = await api('/paper');
  if (stale(rid)) return;
  const ps = d.portfolios;
  v.innerHTML = guide('paper') + `<div class="panel"><div class="panel-head"><div><h3>Dina övningsportföljer${info('paper')}</h3><div class="hint" style="margin:0">Virtuella pengar, riktiga kurser. Courtage ${nf(d.rules.cost_pct, 1)} % per affär ingår. Poängen är för processen${info('processscore')}, inte för vinsten.</div></div><button class="btn primary" id="pp-new">+ Ny övningsportfölj</button></div>
    ${ps.length ? `<div class="pr-grid">${ps.map(p => `<div class="card pr-card" data-id="${p.id}"><div class="lbl">${esc(p.name)}</div><div class="big">${kr(p.equity)}</div>
      <div class="small"><span class="${cls(p.ret)}">${pct(p.ret)}</span> sedan start${p.bench != null ? ` · index ${pct(p.bench)}` : ''}</div>
      <div style="margin:6px 0">${spark(p.curve.map(c => c[1]))}</div>
      <div class="small mut">${p.open_n} öppna · ${p.closed_n} stängda · processpoäng ${p.process_avg == null ? '–' : nf(p.process_avg, 0)}${p.to_review ? ` · <span class="warnc">${p.to_review} att granska</span>` : ''}${p.due_n ? ` · <span class="warnc">${p.due_n} dags att se över</span>` : ''}</div>
      ${p.strategy ? `<div class="small" style="margin-top:6px">${esc(p.strategy)}</div>` : ''}</div>`).join('')}</div>` : `<div class="empty">Du har ingen övningsportfölj ännu. Skapa en och köp din första position med tes, stopp och rätt storlek.</div>`}</div>
    ${ps.length > 1 ? `<div class="panel"><h3>Jämförelse</h3><div class="hint">Samma kurser, olika strategier. Titta mest på processpoängen och på största nedgången, inte bara på avkastningen.</div><div class="tbl-scroll"><table><thead><tr><th class="l">Portfölj</th><th>Värde</th><th>Avkastning</th><th>Mot index</th><th>Största nedgång</th><th>Öppen risk</th><th>Process</th><th>Affärer</th></tr></thead><tbody>
      ${ps.map(p => `<tr><td class="l">${esc(p.name)}</td><td>${kr(p.equity)}</td><td class="${cls(p.ret)}">${pct(p.ret)}</td><td class="${cls(p.excess)}">${p.excess == null ? '–' : pp(p.excess)}</td><td class="${cls(p.max_dd)}">${pct(p.max_dd)}</td><td>${p.risk_open_pct == null ? '–' : nf(p.risk_open_pct, 1) + ' %'}</td><td>${p.process_avg == null ? '–' : nf(p.process_avg, 0)}</td><td>${p.open_n + p.closed_n}</td></tr>`).join('')}</tbody></table></div></div>` : ''}`;
  bindGuides();
  $('#pp-new').onclick = () => dialog(`<div class="g-head"><h3>Ny övningsportfölj</h3></div>
    <label class="fld"><span>Namn</span><input id="np-n" placeholder="t.ex. Trendstrategi"></label>
    <label class="fld"><span>Strategi i en mening (valfritt)</span><input id="np-s" placeholder="t.ex. Köper starka aktier över SMA200 med stopp 3 ATR"></label>
    <label class="fld"><span>Startkapital (kr)</span><input id="np-c" inputmode="numeric" value="100000"></label>
    <div class="dlg-actions"><button class="btn" id="np-x">Avbryt</button><button class="btn primary" id="np-ok">Skapa</button></div>`, dd => {
    $('#np-x', dd).onclick = () => dd.close();
    $('#np-ok', dd).onclick = async () => {
      try {
        const r = await api('/paper', { method: 'POST', body: { name: $('#np-n', dd).value, strategy: $('#np-s', dd).value, cash0: parseFloat($('#np-c', dd).value.replace(/\s/g, '').replace(',', '.')) } });
        dd.close(); PAPER.pid = r.id; gameCheck(); renderView();
      } catch (e) { toast(e.message, true); }
    };
  });
  $$('.pr-card[data-id]').forEach(c => c.onclick = () => { PAPER.pid = +c.dataset.id; renderView(); });
}

async function paperDetail(v, rid) {
  let d;
  try { d = await api('/paper/' + PAPER.pid); } catch (e) { PAPER.pid = null; renderView(); return; }
  if (stale(rid)) return;
  const s = d.summary, curve = s.curve;
  const metric = (l, val, sub = '', c = '', gk = '') => `<div class="card"><div class="lbl">${l}${gk ? info(gk) : ''}</div><div class="big ${c}">${val}</div><div class="small">${sub}</div></div>`;
  const openRow = t => `<tr><td class="l"><b>${esc(t.ticker)}</b><div class="nm">${esc(t.name)}</div></td><td>${nf(t.qty, 0)}</td><td>${nf(t.entry_price, 2)} <span class="mut">${esc(t.currency)}</span></td><td>${nf(t.price, 2)}</td>
    <td class="${cls(t.pnl_pct)}">${pct(t.pnl_pct)}</td><td class="${cls(t.r)}">${t.r == null ? '–' : nf(t.r, 1) + ' R'}</td><td>${nf(t.stop, 2)}<div class="small mut">${nf(t.stop_dist, 1)} % under</div></td><td>${nf(t.risk_pct, 1)} % / ${nf(t.pos_pct, 0)} %</td>
    <td class="l small" title="${esc(t.thesis)}">${t.due ? '<span class="warnc">Dags att se över</span>' : 'Se över ' + esc(t.review_on)}</td>
    <td class="acts"><button class="btn sm" data-stop="${t.id}">Höj stopp</button> <button class="btn sm" data-close="${t.id}">Stäng</button></td></tr>`;
  const closedRow = t => `<tr><td class="l"><b>${esc(t.ticker)}</b></td><td class="${cls(t.pnl_pct)}">${pct(t.pnl_pct)}</td><td class="${cls(t.r)}">${t.r == null ? '–' : nf(t.r, 1) + ' R'}</td><td class="l">${esc(REASON_SV[t.exit_reason] || t.exit_reason)}</td>
    <td title="${esc(procTip(t.points))}">${t.points.total}</td><td class="l small">${t.lesson ? esc(t.lesson) : `<button class="btn sm primary" data-review="${t.id}">Granska</button>`}</td></tr>`;
  v.innerHTML = `<div class="panel"><div class="panel-head"><div><button class="btn sm" id="pd-back">← Alla portföljer</button> <b style="margin-left:10px;font-size:16px">${esc(s.name)}</b>${s.strategy ? `<div class="small mut" style="margin-top:4px">${esc(s.strategy)}</div>` : ''}</div>
      <div><button class="btn primary" id="pd-buy">+ Ny affär</button> <button class="btn" id="pd-del">Ta bort</button></div></div>
    <div class="kv" style="margin-bottom:10px">
      ${metric('Värde', kr(s.equity), `varav kontanter ${kr(s.cash)}`)}
      ${metric('Avkastning', pct(s.ret), `start ${kr(s.cash0)}`, cls(s.ret))}
      ${metric('Mot index', s.excess == null ? '–' : pp(s.excess), s.bench == null ? 'ingen indexdata' : `index ${pct(s.bench)} sedan start`, cls(s.excess))}
      ${metric('Största nedgång', pct(s.max_dd), 'från toppvärde', cls(s.max_dd), 'maxdd')}
      ${metric('Öppen risk', s.risk_open_pct == null ? '–' : nf(s.risk_open_pct, 1) + ' %', 'av portföljen om alla stopp träffas')}
      ${metric('Processpoäng', s.process_avg == null ? '–' : nf(s.process_avg, 0), `${s.closed_n} stängda affärer`, '', 'processscore')}</div>
    ${curve.length > 1 ? `<div class="hint" style="margin:0 0 4px">Värdeutveckling (${esc(curve[0][0])} till ${esc(curve[curve.length - 1][0])})</div>${svgPanel({ small: true, series: [{ name: 'Värde', cls: 'price', y: curve.map(c => c[1]) }], hlines: [{ y: s.cash0, label: 'startkapital' }] })}` : '<div class="hint">Kurvan fylls på när kurserna uppdateras efter ditt första köp.</div>'}</div>
    <div class="panel"><h3>Öppna positioner</h3>${d.open.length ? `<div class="tbl-scroll"><table><thead><tr><th class="l">Bolag</th><th>Antal</th><th>Köpt för</th><th>Kurs nu</th><th>Resultat</th><th>R${info('rr')}</th><th>Stopp${info('stop')}</th><th>Risk / storlek vid köp</th><th class="l">Uppföljning</th><th></th></tr></thead><tbody>${d.open.map(openRow).join('')}</tbody></table></div>
      <div class="hint">Stopp utlöses automatiskt när kurserna uppdateras (dagens lägsta kurs, vid gap öppningskursen${info('gapfill')}). Du kan bara höja ett stopp, aldrig sänka det.</div>` : '<div class="empty">Inga öppna positioner. Klicka på “+ Ny affär”.</div>'}</div>
    <div class="panel"><h3>Stängda affärer och lärdomar</h3>${d.closed.length ? `<div class="tbl-scroll"><table><thead><tr><th class="l">Bolag</th><th>Resultat</th><th>R</th><th class="l">Skäl</th><th>Process${info('processscore')}</th><th class="l">Lärdom</th></tr></thead><tbody>${d.closed.map(closedRow).join('')}</tbody></table></div>
      <div class="hint">Granska varje stängd affär med en lärdom (minst 20 tecken). Det ger 30 av 100 processpoäng och är det som gör övningen värd något.</div>` : '<div class="hint">Inga stängda affärer ännu.</div>'}</div>`;
  $('#pd-back').onclick = () => { PAPER.pid = null; renderView(); };
  $('#pd-del').onclick = async () => { if (confirm(`Ta bort “${s.name}” och alla dess affärer? Det går inte att ångra.`)) { await api('/paper/' + PAPER.pid, { method: 'DELETE' }); PAPER.pid = null; gameCheck(); renderView(); } };
  $('#pd-buy').onclick = () => buyDialog(s, d.rules);
  $$('[data-close]').forEach(b => b.onclick = () => closeDialog(+b.dataset.close, d));
  $$('[data-stop]').forEach(b => b.onclick = () => stopDialog(d.open.find(t => t.id === +b.dataset.stop)));
  $$('[data-review]').forEach(b => b.onclick = () => reviewDialog(d.closed.find(t => t.id === +b.dataset.review)));
}

function buyDialog(s, rules) {
  const tickers = [...new Set(S.lists.flatMap(l => l.items.map(i => i.ticker)))].sort();
  dialog(`<div class="g-head"><h3>Ny övningsaffär</h3><span class="mut">Kontanter ${kr(s.cash)} · värde ${kr(s.equity)}</span></div>
    <div class="row-add"><input id="b-t" list="b-tl" placeholder="Ticker, t.ex. XLK" style="max-width:220px"><datalist id="b-tl">${tickers.map(t => `<option value="${esc(t)}">`).join('')}</datalist><button class="btn" id="b-q">Hämta kurs</button></div>
    <div id="b-q-out" class="small" style="margin-bottom:8px"></div>
    <div id="b-form" hidden>
      <div class="fld2"><label class="fld"><span>Stoppkurs${info('stop')}</span><input id="b-stop" inputmode="decimal"></label>
        <label class="fld"><span>Risk i % av portföljen${info('possize')}</span><input id="b-risk" inputmode="decimal" value="1"></label>
        <label class="fld"><span>Antal aktier</span><input id="b-qty" inputmode="numeric"></label></div>
      <div class="chips" id="b-presets" style="margin:4px 0 8px"></div>
      <div id="b-calc" class="small" style="margin-bottom:10px"></div>
      <label class="fld"><span>Tes: varför köper du? (minst 30 tecken)${info('thesis')}</span><textarea id="b-th" rows="3"></textarea></label>
      <label class="fld"><span>Vad skulle visa att du har fel?${info('invalid')}</span><input id="b-inv"></label>
      <div class="fld2"><label class="fld"><span>Målkurs (valfritt)</span><input id="b-tg" inputmode="decimal"></label>
        <label class="fld"><span>Uppföljning efter (dagar)</span><input id="b-hz" inputmode="numeric" value="90"></label></div></div>
    <div class="dlg-actions"><button class="btn" id="b-x">Avbryt</button><button class="btn primary" id="b-ok" disabled>Köp (virtuellt)</button></div>`, d => {
    const num = id => parseFloat(($(id, d).value || '').replace(/\s/g, '').replace(',', '.'));
    let q = null, qtyTouched = false;
    const calc = () => {
      if (!q) return;
      const stop = num('#b-stop'), risk = num('#b-risk');
      const per = (q.price - stop) * q.fx;
      if (!(stop > 0 && stop < q.price)) { $('#b-calc', d).innerHTML = '<span class="neg">Stoppkursen måste ligga under köpkursen.</span>'; $('#b-ok', d).disabled = true; return; }
      if (!qtyTouched && risk > 0) $('#b-qty', d).value = Math.max(0, Math.min(Math.floor(s.equity * risk / 100 / per), Math.floor(s.cash / (q.price * q.fx * 1.002))));
      const qty = num('#b-qty'), rp = qty * per / s.equity * 100, pp_ = qty * q.price * q.fx / s.equity * 100, cost = qty * q.price * q.fx * (1 + rules.cost_pct / 100);
      $('#b-calc', d).innerHTML = `Kostnad <b>${kr(cost)}</b> · förlust om stoppet träffas <b>${kr(qty * per)}</b> (<b class="${rp > rules.max_risk_pct ? 'neg' : 'pos'}">${nf(rp, 1)} %</b> av portföljen) · position <b class="${pp_ > rules.max_pos_pct ? 'neg' : 'pos'}">${nf(pp_, 0)} %</b> av portföljen
        ${rp > rules.max_risk_pct ? `<div class="neg">Risken är över ${rules.max_risk_pct} %: du får inga processpoäng för riskdelen.</div>` : ''}${pp_ > rules.max_pos_pct ? `<div class="neg">Positionen är över ${rules.max_pos_pct} %: du får inga processpoäng för storleken.</div>` : ''}${cost > s.cash ? '<div class="neg">Det räcker inte med kontanter.</div>' : ''}`;
      $('#b-ok', d).disabled = !(qty > 0) || cost > s.cash;
    };
    $('#b-x', d).onclick = () => d.close();
    $('#b-q', d).onclick = async () => {
      const t = $('#b-t', d).value.trim();
      if (!t) return;
      try {
        q = await api('/paper/quote?ticker=' + encodeURIComponent(t) + (PAPER.pid ? '&pid=' + PAPER.pid : ''));
        $('#b-q-out', d).innerHTML = `<b>${esc(q.name)}</b> (${esc(q.ticker)}): köper vid senaste stängning <b>${nf(q.price, 2)} ${esc(q.currency)}</b> (${esc(q.last_date)}) · dagligt brus (ATR) ${nf(q.atr_pct, 1)} %${q.signal && q.signal.score != null ? ` · signalbetyg ${q.signal.score > 0 ? '+' : ''}${q.signal.score} (${esc(q.signal.label || '')})` : ''}${q.currency !== 'SEK' ? ` · 1 ${esc(q.currency)} = ${nf(q.fx, 2)} kr` : ''}}${(q.links || []).length ? `<div class="hint" style="margin-top:6px"><b>Överlapp med dina öppna innehav:</b> ${q.links.map(l => `${esc(l.ticker)} (${esc(l.text)})`).join('; ')}. Bolag som hänger ihop kan falla samtidigt, så risken är större än den ser ut.</div>` : ''}`;
        $('#b-form', d).hidden = false;
        $('#b-stop', d).value = nf(q.price - 2 * q.atr, 2).replace(/\s/g, '');
        $('#b-presets', d).innerHTML = [['1,5 ATR', 1.5], ['2 ATR', 2], ['3 ATR', 3]].map(([l, m]) => `<span class="chip" data-m="${m}">${l} under</span>`).join('') + [5, 8, 12].map(p => `<span class="chip" data-p="${p}">${p} % under</span>`).join('');
        $$('#b-presets .chip', d).forEach(c => c.onclick = () => { $('#b-stop', d).value = (c.dataset.m ? q.price - c.dataset.m * q.atr : q.price * (1 - c.dataset.p / 100)).toFixed(2).replace('.', ','); qtyTouched = false; calc(); });
        qtyTouched = false; calc();
      } catch (e) { toast(e.message, true); }
    };
    ['#b-stop', '#b-risk'].forEach(id => { $(id, d).oninput = () => { qtyTouched = false; calc(); }; });
    $('#b-qty', d).oninput = () => { qtyTouched = true; calc(); };
    $('#b-ok', d).onclick = async () => {
      try {
        await api(`/paper/${s.id}/buy`, { method: 'POST', body: { ticker: q.ticker, qty: num('#b-qty'), stop: num('#b-stop'), target: isNaN(num('#b-tg')) ? null : num('#b-tg'), thesis: $('#b-th', d).value, invalidation: $('#b-inv', d).value, horizon_days: parseInt($('#b-hz', d).value) || 90 } });
        d.close(); toast('Affär genomförd (virtuellt)'); gameCheck(); renderView();
      } catch (e) { toast(e.message, true); }
    };
  }, 'wide');
}

function closeDialog(tid, d0) {
  const t = d0.open.find(x => x.id === tid);
  dialog(`<div class="g-head"><h3>Stäng ${esc(t.ticker)}</h3></div><p>Du säljer vid senaste stängningskurs (${nf(t.price, 2)} ${esc(t.currency)}). Resultat just nu: <b class="${cls(t.pnl_pct)}">${pct(t.pnl_pct)}</b>.</p>
    <label class="fld"><span>Varför stänger du?</span><select id="c-r">${Object.entries(d0.reasons).map(([k, l]) => `<option value="${k}">${esc(l)}</option>`).join('')}</select></label>
    <div class="dlg-actions"><button class="btn" id="c-x">Avbryt</button><button class="btn primary" id="c-ok">Stäng positionen</button></div>`, d => {
    $('#c-x', d).onclick = () => d.close();
    $('#c-ok', d).onclick = async () => {
      try { await api(`/paper/${PAPER.pid}/trades/${tid}/close`, { method: 'POST', body: { reason: $('#c-r', d).value } }); d.close(); toast('Positionen stängd. Glöm inte att granska den.'); gameCheck(); renderView(); } catch (e) { toast(e.message, true); }
    };
  });
}

function stopDialog(t) {
  dialog(`<div class="g-head"><h3>Höj stopp i ${esc(t.ticker)}</h3></div><p>Nuvarande stopp ${nf(t.stop, 2)}, kurs ${nf(t.price, 2)}. Ett stopp får bara flyttas uppåt: att sänka det för att slippa bli utstoppad är precis det beteende övningen ska bryta.</p>
    <label class="fld"><span>Nytt stopp</span><input id="s-v" inputmode="decimal" value="${nf(t.stop, 2).replace(/\s/g, '')}"></label>
    <div class="dlg-actions"><button class="btn" id="s-x">Avbryt</button><button class="btn primary" id="s-ok">Spara</button></div>`, d => {
    $('#s-x', d).onclick = () => d.close();
    $('#s-ok', d).onclick = async () => {
      try { await api(`/paper/${PAPER.pid}/trades/${t.id}/stop`, { method: 'PUT', body: { stop: parseFloat($('#s-v', d).value.replace(/\s/g, '').replace(',', '.')) } }); d.close(); renderView(); } catch (e) { toast(e.message, true); }
    };
  });
}

function reviewDialog(t) {
  dialog(`<div class="g-head"><h3>Granska ${esc(t.ticker)}</h3><span class="mut">${esc(REASON_SV[t.exit_reason] || '')} · ${pct(t.pnl_pct)} · ${t.r == null ? '' : nf(t.r, 1) + ' R'}</span></div>
    <div class="g-ex"><b>Din tes:</b> ${esc(t.thesis)}<br><b>Fel om:</b> ${esc(t.invalidation)}</div>
    <p class="small">Bedöm processen, inte bara utfallet: höll tesen, följde du planen, var storleken rimlig? Vad skulle du göra annorlunda?</p>
    <label class="fld"><span>Lärdom (minst 20 tecken)${info('hindsight')}</span><textarea id="r-l" rows="4"></textarea></label>
    <div class="dlg-actions"><button class="btn" id="r-x">Avbryt</button><button class="btn primary" id="r-ok">Spara granskning</button></div>`, d => {
    $('#r-x', d).onclick = () => d.close();
    $('#r-ok', d).onclick = async () => {
      try { await api(`/paper/${PAPER.pid}/trades/${t.id}/review`, { method: 'PUT', body: { lesson: $('#r-l', d).value } }); d.close(); toast('Granskning sparad'); gameCheck(); renderView(); } catch (e) { toast(e.message, true); }
    };
  });
}
