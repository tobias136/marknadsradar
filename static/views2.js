/* Vyer för Makro, Backtest, Journal och Portfölj. Använder hjälpare från app.js (esc, nf, pct, cls, info, guide ...). */

const ACTION_SV = { buy: 'Köper', add: 'Köper mer', sell: 'Säljer', trim: 'Minskar', hold: 'Behåller', watch: 'Bevakar' };
const OUTCOME_SV = { as_planned: 'Som planerat', not_as_planned: 'Inte som planerat', unclear: 'Oklart' };
const fmtDate = s => (s || '').slice(0, 10);
const kr = v => v == null ? '–' : nf(v, 0) + ' kr';

/* ============================================================== MAKRO */
async function viewMacro(v, rid) {
  const m = await api('/macro');
  if (stale(rid)) return;
  const rg = m.regime;
  const card = c => c.missing ? `<div class="card"><h4>${esc(c.name)}${info(c.gloss)}</h4><div class="mut">Ingen data ännu. Tryck Uppdatera.</div></div>` : `
    <div class="card macro"><h4>${esc(c.name)}${info(c.gloss)}</h4>
      <div class="big" style="font-size:24px">${nf(c.last, c.last > 1000 ? 0 : 2)} <span class="mut" style="font-size:13px">${esc(c.unit || '')}</span></div>
      <div style="margin:4px 0">${spark(c.spark)}</div>
      <div class="small">${c.ch1d != null ? `1d <span class="${cls(c.ch1d)}">${nf(c.ch1d, 2)}${c.kind === 'level' ? '' : ' %'}</span> · ` : ''}1m <span class="${cls(c.ch1m)}">${c.ch1m == null ? '–' : (c.ch1m > 0 ? '+' : '') + nf(c.ch1m, 2)}${c.kind === 'level' || c.unit === 'p.e.' ? '' : ' %'}</span> · läge i 1-årsspannet: ${nf(c.pctile, 0)} %</div>
      ${c.text ? `<div class="mtext">${esc(c.text)}</div>` : ''}</div>`;
  v.innerHTML = guide('macro') + `
  <div class="panel"><div class="panel-head"><h3>Marknadsklimat${info('regime')}</h3><span class="mut" style="font-size:12px">regelbaserat · beskriver nuläget, förutspår inget</span></div>
    ${rg ? `<div class="sig-top"><div class="sig-big s-${rg.key === 'on' ? 'pos' : rg.key === 'off' ? 'neg' : 'neutral'}" style="font-size:30px">${esc(rg.label)}</div>
      <div style="flex:1;min-width:260px"><div>${esc(rg.lay)}</div></div></div>
      <ul class="plain">${rg.reasons.map(r => `<li><span class="pts ${cls(r.pts)}">${r.pts > 0 ? '+' : ''}${r.pts}</span> ${esc(r.text)}</li>`).join('')}</ul>
      <div class="disclaimer">${esc(rg.disclaimer)}</div>` : '<div class="mut">För lite data ännu. Tryck Uppdatera så hämtas makrodata.</div>'}</div>
  <div class="kv macro-grid">${m.derived.map(card).join('')}${m.cards.map(card).join('')}</div>`;
  bindGuides();
}

/* ============================================================ BACKTEST */
async function viewBacktest(v, rid) {
  const bt = S.bt || (S.bt = { h: 21 });
  const lst = curList();
  const hs = [[5, '1 vecka (5 d)'], [21, '1 månad (21 d)'], [63, '3 månader (63 d)']];
  v.innerHTML = guide('backtest') + `<div class="panel"><div class="panel-head"><div><h3>Backtest av signalbetyget${info('backtest')}</h3>
    <div class="hint" style="margin:0">Lista: <b>${esc(lst.name)}</b> · testar den tekniska delen (trend, momentum, relativ styrka). Mäter vad som hände ${info('forward')} efter varje signal.</div></div>
    <div class="seg" id="seg-h">${hs.map(([k, l]) => `<button data-v="${k}" class="${bt.h === k ? 'on' : ''}">${l}</button>`).join('')}</div></div>
    <div id="bt-body" class="loading">Räknar på historiken… (några sekunder)</div></div>`;
  bindGuides();
  $$('#seg-h button').forEach(b => b.onclick = () => { bt.h = +b.dataset.v; renderView(); });
  let r;
  try { r = await api(`/lists/${lst.id}/backtest?h=${bt.h}`); } catch (e) { if (!stale(rid)) $('#bt-body').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (stale(rid)) return;
  const body = $('#bt-body');
  body.className = '';
  if (r.error) { body.innerHTML = `<div class="empty">${esc(r.error)}</div>`; return; }
  const lvl = { support: 'pos', hint: 'neutral', none: 'neutral', few: 'neutral', reverse: 'neg' }[r.edge.level] || 'neutral';
  const base = r.baseline;
  const row = (label, st, extra = '') => `<tr><td class="l">${label}</td><td>${st.n || 0}</td><td>${st.n ? '≈ ' + nf(st.n_eff, 0) : '–'}</td><td class="${cls(st.avg)}">${st.n ? pct(st.avg, 2) : '–'}</td>
    <td>${st.n ? nf(st.hit, 0) + ' %' : '–'} ${st.hit_lo != null ? `<span class="mut small">(${nf(st.hit_lo, 0)}–${nf(st.hit_hi, 0)})</span>` : ''}</td>
    <td>${st.beat == null ? '–' : nf(st.beat, 0) + ' %'}</td><td class="${cls(extra)}">${extra === '' || extra == null ? '–' : pp(extra, 2)}</td></tr>`;
  const s = r.strategy;
  body.innerHTML = `
    <div class="invalid" style="margin:0 0 14px;border-color:${lvl === 'pos' ? 'rgba(47,192,122,.4)' : lvl === 'neg' ? 'rgba(240,96,93,.4)' : 'rgba(232,179,74,.3)'}">
      <b>Slutsats${info('zscore')}:</b> ${esc(r.edge.text || '')}</div>
    <div class="small mut" style="margin-bottom:8px">${r.tickers_used} av ${r.tickers_total} värdepapper hade tillräcklig historik · ${r.samples.toLocaleString('sv-SE')} dag-observationer · framåt ${r.horizon} handelsdagar${r.skipped.length ? ` · för lite historik: ${esc(r.skipped.join(', '))}` : ''}</div>
    <div class="tbl-scroll"><table><thead><tr><th class="l">Betyg den dagen</th><th>Dagar</th><th>Oberoende ≈</th><th>Snitt efteråt${info('forward')}</th><th>Andel positiva${info('hitrate')} (95 %-intervall)</th><th>Slog indexet</th><th>Mot alla dagar</th></tr></thead><tbody>
      ${row('<i>Alla dagar (jämförelse)</i>', base)}
      ${r.buckets.map(b => row(esc(b.label), b, b.excess)).join('')}</tbody></table></div>
    <div class="hint">Läs så här: om betyget haft värde bör “Starkt positivt” ligga tydligt över “Alla dagar” och “Starkt negativt” under. Se förbehållen längre ned innan du drar slutsatser.</div>

    <h3 style="margin-top:20px">Enkel strategi mot att bara äga${info('strategy')}</h3>
    <div class="cards">
      <div class="card"><div class="lbl">Strategi: äg vid ≥ +20</div><div class="big ${cls(s.ret_strategy)}">${pct(s.ret_strategy, 0)}</div><div class="small">största nedgång ${pct(s.dd_strategy, 0, false)}</div></div>
      <div class="card"><div class="lbl">Bara äga</div><div class="big ${cls(s.ret_bh)}">${pct(s.ret_bh, 0)}</div><div class="small">största nedgång ${pct(s.dd_bh, 0, false)}</div></div>
      <div class="card"><div class="lbl">Ägd tid</div><div class="big">${nf(s.invested, 0)} %</div><div class="small">${nf(s.trades_per_year, 1)} byten per år</div></div>
      <div class="card"><div class="lbl">Slog att äga</div><div class="big">${s.wins}/${s.n}</div><div class="small">värdepapper, ${esc(s.from)} – ${esc(s.to)}</div></div>
    </div>
    <div class="chart-wrap short" style="margin-top:12px"><canvas id="ch-bt"></canvas></div>
    <div class="tbl-scroll" style="margin-top:12px"><table><thead><tr><th class="l">Värdepapper</th><th>Strategi</th><th>Äga</th><th>Nedgång strategi</th><th>Nedgång äga</th><th>Ägd tid</th><th>Betyg nu</th></tr></thead><tbody>
      ${r.per_ticker.map(p => `<tr class="click" data-t="${esc(p.ticker)}"><td class="l tk">${esc(p.ticker)}</td><td class="${cls(p.ret_strategy)}">${pct(p.ret_strategy, 0)}</td><td class="${cls(p.ret_bh)}">${pct(p.ret_bh, 0)}</td><td>${pct(p.dd_strategy, 0, false)}</td><td>${pct(p.dd_bh, 0, false)}</td><td>${nf(p.invested, 0)} %</td><td>${p.last_score == null ? '–' : (p.last_score > 0 ? '+' : '') + p.last_score}</td></tr>`).join('')}</tbody></table></div>

    <div class="invalid" style="margin-top:18px"><b>Förbehåll: läs innan du drar slutsatser${info('overfit')}</b>
      <ul class="plain" style="margin-top:6px">${r.caveats.map(c => `<li>${esc(c)}</li>`).join('')}</ul>
      <div class="mut small">Se även ${'<span class="chip on" data-gk="survivorship">Urvalsfel</span>'} och ${'<span class="chip on" data-gk="overfit">Överanpassning</span>'}.</div></div>`;
  $$('#bt-body [data-gk]').forEach(c => c.onclick = () => openInfo(c.dataset.gk));
  $$('#bt-body tr.click').forEach(tr => tr.onclick = () => openStock(tr.dataset.t));
  mkChart('ch-bt', {
    type: 'line',
    data: { labels: r.curve.dates, datasets: [
      { label: 'Strategi (jämnt viktat)', data: r.curve.strategy, borderColor: '#5aa0ff', borderWidth: 2, pointRadius: 0 },
      { label: 'Bara äga (jämnt viktat)', data: r.curve.buyhold, borderColor: '#e8b34a', borderWidth: 2, pointRadius: 0, borderDash: [5, 4] }] },
    options: { maintainAspectRatio: false, animation: { duration: 250 }, interaction: { mode: 'index', intersect: false },
      plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } } },
      scales: { x: { ticks: { maxTicksLimit: 8 }, grid: { display: false } }, y: { position: 'right', grid: { color: '#1d2736' } } } },
  });
}

/* ============================================================== JOURNAL */
async function viewJournal(v, rid) {
  const j = await api('/journal');
  if (stale(rid)) return;
  const st = j.stats;
  const tickers = [...new Set((S.ov ? S.ov.tickers : []).map(t => t.ticker))];
  const pre = S.jPrefill || (S.stock && S.stock.ticker) || '';
  S.jPrefill = '';
  const eHTML = e => {
    const done = e.status === 'reviewed';
    return `<div class="jentry ${e.due ? 'due' : ''}" data-id="${e.id}">
      <div class="jhead"><span class="tk">${esc(e.ticker)}</span> <span class="tag">${esc(ACTION_SV[e.action] || e.action)}</span>
        <span class="mut">${fmtDate(e.created)}${e.price != null ? ' · kurs ' + nf(e.price, 2) + ' ' + esc(e.currency || '') : ''}</span>
        ${e.signal_score != null ? `<span class="sig s-${e.signal_score >= 50 ? 'strong_pos' : e.signal_score >= 20 ? 'pos' : e.signal_score > -20 ? 'neutral' : e.signal_score > -50 ? 'neg' : 'strong_neg'}" title="Signalbetyg när beslutet loggades">${e.signal_score > 0 ? '+' : ''}${e.signal_score} då</span>` : ''}
        ${e.due ? '<span class="tag flag">⚑ dags att granska</span>' : ''}${done ? `<span class="tag good">granskad ${fmtDate(e.closed_on)}</span>` : `<span class="mut small">granska senast ${esc(e.review_on || '–')}</span>`}
        <span class="spacer"></span><button class="btn sm" data-del="${e.id}" title="Ta bort">✕</button></div>
      <div class="jbody"><div><b>Tes:</b> ${esc(e.thesis) || '<span class="mut">(ingen skriven)</span>'}</div>
        <div><b>Jag ändrar mig om:</b> ${esc(e.invalidation) || '<span class="mut">(ej angivet)</span>'}</div>
        <div class="small" style="margin-top:6px">${done ? 'Kurs vid granskning' : 'Kurs nu'}: ${e.price_now != null ? nf(done ? e.closed_price : e.price_now, 2) : '–'} · förändring sedan beslutet <span class="${cls(e.ret_since)}">${pct(e.ret_since, 1)}</span>
          ${e.dir_return != null && ['buy', 'add', 'sell', 'trim'].includes(e.action) ? ` · <b>i beslutets riktning</b> <span class="${cls(e.dir_return)}">${pct(e.dir_return, 1)}</span>` : ''}</div>
        ${done ? `<div style="margin-top:6px"><span class="tag">${esc(OUTCOME_SV[e.outcome] || e.outcome)}</span> <b>Lärdom:</b> ${esc(e.lesson) || '<span class="mut">–</span>'}</div>` : `<div style="margin-top:8px"><button class="btn sm primary" data-rev="${e.id}">Granska beslutet</button></div><div class="rev-slot"></div>`}
      </div></div>`;
  };
  v.innerHTML = guide('journal') + `
  <div class="panel"><h3>Logga ett beslut${info('journal')}</h3>
    <div class="hint">Skriv medan du fortfarande inte vet hur det går. Det är hela poängen${info('hindsight')}. Appen sparar kursen och signalbetyget just nu.</div>
    <div class="form-grid">
      <label>Värdepapper<input id="j-t" list="j-tl" value="${esc(pre)}" placeholder="t.ex. XLK eller VOLV-B.ST"><datalist id="j-tl">${tickers.map(t => `<option value="${esc(t)}">`).join('')}</datalist></label>
      <label>Beslut<select id="j-a">${Object.entries(ACTION_SV).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></label>
      <label>Ger idén tid<select id="j-h"><option value="30">1 månad</option><option value="90" selected>3 månader</option><option value="180">6 månader</option><option value="365">1 år</option></select></label>
    </div>
    <label class="blk"><span>Tes${info('thesis')}: varför, och vad förväntar du dig?</span><textarea id="j-th" rows="3" placeholder="T.ex. Orderingången växer och marginalerna ökar. Jag förväntar mig bättre rapport än konsensus."></textarea></label>
    <label class="blk"><span>Jag ändrar mig om …${info('invalid')}</span><textarea id="j-in" rows="2" placeholder="T.ex. Kursen stänger under ATR-stoppet, eller marginalen sjunker två kvartal i rad."></textarea></label>
    <button class="btn primary" id="j-save">Spara i journalen</button> <span class="mut small" id="j-msg"></span></div>

  <div class="panel"><h3>Din statistik</h3>
    ${st.total ? `<div class="cards">
      <div class="card"><div class="lbl">Beslut</div><div class="big">${st.total}</div><div class="small">${st.open} öppna · ${st.reviewed} granskade${st.due ? ` · <span class="warnc">${st.due} dags att granska</span>` : ''}</div></div>
      <div class="card"><div class="lbl">Process</div><div class="big">${st.total ? nf(100 * st.with_invalidation / st.total, 0) : 0} %</div><div class="small">har en invalideringsnivå · ${st.with_thesis}/${st.total} har en riktig tes</div></div>
      <div class="card"><div class="lbl">Träffsäkerhet${info('hitrate')}</div><div class="big">${st.hit_rate == null ? '–' : nf(st.hit_rate, 0) + ' %'}</div><div class="small">${st.n_acted} granskade köp/sälj · snitt ${pct(st.avg_dir_return, 1)} ${st.enough ? '' : '· <b>preliminärt: för få för slutsatser</b>'}</div></div>
      <div class="card"><div class="lbl">Följde du signalen?</div><div class="small" style="margin-top:6px">Med signalen: ${st.follow.with.n} beslut${st.follow.with.avg == null ? '' : ', snitt ' + pct(st.follow.with.avg, 1)}<br>Mot signalen: ${st.follow.against.n} beslut${st.follow.against.avg == null ? '' : ', snitt ' + pct(st.follow.against.avg, 1)}<br><span class="mut">Små urval ger slumpresultat.</span></div></div>
    </div>` : '<div class="mut">Ingen statistik ännu. Logga ditt första beslut ovan.</div>'}</div>

  <div class="panel"><h3>Beslut</h3>${j.entries.length ? j.entries.map(eHTML).join('') : '<div class="mut">Inga beslut loggade ännu.</div>'}</div>`;
  bindGuides();
  $('#j-save').onclick = async () => {
    const body = { ticker: $('#j-t').value.trim(), action: $('#j-a').value, thesis: $('#j-th').value, invalidation: $('#j-in').value, horizon_days: +$('#j-h').value };
    if (!body.ticker) { $('#j-msg').textContent = 'Ange en ticker.'; return; }
    try { await api('/journal', { method: 'POST', body }); toast('Beslutet sparades'); gameCheck(); renderView(); } catch (e) { $('#j-msg').textContent = e.message; }
  };
  $$('[data-del]').forEach(b => b.onclick = async () => { if (confirm('Ta bort beslutet från journalen?')) { await api(`/journal/${b.dataset.del}`, { method: 'DELETE' }); renderView(); } });
  $$('[data-rev]').forEach(b => b.onclick = () => {
    const slot = b.closest('.jentry').querySelector('.rev-slot');
    slot.innerHTML = `<div class="rev"><label class="blk">Blev det som du trodde?<select class="r-o">${Object.entries(OUTCOME_SV).map(([k, l]) => `<option value="${k}">${l}</option>`).join('')}</select></label>
      <label class="blk">Lärdom: vad ska du göra annorlunda, eller göra igen?<textarea class="r-l" rows="2"></textarea></label>
      <div class="hint">Bedöm processen: stämde tesen och följde du din plan? Ett bra beslut kan ge förlust och tvärtom.</div>
      <button class="btn primary r-ok">Spara granskning</button></div>`;
    slot.querySelector('.r-ok').onclick = async () => {
      await api(`/journal/${b.dataset.rev}/review`, { method: 'PUT', body: { outcome: slot.querySelector('.r-o').value, lesson: slot.querySelector('.r-l').value } });
      toast('Granskningen sparades'); gameCheck(); renderView();
    };
  });
}

/* ============================================================== PORTFÖLJ */
async function viewPortfolio(v, rid) {
  const p = await api('/portfolio');
  if (stale(rid)) return;
  const t = p.totals || {};
  const known = [...new Set((S.ov ? S.ov.tickers : []).map(x => x.ticker))];
  const bar = (items) => items.map(x => `<div class="hbar"><span class="hl">${esc(x.name)}</span><span class="hb"><i style="width:${Math.min(100, x.weight)}%"></i></span><span class="hv">${nf(x.weight, 0)} %</span></div>`).join('');
  const hrow = h => `<tr data-id="${h.id}"><td class="l">${h.ticker ? `<span class="tk link" data-open="${esc(h.ticker)}">${esc(h.ticker)}</span>` : `<input class="tk-in" list="pf-tl" placeholder="Yahoo-ticker" data-suggest="${esc(h.name)}">`}</td>
    <td class="l">${esc(h.name || '')}${h.status === 'nodata' ? ' <span class="tag flag">saknar kurs</span>' : ''}${h.status === 'nofx' ? ' <span class="tag flag">saknar valutakurs</span>' : ''}</td>
    <td>${nf(h.qty, h.qty % 1 ? 2 : 0)}</td><td>${h.avg_cost != null ? nf(h.avg_cost, 2) : '–'}</td><td>${h.last != null ? nf(h.last, 2) + ' ' + esc(h.price_cur || '') : '–'}</td>
    <td>${kr(h.value_sek)}</td><td>${h.weight == null ? '–' : nf(h.weight, 1) + ' %'}</td><td class="${cls(h.pl_pct)}">${pct(h.pl_pct, 1)}</td>
    <td>${h.signal && h.signal.score != null ? `<span class="sig s-${h.signal.key}">${h.signal.score > 0 ? '+' : ''}${h.signal.score}</span>` : '–'}</td><td class="l">${esc(h.sector || '–')}</td>
    <td><button class="btn sm" data-del="${h.id}">✕</button></td></tr>`;
  v.innerHTML = guide('portfolio') + `
  <datalist id="pf-tl">${known.map(x => `<option value="${esc(x)}">`).join('')}</datalist>
  ${(p.holdings || []).length ? `
  <div class="cards">
    <div class="card"><div class="lbl">Portföljvärde</div><div class="big">${kr(t.value_sek)}</div><div class="small">${t.n_valued} av ${t.n} innehav har kurs${t.n_unmapped ? ` · <span class="warnc">${t.n_unmapped} saknar ticker</span>` : ''}</div></div>
    ${p.concentration ? `<div class="card"><div class="lbl">Koncentration${info('portfolio')}</div><div class="big">${nf(p.concentration.top1, 0)} %</div><div class="small">största innehavet · tre största ${nf(p.concentration.top3, 0)} %</div></div>
    <div class="card"><div class="lbl">Effektivt antal${info('effn')}</div><div class="big">${nf(p.concentration.effective_n, 1)}</div><div class="small">av ${t.n_valued} innehav</div></div>` : ''}
    ${p.risk ? `<div class="card"><div class="lbl">Svängning per år${info('vol')}</div><div class="big">${nf(p.risk.vol, 1)} %</div><div class="small">största nedgång 1 år ${pct(p.risk.max_dd_1y, 1, false)} · beta ${p.risk.beta == null ? '–' : nf(p.risk.beta, 2)}${info('beta')}</div></div>
    <div class="card"><div class="lbl">Spridningsvinst${info('divratio')}</div><div class="big">${p.risk.diversification == null ? '–' : nf(p.risk.diversification, 2) + '×'}</div><div class="small">1,0× = ingen spridning</div></div>` : ''}
  </div>
  <div class="panel"><h3>Att tänka på</h3><ul class="plain">${p.warnings.map(w => `<li><span class="wl w-${w.level}">${{ high: 'Viktigt', medium: 'Tänk på', info: 'Info', ok: 'OK' }[w.level]}</span> ${esc(w.text)}</li>`).join('')}</ul>
    <div class="disclaimer">Enkla tumregler, inte rådgivning. Gränserna (t.ex. 25 % per bolag) är vanliga riktmärken, inte lagar.</div></div>` : ''}
  <div class="panel"><div class="panel-head"><h3>Innehav</h3></div>
    ${(p.holdings || []).length ? `<div class="tbl-scroll"><table class="pf"><thead><tr><th class="l">Ticker</th><th class="l">Namn</th><th>Antal</th><th>Snittpris</th><th>Kurs</th><th>Värde</th><th>Vikt</th><th>+/−</th><th>Signal${info('signal')}</th><th class="l">Sektor</th><th></th></tr></thead><tbody>${p.holdings.map(hrow).join('')}</tbody></table></div>
    <div class="hint">Värden i kronor. Valutor räknas om med senaste kurs. +/− jämför kursen med snittpriset i bolagets valuta.</div>` : '<div class="mut">Inga innehav ännu. Lägg till manuellt eller importera nedan.</div>'}
    <h4 style="margin:16px 0 6px">Lägg till innehav</h4>
    <div class="row-add"><input id="h-t" list="pf-tl" placeholder="Ticker (t.ex. VOLV-B.ST)" style="width:180px"><input id="h-q" type="number" step="any" placeholder="Antal" style="width:100px"><input id="h-c" type="number" step="any" placeholder="Snittpris (valfritt)" style="width:150px"><button class="btn primary" id="h-add">Lägg till</button><span class="mut small" id="h-msg"></span></div>
    <details class="imp"><summary>Importera från Avanza (CSV)${info('csvimport')}</summary>
      <div class="hint">Exportera transaktioner från Avanza (Transaktioner → exportera) och välj filen, eller klistra in innehållet. Inget skickas utanför din dator. Ny import ersätter tidigare importerade innehav men behåller dina ticker-kopplingar.</div>
      <input type="file" id="imp-file" accept=".csv,.txt"><textarea id="imp-text" rows="4" placeholder="…eller klistra in CSV här" style="margin-top:8px"></textarea>
      <div style="margin-top:8px"><button class="btn" id="imp-prev">Förhandsgranska</button> <button class="btn primary" id="imp-apply" disabled>Importera</button></div><div id="imp-out"></div></details></div>
  ${(p.sectors || []).length ? `<div class="panel"><div class="two"><div><h3>Sektorer</h3>${bar(p.sectors)}</div><div><h3>Valutor${info('fx')}</h3>${bar(p.currencies)}</div></div>
    ${(p.pairs || []).length ? `<h4 style="margin:14px 0 6px">Mest lika innehav${info('corr')}</h4><div class="small">${p.pairs.slice(0, 5).map(x => `<span class="tag ${x.corr >= 0.8 ? 'flag' : ''}">${esc(x.a)} · ${esc(x.b)} ${nf(x.corr, 2)}</span>`).join('')}</div>` : ''}</div>` : ''}
  <div class="panel"><h3>Positionsstorlek${info('possize')}</h3>
    <div class="hint">Räkna ut hur många aktier du kan köpa om du på förhand bestämmer hur mycket du högst vill förlora. Stoppnivån är ett beslut du fattar i förväg, ingen garanti att du kommer ur där (kursen kan hoppa förbi).</div>
    <div class="form-grid">
      <label>Ticker (hämtar kurs och ATR-stopp)<input id="ps-t" list="pf-tl" placeholder="t.ex. XLK"></label>
      <label>Kapital (kr)<input id="ps-cap" type="number" value="${Math.round(t.value_sek || 100000)}"></label>
      <label>Max förlust i affären (% av kapitalet)<input id="ps-r" type="number" step="0.1" value="1"></label>
      <label>Köpkurs<input id="ps-e" type="number" step="any"></label>
      <label>Stoppnivå<input id="ps-s" type="number" step="any"></label>
      <label>Valutakurs till kronor<input id="ps-fx" type="number" step="any" value="1"></label>
    </div><div id="ps-out" class="invalid" style="margin-top:10px">Fyll i köpkurs och stoppnivå.</div></div>`;
  bindGuides();
  const msg = s => { $('#h-msg').textContent = s; };
  $('#h-add').onclick = async () => {
    const body = { ticker: $('#h-t').value.trim(), qty: +$('#h-q').value, avg_cost: $('#h-c').value === '' ? null : +$('#h-c').value };
    if (!body.ticker || !(body.qty > 0)) { msg('Ange ticker och antal.'); return; }
    try { await api('/portfolio/holdings', { method: 'POST', body }); toast('Innehav tillagt. Hämtar kurs…'); gameCheck(); setTimeout(renderView, 2500); } catch (e) { msg(e.message); }
  };
  $$('[data-del]').forEach(b => b.onclick = async () => { if (confirm('Ta bort innehavet?')) { await api(`/portfolio/holdings/${b.dataset.del}`, { method: 'DELETE' }); renderView(); } });
  $$('[data-open]').forEach(el => el.onclick = () => openStock(el.dataset.open));
  $$('input.tk-in').forEach(inp => {
    inp.addEventListener('focus', async () => {
      if (inp.dataset.loaded) return; inp.dataset.loaded = 1;
      try { const s = await api('/portfolio/suggest?name=' + encodeURIComponent(inp.dataset.suggest)); if (s.length) inp.placeholder = 'Förslag: ' + s.map(x => x.ticker).join(', '); } catch (e) { /* ok */ }
    });
    inp.onkeydown = async e => {
      if (e.key !== 'Enter') return;
      const id = inp.closest('tr').dataset.id;
      await api(`/portfolio/holdings/${id}`, { method: 'PATCH', body: { ticker: inp.value.trim() } });
      toast('Ticker kopplad. Hämtar kurs…'); setTimeout(renderView, 2500);
    };
  });
  // import
  let csvText = '';
  const prev = async () => {
    csvText = $('#imp-text').value;
    if (!csvText.trim()) { $('#imp-out').innerHTML = '<div class="mut">Välj en fil eller klistra in innehållet.</div>'; return; }
    const r = await api('/portfolio/import', { method: 'POST', body: { csv: csvText, apply: false } });
    if (r.error) { $('#imp-out').innerHTML = `<div class="neg" style="margin-top:8px">${esc(r.error)}</div>`; $('#imp-apply').disabled = true; return; }
    $('#imp-out').innerHTML = `<div class="small" style="margin:8px 0">${r.stats.rows} rader, ${r.stats.trades_used} köp/sälj användes. ${esc(r.stats.note)}</div>
      <div class="tbl-scroll"><table><thead><tr><th class="l">Värdepapper</th><th>Antal</th><th>Snittpris</th><th>Valuta</th><th class="l">Förslag på ticker</th></tr></thead><tbody>${r.holdings.map(h => `<tr><td class="l">${esc(h.name)}</td><td>${nf(h.qty, 2)}</td><td>${nf(h.avg_cost, 2)}</td><td>${esc(h.currency)}</td><td class="l">${h.suggestions.map(s => esc(s.ticker)).join(', ') || '<span class="mut">inget förslag: ange själv efter importen</span>'}</td></tr>`).join('')}</tbody></table></div>`;
    $('#imp-apply').disabled = !r.holdings.length;
  };
  $('#imp-file').onchange = async e => { const f = e.target.files[0]; if (f) { $('#imp-text').value = await f.text(); prev(); } };
  $('#imp-prev').onclick = prev;
  $('#imp-apply').onclick = async () => { const r = await api('/portfolio/import', { method: 'POST', body: { csv: csvText, apply: true } }); toast(`${r.imported} innehav importerade. Koppla dem till tickers i tabellen.`); gameCheck(); renderView(); };
  // positionsstorlek
  const calc = () => {
    const cap = +$('#ps-cap').value, r = +$('#ps-r').value, e = +$('#ps-e').value, s = +$('#ps-s').value, fx = +$('#ps-fx').value || 1;
    const out = $('#ps-out');
    if (!(cap > 0 && r > 0 && e > 0 && s > 0)) { out.innerHTML = 'Fyll i köpkurs och stoppnivå.'; return; }
    if (s >= e) { out.innerHTML = 'Stoppnivån måste ligga under köpkursen (för en köpt position).'; return; }
    const risk = cap * r / 100, per = (e - s) * fx, n = Math.floor(risk / per), val = n * e * fx;
    out.innerHTML = `Högsta förlust: <b>${kr(risk)}</b> (${nf(r, 1)} % av kapitalet). Risk per aktie: ${nf(e - s, 2)} (${nf((e - s) / e * 100, 1)} % av köpkursen).<br>
      Antal aktier: <b>${n.toLocaleString('sv-SE')}</b> · positionens värde ${kr(val)} = <b>${nf(val / cap * 100, 0)} %</b> av kapitalet.${val / cap > 0.25 ? '<br><span class="warnc">Positionen blir över 25 % av kapitalet. Då kan en stoppnivå som ligger nära vara orimlig, eller så är risken per affär större än du tänkt.</span>' : ''}`;
    if (typeof track === 'function') track('possize', '1');
  };
  ['ps-cap', 'ps-r', 'ps-e', 'ps-s', 'ps-fx'].forEach(id => $('#' + id).oninput = calc);
  $('#ps-t').onchange = async () => {
    const sym = $('#ps-t').value.trim().toUpperCase();
    if (!sym) return;
    try {
      const d = await api('/ticker/' + encodeURIComponent(sym));
      if (d.metrics) { $('#ps-e').value = d.metrics.last.toFixed(2); if (d.metrics.stop) $('#ps-s').value = d.metrics.stop.toFixed(2); const fxk = { USD: 'usdsek', EUR: 'eursek' }[d.currency]; if (d.currency === 'SEK') $('#ps-fx').value = 1; else if (fxk) { const mm = await api('/macro'); const c = mm.cards.find(x => x.key === fxk); if (c && !c.missing) $('#ps-fx').value = c.last.toFixed(3); } }
      calc();
    } catch (e) { /* ok */ }
  };
}
