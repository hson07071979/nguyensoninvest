# -*- coding: utf-8 -*-
"""Mua do theo KL du phong, nhac ban T+3, den tam tinh, cfg co null (28/09/2026).
Run: python3 -m unittest tests/test_mua_do_du_phong.py -v"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import live_scan as LS
import exit_rules as ER
import regime_live as RL

CF = dict(vol_floor=2.0, gtgd_min=15e9, stage1=1.0, sell_from=3)


def res(missing, avail=False):
    return dict(missing=list(missing), values=dict(ordimb_available=avail))


class DuPhong(unittest.TestCase):
    def test_luat_1_5_va_1_8(self):
        # 14:23 (frac 0,89): KL 1,6x -> du phong 1,80x -> MUA DO
        self.assertTrue(LS.du_phong_ok(res(['vol', 'ordimb']), CF, 1.62, 50e9, 0.89)[0])   # 1,62/0,89 = 1,82x
        # KL hien tai 1,45x < 1,5x -> khong
        self.assertFalse(LS.du_phong_ok(res(['vol', 'ordimb']), CF, 1.45, 50e9, 0.70)[0])
        # du phong chi 1,7x -> khong
        self.assertFalse(LS.du_phong_ok(res(['vol', 'ordimb']), CF, 1.53, 50e9, 0.90)[0])

    def test_chi_bu_kl_va_gtgd(self):
        # thieu bien do / diem -> KHONG bao gio du phong
        self.assertFalse(LS.du_phong_ok(res(['pct', 'ordimb']), CF, 3.0, 50e9, 0.8)[0])
        self.assertFalse(LS.du_phong_ok(res(['vol', 'score', 'ordimb']), CF, 3.0, 50e9, 0.8)[0])
        # DK9 da co so (sau phien) -> khong con la mua do
        self.assertFalse(LS.du_phong_ok(res(['vol', 'ordimb'], avail=True), CF, 1.9, 50e9, 0.95)[0])
        # du het roi (chi thieu DK9) -> khong phai du phong (mua do thuong lo)
        self.assertFalse(LS.du_phong_ok(res(['ordimb']), CF, 2.5, 50e9, 0.9)[0])

    def test_gtgd_du_phong(self):
        self.assertTrue(LS.du_phong_ok(res(['gtgd', 'ordimb']), CF, 2.5, 13e9, 0.8)[0])
        self.assertFalse(LS.du_phong_ok(res(['gtgd', 'ordimb']), CF, 2.5, 10e9, 0.8)[0])

    def test_khung_gio_14h_14h45(self):
        self.assertEqual((LS.MUA_DO_TU, LS.MUA_DO_DEN), (14.0, 14.75))

    def test_duong_cong_kl_do_that(self):
        # trung vi do 28/09: 14:11 -> 0,84; 14:23 -> 0,89; 14:29 -> 0,92 (sai lech <= 0,03)
        import datetime as dt
        for hh, mm, f in ((14, 11, 0.835), (14, 23, 0.893), (14, 29, 0.916), (13, 29, 0.646)):
            self.assertLess(abs(LS.clock_frac(dt.datetime(2026, 9, 28, hh, mm)) - f), 0.03)


class NhacBan(unittest.TestCase):
    def test_t_cong_3(self):
        self.assertEqual(LS.phien_cong('2026-09-25', 3), '2026-09-30')   # T6 -> T4
        self.assertEqual(LS.phien_cong('2026-09-28', 3), '2026-10-01')


class CfgNull(unittest.TestCase):
    def test_exit_rules_bo_qua_null(self):
        # thresholds.json ghi mo_window = null -> truoc 28/09: TypeError, chuong thoat hong tu 24/09
        C = dict(sell_from=3, mo_by=3, mo_need=0.01, mo_window=None, valve_min=None, t_valve=4,
                 stop=-0.07, hard_stop=-0.10, profit_lock=[[0.08, 0.02], [0.12, 0.05]], big_win=0.19,
                 conf=2, trail_fast=10, trail_ma=30, use_orange_cut=True, orange_cut_only_if_worse=True)
        d = ER.decide(C, 0.001, 0.005, 3)
        self.assertEqual(d['rule'][:8], 'Momentum')
        d = ER.decide(C, 0.08, 0.08, 9, light_today='CAM', light_entry='VANG')
        self.assertTrue(d['rule'].startswith('Đèn Cam'))


class DenTamTinh(unittest.TestCase):
    def test_step_ngay_phan_phoi_thu_5_ra_cam(self):
        st = RL.empty_state(dict(use_ftd=True))
        st.update(g1=1000.0, g1_hist=[900.0] * 199, vc_hist=[1700.0] * 49, vc_prev=1800.0, vv_prev=100.0,
                  dd=[(3, 1810.0), (5, 1805.0), (8, 1800.0), (12, 1795.0)])
        l, _, info = RL.step(st, 0.0, 1795.0, 120.0)       # -0,28%, KL cao hon -> ngay phan phoi
        self.assertEqual((info['dcount'], l), (5, 'CAM'))
        l2, _, _ = RL.step(st, 0.0, 1795.0, 90.0)          # KL thap hon -> khong
        self.assertEqual(l2, 'VANG')                        # 4 ngay phan phoi >= 3 -> Vang


if __name__ == '__main__':
    unittest.main()
