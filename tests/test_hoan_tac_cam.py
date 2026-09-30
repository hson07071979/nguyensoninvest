# -*- coding: utf-8 -*-
"""Bo luat Den Cam (30/09/2026): moi lan 'Den Cam — ha 1/3' cua vi the con mo phai duoc hoan tac
trong so ghi tien — tra co, tru tien, xoa lai da chot — va doi soat ke toan van DAT."""
import os, sys, copy, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import portfolio as PF


def _so():
    C = dict(PF.DEF); C['use_orange_cut'] = False
    p = dict(sym='BVH', entry='2026-09-14', entry_px=68000.0, cost_px=68102.0, sh=2500, part=True,
             last_val=73600.0, x0=None)
    ban = dict(sym='BVH', entry='2026-09-14', exit='2026-09-28', sh=1200, pnl_vnd=6376800, pnl_pct=7.8,
               reason=PF.LY_DO_CAM, phan=0.333)
    khac = dict(sym='PLX', entry='2026-09-15', exit='2026-09-21', sh=1300, pnl_vnd=-842595, pnl_pct=-1.73,
                reason='Van thời gian T+4', phan=1.0)
    cash = PF.NAV0 - 3700 * 68102.0 + (1200 * 68102.0 + 6376800) - 842595
    P = dict(open=[p], closed=[ban, khac], log=[], cash=cash, nav0=PF.NAV0)
    P['nav'] = round(P['cash'] + 2500 * 73600.0)
    return P, C


class T(unittest.TestCase):
    def test_hoan_tac_va_doi_soat(self):
        P, C = _so()
        self.assertTrue(PF.doi_soat(P, C)['pnl_reconcile_ok'])
        nk = PF.hoan_tac_ha_cam(P, C, '2026-09-29')
        self.assertEqual(len(nk), 1)
        self.assertEqual(P['open'][0]['sh'], 3700)
        self.assertFalse(P['open'][0]['part'])
        self.assertEqual([c['reason'] for c in P['closed']], ['Van thời gian T+4'])
        d = PF.doi_soat(P, C)
        self.assertTrue(d['pnl_reconcile_ok'] and d['nav_identity'] and d['cash_nonneg'], d)
        self.assertEqual(PF.hoan_tac_ha_cam(P, C, '2026-09-29'), [])          # chay mot lan

    def test_khong_dung_khi_den_cam_bat(self):
        P, C = _so(); C['use_orange_cut'] = True
        P0 = copy.deepcopy(P)
        self.assertEqual(PF.hoan_tac_ha_cam(P, C, 'x'), [])
        self.assertEqual(P, P0)


if __name__ == '__main__':
    unittest.main()
