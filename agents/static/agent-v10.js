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

  function setupTabs() {
    var tabs = all(document, '[data-tab]');
    if (!tabs.length) return;
    var panels = all(document, '[data-tabpanel]');
    function show(id, push) {
      tabs.forEach(function (t) { t.setAttribute('aria-selected', t.getAttribute('data-tab') === id ? 'true' : 'false'); });
      panels.forEach(function (p) { if (p.id === id) p.setAttribute('data-active', ''); else p.removeAttribute('data-active'); });
      if (push && history.replaceState) history.replaceState(null, '', '#' + id);
    }
    tabs.forEach(function (t) {
      t.addEventListener('click', function (e) { e.preventDefault(); show(t.getAttribute('data-tab'), true); });
    });
    var hash = (location.hash || '').slice(1);
    if (hash && document.getElementById(hash) && document.getElementById(hash).hasAttribute('data-tabpanel')) show(hash, false);
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

  function start() {
    document.documentElement.classList.add('v10-js');
    setupTabs(); setupAccounts(); setupRanges(); setupExpandAll();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
