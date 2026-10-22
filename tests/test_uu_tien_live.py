# -*- coding: utf-8 -*-
"""Thu tu mua khi nhieu ma cung no (R38): live.json phai mang uu_tien cho trang web.
Tu 22/10/2026 mot nguon duy nhat: live_scan.danh_dau_max_unconf (thay xep_uu_tien_live)."""
import live_scan as L


def _h(sym, score, volr, **k):
    return dict(sym=sym, level=k.pop('level', 'SAP_DU'), mua_do=k.pop('mua_do', True),
                score=score, volr=volr, prod_ok=k.pop('prod_ok', False), **k)


def test_xep_va_khong_mua():
    T = {'cfg': {'rank_mode': 'score_volr', 'max_unconf': 1, 'sell_from': 3}, 'book': {'positions': []}}
    hs = [_h('AAA', 90, 3.0), _h('BBB', 80, 2.1), _h('CCC', 70, 2.5), _h('DDD', 99, 9, level='THEO_DOI', mua_do=False)]
    L.danh_dau_max_unconf(hs, T, '2026-10-22')
    m = {h['sym']: h for h in hs}
    assert m['AAA']['uu_tien'] == 1 and m['AAA']['n_ung_vien'] == 3 and not m['AAA'].get('khong_mua')
    assert {m['BBB']['uu_tien'], m['CCC']['uu_tien']} == {2, 3}
    assert m['BBB']['khong_mua'] and m['CCC']['khong_mua']
    assert m['DDD'].get('uu_tien') is None


def test_dang_cam_khong_xep():
    T = {'cfg': {'rank_mode': 'score_volr'}}
    hs = [_h('AAA', 90, 3.0, dang_cam=True), _h('BBB', 80, 2.1)]
    L.danh_dau_max_unconf(hs, T, '2026-10-22')
    assert hs[0].get('uu_tien') is None and hs[1]['uu_tien'] == 1 and hs[1]['n_ung_vien'] == 1
