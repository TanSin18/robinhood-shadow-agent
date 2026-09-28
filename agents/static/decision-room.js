'use strict';
(function(root, factory) {
  const api = factory();
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.ShadowDecisionRoom = api;
})(typeof window === 'undefined' ? {} : window, function() {
  const choose = (state, requested) => ({
    ...state,
    selected: state.available.includes(requested) ? requested : state.available[0]
  });
  const chooseReview = choose;
  const chooseStage = choose;
  const chooseLane = choose;

  function init(root, storage) {
    if (!root) return;
    const status = root.querySelector('[data-decision-room-status]');
    const read = key => {
      try { return storage.getItem(`shadow-${key}`); } catch (_) { return null; }
    };
    const write = (key, value) => {
      try { storage.setItem(`shadow-${key}`, value); } catch (_) {}
    };
    const activate = (scope, key, requested, fallback) => {
      const direct = Array.from(scope.querySelectorAll(`[data-${key}]`));
      const panels = Array.from(scope.querySelectorAll(`[data-${key}-panel]`));
      const choices = Array.from(scope.querySelectorAll(`[data-${key}-choice]`));
      const choiceValue = node => node.dataset[`${key}Choice`];
      const available = key === 'review'
        ? direct.map(node => node.dataset[key]).filter(Boolean)
        : choices.map(choiceValue).filter(Boolean);
      const requestedIsValid = available.includes(requested);
      const fallbackValue = available.includes(fallback) ? fallback : available[0];
      const selected = requestedIsValid ? requested : fallbackValue;
      const targets = key === 'review' ? direct : panels;
      targets.forEach(node => {
        const value = key === 'review' ? node.dataset[key] : node.dataset[`${key}Panel`];
        node.hidden = value !== selected;
      });
      if (key !== 'review') {
        choices.forEach(node => node.setAttribute(
          'aria-pressed', String(choiceValue(node) === selected)
        ));
      }
      if (selected) write(key, selected);
      return {selected, fellBack: Boolean(requested) && !requestedIsValid};
    };
    const currentReview = () => root.querySelector('[data-review]:not([hidden])');
    const reviewChoice = root.querySelector('[data-review-choice]');
    const reviewResult = activate(root, 'review', read('review'));
    if (reviewChoice) reviewChoice.value = reviewResult.selected;
    let panel = currentReview();
    const stageResult = panel
      ? activate(panel, 'stage', read('stage'), panel.dataset.defaultStage)
      : {selected:null, fellBack:false};
    const laneResult = panel
      ? activate(panel, 'lane', read('lane'), 'A')
      : {selected:null, fellBack:false};
    if (status && (reviewResult.fellBack || stageResult.fellBack || laneResult.fellBack)) {
      status.textContent = 'Saved view was unavailable. Showing the latest available review and stage.';
    }
    root.addEventListener('click', event => {
      const stage = event.target.closest('[data-stage-choice]');
      const lane = event.target.closest('[data-lane-choice]');
      panel = currentReview();
      if (stage && panel?.contains(stage)) {
        activate(panel, 'stage', stage.dataset.stageChoice, panel.dataset.defaultStage);
      }
      if (lane && panel?.contains(lane)) activate(panel, 'lane', lane.dataset.laneChoice, 'A');
    });
    reviewChoice?.addEventListener('change', () => {
      const review = activate(root, 'review', reviewChoice.value);
      panel = currentReview();
      if (panel) {
        activate(panel, 'stage', panel.dataset.defaultStage, panel.dataset.defaultStage);
        activate(panel, 'lane', read('lane'), 'A');
      }
      reviewChoice.value = review.selected;
      if (status) status.textContent = 'Review changed. Decision flow and selections updated.';
    });
  }
  return {chooseReview, chooseStage, chooseLane, init};
});
