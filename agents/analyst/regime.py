"""Market regime: a 3-state Gaussian hidden Markov model on daily VTI log returns.

Deterministic by construction (no random restarts): states are initialised from terciles of
20-session realized volatility, fitted by Baum-Welch with scaling, then ordered by variance and
named calm / normal / stressed. It is retrained after every close on all completed sessions.
Shadow only: nothing in the trading path reads it.
"""
from __future__ import annotations

import math

NAMES = ('calm', 'normal', 'stressed')


def log_returns(closes):
    """closes: [(day, close)] sorted -> [(day, 100 * ln(c_t / c_{t-1}))]."""
    out = []
    for (d0, c0), (d1, c1) in zip(closes, closes[1:]):
        if c0 and c1 and c0 > 0 and c1 > 0:
            out.append((d1, 100.0 * math.log(c1 / c0)))
    return out


def _init(x, k):
    import numpy as np
    n = len(x)
    vol = np.array([np.std(x[max(0, i - 19):i + 1]) if i >= 4 else np.std(x[:20]) for i in range(n)])
    edges = np.quantile(vol, np.linspace(0, 1, k + 1)[1:-1])
    lab = np.searchsorted(edges, vol)
    mu = np.array([x[lab == j].mean() if (lab == j).any() else x.mean() for j in range(k)])
    var = np.array([max(x[lab == j].var(), 1e-3) if (lab == j).sum() > 1 else x.var() for j in range(k)])
    a = np.full((k, k), 0.05 / (k - 1))
    np.fill_diagonal(a, 0.95)
    return np.full(k, 1.0 / k), a, mu, var


def _emis(x, mu, var):
    import numpy as np
    return np.exp(-0.5 * (x[:, None] - mu[None, :]) ** 2 / var[None, :]) / np.sqrt(2 * np.pi * var[None, :]) + 1e-300


def _forward_backward(x, pi, a, mu, var):
    import numpy as np
    n, k = len(x), len(pi)
    b = _emis(x, mu, var)
    alpha, c = np.zeros((n, k)), np.zeros(n)
    alpha[0] = pi * b[0]
    c[0] = alpha[0].sum()
    alpha[0] /= c[0]
    for t in range(1, n):
        alpha[t] = (alpha[t - 1] @ a) * b[t]
        c[t] = alpha[t].sum()
        alpha[t] /= c[t]
    beta = np.ones((n, k))
    for t in range(n - 2, -1, -1):
        beta[t] = (a @ (b[t + 1] * beta[t + 1])) / c[t + 1]
    gamma = alpha * beta
    gamma /= gamma.sum(axis=1, keepdims=True)
    xi = np.zeros((k, k))
    for t in range(n - 1):
        m = alpha[t][:, None] * a * (b[t + 1] * beta[t + 1])[None, :] / c[t + 1]
        xi += m / m.sum()
    return gamma, xi, float(np.log(c).sum())


def _viterbi(x, pi, a, mu, var):
    import numpy as np
    n, k = len(x), len(pi)
    lb = np.log(_emis(x, mu, var))
    la = np.log(a + 1e-300)
    d = np.log(pi + 1e-300) + lb[0]
    back = np.zeros((n, k), dtype=int)
    for t in range(1, n):
        s = d[:, None] + la
        back[t] = s.argmax(axis=0)
        d = s.max(axis=0) + lb[t]
    path = [int(d.argmax())]
    for t in range(n - 1, 0, -1):
        path.append(int(back[t][path[-1]]))
    return path[::-1]


def fit(returns, *, k=3, max_iter=200, tol=1e-6):
    """returns: [(day, pct log return)]. Returns a JSON-able result (or {'status': reason})."""
    try:
        import numpy as np
    except ImportError:
        return {'status': 'NUMPY_UNAVAILABLE'}
    if len(returns) < 120:
        return {'status': 'TOO_FEW_SESSIONS', 'sessions': len(returns)}
    days = [d for d, _ in returns]
    x = np.array([r for _, r in returns], dtype=float)
    pi, a, mu, var = _init(x, k)
    ll_prev, it, converged = -np.inf, 0, False
    for it in range(1, max_iter + 1):
        gamma, xi, ll = _forward_backward(x, pi, a, mu, var)
        pi = gamma[0] + 1e-6
        pi /= pi.sum()
        a = xi / xi.sum(axis=1, keepdims=True)
        w = gamma.sum(axis=0)
        mu = (gamma * x[:, None]).sum(axis=0) / w
        var = np.maximum((gamma * (x[:, None] - mu[None, :]) ** 2).sum(axis=0) / w, 1e-3)
        if abs(ll - ll_prev) < tol:
            converged = True
            break
        ll_prev = ll
    order = np.argsort(var)                       # calm -> stressed
    pi, a, mu, var = pi[order], a[np.ix_(order, order)], mu[order], var[order]
    gamma, _, ll = _forward_backward(x, pi, a, mu, var)
    path = _viterbi(x, pi, a, mu, var)
    last = gamma[-1]
    current = int(last.argmax())
    counts = [path.count(j) for j in range(k)]
    run = 1
    for s in reversed(path[:-1]):
        if s != path[-1]:
            break
        run += 1
    tomorrow = last @ a
    return {
        'status': 'OK', 'model': 'gaussian_hmm_3_state_vti_daily_log_returns', 'sessions': len(x),
        'first_day': days[0], 'last_day': days[-1], 'iterations': it, 'converged': converged, 'log_likelihood': round(ll, 3),
        'states': [{'name': NAMES[j], 'mean_daily_pct': round(float(mu[j]), 4), 'vol_daily_pct': round(float(math.sqrt(var[j])), 4),
                    'ann_return_pct': round(float(mu[j]) * 252, 2), 'ann_vol_pct': round(float(math.sqrt(var[j]) * math.sqrt(252)), 2),
                    'expected_duration_sessions': round(1.0 / max(1e-9, 1.0 - float(a[j, j])), 1), 'share_of_days': round(counts[j] / len(x), 3)}
                   for j in range(k)],
        'transition': [[round(float(v), 4) for v in row] for row in a],
        'current': NAMES[current], 'current_probabilities': {NAMES[j]: round(float(last[j]), 4) for j in range(k)},
        'tomorrow_probabilities': {NAMES[j]: round(float(tomorrow[j]), 4) for j in range(k)},
        'current_run_sessions': run,
        'path': [[days[i], NAMES[path[i]]] for i in range(max(0, len(path) - 260), len(path))],
        '_labels': {days[i]: NAMES[path[i]] for i in range(len(path))},   # internal: full path for Kelly; not stored
    }


def stability(new, old, window=20):
    """How many of the last `window` labels changed versus the previous night's fit (nightly refits can relabel history)."""
    if not new or not old or new.get('status') != 'OK' or old.get('status') != 'OK':
        return None
    prev = dict((d, s) for d, s in old.get('path') or [])
    recent = (new.get('path') or [])[-window:]
    common = [(d, s) for d, s in recent if d in prev]
    return {'compared_sessions': len(common), 'relabelled': sum(1 for d, s in common if prev[d] != s)}
