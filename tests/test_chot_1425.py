# -*- coding: utf-8 -*-
"""R48 CHOT LENH DO 14:25 (anh Son duyet 05/11/2026) — lop live.
Ma du DK1-8 voi KL khop that tinh toi 14:25 (nen 1 phut Vietcap) -> xep diem+Vol -> #1 la lenh do.
Truoc 14:25 khong bao mua; khong ai du -> bao ATC theo KL du phong nhu cu; toi ma chot dung TRUOC.
Run: python3 -m unittest tests/test_chot_1425.py -v"""
import datetime as dt
import json, os, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import live_scan as LS
import signal_spec as SP

SES = '2026-11-04'
TZ = dt.timezone(dt.timedelta(hours=7))
CF = dict(chot_phut=1425, vol_floor=2.0, gtgd_min=15e9, volat_min=0.015, min_mktcap=1000e9, min_history=250,
          base_range=0.24, score_floor=45, use_top_liquid=True, use_cond8=False, dk5_lo=0.0, dk5_hi=0.0,
          rank_mode='score_volr', max_unconf=1, sell_from=3, stage1=1.0, ordimb_min=1.4)


def sp_mau(vma=7.0e6, tvma=90e9, rs=75.0, mom=0.6, pts=None):
    # 19 phien truoc: KL vma, GTGD tvma, bien dong 3%
    return dict(thr=0.056, in_topn_prev=True, vol_s19=vma * 19, vol_c19=19, tv_s19=tvma * 19, tv_c19=19,
                rng_s19=0.03 * 19, rng_c19=19, mc_last=12e12, nbars_prev=600, base=0.12, blocked=False,
                npat_yoy=0.5, funda=True, pts_static=pts or dict(C1=10, C2=5, C3=0, A1=5, A2=0),
                hi52_249=13000.0, rs_prev=rs, mom_prev=mom, rmul=1.0)


def nen(ngay, ds):
    """ds: [(hhmm, gia, kl)] -> mang Vietcap."""
    t, h, l, c, v = [], [], [], [], []
    for hm, g, k in ds:
        ts = dt.datetime.fromisoformat(f'{ngay}T{hm // 100:02d}:{hm % 100:02d}:00').replace(tzinfo=TZ)
        t.append(int(ts.timestamp())); h.append(g); l.append(g); c.append(g); v.append(k)
    return dict(t=t, h=h, l=l, c=c, v=v)


class TrangThaiPhut(unittest.TestCase):
    def test_chi_nen_truoc_1425(self):
        x = nen(SES, [(900, 11950, 1000), (1100, 12300, 2000), (1424, 12750, 3000), (1425, 12800, 99999),
                      (1445, 12900, 5)])
        st = SP.trang_thai_phut(x['t'], x['h'], x['l'], x['c'], x['v'], SES, 1425)
        self.assertEqual(st[:5], [1424, 12750.0, 12750.0, 11950.0, 6000.0])
        self.assertEqual(st[5], 11950 * 1000 + 12300 * 2000 + 12750 * 3000)
        self.assertIsNone(SP.trang_thai_phut(x['t'], x['h'], x['l'], x['c'], x['v'], '2026-11-05', 1425))


class ChotPhien(unittest.TestCase):
    def setUp(self):
        self.old = os.getcwd(); self.tmp = tempfile.mkdtemp(); os.chdir(self.tmp)
        self._n = LS.nen_phut_vietcap

    def tearDown(self):
        os.chdir(self.old); LS.nen_phut_vietcap = self._n

    def _du_lieu(self):
        syms = {'TCH': dict(spec=sp_mau()), 'HAH': dict(spec=sp_mau(vma=1.0e6, tvma=45e9)),
                'VND': dict(spec=sp_mau(), dang_cam=True), 'XYZ': dict(spec=sp_mau())}
        fresh = {'TCH': dict(PriceHigh=12750, PriceBasic=11950, PriceClose=12750, AdjClose=12750),
                 'HAH': dict(PriceHigh=48900, PriceBasic=46200, PriceClose=48800, AdjClose=48800),
                 'VND': dict(PriceHigh=13950, PriceBasic=13050, PriceClose=13950, AdjClose=13950),
                 'XYZ': dict(PriceHigh=10100, PriceBasic=10000, PriceClose=10100, AdjClose=10100)}   # khong cham nguong
        bars = {'TCH': nen(SES, [(1000, 12100, 9e6), (1424, 12750, 9.4e6)]),                  # KL 18,4tr ~ 2,4x
                'HAH': nen(SES, [(1000, 46500, 1e5), (1424, 48650, 2e5)])}                       # KL that 0,3x
        goi = []
        LS.nen_phut_vietcap = lambda s, countback=420: (goi.append(s) or bars.get(s, {}))
        return syms, fresh, goi

    def test_chot_tch_bo_hah(self):
        syms, fresh, goi = self._du_lieu()
        rec = LS.chot_phien(CF, syms, fresh, SES, SES, dt.datetime(2026, 11, 4, 14, 26), True)
        self.assertEqual([x['sym'] for x in rec['xep']], ['TCH'])
        self.assertTrue(rec['xong']); self.assertEqual(rec['xep'][0]['gia'], 12750.0)
        self.assertEqual(sorted(goi), ['HAH', 'TCH'])          # VND dang cam, XYZ chua cham nguong: khong goi
        # luu vao live.json -> lan quet sau dung lai, KHONG tinh lai
        json.dump(dict(chot=rec), open('live.json', 'w'))
        LS.nen_phut_vietcap = lambda s, countback=420: self.fail('khong duoc goi lai')
        rec2 = LS.chot_phien(CF, syms, fresh, SES, SES, dt.datetime(2026, 11, 4, 14, 40), True)
        self.assertEqual(rec2, rec)

    def test_truoc_gio_chot_va_tat(self):
        syms, fresh, _ = self._du_lieu()
        self.assertIsNone(LS.chot_phien(CF, syms, fresh, SES, SES, dt.datetime(2026, 11, 4, 14, 24), True))
        self.assertIsNone(LS.chot_phien(dict(CF, chot_phut=None), syms, fresh, SES, SES,
                                        dt.datetime(2026, 11, 4, 14, 30), True))
        self.assertIsNone(LS.chot_phien(CF, syms, fresh, SES, SES, dt.datetime(2026, 11, 4, 14, 30), False))

    def test_loi_nguon_chua_xong(self):
        syms, fresh, _ = self._du_lieu()
        LS.nen_phut_vietcap = lambda s, countback=420: None
        rec = LS.chot_phien(CF, syms, fresh, SES, SES, dt.datetime(2026, 11, 4, 14, 26), True)
        self.assertFalse(rec['xong']); self.assertEqual(sorted(rec['loi']), ['HAH', 'TCH'])
        json.dump(dict(chot=rec), open('live.json', 'w'))
        self.assertIsNone(LS.doc_chot_cu(SES))                 # chua xong -> lan sau tinh lai


class ChuongChot(unittest.TestCase):
    def setUp(self):
        self.sent = []
        self._g = (LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh)
        LS.kenh_co = lambda: True
        LS.gui_tin = lambda text, **k: (self.sent.append(text) or True)
        LS.co_lenh = lambda *a, **k: (8.4, 8.4, [], 1068e6, 12.71e9)
        self.T = dict(asof='2026-11-03', cfg=CF, book=dict(positions=[]))

    def tearDown(self):
        LS.gio_vn, LS.kenh_co, LS.gui_tin, LS.co_lenh = self._g

    def h(self, sym, score, volr, **k):
        d = dict(sym=sym, score=score, volr=volr, level='SAP_DU', prod_ok=False, mua_do=True, dang_cam=False,
                 price=12.75, pct=6.7, mua_do_du_phong=False)
        d.update(k); return d

    def test_truoc_1425_khong_bao_mua(self):
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, 14, 10)
        hits = [self.h('ORS', 74, 2.5, cho_chot=1425)]
        LS.danh_dau_max_unconf(hits, self.T, SES, 3)
        LS.gui_telegram(hits, SES, set(), SES, 'DO', 0.8, self.T)
        self.assertFalse([x for x in self.sent if 'MUA DÒ' in x])

    def test_bao_chot_va_khong_mua_ma_khac(self):
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, 14, 26)
        hits = [self.h('ORS', 74, 2.5), self.h('TCH', 55, 2.4, chot=1424, chot_gia=12.75)]
        LS.danh_dau_max_unconf(hits, self.T, SES, 3, truoc=['TCH'])
        m = {x['sym']: x for x in hits}
        self.assertEqual(m['TCH']['uu_tien'], 1); self.assertEqual(m['ORS']['khong_mua'], 'max_unconf')
        cu = set()
        cu |= set(LS.gui_telegram(hits, SES, cu, SES, 'DO', 0.9, self.T) or [])
        self.assertEqual(len(self.sent), 1)
        self.assertIn('CHỐT MUA DÒ 14:25', self.sent[0]); self.assertIn('*TCH*', self.sent[0])
        self.assertIn('chốt 14:25* giá 12.75', self.sent[0]); self.assertIn('KHÔNG MUA', self.sent[0])
        self.assertIn('D:TCH', cu); self.assertNotIn('D:ORS', cu)
        # nhip sau: van giu TCH -> im lang
        n0 = len(self.sent)
        LS.gui_telegram(hits, SES, cu, SES, 'DO', 0.95, self.T)
        self.assertEqual(len(self.sent), n0)

    def test_khong_ai_du_luc_1425_bao_atc(self):
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, 14, 27)
        hits = [self.h('ORS', 74, 2.5, mua_do_du_phong=True, volr_proj_curve=2.3)]
        LS.danh_dau_max_unconf(hits, self.T, SES, 3, truoc=[])
        LS.gui_telegram(hits, SES, set(), SES, 'DO', 0.9, self.T)
        self.assertEqual(len(self.sent), 1)
        self.assertIn('không mã nào đủ lúc 14:25', self.sent[0]); self.assertIn('*ORS*', self.sent[0])

    def test_toi_ma_chot_dung_truoc_nhu_bo_may(self):
        # 04/11 neu co luat chot: TCH chot 14:25; toi HAH du DK1-8 (truot DK9, diem cao hon) -> TCH van #1
        LS.gio_vn = lambda: dt.datetime(2026, 11, 4, 16, 33)
        tch = self.h('TCH', 55.0, 3.09, level='MUA', prod_ok=True, mua_do=False, gtgd=268.9, ordimb=2.29,
                     ordimb_min=1.4)
        hah = self.h('HAH', 59.1, 2.10, mua_do=False, truot9=True, ordimb=1.06, ordimb_min=1.4)
        hits = [tch, hah]
        LS.danh_dau_max_unconf(hits, self.T, SES, 3, truoc=['TCH'])
        self.assertEqual((tch['uu_tien'], hah['uu_tien']), (1, 2)); self.assertNotIn('khong_mua', tch)
        LS.gui_telegram(hits, SES, {'D:TCH', 'G1:TCH'}, SES, 'DO', 1.0, self.T)
        txt = '\n'.join(self.sent)
        self.assertIn('GIỮ lệnh dò', txt); self.assertIn('*TCH*', txt)
        self.assertNotIn('CHỌN MÃ NÀY', txt)

    def test_ma_chot_rot_dk18_van_giu_luot(self):
        # ma chot toi khong con MUA/mua_do/truot9 (rot DK1-8, giu tren trang qua 'D:') -> van #1 (bo may da mua)
        hits = [self.h('TCH', 55.0, 1.5, mua_do=False), self.h('HAH', 59.1, 2.1, mua_do=False, truot9=True)]
        LS.danh_dau_max_unconf(hits, self.T, SES, 3, truoc=['TCH'])
        self.assertEqual(hits[0]['uu_tien'], 1); self.assertEqual(hits[1]['khong_mua'], 'max_unconf')


if __name__ == '__main__':
    unittest.main()
