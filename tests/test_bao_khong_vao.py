# -*- coding: utf-8 -*-
"""BAO NHUNG KHONG VAO (anh Son 22/11/2026): "bao du diem mua voi viec bo may mua la 2 chuyen khac nhau".
  * Ma DU DIEM MUA nhung bo may khong mo lenh vi tran nganh / tran tong von / het tien / du 12 ma -> chuong
    VAN BAO, tin RIENG 'DU DIEM MUA — BO MAY KHONG VAO' (kem ly do + co PROD tham khao). Bo may giu luat:
    bo qua ma do, ma ke tiep giu luot (= engine2 'continue').
  * Bao lai khi ly do doi; toi chi bao ket qua DK9, khong nhac ban.
  * Cua V: tran nganh / het tien -> ma ke tiep duoc mua; du so ma V / du 12 ma -> tin rieng.
Run: python3 -m unittest tests/test_bao_khong_vao.py -v"""
import datetime as dt
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_scan as LS

SES = '2026-11-24'
CF = dict(max_unconf=1, sell_from=3, rank_mode='score_volr', stage1=1.0, base_size=0.42, max_pos=0.5,
          max_total=1.0, max_pos_n=12, min_size=0.02, max_sector=0.30, nth_mul=[2, 0.5])


def T_(positions, nav=10e9, cash=None):
    inv = sum(p['value'] for p in positions)
    return dict(asof='2026-11-21', light='XANH', cfg=CF,
                book=dict(nav=nav, cash=(nav - inv) if cash is None else cash, positions=positions),
                syms={s: dict(spec=dict(sector=sec, base=0.12, rmul=1.0)) for s, sec in
                      (('AAA', 'NH'), ('BBB', 'CK'), ('CCC', 'NH'))})


def h(sym, score, volr, **k):
    return dict(dict(sym=sym, score=score, volr=volr, level='SAP_DU', prod_ok=False, mua_do=True, dang_cam=False,
                     price=12.75, pct=6.7, mua_do_du_phong=False), **k)


class BaoKhongVao(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._g = (LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.doi_ngua_live)
        LS.kenh_co = lambda: True
        LS.gui_tin = lambda text, **k: (self.sent.append(text) or True)
        LS.doi_ngua_live = lambda *a, **k: None
        LS.gio_vn = lambda: dt.datetime(2026, 11, 24, 14, 26)

    def tearDown(self):
        LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.doi_ngua_live = self._g

    def test_tran_nganh_bao_rieng_ma_ke_tiep_giu_luot(self):
        # ngan hang (NH) da chiem 30% NAV -> AAA (#1, NH) khong vao, BBB (#2, CK) duoc luot
        T = T_([dict(sym='VCB', sector='NH', value=3.0e9, held=10)])
        hits = [h('AAA', 90, 3.0), h('BBB', 60, 2.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        m = {x['sym']: x for x in hits}
        self.assertEqual(m['AAA']['khong_mua'], 'sector_cap')
        self.assertFalse(m['BBB'].get('khong_mua'))
        cu = set(LS.gui_telegram(hits, SES, set(), SES, 'XANH', 0.9, T) or [])
        self.assertEqual(len(self.sent), 2)
        mua = next(x for x in self.sent if 'MUA DÒ' in x)
        kv = next(x for x in self.sent if 'BỘ MÁY KHÔNG VÀO' in x)
        self.assertIn('*BBB*', mua); self.assertNotIn('*AAA*', mua)
        self.assertIn('*AAA*', kv); self.assertIn('trần ngành', kv); self.assertIn('cỡ PROD tham khảo', kv)
        self.assertIn('D:BBB', cu); self.assertNotIn('D:AAA', cu); self.assertIn('KV:AAA:sector_cap', cu)
        # nhip sau cung ly do -> im lang
        n0 = len(self.sent)
        LS.gui_telegram(hits, SES, cu, SES, 'XANH', 0.95, T)
        self.assertEqual(len(self.sent), n0)
        # ly do doi (het tien mat) -> bao lai
        m['AAA']['khong_mua'] = 'cash'
        cu |= set(LS.gui_telegram(hits, SES, cu, SES, 'XANH', 0.95, T) or [])
        self.assertEqual(len(self.sent), n0 + 1)
        self.assertIn('hết tiền mặt', self.sent[-1]); self.assertIn('KV:AAA:cash', cu)

    def test_ma_thu_hai_cung_nganh_tinh_ca_ma_vua_gianh_luot(self):
        # AAA (NH) gianh luot voi ~25% NAV; NH da co 10% -> CCC (NH) tiep theo vuot tran nganh
        T = T_([dict(sym='VCB', sector='NH', value=1.0e9, held=10)])
        hits = [h('AAA', 90, 3.0), h('CCC', 80, 2.5)]
        LS.danh_dau_max_unconf(hits, dict(T, cfg=dict(CF, max_unconf=5)), SES, 3, den='XANH')
        m = {x['sym']: x for x in hits}
        self.assertFalse(m['AAA'].get('khong_mua'))
        self.assertEqual(m['CCC']['khong_mua'], 'sector_cap')

    def test_du_12_ma(self):
        T = T_([dict(sym='M%02d' % k, sector='S%d' % k, value=0.5e9, held=10) for k in range(12)])
        hits = [h('AAA', 90, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertEqual(hits[0]['khong_mua'], 'max_pos_n')
        LS.gui_telegram(hits, SES, set(), SES, 'XANH', 0.9, T)
        self.assertEqual(len(self.sent), 1); self.assertIn('đủ số mã tối đa', self.sent[0])
        self.assertNotIn('MUA DÒ', self.sent[0])

    def test_het_luot_do_giu_cach_bao_cu(self):
        T = T_([dict(sym='PVT', sector='VT', value=1e9, held=1, probe_fail=True)])
        hits = [h('AAA', 90, 3.0)]
        LS.danh_dau_max_unconf(hits, T, SES, 3, den='XANH')
        self.assertEqual(hits[0]['khong_mua'], 'max_unconf')
        LS.gui_telegram(hits, SES, set(), SES, 'XANH', 0.9, T)
        self.assertEqual(len(self.sent), 1); self.assertIn('HẾT LƯỢT', self.sent[0])
        self.assertNotIn('BỘ MÁY KHÔNG VÀO', self.sent[0])

    def test_toi_dk9_chi_bao_ket_qua_khong_nhac_ban(self):
        LS.gio_vn = lambda: dt.datetime(2026, 11, 24, 18, 30)
        T = T_([dict(sym='VCB', sector='NH', value=3.0e9, held=10)])
        a = h('AAA', 90, 3.0, truot9=True, ordimb=1.1, ordimb_min=1.4, khong_mua='sector_cap')
        b = h('BBB', 80, 3.0, level='MUA', prod_ok=True, mua_do=False, ordimb=1.7, ordimb_min=1.4, khong_mua='sector_cap')
        cu = set(LS.gui_telegram([a, b], SES, set(), SES, 'XANH', 1.0, T) or [])
        txt = '\n'.join(self.sent)
        self.assertIn('MÃ BỘ MÁY KHÔNG VÀO', txt)
        self.assertIn('*AAA* dòng tiền 1.1×', txt); self.assertIn('không đạt', txt)
        self.assertIn('*BBB*', txt); self.assertIn('→ *đạt*', txt)
        self.assertNotIn('bán', txt.replace('Bộ máy', ''))
        self.assertIn('X:AAA', cu); self.assertIn('KM:BBB', cu)


class CuaVKhongVao(unittest.TestCase):
    CFGV = dict(CF, v_door=True, v_size=0.30, v_max_n=3, v_per_day=1, v_hold_cap=40, v_up=0.18, chot_phut=1425)
    SES = '2026-11-24'

    def setUp(self):
        self.tin = []
        self._g = (LS.gui_tin, LS.kenh_co, LS.phien_row)
        LS.gui_tin = lambda text, **kw: (self.tin.append(text) or True)
        LS.kenh_co = lambda: True
        LS.phien_row = lambda sym, ses: None

    def tearDown(self):
        LS.gui_tin, LS.kenh_co, LS.phien_row = self._g

    def test_tran_nganh_ma_ke_tiep_duoc_mua(self):
        T = dict(asof='2026-11-21', cfg=self.CFGV,
                 book=dict(nav=1e9, cash=0.7e9, positions=[dict(sym='VCB', sector='NH', value=0.3e9, held=10)]),
                 cua_v=dict(bat=True, ds=[dict(sym='AAA', can=12000, day=10000, sector='NH', rmul=1.0, vma20=1e6),
                                          dict(sym='BBB', can=20000, day=16600, sector='CK', rmul=1.0, vma20=1e6)]))
        rows = {'AAA': dict(Date=self.SES, PriceClose=12500, Volume=3e6),     # vol 3x -> dung truoc
                'BBB': dict(Date=self.SES, PriceClose=21000, Volume=2e6)}
        da, rec, _ = LS.cua_v_phien(T, self.CFGV, self.SES, dt.datetime(2026, 11, 24, 14, 26), rows, set())
        dm = {x['sym']: x for x in rec['dat']}
        self.assertFalse(dm['AAA']['duoc_mua']); self.assertEqual(dm['AAA']['khong_vao'], 'cho')
        self.assertTrue(dm['BBB']['duoc_mua'])
        self.assertIn('V:BBB', da); self.assertNotIn('V:AAA', da); self.assertIn('VK:AAA:cho', da)
        kv = next(x for x in self.tin if 'BỘ MÁY KHÔNG VÀO' in x)
        self.assertIn('*AAA*', kv); self.assertIn('trần ngành', kv); self.assertIn('30% NAV', kv)


if __name__ == '__main__':
    unittest.main()
