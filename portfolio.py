# -*- coding: utf-8 -*-
"""SO LENH TU DONG (LIVE PAPER BOOK) — book_id = LIVE_PAPER.

Chay ngay sau `live_scan.py`, trong cung workflow. Moi phien mot lan, sau khi
thi truong dong cua (sau 14h50 gio Viet Nam):

  1. Voi moi vi the dang mo, tai lai nen ke tu ngay mua va CHAY LAI bo thoat
     cua engine2 tren tung phien (cung thu tu, cung nguong, cung quy uoc gia).
  2. Doc `live.json`. CHI nhung ma o muc MUA ma `prod_ok` = True (moi dieu kien
     PROD — ke ca Dieu kien 9 dong tien — da duoc chung minh bang du lieu that,
     cung prod_config_hash voi thresholds.json) moi duoc vao so.
  3. Co lenh = allocator.py — DUNG CHUNG voi engine2 (backtest), chuong Telegram
     va trang web. Khong tu go cong thuc o day.
  4. Kim tu thap (pyramid) nhu engine2, qua cung allocator (ton trong tran ma,
     tran tong von, tran nganh, tien mat).
  5. Ghi `portfolio.json` + bang doi soat ke toan (`checks`).

AUDIT 23/09/2026 — da sua:
  * Vao so MUA ma khong co Dieu kien 9 (PVP 22/09: OrdImb 1,381 < 1,40).
  * pnl_vnd bo sot phi mua trong gia von.
  * So gia von THO voi gia DIEU CHINH sau nay -> lai/lo gia sau co tuc/chia tach.
    Nay moi so sanh deu tren cung mot chuoi da dieu chinh.
  * Lai/lo de xet cat lo tinh tren gia von DA GOM phi mua, nhu engine2 (epx).
  * Den Cam ha 1/3 chi khi den XAU DI so voi luc mua (orange_cut_only_if_worse).
  * Them kim tu thap cho khop engine2.
"""
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from live_scan import BASE, H, gio_vn
import allocator as AL
import exit_rules as ER   # luat thoat dung chung voi engine2 / live_scan / trang web (26/09/2026)

FILE = 'portfolio.json'
BOOK_ID = 'LIVE_PAPER'
NAV0 = 1_000_000_000.0
TEN_DEN = {'XANH': 'Xanh', 'VANG': 'Vàng', 'CAM': 'Cam', 'DO': 'Đỏ'}

# Mac dinh = PROD tai 23/09/2026 (25/09: them momentum mo_by/mo_need, doc tu cfg). Gia tri THAT doc tu thresholds.json['cfg']
# (xuat tu produce2.PROD) — xem cfg() ben duoi.
DEF = dict(fee_buy=0.0015, fee_sell=0.0025, hard_stop=-0.10, stop=-0.07,
           be_trigger=0.08, be_level=0.01, use_be=False, profit_lock=None, t_valve=4, big_win=0.19,
           conf=2, trail_fast=10, trail_ma=30, use_orange_cut=True,
           orange_cut_only_if_worse=True, use_pyramid=True, use_hard_stop=True)

# Lenh da vao so theo LUAT CU, nay chung minh la sai luat PROD -> dong mot lan,
# minh bach, co ly do (khong xoa lich su).
VOID = {('PVP', '2026-09-22'): 'Huỷ: vào sổ bằng luật cũ, Điều kiện 9 không đạt (OrdImb 1,381 < 1,40)'}


def cfg(T):
    C = dict(DEF)
    C.update({k: v for k, v in (T.get('cfg') or {}).items() if v is not None})
    bad = [k for k in ('use_protective_candle', 'use_giveback', 'use_big_sell', 'use_partial_take',
                       'cb_enable') if C.get(k)]
    # Mua do (PROD 25/09/2026): chi ho tro mua DU lenh luc ATC (stage1=1.0) va ban lenh do
    # truot DK9 o gia dong cua T+2 (hang ve chieu T+2). Bien the khac se lech bo may.
    if C.get('stage1') is not None and (float(C['stage1']) != 1.0 or C.get('probe_exit', 'open') != 'close'):
        bad.append('stage1/probe_exit')
    # ceil_vol_floor chi doi LOP VAO (engine) — so ghi tien vao theo signals cua engine nen khong anh huong
    if C.get('mo_by') and not C.get('mo_need'): bad.append('mo_by khong co mo_need')
    if (C.get('entry_mode') or 'close') != 'close': bad.append('entry_mode')
    if C.get('entry_next_open'): bad.append('entry_next_open')
    # Phien ban duoc dau tien (26/09/2026: T+3 theo tai khoan anh Son). hard stop cung tu phien do.
    if int(C.get('hs_from', 2) or 2) != int(C.get('sell_from', 2) or 2): bad.append('hs_from != sell_from')
    if float(C.get('fill_ratio', 1.0) or 1.0) != 1.0: bad.append('fill_ratio')
    # S1 khoa lai (26/09/2026): so ghi tien chi ho tro dang [[dinh, san], ...] cua exit_rules
    try:
        ER.tiers(C)
    except Exception:
        bad.append('profit_lock')
    if float(C.get('slip') or 0) > 0: bad.append('slip')
    if C.get('use_market_gate') is False: bad.append('use_market_gate=False')
    if bad:
        sys.exit(f"HONG: PROD bat {bad} ma so ghi tien chua ho tro — se lech bo may. Dung.")
    return C


def rong():
    return dict(version=2, book_id=BOOK_ID, nav_source='portfolio.json', nav0=NAV0,
                cash=NAV0, nav=NAV0, session_done=None, updated=None,
                open=[], closed=[], log=[])


def nap():
    if os.path.exists(FILE):
        try:
            P = json.load(open(FILE, encoding='utf-8'))
            for k, v in rong().items():
                P.setdefault(k, v)
            return P
        except Exception as e:
            print(f'canh bao: {FILE} hong ({e}) — lam lai tu dau')
    return rong()


def bars(sym, frm, to):
    """Nen ngay: (date, AdjClose, PriceClose, AdjHigh) tang dan theo ngay."""
    for a in range(4):
        try:
            r = requests.get(BASE + '/Companies/HistoricalQuotes',
                             params={'symbol': sym, 'startDate': frm, 'endDate': to},
                             headers=H, timeout=45)
            d = r.json()
            if isinstance(d, list):
                out = []
                for x in d:
                    try:
                        ac = float(x.get('AdjClose') or 0); pc = float(x.get('PriceClose') or 0)
                        ah = float(x.get('AdjHigh') or ac)
                    except Exception:
                        continue
                    if ac > 0 and pc > 0:
                        out.append((str(x.get('Date', ''))[:10], ac, pc, ah))
                out.sort()
                return out
        except Exception:
            pass
    return []


def ma(seq, n, i):
    if i + 1 < n:
        return None
    return sum(seq[i - n + 1:i + 1]) / n


def cost_px(p, C):
    """Gia von 1 cp DA GOM phi mua (VND, gia THO luc mua)."""
    if p.get('cost_px'):
        return float(p['cost_px'])
    if p.get('cost') and p.get('sh'):
        return float(p['cost']) / float(p['sh'])
    return float(p['entry_px']) * (1 + C['fee_buy'])


def dong_vi_the(P, p, ly_do, ngay, px_adj, px_raw, k_adj, C, phan=1.0):
    """Ban `phan` vi the. QUY UOC GIA (mot quy uoc duy nhat): vi the do bang so co
    phan LUC MUA; gia tri moi co phieu goc tai phien i = AdjClose[i] / k_adj, voi
    k_adj = AdjClose/PriceClose cua phien mua (lay tu CUNG mot lan tai nen). Co tuc
    tien / co phieu / chia tach vi the duoc tinh nhu tai dau tu — khong con lo gia."""
    sh = int(p['sh'] * phan // 100 * 100) if phan < 1 else p['sh']
    if sh <= 0:
        return False
    thu = sh * (px_adj / k_adj) * (1 - C['fee_sell'])
    cp = cost_px(p, C)
    P['cash'] += thu
    von = sh * cp
    P['closed'].insert(0, dict(
        book_id=BOOK_ID, position_source=p.get('position_source', 'live_scan'),
        sym=p['sym'], name=p.get('name', ''), sector=p.get('sector', ''),
        entry=p['entry'], exit=ngay,
        entry_px=round(p['entry_px'] / 1000, 2), exit_px=round(px_raw / 1000, 2),
        sh=sh, held=p.get('held', 0),
        # Lai/lo THAT vao tui: tru phi mua (trong gia von) + phi ban/thue.
        pnl_pct=round((thu / von - 1) * 100, 2),
        pnl_vnd=round(thu - von),
        reason=ly_do, peak=round(p.get('peak', 0) * 100, 1),
        profit_floor=(None if p.get('_floor') is None else round(p['_floor'] * 100, 2)),
        light=p.get('light', ''), phan=round(phan, 3)))
    p['sh'] -= sh
    if phan < 1:
        p['part'] = True
    return p['sh'] <= 0


def main():
    if not os.path.exists('thresholds.json'):
        sys.exit('HONG: chua co thresholds.json — ban dung toi chua dang')
    T = json.load(open('thresholds.json', encoding='utf-8'))
    C = cfg(T)
    # Phien = phien ma ban dung toi vua chot (thresholds.asof), khong phai live.json.
    ses = T.get('asof')
    if not ses:
        print('chua co phien nao — khong lam gi')
        return
    now = gio_vn()
    hom_nay = now.date().isoformat()
    # Chi vao so tren du lieu CUOI PHIEN (loi 2: truoc day chot o lan chay dau tien sau
    # 14h50, lenh MUA den luc 15h40 khong bao gio duoc vao).
    chot = (ses < hom_nay) or (now.hour + now.minute / 60 >= 15.5)
    if not chot:
        print(f'phien {ses} chua dong cua — chua vao so')
        return
    P = nap()
    # DUNG LAI SO MOT LAN (24/09/2026): so cu mo tu 15/09 bang lop quet live cu — bo
    # sot BVH 14/09 (lech nen) va vao sai PVP 22/09 (Dieu kien 9 = 1,381). Dung lai
    # tu 11/09 bang CHINH cac lenh cua bo may (signals_recent) de so ghi tien trung
    # bo may tu dau. Giu ban cu trong `so_cu` de doi chieu, khong xoa dau vet.
    if not P.get('dung_lai_2409') and T.get('light_by_date'):
        cu = {k: P.get(k) for k in ('open', 'closed', 'log', 'cash', 'nav', 'session_done')}
        P = rong()
        P['so_cu'] = cu
        P['dung_lai_2409'] = True
        P['session_done'] = '2026-09-11'
        if '2026-09-14' not in (T.get('light_by_date') or {}):
            print('CANH BAO: cua so light_by_date khong con 14/09 — dung lai so se thieu BVH')
        P['log'] = [dict(date=ses, items=['DỰNG LẠI SỔ: sổ cũ (15–23/09) do lớp quét live cũ ghi — bỏ sót BVH 14/09, '
                                          'vào sai PVP 22/09 (Điều kiện 9 = 1,381 < 1,40). Sổ mới vào đúng các lệnh của '
                                          'bộ máy từ 14/09, vốn 1 tỷ. Bản cũ lưu trong "so_cu".'])]
    if P.get('session_done') == ses and not os.environ.get('LAM_LAI'):
        # PHIEN DA VAO SO — nhung neu cau hinh PROD vua doi (hash khac) hoac vi the thieu
        # truong cua luat thoat dang chay thi phai NANG CAP TRANG THAI, khong duoc im lang
        # tra ve (loi 26/09/2026: deploy TOP110+S1 xong, so van mang hash cu 89c720ebf701,
        # BVH thieu profit_floor/sellable/action).
        if can_nang_cap(P, T):
            nang_cap(P, T, C, ses, now)
            json.dump(P, open(FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        else:
            print(f'phien {ses} da vao so roi')
        kiem_sau(P, T)
        return
    P['version'] = 2; P['book_id'] = BOOK_ID; P['nav_source'] = 'portfolio.json'

    # Den thi truong CUA CHINH PHIEN (engine2 dung den tinh bang dong cua phien do).
    # thresholds.json cua phien nay chi co sau ban dung toi — nen so ghi tien chay
    # trong daily.yml cua repo rieng, SAU khi dang thresholds (loi 3: den tre 1 phien).
    if not T or T.get('asof') != ses:
        print(f"thresholds.json cua phien {ses} chua co (asof={T.get('asof')}) — doi ban dung toi")
        return
    light = T.get('light')
    if light not in ('XANH', 'VANG', 'CAM', 'DO'):
        print('khong co den thi truong hop le — khong vao so'); return
    syms_th = T.get('syms', {})
    from live_scan import loai_so_tay
    loai = set(loai_so_tay())
    if os.path.exists('loai.txt'):
        for line in open('loai.txt', encoding='utf-8'):
            t = line.split('#')[0].strip().upper()
            if t.isalnum() and 3 <= len(t) <= 10:
                loai.add(t)
    nhat_ky = []

    # ---------- CAC PHIEN CHUA XU LY (theo dung thu tu) ----------
    lights = dict(T.get('light_by_date') or {}); lights[ses] = light
    sig_by = {}
    for h in (T.get('signals_recent') or []) + (T.get('signals_today') or []):
        sig_by.setdefault(h.get('date'), {})[h['sym']] = h
    done = P.get('session_done')
    cho = sorted(d for d in lights if (not done or d > done) and d <= ses)
    if done and done < ses and T.get('light_by_date') is None:
        nhat_ky.append(f"CẢNH BÁO: sổ dừng ở {done}; bản dựng không có lịch sử đèn/tín hiệu — chỉ xử lý {ses}")
    CACHE = {}
    # Lo qua nhieu phien (ngoai cua so light_by_date) -> KHONG im lang
    if done and cho and T.get('light_by_date'):
        truoc = min(T['light_by_date'])
        if done < truoc:
            nhat_ky.append(f"CẢNH BÁO: sổ dừng ở {done}, bản dựng chỉ còn lịch sử từ {truoc} — "
                           "các phiên ở giữa không xử lý được lệnh mua / hạ 1/3 / nhồi")
    theo_phien = []
    for d in (cho or [ses]):
        nk = []
        mot_phien(P, T, C, d, lights.get(d), list(sig_by.get(d, {}).values()), loai, syms_th,
                  nk, CACHE, ses)
        if nk:
            theo_phien.append((d, nk))


    # ---------- 4. CHOT SO + DOI SOAT ----------
    mv = sum(p['sh'] * (p.get('last_val') or (p.get('last') or 0) * 1000 or p['entry_px']) for p in P['open'])
    P['nav'] = round(P['cash'] + mv)
    P['session_done'] = ses
    P['updated'] = now.isoformat(timespec='seconds')
    P['light'] = light
    P['prod_config_hash'] = T.get('prod_config_hash')
    P['open'].sort(key=lambda p: p['entry'])
    P['closed'] = P['closed'][:400]
    if nhat_ky:
        P['log'].insert(0, dict(date=ses, items=nhat_ky))
    for d, nk in theo_phien:          # moi viec ghi dung ngay phien cua no
        P['log'].insert(0, dict(date=d, items=nk))
    P['log'].sort(key=lambda x: x['date'], reverse=True)
    P['log'] = P['log'][:120]
    P['checks'] = doi_soat(P, C, T.get('cfg') or {})
    tong_ = P['closed']
    thang = [c for c in tong_ if c['pnl_pct'] > 0]
    P['stats'] = dict(
        n_open=len(P['open']), n_closed=len(tong_),
        winrate=round(100 * len(thang) / len(tong_), 1) if tong_ else None,
        total_return=round((P['nav'] / NAV0 - 1) * 100, 2),
        best=max((c['pnl_pct'] for c in tong_), default=None),
        worst=min((c['pnl_pct'] for c in tong_), default=None),
        since=min([p['entry'] for p in P['open']] + [c['entry'] for c in P['closed']] or [ses]))
    json.dump(P, open(FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    kiem_sau(P, T)
    print(f"so lenh · phien {ses} · den {light} · NAV {P['nav']/1e9:.4f} ty "
          f"({P['stats']['total_return']:+.2f}%) · {len(P['open'])} ma dang cam · doi soat "
          f"{'DAT' if P['checks']['ok'] else 'TRUOT'}")
    for x in nhat_ky:
        print('  ' + x)


def mot_phien(P, T, C, ses, light, signals, loai, syms_th, nhat_ky, CACHE, ASOF):
    """Xu ly MOT phien: huy lenh sai luat, thoat lenh (tang dan), vao lenh bo may,
    nhoi lenh. Goi lan luot cho moi phien chua xu ly (audit 24/09, loi D3: truoc day
    bo lo mot dem la mat lenh mua va lan ha 1/3 cua phien do)."""
    # ---------- 0. HUY LENH SAI LUAT (mot lan) ----------
    for p in P['open']:
        k = (p['sym'], p['entry'])
        if k in VOID and p.get('sh', 0) > 0 and not p.get('void_done'):
            p['void'] = VOID[k]

    # ---------- 1. CHAM SOC CAC VI THE DANG MO ----------
    mo = [p for p in P['open'] if p.get('sh', 0) > 0]
    need = [p for p in mo if p['sym'] not in CACHE]
    if need:
        frm = (min(dt.date.fromisoformat(p['entry']) for p in need) - dt.timedelta(days=75)).isoformat()
        with ThreadPoolExecutor(max_workers=6) as ex:
            CACHE.update(zip([p['sym'] for p in need], ex.map(lambda p: bars(p['sym'], frm, ASOF), need)))
    # chi dung nen TOI phien dang xu ly (xu ly bu nhieu phien bi lo theo dung thu tu)
    hist = {p['sym']: [x for x in (CACHE.get(p['sym']) or []) if x[0] <= ses] for p in mo}

    con_lai = []
    for p in mo:
        p.setdefault('book_id', BOOK_ID); p.setdefault('position_source', 'live_scan')
        p.setdefault('nav_source', 'portfolio.json')
        if 'cost_px' not in p:
            p['cost_px'] = cost_px(p, C)
        b = hist.get(p['sym']) or []
        if not b:
            print(f"  ! {p['sym']}: khong tai duoc nen, giu nguyen")
            con_lai.append(p)
            continue
        ngays = [x[0] for x in b]; adj = [x[1] for x in b]; raw = [x[2] for x in b]; ahi = [x[3] for x in b]
        try:
            i0 = ngays.index(p['entry'])
        except ValueError:
            i0 = max(0, len([d for d in ngays if d < p['entry']]) - 1)
        # quy doi gia von THO sang thang gia DIEU CHINH hien tai
        k_adj = adj[i0] / raw[i0] if raw[i0] else 1.0
        epx_adj = p['cost_px'] * k_adj           # = engine2 epx (gom phi mua)
        if p.get('void') and (len(ngays) - 1 - i0) < int(C.get('sell_from', 2) or 2):
            # chua toi phien ban duoc dau tien — huy o phien ban duoc dau tien
            p.update(held=len(ngays) - 1 - i0, last=round(raw[-1] / 1000, 2),
                     last_val=round(adj[-1] / k_adj, 2), k_adj=round(k_adj, 6), last_day=ngays[-1])
            con_lai.append(p)
            continue
        if p.get('void'):
            dong_vi_the(P, p, p['void'], ngays[-1], adj[-1], raw[-1], k_adj, C)
            p['void_done'] = True
            nhat_ky.append(f"HUỶ {p['sym']} — {p['void']}")
            continue
        # XU LY TANG DAN (audit 24/09, loi 1): chi xet cac phien CHUA xu ly. Chay lai tu
        # ngay mua bang gia von / so co HIEN TAI (sau khi nhoi) tung ban lai o qua khu
        # mot vi the dang lai (-46 tr trong kich ban kiem thu). Nay mang peak/b10/b20
        # sang tu lan truoc, dung nhu engine2 cap nhat tung phien mot.
        ld = p.get('last_done')
        if ld and ld in ngays:
            start = ngays.index(ld) + 1
            peak = float(p.get('peak') or 0.0); b10 = int(p.get('b10') or 0); b20 = int(p.get('b20') or 0)
        else:
            start = i0; peak = 0.0; b10 = 0; b20 = 0
        da_dong = False
        for i in range(start, len(ngays)):
            px = adj[i]
            held = i - i0
            gain = px / epx_adj - 1
            peak = max(peak, gain)
            mF = ma(adj, C['trail_fast'], i); mS = ma(adj, C['trail_ma'], i)
            b10 = b10 + 1 if (mF is not None and px < mF) else 0
            b20 = b20 + 1 if (mS is not None and px < mS) else 0
            p.update(peak=peak, b10=b10, b20=b20, held=held,
                     last=round(raw[i] / 1000, 2), last_adj=round(px / 1000, 4), last_day=ngays[i],
                     last_val=round(px / k_adj, 2), k_adj=round(k_adj, 6),
                     pnl=round((px * (1 - C['fee_sell']) / epx_adj - 1) * 100, 2),
                     last_done=ngays[i])
            # MOT DINH NGHIA DUY NHAT: exit_rules.decide (= engine2, cung thu tu uu tien). Truoc
            # T+sell_from khong ban gi ca (tra ve rule=None, pending = luat dang cham).
            dq = ER.decide(C, gain, peak, held, probe_fail=bool(p.get('probe_fail')), b10=b10, b20=b20,
                           light_today=(light if ngays[i] == ses else None), light_entry=p.get('light'),
                           part=bool(p.get('part')))
            r, phan = dq['rule'], dq['phan']
            if r:
                p['_floor'] = dq['floor']
                het = dong_vi_the(P, p, r, ngays[i], px, raw[i], k_adj, C, phan)
                nhat_ky.append(f"BÁN {p['sym']} {raw[i]/1000:.2f} (lãi/lỗ sau phí {P['closed'][0]['pnl_pct']:+.2f}%) — {r}")
                if het:
                    da_dong = True
                    break
        if not da_dong and p.get('sh', 0) > 0:
            p['_hi10'] = max(ahi[max(0, len(ahi) - 10):]) if ahi else None
            p['_gain'] = adj[-1] / epx_adj - 1
            # TRANG THAI CUA RA sau phien (S1): dinh lai luu BEN VUNG trong `peak` (mang sang
            # lan chay sau qua last_done), san dang bat, ban duoc chua, luat dang cham.
            _h = len(ngays) - 1 - i0; _sf = int(C.get('sell_from', 2) or 2)
            p.update(ER.status(C, p['_gain'], float(p.get('peak') or 0.0), _h,
                               probe_fail=bool(p.get('probe_fail')), b10=int(p.get('b10') or 0),
                               b20=int(p.get('b20') or 0), light_today=(light if ngays[-1] == ses else None),
                               light_entry=p.get('light'), part=bool(p.get('part'))))
            p['earliest_sell'] = ngays[i0 + _sf] if i0 + _sf < len(ngays) else f"T+{_sf}"
            p['cost_basis'] = 'cost_px = gia khop x (1 + phi mua); gain = AdjClose / (cost_px x k_adj) - 1'
            # 30 gia dong cua dieu chinh gan nhat: de lop quet trong phien tinh MA10/MA30 voi gia hom nay
            p['tail_adj'] = [round(x, 2) for x in adj[-30:]]
            con_lai.append(p)
    P['open'] = con_lai

    def gia(p):
        return p.get('last_val') or (p.get('last') or 0) * 1000 or p['entry_px']

    def tong():
        return sum(p['sh'] * gia(p) for p in P['open'])

    # ---------- 2. LENH MUA CUA BO MAY TRONG PHIEN NAY -> VAO SO ----------
    # Nguon DUY NHAT: thresholds.json['signals_today'] = cac lenh engine2 THUC SU mua
    # o phien `ses` (du dieu kien PROD, ke ca Dieu kien 9 da lap du tu nguon chinh
    # thuc). Khong con doc muc MUA cua live.json — lop do de keu chuong trong phien,
    # con so ghi tien phai la ban sao cua bo may (audit 24/09).
    dang_cam = {p['sym'] for p in P['open']}
    muon_mua = []
    for h in (signals or []):
        if h.get('date') != ses:
            continue
        dat9 = (h.get('ordimb') or 0) >= C.get('ordimb_min', 1.4)
        if C.get('use_ordimb', True) and not dat9 and C.get('stage1') is None:
            nhat_ky.append(f"TỪ CHỐI {h['sym']} — Điều kiện 9 không đạt ({h.get('ordimb')})")
            continue
        if h['sym'] in dang_cam or h['sym'] in loai:
            continue
        muon_mua.append(dict(h, price=float(h['price']) / 1000,
                             _probe_fail=bool(C.get('stage1') is not None and C.get('use_ordimb', True) and not dat9)))
    # thu tu uu tien = engine2.rank_rows('score'): diem CANSLIM giam dan, hoa -> ma
    muon_mua.sort(key=lambda h: (-(h.get('score') or 0), h['sym']))

    for h in muon_mua:
        px = float(h['price']) * 1000
        if px <= 0:
            continue
        th = syms_th.get(h['sym'], {})
        sp = dict(rmul=h.get('rmul', 1.0), base=h.get('base'))
        nganh = h.get('sector') or th.get('sector') or 'Khác'
        inv = tong(); nav = P['cash'] + inv
        sec = sum(p['sh'] * gia(p) for p in P['open'] if (p.get('sector') or 'Khác') == nganh)
        A = AL.entry_target(nav, P['cash'], inv, sec, len(P['open']), light,
                            risk_mul=sp.get('rmul', 1.0), base_rng=sp.get('base'), cfg=T.get('cfg') or {})
        if not A['ok']:
            nhat_ky.append(f"BỎ QUA {h['sym']} — {AL.REASON_VI.get(A['binding'], A['binding'])}")
            continue
        c_px = px * (1 + C['fee_buy'])
        sh = AL.lots(A['actual'], c_px)
        if sh < 100:
            nhat_ky.append(f"BỎ QUA {h['sym']} — không đủ 1 lô")
            continue
        chi = sh * c_px
        P['cash'] -= chi
        P['open'].append(dict(
            book_id=BOOK_ID, position_source='engine_signal', nav_source='portfolio.json',
            sym=h['sym'], name=h.get('name') or th.get('name', ''), sector=nganh,
            entry=ses, entry_px=px, cost_px=c_px, sh=sh, cost=round(chi),
            peak=0.0, b10=0, b20=0, part=False, pyr=False, held=0,
            light=light, score=h.get('score'), ordimb=h.get('ordimb'),
            probe_fail=h.get('_probe_fail', False),
            prod_config_hash=T.get('prod_config_hash'),
            size_theo=round(A['theoretical'] / nav * 100, 2), size_reasons=A['reasons'],
            last=round(px / 1000, 2), last_day=ses, pnl=0.0))
        P['open'][-1]['x0'] = ty_trong(P, h['sym'], nganh, ses, gia)
        # vi the vua mua cung phai co trang thai cua ra (T+0: chua ban duoc)
        P['open'][-1].update(ER.status(C, px / c_px - 1, 0.0, 0, probe_fail=bool(h.get('_probe_fail')),
                                       light_today=light, light_entry=light))
        P['open'][-1]['earliest_sell'] = f"T+{int(C.get('sell_from', 2) or 2)}"
        if h.get('_probe_fail'):
            nhat_ky.append(f"MUA DÒ {h['sym']} lúc ATC — tối ĐK9 = {h.get('ordimb')} < {C.get('ordimb_min', 1.4)}: "
                           f"không xác nhận, bán ATC T+{int(C.get('sell_from', 2) or 2)}")
        _x = P['open'][-1]['x0']
        nhat_ky.append(f"MUA {h['sym']} {px/1000:.2f} × {sh:,} cp ({chi/nav*100:.1f}% NAV · ngành {_x['sector_pct']:.1f}% · "
                       f"tổng cổ phiếu {_x['total_pct']:.1f}% NAV · "
                       f"lý thuyết {A['theoretical']/nav*100:.1f}% · đèn {TEN_DEN.get(light, light)} · "
                       f"OrdImb {h.get('ordimb')})")

    # ---------- 3. KIM TU THAP (engine2 lop 9, qua allocator) ----------
    if C.get('use_pyramid') and light == 'XANH':
        for p in P['open']:
            if p.get('pyr') or p['entry'] == ses or p.get('probe_fail'):
                continue
            held = p.get('held', 0); g = p.get('_gain')
            lastp = gia(p); hi10 = p.get('_hi10')
            if not (4 <= held <= 7) or g is None or g < 0.10 or not hi10:
                continue
            if (p.get('last_adj') or 0) * 1000 < 0.999 * hi10:      # gan dinh 10 phien
                continue
            inv = tong(); nav = P['cash'] + inv
            sec = sum(q['sh'] * gia(q) for q in P['open'] if q.get('sector') == p.get('sector'))
            if (T.get('cfg') or {}).get('pyr_caps'):
                room, why = AL.addon_capacity(nav, P['cash'], inv, sec, p['sh'] * lastp, cfg=T.get('cfg') or {})
            else:
                # = engine2 PROD (pyr_caps=False): lenh nhoi chi xet tran moi ma + tien mat
                _mp = (T.get('cfg') or {}).get('max_pos', 0.5)
                room, why = min((nav * _mp - p['sh'] * lastp, 'max_pos'), (P['cash'], 'cash'), key=lambda t: t[0])
                room = max(0.0, room)
            raw_now = (p.get('last') or 0) * 1000
            c2 = raw_now * (1 + C['fee_buy'])
            cur_sh = p['sh'] * lastp / raw_now if raw_now else p['sh']   # so co HIEN TAI (sau chia tach)
            add = int(cur_sh * 0.5 // 100 * 100)
            if (T.get('cfg') or {}).get('pyr_caps'):
                add = min(add, AL.lots(room, c2))
            elif (p['sh'] * lastp + add * raw_now > nav * (T.get('cfg') or {}).get('max_pos', 0.5)
                  or add * c2 > P['cash']):   # = engine2: tran moi ma tinh KHONG phi, tien mat CO phi
                continue
            if add < 100 or raw_now <= 0:
                continue
            # quy doi co phieu mua hom nay sang don vi "co phieu goc" cua vi the
            k = p.get('k_adj') or 1.0
            add_u = int(round(add * raw_now / lastp)) if lastp else add
            p['cost_px'] = (p['cost_px'] * p['sh'] + c2 * add) / (p['sh'] + add_u)
            P['cash'] -= add * c2; p['sh'] = p['sh'] + add_u; p['pyr'] = True
            p['cost'] = round(p['cost_px'] * p['sh'])
            p['xp'] = ty_trong(P, p['sym'], p.get('sector'), ses, gia)
            _x = p['xp']
            nhat_ky.append(f"NHỒI {p['sym']} +{add:,} cp @ {raw_now/1000:.2f} — sau nhồi mã {_x['pos_pct']:.1f}% NAV · "
                           f"ngành {_x['sector_pct']:.1f}% NAV · tổng {_x['total_pct']:.1f}% NAV "
                           f"(giới hạn: {AL.REASON_VI.get(why, why)})")
    for p in P['open']:
        p.pop('_hi10', None); p.pop('_gain', None)


# Truong bat buoc tren moi vi the dang mo = cac truong exit_rules.status xuat ra.
TRUONG_BAT_BUOC = ('peak_gain', 'gain', 'profit_lock_active', 'profit_floor', 'sellable',
                   'pending_exit', 'action')


def thieu_truong(P):
    return [(p.get('sym'), k) for p in P.get('open') or [] if p.get('sh', 0) > 0
            for k in TRUONG_BAT_BUOC if k not in p]


def can_nang_cap(P, T):
    return (P.get('prod_config_hash') != T.get('prod_config_hash')) or bool(thieu_truong(P))


def ty_trong(P, sym, nganh, ngay, gia):
    """Ty trong SAU khi khop, tren NAV cung phien: ma / nganh / tong co phieu (%)."""
    inv = sum(q['sh'] * gia(q) for q in P['open'])
    nav = P['cash'] + inv
    me = sum(q['sh'] * gia(q) for q in P['open'] if q['sym'] == sym)
    se = sum(q['sh'] * gia(q) for q in P['open'] if (q.get('sector') or 'Khác') == (nganh or 'Khác'))
    f = lambda v: round(100 * v / nav, 2) if nav > 0 else None
    return dict(date=ngay, pos_pct=f(me), sector_pct=f(se), total_pct=f(inv), nav=round(nav))


def nang_cap(P, T, C, ses, now):
    """NANG CAP TRANG THAI khi prod_config_hash doi (hoac thieu truong):
    KHONG mua/ban lai, KHONG sua lich su. Voi moi vi the dang mo: tai lai nen tu ngay
    mua toi `ses`, tinh lai peak / b10 / b20 / held theo dung quy uoc gia cua so,
    roi gan trang thai cua ra theo luat MOI (exit_rules.status). Neu luat moi le ra
    da ban o mot phien truoc -> ghi CANH BAO vao nhat ky (khong tu ban lui ngay)."""
    cu = P.get('prod_config_hash'); moi = T.get('prod_config_hash')
    light = T.get('light'); nk = []
    for p in P['open']:
        if p.get('sh', 0) <= 0:
            continue
        frm = (dt.date.fromisoformat(p['entry']) - dt.timedelta(days=75)).isoformat()
        b = [x for x in bars(p['sym'], frm, ses) if x[0] <= ses]
        if not b or p['entry'] > b[-1][0]:
            sys.exit(f"HONG: nang cap so — khong tai duoc nen {p['sym']}, khong the gan trang thai luat moi")
        ngays = [x[0] for x in b]; adj = [x[1] for x in b]; raw = [x[2] for x in b]
        i0 = ngays.index(p['entry']) if p['entry'] in ngays else max(0, len([d for d in ngays if d < p['entry']]) - 1)
        k_adj = adj[i0] / raw[i0] if raw[i0] else 1.0
        epx_adj = cost_px(p, C) * k_adj
        peak = 0.0; b10 = b20 = 0; som = None
        _sf = int(C.get('sell_from', 2) or 2)
        for i in range(i0, len(ngays)):
            px = adj[i]; held = i - i0; gain = px / epx_adj - 1; peak = max(peak, gain)
            mF = ma(adj, C['trail_fast'], i); mS = ma(adj, C['trail_ma'], i)
            b10 = b10 + 1 if (mF is not None and px < mF) else 0
            b20 = b20 + 1 if (mS is not None and px < mS) else 0
            if i < len(ngays) - 1 and som is None:
                dq = ER.decide(C, gain, peak, held, probe_fail=bool(p.get('probe_fail')), b10=b10, b20=b20,
                               light_today=None, light_entry=p.get('light'), part=bool(p.get('part')))
                if dq['rule']:
                    som = (ngays[i], dq['rule'])
        if abs(peak - float(p.get('peak') or 0)) > 0.001:
            nk.append(f"NÂNG CẤP {p['sym']}: đỉnh lãi tính lại {peak*100:+.2f}% (sổ cũ ghi {float(p.get('peak') or 0)*100:+.2f}%)")
        gain = adj[-1] / epx_adj - 1; held = len(ngays) - 1 - i0
        p.update(peak=peak, b10=b10, b20=b20, held=held, last=round(raw[-1] / 1000, 2),
                 last_adj=round(adj[-1] / 1000, 4), last_val=round(adj[-1] / k_adj, 2), k_adj=round(k_adj, 6),
                 last_day=ngays[-1], last_done=ngays[-1],
                 pnl=round((adj[-1] * (1 - C['fee_sell']) / epx_adj - 1) * 100, 2))
        p.update(ER.status(C, gain, peak, held, probe_fail=bool(p.get('probe_fail')), b10=b10, b20=b20,
                           light_today=(light if ngays[-1] == ses else None), light_entry=p.get('light'),
                           part=bool(p.get('part'))))
        p['earliest_sell'] = ngays[i0 + _sf] if i0 + _sf < len(ngays) else f"T+{_sf}"
        p['cost_basis'] = 'cost_px = gia khop x (1 + phi mua); gain = AdjClose / (cost_px x k_adj) - 1'
        p['tail_adj'] = [round(x, 2) for x in adj[-30:]]
        p['cfg_hash_state'] = moi          # hash cua luat dang gan trang thai (prod_config_hash = hash luc mua)
        if som:
            nk.append(f"CẢNH BÁO {p['sym']}: luật mới lẽ ra đã bán phiên {som[0]} ({som[1]}) — "
                      "sổ KHÔNG bán lùi ngày; xử lý ở phiên kế tiếp theo đúng luật")
        nk.append(f"NÂNG CẤP {p['sym']}: đỉnh {p['peak_gain']:+.2f}% · hiện {p['gain']:+.2f}% · sàn "
                  f"{'—' if p['profit_floor'] is None else ('%+.2f%%' % p['profit_floor'])} · {p['action']}")
    P['prod_config_hash'] = moi
    P.setdefault('migrations', []).insert(0, dict(at=now.isoformat(timespec='seconds'), session=ses,
                                                  from_hash=cu, to_hash=moi,
                                                  n_open=len([p for p in P['open'] if p.get('sh', 0) > 0])))
    P['log'].insert(0, dict(date=ses, items=[f"NÂNG CẤP TRẠNG THÁI SỔ: cấu hình {cu} → {moi} "
                                             "(không mua/bán lại, không sửa lịch sử)"] + nk))
    P['log'].sort(key=lambda x: x['date'], reverse=True)
    P['checks'] = doi_soat(P, C, T.get('cfg') or {})
    for x in P['log'][0]['items']:
        print('  ' + x)


def kiem_sau(P, T):
    """CHOT CUNG sau moi lan chay: so phai cung hash voi thresholds.json, moi vi the
    dang mo du truong cua luat thoat dang chay, doi soat DAT. Truot -> thoat ma 1,
    workflow dung, khong dang."""
    loi = []
    if P.get('prod_config_hash') != T.get('prod_config_hash'):
        loi.append(f"hash so {P.get('prod_config_hash')} != thresholds {T.get('prod_config_hash')}")
    t = thieu_truong(P)
    if t:
        loi.append(f"vi the thieu truong: {t[:6]}")
    if not (P.get('checks') or {}).get('ok'):
        loi.append(f"doi soat truot: {P.get('checks')}")
    if loi:
        sys.exit('HONG so ghi tien: ' + ' | '.join(loi))
    print(f"kiem so: DAT (hash {P.get('prod_config_hash')}, {len(P.get('open') or [])} vi the du truong)")


def doi_soat(P, C, cfg=None):
    """Bat bien ke toan + gioi han von cua so (moi lan chay):
      NAV = tien mat + gia tri thi truong; NAV - NAV0 = lai/lo da chot + chua chot
      tien mat >= 0
      TAI THOI DIEM VAO LENH / NHOI (anh chup x0 / xp): ma <= max_pos, tong <= max_total,
      nganh <= sector_cap cho lenh MOI. Lenh NHOI: PROD pyr_caps=False -> chi ma + tien mat
      (dung luat engine2) — nganh vuot 30% khi nhoi duoc LIET KE ro, khong an.
      Khong con dung sai x1,25 cho max_pos. Ty trong hien tai (troi theo gia) chi de xem."""
    cfg = cfg or {}
    mp = float(cfg.get('max_pos', 0.5)); mt = float(cfg.get('max_total', 1.0)); sc = float(cfg.get('sector_cap', 0.3))
    TOL = 0.5   # diem %: lam tron lo 100 cp + phi mua
    g = lambda p: p.get('last_val') or (p.get('last') or 0) * 1000 or p['entry_px']
    mv = sum(p['sh'] * g(p) for p in P['open'])
    real = sum(c.get('pnl_vnd', 0) for c in P['closed'])
    unreal = sum(p['sh'] * g(p) - p['sh'] * cost_px(p, C) for p in P['open'])
    nav = P['cash'] + mv
    gap = (nav - P['nav0']) - (real + unreal)
    vao = [(p['sym'], p['x0']) for p in P['open'] if p.get('x0')]
    nhoi = [(p['sym'], p['xp']) for p in P['open'] if p.get('xp')]
    cu = [p for p in P['open'] if not p.get('x0')]      # vi the truoc 26/09 chua co anh chup
    out = dict(nav_identity=abs(nav - P['nav']) < 1.0,
               pnl_reconcile_gap_vnd=round(gap),
               cash_nonneg=P['cash'] >= -1.0,
               # lenh moi: ma / tong / nganh luc vao; vi the cu: gia von tren NAV hien tai
               max_pos_ok=(all(x['pos_pct'] <= 100 * mp + TOL for _, x in vao + nhoi)
                           and all(p['sh'] * cost_px(p, C) <= mp * nav + 1 for p in cu)),
               max_total_ok=all(x['total_pct'] <= 100 * mt + TOL for _, x in vao + nhoi),
               sector_cap_ok=all(x['sector_pct'] <= 100 * sc + TOL for _, x in vao))
    if cfg.get('pyr_caps'):
        out['sector_cap_ok'] = out['sector_cap_ok'] and all(x['sector_pct'] <= 100 * sc + TOL for _, x in nhoi)
    out['pyr_sector_over'] = [dict(sym=s, **x) for s, x in nhoi if x['sector_pct'] > 100 * sc + TOL]
    sec = {}
    for p in P['open']:
        sec[p.get('sector') or 'Khác'] = sec.get(p.get('sector') or 'Khác', 0) + p['sh'] * g(p)
    out['now'] = dict(max_pos_pct=round(100 * max([p['sh'] * g(p) for p in P['open']] or [0]) / nav, 2) if nav else None,
                      max_sector_pct=round(100 * max(sec.values() or [0]) / nav, 2) if nav else None,
                      total_pct=round(100 * mv / nav, 2) if nav else None)
    # Lich su truoc ban va 23/09 ghi pnl_vnd thieu phi mua -> chenh lech lich su,
    # khong phai loi moi: chi coi la TRUOT neu lech > 0,1% NAV.
    out['pnl_reconcile_ok'] = abs(gap) <= 0.001 * P['nav0']
    out['ok'] = all(v for k, v in out.items() if isinstance(v, bool))
    return out


if __name__ == '__main__':
    main()
