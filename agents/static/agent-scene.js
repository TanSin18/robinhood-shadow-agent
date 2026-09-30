'use strict';
// Decision room: selection, log filters and a replay of the recorded run log.
// Nothing here fetches data; it only moves highlight between server-rendered records.
document.documentElement.classList.add('scene-enhanced');
const PIPE = ['evidence', 'research', 'portfolio', 'critic', 'risk', 'final'];
const players = [];
const scenes = Array.from(document.querySelectorAll('[data-scene-review]'));
scenes.forEach((review, index) => {
  review.hidden = index !== 0;
  const nodes = () => review.querySelectorAll('.flow-node[data-actor], .flow-item[data-actor]');
  function focusEdges(actor) {
    review.querySelectorAll('.flow-svg .flow-edge[data-flow]').forEach(edge => {
      const [a, b] = edge.dataset.flow.split('-');
      edge.classList.toggle('edge-focus', a === actor || b === actor);
    });
  }
  function select(actor, scroll) {
    if (!PIPE.includes(actor)) actor = 'evidence';
    review.dataset.selected = actor;
    review.querySelectorAll('[data-inspect]').forEach(p => { p.hidden = p.dataset.inspect !== actor; });
    nodes().forEach(n => {
      const on = n.dataset.actor === actor;
      n.classList.toggle('is-selected', on);
      n.setAttribute('aria-pressed', String(on));
    });
    focusEdges(actor);
    if (scroll) review.querySelector(`[data-inspect="${actor}"]`)?.scrollIntoView({block: 'nearest', behavior: 'auto'});
  }
  nodes().forEach(n => {
    n.addEventListener('click', () => { stop(); select(n.dataset.actor, false); });
    n.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); stop(); select(n.dataset.actor, false); }
    });
  });
  review.querySelectorAll('[data-log-select]').forEach(b => b.addEventListener('click', () => {
    stop(); select(b.dataset.logSelect, true); mark(b.closest('.log-row'));
  }));
  // Tabs inside each inspector.
  review.querySelectorAll('.inspector').forEach(panel => {
    const tabs = Array.from(panel.querySelectorAll('[data-character-tab]'));
    function tab(nameSel) {
      tabs.forEach(t => { const on = t.dataset.characterTab === nameSel; t.setAttribute('aria-selected', String(on)); t.tabIndex = on ? 0 : -1; });
      panel.querySelectorAll('[data-character-pane]').forEach(p => { p.hidden = p.dataset.characterPane !== nameSel; });
    }
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => tab(t.dataset.characterTab));
      t.addEventListener('keydown', e => {
        if (!['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
        e.preventDefault();
        const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
        tab(next.dataset.characterTab); next.focus();
      });
    });
    tab('work');
  });
  // Log filters.
  const logRows = Array.from(review.querySelectorAll('.log-scroll .log-row'));
  review.querySelectorAll('[data-log-filter]').forEach(b => b.addEventListener('click', () => {
    review.querySelectorAll('[data-log-filter]').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
    const f = b.dataset.logFilter;
    logRows.forEach(r => { r.hidden = f !== 'all' && r.dataset.logActor !== f; });
  }));
  // Replay: walk the recorded log in order; pacing follows recorded offsets.
  const label = review.querySelector('[data-step-label]');
  const play = review.querySelector('[data-replay="play"]');
  let current = -1, timer = null;
  function mark(row) {
    logRows.forEach(r => r.removeAttribute('aria-current'));
    if (row) { row.setAttribute('aria-current', 'true'); row.scrollIntoView({block: 'nearest', behavior: 'auto'}); }
  }
  function seconds(row) { const m = /\+(\d+)s/.exec(row?.querySelector('.log-offset')?.textContent || ''); return m ? Number(m[1]) : null; }
  function step(n) {
    if (!logRows.length) return;
    current = Math.max(0, Math.min(n, logRows.length - 1));
    const row = logRows[current];
    const actor = row.dataset.logActor;
    review.querySelectorAll('.flow-node, .flow-gate').forEach(x => x.classList.remove('is-live'));
    review.querySelectorAll('.flow-edge').forEach(x => x.classList.remove('edge-live'));
    if (actor === 'gate') review.querySelector('.flow-gate')?.classList.add('is-live');
    else review.querySelector(`.flow-node[data-actor="${actor}"]`)?.classList.add('is-live');
    review.querySelectorAll('.flow-svg .flow-edge[data-flow]').forEach(e => {
      const to = e.dataset.flow.split('-')[1];
      if (to === actor || (actor === 'gate' && e.dataset.flow === 'evidence-research')) e.classList.add('edge-live');
    });
    if (PIPE.includes(actor)) select(actor, false);
    mark(row);
    const t = row.querySelector('time')?.textContent || '';
    const who = row.querySelector('.log-actor')?.textContent || '';
    label.textContent = `${current + 1}/${logRows.length} · ${t} · ${who}: ${row.querySelector('.log-title').textContent}`;
    review.querySelector('[data-replay="previous"]').disabled = current === 0;
    review.querySelector('[data-replay="next"]').disabled = current === logRows.length - 1;
  }
  function stop() { clearTimeout(timer); timer = null; if (play) play.textContent = 'Replay run'; review.classList.remove('is-playing'); }
  function tick() {
    if (current >= logRows.length - 1) { stop(); return; }
    const a = seconds(logRows[current]), b = seconds(logRows[current + 1]);
    step(current + 1);
    const gap = (a !== null && b !== null) ? (b - a) * 90 : 900;
    timer = setTimeout(tick, Math.max(650, Math.min(2200, gap + 650)));
  }
  review.querySelectorAll('[data-replay]').forEach(b => b.addEventListener('click', () => {
    if (!logRows.length) return;
    const action = b.dataset.replay;
    if (action === 'play') {
      if (timer) { stop(); return; }
      if (current >= logRows.length - 1) current = -1;
      play.textContent = 'Pause'; review.classList.add('is-playing');
      tick();
    } else { stop(); step(current + (action === 'previous' ? -1 : 1)); }
  }));
  players.push(stop);
  select(review.dataset.selected || 'final', false);
});
document.querySelector('#scene-review')?.addEventListener('change', e => {
  players.forEach(s => s());
  scenes.forEach(s => { s.hidden = s.dataset.sceneReview !== e.target.value; });
});
document.addEventListener('visibilitychange', () => { if (document.hidden) players.forEach(s => s()); });
