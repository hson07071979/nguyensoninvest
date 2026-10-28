# -*- coding: utf-8 -*-
"""BÁO LỆNH HARD — workflow hard.yml (28/10/2026), chạy mỗi lần manual.json hoặc thresholds.json đổi.

So khoá `hard` của manual.json trước và sau lần ghi:
  * lệnh mới (chưa huỷ)      -> tin "HARD BUY / HARD SELL"
  * lệnh vừa được hoàn tác   -> tin "HOÀN TÁC"
Gửi qua đúng kênh của lệnh MUA (live_scan.gui_tin: Telegram + ntfy).

Dùng:  python hard_bao.py <manual.json cũ> <manual.json mới>
File cũ không có / hỏng => coi như chưa có lệnh nào (lệnh mới đều báo).
"""
import json
import sys


def doc(path):
    try:
        M = json.load(open(path, encoding='utf-8'))
        h = M.get('hard') if isinstance(M, dict) else None
        return {str(o.get('id')): o for o in (h or []) if isinstance(o, dict) and o.get('id')}
    except Exception:
        return {}


def ngay(d):
    d = str(d or '')
    return f"{d[8:10]}/{d[5:7]}" if len(d) >= 10 else d


def so(x, k=2):
    try:
        return f"{float(x):,.{k}f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    except Exception:
        return str(x)


def dong(o):
    if o.get('loai') == 'mua':
        return (f"🟢 HARD BUY {o.get('sym')} — giá {so(o.get('gia'))} · {so(o.get('pct_nav'), 1)}% NAV · "
                f"phiên {ngay(o.get('ngay'))}")
    return (f"🔴 HARD SELL {o.get('sym')} — giá {so(o.get('gia'))} · {round(float(o.get('phan') or 1) * 100)}% vị thế · "
            f"phiên {ngay(o.get('ngay'))}")


def tin(cu, moi):
    out = []
    for k, o in moi.items():
        if k not in cu and not o.get('huy'):
            out.append(dong(o) + (f"\nGhi chú: {o['ghi_chu']}" if o.get('ghi_chu') else ''))
        elif k in cu and o.get('huy') and not cu[k].get('huy'):
            out.append('↩️ HOÀN TÁC ' + dong(o)[2:])
    return out


def doc_kq(path):
    """thresholds.json -> {id: fill} cua cac lenh Hard bo may da xu ly."""
    try:
        H = (json.load(open(path, encoding='utf-8')) or {}).get('hard') or {}
        return {str(f.get('id')): f for f in (H.get('fills') or []) if isinstance(f, dict) and f.get('id')}
    except Exception:
        return {}


def ket_qua(cu, moi):
    """Lenh vua duoc ban dung toi xu ly (khop / tu choi) -> mot dong moi lenh."""
    out = []
    for k, f in moi.items():
        if k in cu:
            continue
        ten = ('HARD BUY' if f.get('loai') == 'mua' else 'HARD SELL') + f" {f.get('sym')} phiên {ngay(f.get('phien'))}"
        if f.get('ok'):
            them = f" · {so(f.get('pct_thuc'), 1)}% NAV" if f.get('pct_thuc') is not None else ''
            rb = f" (bị chặn bởi {f['rang_buoc']})" if f.get('rang_buoc') else ''
            out.append(f"✅ {ten}: đã {'mua' if f.get('loai') == 'mua' else 'bán'} {int(f.get('sh') or 0):,} cp"
                       .replace(',', '.') + f" giá {so(f.get('gia'))}{them}{rb}")
        else:
            out.append(f"⛔ {ten}: bộ máy TỪ CHỐI — {f.get('ly_do')}")
    return out


def main_kq(a, b):
    L = ket_qua(doc_kq(a), doc_kq(b))
    if not L:
        print('không có kết quả lệnh Hard mới')
        return 0
    from live_scan import gui_tin
    ok = gui_tin('LỆNH HARD — kết quả bản dựng tối\n' + '\n'.join(L), md=False, prio=4, tags=['hand'])
    print('\n'.join(L))
    print('đã gửi' if ok else 'CHƯA GỬI ĐƯỢC (chưa cài kênh nào?)')
    return 0


def main(a, b):
    L = tin(doc(a), doc(b))
    if not L:
        print('không có lệnh Hard mới / hoàn tác')
        return 0
    from live_scan import gui_tin
    noi = '\n\n'.join(L) + '\n\nLệnh tay của anh Sơn trên danh mục hệ thống — sổ cập nhật ở bản dựng tối.'
    ok = gui_tin('LỆNH HARD — anh Sơn đặt tay\n' + noi, md=False, prio=5, tags=['hand'])
    print('\n'.join(L))
    print('đã gửi' if ok else 'CHƯA GỬI ĐƯỢC (chưa cài kênh nào?)')
    return 0


if __name__ == '__main__':
    # python hard_bao.py <manual cũ> <manual mới>          -> báo lệnh vừa đặt / hoàn tác
    # python hard_bao.py --ket-qua <thr cũ> <thr mới>        -> báo bộ máy đã khớp / từ chối
    a = sys.argv[1:]
    if a and a[0] == '--ket-qua':
        sys.exit(main_kq(a[1] if len(a) > 1 else '', a[2] if len(a) > 2 else 'thresholds.json'))
    sys.exit(main(a[0] if a else '', a[1] if len(a) > 1 else 'manual.json'))
