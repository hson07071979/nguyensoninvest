# -*- coding: utf-8 -*-
"""S1 profit lock in the PAPER BOOK (portfolio.py) — TOP110 + S1, anh Son 26/09/2026.

Close-based, buy fee in the cost basis, sale only from T+sell_from (3), no intraday stop.
Run: python3 -m unittest tests/test_s1.py -v
"""
import datetime as dt, json, os, shutil, sys, tempfile, unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import exit_rules as ER

S1 = [[0.08, 0.02], [0.12, 0.05]]
CFG = dict(top_n=110, vol_floor=2.0, gtgd_min=15e9, volat_min=0.015, min_mktcap=1e12, min_history=250,
           base_range=0.24, ordimb_min=1.4, use_ordimb=True, score_floor=45, use_top_liquid=True,
           fee_buy=0.0015, fee_sell=0.0025, hard_stop=-0.10, stop=-0.07, use_be=False, profit_lock=S1,
           t_valve=4, big_win=0.19, conf=2, trail_fast=10, trail_ma=30, use_orange_cut=True,
           orange_cut_only_if_worse=True, use_pyramid=False, use_hard_stop=True, sell_from=3, hs_from=3,
           mo_by=3, mo_need=0.01, stage1=1.0, probe_exit='close', base_size=0.42, max_pos=0.5, max_total=1.0,
           max_pos_n=12, sector_cap=0.3, size_map={'XANH': 1.0, 'VANG': 0.6, 'CAM': 0.35, 'DO': 0.2})
DAYS = ['2026-09-21', '2026-09-22', '2026-09-23', '2026-09-24', '2026-09-25', '2026-09-28']
ENTRY = 10000.0; COST = ENTRY * 1.0015


def px(g):            # close that gives rule-basis gain g
    return round(COST * (1 + g), 4)


class Book(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd(); self.tmp = tempfile.mkdtemp()
        for f in ('live_scan.py', 'portfolio.py', 'signal_spec.py', 'allocator.py', 'exit_rules.py'):
            shutil.copy(os.path.join(ROOT, f), self.tmp)
        os.chdir(self.tmp); sys.path.insert(0, self.tmp)
        for m in ('portfolio', 'live_scan', 'exit_rules'):
            sys.modules.pop(m, None)
        import portfolio
        self.P = portfolio

    def tearDown(self):
        os.chdir(self.cwd); sys.path.remove(self.tmp); shutil.rmtree(self.tmp)
        sys.modules.pop('exit_rules', None)

    def run_to(self, asof, closes, override=None):
        path = dict(zip(DAYS, closes))
        if override:
            path.update(override)
        self.P.bars = lambda sym, frm, to: [(d, c, c, c) for d, c in sorted(path.items()) if d <= to]
        self.P.gio_vn = lambda: dt.datetime.fromisoformat(asof + 'T20:00:00')
        T = dict(asof=asof, light='XANH', prod_config_hash='H1', cfg=CFG,
                 light_by_date={d: 'XANH' for d in DAYS if d <= asof},
                 signals_recent=[dict(date=DAYS[0], sym='AAA', name='A', price=ENTRY, score=60, ordimb=1.6,
                                      sector='X', rmul=1.0, base=0.1)],
                 syms={'AAA': dict(name='A', spec=dict(sector='X', base=0.1))})
        json.dump(T, open('thresholds.json', 'w'))
        json.dump(dict(session=asof, hits=[]), open('live.json', 'w'))
        self.P.main()
        return json.load(open('portfolio.json'))

    # ---- Example A: peak +9%, current +1.8%, sellable -> S1 Tier 1 SELL at T+3 close ----
    def test_example_A_tier1_sell(self):
        P = self.run_to(DAYS[3], [ENTRY, px(0.09), px(0.06), px(0.018)])
        self.assertEqual(P['open'], [])
        c = P['closed'][0]
        print('\n[A]', json.dumps({k: c[k] for k in ('sym', 'entry', 'exit', 'held', 'peak', 'pnl_pct', 'reason', 'profit_floor')}, ensure_ascii=False))
        self.assertEqual(c['reason'], 'Khoá lãi S1 (đỉnh ≥8% → sàn +2%)')
        self.assertEqual((c['exit'], c['held'], c['profit_floor']), (DAYS[3], 3, 2.0))

    # ---- Example B: peak +13%, current +4.8%, sellable -> S1 Tier 2 SELL ----
    def test_example_B_tier2_sell(self):
        P = self.run_to(DAYS[3], [ENTRY, px(0.13), px(0.10), px(0.048)])
        c = P['closed'][0]
        print('\n[B]', json.dumps({k: c[k] for k in ('sym', 'entry', 'exit', 'held', 'peak', 'pnl_pct', 'reason', 'profit_floor')}, ensure_ascii=False))
        self.assertEqual(c['reason'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')
        self.assertEqual((c['exit'], c['profit_floor']), (DAYS[3], 5.0))

    # ---- Example C: peak +13%, current +4.8% but T+2 -> NO sale, pending breach shown ----
    def test_example_C_before_t3_pending(self):
        P = self.run_to(DAYS[2], [ENTRY, px(0.13), px(0.048)])
        self.assertEqual(P['closed'], [])
        p = P['open'][0]
        out = {k: p[k] for k in ('sym', 'held', 'peak_gain', 'gain', 'profit_lock_active', 'profit_floor', 'sellable',
                                 'exit_reason', 'pending_exit', 'earliest_sell', 'action')}
        print('\n[C]', json.dumps(out, ensure_ascii=False))
        self.assertFalse(p['sellable']); self.assertIsNone(p['exit_reason'])
        self.assertEqual(p['pending_exit'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')
        self.assertTrue(p['action'].startswith('CHỜ T+3 — KHOÁ LÃI ĐÃ THỦNG'))
        self.assertEqual(p['earliest_sell'], 'T+3')
        # next session T+3: still below the floor -> sold at the T+3 close
        P2 = self.run_to(DAYS[3], [ENTRY, px(0.13), px(0.048), px(0.045)])
        self.assertEqual(P2['closed'][0]['exit'], DAYS[3])
        self.assertEqual(P2['closed'][0]['reason'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')

    def test_before_t3_breach_recovered_at_t3_is_kept(self):
        self.run_to(DAYS[2], [ENTRY, px(0.13), px(0.048)])
        P = self.run_to(DAYS[3], [ENTRY, px(0.13), px(0.048), px(0.07)])
        self.assertEqual(P['closed'], []); self.assertTrue(P['open'][0]['profit_lock_active'])
        self.assertEqual(P['open'][0]['profit_floor'], 5.0)

    # ---- peak state persists across workflow reruns (not recomputed from current bars) ----
    def test_peak_persists_across_runs(self):
        P1 = self.run_to(DAYS[1], [ENTRY, px(0.13)])
        self.assertAlmostEqual(P1['open'][0]['peak'], 0.13, places=6)
        # next run: the data source now returns a LOWER T+1 close (revision / partial window).
        # The book must keep the peak it already recorded, not forget it.
        P2 = self.run_to(DAYS[2], [ENTRY, px(0.13), px(0.11)], override={DAYS[1]: px(0.05)})
        p = P2['open'][0]
        self.assertAlmostEqual(p['peak'], 0.13, places=6)
        self.assertEqual(p['profit_floor'], 5.0)

    def test_peak_79_no_floor_and_80_floor(self):
        P = self.run_to(DAYS[3], [ENTRY, px(0.079), px(0.05), px(0.015)])
        self.assertEqual(P['open'][0]['profit_floor'], None)            # 7.9% -> no floor
        P = self.run_to(DAYS[4], [ENTRY, px(0.079), px(0.05), px(0.015), px(0.03)])
        self.assertEqual(P['closed'], [])

    def test_peak_15_uses_5_not_7(self):
        P = self.run_to(DAYS[3], [ENTRY, px(0.15), px(0.10), px(0.06)])      # 6% > 5% floor: E2 would sell at 7%
        self.assertEqual(P['closed'], []); self.assertEqual(P['open'][0]['profit_floor'], 5.0)


class Decide(unittest.TestCase):
    C = CFG

    def d(self, peak, gain, held=5, **kw):
        return ER.decide(self.C, gain, peak, held, **kw)

    def test_boundaries(self):
        self.assertEqual(self.d(0.079, 0.0)['floor'], None)
        self.assertEqual(self.d(0.08, 0.02)['rule'], 'Khoá lãi S1 (đỉnh ≥8% → sàn +2%)')
        self.assertIsNone(self.d(0.08, 0.021)['rule'])
        self.assertEqual(self.d(0.119, 0.021)['floor'], 0.02)
        self.assertEqual(self.d(0.12, 0.05)['rule'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')
        self.assertEqual(self.d(0.15, 0.06)['floor'], 0.05)
        self.assertIsNone(self.d(0.15, 0.06)['rule'])

    def test_ma10_still_works_above_19(self):
        self.assertEqual(self.d(0.25, 0.15, b10=2)['rule'], 'Trailing MA10 (lãi lớn)')
        self.assertEqual(self.d(0.25, 0.049)['rule'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')

    def test_t1_t2_cannot_sell(self):
        for h in (1, 2):
            x = self.d(0.13, 0.04, held=h)
            self.assertIsNone(x['rule']); self.assertFalse(x['sellable'])
            self.assertEqual(x['pending'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')
        self.assertEqual(self.d(0.13, 0.04, held=3)['rule'], 'Khoá lãi S1 (đỉnh ≥12% → sàn +5%)')


if __name__ == '__main__':
    unittest.main()
