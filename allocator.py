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
                size_map={'XANH': 1.0, 'VANG': 0.6, 'CAM': 0.35, 'DO': 0.2},
                # PROD tu 10/11/2026 (anh Son chot 08/11, R49b): lenh thu 3 x0,5 + doi ngua
                nth_mul=None, rot_mode=None, rot_short=0.5, rot_per_day=1, sell_from=3,
                fee_sell=0.0, slip_sell=0.0)

REASON_VI = {'theoretical': 'cỡ lý thuyết', 'max_pos': 'trần mỗi mã',
             'max_total': 'trần tổng vốn', 'sector_cap': 'trần ngành',
             'cash': 'tiền mặt', 'max_pos_n': 'đủ số mã', 'min_size': 'dưới cỡ tối thiểu',
             'light': 'đèn chặn', 'liquidity': 'thanh khoản',
             'max_unconf': 'đang có lệnh dò chưa xác nhận ĐK9',
             'nth_mul': 'lệnh thứ 3 ×0,5 (đang cầm từ 2 mã)'}


def probe_hanging(p, sell_from=3, days_ahead=0):
    """Lenh do 'treo' (luat max_unconf, 03/10/2026): DA truot DK9 nhung chua toi phien ban duoc.
    p: dict co 'probe_fail' va 'held' (so phien da giu tinh toi phien cua p). days_ahead=1 khi
    p lay tu so cua phien TRUOC (vd live_scan doc book toi qua) va dang xet phien hom nay:
    lenh toi phien ban (held+days_ahead >= sell_from) se ban ATC chinh phien do -> khong con treo."""
    return bool(p.get('probe_fail')) and (int(p.get('held') or 0) + int(days_ahead)) < int(sell_from or 2)


def unconf_blocked(n_hanging, cfg=None):
    """True = da du so lenh do treo cho phep -> khong mo lenh do moi. Khong co max_unconf -> False."""
    lim = (cfg or {}).get('max_unconf')
    return lim is not None and int(n_hanging) >= int(lim)


def _hang(vals, syms):
    """Hang phan tram trong tap (0 = kem nhat, 1 = tot nhat) — y het engine2._pr(higher_better=True).
    Bang nhau: engine giu thu tu ung vien = thu tu ma (fa.npz xep theo ma) -> o day xep theo ma."""
    n = len(vals)
    if n <= 1:
        return [1.0] * n
    order = sorted(range(n), key=lambda k: (vals[k], syms[k]))
    out = [0.0] * n
    for r, k in enumerate(order):
        out[k] = r / (n - 1)
    return out


def xep_uu_tien(rows, cfg=None):
    """THU TU UU TIEN khi nhieu ma cung no trong mot phien (R38, PROD tu 22/10/2026).
    rows: list dict co 'sym', 'score', 'volr'. Tra ve list MOI da xep, moi dict them 'uu_tien' (1 = vao truoc).
    rank_mode 'score_volr' = hang(diem) + hang(Vol/TB20) trong chinh tap ung vien, hoa -> ma — cung cong thuc
    engine2.rank_rows. 'score' (PROD cu) = diem giam dan, hoa -> ma. Dung chung cho live_scan va so ghi tien."""
    rows = [dict(r) for r in (rows or [])]
    mode = (cfg or {}).get('rank_mode') or 'score'
    sc = [float(_num(r.get('score')) or 0.0) for r in rows]
    if mode == 'score_volr':
        vr = [float(_num(r.get('volr')) or 0.0) for r in rows]
        sy = [str(r.get('sym')) for r in rows]
        a, b = _hang(sc, sy), _hang(vr, sy)
        idx = sorted(range(len(rows)), key=lambda k: (-(a[k] + b[k]), str(rows[k].get('sym'))))
    else:
        idx = sorted(range(len(rows)), key=lambda k: (-sc[k], str(rows[k].get('sym'))))
    out = [rows[k] for k in idx]
    for n, r in enumerate(out, 1):
        r['uu_tien'] = n
    return out


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
    # LENH THU 3 x0,5 (PROD tu 10/11/2026): dang cam >= nth_mul[0] ma -> lenh moi x nth_mul[1].
    # n_open = so ma dang cam. engine2 tu nhan he so nay vao light_mul (co ngay hieu luc) va goi
    # voi n_open=0, nen khong bi nhan hai lan; so ghi tien + chuong (repo public) goi voi so ma that.
    nm = C.get('nth_mul')
    if nm and int(n_open or 0) >= int(nm[0]):
        theo *= float(nm[1])
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


# ---------------------------------------------------------------------------
# DOI NGUA (PROD tu phien 10/11/2026, anh Son chot 08/11, R49b 'A_duoi5') — MOT dinh nghia
# cho engine2 (backtest) va chuong 14:25 / so ghi tien (repo public).
# ---------------------------------------------------------------------------
def can_doi_ngua(A, invested, nav, cfg=None):
    """True = tin hieu moi bi kep vi day von: tong da cham tran, hoac cai tran dang chan la
    tran tong / tien mat VA chi vao duoc < rot_short x co ly thuyet."""
    C = cfg_of(cfg)
    if not C.get('rot_mode') or not nav:
        return False
    if float(invested or 0) / float(nav) >= float(C['max_total']):
        return True
    return A.get('binding') in ('max_total', 'cash') and \
        float(A.get('actual') or 0) < float(C['rot_short']) * float(A.get('theoretical') or 0)


def chon_doi_ngua(positions, cfg=None, bo=()):
    """Chon ma de BAN nhuong von. positions: list dict co sym, gain (lai sau phi ban, so thap phan),
    held (so phien da giu), stage (0/2 = da xac nhan; 1 = lenh do cho xac nhan; 3 = lenh do truot),
    hard (lenh Hard -> khong dung toi). Tra ve dict cua ma duoc chon hoac None.
    rot_mode: 'duoi5' = lai < 5%; 'lo' = dang lo (<= 0); 'bat_ky' = bat ky. Lai thap nhat duoc chon."""
    C = cfg_of(cfg)
    m = C.get('rot_mode')
    if not m:
        return None
    el = [p for p in positions if p.get('sym') not in set(bo)
          and int(p.get('stage') or 0) in (0, 2) and not p.get('hard')
          and int(p.get('held') or 0) >= int(C.get('sell_from') or 2) and p.get('gain') is not None]
    if m == 'lo':
        el = [p for p in el if float(p['gain']) <= 0]
    elif m == 'duoi5':
        el = [p for p in el if float(p['gain']) < 0.05]
    if not el:
        return None
    return min(el, key=lambda p: (float(p['gain']), p['sym']))
