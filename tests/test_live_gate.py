# -*- coding: utf-8 -*-
"""Offline regression tests for the P0 gates (audit 23/09/2026):
  * the live scanner never labels MUA when Dieu kien 9 (order flow) is missing
    or below threshold;
  * portfolio.py only auto-books MUA hits with prod_ok=True AND proven Cond9.
Run: python -m unittest discover -s tests"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import signal_spec as SP  # noqa: E402

CFG = dict(top_n=40, vol_floor=1.5, gtgd_min=10e9, volat_min=0.02, min_mktcap=1e12,
           min_history=250, base_range=0.22, use_cond8=False, use_ordimb=True,
           ordimb_min=1.40, score_floor=50, use_top_liquid=True)
U = dict(topn_cut=1e9, r12=[i / 100 for i in range(100)], r3=[i / 100 for i in range(100)])
SPEC = dict(thr=0.03, vol_s19=19e6, vol_c19=19, rng_s19=19 * 0.04, rng_c19=19,
            tv_s19=19 * 20e9, tv_c19=19, shares=1e9, nbars=500, base=0.10,
            blocked=False, npat_yoy=0.5, pts_static=dict(C=15, A=10),
            hi52_249=30000, c250=15000, c60=20000)


def row(**kw):
    r = dict(PriceClose=31000, PriceBasic=29000, PriceHigh=31500, PriceLow=29500,
             Volume=5e6, TotalValue=150e9,
             BuyQuantity=3e6, BuyCount=1000, SellQuantity=2e6, SellCount=1000)
    r.update(kw)
    return r


class SignalGate(unittest.TestCase):
    def cls(self, r, cfg=CFG):
        res = SP.evaluate(SPEC, r, U, cfg)
        return res, SP.classify(res, cfg)

    def test_full_signal_is_mua(self):
        res, (lvl, _) = self.cls(row())
        self.assertTrue(res['all_ok'], res['missing'])
        self.assertEqual(lvl, 'MUA')

    def test_missing_flow_is_never_mua(self):
        for k in ('BuyCount', 'BuyQuantity', 'SellCount', 'SellQuantity'):
            res, (lvl, why) = self.cls(row(**{k: None}))
            self.assertNotEqual(lvl, 'MUA')
            self.assertEqual((lvl, why), ('SAP_DU', 'WAITING_FOR_FLOW_CONFIRMATION'))
            self.assertIn('ordimb', res['missing'])

    def test_flow_below_threshold_is_not_mua(self):
        # (3e6/1000) / (2.2e6/1000) = 1.3636 < 1.40
        res, (lvl, _) = self.cls(row(SellQuantity=2.2e6))
        self.assertFalse(res['all_ok'])
        self.assertNotEqual(lvl, 'MUA')

    def test_cond9_required_when_prod_uses_it(self):
        self.assertIn('ordimb', SP.required_conditions(CFG))

    def test_live_scan_defaults_use_ordimb_on(self):
        src = open(os.path.join(ROOT, 'live_scan.py'), encoding='utf-8').read()
        self.assertIn("CF.setdefault('use_ordimb', True)", src)


class PortfolioGate(unittest.TestCase):
    """Paper book (audit 24/09) = copy of the ENGINE: it books only
    thresholds.json signals_today/signals_recent (engine2 actual entries, Cond9
    already proven with end-of-day data). live.json MUA never books."""
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        for f in ('live_scan.py', 'portfolio.py', 'signal_spec.py', 'allocator.py'):
            shutil.copy(os.path.join(ROOT, f), self.tmp)
        os.chdir(self.tmp)
        sys.path.insert(0, self.tmp)
        for m in ('portfolio', 'live_scan'):
            sys.modules.pop(m, None)
        import portfolio
        self.P = portfolio
        portfolio.gio_vn = lambda: dt.datetime(2026, 9, 23, 20, 0)   # after the nightly build

    def tearDown(self):
        os.chdir(self.cwd)
        sys.path.remove(self.tmp)
        shutil.rmtree(self.tmp)

    def run_book(self, live_mua=False, **sig):
        h = dict(date='2026-09-23', sym='AAA', name='A', price=31000.0, score=60, ordimb=1.5,
                 sector='X', rmul=1.0, base=0.1)
        h.update(sig)
        T = dict(asof='2026-09-23', light='XANH', prod_config_hash='H1', cfg=dict(CFG),
                 light_by_date={'2026-09-23': 'XANH'},
                 signals_today=([] if live_mua else [h]),
                 syms={'AAA': dict(name='A', spec=dict(sector='X', base=0.1))})
        json.dump(T, open('thresholds.json', 'w'))
        json.dump(dict(session='2026-09-23', prod_config_hash='H1',
                       hits=[dict(sym='AAA', level='MUA', prod_ok=True, ordimb=1.5, ordimb_available=True,
                                  price=31.0, score=60)] if live_mua else []), open('live.json', 'w'))
        if os.path.exists('portfolio.json'):
            os.remove('portfolio.json')
        self.P.main()
        return json.load(open('portfolio.json'))

    def test_books_engine_signal(self):
        P = self.run_book()
        self.assertEqual([p['sym'] for p in P['open']], ['AAA'])
        self.assertEqual(P['open'][0]['position_source'], 'engine_signal')
        self.assertTrue(P['checks']['ok'])
        self.assertEqual(P['version'], 2)

    def test_rejects_flow_below_threshold(self):
        self.assertEqual(self.run_book(ordimb=1.381)['open'], [])

    def test_rejects_missing_flow(self):
        self.assertEqual(self.run_book(ordimb=None)['open'], [])

    def test_live_mua_never_books(self):
        self.assertEqual(self.run_book(live_mua=True)['open'], [])

    def test_other_session_signal_not_booked(self):
        self.assertEqual(self.run_book(date='2026-09-22')['open'], [])


if __name__ == '__main__':
    unittest.main()
