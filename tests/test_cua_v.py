# -*- coding: utf-8 -*-
"""CUA V (R50, PROD tu 11/11/2026) o repo public: so ghi tien (portfolio.py) + chuong trong phien (live_scan.py).

  * Lenh cua V cua bo may (signals door='V') vao so nhu lenh THUONG: khong phai lenh do truot DK9, co v_size x NAV
    (khong nhan den), khong nhoi, khong chiem luot lenh do, khong lam 'lenh thu 3 x0,5' cua cua chinh.
  * Vi the cua V ban bang CUNG luat thoat + tran thoi gian v_hold_cap.
  * Chuong: chi keu khi gia cham muc `can` cua bang theo doi, tu gio chot, 1 ma/phien, moi ma 1 lan; toi khong con
    du thi nhac ban.
Run: python3 -m unittest tests/test_cua_v.py -v
"""
import datetime as dt, json, os, sys, unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_s1 as S1T   # noqa: E402
DAYS, ENTRY, px = S1T.DAYS, S1T.ENTRY, S1T.px
CFGV = dict(S1T.CFG, v_door=True, v_exit='main', v_size=0.15, v_max_n=3, v_per_day=1, v_hold_cap=4, v_up=0.20,
            max_unconf=1, nth_mul=[2, 0.5], chot_phut=1425)


class SoCuaV(S1T.Book):
    def chay(self, asof, closes, sigs, cfg=CFGV, light='VANG'):
        path = dict(zip(DAYS, closes))
        self.P.bars = lambda sym, frm, to: [(d, c, c, c) for d, c in sorted(path.items()) if d <= to]
        self.P.gio_vn = lambda: dt.datetime.fromisoformat(asof + 'T20:00:00')
        T = dict(asof=asof, light=light, prod_config_hash='HV', cfg=cfg,
                 light_by_date={d: light for d in DAYS if d <= asof}, signals_recent=sigs,
                 syms={s['sym']: dict(name=s['sym'], spec=dict(sector=s.get('sector', 'X'), base=0.1)) for s in sigs})
        json.dump(T, open('thresholds.json', 'w'))
        json.dump(dict(session=asof, hits=[]), open('live.json', 'w'))
        self.P.main()
        return json.load(open('portfolio.json'))

    V = dict(date=DAYS[0], sym='VVV', price=ENTRY, score=None, ordimb=None, sector='Y', rmul=1.0, base=None,
             door='V', probe=False, cond9_ok=None, v_up=0.21, v_low=8.3, uu_tien=None)

    def test_vao_so_nhu_lenh_thuong(self):
        P = self.chay(DAYS[0], [ENTRY], [self.V])
        p = P['open'][0]
        self.assertEqual((p['sym'], p['door'], p['cond9']), ('VVV', 'V', 'CUA_V'))
        self.assertFalse(p['probe_fail']); self.assertTrue(p['pyr'])
        # co 15% NAV du den Vang (cua chinh se la 42% x 0,6): khong nhan den
        self.assertAlmostEqual(p['cost'] / 1e9, 0.15, delta=0.002)
        self.assertTrue(any('CỬA V' in i for L in P['log'] for i in L['items']))

    def test_khong_bi_ban_nhu_lenh_do_truot_va_het_tran_thi_ban(self):
        # T+3 dinh >= 1% (qua momentum), T+4 van lai (qua van thoi gian) -> tran 4 phien cua cua V ban
        closes = [ENTRY, px(0.02), px(0.03), px(0.03), px(0.04)]
        P3 = self.chay(DAYS[3], closes[:4], [self.V])
        self.assertEqual(P3['closed'], [])                      # T+3: KHONG ban (lenh do truot thi da ban o day)
        P4 = self.chay(DAYS[4], closes, [self.V])
        self.assertEqual(P4['open'], [])
        self.assertEqual(P4['closed'][0]['reason'], 'Cửa V: hết 4 phiên')

    def test_cua_chinh_truoc_va_cua_v_khong_chiem_luot(self):
        chinh = dict(date=DAYS[0], sym='AAA', price=ENTRY, score=60, ordimb=1.6, sector='X', rmul=1.0, base=0.2,
                     uu_tien=1, n_ung_vien=1, probe=True, cond9_ok=True)
        P = self.chay(DAYS[0], [ENTRY], [self.V, chinh])
        ma = [p['sym'] for p in P['open']]
        self.assertEqual(ma, ['AAA', 'VVV'])                    # cua chinh vao truoc, cua V van duoc mua
        a = next(p for p in P['open'] if p['sym'] == 'AAA')
        self.assertAlmostEqual(a['cost'] / 1e9, 0.42 * 0.6, delta=0.003)

    def test_vi_the_v_khong_tinh_vao_lenh_thu_3(self):
        v2 = dict(self.V, sym='WWW', sector='Z')
        self.chay(DAYS[0], [ENTRY], [self.V, v2], cfg=dict(CFGV, v_per_day=2))
        chinh = dict(date=DAYS[1], sym='AAA', price=ENTRY, score=60, ordimb=1.6, sector='X', rmul=1.0, base=0.2,
                     uu_tien=1, n_ung_vien=1, probe=True, cond9_ok=True)
        P = self.chay(DAYS[1], [ENTRY, ENTRY], [self.V, v2, chinh], cfg=dict(CFGV, v_per_day=2))
        a = next(p for p in P['open'] if p['sym'] == 'AAA')
        # dang cam 2 vi the V nhung lenh cua cua chinh KHONG bi x0,5
        self.assertAlmostEqual(a['cost'] / P['nav'], 0.42 * 0.6, delta=0.004)


class ChuongCuaV(S1T.Book):
    def setUp(self):
        super().setUp()
        import live_scan
        self.L = live_scan
        self.tin = []
        self.L.gui_tin = lambda text, **kw: (self.tin.append(text) or True)
        self.L.kenh_co = lambda: True
        self.L.phien_row = lambda sym, ses: None

    T = dict(asof='2026-11-10', cfg=CFGV,
             book=dict(nav=1e9, cash=1e9, positions=[]),
             cua_v=dict(bat=True, ds=[dict(sym='VVV', can=12000, day=10000, sector='Y', rmul=1.0, vma20=1e6),
                                      dict(sym='WWW', can=20000, day=16600, sector='Z', rmul=1.0, vma20=1e6)]))
    SES = '2026-11-11'

    def rows(self, v, w, kv=2e6, kw=3e6):
        return {'VVV': dict(Date=self.SES, PriceClose=v, Volume=kv), 'WWW': dict(Date=self.SES, PriceClose=w, Volume=kw)}

    def luc(self, hhmm):
        return dt.datetime.fromisoformat(f'{self.SES}T{hhmm}:00')

    def test_truoc_gio_chot_im_lang(self):
        da, rec, nh = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('14:10'), self.rows(12500, 21000), set())
        self.assertEqual((da, self.tin, nh), ([], [], []))

    def test_keu_mot_ma_kl_cao_nhat_va_khong_keu_lai(self):
        da, rec, _ = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('14:26'), self.rows(12500, 21000), set())
        self.assertEqual(da, ['V:WWW'])                         # ca hai du gia, WWW vol 3x > VVV 2x; 1 ma/phien
        self.assertIn('CỬA V', self.tin[0]); self.assertIn('15.0% NAV', self.tin[0]); self.assertIn('VVV', self.tin[0])
        self.assertEqual([x['duoc_mua'] for x in rec['dat']], [True, False])
        da2, _, _ = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('14:31'), self.rows(12500, 21000), {'V:WWW'})
        self.assertEqual(da2, []); self.assertEqual(len(self.tin), 1)

    def test_chua_du_gia_thi_khong_keu(self):
        da, rec, _ = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('14:30'), self.rows(11950, 19900), set())
        self.assertEqual((da, rec['dat'], self.tin), ([], [], []))

    def test_het_cho_va_dac_ta_cu_thi_khong_keu(self):
        T = dict(self.T, book=dict(nav=1e9, cash=1e9, positions=[dict(sym=s, door='V', value=1e8, sector='Q') for s in 'ABC']))
        da, _, _ = self.L.cua_v_phien(T, CFGV, self.SES, self.luc('14:30'), self.rows(12500, 21000), set())
        self.assertEqual(da, [])                                # da du 3 vi the V
        da, _, _ = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('14:30'), self.rows(12500, 21000), set(), hop_le=False)
        self.assertEqual(da, [])
        da, _, _ = self.L.cua_v_phien(dict(self.T, cua_v=dict(bat=False, ds=self.T['cua_v']['ds'])), CFGV, self.SES,
                                      self.luc('14:30'), self.rows(12500, 21000), set())
        self.assertEqual(da, [])

    def test_toi_khong_con_du_thi_nhac_ban(self):
        da, _, nh = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('15:40'), self.rows(12500, 19000), {'V:WWW'})
        self.assertEqual(da, ['VX:WWW'])
        self.assertEqual((nh[0]['sym'], nh[0]['mua'], nh[0]['ban']), ('WWW', self.SES, '2026-11-16'))
        da, _, nh = self.L.cua_v_phien(self.T, CFGV, self.SES, self.luc('15:40'), self.rows(12500, 21000), {'V:WWW'})
        self.assertEqual((da, nh), ([], []))                    # dong cua van du va van dung dau -> giu

    def test_so_ma_chinh_bo_vi_the_v(self):
        self.assertEqual(self.L.so_ma_chinh([dict(sym='A'), dict(sym='B', door='V'), dict(sym='C', door=None)]), 2)


if __name__ == '__main__':
    unittest.main()
