"""Read-only trading-day clock for the Today screen.

Times are America/New_York; EDT/EST comes from zoneinfo, never a fixed offset.
Close time comes from the exchange calendar (early closes included). The
timeline describes the registered schedule; it is not evidence that any step
ran. Rendered as SVG attributes only (strict CSP: no inline style or script).
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from .components import esc

NY = ZoneInfo('America/New_York')
START = 8 * 60  # visible window starts 8:00 ET
WIDTH, LEFT, RIGHT = 1000, 50, 50


def _minutes(moment):
    return moment.hour * 60 + moment.minute


def _label(minutes):
    h, m = divmod(minutes, 60)
    return f"{(h + 11) % 12 + 1}:{m:02d}{'a' if h < 12 else 'p'}"


def _scale(close):
    """Piecewise scale: widen the busy open and close periods, compress midday."""
    end = close + 75
    knots = [(START, 0.0), (10 * 60 + 30, 0.35), (close - 45, 0.57), (end, 1.0)]
    usable = WIDTH - LEFT - RIGHT
    def x(minutes):
        minutes = min(max(minutes, START), end)
        for (m0, f0), (m1, f1) in zip(knots, knots[1:]):
            if minutes <= m1:
                frac = f0 + (f1 - f0) * (minutes - m0) / max(m1 - m0, 1)
                return LEFT + usable * frac
        return LEFT + usable
    return x, end


def session_for(now, schedule=None):
    """Return (is_session, close_minutes). Unknown calendar => assume nothing."""
    local = now.astimezone(NY)
    try:
        if schedule is None:
            from agents.operator import MarketSchedule
            schedule = MarketSchedule()
        session = schedule._session(local)
        if session is None:
            return False, None
        close = schedule.session_close(local).astimezone(NY)
        return True, _minutes(close)
    except Exception:
        return None, None


def render_clock(now=None, schedule=None):
    now = (now or datetime.now(timezone.utc)).astimezone(NY)
    tz = now.tzname() or 'ET'
    is_session, close = session_for(now, schedule)
    if is_session is None:
        return ('<section class="day-clock" aria-label="Trading day"><h2>Today’s trading day</h2>'
                '<p>Market calendar unavailable. Schedule status unknown.</p></section>')
    if not is_session:
        return ('<section class="day-clock" aria-label="Trading day"><h2>Today’s trading day</h2>'
                f'<p>No US market session today ({esc(now.strftime("%a %b %d"))}). Nothing is scheduled to trade.</p></section>')
    cutoff = min(15 * 60 + 30, close - 30)
    steps = [
        (8 * 60 + 30, 'Health check', 'minor'),
        (9 * 60 + 30, 'Market opens', 'market'),
        (10 * 60, 'Team meeting', 'key'),
        (cutoff, 'No new buys', 'approval'),
        (close - 10, 'Close sweep', 'market'),
        (close, 'Market closes', 'key'),
        (close + 30, 'Daily summary', 'minor'),
    ]
    _x, end = _scale(close)
    y = 30
    svg = [f'<svg class="day-clock-svg" viewBox="0 0 {WIDTH} 110" role="img" aria-labelledby="day-clock-title">',
           f'<title id="day-clock-title">Trading day timeline in New York time, {esc(tz)}</title>',
           f'<line class="track" x1="{LEFT}" y1="{y}" x2="{WIDTH - RIGHT}" y2="{y}"/>',
           f'<line class="open" x1="{_x(9 * 60 + 30):.1f}" y1="{y}" x2="{_x(close):.1f}" y2="{y}"/>',
           f'<line class="approvals" x1="{_x(10 * 60 + 5):.1f}" y1="{y}" x2="{_x(cutoff):.1f}" y2="{y}"/>']
    for index, (minutes, label, kind) in enumerate(steps):
        x = _x(minutes)
        dy = 24 if index % 2 == 0 else 60  # alternate rows so neighbours never collide
        svg.append(f'<circle class="tick {kind}" cx="{x:.1f}" cy="{y}" r="6"/>'
                   f'<line class="stem" x1="{x:.1f}" y1="{y + 7}" x2="{x:.1f}" y2="{y + dy - 12}"/>'
                   f'<text class="t-time" x="{x:.1f}" y="{y + dy}" text-anchor="middle">{_label(minutes)}</text>'
                   f'<text class="t-label {kind}" x="{x:.1f}" y="{y + dy + 16}" text-anchor="middle">{esc(label)}</text>')
    now_m = _minutes(now)
    if START <= now_m <= end:
        x = _x(now_m)
        svg.append(f'<line class="now" x1="{x:.1f}" y1="{y - 16}" x2="{x:.1f}" y2="{y + 8}"/>'
                   f'<text class="now-label" x="{x:.1f}" y="{y - 20}" text-anchor="middle">now</text>')
    svg.append('</svg>')
    phase = ('market closed' if now_m >= close else 'market open' if now_m >= 9 * 60 + 30 else 'pre-market')
    early = ' · early close today' if close < 16 * 60 else ''
    return ('<section class="day-clock" aria-label="Trading day"><div class="day-clock-head"><h2>Today’s trading day</h2>'
            f'<span>Now {esc(_label(now_m))} {esc(tz)} · {esc(phase)}{esc(early)}</span></div>' + ''.join(svg) +
            '<p class="day-clock-note">Registered schedule in New York time; midday is compressed so the busy open and close are readable. A step on this line is a plan, not proof it ran — check Health for what actually ran.</p></section>')
