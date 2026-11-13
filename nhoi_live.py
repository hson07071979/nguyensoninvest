# -*- coding: utf-8 -*-
"""CHUONG LENH NHOI TRONG PHIEN (13/11/2026, anh Son: "lenh nhoi cung bao di").

Truoc day lop 9 (pyramid) chi chay o hai noi luc TOI: engine2 (so bo may) va portfolio.py
(so giao dich thuc te) ghi lenh nhoi bang gia DONG CUA. Khach khong duoc bao trong phien nen
khong the dat lenh ATC -> so thuc te co lenh nhoi ma tai khoan khach khong co.

File nay la MOT dinh nghia luat nhoi trong phien, di nguyen van sang repo public (publish.py +
daily.yml) de live_scan.py import; trang web (site/p21.js) chep lai dung cac phep so nay.

Luat = engine2 lop 9 (PROD): phien thu 4-7 sau ngay mua · dang lai >= 10% (gia von da gom phi mua)
· gia >= 99,9% dinh 10 phien (gom ca dinh trong phien hom nay) · den Xanh · chi 1 lan · khong nhoi
cua V / lenh do truot DK9 / vi the da ban mot phan · them 50% so co dang cam (lo 100) · sau nhoi ma
khong vuot max_pos NAV va du tien mat.

Hai cho la XAP XI (anh Son 13/11: "cua V voi den thi cu ang ang di vi gan dung"):
  - bo may xet bang gia DONG CUA; trong phien xet bang gia hien tai -> toi bo may xac nhan lai.
  - den: bo may dung den cua chinh phien do; trong phien dung den toi qua (hoac den tam tinh neu co).
"""

LUAT = dict(pyr_gain=0.10, pyr_win=(4, 7), pyr_frac=0.5, pyr_near=0.999, pyr_lights=('XANH',))


def bang_gia(d, I=None, syms=None):
    """{ma: {'h9': dinh cao nhat 9 phien gan nhat (gia THO, quy ve thang gia phien cuoi, dong)}}.
    Dinh 10 phien cua phien ke tiep = max(h9, gia cao trong phien ke tiep)."""
    import numpy as np
    AH = d['AdjHigh']; AC = d['AdjClose']; PC = d['PriceClose']
    S = [str(x) for x in d['sym']]
    out = {}
    for j, s in enumerate(S):
        if syms is not None and s not in syms:
            continue
        w = AH[-9:, j]
        w = w[~np.isnan(w)]
        ac, pc = AC[-1, j], PC[-1, j]
        if not len(w) or not (ac == ac and ac > 0 and pc == pc and pc > 0):
            continue
        out[s] = dict(h9=round(float(w.max() * pc / ac), 1))
    return out


def xet(vt, gia_now, cao_now, h9, den, nav=None, cash=None, cfg=None, luat=None):
    """Mot vi the co du dieu kien NHOI ngay luc nay khong.

    vt: dict(sym, held_next, gain_last [phan so, sau phi mua, theo gia dong cua phien truoc],
             last_raw [dong, dong cua phien truoc], sh, pyr, door, probe_fail, part, value_now?)
    gia_now / cao_now: gia hien tai / cao nhat trong phien (dong, gia tho).
    -> dict(ok, ly_do[list], can_lai, can_dinh, them_sh, them_pct_nav, them_tien)"""
    L = dict(LUAT, **(luat or {}))
    cfg = cfg or {}
    ly = []
    if vt.get('pyr'):
        ly.append('đã nhồi rồi (chỉ 1 lần)')
    if vt.get('door') == 'V':
        ly.append('cửa V không nhồi')
    if vt.get('probe_fail'):
        ly.append('lệnh dò trượt ĐK9')
    if vt.get('part'):
        ly.append('đã bán một phần')
    h = vt.get('held_next')
    if h is None or not (L['pyr_win'][0] <= h <= L['pyr_win'][1]):
        ly.append(f'phiên thứ {h} (cần {L["pyr_win"][0]}–{L["pyr_win"][1]})')
    if den not in L['pyr_lights']:
        ly.append(f'đèn {den} (cần Xanh)')
    lr = float(vt.get('last_raw') or 0); g0 = vt.get('gain_last')
    can_lai = (lr * (1 + L['pyr_gain']) / (1 + g0)) if (lr > 0 and g0 is not None) else None
    dinh = max(float(h9 or 0), float(cao_now or 0), float(gia_now or 0))
    can_dinh = L['pyr_near'] * dinh if dinh > 0 else None
    if can_lai is None or not gia_now:
        ly.append('thiếu giá')
    else:
        if gia_now < can_lai - 1e-6:
            ly.append(f'lãi chưa đủ 10% (cần giá ≥ {can_lai/1000:.2f})')
        if can_dinh is not None and gia_now < can_dinh - 1e-6:
            ly.append(f'chưa sát đỉnh 10 phiên (cần ≥ {can_dinh/1000:.2f})')
    # co lenh: 50% so co dang cam, lo 100; tran max_pos + tien mat (= engine2 PROD, pyr_caps=False)
    sh = int(vt.get('sh') or 0)
    them = int(sh * L['pyr_frac'] // 100 * 100)
    pct = tien = None
    if gia_now and them >= 100 and nav:
        fee = float(cfg.get('fee_buy', 0.0015))
        mp = float(cfg.get('max_pos', 0.5))
        if (sh + them) * gia_now > nav * mp:
            ly.append(f'sau nhồi vượt {mp*100:.0f}% NAV một mã')
        if cash is not None and them * gia_now * (1 + fee) > cash:
            ly.append('không đủ tiền mặt')
        tien = them * gia_now
        pct = tien / nav * 100
    elif them < 100:
        ly.append('lệnh thêm dưới 100 cổ')
    return dict(ok=not ly, ly_do=ly, can_lai=can_lai, can_dinh=can_dinh, them_sh=them,
                them_pct_nav=(round(pct, 1) if pct is not None else None), them_tien=tien)


def tu_so(p, asof):
    """Vi the trong portfolio.json (so giao dich thuc te) -> dict cho xet(). None neu so chua chot phien `asof`."""
    if p.get('last_done') != asof or not p.get('sh'):
        return None
    return dict(sym=p['sym'], held_next=int(p.get('held') or 0) + 1,
                gain_last=(float(p['gain']) / 100 if p.get('gain') is not None else None),
                last_raw=float(p.get('last') or 0) * 1000, sh=int(p['sh']), pyr=bool(p.get('pyr')),
                door=p.get('door'), probe_fail=bool(p.get('probe_fail')), part=bool(p.get('part')))
