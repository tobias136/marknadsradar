/* Marknadsradar – gränssnitt (ren JavaScript, ingen byggprocess) */
'use strict';

// ------------------------------------------------------------------ hjälpare
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = (v, d = 1) => v == null || isNaN(v) ? '–' : Number(v).toLocaleString('sv-SE', { minimumFractionDigits: d, maximumFractionDigits: d });
const pct = (v, d = 1, sign = true) => v == null ? '–' : (sign && v > 0 ? '+' : '') + nf(v, d) + ' %';
const pp = (v, d = 1) => v == null ? '–' : (v > 0 ? '+' : '') + nf(v, d) + ' p.e.';
const cls = v => v == null ? 'mut' : v > 0 ? 'pos' : v < 0 ? 'neg' : '';
const frac = (v, d = 1) => v == null ? '–' : nf(v * 100, d) + ' %';
function money(v, cur = '') {
  if (v == null) return '–';
  const a = Math.abs(v);
  const s = a >= 1e9 ? nf(v / 1e9, 2) + ' mdr' : a >= 1e6 ? nf(v / 1e6, 1) + ' mn' : nf(v, 0);
  return (s + ' ' + cur).trim();
}
const SCALE = { r_1d: 3, r_1w: 6, r_1m: 10, r_3m: 18, r_6m: 28, r_ytd: 35, r_1y: 45, rs_1m: 8, rs_3m: 15 };
function heat(v, key) {
  if (v == null) return '';
  const a = (0.10 + 0.62 * Math.min(Math.abs(v) / (SCALE[key] || 10), 1)).toFixed(2);
  return v >= 0 ? `background:rgba(47,192,122,${a})` : `background:rgba(240,96,93,${a})`;
}
const PER = [['r_1d', '1d'], ['r_1w', '1v'], ['r_1m', '1m'], ['r_3m', '3m'], ['r_6m', '6m'], ['r_ytd', 'I år'], ['r_1y', '1 år']];
// Tooltip med jämförelsedag och startkurs för en periodavkastning (t.ex. r_1m).
function baseTip(t, kk, cur) {
  const b = t && t.r_bases && t.r_bases[kk.slice(2)];
  if (!b) return '';
  const d = new Date(b[0] + 'T00:00:00');
  const ds = isNaN(d) ? b[0] : d.toLocaleDateString('sv-SE', { day: 'numeric', month: 'short', year: 'numeric' });
  return ` title="${esc('Jämförs med stängningskursen ' + ds + ': ' + nf(b[1], 2) + (cur ? ' ' + cur : ''))}"`;
}
const info = k => (typeof GLOSSARY !== 'undefined' && GLOSSARY[k]) ? `<span class="info" data-k="${k}" tabindex="0" role="button" aria-label="Förklaring">?</span>` : '';
const PALETTE = ['#5aa0ff', '#2fc07a', '#e8b34a', '#b07cff', '#ff7aa2', '#4fd1c5', '#f08a4b', '#a3c653', '#7fb2ff', '#e26d5c', '#c9d1e0', '#8d7bff'];

async function api(path, opts = {}) {
  const init = { method: opts.method || 'GET', headers: { 'Content-Type': 'application/json' } };
  if (opts.body !== undefined) init.body = JSON.stringify(opts.body);
  const r = await fetch('/api' + path, init);
  let data = null;
  try { data = await r.json(); } catch (e) { /* tomt svar */ }
  if (!r.ok) throw new Error((data && data.detail) || ('Fel ' + r.status));
  return data;
}
function toast(msg, err = false) {
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  $('#toast').appendChild(t);
  setTimeout(() => t.remove(), err ? 7000 : 3800);
}
function spark(arr) {
  if (!arr || arr.length < 2) return '';
  const w = 84, h = 24, min = Math.min(...arr), max = Math.max(...arr);
  const pts = arr.map((v, i) => `${(i / (arr.length - 1) * w).toFixed(1)},${(h - 1 - (v - min) / ((max - min) || 1) * (h - 2)).toFixed(1)}`).join(' ');
  const up = arr[arr.length - 1] >= arr[0];
  return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}"><polyline fill="none" stroke="${up ? '#2fc07a' : '#f0605d'}" stroke-width="1.5" points="${pts}"/></svg>`;
}
Chart.defaults.color = '#8995a8';
Chart.defaults.borderColor = '#243044';
Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
const charts = {};
function mkChart(id, config) {
  if (charts[id]) charts[id].destroy();
  const el = document.getElementById(id);
  if (!el) return null;
  charts[id] = new Chart(el, config);
  return charts[id];
}
function dialog(html, onMount, cls = '') {
  const d = $('#dlg');
  d.className = cls;
  d.innerHTML = html;
  d.showModal();
  d.addEventListener('close', () => { d.innerHTML = ''; }, { once: true });
  onMount && onMount(d);
  return d;
}

// ------------------------------------------------------------- förklaringar (?)
function entryHTML(k) {
  const g = GLOSSARY[k];
  if (!g) return '';
  return `<div class="gbody">${g.plan ? '<div class="planbadge">Planerad funktion – finns inte i appen ännu</div>' : ''}
    <p class="g-short"><b>I korthet:</b> ${esc(g.s)}</p>
    <h5>Vad är det?</h5><p>${esc(g.what)}</p>
    ${g.read ? `<h5>Så läser du det</h5><table class="g-read">${g.read.map(([a, b]) => `<tr><td class="g-l">${esc(a)}</td><td>${esc(b)}</td></tr>`).join('')}</table>` : ''}
    ${g.ex ? `<h5>Exempel</h5><p class="g-ex">${esc(g.ex)}</p>` : ''}
    ${g.watch ? `<h5>Tänk på</h5><p>${esc(g.watch)}</p>` : ''}
    ${g.rel ? `<h5>Se också</h5><div class="chips">${g.rel.filter(r => GLOSSARY[r]).map(r => `<span class="chip on" data-gk="${r}">${esc(GLOSSARY[r].t)}</span>`).join('')}</div>` : ''}</div>`;
}
function openInfo(k) {
  const g = GLOSSARY[k];
  if (!g) return;
  if (typeof track === 'function') track('gloss', k);
  dialog(`<div class="g-head"><h3>${esc(g.t)}</h3><span class="mut g-cat">${esc(g.cat)}</span></div>${entryHTML(k)}
    <div class="dlg-actions"><button class="btn" id="g-all">Öppna ordlistan</button><button class="btn primary" id="g-close">Stäng</button></div>`, d => {
    $('#g-close', d).onclick = () => d.close();
    $('#g-all', d).onclick = () => { d.close(); S.tab = 'glossary'; S.gq = g.t; renderTabs(); renderView(); };
    $$('[data-gk]', d).forEach(c => c.onclick = () => { d.close(); setTimeout(() => openInfo(c.dataset.gk), 60); });
  }, 'wide');
}
const tip = document.createElement('div');
tip.id = 'tip';
document.body.appendChild(tip);
function showTip(el) {
  const g = GLOSSARY[el.dataset.k];
  if (!g) return;
  tip.innerHTML = `<b>${esc(g.t)}</b><div>${esc(g.s)}</div><div class="more">Klicka på ? för förklaring och exempel</div>`;
  tip.style.display = 'block';
  const r = el.getBoundingClientRect(), tw = tip.offsetWidth, th = tip.offsetHeight;
  const x = Math.min(window.innerWidth - tw - 12, Math.max(8, r.left + r.width / 2 - tw / 2));
  let y = r.bottom + 8;
  if (y + th > window.innerHeight - 8) y = r.top - th - 8;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
document.addEventListener('mouseover', e => { const i = e.target.closest && e.target.closest('.info'); if (i) showTip(i); });
document.addEventListener('mouseout', e => { const i = e.target.closest && e.target.closest('.info'); if (i) tip.style.display = 'none'; });
document.addEventListener('click', e => {
  const i = e.target.closest && e.target.closest('.info');
  if (i) { e.stopPropagation(); e.preventDefault(); tip.style.display = 'none'; openInfo(i.dataset.k); }
}, true);
document.addEventListener('keydown', e => {
  const i = e.target.closest && e.target.closest('.info');
  if (i && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); tip.style.display = 'none'; openInfo(i.dataset.k); }
});
function infoEnabled() { try { return localStorage.getItem('mr_noinfo') !== '1'; } catch (e) { return true; } }
function applyInfoSetting() { document.body.classList.toggle('noinfo', !infoEnabled()); }
applyInfoSetting();

const GUIDES = {
  overview: () => `<p><b>Syftet:</b> se vilka delar av marknaden som får pengar just nu och vilka som tappar. Det kallas <i>sektorrotation</i>.</p>
    <ol><li>Börja med <b>värmekartan</b>${info('heatmap')}: grönt betyder att det stigit, rött att det fallit. Läs raden från vänster till höger: har gruppen gått bra länge, eller bara nyligen?</li>
    <li><b>Rel. 1m / 3m</b>${info('rel')} visar om gruppen slår jämförelseindexet${info('index')}. Grönt = den är en ledare.</li>
    <li><b>Marknadsbredd</b>${info('breadth')} visar om många eller bara få bolag är med i uppgången.</li>
    <li>Längst ner finns alla värdepapper. <b>Signal</b>${info('signal')} sammanfattar läget med skäl. Klicka på ett bolag för hela bilden.</li></ol>
    <p class="mut">Exempel: Finans är mörkgrön på 3 månader men röd på 1 dag. Det är en stark trend som tar en liten paus, inte en vändning. Dra aldrig slutsatser av en enskild dag.</p>`,
  compare: () => `<p><b>Syftet:</b> se hur olika bolag eller sektorer utvecklats i förhållande till varandra, oavsett om de kostar 20 kr eller 2 000 kr.</p>
    <ul><li>Klicka på bolag i listan för att lägga till eller ta bort dem. Alla linjer startar på 100${info('rebased')}.</li>
    <li>Välj <b>Relativt index</b>${info('relmode')} för att se om bolaget slår marknaden. En stigande linje betyder att det går bättre än indexet.</li>
    <li>Linjer som divergerar (går isär) visar att något händer: den som drar iväg är ledare.</li></ul>`,
  reports: () => `<p><b>Syftet:</b> se hur bolagens senaste kvartalsrapporter gick, och när nästa kommer.</p>
    <ul><li>Grön <b>tillväxt</b>${info('growth')} och stigande <b>marginal</b>${info('marginchange')} är bra tecken.</li>
    <li><b>EPS vs förv.</b>${info('surprise')}: grön betyder att bolaget slog analytikernas förväntningar. Kursen rör sig ofta mer på förväntningar än på själva siffrorna.</li>
    <li>Klicka på en rad för en löpande text. Sammanfattningen bygger på siffror, inte på ledningens kommentarer.</li></ul>`,
  stock: () => `<p><b>Syftet:</b> förstå ett enskilt bolag: läge, trend, risk, värdering och rapporter på en sida.</p>
    <ol><li><b>Signalbetyget</b>${info('signal')} överst sammanfattar läget. Läs <i>skälen</i> under pelarna och <i>invalideringsnivån</i>${info('invalid')}: den visar vad som skulle ändra bilden.</li>
    <li><b>Kursdiagrammet</b>${info('pricechart')}: ligger kursen över de streckade medelvärdena${info('sma')} är trenden uppåt.</li>
    <li>Korten visar avkastning, risk${info('risk')}, tekniska indikatorer, värdering${info('valuation')} och lönsamhet${info('profitability')}. Håll muspekaren över ? för en snabb förklaring.</li>
    <li>Skriv egna anteckningar längst ner: tes, risker, vad som får dig att ändra dig.</li></ol>`,
  claude: () => `<p><b>Syftet:</b> ge Claude hela marknadsläget i en fil så att den kan analysera, jämföra och förklara. Ladda ner filen eller kopiera texten och klistra in den i ett Claude-samtal.</p>`,
  macro: () => `<p><b>Syftet:</b> se marknadens “väder”: räntor, oro, dollar och råvaror. Det förklarar ofta varför hela marknaden rör sig, oavsett enskilda bolag.</p>
    <ol><li>Börja med <b>Marknadsklimat</b>${info('regime')}: Risk-on betyder att marknaden tar risk, Risk-off att den drar sig undan.</li>
    <li>Varje kort visar nivå, utveckling och var nivån ligger i sitt 1-årsspann (0 % = lägsta på året, 100 % = högsta).</li>
    <li><b>VIX</b>${info('vix')}, <b>räntekurvan</b>${info('yieldcurve')} och <b>kreditoron</b>${info('spreads')} är de som oftast ger tidiga varningar.</li></ol>
    <p class="mut">Makro ger sammanhang, inte köp- eller säljsignaler. Det beskriver nuläget och förutspår inget.</p>`,
  backtest: () => `<p><b>Syftet:</b> ta reda på om signalbetyget faktiskt haft något samband med vad som hände efteråt, i stället för att bara tro på det.</p>
    <ol><li>Appen räknar ut vilket betyg varje aktie hade varje dag bakåt i tiden och mäter vad som hände de följande dagarna${info('forward')}.</li>
    <li>Titta på <b>Slutsats</b> överst. Är z${info('zscore')} under 2 är skillnaden inom vad slumpen kan ge.</li>
    <li>Jämför strategin med att bara äga${info('strategy')}: mindre nedgång brukar kosta avkastning.</li>
    <li><b>Läs förbehållen längst ned.</b> De är viktigare än siffrorna: urvalsfel${info('survivorship')}, överanpassning${info('overfit')} och kort historik.</li></ol>`,
  journal: () => `<p><b>Syftet:</b> lära dig av dina beslut. Skriv ner varför du agerar <i>innan</i> du vet utgången, och granska sedan.</p>
    <ol><li>Skriv en <b>tes</b>${info('thesis')} och vad som skulle få dig att ändra dig${info('invalid')}.</li>
    <li>När granskningsdatum passerat får du en påminnelse. Bedöm <i>processen</i>, inte bara vinsten.</li>
    <li>Statistiken säger inget förrän du har ungefär 20 granskade beslut${info('hitrate')}.</li></ol>`,
  portfolio: () => `<p><b>Syftet:</b> se hur din portfölj faktiskt ser ut: vikter, risk och beroenden, och få varningar om koncentration.</p>
    <ol><li>Lägg till innehav manuellt eller importera Avanza-CSV${info('csvimport')}. Kopplingen till en Yahoo-ticker gör du själv.</li>
    <li>Titta på <b>koncentration</b>${info('portfolio')} och <b>effektivt antal</b>${info('effn')}: tio innehav betyder inte tio spridda innehav.</li>
    <li>Använd positionsstorleken${info('possize')} för att bestämma hur mycket du köper utifrån hur mycket du kan förlora.</li></ol>
    <p class="mut">Allt är beräknat lokalt i appen. Inget skickas till någon.</p>`,
  samband: () => `<p><b>Syftet:</b> undersöka om rörelser hos ett bolag brukar följas av rörelser hos ett annat, och samla vad du vet om hur bolag hänger ihop, med källa.</p>
    <ul><li><b>Lead-lag</b>${info('leadlag')} mäter alla par i dina listor, rensat från marknaden och korrigerat för antalet tester${info('multiple')}. Ofta klarar inget paret korrigeringen, och det är ett riktigt resultat.</li>
    <li><b>Händelser</b>${info('eventstudy')} visar hur andra bolag rör sig kring ett bolags rapporter eller kraftiga rörelser.</li>
    <li><b>Relationer</b>${info('relations')} är dina egna inlägg om leveranser, ägande och samarbeten. Varje rad kräver en källa. Appen söker varje vecka efter ägarrelationer och lägger dem som förslag du godkänner${info('relauto')}.</li></ul>
    <p>Allt är beskrivande statistik över historiken. Det är inget köpråd och inget bevis på orsak.</p>`,
  practice: () => `<p><b>Syftet:</b> träna ögat och räkningen med uppgifter som skapas av riktiga kurser, så att du inte bara läser om det.</p>
    <ul><li><b>Läs diagrammet</b> och <b>Stoppövning</b> använder riktiga kurser med dolda namn. Namnet visas först när du svarat.</li>
    <li><b>Riskräknaren</b>${info('possize')} ger nya tal varje gång. Räkna på papper först.</li>
    <li><b>Samband eller slump</b>${info('multiple')} visar hur starka samband slumpen skapar när man letar bland många par.</li>
    <li><b>Stoppsimulatorn</b>${info('whipsaw')} visar skillnaden mellan stopptyper över många affärer, inte ett enda utfall.</li>
    <li><b>Repetitionskorten</b>${info('spaced')} bygger på Ordlistan.</li>
    <li><b>Beteendefällor</b>${info('biases')} tränar dig att känna igen tankevurporna. Under <b>Handlarens verktyg</b> skriver du din <b>Spelbok</b>${info('playbook')} och gör <b>Månadsgranskningar</b>${info('monthly')}.</li>
    <li>Från nivå 8: <b>Stresstest</b>${info('stresstest')} och <b>Riskpanel</b>${info('risklimits')}, <b>Tur eller skicklighet</b>${info('losingstreak')}, <b>Handelsstatistik</b>${info('expectancy')}, <b>Regeltest</b>${info('ruletest')} och <b>Handlarprofil</b>${info('profile')}. Allt ligger öppet från början, men nivåerna kräver tid och många affärer.</li></ul><p class="mut">Det är träning, inte råd. Ingen siffra här säger vad du ska köpa.</p>`,
  paper: () => `<p><b>Syftet:</b> öva hela kedjan med låtsaspengar: idé, storlek, stopp, uppföljning och granskning.</p>
    <ol><li>Skapa en portfölj och välj ett namn som beskriver strategin. Du kan ha flera och jämföra dem${info('paper')}.</li>
    <li>Varje köp kräver en <b>tes</b>${info('thesis')}, vad som skulle visa att du har fel${info('invalid')} och ett <b>stopp</b>${info('stop')}. Storleken räknas ut från hur mycket du får förlora${info('possize')}.</li>
    <li>Stoppet tillämpas automatiskt när kurserna uppdateras. Du kan höja det men aldrig sänka det.</li>
    <li>Granska varje stängd affär. <b>Processpoängen</b>${info('processscore')} mäter planen, risken, storleken och granskningen. Vinsten ger inga poäng.</li></ol>
    <p class="mut">Pappershandel saknar känslorna. Den lär ut process men inte hur det känns när det är riktiga pengar.</p>`,
  game: () => `<p><b>Syftet:</b> göra lärandet tydligt. Varje nivå har uppdrag och ett quiz. När alla uppdrag på en nivå är klara går du vidare.</p>
    <ul><li>Poäng ges för att <b>läsa, använda funktioner, dokumentera och granska</b>.</li><li>Aldrig för antal affärer och aldrig för vinst på enskilda beslut.</li><li>De sista uppdragen kräver stora urval, eftersom tur annars skulle räcka.</li></ul>`,
  glossary: () => `<p>Här finns förklaringar till allt i appen, även funktioner som är planerade. Sök på ett ord eller bläddra per kategori. Varje förklaring har <i>I korthet</i>, <i>Vad är det</i>, <i>Så läser du det</i>, <i>Exempel</i> och <i>Tänk på</i>. Exemplen har påhittade siffror.</p>`,
};
function guide(tab) {
  let open = true;
  try { open = localStorage.getItem('mr_guide_' + tab) !== 'closed'; } catch (e) { /* ok */ }
  return `<details class="guide" data-g="${tab}" ${open ? 'open' : ''}><summary>💡 Så läser du den här sidan</summary><div class="guide-body">${GUIDES[tab]()}</div></details>`;
}
function bindGuides() {
  $$('details.guide').forEach(d => d.addEventListener('toggle', () => { try { localStorage.setItem('mr_guide_' + d.dataset.g, d.open ? 'open' : 'closed'); } catch (e) { /* ok */ } }));
}

// ----------------------------------------------------------------- tillstånd
const S = {
  lists: [], listId: null, tab: 'overview', status: null, rid: 0,
  ov: null, sortKey: 'r_1m', sortDir: -1, barPeriod: 'r_1m', barMode: 'groups', groupFilter: null,
  cmp: { range: '1y', rel: false, sel: null, listId: null },
  stock: { ticker: null, range: '1y' }, gq: '',
};
const BASE_TABS = [['overview', 'Översikt'], ['compare', 'Jämför'], ['reports', 'Rapporter'], ['stock', 'Aktie'], ['samband', 'Samband'], ['macro', 'Makro'], ['portfolio', 'Portfölj'], ['journal', 'Journal'], ['practice', 'Öva'], ['paper', 'Övningsportfölj'], ['backtest', 'Backtest'], ['claude', 'Claude-export'], ['glossary', 'Ordlista']];
const LIST_TABS = ['overview', 'compare', 'reports', 'stock', 'backtest'];
const allTabs = () => [...BASE_TABS, ...(typeof gameTabs === 'function' ? gameTabs() : [])];
const curList = () => S.lists.find(l => l.id === S.listId);

// -------------------------------------------------------------------- ramverk
async function init() {
  $('#btn-new-list').onclick = newListDialog;
  await loadStatus();
  await loadLists();
  if (typeof gameInit === 'function') await gameInit();
  renderTabs();
  renderView();
  poll();
}
async function loadLists() {
  S.lists = await api('/lists');
  if (!S.lists.find(l => l.id === S.listId)) S.listId = S.lists.length ? S.lists[0].id : null;
  renderSidebar();
}
async function loadStatus() {
  S.status = await api('/status');
  $('#demo-banner').hidden = S.status.provider !== 'demo';
  renderChrome();
}
async function poll() {
  const prev = S.status;
  try { await loadStatus(); } catch (e) { /* servern kan starta om */ }
  const s = S.status;
  if (prev && s && (prev.last_refresh !== s.last_refresh || (prev.running && !s.running))) {
    await loadLists();
    if (prev.running && !s.running) toast('Data uppdaterad' + (Object.keys(s.errors).length ? ` (${Object.keys(s.errors).length} fel – se Inställningar)` : ''), Object.keys(s.errors).length > 0);
    if (!['stock', 'samband', 'claude', 'journal', 'portfolio', 'game', 'glossary', 'practice', 'paper'].includes(S.tab) || prev.running) renderView();
  }
  setTimeout(poll, s && s.running ? 1500 : 15000);
}
function renderSidebar() {
  $('#lists').innerHTML = S.lists.map(l => `<div class="list-item ${l.id === S.listId ? 'active' : ''}" data-id="${l.id}"><span>${esc(l.name)}</span><span class="cnt">${l.items.length}</span></div>`).join('');
  $$('#lists .list-item').forEach(el => el.onclick = () => { S.listId = +el.dataset.id; S.groupFilter = null; renderSidebar(); renderChrome(); renderView(); });
}
function renderTabs() {
  $('#tabs').innerHTML = allTabs().map(([k, l]) => `<div class="tab ${S.tab === k ? 'active' : ''}" data-k="${k}">${l}</div>`).join('');
  $$('#tabs .tab').forEach(el => el.onclick = () => { S.tab = el.dataset.k; renderTabs(); renderView(); });
}
function renderChrome() {
  const l = curList(), st = S.status;
  $('#title').textContent = l ? l.name : 'Marknadsradar';
  $('#subtitle').textContent = l ? (l.description || '') : 'Skapa din första lista till vänster.';
  const pr = st && st.running ? `<div><div class="progress"><div style="width:${st.total ? Math.round(100 * st.done / st.total) : 5}%"></div></div><div class="mut" style="font-size:11px;margin-top:3px">${esc(st.phase)} ${st.done}/${st.total}</div></div>` : '';
  $('#actions').innerHTML = `${pr}<button class="btn primary" id="btn-refresh" ${st && st.running ? 'disabled' : ''}>↻ Uppdatera</button><button class="btn" id="btn-settings">⚙ Inställningar</button>`;
  $('#btn-refresh').onclick = async () => { await api('/refresh', { method: 'POST', body: { full: false } }); await loadStatus(); };
  $('#btn-settings').onclick = settingsDialog;
  if (typeof renderGameChip === 'function') renderGameChip();
  const last = st && st.last_refresh ? new Date(st.last_refresh).toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' }) : 'aldrig';
  $('#side-foot').innerHTML = `<div><span class="dot ${st && st.running ? 'busy' : ''}"></span>${st && st.running ? 'Hämtar data…' : 'Redo'}</div>
    <div>Källa: ${esc(st ? st.provider : '')}</div><div>Uppdaterad: ${last}</div>
    <div>${st && st.interval_minutes > 0 ? `Auto: var ${st.interval_minutes}:e min` : 'Auto-uppdatering av'}</div>`;
}
async function renderView() {
  const rid = ++S.rid, v = $('#view');
  if (!curList() && LIST_TABS.includes(S.tab)) { v.innerHTML = '<div class="empty">Inga listor ännu. Klicka på “+ Ny lista” för att skapa en.</div>'; return; }
  if (typeof track === 'function') track('tab', S.tab);
  v.innerHTML = '<div class="loading">Laddar…</div>';
  try {
    const fn = { overview: viewOverview, compare: viewCompare, reports: viewReports, stock: viewStock, samband: viewSamband, claude: viewClaude, glossary: viewGlossary, macro: viewMacro, portfolio: viewPortfolio, journal: viewJournal, backtest: viewBacktest, game: viewGame, practice: viewPractice, paper: viewPaper }[S.tab];
    await fn(v, rid);
  } catch (e) {
    if (rid === S.rid) v.innerHTML = `<div class="empty">Något gick fel: ${esc(e.message)}</div>`;
  }
}
const stale = rid => rid !== S.rid;
function openStock(t) { S.stock.ticker = t; S.tab = 'stock'; renderTabs(); renderView(); }

// ------------------------------------------------------------------- dialoger
function newListDialog() {
  dialog(`<h3>Ny bevakningslista</h3>
    <label>Namn</label><input id="d-name" placeholder="t.ex. Mina tillväxtbolag">
    <label>Jämförelseindex (valfritt, Yahoo-ticker)</label><input id="d-bench" placeholder="SPY, ^OMX, ^GSPC …" value="SPY">
    <label>Tickers (komma, mellanslag eller radbrytning)</label>
    <textarea id="d-tick" rows="4" placeholder="AAPL MSFT VOLV-B.ST ERIC-B.ST"></textarea>
    <div class="mut" style="font-size:12px;margin-top:6px">Svenska aktier har suffixet .ST. Bolagen grupperas automatiskt per sektor – du kan ändra grupp efteråt.</div>
    <div class="dlg-actions"><button class="btn" id="d-cancel">Avbryt</button><button class="btn primary" id="d-ok">Skapa lista</button></div>`, d => {
    $('#d-cancel', d).onclick = () => d.close();
    $('#d-ok', d).onclick = async () => {
      $('#d-ok', d).disabled = true; $('#d-ok', d).textContent = 'Hämtar kurser…';
      try {
        const r = await api('/lists', { method: 'POST', body: { name: $('#d-name', d).value, benchmark: $('#d-bench', d).value, tickers: $('#d-tick', d).value } });
        d.close();
        r.failed.forEach(f => toast(`${f.ticker}: ${f.error}`, true));
        await loadLists(); S.listId = r.id; S.groupFilter = null; S.tab = 'overview';
        renderSidebar(); renderTabs(); renderChrome(); renderView();
        toast(`Lista skapad (${r.added.length} tillagda)`);
      } catch (e) { toast(e.message, true); $('#d-ok', d).disabled = false; $('#d-ok', d).textContent = 'Skapa lista'; }
    };
  });
}
function listSettingsDialog() {
  const l = curList();
  dialog(`<h3>Listinställningar</h3>
    <label>Namn</label><input id="d-name" value="${esc(l.name)}">
    <label>Jämförelseindex</label><input id="d-bench" value="${esc(l.benchmark)}">
    <label>Beskrivning</label><textarea id="d-desc" rows="3">${esc(l.description)}</textarea>
    <div class="dlg-actions"><button class="btn danger" id="d-del">Radera lista</button>
    <span><button class="btn" id="d-cancel">Avbryt</button> <button class="btn primary" id="d-ok">Spara</button></span></div>`, d => {
    $('#d-cancel', d).onclick = () => d.close();
    $('#d-ok', d).onclick = async () => {
      try {
        await api(`/lists/${l.id}`, { method: 'PUT', body: { name: $('#d-name', d).value, benchmark: $('#d-bench', d).value, description: $('#d-desc', d).value } });
        d.close(); await loadLists(); renderChrome(); setTimeout(renderView, 1200);
      } catch (e) { toast(e.message, true); }
    };
    $('#d-del', d).onclick = async () => {
      if (!confirm(`Radera listan “${l.name}”? Kursdata sparas men listan försvinner.`)) return;
      await api(`/lists/${l.id}`, { method: 'DELETE' });
      d.close(); S.listId = null; await loadLists(); renderChrome(); renderView();
    };
  });
}
function settingsDialog() {
  const st = S.status, opts = [[0, 'Av (bara manuellt)'], [5, 'Var 5:e minut'], [15, 'Var 15:e minut'], [30, 'Var 30:e minut'], [60, 'Varje timme'], [120, 'Var 2:a timme'], [240, 'Var 4:e timme'], [1440, 'Varje dygn']];
  const errs = Object.entries(st.errors || {});
  dialog(`<h3>Inställningar</h3>
    <label>Uppdateringsintervall (appen måste vara igång)</label>
    <select id="d-int">${opts.map(([v, l]) => `<option value="${v}" ${v === st.interval_minutes ? 'selected' : ''}>${l}</option>`).join('')}</select>
    <div class="mut" style="font-size:12px;margin-top:6px">För sektorrotation räcker en gång per dag efter börsstängning. Gratisdata är oftast fördröjd ca 15 min.</div>
    <label>Förklaringar</label><label style="display:flex;gap:8px;align-items:center;color:var(--text);margin:0"><input type="checkbox" id="d-info" style="width:auto" ${infoEnabled() ? 'checked' : ''}> Visa (?)-förklaringar vid funktioner och förkortningar</label>
    <label>Spelläge</label><label style="display:flex;gap:8px;align-items:center;color:var(--text);margin:0"><input type="checkbox" id="d-game" style="width:auto" ${typeof G !== 'undefined' && G.enabled ? 'checked' : ''}> Karriär: nivåer, uppdrag och quiz (frivilligt tillägg)</label>
    <label>Datakälla</label><div>${esc(st.provider)}${st.provider === 'demo' ? ' (syntetisk data)' : ' (Yahoo Finance via yfinance)'}</div>
    <label>Fel vid senaste hämtning</label>
    <div style="max-height:130px;overflow:auto;font-size:12.5px">${errs.length ? errs.map(([t, e]) => `<div><span class="tk">${esc(t)}</span> <span class="mut">${esc(e)}</span></div>`).join('') : '<span class="mut">Inga</span>'}</div>
    <div class="dlg-actions"><button class="btn" id="d-full">Hämta om all historik</button>
    <span><button class="btn" id="d-cancel">Stäng</button> <button class="btn primary" id="d-ok">Spara</button></span></div>`, d => {
    $('#d-cancel', d).onclick = () => d.close();
    $('#d-ok', d).onclick = async () => { await api('/settings', { method: 'PUT', body: { interval_minutes: +$('#d-int', d).value } }); try { localStorage.setItem('mr_noinfo', $('#d-info', d).checked ? '0' : '1'); } catch (e) { /* ok */ } applyInfoSetting(); await api('/game/enabled', { method: 'PUT', body: { enabled: $('#d-game', d).checked } }); await gameInit(); if (!G.enabled && S.tab === 'game') S.tab = 'overview'; renderTabs(); d.close(); await loadStatus(); renderView(); toast('Inställningar sparade'); };
    $('#d-full', d).onclick = async () => { await api('/refresh', { method: 'POST', body: { full: true } }); d.close(); await loadStatus(); };
  });
}

// -------------------------------------------------------------------- översikt
const COLS = [
  { k: 'ticker', l: 'Ticker', left: true, g: 'ticker' }, { k: 'group', l: 'Grupp', left: true, g: 'group' }, { k: 'last', l: 'Kurs', g: 'adjclose' },
  ...PER.map(([k, l]) => ({ k, l, heat: true, g: k === 'r_ytd' ? 'ytd' : 'ret' })),
  { k: 'rsi14', l: 'RSI', g: 'rsi' }, { k: 'vs_sma200', l: 'mot SMA200', g: 'vs_sma' }, { k: 'from_hi52', l: 'från 52v-topp', g: 'hi52' },
  { k: 'pe', l: 'P/E', g: 'pe' }, { k: 'sigscore', l: 'Signal', g: 'signal' }, { k: 'next_earnings', l: 'Nästa rapport', g: 'nextearn' },
  { k: 'spark', l: 'Trend 60d', nosort: true, g: 'sparkline' },
];
function sigBadge(t) {
  const s = t.signal;
  if (!s || s.score == null) return '<span class="sig s-nodata">–</span>';
  return `<span class="sig s-${s.key}" title="${esc(s.lay)}">${s.score > 0 ? '+' : ''}${s.score} <small>${esc(s.label)}</small></span>`;
}
async function viewOverview(v, rid) {
  const ov = await api(`/lists/${S.listId}/overview`);
  if (stale(rid)) return;
  S.ov = ov;
  const gs = ov.groups.filter(g => g.r_1m != null), best = gs[0], worst = gs[gs.length - 1], b = ov.breadth, bm = ov.benchmark;
  const upd = ov.updated || '–';
  const ss = ov.signal_summary || { positive: 0, neutral: 0, negative: 0 };
  v.innerHTML = guide('overview') + `
  <div class="cards">
    <div class="card"><div class="lbl">Marknadsbredd${info('breadth')}</div><div class="big">${b.above_sma200 == null ? '–' : nf(b.above_sma200, 0) + ' %'}</div><div class="small">över 200-dagars · ${nf(b.above_sma50, 0)} % över 50-dagars · ${nf(b.advancers_1d, 0)} % steg senast</div></div>
    <div class="card"><div class="lbl">Starkast (1 mån)${info('ret')}</div><div class="big ${best ? cls(best.r_1m) : ''}">${best ? esc(best.group) : '–'}</div><div class="small">${best ? pct(best.r_1m) : ''} ${best && bm && !bm.missing ? '· rel. index ' + pp(best.rs_1m) : ''}</div></div>
    <div class="card"><div class="lbl">Svagast (1 mån)${info('ret')}</div><div class="big ${worst ? cls(worst.r_1m) : ''}">${worst ? esc(worst.group) : '–'}</div><div class="small">${worst ? pct(worst.r_1m) : ''} ${worst && bm && !bm.missing ? '· rel. index ' + pp(worst.rs_1m) : ''}</div></div>
    <div class="card"><div class="lbl">Index ${bm ? esc(bm.ticker) : ''}${info('index')}</div><div class="big ${bm && !bm.missing ? cls(bm.r_1m) : ''}">${bm && !bm.missing ? pct(bm.r_1m) : '–'}</div><div class="small">${bm && !bm.missing ? `1 mån · ${pct(bm.r_ytd)} i år` : 'ingen data / inget index valt'}</div></div>
    <div class="card"><div class="lbl">Signalläge i listan${info('signal')}</div><div class="big"><span class="pos">${ss.positive}▲</span> <span class="mut">${ss.neutral}■</span> <span class="neg">${ss.negative}▼</span></div><div class="small">positiva · neutrala · negativa (regelbaserat)</div></div>
  </div>
  ${ov.missing.length ? `<div class="panel" style="border-color:rgba(232,179,74,.4)"><span class="neg">Saknar kursdata:</span> ${ov.missing.map(esc).join(', ')} <span class="mut">– tryck “Uppdatera” eller kontrollera tickern (svenska aktier slutar på .ST).</span></div>` : ''}
  <div class="panel">
    <div class="panel-head"><div><h3>Sektor- och temavärmekarta${info('heatmap')}</h3><div class="hint" style="margin:0">Likaviktad${info('equalweight')} avkastning${info('ret')} per grupp${info('group')} · senaste kursdatum ${esc(upd)} · klicka på en rad för att filtrera värdepapperen nedan</div></div>
    <button class="btn sm" id="btn-listset">⚙ Redigera lista</button></div>
    <div class="tbl-scroll"><table class="heat"><thead><tr><th class="l">Grupp</th><th>Antal</th>${PER.map(([, l]) => `<th>${l}</th>`).join('')}<th>Rel. 1m${info('rel')}</th><th>Rel. 3m${info('rel')}</th></tr></thead><tbody>
    ${bm && !bm.missing ? `<tr class="bm"><td class="grp">${esc(bm.ticker)} (index)</td><td></td>${PER.map(([k]) => `<td class="cell" style="${heat(bm[k], k)}">${pct(bm[k])}</td>`).join('')}<td></td><td></td></tr>` : ''}
    ${ov.groups.map(g => `<tr class="click ${S.groupFilter === g.group ? 'sel' : ''}" data-g="${esc(g.group)}"><td class="grp">${esc(g.group)}</td><td class="mut">${g.count}</td>${PER.map(([k]) => `<td class="cell" style="${heat(g[k], k)}">${pct(g[k])}</td>`).join('')}<td class="cell" style="${heat(g.rs_1m, 'rs_1m')}">${pp(g.rs_1m)}</td><td class="cell" style="${heat(g.rs_3m, 'rs_3m')}">${pp(g.rs_3m)}</td></tr>`).join('')}
    </tbody></table></div>
  </div>
  <div class="panel">
    <div class="panel-head"><div><h3>Rangordning${info('ranking')}</h3></div><div style="display:flex;gap:10px;flex-wrap:wrap">
      <div class="seg" id="seg-mode"><button data-v="groups" class="${S.barMode === 'groups' ? 'on' : ''}">Grupper</button><button data-v="tickers" class="${S.barMode === 'tickers' ? 'on' : ''}">Värdepapper</button></div>
      <div class="seg" id="seg-per">${PER.map(([k, l]) => `<button data-v="${k}" class="${S.barPeriod === k ? 'on' : ''}">${l}</button>`).join('')}</div></div></div>
    <div class="chart-wrap tall"><canvas id="ch-bar"></canvas></div>
  </div>
  <div class="panel">
    <div class="panel-head"><h3>Värdepapper${S.groupFilter ? ` – ${esc(S.groupFilter)} <a href="#" id="clr-filter" style="font-size:12px">(visa alla)</a>` : ''}</h3></div>
    <div class="row-add"><input id="add-t" placeholder="Lägg till ticker(s), t.ex. AAPL NVDA VOLV-B.ST"><input id="add-g" list="grp-list" placeholder="Grupp (valfritt)"><datalist id="grp-list">${ov.groups.map(g => `<option value="${esc(g.group)}">`).join('')}</datalist><button class="btn primary" id="btn-add">+ Lägg till</button></div>
    <div class="tbl-scroll"><table id="tbl"><thead></thead><tbody></tbody></table></div>
  </div>`;
  bindGuides();
  $('#btn-listset').onclick = listSettingsDialog;
  $$('.heat tr[data-g]').forEach(tr => tr.onclick = () => { S.groupFilter = S.groupFilter === tr.dataset.g ? null : tr.dataset.g; renderView(); });
  const cf = $('#clr-filter'); if (cf) cf.onclick = e => { e.preventDefault(); S.groupFilter = null; renderView(); };
  $$('#seg-mode button').forEach(b => b.onclick = () => { S.barMode = b.dataset.v; renderView(); });
  $$('#seg-per button').forEach(b => b.onclick = () => { S.barPeriod = b.dataset.v; renderView(); });
  $('#btn-add').onclick = addTickers;
  $('#add-t').onkeydown = e => { if (e.key === 'Enter') addTickers(); };
  drawBar(ov);
  drawTable(ov);
}
function drawBar(ov) {
  const k = S.barPeriod;
  const src = (S.barMode === 'groups' ? ov.groups.map(g => ({ n: g.group, v: g[k] })) : ov.tickers.filter(t => !t.missing).map(t => ({ n: t.ticker, v: t[k] })));
  const data = src.filter(x => x.v != null).sort((a, b) => b.v - a.v);
  const bm = ov.benchmark && !ov.benchmark.missing ? ov.benchmark[k] : null;
  const wrap = $('#ch-bar').parentElement; wrap.style.height = Math.max(200, Math.min(900, data.length * 28 + 70)) + 'px';
  mkChart('ch-bar', {
    type: 'bar',
    data: { labels: data.map(d => d.n), datasets: [{ data: data.map(d => d.v), backgroundColor: data.map(d => d.v >= 0 ? 'rgba(47,192,122,.75)' : 'rgba(240,96,93,.75)'), borderRadius: 4 }] },
    options: {
      indexAxis: 'y', maintainAspectRatio: false, animation: { duration: 250 },
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: c => ` ${pct(c.parsed.x)}${bm != null ? '  (index ' + pct(bm) + ')' : ''}` } } },
      scales: { x: { ticks: { callback: v => v + ' %' }, grid: { color: '#1d2736' } }, y: { grid: { display: false }, ticks: { autoSkip: false } } },
    },
  });
}
function drawTable(ov) {
  let rows = ov.tickers.filter(t => !S.groupFilter || t.group === S.groupFilter);
  const k = S.sortKey, dir = S.sortDir;
  rows = [...rows].sort((a, b) => {
    const x = a[k], y = b[k];
    if (x == null && y == null) return 0; if (x == null) return 1; if (y == null) return -1;
    return (typeof x === 'string' ? x.localeCompare(y, 'sv') : x - y) * dir;
  });
  $('#tbl thead').innerHTML = `<tr>${COLS.map(c => `<th class="${c.left ? 'l' : ''}" data-k="${c.k}" ${c.nosort ? 'data-ns="1"' : ''}>${c.l}${info(c.g)}${S.sortKey === c.k ? (S.sortDir > 0 ? ' ▲' : ' ▼') : ''}</th>`).join('')}<th></th></tr>`;
  $$('#tbl th[data-k]').forEach(th => th.onclick = () => { if (th.dataset.ns) return; const kk = th.dataset.k; if (S.sortKey === kk) S.sortDir *= -1; else { S.sortKey = kk; S.sortDir = (kk === 'ticker' || kk === 'group') ? 1 : -1; } drawTable(ov); });
  $('#tbl tbody').innerHTML = rows.map(t => {
    if (t.missing) return `<tr><td class="l tk">${esc(t.ticker)}</td><td class="l mut" colspan="${COLS.length - 1}">saknar kursdata</td><td><span class="x" data-rm="${esc(t.ticker)}">✕</span></td></tr>`;
    const rsiC = t.rsi14 >= 70 ? 'neg' : t.rsi14 <= 30 ? 'pos' : '';
    return `<tr class="click" data-t="${esc(t.ticker)}">
      <td class="l"><span class="tk">${esc(t.ticker)}</span><div class="nm">${esc(t.name)}</div></td>
      <td class="l"><span class="grpcell" data-gt="${esc(t.ticker)}" data-gv="${esc(t.group)}">${esc(t.group)}</span></td>
      <td>${nf(t.last, 2)} <span class="mut">${esc(t.currency || '')}</span></td>
      ${PER.map(([kk]) => `<td class="${cls(t[kk])}"${baseTip(t, kk, t.currency)}>${pct(t[kk])}</td>`).join('')}
      <td class="${rsiC}">${nf(t.rsi14, 0)}</td><td class="${cls(t.vs_sma200)}">${pct(t.vs_sma200)}</td><td class="${cls(t.from_hi52)}">${pct(t.from_hi52)}</td>
      <td>${nf(t.pe, 1)}</td><td>${sigBadge(t)}</td><td>${esc(t.next_earnings || '–')}</td><td>${spark(t.spark)}</td>
      <td><span class="x" data-rm="${esc(t.ticker)}" title="Ta bort från listan">✕</span></td></tr>`;
  }).join('');
  $$('#tbl tr[data-t]').forEach(tr => tr.onclick = e => { if (e.target.closest('.x') || e.target.closest('.grpcell')) return; openStock(tr.dataset.t); });
  $$('#tbl .x').forEach(x => x.onclick = async e => { e.stopPropagation(); await api(`/lists/${S.listId}/tickers/${encodeURIComponent(x.dataset.rm)}`, { method: 'DELETE' }); await loadLists(); renderView(); });
  $$('#tbl .grpcell').forEach(c => c.onclick = e => {
    e.stopPropagation();
    const inp = document.createElement('input'); inp.value = c.dataset.gv; inp.setAttribute('list', 'grp-list'); inp.style.width = '130px';
    c.replaceWith(inp); inp.focus(); inp.select();
    const save = async () => { await api(`/lists/${S.listId}/tickers/${encodeURIComponent(c.dataset.gt)}`, { method: 'PATCH', body: { group: inp.value } }); await loadLists(); renderView(); };
    inp.onkeydown = ev => { if (ev.key === 'Enter') save(); if (ev.key === 'Escape') renderView(); };
    inp.onblur = save;
  });
}
async function addTickers() {
  const t = $('#add-t').value.trim(); if (!t) return;
  const btn = $('#btn-add'); btn.disabled = true; btn.textContent = 'Hämtar…';
  try {
    const r = await api(`/lists/${S.listId}/tickers`, { method: 'POST', body: { tickers: t, group: $('#add-g').value } });
    if (r.added.length) toast(`Lade till: ${r.added.join(', ')}`);
    r.failed.forEach(f => toast(`${f.ticker}: ${f.error}`, true));
    await loadLists(); renderView();
    if (r.added.length) setTimeout(async () => { await loadLists(); if (S.tab === 'overview') renderView(); }, 6000); // auto-grupp hinner sättas
  } catch (e) { toast(e.message, true); btn.disabled = false; btn.textContent = '+ Lägg till'; }
}

// ----------------------------------------------------------------------- jämför
async function viewCompare(v, rid) {
  const ov = await api(`/lists/${S.listId}/overview`);
  if (stale(rid)) return;
  S.ov = ov;
  const c = S.cmp, live = ov.tickers.filter(t => !t.missing), bench = ov.benchmark && !ov.benchmark.missing ? ov.benchmark.ticker : null;
  if (c.listId !== S.listId || !c.sel) { c.sel = new Set(live.slice(0, 6).map(t => t.ticker)); c.listId = S.listId; }
  if (!bench) c.rel = false;
  const ranges = [['1m', '1 mån'], ['3m', '3 mån'], ['6m', '6 mån'], ['ytd', 'Hittills i år'], ['1y', '1 år'], ['2y', '2 år']];
  v.innerHTML = guide('compare') + `<div class="panel">
    <div class="panel-head"><div><h3>Jämför utveckling${info('rebased')}</h3><div class="hint" style="margin:0">Alla serier indexeras till 100 vid startdatum, så olika bolag och marknader går att jämföra.</div></div>
    <div style="display:flex;gap:10px;flex-wrap:wrap"><div class="seg" id="seg-r">${ranges.map(([k, l]) => `<button data-v="${k}" class="${c.range === k ? 'on' : ''}">${l}</button>`).join('')}</div>
    <div class="seg" id="seg-rel"><button data-v="0" class="${!c.rel ? 'on' : ''}">Absolut</button><button data-v="1" class="${c.rel ? 'on' : ''}" ${bench ? '' : 'disabled'}>Relativt ${bench ? esc(bench) : 'index'}</button></div>${info('relmode')}</div></div>
    <div class="chips" id="chips">${live.map((t, i) => `<span class="chip ${c.sel.has(t.ticker) ? 'on' : ''}" data-t="${esc(t.ticker)}"><i style="${c.sel.has(t.ticker) ? 'background:' + PALETTE[[...c.sel].indexOf(t.ticker) % PALETTE.length] : ''}"></i>${esc(t.ticker)}${t.name !== t.ticker ? ` <span class="mut">${esc(t.name.length > 18 ? t.name.slice(0, 17) + '…' : t.name)}</span>` : ''}</span>`).join('')}
      <span class="chip" id="chip-all">Alla</span><span class="chip" id="chip-none">Ingen</span></div>
    <div class="chart-wrap tall"><canvas id="ch-cmp"></canvas></div></div>
    <div class="panel"><h3>Utveckling under perioden</h3><div class="tbl-scroll"><table id="cmp-tbl"></table></div></div>`;
  bindGuides();
  $$('#seg-r button').forEach(b => b.onclick = () => { c.range = b.dataset.v; renderView(); });
  $$('#seg-rel button').forEach(b => b.onclick = () => { c.rel = b.dataset.v === '1'; renderView(); });
  $$('#chips .chip[data-t]').forEach(ch => ch.onclick = () => { c.sel.has(ch.dataset.t) ? c.sel.delete(ch.dataset.t) : c.sel.add(ch.dataset.t); renderView(); });
  $('#chip-all').onclick = () => { c.sel = new Set(live.map(t => t.ticker)); renderView(); };
  $('#chip-none').onclick = () => { c.sel = new Set(); renderView(); };
  const names = Object.fromEntries(ov.tickers.map(t => [t.ticker, t.name]));
  const sel = [...c.sel];
  if (!sel.length) { $('#cmp-tbl').innerHTML = '<tr><td class="empty">Välj minst ett värdepapper ovan.</td></tr>'; return; }
  const q = [...new Set([...sel, ...(bench ? [bench] : [])])].map(encodeURIComponent).join(',');
  const d = await api(`/compare?tickers=${q}&range=${c.range}`);
  if (stale(rid)) return;
  const B = bench ? d.series[bench] : null;
  const val = (s, i) => c.rel && B ? s[i] / B[i] * 100 : s[i];
  const ds = sel.filter(t => d.series[t]).map((t, i) => ({ label: t, data: d.series[t].map((_, j) => val(d.series[t], j)), borderColor: PALETTE[i % PALETTE.length], backgroundColor: PALETTE[i % PALETTE.length], borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, tension: .15 }));
  if (bench && !c.rel && B) ds.push({ label: bench + ' (index)', data: B, borderColor: '#c9d1e0', borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, tension: .15 });
  mkChart('ch-cmp', {
    type: 'line', data: { labels: d.dates, datasets: ds },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: { duration: 250 },
      plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { callbacks: { label: x => ` ${x.dataset.label}: ${nf(x.parsed.y, 1)} (${pct(x.parsed.y - 100)})` } } },
      scales: { x: { ticks: { maxTicksLimit: 8, autoSkip: true }, grid: { display: false } }, y: { grid: { color: '#1d2736' } } },
    },
  });
  const rowsT = ds.map(s => ({ n: s.label, ch: s.data[s.data.length - 1] - 100 })).sort((a, b) => b.ch - a.ch);
  $('#cmp-tbl').innerHTML = `<thead><tr><th class="l">Värdepapper</th><th>${c.rel ? 'Relativt index' : 'Förändring'}</th></tr></thead><tbody>${rowsT.map(r => `<tr><td class="l"><span class="tk">${esc(r.n)}</span> <span class="mut">${esc(names[r.n] || '')}</span></td><td class="${cls(r.ch)}">${pct(r.ch)}</td></tr>`).join('')}</tbody>`;
}

// ---------------------------------------------------------------------- rapporter
async function viewReports(v, rid) {
  const r = await api(`/lists/${S.listId}/reports`);
  if (stale(rid)) return;
  const all = r.reports, withData = all.filter(x => x.has_data), without = all.filter(x => !x.has_data);
  const today = new Date().toISOString().slice(0, 10);
  const upcoming = all.filter(x => x.next_earnings && x.next_earnings >= today).sort((a, b) => a.next_earnings.localeCompare(b.next_earnings));
  const missingFund = all.some(x => x.fund_missing);
  v.innerHTML = guide('reports') + `
  <div class="panel"><h3>Kommande rapporter${info('nextearn')}</h3>
    <div class="chips">${upcoming.length ? upcoming.map(x => `<span class="chip on" data-t="${esc(x.ticker)}"><b class="tk">${esc(x.ticker)}</b> <span class="mut">${esc(x.next_earnings)}</span></span>`).join('') : '<span class="mut">Inga kommande rapportdatum hittades i den här listan.</span>'}</div></div>
  <div class="panel"><div class="panel-head"><div><h3>Senaste kvartalsrapport${info('quarter')}</h3><div class="hint" style="margin:0">Sammanfattning av rapporterade nyckeltal (inte ledningens kommentarer). Klicka på en rad för en löpande text.</div></div></div>
    ${missingFund ? '<div class="mut" style="margin-bottom:10px">Bolagsdata saknas för vissa värdepapper – tryck “Uppdatera” så hämtas den.</div>' : ''}
    <div class="tbl-scroll"><table id="rep"><thead><tr><th class="l">Bolag</th><th>Kvartal${info('quarter')}</th><th>Omsättning${info('revenue')}</th><th>Tillv. y/y${info('growth')}</th><th>Rörelsemarg.${info('margins')}</th><th>Δ y/y${info('marginchange')}</th><th>Nettoresultat${info('netincome')}</th><th>Netto y/y</th><th>EPS${info('eps')}</th><th>EPS vs förv.${info('surprise')}</th><th>Nästa rapport${info('nextearn')}</th></tr></thead><tbody>
    ${withData.map((x, i) => `<tr class="click" data-i="${i}"><td class="l"><span class="tk">${esc(x.ticker)}</span><div class="nm">${esc(x.name)}</div></td><td>${esc(x.quarter || '–')}</td><td>${money(x.revenue, x.currency)}</td><td class="${cls(x.revenue_yoy)}">${pct(x.revenue_yoy)}</td><td>${nf(x.operating_margin, 1)} %</td>
      <td class="${cls(x.operating_margin != null && x.operating_margin_prev_year != null ? x.operating_margin - x.operating_margin_prev_year : null)}">${x.operating_margin != null && x.operating_margin_prev_year != null ? pp(x.operating_margin - x.operating_margin_prev_year) : '–'}</td>
      <td>${money(x.net_income, x.currency)}</td><td class="${cls(x.net_income_yoy)}">${pct(x.net_income_yoy)}</td><td>${nf(x.eps, 2)}</td><td class="${cls(x.surprise_pct)}">${pct(x.surprise_pct)}</td><td>${esc(x.next_earnings || '–')}</td></tr>
      <tr class="detail" data-d="${i}" hidden><td class="l" colspan="11" style="white-space:normal"><div class="digest">${esc(x.headline)}</div><div>${x.flags.map(f => `<span class="tag flag">⚑ ${esc(f)}</span>`).join('')}</div><button class="btn sm" data-open="${esc(x.ticker)}" style="margin-top:8px">Öppna aktiesidan →</button></td></tr>`).join('')}
    </tbody></table></div>
    ${!withData.length ? '<div class="empty">Ingen kvartalsdata i den här listan (ETF:er och index har inga kvartalsrapporter).</div>' : ''}
    ${without.length ? `<div class="mut" style="margin-top:12px;font-size:12.5px">Utan kvartalsdata: ${without.map(x => esc(x.ticker)).join(', ')}</div>` : ''}
  </div>`;
  bindGuides();
  $$('#rep tr.click').forEach(tr => tr.onclick = () => { const d = $(`#rep tr[data-d="${tr.dataset.i}"]`); d.hidden = !d.hidden; if (!d.hidden && typeof track === 'function') track('report', tr.dataset.i); });
  $$('[data-open]').forEach(b => b.onclick = () => openStock(b.dataset.open));
  $$('.chips .chip[data-t]').forEach(c => c.onclick = () => openStock(c.dataset.t));
}

// ------------------------------------------------------------------------ aktie
async function viewStock(v, rid) {
  if (!S.ov || S.ov.list.id !== S.listId) S.ov = await api(`/lists/${S.listId}/overview`);
  if (stale(rid)) return;
  const st = S.stock, opts = S.ov.tickers;
  if (!st.ticker) st.ticker = opts.length ? opts[0].ticker : '';
  const ranges = [['1m', '1 mån'], ['3m', '3 mån'], ['6m', '6 mån'], ['ytd', 'Hittills i år'], ['1y', '1 år'], ['2y', '2 år']];
  v.innerHTML = `<div class="row-add"><select id="st-sel">${opts.map(t => `<option value="${esc(t.ticker)}" ${t.ticker === st.ticker ? 'selected' : ''}>${esc(t.ticker)} – ${esc(t.name)}</option>`).join('')}${opts.some(t => t.ticker === st.ticker) ? '' : `<option selected>${esc(st.ticker)}</option>`}</select>
    <input id="st-in" placeholder="…eller skriv en ticker som redan finns i någon lista"><button class="btn" id="st-go">Visa</button></div><div id="st-body" class="loading">Hämtar bolagsdata… (första gången kan det ta några sekunder)</div>`;
  $('#st-sel').onchange = e => { st.ticker = e.target.value; renderView(); };
  const go = () => { const t = $('#st-in').value.trim().toUpperCase(); if (t) { st.ticker = t; renderView(); } };
  $('#st-go').onclick = go; $('#st-in').onkeydown = e => { if (e.key === 'Enter') go(); };
  if (!st.ticker) { $('#st-body').innerHTML = '<div class="empty">Listan är tom.</div>'; return; }
  let d, s;
  try { [d, s] = await Promise.all([api(`/ticker/${encodeURIComponent(st.ticker)}`), api(`/ticker/${encodeURIComponent(st.ticker)}/series?range=${st.range}`).catch(() => null)]); }
  catch (e) { $('#st-body').innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
  if (stale(rid)) return;
  const m = d.metrics, i = d.info, cur = d.currency || '';
  if (m && typeof track === 'function') track('stock', d.ticker);
  if (!m) { $('#st-body').innerHTML = `<div class="empty">Ingen kursdata för ${esc(d.ticker)}. Lägg till tickern i en lista först.</div>`; return; }
  const row = (l, val, c = '', tip = '') => `<div class="row"><span>${l}</span><span class="${c}"${tip}>${val}</span></div>`;
  const pos = m.hi52 > m.lo52 ? Math.max(0, Math.min(100, (m.last - m.lo52) / (m.hi52 - m.lo52) * 100)) : 50;
  const sg = d.signal;
  const cards = [
    ['Avkastning', 'ret', PER.map(([k, l]) => row(l, pct(m[k]), cls(m[k]), baseTip(m, k, cur))).join('')],
    ['Risk & trend', 'risk', row('Volatilitet 30d (årlig)' + info('vol'), pct(m.vol_30d, 1, false)) + row('Max nedgång 1 år' + info('maxdd'), pct(m.max_dd_1y), 'neg') + row('Beta' + info('beta'), nf(i.beta, 2)) + row('RSI (14)' + info('rsi'), nf(m.rsi14, 0), m.rsi14 >= 70 ? 'neg' : m.rsi14 <= 30 ? 'pos' : '') + row('Mot SMA50' + info('vs_sma'), pct(m.vs_sma50), cls(m.vs_sma50)) + row('Mot SMA200' + info('vs_sma'), pct(m.vs_sma200), cls(m.vs_sma200)) + row('Volym mot snitt' + info('volratio'), m.vol_ratio == null ? '–' : nf(m.vol_ratio, 1) + '×')],
    ['Tekniska indikatorer', 'trend', techRows(m, row, cur)],
    ['52 veckor', 'hi52', row('Högsta', nf(m.hi52, 2)) + row('Lägsta', nf(m.lo52, 2)) + row('Från högsta', pct(m.from_hi52), cls(m.from_hi52)) + row('Från lägsta', pct(m.from_lo52), cls(m.from_lo52)) + `<div class="rangebar"><i style="left:calc(${pos}% - 1px)"></i></div><div class="mut" style="font-size:11.5px">Nuvarande kurs i 52-veckorsintervallet</div>`],
    ['Värdering', 'valuation', row('Börsvärde' + info('mcap'), money(i.marketCap, cur)) + row('P/E (trailing)' + info('pe'), nf(i.trailingPE, 1)) + row('P/E (forward)' + info('fpe'), nf(i.forwardPE, 1)) + row('P/B' + info('pb'), nf(i.priceToBook, 2)) + row('Utdelningsyta' + info('divyield'), m.div_yield == null ? '–' : pct(m.div_yield, 2, false)) + row('EPS (trailing)' + info('eps'), nf(i.trailingEps, 2)) + row('EPS (forward)' + info('eps'), nf(i.forwardEps, 2))],
    ['Lönsamhet', 'profitability', row('Bruttomarginal' + info('margins'), frac(i.grossMargins)) + row('Rörelsemarginal' + info('margins'), frac(i.operatingMargins)) + row('Nettomarginal' + info('margins'), frac(i.profitMargins)) + row('Avkastning eget kapital' + info('roe'), frac(i.returnOnEquity)) + row('Skuld/eget kapital' + info('de'), nf(i.debtToEquity, 0)) + row('Omsättningstillväxt' + info('growth'), frac(i.revenueGrowth)) + row('Vinsttillväxt' + info('growth'), frac(i.earningsGrowth))],
  ];
  const hasFund = ['trailingPE', 'forwardPE', 'marketCap', 'profitMargins'].some(k => i[k] != null);
  const dg = d.digest, q = d.quarters;
  $('#st-body').className = '';
  $('#st-body').innerHTML = guide('stock') + `
  <div class="stock-head"><div><div><span class="tk" style="font-size:20px">${esc(d.ticker)}</span> <span class="mut" style="font-size:16px">${esc(d.name)}</span></div>
    <div style="margin-top:6px">${[...(d.lists || []).map(x => `<span class="tag">${esc(x)}</span>`), i.sector ? `<span class="tag">${esc(i.sector)}</span>` : '', i.industry ? `<span class="tag">${esc(i.industry)}</span>` : '', i.exchange ? `<span class="tag">${esc(i.exchange)}</span>` : ''].join('')}</div></div>
    <div style="text-align:right"><div class="px">${nf(m.last, 2)} <span class="mut" style="font-size:15px">${esc(cur)}</span></div><div style="margin:4px 0"><button class="btn sm" id="st-journal">📝 Logga beslut</button></div><div class="${cls(m.r_1d)}">${pct(m.r_1d, 2)} idag · <span class="mut">${esc(m.last_date)}</span></div></div></div>
  ${signalPanel(sg, d.signal_basis)}
  <div class="panel"><div class="panel-head"><h3>Kursutveckling${info('pricechart')}</h3><div class="seg" id="seg-sr">${ranges.map(([k, l]) => `<button data-v="${k}" class="${st.range === k ? 'on' : ''}">${l}</button>`).join('')}</div></div>
    <div class="chart-wrap tall"><canvas id="ch-px"></canvas></div></div>
  <div class="kv">${cards.filter(([t]) => hasFund || !['Värdering', 'Lönsamhet'].includes(t)).map(([t, g, b]) => `<div class="card"><h4>${t}${info(g)}</h4>${b}</div>`).join('')}</div>
  <div class="panel"><h3>Kvartalsrapport${info('quarter')}</h3>
    ${d.fund_error ? `<div class="neg" style="font-size:12.5px;margin-bottom:8px">Kunde inte hämta all bolagsdata: ${esc(d.fund_error)}</div>` : ''}
    <div class="digest">${esc(dg.headline)}</div>
    <div style="margin:10px 0">${dg.flags.map(f => `<span class="tag flag">⚑ ${esc(f)}</span>`).join('')}${dg.beats ? `<span class="tag ${dg.beats.beat >= 3 ? 'good' : ''}">Slog förväntningarna i ${dg.beats.beat} av ${dg.beats.of}</span>` : ''}</div>
    ${q.length >= 2 ? '<div class="chart-wrap short"><canvas id="ch-q"></canvas></div>' : ''}
    ${q.length ? `<div class="tbl-scroll" style="margin-top:12px"><table><thead><tr><th class="l">Kvartal</th><th>Omsättning${info('revenue')}</th><th>Bruttovinst</th><th>Rörelseresultat</th><th>Rörelsemarg.${info('margins')}</th><th>Nettoresultat${info('netincome')}</th><th>EBITDA${info('ebitda')}</th><th>EPS${info('eps')}</th><th>Fritt kassaflöde${info('fcf')}</th></tr></thead><tbody>
      ${q.map(x => `<tr><td class="l">${esc(x.date)}</td><td>${money(x.revenue, cur)}</td><td>${money(x.gross_profit, cur)}</td><td>${money(x.operating_income, cur)}</td><td>${x.revenue && x.operating_income != null ? nf(x.operating_income / x.revenue * 100, 1) + ' %' : '–'}</td><td>${money(x.net_income, cur)}</td><td>${money(x.ebitda, cur)}</td><td>${nf(x.eps, 2)}</td><td>${money(x.fcf, cur)}</td></tr>`).join('')}</tbody></table></div>` : ''}
    ${d.earnings.length ? `<h3 style="margin-top:18px">Resultat mot förväntningar${info('surprise')}</h3><div class="tbl-scroll"><table><thead><tr><th class="l">Rapportdatum</th><th>Förväntad EPS</th><th>Faktisk EPS</th><th>Överraskning${info('surprise')}</th></tr></thead><tbody>${d.earnings.slice(0, 8).map(e => `<tr><td class="l">${esc(e.date)}</td><td>${nf(e.eps_estimate, 2)}</td><td>${nf(e.eps_actual, 2)}</td><td class="${cls(e.surprise_pct)}">${pct(e.surprise_pct)}</td></tr>`).join('')}</tbody></table></div>` : ''}
  </div>
  <div class="panel"><h3>Mina anteckningar</h3><div class="hint">Klistra in nyckelpunkter ur rapporten eller skriv din egen tes. Anteckningarna följer med i Claude-exporten.</div>
    <textarea id="note" rows="6" placeholder="Tes, risker, vad som får mig att köpa/sälja …">${esc(d.note.text)}</textarea>
    <div style="margin-top:8px;display:flex;gap:10px;align-items:center"><button class="btn primary" id="note-save">Spara anteckning</button><span class="mut" id="note-ts">${d.note.updated_at ? 'Sparad ' + new Date(d.note.updated_at).toLocaleString('sv-SE', { dateStyle: 'short', timeStyle: 'short' }) : ''}</span></div></div>`;
  bindGuides();
  $('#st-journal').onclick = () => { S.jPrefill = d.ticker; S.tab = 'journal'; renderTabs(); renderView(); };
  $$('#seg-sr button').forEach(b => b.onclick = () => { st.range = b.dataset.v; renderView(); });
  $('#note-save').onclick = async () => { await api(`/ticker/${encodeURIComponent(d.ticker)}/note`, { method: 'PUT', body: { text: $('#note').value } }); $('#note-ts').textContent = 'Sparad nu'; toast('Anteckning sparad'); };
  if (s) drawPrice(s, cur);
  if (q.length >= 2) drawQuarters(q, cur);
  stockRel(d.ticker);
}
function techRows(m, row, cur) {
  const macdTxt = m.macd == null ? '–' : (m.macd > m.macd_signal ? 'över signal' : 'under signal') + (m.macd_hist != null && m.macd_hist_prev != null ? (m.macd_hist > m.macd_hist_prev ? ' · stärks' : ' · avtar') : '');
  const dir = m.plus_di == null ? '' : (m.plus_di > m.minus_di ? ' uppåt' : ' nedåt');
  const adxTxt = m.adx == null ? '–' : nf(m.adx, 0) + (m.adx >= 25 ? ' (tydlig trend' + dir + ')' : m.adx < 20 ? ' (ingen trend)' : ' (svag trend' + dir + ')');
  return row('MACD' + info('macd'), macdTxt, m.macd == null ? '' : m.macd > m.macd_signal ? 'pos' : 'neg')
    + row('ADX (trendstyrka)' + info('adx'), adxTxt)
    + row('ATR (daglig rörelse)' + info('atr'), m.atr == null ? '–' : nf(m.atr, 2) + ' (' + nf(m.atr_pct, 1) + ' % av kursen)')
    + row('ATR-stopp' + info('stop'), m.stop == null ? '–' : nf(m.stop, 2) + ' (' + pct(m.stop_dist, 1) + ')')
    + row('Bollinger-bredd' + info('squeeze'), m.bb_width_pct == null ? '–' : 'percentil ' + nf(m.bb_width_pct, 0) + (m.bb_width_pct <= 10 ? ' · hopdragen' : ''))
    + row('Momentum 12–1' + info('mom121'), pct(m.mom_12_1), cls(m.mom_12_1))
    + row('SMA50 över SMA200' + info('cross'), m.sma50_over_200 == null ? '–' : m.sma50_over_200 ? 'ja' : 'nej', m.sma50_over_200 == null ? '' : m.sma50_over_200 ? 'pos' : 'neg');
}
function signalPanel(sg, basis) {
  if (!sg || sg.score == null) return `<div class="panel"><h3>Signalbetyg${info('signal')}</h3><div class="mut">För lite data för att räkna fram ett betyg (behöver minst ~200 handelsdagar kurshistorik).</div></div>`;
  const pos = Math.max(0, Math.min(100, (sg.score + 100) / 2));
  const conf = String(sg.confidence || '').toLowerCase();
  const bar = sc => { const w = Math.abs(sc) / 2 * 50; const c = sc > 0 ? 'var(--pos)' : sc < 0 ? 'var(--neg)' : 'var(--dim)'; return `<div class="pbar"><b></b><i style="${sc >= 0 ? 'left:50%' : `left:${50 - w}%`};width:${w}%;background:${c}"></i></div>`; };
  const pillarInfo = { trend: 'trend', momentum: 'momentum', rs: 'rsline', fundamentals: 'profitability', valuation: 'valuation' };
  return `<div class="panel"><div class="panel-head"><h3>Signalbetyg${info('signal')}</h3><span class="mut" style="font-size:12px">regelbaserat · ej backtestat · ingen rådgivning</span></div>
    <div class="sig-top"><div class="sig-big s-${sg.key}">${sg.score > 0 ? '+' : ''}${sg.score}<small>/100</small></div>
      <div style="flex:1;min-width:240px"><div class="sig-label">${esc(sg.label)}</div><div class="mut">${esc(sg.lay)}</div>
        <div style="margin-top:6px;font-size:12.5px">Säkerhet${info('confidence')}: <b>${esc(conf)}</b> · ${sg.n_pillars} av 5 pelare${info('pillars')} hade data</div></div></div>
    <div class="gauge"><i style="left:calc(${pos}% - 2px)"></i></div><div class="gauge-l"><span>−100 Sälj</span><span>0</span><span>+100 Köp</span></div>
    <div class="digest" style="margin-top:14px">${esc(sg.summary)}</div>
    <h4 style="margin:16px 0 4px">Så här räknades betyget fram${info('pillars')}</h4>
    <div class="tbl-scroll"><table class="pillars"><tbody>${sg.pillars.map(p => `<tr><td>${esc(p.name)}${info(pillarInfo[p.key])}${p.score == null ? '<div class="mut" style="font-weight:400;font-size:12px">saknar data</div>' : bar(p.score)}<div class="${cls(p.score)}" style="font-weight:400;font-size:12px">${p.score == null ? '' : (p.score > 0 ? '+' : '') + nf(p.score, 1) + ' av ±2'}</div></td>
      <td><ul>${p.reasons.map(r => `<li><span class="pts ${cls(r.pts)}">${r.pts > 0 ? '+' : ''}${r.pts}</span> ${esc(r.text)}</li>`).join('') || '<li class="mut">–</li>'}</ul></td></tr>`).join('')}</tbody></table></div>
    ${sg.warnings.length ? `<div style="margin-top:12px">${sg.warnings.map(w => `<span class="tag flag">⚑ ${esc(w)}</span>`).join('')}</div>` : ''}
    ${sg.invalidation ? `<div class="invalid"><b>Vad skulle ändra bilden?${info('invalid')}</b><br>${esc(sg.invalidation)}</div>` : ''}
    <div class="disclaimer">Betyget är en <b>sammanfattning av tekniska och fundamentala regler</b>, inte en prognos och inte ett råd att köpa eller sälja. Reglerna är inte testade mot historiska data ännu.${basis ? ` Jämförelsen mot andra bolag och index bygger på listan <b>${esc(basis)}</b>.` : ''}</div></div>`;
}
function drawPrice(s, cur) {
  const maxV = Math.max(...s.volume.filter(x => x != null), 1);
  mkChart('ch-px', {
    data: {
      labels: s.dates, datasets: [
        { type: 'line', label: 'Kurs', data: s.close, borderColor: '#5aa0ff', borderWidth: 2, pointRadius: 0, tension: .1, yAxisID: 'y', order: 1, fill: true, backgroundColor: ctx => { const { ctx: c, chartArea: a } = ctx.chart; if (!a) return 'transparent'; const g = c.createLinearGradient(0, a.top, 0, a.bottom); g.addColorStop(0, 'rgba(90,160,255,.22)'); g.addColorStop(1, 'rgba(90,160,255,0)'); return g; } },
        { type: 'line', label: 'SMA 50', data: s.sma50, borderColor: '#e8b34a', borderWidth: 1.3, borderDash: [5, 4], pointRadius: 0, yAxisID: 'y', order: 2 },
        { type: 'line', label: 'SMA 200', data: s.sma200, borderColor: '#b07cff', borderWidth: 1.3, borderDash: [5, 4], pointRadius: 0, yAxisID: 'y', order: 3 },
        { type: 'bar', label: 'Volym', data: s.volume, backgroundColor: 'rgba(137,149,168,.25)', yAxisID: 'yv', order: 4 },
      ]
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false }, animation: { duration: 250 },
      plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { callbacks: { label: c => c.dataset.label === 'Volym' ? ` Volym: ${nf(c.parsed.y / 1e6, 2)} mn` : ` ${c.dataset.label}: ${nf(c.parsed.y, 2)} ${cur}` } } },
      scales: { x: { ticks: { maxTicksLimit: 8, autoSkip: true }, grid: { display: false } }, y: { position: 'right', grid: { color: '#1d2736' } }, yv: { display: false, max: maxV * 5, min: 0 } },
    },
  });
}
function drawQuarters(q, cur) {
  const qs = [...q].reverse();
  mkChart('ch-q', {
    data: {
      labels: qs.map(x => x.date), datasets: [
        { type: 'bar', label: 'Omsättning', data: qs.map(x => x.revenue), backgroundColor: 'rgba(90,160,255,.7)', borderRadius: 4, yAxisID: 'y' },
        { type: 'bar', label: 'Nettoresultat', data: qs.map(x => x.net_income), backgroundColor: 'rgba(47,192,122,.7)', borderRadius: 4, yAxisID: 'y' },
        { type: 'line', label: 'Rörelsemarginal %', data: qs.map(x => x.revenue && x.operating_income != null ? x.operating_income / x.revenue * 100 : null), borderColor: '#e8b34a', backgroundColor: '#e8b34a', borderWidth: 2, pointRadius: 4, yAxisID: 'ym' },
      ]
    },
    options: {
      maintainAspectRatio: false, animation: { duration: 250 },
      plugins: { legend: { position: 'bottom', labels: { usePointStyle: true, boxWidth: 8 } }, tooltip: { callbacks: { label: c => c.dataset.yAxisID === 'ym' ? ` ${c.dataset.label}: ${nf(c.parsed.y, 1)} %` : ` ${c.dataset.label}: ${money(c.parsed.y, cur)}` } } },
      scales: { x: { grid: { display: false } }, y: { grid: { color: '#1d2736' }, ticks: { callback: v => money(v) } }, ym: { position: 'right', grid: { display: false }, ticks: { callback: v => v + ' %' } } },
    },
  });
}

// -------------------------------------------------------------------- Claude-export
async function viewClaude(v, rid) {
  const md = await (await fetch('/api/snapshot.md')).text();
  if (stale(rid)) return;
  const prompt = 'Läs bifogad marknadsradar-fil och ge en analys av marknadsläget: sektorrotation, marknadsbredd, vilka grupper som leder och släpar, tydliga signaler (RSI, 200-dagars, 52-veckorshögsta), samt vad kvartalsrapporterna säger. Skilj tydligt på fakta ur datan och dina tolkningar, och lyft vad som är osäkert.';
  v.innerHTML = guide('claude') + `<div class="panel"><h3>Exportera marknadsläget till Claude</h3>
    <div class="hint">Allt i appen – alla listor, mätetal, rapportsammanfattningar, kommande rapporter och dina anteckningar – samlas i en fil som Claude kan läsa.</div>
    <div class="row-add"><a class="btn primary" href="/api/snapshot/download?fmt=md" style="text-decoration:none">⬇ Ladda ner Markdown</a><a class="btn" href="/api/snapshot/download?fmt=json" style="text-decoration:none">⬇ Ladda ner JSON</a><button class="btn" id="cp-md">Kopiera Markdown</button></div>
    <ol style="line-height:1.8;color:var(--muted)">
      <li>Klicka <b>Uppdatera</b> så att datan är färsk.</li>
      <li>Ladda upp filen i ett Claude-samtal (eller i ditt Akt-handel-projekt) – eller klistra in texten.</li>
      <li>Be Claude analysera. Förslag på fråga:</li></ol>
    <pre class="md" id="prompt" style="max-height:none">${esc(prompt)}</pre>
    <div style="margin-top:8px"><button class="btn sm" id="cp-prompt">Kopiera frågan</button></div>
    <div class="hint" style="margin-top:14px">Filerna skrivs också automatiskt efter varje uppdatering till <code>data/export/snapshot.md</code> och <code>snapshot.json</code> i appmappen. Via API: <code>GET /api/snapshot</code> (JSON) och <code>GET /api/snapshot.md</code>. Om Claude körs lokalt (t.ex. Claude Code) kan den läsa filerna direkt.</div></div>
  <div class="panel"><h3>Förhandsvisning</h3><pre class="md">${esc(md)}</pre></div>`;
  bindGuides();
  $('#cp-md').onclick = async () => { await navigator.clipboard.writeText(md); toast('Markdown kopierad'); };
  $('#cp-prompt').onclick = async () => { await navigator.clipboard.writeText(prompt); toast('Frågan kopierad'); };
}

// -------------------------------------------------------------------- Ordlista
async function viewGlossary(v, rid) {
  const cats = [...new Set(Object.values(GLOSSARY).map(g => g.cat))];
  const st = S.gl || (S.gl = { cat: 'alla', plan: true });
  v.innerHTML = guide('glossary') + `<div class="panel"><div class="panel-head"><h3>Ordlista – ${Object.keys(GLOSSARY).length} begrepp</h3>
      <label class="chk"><input type="checkbox" id="gl-plan" ${st.plan ? 'checked' : ''}> Visa planerade funktioner</label></div>
    <div class="row-add"><input id="gl-q" placeholder="Sök, t.ex. RSI, momentum, P/E, stop …" value="${esc(S.gq || '')}" style="flex:1"></div>
    <div class="chips" id="gl-cats"><span class="chip ${st.cat === 'alla' ? 'on' : ''}" data-c="alla">Alla</span>${cats.map(c => `<span class="chip ${st.cat === c ? 'on' : ''}" data-c="${esc(c)}">${esc(c)}</span>`).join('')}</div>
    <div id="gl-list"></div></div>`;
  bindGuides();
  const draw = () => {
    const q = $('#gl-q').value.trim().toLowerCase();
    const hits = Object.entries(GLOSSARY).filter(([k, g]) => (st.plan || !g.plan) && (st.cat === 'alla' || g.cat === st.cat)
      && (!q || (g.t + ' ' + g.s + ' ' + g.what + ' ' + k).toLowerCase().includes(q)))
      .sort((a, b) => !q ? 0 : (b[1].t.toLowerCase().includes(q) || b[0].includes(q)) - (a[1].t.toLowerCase().includes(q) || a[0].includes(q)));
    $('#gl-list').innerHTML = hits.length ? hits.map(([k, g]) => `<details class="gent" data-k="${k}"><summary><b>${esc(g.t)}${g.plan ? ' <span class="tag">planerad</span>' : ''}</b><span class="s">${esc(g.s)}</span></summary><div class="gl-slot"></div></details>`).join('')
      : '<div class="empty">Inga träffar.</div>';
    $$('#gl-list details.gent').forEach(d => d.addEventListener('toggle', () => {
      const slot = $('.gl-slot', d);
      if (d.open && !slot.innerHTML) {
        slot.innerHTML = entryHTML(d.dataset.k);
        if (typeof track === 'function') track('gloss', d.dataset.k);
        $$('[data-gk]', slot).forEach(c => c.onclick = () => { S.gq = ''; $('#gl-q').value = GLOSSARY[c.dataset.gk].t; draw(); const t = $(`#gl-list details[data-k="${c.dataset.gk}"]`); if (t) { t.open = true; t.scrollIntoView({ block: 'start', behavior: 'smooth' }); } });
      }
    }));
    if (q && hits.length === 1) { const d = $('#gl-list details.gent'); d.open = true; }
  };
  $('#gl-q').oninput = () => { S.gq = ''; draw(); };
  $('#gl-plan').onchange = e => { st.plan = e.target.checked; draw(); };
  $$('#gl-cats .chip').forEach(c => c.onclick = () => { st.cat = c.dataset.c; $$('#gl-cats .chip').forEach(x => x.classList.toggle('on', x === c)); draw(); });
  draw();
  S.gq = '';
}

init().catch(e => { $('#view').innerHTML = `<div class="empty">Kunde inte starta: ${esc(e.message)}</div>`; });
