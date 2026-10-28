# -*- coding: utf-8 -*-
"""Lệnh Hard trong sổ ghi tiến (28/10/2026): vào sổ đúng một lần, mua có trần, bán đúng phần,
giữ đối soát kế toán, vào sổ trễ được chăm sóc từ ngày mua. Không gọi mạng (nến giả)."""
import os, sys, copy, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import portfolio as PF

NGAY = ['2026-10-20', '2026-10-21', '2026-10-22', '2026-10-23', '2026-10-26', '2026-10-27', '2026-10-28']


def _nen(sym, frm, to):
    # gia tho = gia dieu chinh (khong co co tuc), di ngang 20.000 roi len 21.000
    out = []
    for k in range(60):
        out.append((f'2026-08-{k % 28 + 1:02d}' if k < 28 else f'2026-09-{k - 27:02d}', 20000.0, 20000.0, 20100.0))
    out = sorted(set(out))
    for i, d in enumerate(NGAY):
        px = 20000.0 + 150 * i
        out.append((d, px, px, px + 100))
    return [x for x in out if frm <= x[0] <= to]


PF.bars = _nen


def _T(fills, cfg=None):
    c = dict(max_pos=0.5, max_total=1.0, sector_cap=0.3, max_pos_n=12, base_size=0.42)
    c.update(cfg or {})
    return dict(cfg=c, hard=dict(fills=fills), syms={}, prod_config_hash='h', light='XANH')


def _P():
    P = PF.rong()
    P['session_done'] = '2026-10-27'
    return P


C = dict(PF.DEF); C['sell_from'] = 3


class T(unittest.TestCase):
    def test_mua_dung_mot_lan_va_doi_soat(self):
        P = _P(); f = dict(id='a', loai='mua', sym='HPG', phien='2026-10-28', gia=20.9, pct_nav=10, ok=True, sector='Thép')
        T = _T([f])
        nk = []
        PF.ap_hard(P, T, C, f, 'XANH', nk, {}, '2026-10-28', cung_phien=True)
        self.assertEqual(len(P['open']), 1)
        q = P['open'][0]
        self.assertEqual(q['hard'], 'mua'); self.assertEqual(q['sh'] % 100, 0)
        self.assertAlmostEqual(q['sh'] * q['cost_px'] / PF.NAV0, 0.10, delta=0.003)
        self.assertIn('action', q)                     # cung phien: co trang thai cua ra ngay
        self.assertEqual(PF.hard_cho(P, T), [])         # khong vao so lan hai
        P['nav'] = round(P['cash'] + sum(p['sh'] * p['entry_px'] for p in P['open']))
        d = PF.doi_soat(P, C, T['cfg'])
        self.assertTrue(d['ok'], d)

    def test_tran_nganh(self):
        P = _P(); f = dict(id='a', loai='mua', sym='HPG', phien='2026-10-28', gia=20.9, pct_nav=80, ok=True, sector='Thép')
        PF.ap_hard(P, _T([f]), C, f, 'XANH', [], {}, '2026-10-28', cung_phien=True)
        self.assertLessEqual(P['open'][0]['x0']['sector_pct'], 30.5)

    def test_ban_phan_va_lo_100(self):
        P = _P(); nk = []
        f = dict(id='a', loai='mua', sym='HPG', phien='2026-10-20', gia=20.0, pct_nav=10, ok=True, sector='Thép')
        T = _T([f])
        moi = PF.ap_hard_tre(P, T, C, [f], '9999', {}, nk, {}, '2026-10-27')
        P['open'] = PF._cham(P, C, '2026-10-27', 'XANH', nk, {}, '2026-10-27', moi)
        sh0 = P['open'][0]['sh']
        b = dict(id='b', loai='ban', sym='HPG', phien='2026-10-27', gia=20.75, phan=0.5, ok=True)
        PF.ap_hard(P, T, C, b, 'XANH', nk, {}, '2026-10-27', cung_phien=True)
        c = P['closed'][0]
        self.assertEqual(c['hard'], 'ban'); self.assertEqual(c['sh'], int(sh0 * 0.5 // 100 * 100))
        self.assertEqual(c['exit_px'], 20.75)
        self.assertEqual(P['open'][0]['sh'], sh0 - c['sh'])
        P['nav'] = round(P['cash'] + sum(p['sh'] * (p.get('last_val') or p['entry_px']) for p in P['open']))
        self.assertTrue(PF.doi_soat(P, C, T['cfg'])['pnl_reconcile_ok'])
        # ban het
        b2 = dict(id='c', loai='ban', sym='HPG', phien='2026-10-27', gia=20.75, phan=1.0, ok=True)
        PF.ap_hard(P, T, C, b2, 'XANH', nk, {}, '2026-10-27', cung_phien=True)
        self.assertEqual(P['open'], [])

    def test_lo_le(self):
        P = _P(); P['open'] = [dict(sym='ORS', entry='2026-10-20', entry_px=20000.0, cost_px=20030.0, sh=150,
                                    k_adj=1.0, last_val=20750.0, sector='CK')]
        P['cash'] -= 150 * 20030.0
        # 25% cua 150 cp lam tron xuong = 0 cp -> khong du 1 lo (bo may cung tu choi y vay)
        nk = []
        b = dict(id='b', loai='ban', sym='ORS', phien='2026-10-27', gia=20.75, phan=0.25, ok=True)
        PF.ap_hard(P, _T([b]), C, b, 'XANH', nk, {}, '2026-10-27', cung_phien=True)
        self.assertEqual(P['closed'], []); self.assertIn('không đủ 1 lô', nk[0])
        # 100% -> ban het ca lo le
        b2 = dict(id='c', loai='ban', sym='ORS', phien='2026-10-27', gia=20.75, phan=1.0, ok=True)
        PF.ap_hard(P, _T([b2]), C, b2, 'XANH', nk, {}, '2026-10-27', cung_phien=True)
        self.assertEqual(P['closed'][0]['sh'], 150); self.assertEqual(P['open'], [])

    def test_vao_so_tre_duoc_cham_soc(self):
        P = _P(); nk = []
        f = dict(id='a', loai='mua', sym='HPG', phien='2026-10-20', gia=20.0, pct_nav=10, ok=True, sector='Thép')
        T = _T([f])
        moi = PF.ap_hard_tre(P, T, C, [f], '9999', {}, nk, {}, '2026-10-27')
        self.assertEqual(len(moi), 1)
        P['open'] = PF._cham(P, C, '2026-10-27', 'XANH', nk, {}, '2026-10-27', moi)
        q = P['open'][0]
        self.assertEqual(q['last_day'], '2026-10-27'); self.assertEqual(q['held'], 5)
        self.assertTrue(all(k in q for k in PF.TRUONG_BAT_BUOC))
        self.assertTrue(nk[0].startswith('[lệnh phiên 20/10, vào sổ trễ]'))

    def test_ban_ma_khong_cam(self):
        P = _P(); nk = []
        b = dict(id='b', loai='ban', sym='SSI', phien='2026-10-27', gia=20.0, phan=1.0, ok=True)
        PF.ap_hard(P, _T([b]), C, b, 'XANH', nk, {}, '2026-10-27', cung_phien=True)
        self.assertEqual(P['closed'], []); self.assertIn('không cầm', nk[0])
        self.assertEqual(P['hard_done'], ['b'])

    def test_chi_lenh_ok(self):
        P = _P()
        T = _T([dict(id='x', ok=False), dict(id='y', ok=True, loai='mua', sym='A', phien='2026-10-28', gia=1, pct_nav=1)])
        self.assertEqual([f['id'] for f in PF.hard_cho(P, T)], ['y'])


if __name__ == '__main__':
    unittest.main()
