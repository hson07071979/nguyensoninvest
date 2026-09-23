# -*- coding: utf-8 -*-
"""SHARED PORTFOLIO ALLOCATOR — one sizing rule for every layer.

Used by:
  engine2.run()        backtest entries AND pyramid add-ons
  vithe.py             site / lookup / alerts explanation (wraps this)
  portfolio.py         paper book in the public repo (publish.py copies this
                       file next to it, so the formula is byte-identical)

Pure python, no numpy, so it can be copied to the runtime repo as-is.

Entry rule (unchanged from engine2 before 2026-09-23):
    theoretical = nav * base_size * light_mul * risk_mul * base_bonus
    actual      = min(theoretical,
                      nav * max_pos      - existing value of this symbol,
                      nav * max_total    - total invested,
                      nav * sector_cap   - invested in this sector,
                      cash available)
    actual < nav * min_size  -> no entry
    open positions >= max_pos_n -> no entry
Every binding constraint is reported in `reasons`, so an alert can say WHY
a signal gets less than the theoretical size.
"""

SECTOR_CAP = 0.30
DEFAULTS = dict(base_size=0.42, max_pos=0.50, max_total=1.0, max_pos_n=12,
                min_size=0.02, sector_cap=SECTOR_CAP, base_bonus_range=0.10,
                base_bonus=1.2,
                size_map={'XANH': 1.0, 'VANG': 0.6, 'CAM': 0.35, 'DO': 0.2})

REASON_VI = {'theoretical': 'cỡ lý thuyết', 'max_pos': 'trần mỗi mã',
             'max_total': 'trần tổng vốn', 'sector_cap': 'trần ngành',
             'cash': 'tiền mặt', 'max_pos_n': 'đủ số mã', 'min_size': 'dưới cỡ tối thiểu',
             'light': 'đèn chặn', 'liquidity': 'thanh khoản'}


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def cfg_of(cfg=None):
    C = dict(DEFAULTS)
    for k, v in (cfg or {}).items():
        if k in C:
            C[k] = v
    if cfg and cfg.get('max_sector') is not None:
        C['sector_cap'] = cfg['max_sector']
    return C


def entry_target(nav, cash, invested, sector_invested, n_open, light,
                 risk_mul=1.0, base_rng=None, cfg=None, sym_invested=0.0,
                 liquidity_cap=None, light_mul=None):
    """Return dict(theoretical, actual, ok, binding, reasons).

    All money arguments are in the same currency unit (VND). `light_mul`
    overrides the size_map lookup (engine2 passes its regime multiplier,
    which already includes circuit-breaker cuts)."""
    C = cfg_of(cfg)
    nav = _num(nav) or 0.0
    if light_mul is None:
        light_mul = float(C['size_map'].get(light, 0.0))
    risk_mul = 1.0 if risk_mul is None else float(risk_mul)
    bonus = C['base_bonus'] if (base_rng is not None and base_rng <= C['base_bonus_range']) else 1.0
    theo = nav * C['base_size'] * light_mul * risk_mul * bonus
    cand = [('theoretical', theo), ('max_pos', nav * C['max_pos'] - (sym_invested or 0.0))]
    inv = _num(invested)
    if inv is not None:
        cand.append(('max_total', nav * C['max_total'] - inv))
    sec = _num(sector_invested)
    if sec is not None:
        cand.append(('sector_cap', nav * C['sector_cap'] - sec))
    c = _num(cash)
    if c is not None:
        cand.append(('cash', c))
    if liquidity_cap is not None:
        cand.append(('liquidity', float(liquidity_cap)))
    binding, actual = min(cand, key=lambda t: t[1])
    reasons = [k for k, v in cand[1:] if v < theo - 1e-6]
    ok = True
    if light_mul <= 0:
        ok, actual, binding = False, 0.0, 'light'
    elif n_open >= C['max_pos_n']:
        ok, actual, binding = False, 0.0, 'max_pos_n'
    elif actual < nav * C['min_size']:
        ok, binding = False, ('min_size' if binding == 'theoretical' else binding)
        actual = 0.0
    return dict(theoretical=theo, actual=max(0.0, actual), ok=ok,
                binding=binding, reasons=reasons,
                light_mul=light_mul, risk_mul=risk_mul, base_bonus=bonus)


def addon_capacity(nav, cash, invested, sector_invested, sym_value, cfg=None):
    """Money that may be ADDED to an existing position (pyramid) without
    breaching max_pos, max_total, sector_cap or cash."""
    C = cfg_of(cfg)
    cand = [('max_pos', nav * C['max_pos'] - sym_value)]
    inv = _num(invested)
    if inv is not None:
        cand.append(('max_total', nav * C['max_total'] - inv))
    sec = _num(sector_invested)
    if sec is not None:
        cand.append(('sector_cap', nav * C['sector_cap'] - sec))
    c = _num(cash)
    if c is not None:
        cand.append(('cash', c))
    k, v = min(cand, key=lambda t: t[1])
    return max(0.0, v), k


def lots(value, px_all_in, lot=100):
    """Shares affordable for `value` at all-in price, rounded DOWN to a lot."""
    if not px_all_in or px_all_in <= 0 or value <= 0:
        return 0
    return int(value / px_all_in // lot * lot)
