/* Spelläge ("Karriär"): frivilligt tillägg. Allt räknas på servern ur dina egna data (läsning, journal, portfölj, quiz).
   Stängs av under ⚙ Inställningar: då döljs fliken och inget loggas. */

const G = { enabled: false, state: null, quiz: null };
const WHERE_TAB = { overview: 'overview', stock: 'stock', glossary: 'glossary', backtest: 'backtest', journal: 'journal', portfolio: 'portfolio', macro: 'macro', game: 'game', practice: 'practice', paper: 'paper', playbook: 'practice', monthly: 'practice', stress: 'practice', luck: 'practice', spur: 'practice', events: 'samband', samband: 'samband', riskpanel: 'practice', stats: 'practice', rules: 'practice', profile: 'practice' };

async function gameInit() {
  try {
    const s = await api('/game');
    G.enabled = !!s.enabled;
    G.state = s.enabled ? s : null;
  } catch (e) { G.enabled = false; }
  renderGameChip();
}

function track(event, key) {
  if (!G.enabled) return;
  api('/game/track', { method: 'POST', body: { event, key: String(key) } }).then(announce).catch(() => { /* ok */ });
}

async function gameCheck() {
  if (!G.enabled) return;
  try { announce(await api('/game')); } catch (e) { /* ok */ }
}

function announce(s) {
  if (!s || !s.enabled) return;
  G.state = s;
  renderGameChip();
  (s.new || []).forEach((n, i) => setTimeout(() => {
    if (n.type === 'level') toast('🏆 ' + n.title);
    else if (n.type === 'badge') toast('🎖 Märke: ' + n.title);
    else toast('✓ Uppdrag klart: ' + n.title + (n.xp ? ' (+' + n.xp + ' p)' : ''));
  }, i * 900));
  if (S.tab === 'game' && (s.new || []).length) renderView();
}

function renderGameChip() {
  let chip = document.getElementById('game-chip');
  if (!G.enabled || !G.state) { if (chip) chip.remove(); return; }
  const a = document.getElementById('actions');
  if (!a) return;
  if (!chip) { chip = document.createElement('button'); chip.id = 'game-chip'; chip.className = 'btn chip-game'; chip.onclick = () => { S.tab = 'game'; renderTabs(); renderView(); }; a.prepend(chip); }
  chip.innerHTML = `🎓 Nivå ${G.state.level}: ${esc(G.state.rank)} <span class="mut">· ${G.state.xp} p</span>`;
}

function gameTabs() { return G.enabled ? [['game', 'Karriär']] : []; }

async function viewGame(v, rid) {
  const s = await api('/game');
  if (stale(rid)) return;
  if (!s.enabled) { v.innerHTML = '<div class="empty">Spelläget är avstängt. Slå på det under ⚙ Inställningar.</div>'; return; }
  G.state = s; renderGameChip();
  const cur = s.levels.find(l => l.n === s.level);
  const quest = q => `<div class="quest ${q.done ? 'done' : ''}"><span class="qmark">${q.done ? '✓' : '○'}</span>
    <div class="qtxt"><div class="qt">${esc(q.title)} <span class="mut small">+${q.xp} p</span></div><div class="mut small">${esc(q.desc)}</div></div>
    <div class="qprog">${esc(q.progress)}</div>
    ${!q.done && q.where ? `<button class="btn sm" data-go="${q.where}">${q.where === 'game' ? 'Starta quiz' : 'Gå dit'}</button>` : ''}</div>`;
  v.innerHTML = guide('game') + `
  <div class="panel game-hero"><div class="gh-top"><div><div class="mut small">Din nivå</div><div class="gh-rank">Nivå ${s.level}: ${esc(s.rank)}</div><div class="mut">${esc(cur.goal)}</div></div>
      <div class="gh-xp"><div class="big">${s.xp} p</div><div class="mut small">${s.quests_done} av ${s.quests_total} uppdrag klara</div></div></div>
    <div class="lvbar">${s.levels.map(l => `<div class="lv ${l.status}" title="${esc(l.name)}"><b>${l.n}</b><span>${esc(l.name)}</span></div>`).join('')}</div>
    <div class="disclaimer">${esc(s.principle)} <span class="chip on" data-gk="game">Om spelläget</span></div></div>
  ${s.levels.map(l => `<div class="panel lvpanel ${l.status}"><div class="panel-head"><h3>Nivå ${l.n}: ${esc(l.name)} ${l.complete ? '✅' : l.status === 'next' ? '<span class="mut small">(kommande)</span>' : ''}</h3><span class="mut small">${esc(l.goal)}</span></div>
    ${l.quests.map(quest).join('')}
    <div class="quizrow"><span class="small mut">Quiz: ${l.quiz.correct}/${l.quiz.total} rätt${l.quiz.passed ? ' · klarat' : ' · minst 4 krävs'}</span> <button class="btn sm ${l.quiz.passed ? '' : 'primary'}" data-quiz="${l.n}">${l.quiz.answered ? 'Gör om quiz' : 'Starta quiz'}</button></div></div>`).join('')}
  <div class="panel"><h3>Märken</h3><div class="badges">${s.badges.map(b => `<div class="badge ${b.done ? 'on' : ''}" title="${esc(b.desc)}"><span>${b.done ? '🎖' : '🔒'}</span><b>${esc(b.title)}</b><small>${esc(b.desc)}</small></div>`).join('')}</div></div>
  <div class="panel"><div class="mut small">Spelläget är ett hjälpmedel för att lära, inte ett bevis på att du handlar bra. <a href="#" id="game-reset">Nollställ framsteg</a></div></div>`;
  bindGuides();
  $$('[data-go]').forEach(b => b.onclick = () => {
    if (b.dataset.go === 'game') { const n = b.closest('.lvpanel'); n.querySelector('[data-quiz]').click(); return; }
    if (b.dataset.go === 'events' && typeof SB !== 'undefined') { SB.mode = 'events'; }
    if (typeof PR !== 'undefined') PR.mode = ['playbook', 'monthly', 'stress', 'luck', 'spur', 'riskpanel', 'stats', 'rules', 'profile'].includes(b.dataset.go) ? b.dataset.go : null;
    S.tab = WHERE_TAB[b.dataset.go] || 'overview'; renderTabs(); renderView();
  });
  $$('[data-gk]').forEach(c => c.onclick = () => openInfo(c.dataset.gk));
  $$('[data-quiz]').forEach(b => b.onclick = () => startQuiz(+b.dataset.quiz));
  $('#game-reset').onclick = async e => { e.preventDefault(); if (confirm('Nollställa alla nivåer, uppdrag och quizsvar? Journal och portfölj påverkas inte.')) { await api('/game/reset', { method: 'POST' }); await gameInit(); renderView(); } };
}

async function startQuiz(level) {
  const r = await api('/game/quiz/' + level);
  const qs = r.questions;
  let i = 0, right = 0;
  const shuffle = a => a.map(x => [Math.random(), x]).sort((a, b) => a[0] - b[0]).map(x => x[1]);
  const render = d => {
    if (i >= qs.length) {
      d.innerHTML = `<div class="g-head"><h3>Nivå ${level}: resultat</h3></div><p style="font-size:20px"><b>${right} av ${qs.length} rätt</b></p>
        <p>${right >= 4 ? 'Klarat! Det räknas som uppdrag för nivån.' : 'Minst 4 rätt krävs. Läs förklaringarna i Ordlistan och försök igen.'}</p>
        <div class="dlg-actions"><button class="btn primary" id="q-done">Stäng</button></div>`;
      $('#q-done', d).onclick = () => d.close();
      return;
    }
    const q = qs[i];
    d.innerHTML = `<div class="g-head"><h3>Nivå ${level}: quiz</h3><span class="mut">Fråga ${i + 1} av ${qs.length}</span></div>
      <p class="q-text">${esc(q.q)}</p><div class="q-opts">${shuffle(q.options).map(o => `<button class="q-opt" data-i="${o.i}">${esc(o.text)}</button>`).join('')}</div><div id="q-fb"></div>`;
    $$('.q-opt', d).forEach(b => b.onclick = async () => {
      $$('.q-opt', d).forEach(x => x.disabled = true);
      const a = await api('/game/quiz/answer', { method: 'POST', body: { qid: q.id, choice: +b.dataset.i } });
      if (a.correct) right++;
      $$('.q-opt', d).forEach(x => { if (+x.dataset.i === a.answer) x.classList.add('ok'); else if (x === b) x.classList.add('bad'); });
      $('#q-fb', d).innerHTML = `<div class="g-ex" style="margin-top:12px"><b>${a.correct ? 'Rätt.' : 'Inte riktigt.'}</b> ${esc(a.why)}</div><div class="dlg-actions"><button class="btn primary" id="q-next">${i + 1 >= qs.length ? 'Se resultat' : 'Nästa fråga'}</button></div>`;
      $('#q-next', d).onclick = () => { i++; render(d); };
    });
  };
  dialog('', d => render(d), 'wide');
  const d = $('#dlg');
  d.addEventListener('close', () => { gameCheck(); if (S.tab === 'game') renderView(); }, { once: true });
}
