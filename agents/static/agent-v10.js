// Agent Desk v10: tabs, account picker and chart ranges. Every page is complete without this
// script; it only switches which already-rendered panel is visible.
(function () {
  function all(root, sel) { return Array.prototype.slice.call(root.querySelectorAll(sel)); }

  function activate(items, attr, value) {
    items.forEach(function (el) {
      if (el.getAttribute(attr) === value) { el.setAttribute('data-active', ''); }
      else { el.removeAttribute('data-active'); }
    });
  }

  // Tabs come in groups: a tab list may carry data-tabgroup="name" and its panels data-tabpanel="name".
  // The page's main tabs use the unnamed group. Switching one group never touches another.
  function setupTabs() {
    var tabs = all(document, '[data-tab]');
    if (!tabs.length) return;
    var panels = all(document, '[data-tabpanel]');
    function groupOfTab(t) { var g = t.closest('[data-tabgroup]'); return g ? g.getAttribute('data-tabgroup') : ''; }
    function show(id, push) {
      var panel = document.getElementById(id);
      if (!panel || !panel.hasAttribute('data-tabpanel')) return;
      var group = panel.getAttribute('data-tabpanel') || '';
      tabs.forEach(function (t) { if (groupOfTab(t) === group) t.setAttribute('aria-selected', t.getAttribute('data-tab') === id ? 'true' : 'false'); });
      panels.forEach(function (p) {
        if ((p.getAttribute('data-tabpanel') || '') !== group) return;
        if (p.id === id) p.setAttribute('data-active', ''); else p.removeAttribute('data-active');
      });
      var outer = panel.parentElement && panel.parentElement.closest('[data-tabpanel]');
      if (outer && !outer.hasAttribute('data-active')) show(outer.id, false);
      if (push && history.replaceState) history.replaceState(null, '', '#' + id);
    }
    tabs.forEach(function (t) {
      t.addEventListener('click', function (e) { e.preventDefault(); show(t.getAttribute('data-tab'), true); });
    });
    var hash = (location.hash || '').slice(1);
    if (hash) show(hash, false);
  }

  function setupAccounts() {
    var panels = all(document, '[data-acct]');
    if (!panels.length) return;
    var links = all(document, '[data-acct-link]');
    function show(key) {
      activate(panels, 'data-acct', key);
      all(document, '.v10-acct-chip').forEach(function (c) {
        if (c.getAttribute('data-acct-link') === key) c.setAttribute('aria-current', 'true'); else c.removeAttribute('aria-current');
      });
    }
    links.forEach(function (l) {
      l.addEventListener('click', function (e) {
        e.preventDefault();
        show(l.getAttribute('data-acct-link'));
        var picker = document.querySelector('.v10-acct-picker');
        if (picker && l.closest('table')) picker.scrollIntoView({ block: 'start' });
      });
    });
  }

  function setupRanges() {
    all(document, '.v10-ranged').forEach(function (box) {
      var buttons = all(box, '.v10-range');
      var panels = all(box, '[data-range-panel]');
      buttons.forEach(function (b) {
        b.addEventListener('click', function () {
          var r = b.getAttribute('data-range');
          buttons.forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
          activate(panels, 'data-range-panel', r);
        });
      });
    });
  }

  function setupExpandAll() {
    all(document, '[data-expand-all]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var scope = document.getElementById(btn.getAttribute('data-expand-all')) || document;
        var items = all(scope, 'details');
        var open = items.some(function (d) { return !d.open; });
        items.forEach(function (d) { d.open = open; });
        btn.textContent = open ? 'Collapse all' : 'Expand all';
      });
    });
  }

  // Ask Bubbles: an answer takes a few seconds; show that the question was sent and stop double submits.
  function setupAsk() {
    document.querySelectorAll('form.ask-form').forEach(function (form) {
      form.addEventListener('submit', function () {
        var btn = form.querySelector('button[type=submit]');
        setTimeout(function () {
          form.classList.add('is-asking');
          document.querySelectorAll('form.ask-form button[type=submit]').forEach(function (b) { b.disabled = true; });
          if (btn && !form.classList.contains('ask-preset')) btn.textContent = 'Reading the records…';
        }, 0);
      });
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') document.querySelectorAll('details.ask-fab[open]').forEach(function (d) { d.open = false; });
    });
  }

  function start() {
    document.documentElement.classList.add('v10-js');
    setupTabs(); setupAccounts(); setupRanges(); setupExpandAll(); setupAsk();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
