/* Samband: lead-lag, händelsestudie och relationer mellan bolag. Beskrivande statistik, inget köpråd. */
const SB = { mode: 'leadlag', ticker: '', kind: 'move', thr: 2.5 };
const SB_MODES = [['leadlag', 'Lead-lag'], ['events', 'Händelser'], ['edges', 'Relationer']];
const sbPct = (v, d = 2) => v == null ? '–' : (v > 0 ? '+' : '') + nf(v * 100, d) + ' %';
const sbTickers = () => [...new Set((S.lists || []).flatMap(l => l.items.map(i => i.ticker)))].sort();

async function viewSamband(v, rid) {
  const tk = sbTickers();
  if (!SB.ticker || (tk.length && !tk.includes(SB.ticker))) SB.ticker = tk[0] || '';
  v.innerHTML = guide('samband') + `<div class="row-add"><div class="seg" id="sb-seg">${SB_MODES.map(([k, l]) => `<button data-k="${k}" class="${SB.mode === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <select id="sb-t"><option value="">${SB.mode === 'leadlag' ? 'Alla bolag (starkaste sambanden)' : 'Välj bolag'}</option>${tk.map(t => `<option ${t === SB.ticker && (SB.mode !== 'leadlag' || SB.pick) ? 'selected' : ''}>${esc(t)}</option>`).join('')}</select></div><div id="sb-body" class="loading">Räknar…</div>`;
  $$('#sb-seg button').forEach(b => b.onclick = () => { SB.mode = b.dataset.k; renderView(); });
  $('#sb-t').onchange = e => { if (e.target.value) { SB.ticker = e.target.value; SB.pick = true; } else { SB.pick = false; } renderView(); };
  const body = $('#sb-body');
  try {
    if (SB.mode === 'leadlag') await sbLeadlag(body, rid);
    else if (SB.mode === 'events') await sbEvents(body, rid);
    else await sbEdges(body, rid);
  } catch (e) { if (!stale(rid)) body.innerHTML = `<div class="empty">${esc(e.message)}</div>`; }
}

function sbHeader(d) {
  return `<p class="q-text">Rörelserna är <b>rensade från marknaden</b> (index) och mäts mellan alla par i dina listor med ${d.n_obs} handelsdagar (${esc(d.start || '')} till ${esc(d.end || '')}). Alla par testas samtidigt, så p-värdena <b>korrigeras för antal tester</b>${info('multiple')}.</p>
    <div class="hint">${d.n_tests} tester gjordes (${d.n_tickers} bolag, 1–5 dagars fördröjning). Av slump skulle ungefär ${nf(d.expected_false_p05 || 0, 0)} se signifikanta ut utan korrigering. Efter korrigering (FDR ${Math.round(d.fdr_q * 100)} %) återstår <b>${d.n_sig_total != null ? d.n_sig_total : d.n_sig}</b> samband, varav ungefär ${nf(d.expected_false_sig_total != null ? d.expected_false_sig_total : d.expected_false_sig, 1)} väntas vara falska.</div>`;
}

function sbPairRow(x, a, b, an, bn) {
  const dir = x.slope >= 0 ? 'upp' : 'ned';
  return `<tr><td class="l"><b>${esc(a)}</b> <span class="mut small">${esc(an)}</span> → <b>${esc(b)}</b> <span class="mut small">${esc(bn)}</span></td><td>${x.lag} d</td><td>${nf(x.r, 2)}</td>
    <td class="l small">+1 % hos ${esc(a)} → ${x.slope >= 0 ? '+' : ''}${nf(x.slope, 2)} % hos ${esc(b)}</td><td>${x.r1 == null ? '–' : nf(x.r1, 2)} / ${x.r2 == null ? '–' : nf(x.r2, 2)}</td><td class="${x.stable ? 'pos' : 'mut'}">${x.stable ? 'ja' : 'nej'}</td><td>${nf(x.q, 3)}</td></tr>`;
}
const SB_PAIR_HEAD = '<thead><tr><th class="l">Par (X leder Y)</th><th>Dröjsmål</th><th>r</th><th class="l">Storlek</th><th>Halvor (första / andra)</th><th>Stabil</th><th>q</th></tr></thead>';

async function sbLeadlag(body, rid) {
  const d = await api('/rel/leadlag' + (SB.pick && SB.ticker ? '?ticker=' + encodeURIComponent(SB.ticker) : ''));
  if (stale(rid)) return;
  if (d.n_tests === 0) { body.innerHTML = '<div class="empty">För lite kursdata för att räkna. Det behövs minst 300 handelsdagar och tre bolag. Tryck Uppdatera i en lista först.</div>'; return; }
  const best = d.best_uncorrected;
  let list;
  if (SB.pick && SB.ticker) {
    const t = SB.ticker;
    const tbl = (rows, a) => rows.length ? `<div class="tbl-scroll"><table>${SB_PAIR_HEAD}<tbody>${rows.map(x => sbPairRow(x, x.a, x.b, x.a === t ? '' : x.other_name, x.b === t ? '' : x.other_name)).join('')}</tbody></table></div>` : '<div class="mut small">Inga samband klarar korrigeringen.</div>';
    list = `<h4 style="margin:12px 0 6px">${esc(t)} leder (följs av andra)</h4>${tbl(d.leads)}<h4 style="margin:14px 0 6px">${esc(t)} följer (leds av andra)</h4>${tbl(d.led_by)}`;
  } else {
    list = `<h4 style="margin:12px 0 6px">Starkaste sambanden i hela urvalet</h4>${d.sig.length ? `<div class="tbl-scroll"><table>${SB_PAIR_HEAD}<tbody>${d.sig.map(x => sbPairRow(x, x.a, x.b, x.a_name, x.b_name)).join('')}</tbody></table></div>` : '<div class="g-ex"><b>Inga samband klarar korrigeringen.</b> Det är ett vanligt och ärligt resultat: mellan oberoende bolag finns sällan något att hämta dag för dag.</div>'}`;
  }
  body.innerHTML = sbHeader(d) + list + (best ? `<div class="small mut" style="margin-top:10px">Starkaste okorrigerade paret är ${esc(best.a)} → ${esc(best.b)} (${best.lag} d, r=${nf(best.r, 2)}, p=${nf(best.p, 4)}). Med så här många tester väntas något sådant av ren slump, vilket är anledningen till korrigeringen.</div>` : '')
    + `<div class="disclaimer" style="margin-top:12px">Ett samband i historiken är ingen garanti framåt och säger inget om orsak. 'Stabil' betyder att samma riktning syns i båda halvorna av perioden. Storleken är dagens rensade avkastning. Bolag på olika börser stänger vid olika tider, så USA → Sverige kan hamna en dag fel.</div>`;
}

async function sbEvents(body, rid) {
  if (!SB.pick && SB.ticker && !SB.ran) { /* standardval */ }
  body.className = '';
  body.innerHTML = `<p class="q-text">Hur rör sig <b>andra bolag</b> kring ett bolags rapporter eller kraftiga rörelser? Varje händelse är en observation, och med få händelser blir osäkerheten stor.${info('eventstudy')}</p>
    <div class="row-add"><select id="ev-k"><option value="move" ${SB.kind === 'move' ? 'selected' : ''}>Kraftiga rörelser (mer än … standardavvikelser)</option><option value="earnings" ${SB.kind === 'earnings' ? 'selected' : ''}>Rapporter</option></select>
      <input id="ev-thr" inputmode="decimal" value="${SB.thr}" style="max-width:80px" title="Tröskel i standardavvikelser (1,5–5)"> <button class="btn primary" id="ev-go">Kör</button></div>
    <div id="ev-out" style="margin-top:12px"><div class="mut small">Välj bolag uppe till höger (${esc(SB.pick ? SB.ticker : 'inget valt')}) och tryck Kör.</div></div>`;
  $('#ev-go').onclick = async () => {
    if (!SB.pick || !SB.ticker) { toast('Välj ett bolag i listan uppe till höger först', true); return; }
    SB.kind = $('#ev-k').value; SB.thr = parseFloat($('#ev-thr').value.replace(',', '.')) || 2.5;
    const out = $('#ev-out'); out.innerHTML = '<div class="loading">Räknar…</div>';
    try {
      const r = await api(`/rel/events?ticker=${encodeURIComponent(SB.ticker)}&kind=${SB.kind}&thr=${SB.thr}`);
      gameCheck();
      const cell = s => `${s.slope >= 0 ? '+' : ''}${nf(s.slope, 2)} <span class="mut small">(${nf(s.lo, 2)} till ${nf(s.hi, 2)})</span>`;
      out.innerHTML = `<div class="small" style="margin-bottom:8px"><b>${esc(r.ticker)}</b> ${esc(r.name)}: ${r.n_events} händelser (${r.n_up} upp, ${r.n_down} ned).</div>
        ${r.notes.map(n => `<div class="hint">${esc(n)}</div>`).join('')}
        ${r.rows.length ? `<div class="g-ex" style="margin:8px 0">${r.n_sig ? `<b>${r.n_sig} av ${r.rows.length} bolag</b> visar ett samband som klarar korrigeringen.` : '<b>Inget bolag klarar korrigeringen.</b> Då kan inget säkert sägas om att något följer efter.'} Siffrorna nedan är Y:s rörelse i % per +1 % hos ${esc(r.ticker)} (95 %-intervall).</div>
        <div class="tbl-scroll"><table><thead><tr><th class="l">Bolag Y</th><th>Händelser</th><th>Samma dag (dag 0–1)</th><th>q</th><th>Efteråt (dag 2–5)</th><th>q</th></tr></thead><tbody>
        ${r.rows.slice(0, 25).map(x => `<tr class="${x.co.sig || x.after.sig ? 'sig' : ''}"><td class="l"><b>${esc(x.ticker)}</b> <span class="mut small">${esc(x.name)}</span></td><td>${x.n}</td><td>${cell(x.co)}</td><td class="${x.co.sig ? 'pos' : 'mut'}">${nf(x.co.q, 3)}</td><td>${cell(x.after)}</td><td class="${x.after.sig ? 'pos' : 'mut'}">${nf(x.after.q, 3)}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
    } catch (e) { out.innerHTML = `<div class="fb bad">${esc(e.message)}</div>`; }
  };
}

async function sbEdges(body, rid) {
  const [cov, au, ed] = await Promise.all([api('/rel/coverage'), api('/rel/auto'), SB.pick && SB.ticker ? api('/rel/edges?ticker=' + encodeURIComponent(SB.ticker)) : Promise.resolve(null)]);
  if (stale(rid)) return;
  const autoHTML = sbAutoHTML(au);
  const covHTML = `<div class="hint"><b>Täckning:</b> ${cov.n_reviewed} av ${cov.n_tickers} bolag är genomgångna, ${cov.n_edges} relationer inlagda, ${cov.n_with_edges} bolag har minst en. Saknas ett bolag betyder det <b>inte</b> att det saknar relationer, bara att ingen gått igenom det.</div>`;
  let main = '<div class="mut" style="margin:10px 0">Välj ett bolag uppe till höger för att se och lägga in relationer.</div>';
  if (ed) {
    const t = ed.ticker;
    main = `<h4 style="margin:12px 0 6px">${esc(t)} <span class="mut small">${esc(ed.name)}</span> ${ed.reviewed ? `<span class="pos small">genomgånget ${esc(ed.reviewed)}</span>` : '<span class="mut small">ej genomgånget</span>'}</h4>
      ${ed.edges.length ? `<div class="tbl-scroll"><table><thead><tr><th class="l">Relation</th><th class="l">Styrka</th><th class="l">Källa</th><th class="l">Statistiskt stöd</th><th></th></tr></thead><tbody>${ed.edges.map(e => `<tr><td class="l"><b>${esc(e.a)}</b> ${esc(e.verb)} <b>${esc(e.b)}</b>${e.share_pct != null ? ` <span class="mut small">(${nf(e.share_pct, 0)} % av omsättningen)</span>` : ''}${e.amount ? ` <span class="mut small">${esc(e.amount)}</span>` : ''}${e.note ? `<div class="small mut">${esc(e.note)}</div>` : ''}${e.stale ? '<div class="small" style="color:var(--warn,#b7791f)">Äldre än 18 månader: granska igen</div>' : ''}${e.link_state === 'varning' ? `<div class="small" style="color:var(--warn,#b7791f)">Källänken svarar inte (${esc(e.link_note)}). Kan bero på att sajten blockerar robotar.</div>` : ''}</td>
        <td class="l small">${esc(e.strength_text)}<br><span class="mut">${esc(e.confidence)}${e.as_of ? ', ' + esc(e.as_of) : ''}</span></td><td class="l small"><a href="${esc(e.source_url)}" target="_blank" rel="noopener">${esc(e.source_title || 'Källa')}</a></td>
        <td class="l small">${e.stat ? `${esc(e.stat.a)} leder ${esc(e.stat.b)} (${e.stat.lag} d, r=${nf(e.stat.r, 2)}${e.stat.stable ? ', stabil' : ''})` : '<span class="mut">inget som klarar korrigeringen</span>'}</td><td><button class="btn sm" data-del="${e.id}">Ta bort</button></td></tr>`).join('')}</tbody></table></div>` : '<div class="mut small">Inga relationer inlagda för det här bolaget.</div>'}
      <div class="row-add" style="margin-top:8px"><button class="btn sm" id="ed-rev">${ed.reviewed ? 'Markera som ej genomgånget' : 'Markera som genomgånget'}</button><button class="btn sm" id="ed-add">+ Ny relation</button></div>
      <div id="ed-form" hidden class="panel" style="margin-top:8px">
        <div class="fld2"><label class="fld"><span>Från (A)</span><input id="ed-a" value="${esc(t)}"></label><label class="fld"><span>Till (B)</span><input id="ed-b" placeholder="Ticker"></label></div>
        <div class="fld2"><label class="fld"><span>Typ</span><select id="ed-ty">${Object.entries(ed.types).map(([k, l]) => `<option value="${k}">A ${esc(l)} B</option>`).join('')}</select></label>
          <label class="fld"><span>Styrka</span><select id="ed-st">${Object.entries(ed.strengths).map(([k, l]) => `<option value="${k}" ${k === 'mentioned' ? 'selected' : ''}>${esc(l)}</option>`).join('')}</select></label></div>
        <div class="fld2"><label class="fld"><span>Andel av omsättningen, % (om angiven)</span><input id="ed-sh" inputmode="decimal"></label><label class="fld"><span>Belopp (valfritt, fritext)</span><input id="ed-am" placeholder="t.ex. avtal på 2 mdr USD"></label></div>
        <label class="fld"><span>Källa (länk, krävs)</span><input id="ed-url" placeholder="https://… årsredovisning, 10-K, 8-K eller pressmeddelande"></label>
        <div class="fld2"><label class="fld"><span>Källans titel</span><input id="ed-tt"></label><label class="fld"><span>Gäller per (datum)</span><input id="ed-as" placeholder="ÅÅÅÅ-MM-DD"></label></div>
        <label class="fld"><span>Säkerhet</span><select id="ed-cf"><option value="primär">primär källa (bolagets eget dokument)</option><option value="sekundär">sekundär källa (nyhet, analys)</option></select></label>
        <label class="fld"><span>Anteckning</span><input id="ed-no"></label>
        <div class="dlg-actions" style="justify-content:flex-end"><button class="btn primary" id="ed-save">Spara</button></div></div>`;
  }
  body.innerHTML = autoHTML + covHTML + `<p class="q-text">Relationer är <b>hypoteser med källa</b>${info('relations')}: vem som levererar till, äger eller samarbetar med vem. Varje rad kräver en länk till bolagets eget dokument eller en nyhet. Jämför gärna med lead-lag: en relation utan statistiskt stöd är inte felaktig, men den bevisar inte heller att rörelser går åt något håll.</p>` + main
    + `<details style="margin-top:16px"><summary class="mut small">Importera många relationer (JSON)</summary><textarea id="imp" rows="5" style="width:100%" placeholder='[{"a":"NVDA","b":"TSM","rtype":"supplies","strength":"major","share_pct":null,"source_url":"https://…","source_title":"…","as_of":"2025-01-01","confidence":"primär"}]'></textarea><div class="dlg-actions" style="justify-content:flex-end"><button class="btn sm" id="imp-go">Importera</button></div><div id="imp-out" class="small"></div></details>`;
  const reload = () => renderView();
  sbAutoBind(body, reload);
  $$('[data-del]', body).forEach(b => b.onclick = async () => { if (confirm('Ta bort relationen?')) { await api('/rel/edges/' + b.dataset.del, { method: 'DELETE' }); reload(); } });
  const rev = $('#ed-rev'); if (rev) rev.onclick = async () => { await api('/rel/reviewed', { method: 'PUT', body: { ticker: ed.ticker, on: !ed.reviewed } }); reload(); };
  const add = $('#ed-add'); if (add) add.onclick = () => { $('#ed-form').hidden = !$('#ed-form').hidden; };
  const sv = $('#ed-save');
  if (sv) sv.onclick = async () => {
    const g = id => $(id).value.trim();
    try {
      await api('/rel/edges', { method: 'POST', body: { a: g('#ed-a'), b: g('#ed-b'), rtype: $('#ed-ty').value, strength: $('#ed-st').value, share_pct: g('#ed-sh') ? parseFloat(g('#ed-sh').replace(',', '.')) : null, amount: g('#ed-am'), source_url: g('#ed-url'), source_title: g('#ed-tt'), as_of: g('#ed-as'), confidence: $('#ed-cf').value, note: g('#ed-no') } });
      toast('Relation sparad'); reload();
    } catch (e) { toast(e.message, true); }
  };
  $('#imp-go').onclick = async () => {
    let items; try { items = JSON.parse($('#imp').value); } catch (e) { $('#imp-out').textContent = 'Ogiltig JSON'; return; }
    const r = await api('/rel/import', { method: 'POST', body: { items } });
    $('#imp-out').innerHTML = `${r.added} tillagda.${r.skipped.length ? '<br>Hoppade över: ' + r.skipped.map(esc).join('<br>') : ''}`;
    if (r.added) setTimeout(reload, 900);
  };
}

/* Kort på aktiesidan */
async function stockRel(ticker) {
  const host = document.getElementById('st-body');
  if (!host) return;
  let box = document.getElementById('st-rel');
  if (!box) { box = document.createElement('div'); box.id = 'st-rel'; box.className = 'panel'; box.style.marginTop = '14px'; host.appendChild(box); }
  box.innerHTML = '<div class="mut small">Hämtar samband…</div>';
  try {
    const [ll, ed] = await Promise.all([api('/rel/leadlag?ticker=' + encodeURIComponent(ticker)), api('/rel/edges?ticker=' + encodeURIComponent(ticker))]);
    if (!document.getElementById('st-rel')) return;
    const li = x => `<li><b>${esc(x.other)}</b> <span class="mut small">${esc(x.other_name)}</span>, ${x.lag} d, r=${nf(x.r, 2)}${x.stable ? '' : ' (ej stabil)'}</li>`;
    box.innerHTML = `<div class="panel-head"><h3>Samband med andra bolag${info('relations')}</h3><button class="btn sm" id="st-rel-go">Öppna Samband</button></div>
      ${ed.edges.length ? `<ul class="small" style="margin:0 0 8px 18px">${ed.edges.slice(0, 5).map(e => `<li><b>${esc(e.a)}</b> ${esc(e.verb)} <b>${esc(e.b)}</b>${e.share_pct != null ? ` (${nf(e.share_pct, 0)} %)` : ''} <a href="${esc(e.source_url)}" target="_blank" rel="noopener" class="small">källa</a></li>`).join('')}</ul>` : `<div class="mut small">Inga relationer inlagda${ed.reviewed ? '' : ' (bolaget är inte genomgånget)'}.</div>`}
      <div class="small" style="margin-top:6px"><b>Lead-lag</b> (rensat från marknaden, korrigerat för ${ll.n_tests} tester): ${ll.leads.length || ll.led_by.length ? '' : '<span class="mut">inga samband klarar korrigeringen.</span>'}</div>
      ${ll.leads.length ? `<div class="small mut">${esc(ticker)} leder:</div><ul class="small" style="margin:0 0 4px 18px">${ll.leads.slice(0, 4).map(li).join('')}</ul>` : ''}
      ${ll.led_by.length ? `<div class="small mut">${esc(ticker)} följer:</div><ul class="small" style="margin:0 0 4px 18px">${ll.led_by.slice(0, 4).map(li).join('')}</ul>` : ''}
      <div class="disclaimer">Beskrivande statistik över historiken, inget köpråd. Ett samband behöver inte hålla framåt.</div>`;
    $('#st-rel-go').onclick = () => { SB.ticker = ticker; SB.pick = true; SB.mode = 'leadlag'; S.tab = 'samband'; renderTabs(); renderView(); };
  } catch (e) { box.remove(); }
}

/* Automatisk uppdatering av relationer */
function sbAutoHTML(au) {
  const r = au.result || {}, d = r.discover, l = r.links;
  const when = au.last ? new Date(au.last).toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' }) : 'aldrig';
  const sum = [];
  if (d) sum.push(`${d.matched} av ${d.tickers} bolag matchade mot Wikidata${d.ambiguous || d.unknown ? ` (${d.unknown} okända, ${d.ambiguous} tvetydiga hoppades över)` : ''}, ${d.new} nya förslag`);
  if (l) sum.push(`${l.checked} källänkar kontrollerade, ${l.unreachable} svarade inte`);
  return `<div class="panel" style="margin-bottom:12px"><div class="panel-head"><h3>Automatisk uppdatering${info('relauto')}</h3>
    <label class="small"><input type="checkbox" id="au-on" ${au.enabled ? 'checked' : ''}> varje vecka</label></div>
    <div class="small">Senast körd: <b>${esc(when)}</b>${au.running ? ' · körs nu…' : ''}. ${sum.length ? esc(sum.join('. ')) + '.' : 'Inget resultat ännu.'}</div>
    ${au.error ? `<div class="hint">${esc(au.error)}</div>` : ''}
    ${au.n_stale ? `<div class="small" style="margin-top:4px">${au.n_stale} relationer är äldre än 18 månader och bör granskas igen.</div>` : ''}
    <div class="row-add" style="margin-top:8px"><button class="btn sm" id="au-run" ${au.running ? 'disabled' : ''}>Kör nu</button></div>
    <div class="small mut" style="margin-top:6px">Sökningen hittar bara <b>ägande, dotter- och moderbolag</b> mellan bolag i dina listor (Wikidata). Leverantörer, kunder och samarbeten går inte att läsa ut automatiskt och läggs in av dig. Inget hamnar i listan förrän du godkänner det.</div>
    ${au.candidates.length ? `<h4 style="margin:12px 0 6px">Förslag att granska (${au.candidates.length})</h4><div class="tbl-scroll"><table><thead><tr><th class="l">Förslag</th><th class="l">Källa</th><th></th></tr></thead><tbody>${au.candidates.map(c => `<tr><td class="l"><b>${esc(c.a)}</b> ${esc(c.verb)} <b>${esc(c.b)}</b><div class="small mut">${esc(c.a_name)} → ${esc(c.b_name)}</div></td><td class="l small"><a href="${esc(c.source_url)}" target="_blank" rel="noopener">${esc(c.source_title)}</a><div class="mut">${esc(c.confidence)}</div></td><td><button class="btn sm primary" data-cy="${c.id}">Godkänn</button> <button class="btn sm" data-cn="${c.id}">Avvisa</button></td></tr>`).join('')}</tbody></table></div>` : ''}</div>`;
}
function sbAutoBind(body, reload) {
  const on = $('#au-on'); if (on) on.onchange = async () => { await api('/rel/auto/enabled', { method: 'PUT', body: { on: on.checked } }); toast(on.checked ? 'Automatisk uppdatering på' : 'Automatisk uppdatering av'); };
  const run = $('#au-run'); if (run) run.onclick = async () => {
    run.disabled = true; run.textContent = 'Körs…';
    await api('/rel/auto/run', { method: 'POST' });
    for (let i = 0; i < 60; i++) { await new Promise(r => setTimeout(r, 2000)); const s = await api('/rel/auto'); if (!s.running) break; }
    reload();
  };
  $$('[data-cy]', body).forEach(b => b.onclick = async () => { try { await api('/rel/candidates/' + b.dataset.cy, { method: 'POST', body: { accept: true } }); toast('Relation tillagd'); reload(); } catch (e) { toast(e.message, true); } });
  $$('[data-cn]', body).forEach(b => b.onclick = async () => { await api('/rel/candidates/' + b.dataset.cn, { method: 'POST', body: { accept: false } }); reload(); });
}
