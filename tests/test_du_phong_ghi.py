# R57 PROD (27/11/2026): lenh DU PHONG chuong da bao phai duoc ghi lai (ma, gia, gio) cho ban dung toi.
import datetime as dt, json, os
import live_scan as L

def _h(sym, uu=1, dp=True, chot=None, km=None, price=72.4):
    return dict(sym=sym, uu_tien=uu, mua_do_du_phong=dp, chot=chot, khong_mua=km, price=price, volr=1.65, volr_proj_curve=1.82)

def test_ghi_va_doi_uu_tien(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    t = dt.datetime(2026, 11, 27, 14, 25, 30)
    assert L.ghi_du_phong([_h('GAS')], '2026-11-27', set(), t) is None          # chua bao -> khong ghi
    r = L.ghi_du_phong([_h('GAS')], '2026-11-27', {'D:GAS'}, t)
    assert r['sym'] == 'GAS' and r['gia'] == 72400 and r['luc'] == '14:25:30'
    L.ghi_du_phong([_h('GAS')], '2026-11-27', {'D:GAS'}, t + dt.timedelta(minutes=5))
    assert L.doc_du_phong()['2026-11-27']['luc'] == '14:25:30'                  # khong ghi de cung ma
    r = L.ghi_du_phong([_h('PLX', price=40.1), _h('GAS', uu=2)], '2026-11-27', {'D:GAS', 'D:PLX'}, t)
    assert r['sym'] == 'PLX' and r['truoc'] == 'GAS' and r['gia'] == 40100     # doi uu tien -> ma moi

def test_khong_ghi_chot_hoac_het_luot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    t = dt.datetime(2026, 11, 27, 14, 25, 30)
    assert L.ghi_du_phong([_h('GAS', chot=1425)], '2026-11-27', {'D:GAS'}, t) is None
    assert L.ghi_du_phong([_h('GAS', km='max_unconf')], '2026-11-27', {'D:GAS'}, t) is None
    assert L.ghi_du_phong([_h('GAS', dp=False)], '2026-11-27', {'D:GAS'}, t) is None
    assert not os.path.exists('du_phong.json')
