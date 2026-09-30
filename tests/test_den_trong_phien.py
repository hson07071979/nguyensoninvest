# -*- coding: utf-8 -*-
"""Den tam tinh PHAI co trong gio giao dich (30/09/2026): 29-30/09 no rong suot phien vi nen ngay
VN-Index cua DNSE chua co / Quotes chua gan ngay hom nay. Kiem den_tam_tinh voi nguon gia lap."""
import os, sys, json, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import live_scan as LS


def _T():
    st = dict(g1=1000.0, g1_hist=[1000.0] * 205, vc_hist=[1700.0] * 55, vc_prev=1700.0, vv_prev=5e8, dd=[],
              ftd_on=False, ftd_age=0, day1_low=None, cnt=0, ftd_gain=0.012, use_ftd=True, session='2026-09-29')
    return {'asof': '2026-09-29', 'light': 'VANG',
            'regime_live': {'state': st, 'g1_syms': [f'S{k}' for k in range(10)]}}


class T(unittest.TestCase):
    def setUp(self):
        self._q, self._d, self._p = LS.quotes_snapshot, LS.vni_dnse, LS.vni_dnse_trong_phien

    def tearDown(self):
        LS.quotes_snapshot, LS.vni_dnse, LS.vni_dnse_trong_phien = self._q, self._d, self._p

    def test_trong_phien_dung_nen_5_phut_va_dong_phien(self):
        T_ = _T()
        rows = {f'S{k}': dict(Date='2026-09-30T00:00:00', PriceClose=101.0, PriceBasic=100.0) for k in range(6)}
        # 4 ma con lai: Quotes trong phien chua gan ngay hom nay -> van nhan khi phien_mo
        LS.quotes_snapshot = lambda syms: {s: dict(Date='2026-09-29T00:00:00', PriceClose=99.0, PriceBasic=100.0) for s in syms}
        LS.vni_dnse = lambda: [('2026-09-29', 1700.0, 5e8)]          # 1D chua co hom nay
        LS.vni_dnse_trong_phien = lambda ses: (1690.0, 2e8)
        info, loi = LS.den_tam_tinh(T_, '2026-09-30', 0.4, rows=rows, phien_mo=True)
        self.assertIsNone(loi, loi)
        self.assertEqual(info['n_g1'], 10)
        self.assertEqual(info['nguon_vni'], 'DNSE 5 phut')
        self.assertIn(info['light'], ('XANH', 'VANG', 'CAM', 'DO'))

    def test_ly_do_khi_khong_tinh_duoc(self):
        T_ = _T()
        LS.quotes_snapshot = lambda syms: {}
        LS.vni_dnse = lambda: []
        LS.vni_dnse_trong_phien = lambda ses: None
        info, loi = LS.den_tam_tinh(T_, '2026-09-30', 0.4, rows={}, phien_mo=True)
        self.assertIsNone(info); self.assertIn('G1', loi)
        rows = {f'S{k}': dict(Date='2026-09-30', PriceClose=101.0, PriceBasic=100.0) for k in range(10)}
        info, loi = LS.den_tam_tinh(T_, '2026-09-30', 0.4, rows=rows, phien_mo=True)
        self.assertIsNone(info); self.assertIn('DNSE', loi)
        T_['regime_live']['state']['session'] = '2026-09-26'
        info, loi = LS.den_tam_tinh(T_, '2026-09-30', 0.4, rows=rows, phien_mo=True)
        self.assertIsNone(info); self.assertIn('asof', loi)


if __name__ == '__main__':
    unittest.main()
