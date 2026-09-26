# -*- coding: utf-8 -*-
"""SPEC v3 (26/09/2026): live_scan.main() end to end, FireAnt mocked.

  * complete session cross-section -> MUA exactly when the engine would buy;
  * VNM 14/01/2026 pattern: the symbol would rank >= 70 against YESTERDAY's
    distribution but < 70 on the session cross-section -> NOT MUA;
  * downloads of the cross-section failing -> never MUA (CROSS_SECTION_INCOMPLETE);
  * thresholds.json of an older spec version -> never MUA.
Run: python -m unittest tests/test_live_xsec.py -v"""
import datetime as dt
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SES, ASOF = '2026-09-28', '2026-09-25'
CFG = dict(top_n=40, vol_floor=1.5, gtgd_min=10e9, volat_min=0.02, min_mktcap=1e12,
           min_history=250, base_range=0.22, use_cond8=False, use_ordimb=True,
           ordimb_min=1.40, score_floor=60, use_top_liquid=True)
SPEC = dict(thr=0.03, vol_s19=19e6, vol_c19=19, rng_s19=19 * 0.04, rng_c19=19,
            tv_s19=19 * 20e9, tv_c19=19, nbars_prev=499, nbars=500, base=0.10,
            blocked=False, npat_yoy=0.5, pts_static=dict(C1=15, A1=10),
            hi52_249=30000, c250=15000, c60=20000)


def row(**kw):
    r = dict(Date=SES + 'T00:00:00', PriceClose=31000, PriceBasic=29000, PriceHigh=31500, PriceLow=29500,
             AdjClose=31000, AdjHigh=31500, AdjLow=29500, MarketCap=31000 * 1e9,
             Volume=5e6, TotalValue=150e9,
             BuyQuantity=3e6, BuyCount=1000, SellQuantity=2e6, SellCount=1000, _prev=ASOF)
    r.update(kw)
    return r


class LiveXsec(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        self.tmp = tempfile.mkdtemp()
        for f in ('live_scan.py', 'signal_spec.py', 'allocator.py', 'exit_rules.py'):
            shutil.copy(os.path.join(ROOT, f), self.tmp)
        os.chdir(self.tmp)
        sys.path.insert(0, self.tmp)
        for m in ('live_scan', 'signal_spec'):
            sys.modules.pop(m, None)
        import live_scan
        self.L = live_scan
        live_scan.gio_vn = lambda: dt.datetime(2026, 9, 28, 14, 20)
        live_scan.quotes_snapshot = lambda syms, chunk=40: {}
        os.environ.pop('TELEGRAM_TOKEN', None)

    def tearDown(self):
        os.chdir(self.cwd)
        sys.path.remove(self.tmp)
        shutil.rmtree(self.tmp)

    def scan(self, others, fail=(), spec_version=None, aaa=None):
        """others: {sym: r12 of the SESSION}; fail: symbols whose download fails."""
        L = self.L
        xs = {s: [1000.0, 1000.0, 19 * 5e9, 19] for s in others}
        xs['AAA'] = [SPEC['c250'], SPEC['c60'], SPEC['tv_s19'], SPEC['tv_c19']]
        T = dict(asof=ASOF, spec_version=spec_version or L.SP.SPEC_VERSION, prod_config_hash='H',
                 cfg=CFG, light='XANH', spec_u=dict(top_n=CFG['top_n'], xs=xs),
                 syms=dict(AAA=dict(name='A', exch='HOSE', spec=SPEC, need_px=30.0, need_vol=1, base=0.1,
                                    state='cho', score=60)))
        json.dump(T, open('thresholds.json', 'w'))
        a = aaa or row()
        L.latest_row = lambda sym, frm, to: dict(a) if sym == 'AAA' else None
        rows = {s: dict(Date=SES + 'T00:00:00', AdjClose=1000.0 * (1 + v), TotalValue=5e9)
                for s, v in others.items()}
        L.phien_row = lambda sym, ses: (L.KHONG_RO if sym in fail else rows.get(sym))
        L.main()
        return json.load(open('live.json', encoding='utf-8'))

    def hit(self, out):
        return next(h for h in out['hits'] if h['sym'] == 'AAA')

    def test_complete_cross_section_mua(self):
        out = self.scan({'S%02d' % i: i / 100 for i in range(100)})
        self.assertEqual(self.hit(out)['level'], 'MUA')
        self.assertEqual(out['source_health']['xsec']['status'], 'COMPLETE')

    def test_vnm_pattern_session_rank_below_70_is_not_mua(self):
        # AAA r12 = 31000/15000 - 1 = 1.0667. 100 others: 69 below it, 31 above
        # -> percentile 69/100 = 0.69 < 0.70 -> L = 0 -> score 53.5 < 60 (with L = 15 it would be 68.5).
        others = {'S%02d' % i: (0.5 if i < 69 else 1.5) for i in range(100)}
        h = self.hit(self.scan(others))
        self.assertNotEqual(h['level'], 'MUA')
        self.assertIn('score', h['missing_conditions'])

    def test_failed_downloads_never_mua(self):
        others = {'S%02d' % i: i / 100 for i in range(100)}
        out = self.scan(others, fail={'S%02d' % i for i in range(60)})
        h = self.hit(out)
        self.assertNotEqual(h['level'], 'MUA')
        self.assertEqual(out['source_health']['xsec']['status'], 'PARTIAL')

    def test_old_spec_version_never_mua(self):
        out = self.scan({'S%02d' % i: i / 100 for i in range(100)}, spec_version=2)
        self.assertEqual(out['n_mua'], 0)

    def test_missing_cond9_never_mua(self):
        out = self.scan({'S%02d' % i: i / 100 for i in range(100)}, aaa=row(BuyCount=None))
        self.assertNotEqual(self.hit(out)['level'], 'MUA')


if __name__ == '__main__':
    unittest.main()
