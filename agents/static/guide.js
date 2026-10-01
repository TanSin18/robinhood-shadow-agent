// How it works: demo stepper. The page is complete without this script.
(function () {
  function start() {
    var root = document.querySelector('.gd');
    if (!root) return;
    var steps = Array.prototype.slice.call(root.querySelectorAll('.gd-step'));
    var demo = root.querySelector('.gd-demo');
    var status = root.querySelector('.gd-demo-status');
    var playBtn = root.querySelector('[data-demo="play"]');
    var detailBtn = root.querySelector('[data-demo="detail"]');
    var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    var current = -1, timer = null;
    if (!steps.length || !demo) return;
    root.classList.add("gd-js");

    function mark(i, scroll) {
      current = Math.max(0, Math.min(steps.length - 1, i));
      var id = steps[current].getAttribute('data-step');
      steps.forEach(function (s, k) { s.classList.toggle('is-current', k === current); });
      root.querySelectorAll('.gd-node').forEach(function (n) {
        n.classList.toggle('is-current', n.getAttribute('data-step') === id);
      });
      root.querySelectorAll('.gd-edge').forEach(function (e) {
        e.classList.toggle('is-current', e.getAttribute('data-to') === id);
      });
      status.textContent = 'Step ' + (current + 1) + ' of ' + steps.length + ': ' +
        steps[current].querySelector('h3').textContent;
      if (scroll) steps[current].scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'nearest' });
    }
    function stop() { if (timer) { clearInterval(timer); timer = null; playBtn.textContent = 'Play demo'; } }
    function play() {
      if (timer) return stop();
      if (current >= steps.length - 1) current = -1;
      mark(current + 1, true);
      playBtn.textContent = 'Pause';
      timer = setInterval(function () {
        if (current >= steps.length - 1) return stop();
        mark(current + 1, true);
      }, 7000);
    }
    demo.addEventListener('click', function (event) {
      var action = event.target.getAttribute('data-demo');
      if (action === 'play') return play();
      if (action === 'detail') {
        var on = detailBtn.getAttribute('aria-pressed') !== 'true';
        detailBtn.setAttribute('aria-pressed', String(on));
        root.querySelectorAll('.gd-trader').forEach(function (d) { d.open = on; });
        return;
      }
      stop();
      if (action === 'next') mark(current + 1, true);
      if (action === 'prev') mark(current - 1, true);
    });
    root.querySelectorAll('.gd-node').forEach(function (node) {
      node.addEventListener('click', function () {
        stop();
        var id = node.getAttribute('data-step');
        var k = steps.findIndex(function (s) { return s.getAttribute('data-step') === id; });
        if (k >= 0) mark(k, false);
      });
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
