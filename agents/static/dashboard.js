'use strict';
// No broker, model or remote requests. Refresh only this local, filtered view.
const views = Array.from(document.querySelectorAll('[data-view]'));
const recordedCards = new Set();
let recordingCards = false;
async function recordShownCards() {
  if (recordingCards || document.visibilityState !== 'visible') return;
  const token = document.querySelector('input[name="csrf"]')?.value;
  const ids = Array.from(document.querySelectorAll('[data-card-id]'))
    .map(card => card.dataset.cardId).filter(id => !recordedCards.has(id)).slice(0, 30);
  if (!token || !ids.length) return;
  recordingCards = true;
  try {
    const response = await fetch('/views', {method:'POST', mode:'same-origin',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:new URLSearchParams({csrf:token, ids:JSON.stringify(ids)}).toString()});
    if (response.ok) ids.forEach(id => recordedCards.add(id));
  } catch (_) {
    // Optional display receipt: never interrupt reading or approving a card.
  } finally { recordingCards = false; }
}
if (views.length && views.every(view => view.dataset?.view)) {
  const names = {next:'Overview', decisions:'Approvals', activity:'Decision room', history:'History', results:'Results', controls:'Controls'};
  const navigate = (focus = false) => {
    const requested = window.location.hash.slice(1);
    // Preserve the accessible skip link without switching the selected view.
    if (requested === 'main') return;
    const selected = Object.hasOwn(names, requested) ? requested : 'next';
    views.forEach(view => {
      view.hidden = view.dataset.view !== selected;
      if (!view.hidden && focus) view.focus();
    });
    document.querySelectorAll('[data-nav]').forEach(link => {
      if (link.dataset.nav === selected) link.setAttribute('aria-current', 'page');
      else link.removeAttribute('aria-current');
    });
    const heading = document.querySelector('#view-title');
    if (heading) heading.textContent = names[selected];
    document.querySelectorAll('[data-refresh]').forEach(link => {
      link.href = window.location.search + '#' + selected;
    });
    if (focus) window.scrollTo({top:0, behavior:'instant'});
    if (selected === 'decisions') recordShownCards();
  };
  navigate();
  window.addEventListener('hashchange', () => navigate(true));
}
const decisionRoom = document.querySelector('[data-decision-room]');
if (decisionRoom && window.ShadowDecisionRoom) {
  window.ShadowDecisionRoom.init(decisionRoom, window.sessionStorage);
}
const toggle = document.querySelector('#auto-refresh');
const params = new URLSearchParams(window.location.search);
if (toggle && params.get('refresh') === 'off') toggle.checked = false;
if (toggle) toggle.addEventListener('change', () => {
  const url = new URL(window.location.href);
  if (toggle.checked) url.searchParams.delete('refresh');
  else url.searchParams.set('refresh', 'off');
  window.history.replaceState(null, '', url);
});
let editing = false;
document.querySelectorAll('form').forEach(form => {
  form.addEventListener('input', () => { editing = true; });
  form.addEventListener('change', () => { editing = true; });
  form.addEventListener('submit', () => { editing = true; });
});
setInterval(() => {
  const now = Date.now();
  document.querySelectorAll('[data-expires]').forEach(item => {
    const seconds = Math.max(0, Math.ceil((Date.parse(item.dataset.expires) - now) / 1000));
    item.textContent = seconds > 0 ? `Expires in ${Math.floor(seconds / 60)}m ${seconds % 60}s` : 'Expired — refresh to see the recorded status';
    if (seconds === 0) item.closest('article')?.querySelectorAll('button').forEach(button => { button.disabled = true; });
  });
}, 1000);
setInterval(() => {
  if (document.body.dataset.auto !== 'on' || !toggle?.checked || editing) return;
  if (document.visibilityState !== 'visible' || document.querySelector('details[open]')) return;
  if (document.activeElement?.closest('form') ||
      document.activeElement?.matches?.('button,a,input,select,summary,[tabindex]')) return;
  window.location.reload();
}, 30000);
