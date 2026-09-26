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

SPEC v3 (26/09/2026) — exact parity, not "close enough"
-------------------------------------------------------
v2 still left 2 LIVE-ONLY entries in 2018-2026 (2024-02-19 BSR, 2026-01-14 VNM):
RS / Momentum were ranked against the cross-section of the PREVIOUS session
(exported r12/r3 lists of t-1), while engine2 re-ranks the whole market AT t
(fa_ind.pct_rank). VNM: engine RS 67.92 (L = 0, score 44.6) vs live 70.09
(L = 15, score 59.6) -> a MUA the backtest never allowed. The same shortcut made
TOP-N use the t-1 cut. v3:
  * cross_section(): RS / Momentum percentiles and the TOP-N cut are computed on
    the SAME session-t cross-section as the engine (every symbol of the engine's
    universe, exported in U['xs'] with its history, plus its session-t row);
  * pct_ranks() is THE percentile definition: fa_ind.pct_rank (engine) calls it,
    the live layer calls it (min-rank for ties: count of strictly smaller values
    / (n - 1), >= 40 values);
  * mean20() is THE 20-session mean (fa_ind.sma_seq): float64 running sum oldest
    -> newest, NaN skipped, >= 16 values, stored as float32;
  * every quantity is computed with the engine's float32 arithmetic (f32) and
    compared the way numpy 2 compares a float32 matrix with a Python threshold
    (the threshold is cast to float32);
  * missing symbols of the session cross-section never become a guess: RS / Mom
    / TOP-N are bounded over every possible value of the missing symbols and a
    condition that is not decided under every completion is UNDETERMINED
    (never MUA; classify -> SAP_DU / CROSS_SECTION_INCOMPLETE).
tests/test_parity.py replays history session by session and FAILS on any
engine-only or live-only entry (and on any condition-level disagreement).
publish.py copies this file verbatim next to live_scan.py in the public repo.

Pure python, standard library only.
"""
import bisect
import math
import struct

SPEC_VERSION = 3

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

# engine canslim_score() point order (the float32 sum depends on it)
PTS_ORDER = ('C1', 'C2', 'C3', 'A1', 'A2', 'N', 'S', 'L', 'I', 'Mom')
RANK_MIN_N = 40          # fa_ind.pct_rank: fewer valid values -> NaN
MEAN_N, MEAN_NEED = 20, 16   # fa_ind.sma: 20 sessions, NaN if < 80% present


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


# ============================================================================
# float32 arithmetic of the engine. engine2 works on numpy float32 matrices
# (fa_prep.build); every +,-,*,/ is rounded to float32. Doing the operation in
# float64 and rounding once to float32 gives the SAME result for +,-,*,/
# (53 >= 2*24 + 2, double rounding is innocuous).
# ============================================================================
NAN = float('nan')


def f32(x):
    """Round a number to IEEE float32 (numpy float32 storage). None / junk -> NaN."""
    try:
        x = float(x)
    except (TypeError, ValueError):
        return NAN
    if x != x or x in (math.inf, -math.inf):
        return x
    try:
        return struct.unpack('<f', struct.pack('<f', x))[0]
    except OverflowError:
        return math.copysign(math.inf, x)


def isnan(x):
    return x is None or x != x


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return NAN
    return x


def add32(a, b):
    return NAN if (isnan(a) or isnan(b)) else f32(a + b)


def sub32(a, b):
    return NAN if (isnan(a) or isnan(b)) else f32(a - b)


def mul32(a, b):
    return NAN if (isnan(a) or isnan(b)) else f32(a * b)


def div32(a, b):
    """numpy float32 a / b (b == 0 -> +-inf, 0/0 -> NaN)."""
    if isnan(a) or isnan(b):
        return NAN
    if b == 0:
        return NAN if a == 0 else math.copysign(math.inf, a) * math.copysign(1.0, b)
    try:
        return f32(a / b)
    except OverflowError:
        return math.copysign(math.inf, a) * math.copysign(1.0, b)


def pos_or_nan(x):
    """np.where(x > 0, x, nan)."""
    return x if (not isnan(x) and x > 0) else NAN


def ret32(a, b):
    """engine r12 / r3: AC[t] / AC[t-k] - 1 on float32."""
    return sub32(div32(a, b), 1.0)


def round32(x, nd=1):
    """numpy round() of a float32 value: multiply, rint (half to even), divide — all float32."""
    if isnan(x):
        return NAN
    k = 10.0 ** nd
    y = f32(x * k)
    if y in (math.inf, -math.inf):
        return y
    return f32(float(round(y)) / k)


def ge32(x, thr):
    """numpy 2: float32 array/scalar >= Python float -> the threshold is cast to float32."""
    return (not isnan(x)) and x >= f32(thr)


def gt32(x, thr):
    return (not isnan(x)) and x > f32(thr)


def le32(x, thr):
    return (not isnan(x)) and x <= f32(thr)


# ============================================================================
# THE shared definitions (engine fa_ind imports them)
# ============================================================================
def mean20(s19, c19, x, n=MEAN_N, need=MEAN_NEED):
    """20-session mean of the engine (fa_ind.sma_seq) for the session whose value
    is `x`, given the running sum `s19` / count `c19` of the n-1 previous sessions
    (float64 running sum oldest -> newest, NaN skipped). NaN if < `need` values."""
    if s19 is None or c19 is None:
        return NAN
    s, c = float(s19), int(c19)
    if not isnan(x):
        s = s + x
        c += 1
    if c < need or c <= 0:
        return NAN
    return f32(s / c)


def window_sum(vals):
    """(running sum, count) exactly as fa_ind.sma_seq accumulates a window."""
    s, c = 0.0, 0
    for v in vals:
        if not isnan(v):
            s = s + float(v)
            c += 1
    return s, c


def pct_ranks(vals):
    """THE percentile rank of a cross-section (engine fa_ind.pct_rank row).
    vals: list of float / None / NaN. Rank = number of OTHER valid values strictly
    smaller (ties share the lowest rank) / (n - 1); NaN everywhere if n < 40."""
    idx = [k for k, v in enumerate(vals) if not isnan(v)]
    n = len(idx)
    out = [NAN] * len(vals)
    if n < RANK_MIN_N:
        return out
    srt = sorted(vals[k] for k in idx)
    for k in idx:
        out[k] = bisect.bisect_left(srt, vals[k]) / (n - 1)
    return out


def rank_bounds(v, srt, unknown):
    """Engine percentile of `v` in the session cross-section `srt` (sorted, valid
    values of the session; `v` itself included or not) when `unknown` symbols of
    the cross-section are missing. Returns (lo, hi) float32; (p, p) when complete.
    NaN (fewer than 40 values) scores exactly like 0 in canslim_score, so it is
    returned as 0.0. srt=None: cross-section unknown -> (0, 1)."""
    if isnan(v):
        return 0.0, 0.0
    if srt is None:
        return 0.0, 1.0
    c = bisect.bisect_left(srt, v)
    n = len(srt) + (0 if (c < len(srt) and srt[c] == v) else 1)   # n includes v itself
    u = int(unknown or 0)
    if u == 0:
        if n < RANK_MIN_N:
            return 0.0, 0.0
        p = f32(c / (n - 1))
        return p, p
    if n + u < RANK_MIN_N:
        return 0.0, 0.0
    lo = 0.0 if n < RANK_MIN_N else f32(c / (n - 1 + u))
    hi = f32((c + u) / (n - 1 + u))
    return lo, hi


def topn_bounds(x, tv_desc, unknown, top_n):
    """engine vn300.build_topn for one symbol whose 20-day GTGD is `x`.
    tv_desc: session tvma20 (> 0) of the known cross-section, descending.
    Returns True / False when decided under every completion, else None."""
    if isnan(x) or not x > 0:
        return False
    if tv_desc is None:
        return None
    u = int(unknown or 0)
    k = len(tv_desc)
    if k == 0:
        return None if u else False
    m0 = min(int(top_n), k)
    cut_lo = tv_desc[m0 - 1]                       # the missing symbols are absent / small
    m1 = min(int(top_n), k + u)
    cut_hi = math.inf if m1 <= u else tv_desc[m1 - u - 1]   # ... or all above everyone
    if x >= cut_hi:
        return True
    if x < cut_lo:
        return False
    return None


def row_close_adj(row):
    return f32(_num(row.get('AdjClose'))) if row else NAN


def cross_section(U, rows):
    """Session-t cross-section the engine ranks on.
    U['xs']: {sym: [c250, c60, tv_s19, tv_c19]} exported the night before for EVERY
             symbol that can have a valid r12 / r3 / tvma20 at t;
    rows   : {sym: FireAnt row of the session, or None = the symbol has no row for
             the session}. Symbols of U['xs'] absent from `rows` are UNKNOWN (fetch
             failed) -> the ranks and the cut become bounds (see evaluate)."""
    xs = (U or {}).get('xs')
    if not xs:
        return None
    r12, r3, tv = [], [], []
    unknown = []
    for s, e in xs.items():
        if s not in rows:
            unknown.append(s)
            continue
        r = rows[s] or {}
        ac = row_close_adj(r)
        a = ret32(ac, _num(e[0]))
        b = ret32(ac, _num(e[1]))
        m = mean20(e[2], e[3], f32(_num(r.get('TotalValue'))))
        if not isnan(a):
            r12.append(a)
        if not isnan(b):
            r3.append(b)
        if not isnan(m) and m > 0:
            tv.append(m)
    r12.sort(); r3.sort(); tv.sort(reverse=True)
    return dict(r12=r12, r3=r3, tv=tv, unknown=len(unknown), unknown_syms=sorted(unknown)[:50],
                n_xs=len(xs), top_n=U.get('top_n'))


def ordimb_of(row):
    bq, bc = _num(row.get('BuyQuantity')), _num(row.get('BuyCount'))
    sq, sc = _num(row.get('SellQuantity')), _num(row.get('SellCount'))
    if not (bq > 0 and bc > 0 and sq > 0 and sc > 0):
        return None
    return (bq / bc) / (sq / sc)


def ordimb32(row):
    """engine fa_ind: (BQ / BC) / (SQ / SC) on float32, zero counts -> NaN."""
    bq, bc = f32(_num(row.get('BuyQuantity'))), f32(_num(row.get('BuyCount')))
    sq, sc = f32(_num(row.get('SellQuantity'))), f32(_num(row.get('SellCount')))
    bavg = div32(bq, pos_or_nan(bc))
    savg = div32(sq, pos_or_nan(sc))
    return div32(bavg, pos_or_nan(savg))


def _nanmax(*xs):
    v = [x for x in xs if not isnan(x)]
    return max(v) if v else NAN


def _score(pts_static, N, S, L, I, mom):
    """engine canslim_score() total: integer points, then + Mom as float32."""
    ints = sum(int(pts_static.get(k, 0)) for k in ('C1', 'C2', 'C3', 'A1', 'A2')) + N + S + L + I
    if isnan(mom):
        return float(ints), 0.0
    mp = round32(mul32(5.0, mom), 1)
    return add32(float(ints), mp), mp


def evaluate(sp, row, U, cfg, X=None):
    """sp  : per-symbol spec exported for this session (spec_export.export)
    row : FireAnt HistoricalQuotes row of the session (raw prices, VND)
    U   : universe-level spec (U['xs'] cross-section history, top_n)
    cfg : PROD thresholds (thresholds.json['cfg'])
    X   : cross_section(U, rows_of_the_session); None -> RS / Mom / TOP-N unknown
    Returns dict with values, ok (True / False / None = undetermined), passed,
    missing, undetermined, required, all_ok."""
    req = required_conditions(cfg)
    close = f32(_num(row.get('PriceClose')))
    basic = f32(_num(row.get('PriceBasic')))
    if isnan(close) or isnan(basic) or close <= 0 or basic <= 0:
        return dict(valid=False, all_ok=False, passed=[], missing=['data'], undetermined=[],
                    required=req, values={}, ok={})
    # Adjusted OHLC drive everything compared with adjusted history (range, 52w
    # high, RS, momentum), raw prices the % change — exactly the engine's matrices.
    ac, ah, al = f32(_num(row.get('AdjClose'))), f32(_num(row.get('AdjHigh'))), f32(_num(row.get('AdjLow')))
    vol, tv = f32(_num(row.get('Volume'))), f32(_num(row.get('TotalValue')))
    mc = f32(_num(row.get('MarketCap')))
    v, ok = {}, {}
    pct = ret32(close, basic)
    v['pct'] = pct
    ok['pct'] = (not isnan(pct)) and pct >= f32(sp['thr'])
    vma = mean20(sp.get('vol_s19'), sp.get('vol_c19'), vol)
    volr = div32(vol, pos_or_nan(vma))
    v['volr'] = None if isnan(volr) else volr
    ok['vol'] = ge32(volr, cfg['vol_floor'])
    ok['gtgd'] = ge32(tv, cfg['gtgd_min'])
    rng = div32(sub32(ah, al), pos_or_nan(ac))
    volat = mean20(sp.get('rng_s19'), sp.get('rng_c19'), rng)
    v['volat'] = None if isnan(volat) else volat
    ok['volat'] = ge32(volat, cfg['volat_min'])
    v['mcap'] = None if isnan(mc) else mc
    ok['mcap'] = gt32(mc, cfg['min_mktcap'])
    nb = int(sp.get('nbars_prev') or 0) + (0 if isnan(ac) else 1)
    v['nbars'] = nb
    ok['hist'] = nb >= cfg['min_history']
    ok['base'] = le32(_num(sp.get('base')), cfg['base_range'])
    tvma = mean20(sp.get('tv_s19'), sp.get('tv_c19'), tv)
    v['tvma20'] = None if isnan(tvma) else tvma
    if not cfg.get('use_top_liquid', True):
        ok['uni'] = True
    else:
        ok['uni'] = topn_bounds(tvma, None if X is None else X['tv'], None if X is None else X['unknown'],
                                cfg.get('top_n') or (X or {}).get('top_n') or (U or {}).get('top_n'))
    mid = f32(add32(ah, al) / 2) if not isnan(add32(ah, al)) else NAN
    ok['cond8'] = not (ac < mid)                   # engine skips only when AC < mid (NaN passes)
    oi = ordimb32(row)
    v['ordimb'] = None if isnan(oi) else oi
    v['ordimb_available'] = ordimb_of(row) is not None
    ok['ordimb'] = ge32(oi, cfg['ordimb_min'])
    ok['risk'] = not sp.get('blocked')
    npg = sp.get('npat_yoy')
    ok['dk5'] = not (npg is not None and cfg.get('dk5_lo', 0.0) <= npg < cfg.get('dk5_hi', 0.25))
    # ---- CANSLIM score with today's values (engine.canslim_score) ----
    p = dict(sp.get('pts_static') or {})
    hi52 = _nanmax(_num(sp.get('hi52_249')), ah)
    nh = ret32(ac, hi52) if (not isnan(hi52) and hi52 > 0) else NAN
    N = 10 if (not isnan(nh) and nh >= -0.15) else 0
    S = 5 if (not isnan(volr) and volr >= 1.2) else 0
    I = 10 if (not isnan(tvma) and tvma >= 15e9) else 0
    r12 = ret32(ac, _num(sp.get('c250')))
    r3 = ret32(ac, _num(sp.get('c60')))
    X_r12 = None if X is None else X['r12']
    X_r3 = None if X is None else X['r3']
    u = 0 if X is None else X['unknown']
    rs_lo, rs_hi = (mul32(q, 100.0) for q in rank_bounds(r12, X_r12, u))
    mo_lo, mo_hi = rank_bounds(r3, X_r3, u)
    L_lo = 15 if rs_lo >= 70 else 0
    L_hi = 15 if rs_hi >= 70 else 0
    sc_lo, mp_lo = _score(p, N, S, L_lo, I, mo_lo)
    sc_hi, mp_hi = _score(p, N, S, L_hi, I, mo_hi)
    p.update(N=N, S=S, L=L_lo, I=I, Mom=mp_lo)
    exact = (sc_lo == sc_hi and L_lo == L_hi)
    v.update(score=sc_lo, score_hi=sc_hi, pts=p, rs=rs_lo, rs_hi=rs_hi, mom=mo_lo, mom_hi=mo_hi,
             r12=None if isnan(r12) else r12, r3=None if isnan(r3) else r3,
             near_high=None if isnan(nh) else nh, hi52=None if isnan(hi52) else hi52,
             xsec=('none' if X is None else ('complete' if not X['unknown'] else 'partial')),
             xsec_unknown=(None if X is None else X['unknown']), exact_rank=exact)
    floor = cfg['score_floor']
    ok['score'] = True if sc_lo >= floor else (False if sc_hi < floor else None)
    passed = [k for k in req if ok.get(k) is True]
    missing = [k for k in req if ok.get(k) is not True]
    und = [k for k in req if ok.get(k) is None]
    return dict(valid=True, all_ok=not missing, passed=passed, missing=missing, undetermined=und,
                required=req, values=v, ok=ok)


def classify(res, cfg, frac=1.0, volr_proj=None):
    """Signal level from evaluate(). MUA only when EVERY required production
    condition is satisfied with real data. Missing order-flow data, or a session
    cross-section too incomplete to decide RS / Mom / TOP-N, is never MUA."""
    if not res.get('valid'):
        return None, 'NO_DATA'
    miss = set(res['missing'])
    if not miss:
        return 'MUA', None
    und = set(res.get('undetermined') or [])
    flow_wait = not res['values'].get('ordimb_available')
    if und and miss <= (und | ({'ordimb'} if flow_wait else set())):
        return 'SAP_DU', 'CROSS_SECTION_INCOMPLETE'
    if miss == {'ordimb'} and flow_wait:
        return 'SAP_DU', 'WAITING_FOR_FLOW_CONFIRMATION'
    static = {'risk', 'dk5', 'base', 'hist', 'mcap'}
    if miss & static:
        return None, 'NOT_ELIGIBLE'
    intraday = {'pct', 'vol', 'gtgd', 'volat', 'uni', 'cond8', 'score'}
    if len(miss & intraday) <= 1 and (miss - intraday) <= {'ordimb'}:
        return 'SAP_DU', 'NEAR'
    return 'THEO_DOI', 'PARTIAL'
