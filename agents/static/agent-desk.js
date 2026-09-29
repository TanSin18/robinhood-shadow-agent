'use strict';
document.querySelectorAll('.lane-atlas').forEach(atlas => {
  const buttons = atlas.querySelectorAll('[data-lane-mode]');
  function select(mode) {
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.laneMode === mode)));
    atlas.querySelectorAll('[data-lane-view]').forEach(panel => { panel.hidden = panel.dataset.laneView !== mode; });
  }
  buttons.forEach(button => button.addEventListener('click', () => select(button.dataset.laneMode)));
  select('guide');
});
document.documentElement.classList.add('team-interactive');
function updatePreviewExpiry() {
  document.querySelectorAll('[data-preview-expires]').forEach(card => {
    const deadline = new Date(card.dataset.previewExpires);
    if (!Number.isFinite(deadline.getTime()) || Date.now() < deadline.getTime()) return;
    const label = card.querySelector('[data-expiry-label]');
    if (label) label.textContent = 'Expired ' + deadline.toLocaleTimeString('en-US', {timeZone:'America/New_York',hour:'numeric',minute:'2-digit'}) + ' ET';
    const status = card.querySelector('[data-card-status]');
    if (status?.textContent === 'PENDING') status.textContent = 'EXPIRED';
  });
}
updatePreviewExpiry();
setInterval(updatePreviewExpiry, 1000);
const teamReview = document.querySelector('#team-review');
teamReview?.addEventListener('change', () => {
  document.querySelectorAll('[data-review]').forEach(review => {
    review.hidden = review.dataset.review !== teamReview.value;
  });
});
document.querySelectorAll('[data-agent-panel]').forEach(button => {
  button.addEventListener('click', () => {
    const panel = document.getElementById(button.dataset.agentPanel);
    const open = !panel.open;
    button.closest('[data-review]').querySelectorAll('.team-panel').forEach(p => { p.open = false; });
    panel.open = open;
    if (open) panel.scrollIntoView({block: 'nearest', behavior: 'auto'});
  });
});
document.querySelectorAll('.team-panel').forEach(panel => {
  panel.addEventListener('toggle', () => {
    document.querySelector(`[data-agent-panel="${panel.id}"]`)?.setAttribute('aria-expanded', String(panel.open));
  });
});
if (typeof recordShownCards === 'function') recordShownCards();
// Optional presentation enhancement only. All saved runs are readable without JS.
const runPicker = document.querySelector('#desk-run');
runPicker?.addEventListener('change', () => {
  document.querySelectorAll('.desk-run').forEach(run => {
    run.hidden = Boolean(runPicker.value) && run.id !== runPicker.value;
  });
});
