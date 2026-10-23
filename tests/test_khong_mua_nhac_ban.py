# -*- coding: utf-8 -*-
"""Phien 21/10/2026: ORS, DIG, VSC cung du dieu kien; bo may chi mua ORS (max_unconf=1).
(1) live.json phai danh dau DIG/VSC 'khong_mua' de trang khong de chung o 'Du diem mua'.
(2) nhac ban 'thieu Von hoa' cua lan quet som khong duoc song sot khi lan sau cham DAT.
Run: python3 -m unittest tests/test_khong_mua_nhac_ban.py -v"""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import live_scan as LS


def hit(sym, score, level='MUA', prod_ok=True, mua_do=False, dang_cam=False, volr=3.0):
    return dict(sym=sym, score=score, level=level, prod_ok=prod_ok, mua_do=mua_do, dang_cam=dang_cam,
                price=1.0, pct=6.5, volr=volr)


CFG = dict(max_unconf=1, sell_from=3, rank_mode='score_volr')


class KhongMua(unittest.TestCase):
    def test_sau_khi_bo_may_chay_21_10(self):
        # thresholds.json toi 21/10: bo may da mua ORS (held 0) -> DIG, VSC het cho
        T = dict(asof='2026-10-21', cfg=CFG,
                 signals_today=[dict(sym='ORS', date='2026-10-21')],
                 book=dict(positions=[dict(sym='ORS', held=0, probe_fail=False)]))
        hs = [hit('VSC', 48.9, volr=2.86), hit('DIG', 58.8, volr=2.88),
              hit('ORS', 59.3, level='THEO_DOI', prod_ok=True, dang_cam=True, volr=5.33)]   # 21h: ORS da vao so
        n = LS.danh_dau_max_unconf(hs, T, '2026-10-21')
        self.assertEqual(n, 2)
        m = {h['sym']: h for h in hs}
        self.assertNotIn('khong_mua', m['ORS'])
        self.assertEqual(m['DIG']['khong_mua'], 'max_unconf')
        self.assertEqual(m['VSC']['khong_mua_vi'], ['ORS'])
        self.assertEqual(m['DIG']['level'], 'MUA')        # khong doi level / prod_ok
        # thu tu uu tien dung nhu luc bo may chon (ma vua mua van duoc danh so)
        self.assertEqual({s: m[s]['uu_tien'] for s in m}, {'ORS': 1, 'DIG': 2, 'VSC': 3})

    def test_trong_phien_xep_theo_diem(self):
        # thresholds toi qua (20/10), so trong -> ma diem cao nhat chiem cho
        T = dict(asof='2026-10-20', cfg=CFG, book=dict(positions=[]))
        hs = [hit('VSC', 48.9, level='SAP_DU', prod_ok=False, mua_do=True),
              hit('DIG', 58.8, level='SAP_DU', prod_ok=False, mua_do=True),
              hit('ORS', 59.3, level='SAP_DU', prod_ok=False, mua_do=True)]
        LS.danh_dau_max_unconf(hs, T, '2026-10-21')
        self.assertEqual([h['sym'] for h in hs if h.get('khong_mua')], ['VSC', 'DIG'])

    def test_lenh_do_cu_dang_treo_chan_ca_ma_dau(self):
        # PVT truot DK9 hom qua (held 1, probe_fail) -> hom nay (held 2 < 3) van treo -> khong mua ai
        T = dict(asof='2026-09-30', cfg=CFG, book=dict(positions=[dict(sym='PVT', held=1, probe_fail=True)]))
        hs = [hit('AAA', 70, level='SAP_DU', prod_ok=False, mua_do=True)]
        LS.danh_dau_max_unconf(hs, T, '2026-10-01')
        self.assertEqual(hs[0]['khong_mua_vi'], ['PVT'])

    def test_ma_dang_cam_va_khong_co_luat(self):
        T = dict(asof='2026-10-20', cfg=dict(sell_from=3), book=dict(positions=[]))
        hs = [hit('A', 60), hit('B', 50)]
        self.assertEqual(LS.danh_dau_max_unconf(hs, T, '2026-10-21'), 0)
        T['cfg'] = CFG
        hs = [hit('A', 60, dang_cam=True), hit('B', 50)]
        LS.danh_dau_max_unconf(hs, T, '2026-10-21')
        self.assertNotIn('khong_mua', hs[1])               # ma dang cam khong chiem cho


class UuTien(unittest.TestCase):
    def test_vol_lon_vuot_diem_cao_hon_chut(self):
        # A diem 60 vol 2,1x · B diem 59 vol 6x · C diem 50 vol 4x -> diem+vol: B (0,5+1) > A (1+0) = C (0+0,5)
        T = dict(asof='2026-10-20', cfg=CFG, book=dict(positions=[]))
        hs = [hit('A', 60, level='SAP_DU', prod_ok=False, mua_do=True, volr=2.1),
              hit('B', 59, level='SAP_DU', prod_ok=False, mua_do=True, volr=6.0),
              hit('C', 50, level='SAP_DU', prod_ok=False, mua_do=True, volr=4.0)]
        LS.danh_dau_max_unconf(hs, T, '2026-10-22')
        m = {h['sym']: h for h in hs}
        self.assertEqual((m['B']['uu_tien'], m['A']['uu_tien'], m['C']['uu_tien']), (1, 2, 3))
        self.assertNotIn('khong_mua', m['B'])
        self.assertEqual(m['A']['khong_mua_vi'], ['B'])
        # cau hinh cu (chua co rank_mode) -> theo diem nhu truoc
        hs2 = [dict(h) for h in hs]
        for h in hs2: h.pop('uu_tien'); h.pop('khong_mua', None)
        LS.danh_dau_max_unconf(hs2, dict(T, cfg=dict(max_unconf=1, sell_from=3)), '2026-10-22')
        self.assertEqual([h['sym'] for h in sorted(hs2, key=lambda h: h['uu_tien'])], ['A', 'B', 'C'])


class NhacBan(unittest.TestCase):
    def test_bo_nhac_da_xac_nhan_dat(self):
        nhac = [dict(sym='ORS', mua='2026-10-21', ban='2026-10-26', ly_do='… Vốn hoá ≥ 1000 tỷ'),
                dict(sym='TCH', mua='2026-10-21', ban='2026-10-26', ly_do='… Biên độ tăng giá')]
        xn = [dict(sym='ORS', ket_qua='DAT_DK18'), dict(sym='TCH', ket_qua='TRUOT_DK18', thieu=['pct'])]
        out = LS.loc_nhac_ban(nhac, xn, '2026-10-21')
        self.assertEqual([x['sym'] for x in out], ['TCH'])
        # phien khac: khong dung toi
        self.assertEqual(len(LS.loc_nhac_ban(nhac, xn, '2026-10-22')), 2)

    def test_von_hoa_chua_co_so_la_chua_ro(self):
        r = dict(missing=['mcap', 'ordimb'], values=dict(mcap=None))
        self.assertEqual(LS.xet_dk18(r, {})[0], 'CHUA_RO')
        r = dict(missing=['mcap'], values=dict(mcap=9e11))   # co so that, duoi 1.000 ty -> truot
        self.assertEqual(LS.xet_dk18(r, {}), ('TRUOT_DK18', ['mcap']))
        r = dict(missing=['pct', 'mcap'], values=dict(mcap=None))
        self.assertEqual(LS.xet_dk18(r, {})[0], 'CHUA_RO')
        self.assertEqual(LS.xet_dk18(dict(missing=['ordimb'], values={}), {}), ('DAT_DK18', []))



class Max2(unittest.TestCase):
    """PROD tu 23/10/2026: toi da 2 lenh do treo (cfg.max_unconf=2)."""
    CF2 = dict(max_unconf=2, sell_from=3, rank_mode='score_volr')

    def test_trong_phien_hai_ma_dau_duoc_mua(self):
        T = dict(asof='2026-10-20', cfg=self.CF2, book=dict(positions=[]))
        hs = [hit('VSC', 48.9, level='SAP_DU', prod_ok=False, mua_do=True, volr=2.86),
              hit('DIG', 58.8, level='SAP_DU', prod_ok=False, mua_do=True, volr=2.88),
              hit('ORS', 59.3, level='SAP_DU', prod_ok=False, mua_do=True, volr=5.33)]
        self.assertEqual(LS.danh_dau_max_unconf(hs, T, '2026-10-21'), 1)
        m = {h['sym']: h for h in hs}
        self.assertNotIn('khong_mua', m['ORS']); self.assertNotIn('khong_mua', m['DIG'])
        self.assertEqual(m['VSC']['khong_mua_vi'], ['ORS', 'DIG'])

    def test_mot_lenh_cu_treo_con_mot_cho(self):
        T = dict(asof='2026-09-30', cfg=self.CF2, book=dict(positions=[dict(sym='PVT', held=1, probe_fail=True)]))
        hs = [hit('AAA', 70, level='SAP_DU', prod_ok=False, mua_do=True),
              hit('BBB', 50, level='SAP_DU', prod_ok=False, mua_do=True)]
        LS.danh_dau_max_unconf(hs, T, '2026-10-01')
        m = {h['sym']: h for h in hs}
        self.assertNotIn('khong_mua', m['AAA'])
        self.assertEqual(m['BBB']['khong_mua_vi'], ['PVT', 'AAA'])

    def test_sau_khi_bo_may_mua_hai_ma(self):
        T = dict(asof='2026-10-21', cfg=self.CF2,
                 signals_today=[dict(sym='ORS', date='2026-10-21'), dict(sym='DIG', date='2026-10-21')],
                 book=dict(positions=[dict(sym='ORS', held=0, probe_fail=False),
                                      dict(sym='DIG', held=0, probe_fail=False)]))
        hs = [hit('VSC', 48.9, volr=2.86), hit('DIG', 58.8, dang_cam=True, level='THEO_DOI', volr=2.88),
              hit('ORS', 59.3, dang_cam=True, level='THEO_DOI', volr=5.33)]
        self.assertEqual(LS.danh_dau_max_unconf(hs, T, '2026-10-21'), 1)
        self.assertEqual([h['sym'] for h in hs if h.get('khong_mua')], ['VSC'])

if __name__ == '__main__':
    unittest.main()
