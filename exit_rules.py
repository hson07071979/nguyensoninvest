# -*- coding: utf-8 -*-
"""EXIT RULES — the ONE written definition of the production exit chain outside the
numpy backtest loop (26/09/2026, anh Son approved TOP110 + S1).

Used by:
  * engine2.py      -> profit_floor() / lock_reason() for the S1 profit lock
  * produce2.py     -> status() for every open position exported to the website
  * portfolio.py    -> decide() for the paper book (copied verbatim by publish.py)
  * live_scan.py    -> decide() for the in-session ATC exit alert
  * tests           -> parity: decide() replays every engine2 deal and must reproduce
                       the engine's exit day AND reason (tests/test_regressions.py)
The website (site/p15.js) re-implements the same chain in JS; tests/test_exit_js.py runs
the JS through node on a fixture grid and requires identical decisions.

Definitions (identical everywhere, = engine2 convention, research R21):
  gain  = AdjClose(t) / (AdjClose(entry) x (1 + fee_buy)) - 1      daily CLOSE, buy fee included
  peak  = max(gain) over every close since the entry, INCLUDING T+1..T+(sell_from-1)
  A rule is only EXECUTED from held >= sell_from (T+3), at the close (ATC). A floor that is
  breached before T+3 is a PENDING breach: it is sold at the T+3 close only if the T+3 close is
  still at or below the floor. There is NO intraday stop — a stock that gaps through the floor
  in one session is sold at that session's close, wherever it is.

S1 profit lock (cfg['profit_lock'] = [[0.08, 0.02], [0.12, 0.06], [0.15, 0.08]] since 30/09/2026 — chosen after
R32/R33 Monte Carlo per year; 26-29/09 [[0.08,0.02],[0.12,0.05]]; 29/09 one night [[0.08,0.04],[0.10,0.05],[0.12,0.06]]):
  peak >= 8% -> floor +2%;  peak >= 12% -> floor +6%;  peak >= 15% -> floor +8%.
  The highest reached tier wins.  sell if gain <= floor.
  No 15% / 19% tiers. MA10 (peak >= big_win) stays the large-winner trend exit.

Pure python, standard library only.
"""

RULES_VERSION = 1

R_PROBE = 'Cond9 không xác nhận — bán lệnh thăm dò'
R_HARD = 'Hard stop −10%'
R_STOP = 'Cắt lỗ −7%'


def _pct(x, nd=0):
    s = ('%.' + str(nd) + 'f') % (x * 100)
    return s.replace('.', ',')


def tiers(C):
    """[(trigger, floor), ...] sorted by trigger, from cfg['profit_lock'] (None -> [])."""
    t = C.get('profit_lock') if isinstance(C, dict) else C
    out = []
    for x in (t or []):
        a, b = float(x[0]), float(x[1])
        out.append((a, b))
    return sorted(out)


def profit_floor(peak, lock):
    """Highest applicable tier for this peak: (trigger, floor) or (None, None).
    `lock` = cfg dict or tier list. Boundaries are inclusive (peak >= trigger)."""
    best = (None, None)
    for a, b in tiers(lock):
        if peak >= a - 1e-12 and (best[1] is None or b > best[1]):
            best = (a, b)
    return best


def lock_reason(trigger, floor):
    return 'Khoá lãi S1 (đỉnh ≥%s%% → sàn +%s%%)' % (_pct(trigger), _pct(floor))


def is_lock_reason(r):
    return str(r or '').startswith('Khoá lãi S1')


def decide(C, gain, peak, held, probe_fail=False, b10=0, b20=0, light_today=None,
           light_entry=None, part=False):
    """Production exit chain for ONE position on ONE close. Mirrors engine2 order:
        0 failed probe (Cond9)          -> sell at the first sellable close
        1 hard stop  gain <= -10%       (from hs_from = sell_from)
        2 momentum   held >= mo_by and peak < mo_need
        3 stop       held >= 3 and gain <= -7%
        4 [legacy breakeven, only if use_be — OFF in PROD since 26/09]
        5 S1 profit lock
        6 time valve held >= t_valve and gain <= valve_min
        7 MA10       peak >= big_win and b10 >= conf
        8 MA30       b20 >= conf
        9 Cam light  sell 1/3 when light worsens to CAM (partial)
    Returns dict(rule, phan, sellable, pending, floor, trigger, lock_active, sell_from).
    `rule` is the engine reason string when a sale is EXECUTABLE now; when the position is
    not yet sellable, `pending` names the rule that is currently breached (if any)."""
    # Gia tri null trong cfg (thresholds.json ghi PROD.get(k) = None cho nut khong dung, vd
    # mo_window) = DUNG MAC DINH, giong erG() cua ban JS. Truoc 28/09 live_scan truyen thang
    # cfg co None -> 'int <= None' -> chuong luat thoat trong phien hong tu 24/09.
    if isinstance(C, dict):
        C = {k: v for k, v in C.items() if v is not None}
    sf = int(C.get('sell_from', 2) or 2)
    hs_from = int(C.get('hs_from', sf) or sf)
    trig, floor = profit_floor(peak, C)
    out = dict(rule=None, phan=1.0, sellable=held >= sf, pending=None, floor=floor, trigger=trig,
               lock_active=floor is not None, sell_from=sf, held=held, gain=gain, peak=peak)

    def chain(ignore_held):
        h = held if not ignore_held else max(held, sf)
        if probe_fail:
            return R_PROBE, 1.0
        if C.get('use_hard_stop', True) and gain <= C.get('hard_stop', -0.10) and h >= hs_from:
            return R_HARD, 1.0
        if (C.get('mo_by') and C['mo_by'] <= h <= C.get('mo_window', 99) and peak < C.get('mo_need', 0.0)):
            return 'Momentum: không chạy (T+%d chưa lên %.0f%%)' % (C['mo_by'], C['mo_need'] * 100), 1.0
        if h >= 3 and gain <= C.get('stop', -0.07):
            return R_STOP, 1.0
        if C.get('use_be') and peak >= C.get('be_trigger', 0.08) and gain <= C.get('be_level', 0.01):
            return 'Về bờ (đã lãi %d%%)' % int(C.get('be_trigger', 0.08) * 100), 1.0
        if floor is not None and gain <= floor:
            return lock_reason(trig, floor), 1.0
        if h >= C.get('t_valve', 4) and gain <= C.get('valve_min', 0.0):
            return 'Van thời gian T+%d' % C.get('t_valve', 4), 1.0
        if peak >= C.get('big_win', 0.19) and b10 >= C.get('conf', 2):
            return 'Trailing MA%d (lãi lớn)' % C.get('trail_fast', 10), 1.0
        if b20 >= C.get('conf', 2):
            return 'Trailing MA%d' % C.get('trail_ma', 30), 1.0
        if (C.get('use_orange_cut', False) and light_today == 'CAM' and not part
                and (not C.get('orange_cut_only_if_worse', True) or light_entry in ('XANH', 'VANG'))):
            return 'Đèn Cam — hạ 1/3', 1.0 / 3
        return None, 1.0

    if held >= sf or (C.get('use_hard_stop', True) and gain <= C.get('hard_stop', -0.10) and held >= hs_from):
        out['rule'], out['phan'] = chain(False)
    else:
        # not sellable yet: which rule WOULD fire at the first sellable close if nothing changed?
        r, _ = chain(True)
        # time-based rules that only mature at T+mo_by / T+t_valve are not "breaches" yet
        if r and not r.startswith('Momentum') and not r.startswith('Van thời gian'):
            out['pending'] = r
    return out


def action_text(d):
    """One line for the website / Telegram, from a decide() result."""
    g, pk, fl = d.get('gain'), d.get('peak'), d.get('floor')
    r = d.get('rule'); pend = d.get('pending'); sf = d.get('sell_from', 3)
    if r and is_lock_reason(r):
        return 'BÁN ATC — KHOÁ LÃI: từng đạt +%s%%, hiện còn %s%s%%, sàn bảo vệ +%s%%' % (
            _pct(pk, 1), '+' if g >= 0 else '', _pct(g, 1), _pct(fl))
    if r:
        return ('HẠ 1/3 ATC — ' if d.get('phan', 1) < 1 else 'BÁN ATC — ') + r
    if pend and is_lock_reason(pend):
        con = max(0, sf - int(d.get('held') or 0))
        return ('CHỜ T+%d — KHOÁ LÃI ĐÃ THỦNG: từng đạt +%s%%, hiện %s%s%% ≤ sàn +%s%%; chưa bán được '
                '(còn %d phiên) — bán ATC T+%d nếu đóng cửa vẫn ≤ sàn') % (
            sf, _pct(pk, 1), '+' if g >= 0 else '', _pct(g, 1), _pct(fl), con, sf)
    if pend:
        return 'CHỜ T+%d — %s (chưa bán được, xét lại ATC T+%d)' % (sf, pend, sf)
    if d.get('lock_active'):
        return 'GIỮ — khoá lãi đang bật: đỉnh +%s%%, sàn bảo vệ +%s%% (hiện %s%s%%)' % (
            _pct(pk, 1), _pct(fl), '+' if g >= 0 else '', _pct(g, 1))
    return 'GIỮ'


def status(C, gain, peak, held, **kw):
    """decide() + the flat fields exported on every open position (portfolio.json,
    thresholds.json open_positions, live.json)."""
    d = decide(C, gain, peak, held, **kw)
    return dict(peak_gain=round(peak * 100, 2), gain=round(gain * 100, 2),
                profit_lock_active=d['lock_active'],
                profit_floor=(None if d['floor'] is None else round(d['floor'] * 100, 2)),
                profit_trigger=(None if d['trigger'] is None else round(d['trigger'] * 100, 2)),
                sellable=d['sellable'], exit_reason=d['rule'], pending_exit=d['pending'],
                exit_phan=round(d['phan'], 4), action=action_text(d))


# =============================================================================
# KẾ HOẠCH BÁN CHO PHIÊN KẾ TIẾP (03/10/2026, anh Sơn: "mỗi ngày mỗi mã đang cầm phải có
# việc cụ thể — giá bao nhiêu thì bán"). KHÔNG thêm luật mới: chỉ hỏi decide() ở trên với
# từng mức giá đóng cửa giả định của phiên tới, rồi tìm mức giá CAO NHẤT mà luật thoát
# đã bật -> "đóng cửa ≤ X thì BÁN HẾT ATC". Các luật vẫn tính bằng giá ĐÓNG CỬA.
# Đơn vị giá: giá ĐIỀU CHỈNH cùng thang với cost (giá vốn đã gồm phí mua, như engine2).
# =============================================================================
def _ban_tai(C, cost, peak, held, prev, b10, b20, c, probe_fail=False, part=False):
    gain = c / cost - 1
    pk = max(float(peak), gain)
    nf, ns = int(C.get('trail_fast', 10)), int(C.get('trail_ma', 30))
    seq = list(prev) + [c]
    m10 = sum(seq[-nf:]) / nf if len(seq) >= nf else None
    m30 = sum(seq[-ns:]) / ns if len(seq) >= ns else None
    nb10 = b10 + 1 if (m10 is not None and c < m10) else 0
    nb20 = b20 + 1 if (m30 is not None and c < m30) else 0
    return decide(C, gain, pk, held, probe_fail=probe_fail, b10=nb10, b20=nb20, part=part)


def buoc_gia(px):
    """Bước giá HOSE (đ): <10.000 -> 10; <50.000 -> 50; còn lại 100."""
    return 10 if px < 10000 else (50 if px < 50000 else 100)


def ke_hoach_ban(C, cost, peak, held_next, prev_closes, b10=0, b20=0, probe_fail=False, part=False, fx=1.0):
    """Kế hoạch cho phiên tới của MỘT vị thế.
    cost: giá vốn (đ/cp, đã gồm phí mua, thang điều chỉnh); peak: đỉnh lãi theo giá đóng cửa
    tới phiên gần nhất (phân số); held_next: số phiên đã giữ TÍNH CẢ phiên tới; prev_closes:
    giá đóng cửa điều chỉnh các phiên trước (cũ -> mới, >= 30 phiên nếu có); b10/b20: số phiên
    liên tiếp đóng dưới MA10/MA30 tới phiên gần nhất.
    Trả về dict:
      viec: 'BAN' (bán ATC bất kể giá) | 'NGUONG' (bán nếu đóng cửa <= nguong) | 'CHUA_BAN_DUOC' | 'GIU'
      nguong: giá đóng cửa cao nhất vẫn kích hoạt luật bán (None nếu không có)
      ly_do: luật sẽ bật ở ngay dưới ngưỡng
      moc: các mốc tham khảo {khoa_lai, cat_lo, ma10, ma30, momentum}
    """
    if isinstance(C, dict):
        C = {k: v for k, v in C.items() if v is not None}
    prev = [float(x) for x in prev_closes if x == x]
    sf = int(C.get('sell_from', 2) or 2)
    f = lambda c: _ban_tai(C, cost, peak, held_next, prev, b10, b20, c, probe_fail, part)
    hi, lo = cost * 3.0, cost * 0.3
    out = dict(viec='GIU', nguong=None, ly_do=None, held=int(held_next), sell_from=sf, moc={})
    d_hi = f(hi)
    if d_hi.get('rule'):
        out.update(viec='BAN', ly_do=d_hi['rule'])
    elif not f(lo).get('rule'):
        out['viec'] = 'CHUA_BAN_DUOC' if held_next < sf else 'GIU'
        if probe_fail:
            out['ly_do'] = R_PROBE
    else:
        a, b = lo, hi          # f(a) ban, f(b) giu
        for _ in range(60):
            m = (a + b) / 2
            if f(m).get('rule'): a = m
            else: b = m
            if b - a < cost * 1e-6: break
        out.update(viec='NGUONG', nguong=a, ly_do=f(a)['rule'])
        # ngưỡng theo GIÁ THỰC (fx = giá thô / giá điều chỉnh hôm nay), làm tròn theo bước giá:
        # mức cao nhất trên lưới bước giá mà luật vẫn bật.
        raw = a * fx; t = buoc_gia(raw)
        up = (int(raw // t) + 1) * t
        out['nguong_raw'] = up if f(up / fx).get('rule') else int(raw // t) * t
    # moc tham khao (chi de hien, quyet dinh van la decide() o tren)
    trig, floor = profit_floor(peak, C)
    if floor is not None: out['moc']['khoa_lai'] = cost * (1 + floor)
    out['moc']['cat_lo'] = cost * (1 + C.get('stop', -0.07))
    nf, ns = int(C.get('trail_fast', 10)), int(C.get('trail_ma', 30))
    if len(prev) >= nf - 1: out['moc']['ma10'] = sum(prev[-(nf - 1):]) / (nf - 1)
    if len(prev) >= ns - 1: out['moc']['ma30'] = sum(prev[-(ns - 1):]) / (ns - 1)
    if C.get('mo_by') and peak < C.get('mo_need', 0.0) and held_next <= C.get('mo_window', 99):
        out['moc']['momentum'] = cost * (1 + C.get('mo_need', 0.0))
    out['b10'], out['b20'], out['peak'] = int(b10), int(b20), float(peak)
    return out
