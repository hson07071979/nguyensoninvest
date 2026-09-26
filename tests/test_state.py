# -*- coding: utf-8 -*-
"""STATE MIGRATION + HASH GATE + EXPOSURE (26/09/2026, audit sau deploy TOP110 + S1).

  * Cau hinh PROD doi trong CUNG phien da vao so -> so phai nang cap trang thai
    (khong mua/ban lai, khong sua lich su), mang hash moi, du truong cua ra.
  * Sau moi lan chay: hash so != thresholds, thieu truong, doi soat truot -> thoat ma 1.
  * Moi lenh MUA / NHOI ghi ty trong ma / nganh / tong tren NAV sau khi khop.
Run: python3 -m unittest tests/test_state.py -v
"""
import json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_s1 as S1T   # noqa: E402
DAYS, ENTRY, px = S1T.DAYS, S1T.ENTRY, S1T.px

REQ = ('peak_gain', 'gain', 'profit_lock_active', 'profit_floor', 'sellable', 'pending_exit', 'action')


class State(S1T.Book):
    def rerun(self, asof, closes, h):
        """Chay lai CUNG phien voi thresholds.json mang hash `h`."""
        T = json.load(open('thresholds.json')); T['prod_config_hash'] = h
        json.dump(T, open('thresholds.json', 'w'))
        path = dict(zip(DAYS, closes))
        self.P.bars = lambda sym, frm, to: [(d, c, c, c) for d, c in sorted(path.items()) if d <= to]
        self.P.main()
        return json.load(open('portfolio.json'))

    def strip(self, old_hash):
        """Gia lap so ghi bang ban cu: hash cu, vi the chua co truong S1."""
        P = json.load(open('portfolio.json'))
        P['prod_config_hash'] = old_hash
        for p in P['open']:
            for k in REQ:
                p.pop(k, None)
        json.dump(P, open('portfolio.json', 'w'))
        return P

    def test_migration_same_session(self):
        closes = [ENTRY, px(0.09), px(0.05)]
        self.run_to(DAYS[2], closes)
        before = self.strip('OLDHASH')
        P = self.rerun(DAYS[2], closes, 'H1')
        p = P['open'][0]
        self.assertEqual(P['prod_config_hash'], 'H1')
        for k in REQ:
            self.assertIn(k, p)
        self.assertEqual(p['profit_floor'], 2.0)                 # peak 9% -> floor +2%
        self.assertFalse(p['sellable'])                          # T+2
        self.assertEqual(P['migrations'][0]['from_hash'], 'OLDHASH')
        # khong mua/ban lai, khong sua lich su
        self.assertEqual(P['closed'], before['closed'])
        self.assertEqual(P['cash'], before['cash'])
        self.assertEqual(p['sh'], before['open'][0]['sh'])
        self.assertEqual(p['prod_config_hash'], before['open'][0]['prod_config_hash'])   # hash LUC MUA giu nguyen
        self.assertTrue(P['log'][0]['items'][0].startswith('NÂNG CẤP TRẠNG THÁI SỔ'))
        # chay lai lan nua: khong nang cap them
        P2 = self.rerun(DAYS[2], closes, 'H1')
        self.assertEqual(len(P2['migrations']), 1)

    def test_hard_fail_when_checks_broken(self):
        closes = [ENTRY, px(0.02)]
        self.run_to(DAYS[1], closes)
        P = json.load(open('portfolio.json')); P['checks']['ok'] = False
        json.dump(P, open('portfolio.json', 'w'))
        with self.assertRaises(SystemExit):
            self.rerun(DAYS[1], closes, 'H1')

    def test_buy_records_exposure(self):
        P = self.run_to(DAYS[0], [ENTRY])
        x = P['open'][0]['x0']
        self.assertEqual(x['date'], DAYS[0])
        self.assertGreater(x['pos_pct'], 0)
        self.assertEqual(x['pos_pct'], x['sector_pct'])
        self.assertTrue(any('ngành' in i and 'tổng cổ phiếu' in i for d in P['log'] for i in d['items']))


class DoiSoat(unittest.TestCase):
    def setUp(self):
        import importlib
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.P = importlib.import_module('portfolio')

    def book(self, xp_sector):
        pos = dict(sym='AAA', sector='X', sh=1000, entry_px=100.0, cost_px=100.0, last_val=100.0,
                   x0=dict(pos_pct=10.0, sector_pct=10.0, total_pct=10.0),
                   xp=dict(pos_pct=15.0, sector_pct=xp_sector, total_pct=15.0))
        return dict(nav0=1e6, cash=900000.0, nav=1e6, open=[pos], closed=[])

    def test_pyramid_over_sector_listed_not_failed_when_pyr_caps_false(self):
        C = dict(fee_buy=0.0015)
        o = self.P.doi_soat(self.book(35.0), C, dict(pyr_caps=False, sector_cap=0.3, max_pos=0.5, max_total=1.0))
        self.assertTrue(o['ok']); self.assertEqual(o['pyr_sector_over'][0]['sector_pct'], 35.0)
        o = self.P.doi_soat(self.book(35.0), C, dict(pyr_caps=True, sector_cap=0.3, max_pos=0.5, max_total=1.0))
        self.assertFalse(o['ok'])

    def test_no_125_tolerance_on_max_pos(self):
        b = self.book(20.0); b['open'][0]['x0']['pos_pct'] = 55.0     # 55% > 50% + 0,5 diem
        o = self.P.doi_soat(b, dict(fee_buy=0.0015), dict(max_pos=0.5))
        self.assertFalse(o['max_pos_ok'])


if __name__ == '__main__':
    unittest.main()
