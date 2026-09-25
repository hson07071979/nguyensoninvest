# -*- coding: utf-8 -*-
"""SIGNAL SPEC — the ONE definition of a production entry signal outside the backtest.

Why this file exists (audit 23/09/2026)
---------------------------------------
Before this file the live scanner (`live_scan.py`, public repo) decided "MUA" from
four intraday conditions plus a `state == 'cho'` flag computed the night before.
A historical replay (evidence/audit_r5_parity.json) showed:
  * 2023-2026: 99 live "MUA" that the engine never bought, 80 of them failing
    Condition 9 (order imbalance) — and portfolio.py auto-booked MUA;
  * only 92/118 engine entries would have been flagged MUA, because the night-
    before score / TOP-N / volume ratio differ from what engine2 computes with the
    signal-session data (volume ratio includes today in its 20-day mean, RS and
    52-week high include today's close, TOP-N uses today's 20-day GTGD, ...).

Now:
  * spec_export.py (private repo) exports, for the NEXT session, every piece of
    history the engine needs (19-day sums, 52-week high so far, closes 249/59
    sessions back, static CANSLIM points, risk gate, DK5, base width, ...).
  * evaluate() below recombines them with the live session row EXACTLY the way
    engine2.screen() does. tests/test_parity.py replays history and checks that
    evaluate() and engine2.screen() agree session by session.
  * publish.py copies this file verbatim next to live_scan.py in the public repo.

Pure python, standard library only.
"""
import bisect

SPEC_VERSION = 2

LABEL = {
    'uni': 'Trong TOP {top_n} thanh khoản',
    'pct': 'Biên độ tăng giá',
    'vol': 'Khối lượng ≥ {vol_floor}× TB20',
    'gtgd': 'GTGD phiên ≥ {gtgd_bn} tỷ',
    'volat': 'Biến động TB20 ≥ {volat_pct}%',
    'mcap': 'Vốn hoá ≥ {mcap_bn} tỷ',
    'hist': 'Đủ {min_history} phiên lịch sử',
    'base': 'Nền giá ≤ {base_pct}%',
    'cond8': 'Đóng cửa nửa trên nến',
    'ordimb': 'Cỡ lệnh mua ≥ {ordimb_min}× cỡ lệnh bán',
    'risk': 'Qua cổng rủi ro',
    'dk5': 'LNST không ở vùng yếu {dk5_lo}–{dk5_hi}%',
    'score': 'Điểm CANSLIM ≥ {score_floor}',
}


def required_conditions(cfg):
    req = ['uni', 'pct', 'vol', 'gtgd', 'volat', 'mcap', 'hist', 'base', 'risk', 'score']
    if cfg.get('dk5_hi', 0.25) > cfg.get('dk5_lo', 0.0):      # DK5 tat tu 25/09/2026
        req.insert(9, 'dk5')
    if cfg.get('use_cond8'):
        req.append('cond8')
    if cfg.get('use_ordimb'):
        req.append('ordimb')
    return req


def labels(cfg):
    fmt = dict(top_n=cfg.get('top_n'), vol_floor=cfg.get('vol_floor'),
               gtgd_bn=round(cfg.get('gtgd_min', 0) / 1e9), volat_pct=round(cfg.get('volat_min', 0) * 100, 1),
               mcap_bn=round(cfg.get('min_mktcap', 0) / 1e9), min_history=cfg.get('min_history'),
               base_pct=round(cfg.get('base_range', 0) * 100), ordimb_min=('%.2f' % cfg.get('ordimb_min', 0)),
               score_floor=cfg.get('score_floor'),
               dk5_lo=round(cfg.get('dk5_lo', 0.0) * 100), dk5_hi=round(cfg.get('dk5_hi', 0.25) * 100))
    return {k: v.format(**fmt) for k, v in LABEL.items()}


def _f(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def _mean_with_today(s19, c19, today, need=16):
    """engine fa_ind.sma(): nanmean over 20 sessions, NaN if < 80% present."""
    if s19 is None or c19 is None or today is None:
        return None
    n = c19 + 1
    if n < need:
        return None
    return (s19 + today) / n


def _pct_rank(v, others):
    """engine fa_ind.pct_rank for one new value against the other symbols."""
    if v is None or not others or len(others) + 1 < 40:
        return None
    return bisect.bisect_left(others, v) / len(others)


def ordimb_of(row):
    bq, bc = _f(row.get('BuyQuantity')), _f(row.get('BuyCount'))
    sq, sc = _f(row.get('SellQuantity')), _f(row.get('SellCount'))
    if not (bq and bc and sq and sc) or bc <= 0 or sc <= 0 or bq <= 0 or sq <= 0:
        return None
    return (bq / bc) / (sq / sc)


def evaluate(sp, row, U, cfg):
    """sp  : per-symbol spec exported for this session (spec_export.export)
    row : FireAnt HistoricalQuotes row of the session (raw prices, VND)
    U   : universe-level spec (sorted r12 / r3 lists, TOP-N cut)
    cfg : PROD thresholds (thresholds.json['cfg'])
    Returns dict with values, passed, missing, required, all_ok."""
    close = _f(row.get('PriceClose')); basic = _f(row.get('PriceBasic'))
    hi = _f(row.get('PriceHigh')); lo = _f(row.get('PriceLow'))
    vol = _f(row.get('Volume')) or 0.0; tv = _f(row.get('TotalValue')) or 0.0
    # Adjusted OHLC (FireAnt Adj*) drive everything compared with adjusted
    # history (range/volatility, close-location, 52w high, RS, momentum) exactly
    # as engine2 does; raw prices drive the % change and market cap.
    ac = _f(row.get('AdjClose')) or close
    ah = _f(row.get('AdjHigh')) or hi
    al = _f(row.get('AdjLow')) or lo
    v = {}
    ok = {}
    if not close or not basic or close <= 0 or basic <= 0:
        return dict(valid=False, all_ok=False, passed=[], missing=['data'], values={})
    pct = close / basic - 1
    v['pct'] = pct
    ok['pct'] = pct >= sp['thr']
    vma = _mean_with_today(sp.get('vol_s19'), sp.get('vol_c19'), vol)
    volr = (vol / vma) if (vma and vma > 0) else None
    v['volr'] = volr
    ok['vol'] = volr is not None and volr >= cfg['vol_floor']
    ok['gtgd'] = tv >= cfg['gtgd_min']
    rng = ((ah - al) / ac) if (ah is not None and al is not None and ac) else None
    volat = _mean_with_today(sp.get('rng_s19'), sp.get('rng_c19'), rng)
    v['volat'] = volat
    ok['volat'] = volat is not None and volat >= cfg['volat_min']
    mc = (sp.get('shares') or 0) * close
    v['mcap'] = mc
    ok['mcap'] = mc > cfg['min_mktcap']
    ok['hist'] = (sp.get('nbars') or 0) >= cfg['min_history']
    ok['base'] = sp.get('base') is not None and sp['base'] <= cfg['base_range']
    tvma = _mean_with_today(sp.get('tv_s19'), sp.get('tv_c19'), tv)
    v['tvma20'] = tvma
    ok['uni'] = (not cfg.get('use_top_liquid', True)) or (tvma is not None and tvma > 0 and tvma >= U['topn_cut'])
    ok['cond8'] = (ac >= (ah + al) / 2) if (ah is not None and al is not None) else True
    oi = ordimb_of(row)
    v['ordimb'] = oi
    v['ordimb_available'] = oi is not None
    ok['ordimb'] = oi is not None and oi >= cfg['ordimb_min']
    ok['risk'] = not sp.get('blocked')
    npg = sp.get('npat_yoy')
    ok['dk5'] = not (npg is not None and cfg.get('dk5_lo', 0.0) <= npg < cfg.get('dk5_hi', 0.25))
    # ---- CANSLIM score with today's values (engine.canslim_score) ----
    p = dict(sp.get('pts_static') or {})
    _h = [x for x in (sp.get('hi52_249'), ah) if x is not None]
    hi52 = max(_h) if _h else None
    nh = (ac / hi52 - 1) if (hi52 and hi52 > 0) else None
    p['N'] = 10 if (nh is not None and nh >= -0.15) else 0
    p['S'] = 5 if (volr is not None and volr >= 1.2) else 0
    r12 = (ac / sp['c250'] - 1) if sp.get('c250') else None
    rs = _pct_rank(r12, U.get('r12'))
    p['L'] = 15 if (rs is not None and rs * 100 >= 70) else 0
    p['I'] = 10 if (tvma is not None and tvma >= 15e9) else 0
    r3 = (ac / sp['c60'] - 1) if sp.get('c60') else None
    mom = _pct_rank(r3, U.get('r3'))
    p['Mom'] = round(5 * (mom if mom is not None else 0.0), 1)
    score = sum(p.values())
    v.update(score=score, pts=p, rs=(None if rs is None else rs * 100), near_high=nh)
    ok['score'] = score >= cfg['score_floor']
    req = required_conditions(cfg)
    passed = [k for k in req if ok.get(k)]
    missing = [k for k in req if not ok.get(k)]
    return dict(valid=True, all_ok=not missing, passed=passed, missing=missing,
                required=req, values=v, ok=ok)


def classify(res, cfg, frac=1.0, volr_proj=None):
    """Signal level from evaluate(). MUA only when EVERY required production
    condition is satisfied with real data. Missing order-flow data is never MUA."""
    if not res.get('valid'):
        return None, 'NO_DATA'
    miss = set(res['missing'])
    if not miss:
        return 'MUA', None
    flow_wait = (miss == {'ordimb'} and not res['values'].get('ordimb_available'))
    if flow_wait:
        return 'SAP_DU', 'WAITING_FOR_FLOW_CONFIRMATION'
    static = {'risk', 'dk5', 'base', 'hist', 'mcap'}
    if miss & static:
        return None, 'NOT_ELIGIBLE'
    intraday = {'pct', 'vol', 'gtgd', 'volat', 'uni', 'cond8', 'score'}
    if len(miss & intraday) <= 1 and (miss - intraday) <= {'ordimb'}:
        return 'SAP_DU', 'NEAR'
    return 'THEO_DOI', 'PARTIAL'
