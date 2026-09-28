'use strict';
document.documentElement.classList.add('scene-enhanced');
const scenes = Array.from(document.querySelectorAll('[data-scene-review]'));
const players = [];
scenes.forEach((review, index) => {
  review.hidden = index !== 0;
  const scene = review.querySelector('[data-scene]');
  const steps = Array.from(scene.querySelectorAll('[data-handoff-step]'));
  let current = 0, timer = null;
  const play = scene.querySelector('[data-replay="play"]');
  function stop() {
    clearInterval(timer); timer = null;
    play.textContent = 'Play'; scene.classList.remove('is-playing');
  }
  function select(n) {
    if (!steps.length) return;
    current = Math.max(0, Math.min(n, steps.length - 1));
    const selected = steps[current];
    const edges = selected.dataset.handoffEdges.split(' ');
    scene.querySelectorAll('[data-edge]').forEach(edge => edge.classList.toggle('edge-selected', edges.includes(edge.dataset.edge)));
    steps.forEach((step,i) => step.setAttribute('aria-current', String(i === current)));
    scene.querySelector('.speech-who').textContent = selected.querySelector('.handoff-from').textContent;
    scene.querySelector('.speech-message').textContent = selected.querySelector('.handoff-message').textContent;
    scene.querySelector('[data-step-label]').textContent = `Step ${current + 1} of ${steps.length} · Recorded replay`;
    scene.querySelector('[data-replay="previous"]').disabled = current === 0;
    scene.querySelector('[data-replay="next"]').disabled = current === steps.length - 1;
  }
  scene.querySelectorAll('[data-replay]').forEach(button => button.addEventListener('click', () => {
    if (!steps.length) return;
    const action = button.dataset.replay;
    if (action === 'play') {
      if (timer) { stop(); return; }
      if (current === steps.length - 1) select(0);
      play.textContent = 'Pause'; scene.classList.add('is-playing');
      timer = setInterval(() => { if (current === steps.length - 1) stop(); else select(current + 1); }, 2200);
    } else {
      stop();
      if (action === 'all') {
        scene.querySelectorAll('[data-edge]').forEach(edge => edge.classList.add('edge-selected'));
        scene.querySelector('[data-step-label]').textContent = 'Whole recorded path';
      } else select(current + (action === 'previous' ? -1 : 1));
    }
  }));
  steps.forEach((step,i) => step.addEventListener('click', () => { stop(); select(i); }));
  scene.addEventListener('keydown', event => {
    if (!steps.length || !event.target.closest('.scene-player')) return;
    if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
      event.preventDefault(); stop(); select(current + (event.key === 'ArrowRight' ? 1 : -1));
    }
  });
  review.querySelectorAll('[data-character]').forEach(button => button.addEventListener('click', () => {
    const panel = document.getElementById(button.dataset.character);
    const next = !panel.open;
    review.querySelectorAll('.scene-character').forEach(p => { p.open = false; });
    panel.open = next;
    if (next) panel.scrollIntoView({block:'nearest',behavior:'auto'});
  }));
  review.querySelectorAll('.scene-character').forEach(panel => {
    panel.addEventListener('toggle', () => {
      const button = review.querySelector(`[data-character="${panel.id}"]`);
      button.setAttribute('aria-expanded', String(panel.open));
    });
    const tabs = Array.from(panel.querySelectorAll('[data-character-tab]'));
    function tabSelect(name) {
      tabs.forEach(t => { const chosen=t.dataset.characterTab===name; t.setAttribute('aria-selected',String(chosen)); t.tabIndex=chosen?0:-1; });
      panel.querySelectorAll('[data-character-pane]').forEach(p => { p.hidden=p.dataset.characterPane!==name; });
    }
    tabs.forEach((tab,i) => {
      tab.addEventListener('click', () => tabSelect(tab.dataset.characterTab));
      tab.addEventListener('keydown', e => {
        if (!['ArrowLeft','ArrowRight'].includes(e.key)) return;
        e.preventDefault(); const t=tabs[(i+(e.key==='ArrowRight'?1:tabs.length-1))%tabs.length];
        tabSelect(t.dataset.characterTab); t.focus();
      });
    });
    tabSelect('work');
  });
  select(0); players.push(stop);
});
document.querySelector('#scene-review')?.addEventListener('change', e => {
  players.forEach(stop => stop());
  scenes.forEach(s => { s.hidden=s.dataset.sceneReview!==e.target.value; });
});
document.addEventListener('visibilitychange', () => { if (document.hidden) players.forEach(stop => stop()); });
