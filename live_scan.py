# -*- coding: utf-8 -*-
"""BO QUET TRONG PHIEN — chay o repo public, moi 20 phut.

Doc `thresholds.json` (do repo private xuat ra moi toi), cao dong du lieu NGAY cua
tung ma tu FireAnt, so voi nguong, roi ghi `live.json` cho trang web doc.

File nay KHONG chua luat giao dich nao. No chi lam mot viec: so gia va khoi luong
hom nay voi hai con so da duoc tinh san. Toan bo he thong nam o repo private.

CANH BAO — dung dung `Markets/IntradayQuotes` de do khoi luong. Feed tick cua
FireAnt bi cat cut, cat nang nhat dung o nhom ma thanh khoan cao. Do thuc te phien
19/08/2026: TDM chi hien 0,4% khoi luong that, POW 13,1%, HDB 11,9%. Luon doc dong
du lieu NGAY (`Companies/HistoricalQuotes`) — no cong don dung trong phien.
"""
import datetime as dt
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests

import signal_spec as SP
from signal_spec import ordimb_of

# Duoi muc nay la DU LIEU THIEU, khong phai 'khong co tin hieu'.
MIN_COVERAGE = 0.90

H = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36',
     'Referer': 'https://fireant.vn/', 'Accept': 'application/json'}
BASE = 'https://www.fireant.vn/api/Data'

# Duong cong khoi luong luy ke dien hinh cua mot phien HOSE/HNX (gio Viet Nam).
# 9h15 ATO · 9h15-11h30 khop lien tuc · nghi trua · 13h00-14h30 · 14h30-14h45 ATC.
# Ma trong watchlist tang tu muc nay tro len thi keo CHUONG VANG — chi de mat,
# KHONG phai lenh. Nguyen tac vao lenh khong doi mot chu.
DE_MAT_PCT = 2.5

VOL_CURVE = [(9.25, 0.02), (9.50, 0.10), (10.00, 0.24), (10.50, 0.34), (11.00, 0.44),
             (11.50, 0.55), (13.00, 0.55), (13.50, 0.67), (14.00, 0.79), (14.25, 0.86),
             (14.50, 0.92), (14.75, 1.00)]


def gio_vn():
    """Gio Viet Nam, KHONG phu thuoc mui gio may chay. May chu GitHub chay theo UTC."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).replace(tzinfo=None)
    except Exception:
        return dt.datetime.utcnow() + dt.timedelta(hours=7)


def clock_frac(now=None):
    """Phien da di duoc bao nhieu phan khoi luong, tinh theo dong ho."""
    now = now or gio_vn()
    if now.weekday() >= 5:
        return 1.0
    t = now.hour + now.minute / 60.0
    if t <= VOL_CURVE[0][0]:
        return 0.02
    if t >= VOL_CURVE[-1][0]:
        return 1.0
    for k in range(1, len(VOL_CURVE)):
        t0, f0 = VOL_CURVE[k - 1]
        t1, f1 = VOL_CURVE[k]
        if t <= t1:
            return f0 + (f1 - f0) * (t - t0) / max(t1 - t0, 1e-9)
    return 1.0


def latest_row(sym, frm, to):
    """Dong du lieu cua PHIEN GAN NHAT trong khoang [frm, to].

    Khong hoi cung mot ngay `today`: truoc 9h15, sau nua dem, hay ngay nghi le thi
    hom nay khong co phien nao ca. Hoi mot khoang vai ngay roi lay dong moi nhat thi
    luc nao cung co so de hien, va co `session` de biet do la phien nao.
    """
    for a in range(3):
        try:
            r = requests.get(BASE + '/Companies/HistoricalQuotes',
                             params={'symbol': sym, 'startDate': frm, 'endDate': to},
                             headers=H, timeout=40)
            d = r.json()
            if isinstance(d, list):
                if not d:
                    return None
                d = sorted(d, key=lambda x: str(x.get('Date', '')))
                row = dict(d[-1])
                # phien giao dich LIEN TRUOC (tu chinh du lieu, khong doan bang lich —
                # ngay le khong lam hong viec khop dac ta)
                row['_prev'] = str(d[-2].get('Date', ''))[:10] if len(d) >= 2 else None
                return row
        except Exception:
            time.sleep(1.2 * (a + 1))
    return None



# ============================================================================
# CHUONG BAO GUI VE DIEN THOAI (Telegram)
#
# Lop real-time trong trinh duyet chi keu khi TAB DANG MO. Dong trinh duyet la
# khong biet gi ca. Day la manh con thieu: bot phai goi duoc anh Son ke ca luc
# anh dang lam viec khac.
#
# Vi sao Telegram chu khong phai email/SMS: mien phi vinh vien, khong gioi han
# so tin, khong can may chu, khong can the ngan hang, va tin den trong 1-2 giay.
#
# Chi gui khi CO MA MOI len muc MUA. So sanh voi live.json cua lan quet TRUOC —
# khong can file trang thai rieng, va cung khong the gui trung vi live.json da
# duoc commit vao git sau moi lan chay.
#
# Khong khai bao TELEGRAM_TOKEN/TELEGRAM_CHAT thi ham nay lang le bo qua. Bo quet
# van chay binh thuong nhu cu.
# ============================================================================
def doc_live_cu():
    """Nhung ma DA KEU CHUONG trong phien (`alerted`), giu qua moi lan quet — ke ca
    lan quet hong du lieu. Truoc day chi so voi MUA cua lan quet TRUOC, nen mot lan
    FireAnt sap hay OrdImb nhap nhay quanh 1,40 lam keu lai cung mot ma (audit 24/09)."""
    try:
        d = json.load(open('live.json', encoding='utf-8'))
        if 'alerted' in d:          # chi nhung ma DA GUI THANH CONG — gui hong thi lan sau gui lai
            al = d.get('alerted') or {}
            return set(al.get('syms') or []), (al.get('session') or d.get('session'))
        return {h['sym'] for h in d.get('hits', []) if h.get('level') == 'MUA'}, d.get('session')
    except Exception:
        return set(), None


def co_lenh(h, T, den):
    """Size shown in the alert = the SHARED allocator (allocator.py) applied to the
    live paper book, not a hand-typed 42% x light. Returns (theoretical %, actual %,
    reasons)."""
    try:
        import allocator as AL
        CF = T.get('cfg') or {}
        sp = (T['syms'].get(h['sym']) or {}).get('spec') or {}
        # NAV HIEN TAI cua so he thong (bo may) do ban dung toi qua xuat ra —
        # KHONG phai von goc 1 ty. Thieu thi moi lui ve so ghi tien.
        B = T.get('book') or {}
        if B.get('nav'):
            op = B.get('positions') or []
            inv = sum(float(p.get('value') or 0) for p in op)
            nav = float(B['nav']); cash = float(B.get('cash', nav - inv))
            sec = sum(float(p.get('value') or 0) for p in op if (p.get('sector') or 'Khác') == (sp.get('sector') or 'Khác'))
        else:
            P = json.load(open('portfolio.json', encoding='utf-8')) if os.path.exists('portfolio.json') else {}
            op = [p for p in (P.get('open') or []) if (p.get('sh') or 0) > 0]
            val = lambda p: p['sh'] * ((p.get('last') or 0) * 1000 or p['entry_px'])
            inv = sum(val(p) for p in op)
            nav = (P.get('cash') + inv) if P.get('cash') is not None else 1e9
            cash = P.get('cash', nav)
            sec = sum(val(p) for p in op if (p.get('sector') or 'Khác') == (sp.get('sector') or 'Khác'))
        A = AL.entry_target(nav, cash, inv, sec, len(op), den, risk_mul=sp.get('rmul', 1.0),
                            base_rng=sp.get('base'), cfg=CF)
        return (round(A['theoretical'] / nav * 100, 1), round(A['actual'] / nav * 100, 1),
                [AL.REASON_VI.get(x, x) for x in (A['reasons'] + ([A['binding']] if not A['ok'] else []))],
                A['actual'], nav)
    except Exception as e:
        print('co_lenh loi:', e)
        return None, None, [], None, None


def gui_telegram(hits, ses, cu_mua, cu_ses, den, frac, T=None):
    # Chuong ve dien thoai chi keu TRONG PHIEN, tu 09h00 den 15h00 gio VN.
    now_bao = gio_vn()
    if now_bao.weekday() >= 5 or not (9.0 <= now_bao.hour + now_bao.minute / 60 <= 15.0):
        print('ngoai gio bao chuong (09h00-15h00 T2-T6) - bo qua')
        return

    tok = os.environ.get('TELEGRAM_TOKEN', '').strip()
    chat = os.environ.get('TELEGRAM_CHAT', '').strip()
    if not tok or not chat:
        return

    # MUA only — and only hits whose EVERY required production condition passed.
    mua = [h for h in hits if h['level'] == 'MUA' and h.get('prod_ok')]
    moi = [h for h in mua if cu_ses != ses or h['sym'] not in cu_mua]
    if not moi:
        return []

    dong = [f"\U0001F534 *{len(moi)} mã đủ TOÀN BỘ điều kiện PROD* — phiên {ses}", '']
    for h in moi:
        theo, thuc, ly, tien, nav = co_lenh(h, T or {}, den)
        size = (f"cỡ PROD *{theo:.1f}% NAV*" if theo is not None else "cỡ: không tính được")
        if thuc is not None and theo is not None and abs(thuc - theo) > 0.05:
            size += f" → còn vào được *{thuc:.1f}%* ({', '.join(ly) or 'giới hạn'})"
        if tien and nav:
            size += f" = *{tien/1e6:,.0f} triệu* trên NAV hiện tại {nav/1e9:.2f} tỷ"
        dong.append(
            f"*{h['sym']}*  {h['price']}  ({h['pct']:+.2f}%)\n"
            f"   vol {h['volr']}× TB20 · GTGD {h['gtgd']} tỷ · điểm {h['score']:.0f} · "
            f"dòng tiền {h['ordimb']}× (≥ {h['ordimb_min']})\n"
            f"   {size}")
    dong += ['', f"Đèn thị trường *{den}* · phiên đã đi {frac*100:.0f}%"]

    try:
        r = requests.post(
            f'https://api.telegram.org/bot{tok}/sendMessage',
            json={'chat_id': chat, 'text': '\n'.join(dong),
                  'parse_mode': 'Markdown', 'disable_web_page_preview': True},
            timeout=20)
        print('telegram:', 'da gui' if r.ok else f'HONG {r.status_code} {r.text[:120]}')
        return [h['sym'] for h in moi] if r.ok else []
    except Exception as e:
        print('telegram loi:', type(e).__name__, e)


def loai_so_tay():
    """Ma anh Son loai tay o So tay. Doc THANG manual.json nam ngay canh file nay,
    de loai mot ma la no im chuong ngay luot quet sau — khong phai cho toi 19h30.

    Co y KHONG import manual.py: file do nam o repo private, khong duoc day sang
    day. Vai dong doc JSON re hon nhieu so voi viec dong bo them mot file nua."""
    try:
        with open('manual.json', encoding='utf-8') as f:
            o = json.load(f)
    except Exception:
        return set()
    out = set()
    for w in (o.get('loai') or []):
        s = str((w.get('sym') if isinstance(w, dict) else w) or '').strip().upper()
        if s.isalnum() and 3 <= len(s) <= 10:
            out.add(s)
    return out


def quotes_snapshot(syms, chunk=40):
    """FireAnt Markets/Quotes, nhieu ma mot lan goi. Tra ve {sym: row}."""
    out = {}
    for k in range(0, len(syms), chunk):
        part = syms[k:k + chunk]
        for a in range(3):
            try:
                r = requests.get(BASE + '/Markets/Quotes', params={'symbols': ','.join(part)},
                                 headers=H, timeout=40)
                d = r.json()
                if isinstance(d, list):
                    for x in d:
                        if x.get('Symbol'):
                            out[str(x['Symbol']).upper()] = x
                    break
            except Exception:
                time.sleep(1.2 * (a + 1))
    return out


def _hash_ok(T):
    return bool(T.get('prod_config_hash')) and isinstance(T.get('cfg'), dict)


def flow_obs(ses, now, rows, syms):
    """Append one line of Condition-9 observability evidence per scan: how many
    symbols already carry BuyCount/SellCount/BuyQuantity/SellQuantity at this
    minute. Answers "is OrdImb observable before the close?" with real data."""
    def has(r, k):
        try:
            return float(r.get(k) or 0) > 0
        except Exception:
            return False
    n_oi = sum(1 for r in rows.values() if ordimb_of(r) is not None)
    rec = dict(at=now.isoformat(timespec='seconds'), session=ses, expected=len(syms),
               received=len(rows),
               buy_count=sum(1 for r in rows.values() if has(r, 'BuyCount')),
               sell_count=sum(1 for r in rows.values() if has(r, 'SellCount')),
               buy_qty=sum(1 for r in rows.values() if has(r, 'BuyQuantity')),
               sell_qty=sum(1 for r in rows.values() if has(r, 'SellQuantity')),
               ordimb=n_oi)
    try:
        os.makedirs('obs', exist_ok=True)
        with open(f"obs/flow_{now.strftime('%Y-%m')}.jsonl", 'a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
    except Exception as e:
        print('obs loi:', e)
    return rec


def main():
    if not os.path.exists('thresholds.json'):
        sys.exit('HONG: khong co thresholds.json — repo private chua day sang')
    T = json.load(open('thresholds.json', encoding='utf-8'))
    CF = dict(T.get('cfg') or {})
    # Dieu kien 9 la dieu kien PROD: cfg thieu khoa use_ordimb thi van BAT BUOC (fail safe).
    if CF:
        CF.setdefault('use_ordimb', True)
    U = T.get('spec_u') or {}
    spec_ok = _hash_ok(T) and bool(U) and T.get('spec_version') == SP.SPEC_VERSION
    BO = loai_so_tay()
    syms = {k: v for k, v in T['syms'].items() if k not in BO}
    if BO:
        print(f'bo qua {len(BO)} ma anh Son loai tay: {" ".join(sorted(BO))}')
    cu_mua, cu_ses = doc_live_cu()

    now = gio_vn()
    today = now.date().isoformat()
    frm = (now.date() - dt.timedelta(days=21)).isoformat()   # du dai de qua ky nghi Tet
    frac = clock_frac(now)
    phien_mo = now.weekday() < 5 and 9.0 <= (now.hour + now.minute / 60) <= 15.1

    rows = {}; loi = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for s, r in zip(syms, ex.map(lambda s: latest_row(s, frm, today), syms)):
            if r:
                rows[s] = r
            else:
                loi.append(s)

    base = dict(asof=now.isoformat(timespec='seconds'), base_session=T['asof'],
                prod_config_hash=T.get('prod_config_hash'), spec_version=T.get('spec_version'),
                ordimb_min=CF.get('ordimb_min', T.get('ordimb_min')), universe=len(syms))
    if not rows:
        out = dict(base, session=None, open=False, frac=round(frac, 3), scanned=0, hits=[],
                   status='DATA_DEGRADED',
                   source_health=dict(status='DOWN', expected=len(syms), scanned=0, coverage=0.0,
                                      missing=sorted(loi)[:200], source='FireAnt HistoricalQuotes'),
                   note='Chưa lấy được dữ liệu từ FireAnt — KHÔNG phải "không có tín hiệu".',
                   alerted=dict(session=cu_ses, syms=sorted(cu_mua)))
        json.dump(out, open('live.json', 'w', encoding='utf-8'), ensure_ascii=False)
        print('khong co du lieu phien hom nay — DATA_DEGRADED')
        return

    from collections import Counter
    ses = Counter(str(r.get('Date', ''))[:10] for r in rows.values()).most_common(1)[0][0] or today
    # ---- NGUON DONG TIEN THU HAI (audit 24/09/2026) ----
    # FireAnt Markets/Quotes: snapshot song, CUNG dinh nghia 4 truong (so lenh +
    # KL dat mua/ban), khop HistoricalQuotes 147/147 ma khi doi chung sau phien.
    # Dung de LAP CHO TRONG khi HistoricalQuotes chua co BuyCount (HNX cong bo tre).
    # Khong bao gio ghi de mot gia tri da co; ghi ro nguon vao `ordimb_source`.
    of_src = {}
    try:
        snap = quotes_snapshot(list(rows))
        for s_, x in snap.items():
            r = rows.get(s_)
            if not r or str(x.get('Date', ''))[:10] != str(r.get('Date', ''))[:10]:
                continue
            if ordimb_of(r) is None and ordimb_of(x) is not None:
                for k in ('BuyCount', 'BuyQuantity', 'SellCount', 'SellQuantity'):
                    r[k] = x.get(k)
                of_src[s_] = 'fireant.Markets/Quotes'
    except Exception as e:
        print('nguon dong tien thu hai loi:', type(e).__name__, e)
    if ses != today or not phien_mo:
        phien_mo = False
        frac = 1.0
    # The spec describes the session RIGHT AFTER the nightly build (T['asof']).
    # Evaluating it against an older/already-built session, or after a missed
    # build, would double-count today inside the 20-day windows -> no MUA then.
    def _weekdays_between(a, b):
        try:
            d0, d1 = dt.date.fromisoformat(a), dt.date.fromisoformat(b)
        except Exception:
            return 99
        n, d = 0, d0 + dt.timedelta(days=1)
        while d < d1:
            n += d.weekday() < 5
            d += dt.timedelta(days=1)
        return n
    prev_ses = Counter(r.get('_prev') for r in rows.values() if str(r.get('Date', ''))[:10] == ses
                       and r.get('_prev')).most_common(1)
    prev_ses = prev_ses[0][0] if prev_ses else None
    spec_for_session = bool(T.get('asof')) and ses > T['asof'] and (
        prev_ses == T['asof'] if prev_ses else _weekdays_between(T['asof'], ses) == 0)
    if not spec_for_session:
        print(f"dac ta toi {T.get('asof')} khong danh cho phien {ses} — khong bao MUA")
    spec_ok = spec_ok and spec_for_session
    stale = sorted(s for s, r in rows.items() if str(r.get('Date', ''))[:10] != ses)
    fresh = {s: r for s, r in rows.items() if s not in stale}
    obs = flow_obs(ses, now, fresh, syms)
    obs_extra = dict(filled_from_quotes=len(of_src))

    hits = []
    for s, r in fresh.items():
        t = syms[s]
        sp = t.get('spec')
        try:
            close = float(r.get('PriceClose') or 0); basic = float(r.get('PriceBasic') or 0)
            vol = float(r.get('Volume') or 0); tv = float(r.get('TotalValue') or 0)
        except Exception:
            continue
        if close <= 0 or basic <= 0:
            continue
        pct = close / basic - 1
        vma = t.get('vma20') or 0
        volr = vol / vma if vma else 0.0
        volr_proj = volr / frac if frac > 0 else volr
        tv_proj = tv / frac if frac > 0 else tv
        if spec_ok and sp:
            res = SP.evaluate(sp, r, U, CF)
            lvl, why = SP.classify(res, CF)
        else:
            # Old thresholds without a spec: fail SAFE. Nothing can be MUA because the
            # production conditions cannot be proven. Show movers only.
            res = dict(valid=True, all_ok=False, passed=[], missing=['spec'], required=['spec'],
                       values=dict(pct=pct, volr=volr, ordimb=ordimb_of(r),
                                   ordimb_available=ordimb_of(r) is not None, score=t.get('score')))
            lvl, why = (None, 'SPEC_MISSING')
        dang_cam = bool(t.get('dang_cam'))
        if lvl == 'MUA' and dang_cam:
            lvl, why = 'THEO_DOI', 'ALREADY_HELD'
        if lvl is None and pct * 100 >= DE_MAT_PCT and t.get('state') in ('cho', 'fa'):
            lvl, why = 'DE_MAT', why
        if lvl is None:
            continue
        v = res['values']
        oi = v.get('ordimb')
        hits.append(dict(
            sym=s, name=t['name'], level=lvl, reason=why, fa=(t.get('state') == 'fa'),
            fund=t.get('fund'),
            price=round(close / 1000, 2), ref=round(basic / 1000, 2),
            pct=round(pct * 100, 2), need_px=t['need_px'],
            volr=round(v.get('volr') or volr, 2), volr_proj=round(volr_proj, 2),
            need_vol=t['need_vol'], vol=int(vol),
            gtgd=round(tv / 1e9, 1), gtgd_proj=round(tv_proj / 1e9, 1),
            score=(round(v['score'], 1) if v.get('score') is not None else t.get('score')),
            score_prev=t.get('score'), base=t['base'],
            ordimb=(None if oi is None else round(oi, 4)),
            ordimb_min=CF.get('ordimb_min'),
            ordimb_available=bool(v.get('ordimb_available')),
            ordimb_asof=(now.isoformat(timespec='seconds') if oi is not None else None),
            ordimb_source=(of_src.get(s, 'fireant.HistoricalQuotes') if oi is not None else None),
            required_conditions=res.get('required', []),
            passed_conditions=res.get('passed', []),
            missing_conditions=res.get('missing', []),
            prod_ok=bool(res.get('all_ok')),
            size_pct=t.get('size_pct'), size_tran=t.get('size_tran'),
            dang_cam=dang_cam,
            cond={SP.labels(CF).get(k, k) if CF else k: (k in res.get('passed', []))
                  for k in res.get('required', [])},
            miss=[SP.labels(CF).get(k, k) if CF else k for k in res.get('missing', [])],
        ))

    order = {'MUA': 0, 'SAP_DU': 1, 'DE_MAT': 2, 'THEO_DOI': 3}
    hits.sort(key=lambda x: (order[x['level']], -x['pct']))

    cov = len(fresh) / max(1, len(syms))
    oi_cov = obs['ordimb'] / max(1, len(fresh))
    degraded = (cov < MIN_COVERAGE) or (not spec_ok and spec_for_session)
    health = dict(status=('OK' if not degraded else 'DEGRADED'), expected=len(syms), scanned=len(fresh),
                  coverage=round(cov, 3), missing=sorted(set(loi) | set(stale))[:200],
                  stale=stale[:50], price_coverage=round(cov, 3),
                  ordimb_coverage=round(oi_cov, 3), freshness=ses,
                  source='FireAnt HistoricalQuotes (+ Markets/Quotes cho dong tien)',
                  ordimb_filled_from_quotes=obs_extra['filled_from_quotes'],
                  spec_ok=spec_ok, spec_for_session=spec_for_session)
    out = dict(base,
               session=ses, open=phien_mo, frac=round(frac, 3),
               scanned=len(fresh),
               status=('DATA_DEGRADED' if degraded else ('OK' if spec_for_session else
                       ('SPEC_STALE' if ses > (T.get('asof') or '') else 'BUILD_DONE'))),
               source_health=health,
               hits=hits, de_mat_pct=DE_MAT_PCT,
               n_mua=sum(1 for h in hits if h['level'] == 'MUA'),
               n_de_mat=sum(1 for h in hits if h['level'] == 'DE_MAT'),
               n_cho_dong_tien=sum(1 for h in hits if h.get('reason') == 'WAITING_FOR_FLOW_CONFIRMATION'))
    da_keu = gui_telegram(hits, ses, cu_mua, cu_ses, T.get('light', 'VANG'), frac, T) or []
    out['alerted'] = dict(session=ses, syms=sorted((cu_mua if cu_ses == ses else set()) | set(da_keu)))
    json.dump(out, open('live.json', 'w', encoding='utf-8'), ensure_ascii=False)
    print(f"quét {len(fresh)}/{len(syms)} mã ({cov:.0%}) · phiên {ses} · đã đi {frac*100:.0f}% "
          f"· dòng tiền có {obs['ordimb']}/{len(fresh)} · {out['n_mua']} MUA · "
          f"{out['n_cho_dong_tien']} chờ dòng tiền · trạng thái {out['status']}")
    for h in hits[:10]:
        print(f"  [{h['level']:8s}] {h['sym']:5s} {h['pct']:+6.2f}% vol {h['volr']:.2f}× "
              f"GTGD {h['gtgd']:.0f} tỷ OI {h['ordimb']}" + (f" | thiếu: {', '.join(h['miss'])}" if h['miss'] else ''))


if __name__ == '__main__':
    main()
