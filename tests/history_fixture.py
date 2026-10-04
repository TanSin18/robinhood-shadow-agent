"""A small synthetic provider for the Checkpoint 8 tests. Invented prices in the vendor's documented file layout.

Nothing here is market data. The cases are chosen to exercise the rules: a split, a renamed company, an acquired
company, a bankrupt company, a spin-off, a large one-off distribution, a split factor with no recorded split, a
low-priced stock, a reused ticker, and a set of bad rows.
"""
import csv

import numpy as np

from firm_lab.history import calendar

FIRST, LAST = '2018-06-01', '2026-10-09'
SESSIONS = calendar.sessions(FIRST, LAST)
PRICE_HEADER = ['ticker', 'date', 'open', 'high', 'low', 'close', 'volume', 'closeadj', 'closeunadj', 'lastupdated']
TICKER_HEADER = ['table', 'permaticker', 'ticker', 'name', 'exchange', 'isdelisted', 'category', 'cusips', 'siccode', 'sicsector', 'sicindustry', 'famasector',
                 'famaindustry', 'sector', 'industry', 'scalemarketcap', 'scalerevenue', 'relatedtickers', 'currency', 'location', 'lastupdated', 'firstadded',
                 'firstpricedate', 'lastpricedate', 'firstquarter', 'lastquarter', 'secfilings', 'companysite']
# ticker -> (permaticker, start price, daily dollar volume scale, last session or None, delisted)
SECURITIES = {
    'AAA': (100001, 80.0, 9.0, None, False),      # 2-for-1 split on 2020-06-15
    'BBB': (100002, 40.0, 8.0, None, False),      # renamed from OLDB on 2020-03-02; one permanent identifier
    'CCC': (100003, 55.0, 7.5, '2021-06-30', True),   # acquired
    'DDD': (100004, 30.0, 7.0, '2020-09-15', True),   # bankrupt
    'EEE': (100005, 60.0, 6.5, None, False),      # spin-off ex-date 2020-08-03
    'FFF': (100006, 45.0, 6.0, None, False),      # 10% one-off cash distribution on 2020-05-11
    'GGG': (100007, 70.0, 5.5, None, False),      # split factor steps on 2020-07-01 with no recorded split
    'HHH': (100008, 2.0, 5.0, None, False),       # below the minimum price
    'III': (100009, 25.0, 4.5, None, False),
    'JJJ': (100010, 35.0, 4.0, None, False),
    'KKK': (100011, 90.0, 3.5, None, False),
    'LLL': (100012, 20.0, 3.0, None, False),
    'MMM': (100013, 65.0, 2.5, None, False),      # too thinly traded to rank inside a universe of six
}
SPLIT = ('AAA', '2020-06-15', 2.0)
FACTOR_STEP = ('GGG', '2020-07-01', 3.0)
SPIN_OFF = ('EEE', '2020-08-03', 0.80)
DISTRIBUTION = ('FFF', '2020-05-11', 0.10)


def series(ticker, seed=7):
    """{'sessions', 'open', 'high', 'low', 'close' (split-adjusted), 'volume', 'unadjusted', 'total'} for one security."""
    perma, start, scale, last, _ = SECURITIES[ticker]
    sessions = [s for s in SESSIONS if last is None or s <= last]
    rng = np.random.default_rng(seed + perma)
    returns = rng.normal(0.0003, 0.018, len(sessions))
    close = start * np.exp(np.cumsum(returns))
    if ticker == SPIN_OFF[0]:
        close[sessions.index(SPIN_OFF[1]):] *= SPIN_OFF[2]
    if ticker == DISTRIBUTION[0]:
        close[sessions.index(DISTRIBUTION[1]):] *= 1 - DISTRIBUTION[2]
    overnight = rng.normal(0, 0.004, len(sessions))
    open_ = np.r_[close[0], close[:-1]] * np.exp(overnight)
    wiggle = np.abs(rng.normal(0, 0.006, (2, len(sessions))))
    high = np.maximum(open_, close) * (1 + wiggle[0])
    low = np.minimum(open_, close) * (1 - wiggle[1])
    volume = np.round(np.exp(rng.normal(scale + 6, 0.35, len(sessions))) / close)
    factor = np.ones(len(sessions))                       # unadjusted close over split-adjusted close
    for who, day, ratio in (SPLIT, FACTOR_STEP):
        if ticker == who:
            factor[:sessions.index(day)] = ratio
    total = close.copy()
    if ticker == DISTRIBUTION[0]:
        total[:sessions.index(DISTRIBUTION[1])] *= 1 - DISTRIBUTION[2]
    return {'sessions': sessions, 'open': open_, 'high': high, 'low': low, 'close': close, 'volume': volume, 'unadjusted': close * factor, 'total': total}


def price_rows(tickers=None, *, through=LAST, rescale=None, decimals=6):
    """Vendor price rows. ``rescale`` = (ticker, factor) re-adjusts that ticker as a later split would; ``decimals`` is
    how finely the adjusted prices are printed."""
    for ticker in tickers or SECURITIES:
        data = series(ticker)
        k = 1.0 if not rescale or rescale[0] != ticker else rescale[1]
        for i, s in enumerate(data['sessions']):
            if s > through:
                break
            yield [ticker, s] + [f'{data[c][i] / k:.{decimals}f}' for c in ('open', 'high', 'low', 'close')] + [f'{data["volume"][i] * k:.1f}',
                                                                                                              f'{data["total"][i] / k:.{decimals}f}',
                                                                                                              f'{data["unadjusted"][i]:.4f}', '2026-10-03']


def write_prices(path, rows):
    with open(path, 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(PRICE_HEADER)
        writer.writerows(rows)
    return path


def write_tickers(path, *, extra=(), without_delisted=False):
    with open(path, 'w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=TICKER_HEADER)
        writer.writeheader()
        for ticker, (perma, _, _, last, delisted) in SECURITIES.items():
            if without_delisted and delisted:
                continue
            writer.writerow({'table': 'SEP', 'permaticker': perma, 'ticker': ticker, 'name': f'{ticker} Corp', 'exchange': 'NYSE', 'isdelisted': 'Y' if delisted else 'N',
                             'category': 'Domestic Common Stock', 'currency': 'USD', 'firstpricedate': FIRST, 'lastpricedate': last or LAST, 'sector': 'Technology',
                             'industry': 'Software', 'siccode': '7372', 'lastupdated': '2026-10-03',
                             'secfilings': f'https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={perma:010d}'})
            writer.writerow({'table': 'SF1', 'permaticker': perma, 'ticker': ticker, 'name': f'{ticker} Corp', 'exchange': 'NYSE', 'isdelisted': 'N',
                             'category': 'Domestic Common Stock', 'currency': 'USD', 'firstpricedate': FIRST, 'lastpricedate': LAST})
        for row in extra:
            writer.writerow(row)
    return path


def write_actions(path, extra=()):
    fff = series('FFF')
    paid = DISTRIBUTION[2] * fff['unadjusted'][fff['sessions'].index(DISTRIBUTION[1]) - 1]        # one tenth of the prior close
    rows = [['2020-06-15', 'split', 'AAA', 'AAA Corp', '2.0', '', ''],
            ['2020-03-02', 'tickerchangeto', 'BBB', 'BBB Corp', '', 'OLDB', 'OLDB Corp'],
            ['2021-06-30', 'acquisitionby', 'CCC', 'CCC Corp', '', 'AAA', 'AAA Corp'], ['2021-06-30', 'delisted', 'CCC', 'CCC Corp', '', '', ''],
            ['2020-09-15', 'bankruptcyliquidation', 'DDD', 'DDD Corp', '', '', ''],
            ['2020-08-03', 'spinoff', 'EEE', 'EEE Corp', '12.0', 'NEWE', 'NewE Corp'],
            ['2020-05-11', 'dividend', 'FFF', 'FFF Corp', f'{paid:.4f}', '', ''], ['2021-03-15', 'dividend', 'FFF', 'FFF Corp', '0.10', '', ''],
            ['2020-02-03', 'dividend', 'ZZZ', 'Unknown Corp', '0.10', '', '']]
    with open(path, 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['date', 'action', 'ticker', 'name', 'value', 'contraticker', 'contraname'])
        writer.writerows(rows + [list(r) for r in extra])
    return path


def write_sp500(path):
    with open(path, 'w', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['date', 'action', 'ticker', 'name', 'contraticker', 'contraname', 'note'])
        writer.writerows([['2019-01-02', 'added', 'AAA', 'AAA Corp', '', '', ''], ['2021-06-30', 'removed', 'CCC', 'CCC Corp', '', '', 'acquired']])
    return path


def provider(folder, *, through=LAST, rescale=None):
    """Writes the four vendor files into ``folder`` and returns their paths."""
    return {'tickers': write_tickers(folder / 'TICKERS.csv'), 'prices': write_prices(folder / 'SEP.csv', price_rows(through=through, rescale=rescale)),
            'actions': write_actions(folder / 'ACTIONS.csv'), 'sp500': write_sp500(folder / 'SP500.csv')}
