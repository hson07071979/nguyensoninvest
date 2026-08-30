# -*- coding: utf-8 -*-
"""SO LENH TU DONG — bot ra tin hieu MUA la tu day vao danh muc.

Chay ngay sau `live_scan.py`, trong cung workflow. Moi phien mot lan, sau khi
thi truong dong cua (sau 14h50 gio Viet Nam):

  1. Doc `live.json`. Ma nao o muc MUA thi mo mot vi the moi, gia von = gia dong
     cua phien do — dung bang gia thiet khop lenh cua backtest.
  2. Voi moi vi the dang mo, tai lai toan bo nen ke tu ngay mua, tinh MA10/MA30,
     roi CHAY LAI bo thoat tren tung phien mot. Phien nao cham nguong truoc thi
     dong o do.
  3. Ghi `portfolio.json`. GitHub Actions commit file nay, nen lich su git chinh la
     so cai — khong ai sua duoc ma khong de lai dau vet.

VI SAO PHAI CHAY LAI TU DAU MOI LAN, thay vi cong don?
Vi workflow co the truot mot phien (GitHub tre, mang loi, ngay le). Cong don thi
mot lan truot la sai vinh vien. Chay lai thi lan sau tu vaf lai dung — muon con
hon sai.

KHAC BIET DA BIET so voi backtest, noi truoc cho khoi tuong nham:
  - Backtest con hai bo loc nua o buoc vao lenh (dong tien mua/ban >= 1,20 va
    loai truong hop loi rong tang 0-25%). So lenh nay khong co hai cai do, nen
    co the mo nhieu lenh hon backtest mot chut.
  - Backtest co kim tu thap (mua them khi lai). So lenh nay khong nhoi them.
  - "Den Cam ha 1/3" chi ap dung o phien hien tai, vi lich su den thi truong nam
    o repo private chu khong o day.
So lenh nay la BANG CHUNG SONG, khong phai ban sao cua backtest.
"""
import datetime as dt
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests

from live_scan import BASE, H, gio_vn

FILE = 'portfolio.json'

# --- dung y nguyen cau hinh PROD cua bot ---
NAV0        = 1_000_000_000.0
FEE_BUY     = 0.0015
FEE_SELL    = 0.0025
BASE_SIZE   = 0.42
MAX_POS     = 0.50
MAX_TOTAL   = 1.00
MAX_POS_N   = 12
SIZE_MAP    = {'XANH': 1.0, 'VANG': 0.6, 'CAM': 0.35, 'DO': 0.2}
TEN_DEN     = {'XANH': 'Xanh', 'VANG': 'Vàng', 'CAM': 'Cam', 'DO': 'Đỏ'}
HARD_STOP   = -0.10
STOP        = -0.07
BE_TRIGGER  = 0.08
BE_LEVEL    = 0.01
T_VALVE     = 6
BIG_WIN     = 0.19
CONF        = 2
TRAIL_FAST  = 10
TRAIL_SLOW  = 30


def rong():
    return dict(version=1, nav0=NAV0, cash=NAV0, nav=NAV0,
                session_done=None, updated=None,
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
    """Nen ngay tu `frm` den `to`, sap xep tang dan theo ngay."""
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
                        px = float(x.get('AdjClose') or x.get('PriceClose') or 0)
                    except Exception:
                        continue
                    if px > 0:
                        out.append((str(x.get('Date', ''))[:10], px))
                out.sort()
                return out
        except Exception:
            pass
    return []


def ma(seq, n, i):
    """Trung binh dong n phien tinh den vi tri i. Thieu du lieu thi tra None."""
    if i + 1 < n:
        return None
    return sum(seq[i - n + 1:i + 1]) / n


def dong_vi_the(P, p, ly_do, ngay, px, phan=1.0):
    sh = int(p['sh'] * phan // 100 * 100) if phan < 1 else p['sh']
    if sh <= 0:
        return False
    thu = sh * px * (1 - FEE_SELL)
    P['cash'] += thu
    P['closed'].insert(0, dict(
        sym=p['sym'], name=p.get('name', ''), sector=p.get('sector', ''),
        entry=p['entry'], exit=ngay,
        entry_px=round(p['entry_px'] / 1000, 2), exit_px=round(px / 1000, 2),
        sh=sh, held=p.get('held', 0),
        # Lai/lo THAT vao tui: tru ca phi mua lan phi ban + thue. Dung cong thuc
        # nay o moi cho tren trang, khong noi nao tinh khac.
        pnl_pct=round((px * (1 - FEE_SELL) / (p['entry_px'] * (1 + FEE_BUY)) - 1) * 100, 2),
        pnl_vnd=round(thu - sh * p['entry_px']),
        reason=ly_do, peak=round(p.get('peak', 0) * 100, 1),
        light=p.get('light', ''), phan=round(phan, 3)))
    p['sh'] -= sh
    if phan < 1:
        p['part'] = True
    return p['sh'] <= 0


def main():
    if not os.path.exists('live.json'):
        sys.exit('HONG: chua co live.json — chay live_scan.py truoc')
    L = json.load(open('live.json', encoding='utf-8'))
    T = json.load(open('thresholds.json', encoding='utf-8')) if os.path.exists('thresholds.json') else {}
    ses = L.get('session')
    if not ses:
        print('chua co phien nao — khong lam gi')
        return

    now = gio_vn()
    hom_nay = now.date().isoformat()
    # Chi vao so KHI PHIEN DA CHOT. Trong phien gia con nhay, ghi vao la ghi bay.
    chot = (ses < hom_nay) or (now.hour + now.minute / 60 >= 14.83)
    if not chot:
        print(f'phien {ses} chua dong cua — chua vao so')
        return

    P = nap()
    if P.get('session_done') == ses and not os.environ.get('LAM_LAI'):
        print(f'phien {ses} da vao so roi')
        return

    light = T.get('light') or 'XANH'
    smul = SIZE_MAP.get(light, 1.0)
    syms_th = T.get('syms', {})
    loai = set()
    if os.path.exists('loai.txt'):
        for line in open('loai.txt', encoding='utf-8'):
            t = line.split('#')[0].strip().upper()
            if t.isalnum() and 3 <= len(t) <= 10:
                loai.add(t)

    nhat_ky = []

    # ---------- 1. CHAM SOC CAC VI THE DANG MO ----------
    mo = [p for p in P['open'] if p.get('sh', 0) > 0]
    if mo:
        frm = (min(dt.date.fromisoformat(p['entry']) for p in mo)
               - dt.timedelta(days=75)).isoformat()
        with ThreadPoolExecutor(max_workers=6) as ex:
            hist = dict(zip([p['sym'] for p in mo],
                            ex.map(lambda p: bars(p['sym'], frm, ses), mo)))
    else:
        hist = {}

    con_lai = []
    for p in mo:
        b = hist.get(p['sym']) or []
        if not b:
            print(f"  ! {p['sym']}: khong tai duoc nen, giu nguyen")
            con_lai.append(p)
            continue
        ngays = [x[0] for x in b]
        gia = [x[1] for x in b]
        try:
            i0 = ngays.index(p['entry'])
        except ValueError:
            i0 = max(0, len([d for d in ngays if d < p['entry']]) - 1)

        peak = 0.0; b10 = 0; b20 = 0; da_dong = False
        for i in range(i0, len(ngays)):
            px = gia[i]
            held = i - i0
            gain = px / p['entry_px'] - 1
            peak = max(peak, gain)
            mF = ma(gia, TRAIL_FAST, i)
            mS = ma(gia, TRAIL_SLOW, i)
            b10 = b10 + 1 if (mF is not None and px < mF) else 0
            b20 = b20 + 1 if (mS is not None and px < mS) else 0
            p.update(peak=peak, b10=b10, b20=b20, held=held,
                     last=round(px / 1000, 2), last_day=ngays[i],
                     pnl=round((px * (1 - FEE_SELL) / (p['entry_px'] * (1 + FEE_BUY)) - 1) * 100, 2))
            if held < 2:
                continue
            r = None; phan = 1.0
            if gain <= HARD_STOP:                              r = 'Hard stop −10%'
            elif held >= 3 and gain <= STOP:                    r = 'Cắt lỗ −7%'
            elif peak >= BE_TRIGGER and gain <= BE_LEVEL:       r = 'Về bờ (đã lãi 8%)'
            elif held >= T_VALVE and gain <= 0:                 r = f'Van thời gian T+{T_VALVE}'
            elif peak >= BIG_WIN and b10 >= CONF:               r = f'Trailing MA{TRAIL_FAST} (lãi lớn)'
            elif b20 >= CONF:                                   r = f'Trailing MA{TRAIL_SLOW}'
            elif (ngays[i] == ses and light == 'CAM' and not p.get('part')):
                r, phan = 'Đèn Cam — hạ 1/3', 1 / 3
            if r:
                het = dong_vi_the(P, p, r, ngays[i], px, phan)
                nhat_ky.append(f"BÁN {p['sym']} {px/1000:.2f} ({gain*100:+.1f}%) — {r}")
                if het:
                    da_dong = True
                    break
        if not da_dong and p.get('sh', 0) > 0:
            con_lai.append(p)
    P['open'] = con_lai

    # ---------- 2. TIN HIEU MUA HOM NAY -> VAO SO ----------
    dang_cam = {p['sym'] for p in P['open']}
    ban_hom_nay = {c['sym'] for c in P['closed'] if c['exit'] == ses}
    muon_mua = [h for h in L.get('hits', [])
                if h.get('level') == 'MUA' and h['sym'] not in dang_cam
                and h['sym'] not in ban_hom_nay and h['sym'] not in loai]
    muon_mua.sort(key=lambda h: -(h.get('score') or 0))

    for h in muon_mua:
        if len(P['open']) >= MAX_POS_N:
            nhat_ky.append(f"BỎ QUA {h['sym']} — đã đủ {MAX_POS_N} mã trong danh mục")
            continue
        px = float(h['price']) * 1000
        if px <= 0:
            continue
        nav = P['cash'] + sum(p['sh'] * (p.get('last', 0) * 1000 or p['entry_px']) for p in P['open'])
        dang_dung = sum(p['sh'] * (p.get('last', 0) * 1000 or p['entry_px']) for p in P['open'])
        tran_con = max(0.0, MAX_TOTAL * nav - dang_dung)
        tien = min(BASE_SIZE * smul * nav, MAX_POS * nav, tran_con, P['cash'] / (1 + FEE_BUY))
        sh = int(tien / px // 100 * 100)
        if sh < 100:
            nhat_ky.append(f"BỎ QUA {h['sym']} — không đủ tiền/room")
            continue
        chi = sh * px * (1 + FEE_BUY)
        P['cash'] -= chi
        th = syms_th.get(h['sym'], {})
        P['open'].append(dict(
            sym=h['sym'], name=h.get('name') or th.get('name', ''),
            sector=th.get('sector') or 'Khác',
            entry=ses, entry_px=px, sh=sh, cost=round(chi),
            peak=0.0, b10=0, b20=0, part=False, held=0,
            light=light, score=h.get('score'),
            last=round(px / 1000, 2), last_day=ses, pnl=0.0))
        nhat_ky.append(f"MUA {h['sym']} {px/1000:.2f} × {sh:,} cp "
                       f"({BASE_SIZE*smul*100:.0f}% NAV · đèn {TEN_DEN.get(light, light)})")

    # ---------- 3. CHOT SO ----------
    mv = sum(p['sh'] * (p.get('last', 0) * 1000 or p['entry_px']) for p in P['open'])
    P['nav'] = round(P['cash'] + mv)
    P['session_done'] = ses
    P['updated'] = now.isoformat(timespec='seconds')
    P['light'] = light
    P['open'].sort(key=lambda p: p['entry'])
    P['closed'] = P['closed'][:400]
    if nhat_ky:
        P['log'].insert(0, dict(date=ses, items=nhat_ky))
        P['log'] = P['log'][:120]

    tong = [c for c in P['closed']]
    thang = [c for c in tong if c['pnl_pct'] > 0]
    P['stats'] = dict(
        n_open=len(P['open']), n_closed=len(tong),
        winrate=round(100 * len(thang) / len(tong), 1) if tong else None,
        total_return=round((P['nav'] / NAV0 - 1) * 100, 2),
        best=max((c['pnl_pct'] for c in tong), default=None),
        worst=min((c['pnl_pct'] for c in tong), default=None),
        since=(P['log'][-1]['date'] if P['log'] else ses),
    )

    json.dump(P, open(FILE, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    print(f"so lenh · phien {ses} · den {light} · NAV {P['nav']/1e9:.4f} ty "
          f"({P['stats']['total_return']:+.2f}%) · {len(P['open'])} ma dang cam · "
          f"{len(tong)} lenh da dong")
    for x in nhat_ky:
        print('  ' + x)
    if not nhat_ky:
        print('  (khong co gi thay doi)')


if __name__ == '__main__':
    main()
