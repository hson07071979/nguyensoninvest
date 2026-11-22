# -*- coding: utf-8 -*-
"""SO HE THONG NHIN TU PHIEN DANG QUET (audit 22/11/2026, doi chieu 310 phien chuong vs bo may).
  * Lenh do truot DK9 toi phien ban (held+1 >= sell_from) bi bo may BAN ATC truoc khi mua -> tien / cho nganh /
    tran tong von duoc tra lai. Ca that: HAH 20/01/2026 (chuong bao nham 'tran tong von'), DRC thay AAA
    15/06/2021 (chuong bao MUA nham ma).
  * Cua V xet SAU cua chinh: ma cua chinh vua duoc luot chiem tien / nganh truoc.
  * Toi (bo may da chay cho phien): ma khong nam trong lenh bo may thi LUON co ly do khong vao.
Run: python3 -m unittest tests/test_so_phien.py -v"""
import datetime as dt
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import live_scan as LS

SES = '2026-11-24'
CF = dict(max_unconf=1, sell_from=3, rank_mode='score_volr', stage1=1.0, base_size=0.42, max_pos=0.5,
          max_total=1.0, max_pos_n=12, min_size=0.02, sector_cap=0.30, nth_mul=[2, 0.5],
          fee_sell=0.0025, slip=0.002, v_door=True, v_size=0.30, v_max_n=3, v_per_day=1)
NAV = 10e9


def T_(positions, cash, asof='2026-11-21', ses=SES):
    return dict(asof=asof, _ses=ses, light='XANH', cfg=CF,
                book=dict(nav=NAV, cash=cash, positions=positions),
                syms={s: dict(spec=dict(sector=sec, base=0.12, rmul=1.0)) for s, sec in
                      (('AAA', 'HC'), ('BBB', 'CK'), ('HAH', 'VT'))})


def h(sym, score, volr):
    return dict(sym=sym, score=score, volr=volr, level='SAP_DU', prod_ok=False, mua_do=True, dang_cam=False)


class SoPhien(unittest.TestCase):
    def setUp(self):
        self._d = LS.doi_ngua_live
        LS.doi_ngua_live = lambda *a, **k: None

    def tearDown(self):
        LS.doi_ngua_live = self._d

    def test_lenh_do_ban_hom_nay_tra_cho_nganh(self):
        # DCM (HC, 30% NAV) truot DK9, giu 2 phien -> hom nay T+3 ban ATC: AAA (HC) duoc vao (ca DRC/AAA 15/06/2021)
        T = T_([dict(sym='DCM', sector='HC', value=3.0e9, held=2, probe_fail=True, stage=3)], cash=7.0e9)
        hits = [h('AAA', 90, 3.0), h('BBB', 60, 2.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        m = {x['sym']: x for x in hits}
        self.assertFalse(m['AAA'].get('khong_mua'))
        self.assertEqual(m['BBB']['khong_mua'], 'max_unconf')      # AAA thanh lenh do treo moi

    def test_lenh_do_chua_toi_phien_ban_van_giu_cho(self):
        # giu 1 phien (T+2 hom nay) -> chua ban duoc -> van treo: het luot mua do
        T = T_([dict(sym='DCM', sector='HC', value=3.0e9, held=1, probe_fail=True, stage=3)], cash=7.0e9)
        hits = [h('AAA', 90, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertEqual(hits[0]['khong_mua'], 'max_unconf')

    def test_het_tien_nhung_lenh_do_ban_giai_phong(self):
        # ca HAH 20/01/2026: 2 ma lon gan het tien + PHR do truot ban hom nay -> du cho mua HAH
        T = T_([dict(sym='GAS', sector='DIEN', value=4.87e9, held=13),
                dict(sym='PLX', sector='DK', value=4.91e9, held=8),
                dict(sym='PHR', sector='HC', value=0.22e9, held=2, probe_fail=True, stage=3)], cash=0.0)
        hits = [h('HAH', 70, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertFalse(hits[0].get('khong_mua'))
        # book da la cua chinh phien (toi) -> khong dieu chinh
        T2 = dict(T, asof=SES)
        op, nav, cash = LS.so_phien(T2)
        self.assertEqual(len(op), 3); self.assertEqual(cash, 0.0)

    def test_cua_v_sau_cua_chinh(self):
        # cua chinh vua lay AAA (HC) hom nay -> ma cua V cung nganh HC con it cho hon
        T = T_([dict(sym='DCM', sector='HC', value=1.0e9, held=10)], cash=9.0e9)
        hits = [h('AAA', 90, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertTrue(T['_them_chinh'] and T['_them_chinh'][0]['sym'] == 'AAA')
        op, nav, cash = LS.so_phien(T, them_chinh=True)
        self.assertIn('AAA', [p['sym'] for p in op])
        sec_hc = sum(p['value'] for p in op if p.get('sector') == 'HC')
        self.assertGreaterEqual(sec_hc, 2.9e9)                    # DCM 1 ty + AAA ~2 ty (tran nganh 30% chan)
        pct, _, _ = LS.cua_v_co(dict(sym='VVV', sector='HC', rmul=1.0), T, CF)
        self.assertEqual(pct, 0.0)

    def test_toi_ma_khong_mua_luon_co_ly_do(self):
        T = T_([dict(sym='DCM', sector='HC', value=1.0e9, held=0)], cash=9.0e9, asof=SES)
        T['signals_today'] = []
        hits = [h('BBB', 60, 2.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertTrue(hits[0].get('khong_mua'))                 # bo may khong mua -> khong de trong


class HetLuotNhipSau(unittest.TestCase):
    """Ma giu luot khong doi, nhip sau co ma MOI du dieu kien mua do nhung het luot -> phai bao ngay."""
    def setUp(self):
        self.sent = []
        self._g = (LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.doi_ngua_live)
        LS.kenh_co = lambda: True
        LS.gui_tin = lambda text, **k: (self.sent.append(text) or True)
        LS.doi_ngua_live = lambda *a, **k: None

    def tearDown(self):
        LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.doi_ngua_live = self._g

    def _h(self, sym, score, volr):
        return dict(h(sym, score, volr), price=12.75, pct=6.7, mua_do_du_phong=False)

    def test_ma_moi_het_luot_bao_mot_lan(self):
        T = T_([], cash=NAV)
        LS.gio_vn = lambda: dt.datetime(2026, 11, 24, 14, 26)
        hits = [self._h('AAA', 90, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        cu = set(LS.gui_telegram(hits, SES, set(), SES, 'XANH', 0.9, T) or [])
        self.assertIn('D:AAA', cu); self.sent.clear()
        LS.gio_vn = lambda: dt.datetime(2026, 11, 24, 14, 36)
        T = T_([], cash=NAV)
        hits = [self._h('AAA', 90, 3.0), self._h('BBB', 50, 1.5)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        cu |= set(LS.gui_telegram(hits, SES, cu, SES, 'XANH', 0.9, T) or [])
        self.assertEqual(len(self.sent), 1)
        self.assertIn('HẾT LƯỢT', self.sent[0]); self.assertIn('*BBB*', self.sent[0]); self.assertIn('AAA', self.sent[0])
        self.assertIn('DK:BBB', cu); self.sent.clear()
        LS.gui_telegram(hits, SES, cu, SES, 'XANH', 0.9, T)
        self.assertEqual(self.sent, [])                           # nhip sau nua: khong bao trung


if __name__ == '__main__':
    unittest.main()
