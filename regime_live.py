# -*- coding: utf-8 -*-
"""DEN THI TRUONG TAM TINH TRONG PHIEN (28/09/2026) — mot buoc cua regime2.build_regime.

Bo may tinh den cua phien i bang DONG CUA phien i (regime2). Chuong trong phien truoc day
dung den cua phien hom truoc -> 12% tin hieu co den doi dung phien do (co lenh sai) va luat
"Den Cam — ha 1/3" KHONG BAO GIO bao trong phien.

File nay tach DUNG vong lap cua regime2 thanh ham `step(state, ...)`:
  - toi: `state_from_history` chay step() tu dau lich su (phat lai khop regime2 100%, xem
    tests/test_regime_live.py) va xuat trang thai sau phien cuoi vao thresholds.json;
  - trong phien: live_scan goi step() voi so TAM TINH cua hom nay (loi suat dong trong so
    cua vu tru G1, VN-Index va khoi luong du phong tu DNSE) -> den tam tinh.
Khong doi luat nao. Chi la lam som mot phep tinh ma bo may van lam luc toi.
"""
import math

HIST_G1 = 199      # g1ma[i] = mean(g1[i-199 : i+1]) -> can 199 gia tri truoc + hom nay
HIST_VC = 49       # vma50[i] = nanmean(vc[i-49 : i+1])


def _mean(xs):
    xs = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return sum(xs) / len(xs) if xs else float('nan')


def empty_state(cfg):
    return dict(g1=1000.0, g1_hist=[], vc_hist=[], vc_prev=None, vv_prev=None, dd=[],
                ftd_on=False, ftd_age=0, day1_low=None, cnt=0,
                ftd_gain=cfg.get('ftd_gain', 0.012), use_ftd=bool(cfg.get('use_ftd', True)))


def step(st, eq_ret, vc, vv):
    """Mot phien, DUNG thu tu cua regime2.build_regime. Tra ve (light, state_moi, info).
    eq_ret: loi suat dong trong so cua vu tru G1 (da chan |r| > 20%); vc/vv: VN-Index dong
    cua / khoi luong phien (trong phien: gia hien tai / KL du phong)."""
    g1 = st['g1'] * (1.0 + (eq_ret or 0.0))
    hist = st['g1_hist'] + [g1]
    g1ma = _mean(hist[-(HIST_G1 + 1):]) if len(hist) >= HIST_G1 + 1 else float('nan')
    red = (not math.isnan(g1ma)) and g1 < g1ma
    vc_prev, vv_prev = st['vc_prev'], st['vv_prev']
    vhist = st['vc_hist'] + [vc]
    vma50 = _mean(vhist[-(HIST_VC + 1):]) if len(vhist) >= HIST_VC + 1 else float('nan')
    # ---- ngay phan phoi (tuoi = so phien tu ngay do)
    dd = [(a + 1, p) for a, p in st['dd']]
    if vc_prev:
        chg = vc / vc_prev - 1 if vc_prev > 0 else 0.0
        if chg < -0.002 and vv is not None and vv_prev is not None and vv > vv_prev:
            dd.append((0, vc))
    else:
        chg = 0.0
    dd = [(a, p) for a, p in dd if a <= 25 and vc < p * 1.05]
    dcount = len(dd)
    # ---- FTD (vong 1 cua regime2)
    day1_low, cnt, ftd = st['day1_low'], st['cnt'], False
    if vc_prev is not None:
        if not red:
            day1_low, cnt = None, 0
        elif day1_low is None:
            if vc > vc_prev:
                day1_low, cnt = vc * 0.995, 1
        else:
            if vc < day1_low:
                day1_low, cnt = None, 0
            else:
                cnt += 1
                if cnt >= 4 and chg >= st['ftd_gain'] and vv is not None and vv_prev is not None and vv > vv_prev:
                    ftd = True
    # ---- den (vong 2 cua regime2)
    ftd_on, ftd_age = st['ftd_on'], st['ftd_age']
    if not red:
        ftd_on, ftd_age = False, 0
    else:
        if ftd and st['use_ftd']:
            ftd_on, ftd_age = True, 0
        elif ftd_on:
            ftd_age += 1
            if not math.isnan(vma50) and vc < vma50 * 0.97:
                ftd_on = False
    if red and not ftd_on:
        light = 'DO'
    elif dcount >= 5:
        light = 'CAM'
    elif (not math.isnan(vma50) and vc < vma50) or dcount >= 3 or ftd_on:
        light = 'VANG'
    elif math.isnan(g1ma):
        light = 'VANG'
    else:
        light = 'XANH'
    new = dict(st, g1=g1, g1_hist=hist[-HIST_G1:], vc_hist=vhist[-HIST_VC:], vc_prev=vc, vv_prev=vv,
               dd=dd, ftd_on=ftd_on, ftd_age=ftd_age, day1_low=day1_low, cnt=cnt)
    info = dict(g1=round(g1, 3), g1ma=(None if math.isnan(g1ma) else round(g1ma, 3)), red=red,
                vni=vc, vma50=(None if math.isnan(vma50) else round(vma50, 2)), dcount=dcount,
                ftd_on=ftd_on, chg=round(chg, 5), g1_margin=(None if math.isnan(g1ma) else round(g1 / g1ma - 1, 4)))
    return light, new, info


def replay(eq, vc, vv, cfg):
    """Chay step() tu dau lich su. eq[i] = loi suat G1 phien i (eq[0] bo qua)."""
    st = empty_state(cfg); lights = []
    for i in range(len(vc)):
        l, st, _ = step(st, eq[i] if i > 0 else 0.0, float(vc[i]), float(vv[i]))
        lights.append(l)
    return lights, st


def state_for_export(st, session):
    """Trang thai sau phien `session`, gon de nhet vao thresholds.json."""
    o = dict(st); o['session'] = session
    o['dd'] = [[int(a), float(p)] for a, p in st['dd']]
    o['g1_hist'] = [round(float(x), 6) for x in st['g1_hist']]
    o['vc_hist'] = [float(x) for x in st['vc_hist']]
    return o


def state_from_export(o):
    st = dict(o); st.pop('session', None)
    st['dd'] = [(int(a), float(p)) for a, p in (o.get('dd') or [])]
    return st


def g1_return(rows, valid):
    """Loi suat dong trong so cua vu tru G1 tu bang gia trong phien: PriceClose / PriceBasic - 1
    (gia tham chieu da dieu chinh co tuc = AdjClose hom qua), chan |r| > 20% nhu regime2."""
    rs = []
    for s in valid:
        r = rows.get(s)
        if not r:
            continue
        try:
            c, b = float(r.get('PriceClose') or 0), float(r.get('PriceBasic') or 0)
        except Exception:
            continue
        if c > 0 and b > 0:
            x = c / b - 1
            if abs(x) <= 0.20:
                rs.append(x)
    return (sum(rs) / len(rs) if rs else None), len(rs)
